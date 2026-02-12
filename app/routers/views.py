from fastapi import APIRouter, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from app import config
from app.state import monitor_config

router = APIRouter(tags=["views"])

templates = Jinja2Templates(directory=config.TEMPLATES_PATH)

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    from app.state import monitor_config
    return templates.TemplateResponse("index.html", {"request": request, "config": {
        "room_id": monitor_config.room_id,
        "uid": monitor_config.uid,
        "username": monitor_config.username,
        "log_dir": monitor_config.log_dir,
        "is_configured": monitor_config.is_configured
    }})

@router.get("/config/api", response_class=HTMLResponse)
async def config_api(request: Request):
    from app.state import credentials_manager
    return templates.TemplateResponse("config_api.html", {"request": request, "config": credentials_manager.load_credentials()})

@router.get("/config/tts", response_class=HTMLResponse)
async def config_tts(request: Request):
    from app.state import tts_config
    from tts_engines.manager import tts_manager
    return templates.TemplateResponse("config_tts.html", {"request": request, "config": {
        "engine": tts_config.engine,
        "voice": tts_config.voice,
        "speed_normal": tts_config.speed_normal,
        "speed_name": tts_config.speed_name,
        "available_voices": tts_manager.get_voices_by_type(tts_config.engine),
        "defaults": tts_config.DEFAULT_SETTINGS,
        "is_kokoro_available": tts_manager.is_engine_available('kokoro'),
        "is_aws_available": tts_manager.is_engine_available('aws_polly')
    }})

@router.get("/config/gifts", response_class=HTMLResponse)
async def config_gifts(request: Request):
    from app.state import gift_config
    return templates.TemplateResponse("config_monetization_tracking.html", {"request": request, "config": gift_config.get_config()})

@router.get("/config/members", response_class=HTMLResponse)
async def config_members(request: Request):
    from app.state import member_config
    return templates.TemplateResponse("config_members_display.html", {"request": request, "config": member_config.get_config()})

@router.get("/config/members_progress", response_class=HTMLResponse)
async def config_members_progress(request: Request):
    from app.state import member_progress_config
    return templates.TemplateResponse("config_members_progress.html", {"request": request, "config": member_progress_config.get_config()})

@router.get("/config/sounds", response_class=HTMLResponse)
async def config_sounds(request: Request):
    from app.state import sound_config
    return templates.TemplateResponse("config_sounds.html", {"request": request, "config": sound_config.get_commands()})

@router.get("/config/voting", response_class=HTMLResponse)
async def config_voting(request: Request):
    from app.state import voting_config
    return templates.TemplateResponse("config_voting.html", {"request": request, "config": voting_config.get_state()})

@router.get("/widget/gifts", response_class=HTMLResponse)
async def widget_gifts(request: Request):
    from app.state import gift_config, state
    config_data = gift_config.get_config()
    config_data.update({
        'current_progress': state.milestone_progress,
        'milestone_count': state.milestone_count
    })
    return templates.TemplateResponse("monetization_tracking_widget.html", {"request": request, "config": config_data})

@router.get("/widget/gifts-v2", response_class=HTMLResponse)
async def widget_gifts_v2(request: Request):
    from app.state import gift_config, state
    config_data = gift_config.get_config()
    config_data.update({
        'current_progress': state.milestone_progress,
        'milestone_count': state.milestone_count
    })
    return templates.TemplateResponse("monetization_tracking_widget.html", {"request": request, "config": config_data})

@router.get("/widget/members", response_class=HTMLResponse)
async def widget_members(request: Request):
    from app.state import member_config
    return templates.TemplateResponse("members_display_widget.html", {"request": request, "config": member_config.get_config()})
    
@router.get("/widget/members_progress", response_class=HTMLResponse)
@router.get("/widget/guards", response_class=HTMLResponse)
async def widget_members_progress(request: Request):
    from app.state import member_progress_config, state as app_state
    return templates.TemplateResponse("members_progress_widget.html", {
        "request": request, 
        "config": member_progress_config.get_config(),
        "initial_count": app_state.total_guard_count
    })

@router.get("/widget/voting", response_class=HTMLResponse)
async def widget_voting(request: Request):
    from app.state import voting_config
    return templates.TemplateResponse("voting_widget.html", {"request": request, "state": voting_config.get_state()})

@router.get("/widget/tts", response_class=HTMLResponse)
async def widget_tts(request: Request):
    return templates.TemplateResponse("tts_widget.html", {"request": request})

# Fallbroken routes or redirects from old structure?
# Original app had everything at root or /widget/...
# This seems to cover it.
