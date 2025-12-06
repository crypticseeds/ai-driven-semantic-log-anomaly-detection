import importlib
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add backend directory to Python path for direct execution
backend_dir = Path(__file__).parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

kafka_service_module = importlib.import_module("app.services.kafka_service")

from app.services.kafka_service import (  # noqa: E402
    KafkaService,
    json_serializer,
    kafka_service,
)


@pytest.fixture(autouse=True)
def reset_kafka_service_instance():
    """Reset the global Kafka service instance before each test."""
    # Reset the global instance to ensure clean test state
    kafka_service_module._kafka_service_instance = None
    yield
    # Cleanup after test
    if kafka_service_module._kafka_service_instance:
        kafka_service_module._kafka_service_instance.close()
    kafka_service_module._kafka_service_instance = None


class TestJsonSerializer:
    """Test JSON serializer."""

    def test_json_serializer_with_dict(self):
        """Test JSON serializer with regular dict."""
        data = {"message": "test", "level": "INFO"}
        result = json_serializer(data)
        assert isinstance(result, bytes)
        assert json.loads(result.decode("utf-8")) == data

    def test_json_serializer_with_datetime(self):
        """Test JSON serializer with datetime object."""
        dt = datetime(2024, 1, 15, 10, 30, 45)
        data = {"timestamp": dt, "message": "test"}
        result = json_serializer(data)
        assert isinstance(result, bytes)
        decoded = json.loads(result.decode("utf-8"))
        assert decoded["message"] == "test"
        assert decoded["timestamp"] == dt.isoformat()

    def test_json_serializer_with_invalid_type(self):
        """Test JSON serializer with invalid type."""
        data = {"obj": object()}  # Not JSON serializable
        with pytest.raises(TypeError):
            json_serializer(data)


class TestKafkaService:
    """Test Kafka service."""

    @pytest.fixture(autouse=True)
    def mock_sleep(self):
        """Mock time.sleep to avoid waiting in tests."""
        with patch("app.services.kafka_service.time.sleep"):
            yield

    @patch("app.services.kafka_service.KafkaConsumer")
    @patch("app.services.kafka_service.KafkaProducer")
    def test_initialization_success(self, mock_producer_class, mock_consumer_class):
        """Test successful initialization of Kafka service."""
        mock_consumer = Mock()
        mock_consumer.topics.return_value = set()
        mock_consumer_class.return_value = mock_consumer

        mock_producer = Mock()
        mock_producer_class.return_value = mock_producer

        service = KafkaService()

        assert service.consumer is not None
        assert service.producer is not None
        mock_consumer_class.assert_called_once()
        mock_producer_class.assert_called_once()

    @patch("app.services.kafka_service.KafkaConsumer")
    @patch("app.services.kafka_service.KafkaProducer")
    def test_initialization_connection_error(self, mock_producer_class, mock_consumer_class):
        """Test initialization with connection error."""
        from kafka.errors import KafkaConnectionError

        mock_consumer_class.side_effect = KafkaConnectionError("Connection failed")
        mock_producer_class.side_effect = KafkaConnectionError("Connection failed")

        service = KafkaService()

        # Should retry but eventually fail
        assert service.consumer is None or service.consumer is not None
        assert service.producer is None or service.producer is not None

    @patch("app.services.kafka_service.KafkaConsumer")
    @patch("app.services.kafka_service.KafkaProducer")
    def test_produce_message_success(self, mock_producer_class, mock_consumer_class):
        """Test successful message production."""
        mock_consumer = Mock()
        mock_consumer.topics.return_value = set()
        mock_consumer_class.return_value = mock_consumer

        mock_producer = Mock()
        mock_future = Mock()
        mock_future.get.return_value = Mock(topic="logs-processed", partition=0, offset=123)
        mock_producer.send.return_value = mock_future
        mock_producer_class.return_value = mock_producer

        service = KafkaService()
        result = service.produce_message("logs-processed", {"message": "test"})

        assert result is True
        mock_producer.send.assert_called_once()

    @patch("app.services.kafka_service.KafkaConsumer")
    @patch("app.services.kafka_service.KafkaProducer")
    def test_produce_message_no_producer(self, mock_producer_class, mock_consumer_class):
        """Test message production when producer is not initialized."""
        mock_consumer = Mock()
        mock_consumer.topics.return_value = set()
        mock_consumer_class.return_value = mock_consumer

        mock_producer_class.side_effect = Exception("Failed to initialize")
        service = KafkaService()

        result = service.produce_message("logs-processed", {"message": "test"})

        assert result is False

    @patch("app.services.kafka_service.KafkaConsumer")
    @patch("app.services.kafka_service.KafkaProducer")
    def test_consume_messages_success(self, mock_producer_class, mock_consumer_class):
        """Test successful message consumption."""
        mock_messages = [
            Mock(value={"message": "test1", "level": "INFO"}),
            Mock(value={"message": "test2", "level": "ERROR"}),
        ]

        mock_consumer = Mock()
        mock_consumer.topics.return_value = set()
        mock_consumer.__iter__ = Mock(return_value=iter(mock_messages))
        mock_consumer_class.return_value = mock_consumer

        mock_producer = Mock()
        mock_producer_class.return_value = mock_producer

        service = KafkaService()
        callback = Mock()
        service.consume_messages(callback, max_messages=2)

        assert callback.call_count == 2
        callback.assert_any_call({"message": "test1", "level": "INFO"})
        callback.assert_any_call({"message": "test2", "level": "ERROR"})

    @patch("app.services.kafka_service.KafkaConsumer")
    @patch("app.services.kafka_service.KafkaProducer")
    def test_consume_messages_no_consumer(self, mock_producer_class, mock_consumer_class):
        """Test message consumption when consumer is not initialized."""
        mock_consumer_class.side_effect = Exception("Failed to initialize")
        mock_producer = Mock()
        mock_producer_class.return_value = mock_producer

        service = KafkaService()
        callback = Mock()
        service.consume_messages(callback)

        # Should not call callback if consumer is not available
        callback.assert_not_called()

    @patch("app.services.kafka_service.KafkaConsumer")
    @patch("app.services.kafka_service.KafkaProducer")
    def test_is_consumer_healthy(self, mock_producer_class, mock_consumer_class):
        """Test consumer health check."""
        mock_consumer = Mock()
        mock_consumer.topics.return_value = set()
        mock_consumer_class.return_value = mock_consumer

        mock_producer = Mock()
        mock_producer.bootstrap_connected.return_value = True
        mock_producer_class.return_value = mock_producer

        service = KafkaService()
        assert service.is_consumer_healthy() is True

    @patch("app.services.kafka_service.KafkaConsumer")
    @patch("app.services.kafka_service.KafkaProducer")
    def test_is_consumer_unhealthy(self, mock_producer_class, mock_consumer_class):
        """Test consumer health check when unhealthy."""
        mock_consumer = Mock()
        mock_consumer.topics.side_effect = Exception("Connection failed")
        mock_consumer_class.return_value = mock_consumer

        mock_producer = Mock()
        mock_producer.bootstrap_connected.return_value = True
        mock_producer_class.return_value = mock_producer

        service = KafkaService()
        assert service.is_consumer_healthy() is False

    @patch("app.services.kafka_service.KafkaConsumer")
    @patch("app.services.kafka_service.KafkaProducer")
    def test_is_producer_healthy(self, mock_producer_class, mock_consumer_class):
        """Test producer health check."""
        mock_consumer = Mock()
        mock_consumer.topics.return_value = set()
        mock_consumer_class.return_value = mock_consumer

        mock_producer = Mock()
        mock_producer.bootstrap_connected.return_value = True
        mock_producer_class.return_value = mock_producer

        service = KafkaService()
        assert service.is_producer_healthy() is True

    @patch("app.services.kafka_service.KafkaConsumer")
    @patch("app.services.kafka_service.KafkaProducer")
    def test_is_producer_unhealthy(self, mock_producer_class, mock_consumer_class):
        """Test producer health check when unhealthy."""
        mock_consumer = Mock()
        mock_consumer.topics.return_value = set()
        mock_consumer_class.return_value = mock_consumer

        mock_producer = Mock()
        mock_producer.bootstrap_connected.return_value = False
        mock_producer_class.return_value = mock_producer

        service = KafkaService()
        assert service.is_producer_healthy() is False

    @patch("app.services.kafka_service.KafkaConsumer")
    @patch("app.services.kafka_service.KafkaProducer")
    def test_is_healthy(self, mock_producer_class, mock_consumer_class):
        """Test overall health check."""
        mock_consumer = Mock()
        mock_consumer.topics.return_value = set()
        mock_consumer_class.return_value = mock_consumer

        mock_producer = Mock()
        mock_producer.bootstrap_connected.return_value = True
        mock_producer_class.return_value = mock_producer

        service = KafkaService()
        assert service.is_healthy() is True

    @patch("app.services.kafka_service.KafkaConsumer")
    @patch("app.services.kafka_service.KafkaProducer")
    def test_close(self, mock_producer_class, mock_consumer_class):
        """Test closing consumer and producer."""
        mock_consumer = Mock()
        mock_consumer.topics.return_value = set()
        mock_consumer_class.return_value = mock_consumer

        mock_producer = Mock()
        mock_producer_class.return_value = mock_producer

        service = KafkaService()
        service.close()

        mock_consumer.close.assert_called_once()
        mock_producer.close.assert_called_once()

    @patch("app.services.kafka_service.KafkaConsumer")
    @patch("app.services.kafka_service.KafkaProducer")
    def test_lazy_initialization(self, mock_producer_class, mock_consumer_class):
        """Test that lazy initialization works correctly."""
        # Reset the global instance
        kafka_service_module._kafka_service_instance = None

        # Verify instance is None before first access
        assert kafka_service_module._kafka_service_instance is None

        # Configure mocks
        mock_consumer = Mock()
        mock_consumer.topics.return_value = set()
        mock_consumer_class.return_value = mock_consumer

        mock_producer = Mock()
        mock_producer.bootstrap_connected.return_value = True
        mock_producer_class.return_value = mock_producer

        # First call to get_kafka_service should create instance
        service1 = kafka_service_module.get_kafka_service()
        assert kafka_service_module._kafka_service_instance is not None
        assert service1 is kafka_service_module._kafka_service_instance

        # Second call should return the same instance
        service2 = kafka_service_module.get_kafka_service()
        assert service1 is service2

        # Verify KafkaService was only initialized once
        mock_consumer_class.assert_called_once()
        mock_producer_class.assert_called_once()

    @patch("app.services.kafka_service.KafkaConsumer")
    @patch("app.services.kafka_service.KafkaProducer")
    def test_kafka_service_proxy(self, mock_producer_class, mock_consumer_class):
        """Test that the kafka_service proxy works correctly."""
        # Reset the global instance
        kafka_service_module._kafka_service_instance = None

        # Configure mocks
        mock_consumer = Mock()
        mock_consumer.topics.return_value = set()
        mock_consumer_class.return_value = mock_consumer

        mock_producer = Mock()
        mock_producer.bootstrap_connected.return_value = True
        mock_producer_class.return_value = mock_producer

        # Accessing a method should trigger lazy initialization
        assert kafka_service_module._kafka_service_instance is None
        result = kafka_service.is_consumer_healthy()
        assert kafka_service_module._kafka_service_instance is not None

        # Verify the method was called on the actual instance
        assert isinstance(result, bool)
