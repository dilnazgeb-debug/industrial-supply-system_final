"""
PDF Document Parser with Multi-Model Support
===============================================

Extracts text from PDFs, segments by equipment models, and handles complex layouts.
Supports tables, fuzzy matching, and unit conversion.
"""

import os
import logging
import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict
import json

try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# UNIT CONVERSION
# ═══════════════════════════════════════════════════════════════════

UNIT_CONVERSIONS = {
    'celsius_to_kelvin': lambda x: x + 273.15,
    'fahrenheit_to_kelvin': lambda x: (x - 32) * 5/9 + 273.15,
    'psi_to_bar': lambda x: x * 0.0689476,
    'mpa_to_bar': lambda x: x * 10,
}

TEMPERATURE_PATTERNS = {
    '°C': 'celsius',
    'C': 'celsius',
    '°F': 'fahrenheit',
    'F': 'fahrenheit',
    'K': 'kelvin',
    'K': 'kelvin'
}

PRESSURE_PATTERNS = {
    'psi': 'psi',
    'PSI': 'psi',
    'bar': 'bar',
    'BAR': 'bar',
    'mpa': 'mpa',
    'MPA': 'mpa',
    'pa': 'pa',
    'PA': 'pa',
    'atm': 'atm',
    'ATM': 'atm'
}

# ═══════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class EquipmentSegment:
    """Represents one equipment entry from a PDF"""
    segment_index: int
    model_number: Optional[str]
    equipment_title: Optional[str]
    raw_text: str
    extracted_tables: List[str]
    page_numbers: List[int]
    confidence_score: float
    source_file: str
    
    def to_dict(self):
        return asdict(self)

@dataclass
class PDFExtractionResult:
    """Result of PDF extraction"""
    filename: str
    total_pages: int
    segments: List[EquipmentSegment]
    extraction_quality: str  # 'excellent', 'good', 'fair', 'poor'
    warnings: List[str]
    
    def to_dict(self):
        return {
            'filename': self.filename,
            'total_pages': self.total_pages,
            'segments': [seg.to_dict() for seg in self.segments],
            'extraction_quality': self.extraction_quality,
            'warnings': self.warnings
        }

# ═══════════════════════════════════════════════════════════════════
# PDF PARSER
# ═══════════════════════════════════════════════════════════════════

class PDFParser:
    """
    Intelligent PDF parser with:
    - Multi-model segmentation
    - Fuzzy regex extraction
    - Unit conversion
    - Table parsing
    """
    
    # Patterns for equipment segmentation
    MODEL_NUMBER_PATTERNS = [
        r'model\s*(?:number|#|:)?\s*([A-Z0-9\-]{2,10})',
        r'модель\s*(?:#|:)?\s*([A-Z0-9\-]{2,10})',
        r'型号\s*(?:：|:)?\s*([A-Z0-9\-]{2,10})',
        r'(?:^|\n)([A-Z]{2,4}[-\s]?\d{3,6}[A-Z]?)(?:\s|$)',  # Generic model
    ]
    
    EQUIPMENT_TITLE_PATTERNS = [
        r'(?:^|\n)(.*?(?:pump|valve|cooler|accumulator|motor|motor|engine|turbine).*?)(?:\n|$)',
        r'(?:^|\n)(.*?(?:насос|клапан|охладитель|аккумулятор|двигатель).*?)(?:\n|$)',
        r'(?:^|\n)(.*?(?:泵|阀门|冷却器|蓄能器).*?)(?:\n|$)',
        r'product\s*(?:name|title|:)\s*([^\n]+)',
    ]
    
    @staticmethod
    def extract_from_pdf(pdf_path: str) -> PDFExtractionResult:
        """
        Extract text and structure from PDF
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            PDFExtractionResult with segments
        """
        if not PDF_SUPPORT:
            raise ImportError("pdfplumber not installed. Run: pip install pdfplumber")
        
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        filename = os.path.basename(pdf_path)
        logger.info(f"📄 Parsing PDF: {filename}")
        
        segments = []
        warnings = []
        all_pages_text = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                logger.info(f"   Pages: {total_pages}")
                
                # Extract text from all pages
                for page_idx, page in enumerate(pdf.pages):
                    try:
                        # Get text
                        text = page.extract_text() or ""
                        all_pages_text.append({
                            'page': page_idx + 1,
                            'text': text,
                            'tables': PDFParser._extract_tables(page)
                        })
                    except Exception as e:
                        warnings.append(f"Error parsing page {page_idx + 1}: {e}")
                        logger.warning(f"⚠️  Page {page_idx + 1}: {e}")
                
                # Segment documents by equipment
                combined_text = "\n".join([p['text'] for p in all_pages_text])
                segments = PDFParser._segment_equipment(
                    combined_text, 
                    all_pages_text,
                    filename
                )
                
                # Evaluate extraction quality
                quality = PDFParser._evaluate_extraction_quality(combined_text, segments)
                
        except Exception as e:
            logger.error(f"❌ PDF extraction failed: {e}")
            warnings.append(f"Critical error: {e}")
            quality = 'poor'
        
        logger.info(f"✅ Extracted {len(segments)} equipment segments")
        
        return PDFExtractionResult(
            filename=filename,
            total_pages=total_pages if 'total_pages' in locals() else 0,
            segments=segments,
            extraction_quality=quality,
            warnings=warnings
        )
    
    @staticmethod
    def _extract_tables(page) -> List[str]:
        """Extract tables from a PDF page"""
        tables = []
        try:
            extracted_tables = page.extract_tables()
            if extracted_tables:
                for table in extracted_tables:
                    # Convert table to text
                    table_text = "\n".join([
                        " | ".join([str(cell) if cell else "" for cell in row])
                        for row in table
                    ])
                    tables.append(table_text)
        except Exception as e:
            logger.debug(f"Table extraction issue: {e}")
        
        return tables
    
    @staticmethod
    def _segment_equipment(
        combined_text: str,
        page_data: List[Dict],
        source_file: str
    ) -> List[EquipmentSegment]:
        """
        Segment PDF into individual equipment entries
        
        Logic:
        1. Find all model numbers and equipment titles
        2. Create segments starting from each model number
        3. Assign text and tables to segments
        """
        segments = []
        
        # Find all model numbers in text
        model_positions = []
        for pattern in PDFParser.MODEL_NUMBER_PATTERNS:
            for match in re.finditer(pattern, combined_text, re.IGNORECASE | re.MULTILINE):
                model_positions.append({
                    'pos': match.start(),
                    'model': match.group(1) if match.lastindex else match.group(0),
                    'pattern': pattern
                })
        
        # Sort by position
        model_positions.sort(key=lambda x: x['pos'])
        
        # Create segments
        for idx, model_info in enumerate(model_positions):
            start_pos = model_info['pos']
            
            # Find end position (start of next model or end of text)
            if idx + 1 < len(model_positions):
                end_pos = model_positions[idx + 1]['pos']
            else:
                end_pos = len(combined_text)
            
            segment_text = combined_text[start_pos:end_pos]
            
            # Extract equipment title (first few lines with equipment keyword)
            title_match = None
            for pattern in PDFParser.EQUIPMENT_TITLE_PATTERNS:
                title_match = re.search(pattern, segment_text[:500], re.IGNORECASE | re.MULTILINE)
                if title_match:
                    break
            
            title = title_match.group(1).strip() if title_match else None
            
            # Find which pages this segment spans
            page_numbers = PDFParser._find_segment_pages(start_pos, end_pos, combined_text, page_data)
            
            # Extract tables from segment
            segment_tables = []
            for page_info in page_data:
                if page_info['page'] in page_numbers:
                    segment_tables.extend(page_info['tables'])
            
            segment = EquipmentSegment(
                segment_index=idx,
                model_number=model_info['model'],
                equipment_title=title,
                raw_text=segment_text,
                extracted_tables=segment_tables,
                page_numbers=page_numbers,
                confidence_score=PDFParser._calculate_segment_confidence(segment_text),
                source_file=source_file
            )
            
            segments.append(segment)
            logger.info(f"   ✓ Segment {idx}: {segment.model_number or 'Unknown'} ({len(segment_text)} chars)")
        
        return segments
    
    @staticmethod
    def _find_segment_pages(
        start_pos: int,
        end_pos: int,
        combined_text: str,
        page_data: List[Dict]
    ) -> List[int]:
        """Find which pages a segment spans"""
        pages = []
        current_pos = 0
        
        for page_info in page_data:
            page_text = page_info['text']
            page_start = current_pos
            page_end = current_pos + len(page_text)
            
            if start_pos < page_end and end_pos > page_start:
                pages.append(page_info['page'])
            
            current_pos = page_end
        
        return pages if pages else [1]
    
    @staticmethod
    def _calculate_segment_confidence(segment_text: str) -> float:
        """Calculate confidence score (0-1) for segment quality"""
        score = 0.5  # Base score
        
        # Has model number
        if re.search(r'model|модель|型号', segment_text, re.IGNORECASE):
            score += 0.2
        
        # Has parameters
        param_count = len(re.findall(r'\d+\.?\d*\s*(?:rpm|bar|kw|nm|k|°c)', segment_text, re.IGNORECASE))
        score += min(0.2, param_count * 0.05)
        
        # Has tables (usually high quality)
        if '|' in segment_text:
            score += 0.1
        
        return min(1.0, score)
    
    @staticmethod
    def _evaluate_extraction_quality(text: str, segments: List[EquipmentSegment]) -> str:
        """Evaluate overall extraction quality"""
        if not segments:
            return 'poor'
        
        avg_confidence = sum(s.confidence_score for s in segments) / len(segments)
        
        if avg_confidence > 0.8:
            return 'excellent'
        elif avg_confidence > 0.6:
            return 'good'
        elif avg_confidence > 0.4:
            return 'fair'
        else:
            return 'poor'

# ═══════════════════════════════════════════════════════════════════
# FUZZY PARAMETER EXTRACTION
# ═══════════════════════════════════════════════════════════════════

class FuzzyParameterExtractor:
    """
    Extract parameters using fuzzy matching and context clues
    Handles noisy text, tables, and missing values
    """
    
    # Fuzzy patterns (more lenient than strict regex)
    FUZZY_PATTERNS = {
        'rpm': [
            r'rpm\s*:?\s*(\d+)',
            r'rotation.*?(\d+)\s*rpm',
            r'speed.*?(\d+)\s*rpm',
            r'(\d{3,5})\s*(?:rpm|ob|об/мин)',
        ],
        'pressure': [
            r'pressure\s*:?\s*(\d+)\s*(?:bar|psi)',
            r'(\d+)\s*(?:bar|psi|pa)',
            r'давл.*?(\d+)\s*(?:bar|атм)',
        ],
        'temperature': [
            r'temp\s*:?\s*(\d+)\s*(?:k|°c|°f)',
            r'temperature\s*:?\s*(\d+)\s*(?:k|°c|°f)',
            r'(\d+)\s*(?:°c|k|°f)',
        ],
        'torque': [
            r'torque\s*:?\s*(\d+)\s*(?:nm|n\.m)',
            r'момент\s*:?\s*(\d+)\s*(?:nm|н\.м)',
            r'(\d+)\s*(?:nm|н\.м)',
        ],
        'power': [
            r'power\s*:?\s*(\d+)\s*(?:kw|hp|квт)',
            r'мощность\s*:?\s*(\d+)\s*(?:kw|квт)',
            r'(\d+)\s*(?:kw|квт)',
        ],
    }
    
    @staticmethod
    def extract_parameters_fuzzy(text: str, tables: List[str]) -> Dict[str, Tuple[float, str, bool]]:
        """
        Extract parameters with fuzzy matching
        
        Returns:
            Dict with param_name -> (value, source, is_estimated)
            source: 'text', 'table', 'inferred'
        """
        parameters = {}
        
        # Try text extraction first
        for param_name, patterns in FuzzyParameterExtractor.FUZZY_PATTERNS.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    try:
                        value = float(match.group(1))
                        parameters[param_name] = (value, 'text', False)
                        logger.info(f"✓ Extracted {param_name}: {value} (fuzzy)")
                        break
                    except (ValueError, IndexError):
                        pass
                
                if param_name in parameters:
                    break
        
        # Try table extraction
        for table_text in tables:
            for param_name, patterns in FuzzyParameterExtractor.FUZZY_PATTERNS.items():
                if param_name not in parameters:
                    for pattern in patterns:
                        match = re.search(pattern, table_text, re.IGNORECASE)
                        if match:
                            try:
                                value = float(match.group(1))
                                parameters[param_name] = (value, 'table', False)
                                logger.info(f"✓ Extracted {param_name}: {value} (table)")
                                break
                            except (ValueError, IndexError):
                                pass
        
        return parameters
    
    @staticmethod
    def convert_units(value: float, from_unit: str, to_unit: str) -> float:
        """Convert units automatically"""
        if from_unit == to_unit:
            return value
        
        conversion_key = f'{from_unit}_to_{to_unit}'.lower()
        if conversion_key in UNIT_CONVERSIONS:
            return UNIT_CONVERSIONS[conversion_key](value)
        
        logger.warning(f"⚠️ Unknown conversion: {from_unit} → {to_unit}")
        return value

# ═══════════════════════════════════════════════════════════════════
# PDF WORKFLOW
# ═══════════════════════════════════════════════════════════════════

def parse_pdf_and_audit(pdf_path: str, knowledge_base: Dict = None) -> List[Dict]:
    """
    Complete workflow: Parse PDF → Segment → Extract → Audit
    
    Args:
        pdf_path: Path to PDF file
        knowledge_base: Optional knowledge base for RAG
        
    Returns:
        List of audit results per equipment
    """
    logger.info("🚀 Starting PDF Audit Pipeline")
    
    # Step 1: Extract from PDF
    result = PDFParser.extract_from_pdf(pdf_path)
    logger.info(f"   Quality: {result.extraction_quality}")
    
    if result.warnings:
        logger.warning(f"⚠️ Warnings: {result.warnings}")
    
    # Step 2: Process each segment
    audits = []
    for segment in result.segments:
        logger.info(f"\n   📊 Processing segment {segment.segment_index}: {segment.model_number}")
        
        # Extract parameters with fuzzy matching
        parameters = FuzzyParameterExtractor.extract_parameters_fuzzy(
            segment.raw_text,
            segment.extracted_tables
        )
        
        # Use knowledge base for missing parameters
        if knowledge_base and segment.model_number:
            parameters = _enrich_with_knowledge_base(
                segment.model_number,
                parameters,
                knowledge_base
            )
        
        # Prepare audit payload
        audit_payload = {
            'model_number': segment.model_number,
            'equipment_title': segment.equipment_title,
            'raw_text': segment.raw_text,
            'parameters': parameters,
            'tables': segment.extracted_tables,
            'page_numbers': segment.page_numbers,
            'confidence': segment.confidence_score,
            'source_file': segment.source_file
        }
        
        audits.append(audit_payload)
    
    logger.info(f"✅ Processed {len(audits)} equipment entries")
    return audits

def _enrich_with_knowledge_base(
    model_number: str,
    extracted_params: Dict,
    knowledge_base: Dict
) -> Dict:
    """
    Use knowledge base to fill missing parameters
    If model found in KB, use KB values as defaults
    """
    if 'models' not in knowledge_base:
        return extracted_params
    
    # Search for model in knowledge base
    for model_entry in knowledge_base.get('models', []):
        if model_entry.get('model_number', '').lower() == model_number.lower():
            logger.info(f"   📚 Found in knowledge base: {model_number}")
            
            # Fill missing parameters from KB
            for param_name, kb_value in model_entry.get('default_parameters', {}).items():
                if param_name not in extracted_params:
                    extracted_params[param_name] = (kb_value, 'knowledge_base', True)
                    logger.info(f"   ✓ Added from KB: {param_name} = {kb_value} (estimated)")
            
            break
    
    return extracted_params
