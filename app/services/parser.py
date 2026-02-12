import re
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from app.models import MessageType, ParsedMessage
# We can't import TTSService yet as it doesn't exist, and circular imports might be an issue.
# Refactoring decision: The parser should just PARSE. The processing (TTS) should be done by the service calling the parser.
# This decouples the parser from the TTS service.
# For now, I will remove the TTSService call from here and move it to the caller (LogWatcherService).

logger = logging.getLogger('biliutility.parser')

GUARD_CONFIG = {
    '舰长': {'id': 'captain', 'webhook_type': 'captain'},
    '提督': {'id': 'admiral', 'webhook_type': 'admiral'},
    '总督': {'id': 'governor', 'webhook_type': 'governor'},
}
GUARD_TYPES = tuple(GUARD_CONFIG.keys())

class ChatLogParser:
    @staticmethod
    def parse_line(line: str) -> Optional[ParsedMessage]:
        try:
            timestamp_end = line.find(' [')
            if timestamp_end == -1:
                return None

            timestamp_str = line[:timestamp_end].lstrip('\ufeff')
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')

            type_start = timestamp_end + 2
            type_end = line.find(']', type_start)
            if type_end == -1:
                return None

            msg_type_str = line[type_start:type_end]
            try:
                msg_type = MessageType(msg_type_str)
            except ValueError:
                return None

            content_str = line[type_end + 2:].strip()

            if msg_type == MessageType.DM:
                return ChatLogParser._parse_dm(timestamp, content_str)
            elif msg_type == MessageType.FREE_GIFT:
                return ChatLogParser._parse_free_gift(timestamp, content_str)
            elif msg_type == MessageType.PAID_GIFT:
                return ChatLogParser._parse_paid_gift(timestamp, content_str)
            elif msg_type == MessageType.GUARD:
                return ChatLogParser._parse_guard(timestamp, content_str, line)
            elif msg_type == MessageType.SUPERCHAT:
                return ChatLogParser._parse_superchat(timestamp, content_str)

        except Exception as e:
            logger.error(f"Error parsing line: {line.strip()}, Error: {e}")
            return None

    @staticmethod
    def _parse_dm(timestamp: datetime, content: str) -> ParsedMessage:
        parts = content.split('：', 1)
        username = parts[0] if len(parts) > 0 else ""
        message = parts[1] if len(parts) > 1 else ""
        return ParsedMessage(
            timestamp=timestamp,
            type=MessageType.DM,
            username=username,
            content={"message": message},
            unique_id=f"{timestamp.isoformat()}_{username}_dm"
        )

    @staticmethod
    def _parse_gift(timestamp: datetime, content: str,
                    msg_type: MessageType, currency: str) -> ParsedMessage:
        username_end = content.find(' 赠送了 ')
        username = content[:username_end]

        gift_start = username_end + 5
        gift_end = content.find(' x ', gift_start)
        gift_name = content[gift_start:gift_end]

        quantity_start = gift_end + 3
        quantity_end = content.find('，', quantity_start)
        quantity = int(content[quantity_start:quantity_end])

        value_start = content.find('总价 ') + 3
        value_end = content.find(f' {currency}')
        value = float(content[value_start:value_end])

        type_suffix = 'free_gift' if msg_type == MessageType.FREE_GIFT else 'paid_gift'

        return ParsedMessage(
            timestamp=timestamp,
            type=msg_type,
            username=username,
            content={
                "gift_name": gift_name,
                "quantity": quantity,
                "value": value,
                "currency": currency
            },
            unique_id=f"{timestamp.isoformat()}_{username}_{type_suffix}"
        )

    @staticmethod
    def _parse_free_gift(timestamp: datetime, content: str) -> ParsedMessage:
        return ChatLogParser._parse_gift(timestamp, content, MessageType.FREE_GIFT, "银瓜子")

    @staticmethod
    def _parse_paid_gift(timestamp: datetime, content: str) -> ParsedMessage:
        return ChatLogParser._parse_gift(timestamp, content, MessageType.PAID_GIFT, "元")

    @staticmethod
    def _parse_guard(timestamp: datetime, content: str, original_line: str) -> ParsedMessage:
        guard_pattern = r'^(.+?) 购买了 (\d+)([^\s]+) (舰长|提督|总督)，总价 ([\d.]+) 元$'
        match = re.match(guard_pattern, content)

        if match:
            username = match.group(1)
            duration = int(match.group(2))
            guard_type = match.group(4)
            value = float(match.group(5))
        else:
            username_end = content.find(' 购买了 ')
            username = content[:username_end]
            duration_start = username_end + 5
            duration_end = duration_start
            while duration_end < len(content) and content[duration_end].isdigit():
                duration_end += 1
            duration = int(content[duration_start:duration_end])

            guard_type = None
            for gt in GUARD_TYPES:
                if gt in content:
                    guard_type = gt
                    break
            if guard_type is None:
                guard_type = '未知舰队等级'

            value_start = content.find('总价 ') + 3
            value_end = content.find(' 元')
            value = float(content[value_start:value_end])

        webhook_type = GUARD_CONFIG.get(guard_type, {}).get('webhook_type')
        tts_text = f"{username}。\t 非常感谢您的支持！"

        return ParsedMessage(
            timestamp=timestamp,
            type=MessageType.GUARD,
            username=username,
            content={
                "duration": duration,
                "guard_type": guard_type,
                "value": value,
                "currency": "元"
            },
            tts_enabled=True,
            tts_text=tts_text,
            webhook_type=webhook_type,
            unique_id=f"{timestamp.isoformat()}_{username}_guard_{guard_type}"
        )

    @staticmethod
    def _parse_superchat(timestamp: datetime, content: str) -> ParsedMessage:
        username_end = content.find(' 发送了 ')
        username = content[:username_end]

        amount_start = username_end + 5
        amount_end = content.find(' 元的醒目留言：')
        amount = float(content[amount_start:amount_end])

        message_start = amount_end + 8
        message = content[message_start:]

        return ParsedMessage(
            timestamp=timestamp,
            type=MessageType.SUPERCHAT,
            username=username,
            content={
                "amount": amount,
                "message": message,
                "currency": "元"
            },
            tts_enabled=True,
            tts_text=f"{username}说: {message}",
            unique_id=f"{timestamp.isoformat()}_{username}_sc"
        )
