"""
Intelligent Model Dispatcher (IMD) - Analytics Module
======================================================

Multi-language NLP parser + ML model routing system
Features:
  - Smart equipment type detection (RU/EN/CN) with BERT embeddings
  - Parameter extraction from free text
  - ML model selection and inference
  - Database benchmarking
  - Risk detection
  - Semantic similarity matching for unknown equipment
"""

import os
import re
import json
import logging
import joblib
import numpy as np
import pandas as pd
from typing import Dict, Tuple, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from sentence_transformers import SentenceTransformer, util

logger = logging.getLogger(__name__)


def _load_local_env_files() -> None:
    """Load GROQ API key from local env files if present."""
    for env_name in ("qrok.env", "groq.env", ".env"):
        env_path = os.path.join(os.path.dirname(__file__), env_name)
        if not os.path.exists(env_path):
            continue

        try:
            with open(env_path, "r", encoding="utf-8") as env_file:
                for raw_line in env_file:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
        except Exception as e:
            logger.warning(f"⚠️ Failed to load env file {env_name}: {e}")


_load_local_env_files()

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

MODELS_PATH = os.path.join(os.path.dirname(__file__), 'models')
KNOWLEDGE_BASE_PATH = os.path.join(os.path.dirname(__file__), 'knowledge_base.json')

# Multi-language equipment keywords with ENHANCED TECHNICAL DESCRIPTIONS for BERT
EQUIPMENT_KEYWORDS = {
    'pump': {
        'keywords': [
            'насос', 'pump', '泵', 'pompa', 'pumpen',
            'водяной', 'centrifugal', 'поршневой', 'gear pump',
            'перекачивающий', '水泵', '给水泵'
        ],
        'model_file': 'pump.pkl',
        'model_name': 'Pump Failure Predictor',
        'description': "Industrial pump for liquids, centrifugal or gear water lifting machine",
        'technical_description': (
            "Centrifugal or gear pump for industrial fluid transfer. Operates at 1000-1800 RPM with steel or iron "
            "housing. Handles pressure ranges from 100-350 bar. Fluid temperature typically 280-320K. Common failure "
            "modes include cavitation (low inlet pressure), seal wear, and bearing degradation. Maintenance includes "
            "regular inspections of impeller, seals, and bearing lubrication. Noise above 85dB indicates potential issues."
        )
    },
    'valve': {
        'keywords': [
            'клапан', 'valve', '阀门', 'valvola', 'ventil',
            'запорный', 'directional', 'регулирующий', 'ball valve',
            'затворный', '控制阀', '截止阀'
        ],
        'model_file': 'valve.pkl',
        'model_name': 'Valve Failure Predictor',
        'description': "Control valve, directional valve, flow regulation pressure valve",
        'technical_description': (
            "Proportional or directional control valve with spool mechanism. Rated for 200-250 bar working pressure, "
            "operates at 280-320K fluid temperature. Response time typically 80-150 milliseconds. Housing material can be "
            "ductile iron or aluminum alloy. Valve spool rotates internally with hardened steel surfaces. Sealing achieved "
            "through precision-ground surfaces or elastomer seals. Common failures: spool stiction, seal extrusion, cavity erosion, "
            "and coil burn-out in proportional solenoids. Requires annual flushing and seal inspection."
        )
    },
    'cooler': {
        'keywords': [
            'охладитель', 'cooler', '冷却器', 'raffreddatore', 'kühler',
            'охлаждение', 'air cooler', 'теплообменник', 'cooling system',
            'радиатор', '冷却液', '散热'
        ],
        'model_file': 'cooler.pkl',
        'model_name': 'Cooler Failure Predictor',
        'description': "Industrial cooling system, heat exchanger, air cooler radiator",
        'technical_description': (
            "Aluminum or copper bar-plate heat exchanger. Handles fluid temperatures 300-330K with ambient air at 280-310K. "
            "Typical flow rate 50-200 l/min. Housing pressure rating 5-10 bar. Fins are thin aluminum (0.1mm) prone to corrosion "
            "in humid climates. Tube material is copper or cupro-nickel for saltwater resistance. Common degradation: fin fouling, "
            "tube pitting, gasket softening (silicone vs EPDM), and thermal efficiency loss. Maintenance: annual flushing with "
            "inhibited coolant, visual inspection for leaks and fin damage."
        )
    },
    'accumulator': {
        'keywords': [
            'аккумулятор', 'accumulator', '蓄能器', 'accumulatore', 'speicher',
            'гидроаккумулятор', 'pneumatic', 'запас', 'pressure vessel',
            'резервуар', '储能器', '蓄电池'
        ],
        'model_file': 'accumulator.pkl',
        'model_name': 'Accumulator Failure Predictor',
        'description': "Hydraulic pressure accumulator, energy storage vessel",
        'technical_description': (
            "Cylindrical or spherical pressure vessel with 1-100 liter capacity. Wall thickness 5-15mm steel or titanium alloy. "
            "Rated for 210-280 bar working pressure with 1.5:1 safety factor. Bladder material (nitrile or EPTM rubber) rated for "
            "280-330K fluid temperature. Precharge gas (nitrogen) at 0.6x min working pressure. Safety block includes isolating and "
            "check valves. Failure modes: bladder rupture (sudden pressure drop), corrosion/pitting of steel shell, faulty gas valve, "
            "and loss of precharge. Inspection required every 3-5 years with destructive testing every 10 years per ASME standards."
        )
    }
}

# Parameter extraction patterns (multi-language) - UPDATED
PARAMETER_PATTERNS = {
    'rpm': {
        'keywords': ['rpm', 'оборотов', '转速', 'revolutions per minute', 'об/мин', 'тур/мин', 'speed'],
        'pattern': r'(?:rpm|speed|оборотов|转速|об/мин)[:\s]*(\d+\.?\d*)',
        'unit': 'rpm',
        'range': (0, 5000),
    },
    'torque': {
        'keywords': ['torque', 'момент', '扭矩', 'crcoppia', 'drehmoment', 'nm', 'н.м'],
        'pattern': r'(?:torque|nm|н\.м|момент|扭矩)[:\s]*(\d+\.?\d*)',
        'unit': 'Nm',
        'range': (0, 500),
    },
    'air_temperature': {
        'keywords': ['air temperature', 'атмосферная', 'air temp', 'воздух'],
        'pattern': r'(?:air temp|air temperature|атмосферная)[:\s]*(\d+\.?\d*)\s*(?:k|°c|°)?',
        'unit': 'K',
        'range': (280, 350),
    },
    'process_temperature': {
        'keywords': ['process temperature', 'рабочая', 'process temp', '工艺'],
        'pattern': r'(?:process temp|process temperature|рабочая температура|工艺温度)[:\s]*(\d+\.?\d*)\s*(?:k|°c|°)?',
        'unit': 'K',
        'range': (280, 500),
    },
    'temperature': {
        'keywords': ['temperature', 'температур', '温度', 'temp', 'градус', '℃', '°c'],
        'pattern': r'(?:temp|температура|温度)[:\s]*(\d+\.?\d*)\s*(?:k|°c|°)?',
        'unit': 'K',
        'range': (280, 500),
    },
    'pressure': {
        'keywords': ['pressure', 'давлен', '压力', 'bar', 'pa', 'атм'],
        'pattern': r'(?:pressure|давление|压力)[:\s]*(\d+\.?\d*)\s*(?:bar|pa|атм|psi)?',
        'unit': 'bar',
        'range': (0, 350),
    },
    'flow_rate': {
        'keywords': ['flow', 'поток', '流量', 'l/min', 'm3/h', 'л/мин'],
        'pattern': r'(?:flow|поток|расход|流量)[:\s]*(\d+\.?\d*)\s*(?:l/min|m3/h|л/мин|куб)',
        'unit': 'l/min',
        'range': (0, 5000),
    },
    'power': {
        'keywords': ['power', 'мощность', '功率', 'kw', 'квт', 'hp'],
        'pattern': r'(?:power|мощность|功率)[:\s]*(\d+\.?\d*)\s*(?:kw|квт|hp)',
        'unit': 'kW',
        'range': (0, 500),
    },
    'tool_wear': {
        'keywords': ['tool wear', 'износ', '工具磨损'],
        'pattern': r'(?:tool wear|износ инструмента)[:\s]*(\d+\.?\d*)',
        'unit': '%',
        'range': (0, 100),
    }
}

# Default feature values for imputation
DEFAULT_VALUES = {
    'rpm': 1500,
    'temperature': 305,
    'torque': 40,
    'pressure': 150,
    'tool_wear': 0,
    'air_temperature': 298,
    'process_temperature': 309,
    'flow_rate': 100,
    'power': 50,
}

# Risk keywords
RISK_KEYWORDS = {
    'payment': [
        '100% предоплата', 'full prepayment', '全款预付', '提前付款',
        'advance payment required', 'non-refundable', 'no refund'
    ],
    'warranty': [
        'no warranty', 'без гарантии', '无保修', 'warranty void',
        'as-is condition', 'не гарантируем', '产品保证'
    ],
    'delivery': [
        'delivery only', 'non-returnable', 'no exchange', 'final sale',
        'только отправка', '仅发货', 'доставка окончательная'
    ],
    'price': [
        'цена', 'price', 'стоимость', '价格', 'cost', '成本'
    ],
    'quality': [
        'damaged', 'broken', 'used', 'refurbished', 'поврежден',
        'б/у', '修复', '二手'
    ]
}


# ═══════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class DetectionResult:
    """Result of equipment type detection"""
    equipment_type: Optional[str]
    confidence: float
    method: str  # 'keyword' or 'bert'
    alternative_matches: List[Tuple[str, float]]
    
    def to_dict(self):
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════
# MODEL MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

class ModelCache:
    """Cache for loaded ML models"""
    _models = {}
    _scaler = None
    
    @classmethod
    def get_model(cls, equipment_type: str):
        """Load model from cache or disk"""
        if equipment_type not in cls._models:
            model_file = EQUIPMENT_KEYWORDS[equipment_type]['model_file']
            model_path = os.path.join(MODELS_PATH, model_file)
            
            try:
                if os.path.exists(model_path):
                    cls._models[equipment_type] = joblib.load(model_path)
                    logger.info(f"✅ Loaded model: {model_file}")
                else:
                    logger.warning(f"⚠️ Model file not found: {model_path}")
                    return None
            except Exception as e:
                logger.error(f"❌ Error loading model {model_file}: {e}")
                return None
        
        return cls._models[equipment_type]
    
    @classmethod
    def get_scaler(cls):
        """Load scaler for feature normalization"""
        if cls._scaler is None:
            scaler_path = os.path.join(MODELS_PATH, 'scaler.pkl')
            try:
                if os.path.exists(scaler_path):
                    cls._scaler = joblib.load(scaler_path)
                    logger.info("✅ Loaded scaler")
                else:
                    logger.warning(f"⚠️ Scaler file not found: {scaler_path}")
                    return None
            except Exception as e:
                logger.error(f"❌ Error loading scaler: {e}")
                return None
        
        return cls._scaler


# ═══════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE & RAG (RETRIEVAL-AUGMENTED GENERATION)
# ═══════════════════════════════════════════════════════════════════

class KnowledgeBase:
    """
    Knowledge Base manager for RAG-based parameter inference
    Loads equipment specifications and provides fallback values
    """
    _kb_data = None
    
    @classmethod
    def load(cls) -> Dict:
        """Load knowledge base from JSON file"""
        if cls._kb_data is None:
            try:
                if os.path.exists(KNOWLEDGE_BASE_PATH):
                    with open(KNOWLEDGE_BASE_PATH, 'r') as f:
                        cls._kb_data = json.load(f)
                    logger.info(f"📚 Knowledge base loaded: {len(cls._kb_data.get('models', []))} models")
                else:
                    logger.warning(f"⚠️ Knowledge base not found: {KNOWLEDGE_BASE_PATH}")
                    cls._kb_data = {'models': [], 'equipment_types': {}}
            except Exception as e:
                logger.error(f"❌ Error loading knowledge base: {e}")
                cls._kb_data = {'models': [], 'equipment_types': {}}
        
        return cls._kb_data
    
    @classmethod
    def find_model(cls, model_number: str) -> Optional[Dict]:
        """Find model specifications in knowledge base"""
        kb = cls.load()
        
        model_number_lower = model_number.lower()
        for model in kb.get('models', []):
            if model.get('model_number', '').lower() == model_number_lower:
                logger.info(f"📚 Found model in KB: {model_number}")
                return model
        
        return None
    
    @classmethod
    def get_equipment_defaults(cls, equipment_type: str) -> Dict:
        """Get default parameters for equipment type"""
        kb = cls.load()
        equipment = kb.get('equipment_types', {}).get(equipment_type, {})
        return equipment.get('common_defaults', {})
    
    @classmethod
    def enrich_parameters(cls, model_number: str, equipment_type: str, 
                         extracted_params: Dict) -> Dict:
        """
        Enrich extracted parameters using knowledge base
        Fill missing parameters from model specs or type defaults
        """
        enriched = dict(extracted_params)
        
        # Try model-specific defaults first
        if model_number:
            model_spec = cls.find_model(model_number)
            if model_spec:
                for param_name, default_value in model_spec.get('default_parameters', {}).items():
                    if param_name not in enriched:
                        enriched[param_name] = (default_value, 'knowledge_base', True)
                        logger.info(f"   ✓ KB filled {param_name}: {default_value}")
        
        # Fallback to equipment type defaults
        if equipment_type:
            type_defaults = cls.get_equipment_defaults(equipment_type)
            for param_name, default_value in type_defaults.items():
                if param_name not in enriched:
                    enriched[param_name] = (default_value, 'equipment_type_default', True)
                    logger.info(f"   ✓ Type default {param_name}: {default_value}")
        
        return enriched


# ═══════════════════════════════════════════════════════════════════
# BERT POWERED NLP PARSING ENGINE
# ═══════════════════════════════════════════════════════════════════

def get_structured_data_via_llm(text_segment: str) -> Optional[Dict]:
    """
    Отправляет кусок текста в Groq и получает чистый JSON.
    
    """

    prompt = f"""
    Act as a Senior Industrial Systems Engineer. Parse technical data into a strict JSON.
    Analyze the provided text which can be in ENGLISH, RUSSIAN, or CHINESE.
    
STRICT RULES:
    1. Classification: 'equipment_type' must be one of: "pump", "valve", "cooler", "accumulator".
    2. Numerical Only: All parameters must be single FLOAT values. 
    3. Ranges: If you find a range (e.g. "-5 to 70C"), return the MAXIMUM value.
    4. Units: Convert Celsius to Kelvin (K = C + 273.15). Convert MPa to bar (1 MPa = 10 bar).
    5. Supplier: Identify the manufacturer or supplier name. 
    6. Languages: 
       - If Russian: "Частота вращения" -> rpm, "Давление" -> pressure, "Крутящий момент" -> torque, "Производитель" -> supplier.
       - If Chinese: "转速" -> rpm, "压力" -> pressure, "转矩/扭矩" -> torque, "厂家/供应商" -> supplier.
    
    JSON STRUCTURE:
    {{
      "equipment_type": "string",
      "model": "string",
      "supplier": "string",
      "parameters": {{
         "rpm": float or null,
         "pressure": float or null,
         "temperature": float or null,
         "torque": float or null,
         "flow_rate": float or null
      }}
    }}

    TEXT TO ANALYZE:
    {text_segment[:4000]}
    """

    try:
        from groq import Groq
        import os
        import json

        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        raw_content = completion.choices[0].message.content
        return json.loads(raw_content)
        
    except Exception as e:

        if "logger" in globals():
            logger.error(f"❌ Groq Error: {e}")
        else:
            print(f"❌ Groq Error: {e}")
        return None


class SmartParser:
    """
    Multi-language equipment and parameter parser with BERT embeddings
    Uses semantic similarity for better equipment detection
    """
    
    # Class-level BERT model (shared across instances)
    _bert_model = None
    
    @classmethod
    def _get_bert_model(cls):
        """Lazy load BERT model"""
        if cls._bert_model is None:
            try:
                logger.info("🤖 Loading BERT model: paraphrase-multilingual-MiniLM-L12-v2")
                cls._bert_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                logger.info("✅ BERT model loaded successfully")
            except Exception as e:
                logger.error(f"❌ Failed to load BERT model: {e}")
                cls._bert_model = None
        return cls._bert_model
    
    @staticmethod
    def detect_equipment_type_semantic(text: str, confidence_threshold: float = 0.4) -> DetectionResult:
        """
        Detect equipment type using BERT semantic similarity
        More accurate than keyword matching, especially for complex descriptions
        
        Args:
            text: Input text description
            confidence_threshold: Minimum confidence to accept (0.0-1.0)
        
        Returns:
            DetectionResult with type, confidence, and alternative matches
        """
        text_lower = text.lower()
        model = SmartParser._get_bert_model()
        
        # First try keyword matching for quick results
        keyword_result = SmartParser.detect_equipment_type_keywords(text)
        
        if model is None:
            # Fallback to keyword matching
            return DetectionResult(
                equipment_type=keyword_result,
                confidence=1.0 if keyword_result else 0.0,
                method='keyword',
                alternative_matches=[]
            )
        
        try:
            # Encode input text
            input_embedding = model.encode(text, convert_to_tensor=True)
            
            # Prepare category descriptions
            category_descriptions = {
                equipment: config['description']
                for equipment, config in EQUIPMENT_KEYWORDS.items()
            }
            
            # Calculate similarities
            similarities = {}
            for category, desc in category_descriptions.items():
                desc_embedding = model.encode(desc, convert_to_tensor=True)
                similarity = util.cos_sim(input_embedding, desc_embedding).item()
                similarities[category] = similarity
                logger.debug(f"BERT similarity for {category}: {similarity:.3f}")
            
            # Find best match
            best_category = max(similarities, key=similarities.get)
            best_score = similarities[best_category]
            
            # Get alternative matches (sorted by score)
            alternatives = sorted(
                [(cat, score) for cat, score in similarities.items() if cat != best_category],
                key=lambda x: x[1],
                reverse=True
            )[:3]
            
            # Determine which result to use
            if best_score > confidence_threshold:
                logger.info(f"🎯 BERT detected: {best_category} with confidence {best_score:.2f}")
                return DetectionResult(
                    equipment_type=best_category,
                    confidence=best_score,
                    method='bert',
                    alternative_matches=alternatives
                )
            elif keyword_result:
                logger.info(f"🎯 Keyword fallback detected: {keyword_result}")
                return DetectionResult(
                    equipment_type=keyword_result,
                    confidence=0.5,
                    method='keyword',
                    alternative_matches=list(similarities.items())
                )
            else:
                logger.warning("⚠️ Equipment type not detected by BERT or keywords")
                return DetectionResult(
                    equipment_type=None,
                    confidence=0.0,
                    method='none',
                    alternative_matches=list(similarities.items())
                )
                
        except Exception as e:
            logger.error(f"❌ BERT detection error: {e}")
            return DetectionResult(
                equipment_type=keyword_result,
                confidence=0.5 if keyword_result else 0.0,
                method='keyword_fallback',
                alternative_matches=[]
            )
    
    @staticmethod
    def detect_equipment_type_keywords(text: str) -> Optional[str]:
        """
        Detect equipment type using keyword matching (legacy method)
        
        Returns: equipment_type or None
        """
        text_lower = text.lower()
        
        scores = {}
        for equipment, config in EQUIPMENT_KEYWORDS.items():
            match_count = sum(1 for keyword in config['keywords'] if keyword in text_lower)
            if match_count > 0:
                scores[equipment] = match_count
        
        if scores:
            detected = max(scores, key=scores.get)
            logger.info(f"🎯 Keyword detected: {detected} (confidence: {scores[detected]})")
            return detected
        
        return None
    
    @staticmethod
    def detect_equipment_type(text: str, use_bert: bool = True) -> Optional[str]:
        """
        Main equipment detection method with BERT option
        
        Args:
            text: Input text
            use_bert: Whether to use BERT semantic matching
        
        Returns: equipment_type or None
        """
        if use_bert:
            result = SmartParser.detect_equipment_type_semantic(text)
            return result.equipment_type
        else:
            return SmartParser.detect_equipment_type_keywords(text)
    
    @staticmethod
    def extract_parameters(text: str) -> Dict[str, float]:
        """
        Extract numerical parameters from text using LLM
        """
        structured_data = get_structured_data_via_llm(text)
        if not structured_data:
            return {}

        parameters = structured_data.get('parameters', {}) or {}
        return {
            key: value
            for key, value in parameters.items()
            if value is not None
        }
    
    @staticmethod
    def extract_all_numbers(text: str) -> Dict[str, List[float]]:
        """
        Extract all numbers with context to help identify parameters
        """
        # Pattern to capture numbers with nearby context
        pattern = r'(\d+(?:[.,]\d+)?)\s*([a-zA-Zа-яА-Я\u0400-\u04FF/°]+)?'
        matches = re.findall(pattern, text)
        
        result = {'numbers': [], 'with_units': []}
        for match in matches:
            try:
                num = float(match[0].replace(',', '.'))
                unit = match[1] if len(match) > 1 else ''
                result['numbers'].append(num)
                if unit:
                    result['with_units'].append({'value': num, 'unit': unit})
            except:
                pass
        
        return result
    
    @staticmethod
    def extract_price(text: str) -> Optional[float]:
        """Extract price from text with multiple currency formats"""
        price_patterns = [
            r'(\d+[,.]?\d*)\s*(?:USD|$|¥|€|₽|CNY|RUB)',
            r'(?:цена|price|стоимость|价格)[\s:]*(\d+[,.]?\d*)',
            r'(\d+[,.]?\d*)\s*(?:долл|руб|тенге|тг)',
            r'(?:total|всего|итого)[\s:]*(\d+[,.]?\d*)',
        ]
        
        for pattern in price_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    price = float(match.group(1).replace(',', '.'))
                    logger.info(f"💰 Extracted price: {price}")
                    return price
                except:
                    pass
        
        return None
    
    @staticmethod
    def detect_risks(text: str) -> List[Dict[str, str]]:
        """Detect contractual and business risks with severity scoring"""
        risks = []
        text_lower = text.lower()
        
        severity_map = {
            'payment': 'critical',
            'warranty': 'critical',
            'quality': 'high',
            'delivery': 'medium',
            'price': 'low'
        }
        
        for risk_type, keywords in RISK_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    risks.append({
                        'type': risk_type,
                        'keyword': keyword,
                        'severity': severity_map.get(risk_type, 'medium')
                    })
                    logger.warning(f"⚠️ Risk detected: {risk_type} - {keyword}")
        
        # Remove duplicates
        unique_risks = []
        seen = set()
        for risk in risks:
            key = (risk['type'], risk['keyword'])
            if key not in seen:
                seen.add(key)
                unique_risks.append(risk)
        
        return unique_risks
    
    @staticmethod
    def extract_supplier_name(text: str) -> Optional[str]:
        """Extract supplier/manufacturer name from text with better patterns"""
        patterns = [
            r'(?:компани|company|фирм|производит|manufacturer|от|from|поставщик|supplier|vendor)[\s:]*([A-Za-z\u0400-\u04FF]+(?:\s+[A-Za-z\u0400-\u04FF]+){0,3})',
            r'(?:supplied by|manufactured by|produced by)[\s:]*([A-Za-z\u0400-\u04FF]+)',
            r'^([A-Z][A-Za-z\u0400-\u04FF]+(?:\s+[A-Z][A-Za-z\u0400-\u04FF]+){0,2})',  # Capitalized words at start
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                supplier_name = match.group(1).strip()
                # Filter out common false positives
                if len(supplier_name) > 2 and not supplier_name.lower() in ['the', 'and', 'for', 'with']:
                    logger.info(f"🏢 Extracted supplier: {supplier_name}")
                    return supplier_name
        
        return None
    
    @staticmethod
    def extract_model_number(text: str) -> Optional[str]:
        """Extract product/model number from text"""
        patterns = [
            r'(?:model|модель|型号|part|артикул)[\s:]*([A-Z0-9\-]+)',
            r'(?:p/n|part number|код)[\s:]*([A-Z0-9\-]+)',
            r'\b([A-Z]{2,4}[-\s]?\d{3,6}[A-Z]?)\b',  # Generic model pattern
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                model = match.group(1).strip()
                logger.info(f"🔢 Extracted model: {model}")
                return model
        
        return None


# ═══════════════════════════════════════════════════════════════════
# ML INFERENCE ENGINE
# ═══════════════════════════════════════════════════════════════════

class MLInferenceEngine:
    """ML model prediction and result formatting"""
    
    @staticmethod
    def prepare_features(equipment_type: str, parameters: Dict[str, float]) -> Optional[np.ndarray]:
        """
        Prepare feature vector for ML model
        
        Handles:
        - Feature imputation (missing values)
        - Feature normalization (scaler)
        - Feature ordering (model-specific)
        """
        model = ModelCache.get_model(equipment_type)
        if not model:
            return None
        
        # Extended feature mapping
        feature_mapping = {
            'pump': ['rpm', 'pressure', 'temperature', 'torque', 'flow_rate'],
            'valve': ['rpm', 'pressure', 'temperature', 'torque', 'tool_wear'],
            'cooler': ['rpm', 'pressure', 'temperature', 'torque', 'tool_wear'],
            'accumulator': ['rpm', 'pressure', 'temperature', 'torque','tool_wear'],
        }
        
        expected_features = feature_mapping.get(equipment_type, [])
        
        # Build feature vector with imputation
        feature_vector = []
        for feature_name in expected_features:
            if feature_name in parameters:
                value = parameters[feature_name]
                logger.info(f"✅ Using extracted {feature_name}: {value}")
            else:
                value = DEFAULT_VALUES.get(feature_name, 0)
                logger.info(f"📝 Imputed {feature_name}: {value} (default)")
            
            feature_vector.append(value)
        
        # Normalize with scaler if available
        scaler = ModelCache.get_scaler()
        if scaler:
            try:
                feature_vector = np.array(feature_vector).reshape(1, -1)
                feature_vector = scaler.transform(feature_vector)
                logger.info(f"📏 Normalized features")
            except Exception as e:
                logger.error(f"❌ Scaler error: {e}")
                return None
        
        return np.array(feature_vector).reshape(1, -1)
    
    @staticmethod
    def predict(equipment_type: str, parameters: Dict[str, float]) -> Optional[Dict]:
        """
        Make ML prediction with confidence intervals
        
        Returns: dict with probability, failure type, and confidence
        """
        features = MLInferenceEngine.prepare_features(equipment_type, parameters)
        if features is None:
            return None
        
        model = ModelCache.get_model(equipment_type)
        if not model:
            return None
        
        try:
            if hasattr(model, 'predict_proba'):
                proba = model.predict_proba(features)[0]
                failure_probability = float(proba[1]) if len(proba) > 1 else float(proba[0])
                
                # Calculate confidence based on distance from decision boundary
                confidence = abs(failure_probability - 0.5) * 2  # 0 to 1 scale
                
                # Get prediction class if available
                prediction_class = 1 if failure_probability > 0.5 else 0
            else:
                prediction = model.predict(features)[0]
                failure_probability = float(prediction)
                confidence = 0.5  # Default confidence when no probability available
            
            logger.info(f"🤖 Prediction: {failure_probability:.2%} failure probability (confidence: {confidence:.2%})")
            
            return {
                'failure_probability': failure_probability,
                'is_failure_likely': failure_probability > 0.5,
                'confidence': confidence,
                'risk_level': 'critical' if failure_probability > 0.8 else 
                             'high' if failure_probability > 0.6 else 
                             'medium' if failure_probability > 0.4 else 
                             'low',
                'recommendation': _get_recommendation(failure_probability)
            }
        except Exception as e:
            logger.error(f"❌ Prediction error: {e}")
            return None


def _get_recommendation(failure_probability: float) -> str:
    """Generate recommendation based on failure probability"""
    if failure_probability > 0.8:
        return "⚠️ CRITICAL: Immediate replacement recommended. Do not use equipment."
    elif failure_probability > 0.6:
        return "🔴 HIGH RISK: Schedule maintenance within 1 week. Monitor closely."
    elif failure_probability > 0.4:
        return "🟡 MEDIUM RISK: Plan preventive maintenance within 1 month."
    elif failure_probability > 0.2:
        return "🟢 LOW RISK: Regular maintenance schedule is sufficient."
    else:
        return "✅ GOOD CONDITION: Equipment appears healthy. Continue normal operation."


# ═══════════════════════════════════════════════════════════════════
# DATABASE BENCHMARKING
# ═══════════════════════════════════════════════════════════════════

class DatabaseBenchmark:
    """Database queries for price and supplier comparison"""
    
    @staticmethod
    def get_average_price(db_session, equipment_type: str) -> Optional[float]:
        """Get average price from database by equipment type"""
        try:
            from sqlalchemy import func
            from app_hybrid import IndustrialEquipment
            
            avg_price = db_session.query(
                func.avg(IndustrialEquipment.price)
            ).filter(
                IndustrialEquipment.category == equipment_type
            ).scalar()
            
            return float(avg_price) if avg_price else None
        except Exception as e:
            logger.error(f"❌ Database error: {e}")
            return None
    
    @staticmethod
    def get_price_stats(db_session, equipment_type: str) -> Optional[Dict]:
        """Get comprehensive price statistics"""
        try:
            from sqlalchemy import func
            from app_hybrid import IndustrialEquipment
            
            stats = db_session.query(
                func.avg(IndustrialEquipment.price).label('avg'),
                func.min(IndustrialEquipment.price).label('min'),
                func.max(IndustrialEquipment.price).label('max'),
                func.count(IndustrialEquipment.id).label('count')
            ).filter(
                IndustrialEquipment.category == equipment_type
            ).first()
            
            if stats and stats.avg:
                return {
                    'average': float(stats.avg),
                    'min': float(stats.min),
                    'max': float(stats.max),
                    'sample_count': stats.count
                }
        except Exception as e:
            logger.error(f"❌ Database error: {e}")
        
        return None
    
    @staticmethod
    def find_supplier(db_session, supplier_name: str) -> Optional[Dict]:
        """Find supplier in database"""
        try:
            from app_hybrid import db
            
            query = db.session.query(db.Model).filter(
                db.Model.name.ilike(f'%{supplier_name}%')
            ).first()
            
            if query:
                return {
                    'name': getattr(query, 'name', supplier_name),
                    'rating': getattr(query, 'reliability_score', 'N/A'),
                    'country': getattr(query, 'country', 'Unknown'),
                }
        except Exception as e:
            logger.warning(f"⚠️ Supplier search failed: {e}")
        
        return None


# ═══════════════════════════════════════════════════════════════════
# MAIN API
# ═══════════════════════════════════════════════════════════════════

def intelligent_audit(text: str, db_session=None, use_bert: bool = True) -> Dict:
    """
    Main function for intelligent equipment audit
    
    Args:
        text: Free-form description of equipment/purchase
        db_session: SQLAlchemy session for database queries
        use_bert: Retained for backward compatibility; LLM extraction is used instead
    
    Returns:
        Comprehensive audit report
    """
    logger.info("=" * 60)
    logger.info("🚀 Starting Intelligent Equipment Audit")
    logger.info("=" * 60)

    audit_report = {
        'timestamp': datetime.utcnow().isoformat(),
        'input_text': text[:500],
        'equipment_type': None,
        'detection_details': None,
        'parameters': {},
        'all_extracted_numbers': {},
        'ml_prediction': None,
        'database_benchmark': {},
        'risks': [],
        'supplier': None,
        'model_number': None,
        'model': None,
        'price': None,
        'status': 'pending'
    }

    logger.info("📍 Step 1: LLM Extraction")
    structured_data = get_structured_data_via_llm(text)

    if not structured_data:
        logger.error("❌ LLM returned None. Aborting audit step.")
        audit_report['status'] = 'llm_error'
        return audit_report

    equipment_type = structured_data.get('equipment_type')
    raw_params = structured_data.get('parameters', {})
    llm_supplier = (
        structured_data.get('supplier') or
        structured_data.get('manufacturer') or
        structured_data.get('brand') or
        structured_data.get('company')
    )

    audit_report['equipment_type'] = equipment_type
    audit_report['model'] = structured_data.get('model')
    audit_report['parameters'] = raw_params

    if not isinstance(raw_params, dict):
        raw_params = {}

    audit_report['equipment_type'] = equipment_type
    audit_report['model'] = structured_data.get('model')
    audit_report['model_number'] = structured_data.get('model')
    audit_report['parameters'] = raw_params

    if not equipment_type:
        audit_report['status'] = 'equipment_not_detected'
        return audit_report

    logger.info("📊 Step 2: Parameter Context")
    audit_report['all_extracted_numbers'] = SmartParser.extract_all_numbers(text)

    logger.info("🤖 Step 3: ML Prediction")

    logger.info(f"🔍 DEBUG: Raw equipment_type from LLM: '{equipment_type}'")
    eq_type_raw = str(equipment_type or "").lower().strip()

    translation_map = {
        'насос': 'pump', '泵': 'pump', 'bèng': 'pump',
        'клапан': 'valve', '阀': 'valve', 'fá': 'valve',
        'охладитель': 'cooler', '冷却器': 'cooler', 'lěngquèqì': 'cooler',
        'аккумулятор': 'accumulator', '蓄能器': 'accumulator', 'xùnéngqì': 'accumulator'
    }

    normalized_type = translation_map.get(eq_type_raw, eq_type_raw)

    def clean_to_float(val, default=0.0):
        if val is None: return default
        try:
            if isinstance(val, (int, float)): return float(val)
            cleaned = "".join(c for c in str(val) if c.isdigit() or c == '.')
            return float(cleaned) if cleaned else default
        except:
            return default

    if normalized_type in EQUIPMENT_KEYWORDS:
        def clean_to_float(val, default=0.0):
            if val is None: return default
            try:
                if isinstance(val, (int, float)): return float(val)

                cleaned = "".join(c for c in str(val) if c.isdigit() or c == '.')
                return float(cleaned) if cleaned else default
            except:
                return default
            
            
            
    if normalized_type in EQUIPMENT_KEYWORDS:
        try:

            clean_features = {
                'rpm': clean_to_float(raw_params.get('rpm')),
                'pressure': clean_to_float(raw_params.get('pressure')),
                'temperature': clean_to_float(raw_params.get('temperature'), 293.15),
                'torque': clean_to_float(raw_params.get('torque')),
                'flow_rate': clean_to_float(raw_params.get('flow_rate'))
            }

            logger.info(f"✅ Features prepared: {clean_features}")


            prediction = MLInferenceEngine.predict(normalized_type, clean_features)
            audit_report['ml_prediction'] = prediction
            logger.info(f"🤖 ML Result: {prediction}")

        except Exception as e:
            logger.error(f"❌ ML Calculation Error: {e}")
    else:

        logger.warning(f"⚠️ ML Skipped: '{normalized_type}' is not in {EQUIPMENT_KEYWORDS}")
    logger.info("💰 Step 4: Price Benchmarking")
    price = SmartParser.extract_price(text)
    audit_report['price'] = price

    if price and db_session:
        price_stats = DatabaseBenchmark.get_price_stats(db_session, equipment_type)
        if price_stats:
            audit_report['database_benchmark'] = {
                'extracted_price': price,
                'average_price': price_stats['average'],
                'price_ratio': price / price_stats['average'] if price_stats['average'] else None,
                'price_status': 'overpriced' if price_stats['average'] and price > price_stats['average'] * 1.2 else
                               'underpriced' if price_stats['average'] and price < price_stats['average'] * 0.8 else
                               'normal',
                'price_range': {'min': price_stats['min'], 'max': price_stats['max']},
                'sample_count': price_stats['sample_count']
            }

    logger.info("⚠️ Step 5: Risk Detection")
    risks = SmartParser.detect_risks(text)
    audit_report['risks'] = risks

    logger.info("🏢 Step 6: Supplier Identification")
    supplier_name = llm_supplier


    if not supplier_name:
        logger.warning("⚠️ LLM missed supplier, falling back to Regex")
        supplier_name = SmartParser.extract_supplier_name(text)

    if supplier_name and db_session:
        from models import Supplier
        supplier = db_session.query(Supplier).filter(
            Supplier.name.ilike(f"%{supplier_name[:5]}%")
        ).first()
        if supplier:
            audit_report['supplier'] = {
                'name': supplier.name,
                'found': True,
                'id': supplier.id,
                'rating': getattr(supplier, 'rating', 'N/A'),
            }
        else:
            audit_report['supplier'] = {'name': supplier_name, 'found': False}
    else:
        audit_report['supplier'] = {'name': supplier_name,'found': False} if supplier_name else None
    
    logger.info("=" * 60)
    logger.info(f"✅ Audit completed: {equipment_type}")
    logger.info("=" * 60)

    return audit_report


def _calculate_overall_score(audit: Dict) -> Dict:
    """Calculate overall equipment score and recommendations"""
    score = 100  # Start with perfect score
    deductions = []
    
    # Deduct for ML prediction
    ml_pred = audit.get('ml_prediction')
    if ml_pred:
        failure_prob = ml_pred.get('failure_probability', 0)
        if failure_prob > 0.7:
            score -= 40
            deductions.append(f"High failure probability ({failure_prob:.0%})")
        elif failure_prob > 0.4:
            score -= 20
            deductions.append(f"Medium failure probability ({failure_prob:.0%})")
    
    # Deduct for risks
    risks = audit.get('risks', [])
    for risk in risks:
        severity = risk.get('severity', 'medium')
        if severity == 'critical':
            score -= 25
            deductions.append(f"Critical risk: {risk['type']}")
        elif severity == 'high':
            score -= 15
            deductions.append(f"High risk: {risk['type']}")
        elif severity == 'medium':
            score -= 10
            deductions.append(f"Medium risk: {risk['type']}")
    
    # Deduct for price issues
    benchmark = audit.get('database_benchmark', {})
    if benchmark.get('price_status') == 'overpriced':
        score -= 15
        deductions.append("Overpriced compared to market average")
    
    score = max(0, min(100, score))
    
    # Determine grade
    if score >= 80:
        grade = "A"
        recommendation = "Excellent condition. Proceed with confidence."
    elif score >= 60:
        grade = "B"
        recommendation = "Good condition with minor concerns. Review recommendations."
    elif score >= 40:
        grade = "C"
        recommendation = "Fair condition. Significant improvements needed."
    elif score >= 20:
        grade = "D"
        recommendation = "Poor condition. High risk transaction."
    else:
        grade = "F"
        recommendation = "Critical issues detected. Avoid transaction."
    
    return {
        'score': score,
        'grade': grade,
        'deductions': deductions,
        'recommendation': recommendation
    }


def predict_risk_from_features(features):
    air_temp, proc_temp, rpm, torque, tool_wear = [float(x) for x in features]
    

    temp_diff = proc_temp - air_temp
    

    risk = 15.0 
    

    if temp_diff > 8:
        risk += (temp_diff - 8) * 4
        

    risk += (rpm * torque) / 2000
    

    risk += tool_wear * 0.1
    

    final_prob = max(1.0, min(99.0, risk))
    



    
    return {
        'probability': round(final_prob, 1),
        'level': 'high' if final_prob > 60 else 'medium' if final_prob > 30 else 'low'
    }

# ═══════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def format_audit_for_display(audit: Dict) -> Dict:
    """Format audit report for web display safely"""

    if audit is None:
        audit = {}

    equipment_type = audit.get('equipment_type')
    ml_pred = audit.get('ml_prediction')
    

    if equipment_type is None:
        status_color = 'gray'
        status_text = 'Оборудование не определено'
    elif ml_pred is None:
        status_color = 'blue'
        status_text = 'Анализ ожидается или недоступен'
    else:

        prob = ml_pred.get('failure_probability', 0)
        if prob > 0.7:
            status_color = 'red'
            status_text = 'Высокий риск отказа'
        elif prob > 0.4:
            status_color = 'yellow'
            status_text = 'Средний риск отказа'
        else:
            status_color = 'green'
            status_text = 'Низкий риск отказа'
    

    display_probability = None
    if ml_pred and 'failure_probability' in ml_pred:
        display_probability = ml_pred['failure_probability'] * 100


    return {
        'status_color': status_color,
        'status_text': status_text,
        'equipment_type': equipment_type,
        'equipment_display_name': EQUIPMENT_KEYWORDS.get(equipment_type, {}).get('model_name', equipment_type) if equipment_type else 'Unknown',
        'failure_probability': display_probability,
        'risk_level': ml_pred.get('risk_level') if ml_pred else 'N/A',
        **audit
    }