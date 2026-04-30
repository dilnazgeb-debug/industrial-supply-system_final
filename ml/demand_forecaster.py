"""
ml/demand_forecaster.py
-----------------------
Machine Learning Module – Demand Forecasting

Pipeline
--------
1. Feature engineering from sales history
2. Train / test split (last 6 months = test)
3. RandomForestRegressor (primary) + LinearRegression (baseline)
4. Evaluation: MAE, RMSE, R²
5. Feature importance analysis
6. Forecast next 6 months

Target : sales_qty  (monthly units sold per product)

Features
--------
- price_usd               (continuous)
- lead_time_days          (continuous)
- month                   (cyclic → sin/cos encoding)
- year_offset             (trend: years since 2022)
- product_type_enc        (label-encoded)
- supplier_id             (label-encoded)
- is_peak_season          (bool: Apr–Jun)
- rolling_3m_avg          (3-month lagged average – momentum)
"""

import logging
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def engineer_features(sales_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add ML-ready feature columns to the sales history DataFrame.
    """
    df = sales_df.copy()

    # Sort for lag features
    df.sort_values(["product_id", "year", "month"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Cyclic month encoding (captures seasonality without ordinal bias)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    # Linear trend (years since dataset start)
    df["year_offset"] = df["year"] - df["year"].min()

    # Peak season flag: Apr, May, Jun
    df["is_peak_season"] = df["month"].isin([4, 5, 6]).astype(int)

    # 3-month rolling average (lagged to avoid data leakage)
    df["rolling_3m_avg"] = (
        df.groupby("product_id")["sales_qty"]
          .transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
    )
    df["rolling_3m_avg"].fillna(df["sales_qty"].mean(), inplace=True)

    # Encode categoricals
    le_type = LabelEncoder()
    le_sup  = LabelEncoder()
    df["product_type_enc"] = le_type.fit_transform(df["product_type"].fillna("Unknown"))
    df["supplier_enc"]     = le_sup.fit_transform(df["supplier_id"].astype(str))

    return df, le_type, le_sup


FEATURE_COLS = [
    "price_usd", "lead_time_days",
    "month_sin", "month_cos",
    "year_offset", "is_peak_season",
    "rolling_3m_avg",
    "product_type_enc", "supplier_enc",
]
TARGET_COL = "sales_qty"


# ---------------------------------------------------------------------------
# Model training & evaluation
# ---------------------------------------------------------------------------

def train_and_evaluate(sales_df: pd.DataFrame) -> dict:
    """
    Full ML pipeline: engineer → split → train → evaluate.

    Parameters
    ----------
    sales_df : output of generate_sales_history()

    Returns
    -------
    dict with keys:
        rf_model, lr_model,
        X_test, y_test, y_pred_rf, y_pred_lr,
        metrics, feature_importance, df_featured
    """
    logger.info("=== Starting ML pipeline ===")

    # Feature engineering
    df, le_type, le_sup = engineer_features(sales_df)
    df.dropna(subset=FEATURE_COLS + [TARGET_COL], inplace=True)

    X = df[FEATURE_COLS].values
    y = df[TARGET_COL].values

    # Temporal split: last 6 months as test set
    # (avoids data leakage from rolling features)
    split_idx = int(len(df) * 0.85)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]
    logger.info(f"Train size: {len(X_train)}, Test size: {len(X_test)}")

    # ---- Random Forest ----
    rf = RandomForestRegressor(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=3,
        random_state=42,
        n_jobs=-1,
    )
    rf.fit(X_train, y_train)
    y_pred_rf = rf.predict(X_test)

    # ---- Linear Regression (baseline) ----
    lr = LinearRegression()
    lr.fit(X_train, y_train)
    y_pred_lr = lr.predict(X_test)

    # ---- Metrics ----
    def calc_metrics(y_true, y_pred, name):
        mae  = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        ss_res = np.sum((y_true - y_pred) ** 2)
        ss_tot = np.sum((y_true - y_true.mean()) ** 2)
        r2   = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        logger.info(f"{name:20s} | MAE={mae:.2f}  RMSE={rmse:.2f}  R²={r2:.3f}")
        return {"model": name, "MAE": round(mae, 2),
                "RMSE": round(rmse, 2), "R2": round(r2, 3)}

    metrics = [
        calc_metrics(y_test, y_pred_rf, "RandomForest"),
        calc_metrics(y_test, y_pred_lr, "LinearRegression"),
    ]

    # ---- Feature importance ----
    fi = pd.DataFrame({
        "feature":   FEATURE_COLS,
        "importance": rf.feature_importances_,
    }).sort_values("importance", ascending=False).reset_index(drop=True)
    logger.info("Feature importances:\n" + fi.to_string(index=False))

    logger.info("=== ML pipeline complete ===")
    return {
        "rf_model":         rf,
        "lr_model":         lr,
        "X_train":          X_train,
        "X_test":           X_test,
        "y_train":          y_train,
        "y_test":           y_test,
        "y_pred_rf":        y_pred_rf,
        "y_pred_lr":        y_pred_lr,
        "metrics":          metrics,
        "feature_importance": fi,
        "df_featured":      df,
        "feature_cols":     FEATURE_COLS,
    }


def forecast_next_n_months(ml_results: dict,
                            products_df: pd.DataFrame,
                            n_months: int = 6) -> pd.DataFrame:
    """
    Use the trained RF model to forecast the next n months for each product.

    Returns
    -------
    DataFrame with columns: product_id, model, year, month, forecast_qty
    """
    rf = ml_results["rf_model"]
    df = ml_results["df_featured"]
    feature_cols = ml_results.get("feature_cols", FEATURE_COLS)

    # Find the latest date in the data
    last_year  = int(df["year"].max())
    last_month = int(df[df["year"] == last_year]["month"].max())

    # Get per-product averages for non-time features
    product_avg = (
        df.groupby("product_id")
          .agg(price_usd        =("price_usd",        "mean"),
               lead_time_days   =("lead_time_days",   "mean"),
               rolling_3m_avg   =("rolling_3m_avg",   "mean"),
               product_type_enc =("product_type_enc", "first"),
               supplier_enc     =("supplier_enc",     "first"))
          .reset_index()
    )

    # ✅ ВАЛИДАЦИЯ: Заполнить NaN значения глобальными средними
    for col in ["price_usd", "lead_time_days", "rolling_3m_avg"]:
        global_mean = df[col].mean()
        product_avg[col].fillna(global_mean, inplace=True)
        # Проверка на Inf
        product_avg[col] = product_avg[col].replace([np.inf, -np.inf], global_mean)

    rows = []
    for m_offset in range(1, n_months + 1):
        total_months = last_month + m_offset
        f_year  = last_year + (total_months - 1) // 12
        f_month = ((total_months - 1) % 12) + 1

        for _, prod in product_avg.iterrows():
            try:
                feat = {
                    "price_usd":         max(0, float(prod["price_usd"])),
                    "lead_time_days":    max(0, float(prod["lead_time_days"])),
                    "month_sin":         np.sin(2 * np.pi * f_month / 12),
                    "month_cos":         np.cos(2 * np.pi * f_month / 12),
                    "year_offset":       float(f_year - df["year"].min()),
                    "is_peak_season":    int(f_month in [4, 5, 6]),
                    "rolling_3m_avg":    max(0, float(prod["rolling_3m_avg"])),
                    "product_type_enc":  float(prod["product_type_enc"]),
                    "supplier_enc":      float(prod["supplier_enc"]),
                }
                
                # ✅ ПРОВЕРКА НАЛИЧИЯ ВСЕХ ТРЕБУЕМЫХ ФИЧ
                X = np.array([[feat.get(c, 0) for c in feature_cols]])
                
                # ✅ ПРОВЕРКА НА NaN И INF В ВХОДНЫХ ДАННЫХ
                if np.any(np.isnan(X)) or np.any(np.isinf(X)):
                    logger.warning(f"Skipping invalid features for product {prod['product_id']}")
                    continue
                
                qty = max(0, int(rf.predict(X)[0]))

                prod_info = products_df[products_df["product_id"] == prod["product_id"]]
                model_name = prod_info["model"].values[0] if len(prod_info) else "Unknown"

                rows.append({
                    "product_id":   int(prod["product_id"]),
                    "model":        model_name,
                    "year":         f_year,
                    "month":        f_month,
                    "forecast_qty": qty,
                })
            except Exception as e:
                logger.warning(f"Error forecasting product {prod['product_id']}: {e}")
                continue

    forecast_df = pd.DataFrame(rows)
    logger.info(f"Forecasted {n_months} months for {len(product_avg)} products. "
                f"Generated {len(forecast_df)} forecast rows.")
    return forecast_df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Quick test with synthetic data
    import sys
    sys.path.insert(0, "..")
    from database.supply_chain_sim import generate_sales_history
    from cleaning.data_cleaner import flatten_products
    # Minimal inline products
    prods = pd.DataFrame([
        {"product_id": 1, "supplier_id": 1, "model": "KS-7A",
         "product_type": "Screw", "price_usd": 1800.0},
        {"product_id": 2, "supplier_id": 2, "model": "DA-22A",
         "product_type": "Variable", "price_usd": 3900.0},
    ])
    sales = generate_sales_history(prods)
    result = train_and_evaluate(sales)
    for m in result["metrics"]:
        print(m)
