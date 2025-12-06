# ai-driven-semantic-log-anomaly-detection
AI-driven semantic log anomaly detection project 

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Doppler CLI (for secrets management)

## 🔐 Doppler Secrets Management

This project uses [Doppler](https://www.doppler.com/) for secure secrets management. All sensitive configuration values (API keys, database URLs, etc.) are stored in Doppler and injected at runtime.

### Installing Doppler CLI

**macOS:**
```bash
brew install dopplerhq/cli/doppler
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt-get update && sudo apt-get install -y apt-transport-https ca-certificates curl gnupg
curl -sLf --retry 3 --tlsv1.2 --proto "=https" 'https://packages.doppler.com/public/cli/gpg.DE2A7741A397C129.key' | sudo gpg --dearmor -o /usr/share/keyrings/doppler-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/doppler-archive-keyring.gpg] https://packages.doppler.com/public/cli/deb/debian any-version main" | sudo tee /etc/apt/sources.list.d/doppler-cli.list
sudo apt-get update && sudo apt-get install doppler
```

**Other platforms:** See [Doppler CLI installation guide](https://docs.doppler.com/docs/install-cli)

### Setting Up Doppler

1. **Authenticate with Doppler:**
   ```bash
   doppler login
   ```

2. **Create a Doppler project:**
   ```bash
   doppler projects create ai-log-analytics
   ```

3. **Set up the project configuration:**
   ```bash
   doppler setup --project ai-log-analytics --config dev
   ```

4. **Add secrets to Doppler:**

   You can add secrets via the Doppler dashboard or CLI:

   ```bash
   # Add secrets via CLI
   doppler secrets set DATABASE_URL="postgresql://ailog:changeme@localhost:5432/ailog"
   doppler secrets set KAFKA_BOOTSTRAP_SERVERS="localhost:9092"
   doppler secrets set OPENAI_API_KEY="your-openai-api-key"
   doppler secrets set QDRANT_URL="your-qdrant-url"
   doppler secrets set QDRANT_API_KEY="your-qdrant-api-key"
   doppler secrets set LANGFUSE_SECRET_KEY="your-langfuse-secret-key"
   doppler secrets set LANGFUSE_PUBLIC_KEY="your-langfuse-public-key"
   doppler secrets set LANGFUSE_HOST="http://langfuse:3000"
   ```

   **Required secrets:**
   - `DATABASE_URL` - PostgreSQL connection string
   - `KAFKA_BOOTSTRAP_SERVERS` - Kafka bootstrap servers
   - `OPENAI_API_KEY` - OpenAI API key for embeddings (optional)
   - `QDRANT_URL` - Qdrant Cloud URL (optional)
   - `QDRANT_API_KEY` - Qdrant Cloud API key (optional)
   - `LANGFUSE_SECRET_KEY` - Langfuse secret key (optional)
   - `LANGFUSE_PUBLIC_KEY` - Langfuse public key (optional)
   - `LANGFUSE_HOST` - Langfuse host URL (optional)

### Using Doppler with the Application

Run the application with Doppler CLI to automatically inject secrets as environment variables:

**For Local Development:**
```bash
# Run FastAPI app with Doppler
doppler run -- uvicorn app.main:app --host 0.0.0.0 --port 8000

# Or with Docker Compose
doppler run -- docker-compose up
```

**For CI/CD (with DOPPLER_TOKEN):**
```bash
# Set DOPPLER_TOKEN environment variable, then:
doppler run --token=$DOPPLER_TOKEN -- docker-compose up
```

The application automatically loads secrets from environment variables injected by the Doppler CLI. No SDK or special code is needed - the Doppler CLI injects secrets as environment variables, which your application reads normally.

### Configuration Priority

The application loads configuration in the following order:
1. **Environment variables** (from Doppler CLI injection or direct env vars)
2. **`.env` file** (if present)
3. **Default values** (for development only)

### Running the Stack

**With Doppler (Recommended):**
```bash
cd infra
doppler run -- docker-compose up -d
```

**Without Doppler (uses defaults/.env):**
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
- **Mode**: KRaft (no Zookeeper required)
- **Topics**: `logs-raw`, `logs-processed`

**Kafka KRaft Setup:**

This project uses Apache Kafka in KRaft (Kafka Raft) mode, which eliminates the need for Zookeeper. KRaft mode provides:
- Simplified deployment (no Zookeeper dependency)
- Faster startup times
- Better scalability
- Self-managed metadata

**Topics are automatically created** when the stack starts via the `kafka-init` service. The initialization script creates:
- `logs-raw`: Raw log entries from Fluent Bit (3 partitions, 1 week retention)
- `logs-processed`: Processed log entries after PII redaction and normalization (3 partitions, 1 week retention)

**Kafka CLI Commands:**
```bash
# List all topics
docker exec -it ai-log-kafka kafka-topics.sh --bootstrap-server localhost:9092 --list

# Describe a topic
docker exec -it ai-log-kafka kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic logs-raw

# Consume messages from logs-raw topic
docker exec -it ai-log-kafka kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic logs-raw --from-beginning

# Consume messages from logs-processed topic
docker exec -it ai-log-kafka kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic logs-processed --from-beginning

# Produce a test message
docker exec -it ai-log-kafka kafka-console-producer.sh --bootstrap-server localhost:9092 --topic logs-raw
```

**Kafka Health Check:**
```bash
# Check Kafka health via API
curl http://localhost:8000/health/kafka
```

**Kafka Configuration:**
- **Replication Factor**: 1 (single node for development)
- **Partitions**: 3 per topic (for parallel processing)
- **Retention**: 7 days or 1GB per topic
- **Consumer Group**: `log-processor-group`

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