# -*- coding: utf-8 -*-
"""Audio post-processing: enhancement, normalization, tempo adjustment,
effects processing, silence trimming, and noise suppression."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger("tts_multimodel")

# ---------------------------------------------------------------------------
# Optional dependency: pyloudnorm (LUFS measurement / normalization)
# ---------------------------------------------------------------------------
try:
    import pyloudnorm as _pyloudnorm

    _HAS_PYLOUDNORM = True
except ImportError:
    _pyloudnorm = None  # type: ignore[assignment]
    _HAS_PYLOUDNORM = False

# ---------------------------------------------------------------------------
# Optional dependency: pedalboard (audio effects)
# ---------------------------------------------------------------------------
try:
    import pedalboard as _pedalboard

    _HAS_PEDALBOARD = True
except ImportError:
    _pedalboard = None  # type: ignore[assignment]
    _HAS_PEDALBOARD = False

# ---------------------------------------------------------------------------
# Optional dependency: noisereduce (noise suppression fallback)
# ---------------------------------------------------------------------------
try:
    import noisereduce as _noisereduce

    _HAS_NOISEREDUCE = True
except ImportError:
    _noisereduce = None  # type: ignore[assignment]
    _HAS_NOISEREDUCE = False


# ======================================================================
# 1. Loudness normalization
# ======================================================================

# Common LUFS targets
LUFS_SPEECH: float = -16.0      # Default for speech content
LUFS_CHATTERBOX: float = -27.0   # Chatterbox standard
LUFS_PODCAST: float = -16.0      # Podcast standard
LUFS_MUSIC: float = -14.0        # Typical music streaming


def _normalize_loudness_rms(
    audio: np.ndarray,
    sample_rate: int,
    target_lufs: float,
) -> np.ndarray:
    """RMS-based loudness normalization (fallback when pyloudnorm unavailable).

    Uses RMS energy as a rough approximation of perceived loudness.
    """
    if audio.size == 0:
        return audio

    rms = np.sqrt(np.mean(audio ** 2))
    if rms < 1e-10:
        return audio  # Silence – skip normalization

    current_loudness = 20 * np.log10(rms)
    gain_db = target_lufs - current_loudness
    gain_linear = 10 ** (gain_db / 20.0)

    normalized = audio * gain_linear

    # Soft clipping protection
    max_val = np.max(np.abs(normalized))
    if max_val > 0.99:
        normalized = normalized / max_val * 0.95

    return normalized.astype(np.float32)


def _normalize_loudness_lufs(
    audio: np.ndarray,
    sample_rate: int,
    target_lufs: float,
) -> np.ndarray:
    """Accurate LUFS normalization using pyloudnorm."""
    if audio.size == 0:
        return audio

    # pyloudnorm expects float input; ensure correct shape
    meter = _pyloudnorm.Meter(sample_rate)  # type: ignore[union-attr]
    try:
        current_loudness = meter.integrated_loudness(audio)
    except Exception as exc:
        logger.warning("pyloudnorm loudness measurement failed (%s), falling back to RMS", exc)
        return _normalize_loudness_rms(audio, sample_rate, target_lufs)

    # Silence / very low signal – pyloudnorm may return -inf
    if not np.isfinite(current_loudness) or current_loudness < -70.0:
        return audio

    try:
        normalized = _pyloudnorm.normalize.loudness(audio, current_loudness, target_lufs)  # type: ignore[union-attr]
    except Exception as exc:
        logger.warning("pyloudnorm normalization failed (%s), falling back to RMS", exc)
        return _normalize_loudness_rms(audio, sample_rate, target_lufs)

    # Final clipping guard
    max_val = np.max(np.abs(normalized))
    if max_val > 0.99:
        normalized = normalized / max_val * 0.95

    return normalized.astype(np.float32)


def normalize_loudness(
    audio: np.ndarray,
    sample_rate: int = 24000,
    target_lufs: float = -16.0,
    method: str = "auto",
) -> np.ndarray:
    """Normalize audio to target loudness.

    Args:
        audio: Input audio array (float32, -1 to 1).
        sample_rate: Sample rate in Hz.
        target_lufs: Target loudness in LUFS.  Common values:
            -16.0 (speech/podcast, default),
            -27.0 (Chatterbox standard),
            -14.0 (music streaming).
        method: Normalization method — ``"lufs"`` (pyloudnorm),
            ``"rms"`` (RMS approximation), or ``"auto"`` (try lufs,
            fall back to rms when pyloudnorm is not installed).

    Returns:
        Normalized audio array (float32).
    """
    if method == "lufs":
        if not _HAS_PYLOUDNORM:
            logger.warning(
                "pyloudnorm not installed; method='lufs' unavailable. "
                "Falling back to RMS normalization. "
                "Install pyloudnorm for accurate LUFS: pip install pyloudnorm"
            )
            return _normalize_loudness_rms(audio, sample_rate, target_lufs)
        return _normalize_loudness_lufs(audio, sample_rate, target_lufs)

    if method == "rms":
        return _normalize_loudness_rms(audio, sample_rate, target_lufs)

    # method == "auto"
    if _HAS_PYLOUDNORM:
        return _normalize_loudness_lufs(audio, sample_rate, target_lufs)
    return _normalize_loudness_rms(audio, sample_rate, target_lufs)


# ======================================================================
# 2. Tempo adjustment
# ======================================================================


def adjust_tempo(audio: np.ndarray, sample_rate: int, factor: float) -> tuple[np.ndarray, int]:
    """Adjust audio tempo without changing pitch.

    Uses simple resampling approach (changes pitch slightly).
    For pitch-preserving tempo change, would need phase vocoder or WSOLA.

    Args:
        audio: Input audio array.
        sample_rate: Original sample rate.
        factor: Tempo factor (>1 = faster, <1 = slower).

    Returns:
        (adjusted_audio, new_sample_rate)
    """
    if factor <= 0 or factor == 1.0:
        return audio, sample_rate

    new_length = int(len(audio) / factor)
    indices = np.linspace(0, len(audio) - 1, new_length).astype(int)
    adjusted = audio[indices]

    return adjusted.astype(np.float32), sample_rate


# ======================================================================
# 3. Voice enhancement (built-in, no external deps)
# ======================================================================


def apply_voice_enhancement(audio: np.ndarray, sample_rate: int = 24000) -> np.ndarray:
    """Apply voice-specific enhancement: gentle EQ + compression.

    Args:
        audio: Input audio array.
        sample_rate: Sample rate in Hz.

    Returns:
        Enhanced audio array.
    """
    if audio.size == 0:
        return audio

    from scipy.signal import butter, lfilter

    nyquist = sample_rate / 2.0
    cutoff = 80.0 / nyquist
    b, a = butter(2, cutoff, btype="high", analog=False)
    enhanced = lfilter(b, a, audio)

    # Gentle compression
    threshold = 0.3
    ratio = 4.0
    compressed = np.zeros_like(enhanced)
    abs_signal = np.abs(enhanced)
    above_threshold = abs_signal > threshold

    compressed[~above_threshold] = enhanced[~above_threshold]
    if np.any(above_threshold):
        gain = threshold + (abs_signal[above_threshold] - threshold) / ratio
        compressed[above_threshold] = np.sign(enhanced[above_threshold]) * gain

    # Normalize to -3dB peak
    peak = np.max(np.abs(compressed))
    if peak > 0:
        compressed = compressed / peak * 0.708  # -3dB

    return compressed.astype(np.float32)


# ======================================================================
# 4. Pedalboard audio effects
# ======================================================================

# Preset definitions: each maps to a list of (Pedalboard_class, kwargs)
_EFFECT_PRESETS: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "warm": [
        ("Reverb", {"room_size": 0.4, "damping": 0.6, "wet_level": 0.15, "dry_level": 0.85}),
        ("Gain", {"gain_db": 2.0}),
        ("LowShelfFilter", {"cutoff_frequency_hz": 200, "gain_db": 3.0}),
    ],
    "bright": [
        ("HighShelfFilter", {"cutoff_frequency_hz": 4000, "gain_db": 4.0}),
        ("HighpassFilter", {"cutoff_frequency_hz": 100}),
        ("Gain", {"gain_db": 1.0}),
    ],
    "radio": [
        ("HighpassFilter", {"cutoff_frequency_hz": 300}),
        ("LowpassFilter", {"cutoff_frequency_hz": 3000}),
        ("Compressor", {"threshold_db": -20, "ratio": 5.0, "attack_ms": 5.0, "release_ms": 50.0}),
        ("Gain", {"gain_db": 3.0}),
    ],
    "cinematic": [
        ("Reverb", {"room_size": 0.8, "damping": 0.4, "wet_level": 0.3, "dry_level": 0.7}),
        ("Compressor", {"threshold_db": -18, "ratio": 3.0, "attack_ms": 10.0, "release_ms": 100.0}),
        ("LowShelfFilter", {"cutoff_frequency_hz": 150, "gain_db": 2.0}),
        ("Gain", {"gain_db": 1.5}),
    ],
}


class AudioEffectsProcessor:
    """Chainable audio effects processor powered by Spotify Pedalboard.

    If ``pedalboard`` is not installed, all processing methods return the
    input unchanged and emit a warning on first use.

    Usage::

        proc = AudioEffectsProcessor(sample_rate=24000)
        result = proc.apply(audio, effects=["reverb", "gain"], reverb_room_size=0.5)
        result = proc.apply_preset(audio, "warm")
    """

    _warned_no_pedalboard: bool = False

    def __init__(self, sample_rate: int = 24000) -> None:
        self.sample_rate = sample_rate
        self._board: list[Any] = []  # populated per apply() call

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _warn_stub(cls) -> None:
        if not cls._warned_no_pedalboard:
            logger.warning(
                "pedalboard is not installed; audio effects will be no-ops. "
                "Install pedalboard for audio effects: pip install pedalboard"
            )
            cls._warned_no_pedalboard = True

    def _build_effect(self, name: str, **kwargs: Any) -> Any | None:
        """Instantiate a single pedalboard effect by name."""
        if not _HAS_PEDALBOARD:
            return None

        effect_map: dict[str, type] = {
            "pitch_shift": _pedalboard.PitchShift,
            "reverb": _pedalboard.Reverb,
            "delay": _pedalboard.Delay,
            "chorus": _pedalboard.Chorus,
            "compression": _pedalboard.Compressor,
            "compressor": _pedalboard.Compressor,
            "gain": _pedalboard.Gain,
            "highpass": _pedalboard.HighpassFilter,
            "highpass_filter": _pedalboard.HighpassFilter,
            "lowpass": _pedalboard.LowpassFilter,
            "lowpass_filter": _pedalboard.LowpassFilter,
        }

        cls = effect_map.get(name)
        if cls is None:
            logger.warning("Unknown pedalboard effect: %s (skipped)", name)
            return None

        try:
            return cls(**kwargs)
        except Exception as exc:
            logger.warning("Failed to create effect %s(%s): %s", name, kwargs, exc)
            return None

    def _build_preset(self, preset_name: str) -> list[Any]:
        """Build a Pedalboard chain from a preset definition."""
        if not _HAS_PEDALBOARD:
            return []

        spec_list = _EFFECT_PRESETS.get(preset_name)
        if spec_list is None:
            logger.warning("Unknown preset: %s", preset_name)
            return []

        effects: list[Any] = []
        for effect_name, effect_kwargs in spec_list:
            # Resolve special names that don't map 1:1 to pedalboard classes
            if effect_name == "LowShelfFilter":
                try:
                    effects.append(_pedalboard.LowShelfFilter(**effect_kwargs))
                except Exception as exc:
                    logger.warning("Failed to create %s: %s", effect_name, exc)
            elif effect_name == "HighShelfFilter":
                try:
                    effects.append(_pedalboard.HighShelfFilter(**effect_kwargs))
                except Exception as exc:
                    logger.warning("Failed to create %s: %s", effect_name, exc)
            else:
                eff = self._build_effect(effect_name.lower(), **effect_kwargs)
                if eff is not None:
                    effects.append(eff)

        return effects

    def _process_with_board(self, audio: np.ndarray, effects: list[Any]) -> np.ndarray:
        """Run audio through a Pedalboard instance."""
        if not effects or not _HAS_PEDALBOARD:
            return audio

        board = _pedalboard.Pedalboard(effects)
        # pedalboard expects (channels, samples) for 2-D or (samples,) for 1-D
        if audio.ndim == 1:
            result = board(audio, self.sample_rate)
        else:
            result = board(audio, self.sample_rate)

        return result.astype(np.float32)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(
        self,
        audio: np.ndarray,
        effects: list[str] | None = None,
        *,
        pitch_shift_semitones: int = 0,
        reverb_room_size: float = 0.5,
        reverb_damping: float = 0.5,
        reverb_wet_level: float = 0.2,
        reverb_dry_level: float = 0.8,
        delay_delay_seconds: float = 0.3,
        delay_feedback: float = 0.3,
        delay_mix: float = 0.3,
        chorus_rate_hz: float = 1.5,
        chorus_depth: float = 0.25,
        chorus_mix: float = 0.5,
        compression_threshold_db: float = -20.0,
        compression_ratio: float = 4.0,
        compression_attack_ms: float = 10.0,
        compression_release_ms: float = 100.0,
        gain_db: float = 0.0,
        highpass_cutoff_hz: float | None = None,
        lowpass_cutoff_hz: float | None = None,
    ) -> np.ndarray:
        """Apply a chain of named effects with keyword parameters.

        Args:
            audio: Input audio array (float32).
            effects: List of effect names to apply.  Supported:
                ``"pitch_shift"``, ``"reverb"``, ``"delay"``,
                ``"chorus"``, ``"compression"``, ``"gain"``,
                ``"highpass"``, ``"lowpass"``.
            pitch_shift_semitones: Semitones to shift pitch.
            reverb_room_size / reverb_damping / reverb_wet_level / reverb_dry_level:
                Reverb parameters.
            delay_delay_seconds / delay_feedback / delay_mix:
                Delay parameters.
            chorus_rate_hz / chorus_depth / chorus_mix:
                Chorus parameters.
            compression_threshold_db / compression_ratio / compression_attack_ms / compression_release_ms:
                Compressor parameters.
            gain_db: Gain in dB.
            highpass_cutoff_hz: High-pass filter cutoff.  ``None`` = skip.
            lowpass_cutoff_hz: Low-pass filter cutoff.  ``None`` = skip.

        Returns:
            Processed audio (float32).
        """
        if not _HAS_PEDALBOARD:
            self._warn_stub()
            return audio

        if not effects:
            return audio

        effect_instances: list[Any] = []

        for name in effects:
            if name == "pitch_shift" and pitch_shift_semitones != 0:
                effect_instances.append(
                    self._build_effect("pitch_shift", semitones=pitch_shift_semitones)
                )
            elif name == "reverb":
                effect_instances.append(
                    self._build_effect(
                        "reverb",
                        room_size=reverb_room_size,
                        damping=reverb_damping,
                        wet_level=reverb_wet_level,
                        dry_level=reverb_dry_level,
                    )
                )
            elif name == "delay":
                effect_instances.append(
                    self._build_effect(
                        "delay",
                        delay_seconds=delay_delay_seconds,
                        feedback=delay_feedback,
                        mix=delay_mix,
                    )
                )
            elif name == "chorus":
                effect_instances.append(
                    self._build_effect(
                        "chorus",
                        rate_hz=chorus_rate_hz,
                        depth=chorus_depth,
                        mix=chorus_mix,
                    )
                )
            elif name in ("compression", "compressor"):
                effect_instances.append(
                    self._build_effect(
                        "compression",
                        threshold_db=compression_threshold_db,
                        ratio=compression_ratio,
                        attack_ms=compression_attack_ms,
                        release_ms=compression_release_ms,
                    )
                )
            elif name == "gain" and gain_db != 0.0:
                effect_instances.append(
                    self._build_effect("gain", gain_db=gain_db)
                )
            elif name == "highpass" and highpass_cutoff_hz is not None:
                effect_instances.append(
                    self._build_effect("highpass", cutoff_frequency_hz=highpass_cutoff_hz)
                )
            elif name == "lowpass" and lowpass_cutoff_hz is not None:
                effect_instances.append(
                    self._build_effect("lowpass", cutoff_frequency_hz=lowpass_cutoff_hz)
                )
            else:
                logger.debug("Effect %s skipped (no parameters or unknown)", name)

        # Filter out None entries (failed constructions)
        effect_instances = [e for e in effect_instances if e is not None]

        if not effect_instances:
            return audio

        return self._process_with_board(audio, effect_instances)

    def apply_preset(self, audio: np.ndarray, preset: str) -> np.ndarray:
        """Apply a named effect preset.

        Available presets: ``"warm"``, ``"bright"``, ``"radio"``,
        ``"cinematic"``.

        Args:
            audio: Input audio array (float32).
            preset: Preset name.

        Returns:
            Processed audio (float32).
        """
        if not _HAS_PEDALBOARD:
            self._warn_stub()
            return audio

        effects = self._build_preset(preset)
        if not effects:
            return audio

        return self._process_with_board(audio, effects)

    @staticmethod
    def available_presets() -> list[str]:
        """Return list of available preset names."""
        return list(_EFFECT_PRESETS.keys())

    @staticmethod
    def is_available() -> bool:
        """Return ``True`` if pedalboard is installed and effects work."""
        return _HAS_PEDALBOARD


# ======================================================================
# 5. Silence trimming
# ======================================================================


def trim_tts_output(
    audio: np.ndarray,
    sample_rate: int = 24000,
    threshold_db: float = -40.0,
    padding_ms: int = 50,
    pop_threshold_db: float = -3.0,
) -> np.ndarray:
    """Auto-trim leading/trailing silence and anomalous pops from TTS output.

    Uses energy-based detection to find the first and last non-silent
    samples, then adds a small padding to avoid cutting consonants.
    Also detects and trims anomalous loud segments (pops) at the very
    start or end.

    Args:
        audio: Input audio array (float32, -1 to 1).
        sample_rate: Sample rate in Hz.
        threshold_db: Silence threshold in dB (default -40 dB).
        padding_ms: Padding in milliseconds to keep before/after
            detected speech boundaries (default 50 ms).
        pop_threshold_db: Threshold in dB above which a sample at the
            very start/end is considered a pop (default -3 dB).

    Returns:
        Trimmed audio array (float32).
    """
    if audio.size == 0:
        return audio

    threshold_linear = 10 ** (threshold_db / 20.0)
    pop_linear = 10 ** (pop_threshold_db / 20.0)
    padding_samples = int(sample_rate * padding_ms / 1000.0)

    # --- Detect and remove leading pops ---
    # A pop is a very loud transient in the first few milliseconds.
    pop_scan_end = min(sample_rate // 20, audio.size)  # first 50 ms
    leading_pop_end = 0
    for i in range(pop_scan_end):
        if np.abs(audio[i]) > pop_linear:
            # Found a pop — scan forward until signal drops below pop level
            j = i + 1
            while j < pop_scan_end and np.abs(audio[j]) > pop_linear:
                j += 1
            # Skip a small window after the pop decays
            j = min(j + padding_samples, pop_scan_end)
            leading_pop_end = max(leading_pop_end, j)

    # --- Detect and remove trailing pops ---
    pop_scan_start = max(audio.size - sample_rate // 20, 0)  # last 50 ms
    trailing_pop_start = audio.size
    for i in range(audio.size - 1, pop_scan_start - 1, -1):
        if np.abs(audio[i]) > pop_linear:
            j = i - 1
            while j > pop_scan_start and np.abs(audio[j]) > pop_linear:
                j -= 1
            j = max(j - padding_samples, pop_scan_start)
            trailing_pop_start = min(trailing_pop_start, j)

    # Apply pop trimming first
    trimmed = audio[leading_pop_end:trailing_pop_start]

    if trimmed.size == 0:
        return audio  # Everything was a pop — return original

    # --- Energy-based silence trimming ---
    abs_audio = np.abs(trimmed)
    above_threshold = abs_audio > threshold_linear

    if not np.any(above_threshold):
        # Entirely below threshold — return original (might be very quiet speech)
        return audio

    first_speech = int(np.argmax(above_threshold))
    last_speech = int(len(above_threshold) - 1 - np.argmax(above_threshold[::-1]))

    # Add padding, clamped to array bounds
    start = max(0, first_speech - padding_samples)
    end = min(len(trimmed), last_speech + padding_samples + 1)

    result = trimmed[start:end]

    return result.astype(np.float32)


# ======================================================================
# 6. Noise suppression / denoising
# ======================================================================


def denoise_audio(
    audio: np.ndarray,
    sample_rate: int = 24000,
    *,
    prop_decrease: float = 1.0,
    use_enhancer: bool = True,
) -> np.ndarray:
    """Denoise audio using available noise suppression methods.

    Priority:
        1. ZipEnhancer model (if loaded in ``registry.voxcpm_enhancer_model``)
        2. ``noisereduce`` library (if installed)
        3. Return audio unchanged with warning

    Args:
        audio: Input audio array (float32, -1 to 1).
        sample_rate: Sample rate in Hz.
        prop_decrease: Proportion of noise to remove (0.0 – 1.0).
            Only applies to noisereduce.  Default 1.0 (full suppression).
        use_enhancer: Whether to attempt ZipEnhancer model first.
            Default ``True``.

    Returns:
        Denoised audio array (float32).
    """
    if audio.size == 0:
        return audio

    # --- 1. Try ZipEnhancer model from registry ---
    if use_enhancer:
        try:
            from .model_registry import registry

            enhancer = registry.voxcpm_enhancer_model
            if enhancer is not None:
                logger.debug("Using ZipEnhancer model for denoising")
                try:
                    # ZipEnhancer typically expects (batch, channels, samples)
                    # or (channels, samples).  Adapt based on what the model
                    # exposes; common interface is model(audio, sample_rate).
                    # We attempt the most common calling convention and fall
                    # back gracefully.
                    if hasattr(enhancer, "denoise"):
                        result = enhancer.denoise(audio, sample_rate)
                    elif callable(enhancer):
                        result = enhancer(audio, sample_rate)
                    else:
                        logger.warning(
                            "ZipEnhancer model loaded but has no callable interface; skipping"
                        )
                        result = None

                    if result is not None:
                        if isinstance(result, np.ndarray):
                            return result.astype(np.float32)
                        # torch tensor
                        if hasattr(result, "cpu"):
                            return result.cpu().numpy().astype(np.float32)
                        return np.asarray(result, dtype=np.float32)
                except Exception as exc:
                    logger.warning("ZipEnhancer denoising failed: %s", exc)
        except ImportError:
            pass

    # --- 2. Try noisereduce library ---
    if _HAS_NOISEREDUCE:
        logger.debug("Using noisereduce library for denoising")
        try:
            # noisereduce.reduce_noise operates on 1-D or 2-D arrays
            result = _noisereduce.reduce_noise(
                y=audio,
                sr=sample_rate,
                prop_decrease=prop_decrease,
                stationary=False,
            )
            return result.astype(np.float32)
        except Exception as exc:
            logger.warning("noisereduce failed: %s", exc)

    # --- 3. Fallback: return unchanged ---
    logger.warning(
        "No noise suppression available (neither ZipEnhancer model loaded "
        "nor noisereduce installed). Returning audio unchanged. "
        "Install noisereduce for basic denoising: pip install noisereduce"
    )
    return audio


# ======================================================================
# 7. Master enhance_audio pipeline
# ======================================================================


def enhance_audio(
    audio: np.ndarray,
    sample_rate: int,
    normalize: bool = True,
    tempo_factor: float = 1.0,
    voice_enhancement: bool = False,
    target_lufs: float = -16.0,
    method: str = "auto",
    trim_silence: bool = False,
    denoise: bool = False,
    effects_preset: str | None = None,
) -> np.ndarray:
    """Apply all post-processing steps in sequence.

    Processing order:
        1. Denoise (if enabled)
        2. Voice enhancement (EQ + compression, if enabled)
        3. Loudness normalization
        4. Silence trimming (if enabled)
        5. Effects preset (if specified)
        6. Tempo adjustment

    Args:
        audio: Input audio array.
        sample_rate: Sample rate in Hz.
        normalize: Whether to apply loudness normalization.
        tempo_factor: Tempo adjustment factor (1.0 = no change).
        voice_enhancement: Whether to apply voice enhancement (EQ + compression).
        target_lufs: Target loudness in LUFS for normalization (default -16.0).
        method: Normalization method — ``"auto"``, ``"lufs"``, or ``"rms"``.
        trim_silence: Whether to auto-trim leading/trailing silence.
        denoise: Whether to apply noise suppression.
        effects_preset: Pedalboard effects preset name (e.g. ``"warm"``).

    Returns:
        Processed audio array.
    """
    result = audio.copy()

    if denoise:
        result = denoise_audio(result, sample_rate)

    if voice_enhancement:
        result = apply_voice_enhancement(result, sample_rate)

    if normalize:
        result = normalize_loudness(result, sample_rate, target_lufs, method=method)

    if trim_silence:
        result = trim_tts_output(result, sample_rate)

    if effects_preset is not None:
        proc = AudioEffectsProcessor(sample_rate=sample_rate)
        result = proc.apply_preset(result, effects_preset)

    if tempo_factor != 1.0:
        result, _ = adjust_tempo(result, sample_rate, tempo_factor)

    return result
