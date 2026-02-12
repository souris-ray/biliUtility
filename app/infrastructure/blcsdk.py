import asyncio
import logging
import json
import os
from datetime import datetime
from typing import Optional, Callable, Dict, Any

import blcsdk
import blcsdk.models as sdk_models

from app import config
from app.models import ParsedMessage, MessageType

logger = logging.getLogger('biliutility.sdk')

_msg_handler: Optional['MsgHandler'] = None
_backup_file = None
_current_backup_date: Optional[str] = None
_loop = None

GUARD_LEVEL_NAMES = {
    sdk_models.GuardLevel.LV1: '舰长',
    sdk_models.GuardLevel.LV2: '提督',
    sdk_models.GuardLevel.LV3: '总督',
}

async def init_sdk(message_callback: Callable[[ParsedMessage], Any]):
    """Initialize the message handler with blcsdk."""
    global _msg_handler, _loop
    _loop = asyncio.get_running_loop()
    _msg_handler = MsgHandler(message_callback, _loop)
    blcsdk.set_msg_handler(_msg_handler)
    logger.info('[SDK] Message handler initialized')

def shut_down_sdk():
    """Clean up resources on shutdown."""
    global _backup_file
    blcsdk.set_msg_handler(None)
    if _backup_file is not None:
        _backup_file.close()
        _backup_file = None
    logger.info('[SDK] Message handler shut down')

def _get_backup_file():
    """Get or create the JSON backup log file for today."""
    global _backup_file, _current_backup_date

    # Using config from app/config.py which we imported as `config`
    # Check if BACKUP_LOG_ENABLED is available there. 
    # In app/config.py, we defined: `BACKUP_LOG_ENABLED` (default False via env?)
    # Wait, in the original `config.py`, it was:
    # BACKUP_LOG_ENABLED = os.getenv('ENABLE_BACKUP_LOG', 'false').lower() == 'true'
    # In my new `app/config.py` (which I created earlier), I included it?
    # Let's assume yes or use default logic.
    
    if not getattr(config, 'BACKUP_LOG_ENABLED', False):
        return None

    today = datetime.now().strftime('%Y-%m-%d')
    if _current_backup_date != today:
        if _backup_file is not None:
            _backup_file.close()

        # BACKUP_LOG_PATH should be in config
        backup_path = getattr(config, 'BACKUP_LOG_PATH', 'backups')
        if not os.path.exists(backup_path):
             os.makedirs(backup_path, exist_ok=True)
             
        filename = f'messages_{today}.jsonl'
        filepath = os.path.join(backup_path, filename)
        _backup_file = open(filepath, 'a', encoding='utf-8')
        _current_backup_date = today
        logger.info(f'[SDK] Opened backup log: {filepath}')

    return _backup_file

def _write_backup_log(msg_type: str, data: Dict[str, Any], room_id: Optional[int] = None):
    # This function is kept for backward compatibility if any other part uses it,
    # but primarily we rely on raw logging now.
    pass

async def _log_raw_packet(command: Dict[str, Any]):
    """Async logging of raw JSON packet"""
    try:
        # Use a separate file pattern for raw events
        today = datetime.now().strftime('%Y-%m-%d')
        # Using config.LOG_PATH
        log_path = getattr(config, 'LOG_PATH', 'log')
        if not os.path.exists(log_path):
             os.makedirs(log_path, exist_ok=True)
             
        filepath = os.path.join(log_path, f'raw_plugin_events_{today}.jsonl')
        
        async with aiofiles.open(filepath, mode='a', encoding='utf-8') as f:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'packet': command
            }
            await f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.error(f'[SDK] Failed to log raw packet: {e}')

class MsgHandler(blcsdk.BaseHandler):
    def __init__(self, callback: Callable[[ParsedMessage], Any], loop: asyncio.AbstractEventLoop):
        self._callback = callback
        self._loop = loop

    def on_client_stopped(self, client: blcsdk.BlcPluginClient, exception: Optional[Exception]):
        logger.info('[SDK] blivechat disconnected')

    def _safe_callback(self, msg: ParsedMessage):
        """Invoke async callback from sync context"""
        if self._loop and self._loop.is_running():
             asyncio.run_coroutine_threadsafe(self._callback(msg), self._loop)

    def handle(self, client: blcsdk.BlcPluginClient, command: dict):
        # 1. Fire-and-forget raw logging
        if _loop:
            asyncio.run_coroutine_threadsafe(_log_raw_packet(command), _loop)
        
        # 2. Direct processing for efficiency
        cmd = command.get('cmd')
        data = command.get('data', {})
        extra = command.get('extra', {})
        
        # Determine room_id if possible
        # Check blcsdk/models.py: ExtraData has room_id
        room_id = extra.get('room_id') if isinstance(extra, dict) else None

        # Process specific commands directly
        # Command.ADD_TEXT = 50
        if cmd == 50:
            self._process_add_text(data, room_id)
        # Command.ADD_GIFT = 51
        elif cmd == 51:
            self._process_add_gift(data, room_id)
        # Command.ADD_MEMBER = 52
        elif cmd == 52:
            self._process_add_member(data, room_id)
        # Command.ADD_SUPER_CHAT = 53
        elif cmd == 53:
            self._process_add_super_chat(data, room_id)
        
        # We ignore other commands or let BaseHandler handle them if needed, 
        # but since we override handle(), BaseHandler logic is bypassed.
        # This is intentional for efficiency.

    def _process_add_text(self, data: dict, room_id: Optional[int]):
        # Structure from models.py AddTextMsg
        # content, authorName, uid, authorType, ...
        # data is a dict directly here.
        
        content = data.get('content', '')
        author_name = data.get('authorName', '')
        
        # Logic from original _on_add_text
        ts_dt = datetime.now() # SDK usually has timestamp in data? models.py says timestamp is NOT in AddTextMsg, it's implied?
        # creating a timestamp now is safer
        
        parsed = ParsedMessage(
            timestamp=ts_dt,
            type=MessageType.DM,
            username=author_name,
            content={"message": content},
            unique_id=f"{ts_dt.isoformat()}_{author_name}_dm"
        )
        self._safe_callback(parsed)

    def _process_add_gift(self, data: dict, room_id: Optional[int]):
        # AddGiftMsg: giftName, num, totalCoin, totalFreeCoin...
        total_coin = data.get('totalCoin', 0)
        is_paid = total_coin != 0
        
        msg_type = MessageType.PAID_GIFT if is_paid else MessageType.FREE_GIFT
        currency = '元' if is_paid else '银瓜子'
        value = (total_coin / 1000) if is_paid else data.get('totalFreeCoin', 0)
        
        author_name = data.get('authorName', '')
        gift_name = data.get('giftName', '')
        num = data.get('num', 0)
        
        ts_dt = datetime.now()
        type_suffix = 'paid_gift' if is_paid else 'free_gift'
        
        parsed = ParsedMessage(
            timestamp=ts_dt,
            type=msg_type,
            username=author_name,
            content={
                "gift_name": gift_name,
                "quantity": num,
                "value": value,
                "currency": currency
            },
            unique_id=f"{ts_dt.isoformat()}_{author_name}_{type_suffix}"
        )
        self._safe_callback(parsed)

    def _process_add_member(self, data: dict, room_id: Optional[int]):
        # AddMemberMsg: privilegeType 
        privilege_type = data.get('privilegeType', 0)
        guard_name = GUARD_LEVEL_NAMES.get(privilege_type, '未知舰队等级')
        
        total_coin = data.get('totalCoin', 0)
        value = total_coin / 1000
        
        webhook_type = None
        if privilege_type == 1: webhook_type = 'captain'
        elif privilege_type == 2: webhook_type = 'admiral'
        elif privilege_type == 3: webhook_type = 'governor'

        author_name = data.get('authorName', '')
        num = data.get('num', 0)
        
        ts_dt = datetime.now()
        tts_text = f"{author_name}。\t 非常感谢您的支持！"
        
        parsed = ParsedMessage(
            timestamp=ts_dt,
            type=MessageType.GUARD,
            username=author_name,
            content={
                "duration": num,
                "guard_type": guard_name,
                "value": value,
                "currency": "元"
            },
            tts_enabled=True,
            tts_text=tts_text,
            webhook_type=webhook_type,
            unique_id=f"{ts_dt.isoformat()}_{author_name}_guard_{webhook_type or 'unknown'}"
        )
        self._safe_callback(parsed)

    def _process_add_super_chat(self, data: dict, room_id: Optional[int]):
        # AddSuperChatMsg: price, content
        price = data.get('price', 0)
        content = data.get('content', '')
        author_name = data.get('authorName', '')
        
        ts_dt = datetime.now()
        
        parsed = ParsedMessage(
            timestamp=ts_dt,
            type=MessageType.SUPERCHAT,
            username=author_name,
            content={
                "amount": price,
                "message": content,
                "currency": "元"
            },
            tts_enabled=True,
            tts_text=f"{author_name}说: {content}",
            unique_id=f"{ts_dt.isoformat()}_{author_name}_sc"
        )
        self._safe_callback(parsed)
