# -*- coding: utf-8 -*-
"""
TTS Engine Manager

Singleton manager that ensures only ONE TTS engine is active at a time.
Handles engine lifecycle, switching, and proper disposal.
"""
from typing import Optional

from . import TTSEngine


class TTSEngineManager:
    """Manages TTS engine lifecycle - ensures only ONE engine active at a time.

    This is a singleton class. Use the global `tts_manager` instance.

    Key guarantees:
    1. Single Instance: Only one TTSEngineManager exists
    2. Single Engine: Only one TTS engine is active at any time
    3. Proper Disposal: Old engine is disposed before new one is created
    4. No Per-Call Creation: Engines reuse their internal pipelines/clients
    """

    _instance: Optional['TTSEngineManager'] = None

    def __new__(cls) -> 'TTSEngineManager':
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._current_engine: Optional[TTSEngine] = None
            cls._instance._current_engine_type: Optional[str] = None
            cls._instance._sio = None
            cls._instance._availability_cache = {}
            cls._instance._voices_cache = {}
            print("[TTSEngineManager] Singleton instance created")
        return cls._instance

    def set_sio(self, sio):
        """Set SocketIO instance for broadcasting updates."""
        self._sio = sio

    def get_engine(self) -> TTSEngine:
        """Get the current active engine (creates default Kokoro if none).

        Returns:
            The currently active TTS engine
        """
        if self._current_engine is None:
            # We import here to avoid circular imports and only load when needed
            from app.state import tts_config
            print(f"[TTSEngineManager] No engine active, creating default ({tts_config.engine})...")
            self.switch_engine(tts_config.engine)
        return self._current_engine

    def get_current_engine_type(self) -> Optional[str]:
        """Get the current engine type name.

        Returns:
            'kokoro', 'aws_polly', or None if no engine is active
        """
        return self._current_engine_type

    def switch_engine(self, engine_type: str) -> TTSEngine:
        """Switch to a different engine, properly disposing the old one.

        CRITICAL: Old engine is disposed BEFORE new engine is created.
        This ensures only one engine holds resources at any time.

        Args:
            engine_type: 'kokoro' or 'aws_polly'

        Returns:
            The newly activated TTS engine
        """
        # Check if already using this engine
        if self._current_engine_type == engine_type and self._current_engine is not None:
            print(f"[TTSEngineManager] Already using {engine_type} engine")
            return self._current_engine

        # Stop any ongoing playback before switching
        self._stop_playback()

        # Dispose old engine FIRST (before creating new one)
        if self._current_engine is not None:
            print(f"[TTSEngineManager] Disposing {self._current_engine_type} engine...")
            self._current_engine.dispose()
            self._current_engine = None
            self._current_engine_type = None

        # Create new engine
        print(f"[TTSEngineManager] Creating {engine_type} engine...")
        try:
            if engine_type == 'kokoro':
                from .kokoro_engine import KokoroEngine
                self._current_engine = KokoroEngine()
            elif engine_type == 'aws_polly':
                from .polly_engine import PollyEngine
                self._current_engine = PollyEngine()
            else:
                raise ValueError(f"Unknown engine type: {engine_type}")
        except Exception as e:
            print(f"[TTSEngineManager] Critical error creating engine {engine_type}: {e}")
            # Fallback to Kokoro if AWS fails, but avoid infinite loop
            if engine_type != 'kokoro':
                print("[TTSEngineManager] Attempting fallback to kokoro...")
                return self.switch_engine('kokoro')
            raise

        self._current_engine_type = engine_type
        print(f"[TTSEngineManager] Now using {engine_type} engine")

        # Broadcast config update to frontend if sio available
        if self._sio:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._sio.emit('tts:config_updated', {
                        "engine": engine_type,
                        "voice": self._current_engine.voice,
                        "speed_normal": self._current_engine.speed_normal,
                        "speed_name": self._current_engine.speed_name
                    }))
            except Exception as e:
                print(f"[TTSEngineManager] Failed to emit engine switch: {e}")

        return self._current_engine

    def update_config(self, voice: str, speed_normal: float, speed_name: float) -> None:
        """Update current engine config WITHOUT switching/recreating.

        This is the preferred method when only changing voice/speed settings.
        The engine's internal pipeline/client remains unchanged.

        Args:
            voice: Voice ID for current engine
            speed_normal: Speed for normal text
            speed_name: Speed for usernames
        """
        if self._current_engine is not None:
            self._current_engine.update_config(voice, speed_normal, speed_name)
        else:
            print("[TTSEngineManager] No engine active, config update skipped")

    def is_engine_available(self, engine_type: str, use_cache: bool = True) -> bool:
        """Check if a specific engine type is available.

        Args:
            engine_type: 'kokoro' or 'aws_polly'
            use_cache: If True, use cached result if available

        Returns:
            True if the engine can be used
        """
        if use_cache and engine_type in self._availability_cache:
            return self._availability_cache[engine_type]

        is_available = False
        if engine_type == 'kokoro':
            try:
                # We check for the module presence without importing everything if possible
                # However, kokoro usually doesn't have a submodule for just checking.
                # Python's import system caches imports anyway.
                import importlib.util
                is_available = importlib.util.find_spec("kokoro") is not None
            except Exception:
                is_available = False
        elif engine_type == 'aws_polly':
            import os
            access_key = os.getenv('AWS_ACCESS_KEY_ID')
            secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
            if access_key and secret_key:
                try:
                    import importlib.util
                    is_available = importlib.util.find_spec("boto3") is not None
                except:
                    is_available = False
            else:
                is_available = False
        
        self._availability_cache[engine_type] = is_available
        return is_available

    def get_available_engines(self) -> list:
        """Get list of available engine types.

        Returns:
            List of engine type strings that are currently available
        """
        available = []
        if self.is_engine_available('kokoro'):
            available.append('kokoro')
        if self.is_engine_available('aws_polly'):
            available.append('aws_polly')
        return available

    def dispose_current(self) -> None:
        """Dispose the current engine (for shutdown/cleanup)."""
        self._stop_playback()
        if self._current_engine is not None:
            print(f"[TTSEngineManager] Disposing current engine ({self._current_engine_type})...")
            self._current_engine.dispose()
            self._current_engine = None
            self._current_engine_type = None
            print("[TTSEngineManager] Engine disposed")
        
        # Clear cache on disposal as environment might have changed (e.g. AWS keys)
        self._availability_cache.clear()

    def get_voices_by_type(self, engine_type: str) -> list:
        """Get available voices for a specific engine type.

        Args:
            engine_type: 'kokoro' or 'aws_polly'

        Returns:
            List of voice dictionaries
        """
        if engine_type in self._voices_cache:
            return self._voices_cache[engine_type]

        voices = []
        if engine_type == 'kokoro':
            try:
                from .kokoro_engine import KokoroEngine
                voices = KokoroEngine.VOICES
            except:
                pass
        elif engine_type == 'aws_polly':
            try:
                from .polly_engine import PollyEngine
                voices = PollyEngine.VOICES
            except:
                pass
        
        if voices:
            self._voices_cache[engine_type] = voices
        return voices

    def _stop_playback(self) -> None:
        """Stop any ongoing audio playback."""
        try:
            import sounddevice as sd
            sd.stop()
        except Exception as e:
            print(f"[TTSEngineManager] Error stopping playback: {e}")


# Global singleton instance
tts_manager = TTSEngineManager()
