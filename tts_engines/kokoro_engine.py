# -*- coding: utf-8 -*-
"""
Kokoro TTS Engine

Wraps the Kokoro-82M TTS model for Chinese text-to-speech.
Maintains a single pipeline instance that is reused for all TTS calls.
"""
import gc
import io
from typing import List, Dict

import numpy as np
import soundfile as sf

from . import TTSEngine


class KokoroEngine(TTSEngine):
    """Kokoro TTS engine wrapper - maintains single pipeline instance.

    The pipeline is created lazily on first use and reused for all subsequent calls.
    Voice and speed parameters are passed per-call, so config changes don't require
    pipeline recreation.
    """

    # Available Chinese voices
    VOICES = [
        {'value': 'zm_yunjian', 'label': 'Chinese Male (云健)'},
        {'value': 'zf_xiaoxiao', 'label': 'Chinese Female (晓晓)'},
        {'value': 'zf_xiaoyi', 'label': 'Chinese Female (晓依)'},
        {'value': 'zm_yunxi', 'label': 'Chinese Male (云希)'},
    ]

    def __init__(self):
        """Initialize Kokoro engine with lazy pipeline creation."""
        self._pipeline = None  # Lazy initialization
        self._voice = 'zm_yunjian'
        self._speed_normal = 0.7
        self._speed_name = 0.6
        print("[KokoroEngine] Initialized (pipeline will be created on first use)")

    def _ensure_pipeline(self):
        """Create pipeline only once, reuse for all calls."""
        if self._pipeline is None:
            print("[KokoroEngine] Creating Kokoro pipeline (first use)...")
            from kokoro import KPipeline
            self._pipeline = KPipeline(lang_code='z', repo_id='hexgrad/Kokoro-82M')
            print("[KokoroEngine] Pipeline created successfully")

    def generate_audio(self, text: str, voice: str, speed: float) -> io.BytesIO:
        """Generate audio using EXISTING pipeline (no new pipeline creation).

        Args:
            text: Text to synthesize
            voice: Voice ID (e.g., 'zm_yunjian', 'zf_xiaoxiao')
            speed: Speed multiplier (0.3 - 2.0)

        Returns:
            BytesIO buffer containing WAV audio data at 24kHz
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")

        self._ensure_pipeline()

        # Generate audio using existing pipeline
        audio_chunks = []
        for _, _, audio in self._pipeline(text, voice=voice, speed=speed):
            if audio is not None:
                if hasattr(audio, 'cpu'):
                    audio_chunks.append(audio.cpu().numpy())
                else:
                    audio_chunks.append(audio)

        if not audio_chunks:
            raise RuntimeError(f"No audio generated for text: {text[:50]}")

        # Concatenate all audio chunks
        full_audio = np.concatenate(audio_chunks)

        # Write audio to BytesIO buffer as WAV format (24kHz sample rate)
        audio_buffer = io.BytesIO()
        sf.write(audio_buffer, full_audio, 24000, format='WAV')
        audio_buffer.seek(0)

        return audio_buffer

    def get_available_voices(self) -> List[Dict[str, str]]:
        """Return list of available Kokoro voices."""
        return self.VOICES.copy()

    def update_config(self, voice: str, speed_normal: float, speed_name: float) -> None:
        """Update voice/speed config - NO pipeline recreation needed.

        Voice and speed are passed per-call to generate_audio(), so we just
        store the new values. The pipeline remains unchanged.
        """
        self._voice = voice
        self._speed_normal = speed_normal
        self._speed_name = speed_name
        print(f"[KokoroEngine] Config updated - Voice: {voice}, Speed: {speed_normal}/{speed_name}")

    def dispose(self) -> None:
        """Clean up pipeline and free memory (VRAM/RAM)."""
        if self._pipeline is not None:
            print("[KokoroEngine] Disposing pipeline...")
            del self._pipeline
            self._pipeline = None
            gc.collect()  # Force garbage collection to free VRAM
            print("[KokoroEngine] Pipeline disposed, memory freed")
        else:
            print("[KokoroEngine] No pipeline to dispose")

    def get_engine_name(self) -> str:
        """Return engine display name."""
        return "Kokoro"

    def is_available(self) -> bool:
        """Check if Kokoro is available (always true if package is installed)."""
        try:
            from kokoro import KPipeline
            return True
        except ImportError:
            return False

    @property
    def voice(self) -> str:
        """Current voice setting."""
        return self._voice

    @property
    def speed_normal(self) -> float:
        """Current normal text speed."""
        return self._speed_normal

    @property
    def speed_name(self) -> float:
        """Current username speed."""
        return self._speed_name
