#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to verify that all new modules can be imported and basic functionality works.
This script checks syntax, imports, and basic class/function availability without requiring full dependencies.
"""

import sys
import os

# Add the integrated_app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'integrated_app'))

def test_module_imports():
    """Test that all new modules can be imported."""
    print("Testing module imports...")
    
    # Test GPU utils
    try:
        from gpu_utils import is_oom_error, free_gpu_memory
        print("  [OK] gpu_utils")
    except ImportError as e:
        print(f"  [FAIL] gpu_utils: {e}")
        return False
    
    # Test model registry
    try:
        from model_registry import ModelRegistry
        print("  [OK] model_registry")
    except ImportError as e:
        print(f"  [FAIL] model_registry: {e}")
        return False
    
    # Test config models
    try:
        from config_models import AppConfig
        print("  [OK] config_models")
    except ImportError as e:
        print(f"  [FAIL] config_models: {e}")
        return False
    
    # Test estimator
    try:
        from estimator import GenerationTimeEstimator
        print("  [OK] estimator")
    except ImportError as e:
        print(f"  [FAIL] estimator: {e}")
        return False
    
    # Test engine interface
    try:
        from engine_interface import TTSEngine, ControllableTTSEngine
        print("  [OK] engine_interface")
    except ImportError as e:
        print(f"  [FAIL] engine_interface: {e}")
        return False
    
    # Test monitor
    try:
        from monitor import HealthMonitor, get_health_monitor
        print("  [OK] monitor")
    except ImportError as e:
        print(f"  [FAIL] monitor: {e}")
        return False
    
    # Test audio processing
    try:
        from audio_processing import enhance_audio, normalize_loudness
        print("  [OK] audio_processing")
    except ImportError as e:
        print(f"  [FAIL] audio_processing: {e}")
        return False
    
    # Test history db
    try:
        from history_db import HistoryDatabase, create_history_db
        print("  [OK] history_db")
    except ImportError as e:
        print(f"  [FAIL] history_db: {e}")
        return False
    
    # Test batch inference
    try:
        from batch_inference import BatchInferencer, BatchResult
        print("  [OK] batch_inference")
    except ImportError as e:
        print(f"  [FAIL] batch_inference: {e}")
        return False
    
    # Test persona metadata
    try:
        from persona_metadata import PersonaMetadata, PersonaExporter, load_persona_metadata
        print("  [OK] persona_metadata")
    except ImportError as e:
        print(f"  [FAIL] persona_metadata: {e}")
        return False
    
    # Test comparison
    try:
        from comparison import ComparisonSession, format_param_diff
        print("  [OK] comparison")
    except ImportError as e:
        print(f"  [FAIL] comparison: {e}")
        return False
    
    print("All modules imported successfully!")
    return True


def test_basic_functionality():
    """Test basic functionality of key components."""
    print("\nTesting basic functionality...")
    
    # Test GenerationTimeEstimator
    try:
        from estimator import GenerationTimeEstimator
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name
        
        estimator = GenerationTimeEstimator(data_file=temp_file, max_entries=10)
        
        # Record some dummy data
        estimator.record(100, 5.0, "voxcpm2", segment_count=1)
        estimator.record(200, 8.0, "voxcpm2", segment_count=1)
        
        # Test estimation
        est_time = estimator.estimate(150, segment_count=1)
        assert est_time is not None, "Estimation should not be None"
        assert est_time > 0, "Estimation should be positive"
        
        print(f"  [OK] GenerationTimeEstimator: 150 chars -> {est_time:.1f}s")
        
        # Clean up
        os.unlink(temp_file)
    except Exception as e:
        print(f"  [FAIL] GenerationTimeEstimator: {e}")
        return False
    
    # Test HistoryDB
    try:
        from history_db import HistoryDatabase, create_history_db
        import tempfile
        
        with tempfile.TemporaryDirectory() as temp_dir:
            db = create_history_db(temp_dir)
            
            # Insert a record
            record = {
                "filename": "test.wav",
                "filepath": "/test/test.wav",
                "created_at": "2024-01-01T00:00:00",
                "file_size_bytes": 1024,
                "duration_seconds": 5.5,
                "text_preview": "Hello world",
                "engine": "voxcpm2",
                "model_type": "声音设计",
                "model_size": "VoxCPM2",
                "persona_name": None,
                "output_format": "wav",
                "is_success": True,
                "error_msg": None,
            }
            
            db.insert(record)
            
            # Query records
            records = db.query(limit=10)
            assert len(records) == 1, f"Should have 1 record, got {len(records)}"
            assert records[0]["filename"] == "test.wav"
            
            print("  [OK] HistoryDB: Insert and query work correctly")
    except Exception as e:
        print(f"  [FAIL] HistoryDB: {e}")
        return False
    
    # Test PersonaMetadata
    try:
        from persona_metadata import PersonaMetadata
        
        meta = PersonaMetadata(
            name="Test Voice",
            description="A test voice",
            tags=["female", "young"],
            category="Custom",
            voice_type="Sweet",
            traits="Clear and bright",
        )
        
        # Test serialization
        data = meta.to_dict()
        assert data["name"] == "Test Voice"
        assert "female" in data["tags"]
        
        # Test deserialization
        meta2 = PersonaMetadata.from_dict(data)
        assert meta2.name == meta.name
        assert meta2.description == meta.description
        assert meta2.tags == meta.tags
        
        print("  [OK] PersonaMetadata: Serialization/deserialization works")
    except Exception as e:
        print(f"  [FAIL] PersonaMetadata: {e}")
        return False
    
    print("All basic functionality tests passed!")
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("TTS MultiModel - Integration Test Suite")
    print("=" * 50)
    
    success = True
    
    # Test imports
    if not test_module_imports():
        success = False
    
    # Test functionality (only if imports passed)
    if success and not test_basic_functionality():
        success = False
    
    print("\n" + "=" * 50)
    if success:
        print("All tests passed!")
    else:
        print("Some tests failed!")
    print("=" * 50)
    
    sys.exit(0 if success else 1)