"""SQLAlchemy models for PostgreSQL."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class LogEntry(Base):
    """Log entry model."""

    __tablename__ = "log_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime, nullable=False, index=True)
    level = Column(String(20), nullable=False, index=True)
    service = Column(String(100), nullable=False, index=True)
    message = Column(Text, nullable=False)
    raw_log = Column(Text, nullable=False)
    log_metadata = Column(JSON, nullable=True)  # Renamed from 'metadata' (reserved in SQLAlchemy)
    pii_redacted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AnomalyResult(Base):
    """Anomaly detection result model."""

    __tablename__ = "anomaly_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    log_entry_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    anomaly_score = Column(Float, nullable=False)
    is_anomaly = Column(Boolean, default=False, nullable=False, index=True)
    detection_method = Column(String(50), nullable=False)  # HDBSCAN, IsolationForest, LOF
    cluster_id = Column(Integer, nullable=True, index=True)
    llm_reasoning = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ClusteringMetadata(Base):
    """HDBSCAN clustering metadata model."""

    __tablename__ = "clustering_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_id = Column(Integer, nullable=False, index=True)
    cluster_size = Column(Integer, nullable=False)
    cluster_centroid = Column(JSON, nullable=True)  # Vector coordinates
    representative_logs = Column(JSON, nullable=True)  # Sample log IDs
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
