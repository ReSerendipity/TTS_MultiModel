# -*- coding: utf-8 -*-
"""
多GPU支持验证脚本

用于验证改造后的代码是否正确支持多种GPU后端。
运行此脚本以检查当前环境的GPU支持情况。
"""

import sys
import torch

print("=" * 60)
print("TTS_MultiModel 多GPU支持验证")
print("=" * 60)
print()

# 检查PyTorch版本
print(f"PyTorch 版本: {torch.__version__}")
print()

# 1. 检查 CUDA 支持
print("--- CUDA 检查 ---")
if torch.cuda.is_available():
    print(f"✅ CUDA 可用")
    print(f"   CUDA 版本: {torch.version.cuda}")
    print(f"   GPU 数量: {torch.cuda.device_count()}")
    
    for i in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(i)
        name = props.name
        vram_gb = props.total_memory / (1024**3)
        print(f"   GPU {i}: {name} (VRAM: {vram_gb:.1f} GB)")
        
        # 检测品牌
        name_lower = name.lower()
        if any(k in name_lower for k in ["nvidia", "geforce", "rtx", "gtx", "quadro", "tesla"]):
            print(f"   品牌: NVIDIA")
        elif any(k in name_lower for k in ["amd", "radeon", "rx ", "vega", "navi", "gfx"]):
            print(f"   品牌: AMD (ROCM)")
else:
    print("❌ CUDA 不可用")
print()

# 2. 检查 Intel XPU 支持
print("--- Intel XPU 检查 ---")
try:
    import intel_extension_for_pytorch as ipex
    if hasattr(ipex, 'xpu') and ipex.xpu.is_available():
        print(f"✅ Intel XPU 可用")
        print(f"   XPU 设备数量: {ipex.xpu.device_count()}")
        
        for i in range(ipex.xpu.device_count()):
            props = ipex.xpu.get_device_properties(i)
            name = props.get('name', f'Intel XPU {i}')
            vram_gb = props.get('total_memory', 0) / (1024**3)
            print(f"   XPU {i}: {name} (VRAM: {vram_gb:.1f} GB)")
    else:
        print("❌ Intel XPU 不可用")
except ImportError:
    print("❌ intel-extension-for-pytorch 未安装")
print()

# 3. 检查 Apple MPS 支持
print("--- Apple MPS 检查 ---")
try:
    if torch.backends.mps.is_available():
        print(f"✅ Apple MPS 可用")
        print(f"   设备: Apple Silicon (Metal)")
    else:
        print("❌ Apple MPS 不可用")
except Exception as e:
    print(f"❌ Apple MPS 检查失败: {e}")
print()

# 4. 导入项目GPU后端管理器
print("--- 项目GPU后端管理器 ---")
try:
    sys.path.insert(0, r"c:\Users\HONOR\Documents\TTS_MultiModel\bin\integrated_app")
    from gpu_backend import GPUBackendManager, GPUBackend
    
    backend = GPUBackendManager.detect_backend()
    print(f"✅ 检测到后端: {backend.value.upper()}")
    
    is_available = GPUBackendManager.is_available()
    print(f"✅ GPU 可用: {is_available}")
    
    if is_available:
        device = GPUBackendManager.get_device()
        device_name = GPUBackendManager.get_device_name()
        device_count = GPUBackendManager.get_device_count()
        
        print(f"   设备: {device}")
        print(f"   名称: {device_name}")
        print(f"   数量: {device_count}")
        
        # 显存信息
        mem_info = GPUBackendManager.get_memory_info()
        total_gb = mem_info[0] / (1024**3)
        allocated_gb = mem_info[1] / (1024**3)
        free_gb = mem_info[3] / (1024**3)
        
        print(f"   总显存: {total_gb:.2f} GB")
        print(f"   已分配: {allocated_gb:.2f} GB")
        print(f"   可用: {free_gb:.2f} GB")
        
        # 检查是否满足VoxCPM2需求
        needed_gb = 6.5
        if free_gb >= needed_gb:
            print(f"   ✅ 满足 VoxCPM2 需求 (需要 {needed_gb} GB)")
        else:
            print(f"   ⚠️  可能不满足 VoxCPM2 需求 (需要 {needed_gb} GB, 可用 {free_gb:.2f} GB)")
    else:
        print("⚠️  使用CPU模式")
except Exception as e:
    print(f"❌ 项目GPU后端管理器导入失败: {e}")
    import traceback
    traceback.print_exc()
print()

print("=" * 60)
print("验证完成")
print("=" * 60)
