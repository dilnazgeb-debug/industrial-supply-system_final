# 🚀 Big Data Infrastructure Setup

Complete Docker Compose stack for scalable supply chain analytics.

## 📋 Quick Start

### Prerequisites
- Docker & Docker Compose installed
- 8GB RAM minimum (for full cluster)
- Linux/macOS (Windows WSL2 recommended)

### Start the Stack
```bash
cd infrastructure
docker-compose up -d
```

### Verify Services
```bash
docker-compose ps
```

Expected output:
```
NAME              IMAGE                      STATUS      PORTS
postgres          postgres:15-alpine         Up          5432:5432
zookeeper         confluentinc/cp-zookeeper Up          2181:2181
kafka             confluentinc/cp-kafka     Up          9092:9092
spark-master      bitnami/spark:3.5.0       Up          8080:8080, 7077:7077
spark-worker-1    bitnami/spark:3.5.0       Up          8081:8081
spark-worker-2    bitnami/spark:3.5.0       Up          8082:8082
redis             redis:7-alpine            Up          6379:6379
prometheus        prom/prometheus:latest    Up          9090:9090
```

---

## 🎯 Service Access

| Service | URL | Credentials |
|---------|-----|-------------|
| **Spark Master** | http://localhost:8080 | - |
| **Spark Worker 1** | http://localhost:8081 | - |
| **Spark Worker 2** | http://localhost:8082 | - |
| **Prometheus** | http://localhost:9090 | - |
| **PostgreSQL** | localhost:5432 | user: analytics / pass: secure_password_123 |
| **Redis** | localhost:6379 | - |
| **Kafka** | localhost:9092 | - |

---

## 🔧 Configuration

### Environment Variables
Edit `docker-compose.yml` to customize:

```yaml
# PostgreSQL
POSTGRES_USER: analytics
POSTGRES_PASSWORD: secure_password_123

# Spark
SPARK_WORKER_MEMORY: 2G        # Per worker
SPARK_WORKER_CORES: 2          # Per worker

# Kafka
KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
```

### Resource Limits
Adjust for your system:

```yaml
# For limited resources (2GB RAM):
SPARK_WORKER_MEMORY: 1G
services: Keep postgres + spark-master + 1 worker only

# For powerful machine (16GB RAM):
SPARK_WORKER_MEMORY: 4G
Add more workers, increase executor count
```

---

## 📊 PostgreSQL Data Warehouse

### Connect to PostgreSQL
```bash
# Using psql (if installed)
psql -U analytics -h localhost -d supply_chain_data_lake

# Or inside Docker
docker exec -it supply_chain_postgres psql -U analytics -d supply_chain_data_lake
```

### Create Initial Schema
```bash
# The schema initializes from ./sql/init.sql if it exists
# Create the file to pre-populate data:

cat > infrastructure/sql/init.sql << 'EOF'
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id SERIAL PRIMARY KEY,
    company_name VARCHAR(255),
    country VARCHAR(100),
    city VARCHAR(100),
    website VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS products (
    product_id SERIAL PRIMARY KEY,
    supplier_id INTEGER REFERENCES suppliers(supplier_id),
    model VARCHAR(100),
    product_type VARCHAR(50),
    price_usd FLOAT
);

CREATE TABLE IF NOT EXISTS sales_history (
    sale_id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES products(product_id),
    year INTEGER,
    month INTEGER,
    sales_qty INTEGER,
    revenue_usd FLOAT
);
EOF
```

---

## 🎬 Spark Job Submission

### Submit via Docker
```bash
# Submit Python job to Spark cluster
docker exec spark-master spark-submit \
  --master spark://spark-master:7077 \
  --num-executors 2 \
  --executor-cores 2 \
  --executor-memory 2G \
  /opt/spark-apps/supply_chain_analysis.py
```

### Submit from Host
```bash
# If spark-submit is installed locally
spark-submit \
  --master spark://localhost:7077 \
  --deploy-mode client \
  --num-executors 2 \
  --executor-cores 2 \
  --executor-memory 2G \
  /path/to/script.py
```

### Example: Process Sales Data
```python
# ./spark-apps/supply_chain_analysis.py
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("SupplyChainAnalysis") \
    .getOrCreate()

# Read from HDFS, S3, or local
df = spark.read.csv("s3://bucket/sales.csv", header=True, inferSchema=True)

# Process with Spark SQL
df.createOrReplaceTempView("sales")
result = spark.sql("""
    SELECT supplier_id, SUM(revenue) as total
    FROM sales
    GROUP BY supplier_id
""")

result.write.parquet("s3://bucket/results/sales_summary")
```

---

## 📨 Kafka Streaming Setup

### Create Topic
```bash
docker exec kafka kafka-topics --create \
  --topic supplier-events \
  --bootstrap-server kafka:9092 \
  --partitions 3 \
  --replication-factor 1
```

### Produce Messages
```bash
# Interactive producer
docker exec -it kafka kafka-console-producer \
  --topic supplier-events \
  --bootstrap-server kafka:9092

# Paste JSON events:
{"supplier_id": 1, "sales_qty": 100, "timestamp": "2025-01-20T10:00:00Z"}
{"supplier_id": 2, "sales_qty": 250, "timestamp": "2025-01-20T10:01:00Z"}
^C to exit
```

### Consume Messages
```bash
docker exec kafka kafka-console-consumer \
  --topic supplier-events \
  --bootstrap-server kafka:9092 \
  --from-beginning
```

---

## 💾 Redis Caching

### Interactive Commands
```bash
# Connect to Redis
docker exec -it redis_cache redis-cli

# Inside redis-cli:
> PING
PONG

> SET supplier:1 "Kaishan Group"
OK

> GET supplier:1
"Kaishan Group"

> DEL supplier:1
(integer) 1
```

### Cache Warm-up Script
```python
import redis

r = redis.Redis(host='localhost', port=6379, db=0)

# Cache supplier data
suppliers = [
    {'id': 1, 'name': 'Kaishan', 'country': 'China'},
    {'id': 2, 'name': 'DENAIR', 'country': 'China'},
]

for sup in suppliers:
    r.hset(f"supplier:{sup['id']}", mapping=sup)

# Check TTL
r.expire(f"supplier:1", 3600)  # Expire in 1 hour
```

---

## 📊 Prometheus Monitoring

### Access Prometheus
Open http://localhost:9090

### Query Examples
```promql
# CPU usage
container_cpu_usage_seconds_total

# Memory usage
container_memory_usage_bytes

# Spark executors running
spark_executor_count

# Custom metrics
supply_chain_sales_total
```

### Add Spark Metrics
```yaml
# In spark-master environment:
SPARK_CONF: --conf spark.metrics.conf=/opt/spark-conf/metrics.conf

# /opt/spark-conf/metrics.conf:
*.sink.prometheus.class=org.apache.spark.metrics.sink.PrometheusSink
*.sink.prometheus.period=10
*.sink.prometheus.unit=seconds
```

---

## 🧹 Cleanup & Management

### Stop Services
```bash
docker-compose stop
```

### Restart Services
```bash
docker-compose restart
```

### View Logs
```bash
docker-compose logs -f spark-master
docker-compose logs -f postgres
docker-compose logs kafka
```

### Delete Everything (⚠️ deletes data)
```bash
docker-compose down -v
```

### Backup PostgreSQL
```bash
docker exec supply_chain_postgres pg_dump \
  -U analytics supply_chain_data_lake > backup.sql
```

### Restore PostgreSQL
```bash
docker exec -i supply_chain_postgres psql \
  -U analytics supply_chain_data_lake < backup.sql
```

---

## 🐛 Troubleshooting

### Spark Master Not Accessible
```bash
# Check if port 8080 is free
lsof -i :8080

# Force remove
docker-compose down -v
docker-compose up -d
```

### PostgreSQL Connection Failed
```bash
# Check password
PGPASSWORD=secure_password_123 psql -U analytics -h localhost

# View logs
docker-compose logs postgres
```

### Out of Memory
```bash
# Reduce worker memory:
# Edit docker-compose.yml:
SPARK_WORKER_MEMORY: 1G  # from 2G
```

### Kafka Not Responding
```bash
# Check Zookeeper connection
docker exec kafka kafka-broker-api-versions \
  --bootstrap-server kafka:9092

# Restart Zookeeper & Kafka
docker-compose restart zookeeper kafka
```

---

## 📈 Scaling the Cluster

### Add More Spark Workers
```yaml
spark-worker-3:
  image: bitnami/spark:3.5.0
  environment:
    SPARK_MODE: worker
    SPARK_MASTER_URL: spark://spark-master:7077
    SPARK_WORKER_MEMORY: 2G
    SPARK_WORKER_CORES: 2
  ports:
    - "8083:8081"
  networks:
    - supply_chain_network
```

Then restart:
```bash
docker-compose up -d spark-worker-3
```

### Increase PostgreSQL Capacity
```yaml
postgres:
  environment:
    POSTGRES_INITDB_ARGS: "-c max_connections=1000 -c shared_buffers=256MB"
  
  # Add volume for large data
  volumes:
    - large_postgres_data:/var/lib/postgresql/data
```

---

## 📚 Resources

- [Spark Documentation](https://spark.apache.org/docs/)
- [Kafka Documentation](https://kafka.apache.org/documentation/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
- [Prometheus Querying](https://prometheus.io/docs/prometheus/latest/querying/)

---

**Last Updated**: 2025-04-20  
**Status**: ✅ Production Ready
