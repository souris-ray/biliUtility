from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pydantic import BaseModel, Field

class MessageType(str, Enum):
    DM = "dm"
    FREE_GIFT = "free_gift"
    PAID_GIFT = "paid_gift"
    GUARD = "guard"
    SUPERCHAT = "superchat"

class ParsedMessage(BaseModel):
    timestamp: datetime
    type: MessageType
    username: str
    content: Dict[str, Any]
    
    # New fields for TTS
    tts_enabled: bool = False
    tts_text: Optional[str] = None
    command_segments: Optional[List[Tuple[str, bool]]] = None
    translation: Optional[str] = None
    pinyin: Optional[str] = None
    formatted_text: Optional[str] = None
    
    # New fields for webhooks
    webhook_type: Optional[str] = None
    
    # Unique identifier
    unique_id: Optional[str] = None
    
    # Read status for TTS
    is_read: bool = False

    class Config:
        arbitrary_types_allowed = True

# API Request Models

class CredentialsUpdate(BaseModel):
    aws_access_key: Optional[str] = ""
    aws_secret_key: Optional[str] = ""
    aws_region: Optional[str] = "us-east-1"
    deepl_auth_key: Optional[str] = ""
    webhook_url_captain: Optional[str] = ""
    webhook_url_admiral: Optional[str] = ""
    webhook_url_governor: Optional[str] = ""

class ConfigUpdate(BaseModel):
    room_id: str
    uid: str
    username: str
    log_dir: Optional[str] = None

class TTSConfigUpdate(BaseModel):
    engine: Optional[str] = None
    voice: Optional[str] = None
    speed_normal: Optional[float] = None
    speed_name: Optional[float] = None

class GiftConfigUpdate(BaseModel):
    milestone_goal: Optional[int] = None
    title_text: Optional[str] = None
    title_style: Optional[Dict[str, Any]] = None
    show_title: Optional[bool] = None
    background_style: Optional[Dict[str, Any]] = None
    show_background: Optional[bool] = None
    count_color: Optional[str] = None
    label_color: Optional[str] = None
    progress_bar_start_color: Optional[str] = None
    progress_bar_end_color: Optional[str] = None

class MemberConfigUpdate(BaseModel):
    thank_you_text: Optional[str] = None
    show_member_info: Optional[bool] = None
    enable_webhook_captain: Optional[bool] = None
    enable_webhook_admiral: Optional[bool] = None
    enable_webhook_governor: Optional[bool] = None
    styles: Optional[Dict[str, Any]] = None
