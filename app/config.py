# -*- coding: utf-8 -*-
"""
BiliUtility Application Configuration

Provides path configuration for plugin mode (PyInstaller bundled)
and development mode.
"""
import os
import sys

# Detect if running as PyInstaller bundle
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # Running as compiled executable
    RESOURCE_BASE = sys._MEIPASS
    USER_BASE = os.path.dirname(sys.executable)
else:
    # Running as script
    # Current file is app/config.py
    # We want the project root (one level up)
    _current_dir = os.path.dirname(os.path.realpath(__file__))
    RESOURCE_BASE = os.path.dirname(_current_dir)
    USER_BASE = RESOURCE_BASE

# Directory paths
# Mutable data (Logs, Configs) lives in USER_BASE (next to executable)
LOG_PATH = os.path.join(USER_BASE, 'log')
DATA_PATH = os.path.join(USER_BASE, 'data')
BACKUP_LOG_PATH = os.path.join(LOG_PATH, 'messages')

# Immutable resources (Web assets, Default Audio) live in RESOURCE_BASE (bundled)
STATIC_PATH = os.path.join(RESOURCE_BASE, 'static')
TEMPLATES_PATH = os.path.join(RESOURCE_BASE, 'templates')
AUDIO_PATH = os.path.join(RESOURCE_BASE, 'audio_commands')

# Ports
FLASK_PORT = 5001 # Legacy/Plugin Port
FASTAPI_PORT = 5149 # Standalone Port

# JSON backup log settings
BACKUP_LOG_ENABLED = True

# Mode Flag (Set by main.py)
IS_PLUGIN_MODE = False

# Ensure mutable directories exist
def ensure_directories():
    for path in [LOG_PATH, DATA_PATH, BACKUP_LOG_PATH, STATIC_PATH]:
        os.makedirs(path, exist_ok=True)

# Run on import
ensure_directories()
