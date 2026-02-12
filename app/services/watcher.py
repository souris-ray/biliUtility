import asyncio
import os
import aiofiles
import logging
from typing import Optional, List
from pathlib import Path
from datetime import datetime
from app import config
from app.state import monitor_config, state
from app.services.parser import ChatLogParser
from app.services.tts import TTSService

logger = logging.getLogger('biliutility.watcher')

class LogWatcherService:
    def __init__(self):
        self.running = False
        self.task = None
        self._stop_event = asyncio.Event()

    async def start(self):
        """Start the log watcher task"""
        if self.running:
            return
        
        self.running = True
        self._stop_event.clear()
        self.task = asyncio.create_task(self._watch_loop())
        logger.info("[LogWatcher] Started")

    async def stop(self):
        """Stop the log watcher task"""
        self.running = False
        self._stop_event.set()
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("[LogWatcher] Stopped")

    def _get_log_dir(self) -> str:
        """Get the configured log directory or default to local project log/messages"""
        configured_dir = monitor_config.get_log_dir()
        if configured_dir and os.path.exists(configured_dir):
            return configured_dir
        
        # Default to baked-in testing folder: log/messages/
        default_dir = os.path.join(config.USER_BASE, 'log', 'messages')
        if not os.path.exists(default_dir):
            try:
                os.makedirs(default_dir, exist_ok=True)
            except OSError:
                pass
        return default_dir

    def _get_target_files(self, room_id: str, log_dir: str) -> List[str]:
        """
        Scan for files matching room_{room_id}-{today}_*.txt
        Returns sorted list of absolute paths.
        Filters out files that have already been processed and marked in state.file_tracker.
        """
        if not os.path.exists(log_dir):
            return []

        today_str = datetime.now().strftime('%Y%m%d')
        # Pattern: room_{room_id}-{today}_*.txt
        # Example: room_1769174835-20260118_050632.txt
        prefix = f"room_{room_id}-{today_str}_"
        suffix = ".txt"

        matching_files = []
        try:
            for fname in os.listdir(log_dir):
                if fname.startswith(prefix) and fname.endswith(suffix):
                    # Check if already processed
                    if state.file_tracker.is_processed(fname):
                        continue
                    matching_files.append(fname)
        except OSError as e:
            logger.error(f"[LogWatcher] Error listing directory: {e}")
            return []

        # Sort by filename (which includes timestamp)
        matching_files.sort()
        return [os.path.join(log_dir, f) for f in matching_files]

    async def _process_line(self, line: str):
        if not line.strip():
            return
            
        # Parse line
        msg = ChatLogParser.parse_line(line)
        if msg:
            # Process for TTS (async translation etc)
            await TTSService.process_message_for_tts(msg)
            
            # Add to state (handles logic for gifts, guards, etc. and enqueues for TTS)
            await state.add_message(msg)
            
            # Broadcast to Frontend Widgets
            from app.routers.sockets import broadcast_message
            await broadcast_message(msg)

    async def _read_file_fully(self, filepath: str):
        """Read a file from start to finish (used for historical files)"""
        filename = os.path.basename(filepath)
        logger.info(f"[LogWatcher] Processing historical file: {filepath}")
        
        try:
            async with aiofiles.open(filepath, mode='r', encoding='utf-8-sig') as f:
                async for line in f:
                    await self._process_line(line)
            
            # Mark as processed immediately after finishing
            state.file_tracker.mark_processed(filename)
            logger.info(f"[LogWatcher] Finished processing: {filename}")
            
        except Exception as e:
            logger.error(f"[LogWatcher] Error processing file {filename}: {e}")

    async def _watch_loop(self):
        logger.info("[LogWatcher] Loop starting...")
        
        # Wait for Room ID configuration
        while self.running:
            room_id = monitor_config.get_room_id()
            if room_id:
                break
            logger.warning("[LogWatcher] Room ID not configured. Waiting...")
            await asyncio.sleep(2)
            
        current_tail_file: Optional[str] = None
        active_handle = None
        last_offset = 0
        
        log_dir = self._get_log_dir()
        logger.info(f"[LogWatcher] Watching directory: {log_dir} for Room {room_id}")

        while self.running:
            try:
                # 1. Update Room ID / Log Dir (in case config changed, though usually restart needed)
                # simpler to just re-fetch
                room_id = monitor_config.get_room_id()
                log_dir = self._get_log_dir()
                
                # 2. Scan for valid files
                target_files = self._get_target_files(room_id, log_dir)
                
                if not target_files:
                    if current_tail_file:
                         # We are currently tailing, but maybe the day changed or file was deleted?
                         # If day changed, target_files would be empty (if no files for new day yet).
                         # We should probably continue tailing the current file until a NEW file appears 
                         # OR if the current file date is not today?
                         # User requirement: "Matches same room id and same date as current day".
                         # If date changes, we stop matching old files.
                         # Logic: If current_tail_file is NOT in target_files, and target_files is empty, 
                         # it means we might have rolled over day.
                         # We should just close the current file?
                         # Or maybe we keep tailing it until a file for TODAY appears?
                         # Let's keep tailing active_handle if exists.
                         pass
                    else:
                         logger.debug(f"[LogWatcher] No files found for today in {log_dir}. Waiting...")
                         await asyncio.sleep(2)
                         continue

                # 3. Identify files to process fully vs files to tail
                # If we have multiple files, all except the LAST one should be processed fully and closed.
                # The LAST one should be tailed.
                
                # Check for historical files (all but last)
                if len(target_files) > 1:
                    files_to_process = target_files[:-1]
                    last_file = target_files[-1]
                    
                    # Process historical
                    for fp in files_to_process:
                        # If we are currently tailing this file (unlikely if logic works, but possible if new files appeared rapidly)
                        if current_tail_file == fp and active_handle:
                             # We were tailing it, but now a newer file appeared.
                             # We should finish reading it from current offset, then close it.
                             logger.info(f"[LogWatcher] Newer file detected. Finishing current file: {fp}")
                             await active_handle.seek(last_offset)
                             lines = await active_handle.readlines()
                             for line in lines:
                                 await self._process_line(line)
                             await active_handle.close()
                             active_handle = None
                             current_tail_file = None
                             state.file_tracker.mark_processed(os.path.basename(fp))
                        else:
                             # It's a file we haven't touched (or shouldn't be tailing), just read it whole
                             await self._read_file_fully(fp)

                    # Now we are ready to focus on the last file
                    target_tail_file = last_file
                else:
                    # Only one file found
                    target_tail_file = target_files[0]
                
                # 4. Manage Tailing
                # If we need to switch file
                if current_tail_file != target_tail_file:
                    
                    # Close old if open
                    if active_handle:
                        try:
                            # Read remaining
                            await active_handle.seek(last_offset)
                            lines = await active_handle.readlines()
                            for line in lines:
                                await self._process_line(line)
                            await active_handle.close()
                            # Mark old processed
                            if current_tail_file:
                                state.file_tracker.mark_processed(os.path.basename(current_tail_file))
                        except Exception as e:
                            logger.error(f"[LogWatcher] Error closing old file: {e}")
                        active_handle = None
                    
                    # Open new
                    try:
                        logger.info(f"[LogWatcher] Tailing new file: {target_tail_file}")
                        active_handle = await aiofiles.open(target_tail_file, mode='r', encoding='utf-8-sig')
                        # Note: we start from 0. If we had already processed it (e.g. restart), 
                        # checking state.file_tracker at the top would have filtered it out IF it was marked processed.
                        # But while tailing, it's NOT marked processed yet.
                        # So if we crash and restart, we might re-read the active file.
                        # This is acceptable per "fresh sequential logic" implication, 
                        # or we could implement offset persistence. 
                        # Given user requirements, simplest is start from 0 for current active file.
                        last_offset = 0
                        current_tail_file = target_tail_file
                    except Exception as e:
                        logger.error(f"[LogWatcher] Failed to open {target_tail_file}: {e}")
                        await asyncio.sleep(1)
                        continue

                # 5. Tail loop (Read available lines)
                if active_handle:
                    try:
                        # Check size for truncation / rotation logic or just read
                        current_size = os.path.getsize(current_tail_file)
                        if current_size < last_offset:
                            # File truncated
                            last_offset = 0
                            await active_handle.seek(0)
                        
                        await active_handle.seek(last_offset)
                        lines = await active_handle.readlines()
                        if lines:
                            for line in lines:
                                await self._process_line(line)
                            last_offset = await active_handle.tell()
                    except Exception as e:
                        logger.error(f"[LogWatcher] Tailing error: {e}")
                        # Close and retry next loop
                        try:
                            await active_handle.close()
                        except: pass
                        active_handle = None
                        current_tail_file = None

                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"[LogWatcher] Loop exception: {e}")
                await asyncio.sleep(2)

# Singleton instance
watcher_service = LogWatcherService()
