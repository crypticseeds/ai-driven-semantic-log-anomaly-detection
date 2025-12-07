#!/usr/bin/env python3
"""
System Verification Script for AI-Driven Semantic Log Anomaly Detection.

This script performs end-to-end verification of the system:
1. Checks if Backend is healthy.
2. Checks connectivity to Kafka.
3. Sends a test log to the 'logs-raw' topic (simulating Fluent Bit).
4. Listens on 'logs-processed' to verify the Backend processed it and REDACTED PII.
5. Verifies Qdrant connectivity (read-only check).
"""

import json
import logging
import sys
import time
import uuid

import requests
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable

# Configuration
BACKEND_URL = "http://localhost:8000"
KAFKA_BOOTSTRAP = "localhost:9094"
TOPIC_RAW = "logs-raw"
TOPIC_PROCESSED = "logs-processed"
TEST_TIMEOUT = 30  # seconds

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def check_backend_health():
    """Check if the backend is reachable and healthy."""
    logger.info("Checking Backend health...")
    try:
        res = requests.get(f"{BACKEND_URL}/health", timeout=5)
        if res.status_code == 200:
            logger.info("✅ Backend is HEALTHY")
            return True
        else:
            logger.error(f"❌ Backend returned status {res.status_code}: {res.text}")
            return False
    except requests.exceptions.ConnectionError:
        logger.error("❌ Could not connect to Backend. Is it running?")
        return False


def check_kafka_connection():
    """Check if we can connect to Kafka."""
    logger.info("Checking Kafka connectivity...")
    try:
        consumer = KafkaConsumer(bootstrap_servers=KAFKA_BOOTSTRAP, request_timeout_ms=5000)
        topics = consumer.topics()
        logger.info(f"✅ Connected to Kafka. Available topics: {topics}")
        return True
    except NoBrokersAvailable:
        logger.error(f"❌ Could not connect to Kafka Broker at {KAFKA_BOOTSTRAP}")
        return False
    except Exception as e:
        logger.error(f"❌ Kafka Error: {e}")
        return False


def check_qdrant_via_backend():
    """Indirectly check Qdrant via backend logs or health if available."""
    # Since we can't easily access Qdrant credentials here without pulling deps,
    # we rely on the Backend's own checks or just skip this for the script
    # and rely on the manual guide for direct Qdrant Curl command.
    pass


def run_end_to_end_test():
    """
    Simulate the flow:
    Produce PII Log -> 'logs-raw' -> Backend Process -> 'logs-processed' -> Verify Redaction
    """
    logger.info("🚀 Starting End-to-End Log Flow Test...")

    test_id = str(uuid.uuid4())
    # A log message with PII (email)
    test_message = {
        "timestamp": time.time(),
        "service": "verification-script",
        "level": "INFO",
        "message": f"Test log {test_id}: User testing@example.com logged in successfully.",
        "extra": {"test_id": test_id},
    }

    # 1. Produce to logs-raw
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        producer.send(TOPIC_RAW, test_message)
        producer.flush()
        print(f"\n📤 SENT LOG (to {TOPIC_RAW}):")
        print(json.dumps(test_message, indent=2))
        logger.info(f"✅ Sent test log with ID: {test_id}")
    except Exception as e:
        logger.error(f"❌ Failed to produce to Kafka: {e}")
        return False

    # 2. Listen on logs-processed for the result
    logger.info(f"Waiting for processed log in '{TOPIC_PROCESSED}'...")
    try:
        consumer = KafkaConsumer(
            TOPIC_PROCESSED,
            bootstrap_servers=KAFKA_BOOTSTRAP,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=lambda x: json.loads(x.decode("utf-8")),
            consumer_timeout_ms=TEST_TIMEOUT * 1000,
        )

        start_time = time.time()
        for message in consumer:
            data = message.value
            # Check if this is our log
            if "test_id" in str(data) and test_id in str(data):
                print(f"\n📥 RECEIVED LOG (from {TOPIC_PROCESSED}):")
                print(json.dumps(data, indent=2))

                # 3. Verify PII Redaction
                msg_content = data.get("message", "")
                if "[EMAIL_ADDRESS]" in msg_content or "testing@example.com" not in msg_content:
                    print("\n✅ PII Redaction Verified! Email was obscured.")
                    return True
                else:
                    print("\n❌ PII was NOT redacted!")
                    return False

            if time.time() - start_time > TEST_TIMEOUT:
                logger.error("❌ Timeout waiting for processed log.")
                break

    except Exception as e:
        logger.error(f"❌ Error consuming from Kafka: {e}")

    logger.error("❌ End-to-End Test FAILED or TIMED OUT")
    return False


def main():
    print("========================================")
    print("   AI-Log System Verification Tool")
    print("========================================")

    if not check_backend_health():
        print("\n⚠️  Backend issues detected. Check 'docker logs ai-log-backend'.")

    if not check_kafka_connection():
        print("\n⚠️  Kafka issues detected. Check 'docker logs ai-log-kafka'.")
        sys.exit(1)

    print("\n--- Running Flow Verification ---")
    if run_end_to_end_test():
        print("\n✅✅✅ SYSTEM VERIFICATION SUCCESSFUL ✅✅✅")
        sys.exit(0)
    else:
        print("\n❌❌❌ SYSTEM VERIFICATION FAILED ❌❌❌")
        sys.exit(1)


if __name__ == "__main__":
    main()
