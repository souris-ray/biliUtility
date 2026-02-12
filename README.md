# BiliUtility

**The all-in-one widget toolkit for Bilibili streamers and VTubers.**

Elevate your stream with elegent, real-time widgets - goal tracking, interactive polls, member celebrations, TTS, and more. No coding required.

![BiliUtility Badge](https://img.shields.io/badge/BiliUtility-Widget_Suite-00AEEC?style=for-the-badge)

---

# 📺 For Streamers

Everything you need to get started - no technical knowledge required.

## What's Included

### Monetization & Punishment Wheel
Track all incoming support - Paid Gifts, SuperChats, and Memberships - in one place. Watch your progress bar fill in real time, hit milestones throughout your stream, and trigger the Punishment Wheel when goals are reached.

- Real-time animated progress bar
- Customizable milestone levels
- Standalone Punishment Wheel page with fully editable segments

### Member Progress (Guard Goals)
Set visual goals for your Guards (舰长 / 提督 / 总督) and celebrate every step of the way.

- Define multiple levels with individual targets
- Upload custom artwork for each milestone
- Automatically syncs with your live stream

### Live Voting
Run real-time polls right inside your stream.

- Viewers vote by typing a number in chat - simple and intuitive
- Results update live as votes come in
- Fully styled to match your stream layout

### Member Welcome Animations
Make every new member feel special with dedicated entrance animations.

- Unique animations for each Guard rank (舰长, 提督, 总督)
- Upload your own images, GIFs, and sound effects
- Customizable thank-you messages for each tier

### TTS & Sound Commands
Never miss a SuperChat or membership message again.

- Kokoro TTS - high-quality, local AI-powered voice synthesis
- AWS Polly - cloud-based TTS with natural voices
- Built-in translation support via DeepL or AWS
- Let viewers trigger sound effects in your stream with custom chat commands (e.g., `!yay`)

---

## Getting Started

**1. Download BiliUtility**  
Download the latest `biliutility.zip` from the [GitHub Releases](https://github.com/SourisRay/v2_BiliUtility/releases) page and extract it.

**2. Install as a Plugin**  
- Open your **blivechat** folder.
- Navigate to `data/plugins/`.
- Create a new folder named `biliutility`.
- Place all extracted files (including `biliutility.exe` and `plugin.json`) into this folder.

**3. Launch & Connect**
- Restart **blivechat**.
- Ensure **Advanced → Relay messages by the server** is enabled.
- Connect your Bilibili account by entering your **Identity Code (身份码)** in the blivechat setup.

**4. Open the Dashboard**  
Navigate to `http://localhost:5001` in your browser to configure your widgets. 
*(If running standalone, use `http://localhost:5149`)*.

**5. Add Widgets to OBS**
- Copy the **Widget URL** from your BiliUtility dashboard.
- In OBS Studio, create a new **Browser Source**.
- Paste the URL and set the resolution to **1920 × 1080**.
- Enable *"Shutdown source when not visible"*.

That's it - your widgets are live!

---

## How to Use Each Widget

### Monetization Tracking
Open **Monetization Config** on the dashboard to set your target amount and milestone steps. The widget listens for gifts automatically and updates in real time - Paid Gifts, SuperChats, and Memberships are all tracked together.

### Member Progress
Head to the Member Progress config page to define your Guard levels (e.g., Level 1 = 10 Captains). Upload a custom image for each level, and add the `/widget/guards` URL as a Browser Source in OBS.

### Live Voting
Open the **Voting Config** page, enter your question and the answer options, and click **Start**. A prompt will appear in chat for each choice. When the vote is complete, click **Stop** to lock the final results.

### TTS & Translation
Open the **TTS Control Panel** - ideally on a second monitor. Toggle **Auto-Play** to have messages read aloud as they come in. Multiple messages are handled in a fair queue so nothing gets skipped. To enable translation, add your DeepL or AWS API key on the **API Credentials** page.

### Sound Commands
Go to **Sound Configuration**, upload an audio file (`.mp3` or `.wav`), and assign it a command word (e.g., `!wow`). Whenever a viewer types that command in chat, the sound plays on your stream.

---
| Widget | Config Page | How It Works |
|--------|-------------|--------------|
| **Monetization Tracking** | Monetization Config | Set target amount and milestones. Tracks Paid Gifts, SuperChats, and Memberships automatically. |
| **Member Progress** | Member Progress Config | Define Guard levels (e.g., 10 Captains = Level 1). Upload custom images for each milestone. |
| **Live Voting** | Voting Config | Enter question and options, click Start. Viewers vote by typing numbers in chat. |
| **TTS & Translation** | TTS Control Panel | Toggle Auto-Play to read messages aloud. Add API keys for DeepL/AWS translation. |
| **Sound Commands** | Sound Configuration | Upload audio files and assign command words (e.g., `!wow`). |



---

## Personalization

Every widget supports **Light** and **Dark** themes. Adjust colors, fonts, and transparency to match your stream layout.

---

# 🛠️ For Developers

Technical documentation for contributing or building from source.

## Architecture Overview

BiliUtility is a FastAPI + Socket.IO application that connects to Bilibili's live streaming API through the blivechat relay.

```
┌─────────────────────────────────────────────────────────────┐
│                        OBS Browser Sources                   │
└──────────────────────────┬──────────────────────────────────┘
                           │ Socket.IO (real-time updates)
┌──────────────────────────▼──────────────────────────────────┐
│                     FastAPI Application                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Routers   │  │  Services   │  │    TTS Engines      │  │
│  │  - config   │  │  - tts      │  │  - Kokoro (local)   │  │
│  │  - sockets  │  │  - watcher  │  │  - AWS Polly        │  │
│  │  - views    │  │  - parser   │  └─────────────────────┘  │
│  │  - voting   │  │  - webhook  │                           │
│  │  - sounds   │  └─────────────┘                           │
│  └─────────────┘                                            │
└──────────────────────────┬──────────────────────────────────┘
                           │ Log file watching / SDK
┌──────────────────────────▼──────────────────────────────────┐
│                    blivechat Relay                          │
│               (Bilibili Live Chat Messages)                  │
└─────────────────────────────────────────────────────────────┘
```

## Project Structure

```
v2_BiliUtility/
├── app/                    # FastAPI application core
│   ├── __init__.py         # App factory (create_app)
│   ├── main.py             # Entry point (standalone & plugin mode)
│   ├── config.py           # Configuration constants
│   ├── models.py           # Pydantic models
│   ├── state.py            # Application state management
│   ├── routers/            # API routes
│   │   ├── config.py       # Configuration endpoints
│   │   ├── sockets.py      # Socket.IO handlers
│   │   ├── views.py        # HTML template routes
│   │   ├── voting.py       # Voting endpoints
│   │   └── sounds.py       # Sound command endpoints
│   ├── services/           # Business logic
│   │   ├── tts.py          # TTS processing & queue
│   │   ├── watcher.py      # Log file watcher
│   │   └── parser.py       # Message parsing
│   └── infrastructure/     # External integrations
│       └── blcsdk.py       # Bilibili SDK wrapper
├── tts_engines/            # TTS engine implementations
│   ├── __init__.py         # Base TTSEngine class
│   ├── manager.py          # Singleton engine manager
│   ├── kokoro_engine.py    # Local Kokoro TTS
│   └── polly_engine.py     # AWS Polly TTS
├── blcsdk/                 # Bilibili Live Chat SDK
├── templates/              # Jinja2 HTML templates
├── static/                 # Static assets (JS, CSS, images)
├── audio_commands/         # Sound effect files
├── data/                   # Runtime configuration (JSON)
├── log/                    # Application logs
├── build.py                # Build script
└── biliutility.spec        # PyInstaller configuration
```

## Development Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd BiliUtility

# 2. Create virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Install Kokoro for local TTS
pip install kokoro

# 5. Run the application
python -m app.main
```

The dashboard will be available at `http://localhost:5149`.

## Environment Variables

Create a `.env` file in the project root (see `data/.env.example`):

| Variable | Description |
|----------|-------------|
| `DEEPL_API_KEY` | DeepL API key for translation |
| `AWS_ACCESS_KEY_ID` | AWS credentials for Polly TTS |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials for Polly TTS |
| `AWS_REGION` | AWS region (default: `us-east-1`) |

## Building for Distribution

```bash
# Stage files and run PyInstaller
python build.py --build
```

Output: `dist/biliutility/` - ready-to-distribute standalone executable.

## Key Technologies

| Technology | Purpose |
|------------|---------|
| FastAPI | Web framework |
| Socket.IO | Real-time WebSocket communication |
| Jinja2 | HTML templating |
| Kokoro | Local AI TTS (optional) |
| AWS Polly | Cloud TTS |
| DeepL | Translation API |
| PyInstaller | Executable bundling |

---

*Made with ❤️ for the community by Souris Ray*