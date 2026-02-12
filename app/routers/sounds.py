from fastapi import APIRouter, UploadFile, File
import shutil
import logging
from pathlib import Path
from app.state import sound_config
from app import config as app_config
from app.services.tts import TTSService

logger = logging.getLogger('biliutility.sounds')
router = APIRouter(prefix="/api/sounds", tags=["sounds"])

COMMAND_AUDIO_PATH = Path(app_config.AUDIO_PATH)

@router.get("/config")
async def get_sound_config():
    commands = sound_config.get_commands()
    audio_files = []
    if COMMAND_AUDIO_PATH.exists():
        for f in COMMAND_AUDIO_PATH.glob('*'):
            if f.suffix.lower() in ['.mp3', '.wav', '.ogg']:
                audio_files.append(f.name)
    return {
        "success": True, 
        "commands": commands, 
        "audio_files": sorted(audio_files)
    }

@router.post("/update")
async def update_sound_command(data: dict):
    trigger = data.get('trigger')
    filename = data.get('filename')
    
    if not trigger or not filename:
        return {"success": False, "error": "Missing trigger or filename"}
        
    if not trigger.startswith('!'):
        trigger = '!' + trigger
        
    sound_config.update_command(trigger, filename)
    logger.info(f"[Sounds] Command '{trigger}' updated/created with file '{filename}'")
    return {"success": True}

@router.post("/delete")
async def delete_sound_command(data: dict):
    trigger = data.get('trigger')
    if not trigger:
        return {"success": False, "error": "Missing trigger"}
    sound_config.delete_command(trigger)
    logger.info(f"[Sounds] Command '{trigger}' deleted")
    return {"success": True}

@router.post("/volume")
async def update_sound_volume(data: dict):
    trigger = data.get('trigger')
    volume = data.get('volume')
    
    if not trigger or volume is None:
        return {"success": False, "error": "Missing parameters"}
        
    sound_config.update_volume(trigger, float(volume))
    logger.info(f"[Sounds] Volume for command '{trigger}' updated to {volume}")
    return {"success": True}

@router.post("/upload")
async def upload_sound_file(file: UploadFile = File(...)):
    if not COMMAND_AUDIO_PATH.exists():
        COMMAND_AUDIO_PATH.mkdir(parents=True, exist_ok=True)
    
    file_path = COMMAND_AUDIO_PATH / file.filename
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"success": True, "filename": file.filename}
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return {"success": False, "error": str(e)}

@router.post("/preview")
async def preview_sound(data: dict):
    trigger = data.get('trigger')
    filename = data.get('filename')
    
    if not trigger and not filename:
        return {"success": False, "error": "Missing trigger or filename"}
        
    try:
        if trigger:
            # If trigger is provided, use the configured volume
            await TTSService.play_command_audio(trigger)
        else:
            # If only filename is provided, play with default volume (previewing un-associated file)
            # We need a way to play a raw file in TTSService or here.
            # TTSService._play_command_sync plays by filename if we adjust it.
            # For simplicity, let's create a temporary fake command or just play it.
            import sounddevice as sd
            import soundfile as sf
            audio_path = COMMAND_AUDIO_PATH / filename
            if audio_path.exists():
                data, samplerate = sf.read(str(audio_path), dtype='float32')
                sd.play(data, samplerate)
                sd.wait()
        return {"success": True}
    except Exception as e:
        logger.error(f"Preview failed: {e}")
        return {"success": False, "error": str(e)}
