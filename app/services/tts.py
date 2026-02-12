import asyncio
import logging
import re
import io
import time
import sounddevice as sd
import soundfile as sf
import deepl
from typing import Tuple, List, Optional
from datetime import datetime

from app.state import sound_config, tts_config, state, credentials_manager
from app.models import ParsedMessage
from tts_engines.manager import tts_manager
from app.services.webhook import WebhookService

logger = logging.getLogger('biliutility.tts')

# Command Audio Path
from app import config as app_config
from pathlib import Path

COMMAND_AUDIO_PATH = Path(app_config.AUDIO_PATH)

class TTSService:
    """Service for handling text-to-speech functionality"""
    
    _translator = None

    @staticmethod
    def get_translator() -> Optional[deepl.Translator]:
        auth_key = credentials_manager.credentials.get('deepl_auth_key')
        if not auth_key:
            return None
        
        # Simple singleton-like logic
        if TTSService._translator is None:
             try:
                TTSService._translator = deepl.Translator(auth_key)
             except Exception as e:
                 logger.error(f"[TTS] Failed to initialize DeepL: {e}")
                 return None
        return TTSService._translator

    @staticmethod
    async def translate_text(text: str) -> str:
        """Translate text from Chinese to English using DeepL (Async wrapper)"""
        translator = TTSService.get_translator()
        if not translator:
            return "Translation unavailable"

        try:
            # wrapping blocking I/O in executor
            result = await asyncio.to_thread(
                translator.translate_text,
                text,
                source_lang='ZH',
                target_lang='EN-US'
            )
            if isinstance(result, list):
                return result[0].text if result else "Translation failed"
            return result.text
        except Exception as e:
            logger.error(f"[Translation] DeepL error: {e}")
            return "Translation failed"

    @staticmethod
    def get_pinyin(text: str) -> str:
        """Convert Chinese text to Pinyin (Sync)"""
        try:
            from pypinyin import pinyin
            pinyin_result = pinyin(text)
            return ' '.join([''.join(syllable) for syllable in pinyin_result])
        except Exception as e:
            logger.error(f"Pinyin conversion error: {e}")
            return "Pinyin conversion failed"

    @staticmethod
    def split_text_with_commands(text: str) -> Tuple[List[Tuple[str, bool]], str, bool]:
        """Split text into segments and provide a cleaned version without commands"""
        commands = sorted(sound_config.get_commands().keys(), key=len, reverse=True)
        if not commands:
            return [(text, False)], text, False

        pattern = '|'.join(map(re.escape, commands))
        segments = []
        cleaned_parts = []
        current_pos = 0
        command_count = 0
        
        for match in re.finditer(pattern, text):
            if match.start() > current_pos:
                pre_text = text[current_pos:match.start()].strip()
                if pre_text:
                    segments.append((pre_text, False))
                    cleaned_parts.append(pre_text)
            
            command = match.group()
            segments.append((command, True))
            command_count += 1
            current_pos = match.end()
        
        if current_pos < len(text):
            remaining = text[current_pos:].strip()
            if remaining:
                segments.append((remaining, False))
                cleaned_parts.append(remaining)
        
        cleaned_text = ' '.join(cleaned_parts).strip()
        too_many_commands = command_count > 3
        return segments, cleaned_text, too_many_commands

    @staticmethod
    def format_commands(text: str) -> str:
        commands = sorted(sound_config.get_commands().keys(), key=len, reverse=True)
        formatted_text = text
        for command in commands:
            if command in formatted_text:
                formatted_text = formatted_text.replace(
                    command,
                    f'<span class="command-text">{command}</span>'
                )
        return formatted_text

    @staticmethod
    async def process_message_for_tts(message: ParsedMessage):
        """Process a message for TTS, adding translation, pinyin, etc. (Async)"""
        if message.tts_text:
            segments, cleaned_text, too_many_commands = TTSService.split_text_with_commands(message.tts_text)

            if too_many_commands:
                message.command_segments = [(message.tts_text, False)]
                translate_task = asyncio.create_task(TTSService.translate_text(message.tts_text))
                message.pinyin = TTSService.get_pinyin(message.tts_text)
            else:
                message.command_segments = segments
                translate_task = asyncio.create_task(TTSService.translate_text(cleaned_text))
                message.pinyin = TTSService.get_pinyin(cleaned_text)
            
            message.formatted_text = TTSService.format_commands(message.tts_text)
            
            # Await translation
            message.translation = await translate_task

    @staticmethod
    async def play_text_segment(text: str, is_name: bool = False):
        """Generate and play TTS audio (Async wrapper for blocking duration)"""
        if not text.strip():
            return

        logger.debug(f"[DEBUG][TTS] Playing text segment: '{text}' (is_name: {is_name})")
        try:
            # We run the entire generation and playback in a thread to be safe
            # as tts_manager.generate_audio might take time and sd.wait() definitely blocks.
            await asyncio.to_thread(TTSService._play_text_sync, text, is_name)
        except Exception as e:
            logger.error(f"[TTS] Error playing text segment: {e}")

    @staticmethod
    def _play_text_sync(text: str, is_name: bool):
        engine = tts_manager.get_engine()
        speed = tts_config.speed_name if is_name else tts_config.speed_normal
        audio_buffer = engine.generate_audio(text, tts_config.voice, speed)
        
        if not audio_buffer:
            logger.info(f"[TTS] No audio generated for: {text[:50]}")
            return

        audio_buffer.seek(0)
        data, samplerate = sf.read(audio_buffer, dtype='float32')
        sd.play(data, samplerate)
        sd.wait()

    @staticmethod
    async def play_command_audio(command: str) -> bool:
        """Play command audio file (Async wrapper)"""
        return await asyncio.to_thread(TTSService._play_command_sync, command)

    @staticmethod
    def _play_command_sync(command: str) -> bool:
        command_info = sound_config.get_command_info(command)
        if not command_info:
            return False
        
        audio_file = command_info.get('filename')
        volume = command_info.get('volume', 1.0)
        
        if not audio_file:
            return False
            
        audio_path = COMMAND_AUDIO_PATH / audio_file
        if not audio_path.exists():
            return False
            
        try:
            data, samplerate = sf.read(str(audio_path), dtype='float32')
            data = data * float(volume)
            sd.play(data, samplerate)
            sd.wait()
            return True
        except Exception as e:
            logger.error(f"[TTS] Error playing command audio: {e}")
            return False

class TTSProcessor:
    def __init__(self, sio):
        self.sio = sio
        self.running = False
        self.task = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._process_queue())
        logger.info("[TTSProcessor] Started")

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("[TTSProcessor] Stopped")

    async def _process_queue(self):
        logger.debug("[TTSProcessor] Loop running...")
        while self.running:
            try:
                # Get next message from async queue (blocks until available)
                queue_item = await state.tts_queue.get()
                msg, should_mark_read = queue_item
                
                logger.debug(f"[TTSProcessor] Processing: {msg.unique_id}")
                
                async with state.lock:
                    state.tts_playing = msg

                # Trigger webhook
                if msg.webhook_type:
                    # Run Webhook trigger in thread as request is sync
                    await asyncio.to_thread(WebhookService.trigger_webhook, msg.webhook_type)
                    # Webhook cooldown
                    await asyncio.sleep(1.0)

                # Play audio segments
                if msg.command_segments:
                    for segment, is_command in msg.command_segments:
                        if not self.running: break
                        
                        # Emit segment status for better visual feedback
                        if self.sio:
                            display_text = f"Playing Command: {segment}" if is_command else segment
                            await self.sio.emit('tts:now_playing', {
                                'unique_id': msg.unique_id,
                                'username': msg.username,
                                'text': display_text,
                                'type': msg.type.value,
                                'is_command': is_command
                            })

                        if is_command:
                            logger.info(f"[TTSProcessor] Playing Command: {segment} for message {msg.unique_id}")
                            await TTSService.play_command_audio(segment)
                        else:
                            logger.info(f"[TTSProcessor] Playing Text Segment: {segment[:50]}... for message {msg.unique_id}")
                            await TTSService.play_text_segment(segment)
                else:
                    # Fallback for messages without segments
                    if self.sio:
                        await self.sio.emit('tts:now_playing', {
                            'unique_id': msg.unique_id,
                            'username': msg.username,
                            'text': msg.tts_text,
                            'type': msg.type.value
                        })
                    logger.info(f"[TTSProcessor] Playing Full Text: {msg.tts_text[:50]}... for message {msg.unique_id}")
                    await TTSService.play_text_segment(msg.tts_text)

                # Mark as read
                async with state.lock:
                    if should_mark_read:
                        msg.is_read = True
                    state.tts_playing = None

                # Emit completion event
                if self.sio:
                    await self.sio.emit('tts:playback_complete', {
                        'unique_id': msg.unique_id
                    })
                
                state.tts_queue.task_done()
                
                # Small delay between messages
                await asyncio.sleep(0.5)

                # Autoplay check logic handled by queue consumer natural behavior
                # But we might need to enqueue more if we are consuming from 'unread' list like original logic?
                # The original logic pulled from unread list if queue was empty.
                # Here, we assume the provider (LogWatcher) pushes to queue.
                # However, original logic:
                # "If autoplay is on and queue is empty, check for unread messages"
                # This suggests there is a pool of unread messages that are NOT in the queue?
                # Yes, if autoplay was OFF, messages accumulate. When turned ON, they should be queued.
                # We can handle this by having an explicit "fill queue" action when autoplay is toggled,
                # rather than polling inside the consumer.
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[TTSProcessor] Error: {e}")
                await asyncio.sleep(1.0)
