import logging

from src.splunk_ddss_extractor.extractor import Extractor

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    extractor = Extractor()
    extractor.extract(
        # input_path="test_data/journal.gz",
        # input_path="test_data/net_firewall.zst",
        # input_path="test_data/journal.zst",
        input_path="test_data/new",
        # output_path="/tmp/output.gz",
        output_format="ndjson",
    )
    print("Extraction complete.")
