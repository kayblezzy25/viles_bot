# Telegram Channel Auto-Poster Bot

AI-powered multi-agent Telegram bot. Add it to any number of channels — it manages each one independently, posting OpenAI-generated content every 20 minutes (10/day for 5 days, 50 total).

---

## Commands

| Command | What it does |
|---------|-------------|
| `/start` | Welcome message and instructions |
| `/write [topic]` | Start a campaign — describe your channel inline |
| `/status` | Check posting progress for this channel |
| `/stop` | Pause the current campaign |
| `/restart` | Clear campaign and start fresh |
| `/help` | Show all commands |

### Example

```
/write A daily crypto channel for beginners — Bitcoin, Ethereum, DeFi tips and market analysis
```

The bot generates posts and starts posting every 20 min — no confirmation step needed.

---

## Setup

### 1. Create your Telegram bot

1. Open Telegram → search **@BotFather**
2. `/newbot` → follow prompts → copy your **bot token**
3. Register commands (optional but nice):
   ```
   /setcommands → your bot
   start - Start the bot
   write - Start a new posting campaign
   status - Check campaign progress
   stop - Stop the campaign
   restart - Clear and start fresh
   help - Show commands
   ```
4. **Disable Group Privacy** so the bot can read commands in channels:
   BotFather → `/setprivacy` → your bot → Disable

### 2. Add bot to your channels

For each channel:
1. Channel settings → **Administrators** → Add Administrator
2. Search your bot's username
3. Enable **Post Messages** permission → confirm

### 3. Deploy to Render.com

**Step 1 — Push to GitHub**
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/telegram-bot
git push -u origin main
```

**Step 2 — Create the service**
1. [render.com](https://render.com) → **New → Background Worker**
2. Connect your GitHub repo
3. Settings:
   - Runtime: **Python**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python bot.py`
   - Plan: **Starter ($7/mo)** — essential so the bot never sleeps

**Step 3 — Add environment variables**
In your service → Environment:
| Key | Value |
|-----|-------|
| `TELEGRAM_BOT_TOKEN` | From BotFather |
| `OPENAI_API_KEY` | From platform.openai.com |

**Step 4 — Add Persistent Disk (critical for campaign persistence)**
Your service → **Disks** → Add Disk:
- Name: `bot-data`
- Mount Path: `/opt/render/project/src/data`
- Size: 1 GB (free tier available)

Without this disk, all active campaigns are lost on every redeploy.

**Step 5 — Deploy**
Click **Deploy** — the bot is live.

---

## How it works

### Multi-agent architecture
Each channel that uses `/write` gets an independent record in `data/channels.json` keyed by its Telegram channel ID (captured automatically — no hardcoding). The PTB job queue holds a separate repeating job per channel. When the bot restarts, `on_startup()` reads the file and re-registers all active jobs.

### Posting schedule
- Posts every 20 minutes (configurable via `POST_INTERVAL_MINUTES`)
- Maximum 10 posts per calendar day (resets at midnight UTC)
- Campaign ends after 50 total posts (10/day × 5 days)
- Bot sends a completion message when done

### Content generation
Each post is generated fresh via GPT-4o-mini with a rotating theme:
1. Educational fact or concept
2. Practical how-to or tip
3. Motivational story or case study
4. News-style trend or development
5. Advanced insight or expert perspective

---

## Cost estimate

| Service | Cost |
|---------|------|
| Render.com Starter | $7/month |
| OpenAI GPT-4o-mini | ~$0.01–0.03 per campaign (50 posts) |
| Telegram Bot API | Free |

---

## File structure

```
.
├── bot.py              # Entire bot — single file
├── requirements.txt    # 3 dependencies
├── render.yaml         # Render deployment config
├── .env.example        # Environment variable template
├── .gitignore
└── data/
    └── channels.json   # Runtime state (auto-created, persist via Render Disk)
```
