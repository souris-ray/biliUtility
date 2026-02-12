import socketio
import logging
from app.state import state, voting_config, monitor_config

logger = logging.getLogger('biliutility.sockets')

# Initialize Async SocketIO Server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

@sio.event
async def connect(sid, environ):
    logger.info(f"[Socket] Client connected: {sid}")
    # Send initial state if needed
    # await sio.emit('init_state', ..., to=sid)
    # The frontend usually polls APIs for config, but might expect push updates.
    
    # Example: Send current config status
    await sio.emit('config:status', {
        'is_configured': monitor_config.is_configured,
        'username': monitor_config.username
    }, to=sid)

    # Send current application state
    await sio.emit('initial_state', await state.get_state(), to=sid)

    # Send current TTS status
    await sio.emit('tts:status', {
        'autoplay': state.tts_autoplay,
        'queue_size': state.tts_queue.qsize(),
        'is_playing': state.tts_playing is not None
    }, to=sid)

@sio.event
async def disconnect(sid):
    logger.info(f"[Socket] Client disconnected: {sid}")

@sio.on('backend:update_config')
async def handle_update_config(sid, data):
    # Validating legacy support.
    # Frontend might emit this to request config update?
    # Usually handled via API now.
    pass

@sio.on('speech:play')
async def handle_speech_play(sid, data):
    # Test speech play from frontend
    # data: {'text': '...', 'voice': '...' ...}
    # This might be useful for preview.
    # We can delegate to TTSService test logic?
    # Or just ignore if API covers it.
    pass

# Helper to broadcast updates
async def broadcast_voting_update():
    await sio.emit('voting:update', await voting_config.get_state())

def _build_tts_payload(msg):
    """Build TTS message payload for Socket.IO emission"""
    payload = {
        'unique_id': msg.unique_id,
        'username': msg.username,
        'text': msg.tts_text,
        'type': msg.type.value if hasattr(msg.type, 'value') else msg.type,
        'translation': msg.translation,
        'pinyin': msg.pinyin,
        'formatted_text': msg.formatted_text,
        'is_read': msg.is_read
    }
    # Include amount for superchat messages
    if msg.type == 'superchat' and 'amount' in msg.content:
        payload['amount'] = msg.content['amount']
    return payload

async def broadcast_message(msg):
    """Broadcast message events to widgets based on type"""
    # Get current state snapshot
    current_state = await state.get_state() if hasattr(state, 'get_state') else {
        'paid_gift_total_value': state.paid_gift_total_value,
        'paid_gift_count': state.paid_gift_count,
        'milestone_progress': state.milestone_progress,
        'milestone_count': state.milestone_count,
        'total_guard_count': state.total_guard_count
    }
    
    # Check direct attribute access vs get_state method (WidgetState usually has attributes)
    logger.info(f"[Socket] Broadcasting event: {msg.type} for {msg.unique_id}")
    
    # Normalize type to string for comparison
    msg_type_str = msg.type.value if hasattr(msg.type, 'value') else str(msg.type)
    
    if msg_type_str == 'paid_gift':
        payload = {
            'total_value': state.paid_gift_total_value,
            'total_count': state.paid_gift_count,
            'milestone_progress': state.milestone_progress,
            'milestone_count': state.milestone_count,
            'username': msg.username,
            'gift_name': msg.content.get('gift_name'),
            'quantity': msg.content.get('quantity'),
            'value': msg.content.get('value')
        }
        await sio.emit('paid_gift', payload)
        
    elif msg_type_str == 'superchat':
        payload = {
            'milestone_progress': state.milestone_progress,
            'milestone_count': state.milestone_count,
            'amount': msg.content.get('amount'),
            'message': msg.content.get('message'),
            'username': msg.username
        }
        await sio.emit('superchat', payload)
        # Emit TTS message if enabled
        if msg.tts_enabled:
            await sio.emit('tts:new_message', _build_tts_payload(msg))
        
    elif msg_type_str == 'guard':
        payload = {
            'total_guard_count': state.total_guard_count,
            'milestone_progress': state.milestone_progress,
            'milestone_count': state.milestone_count,
            'username': msg.username,
            'guard_type': msg.content.get('guard_type'),
            'value': msg.content.get('value')
        }
        await sio.emit('guard', payload)
        # Also emit member:new to trigger widget queue check
        await sio.emit('member:new', {'username': msg.username})
        # Emit TTS message if enabled
        if msg.tts_enabled:
            await sio.emit('tts:new_message', _build_tts_payload(msg))
        
@sio.on('member:get_next')
async def handle_member_get_next(sid):
    member = await state.get_next_member()
    if member:
        logger.info(f"[Socket] Sending next member to display for {sid}: {member.username}")
        payload = {
            'username': member.username,
            'guard_type': member.content.get('guard_type', '舰长'),
        }
        await sio.emit('member:display', payload)
    else:
        # Avoid excessive logging for polling
        # logger.debug(f"[Socket] Queue empty for {sid}")
        await sio.emit('member:queue_empty')

@sio.on('member:queue_status')
async def handle_queue_status(sid):
    size = await state.get_member_queue_size()
    logger.debug(f"[Socket] Queue status requested by {sid}: size={size}")
    await sio.emit('member:queue_size', {'size': size})

# --- TTS Socket Handlers ---

@sio.on('tts:toggle_autoplay')
async def handle_tts_toggle_autoplay(sid, data):
    enabled = data.get('enabled', False)
    async with state.lock:
        state.tts_autoplay = enabled
        
        if state.tts_autoplay:
            # If turning on, queue the first unread message to kick off the processor
            unread = [msg for msg in state.tts_messages.values() if not msg.is_read]
            unread.sort(key=lambda m: m.timestamp)
            if unread and state.tts_queue.empty():
                await state.tts_queue.put((unread[0], True))
        else:
            # If turning off, clear the queue so no further messages play automatically
            while not state.tts_queue.empty():
                try:
                    state.tts_queue.get_nowait()
                    state.tts_queue.task_done()
                except asyncio.QueueEmpty:
                    break
            await sio.emit('tts:queue_cleared', {'queue_size': 0})
    
    logger.info(f"[Socket] TTS Autoplay toggled to {enabled} by {sid}")
    await sio.emit('tts:status', {
        'autoplay': state.tts_autoplay,
        'queue_size': state.tts_queue.qsize(),
        'is_playing': state.tts_playing is not None
    })

@sio.on('tts:get_history')
async def handle_tts_get_history(sid):
    async with state.lock:
        history = [_build_tts_payload(msg) for msg in state.tts_messages.values()]
        # Sort history by timestamp to ensure chronological order in UI
        # ParsedMessage doesn't have a direct 'timestamp' attribute access in the dict, 
        # but the objects themselves do.
        history.sort(key=lambda x: x.get('unique_id', '')) # unique_id starts with timestamp

    await sio.emit('tts:history', {'messages': history}, to=sid)
    
    # Also send current status
    await sio.emit('tts:status', {
        'autoplay': state.tts_autoplay,
        'queue_size': state.tts_queue.qsize(),
        'is_playing': state.tts_playing is not None
    }, to=sid)

@sio.on('tts:play_message')
async def handle_tts_play_message(sid, data):
    unique_id = data.get('unique_id')
    async with state.lock:
        if unique_id in state.tts_messages:
            msg = state.tts_messages[unique_id]
            # Manual play always marks as read if it was unread
            await state.tts_queue.put((msg, True))
            logger.info(f"[Socket] Message {unique_id} manually queued for playback by {sid}")
            await sio.emit('tts:message_queued', {
                'unique_id': unique_id,
                'queue_size': state.tts_queue.qsize()
            })

@sio.on('tts:skip_current')
async def handle_tts_skip_current(sid):
    import sounddevice as sd
    logger.info(f"[Socket] TTS Playback skipped by {sid}")
    try:
        sd.stop()
        await sio.emit('tts:skipped')
    except Exception as e:
        logger.error(f"Error skipping TTS: {e}")

@sio.on('tts:clear_queue')
async def handle_tts_clear_queue(sid):
    # Draining a queue in asyncio
    while not state.tts_queue.empty():
        try:
            state.tts_queue.get_nowait()
            state.tts_queue.task_done()
        except asyncio.QueueEmpty:
            break
            
    logger.info(f"[Socket] TTS Queue cleared by {sid}")
    await sio.emit('tts:queue_cleared', {'queue_size': 0})

@sio.on('tts:mark_all_read')
async def handle_tts_mark_all_read(sid):
    async with state.lock:
        for msg in state.tts_messages.values():
            msg.is_read = True
    await sio.emit('tts:all_marked_read')

@sio.on('tts:toggle_read')
async def handle_tts_toggle_read(sid, data):
    unique_id = data.get('unique_id')
    is_read = data.get('is_read')
    
    async with state.lock:
        if unique_id in state.tts_messages:
            msg = state.tts_messages[unique_id]
            if is_read is not None:
                msg.is_read = is_read
            else:
                msg.is_read = not msg.is_read
            
            await sio.emit('tts:read_state_changed', {
                'unique_id': unique_id,
                'is_read': msg.is_read
            })
