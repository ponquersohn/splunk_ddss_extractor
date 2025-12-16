#!/bin/bash
# Simple Splunk Rehydration Script
# Usage: ./splunk_rehydrate.sh <journal_file.zst> [index_name] [output_file]

# set -e

# Get script directory for sourcing vars
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/splunk_vars.sh"

JOURNAL_FILE="${1:?Usage: $0 <journal_file> [index_name] [output_file]}"
INDEX_NAME="${2:-$INDEX_NAME}"
OUTPUT_FILE="${3:-splunk_output.json}"

echo "Starting Splunk rehydration..."
echo "Journal: $JOURNAL_FILE"
echo "Index: $INDEX_NAME"
echo "Output: $OUTPUT_FILE"
echo ""

# Recreate Splunk container with HEC
# echo "[1/3] Recreating Splunk container..."
# "$SCRIPT_DIR/recreate_splunk"
echo ""

# Create thawed bucket and copy journal
echo "[2/3] Restoring archived data to thawed directory..."
BUCKET_NAME="db_9999999999_0_1"
THAWED_PATH="/opt/splunk/var/lib/splunk/$INDEX_NAME/thaweddb/$BUCKET_NAME"

# Determine journal extension
JOURNAL_EXT=$(echo "$JOURNAL_FILE" | sed 's/.*\(\.zst\|\.gz\)$/\1/')
if [[ "$JOURNAL_EXT" == "$JOURNAL_FILE" ]]; then
  JOURNAL_EXT=""  # No extension (uncompressed)
fi

docker exec -u splunk $CONTAINER_NAME mkdir -p $THAWED_PATH/rawdata
docker cp "$JOURNAL_FILE" $CONTAINER_NAME:/tmp/temp_journal
docker exec -u root $CONTAINER_NAME chown splunk:splunk /tmp/temp_journal
docker exec -u splunk $CONTAINER_NAME mv /tmp/temp_journal $THAWED_PATH/rawdata/journal$JOURNAL_EXT
docker exec -u root $CONTAINER_NAME chown -R splunk:splunk /opt/splunk/var/lib/splunk/$INDEX_NAME/thaweddb

echo "Journal file copied as: journal$JOURNAL_EXT"

# Restart Splunk to discover thawed data
echo "[3/3] Rebuild and restart Splunk to discover thawed data..."
#
docker exec -u splunk $CONTAINER_NAME /opt/splunk/bin/splunk rebuild /opt/splunk/var/lib/splunk/$INDEX_NAME/thaweddb/$BUCKET_NAME $INDEX_NAMEyy
docker exec -u splunk $CONTAINER_NAME /opt/splunk/bin/splunk restart 2>&1 | tail -5
sleep 20

# Search and export
echo "Searching and exporting events..."
docker exec -u splunk $CONTAINER_NAME /opt/splunk/bin/splunk search \
  "search index=$INDEX_NAME earliest=0 | fields + _* | head 10000" \
  -auth admin:$SPLUNK_PASSWORD \
  -output json > "$OUTPUT_FILE" 2>/dev/null

# Count events
EVENT_COUNT=$(cat "$OUTPUT_FILE" | grep -v "lastrow" | grep -c "{" || echo "0")
