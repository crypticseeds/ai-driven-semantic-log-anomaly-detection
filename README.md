# ai-driven-semantic-log-anomaly-detection
AI-driven semantic log anomaly detection project 

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Doppler CLI (for secrets management)

### Running the Stack
```bash
cd infra
docker-compose up -d
```

## 📍 Service Endpoints

Once the services are running, you can access them at the following endpoints:

### Services Overview

| Service | Port | Web UI? | URL / Access |
|---------|------|---------|--------------|
| **FastAPI Backend** | 8000 | ✅ Yes | http://localhost:8000/docs |
| **Grafana** | 3001 | ✅ Yes | http://localhost:3001 (admin/admin) |
| **Prometheus** | 9090 | ✅ Yes | http://localhost:9090 |
| **Tempo** | 3200 | ❌ API only | `curl http://localhost:3200/ready` |
| **Kafka** | 9092 | ❌ Binary protocol | Use CLI (see below) |
| **PostgreSQL** | 5432 | ❌ Database protocol | Use psql (see below) |
| **Fluent Bit** | 2020 | ❌ Internal | Log forwarder (internal only) |

### API Endpoints

#### FastAPI Backend
- **Root**: `GET http://localhost:8000/`
- **Health Check**: `GET http://localhost:8000/health`
- **API Docs**: `GET http://localhost:8000/docs`
- **ReDoc**: `GET http://localhost:8000/redoc`

### Programmatic Access

#### Kafka (Message Broker)
- **Bootstrap Server**: `localhost:9092`
- **Main Topic**: `logs-raw`

**Kafka CLI Commands:**
```bash
# List all topics
docker exec -it ai-log-kafka kafka-topics.sh --bootstrap-server localhost:9092 --list

# Consume messages from logs-raw topic
docker exec -it ai-log-kafka kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic logs-raw --from-beginning

# Produce a test message
docker exec -it ai-log-kafka kafka-console-producer.sh --bootstrap-server localhost:9092 --topic logs-raw
```

#### PostgreSQL (Database)
- **Host**: `localhost`
- **Port**: `5432`
- **Database**: `ailog` (default)
- **User**: `ailog` (default)
- **Password**: `changeme` (default)
- **Connection String**: `postgresql://ailog:changeme@localhost:5432/ailog`

**PostgreSQL CLI:**
```bash
docker exec -it ai-log-postgres psql -U ailog -d ailog
```

#### Tempo (Distributed Tracing)
- **OTLP gRPC Endpoint**: `localhost:4317`
- **OTLP HTTP Endpoint**: `http://localhost:4318`
- **Tempo UI**: `http://localhost:3200`

### Container Management

**View running containers:**
```bash
docker ps
```

**View logs:**
```bash
docker-compose -f infra/docker-compose.yml logs -f [service-name]
```

**Stop all services:**
```bash
docker-compose -f infra/docker-compose.yml down
```

**Stop and remove volumes:**
```bash
docker-compose -f infra/docker-compose.yml down -v
```

## 📝 Resume Bullet Points (You Can Copy)
AI Log Analyzer (FastAPI, LLMs, OpenTelemetry, Streamlit, Qdrant)
Designed and implemented an AI-powered log-analysis platform capable of ingesting live system logs, detecting anomalies, and generating LLM-driven root-cause analysis.
Built semantic search using vector embeddings (OpenAI + Qdrant) enabling natural-language querying across large log datasets.
Implemented anomaly detection models using PyOD (IsolationForest) with structured log parsing and clustering.
Developed a full observability stack (OpenTelemetry + Grafana + Prometheus) for tracing, metrics, and pipeline insights.
Delivered an interactive Streamlit dashboard visualizing log trends, anomaly timelines, and on-demand AI summaries.