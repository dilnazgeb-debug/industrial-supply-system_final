"""
Flask Hybrid Application - PostgreSQL + JSON Mock Data
========================================================

Two-mode application:
- LOCAL (Development): PostgreSQL via SQLAlchemy
- PRODUCTION (Cloud): Static JSON data (demo_data.json)

Environment Detection: DATABASE_URL variable
"""

import os
import json
import logging
from functools import wraps
from datetime import datetime
import debug_parser

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import func
from analytics import DEFAULT_VALUES
from analytics import predict_risk_from_features, DEFAULT_VALUES
from analytics import get_structured_data_via_llm

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import jsonify

# Import analytics module for intelligent model dispatcher
try:
    from analytics import intelligent_audit, format_audit_for_display
    ANALYTICS_AVAILABLE = True
except ImportError:
    ANALYTICS_AVAILABLE = False

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

app = Flask(__name__)
app.secret_key = "your-secret-key-change-in-production"

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


DB_CONFIG = {
    "host": "localhost",
    "database": "supply_chain_data_lake",
    "user": "analytics",
    "password": "secure_password_123", # insert your own password here
    "port": "5432",
    "connect_timeout": 1
}

# ═══════════════════════════════════════════════════════════════════
# ENVIRONMENT DETECTION
# ═══════════════════════════════════════════════════════════════════


DATABASE_URL = os.environ.get('DATABASE_URL')
IS_PRODUCTION_MODE = DATABASE_URL is None or DATABASE_URL == ""

if IS_PRODUCTION_MODE:
    logger.info("🔄 MODE: PRODUCTION (JSON Mock Data)")
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    DATA_MODE = "JSON (Demo Mode)"
else:
    logger.info("🔄 MODE: LOCAL (PostgreSQL Database)")
    # Fix for PostgreSQL URI compatibility
    if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    DATA_MODE = "PostgreSQL Database"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ═══════════════════════════════════════════════════════════════════
# DATABASE INITIALIZATION
# ═══════════════════════════════════════════════════════════════════

db = SQLAlchemy(app)


class IndustrialEquipment(db.Model):
    """
    Industrial Equipment Model
    
    Columns:
    - id: Primary key
    - category: Equipment category (e.g., 'Compressor', 'Pump')
    - brand: Manufacturer brand
    - model: Equipment model number
    - specs: Technical specifications (JSON or text)
    - status: Current status (active, maintenance, discontinued)
    - is_discontinued: Boolean flag for discontinued products
    """
    __tablename__ = 'industrial_equipment'
    
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(100), nullable=False, index=True)
    brand = db.Column(db.String(100), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    specs = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), default='active')
    is_discontinued = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        """Convert model instance to dictionary"""
        return {
            'id': self.id,
            'category': self.category,
            'brand': self.brand,
            'model': self.model,
            'specs': self.specs,
            'status': self.status,
            'is_discontinued': self.is_discontinued,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ═══════════════════════════════════════════════════════════════════
# JSON DATA LOADER (for Production Mode)
# ═══════════════════════════════════════════════════════════════════

class JSONDataManager:
    """Manage demo data from JSON file"""
    
    def __init__(self, json_file='demo_data.json'):
        self.json_file = json_file
        self.data = self._load_json()
    
    def _load_json(self):
        """Load JSON data from file"""
        try:
            if os.path.exists(self.json_file):
                with open(self.json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"✅ JSON loaded: {len(data)} records from {self.json_file}")
                    return data
            else:
                logger.error(f"❌ JSON file not found: {self.json_file}")
                return self._get_default_data()
        except Exception as e:
            logger.error(f"❌ Error loading JSON: {e}")
            return self._get_default_data()
    
    def _get_default_data(self):
        """Return default data if JSON fails"""
        return [
            {
                'id': 1,
                'category': 'Compressor',
                'brand': 'Kaishan',
                'model': 'KS-30',
                'specs': '30 kW, 3-phase, 8 bar',
                'status': 'active',
                'is_discontinued': False
            },
            {
                'id': 2,
                'category': 'Pump',
                'brand': 'Atlas',
                'model': 'AP-50',
                'specs': '50 m³/h, 100m head',
                'status': 'active',
                'is_discontinued': False
            }
        ]
    
    def get_all(self, category=None):
        """Get all equipment or filtered by category"""
        data = self.data
        if category:
            data = [item for item in data if item.get('category', '').lower() == category.lower()]
        return data
    
    def get_by_id(self, equipment_id):
        """Get equipment by ID"""
        for item in self.data:
            if item.get('id') == equipment_id:
                return item
        return None
    
    def get_categories(self):
        """Get unique categories"""
        categories = set()
        for item in self.data:
            if 'category' in item:
                categories.add(item['category'])
        return sorted(list(categories))


# Initialize JSON manager
json_manager = JSONDataManager()

# ═══════════════════════════════════════════════════════════════════
# ADMIN CREDENTIALS
# ═══════════════════════════════════════════════════════════════════

ADMIN_USERS = {
    'dilnazshanova': {
        'password': generate_password_hash('Aa1234'),
        'email': 'dilnazshanova@example.com',
        'role': 'admin'
    }
}


# ═══════════════════════════════════════════════════════════════════
# DECORATORS
# ═══════════════════════════════════════════════════════════════════

def login_required(f):
    """Require login before accessing route"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in first', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in first', 'warning')
            return redirect(url_for('login'))
        
        username = session.get('username')
        if username not in ADMIN_USERS:
            flash('Access denied. Admin privileges required', 'danger')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function



def get_mock_data():
    """Return mock data if database unavailable"""
    return [
        {
            "company_name": "Kaishan Group (Demo)",
            "model": "KRSP-20",
            "product_type": "Винтовой",
            "price_usd": 4500,
            "moq": 1,
            "lead_time_days": 15,
            "shipping_terms": "FOB",
            "warranty_months": 12
        },
        {
            "company_name": "Denair Compressor (Demo)",
            "model": "DA-15",
            "product_type": "Центробежный",
            "price_usd": 8900,
            "moq": 1,
            "lead_time_days": 30,
            "shipping_terms": "CIF",
            "warranty_months": 24
        }
    ]

# ═══════════════════════════════════════════════════════════════════
# ROUTES - AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════

def predict_risk_from_features(features):
    """Calculate risk probability from 5-feature vector: [AirTemp, ProcTemp, RPM, Torque, ToolWear]"""
    try:
        air_temp, proc_temp, rpm, torque, tool_wear = [float(x) for x in features]
        
        temp_diff = proc_temp - air_temp
        temp_score = 0
        if temp_diff > 10:
            temp_score = (temp_diff - 10) * 5 + 20
        else:
            temp_score = max(0, temp_diff * 1.5)

        power_factor = (rpm * torque) / 2500 
        
        wear_score = tool_wear * 0.1

        total_prob = 10.0 + temp_score + power_factor + wear_score
        final_prob = min(99.9, max(1.0, total_prob))
        
        return {
            'probability': round(final_prob, 1),
            'level': 'high' if final_prob > 60 else 'medium' if final_prob > 30 else 'low'
        }
    except Exception as e:
        return {'probability': 20.5, 'level': 'low'}

@app.route('/')
def index():
    """Home page"""
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # Validate input
        if not username or not password:
            flash('Username and password required', 'danger')
            return render_template('login.html')
        
        # Check credentials
        if username in ADMIN_USERS:
            user = ADMIN_USERS[username]
            if check_password_hash(user['password'], password):
                session['username'] = username
                session['role'] = user['role']
                logger.info(f"✅ User {username} logged in successfully")
                flash(f'Welcome, {username}!', 'success')
                return redirect(url_for('dashboard'))
        
        logger.warning(f"⚠️ Failed login attempt for user: {username}")
        flash('Invalid username or password', 'danger')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Logout"""
    username = session.get('username', 'Unknown')
    session.clear()
    logger.info(f"✅ User {username} logged out")
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))


# ═══════════════════════════════════════════════════════════════════
# ROUTES - DASHBOARD & DATA
# ═══════════════════════════════════════════════════════════════════

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard with equipment list"""
    category_filter = request.args.get('category', '').strip()
    
    # Get equipment data
    if IS_PRODUCTION_MODE:
        equipment_list = json_manager.get_all(category=category_filter if category_filter else None)
        categories = json_manager.get_categories()
    else:
        query = IndustrialEquipment.query
        if category_filter:
            query = query.filter_by(category=category_filter)
        equipment_list = [eq.to_dict() for eq in query.all()]
        categories = sorted(list(set(eq.category for eq in IndustrialEquipment.query.all())))
    
    # Calculate statistics
    stats = {
        'total': len(equipment_list),
        'working': sum(1 for eq in equipment_list if eq.get('status') == 'active'),
        'maintenance': sum(1 for eq in equipment_list if eq.get('status') == 'maintenance'),
        'critical': sum(1 for eq in equipment_list if eq.get('status') == 'critical'),
        'data_source': DATA_MODE
    }
    
    return render_template('dashboard.html',
                         equipment=equipment_list,
                         categories=categories,
                         selected_category=category_filter,
                         stats=stats)


@app.route('/equipment/<int:equipment_id>')
@login_required
def equipment_detail(equipment_id):
    """Equipment detail page"""
    if IS_PRODUCTION_MODE:
        equipment = json_manager.get_by_id(equipment_id)
        if not equipment:
            flash('Equipment not found', 'danger')
            return redirect(url_for('dashboard'))
    else:
        equipment = IndustrialEquipment.query.get_or_404(equipment_id)
        equipment = equipment.to_dict()
    
    return render_template('equipment_detail.html', equipment=equipment)


@app.route('/status')
@login_required
def status():
    """System status page"""
    
    db_connected = False
    eq_count = 0
    if not IS_PRODUCTION_MODE:
        try:
            db.session.execute('SELECT 1')
            db_connected = True
            eq_count = IndustrialEquipment.query.count()
        except:
            db_connected = False
    else:
        db_connected = True
        eq_count = len(json_manager.data)

    status_data = {
        'status': 'ok' if db_connected else 'warning',
        'server_time': datetime.now().strftime("%H:%M:%S"),
        'uptime': 'Running',
        
        'services': [
            {
                'name': 'Database',
                'status': 'ok' if db_connected else 'critical',
                'description': f'Using {DATA_MODE}. Records: {eq_count}'
            },
            {
                'name': 'Mode',
                'status': 'ok',
                'description': 'PRODUCTION' if IS_PRODUCTION_MODE else 'DEVELOPMENT'
            }
        ],
        
        'system_info': {
            'environment': 'Cloud/Static' if IS_PRODUCTION_MODE else 'Local Python 3.12',
            'user': session.get('username'),
            'role': session.get('role'),
            'updated_at': datetime.now().strftime("%Y-%m-%d %H:%M")
        },
        
        'api_endpoints': [
            {'path': '/api/supply-chain', 'description': 'Supply chain data', 'status': 'ok'},
            {'path': '/api/status', 'description': 'System monitoring', 'status': 'ok'}
        ]
    }
    
    return render_template('status.html', status=status_data)
# ═══════════════════════════════════════════════════════════════════
# API ROUTES (JSON responses)
# ═══════════════════════════════════════════════════════════════════

@app.route('/api/equipment')
@login_required
def api_equipment():
    """API: Get all equipment (supports filtering)"""
    try:
        category = request.args.get('category', '').strip()
        
        if IS_PRODUCTION_MODE:
            equipment = json_manager.get_all(category=category if category else None)
        else:
            query = IndustrialEquipment.query
            if category:
                query = query.filter_by(category=category)
            equipment = [eq.to_dict() for eq in query.all()]
        
        return jsonify({
            'success': True,
            'count': len(equipment),
            'data': equipment,
            'mode': 'JSON' if IS_PRODUCTION_MODE else 'PostgreSQL'
        })
    except Exception as e:
        logger.error(f"API Error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/categories')
@login_required
def api_categories():
    """API: Get all categories"""
    try:
        if IS_PRODUCTION_MODE:
            categories = json_manager.get_categories()
        else:
            categories = sorted(list(set(eq.category for eq in IndustrialEquipment.query.all())))
        
        return jsonify({
            'success': True,
            'categories': categories,
            'count': len(categories)
        })
    except Exception as e:
        logger.error(f"API Error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/status')
def api_status():
    """API: Get system status (public endpoint)"""
    try:
        status_info = {
            'mode': 'PRODUCTION' if IS_PRODUCTION_MODE else 'LOCAL',
            'data_source': DATA_MODE,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if IS_PRODUCTION_MODE:
            status_info['status'] = '✅ JSON Mock Data Online'
            status_info['records'] = len(json_manager.data)
        else:
            try:
                db.session.execute('SELECT 1')
                status_info['status'] = '✅ PostgreSQL Online'
                status_info['records'] = IndustrialEquipment.query.count()
            except Exception as e:
                status_info['status'] = f'❌ Database Error'
                status_info['error'] = str(e)
        
        return jsonify(status_info)
    except Exception as e:
        return jsonify({
            'status': '❌ Error',
            'error': str(e)
        }), 500


# ═══════════════════════════════════════════════════════════════════
# ERROR HANDLERS
# ═══════════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(error):
    """404 error handler"""
    return render_template('error.html',
                         error_code=404,
                         error_message='Page not found'), 404


@app.errorhandler(500)
def server_error(error):
    """500 error handler"""
    logger.error(f"Server Error: {error}")
    return render_template('error.html',
                         error_code=500,
                         error_message='Internal server error'), 500


# ═══════════════════════════════════════════════════════════════════
# INTELLIGENT MODEL DISPATCHER (ANALYTICS ROUTES)
# ═══════════════════════════════════════════════════════════════════

@app.route('/audit', methods=['GET', 'POST'])
@login_required
def audit():
    """Equipment audit form and processing"""
    if request.method == 'GET':
        return render_template('audit.html')
    
    # POST request - process audit
    if not ANALYTICS_AVAILABLE:
        flash('Analytics module not available', 'danger')
        return redirect(url_for('audit'))
    
    audit_text = request.form.get('audit_text', '').strip()
    if not audit_text:
        flash('Please enter equipment description', 'warning')
        return redirect(url_for('audit'))
    
    try:
        # Run intelligent audit
        db_session = db.session if not IS_PRODUCTION_MODE else None
        audit_result = intelligent_audit(audit_text, db_session)
        
        # Store result in session for display
        session['audit_result'] = audit_result
        
        logger.info(f"✅ Audit completed for user {session.get('username')}")
        return redirect(url_for('audit_result'))
    
    except Exception as e:
        logger.error(f"❌ Audit processing error: {e}")
        flash(f'Error processing audit: {str(e)}', 'danger')
        return redirect(url_for('audit'))


@app.route('/audit-result')
@login_required
def audit_result():
    """Display audit results"""
    if 'audit_result' not in session:
        flash('No audit result available', 'warning')
        return redirect(url_for('audit'))
    
    try:
        audit_data = session.get('audit_result', {})
        result = format_audit_for_display(audit_data)
        
        return render_template('audit_result.html', 
                             audit=result,
                             equipment_keywords=result.get('equipment_type'))
    
    except Exception as e:
        logger.error(f"❌ Error displaying audit result: {e}")
        flash(f'Error displaying result: {str(e)}', 'danger')
        return redirect(url_for('audit'))


@app.route('/api/audit', methods=['POST'])
@login_required
def api_audit():
    """API endpoint for equipment audit"""
    if not ANALYTICS_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'Analytics module not available'
        }), 503
    
    try:
        data = request.get_json()
        audit_text = data.get('text', '').strip()
        
        if not audit_text:
            return jsonify({
                'success': False,
                'error': 'Text is required'
            }), 400
        
        # Run intelligent audit
        db_session = db.session if not IS_PRODUCTION_MODE else None
        audit_result = intelligent_audit(audit_text, db_session)
        
        return jsonify({
            'success': True,
            'audit': audit_result
        })
    
    except Exception as e:
        logger.error(f"API Audit error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ═══════════════════════════════════════════════════════════════════
# PDF UPLOAD & MULTI-EQUIPMENT PROCESSING
# ═══════════════════════════════════════════════════════════════════

@app.route('/upload-pdf', methods=['GET', 'POST'])
def upload_pdf():
    if request.method == 'GET':
        return render_template('upload_pdf.html')
    
    pdf_file = request.files.get('pdf_file')
    if not pdf_file:
        flash('No file selected', 'warning')
        return redirect(request.url)
    
    try:
        import tempfile
        import debug_parser
        import os


        original_filename = pdf_file.filename
        logger.info(f"📄 Processing PDF: {original_filename}")



        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"upload_{original_filename}")
        
        try:

            pdf_file.save(temp_path)
            

            from pathlib import Path
            text = debug_parser.read_pdf_text(Path(temp_path))
            
            raw_data = get_structured_data_via_llm(text)
            
            if not raw_data:
                raw_data = {
                    "rpm": debug_parser.extract_rpm(text).to_dict(),
                    "pressure": debug_parser.extract_pressure(text).to_dict(),
                    "temperature": debug_parser.extract_temperature(text).to_dict(),
                    "torque": debug_parser.extract_torque(text).to_dict(),
                    "flow_rate": debug_parser.extract_flow_rate(text).to_dict()
                }

            processed = {}
            
            source_data = raw_data.get('parameters') if isinstance(raw_data.get('parameters'), dict) else raw_data

            for field in debug_parser.FEATURE_ORDER:
                d = source_data.get(field, {})
                
                if isinstance(d, dict):
                    raw_val = d.get("value")
                    unit = d.get("unit", "")
                else:
                    raw_val = d
                    unit = ""
                
                val = debug_parser.safe_float(raw_val, 0.0)
                
                if field == "pressure": val = debug_parser.normalize_pressure_value(val, unit)
                elif field == "temperature": val = debug_parser.normalize_temperature_value(val, unit)
                elif field == "torque": val = debug_parser.normalize_torque_value(val, unit)
                elif field == "flow_rate": val = debug_parser.normalize_flow_rate_value(val, unit)
                
                processed[field] = val


            from analytics import EQUIPMENT_KEYWORDS, predict_risk_from_features, DEFAULT_VALUES
            
            detected_type = 'unknown'
            text_lower = text.lower()
            for eq_type, info in EQUIPMENT_KEYWORDS.items():
                if any(kw.lower() in text_lower for kw in info['keywords']):
                    detected_type = eq_type
                    break


            features = [
                processed.get('air_temperature') or DEFAULT_VALUES['air_temperature'],
                processed.get('process_temperature') or DEFAULT_VALUES['process_temperature'],
                processed.get('rpm') or DEFAULT_VALUES['rpm'],
                processed.get('torque') or DEFAULT_VALUES['torque'],
                processed.get('tool_wear') or DEFAULT_VALUES['tool_wear']
            ]

            risk_data = predict_risk_from_features(features)
            risk_value = risk_data['probability']
            risk_level = risk_data['level']

            print("DEBUG: AI Raw Response Keys:", raw_data.keys())
            print("DEBUG: AI Raw Response Content:", raw_data)


            def find_key(data, keys_to_try):
                for k in keys_to_try:
                    if k in data and data[k]:
                        return data[k]
                return 'Unknown'


            model_val = raw_data.get('model')
            supplier_val = raw_data.get('supplier')


            if not model_val or model_val == 'Unknown':
                import re

                model_match = re.search(r'Model[:\s]*([A-Z0-9-]{3,})', text, re.IGNORECASE)
                model_val = model_match.group(1) if model_match else "CL-3000-A"


            if not supplier_val or supplier_val == 'Unknown':
                if "中派工业" in text:
                    supplier_val = "Zhongpai Industrial (中派工业)"
                elif "AL CO., LTD" in text:
                    supplier_val = "AL CO., LTD"
                else:
                    supplier_val = "Zhongpai Industrial"


            ai_audit = {
                'segment_index': 0,
                'equipment_type': detected_type,
                'model_number': str(model_val),
                'parameters': {
                    'rpm': processed.get('rpm') or DEFAULT_VALUES['rpm'],
                    'torque': processed.get('torque') or DEFAULT_VALUES['torque'],
                    'air_temperature': processed.get('air_temperature') or DEFAULT_VALUES['air_temperature'],
                    'process_temperature': processed.get('process_temperature') or DEFAULT_VALUES['process_temperature'],
                    'pressure': processed.get('pressure') or DEFAULT_VALUES['pressure'],
                    'flow_rate': processed.get('flow_rate') or DEFAULT_VALUES['flow_rate'],
                    'tool_wear': processed.get('tool_wear') or DEFAULT_VALUES['tool_wear']
                },
                'failure_probability': risk_value,
                'risk_level': risk_level,
                'status_color': 'red' if risk_level == 'high' else 'yellow' if risk_level == 'medium' else 'green',
                'ml_prediction': True,
                'input_text': text[:1000],
                'supplier': {
                    'name': str(supplier_val)
                }
            }

            session['pdf_audits'] = [ai_audit]
            session['pdf_filename'] = original_filename
            
            session['raw_data'] = raw_data 
            


            return redirect(url_for('pdf_results'))
            
        finally:

            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
                logger.error(f"❌ PDF processing error: {str(e)}", exc_info=True)
                flash(f'Ошибка при обработке: {str(e)}', 'danger')
                return redirect(url_for('upload_pdf'))
    
@app.route('/debug-upload', methods=['GET', 'POST'])
def debug_upload():
    if request.method == 'GET':

        return '''
            <!DOCTYPE html>
            <html lang="ru">
            <head><title>Debug AI Parser</title></head>
            <body style="padding: 50px; font-family: sans-serif;">
                <h2>🚀 Тестовая загрузка PDF (AI Groq)</h2>
                <form method="post" enctype="multipart/form-data">
                    <input type="file" name="file" required>
                    <button type="submit" style="padding: 10px 20px;">Запустить анализ</button>
                </form>
                <br><a href="/dashboard">← Назад в систему</a>
            </body>
            </html>
        '''


    file = request.files.get('file')
    if not file:
        return "Файл не найден", 400



    from pathlib import Path
    temp_path = Path("temp_debug.pdf")
    file.save(temp_path)


    text = debug_parser.read_pdf_text(temp_path)
    raw_data = debug_parser.extract_with_groq(text)
    
    if not raw_data:

        raw_data = {
            "rpm": debug_parser.extract_rpm(text).to_dict(),
            "pressure": debug_parser.extract_pressure(text).to_dict(),
            "temperature": debug_parser.extract_temperature(text).to_dict(),
            "torque": debug_parser.extract_torque(text).to_dict(),
            "flow_rate": debug_parser.extract_flow_rate(text).to_dict()
        }


    processed = {}

    for field in debug_parser.FEATURE_ORDER:
        data = raw_data.get(field, {})

        val = debug_parser.safe_float(data.get("value"), 0.0)
        unit = data.get("unit", "")
        
        if field == "pressure": val = debug_parser.normalize_pressure_value(val, unit)
        if field == "temperature": val = debug_parser.normalize_temperature_value(val, unit)
        if field == "torque": val = debug_parser.normalize_torque_value(val, unit)
        if field == "flow_rate": val = debug_parser.normalize_flow_rate_value(val, unit)
        
        processed[field] = val


    risk = debug_parser.heuristic_probability_from_inputs(processed)

    return render_template('debug_result.html', 
                           data=raw_data, 
                           normalized=processed, 
                           risk=risk)

@app.route('/pdf-results')
@login_required
def pdf_results():
    """Просто показывает готовые результаты из сессии, не запуская аудит заново"""
    if 'pdf_audits' not in session:
        flash('Результаты PDF недоступны', 'warning')
        return redirect(url_for('upload_pdf'))
    
    try:

        audits = session.get('pdf_audits', [])
        filename = session.get('pdf_filename', 'unknown.pdf')
        


        for idx, audit in enumerate(audits):
            if 'segment_index' not in audit:
                audit['segment_index'] = idx


        return render_template('pdf_results.html',
                             audits=audits,
                             pdf_filename=filename,
                             total_items=len(audits))
    
    except Exception as e:
        logger.error(f"❌ Error displaying PDF results: {e}")
        flash(f'Ошибка отображения результатов.', 'danger')
        return redirect(url_for('upload_pdf'))




# ═══════════════════════════════════════════════════════════════════
# INTERACTIVE CORRECTION & RECALCULATION
# ═══════════════════════════════════════════════════════════════════

@app.route('/api/audit-recalculate', methods=['POST'])
@login_required
def api_audit_recalculate():
    """Пересчет риска на основе точных числовых данных"""
    try:
        data = request.get_json()
        corrections = data.get('corrections', {})
        

        try:
            air_temp = float(corrections.get('air_temperature') or 298)
            proc_temp = float(corrections.get('process_temperature') or 309)
            rpm = float(corrections.get('rpm') or 1500)
            torque = float(corrections.get('torque') or 40)
            tool_wear = float(corrections.get('tool_wear') or 0)
        except ValueError:
            return jsonify({'success': False, 'error': 'Введите корректные числа'}), 400


        pressure = corrections.get('pressure', 0)
        flow_rate = corrections.get('flow_rate', 0)


        from analytics import predict_risk_from_features
        

        risk_data = predict_risk_from_features([air_temp, proc_temp, rpm, torque, tool_wear])
        

        formatted = {
            'failure_probability': risk_data['probability'],
            'risk_level': risk_data['level'],
            'status_color': 'red' if risk_data['probability'] > 50 else 'yellow' if risk_data['probability'] > 20 else 'green',
            'parameters': {
                'air_temperature': air_temp,
                'process_temperature': proc_temp,
                'rpm': rpm,
                'torque': torque,
                'tool_wear': tool_wear,
                'pressure': pressure,
                'flow_rate': flow_rate
            }
        }
        
        return jsonify({
            'success': True,
            'audit': formatted
        })
    
    except Exception as e:
        logger.error(f"Recalculation error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ═══════════════════════════════════════════════════════════════════
# DATABASE SAVE & CORRECTION LOGGING
# ═══════════════════════════════════════════════════════════════════

@app.route('/api/save-to-db', methods=['POST'])
@login_required
def api_save_to_db():
    """Save corrected equipment data to database"""
    if IS_PRODUCTION_MODE:
        return jsonify({
            'success': False,
            'error': 'Database not available in production mode'
        }), 503
    
    try:
        from analytics import intelligent_audit
        
        data = request.get_json()
        
        # Validate required fields
        equipment_type = data.get('equipment_type')
        model_number = data.get('model_number')
        supplier_name = data.get('supplier_name', 'Unknown')
        
        if not equipment_type or not model_number:
            return jsonify({
                'success': False,
                'error': 'Equipment type and model number are required'
            }), 400
        
        # Extract numeric parameters
        parameters = {
            'rpm': float(data.get('rpm', 0)) or None,
            'pressure': float(data.get('pressure', 0)) or None,
            'temperature': float(data.get('temperature', 0)) or None,
            'torque': float(data.get('torque', 0)) or None,
            'power': float(data.get('power', 0)) or None,
        }
        
        # Remove None values
        parameters = {k: v for k, v in parameters.items() if v is not None}
        
        # Create or update equipment record
        equipment = IndustrialEquipment(
            category=equipment_type,
            brand=supplier_name,
            model=model_number,
            specs=json.dumps(parameters),
            status='active',
            is_discontinued=False
        )
        
        db.session.add(equipment)
        db.session.commit()
        
        logger.info(f"✅ Saved to DB: {equipment_type} {model_number}")
        
        # Log correction for retraining
        if 'corrections' in data:
            logger.info(f"📝 User corrections logged: {data['corrections']}")
        
        return jsonify({
            'success': True,
            'message': f'Saved {model_number} to database',
            'equipment_id': equipment.id
        })
    
    except Exception as e:
        logger.error(f"Database save error: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ═══════════════════════════════════════════════════════════════════
# DATABASE INITIALIZATION
# ═══════════════════════════════════════════════════════════════════


def init_db():
    """Initialize database with sample data"""
    with app.app_context():
        try:
            # Create tables
            db.create_all()
            
            # Check if data exists
            if IndustrialEquipment.query.count() == 0:
                # Add sample data
                sample_equipment = [
                    IndustrialEquipment(
                        category='Compressor',
                        brand='Kaishan',
                        model='KS-30',
                        specs='30 kW, 3-phase, 8 bar, 8000 RPM',
                        status='active',
                        is_discontinued=False
                    ),
                    IndustrialEquipment(
                        category='Compressor',
                        brand='Fusheng',
                        model='FS-45',
                        specs='45 kW, 3-phase, 10 bar, 7500 RPM',
                        status='active',
                        is_discontinued=False
                    ),
                    IndustrialEquipment(
                        category='Pump',
                        brand='Atlas Copco',
                        model='CP-50',
                        specs='50 m³/h, 100m head, 37 kW',
                        status='maintenance',
                        is_discontinued=False
                    ),
                    IndustrialEquipment(
                        category='Pump',
                        brand='Ingersoll Rand',
                        model='IR-75',
                        specs='75 m³/h, 150m head, 55 kW',
                        status='active',
                        is_discontinued=False
                    ),
                    IndustrialEquipment(
                        category='Motor',
                        brand='Siemens',
                        model='1LA7-163-4A',
                        specs='22 kW, 4-pole, 1500 RPM, 380V',
                        status='active',
                        is_discontinued=False
                    ),
                ]
                
                for eq in sample_equipment:
                    db.session.add(eq)
                
                db.session.commit()
                logger.info(f"✅ Database initialized with {len(sample_equipment)} records")
        except Exception as e:
            logger.error(f"❌ Database initialization error: {e}")


# ═══════════════════════════════════════════════════════════════════
# SUPPLIERS & PRODUCTS MANAGEMENT ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.route('/suppliers')
def suppliers_page():
    """Display suppliers page (requires login)"""
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('suppliers.html')


@app.route('/products')
def products_page():
    """Display products page (requires login)"""
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('products.html')

@app.route('/supply-chain')
def supply_chain_page():
    return render_template('supply-chain.html')

@app.route('/api/supply-chain')
def supply_chain_api():
    """API с автоматическим переключением: DB -> Mock"""
    conn = None
    try:

        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        

        cur.execute("SELECT * FROM supply_chain_data LIMIT 50;")
        rows = cur.fetchall()
        
        cur.close()
        conn.close()
        

        return jsonify(rows if rows else get_mock_data())

    except Exception as e:

        print(f"--- DB not available (using Mock data) --- Reason: {e}")
        if conn:
            conn.close()
        return jsonify(get_mock_data())


@app.route('/forecast')
def forecast_page():
    """Display forecast page (requires login)"""
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('forecast.html')


def _load_forecast_data():
    """Load real forecast rows from outputs/forecast.csv."""
    forecast_path = os.path.join(os.path.dirname(__file__), 'outputs', 'forecast.csv')
    if not os.path.exists(forecast_path):
        logger.warning(f"⚠️ Forecast file not found: {forecast_path}")
        return []

    import csv

    rows = []
    with open(forecast_path, 'r', encoding='utf-8') as forecast_file:
        reader = csv.DictReader(forecast_file)
        for raw_row in reader:
            try:
                row = {
                    'product_id': int(raw_row.get('product_id') or 0),
                    'model': raw_row.get('model', ''),
                    'year': int(raw_row.get('year') or 0),
                    'month': int(raw_row.get('month') or 0),
                    'forecast_qty': int(float(raw_row.get('forecast_qty') or 0))
                }
                rows.append(row)
            except (TypeError, ValueError) as e:
                logger.warning(f"⚠️ Skipping malformed forecast row {raw_row}: {e}")

    rows.sort(key=lambda item: (
        item.get('year') or 0,
        item.get('month') or 0,
        item.get('product_id') or 0
    ))
    return rows


@app.route('/api/forecast-data')
@login_required
def api_forecast_data():
    """Return real forecast data from outputs/forecast.csv."""
    try:
        rows = _load_forecast_data()

        if not rows:
            return jsonify({
                'success': False,
                'error': 'Forecast data not found',
                'rows': [],
                'monthly_summary': [],
                'count': 0
            }), 404

        summary_map = {}
        for row in rows:
            key = (row['year'], row['month'])
            if key not in summary_map:
                summary_map[key] = {
                    'year': row['year'],
                    'month': row['month'],
                    'forecast_qty': 0,
                    'products': 0
                }
            summary_map[key]['forecast_qty'] += row['forecast_qty']
            summary_map[key]['products'] += 1

        monthly_summary = sorted(
            summary_map.values(),
            key=lambda item: (item['year'], item['month'])
        )

        return jsonify({
            'success': True,
            'source': 'outputs/forecast.csv',
            'count': len(rows),
            'rows': rows,
            'monthly_summary': monthly_summary
        })
    except Exception as e:
        logger.error(f"Forecast API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'rows': [],
            'monthly_summary': [],
            'count': 0
        }), 500


@app.route('/api/suppliers-scrape')
def api_suppliers_scrape():
    """API endpoint to scrape suppliers from internet"""
    try:
        from scraper.web_scraper import scrape_all_suppliers, FALLBACK_DATA
        
        # Use default supplier URLs or fallback data
        sample_urls = [
            "https://www.kaishangroup.com/en",
            "https://www.fusheng-compressor.com",
            "https://www.denair.net",
            "https://www.atlas-copco.com",
        ]
        
        # Try to scrape, but fallback to static data
        try:
            suppliers = scrape_all_suppliers(sample_urls)
        except:
            suppliers = FALLBACK_DATA
        
        return jsonify({
            'success': True,
            'data': suppliers,
            'count': len(suppliers)
        })
    except Exception as e:
        logger.error(f"Scraping error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/suppliers-data')
def api_suppliers_data():
    """Get suppliers data from demo source"""
    try:
        from scraper.web_scraper import FALLBACK_DATA
        return jsonify({
            'success': True,
            'suppliers': FALLBACK_DATA,
            'count': len(FALLBACK_DATA)
        })
    except Exception as e:
        logger.error(f"Error fetching suppliers: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500





# ═══════════════════════════════════════════════════════════════════
# APPLICATION STARTUP
# ═══════════════════════════════════════════════════════════════════

def main():
    """Функция запуска приложения"""
    global IS_PRODUCTION_MODE
    

    IS_PRODUCTION_MODE = (DATABASE_URL is None or DATABASE_URL == "")
    

    if not IS_PRODUCTION_MODE:
        try:
            from database import init_db
            init_db()
            logger.info("✅ Database initialized successfully.")
        except Exception as e:
            logger.error(f"❌ DATABASE ERROR: {e}")
            logger.info("🔄 Falling back to JSON mode...")
            IS_PRODUCTION_MODE = True
    

    data_info = "JSON (Demo Mode)" if IS_PRODUCTION_MODE else "PostgreSQL (Live)"
    print(f"""
    ╔════════════════════════════════════════════════════════════╗
    ║        Flask Hybrid Application - Starting                 ║
    ║─────────────────────────────────────────────────────────────║
    ║  MODE: {('PRODUCTION (JSON)' if IS_PRODUCTION_MODE else 'LOCAL (PostgreSQL)').ljust(40)}║
    ║  DATA: {data_info.ljust(50)}║
    ║  URL:  http://localhost:5052                               ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    

    app.run(debug=True, host='0.0.0.0', port=5052, use_reloader=False)

if __name__ == '__main__':
    main()