from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Form
from typing import Dict, Any
import time
from pathlib import Path
import json
import logging

from app import config
from app.models import (
    ConfigUpdate, TTSConfigUpdate, GiftConfigUpdate, MemberConfigUpdate
)
from app.state import (
    monitor_config, tts_config, gift_config, member_config, member_progress_config, MemberProgressConfigState, state
)
from app.routers.sockets import sio

router = APIRouter(prefix="/api", tags=["config"])

# Monitor Config
@router.get("/get_config")
async def get_config():
    return {
        "room_id": monitor_config.room_id,
        "uid": monitor_config.uid,
        "username": monitor_config.username,
        "log_dir": monitor_config.log_dir,
        "is_configured": monitor_config.is_configured
    }

@router.post("/save_config")
async def save_config(data: ConfigUpdate):
    monitor_config.set_config(
        room_id=data.room_id,
        uid=data.uid,
        username=data.username,
        log_dir=data.log_dir
    )
    # Restart logic is handled by frontend calling /shutdown or separate restart endpoint?
    # In legacy, save_config didn't auto-restart watcher.
    return {"success": True, "message": "Configuration saved"}

# TTS Config
@router.get("/get_tts_config")
@router.get("/tts/get_config")
async def get_tts_config():
    # Only expose safe values
    from tts_engines.manager import tts_manager
    return {
        "engine": tts_config.engine,
        "voice": tts_config.voice,
        "speed_normal": tts_config.speed_normal,
        "speed_name": tts_config.speed_name,
        "available_voices": tts_manager.get_voices_by_type(tts_config.engine),
        "defaults": tts_config.DEFAULT_SETTINGS,
        "is_kokoro_available": tts_manager.is_engine_available('kokoro'),
        "is_aws_available": tts_manager.is_engine_available('aws_polly')
    }

@router.post("/save_tts_config")
@router.post("/tts/update_config")
async def save_tts_config(data: TTSConfigUpdate):
    from tts_engines.manager import tts_manager
    
    # If engine changed, switch it in manager
    if data.engine and data.engine != tts_config.engine:
        tts_manager.switch_engine(data.engine)
    
    tts_config.update(
        engine=data.engine,
        voice=data.voice,
        speed_normal=data.speed_normal,
        speed_name=data.speed_name
    )
    
    # Update manager's internal config for the current engine
    tts_manager.update_config(
        voice=tts_config.voice,
        speed_normal=tts_config.speed_normal,
        speed_name=tts_config.speed_name
    )
    
    config_data = {
        "engine": tts_config.engine,
        "voice": tts_config.voice,
        "speed_normal": tts_config.speed_normal,
        "speed_name": tts_config.speed_name
    }
    
    await sio.emit('tts:config_updated', config_data)
    
    return {
        "success": True, 
        "message": "TTS Configuration saved",
        "config": config_data,
        "available_voices": tts_manager.get_voices_by_type(tts_config.engine)
    }

@router.get("/tts/voices")
async def get_tts_voices(engine: str):
    from tts_engines.manager import tts_manager
    voices = tts_manager.get_voices_by_type(engine)
    return {"success": True, "voices": voices}

@router.post("/tts/test")
async def test_tts(data: Dict[str, Any]):
    from tts_engines.manager import tts_manager
    from fastapi.responses import Response
    import io
    
    logger = logging.getLogger('biliutility.config')
    try:
        engine_type = data.get('engine', tts_config.engine)
        voice = data.get('voice', tts_config.voice)
        speed = data.get('speed', tts_config.speed_normal)
        text = data.get('text', "你好，这是一个测试。")
        
        logger.info(f"Testing TTS: Engine={engine_type}, Voice={voice}, Speed={speed}")
        
        # Check if engine is actually available
        if not tts_manager.is_engine_available(engine_type):
            msg = f"Engine {engine_type} is not available (Missing credentials or package)"
            logger.error(msg)
            return Response(content=json.dumps({"success": False, "error": msg}), status_code=400, media_type="application/json")

        current_engine = tts_manager.switch_engine(engine_type)
        if not current_engine:
             logger.error(f"Failed to switch to engine: {engine_type}")
             return Response(content=json.dumps({"success": False, "error": f"Invalid engine: {engine_type}"}), status_code=400, media_type="application/json")

        logger.info(f"Generating audio with {current_engine.get_engine_name()}...")
        try:
            audio_buffer = current_engine.generate_audio(text, voice, speed)
        except Exception as audio_err:
            error_msg = str(audio_err)
            if "InvalidSignatureException" in error_msg or "InvalidClientTokenId" in error_msg:
                user_msg = "AWS Polly: Authentication failed. Please check your Access Key and Secret Key in API Settings."
            elif "AccessDenied" in error_msg:
                user_msg = "AWS Polly: Access Denied. Your credentials don't have permission for Polly."
            else:
                user_msg = f"Audio generation failed: {error_msg}"
            
            logger.error(f"TTS Audio Generation Error: {error_msg}")
            return Response(content=json.dumps({"success": False, "error": user_msg}), status_code=500, media_type="application/json")

        if not audio_buffer:
            logger.error("Audio generation returned empty buffer")
            return Response(content=json.dumps({"success": False, "error": "Failed to generate audio"}), status_code=500, media_type="application/json")
            
        logger.info("TTS Test audio generated successfully")
        return Response(content=audio_buffer.getvalue(), media_type="audio/wav")
    except Exception as e:
        logger.error(f"TTS Test Global Error: {e}")
        return Response(content=json.dumps({"success": False, "error": str(e)}), status_code=500, media_type="application/json")

# Gift Config
@router.get("/get_gift_config")
@router.get("/gifts/get_config")
async def get_gift_config():
    return gift_config.get_config()

@router.post("/save_gift_config")
@router.post("/gifts/save_config")
@router.post("/gifts/update_config")
async def save_gift_config(data: GiftConfigUpdate):
    from app.routers.sockets import logger as socket_logger
    socket_logger.info(f"Received gift config update: {data}")
    
    # Recalculate if goal changed
    if data.milestone_goal is not None and data.milestone_goal > 0:
        await state.recalculate_milestones(data.milestone_goal)
    
    gift_config.update(
        milestone_goal=data.milestone_goal,
        title_text=data.title_text,
        title_style=data.title_style,
        show_title=data.show_title,
        background_style=data.background_style,
        show_background=data.show_background,
        count_color=data.count_color,
        label_color=data.label_color,
        progress_bar_start_color=data.progress_bar_start_color,
        progress_bar_end_color=data.progress_bar_end_color
    )
    
    config_snapshot = gift_config.get_config()
    
    # Inject current progress/count into snapshot so widget updates immediately
    current_state = await state.get_state() if hasattr(state, 'get_state') else {
        'milestone_progress': state.milestone_progress,
        'milestone_count': state.milestone_count
    }
    
    # Ensure attributes exist (WidgetState usually has attributes directly accessible if not using get_state)
    # But since we are in async context and just called recalculate, we can access them.
    # However, wait, state.get_state() method does not exist in the code I viewed earlier for WidgetState!
    # I should simply access attributes or use the lock if I want to be 100% safe, 
    # but accessing safely after await is usually fine in this single-threaded event loop context (unless threaded).
    # Ideally I should add a get_state method or just access attributes. 
    # Let's access attributes directly for now as they are on the instance.
    
    config_snapshot['milestone_progress'] = state.milestone_progress
    config_snapshot['milestone_count'] = state.milestone_count
    
    socket_logger.info(f"Emitting gift config update: {config_snapshot}")
    
    # Emit update to widgets
    await sio.emit('gifts:config_updated', config_snapshot)
    return {"success": True}

# Member Config
@router.get("/get_member_config")
@router.get("/members/get_config")
async def get_member_config():
    return member_config.get_config()

@router.post("/save_member_config_styles")
@router.post("/members/save_config_styles")
@router.post("/members/update_config_styles")
@router.post("/members/set_styles")
async def save_member_config_styles(data: MemberConfigUpdate):
    from app.routers.sockets import logger as socket_logger
    socket_logger.info(f"[Config] Received member style update")
    
    member_config.update(**data.dict(exclude_unset=True))
    full_config = member_config.get_config()
    
    # Emit update using standardized event name
    await sio.emit('members:config_updated', full_config)
    return {"success": True, **full_config}

@router.post("/members/set_thank_you_text")
async def set_thank_you_text(data: Dict[str, str]):
    text = data.get('text', '')
    member_config.update(thank_you_text=text)
    full_config = member_config.get_config()
    await sio.emit('members:config_updated', full_config)
    return {"success": True, **full_config}

@router.get("/members/get_gifs")
async def get_member_gifs():
    return {
        "success": True,
        "gifs": member_config.get_config().get('gifs', {})
    }

@router.get("/members/get_styles")
async def get_member_styles():
    config_data = member_config.get_config()
    return {
        "success": True,
        "styles": config_data.get('styles', {}),
        "show_member_info": config_data.get('show_member_info', True)
    }

@router.get("/members/get_thank_you_text")
async def get_thank_you_text():
    return {
        "success": True, 
        "text": member_config.thank_you_text,
        "default": "感谢您的支持！" 
    }

@router.post("/members/upload_gif")
async def upload_member_gif(
    file: UploadFile = File(...),
    tier: str = Form(...)
):
    try:
        # Generate unique filename
        ext = Path(file.filename).suffix
        filename = f"member_{tier}_{int(time.time())}{ext}"
        file_path = Path(config.STATIC_PATH) / filename
        
        # Save file
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
            
        # Update config
        member_config.set_gif(tier, filename, is_custom=True)
        
        # Notify clients
        await sio.emit('members:config_updated', member_config.get_config())
        
        return {
            "success": True,
            "filename": filename,
            "url": f"/static/{filename}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/members/reset_gif")
async def reset_member_gif(data: dict):
    try:
        tier = data.get('tier')
        if not tier:
            return {"success": False, "error": "Missing tier"}
            
        member_config.reset_gif(tier)
        
        # Notify clients
        await sio.emit('members:config_updated', member_config.get_config())
        
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Member Progress Config
@router.get("/get_member_progress_config")
@router.get("/members/get_progress_config")
@router.get("/members_progress/config")
async def get_member_progress_config():
    return member_progress_config.get_config()
    
@router.post("/save_member_progress_config")
@router.post("/members/save_progress_config")
@router.post("/members/update_progress_config")
@router.post("/members_progress/config")
async def save_member_progress_config(data: Dict[str, Any]):
    # Using generic dict for now as model might be complex
    member_progress_config.update(**data)
    await sio.emit('members_progress:config_updated', member_progress_config.get_config())
    return {"success": True}

@router.post("/members_progress/upload_image")
async def upload_member_progress_image(
    file: UploadFile = File(...),
    index: int = Form(...)
):
    try:
        # Generate unique filename
        ext = Path(file.filename).suffix
        filename = f"level_{index}_{int(time.time())}{ext}"
        file_path = Path(config.STATIC_PATH) / filename
        
        # Save file
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
            
        # Update config
        member_progress_config.set_level_image(index, filename, is_custom=True)
        
        # Notify clients
        await sio.emit('members_progress:config_updated', member_progress_config.get_config())
        
        return {
            "success": True,
            "filename": filename,
            "url": f"/static/{filename}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/members_progress/reset_image")
async def reset_member_progress_image(data: dict):
    try:
        index = data.get('index')
        if index is None:
            return {"success": False, "error": "Missing index"}
            
        # Revert to default
        if 0 <= index < len(MemberProgressConfigState.DEFAULT_LEVELS):
            filename = MemberProgressConfigState.DEFAULT_LEVELS[index]['image']
            member_progress_config.set_level_image(index, filename, is_custom=False)
            
            # Notify clients
            await sio.emit('members_progress:config_updated', member_progress_config.get_config())
            
            return {
                "success": True,
                "filename": filename,
                "url": f"/static/{filename}"
            }
        else:
            return {"success": False, "error": "Invalid index"}
    except Exception as e:
        return {"success": False, "error": str(e)}
