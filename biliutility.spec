# -*- mode: python ; coding: utf-8 -*-
"""
BiliUtility PyInstaller Specification

Build command: pyinstaller biliutility.spec
Output: dist/biliutility/ (folder with executable and dependencies)
Package: dist/biliutility.zip (ready for distribution)
"""
import typing
import subprocess
import sys
import os
from pathlib import Path

sys.setrecursionlimit(5000)

# Workaround for some libraries checking dataclasses.__version__
import dataclasses
if not hasattr(dataclasses, '__version__'):
    dataclasses.__version__ = '0.8'

if typing.TYPE_CHECKING:
    from PyInstaller.building.api import COLLECT, EXE, PYZ
    from PyInstaller.building.build_main import Analysis

NAME = 'biliutility'

# Ensure we are in the project root
PROJECT_ROOT = os.getcwd()

# Module search paths
PYTHONPATH = [
    PROJECT_ROOT,
]

# Data files to include
# Format: (Source Path, Destination directory in dist)
DATAS = [
    ('plugin.json', '.'),
    ('blcsdk', 'blcsdk'),
    ('tts_engines', 'tts_engines'),
    ('static', 'static'),
    ('templates', 'templates'),
    ('audio_commands', 'audio_commands'),
    ('data/.env.example', 'data'),
    ('log/.gitkeep', 'log'),
    # Explicitly include app source if needed for dynamic loading, 
    # though Analysis usually finds it.
    # ('app', 'app'), 
]

# Hidden imports
# These are modules that PyInstaller might fail to detect statically
HIDDENIMPORTS = [
    # FastAPI & Uvicorn Core
    'fastapi',
    'starlette',
    'pydantic',
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.protocols.websockets.wsproto_impl',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    
    # SocketIO / Async stuff
    'socketio',
    'engineio.async_drivers.asgi', # Critical for ASGI
    'aiofiles',
    'httpx',
    'dns', # dnspython often needed for async IO resolution
    
    # Audio & Hardware
    'sounddevice',
    'soundfile',
    'numpy',
    'cffi',
    
    # TTS / ML / Cloud
    'boto3',
    'botocore',
    'deepl',
    'pypinyin',
    'jieba',
    'requests',
    
    # Kokoro / Torch (If used)
    'kokoro',
    'misaki',
    'torch',
    'transformers',
    'safetensors',
    'tokenizers',
    'scipy',
    'scipy.special.cython_special', # Common hidden import for scipy
]

block_cipher = None

a = Analysis(
    ['app/main.py'],  # Main Entry Point
    pathex=PYTHONPATH,
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDENIMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['flask', 'flask_socketio', 'tkinter'], # Exclude unnecessary heavy frameworks
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True, # Keep console for logs
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=NAME,
)

