#!/bin/bash
# Recreate Splunk Docker container with HEC enabled
# Usage: ./recreate_splunk

set -e

# Get script directory for sourcing vars
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/splunk_vars.sh"

echo "Recreating Splunk container: $CONTAINER_NAME"
echo ""

# Clean up any existing container
echo "[1/5] Cleaning up existing container..."
docker stop $CONTAINER_NAME 2>/dev/null || true
docker rm $CONTAINER_NAME 2>/dev/null || true

# Start Splunk container with HEC port exposed
echo "[2/5] Starting Splunk container..."
docker run -d \
  --name $CONTAINER_NAME \
  -p 8000:8000 \
  -p 8088:8088 \
  -p 8089:8089 \
  -e SPLUNK_START_ARGS='--accept-license' \
  -e SPLUNK_PASSWORD="$SPLUNK_PASSWORD" \
  -e SPLUNK_GENERAL_TERMS='--accept-sgt-current-at-splunk-com' \
  splunk/splunk:latest

# Wait for Splunk to be ready
echo "[3/5] Waiting for Splunk to start (this takes 2-3 minutes)..."
for i in {1..60}; do
  # Use timeout to prevent hanging (10 second limit per check)
  if timeout 10 docker exec -u splunk $CONTAINER_NAME /opt/splunk/bin/splunk status 2>/dev/null | grep -q "splunkd is running"; then
    echo "Splunk is ready!"
    break
  fi
  echo -n "."
  sleep 5
done
echo ""

# Create test index
echo "[4/5] Creating index: $INDEX_NAME..."
timeout 30 docker exec -u splunk $CONTAINER_NAME /opt/splunk/bin/splunk add index $INDEX_NAME -auth admin:$SPLUNK_PASSWORD 2>&1 || echo "Index may already exist"

# Enable HEC and create token
echo "[5/5] Enabling HEC and creating token..."
timeout 30 docker exec -u splunk $CONTAINER_NAME /opt/splunk/bin/splunk http-event-collector enable -uri https://localhost:8089 -auth admin:$SPLUNK_PASSWORD 2>&1

# Create or update HEC token with proper configuration
echo "Configuring HEC token for index: $INDEX_NAME..."
HEC_TOKEN=$(timeout 30 docker exec -u splunk $CONTAINER_NAME /opt/splunk/bin/splunk http-event-collector create default-token -uri https://localhost:8089 -auth admin:$SPLUNK_PASSWORD 2>&1 | grep -oP 'token=\K[a-f0-9-]+' || echo "")

if [ -z "$HEC_TOKEN" ]; then
  echo "Token may already exist, attempting to retrieve it..."
  HEC_TOKEN=$(docker exec -u splunk $CONTAINER_NAME grep -h 'token =' /opt/splunk/etc/apps/*/local/inputs.conf 2>/dev/null | head -1 | cut -d '=' -f2 | tr -d ' \r\n')
fi

if [ -n "$HEC_TOKEN" ]; then
  echo "HEC Token: $HEC_TOKEN"

  # Configure the HEC inputs.conf to use the correct index
  docker exec -u root $CONTAINER_NAME /bin/bash -c "cat > /opt/splunk/etc/apps/splunk_httpinput/local/inputs.conf << EOF
[http]
disabled = 0
useIndexedAck = false

[http://default-token]
disabled = 0
token = $HEC_TOKEN
index = $INDEX_NAME
indexes = $INDEX_NAME
EOF
chown splunk:splunk /opt/splunk/etc/apps/splunk_httpinput/local/inputs.conf
"

  echo "HEC configured to use index: $INDEX_NAME"
else
  echo "Warning: Could not configure HEC token"
fi

echo ""
echo "✓ Splunk container recreated successfully!"
echo "  Web UI:  http://localhost:8000 (admin / $SPLUNK_PASSWORD)"
echo "  HEC:     https://localhost:8088/services/collector/event"
echo "  Index:   $INDEX_NAME"