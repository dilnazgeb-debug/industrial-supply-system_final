from __future__ import annotations

import copy
import json
import math
import os
import pickle
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from dotenv import load_dotenv


load_dotenv("groq.env")

import pdfplumber

# ---------------------------------------------------------------------------
# INPUT SOURCE
# ---------------------------------------------------------------------------
# Option 1: paste the PDF text directly into TEST_TEXT.
# Option 2: put the extracted text into a sibling file named test.txt.
# Option 3: pass a file path as the first CLI argument.
TEST_TEXT = ""
TEST_TEXT_PATH = Path(__file__).with_name("test.txt")
DEFAULT_PDF_PATH = Path(__file__).with_name("Industrial-Valves.pdf")

if TEST_TEXT_PATH.exists():
    TEST_TEXT = TEST_TEXT_PATH.read_text(encoding="utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# GROQ PROMPT ENGINEERING
# ---------------------------------------------------------------------------
GROQ_SYSTEM_PROMPT = """
You are a strict industrial PDF extraction engine.

Your only job is to read the provided PDF text and return exactly one valid JSON object.
Do not add markdown, code fences, explanations, or extra keys outside the schema below.

Required JSON schema:
{
  "rpm": {
    "value": number,
    "unit": string,
    "confidence": number,
    "source_text": string,
    "is_imputed": boolean
  },
  "pressure": {
    "value": number,
    "unit": string,
    "confidence": number,
    "source_text": string,
    "is_imputed": boolean
  },
  "temperature": {
    "value": number,
    "unit": string,
    "confidence": number,
    "source_text": string,
    "is_imputed": boolean
  },
  "torque": {
    "value": number,
    "unit": string,
    "confidence": number,
    "source_text": string,
    "is_imputed": boolean
  },
  "flow_rate": {
    "value": number,
    "unit": string,
    "confidence": number,
    "source_text": string,
    "is_imputed": boolean
  }
}

Extraction rules:
- For each field, return a numeric value plus the original unit exactly as seen in the PDF when possible.
- Use source_text as a short direct quote from the PDF that supports the value.
- If a field is missing or ambiguous, infer the most logical technical value from the document context.
- When a value is inferred, set is_imputed to true.
- Confidence must be a float in the range [0, 1].
- Prefer the most relevant explicit value over inferred values.
- Normalize numbers with a dot decimal separator.
- Preserve original units in the unit field even when the model can infer a standard unit.
- If the document contains multiple candidate values, choose the one most relevant to the main valve specification, not a random table cell.
- If a field is not explicitly present, do not omit it; impute it and mark it as imputed.
- Keep source_text short, but long enough to prove the value came from the PDF context.
- If the document is a catalog with tables, look for 'Design Pressure', 'Max Pressure', 'Rated Speed' or 'Operating Range'.
- For Chillers/Coolers: Pressure is often 10-20 bar, Flow rate is often in m3/h or l/min.
- Do not return 0 if you see a range (e.g., if it says 5-10 bar, return 10).
""".strip()

GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


# ---------------------------------------------------------------------------
# DATA MODEL
# ---------------------------------------------------------------------------
FEATURE_ORDER = ["rpm", "pressure", "temperature", "torque", "flow_rate"]

DEFAULT_DOCUMENT_TYPE = "maintenance"
MODELS_DIR = Path(__file__).resolve().parent / "models"

MODEL_REGISTRY: Dict[str, Dict[str, Optional[str]]] = {
    "valve": {"model": "valve.pkl", "scaler": "scaler.pkl"},
    "cooler": {"model": "cooler.pkl", "scaler": "scaler.pkl"},
    "pump": {"model": "pump.pkl", "scaler": "scaler.pkl"},
    "accumulator": {"model": "accumulator.pkl", "scaler": "scaler.pkl"},
    "maintenance": {"model": "maintenance.pkl", "scaler": "scaler.pkl"},
}

DOCUMENT_TYPE_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "valve": (
        "valve",
        "gate valve",
        "globe valve",
        "check valve",
        "ball valve",
        "knife gate",
        "trunnion",
        "api 600",
        "api 6d",
    ),
    "cooler": (
        "cooler",
        "chiller",
        "heat exchanger",
        "condenser",
        "evaporator",
        "refrigeration",
        "cooling",
    ),
    "pump": (
        "pump",
        "impeller",
        "centrifugal",
        "booster pump",
        "suction",
        "discharge",
    ),
    "accumulator": (
        "accumulator",
        "hydraulic",
        "bladder",
        "piston accumulator",
        "nitrogen charge",
        "precharge",
    ),
    "maintenance": (
        "maintenance",
        "predictive maintenance",
        "vibration",
        "bearing",
        "motor",
        "fault",
        "condition monitoring",
        "diagnostic",
    ),
}

DEFAULT_IMPUTATIONS: Dict[str, Tuple[float, str, float, str]] = {
    "rpm": (
        0.0,
        "rpm",
        0.32,
        "Imputed because the valve catalog describes hand-operated and gear-operated valves, but no explicit RPM value is present.",
    ),
    "pressure": (
        16.0,
        "bar",
        0.40,
        "Imputed conservative nominal pressure because no direct operating pressure was extracted.",
    ),
    "temperature": (
        25.0,
        "°C",
        0.35,
        "Imputed ambient temperature because no single operating temperature was confidently extracted.",
    ),
    "torque": (
        120.0,
        "N.m",
        0.30,
        "Imputed nominal torque because the catalog contains torque tables but no unambiguous row-level torque value was isolated.",
    ),
    "flow_rate": (
        100.0,
        "m3/h",
        0.28,
        "Imputed nominal flow rate because the catalog does not provide a direct flow-rate specification.",
    ),
}


@dataclass
class FieldValue:
    value: float
    unit: str
    confidence: float
    source_text: str
    is_imputed: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "unit": self.unit,
            "confidence": self.confidence,
            "source_text": self.source_text,
            "is_imputed": self.is_imputed,
        }


@dataclass
class PredictionBundle:
    document_type: str
    model_path: Optional[Path]
    scaler_path: Optional[Path]
    model: Any = None
    scaler: Any = None
    load_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_type": self.document_type,
            "model_name": self.model_path.name if self.model_path else None,
            "model_path": str(self.model_path) if self.model_path else None,
            "scaler_name": self.scaler_path.name if self.scaler_path else None,
            "scaler_path": str(self.scaler_path) if self.scaler_path else None,
            "model_loaded": self.model is not None,
            "scaler_loaded": self.scaler is not None,
            "load_error": self.load_error,
        }


# ---------------------------------------------------------------------------
# TEXT UTILITIES
# ---------------------------------------------------------------------------
def read_pdf_text(pdf_path: Path) -> str:
    print(f"🔍 Попытка чтения файла: {pdf_path}")
    if not pdf_path.exists():
        print(f"❌ ФАЙЛ НЕ НАЙДЕН: {pdf_path}")
        return ""

    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        print(f"📄 В файле обнаружено страниц: {len(pdf.pages)}")
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text)
    
    full_text = "\n".join(pages).strip()

    print(f"📝 Начало считанного текста: {full_text[:100]}...") 
    return full_text


def load_input_text() -> str:
    if len(sys.argv) > 1:
        candidate = Path(sys.argv[1])
        if candidate.exists() and candidate.is_file():
            if candidate.suffix.lower() == ".pdf":
                pdf_text = read_pdf_text(candidate)
                if pdf_text:
                    return pdf_text
            return candidate.read_text(encoding="utf-8", errors="ignore")

    if TEST_TEXT.strip():
        return TEST_TEXT

    pdf_text = read_pdf_text(DEFAULT_PDF_PATH)
    if pdf_text:
        return pdf_text

    return TEST_TEXT


def normalize_whitespace(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        if math.isnan(float(value)) or math.isinf(float(value)):
            return default
        return float(value)
    text = str(value).strip()
    if not text:
        return default
    text = text.replace(",", ".")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return default
    try:
        result = float(match.group(0))
    except ValueError:
        return default
    if math.isnan(result) or math.isinf(result):
        return default
    return result


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compact_excerpt(text: str, limit: int = 160) -> str:
    compact = normalize_whitespace(text)
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def first_regex_match(patterns: Iterable[re.Pattern[str]], text: str) -> Optional[re.Match[str]]:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match
    return None


def detect_document_type(text: str) -> str:
    normalized_text = normalize_whitespace(text).lower()
    if not normalized_text:
        return DEFAULT_DOCUMENT_TYPE

    scores: Dict[str, float] = {name: 0.0 for name in MODEL_REGISTRY}
    for document_type, keywords in DOCUMENT_TYPE_KEYWORDS.items():
        score = 0.0
        for keyword in keywords:
            if keyword and keyword in normalized_text:
                score += 1.0 + (len(keyword) / 50.0)
        scores[document_type] = score

    best_document_type = max(scores, key=scores.get)
    if scores.get(best_document_type, 0.0) <= 0.0:
        return DEFAULT_DOCUMENT_TYPE
    return best_document_type


def resolve_model_paths(document_type: str) -> Tuple[Path, Optional[Path]]:
    registry = MODEL_REGISTRY.get(document_type, MODEL_REGISTRY[DEFAULT_DOCUMENT_TYPE])
    model_filename = registry.get("model") or MODEL_REGISTRY[DEFAULT_DOCUMENT_TYPE]["model"]
    scaler_filename = registry.get("scaler")
    model_path = MODELS_DIR / model_filename
    scaler_path = MODELS_DIR / scaler_filename if scaler_filename else None
    return model_path, scaler_path


def load_serialized_object(path: Optional[Path]) -> Any:
    if path is None or not path.exists() or not path.is_file():
        return None

    try:
        with path.open("rb") as file_handle:
            return pickle.load(file_handle)
    except Exception:
        try:
            from joblib import load as joblib_load  # type: ignore

            return joblib_load(path)
        except Exception:
            return None


def prepare_prediction_bundle(text: str, explicit_document_type: Optional[str] = None) -> PredictionBundle:
    document_type = explicit_document_type or detect_document_type(text)
    if document_type not in MODEL_REGISTRY:
        document_type = DEFAULT_DOCUMENT_TYPE

    model_path, scaler_path = resolve_model_paths(document_type)
    model = load_serialized_object(model_path)
    scaler = load_serialized_object(scaler_path)
    load_error: Optional[str] = None

    if model is None:
        load_error = f"Could not load model from {model_path}"
    elif scaler_path is not None and scaler is None and scaler_path.exists():
        load_error = f"Model loaded, but scaler could not be loaded from {scaler_path}"

    return PredictionBundle(
        document_type=document_type,
        model_path=model_path,
        scaler_path=scaler_path,
        model=model,
        scaler=scaler,
        load_error=load_error,
    )


def _extract_scalar(value: Any) -> float:
    if hasattr(value, "tolist"):
        value = value.tolist()

    while isinstance(value, (list, tuple)) and value:
        value = value[0]

    return safe_float(value, 0.0)


def predict_probability_from_model(
    model: Any,
    feature_row: List[float],
    scaler: Any = None,
) -> Optional[float]:
    matrix: Any = [feature_row]

    if scaler is not None and hasattr(scaler, "transform"):
        try:
            matrix = scaler.transform(matrix)
        except Exception:
            matrix = [feature_row]

    if hasattr(model, "predict_proba"):
        try:
            probabilities = model.predict_proba(matrix)
            if hasattr(probabilities, "tolist"):
                probabilities = probabilities.tolist()

            if isinstance(probabilities, (list, tuple)) and probabilities:
                first_row = probabilities[0]
                if isinstance(first_row, (list, tuple)) and first_row:
                    target_probability = first_row[-1] if len(first_row) > 1 else first_row[0]
                    return clamp(_extract_scalar(target_probability) * 100.0, 0.0, 100.0)
                return clamp(_extract_scalar(first_row) * 100.0, 0.0, 100.0)
        except Exception:
            pass

    if hasattr(model, "predict"):
        try:
            prediction = model.predict(matrix)
            score = _extract_scalar(prediction)

            if 0.0 <= score <= 1.0:
                return clamp(score * 100.0, 0.0, 100.0)
            if 1.0 < score <= 100.0:
                return clamp(score, 0.0, 100.0)
            if score > 100.0:
                return 100.0
            if score == 1.0:
                return 100.0
        except Exception:
            return None

    return None


def heuristic_probability_from_inputs(normalized_inputs: Mapping[str, float]) -> float:
    rpm = max(0.0, safe_float(normalized_inputs.get("rpm"), DEFAULT_IMPUTATIONS["rpm"][0]))
    pressure = max(0.0, safe_float(normalized_inputs.get("pressure"), DEFAULT_IMPUTATIONS["pressure"][0]))
    temperature = safe_float(normalized_inputs.get("temperature"), DEFAULT_IMPUTATIONS["temperature"][0])
    torque = max(0.0, safe_float(normalized_inputs.get("torque"), DEFAULT_IMPUTATIONS["torque"][0]))
    flow_rate = max(0.0, safe_float(normalized_inputs.get("flow_rate"), DEFAULT_IMPUTATIONS["flow_rate"][0]))

    score = 8.0
    score += sigmoid((pressure - 16.0) / 8.0) * 28.0
    score += sigmoid((abs(temperature - 25.0) - 35.0) / 14.0) * 18.0
    score += sigmoid((torque - 120.0) / 90.0) * 16.0
    score += sigmoid((rpm - 0.0) / 900.0) * 10.0
    score += sigmoid((flow_rate - 100.0) / 140.0) * 12.0

    return clamp(score, 0.0, 100.0)
def first_regex_match(patterns: Iterable[re.Pattern[str]], text: str) -> Optional[re.Match[str]]:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match
    return None


def detect_document_type(text: str) -> str:
    normalized_text = normalize_whitespace(text).lower()
    if not normalized_text:
        return DEFAULT_DOCUMENT_TYPE

    scores: Dict[str, float] = {name: 0.0 for name in MODEL_REGISTRY}
    for document_type, keywords in DOCUMENT_TYPE_KEYWORDS.items():
        score = 0.0
        for keyword in keywords:
            if keyword and keyword in normalized_text:
                score += 1.0 + (len(keyword) / 50.0)
        scores[document_type] = score

    best_document_type = max(scores, key=scores.get)
    if scores.get(best_document_type, 0.0) <= 0.0:
        return DEFAULT_DOCUMENT_TYPE
    return best_document_type


def resolve_model_paths(document_type: str) -> Tuple[Path, Optional[Path]]:
    registry = MODEL_REGISTRY.get(document_type, MODEL_REGISTRY[DEFAULT_DOCUMENT_TYPE])
    model_filename = registry.get("model") or MODEL_REGISTRY[DEFAULT_DOCUMENT_TYPE]["model"]
    scaler_filename = registry.get("scaler")
    model_path = MODELS_DIR / model_filename
    scaler_path = MODELS_DIR / scaler_filename if scaler_filename else None
    return model_path, scaler_path


def load_serialized_object(path: Optional[Path]) -> Any:
    if path is None or not path.exists() or not path.is_file():
        return None

    try:
        with path.open("rb") as file_handle:
            return pickle.load(file_handle)
    except Exception:
        try:
            from joblib import load as joblib_load  # type: ignore

            return joblib_load(path)
        except Exception:
            return None


def prepare_prediction_bundle(text: str, explicit_document_type: Optional[str] = None) -> PredictionBundle:
    document_type = explicit_document_type or detect_document_type(text)
    if document_type not in MODEL_REGISTRY:
        document_type = DEFAULT_DOCUMENT_TYPE

    model_path, scaler_path = resolve_model_paths(document_type)
    model = load_serialized_object(model_path)
    scaler = load_serialized_object(scaler_path)
    load_error: Optional[str] = None

    if model is None:
        load_error = f"Could not load model from {model_path}"
    elif scaler_path is not None and scaler is None and scaler_path.exists():
        load_error = f"Model loaded, but scaler could not be loaded from {scaler_path}"

    return PredictionBundle(
        document_type=document_type,
        model_path=model_path,
        scaler_path=scaler_path,
        model=model,
        scaler=scaler,
        load_error=load_error,
    )


def _extract_scalar(value: Any) -> float:
    if hasattr(value, "tolist"):
        value = value.tolist()

    while isinstance(value, (list, tuple)) and value:
        value = value[0]

    return safe_float(value, 0.0)


def predict_probability_from_model(
    model: Any,
    feature_row: List[float],
    scaler: Any = None,
) -> Optional[float]:
    matrix: Any = [feature_row]

    if scaler is not None and hasattr(scaler, "transform"):
        try:
            matrix = scaler.transform(matrix)
        except Exception:
            matrix = [feature_row]

    if hasattr(model, "predict_proba"):
        try:
            probabilities = model.predict_proba(matrix)
            if hasattr(probabilities, "tolist"):
                probabilities = probabilities.tolist()

            if isinstance(probabilities, (list, tuple)) and probabilities:
                first_row = probabilities[0]
                if isinstance(first_row, (list, tuple)) and first_row:
                    target_probability = first_row[-1] if len(first_row) > 1 else first_row[0]
                    return clamp(_extract_scalar(target_probability) * 100.0, 0.0, 100.0)
                return clamp(_extract_scalar(first_row) * 100.0, 0.0, 100.0)
        except Exception:
            pass

    if hasattr(model, "predict"):
        try:
            prediction = model.predict(matrix)
            score = _extract_scalar(prediction)

            if 0.0 <= score <= 1.0:
                return clamp(score * 100.0, 0.0, 100.0)
            if 1.0 < score <= 100.0:
                return clamp(score, 0.0, 100.0)
            if score > 100.0:
                return 100.0
            if score == 1.0:
                return 100.0
        except Exception:
            return None

    return None


def heuristic_probability_from_inputs(normalized_inputs: Mapping[str, float]) -> float:
    rpm = max(0.0, safe_float(normalized_inputs.get("rpm"), DEFAULT_IMPUTATIONS["rpm"][0]))
    pressure = max(0.0, safe_float(normalized_inputs.get("pressure"), DEFAULT_IMPUTATIONS["pressure"][0]))
    temperature = safe_float(normalized_inputs.get("temperature"), DEFAULT_IMPUTATIONS["temperature"][0])
    torque = max(0.0, safe_float(normalized_inputs.get("torque"), DEFAULT_IMPUTATIONS["torque"][0]))
    flow_rate = max(0.0, safe_float(normalized_inputs.get("flow_rate"), DEFAULT_IMPUTATIONS["flow_rate"][0]))

    score = 8.0
    score += sigmoid((pressure - 16.0) / 8.0) * 28.0
    score += sigmoid((abs(temperature - 25.0) - 35.0) / 14.0) * 18.0
    score += sigmoid((torque - 120.0) / 90.0) * 16.0
    score += sigmoid((rpm - 0.0) / 900.0) * 10.0
    score += sigmoid((flow_rate - 100.0) / 140.0) * 12.0

    return clamp(score, 0.0, 100.0)


# ---------------------------------------------------------------------------
# UNIT CONVERSION
# ---------------------------------------------------------------------------
def psi_to_bar(value: float) -> float:
    return value * 0.0689475729


def mpa_to_bar(value: float) -> float:
    return value * 10.0


def kpa_to_bar(value: float) -> float:
    return value / 100.0


def pa_to_bar(value: float) -> float:
    return value / 100000.0


def atm_to_bar(value: float) -> float:
    return value * 1.01325


def kgf_cm2_to_bar(value: float) -> float:
    return value * 0.980665


def fahrenheit_to_celsius(value: float) -> float:
    return (value - 32.0) / 1.8


def kelvin_to_celsius(value: float) -> float:
    return value - 273.15


def lbft_to_nm(value: float) -> float:
    return value * 1.3558179483


def kgfm_to_nm(value: float) -> float:
    return value * 9.80665


def kgfcm_to_nm(value: float) -> float:
    return value * 0.0980665


def lpm_to_m3h(value: float) -> float:
    return value * 0.06


def lps_to_m3h(value: float) -> float:
    return value * 3.6


def gpm_to_m3h(value: float) -> float:
    return value * 0.227124707


def m3min_to_m3h(value: float) -> float:
    return value * 60.0


def m3s_to_m3h(value: float) -> float:
    return value * 3600.0


def class_to_bar(value: float) -> float:
    # Approximate ASME pressure class conversion at room temperature.
    mapping = {
        150.0: 19.6,
        300.0: 51.1,
        600.0: 102.1,
        900.0: 153.0,
        1500.0: 255.0,
        2500.0: 425.0,
    }
    rounded = round(value)
    if float(rounded) in mapping:
        return mapping[float(rounded)]
    # Best-effort scaling for uncommon classes.
    return value / 7.65


def normalize_pressure_value(value: float, unit: Any) -> float:
    if unit is None:
            unit = ""
    normalized_unit = unit.lower().strip()
    if normalized_unit in {"bar", "bars"}:
        return value
    if normalized_unit in {"mpa"}:
        return mpa_to_bar(value)
    if normalized_unit in {"kpa"}:
        return kpa_to_bar(value)
    if normalized_unit in {"pa"}:
        return pa_to_bar(value)
    if normalized_unit in {"psi", "psig"}:
        return psi_to_bar(value)
    if normalized_unit in {"atm", "atmosphere", "atmospheres"}:
        return atm_to_bar(value)
    if normalized_unit in {"kgf/cm2", "kg/cm2", "kgf/cm²", "kg/cm²"}:
        return kgf_cm2_to_bar(value)
    if normalized_unit in {"class"}:
        return class_to_bar(value)
    return value


def normalize_temperature_value(value: float, unit: Any) -> float:
    if unit is None:
            unit = ""
    normalized_unit = unit.lower().strip()
    if normalized_unit in {"c", "°c", "celsius"}:
        return value
    if normalized_unit in {"f", "°f", "fahrenheit"}:
        return fahrenheit_to_celsius(value)
    if normalized_unit in {"k", "kelvin"}:
        return kelvin_to_celsius(value)
    return value


def normalize_torque_value(value: float, unit: Any) -> float:

    if unit is None:
        unit = ""
    normalized_unit = unit.lower().strip()
    if normalized_unit in {"n.m", "nm", "n-m", "newton-meter", "newton meters", "newton meter", "n·m"}:
        return value
    if normalized_unit in {"lb-ft", "lbf-ft", "ft-lb", "ft-lbs"}:
        return lbft_to_nm(value)
    if normalized_unit in {"kgf.m", "kgf*m", "kgfm", "kgf-m"}:
        return kgfm_to_nm(value)
    if normalized_unit in {"kgfcm", "kgf.cm", "kgf-cm"}:
        return kgfcm_to_nm(value)
    return value


def normalize_flow_rate_value(value: float, unit: Any) -> float:
    if unit is None:
            unit = ""
    normalized_unit = unit.lower().strip()
    if normalized_unit in {"m3/h", "m^3/h", "m³/h"}:
        return value
    if normalized_unit in {"l/min", "lpm", "l/minute"}:
        return lpm_to_m3h(value)
    if normalized_unit in {"l/s", "lps"}:
        return lps_to_m3h(value)
    if normalized_unit in {"gpm"}:
        return gpm_to_m3h(value)
    if normalized_unit in {"m3/min", "m^3/min", "m³/min"}:
        return m3min_to_m3h(value)
    if normalized_unit in {"m3/s", "m^3/s", "m³/s"}:
        return m3s_to_m3h(value)
    return value


# ---------------------------------------------------------------------------
# GROQ INTEGRATION
# ---------------------------------------------------------------------------
def build_groq_messages(text: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": GROQ_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Extract the five parameters from the following PDF text and return only JSON.\n\n"
                f"{text}"
            ),
        },
    ]


def extract_json_object(content: str) -> Optional[Dict[str, Any]]:
    content = content.strip()
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def extract_with_groq(text: str) -> Optional[Dict[str, Any]]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None

    try:
        from groq import Groq  # type: ignore
    except Exception:
        return None

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=build_groq_messages(text),
            temperature=0.0,
            max_tokens=1200,
        )
        content = response.choices[0].message.content or ""
        return extract_json_object(content)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# LOCAL HEURISTIC EXTRACTION
# ---------------------------------------------------------------------------
def build_imputed_field(name: str) -> FieldValue:
    value, unit, confidence, source_text = DEFAULT_IMPUTATIONS[name]
    return FieldValue(
        value=value,
        unit=unit,
        confidence=confidence,
        source_text=source_text,
        is_imputed=True,
    )


def extract_pressure(text: str) -> FieldValue:
    search_text = normalize_whitespace(text)

    pn_match = re.search(
        r"(?i)\bPN\s*([0-9]+(?:\.[0-9]+)?)(?:\s*/\s*[0-9]+(?:\.[0-9]+)?)*",
        search_text,
    )
    if pn_match:
        value = safe_float(pn_match.group(1), 0.0)
        return FieldValue(
            value=value,
            unit="MPa",
            confidence=0.95,
            source_text=compact_excerpt(pn_match.group(0)),
            is_imputed=False,
        )

    explicit_pressure_patterns = [
        re.compile(
            r"(?i)\b(?:shell test|water seal test|air seal test|pressure[- ]?test|test pressure)\b[^0-9]{0,30}([0-9]+(?:\.[0-9]+)?)\s*(Mpa|MPa|bar|psi|psig)\b"
        ),
        re.compile(r"(?i)\b([0-9]+(?:\.[0-9]+)?)\s*(Mpa|MPa|bar|psi|psig)\b"),
    ]
    match = first_regex_match(explicit_pressure_patterns, search_text)
    if match:
        value = safe_float(match.group(1), 0.0)
        unit = match.group(2)
        return FieldValue(
            value=value,
            unit=unit,
            confidence=0.90,
            source_text=compact_excerpt(match.group(0)),
            is_imputed=False,
        )

    class_match = re.search(r"(?i)\bclass\s*(150|300|600|900|1500|2500)\b", search_text)
    if class_match:
        value = safe_float(class_match.group(1), 0.0)
        return FieldValue(
            value=value,
            unit="class",
            confidence=0.78,
            source_text=compact_excerpt(class_match.group(0)),
            is_imputed=False,
        )

    return build_imputed_field("pressure")


def extract_temperature(text: str) -> FieldValue:
    search_text = normalize_whitespace(text)
    patterns = [
        re.compile(
            r"(?i)\b(?:suitable temp\.?|temperature|temp\.\s*&\s*pressure|working temperature)\b[^-0-9]{0,40}(-?[0-9]+(?:\.[0-9]+)?)\s*°?\s*([CFK])\b"
        ),
        re.compile(r"(?i)\b(-?[0-9]+(?:\.[0-9]+)?)\s*°\s*([CFK])\b"),
        re.compile(r"(?i)\b(-?[0-9]+(?:\.[0-9]+)?)\s*deg\s*([CFK])\b"),
    ]
    match = first_regex_match(patterns, search_text)
    if match:
        value = safe_float(match.group(1), 0.0)
        unit = match.group(2)
        return FieldValue(
            value=value,
            unit=unit if unit != "C" else "°C",
            confidence=0.93,
            source_text=compact_excerpt(match.group(0)),
            is_imputed=False,
        )

    # The PDF contains many temperatures in the body, so capture a bare negative Celsius value if it is clearly labeled.
    bare_pattern = re.search(r"(?i)\b(?:suitable temp\.?|temperature|working temperature)[^0-9\-]{0,40}(-?[0-9]+(?:\.[0-9]+)?)\s*°?\s*C\b", search_text)
    if bare_pattern:
        value = safe_float(bare_pattern.group(1), 0.0)
        return FieldValue(
            value=value,
            unit="°C",
            confidence=0.88,
            source_text=compact_excerpt(bare_pattern.group(0)),
            is_imputed=False,
        )

    return build_imputed_field("temperature")


def extract_rpm(text: str) -> FieldValue:
    search_text = normalize_whitespace(text)
    patterns = [
        re.compile(r"(?i)\b([0-9]+(?:\.[0-9]+)?)\s*(rpm|r/min|rev/min)\b"),
        re.compile(r"(?i)\b(rpm|r/min|rev/min)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\b"),
    ]
    match = first_regex_match(patterns, search_text)
    if match:
        if match.lastindex == 2 and re.fullmatch(r"(?i)(rpm|r/min|rev/min)", match.group(1)):
            unit = match.group(1)
            value_text = match.group(2)
        else:
            value_text = match.group(1)
            unit = match.group(2)
        return FieldValue(
            value=safe_float(value_text, 0.0),
            unit=unit,
            confidence=0.84,
            source_text=compact_excerpt(match.group(0)),
            is_imputed=False,
        )

    return build_imputed_field("rpm")


def extract_torque(text: str) -> FieldValue:
    search_text = normalize_whitespace(text)
    patterns = [
        re.compile(r"(?i)\b([0-9]+(?:\.[0-9]+)?)\s*(N\.?M|N-M|Nm|newton[- ]?meter[s]?)\b"),
        re.compile(r"(?i)\b(Torque|Toqure)\b[^0-9]{0,80}([0-9]+(?:\.[0-9]+)?)\s*(N\.?M|N-M|Nm|newton[- ]?meter[s]?)\b"),
    ]
    match = first_regex_match(patterns, search_text)
    if match:
        if match.lastindex == 3:
            value_text = match.group(2)
            unit = match.group(3)
        else:
            value_text = match.group(1)
            unit = match.group(2)
        return FieldValue(
            value=safe_float(value_text, 0.0),
            unit=unit,
            confidence=0.90,
            source_text=compact_excerpt(match.group(0)),
            is_imputed=False,
        )

    return build_imputed_field("torque")


def extract_flow_rate(text: str) -> FieldValue:
    search_text = normalize_whitespace(text)
    patterns = [
        re.compile(r"(?i)\b([0-9]+(?:\.[0-9]+)?)\s*(m3/h|m\^3/h|m³/h|l/min|lpm|l/s|gpm|m3/min|m\^3/min|m3/s|m\^3/s)\b"),
        re.compile(r"(?i)\b(flow rate|flow|capacity)\b[^0-9]{0,60}([0-9]+(?:\.[0-9]+)?)\s*(m3/h|m\^3/h|m³/h|l/min|lpm|l/s|gpm|m3/min|m\^3/min|m3/s|m\^3/s)\b"),
    ]
    match = first_regex_match(patterns, search_text)
    if match:
        if match.lastindex == 3:
            value_text = match.group(2)
            unit = match.group(3)
        else:
            value_text = match.group(1)
            unit = match.group(2)
        return FieldValue(
            value=safe_float(value_text, 0.0),
            unit=unit,
            confidence=0.88,
            source_text=compact_excerpt(match.group(0)),
            is_imputed=False,
        )

    return build_imputed_field("flow_rate")


def local_extract(text: str) -> Dict[str, FieldValue]:
    extracted = {
        "rpm": extract_rpm(text),
        "pressure": extract_pressure(text),
        "temperature": extract_temperature(text),
        "torque": extract_torque(text),
        "flow_rate": extract_flow_rate(text),
    }
    return extracted


def coerce_llm_field(name: str, payload: Any) -> FieldValue:
    if not isinstance(payload, Mapping):
        return build_imputed_field(name)

    value = safe_float(payload.get("value"), DEFAULT_IMPUTATIONS[name][0])
    unit = str(payload.get("unit") or DEFAULT_IMPUTATIONS[name][1])
    confidence = safe_float(payload.get("confidence"), DEFAULT_IMPUTATIONS[name][2])
    confidence = clamp(confidence, 0.0, 1.0)
    source_text = str(payload.get("source_text") or DEFAULT_IMPUTATIONS[name][3])
    is_imputed = bool(payload.get("is_imputed", False))
    return FieldValue(
        value=value,
        unit=unit,
        confidence=confidence,
        source_text=source_text,
        is_imputed=is_imputed,
    )


def extract_parameters(text: str) -> Dict[str, FieldValue]:
    groq_payload = extract_with_groq(text)
    if isinstance(groq_payload, Mapping):
        result: Dict[str, FieldValue] = {}
        for name in FEATURE_ORDER:
            result[name] = coerce_llm_field(name, groq_payload.get(name))
        return result
    return local_extract(text)


# ---------------------------------------------------------------------------
# NORMALIZATION / ML FEATURES
# ---------------------------------------------------------------------------
def normalize_parameter(name: str, field: FieldValue) -> float:
    if name == "pressure":
        return normalize_pressure_value(field.value, field.unit)
    if name == "temperature":
        return normalize_temperature_value(field.value, field.unit)
    if name == "torque":
        return normalize_torque_value(field.value, field.unit)
    if name == "flow_rate":
        return normalize_flow_rate_value(field.value, field.unit)
    if name == "rpm":
        return field.value
    return field.value


def build_normalized_features(raw_data: Mapping[str, FieldValue]) -> Dict[str, float]:
    normalized: Dict[str, float] = {}
    for name in FEATURE_ORDER:
        field = raw_data.get(name) if isinstance(raw_data, Mapping) else None
        if isinstance(field, FieldValue):
            normalized[name] = safe_float(normalize_parameter(name, field), 0.0)
        elif isinstance(field, Mapping):
            coerced = coerce_llm_field(name, field)
            normalized[name] = safe_float(normalize_parameter(name, coerced), 0.0)
        else:
            normalized[name] = safe_float(DEFAULT_IMPUTATIONS[name][0], 0.0)
    return normalized


def feature_vector(normalized_features: Mapping[str, float]) -> List[float]:
    return [safe_float(normalized_features.get(name), 0.0) for name in FEATURE_ORDER]


# ---------------------------------------------------------------------------
# RISK MODEL EMULATION
# ---------------------------------------------------------------------------
def sigmoid(value: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-value))
    except OverflowError:
        return 0.0 if value < 0 else 1.0


def calculate_risk(
    params: Mapping[str, Any],
    prediction_bundle: Optional[PredictionBundle] = None,
) -> Dict[str, Any]:
    # The function is intentionally defensive: any None/missing value is replaced with a safe default.
    normalized_inputs = {
        "rpm": safe_float(params.get("rpm"), DEFAULT_IMPUTATIONS["rpm"][0]),
        "pressure": safe_float(params.get("pressure"), DEFAULT_IMPUTATIONS["pressure"][0]),
        "temperature": safe_float(params.get("temperature"), DEFAULT_IMPUTATIONS["temperature"][0]),
        "torque": safe_float(params.get("torque"), DEFAULT_IMPUTATIONS["torque"][0]),
        "flow_rate": safe_float(params.get("flow_rate"), DEFAULT_IMPUTATIONS["flow_rate"][0]),
    }

    feature_row = [
        max(0.0, normalized_inputs["rpm"]),
        max(0.0, normalized_inputs["pressure"]),
        normalized_inputs["temperature"],
        max(0.0, normalized_inputs["torque"]),
        max(0.0, normalized_inputs["flow_rate"]),
    ]

    probability = None
    backend_source = "heuristic"
    backend_error = None

    if prediction_bundle is not None and prediction_bundle.model is not None:
        try:
            model_probability = predict_probability_from_model(
                prediction_bundle.model,
                feature_row,
                prediction_bundle.scaler,
            )
            if model_probability is not None and not math.isnan(model_probability):
                probability = clamp(model_probability, 0.0, 100.0)
                backend_source = "model"
        except Exception as exc:
            backend_error = str(exc)

    if probability is None:
        probability = heuristic_probability_from_inputs(normalized_inputs)

    if probability < 25.0:
        risk_level = "LOW"
    elif probability < 50.0:
        risk_level = "MEDIUM"
    elif probability < 75.0:
        risk_level = "HIGH"
    else:
        risk_level = "CRITICAL"

    model_info = prediction_bundle.to_dict() if prediction_bundle is not None else {
        "document_type": DEFAULT_DOCUMENT_TYPE,
        "model_name": None,
        "model_path": None,
        "scaler_name": None,
        "scaler_path": None,
        "model_loaded": False,
        "scaler_loaded": False,
        "load_error": None,
    }

    return {
        "probability_percent": round(clamp(probability, 0.0, 100.0), 2),
        "risk_level": risk_level,
        "normalized_inputs": {
            key: round(value, 4) for key, value in normalized_inputs.items()
        },
        "prediction_backend": {
            "source": backend_source,
            "error": backend_error,
            **model_info,
        },
    }


# ---------------------------------------------------------------------------
# RE-CALCULATE LOGIC
# ---------------------------------------------------------------------------
def merge_field_override(base_field: FieldValue, override: Any, name: str) -> FieldValue:
    if isinstance(override, Mapping):
        merged = {
            "value": override.get("value", base_field.value),
            "unit": override.get("unit", base_field.unit),
            "confidence": override.get("confidence", 1.0),
            "source_text": override.get("source_text", "Manual override"),
            "is_imputed": override.get("is_imputed", False),
        }
        return coerce_llm_field(name, merged)

    return FieldValue(
        value=safe_float(override, base_field.value),
        unit=base_field.unit,
        confidence=1.0,
        source_text="Manual override",
        is_imputed=False,
    )


def recalculate_with_manual_input(
    original_data: Any,
    manual_changes: Mapping[str, Any],
    prediction_bundle: Optional[PredictionBundle] = None,
) -> Dict[str, Any]:
    if isinstance(original_data, Mapping) and "raw_data" in original_data:
        base_raw = original_data["raw_data"]
    else:
        base_raw = original_data

    if prediction_bundle is None and isinstance(original_data, Mapping):
        model_selection = original_data.get("model_selection")
        document_type = DEFAULT_DOCUMENT_TYPE
        if isinstance(model_selection, Mapping):
            document_type = str(model_selection.get("document_type") or DEFAULT_DOCUMENT_TYPE)
        prediction_bundle = prepare_prediction_bundle("", explicit_document_type=document_type)

    updated_raw: Dict[str, FieldValue] = {}

    for name in FEATURE_ORDER:
        base_field = base_raw.get(name) if isinstance(base_raw, Mapping) else None
        if isinstance(base_field, FieldValue):
            updated_raw[name] = copy.deepcopy(base_field)
        elif isinstance(base_field, Mapping):
            updated_raw[name] = coerce_llm_field(name, base_field)
        else:
            updated_raw[name] = build_imputed_field(name)

    for name, override in manual_changes.items():
        if name not in FEATURE_ORDER:
            continue
        updated_raw[name] = merge_field_override(updated_raw[name], override, name)

    normalized = build_normalized_features(updated_raw)
    risk_report = calculate_risk(normalized, prediction_bundle)

    return {
        "document_type": prediction_bundle.document_type if prediction_bundle else DEFAULT_DOCUMENT_TYPE,
        "model_selection": prediction_bundle.to_dict() if prediction_bundle else {
            "document_type": DEFAULT_DOCUMENT_TYPE,
            "model_name": None,
            "model_path": None,
            "scaler_name": None,
            "scaler_path": None,
            "model_loaded": False,
            "scaler_loaded": False,
            "load_error": None,
        },
        "raw_data": {name: field.to_dict() for name, field in updated_raw.items()},
        "normalized_features": normalized,
        "feature_vector": feature_vector(normalized),
        "risk_report": risk_report,
    }


# ---------------------------------------------------------------------------
# PIPELINE HELPERS
# ---------------------------------------------------------------------------
def analyze_text(text: str) -> Dict[str, Any]:
    prediction_bundle = prepare_prediction_bundle(text)
    raw_data = extract_parameters(text)
    normalized_features = build_normalized_features(raw_data)
    risk_report = calculate_risk(normalized_features, prediction_bundle)

    return {
        "document_type": prediction_bundle.document_type,
        "model_selection": prediction_bundle.to_dict(),
        "raw_data": {name: field.to_dict() for name, field in raw_data.items()},
        "normalized_features": normalized_features,
        "feature_vector": feature_vector(normalized_features),
        "risk_report": risk_report,
    }


def print_analysis_block(title: str, bundle: Mapping[str, Any]) -> None:
    print(f"\n=== {title} ===")
    print(f"Detected Document Type: {bundle.get('document_type', DEFAULT_DOCUMENT_TYPE)}")
    print("Model Selection")
    print(json.dumps(bundle.get("model_selection", {}), ensure_ascii=False, indent=2))
    print("Raw Data from LLM")
    print(json.dumps(bundle["raw_data"], ensure_ascii=False, indent=2))
    print("\nNormalized Features for ML")
    print(json.dumps(bundle["feature_vector"], ensure_ascii=False, indent=2))
    print("\nFinal Risk Report")
    print(json.dumps(bundle["risk_report"], ensure_ascii=False, indent=2))


def simulate_manual_recalculation(bundle: Mapping[str, Any]) -> Dict[str, Any]:
    current_rpm = safe_float(bundle["normalized_features"].get("rpm"), 0.0)
    manual_changes = {
        "rpm": {
            "value": current_rpm + 250.0,
            "unit": "rpm",
            "confidence": 1.0,
            "source_text": "Manual CLI override for recalculation demo",
            "is_imputed": False,
        }
    }
    return recalculate_with_manual_input(bundle, manual_changes)


def main() -> None:
    text = load_input_text()
    if not text.strip():
        print("No input text found. Paste extracted PDF text into TEST_TEXT or create test.txt next to debug_parser.py.")
        text = ""

    first_bundle = analyze_text(text)
    print_analysis_block("Initial Analysis", first_bundle)

    updated_bundle = simulate_manual_recalculation(first_bundle)
    print_analysis_block("Recalculated After Manual RPM Override", updated_bundle)


if __name__ == "__main__":
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    
    print("="*50)
    print("🔍 ПРОВЕРКА ОКРУЖЕНИЯ:")
    if api_key:
        print(f"✅ GROQ_API_KEY найден! (начинается на: {api_key[:7]}...)")
    else:
        print("❌ КЛЮЧ НЕ НАЙДЕН! Проверь, что файл .env лежит в этой же папке.")
    

    if len(sys.argv) > 1:
        target_file = sys.argv[1]
        print(f"📂 Целевой файл для парсинга: {target_file}")
    else:
        print(f"📂 Файл не указан, использую дефолт: {DEFAULT_PDF_PATH}")
    print("="*50 + "\n")
    print("🚀 Запуск отладочного парсера...")
    

    input_text = load_input_text()
    
    if not input_text:
        print("❌ Ошибка: Входной текст не найден. Проверьте файлы или аргументы.")
        sys.exit(1)
        
    print(f"📄 Текст загружен (символов: {len(input_text)})")
    print("-" * 50)


    print("🤖 Отправка запроса в Groq LLM...")
    raw_result = extract_with_groq(input_text)
    
    if raw_result:
        print("✅ Данные успешно получены от ИИ!")
    else:
        print("⚠️ Groq не ответил. Проверьте API_KEY или интернет.")
        print("⚙️ Переключаюсь на локальные (старые) функции...")

        raw_result = {
            "rpm": extract_rpm(input_text).to_dict(),
            "pressure": extract_pressure(input_text).to_dict(),
            "temperature": extract_temperature(input_text).to_dict(),
            "torque": extract_torque(input_text).to_dict(),
            "flow_rate": extract_flow_rate(input_text).to_dict()
        }


    print("\n⚖️ Нормализация единиц измерения...")
    features_for_ml = []
    

    processed_data = {}
    for field in FEATURE_ORDER:
        data = raw_result.get(field, {})
        val = safe_float(data.get("value"), 0.0)
        unit = data.get("unit", "")
        

        if field == "pressure": val = normalize_pressure_value(val, unit)
        if field == "temperature": val = normalize_temperature_value(val, unit)
        if field == "torque": val = normalize_torque_value(val, unit)
        if field == "flow_rate": val = normalize_flow_rate_value(val, unit)
        
        processed_data[field] = val
        features_for_ml.append(val)


    print("\n" + "="*60)
    print(f"{'ПАРАМЕТР':<15} | {'ИСХОДНЫЙ':<15} | {'ПОСЛЕ КОНВЕРТАЦИИ':<15}")
    print("-" * 60)
    for field in FEATURE_ORDER:
        orig = raw_result.get(field, {})
        

        raw_val = orig.get('value') if orig.get('value') is not None else "0.0"
        raw_unit = orig.get('unit') if orig.get('unit') is not None else ""
        

        print(f"{field:<15} | {str(raw_val):>7} {str(raw_unit):<6} | {processed_data[field]:>10.2f}")


    risk = heuristic_probability_from_inputs(processed_data)
    print("="*60)
    print(f"🔮 ИТОГОВЫЙ ML-ПРОГНОЗ РИСКА: {risk:.1f}%")
    

    print("\n🔄 ИМИТАЦИЯ РУЧНОГО ИЗМЕНЕНИЯ (Повышаем давление до 500 Bar)...")
    manual_data = copy.deepcopy(processed_data)
    manual_data["pressure"] = 500.0
    new_risk = heuristic_probability_from_inputs(manual_data)
    print(f"📈 ОБНОВЛЕННЫЙ РИСК: {new_risk:.1f}%")