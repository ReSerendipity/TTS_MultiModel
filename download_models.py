"""
Model download script for TTS MultiModel project.
Run with: python download_models.py
Requires: pip install modelscope huggingface_hub
"""
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent

MODEL_LIST = [
    ("Qwen/Qwen3-TTS-12Hz-0.6B-Base", "models/Qwen3-TTS-12Hz-0.6B-Base"),
    ("Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice", "models/Qwen3-TTS-12Hz-0.6B-CustomVoice"),
    ("Qwen/Qwen3-TTS-12Hz-1.7B-Base", "models/Qwen3-TTS-12Hz-1.7B-Base"),
    ("Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", "models/Qwen3-TTS-12Hz-1.7B-CustomVoice"),
    ("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", "models/Qwen3-TTS-12Hz-1.7B-VoiceDesign"),
    ("FunAudioLLM/SenseVoiceSmall", "pretrained_models/SenseVoiceSmall"),
    ("openbmb/VoxCPM2", "pretrained_models/VoxCPM2"),
    ("modelscope/speech_zipenhancer_ans_multiloss_16k_base", "pretrained_models/speech_zipenhancer"),
]


def download_model(model_id, target_dir, method="auto"):
    full_path = PROJECT_DIR / target_dir

    safetensors = list(full_path.glob("*.safetensors"))
    bins = list(full_path.glob("*.bin"))
    if full_path.exists() and (safetensors or bins):
        print(f"[OK] {model_id} already exists, skipping")
        return True

    print(f"[Downloading] {model_id} -> {target_dir}")
    os.makedirs(full_path, exist_ok=True)

    if method in ("auto", "modelscope"):
        try:
            from modelscope import snapshot_download
            snapshot_download(model_id, local_dir=str(full_path))
            print(f"[Done] {model_id} via ModelScope")
            return True
        except ImportError:
            if method == "modelscope":
                print("[Error] modelscope not installed. Run: pip install modelscope")
                return False
        except Exception as e:
            print(f"[Warning] ModelScope failed: {e}")
            if method == "modelscope":
                return False

    if method in ("auto", "huggingface"):
        try:
            from huggingface_hub import snapshot_download as hf_download
            hf_download(repo_id=model_id, local_dir=str(full_path))
            print(f"[Done] {model_id} via HuggingFace")
            return True
        except ImportError:
            if method == "huggingface":
                print("[Error] huggingface_hub not installed. Run: pip install huggingface_hub")
                return False
        except Exception as e:
            print(f"[Error] HuggingFace download failed: {e}")
            return False

    return False


def main():
    print("=" * 60)
    print("TTS MultiModel - Model Downloader")
    print("=" * 60)

    if len(sys.argv) > 1:
        method = sys.argv[1]
    else:
        method = "auto"

    print(f"Download method: {method}")
    print()

    success = 0
    failed = 0

    for model_id, target_dir in MODEL_LIST:
        if download_model(model_id, target_dir, method):
            success += 1
        else:
            failed += 1
        print()

    print("=" * 60)
    print(f"Complete: {success} succeeded, {failed} failed")
    print("=" * 60)

    if failed > 0:
        print("\nFor manual download, use one of these commands:")
        print("  ModelScope: python -c \"from modelscope import snapshot_download; snapshot_download('MODEL_ID', local_dir='TARGET_DIR')\"")
        print("  HuggingFace: huggingface-cli download MODEL_ID --local-dir TARGET_DIR")
        sys.exit(1)


if __name__ == "__main__":
    main()
