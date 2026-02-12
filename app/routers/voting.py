from fastapi import APIRouter
import logging
from app.state import voting_config, state
from app.routers.sockets import sio

router = APIRouter(prefix="/api/voting", tags=["voting"])
logger = logging.getLogger('biliutility.voting')

@router.get("/state")
async def get_voting_state():
    return voting_config.get_state()

@router.post("/start")
async def start_voting(data: dict):
    title = data.get('title', 'Chat Voting')
    options = data.get('options', [])
    show_title = data.get('show_title')
    show_background = data.get('show_background')
    
    # Handle frontend sending list of dicts [{'text':...}, ...] or list of strings
    final_options = []
    if options and isinstance(options[0], dict):
        final_options = [o.get('text', '') for o in options]
    else:
        final_options = options

    new_state = voting_config.start_voting(
        title, 
        final_options, 
        show_title=show_title, 
        show_background=show_background
    )
    await sio.emit('voting:update', new_state)
    return {"success": True, "state": new_state}

@router.post("/stop")
async def stop_voting():
    new_state = voting_config.stop_voting()
    await sio.emit('voting:update', new_state)
    return {"success": True, "state": new_state}

@router.post("/reset")
async def reset_voting():
    new_state = voting_config.reset_voting()
    await sio.emit('voting:update', new_state)
    return {"success": True, "state": new_state}

@router.post("/set_styles")
async def set_voting_styles(data: dict):
    new_state = voting_config.update_styles(data)
    await sio.emit('voting:update', new_state)
    return {"success": True, "state": new_state}
