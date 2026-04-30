"""
database/supply_chain_sim.py
----------------------------
Supply Chain Dataset Simulation Module

Generates realistic supply-chain attributes for every
(supplier, product) pair and builds a historical sales dataset
suitable for training a demand-forecasting model.

Outputs
-------
- supplier_products DataFrame  (MOQ, lead time, shipping terms, etc.)
- sales_history    DataFrame   (monthly sales for each product, 3 years)
"""

import random
import logging
import numpy as np
import pandas as pd
from datetime import date

logger = logging.getLogger(__name__)

random.seed(42)
np.random.seed(42)

# ---------------------------------------------------------------------------
# Supply-chain constants (realistic ranges for China → Kazakhstan trade)
# ---------------------------------------------------------------------------
SHIPPING_TERMS   = ["FOB", "CIF", "EXW", "DAP"]
INCOTERM_PORTS   = ["Shanghai", "Tianjin", "Guangzhou", "Shenzhen", "Ningbo"]

# Lead times: small factories 30-60 d, large 15-30 d
LEAD_TIME_RANGE  = (15, 65)      # days
MOQ_RANGE        = (1, 10)       # units
WARRANTY_RANGE   = (12, 36)      # months


def generate_supplier_products(products_df: pd.DataFrame) -> pd.DataFrame:
    """
    Attach supply-chain attributes to each product record.

    Parameters
    ----------
    products_df : clean products DataFrame (from data_cleaner)

    Returns
    -------
    DataFrame ready for insertion into supplier_products table
    """
    rows = []
    for _, row in products_df.iterrows():
        # Larger, more expensive machines → longer lead time, lower MOQ
        if row["price_usd"] and row["price_usd"] > 10000:
            moq       = random.randint(1, 3)
            lead_time = random.randint(30, 65)
        elif row["price_usd"] and row["price_usd"] > 3000:
            moq       = random.randint(2, 5)
            lead_time = random.randint(20, 45)
        else:
            moq       = random.randint(3, 10)
            lead_time = random.randint(15, 35)

        rows.append({
            "supplier_id":     int(row["supplier_id"]),
            "product_id":      int(row["product_id"]),
            "moq":             moq,
            "lead_time_days":  lead_time,
            "shipping_terms":  random.choice(SHIPPING_TERMS),
            "warranty_months": random.choice(WARRANTY_RANGE),
            "incoterm_port":   random.choice(INCOTERM_PORTS),
        })

    df = pd.DataFrame(rows)
    logger.info(f"Generated {len(df)} supplier_product supply-chain records.")
    return df


def generate_sales_history(products_df: pd.DataFrame,
                            start_year: int = 2022,
                            end_year:   int = 2024) -> pd.DataFrame:
    """
    Simulate 3 years of monthly sales for each product.

    Demand model
    ------------
    base_demand  : inversely proportional to price (cheaper = higher volume)
    seasonality  : Q1 low, Q2-Q3 peak (construction season in CIS)
    trend        : +5% per year (growing market)
    noise        : ±30% random variation
    supplier_fx  : well-known brands get a 10-30% boost

    Returns
    -------
    DataFrame with columns:
        sale_id, product_id, supplier_id, model, product_type, price_usd,
        year, month, sales_qty, revenue_usd, lead_time_days
    """
    monthly_seasonality = {
        1: 0.65, 2: 0.70, 3: 0.85,   # Q1 – post-New Year slow
        4: 1.10, 5: 1.20, 6: 1.25,   # Q2 – spring peak
        7: 1.15, 8: 1.10, 9: 1.05,   # Q3 – summer
        10: 0.95, 11: 0.85, 12: 0.75 # Q4 – year-end slowdown
    }

    rows   = []
    sale_id = 1

    for _, prod in products_df.iterrows():
        price = prod.get("price_usd") or 2000.0

        # Base monthly demand: roughly inversely proportional to price
        base = max(1, int(20000 / max(price, 100)))

        for year in range(start_year, end_year + 1):
            trend_mult = 1 + 0.05 * (year - start_year)
            for month in range(1, 13):
                season_mult = monthly_seasonality[month]
                noise       = np.random.uniform(0.70, 1.30)
                sales_qty   = max(0, int(base * trend_mult * season_mult * noise))

                rows.append({
                    "sale_id":      sale_id,
                    "product_id":   int(prod["product_id"]),
                    "supplier_id":  int(prod["supplier_id"]),
                    "model":        prod["model"],
                    "product_type": prod["product_type"],
                    "price_usd":    float(price),
                    "year":         year,
                    "month":        month,
                    "sales_qty":    sales_qty,
                    "revenue_usd":  round(sales_qty * float(price), 2),
                    "lead_time_days": random.randint(15, 65),
                })
                sale_id += 1

    df = pd.DataFrame(rows)
    logger.info(
        f"Generated {len(df)} monthly sales records "
        f"({start_year}–{end_year}, {len(products_df)} products)."
    )
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Minimal test
    sample_products = pd.DataFrame([
        {"product_id": 1, "supplier_id": 1, "model": "KS-7A",
         "product_type": "Screw", "price_usd": 1800.0},
        {"product_id": 2, "supplier_id": 1, "model": "KS-37A",
         "product_type": "Screw", "price_usd": 6500.0},
    ])
    sp  = generate_supplier_products(sample_products)
    sal = generate_sales_history(sample_products)
    print(sp)
    print(sal.head(6))
