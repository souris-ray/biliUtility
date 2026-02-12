import os
import json
import logging
import threading
import copy
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from cryptography.fernet import Fernet
from app import config
from app.models import MessageType, ParsedMessage

logger = logging.getLogger('biliutility.state')

# -------------------------
# Configuration State Management
# -------------------------
class ConfigState:
    def __init__(self):
        self.room_id = None
        self.uid = None
        self.username = None
        self.log_dir = None
        self.is_configured = False
        self.lock = threading.RLock()
        self.config_file = Path(config.DATA_PATH) / 'bilibili_config.json'
        self.load_config()

    def load_config(self):
        """Load config from JSON file if it exists"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.room_id = data.get('room_id')
                    self.uid = data.get('uid')
                    self.username = data.get('username')
                    self.log_dir = data.get('log_dir')
                    self.is_configured = data.get('is_configured', False)
                logger.info(f"[Monitor Config] Loaded config - Room: {self.room_id}, User: {self.username}")
        except Exception as e:
            logger.error(f"[Monitor Config] Error loading config: {e}")

    def save_config(self):
        """Save config to JSON file"""
        try:
            data = {
                'room_id': self.room_id,
                'uid': self.uid,
                'username': self.username,
                'log_dir': self.log_dir,
                'is_configured': self.is_configured
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[Monitor Config] Error saving config: {e}")

    def set_config(self, room_id: str, uid: str, username: str, log_dir: Optional[str] = None):
        with self.lock:
            self.room_id = room_id
            self.uid = uid
            self.username = username
            self.log_dir = log_dir
            self.is_configured = True
            self.save_config()

    def clear_config(self):
        with self.lock:
            self.room_id = None
            self.uid = None
            self.username = None
            self.log_dir = None
            self.is_configured = False
            self.save_config()

    def get_room_id(self, fallback: Optional[str] = None) -> Optional[str]:
        """Get configured room_id or fallback to default"""
        with self.lock:
            return self.room_id if self.is_configured else fallback

    def get_log_dir(self, fallback: Optional[str] = None) -> str:
        """Get configured log_dir or fallback to default"""
        with self.lock:
            return self.log_dir if (self.is_configured and self.log_dir) else fallback

# -------------------------
# TTS Configuration State Management
# -------------------------
class TTSConfigState:
    """Manages TTS engine, voice and speed configuration with JSON persistence"""
    DEFAULT_SETTINGS = {
        'engine': 'kokoro',
        'voice': 'zm_yunjian',
        'speed_normal': 0.9,
        'speed_name': 0.8
    }

    def __init__(self):
        self.engine = self.DEFAULT_SETTINGS['engine']
        self.voice = self.DEFAULT_SETTINGS['voice']
        self.speed_normal = self.DEFAULT_SETTINGS['speed_normal']
        self.speed_name = self.DEFAULT_SETTINGS['speed_name']
        self.lock = threading.RLock()
        self.config_file = Path(config.DATA_PATH) / 'tts_config.json'
        # Note: We don't initialize tts_manager here to avoid circular imports.
        # Logic using tts_manager should be in service layer.
        self.load_config()

    def load_config(self):
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.engine = data.get('engine', self.DEFAULT_SETTINGS['engine'])
                    self.voice = data.get('voice', self.DEFAULT_SETTINGS['voice'])
                    self.speed_normal = data.get('speed_normal', self.DEFAULT_SETTINGS['speed_normal'])
                    self.speed_name = data.get('speed_name', self.DEFAULT_SETTINGS['speed_name'])
                logger.info(f"[TTS Config] Loaded config - Engine: {self.engine}, Voice: {self.voice}")
        except Exception as e:
            logger.error(f"[TTS Config] Error loading config, using defaults: {e}")

    def save_config(self):
        try:
            data = {
                'engine': self.engine,
                'voice': self.voice,
                'speed_normal': self.speed_normal,
                'speed_name': self.speed_name
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"[TTS Config] Error saving config: {e}")

    def update(self, engine=None, voice=None, speed_normal=None, speed_name=None):
        """Update config values and save to file"""
        with self.lock:
            if engine is not None:
                self.engine = engine
            if voice is not None:
                self.voice = voice
            if speed_normal is not None:
                self.speed_normal = float(speed_normal)
            if speed_name is not None:
                self.speed_name = float(speed_name)
            self.save_config()

# -------------------------
# Credentials Management
# -------------------------
class CredentialsManager:
    """Manages encrypted API credentials (AWS, DeepL)"""
    def __init__(self):
        self.key_file = Path(config.DATA_PATH) / '.secret.key'
        self.creds_file = Path(config.DATA_PATH) / 'credentials.json'
        self.fernet = self._load_or_generate_key()
        self.credentials = self.load_credentials()
        self._apply_to_env()

    def _load_or_generate_key(self):
        try:
            if self.key_file.exists():
                key = self.key_file.read_bytes()
            else:
                key = Fernet.generate_key()
                self.key_file.write_bytes(key)
            return Fernet(key)
        except Exception as e:
            logger.error(f"[Credentials] Error initializing encryption key: {e}")
            return Fernet(Fernet.generate_key())

    def load_credentials(self):
        if self.creds_file.exists():
            try:
                with open(self.creds_file, 'r', encoding='utf-8') as f:
                    encrypted_data = json.load(f)
                
                decrypted_data = {}
                for k, v in encrypted_data.items():
                    if v:
                        try:
                            decrypted_data[k] = self.fernet.decrypt(v.encode()).decode()
                        except:
                            decrypted_data[k] = v
                    else:
                        decrypted_data[k] = ""
                return decrypted_data
            except Exception as e:
                logger.error(f"[Credentials] Error loading credentials: {e}")
        
        return {
            "aws_access_key": "",
            "aws_secret_key": "",
            "aws_region": "",
            "deepl_auth_key": "",
            "webhook_url_captain": "",
            "webhook_url_admiral": "",
            "webhook_url_governor": ""
        }

    def save_credentials(self, data):
        encrypted_data = {}
        for k, v in data.items():
            if v:
                encrypted_data[k] = self.fernet.encrypt(v.encode()).decode()
            else:
                encrypted_data[k] = ""
        try:
            with open(self.creds_file, 'w', encoding='utf-8') as f:
                json.dump(encrypted_data, f, indent=4)
            self.credentials = data
            self._apply_to_env()
        except Exception as e:
            logger.error(f"[Credentials] Error saving credentials: {e}")
            raise

    def _apply_to_env(self):
        os.environ['AWS_ACCESS_KEY_ID'] = self.credentials.get('aws_access_key', "")
        os.environ['AWS_SECRET_ACCESS_KEY'] = self.credentials.get('aws_secret_key', "")
        os.environ['AWS_REGION'] = self.credentials.get('aws_region', "us-east-1")
        os.environ['DEEPL_AUTH_KEY'] = self.credentials.get('deepl_auth_key', "")

    def get_webhook_urls(self) -> dict:
        return {
            'captain': self.credentials.get('webhook_url_captain', ''),
            'admiral': self.credentials.get('webhook_url_admiral', ''),
            'governor': self.credentials.get('webhook_url_governor', '')
        }

# -------------------------
# Gift Widget Configuration
# -------------------------
class GiftConfigState:
    DEFAULT_MILESTONE_GOAL = 500
    DEFAULT_TITLE = "惩罚轮盘进度"
    DEFAULT_TITLE_STYLE = {
        'type': 'solid', 'colors': ['#E8D57C'], 'angle': 90, 'glass_blur': 0,
        'glass_opacity': 1.0, 'shadow_color': '#000000', 'shadow_size': 0, 'border_color': '#ffffff', 'border_width': 0
    }
    DEFAULT_BG_STYLE = {
        'type': 'linear', 'colors': ['#9C6C8C', '#5A4F77'], 'angle': 135, 'glass_blur': 0,
        'glass_opacity': 1.0, 'shadow_color': '#000000', 'shadow_size': 0, 'border_color': 'rgba(255, 215, 0, 0)', 'border_width': 0
    }

    def __init__(self):
        self.milestone_goal = self.DEFAULT_MILESTONE_GOAL
        self.title_text = self.DEFAULT_TITLE
        self.title_style = copy.deepcopy(self.DEFAULT_TITLE_STYLE)
        self.show_title = True
        self.background_style = copy.deepcopy(self.DEFAULT_BG_STYLE)
        self.show_background = True
        self.count_color = '#E8D57C'
        self.label_color = 'rgba(255, 255, 255, 0.8)'
        self.progress_bar_start_color = '#E8D57C'
        self.progress_bar_end_color = '#C87041'
        self.lock = threading.RLock()
        self.config_file = Path(config.DATA_PATH) / 'gift_config.json'
        self.load_config()

    def load_config(self):
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.milestone_goal = data.get('milestone_goal', self.DEFAULT_MILESTONE_GOAL)
                    self.title_text = data.get('title_text', self.DEFAULT_TITLE)
                    self.title_style = data.get('title_style', copy.deepcopy(self.DEFAULT_TITLE_STYLE))
                    self.show_title = data.get('show_title', True)
                    self.background_style = data.get('background_style', copy.deepcopy(self.DEFAULT_BG_STYLE))
                    self.show_background = data.get('show_background', True)
                    self.count_color = data.get('count_color', '#E8D57C')
                    self.label_color = data.get('label_color', 'rgba(255, 255, 255, 0.8)')
                    self.progress_bar_start_color = data.get('progress_bar_start_color', '#E8D57C')
                    self.progress_bar_end_color = data.get('progress_bar_end_color', '#C87041')
        except Exception as e:
            logger.error(f"[Gift Config] Error loading config: {e}")

    def save_config(self):
        try:
            data = {
                'milestone_goal': self.milestone_goal,
                'title_text': self.title_text,
                'title_style': self.title_style,
                'show_title': self.show_title,
                'background_style': self.background_style,
                'show_background': self.show_background,
                'count_color': self.count_color,
                'label_color': self.label_color,
                'progress_bar_start_color': self.progress_bar_start_color,
                'progress_bar_end_color': self.progress_bar_end_color
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[Gift Config] Error saving config: {e}")

    def update(self, **kwargs):
        with self.lock:
            for k, v in kwargs.items():
                if hasattr(self, k) and v is not None:
                    setattr(self, k, v)
                    # Handle type conversion if needed
                    if k == 'milestone_goal':
                         self.milestone_goal = int(v)
            self.save_config()
            
    def get_milestone_goal(self) -> int:
        with self.lock:
            return self.milestone_goal

    def get_config(self) -> dict:
        with self.lock:
            return {
                'milestone_goal': self.milestone_goal,
                'title_text': self.title_text,
                'title_style': self.title_style,
                'show_title': self.show_title,
                'background_style': self.background_style,
                'show_background': self.show_background,
                'count_color': self.count_color,
                'label_color': self.label_color,
                'progress_bar_start_color': self.progress_bar_start_color,
                'progress_bar_end_color': self.progress_bar_end_color
            }

# -------------------------
# Member Widget Configuration
# -------------------------
class MemberConfigState:
    DEFAULT_GIFS = {
        'captain': 'souris_captain.png',
        'admiral': 'souris_admiral.png',
        'governor': 'souris_governor.png'
    }
    DEFAULT_THANK_YOU_TEXT = "感谢您加入舰队！"
    DEFAULT_STYLES_PER_TIER = {
        'bg_style': { 'type': 'solid', 'colors': ['rgba(50, 40, 80, 0.95)'], 'angle': 90, 'glass_blur': 0, 'glass_opacity': 1.0, 'shadow_color': '#000000', 'shadow_size': 0, 'border_color': 'rgba(100, 200, 255, 0.8)', 'border_width': 2 },
        'name_style': { 'type': 'solid', 'colors': ['#FFD700'], 'angle': 90, 'shadow_color': '#000000', 'shadow_size': 0 },
        'rank_style': { 'type': 'solid', 'colors': ['#87CEEB'], 'angle': 90, 'shadow_color': '#000000', 'shadow_size': 0 }
    }

    def __init__(self):
        self.custom_gifs = {}
        self.thank_you_text = self.DEFAULT_THANK_YOU_TEXT
        self.show_member_info = True
        self.enable_webhook_captain = False
        self.enable_webhook_admiral = False
        self.enable_webhook_governor = False
        self.styles = {
            'captain': copy.deepcopy(self.DEFAULT_STYLES_PER_TIER),
            'admiral': copy.deepcopy(self.DEFAULT_STYLES_PER_TIER),
            'governor': copy.deepcopy(self.DEFAULT_STYLES_PER_TIER)
        }
        self.lock = threading.RLock()
        self.config_file = Path(config.DATA_PATH) / 'member_config.json'
        self.load_config()

    def load_config(self):
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.custom_gifs = data.get('custom_gifs', {})
                    self.thank_you_text = data.get('thank_you_text', self.DEFAULT_THANK_YOU_TEXT)
                    self.show_member_info = data.get('show_member_info', True)
                    self.enable_webhook_captain = data.get('enable_webhook_captain', False)
                    self.enable_webhook_admiral = data.get('enable_webhook_admiral', False)
                    self.enable_webhook_governor = data.get('enable_webhook_governor', False)
                    
                    saved_styles = data.get('styles', {})
                    if 'captain' in saved_styles or 'admiral' in saved_styles:
                         for tier in ['captain', 'admiral', 'governor']:
                            if tier in saved_styles:
                                self.styles[tier] = saved_styles[tier]
                    else:
                        # Legacy support omitted for brevity, assuming migrated
                         pass

        except Exception as e:
            logger.error(f"[Member Config] Error loading config: {e}")

    def save_config(self):
        try:
            data = {
                'custom_gifs': self.custom_gifs,
                'thank_you_text': self.thank_you_text,
                'show_member_info': self.show_member_info,
                'enable_webhook_captain': self.enable_webhook_captain,
                'enable_webhook_admiral': self.enable_webhook_admiral,
                'enable_webhook_governor': self.enable_webhook_governor,
                'styles': self.styles
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[Member Config] Error saving config: {e}")

    def update(self, **kwargs):
        with self.lock:
            if 'styles' in kwargs and kwargs['styles'] is not None:
                self.styles = kwargs['styles']
            
            # Legacy/Partial updates
            for tier in ['captain', 'admiral', 'governor']:
                if tier in kwargs and isinstance(kwargs[tier], dict):
                    self.styles[tier] = kwargs[tier]

            if 'show_member_info' in kwargs and kwargs['show_member_info'] is not None:
                self.show_member_info = bool(kwargs['show_member_info'])
            
            if 'thank_you_text' in kwargs and kwargs['thank_you_text'] is not None:
                self.thank_you_text = str(kwargs['thank_you_text'])

            if 'enable_webhook_captain' in kwargs and kwargs['enable_webhook_captain'] is not None:
                self.enable_webhook_captain = bool(kwargs['enable_webhook_captain'])
            if 'enable_webhook_admiral' in kwargs and kwargs['enable_webhook_admiral'] is not None:
                self.enable_webhook_admiral = bool(kwargs['enable_webhook_admiral'])
            if 'enable_webhook_governor' in kwargs and kwargs['enable_webhook_governor'] is not None:
                self.enable_webhook_governor = bool(kwargs['enable_webhook_governor'])
                
            self.save_config()

    def get_config(self) -> dict:
        with self.lock:
            gifs = {}
            for tier in ['captain', 'admiral', 'governor']:
                is_custom = tier in self.custom_gifs
                url = f"/static/{self.custom_gifs.get(tier, self.DEFAULT_GIFS.get(tier))}"
                gifs[tier] = {'url': url, 'is_custom': is_custom}
            
            return {
                'styles': copy.deepcopy(self.styles),
                'show_member_info': self.show_member_info,
                'thank_you_text': self.thank_you_text,
                'enable_webhook_captain': self.enable_webhook_captain,
                'enable_webhook_admiral': self.enable_webhook_admiral,
                'enable_webhook_governor': self.enable_webhook_governor,
                'gifs': gifs
            }
    
    def get_gif(self, tier: str) -> str:
        with self.lock:
            return self.custom_gifs.get(tier, self.DEFAULT_GIFS.get(tier))

    def set_gif(self, tier: str, filename: str, is_custom: bool = True):
        with self.lock:
            if is_custom:
                self.custom_gifs[tier] = filename
            elif tier in self.custom_gifs:
                del self.custom_gifs[tier]
            self.save_config()

    def reset_gif(self, tier: str):
        self.set_gif(tier, "", is_custom=False)

# -------------------------
# Voting Configuration
# -------------------------
class VotingConfigState:
    DEFAULT_TITLE = "Chat Voting"
    DEFAULT_TITLE_STYLE = { 'type': 'linear', 'colors': ['#E8D57C', '#CAAD8E'], 'angle': 135, 'glass_blur': 0, 'glass_opacity': 1.0, 'shadow_color': '#000000', 'shadow_size': 0, 'border_color': '#ffffff', 'border_width': 0 }
    DEFAULT_BG_STYLE = { 'type': 'linear', 'colors': ['rgba(90, 79, 119, 0.8)', 'rgba(156, 108, 140, 0.8)'], 'angle': 135, 'glass_blur': 0, 'glass_opacity': 1.0, 'shadow_color': '#000000', 'shadow_size': 0, 'border_color': 'rgba(255, 215, 0, 0.3)', 'border_width': 2 }
    DEFAULT_OPTION_STYLE = { 'type': 'linear', 'colors': ['#E8D57C', '#CAAD8E'], 'angle': 135, 'glass_blur': 0, 'glass_opacity': 1.0, 'shadow_color': '#000000', 'shadow_size': 0, 'border_color': '#ffffff', 'border_width': 0 }
    DEFAULT_BAR_BG_STYLE = { 'type': 'solid', 'colors': ['rgba(0, 0, 0, 0.3)'], 'angle': 90, 'glass_blur': 0, 'glass_opacity': 1.0, 'shadow_color': '#000000', 'shadow_size': 0, 'border_color': '#ffffff', 'border_width': 0 }
    DEFAULT_BAR_FILL_STYLE = { 'type': 'linear', 'colors': ['#3498db', '#D6EFFF'], 'angle': 90, 'glass_blur': 0, 'glass_opacity': 1.0, 'shadow_color': '#000000', 'shadow_size': 0, 'border_color': '#ffffff', 'border_width': 0 }
    DEFAULT_BAR_TEXT_STYLE = { 'type': 'solid', 'colors': ['#ffffff'], 'angle': 90, 'glass_blur': 0, 'glass_opacity': 1.0, 'shadow_color': '#000000', 'shadow_size': 4, 'border_color': '#ffffff', 'border_width': 0 }

    def __init__(self):
        self.lock = threading.RLock()
        self.config_file = Path(config.DATA_PATH) / 'voting_config.json'
        self.is_active = False
        self.title = self.DEFAULT_TITLE
        self.options: List[str] = []
        self.vote_counts: List[int] = []
        self.title_style = copy.deepcopy(self.DEFAULT_TITLE_STYLE)
        self.show_title = True
        self.background_style = copy.deepcopy(self.DEFAULT_BG_STYLE)
        self.show_background = True
        self.option_style = copy.deepcopy(self.DEFAULT_OPTION_STYLE)
        self.bar_bg_style = copy.deepcopy(self.DEFAULT_BAR_BG_STYLE)
        self.bar_fill_style = copy.deepcopy(self.DEFAULT_BAR_FILL_STYLE)
        self.bar_text_style = copy.deepcopy(self.DEFAULT_BAR_TEXT_STYLE)
        self.load_config()

    def load_config(self):
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.title = data.get('title', self.DEFAULT_TITLE)
                    self.title_style = data.get('title_style', copy.deepcopy(self.DEFAULT_TITLE_STYLE))
                    self.show_title = data.get('show_title', True)
                    self.background_style = data.get('background_style', copy.deepcopy(self.DEFAULT_BG_STYLE))
                    self.show_background = data.get('show_background', True)
                    self.option_style = data.get('option_style', copy.deepcopy(self.DEFAULT_OPTION_STYLE))
                    self.bar_bg_style = data.get('bar_bg_style', copy.deepcopy(self.DEFAULT_BAR_BG_STYLE))
                    self.bar_fill_style = data.get('bar_fill_style', copy.deepcopy(self.DEFAULT_BAR_FILL_STYLE))
                    self.bar_text_style = data.get('bar_text_style', copy.deepcopy(self.DEFAULT_BAR_TEXT_STYLE))
        except Exception as e:
            logger.error(f"[Voting Config] Error loading config: {e}")

    def save_config(self):
        try:
            data = {
                'title': self.title,
                'title_style': self.title_style,
                'show_title': self.show_title,
                'background_style': self.background_style,
                'show_background': self.show_background,
                'option_style': self.option_style,
                'bar_bg_style': self.bar_bg_style,
                'bar_fill_style': self.bar_fill_style,
                'bar_text_style': self.bar_text_style
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[Voting Config] Error saving config: {e}")
            
    def start_voting(self, title: str, options: List[str], show_title: bool = None, show_background: bool = None):
        with self.lock:
            self.title = title
            self.options = options
            self.vote_counts = [0] * len(options)
            self.is_active = True
            if show_title is not None:
                self.show_title = show_title
            if show_background is not None:
                self.show_background = show_background
            self.save_config()
            return self.get_state()

    def stop_voting(self):
        with self.lock:
            self.is_active = False
            return self.get_state()

    def reset_voting(self):
        with self.lock:
            self.title = self.DEFAULT_TITLE
            self.options = []
            self.vote_counts = []
            self.is_active = False
            self.save_config()
            return self.get_state()

    def update_styles(self, data: dict):
        with self.lock:
            if 'title' in data:
                self.title = data['title']
            if 'title_style' in data:
                self.title_style = data['title_style']
            if 'show_title' in data:
                self.show_title = bool(data['show_title'])
            if 'background_style' in data:
                self.background_style = data['background_style']
            if 'show_background' in data:
                self.show_background = bool(data['show_background'])
            if 'option_style' in data:
                self.option_style = data['option_style']
            if 'bar_bg_style' in data:
                self.bar_bg_style = data['bar_bg_style']
            if 'bar_fill_style' in data:
                self.bar_fill_style = data['bar_fill_style']
            if 'bar_text_style' in data:
                self.bar_text_style = data['bar_text_style']
            
            self.save_config()
            return self.get_state()
            
    def register_vote(self, index: int):
        with self.lock:
            if not self.is_active:
                return False
            if 0 <= index < len(self.vote_counts):
                self.vote_counts[index] += 1
                return True
            return False

    def get_state(self):
        with self.lock:
            return {
                'title': self.title,
                'title_style': self.title_style,
                'show_title': self.show_title,
                'background_style': self.background_style,
                'show_background': self.show_background,
                'option_style': self.option_style,
                'bar_bg_style': self.bar_bg_style,
                'bar_fill_style': self.bar_fill_style,
                'bar_text_style': self.bar_text_style,
                'options': [{'idx': i, 'text': opt} for i, opt in enumerate(self.options)],
                'vote_counts': list(self.vote_counts),
                'is_active': self.is_active
            }


# -------------------------
# Sound Configuration
# -------------------------
class SoundConfigState:
    def __init__(self):
        self.lock = threading.RLock()
        self.config_file = Path(config.DATA_PATH) / 'sound_config.json'
        self.commands = {}
        self.load_config()

    def load_config(self):
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    raw_commands = data.get('commands', {})
                    for trigger, value in raw_commands.items():
                        if isinstance(value, str):
                            self.commands[trigger] = {'filename': value, 'volume': 1.0}
                        elif isinstance(value, dict):
                            self.commands[trigger] = {
                                'filename': value.get('filename', ''),
                                'volume': value.get('volume', 1.0)
                            }
        except Exception as e:
            logger.error(f"[Sound Config] Error loading config: {e}")

    def save_config(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump({'commands': self.commands}, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[Sound Config] Error saving config: {e}")

    def get_commands(self) -> Dict[str, dict]:
        with self.lock:
            return copy.deepcopy(self.commands)
    
    def get_command_info(self, trigger: str) -> dict:
        with self.lock:
            return self.commands.get(trigger, {}).copy()

    def update_command(self, trigger: str, filename: str):
        with self.lock:
            if trigger not in self.commands:
                self.commands[trigger] = {'filename': filename, 'volume': 1.0}
            else:
                self.commands[trigger]['filename'] = filename
            self.save_config()

    def delete_command(self, trigger: str):
        with self.lock:
            if trigger in self.commands:
                del self.commands[trigger]
                self.save_config()

    def update_volume(self, trigger: str, volume: float):
        with self.lock:
            if trigger in self.commands:
                self.commands[trigger]['volume'] = volume
                self.save_config()


# -------------------------
# Member Progress Configuration
# -------------------------
class MemberProgressConfigState:
    DEFAULT_TITLE = "冲舰"
    DEFAULT_STYLE = { "type": "solid", "colors": ["#E8D57C"], "angle": 90, "glass_blur": 0, "glass_opacity": 1.0, "shadow_color": "#000000", "shadow_size": 0, "border_color": "#ffffff", "border_width": 0 }
    DEFAULT_BG_STYLE = { "type": "solid", "colors": ["#5A4F77"], "angle": 135, "glass_blur": 0, "glass_opacity": 1.0, "shadow_color": "#000000", "shadow_size": 0, "border_color": "rgba(255, 215, 0, 0)", "border_width": 0 }
    DEFAULT_LEVELS = [
        {"min": 0, "max": 50, "image": "souris_captain.png", "is_custom": False, "start_color": "#3498db", "end_color": "#5dade2"},
        {"min": 50, "max": 100, "image": "souris_admiral.png", "is_custom": False, "start_color": "#9b59b6", "end_color": "#bb8fce"},
        {"min": 100, "max": 999999, "image": "souris_governor.png", "is_custom": False, "start_color": "#f1c40f", "end_color": "#f7dc6f"}
    ]

    def __init__(self):
        self.lock = threading.RLock()
        self.config_file = Path(config.DATA_PATH) / 'member_progress.json'
        self.title_text = self.DEFAULT_TITLE
        self.title_style = self.DEFAULT_STYLE.copy()
        self.show_title = True
        self.background_style = self.DEFAULT_BG_STYLE.copy()
        self.show_background = True
        self.count_color = '#ffffff'
        self.label_color = 'rgba(255, 255, 255, 0.8)'
        self.image_size = 80
        self.levels = self.DEFAULT_LEVELS.copy()
        self.load_config()

    def load_config(self):
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.title_text = data.get('title_text', self.DEFAULT_TITLE)
                    self.show_title = data.get('show_title', True)
                    self.show_background = data.get('show_background', True)
                    self.title_style = data.get('title_style', copy.deepcopy(self.DEFAULT_STYLE))
                    self.background_style = data.get('background_style', copy.deepcopy(self.DEFAULT_BG_STYLE))
                    self.levels = data.get('levels', copy.deepcopy(self.DEFAULT_LEVELS))
                    self.count_color = data.get('count_color', '#ffffff')
                    self.label_color = data.get('label_color', 'rgba(255, 255, 255, 0.8)')
                    self.image_size = data.get('image_size', 80)
        except Exception as e:
            logger.error(f"[Member Progress] Error loading config: {e}")

    def save_config(self):
        try:
            data = {
                'title_text': self.title_text,
                'title_style': self.title_style,
                'show_title': self.show_title,
                'background_style': self.background_style,
                'show_background': self.show_background,
                'count_color': self.count_color,
                'label_color': self.label_color,
                'image_size': self.image_size,
                'levels': self.levels
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[Member Progress] Error saving config: {e}")
            
    def update(self, **kwargs):
        with self.lock:
            for k, v in kwargs.items():
                if hasattr(self, k) and v is not None:
                    setattr(self, k, v)
            self.save_config()

    def set_level_image(self, index, filename, is_custom=True):
        with self.lock:
            if 0 <= index < len(self.levels):
                self.levels[index]['image'] = filename
                self.levels[index]['is_custom'] = is_custom
                self.save_config()

    def get_config(self) -> dict:
        with self.lock:
            return {
                'title_text': self.title_text,
                'title_style': self.title_style,
                'show_title': self.show_title,
                'background_style': self.background_style,
                'show_background': self.show_background,
                'count_color': self.count_color,
                'label_color': self.label_color,
                'image_size': self.image_size,
                'levels': copy.deepcopy(self.levels)
            }



# -------------------------
# File Persistence Tracker
# -------------------------
class ProcessedFilesTracker:
    """Tracks which log files have been processed to avoid reprocessing"""
    def __init__(self):
        self.TRACKING_FILE = Path(config.LOG_PATH) / 'accessed_file.txt'
        self._processed: set = set()
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        try:
            if self.TRACKING_FILE.exists():
                with open(self.TRACKING_FILE, 'r') as f:
                    self._processed = set(line.strip() for line in f if line.strip())
        except Exception:
            self._processed = set()

    def is_processed(self, filename: str) -> bool:
        with self._lock:
            return filename in self._processed

    def mark_processed(self, filename: str):
        with self._lock:
            if filename not in self._processed:
                self._processed.add(filename)
                with open(self.TRACKING_FILE, 'a') as f:
                    f.write(f"{filename}\n")

# -------------------------
# Shared State for Widgets (ASYNC)
# -------------------------
class WidgetState:
    def __init__(self):
        # Numeric state can still be sync-accessed if we are careful,
        # but for safety in async endpoint context, we should use asyncio.Lock or keep it atomic.
        # Since we have hybrid usage (some background tasks might be sync or threaded), 
        # we might need both locks or be very careful. 
        # For now, we assume ALL access to WidgetState will be from Async Context (FastAPI/SocketIO)
        # OR from the LogWatcher which we will rewrite to be Async.
        
        self.paid_gift_total_value = 0.0
        self.paid_gift_count = 0
        self.superchat_total_value = 0.0
        self.membership_total_value = 0.0
        self.guard_counts: Dict[str, int] = {}
        self.milestone_progress = 0.0
        self.milestone_count = 0
        self.total_guard_count = 0
        self.initial_guard_count = 0
        self.recent_messages: List[ParsedMessage] = []
        
        self.lock = asyncio.Lock()

        # TTS state
        self.tts_queue: asyncio.Queue = asyncio.Queue()
        self.tts_playing: Optional[ParsedMessage] = None
        self.tts_autoplay = False
        self.tts_messages: Dict[str, ParsedMessage] = {}

        # Member display state
        self.member_queue: asyncio.Queue = asyncio.Queue()
        self.current_member: Optional[ParsedMessage] = None

        self.file_tracker = ProcessedFilesTracker()

    async def set_initial_guard_count(self, count: int):
        async with self.lock:
            self.initial_guard_count = count
            self.total_guard_count = count

    async def add_message(self, message: ParsedMessage):
        """Async method to add message and update state"""
        async with self.lock:
            self.recent_messages.append(message)
            if message.tts_enabled and message.unique_id:
                self.tts_messages[message.unique_id] = message

            if message.type == MessageType.PAID_GIFT:
                self.paid_gift_total_value += message.content.get('value', 0)
                self.paid_gift_count += message.content.get('quantity', 0)
                self.milestone_progress += message.content.get('value', 0)
                milestone_goal = gift_config.get_milestone_goal()
                while self.milestone_progress >= milestone_goal:
                    self.milestone_progress -= milestone_goal
                    self.milestone_count += 1

            elif message.type == MessageType.GUARD:
                guard_type = message.content.get('guard_type')
                duration = message.content.get('duration', 1)
                
                if guard_type:
                    self.guard_counts[guard_type] = self.guard_counts.get(guard_type, 0) + duration
                self.total_guard_count += duration
                
                membership_price = message.content.get('value', 0.0)
                self.membership_total_value += membership_price
                self.milestone_progress += membership_price
                milestone_goal = gift_config.get_milestone_goal()
                while self.milestone_progress >= milestone_goal:
                    self.milestone_progress -= milestone_goal
                    self.milestone_count += 1

                # Enqueue member
                await self.member_queue.put(message)
                
                if self.tts_autoplay and not message.is_read:
                    await self.tts_queue.put((message, True))

            elif message.type == MessageType.SUPERCHAT:
                self.superchat_total_value += message.content.get('amount', 0)
                self.milestone_progress += message.content.get('amount', 0)
                milestone_goal = gift_config.get_milestone_goal()
                while self.milestone_progress >= milestone_goal:
                    self.milestone_progress -= milestone_goal
                    self.milestone_count += 1
    
                if self.tts_autoplay and not message.is_read:
                    await self.tts_queue.put((message, True))

    async def recalculate_milestones(self, new_goal: int):
        """Recalculate milestone progress and count based on a new goal"""
        async with self.lock:
            if new_goal <= 0:
                return

            total_revenue = (
                self.paid_gift_total_value + 
                self.membership_total_value + 
                self.superchat_total_value
            )
            
            self.milestone_count = int(total_revenue // new_goal)
            self.milestone_progress = total_revenue % new_goal
            
            logger.info(f"[State] Recalculated milestones. Total Revenue: {total_revenue}, New Goal: {new_goal}, Count: {self.milestone_count}, Progress: {self.milestone_progress}")
    
    async def get_next_member(self) -> Optional[ParsedMessage]:
        try:
            return self.member_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def get_member_queue_size(self) -> int:
        return self.member_queue.qsize()
    
    async def get_state(self):
        async with self.lock:
            return {
                'paid_gift_total_value': self.paid_gift_total_value,
                'paid_gift_count': self.paid_gift_count,
                'guard_counts': self.guard_counts.copy(),
                'milestone_progress': self.milestone_progress,
                'milestone_count': self.milestone_count,
                'total_guard_count': self.total_guard_count
            }
            
    async def toggle_message_read_status(self, unique_id: str) -> bool:
        async with self.lock:
            if unique_id in self.tts_messages:
                msg = self.tts_messages[unique_id]
                msg.is_read = not msg.is_read
                return msg.is_read
        return False
        
    async def get_unread_tts_messages(self) -> List[ParsedMessage]:
        async with self.lock:
             return [msg for msg in self.tts_messages.values() if not msg.is_read]

# Initialize global state instances
credentials_manager = CredentialsManager()
monitor_config = ConfigState()
tts_config = TTSConfigState()
gift_config = GiftConfigState()
member_config = MemberConfigState()
voting_config = VotingConfigState()
sound_config = SoundConfigState()
member_progress_config = MemberProgressConfigState()

# Main application state (async)
state = WidgetState()
