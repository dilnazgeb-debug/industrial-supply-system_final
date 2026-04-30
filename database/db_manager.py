"""
database/db_manager.py
----------------------
Database Module

Handles:
- PostgreSQL schema creation (DDL)
- Data insertion from clean DataFrames
- Query helpers

If psycopg2 / PostgreSQL is not available, the module automatically
falls back to SQLite so the prototype can run without a Postgres server.
"""

import logging
import sqlite3
import os
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL – works for both PostgreSQL and SQLite (minor dialect differences noted)
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- ============================================================
-- Suppliers master table
-- ============================================================
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id   SERIAL PRIMARY KEY,
    company_name  TEXT    NOT NULL,
    country       TEXT    DEFAULT 'China',
    city          TEXT,
    website       TEXT    UNIQUE,
    data_source   TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Products catalogue
-- ============================================================
CREATE TABLE IF NOT EXISTS products (
    product_id      SERIAL PRIMARY KEY,
    supplier_id     INTEGER NOT NULL REFERENCES suppliers(supplier_id),
    model           TEXT,
    product_type    TEXT,        -- Screw / Piston / Variable
    pressure_bar    REAL,
    power_kw        REAL,
    capacity_m3min  REAL,
    price_usd       REAL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Supplier ↔ Product link with supply-chain attributes
-- ============================================================
CREATE TABLE IF NOT EXISTS supplier_products (
    id              SERIAL PRIMARY KEY,
    supplier_id     INTEGER NOT NULL REFERENCES suppliers(supplier_id),
    product_id      INTEGER NOT NULL REFERENCES products(product_id),
    moq             SERIAL,          
    lead_time_days  SERIAL,          
    shipping_terms  TEXT,             
    warranty_months SERIAL,
    incoterm_port   TEXT,
    UNIQUE(supplier_id, product_id)
);

-- ============================================================
-- Contact information
-- ============================================================
CREATE TABLE IF NOT EXISTS contacts (
    contact_id   SERIAL PRIMARY KEY,
    supplier_id  INTEGER NOT NULL REFERENCES suppliers(supplier_id),
    phone        TEXT,
    email        TEXT,
    whatsapp     TEXT,
    wechat       TEXT,
    UNIQUE(supplier_id)
);

-- ============================================================
-- Raw scraping log (audit trail)
-- ============================================================
CREATE TABLE IF NOT EXISTS scraped_leads (
    lead_id       SERIAL PRIMARY KEY,
    url           TEXT    NOT NULL,
    scraped_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status        TEXT,    -- success / fallback / error
    company_name  TEXT,
    products_found INTEGER DEFAULT 0
);

-- ============================================================
-- Sales history (for ML forecasting)
-- ============================================================
CREATE TABLE IF NOT EXISTS sales_history (
    sale_id     SERIAL PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES products(product_id),
    year        INTEGER NOT NULL,
    month       INTEGER NOT NULL,
    quantity    INTEGER NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

class DatabaseManager:
    """
    Thin wrapper around SQLite (default) or PostgreSQL.

    Usage
    -----
    db = DatabaseManager()           # SQLite in-project file
    db = DatabaseManager(pg_dsn="postgresql://user:pass@host/dbname")
    """

    def __init__(self, sqlite_path: str = "data/supplier_system.db",
                 pg_dsn: str | None = None, strict_pg: bool = False):
        self.pg_dsn     = pg_dsn
        self.sqlite_path = sqlite_path
        self.strict_pg  = strict_pg
        self._conn       = None
        self._backend    = None

    # ------------------------------------------------------------------
    def connect(self):
        if self.pg_dsn and self.strict_pg:
            try:
                import psycopg2
                self._conn = psycopg2.connect(self.pg_dsn)
                self._backend = "postgresql"
                logger.info(f"✅ Connected to PostgreSQL: {self.pg_dsn.split('@')[1].split('/')[0]}")
                
                # Test connection
                cur = self._conn.cursor()
                cur.execute("SELECT 1")
                cur.close()
                logger.info("✅ PostgreSQL test query OK")
                
            except Exception as exc:
                logger.error(f"❌ PostgreSQL STRICT MODE FAILED: {exc}")
                raise ConnectionError(f"PostgreSQL connection failed in strict mode: {exc}")
        elif self.pg_dsn:
            try:
                import psycopg2
                self._conn = psycopg2.connect(self.pg_dsn)
                self._backend = "postgresql"
                logger.info("✅ Connected to PostgreSQL.")
                cur = self._conn.cursor()
                cur.execute("SELECT 1")
                cur.close()
            except Exception as exc:
                logger.warning(f"PG failed, fallback SQLite: {exc}")
                self._use_sqlite()
        else:
            self._use_sqlite()
        logger.info(f"🔧 Using backend: {self._backend}")
        return self

    def _use_sqlite(self):
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn    = sqlite3.connect(self.sqlite_path)
        self._backend = "sqlite"
        # Enable foreign keys in SQLite
        self._conn.execute("PRAGMA foreign_keys = ON")
        logger.info(f"Connected to SQLite: {self.sqlite_path}")

    def close(self):
        if self._conn:
            self._conn.close()

    def clear_tables(self):
        """Очистить все таблицы (перед новым импортом)"""
        cur = self._conn.cursor()
        tables = [
            'sales_history', 'supplier_products', 'contacts',
            'products', 'suppliers', 'scraped_leads'
        ]
        for table in tables:
            try:
                if self._backend == "sqlite":
                    cur.execute(f'DELETE FROM {table}')
                else:
                    cur.execute(f'TRUNCATE TABLE {table} CASCADE')
                logger.info(f"Cleared table: {table}")
            except Exception as e:
                logger.debug(f"Could not clear {table}: {e}")
        self._conn.commit()
        logger.info("✅ All tables cleared")

    def __enter__(self):
        return self.connect()

    def __exit__(self, *_):
        self.close()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    def create_schema(self):
        """Run all CREATE TABLE IF NOT EXISTS statements."""
        cur = self._conn.cursor()
        # SQLite handles the whole script at once; psycopg2 needs split
        if self._backend == "sqlite":
            cur.executescript(SCHEMA_SQL)
        else:
            for stmt in SCHEMA_SQL.split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)
        self._conn.commit()
        logger.info("Schema created / verified.")

    # ------------------------------------------------------------------
    # Insert helpers
    # ------------------------------------------------------------------
    def _placeholder(self):
        return "?" if self._backend == "sqlite" else "%s"

    def upsert_suppliers(self, df: pd.DataFrame):
        """Insert suppliers, ignore on conflict (website unique key)."""
        cur = self._conn.cursor()
        ph  = self._placeholder()
        if self._backend == "sqlite":
            sql = f"""
                INSERT OR IGNORE INTO suppliers
                    (supplier_id, company_name, country, city, website, data_source)
                VALUES ({ph},{ph},{ph},{ph},{ph},{ph})
            """
        else:
            sql = """
                INSERT INTO suppliers (supplier_id, company_name, country, city, website, data_source)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (website) DO NOTHING
            """
        for _, row in df.iterrows():
            cur.execute(sql, (
                int(row["supplier_id"]),
                row["company_name"],
                row.get("country"),
                row.get("city"),
                row.get("website"),
                row.get("data_source"),
            ))
        self._conn.commit()
        logger.info(f"Upserted {len(df)} suppliers.")

    def upsert_products(self, df: pd.DataFrame):
        cur = self._conn.cursor()
        if self._backend == "sqlite":
            sql = """
                INSERT OR IGNORE INTO products
                    (product_id, supplier_id, model, product_type,
                     pressure_bar, power_kw, capacity_m3min, price_usd)
                VALUES (?,?,?,?,?,?,?,?)
            """
        else:
            sql = """
                INSERT INTO products (product_id, supplier_id, model, product_type,
                    pressure_bar, power_kw, capacity_m3min, price_usd)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """
        for _, row in df.iterrows():
            cur.execute(sql, (
                int(row["product_id"]),
                int(row["supplier_id"]),
                row.get("model"),
                row.get("product_type"),
                row.get("pressure_bar") if pd.notna(row.get("pressure_bar")) else None,
                row.get("power_kw")     if pd.notna(row.get("power_kw"))     else None,
                row.get("capacity_m3min") if pd.notna(row.get("capacity_m3min")) else None,
                row.get("price_usd")    if pd.notna(row.get("price_usd"))    else None,
            ))
        self._conn.commit()
        logger.info(f"Upserted {len(df)} products.")

    def upsert_contacts(self, df: pd.DataFrame):
        cur = self._conn.cursor()
        if self._backend == "sqlite":
            sql = """
                INSERT OR IGNORE INTO contacts
                    (contact_id, supplier_id, phone, email, whatsapp, wechat)
                VALUES (?,?,?,?,?,?)
            """
        else:
            sql = """
                INSERT INTO contacts
                    (contact_id, supplier_id, phone, email, whatsapp, wechat)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (supplier_id) DO NOTHING
            """
        for _, row in df.iterrows():
            cur.execute(sql, (
                int(row["contact_id"]),
                int(row["supplier_id"]),
                row.get("phone"),
                row.get("email"),
                row.get("whatsapp"),
                row.get("wechat"),
            ))
        self._conn.commit()
        logger.info(f"Upserted {len(df)} contacts.")

    def insert_supplier_products(self, df: pd.DataFrame):
        """Insert supply-chain attributes (MOQ, lead time, terms)."""
        cur = self._conn.cursor()
        sql = """
            INSERT OR IGNORE INTO supplier_products
                (supplier_id, product_id, moq, lead_time_days,
                 shipping_terms, warranty_months, incoterm_port)
            VALUES (?,?,?,?,?,?,?)
        """ if self._backend == "sqlite" else """
            INSERT INTO supplier_products
                (supplier_id, product_id, moq, lead_time_days,
                 shipping_terms, warranty_months, incoterm_port)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
        """
        for _, row in df.iterrows():
            cur.execute(sql, (
                int(row["supplier_id"]),
                int(row["product_id"]),
                int(row["moq"]),
                int(row["lead_time_days"]),
                row["shipping_terms"],
                int(row["warranty_months"]),
                row.get("incoterm_port"),
            ))
        self._conn.commit()
        logger.info(f"Inserted {len(df)} supplier_product records.")


    def insert_sales_history(self, df: pd.DataFrame):
        """Insert sales history records."""
        cur = self._conn.cursor()
        sql = """
            INSERT OR IGNORE INTO sales_history
                (sale_id, product_id, month, year, quantity)
            VALUES (?,?,?,?,?)
        """ if self._backend == "sqlite" else """
            INSERT INTO sales_history
                (sale_id, product_id, month, year, quantity)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
        """
        for _, row in df.iterrows():
            cur.execute(sql, (
                int(row["sale_id"]),
                int(row["product_id"]),
                int(row["month"]),
                int(row["year"]),
                int(row["sales_qty"]),
            ))
        self._conn.commit()
        logger.info(f"Inserted {len(df)} sales_history records.")

    def log_scraped_lead(self, url: str, status: str,
                         company_name: str | None = None,
                         products_found: int = 0):
        cur = self._conn.cursor()
        sql = """
            INSERT INTO scraped_leads (url, status, company_name, products_found)
            VALUES (?,?,?,?)
        """ if self._backend == "sqlite" else """
            INSERT INTO scraped_leads (url, status, company_name, products_found)
            VALUES (%s,%s,%s,%s)
        """
        cur.execute(sql, (url, status, company_name, products_found))
        self._conn.commit()

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def query(self, sql: str, params=()) -> pd.DataFrame:
        return pd.read_sql_query(sql, self._conn, params=params)

    def get_all_suppliers(self) -> pd.DataFrame:
        return self.query("SELECT * FROM suppliers ORDER BY supplier_id")

    def get_all_products(self) -> pd.DataFrame:
        return self.query("""
            SELECT p.*, s.company_name
            FROM products p
            JOIN suppliers s USING (supplier_id)
            ORDER BY product_id
        """)

    def get_supply_chain_view(self) -> pd.DataFrame:
        return self.query("""
            SELECT s.company_name, p.model, p.product_type,
                   p.price_usd, sp.moq, sp.lead_time_days,
                   sp.shipping_terms, sp.warranty_months
            FROM supplier_products sp
            JOIN suppliers s USING (supplier_id)
            JOIN products   p USING (product_id)
            ORDER BY s.company_name, p.model
        """)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db = DatabaseManager(sqlite_path="data/test.db")
    db.connect()
    db.create_schema()
    print("Schema OK")
    db.close()
