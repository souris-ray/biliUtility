from fastapi import APIRouter
import os
import signal
import logging
from app.state import credentials_manager, monitor_config, tts_config
from app.models import CredentialsUpdate
from tts_engines.manager import tts_manager
import json

router = APIRouter(prefix="/api", tags=["system"])
logger = logging.getLogger('biliutility.system')

@router.post("/shutdown")
async def shutdown():
    """Shutdown the application"""
    logger.info("Shutdown requested via API")
    # In Uvicorn, we can trigger shutdown by sending SIGTERM to self or raising SystemExit
    # But usually sending SIGINT/SIGTERM to the process is cleaner.
    os.kill(os.getpid(), signal.SIGINT)
    return {"status": "shutting_down"}

@router.get("/credentials")
async def get_credentials():
    return {
        "success": True,
        "credentials": credentials_manager.credentials
    }

@router.post("/credentials")
async def save_credentials(data: CredentialsUpdate):
    credentials_manager.save_credentials({
        "aws_access_key": data.aws_access_key,
        "aws_secret_key": data.aws_secret_key,
        "aws_region": data.aws_region,
        "deepl_auth_key": data.deepl_auth_key,
        "webhook_url_captain": str(data.webhook_url_captain) if data.webhook_url_captain else "",
        "webhook_url_admiral": str(data.webhook_url_admiral) if data.webhook_url_admiral else "",
        "webhook_url_governor": str(data.webhook_url_governor) if data.webhook_url_governor else ""
    })
    
    # Dispose current TTS engine to ensure new credentials (like AWS) are picked up
    tts_manager.dispose_current()
    
    return {"success": True, "message": "Credentials saved"}

from app.infrastructure.http_client import BiliHTTPClient
from fastapi import Body

# Helper functions for validation
def fetch_user_info(uid: int):
    data = BiliHTTPClient.get(
        "https://api.live.bilibili.com/xlive/app-ucenter/v2/card/user",
        params={"uid": uid, "ruid": uid},
        timeout=5
    )
    if data:
        return {
            'username': data['uname'],
            'face': data['face'],
            'desc': data.get('desc', '')
        }
    return None

def fetch_room_owner_uid(room_id: int):
    data = BiliHTTPClient.get(
        "https://api.live.bilibili.com/room/v1/Room/get_info",
        params={"room_id": room_id},
        timeout=5
    )
    if data:
        return data.get('uid')
    return None

def fetch_initial_guard_count(room_id: int, uid: int) -> int:
    """Fetch initial guard count for a room"""
    data = BiliHTTPClient.get(
        "https://api.live.bilibili.com/xlive/app-room/v2/guardTab/topList",
        params={"roomid": room_id, "page": 1, "ruid": uid, "page_size": 1}
    )
    if data and 'info' in data:
        return data['info'].get('num', 0)
    return 0

@router.post("/validate_credentials")
async def validate_credentials(data: dict = Body(...)):
    """Validate room_id and uid, return user info if valid"""
    try:
        room_id = str(data.get('room_id', '')).strip()
        uid = str(data.get('uid', '')).strip()

        if not room_id or not uid:
            return {'success': False, 'error': 'Room ID and UID are required'}

        try:
            room_id_int = int(room_id)
            uid_int = int(uid)
        except ValueError:
            return {'success': False, 'error': 'Invalid Room ID or UID format'}

        # Fetch user info
        user_info = fetch_user_info(uid_int)
        if not user_info:
            return {'success': False, 'error': 'Unable to validate credentials. Please check your UID.'}

        # Fetch room owner UID
        room_owner_uid = fetch_room_owner_uid(room_id_int)
        if not room_owner_uid:
            return {'success': False, 'error': 'Unable to fetch room information. Please check your Room ID.'}

        # Validate UID matches room owner
        if room_owner_uid != uid_int:
            return {'success': False, 'error': 'The Room ID does not belong to this UID. Please verify your credentials.'}

        return {
            'success': True,
            'username': user_info['username'],
            'face': user_info['face'],
            'desc': user_info['desc']
        }
    except Exception as e:
        logger.error(f"[validate_credentials] Error: {e}")
        return {'success': False, 'error': 'Unable to validate credentials. Please check and try again.'}

@router.post("/start_monitoring")
async def start_monitoring(data: dict = Body(...)):
    """Start monitoring with validated credentials"""
    try:
        room_id = (data.get('room_id') or '').strip()
        uid = (data.get('uid') or '').strip()
        username = (data.get('username') or '').strip()
        log_dir_raw = data.get('log_dir')
        log_dir = log_dir_raw.strip() if log_dir_raw else None

        if not room_id or not uid or not username:
            return {'success': False, 'error': 'Missing required fields'}

        # Store configuration
        monitor_config.set_config(room_id, uid, username, log_dir)
        
        # Fetch initial guard count
        from app.state import state as app_state
        initial_count = fetch_initial_guard_count(int(room_id), int(uid))
        await app_state.set_initial_guard_count(initial_count)
        
        return {'success': True, 'message': 'Monitoring started successfully', 'initial_count': initial_count}
    except Exception as e:
        logger.error(f"[start_monitoring] Error: {e}")
        return {'success': False, 'error': 'Failed to start monitoring'}

@router.post("/reset_config")
async def reset_config():
    """Reset configuration (logout)"""
    try:
        monitor_config.clear_config()
        return {'success': True, 'message': 'Configuration reset successfully'}
    except Exception as e:
        logger.error(f"[reset_config] Error: {e}")
        return {'success': False, 'error': 'Failed to reset configuration'}