"""Kafka consumer and producer service."""

import json
import logging
from collections.abc import Callable
from datetime import datetime

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


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
        self._initialize_consumer()
        self._initialize_producer()

    def _initialize_consumer(self):
        """Initialize Kafka consumer for logs-raw topic."""
        try:
            self.consumer = KafkaConsumer(
                "logs-raw",
                bootstrap_servers=settings.kafka_bootstrap_servers.split(","),
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="earliest",
                enable_auto_commit=True,
                group_id="log-processor-group",
                consumer_timeout_ms=1000,  # Timeout for polling
            )
            logger.info("Kafka consumer initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka consumer: {e}")
            self.consumer = None

    def _initialize_producer(self):
        """Initialize Kafka producer for logs-processed topic."""
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers.split(","),
                value_serializer=json_serializer,
                acks="all",  # Wait for all replicas
                retries=3,
            )
            logger.info("Kafka producer initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            self.producer = None

    def consume_messages(self, callback: Callable[[dict], None], max_messages: int | None = None):
        """Consume messages from logs-raw topic and call callback for each."""
        if not self.consumer:
            logger.error("Kafka consumer not initialized")
            return

        message_count = 0
        try:
            for message in self.consumer:
                try:
                    callback(message.value)
                    message_count += 1
                    if max_messages and message_count >= max_messages:
                        break
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error consuming messages: {e}")

    def produce_message(self, topic: str, value: dict) -> bool:
        """Produce message to Kafka topic."""
        if not self.producer:
            logger.error("Kafka producer not initialized")
            return False

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
        except KafkaError as e:
            logger.error(f"Failed to send message to Kafka: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending message: {e}")
            return False

    def close(self):
        """Close Kafka consumer and producer."""
        if self.consumer:
            self.consumer.close()
        if self.producer:
            self.producer.close()


# Global instance
kafka_service = KafkaService()
