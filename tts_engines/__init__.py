# -*- coding: utf-8 -*-
"""
TTS Engines Package

Provides abstraction layer for multiple TTS engines (Kokoro, AWS Polly).
Uses singleton pattern to ensure only one engine instance is active at a time.
"""
from abc import ABC, abstractmethod
from typing import List, Dict
import io


class TTSEngine(ABC):
    """Base class for TTS engines. Each engine is a singleton - only one instance exists."""

    @abstractmethod
    def generate_audio(self, text: str, voice: str, speed: float) -> io.BytesIO:
        """Generate audio using the existing pipeline (NO new pipeline creation).

        Args:
            text: Text to synthesize
            voice: Voice ID to use
            speed: Speed multiplier (0.3 - 2.0)

        Returns:
            BytesIO buffer containing WAV audio data
        """
        pass

    @abstractmethod
    def get_available_voices(self) -> List[Dict[str, str]]:
        """Return list of available voices.

        Returns:
            List of {'value': 'voice_id', 'label': 'Display Name'}
        """
        pass

    @abstractmethod
    def update_config(self, voice: str, speed_normal: float, speed_name: float) -> None:
        """Update configuration without recreating the pipeline (if possible).

        Args:
            voice: New voice ID
            speed_normal: Speed for normal text
            speed_name: Speed for usernames
        """
        pass

    @abstractmethod
    def dispose(self) -> None:
        """Clean up resources, free memory, release GPU/API connections.

        MUST be called before switching to another engine.
        """
        pass

    @abstractmethod
    def get_engine_name(self) -> str:
        """Return engine display name."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if engine is ready (credentials valid, model loaded, etc.)."""
        pass


# Export classes for easier imports
from .kokoro_engine import KokoroEngine
from .polly_engine import PollyEngine
from .manager import TTSEngineManager, tts_manager

__all__ = ['TTSEngine', 'KokoroEngine', 'PollyEngine', 'TTSEngineManager', 'tts_manager']
