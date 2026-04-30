from flask import Flask, jsonify, render_template, request, redirect
from database.db_manager import DatabaseManager
from config import PG_DSN
import os
import pandas as pd

app = Flask(__name__, template_folder='templates', static_folder='static')

db = DatabaseManager(pg_dsn=PG_DSN, strict_pg=True)

# ═══════════════════════════════════════════════════════════════
# DASHBOARD & MAIN PAGES
# ═══════════════════════════════════════════════════════════════

@app.route('/')
def dashboard():
    db.connect()
    stats = {
        'suppliers': db.query("SELECT COUNT(*) as cnt FROM suppliers").iloc[0,0],
        'products': db.query("SELECT COUNT(*) as cnt FROM products").iloc[0,0],
        'sales': db.query("SELECT SUM(sales_qty) as total FROM sales_history").iloc[0,0] or 0,
        'revenue': db.query("SELECT SUM(revenue_usd) as total FROM sales_history").iloc[0,0] or 0,
    }
    db.close()
    return render_template('index.html', stats=stats)

# ═══════════════════════════════════════════════════════════════
# SUPPLIER ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/suppliers')
def api_suppliers():
    db.connect()
    suppliers = db.query("""
        SELECT supplier_id, company_name, country, city, website 
        FROM suppliers 
        ORDER BY company_name
    """).to_dict('records')
    db.close()
    return jsonify(suppliers)

@app.route('/api/suppliers/top')
def api_suppliers_top():
    """Top suppliers by revenue"""
    limit = request.args.get('limit', 10, type=int)
    db.connect()
    top = db.query(f"""
        SELECT s.supplier_id, s.company_name, s.country,
               COUNT(DISTINCT sp.product_id) as num_products,
               SUM(sh.revenue_usd) as total_revenue,
               SUM(sh.sales_qty) as total_units
        FROM suppliers s
        LEFT JOIN supplier_products sp ON s.supplier_id = sp.supplier_id
        LEFT JOIN sales_history sh ON sp.product_id = sh.product_id
        GROUP BY s.supplier_id, s.company_name, s.country
        ORDER BY total_revenue DESC NULLS LAST
        LIMIT {limit}
    """).to_dict('records')
    db.close()
    return jsonify(top)

@app.route('/api/suppliers/search')
def api_suppliers_search():
    """Search suppliers by name or country"""
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify([])
    
    db.connect()
    results = db.query(f"""
        SELECT supplier_id, company_name, country, city, website
        FROM suppliers
        WHERE company_name ILIKE '%{query}%' 
           OR city ILIKE '%{query}%'
           OR country ILIKE '%{query}%'
        LIMIT 20
    """).to_dict('records')
    db.close()
    return jsonify(results)

# ═══════════════════════════════════════════════════════════════
# PRODUCT ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/products')
def api_products():
    db.connect()
    products = db.query("""
        SELECT p.product_id, p.model, p.product_type, p.price_usd, s.company_name 
        FROM products p
        JOIN suppliers s ON p.supplier_id = s.supplier_id
        ORDER BY p.product_id
    """).to_dict('records')
    db.close()
    return jsonify(products)

@app.route('/api/products/top')
def api_products_top():
    """Top products by sales volume"""
    limit = request.args.get('limit', 10, type=int)
    db.connect()
    top = db.query(f"""
        SELECT p.product_id, p.model, p.product_type, p.price_usd,
               s.company_name,
               SUM(sh.sales_qty) as total_qty,
               SUM(sh.revenue_usd) as total_revenue,
               AVG(sh.sales_qty) as avg_monthly_qty
        FROM products p
        JOIN suppliers s ON p.supplier_id = s.supplier_id
        LEFT JOIN sales_history sh ON p.product_id = sh.product_id
        GROUP BY p.product_id, p.model, p.product_type, p.price_usd, s.company_name
        ORDER BY total_qty DESC NULLS LAST
        LIMIT {limit}
    """).to_dict('records')
    db.close()
    return jsonify(top)

@app.route('/api/products/by-type')
def api_products_by_type():
    """Products grouped by type"""
    db.connect()
    types = db.query("""
        SELECT product_type, COUNT(*) as count, 
               AVG(price_usd) as avg_price,
               MIN(price_usd) as min_price,
               MAX(price_usd) as max_price
        FROM products
        GROUP BY product_type
        ORDER BY count DESC
    """).to_dict('records')
    db.close()
    return jsonify(types)

# ═══════════════════════════════════════════════════════════════
# SALES & ANALYTICS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/sales')
def api_sales():
    db.connect()
    sales = db.query("""
        SELECT year, month, SUM(sales_qty) as total_qty, SUM(revenue_usd) as total_revenue
        FROM sales_history 
        GROUP BY year, month
        ORDER BY year DESC, month DESC 
        LIMIT 36
    """).to_dict('records')
    db.close()
    return jsonify(sales)

@app.route('/api/sales/trend')
def api_sales_trend():
    """Monthly sales trend"""
    db.connect()
    trend = db.query("""
        SELECT year, month, 
               SUM(sales_qty) as qty,
               SUM(revenue_usd) as revenue,
               COUNT(DISTINCT product_id) as num_products
        FROM sales_history
        GROUP BY year, month
        ORDER BY year, month DESC
        LIMIT 24
    """).to_dict('records')
    db.close()
    return jsonify(trend)

@app.route('/api/sales/by-supplier')
def api_sales_by_supplier():
    """Sales aggregated by supplier"""
    db.connect()
    by_supplier = db.query("""
        SELECT s.company_name, s.country,
               SUM(sh.sales_qty) as total_qty,
               SUM(sh.revenue_usd) as total_revenue,
               COUNT(DISTINCT sh.product_id) as num_products
        FROM sales_history sh
        JOIN supplier_products sp ON sh.product_id = sp.product_id
        JOIN suppliers s ON sp.supplier_id = s.supplier_id
        GROUP BY s.company_name, s.country
        ORDER BY total_revenue DESC
    """).to_dict('records')
    db.close()
    return jsonify(by_supplier)

# ═══════════════════════════════════════════════════════════════
# SUPPLY CHAIN & CONTACTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/supply-chain')
def api_supply_chain():
    db.connect()
    chain = db.get_supply_chain_view().to_dict('records')
    db.close()
    return jsonify(chain)

@app.route('/api/contacts')
def api_contacts():
    db.connect()
    contacts = db.query("""
        SELECT c.*, s.company_name, s.website
        FROM contacts c
        JOIN suppliers s ON c.supplier_id = s.supplier_id
        ORDER BY s.company_name
    """).to_dict('records')
    db.close()
    return jsonify(contacts)

# ═══════════════════════════════════════════════════════════════
# FORECAST & PREDICTIONS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/forecast')
def api_forecast():
    db.connect()
    forecast = db.query("""
        SELECT * FROM forecast ORDER BY year, month LIMIT 100
    """).to_dict('records')
    db.close()
    return jsonify(forecast)

@app.route('/api/forecast/summary')
def api_forecast_summary():
    """Forecast summary by product type"""
    db.connect()
    summary = db.query("""
        SELECT p.product_type,
               SUM(f.forecast_qty) as forecasted_qty,
               COUNT(DISTINCT f.product_id) as num_products
        FROM forecast f
        JOIN products p ON f.product_id = p.product_id
        GROUP BY p.product_type
        ORDER BY forecasted_qty DESC
    """).to_dict('records')
    db.close()
    return jsonify(summary)

# ═══════════════════════════════════════════════════════════════
# ANALYTICS & INSIGHTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/analytics/overview')
def api_analytics_overview():
    """System-wide analytics overview"""
    db.connect()
    overview = {
        'total_suppliers': db.query("SELECT COUNT(*) as cnt FROM suppliers").iloc[0,0],
        'total_products': db.query("SELECT COUNT(*) as cnt FROM products").iloc[0,0],
        'total_sales_qty': int(db.query("SELECT SUM(sales_qty) as total FROM sales_history").iloc[0,0] or 0),
        'total_revenue': float(db.query("SELECT SUM(revenue_usd) as total FROM sales_history").iloc[0,0] or 0),
        'avg_price': float(db.query("SELECT AVG(price_usd) as avg FROM products").iloc[0,0] or 0),
        'top_country': db.query("SELECT country FROM suppliers GROUP BY country ORDER BY COUNT(*) DESC LIMIT 1").iloc[0,0] if len(db.query("SELECT country FROM suppliers")) > 0 else "China",
    }
    db.close()
    return jsonify(overview)

@app.route('/api/analytics/market-share')
def api_market_share():
    """Market share by supplier"""
    db.connect()
    share = db.query("""
        SELECT s.company_name,
               ROUND(100.0 * SUM(sh.revenue_usd) / (SELECT SUM(revenue_usd) FROM sales_history), 2) as market_share_pct,
               SUM(sh.revenue_usd) as revenue
        FROM sales_history sh
        JOIN supplier_products sp ON sh.product_id = sp.product_id
        JOIN suppliers s ON sp.supplier_id = s.supplier_id
        GROUP BY s.company_name
        ORDER BY market_share_pct DESC
        LIMIT 10
    """).to_dict('records')
    db.close()
    return jsonify(share)

@app.route('/api/analytics/price-distribution')
def api_price_distribution():
    """Product price distribution analysis"""
    db.connect()
    dist = db.query("""
        SELECT 
            CASE 
                WHEN price_usd < 1000 THEN 'Budget (<$1K)'
                WHEN price_usd < 5000 THEN 'Mid-range ($1K-$5K)'
                WHEN price_usd < 10000 THEN 'Premium ($5K-$10K)'
                ELSE 'Enterprise (>$10K)'
            END as price_range,
            COUNT(*) as num_products,
            ROUND(AVG(price_usd), 2) as avg_price
        FROM products
        GROUP BY price_range
        ORDER BY avg_price
    """).to_dict('records')
    db.close()
    return jsonify(dist)

# ═══════════════════════════════════════════════════════════════
# HTML ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route('/suppliers')
def suppliers():
    return render_template('suppliers.html')

@app.route('/products')
def products():
    return render_template('products.html')

@app.route('/supply-chain')
def supply_chain():
    return render_template('supply-chain.html')

@app.route('/forecast')
def forecast():
    return render_template('forecast.html')

@app.route('/contacts')
def contacts():
    return render_template('contacts.html')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html') if os.path.exists('templates/analytics.html') else redirect('/'), 200

# ═══════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════

@app.route('/api/health')
def health():
    """Health check endpoint"""
    try:
        db.connect()
        db.query("SELECT 1")
        db.close()
        return jsonify({"status": "ok", "message": "System operational"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 503

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    app.run(debug=True, port=5422, host='0.0.0.0')
