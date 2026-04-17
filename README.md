# Telegram Multi-Channel AI Content Bot

An intelligent Telegram bot that automatically generates and posts AI-powered content to multiple channels. Perfect for content creators, marketers, and community managers who want consistent, high-quality posts without manual effort.

## Features

- **Multi-Channel Support**: Add the bot to unlimited channels, each with independent campaigns
- **AI-Powered Content**: Uses OpenAI GPT to generate engaging, unique posts
- **Automatic Scheduling**: Posts every 20 minutes (10 posts/day, 50 posts total over 5 days)
- **Dynamic Registration**: No channel IDs needed - works automatically when added to any channel
- **Admin Controls**: Start, stop, pause, and resume campaigns with simple commands
- **Self-Healing**: Recovers scheduled jobs after server restarts
- **Daily Limits**: Automatically enforces 10 posts per day, resets at midnight UTC

## Commands

| Command | Description | Usage |
|---------|-------------|-------|
| `/start` | Show welcome message and bot info | `/start` |
| `/write` | Start a new content campaign | `/write [topic]` |
| `/status` | Check campaign progress | `/status` |
| `/stop` | Pause the current campaign | `/stop` |
| `/resume` | Resume a paused campaign | `/resume` |

## Quick Start

### 1. Create a Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow instructions
3. Copy your bot token (you'll need it later)

### 2. Get OpenAI API Key

1. Go to [OpenAI Platform](https://platform.openai.com/api-keys)
2. Create a new API key
3. Copy the key (you'll need it later)

### 3. Deploy to Render.com

#### Option A: One-Click Deploy (Recommended)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

1. Click the button above
2. Connect your GitHub account
3. Fill in environment variables:
   - `BOT_TOKEN`: Your Telegram bot token
   - `OPENAI_API_KEY`: Your OpenAI API key
4. Click "Deploy"

#### Option B: Manual Deploy

1. Fork/clone this repository to GitHub
2. Log in to [Render.com](https://render.com)
3. Click "New +" → "Web Service"
4. Connect your GitHub repository
5. Configure:
   - **Name**: `telegram-ai-bot` (or your preference)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
6. Add environment variables:
   - `BOT_TOKEN`: Your Telegram bot token
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `WEBHOOK_URL`: `https://your-service-name.onrender.com`
7. Click "Create Web Service"

### 4. Add Bot to Your Channel

1. Add your bot to any Telegram channel as an **Administrator**
2. Grant these permissions:
   - ✅ Post messages
   - ✅ Edit messages
   - ✅ Delete messages
3. In the channel, send: `/write [your topic]`

**Example:**
```
/write Daily productivity tips for entrepreneurs
```

The bot will immediately generate the first post and continue every 20 minutes!

## Local Development

### Prerequisites

- Python 3.11+
- pip

### Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/telegram-ai-bot.git
cd telegram-ai-bot
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create `.env` file:
```bash
cp .env.example .env
# Edit .env with your credentials
```

5. Run the bot:
```bash
python bot.py
```

## Environment Variables

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `BOT_TOKEN` | ✅ Yes | Telegram bot token from @BotFather | - |
| `OPENAI_API_KEY` | ✅ Yes | OpenAI API key | - |
| `WEBHOOK_URL` | ❌ No | Public URL for webhook mode | - |
| `PORT` | ❌ No | Server port | `10000` |
| `DATABASE_URL` | ❌ No | Database connection string | `sqlite:///bot.db` |

## How It Works

### Campaign Lifecycle

1. **Activation** (`/write` command):
   - Bot verifies admin privileges
   - Generates first post immediately
   - Schedules remaining 49 posts

2. **Posting Schedule**:
   - Posts every 20 minutes
   - 10 posts per day maximum
   - 50 posts total (5 days)

3. **Daily Reset**:
   - Counter resets at midnight UTC
   - Resumes posting next day

4. **Completion**:
   - Sends completion message
   - Removes scheduled jobs
   - Ready for new `/write` command

### Database Schema

**channels table:**
- `chat_id`: Telegram channel ID (primary key)
- `prompt_text`: Topic/prompt for content generation
- `posts_total`: Total posts in campaign (50)
- `posts_remaining`: Posts left to send
- `posts_today`: Posts sent today (resets at midnight)
- `status`: active, paused, completed, failed
- `next_post_at`: Scheduled time for next post

**posts table:**
- `id`: Post record ID
- `chat_id`: Channel ID
- `post_number`: Sequence number (1-50)
- `content`: Generated post content
- `status`: pending, sent, failed

## Content Generation

The bot uses OpenAI GPT to create diverse, engaging content:

### Post Types (Rotating)

1. **Educational Insight** - Share valuable knowledge
2. **Quick Tip** - Actionable advice
3. **Thought-Provoking Question** - Engage the audience
4. **Practical Example** - Real-world application
5. **Key Takeaway** - Memorable summary
6. **Myth-Busting** - Correct misconceptions
7. **Step-by-Step Guide** - Process breakdown
8. **Industry News Angle** - Current trends
9. **Common Mistake Warning** - Help avoid errors
10. **Success Story Framework** - Inspiring principles

### Content Guidelines

- 100-800 characters per post
- Natural emoji usage (2-4 per post)
- Conversational, engaging tone
- Formatted for Telegram
- No hashtags (Telegram style)
- Hook at the beginning
- Call-to-action at the end

## Troubleshooting

### Bot doesn't respond to commands

1. Verify bot is admin in the channel
2. Check that bot has posting permissions
3. Ensure you're using commands as an admin

### Posts aren't being sent

1. Check `/status` to see campaign state
2. Verify bot hasn't reached daily limit (10/day)
3. Check Render.com logs for errors

### OpenAI errors

1. Verify `OPENAI_API_KEY` is set correctly
2. Check OpenAI account has available credits
3. Review rate limits on your OpenAI plan

### Render.com free tier limitations

**Important**: Render's free tier has a 15-minute idle timeout. For reliable 24/7 operation:

- **Option 1**: Upgrade to Render's paid tier ($7+/month)
- **Option 2**: Use a keep-alive service (ping every 10 minutes)
- **Option 3**: Deploy to AWS Lambda (free tier available)

## Advanced Configuration

### Custom Post Schedule

Edit `bot.py` to change posting frequency:

```python
# Campaign settings
POSTS_TOTAL = 50      # Total posts
POSTS_PER_DAY = 10    # Daily limit
INTERVAL_MINUTES = 20 # Minutes between posts
```

### Custom OpenAI Model

Edit `openai_client.py`:

```python
DEFAULT_MODEL = "gpt-4"  # or "gpt-3.5-turbo"
MAX_TOKENS = 1000
TEMPERATURE = 0.8
```

### Using PostgreSQL on Render

1. Create a PostgreSQL instance on Render
2. Copy the "Internal Database URL"
3. Add to environment variables as `DATABASE_URL`

## Security Best Practices

1. **Never commit `.env` file** - It's in `.gitignore` for a reason
2. **Rotate API keys regularly** - Especially if compromised
3. **Use webhook mode in production** - More secure than polling
4. **Verify admin status** - Bot checks before executing commands
5. **Validate permissions** - Bot verifies posting rights

## API Costs

OpenAI API usage costs approximately:

- **GPT-3.5-turbo**: ~$0.002 per post = $0.10 per campaign (50 posts)
- **GPT-4**: ~$0.03 per post = $1.50 per campaign (50 posts)

For 10 channels running campaigns: ~$1-15/month

## License

MIT License - Feel free to use, modify, and distribute!

## Support

Need help? Here are some resources:

- [python-telegram-bot docs](https://docs.python-telegram-bot.org/)
- [OpenAI API docs](https://platform.openai.com/docs)
- [Render.com docs](https://render.com/docs)

---

**Happy posting! 🚀**
