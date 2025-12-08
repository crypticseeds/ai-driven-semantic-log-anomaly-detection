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
   doppler secrets set OPENAI_BUDGET="10.0"  # Daily budget in USD (optional)
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
   - `OPENAI_BUDGET` - Daily budget limit for OpenAI embeddings in USD (optional, default: unlimited)
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
- **Health Check (Kafka)**: `GET http://localhost:8000/health/kafka`
- **API Docs**: `GET http://localhost:8000/docs`
- **ReDoc**: `GET http://localhost:8000/redoc`
- **Log Search**: `GET http://localhost:8000/api/v1/logs/search`
- **Get Log by ID**: `GET http://localhost:8000/api/v1/logs/{log_id}`
- **Run Clustering**: `POST http://localhost:8000/api/v1/logs/clustering/run`
- **List Clusters**: `GET http://localhost:8000/api/v1/logs/clustering/clusters`
- **Get Outliers**: `GET http://localhost:8000/api/v1/logs/clustering/outliers`
- **Detect Anomalies (IsolationForest)**: `POST http://localhost:8000/api/v1/logs/anomaly-detection/isolation-forest`
- **Detect Anomalies (Z-score)**: `POST http://localhost:8000/api/v1/logs/anomaly-detection/z-score`
- **Detect Anomalies (IQR)**: `POST http://localhost:8000/api/v1/logs/anomaly-detection/iqr`
- **Score Log Entry**: `POST http://localhost:8000/api/v1/logs/anomaly-detection/score/{log_id}`

#### Agent API Endpoints (LangChain Tools)

The agent API endpoints provide programmatic access to LLM reasoning capabilities through LangChain tool wrappers. These endpoints enable integration with agent executors and provide enhanced root cause analysis.

- **Analyze Anomaly**: `POST http://localhost:8000/api/v1/agent/analyze-anomaly`
  - Analyzes a log message with optional root cause analysis
  - Parameters: `log_message` (required), `log_level`, `log_service`, `include_root_cause` (default: true)
  - Returns: Structured analysis with explanation, root causes, remediation steps, and severity

- **Analyze Anomaly by ID**: `POST http://localhost:8000/api/v1/agent/analyze-anomaly/{log_id}`
  - Analyzes a specific log entry by UUID with optional cluster context
  - Parameters: `include_root_cause` (default: true), `use_cluster_context` (default: true)
  - Returns: Enhanced analysis with cluster comparison if available

- **Detect Anomaly**: `POST http://localhost:8000/api/v1/agent/detect-anomaly`
  - Detects if a log entry is anomalous using LLM classification
  - Parameters: `log_message` (required), `log_level`, `log_service`
  - Returns: Detection result with `is_anomaly`, `confidence`, and `reasoning`

- **Stream Analysis**: `POST http://localhost:8000/api/v1/agent/analyze-anomaly/stream`
  - Streaming endpoint for real-time analysis results
  - Parameters: Same as analyze-anomaly endpoint
  - Returns: Server-Sent Events (SSE) stream with analysis results

- **List Agent Tools**: `GET http://localhost:8000/api/v1/agent/tools`
  - Lists all available agent tools with descriptions and parameters
  - Returns: JSON array of tool definitions

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

#### OpenAI Budget Management

The system includes built-in budget enforcement for OpenAI API usage to control costs and prevent unexpected spending.

**Features:**
- **Daily Budget Limit**: Set a daily spending limit via `OPENAI_BUDGET` environment variable
- **Automatic Tracking**: Daily spending is automatically tracked and reset at midnight UTC
- **Budget Enforcement**: Requests are rejected when the daily budget is exceeded
- **Cost Estimation**: Estimates cost before making API calls to prevent budget overruns
- **Warning Thresholds**: Logs warnings when spending reaches 80% of budget
- **Prometheus Metrics**: Budget metrics exposed for monitoring (`openai_daily_spending_usd`, `openai_budget_exceeded_total`)
- **Cache-Aware**: Cached embeddings don't count toward the budget

**Configuration:**
```bash
# Set daily budget to $10 USD
doppler secrets set OPENAI_BUDGET="10.0"

# Or via environment variable
export OPENAI_BUDGET=10.0
```

**Budget Behavior:**
- Budget resets automatically at midnight UTC each day
- If budget is not set (or set to `None`), spending is unlimited
- When budget is exceeded, embedding requests return HTTP 429 (Too Many Requests)
- Budget tracking persists across service restarts (in-memory, resets on restart)
- For production, consider using Redis or a database for persistent budget tracking

**Monitoring:**
- View current daily spending: Prometheus metric `openai_daily_spending_usd`
- Track budget rejections: Prometheus counter `openai_budget_exceeded_total`
- Budget statistics available via `embedding_service.get_budget_stats()`

**Example:**
```python
# Get budget statistics
stats = embedding_service.get_budget_stats()
# Returns:
# {
#   "daily_budget_usd": 10.0,
#   "current_daily_spending_usd": 3.45,
#   "budget_remaining_usd": 6.55,
#   "budget_utilization_percent": 34.5,
#   "budget_enabled": True
# }
```

#### PII Detection and Redaction (Presidio)

This system uses [Microsoft Presidio](https://microsoft.github.io/presidio/) for automatic PII (Personally Identifiable Information) detection and redaction. All log entries are automatically scanned and redacted before storage and display.

**Features:**
- Automatic PII detection during log ingestion
- PII redaction in search results and API responses
- Support for multiple PII types: emails, phone numbers, SSN, credit cards, IP addresses, and more
- Original logs preserved in `raw_log` field for audit purposes

**PII Types Detected:**
- Email addresses → `[EMAIL]`
- Phone numbers → `[PHONE]`
- Credit card numbers → `[CREDIT_CARD]`
- Social Security Numbers → `[SSN]`
- IP addresses → `[IP]`
- Person names, passport numbers, driver's licenses, and more

**Configuration:**
- PII service: `backend/app/services/pii_service.py`
- Full documentation: `docs/presidio-configuration.md`

**Usage:**
PII redaction happens automatically at three points:
1. **During Ingestion**: Logs are redacted before storing in PostgreSQL
2. **During Search**: Search results are redacted before being returned
3. **Dashboard Display**: Logs are redacted via API before display

#### HDBSCAN Semantic Clustering

This system uses [HDBSCAN](https://hdbscan.readthedocs.io/) (Hierarchical Density-Based Spatial Clustering of Applications with Noise) for semantic clustering of log embeddings. HDBSCAN is a powerful clustering algorithm that groups similar log entries based on their semantic embeddings, enabling automatic pattern discovery and anomaly detection.

**What is HDBSCAN?**

HDBSCAN is an advanced clustering algorithm that extends DBSCAN with hierarchical clustering capabilities. It's particularly well-suited for:
- **Variable density clusters**: Handles clusters of different densities effectively
- **Outlier detection**: Automatically identifies outliers (noise points) as cluster ID -1
- **No pre-specified cluster count**: Automatically determines the optimal number of clusters
- **Robust to noise**: Handles noisy data better than traditional clustering methods

**How HDBSCAN Works in This Project:**

1. **Embedding Extraction**: Log entries are converted to semantic embeddings using OpenAI's embedding model and stored in Qdrant vector database
2. **Clustering**: HDBSCAN analyzes the embedding vectors to identify groups of semantically similar logs
3. **Cluster Assignment**: Each log entry is assigned to a cluster (or marked as an outlier with cluster_id = -1)
4. **Metadata Storage**: Cluster statistics, centroids, and representative logs are stored in the database
5. **Anomaly Detection**: Outliers (cluster_id = -1) are automatically flagged as anomalies

**Key Features:**

- **Semantic Clustering**: Groups logs based on meaning, not just exact text matches
- **Automatic Outlier Detection**: Identifies anomalous log entries that don't fit into any cluster
- **Variable Cluster Sizes**: Handles both large and small clusters effectively
- **No Manual Tuning**: Automatically determines optimal number of clusters
- **Persistent Storage**: Cluster assignments and metadata stored in PostgreSQL
- **Scalable**: Supports sampling for very large datasets

**Configuration:**

The clustering service can be configured via environment variables or settings:

```python
# Configuration options (with defaults)
HDBSCAN_MIN_CLUSTER_SIZE=5      # Minimum points to form a cluster
HDBSCAN_MIN_SAMPLES=3           # Minimum samples in neighborhood
HDBSCAN_SAMPLE_SIZE=None        # Optional: sample size for large datasets
HDBSCAN_CLUSTER_SELECTION_EPSILON=0.0  # Epsilon for cluster selection
HDBSCAN_MAX_CLUSTER_SIZE=None   # Optional: maximum cluster size
```

**Usage:**

The clustering service is available via the `ClusteringService` class:

```python
from app.services.clustering_service import clustering_service

# Perform clustering on all embeddings
result = clustering_service.perform_clustering()

# With custom parameters
result = clustering_service.perform_clustering(
    sample_size=10000,          # Sample 10k embeddings for large datasets
    min_cluster_size=10,         # Require at least 10 points per cluster
    min_samples=5                # Require at least 5 samples in neighborhood
)

# Result structure:
# {
#     "n_clusters": 15,           # Number of clusters found
#     "n_outliers": 42,           # Number of outliers (anomalies)
#     "cluster_assignments": {    # Mapping of log_id to cluster_id
#         "log-uuid-1": 0,
#         "log-uuid-2": 0,
#         "log-uuid-3": -1,       # -1 indicates outlier/anomaly
#         ...
#     },
#     "cluster_metadata": {       # Statistics for each cluster
#         0: {
#             "cluster_id": 0,
#             "cluster_size": 150,
#             "centroid": [...],  # Cluster center in embedding space
#             "representative_logs": ["uuid1", "uuid2", ...]
#         },
#         ...
#     }
# }

# Get information about a specific cluster
cluster_info = clustering_service.get_cluster_info(cluster_id=0)
```

**Cluster Results:**

- **Cluster IDs**: Positive integers (0, 1, 2, ...) represent valid clusters
- **Outlier ID**: `-1` represents outliers/anomalies that don't belong to any cluster
- **Cluster Metadata**: Each cluster stores its size, centroid, and representative log entries
- **Anomaly Detection**: Logs with `cluster_id = -1` are automatically marked as anomalies

**Benefits for Log Analysis:**

1. **Pattern Discovery**: Automatically groups similar log patterns together
2. **Anomaly Detection**: Identifies unusual log entries that don't match common patterns
3. **Root Cause Analysis**: Clusters help identify related issues and their scope
4. **Reduced Noise**: Focuses attention on clusters and outliers rather than individual logs
5. **Scalability**: Handles large volumes of logs efficiently with optional sampling

**Service Location:**

- Clustering service: `backend/app/services/clustering_service.py`
- Database models: `backend/app/db/postgres.py` (AnomalyResult, ClusteringMetadata)

#### Hybrid/Tiered Anomaly Detection Pipeline

This system uses a **hybrid two-tier detection approach** that combines fast statistical methods with intelligent LLM validation to achieve both speed and accuracy in anomaly detection.

**What is the Hybrid Approach?**

The hybrid pipeline uses two tiers:
- **Tier 1 (Fast Detection)**: Statistical methods (IsolationForest, Z-score, IQR) run on every log entry for real-time detection
- **Tier 2 (Smart Validation)**: LLM semantic validation runs only on high-scoring anomalies to reduce false positives and provide explanations

**How It Works:**

**Real-Time Pipeline (During Log Ingestion):**

1. **Tier 1 - Fast Statistical Detection**:
   - IsolationForest runs on every new log entry as it's stored
   - Provides immediate anomaly scoring
   - Fast and cost-effective (no LLM calls for normal logs)

2. **Tier 2 - LLM Validation** (conditional):
   - Triggers only when:
     - Tier 1 flags the log as anomalous (`is_anomaly = True`)
     - Anomaly score exceeds threshold (default: 0.7)
   - LLM validates the anomaly semantically
   - Provides explanation for why the log is anomalous
   - Reduces false positives by confirming true anomalies

3. **Result Storage**:
   - All results stored in `AnomalyResult` table
   - LLM reasoning stored in `llm_reasoning` field
   - Explanations always generated (fallback to explanation-only if detection fails)

**Batch Pipeline (HDBSCAN Clustering):**

1. **Tier 1 - HDBSCAN Clustering**:
   - Groups log embeddings into semantic clusters
   - Identifies outliers (cluster_id = -1) as potential anomalies

2. **Tier 2 - LLM Validation**:
   - Validates each outlier with LLM semantic analysis
   - Confirms or rejects HDBSCAN outlier classification
   - Generates explanations for confirmed anomalies

**Key Features:**

- **Cost-Effective**: LLM only runs on ~10-20% of logs (high-scoring anomalies)
- **Fast Real-Time**: Statistical methods provide immediate results
- **High Accuracy**: LLM validation reduces false positives
- **Always Explained**: Every anomaly gets LLM reasoning (detection + explanation or explanation-only fallback)
- **Configurable Thresholds**: Adjust when LLM validation triggers

**Configuration:**

The hybrid detection pipeline can be configured via environment variables:

```bash
# Anomaly Detection Thresholds
ANOMALY_SCORE_THRESHOLD=0.7              # Score threshold to trigger LLM validation (0.0-1.0)
LLM_VALIDATION_ENABLED=true              # Enable/disable LLM validation
LLM_VALIDATION_CONFIDENCE_THRESHOLD=0.6  # Minimum LLM confidence to confirm anomaly (0.0-1.0)
```

**Detection Methods Available:**

1. **IsolationForest** (default for real-time):
   - Unsupervised anomaly detection
   - Works well with high-dimensional embeddings
   - Fast and scalable

2. **Z-score**:
   - Statistical outlier detection
   - Based on standard deviations from mean
   - Good for normally distributed data

3. **IQR (Interquartile Range)**:
   - Statistical method using quartiles
   - Robust to outliers
   - Good for skewed distributions

4. **HDBSCAN** (batch):
   - Semantic clustering with automatic outlier detection
   - Groups similar logs, flags outliers

5. **LLM Validation** (Tier 2):
   - Semantic understanding of log content
   - Context-aware anomaly detection
   - Provides human-readable explanations

**Usage Example:**

```python
# Real-time detection happens automatically during log storage
# Results are stored in AnomalyResult table with:
# - detection_method: "IsolationForest" (or "HDBSCAN" for batch)
# - is_anomaly: True/False
# - anomaly_score: 0.0-1.0
# - llm_reasoning: Explanation text (if LLM validation ran)

# Query anomalies
from app.db.postgres import AnomalyResult
anomalies = db.query(AnomalyResult).filter(AnomalyResult.is_anomaly == True).all()

for anomaly in anomalies:
    print(f"Anomaly: {anomaly.anomaly_score:.2f}")
    print(f"Method: {anomaly.detection_method}")
    print(f"Explanation: {anomaly.llm_reasoning}")
```

**Benefits:**

1. **Speed**: Fast statistical methods provide immediate results
2. **Accuracy**: LLM validation reduces false positives
3. **Cost Control**: LLM only runs on high-confidence anomalies
4. **Explainability**: Every anomaly gets semantic explanation
5. **Flexibility**: Multiple detection methods available
6. **Scalability**: Handles high-volume log streams efficiently

**Service Locations:**

- Real-time detection: `backend/app/services/storage_service.py`
- Batch detection: `backend/app/services/clustering_service.py`
- Anomaly detection methods: `backend/app/services/anomaly_detection_service.py`
- LLM validation: `backend/app/services/llm_reasoning_service.py`
- Database models: `backend/app/db/postgres.py` (AnomalyResult)

#### LLM Reasoning Agent & LangChain Integration

This system includes a comprehensive LLM reasoning agent built with LangChain that provides advanced root cause analysis and anomaly explanation capabilities.

**What is the LLM Reasoning Agent?**

The LLM reasoning agent extends the base LLM reasoning service with:
- **Structured Root Cause Analysis**: Identifies specific root causes with confidence scores
- **Actionable Remediation Steps**: Provides prioritized remediation actions
- **Severity Assessment**: Classifies anomalies by severity (LOW/MEDIUM/HIGH/CRITICAL)
- **Cluster-Aware Analysis**: Compares outliers against cluster patterns for richer context
- **LangChain Tool Integration**: Exposes capabilities as reusable tools for agent executors

**Key Features:**

1. **Enhanced Root Cause Analysis**:
   - Multiple root cause hypotheses with confidence scores
   - Technical explanations of underlying issues
   - Comparison against normal log patterns

2. **Remediation Guidance**:
   - Prioritized action steps (HIGH/MEDIUM/LOW)
   - Specific remediation actions
   - Operational guidance

3. **Cluster Context Integration**:
   - Compares outliers against cluster patterns
   - Uses `clustering_service.get_cluster_info()` for richer context
   - Identifies why a log doesn't fit cluster patterns

4. **LangChain Tool Wrappers**:
   - Three reusable tools for agent executors
   - Standardized tool interface
   - Automatic context retrieval from Qdrant

**Available LangChain Tools:**

The system provides three LangChain tools accessible via `get_agent_tools()`:

1. **`analyze_anomaly_tool`**:
   - Analyzes log anomalies with optional root cause analysis
   - Automatically retrieves similar logs from Qdrant for context
   - Returns structured analysis with root causes and remediation steps

2. **`detect_anomaly_tool`**:
   - Classifies logs as anomalous or normal
   - Returns confidence score and reasoning
   - Uses semantic analysis for classification

3. **`analyze_anomaly_with_cluster_context`**:
   - Enhanced analysis using cluster information
   - Compares outlier against cluster patterns
   - Provides cluster-aware root cause analysis

**Usage Example - LangChain Tools:**

```python
from app.services.agent_tools import get_agent_tools, analyze_anomaly_tool

# Get all available tools
tools = get_agent_tools()

# Use a specific tool directly
result = analyze_anomaly_tool.invoke({
    "log_message": "Error: Database connection pool exhausted",
    "log_level": "ERROR",
    "log_service": "database",
    "include_root_cause": True
})

# Result structure:
# {
#     "explanation": "This log indicates a database connection pool exhaustion...",
#     "root_causes": [
#         {
#             "hypothesis": "Connection pool size too small",
#             "confidence": 0.85,
#             "description": "The pool may be undersized for current load"
#         },
#         {
#             "hypothesis": "Connection leaks",
#             "confidence": 0.75,
#             "description": "Connections may not be properly closed"
#         }
#     ],
#     "remediation_steps": [
#         {
#             "step": "Increase connection pool size",
#             "priority": "HIGH",
#             "description": "Increase pool size from 10 to 20 connections"
#         },
#         {
#             "step": "Check for connection leaks",
#             "priority": "MEDIUM",
#             "description": "Audit code for unclosed connections"
#         }
#     ],
#     "severity": "HIGH",
#     "severity_reason": "Database connectivity issues can cause service outages"
# }
```

**Usage Example - API Endpoints:**

```bash
# Analyze an anomaly with root cause analysis
curl -X POST "http://localhost:8000/api/v1/agent/analyze-anomaly?log_message=Error%3A%20Database%20connection%20failed&log_level=ERROR&include_root_cause=true"

# Analyze a specific log by ID with cluster context
curl -X POST "http://localhost:8000/api/v1/agent/analyze-anomaly/{log_id}?include_root_cause=true&use_cluster_context=true"

# Detect if a log is anomalous
curl -X POST "http://localhost:8000/api/v1/agent/detect-anomaly?log_message=Error%3A%20Connection%20timeout&log_level=ERROR"

# Stream analysis results (Server-Sent Events)
curl -X POST "http://localhost:8000/api/v1/agent/analyze-anomaly/stream?log_message=Error%3A%20Memory%20limit%20exceeded&include_root_cause=true"

# List all available agent tools
curl "http://localhost:8000/api/v1/agent/tools"
```

**Integration with Agent Executors:**

The tools are designed to work with LangChain agent executors:

```python
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_openai import ChatOpenAI
from app.services.agent_tools import get_agent_tools

# Initialize LLM
llm = ChatOpenAI(model="gpt-4", temperature=0)

# Get agent tools
tools = get_agent_tools()

# Create agent executor
agent = create_openai_tools_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

# Use the agent
result = executor.invoke({
    "input": "Analyze this log entry: Error: Database connection failed"
})
```

**Enhanced Reasoning Prompts:**

The LLM reasoning service uses enhanced prompts that include:
- **Anomaly Explanation**: Detailed explanation of why the log is anomalous
- **Root Cause Hypotheses**: 2-3 most likely root causes with confidence scores
- **Remediation Steps**: Prioritized actionable steps to resolve the issue
- **Severity Assessment**: Operational impact classification
- **Cluster Comparison**: Context from cluster patterns (when available)

**Response Format:**

Root cause analysis returns structured JSON with:
- `explanation`: Detailed explanation (3-4 sentences)
- `root_causes`: Array of root cause hypotheses with confidence scores
- `remediation_steps`: Array of prioritized remediation actions
- `severity`: Severity level (LOW/MEDIUM/HIGH/CRITICAL)
- `severity_reason`: Explanation of severity assessment
- `cluster_context`: Cluster comparison information (when available)

**Service Locations:**

- Agent tools: `backend/app/services/agent_tools.py`
- Agent API endpoints: `backend/app/api/v1/agent.py`
- Enhanced LLM reasoning: `backend/app/services/llm_reasoning_service.py`
- Cluster context integration: `backend/app/services/clustering_service.py`

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
