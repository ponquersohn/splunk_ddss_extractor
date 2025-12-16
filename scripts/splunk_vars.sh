#!/bin/bash
# Splunk common variables
# Source this file in other Splunk-related scripts: source ./splunk_vars.sh

CONTAINER_NAME="${CONTAINER_NAME:-splunk-rehydrate}"
SPLUNK_PASSWORD="${SPLUNK_PASSWORD:-SplunkAdmin123!}"
HEC_ENDPOINT="${HEC_ENDPOINT:-https://localhost:8088/services/collector/event}"
INDEX_NAME="${INDEX_NAME:-test_index}"