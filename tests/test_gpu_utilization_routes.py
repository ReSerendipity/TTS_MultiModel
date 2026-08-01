# -*- coding: utf-8 -*-
"""Test script for GPU utilization monitoring in system.py.

Tests:
1. NVML initialization and handle caching
2. GPU utilization retrieval with fallback
3. Thread-safety of NVML state
4. nvidia-smi fallback method
5. Error handling and logging
"""

import sys
import os
import time
import threading
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_gpu_util")

# Add bin directory to path
_BIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

def test_imports():
    """Test that all required imports work."""
    logger.info("=" * 60)
    logger.info("Test 1: Testing imports...")
    try:
        from integrated_app.routes.system.gpu import (
            _get_nvml_handle,
            _get_gpu_utilization,
            _get_gpu_utilization_from_nvml,
            _get_gpu_utilization_from_nvidia_smi,
            _nvml_state,
            _nvml_lock
        )
        logger.info("All imports successful")
        return True
    except Exception as e:
        logger.error(f"Import failed: {e}")
        return False

def test_nvml_initialization():
    """Test NVML initialization and handle caching."""
    logger.info("=" * 60)
    logger.info("Test 2: Testing NVML initialization...")
    try:
        from integrated_app.routes.system.gpu import _get_nvml_handle, _nvml_state

        # First call should initialize NVML
        handle1 = _get_nvml_handle()
        if handle1 is not None:
            logger.info(f"NVML initialized, handle: {handle1}")
            logger.info(f"   Device index: {_nvml_state['device_index']}")
            logger.info(f"   Init time: {_nvml_state['init_time']}")
        else:
            logger.warning("NVML handle is None (may not have NVIDIA GPU or pynvml not installed)")
            if _nvml_state['last_error']:
                logger.warning(f"   Last error: {_nvml_state['last_error']}")

        # Second call should return cached handle
        handle2 = _get_nvml_handle()
        if handle2 is not None and handle1 is not None:
            if handle1 == handle2:
                logger.info("Handle caching works correctly")
            else:
                logger.error("Handle caching failed - different handles returned")
                return False

        return True
    except Exception as e:
        logger.error(f"NVML initialization test failed: {e}", exc_info=True)
        return False

def test_gpu_utilization_nvml():
    """Test GPU utilization from NVML."""
    logger.info("=" * 60)
    logger.info("Test 3: Testing GPU utilization from NVML...")
    try:
        from integrated_app.routes.system.gpu import _get_gpu_utilization_from_nvml

        util = _get_gpu_utilization_from_nvml()
        if util is not None:
            logger.info(f"GPU utilization from NVML: {util}%")
            if 0 <= util <= 100:
                logger.info("Utilization value is in valid range (0-100)")
            else:
                logger.warning(f"Utilization value out of range: {util}")
            return True
        else:
            logger.warning("NVML utilization returned None")
            return False
    except Exception as e:
        logger.error(f"NVML utilization test failed: {e}", exc_info=True)
        return False

def test_gpu_utilization_nvidia_smi():
    """Test GPU utilization from nvidia-smi fallback."""
    logger.info("=" * 60)
    logger.info("Test 4: Testing GPU utilization from nvidia-smi...")
    try:
        from integrated_app.routes.system.gpu import _get_gpu_utilization_from_nvidia_smi

        util = _get_gpu_utilization_from_nvidia_smi()
        if util is not None:
            logger.info(f"GPU utilization from nvidia-smi: {util}%")
            if 0 <= util <= 100:
                logger.info("Utilization value is in valid range (0-100)")
            else:
                logger.warning(f"Utilization value out of range: {util}")
            return True
        else:
            logger.info("nvidia-smi utilization returned None (may not be available)")
            return True  # Not a failure, just unavailable
    except Exception as e:
        logger.error(f"nvidia-smi utilization test failed: {e}", exc_info=True)
        return False

def test_gpu_utilization_unified():
    """Test unified GPU utilization function."""
    logger.info("=" * 60)
    logger.info("Test 5: Testing unified GPU utilization function...")
    try:
        from integrated_app.routes.system.gpu import _get_gpu_utilization

        # Test multiple calls to ensure consistency and caching
        utils = []
        for i in range(3):
            util = _get_gpu_utilization()
            utils.append(util)
            logger.info(f"   Call {i+1}: GPU utilization = {util}%")
            time.sleep(0.5)

        logger.info(f"All calls returned valid values")
        logger.info(f"   Values: {utils}")

        # Values should be in valid range
        for util in utils:
            if not (0 <= util <= 100):
                logger.error(f"Utilization value out of range: {util}")
                return False

        return True
    except Exception as e:
        logger.error(f"Unified utilization test failed: {e}", exc_info=True)
        return False

def test_thread_safety():
    """Test thread-safety of NVML initialization."""
    logger.info("=" * 60)
    logger.info("Test 6: Testing thread-safety...")
    try:
        from integrated_app.routes.system.gpu import _get_nvml_handle, _nvml_state

        handles = []
        errors = []

        def get_handle_in_thread():
            try:
                h = _get_nvml_handle()
                handles.append(h)
            except Exception as e:
                errors.append(str(e))

        # Create multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=get_handle_in_thread)
            threads.append(t)

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        if errors:
            logger.error(f"Thread errors: {errors}")
            return False

        # All handles should be the same (cached)
        valid_handles = [h for h in handles if h is not None]
        if len(valid_handles) > 0:
            first_handle = valid_handles[0]
            all_same = all(h == first_handle for h in valid_handles)
            if all_same:
                logger.info(f"All threads got the same cached handle")
                logger.info(f"   Total threads: {len(handles)}")
                logger.info(f"   Valid handles: {len(valid_handles)}")
                return True
            else:
                logger.error("Different threads got different handles")
                return False
        else:
            logger.warning("No valid handles obtained (NVML may not be available)")
            return True
    except Exception as e:
        logger.error(f"Thread-safety test failed: {e}", exc_info=True)
        return False

def test_error_handling():
    """Test error handling and recovery."""
    logger.info("=" * 60)
    logger.info("Test 7: Testing error handling...")
    try:
        from integrated_app.routes.system.gpu import _nvml_state

        # Check that error state is properly tracked
        logger.info(f"   NVML state: initialized={_nvml_state['initialized']}")
        logger.info(f"   NVML state: init_failed={_nvml_state['init_failed']}")
        logger.info(f"   NVML state: last_error={_nvml_state['last_error']}")
        logger.info(f"   NVML state: device_index={_nvml_state['device_index']}")

        # Verify state dictionary has all required fields
        required_fields = ['handle', 'initialized', 'init_time', 'init_failed',
                          'last_error', 'device_index']
        for field in required_fields:
            if field not in _nvml_state:
                logger.error(f"Missing field in _nvml_state: {field}")
                return False

        logger.info("All required state fields present")
        return True
    except Exception as e:
        logger.error(f"Error handling test failed: {e}", exc_info=True)
        return False

def main():
    """Run all tests."""
    logger.info("Starting GPU Utilization Monitoring Tests")
    logger.info("=" * 60)

    tests = [
        test_imports,
        test_nvml_initialization,
        test_gpu_utilization_nvml,
        test_gpu_utilization_nvidia_smi,
        test_gpu_utilization_unified,
        test_thread_safety,
        test_error_handling
    ]

    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append((test_func.__name__, result))
        except Exception as e:
            logger.error(f"Test {test_func.__name__} crashed: {e}", exc_info=True)
            results.append((test_func.__name__, False))

    # Summary
    logger.info("=" * 60)
    logger.info("Test Summary:")
    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "PASSED" if result else "FAILED"
        logger.info(f"  {status}: {name}")

    logger.info(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        logger.info("\nAll tests passed!")
        return 0
    else:
        logger.warning(f"\n{total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
