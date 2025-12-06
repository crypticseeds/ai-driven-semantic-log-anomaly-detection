#!/bin/bash
# Initialize Kafka topics for the log ingestion pipeline
# This script creates the required topics: logs-raw and logs-processed

set -e

BOOTSTRAP_SERVER="${KAFKA_BOOTSTRAP_SERVER:-localhost:9092}"
KAFKA_BIN="/opt/kafka/bin"

echo "Waiting for Kafka to be ready..."
# Wait for Kafka to be available
for i in {1..30}; do
    if $KAFKA_BIN/kafka-broker-api-versions.sh --bootstrap-server $BOOTSTRAP_SERVER > /dev/null 2>&1; then
        echo "Kafka is ready!"
        break
    fi
    echo "Waiting for Kafka... ($i/30)"
    sleep 2
done

# Check if Kafka is available
if ! $KAFKA_BIN/kafka-broker-api-versions.sh --bootstrap-server $BOOTSTRAP_SERVER > /dev/null 2>&1; then
    echo "ERROR: Kafka is not available at $BOOTSTRAP_SERVER"
    exit 1
fi

echo "Creating Kafka topics..."

# Create logs-raw topic (for raw log entries from Fluent Bit)
$KAFKA_BIN/kafka-topics.sh \
    --bootstrap-server $BOOTSTRAP_SERVER \
    --create \
    --if-not-exists \
    --topic logs-raw \
    --partitions 3 \
    --replication-factor 1 \
    --config retention.ms=604800000 \
    --config retention.bytes=1073741824

echo "✓ Created topic: logs-raw"

# Create logs-processed topic (for processed log entries)
$KAFKA_BIN/kafka-topics.sh \
    --bootstrap-server $BOOTSTRAP_SERVER \
    --create \
    --if-not-exists \
    --topic logs-processed \
    --partitions 3 \
    --replication-factor 1 \
    --config retention.ms=604800000 \
    --config retention.bytes=1073741824

echo "✓ Created topic: logs-processed"

echo ""
echo "Listing all topics:"
$KAFKA_BIN/kafka-topics.sh --bootstrap-server $BOOTSTRAP_SERVER --list

echo ""
echo "Topic initialization complete!"
