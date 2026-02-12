# -*- coding: utf-8 -*-
"""
AWS Polly TTS Engine

Uses AWS Polly for cloud-based text-to-speech.
Maintains a single boto3 client instance that is reused for all API calls.
"""
import io
import os
import struct
import wave
from typing import List, Dict

from . import TTSEngine


class PollyEngine(TTSEngine):
    """AWS Polly TTS engine - maintains single boto3 client instance.

    The boto3 client is created lazily on first use and reused for all subsequent calls.
    Supports both Neural and Standard engine types.
    """

    # Available Chinese voices (AWS Polly)
    VOICES = [
        {'value': 'Zhiyu-Neural', 'label': 'Zhiyu (Female - Neural)'},
        {'value': 'Zhiyu-Standard', 'label': 'Zhiyu (Female - Standard)'},
    ]

    # Engine types
    ENGINE_TYPES = ['neural', 'standard']

    def __init__(self):
        """Initialize Polly engine with lazy client creation."""
        self._client = None  # Lazy initialization
        self._voice = 'Zhiyu'
        self._engine_type = 'neural'  # 'neural' or 'standard'
        self._speed_normal = 1.0
        self._speed_name = 0.9
        self._region = os.getenv('AWS_REGION', 'us-east-1')
        print(f"[PollyEngine] Initialized (client will be created on first use, region: {self._region})")

    def _ensure_client(self):
        """Create boto3 Polly client only once."""
        if self._client is None:
            print(f"[PollyEngine] Creating boto3 Polly client (region: {self._region})...")
            import boto3
            self._client = boto3.client(
                'polly',
                region_name=self._region
            )
            print("[PollyEngine] Client created successfully")

    def _pcm_to_wav(self, pcm_data: bytes, sample_rate: int = 24000) -> io.BytesIO:
        """Convert raw PCM data to WAV format.

        Args:
            pcm_data: Raw PCM audio data (16-bit signed, mono)
            sample_rate: Sample rate in Hz

        Returns:
            BytesIO buffer containing WAV audio data
        """
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)
        wav_buffer.seek(0)
        return wav_buffer

    def generate_audio(self, text: str, voice: str, speed: float) -> io.BytesIO:
        """Generate audio using AWS Polly API.

        Args:
            text: Text to synthesize
            voice: Voice ID (e.g., 'Zhiyu')
            speed: Speed multiplier (0.3 - 2.0), converted to SSML prosody rate

        Returns:
            BytesIO buffer containing WAV audio data at 24kHz
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")

        self._ensure_client()

        # Convert speed multiplier to SSML prosody rate percentage
        # Kokoro uses 0.3-2.0, Polly uses 20%-200%
        rate_percent = max(20, min(200, int(speed * 100)))

        # Wrap text in SSML with prosody for speed control
        ssml_text = f'<speak><prosody rate="{rate_percent}%">{text}</prosody></speak>'

        # Parse engine type if encoded in voice string (e.g., 'Zhiyu-Neural')
        actual_voice = voice
        actual_engine = self._engine_type
        if '-' in voice:
            actual_voice, engine_suffix = voice.split('-', 1)
            actual_engine = engine_suffix.lower()

        # For PCM output format, AWS Polly only supports 8000 or 16000 Hz.
        # Higher rates like 22050 or 24000 are NOT supported for PCM.
        sample_rate = '16000'

        try:
            response = self._client.synthesize_speech(
                Text=ssml_text,
                TextType='ssml',
                OutputFormat='pcm',
                VoiceId=actual_voice,
                Engine=actual_engine,
                SampleRate=sample_rate,
                LanguageCode='cmn-CN'  # Mandarin Chinese
            )

            # Read PCM data from response
            pcm_data = response['AudioStream'].read()

            # Convert PCM to WAV
            wav_buffer = self._pcm_to_wav(pcm_data, sample_rate=int(sample_rate))

            return wav_buffer

        except Exception as e:
            print(f"[PollyEngine] Error generating audio: {e}")
            raise

    def get_available_voices(self) -> List[Dict[str, str]]:
        """Return list of available Polly voices for Chinese."""
        return self.VOICES.copy()

    def update_config(self, voice: str, speed_normal: float, speed_name: float) -> None:
        """Update voice/speed config.
        
        If voice contains engine type (e.g. 'Zhiyu-Neural'), we split it.
        """
        self._voice = voice
        if '-' in voice:
            _, engine_suffix = voice.split('-', 1)
            self._engine_type = engine_suffix.lower()
            
        self._speed_normal = speed_normal
        self._speed_name = speed_name
        print(f"[PollyEngine] Config updated - Voice: {voice}, Engine: {self._engine_type}, Speed: {speed_normal}/{speed_name}")

    def set_engine_type(self, engine_type: str) -> None:
        """Set the Polly engine type (neural or standard).

        Args:
            engine_type: 'neural' or 'standard'
        """
        if engine_type not in self.ENGINE_TYPES:
            raise ValueError(f"Invalid engine type: {engine_type}. Must be one of {self.ENGINE_TYPES}")
        self._engine_type = engine_type
        print(f"[PollyEngine] Engine type set to: {engine_type}")

    def dispose(self) -> None:
        """Clean up boto3 client.

        boto3 clients don't hold resources that need explicit cleanup,
        but we set to None for consistency.
        """
        if self._client is not None:
            print("[PollyEngine] Disposing client...")
            self._client = None
            print("[PollyEngine] Client disposed")
        else:
            print("[PollyEngine] No client to dispose")

    def get_engine_name(self) -> str:
        """Return engine display name."""
        return "AWS Polly"

    def is_available(self) -> bool:
        """Check if AWS Polly is available (credentials configured)."""
        # Check for AWS credentials
        access_key = os.getenv('AWS_ACCESS_KEY_ID')
        secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')

        if not access_key or not secret_key:
            return False

        # Optionally verify credentials work by making a test call
        try:
            import boto3
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

    @property
    def engine_type(self) -> str:
        """Current Polly engine type (neural/standard)."""
        return self._engine_type
