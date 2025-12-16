#!/bin/bash

# This script gets hec token from $CONTAINER_NAME container and uses it to send STDIN events to HEC endpoint

# Get script directory for sourcing vars
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/splunk_vars.sh"

# Get HEC token from container
HEC_TOKEN=$(
    docker exec -u splunk $CONTAINER_NAME /bin/bash -c "
        grep -h 'token =' /opt/splunk/etc/apps/*/local/inputs.conf /opt/splunk/etc/system/local/inputs.conf 2>/dev/null | head -1 | cut -d '=' -f2 | tr -d ' '
    " 2>/dev/null | tr -d '\r\n'
)

if [ -z "$HEC_TOKEN" ]; then
    echo "Error: Could not retrieve HEC token from container" >&2
    exit 1
fi

echo "Using HEC token: ${HEC_TOKEN:0:10}..." >&2

# Read from stdin and send each line to HEC using curl directly
counter=0

while IFS= read -r line; do
    # Send directly to HEC endpoint (port 8088 is now exposed)
    response=$(curl -k -s -w '\n%{http_code}' \
        -H "Authorization: Splunk $HEC_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$line" \
        "$HEC_ENDPOINT" 2>/dev/null)

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" != "200" ]; then
        echo "Error: HTTP $http_code - $body" >&2
    else
        counter=$((counter + 1))
        echo "Sent event $counter: $(echo "$line" | cut -c1-60)..." >&2
    fi
done

echo "Total events sent: $counter" >&2
