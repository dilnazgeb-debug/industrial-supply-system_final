#!/usr/bin/env python3
"""
Model Training Script for Equipment Failure Prediction

This script trains machine learning models for the Intelligent Model Dispatcher
system. It uses the predictive_maintenance.csv file to create equipment-specific
failure prediction models.

Usage:
    python train_models.py
    
    Or with specific parameters:
    python train_models.py --algorithm xgboost --cv-folds 10
"""

import os
import sys
import json
import joblib
import pandas as pd
import numpy as np
import warnings
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Tuple, List

# Suppress warnings
warnings.filterwarnings('ignore')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import ML libraries
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, 
    roc_auc_score, confusion_matrix, classification_report
)

try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logger.warning("⚠️  XGBoost not installed. Using scikit-learn models only.")


# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

MODELS_DIR = Path(__file__).parent / 'models'
DATA_FILE = Path(__file__).parent / 'predictive_maintenance.csv'

EQUIPMENT_TYPES = {
    'L': {
        'name': 'pump',
        'file': 'pump.pkl',
        'description': 'Centrifugal/Axial Flow Pumps'
    },
    'M': {
        'name': 'valve',
        'file': 'valve.pkl',
        'description': 'Directional Control Valves'
    },
    'H': {
        'name': 'cooler',
        'file': 'cooler.pkl',
        'description': 'Air Coolers and Heat Exchangers'
    },
    'D': {
        'name': 'accumulator',
        'file': 'accumulator.pkl',
        'description': 'Hydraulic Accumulators'
    }
}

FEATURE_NAMES = [
    'Air temperature [K]',
    'Process temperature [K]',
    'Rotational speed [rpm]',
    'Torque [Nm]',
    'Tool wear [min]'
]

MODEL_PARAMS = {
    'random_forest': {
        'n_estimators': 100,
        'max_depth': 10,
        'min_samples_split': 5,
        'min_samples_leaf': 2,
        'random_state': 42,
        'n_jobs': -1,
        'class_weight': 'balanced'
    },
    'xgboost': {
        'n_estimators': 100,
        'max_depth': 7,
        'learning_rate': 0.1,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'scale_pos_weight': 3,
        'random_state': 42,
        'eval_metric': 'logloss'
    },
    'gradient_boosting': {
        'n_estimators': 100,
        'learning_rate': 0.05,
        'max_depth': 5,
        'min_samples_split': 5,
        'min_samples_leaf': 2,
        'random_state': 42,
        'subsample': 0.8
    }
}


# ═══════════════════════════════════════════════════════════════════
# DATA LOADING & PREPARATION
# ═══════════════════════════════════════════════════════════════════

def load_and_validate_data() -> pd.DataFrame:
    """Load and validate predictive maintenance data"""
    logger.info(f"📂 Loading data from: {DATA_FILE}")
    
    if not DATA_FILE.exists():
        logger.error(f"❌ Data file not found: {DATA_FILE}")
        sys.exit(1)
    
    data = pd.read_csv(DATA_FILE)
    logger.info(f"✅ Loaded {len(data)} records")
    
    # Validate required columns
    missing_cols = [col for col in FEATURE_NAMES + ['Type', 'Target'] if col not in data.columns]
    if missing_cols:
        logger.error(f"❌ Missing columns: {missing_cols}")
        sys.exit(1)
    
    logger.info(f"✅ Data validation passed")
    return data


def prepare_features(data: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, StandardScaler]:
    """Prepare and scale features"""
    logger.info("🔄 Preparing features...")
    
    X = data[FEATURE_NAMES].values
    y = data['Target'].values
    
    # Handle missing values
    X = np.nan_to_num(X, nan=np.nanmean(X, axis=0))
    
    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    logger.info(f"✅ Features prepared: shape {X_scaled.shape}")
    logger.info(f"  - Feature means: {scaler.mean_}")
    logger.info(f"  - Feature stds:  {scaler.scale_}")
    
    return X_scaled, y, scaler


# ═══════════════════════════════════════════════════════════════════
# MODEL TRAINING
# ═══════════════════════════════════════════════════════════════════

def create_model(algorithm: str = 'random_forest'):
    """Create ML model based on algorithm"""
    if algorithm == 'xgboost':
        if not XGBOOST_AVAILABLE:
            logger.warning("XGBoost not available, using RandomForest instead")
            return RandomForestClassifier(**MODEL_PARAMS['random_forest'])
        return XGBClassifier(**MODEL_PARAMS['xgboost'])
    elif algorithm == 'gradient_boosting':
        return GradientBoostingClassifier(**MODEL_PARAMS['gradient_boosting'])
    else:  # random_forest (default)
        return RandomForestClassifier(**MODEL_PARAMS['random_forest'])


def train_equipment_model(
    equipment_code: str,
    data: pd.DataFrame,
    X_scaled: np.ndarray,
    y: np.ndarray,
    algorithm: str = 'random_forest',
    cv_folds: int = 5
) -> Dict:
    """Train model for specific equipment type"""
    
    equipment_info = EQUIPMENT_TYPES[equipment_code]
    equipment_name = equipment_info['name']
    
    logger.info(f"\n🚀 Training {equipment_name.upper()} model...")
    logger.info(f"   Description: {equipment_info['description']}")
    
    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, 
        test_size=0.2, 
        random_state=42,
        stratify=y
    )
    
    logger.info(f"   Training set: {len(X_train)} samples")
    logger.info(f"   Test set: {len(X_test)} samples")
    logger.info(f"   Class distribution (train): {np.bincount(y_train)}")
    
    # Create and train model
    model = create_model(algorithm)
    logger.info(f"   Algorithm: {algorithm}")
    
    model.fit(X_train, y_train)
    
    # Evaluate
    y_train_pred = model.predict(X_train)
    y_test_pred = model.predict(X_test)
    y_test_proba = model.predict_proba(X_test)[:, 1]
    
    train_accuracy = accuracy_score(y_train, y_train_pred)
    test_accuracy = accuracy_score(y_test, y_test_pred)
    
    # Cross-validation
    cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)
    cv_scores = cross_val_score(model, X_train, y_train, cv=cv, scoring='accuracy')
    
    # Detailed metrics
    precision = precision_score(y_test, y_test_pred, zero_division=0)
    recall = recall_score(y_test, y_test_pred, zero_division=0)
    f1 = f1_score(y_test, y_test_pred, zero_division=0)
    roc_auc = roc_auc_score(y_test, y_test_proba) if len(np.unique(y_test)) > 1 else 0
    
    # Feature importance
    if hasattr(model, 'feature_importances_'):
        feature_importance = dict(zip(
            ['Air Temp', 'Process Temp', 'RPM', 'Torque', 'Tool Wear'],
            model.feature_importances_
        ))
    else:
        feature_importance = {}
    
    # Results
    results = {
        'equipment': equipment_name,
        'algorithm': algorithm,
        'train_accuracy': float(train_accuracy),
        'test_accuracy': float(test_accuracy),
        'cv_mean': float(cv_scores.mean()),
        'cv_std': float(cv_scores.std()),
        'precision': float(precision),
        'recall': float(recall),
        'f1_score': float(f1),
        'roc_auc': float(roc_auc),
        'feature_importance': feature_importance,
        'timestamp': datetime.now().isoformat()
    }
    
    # Logging results
    logger.info(f"\n   📊 Performance Metrics:")
    logger.info(f"      Train Accuracy: {train_accuracy:.2%}")
    logger.info(f"      Test Accuracy:  {test_accuracy:.2%}")
    logger.info(f"      CV Score:       {cv_scores.mean():.2%} (± {cv_scores.std():.2%})")
    logger.info(f"      Precision:      {precision:.2%}")
    logger.info(f"      Recall:         {recall:.2%}")
    logger.info(f"      F1-Score:       {f1:.2%}")
    logger.info(f"      ROC-AUC:        {roc_auc:.2%}")
    
    if feature_importance:
        logger.info(f"\n   🎯 Feature Importance:")
        for feat, imp in sorted(feature_importance.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"      {feat}: {imp:.2%}")
    
    # Classification report
    logger.info(f"\n   📋 Classification Report:")
    report = classification_report(y_test, y_test_pred, output_dict=True)
    logger.info(f"      Class 0 (Normal):   Precision={report['0']['precision']:.2%}, "
                f"Recall={report['0']['recall']:.2%}")
    logger.info(f"      Class 1 (Failure):  Precision={report['1']['precision']:.2%}, "
                f"Recall={report['1']['recall']:.2%}")
    
    return model, results


def save_models(models: Dict, scaler: StandardScaler) -> None:
    """Save trained models to disk"""
    logger.info(f"\n💾 Saving models to: {MODELS_DIR}")
    
    # Create models directory if needed
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save models
    for equipment_code, model_info in EQUIPMENT_TYPES.items():
        if equipment_code in models:
            model, results = models[equipment_code]
            filepath = MODELS_DIR / model_info['file']
            joblib.dump(model, filepath)
            logger.info(f"✅ Saved: {model_info['file']}")
    
    # Save scaler
    scaler_path = MODELS_DIR / 'scaler.pkl'
    joblib.dump(scaler, scaler_path)
    logger.info(f"✅ Saved: scaler.pkl")
    
    # Save metadata
    metadata = {
        'created': datetime.now().isoformat(),
        'models': {
            code: {
                'name': EQUIPMENT_TYPES['name'],
                'file': EQUIPMENT_TYPES['file'],
                'description': EQUIPMENT_TYPES['description'],
                **models[code][1]
            }
            for code in models if code in EQUIPMENT_TYPES
        }
    }
    
    metadata_path = MODELS_DIR / 'metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"✅ Saved: metadata.json")


def load_and_test_models(scaler: StandardScaler) -> None:
    """Load and test saved models"""
    logger.info(f"\n🧪 Testing saved models...")
    
    # Test data sample
    test_sample = np.array([[298.1, 308.6, 1500, 42.5, 0]])
    test_scaled = scaler.transform(test_sample)
    
    for equipment_code, info in EQUIPMENT_TYPES.items():
        model_path = MODELS_DIR / info['file']
        
        if model_path.exists():
            model = joblib.load(model_path)
            prediction = model.predict_proba(test_scaled)[0]
            
            logger.info(f"   {info['name'].upper()}:")
            logger.info(f"      Normal probability: {prediction[0]:.2%}")
            logger.info(f"      Failure probability: {prediction[1]:.2%}")
        else:
            logger.warning(f"   ⚠️  Model not found: {model_path}")


# ═══════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════

def main():
    """Main training pipeline"""
    logger.info("="*60)
    logger.info("🤖 Equipment Failure Prediction Model Training")
    logger.info("="*60)
    
    # 1. Load and prepare data
    data = load_and_validate_data()
    X_scaled, y, scaler = prepare_features(data)
    
    # 2. Train models for each equipment type
    models = {}
    for equipment_code in EQUIPMENT_TYPES.keys():
        model, results = train_equipment_model(
            equipment_code,
            data,
            X_scaled,
            y,
            algorithm='random_forest',
            cv_folds=5
        )
        models[equipment_code] = (model, results)
    
    # 3. Save models
    save_models(models, scaler)
    
    # 4. Test models
    load_and_test_models(scaler)
    
    logger.info("\n" + "="*60)
    logger.info("✅ Training completed successfully!")
    logger.info("="*60)
    logger.info(f"\nModels saved to: {MODELS_DIR}")
    logger.info("\nYou can now use the Intelligent Model Dispatcher system.")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.error(f"❌ Error during training: {e}", exc_info=True)
        sys.exit(1)
