import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import socketio

from app import config
from app.state import monitor_config, tts_config
from app.services.watcher import watcher_service
from app.services.tts import TTSProcessor

logger = logging.getLogger('biliutility.app')

# Import routers and socket server
from app.routers import system, config as config_router, views, voting, sounds, sockets
from app.routers.sockets import sio
from app.state import state as app_state

def create_app() -> socketio.ASGIApp:
    """
    Create and configure the FastAPI application wrapped in SocketIO ASGIApp.
    """
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        logger.info("[Lifespan] Application starting up...")
        
        # Ensure directories
        config.ensure_directories()
        
        # Start TTS Processor
        app.state.tts_processor = TTSProcessor(sio)
        await app.state.tts_processor.start()
        
        # Link TTS manager with SocketIO for real-time updates
        from tts_engines.manager import tts_manager
        tts_manager.set_sio(sio)
        
        # Auto-initialize default engine on startup
        logger.info(f"[Lifespan] Initializing default TTS engine ({tts_config.engine})...")
        try:
            tts_manager.switch_engine(tts_config.engine)
        except Exception as e:
            logger.error(f"[Lifespan] Failed to auto-initialize TTS engine: {e}")
        
        # Start Log Watcher if in Standalone Mode
        if not config.IS_PLUGIN_MODE:
            logger.info("[Lifespan] Starting LogWatcherService (Standalone Mode)")
            await watcher_service.start()
        else:
            logger.info("[Lifespan] LogWatcherService execution skipped (Plugin Mode)")
        
        # Initial Guard Count Fetch if configured
        if monitor_config.is_configured:
            from app.routers.system import fetch_initial_guard_count
            try:
                initial_count = fetch_initial_guard_count(int(monitor_config.room_id), int(monitor_config.uid))
                await app_state.set_initial_guard_count(initial_count)
                logger.info(f"[Lifespan] Initial guard count fetched: {initial_count}")
            except Exception as e:
                logger.error(f"[Lifespan] Failed to fetch initial guard count: {e}")
        
        yield
        
        # Shutdown
        logger.info("[Lifespan] Application shutting down...")
        await app.state.tts_processor.stop()
        if not config.IS_PLUGIN_MODE:
            await watcher_service.stop()

    app = FastAPI(lifespan=lifespan)

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static Files
    app.mount("/static", StaticFiles(directory=config.STATIC_PATH), name="static")

    # Include Routers
    app.include_router(system.router)
    app.include_router(config_router.router)
    app.include_router(views.router)
    app.include_router(voting.router)
    app.include_router(sounds.router)
    
    # Wrap with SocketIO
    socket_app = socketio.ASGIApp(sio, app)
    
    return socket_app
