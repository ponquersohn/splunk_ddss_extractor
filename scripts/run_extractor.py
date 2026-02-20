import logging

from src.splunk_ddss_extractor.extractor import Extractor

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    extractor = Extractor()
    extractor.extract(
        # input_path="test_data/journal.gz",
        # input_path="test_data/net_firewall.zst",
        # input_path="test_data/journal.zst",
        input_path="s3://pepsec-f9ltd0x34cp8-splunk-archive-prod/net_firewall/net_firewall_traffic/db_1732593180_1732556924_10361_D1AC40DF-C971-47B3-9F20-3C35A27F33C9/rawdata/journal.zst",
        # output_path="/tmp/output.gz",
        output_format="ndjson",
    )
    # print("Extraction complete.")
