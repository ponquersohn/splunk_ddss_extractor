#!/usr/bin/env python3
"""
ECS Task Script - Process Splunk archives from SQS queue

This script:
1. Polls SQS queue for S3 event notifications
2. Downloads journal files from S3
3. Extracts events using splunk_archiver module
4. Writes raw output to S3
5. Deletes message from SQS on success
"""

import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from splunk_ddss_extractor.extractor import extract_to_file
from splunk_ddss_extractor.utils import setup_logging, parse_s3_event


def get_env_var(name: str, default: Optional[str] = None) -> str:
    """Get environment variable with optional default"""
    value = os.environ.get(name, default)
    if value is None:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def process_message(
    s3_client,
    sqs_client,
    bucket: str,
    queue_url: str,
    output_prefix: str,
    output_format: str,
    output_compress: bool,
    message: dict
) -> bool:
    """
    Process a single SQS message

    Returns True if successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    receipt_handle = message["ReceiptHandle"]

    try:
        # Parse S3 event from message
        body = json.loads(message["Body"])

        # SNS wraps the S3 event
        if "Message" in body:
            s3_event = json.loads(body["Message"])
        else:
            s3_event = body

        # Extract S3 object info
        if "Records" not in s3_event:
            logger.error(f"Invalid S3 event format: {s3_event}")
            return False

        for record in s3_event["Records"]:
            s3_info = record.get("s3", {})
            source_key = s3_info.get("object", {}).get("key")

            if not source_key:
                logger.error(f"No object key in record: {record}")
                continue

            logger.info(f"Processing: s3://{bucket}/{source_key}")

            # Download journal file to temp location
            with tempfile.TemporaryDirectory() as tmpdir:
                local_path = Path(tmpdir) / "journal.zst"

                logger.debug(f"Downloading to {local_path}")
                s3_client.download_file(bucket, source_key, str(local_path))

                # Extract events
                output_file = Path(tmpdir) / f"output.{output_format}"
                logger.info(f"Extracting events to {output_file}")

                event_count = extract_to_file(
                    str(local_path),
                    str(output_file),
                    output_format=output_format,
                    compress=output_compress
                )

                logger.info(f"Extracted {event_count} events")

                # Upload to S3
                # Generate output key based on source key
                source_name = Path(source_key).stem
                if source_name.endswith(".journal"):
                    source_name = source_name[:-8]

                output_key = f"{output_prefix}{source_name}.{output_format}"

                logger.info(f"Uploading to s3://{bucket}/{output_key}")
                s3_client.upload_file(
                    str(output_file),
                    bucket,
                    output_key,
                    ExtraArgs={
                        "Metadata": {
                            "source_key": source_key,
                            "event_count": str(event_count),
                            "processed_by": "splunk-archiver"
                        }
                    }
                )

        # Delete message from queue on success
        logger.debug(f"Deleting message from queue")
        sqs_client.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=receipt_handle
        )

        return True

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        return False


def main():
    """Main processing loop"""
    # Setup logging
    log_level = get_env_var("LOG_LEVEL", "INFO")
    logger = setup_logging(log_level)

    # Get configuration
    aws_region = get_env_var("AWS_REGION", "us-east-1")
    bucket = get_env_var("S3_BUCKET")
    queue_url = get_env_var("SQS_QUEUE_URL")
    output_prefix = get_env_var("OUTPUT_PREFIX", "raw_archive/new/")
    output_format = get_env_var("OUTPUT_FORMAT", "json")
    output_compress_str = get_env_var("OUTPUT_COMPRESS", "true")
    output_compress = output_compress_str.lower() in ("true", "1", "yes")
    archive_name = get_env_var("ARCHIVE_NAME", "unknown")

    logger.info("Starting Splunk Archiver Processor")
    logger.info(f"Archive: {archive_name}")
    logger.info(f"Region: {aws_region}")
    logger.info(f"Bucket: {bucket}")
    logger.info(f"Queue: {queue_url}")
    logger.info(f"Output prefix: {output_prefix}")
    logger.info(f"Output format: {output_format}")
    logger.info(f"Output compress: {output_compress}")

    # Initialize AWS clients
    s3_client = boto3.client("s3", region_name=aws_region)
    sqs_client = boto3.client("sqs", region_name=aws_region)

    # Main processing loop
    empty_receives = 0
    max_empty_receives = 10

    while True:
        try:
            # Receive messages from SQS
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,  # Process one at a time
                WaitTimeSeconds=20,     # Long polling
                VisibilityTimeout=900   # 15 minutes
            )

            messages = response.get("Messages", [])

            if not messages:
                empty_receives += 1
                logger.debug(f"No messages ({empty_receives}/{max_empty_receives})")

                if empty_receives >= max_empty_receives:
                    logger.info("No messages for extended period, exiting")
                    break

                continue

            # Reset counter on message receive
            empty_receives = 0

            # Process each message
            for message in messages:
                success = process_message(
                    s3_client,
                    sqs_client,
                    bucket,
                    queue_url,
                    output_prefix,
                    output_format,
                    output_compress,
                    message
                )

                if not success:
                    logger.warning("Message processing failed, will retry")

        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
            break

        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
            time.sleep(5)  # Brief pause before retrying

    logger.info("Processor shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
