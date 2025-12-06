"""Kafka consumer and producer service."""

import json
import logging
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaConnectionError, KafkaError, KafkaTimeoutError

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
CONNECTION_RETRY_DELAY = 5  # seconds for connection errors


def json_serializer(obj: dict) -> bytes:
    """JSON serializer that handles datetime objects."""

    def default_encoder(o):
        if isinstance(o, datetime):
            return o.isoformat()
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    return json.dumps(obj, default=default_encoder).encode("utf-8")


class KafkaService:
    """Kafka service for consuming and producing log messages."""

    def __init__(self):
        """Initialize Kafka consumer and producer."""
        self.consumer: KafkaConsumer | None = None
        self.producer: KafkaProducer | None = None
        self._consumer_retry_count = 0
        self._producer_retry_count = 0
        self._initialize_consumer()
        self._initialize_producer()

    def _initialize_consumer(self, retry: bool = False):
        """Initialize Kafka consumer for logs-raw topic with retry logic."""
        if retry:
            self._consumer_retry_count += 1
            if self._consumer_retry_count > MAX_RETRIES:
                logger.error("Max retries reached for consumer initialization")
                return
            logger.info(
                f"Retrying consumer initialization (attempt {self._consumer_retry_count}/{MAX_RETRIES})"
            )
            time.sleep(CONNECTION_RETRY_DELAY)

        try:
            self.consumer = KafkaConsumer(
                "logs-raw",
                bootstrap_servers=settings.kafka_bootstrap_servers.split(","),
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                group_id="log-processor-group",
                consumer_timeout_ms=1000,  # Timeout for polling
                api_version=(0, 10, 1),  # Specify API version for compatibility
            )
            # Test the connection
            self.consumer.topics()
            logger.info("Kafka consumer initialized successfully")
            self._consumer_retry_count = 0
        except (KafkaConnectionError, KafkaTimeoutError) as e:
            logger.warning(f"Kafka connection error during consumer initialization: {e}")
            self.consumer = None
            if not retry:
                self._initialize_consumer(retry=True)
        except Exception as e:
            logger.error(f"Failed to initialize Kafka consumer: {e}")
            self.consumer = None

    def _initialize_producer(self, retry: bool = False):
        """Initialize Kafka producer for logs-processed topic with retry logic."""
        if retry:
            self._producer_retry_count += 1
            if self._producer_retry_count > MAX_RETRIES:
                logger.error("Max retries reached for producer initialization")
                return
            logger.info(
                f"Retrying producer initialization (attempt {self._producer_retry_count}/{MAX_RETRIES})"
            )
            time.sleep(CONNECTION_RETRY_DELAY)

        try:
            self.producer = KafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers.split(","),
                value_serializer=json_serializer,
                acks="all",  # Wait for all replicas
                retries=3,
                max_in_flight_requests_per_connection=1,  # Ensure ordering
                api_version=(0, 10, 1),  # Specify API version for compatibility
            )
            logger.info("Kafka producer initialized successfully")
            self._producer_retry_count = 0
        except (KafkaConnectionError, KafkaTimeoutError) as e:
            logger.warning(f"Kafka connection error during producer initialization: {e}")
            self.producer = None
            if not retry:
                self._initialize_producer(retry=True)
        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            self.producer = None

    def _reconnect_consumer(self):
        """Attempt to reconnect the consumer."""
        logger.info("Attempting to reconnect Kafka consumer...")
        if self.consumer:
            with suppress(Exception):
                self.consumer.close()
        self.consumer = None
        self._consumer_retry_count = 0
        self._initialize_consumer()

    def _reconnect_producer(self):
        """Attempt to reconnect the producer."""
        logger.info("Attempting to reconnect Kafka producer...")
        if self.producer:
            with suppress(Exception):
                self.producer.close()
        self.producer = None
        self._producer_retry_count = 0
        self._initialize_producer()

    def consume_messages(self, callback: Callable[[dict], None], max_messages: int | None = None):
        """Consume messages from logs-raw topic and call callback for each."""
        if not self.consumer:
            logger.warning("Kafka consumer not initialized, attempting to reconnect...")
            self._reconnect_consumer()
            if not self.consumer:
                logger.error("Kafka consumer still not available")
                return

        message_count = 0
        retry_count = 0
        try:
            for message in self.consumer:
                try:
                    callback(message.value)
                    message_count += 1
                    retry_count = 0  # Reset retry count on successful message
                    if max_messages and message_count >= max_messages:
                        break
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    continue
        except (KafkaConnectionError, KafkaTimeoutError) as e:
            logger.warning(f"Kafka connection error while consuming: {e}")
            retry_count += 1
            if retry_count <= MAX_RETRIES:
                time.sleep(CONNECTION_RETRY_DELAY)
                self._reconnect_consumer()
            else:
                logger.error("Max retries reached for consumer reconnection")
        except Exception as e:
            logger.error(f"Unexpected error consuming messages: {e}")

    def produce_message(self, topic: str, value: dict, retry: bool = True) -> bool:
        """Produce message to Kafka topic with retry logic."""
        if not self.producer:
            logger.warning("Kafka producer not initialized, attempting to reconnect...")
            self._reconnect_producer()
            if not self.producer:
                logger.error("Kafka producer still not available")
                return False

        for attempt in range(MAX_RETRIES + 1):
            try:
                future = self.producer.send(topic, value=value)
                # Wait for the message to be sent
                record_metadata = future.get(timeout=10)
                logger.debug(
                    f"Message sent to {record_metadata.topic} "
                    f"partition {record_metadata.partition} "
                    f"offset {record_metadata.offset}"
                )
                return True
            except (KafkaConnectionError, KafkaTimeoutError) as e:
                if attempt < MAX_RETRIES and retry:
                    logger.warning(
                        f"Kafka connection error (attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                    )
                    time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
                    self._reconnect_producer()
                    continue
                else:
                    logger.error(
                        f"Failed to send message to Kafka after {MAX_RETRIES} retries: {e}"
                    )
                    return False
            except KafkaError as e:
                logger.error(f"Kafka error sending message: {e}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error sending message: {e}")
                return False

        return False

    def is_consumer_healthy(self) -> bool:
        """Check if Kafka consumer is healthy."""
        if not self.consumer:
            return False
        try:
            # Try to get topics to verify connection (same method used in initialization)
            self.consumer.topics()
            return True
        except Exception:
            return False

    def is_producer_healthy(self) -> bool:
        """Check if Kafka producer is healthy."""
        if not self.producer:
            return False
        try:
            # Check if producer is connected to bootstrap servers
            # bootstrap_connected() returns True if connected to at least one broker
            return self.producer.bootstrap_connected()
        except Exception:
            return False

    def is_healthy(self) -> bool:
        """Check if both consumer and producer are healthy."""
        return self.is_consumer_healthy() and self.is_producer_healthy()

    def close(self):
        """Close Kafka consumer and producer."""
        if self.consumer:
            self.consumer.close()
        if self.producer:
            self.producer.close()


# Global instance
kafka_service = KafkaService()
