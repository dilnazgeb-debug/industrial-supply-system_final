"""
cleaning/data_cleaner.py
------------------------
Data Cleaning & Preprocessing Module

Converts raw scraped dicts into clean, normalised pandas DataFrames
for suppliers, products, and contacts.

Steps
-----
1. Flatten nested structures
2. Normalise text (strip, title-case)
3. Standardise phone numbers
4. Validate / normalise email addresses
5. Remove duplicates
6. Handle missing values
7. Type casting
"""

import re
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def normalize_text(value) -> str | None:
    """Strip whitespace, collapse internal spaces, title-case."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    s = str(value).strip()
    s = re.sub(r"\s+", " ", s)
    return s if s else None


def normalize_phone(phone: str | None) -> str | None:
    """
    Standardise phone numbers to E.164-like format +XXXXXXXXXXX
    Strips spaces, dashes, parentheses; keeps leading +.
    """
    if not phone:
        return None
    digits = re.sub(r"[^\d+]", "", str(phone))
    # Ensure starts with +
    if not digits.startswith("+"):
        digits = "+" + digits
    # Reject garbage (too short / too long)
    if len(digits) < 8 or len(digits) > 17:
        return None
    return digits


def normalize_email(email: str | None) -> str | None:
    """Lowercase and basic format validation."""
    if not email:
        return None
    email = str(email).strip().lower()
    pattern = r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$"
    return email if re.match(pattern, email) else None


def normalize_price(price) -> float | None:
    """Convert price to float; return None if not parseable."""
    if price is None:
        return None
    try:
        return float(price)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Flattening raw scraper output
# ---------------------------------------------------------------------------

def flatten_suppliers(raw_records: list[dict]) -> pd.DataFrame:
    """
    Flatten the raw supplier records from the scraper into a DataFrame.

    Returns
    -------
    DataFrame with columns:
        supplier_id, company_name, country, city, website, data_source
    """
    rows = []
    for idx, rec in enumerate(raw_records, start=1):
        rows.append({
            "supplier_id":   idx,
            "company_name":  normalize_text(rec.get("company_name")),
            "country":       normalize_text(rec.get("country", "China")),
            "city":          normalize_text(rec.get("city")),
            "website":       normalize_text(rec.get("website")),
            "data_source":   rec.get("_source", "unknown"),
        })

    df = pd.DataFrame(rows)

    # 🧹 De-duplication: Remove duplicates on website URL (priority 1)
    before = len(df)
    df_valid_url = df[df["website"].notna()].copy()
    df_no_url = df[df["website"].isna()].copy()
    
    df_valid_url.drop_duplicates(subset=["website"], keep="first", inplace=True)
    df = pd.concat([df_valid_url, df_no_url], ignore_index=True)
    
    if before > len(df):
        logger.info(f"Removed {before - len(df)} duplicate supplier URLs.")
    
    # 🧹 De-duplication: Remove duplicates on company_name (priority 2)
    # This catches the same company scraped from different sources
    before = len(df)
    df.drop_duplicates(subset=["company_name"], keep="first", inplace=True)
    df.reset_index(drop=True, inplace=True)
    
    if before > len(df):
        logger.info(f"Removed {before - len(df)} duplicate supplier names.")

    # Fill missing country
    df["country"].fillna("China", inplace=True)

    logger.info(f"Clean supplier table: {len(df)} rows.")
    return df


def flatten_products(raw_records: list[dict],
                     supplier_df: pd.DataFrame) -> pd.DataFrame:
    """
    Expand the products list inside each supplier record into a flat DataFrame.

    Returns
    -------
    DataFrame with columns:
        product_id, supplier_id, model, product_type,
        pressure_bar, power_kw, capacity_m3min, price_usd
    """
    # Build a website → supplier_id lookup
    url_to_sid = dict(zip(supplier_df["website"], supplier_df["supplier_id"]))

    rows = []
    pid  = 1
    for rec in raw_records:
        sid = url_to_sid.get(normalize_text(rec.get("website")))
        if sid is None:
            continue
        for prod in rec.get("products", []):
            rows.append({
                "product_id":     pid,
                "supplier_id":    sid,
                "model":          normalize_text(prod.get("model")),
                "product_type":   normalize_text(prod.get("type")),
                "pressure_bar":   normalize_price(prod.get("pressure_bar")),
                "power_kw":       normalize_price(prod.get("power_kw")),
                "capacity_m3min": normalize_price(prod.get("capacity_m3min")),
                "price_usd":      normalize_price(prod.get("price_usd")),
            })
            pid += 1

    df = pd.DataFrame(rows)
    if df.empty:
        logger.warning("No products found after flattening.")
        return df

    # Remove fully duplicate product rows
    df.drop_duplicates(subset=["supplier_id", "model"], keep="first", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Type safety
    for col in ["pressure_bar", "power_kw", "capacity_m3min", "price_usd"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    logger.info(f"Clean product table: {len(df)} rows.")
    return df


def flatten_contacts(raw_records: list[dict],
                     supplier_df: pd.DataFrame) -> pd.DataFrame:
    """
    Flatten contact information from each supplier record.

    Returns
    -------
    DataFrame with columns:
        contact_id, supplier_id, phone, email, whatsapp, wechat
    """
    url_to_sid = dict(zip(supplier_df["website"], supplier_df["supplier_id"]))

    rows = []
    cid  = 1
    for rec in raw_records:
        sid = url_to_sid.get(normalize_text(rec.get("website")))
        if sid is None:
            continue
        contacts = rec.get("contacts", {})
        rows.append({
            "contact_id":  cid,
            "supplier_id": sid,
            "phone":       normalize_phone(contacts.get("phone")),
            "email":       normalize_email(contacts.get("email")),
            "whatsapp":    normalize_phone(contacts.get("whatsapp")),
            "wechat":      normalize_text(contacts.get("wechat")),
        })
        cid += 1

    df = pd.DataFrame(rows)
    if df.empty:
        logger.warning("No contacts found after flattening.")
        return df

    df.drop_duplicates(subset=["supplier_id"], keep="first", inplace=True)
    df.reset_index(drop=True, inplace=True)

    logger.info(f"Clean contact table: {len(df)} rows.")
    return df


# ---------------------------------------------------------------------------
# Master cleaning pipeline
# ---------------------------------------------------------------------------

def clean_all(raw_records: list[dict]) -> dict[str, pd.DataFrame]:
    """
    Run the full cleaning pipeline on raw scraped records.

    Returns
    -------
    dict with keys: 'suppliers', 'products', 'contacts'
    """
    logger.info("=== Starting data cleaning pipeline ===")

    suppliers = flatten_suppliers(raw_records)
    products  = flatten_products(raw_records, suppliers)
    contacts  = flatten_contacts(raw_records, suppliers)

    logger.info("=== Data cleaning complete ===")
    return {
        "suppliers": suppliers,
        "products":  products,
        "contacts":  contacts,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Quick sanity check with dummy data
    sample = [
        {
            "company_name": "  Test Compressor Co. ",
            "country": "China",
            "city": "Shanghai",
            "website": "https://www.testco.com",
            "products": [
                {"model": "TC-10", "type": "Screw", "pressure_bar": 8,
                 "power_kw": 10, "capacity_m3min": 1.5, "price_usd": 2000}
            ],
            "contacts": {
                "phone": "+86 21 1234 5678",
                "email": " Sales@TestCo.COM ",
                "whatsapp": None,
                "wechat": "testco_wechat",
            },
            "_source": "simulated",
        }
    ]
    result = clean_all(sample)
    for name, df in result.items():
        print(f"\n--- {name} ---")
        print(df.to_string(index=False))
