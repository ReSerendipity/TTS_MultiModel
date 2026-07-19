"""
Training utilities for VoxCPM fine-tuning.

This package mirrors the training mechanics used in the minicpm-audio
tooling while relying solely on local audio-text datasets managed via
the HuggingFace ``datasets`` library.
"""

from .accelerator import Accelerator
from .data import (
    BatchProcessor,
    HFVoxCPMDataset,
    build_dataloader,
    load_audio_text_datasets,
)
from .state import TrainingState
from .tracker import TrainingTracker

__all__ = [
    "Accelerator",
    "TrainingTracker",
    "HFVoxCPMDataset",
    "BatchProcessor",
    "TrainingState",
    "load_audio_text_datasets",
    "build_dataloader",
]
