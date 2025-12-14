import logging

from src.splunk_ddss_extractor.extractor import Extractor

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    extractor = Extractor()
    extractor.extract(
        # input_path="test_data/journal.gz",
        input_path="test_data/net_firewall.zst",
        # input_path="test_data/journal.zst",
        # input_path="s3://pepsec-f9ltd0x34cp8-splunk-archive-prod/net_firewall/net_firewall_traffic/db_1732400452_1732364903_2909_1924563A-FB56-4A10-BF25-99F01B29FD02/rawdata/journal.zst",
        output_path="/tmp/output.gz",
        output_format="ndjson",
    )
    print("Extraction complete.")
