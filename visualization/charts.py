"""
visualization/charts.py
-----------------------
Visualization Module

Generates and saves the following plots:
1. sales_trend.png          – Monthly total sales quantity over time
2. predicted_vs_actual.png  – RF predictions vs actual (test set)
3. top_suppliers.png        – Suppliers ranked by product count
4. price_vs_demand.png      – Scatter: price vs avg monthly demand
5. feature_importance.png   – Top feature importances from RF model
6. revenue_trend.png        – Monthly revenue in USD
"""

import os
import logging
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")          # non-interactive backend for server/file output
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------
PALETTE   = ["#2563EB", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899"]
BG_COLOR  = "#F8FAFC"
GRID_COLOR = "#E2E8F0"
FONT_FAMILY = "DejaVu Sans"

plt.rcParams.update({
    "figure.facecolor":   BG_COLOR,
    "axes.facecolor":     BG_COLOR,
    "axes.edgecolor":     "#CBD5E1",
    "axes.grid":          True,
    "grid.color":         GRID_COLOR,
    "grid.linestyle":     "--",
    "grid.alpha":         0.7,
    "font.family":        FONT_FAMILY,
    "axes.titlepad":      12,
    "axes.titlesize":     13,
    "axes.labelsize":     11,
})

OUTPUT_DIR = "outputs"


def _ensure_output_dir(path: str = OUTPUT_DIR):
    os.makedirs(path, exist_ok=True)


def _save(fig, filename: str, output_dir: str = OUTPUT_DIR):
    path = os.path.join(output_dir, filename)
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    logger.info(f"Saved: {path}")
    return path


# ---------------------------------------------------------------------------
# 1. Sales trend over time
# ---------------------------------------------------------------------------
def plot_sales_trend(sales_df: pd.DataFrame, output_dir: str = OUTPUT_DIR) -> str:
    _ensure_output_dir(output_dir)
    monthly = (
        sales_df.groupby(["year", "month"])["sales_qty"]
                .sum()
                .reset_index()
    )
    monthly["date"] = pd.to_datetime(
        monthly["year"].astype(str) + "-" + monthly["month"].astype(str) + "-01"
    )
    monthly.sort_values("date", inplace=True)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.fill_between(monthly["date"], monthly["sales_qty"],
                    alpha=0.15, color=PALETTE[0])
    ax.plot(monthly["date"], monthly["sales_qty"],
            color=PALETTE[0], linewidth=2.2, marker="o", markersize=4)

    ax.set_title("Monthly Total Sales Volume – All Products", fontweight="bold")
    ax.set_xlabel("Month")
    ax.set_ylabel("Total Units Sold")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.xticks(rotation=35)
    fig.tight_layout()
    return _save(fig, "sales_trend.png", output_dir)


# ---------------------------------------------------------------------------
# 2. Predicted vs Actual (test set)
# ---------------------------------------------------------------------------
def plot_predicted_vs_actual(y_test: np.ndarray,
                              y_pred_rf: np.ndarray,
                              y_pred_lr: np.ndarray,
                              output_dir: str = OUTPUT_DIR) -> str:
    _ensure_output_dir(output_dir)
    idx = np.arange(len(y_test))

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    for ax, y_pred, name, color in [
        (axes[0], y_pred_rf, "Random Forest", PALETTE[0]),
        (axes[1], y_pred_lr, "Linear Regression", PALETTE[1]),
    ]:
        ax.scatter(y_test, y_pred, alpha=0.35, s=18, color=color, label="Samples")
        lims = [min(y_test.min(), y_pred.min()), max(y_test.max(), y_pred.max())]
        ax.plot(lims, lims, "r--", linewidth=1.5, label="Perfect fit")
        ax.set_title(f"{name}: Predicted vs Actual", fontweight="bold")
        ax.set_xlabel("Actual Sales Qty")
        ax.set_ylabel("Predicted Sales Qty")
        ax.legend(fontsize=9)

    fig.suptitle("Demand Forecast – Model Comparison (Test Set)", fontsize=14, fontweight="bold")
    fig.tight_layout()
    return _save(fig, "predicted_vs_actual.png", output_dir)


# ---------------------------------------------------------------------------
# 3. Top suppliers by product count
# ---------------------------------------------------------------------------
def plot_top_suppliers(suppliers_df: pd.DataFrame,
                       products_df:  pd.DataFrame,
                       output_dir:   str = OUTPUT_DIR) -> str:
    _ensure_output_dir(output_dir)
    counts = (
        products_df.groupby("supplier_id")["product_id"]
                   .count()
                   .reset_index()
                   .rename(columns={"product_id": "product_count"})
    )
    merged = counts.merge(suppliers_df[["supplier_id", "company_name"]], on="supplier_id")
    merged.sort_values("product_count", ascending=True, inplace=True)

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(merged["company_name"], merged["product_count"],
                   color=PALETTE[:len(merged)] * 3)
    ax.set_title("Suppliers Ranked by Number of Products in Catalogue",
                 fontweight="bold")
    ax.set_xlabel("Number of Products")
    for bar in bars:
        w = bar.get_width()
        ax.text(w + 0.05, bar.get_y() + bar.get_height() / 2,
                str(int(w)), va="center", fontsize=9)
    fig.tight_layout()
    return _save(fig, "top_suppliers.png", output_dir)


# ---------------------------------------------------------------------------
# 4. Price vs Average Demand
# ---------------------------------------------------------------------------
def plot_price_vs_demand(sales_df: pd.DataFrame,
                         products_df: pd.DataFrame,
                         output_dir: str = OUTPUT_DIR) -> str:
    _ensure_output_dir(output_dir)
    avg_sales = (
        sales_df.groupby("product_id")["sales_qty"]
                .mean()
                .reset_index()
                .rename(columns={"sales_qty": "avg_monthly_sales"})
    )
    merged = avg_sales.merge(
        products_df[["product_id", "price_usd", "product_type", "model"]],
        on="product_id"
    )

    fig, ax = plt.subplots(figsize=(10, 6))
    types = merged["product_type"].unique()
    for i, ptype in enumerate(types):
        sub = merged[merged["product_type"] == ptype]
        ax.scatter(sub["price_usd"], sub["avg_monthly_sales"],
                   label=ptype, s=80, alpha=0.8,
                   color=PALETTE[i % len(PALETTE)])

    # Trend line
    if len(merged) > 2:
        z = np.polyfit(merged["price_usd"].fillna(0),
                       merged["avg_monthly_sales"], 1)
        p = np.poly1d(z)
        xs = np.linspace(merged["price_usd"].min(), merged["price_usd"].max(), 100)
        ax.plot(xs, p(xs), "r--", linewidth=1.5, alpha=0.6, label="Trend")

    ax.set_title("Price vs Average Monthly Demand by Product Type",
                 fontweight="bold")
    ax.set_xlabel("Unit Price (USD)")
    ax.set_ylabel("Avg Monthly Sales (units)")
    ax.legend()
    fig.tight_layout()
    return _save(fig, "price_vs_demand.png", output_dir)


# ---------------------------------------------------------------------------
# 5. Feature importance
# ---------------------------------------------------------------------------
def plot_feature_importance(fi_df: pd.DataFrame,
                             output_dir: str = OUTPUT_DIR) -> str:
    _ensure_output_dir(output_dir)
    top = fi_df.head(9).sort_values("importance", ascending=True)

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.barh(top["feature"], top["importance"],
                   color=PALETTE[0], alpha=0.85)
    ax.set_title("Random Forest – Feature Importances (Top 9)",
                 fontweight="bold")
    ax.set_xlabel("Importance Score")
    for bar in bars:
        w = bar.get_width()
        ax.text(w + 0.001, bar.get_y() + bar.get_height() / 2,
                f"{w:.3f}", va="center", fontsize=9)
    fig.tight_layout()
    return _save(fig, "feature_importance.png", output_dir)


# ---------------------------------------------------------------------------
# 6. Monthly revenue trend
# ---------------------------------------------------------------------------
def plot_revenue_trend(sales_df: pd.DataFrame,
                       output_dir: str = OUTPUT_DIR) -> str:
    _ensure_output_dir(output_dir)
    monthly = (
        sales_df.groupby(["year", "month"])["revenue_usd"]
                .sum()
                .reset_index()
    )
    monthly["date"] = pd.to_datetime(
        monthly["year"].astype(str) + "-" + monthly["month"].astype(str) + "-01"
    )
    monthly.sort_values("date", inplace=True)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.fill_between(monthly["date"], monthly["revenue_usd"] / 1000,
                    alpha=0.15, color=PALETTE[2])
    ax.plot(monthly["date"], monthly["revenue_usd"] / 1000,
            color=PALETTE[2], linewidth=2.2, marker="o", markersize=4)

    ax.set_title("Monthly Revenue – All Products (USD thousands)",
                 fontweight="bold")
    ax.set_xlabel("Month")
    ax.set_ylabel("Revenue (USD K)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.xticks(rotation=35)
    fig.tight_layout()
    return _save(fig, "revenue_trend.png", output_dir)


# ---------------------------------------------------------------------------
# 7. Forecast vs history for a single top product
# ---------------------------------------------------------------------------
def plot_forecast(sales_df: pd.DataFrame,
                  forecast_df: pd.DataFrame,
                  output_dir: str = OUTPUT_DIR) -> str:
    _ensure_output_dir(output_dir)

    # Pick the product with highest total sales
    top_pid = sales_df.groupby("product_id")["sales_qty"].sum().idxmax()
    top_name = sales_df[sales_df["product_id"] == top_pid]["model"].iloc[0]

    hist = (
        sales_df[sales_df["product_id"] == top_pid]
        .groupby(["year", "month"])["sales_qty"].sum().reset_index()
    )
    hist["date"] = pd.to_datetime(
        hist["year"].astype(str) + "-" + hist["month"].astype(str) + "-01"
    )

    fc = forecast_df[forecast_df["product_id"] == top_pid].copy()
    fc["date"] = pd.to_datetime(
        fc["year"].astype(str) + "-" + fc["month"].astype(str) + "-01"
    )

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(hist["date"], hist["sales_qty"],
            color=PALETTE[0], linewidth=2.2, label="Historical")
    ax.plot(fc["date"], fc["forecast_qty"],
            color=PALETTE[3], linewidth=2.2, linestyle="--",
            marker="D", markersize=5, label="Forecast (RF)")

    ax.axvline(x=hist["date"].max(), color="#94A3B8",
               linestyle=":", linewidth=1.5, label="Forecast start")
    ax.set_title(f"Demand Forecast – {top_name}", fontweight="bold")
    ax.set_xlabel("Month")
    ax.set_ylabel("Units Sold")
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.xticks(rotation=35)
    fig.tight_layout()
    return _save(fig, "forecast_top_product.png", output_dir)


# ---------------------------------------------------------------------------
# Generate all charts at once
# ---------------------------------------------------------------------------
def generate_all_charts(sales_df: pd.DataFrame,
                         suppliers_df: pd.DataFrame,
                         products_df:  pd.DataFrame,
                         ml_results:   dict,
                         forecast_df:  pd.DataFrame,
                         output_dir:   str = OUTPUT_DIR) -> list[str]:
    paths = []
    paths.append(plot_sales_trend(sales_df, output_dir))
    paths.append(plot_predicted_vs_actual(
        ml_results["y_test"], ml_results["y_pred_rf"], ml_results["y_pred_lr"],
        output_dir))
    paths.append(plot_top_suppliers(suppliers_df, products_df, output_dir))
    paths.append(plot_price_vs_demand(sales_df, products_df, output_dir))
    paths.append(plot_feature_importance(ml_results["feature_importance"], output_dir))
    paths.append(plot_revenue_trend(sales_df, output_dir))
    paths.append(plot_forecast(sales_df, forecast_df, output_dir))
    logger.info(f"All {len(paths)} charts saved to '{output_dir}/'.")
    return paths
