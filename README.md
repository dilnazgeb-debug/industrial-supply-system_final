# Industrial Supply System (Equipment Auditing + Demand Forecasting)

This repository contains two related parts:

1) **Web app (Flask)** for equipment auditing:
- extracts structured parameters from user text and PDFs (LLM + fallback parsing),
- predicts failure/risk scores with pre-trained ML models,
- shows results in a browser UI,
- supports **two data modes**: PostgreSQL (local) and static JSON (cloud/demo).

2) **Offline pipeline** (`main.py`) for supplier discovery + demand forecasting:
- searches suppliers on the web,
- scrapes supplier pages,
- cleans extracted tables,
- simulates supply-chain datasets,
- trains/validates ML demand forecasting models,
- exports CSV outputs and charts.

---

## Tech Stack

- **Backend:** Python + Flask
- **Data layer:** SQLAlchemy + PostgreSQL (optional), SQLite fallback
- **NLP/LLM:** Groq API (structured extraction) + fallback parsing utilities
- **ML:** scikit-learn models serialized in `models/*.pkl`
- **Visualization:** charts saved under `outputs/`
- **Optional big data:** Spark pipeline helper (see `ml/spark_processor.py`)
- **Containerization:** Docker Compose (see `infrastructure/docker-compose.yml`)

---

## Running the Web App (Flask)

### 1) Install dependencies
```bash
pip install -r requirements.txt
```

### 2) Configure environment variables

**Required for LLM extraction (recommended):**
- `GROQ_API_KEY` (set in your shell or `.env` equivalent)

**For PostgreSQL mode:**
- `DATABASE_URL` (if not set or empty → app uses JSON demo mode)

Examples:

- **JSON demo mode (no PostgreSQL):**
  - do not set `DATABASE_URL` (or set it to empty)

- **PostgreSQL mode:**
  - `DATABASE_URL=postgresql://analytics:secure_password_123@localhost:5432/supply_chain_data_lake`

### 3) Start the server
```bash
python app_hybrid.py
```

The app runs on:
- **host:** `0.0.0.0`
- **port:** `5052`

Open in browser:
- http://localhost:5052

### Login
The web UI uses Flask session auth and checks credentials stored in code (`ADMIN_USERS` in `app_hybrid.py`).

---

## Running the Offline Pipeline (`main.py`)

### Install dependencies
```bash
pip install -r requirements.txt
```

### Execute
```bash
python main.py --keyword "air compressor manufacturer China" --num-suppliers 10 --output outputs
```

### Useful flags
- `--no-db` : skip the SQLite/Postgres storage step (pipeline still generates outputs)
- `--spark` : run the Spark scalability check (demo)

Outputs produced:
- `outputs/suppliers.csv`
- `outputs/products.csv`
- `outputs/contacts.csv`
- `outputs/supplier_products.csv`
- `outputs/sales_history.csv`
- `outputs/forecast.csv`
- chart images (created by `visualization/`)

---

## Docker Compose (Infrastructure)

Configuration is located at:
- `infrastructure/docker-compose.yml`

Typical usage:
```bash
docker-compose -f infrastructure/docker-compose.yml up -d
```

The Compose stack is designed to support:
- PostgreSQL
- Redis
- Kafka
- Spark
- Prometheus

(Your Flask web app expects `DATABASE_URL` to point at the PostgreSQL service when running inside containers.)

---

## Repository Structure (file-by-file)

### Top-level
- `analytics.py` — core auditing logic (LLM extraction, feature prep, ML prediction helpers)
- `app_hybrid.py` — Flask web app (routes + two-mode backend: PostgreSQL vs JSON demo)
- `main.py` — offline supplier discovery + demand forecasting pipeline orchestrator
- `pdf_parser.py` — PDF parsing helpers (used by PDF workflows)
- `debug_parser.py` — debugging utilities for PDF extraction + heuristics
- `train_models.py` — ML training script(s) used to generate artifacts in `models/`
- `config.py` — configuration helpers (e.g., Postgres DSN / runtime settings)
- `conn.py` — DB connection helpers (if used by scripts)
- `DEPLOYMENT_GUIDE.md` — deployment notes
- `INTEGRATION_GUIDE.md` — integration notes
- `PRODUCTION_READINESS_REPORT.md` — architectural report and readiness checklist (reference only)
- `BIG_DATA_ANALYSIS_REPORT.md` — scalability / big-data related notes
- `requirements.txt` — Python dependencies for dev/local usage
- `requirements-production.txt` — dependencies for production environment
- `.env.example` — example environment variables template
- `.gitignore` — Git ignore rules
- `demo_data.json` — JSON dataset used in demo mode by the web app
- `knowledge_base.json` — additional knowledge base used by parsing/extraction
- `hybrid.txt` — example input text for extraction/audit
- `predictive_maintenance.csv` — dataset used for ML tasks
- `companies_china_50.csv` — dataset used in supplier/discovery forecasting pipeline
- `temp_debug.pdf` — temporary artifact (kept out of the main code path; verify before commit)
- `pipeline.log` — runtime log output (created at execution time)

### Folders: application subsystems
- `cleaning/`
  - `__init__.py` — cleaning package marker
  - `data_cleaner.py` — cleaning + preprocessing of scraped tables
- `database/`
  - `__init__.py` — database package marker
  - `db_manager.py` — DB manager used by `main.py` pipeline
  - `supply_chain_sim.py` — supply chain simulation dataset generators
- `scraper/`
  - `__init__.py` — scraper package marker
  - `web_scraper.py` — page scraping logic
  - `web_search.py` — web search (supplier discovery)
- `ml/`
  - `__init__.py` — ML package marker
  - `demand_forecaster.py` — training/evaluation/forecasting for demand
  - `spark_processor.py` — Spark demo processing helper
- `visualization/`
  - `__init__.py` — visualization package marker
  - `charts.py` — generates charts saved to `outputs/`
- `static/`
  - `style.css` — UI styles
  - `script.js` — frontend JS logic (AJAX calls, UI updates)
- `templates/` — Jinja2 templates for the Flask UI:
  - `base.html` — base layout
  - `index.html` — landing page
  - `login.html` — login page
  - `dashboard.html` — equipment dashboard
  - `audit.html` — audit input page
  - `audit_result.html` — audit result view
  - `equipment_detail.html` — equipment details
  - `suppliers.html` — suppliers page
  - `products.html` — products page
  - `supply-chain.html` — supply chain page
  - `forecast.html` — forecast page
  - `pdf_results.html` — PDF audit results
  - `status.html` — system status page
  - `upload_pdf.html` — PDF upload page
  - `contacts.html` — contacts view
  - `error.html` — error page
  - `debug_result.html` — debug output page
  - `pdf_results.html` — PDF results display
- `models/` — pre-trained ML artifacts:
  - `README.md` — model documentation
  - `scaler.pkl` — feature scaler artifact
  - `pump.pkl` — pump risk model
  - `valve.pkl` — valve risk model
  - `cooler.pkl` — cooler risk model
  - `accumulator.pkl` — accumulator risk model
  - `maintenance.pkl` — maintenance-related model

### Data / Outputs
- `data/`
  - `supplier_system.db` — local SQLite DB (if created/used)
- `outputs/` — generated CSVs and images from simulated data:
  - `suppliers.csv`, `products.csv`, `contacts.csv`
  - `supplier_products.csv`, `sales_history.csv`, `forecast.csv`
  - chart images: `feature_importance.png`, `predicted_vs_actual.png`, `top_suppliers.png`, etc.

### Testing & Debugging (additional/)
- `app.py` — alternative Flask application setup for database testing and verification
- `test_connection.py` — utility script for testing database connectivity and configuration
- `test_pg_fixed.py` — PostgreSQL connection tests with error handling and diagnostics
- `test_scraping.py` — web scraping functionality tests and BeautifulSoup validation
- `TEST_SEARCH_METHODS.py` — comparison and testing of different search and query methods

These scripts are used during development to verify component functionality in isolation before integration into the main pipeline.


---

## Notes / Configuration Pitfalls

- **LLM requires `GROQ_API_KEY`**. If it’s missing, the app falls back to parsing utilities (behavior depends on `analytics.py`).
- **Two backend modes in `app_hybrid.py`:**
  - If `DATABASE_URL` is empty → JSON demo mode
  - If `DATABASE_URL` is set → PostgreSQL mode
- **Pre-trained ML artifacts** must exist in `models/` for ML predictions to work.

---
