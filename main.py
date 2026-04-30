"""
main.py
-------
Supplier Discovery & Demand Forecasting System
Kazakhstan Import Company – End-to-End Pipeline Orchestrator

Run:
    python main.py

Optional flags:
    --no-db      Skip database storage (SQLite fallback still runs)
    --keyword    Custom search keyword (default: "air compressor manufacturer China")
    --output     Output directory for charts (default: outputs/)
"""

import argparse
import logging
import os
import sys

import pandas as pd

# ─────────────────────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline.log", mode="w"),
    ],
)
logger = logging.getLogger("main")


def separator(title: str):
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"  {title}")
    logger.info("=" * 60)


# ─────────────────────────────────────────────────────────────
# Module imports (project packages)
# ─────────────────────────────────────────────────────────────
from scraper.web_search   import get_supplier_urls
from scraper.web_scraper  import scrape_all_suppliers
from cleaning.data_cleaner import clean_all
from database.db_manager   import DatabaseManager
from database.supply_chain_sim import (
    generate_supplier_products,
    generate_sales_history,
)
from ml.demand_forecaster  import train_and_evaluate, forecast_next_n_months
from ml.spark_processor    import run_big_data_processing
from visualization.charts  import generate_all_charts


# ─────────────────────────────────────────────────────────────
# Pipeline steps
# ─────────────────────────────────────────────────────────────

def step1_search(keyword: str, num_suppliers: int = 10) -> list[str]:
    separator("STEP 1 – Web Search")
    urls = get_supplier_urls(keyword, max_results=num_suppliers)
    logger.info(f"Discovered {len(urls)} supplier URLs.")
    for u in urls:
        logger.info(f"  → {u}")
    return urls


def step2_scrape(urls: list[str]) -> list[dict]:
    separator("STEP 2 – Web Scraping")
    raw_records = scrape_all_suppliers(urls)
    logger.info(f"Scraped {len(raw_records)} supplier records.")
    return raw_records


def step3_clean(raw_records: list[dict]) -> dict[str, pd.DataFrame]:
    separator("STEP 3 – Data Cleaning & Preprocessing")
    tables = clean_all(raw_records)
    for name, df in tables.items():
        logger.info(f"  {name:12s}: {len(df)} rows × {len(df.columns)} cols")
    return tables


def step4_simulate_supply_chain(products_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    separator("STEP 4 – Supply Chain Dataset Simulation")
    sp_df    = generate_supplier_products(products_df)
    sales_df = generate_sales_history(products_df, start_year=2022, end_year=2024)
    logger.info(f"  supplier_products : {len(sp_df)} rows")
    logger.info(f"  sales_history     : {len(sales_df)} rows")
    return {"supplier_products": sp_df, "sales_history": sales_df}


def step5_database(tables: dict[str, pd.DataFrame],
                   sc_tables: dict[str, pd.DataFrame],
                   raw_records: list[dict],
                   db: DatabaseManager):
    separator("STEP 5 – Database Storage (SQLite)")
    db.create_schema()
    db.clear_tables()
    db.upsert_suppliers(tables["suppliers"])
    db.upsert_products(tables["products"])
    db.upsert_contacts(tables["contacts"])
    db.insert_supplier_products(sc_tables["supplier_products"])
    db.insert_sales_history(sc_tables["sales_history"])

    # Log each scraped URL as a lead
    for rec in raw_records:
        db.log_scraped_lead(
            url=rec.get("website", ""),
            status=rec.get("_source", "unknown"),
            company_name=rec.get("company_name"),
            products_found=len(rec.get("products", [])),
        )

    logger.info("All data committed to database.")

    # Show supply-chain view
    view_df = db.get_supply_chain_view()
    logger.info(f"\nSupply Chain View ({len(view_df)} rows):\n"
                + view_df.head(10).to_string(index=False))

    # Export CSVs for inspection
    os.makedirs("outputs", exist_ok=True)
    tables["suppliers"].to_csv("outputs/suppliers.csv", index=False)
    tables["products"].to_csv("outputs/products.csv", index=False)
    tables["contacts"].to_csv("outputs/contacts.csv", index=False)
    sc_tables["supplier_products"].to_csv("outputs/supplier_products.csv", index=False)
    sc_tables["sales_history"].to_csv("outputs/sales_history.csv", index=False)
    logger.info("CSVs exported to outputs/")


def step6_ml(sales_df: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    separator("STEP 6 – Machine Learning (Demand Forecasting)")
    ml_results  = train_and_evaluate(sales_df)

    logger.info("\nModel Evaluation Results:")
    for m in ml_results["metrics"]:
        logger.info(f"  {m['model']:20s} | MAE={m['MAE']:6.2f}  "
                    f"RMSE={m['RMSE']:6.2f}  R²={m['R2']:.3f}")

    logger.info("\nTop-5 Feature Importances (Random Forest):")
    for _, row in ml_results["feature_importance"].head(5).iterrows():
        logger.info(f"  {row['feature']:20s} : {row['importance']:.4f}")

    return ml_results, ml_results["df_featured"]


def step7_forecast(ml_results: dict, products_df: pd.DataFrame) -> pd.DataFrame:
    separator("STEP 7 – 6-Month Ahead Forecast")
    forecast_df = forecast_next_n_months(ml_results, products_df, n_months=6)
    logger.info(f"Forecast generated: {len(forecast_df)} rows.")
    forecast_df.to_csv("outputs/forecast.csv", index=False)
    logger.info("Saved: outputs/forecast.csv")

    # Print a summary
    summary = (
        forecast_df.groupby(["year", "month"])["forecast_qty"]
                   .sum()
                   .reset_index()
    )
    logger.info("\nMonthly Forecast Summary (all products):")
    for _, row in summary.iterrows():
        logger.info(f"  {int(row['year'])}-{int(row['month']):02d} : "
                    f"{int(row['forecast_qty']):4d} units")
    return forecast_df


def step8_visualize(sales_df, suppliers_df, products_df,
                    ml_results, forecast_df, output_dir):
    separator("STEP 8 – Visualization")
    paths = generate_all_charts(
        sales_df, suppliers_df, products_df,
        ml_results, forecast_df, output_dir,
    )
    for p in paths:
        logger.info(f"  Chart saved: {p}")


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Supplier Discovery & Demand Forecasting Pipeline"
    )
    p.add_argument("--keyword", default="air compressor manufacturer China",
                   help="Search keyword for supplier discovery")
    p.add_argument("--num-suppliers", type=int, default=10,
                   help="Number of suppliers to search for (default: 10, max: 50)")
    p.add_argument("--output", default="outputs",
                   help="Directory for chart output")
    p.add_argument("--no-db", action="store_true",
                   help="Skip SQLite storage step")
    p.add_argument("--spark", action="store_true",
                   help="Run Big Data scalability check via Apache Spark")
    return p.parse_args()


def main():
    args = parse_args()
    
    # Validate num_suppliers
    num_suppliers = min(args.num_suppliers, 50)  # Max 50 for performance
    num_suppliers = max(num_suppliers, 1)  # Min 1
    
    separator("SUPPLIER DISCOVERY & DEMAND FORECASTING SYSTEM")
    logger.info("Kazakhstan Import Company – Air Compressors")
    logger.info(f"Keyword      : {args.keyword}")
    logger.info(f"# Suppliers  : {num_suppliers}")
    logger.info(f"Output       : {args.output}/")

    os.makedirs(args.output, exist_ok=True)
    os.makedirs("data", exist_ok=True)

    # --- Step 1: Search ---
    urls = step1_search(args.keyword, num_suppliers)

    # --- Step 2: Scrape ---
    raw_records = step2_scrape(urls)

    # --- Step 3: Clean ---
    tables = step3_clean(raw_records)
    suppliers_df = tables["suppliers"]
    products_df  = tables["products"]
    contacts_df  = tables["contacts"]

    if products_df.empty:
        logger.error("No products extracted. Cannot continue. Exiting.")
        sys.exit(1)

    # --- Step 4: Simulate supply-chain data ---
    sc_tables = step4_simulate_supply_chain(products_df)
    sales_df  = sc_tables["sales_history"]

    # --- Step 5: Database ---
    if not args.no_db:
        logger.info("=== STEP 5: Database Storage PostgreSQL ONLY ===")
        try:
            from config import PG_DSN
            db = DatabaseManager(pg_dsn=PG_DSN, strict_pg=True)
        except ImportError:
            logger.error("❌ config.py not found or PG_DSN missing")
            sys.exit(1)
        db.connect()
        step5_database(tables, sc_tables, raw_records, db)
        logger.info(f"✅ Database step complete. Backend: {db._backend}")
        db.close()
    else:
        logger.info("⏭️  STEP 5: Skipped (--no-db flag)")
        db = None

    # --- Step 6: ML ---
    ml_results, _ = step6_ml(sales_df)

    # --- Step 7: Forecast ---
    forecast_df = step7_forecast(ml_results, products_df)

    # --- Step 8: Visualize ---
    step8_visualize(
        sales_df, suppliers_df, products_df,
        ml_results, forecast_df, args.output,
    )

    # ─── Final summary ────────────────────────────────────────
    separator("PIPELINE COMPLETE")
    logger.info(f"  Suppliers found   : {len(suppliers_df)}")
    logger.info(f"  Products scraped  : {len(products_df)}")
    logger.info(f"  Sales records     : {len(sales_df)}")
    logger.info(f"  Forecast rows     : {len(forecast_df)}")
    logger.info(f"  Charts generated  : outputs/")
    if not args.no_db and db:
        logger.info(f"  Database          : data/supplier_system.db")
    logger.info(f"  Log               : pipeline.log")
    logger.info("")
    logger.info("  Output files:")
    for f in sorted(os.listdir(args.output)):
        logger.info(f"    {args.output}/{f}")
    logger.info("")
    logger.info("  Done.")
    
    # ─── Optional: Big Data Scalability Check (Spark) ────────
    if args.spark:
        separator("BIG DATA SCALABILITY CHECK (SPARK MODE)")
        spark_result = run_big_data_processing(
            f"{args.output}/sales_history.csv",
            mode="demo"
        )
        if spark_result.get("status") == "success":
            logger.info("✅ Big Data processing successful!")
            logger.info(f"   Rows processed: {spark_result.get('rows_processed'):,}")
            logger.info(f"   RMSE: {spark_result.get('rmse'):.2f}")
            logger.info(f"   R²: {spark_result.get('r2'):.3f}")
        else:
            logger.warning(f"⚠️  Big Data check skipped: {spark_result.get('reason')}")


if __name__ == "__main__":
    main()
