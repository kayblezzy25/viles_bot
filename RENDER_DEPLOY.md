# Render.com Deployment Guide

This guide walks you through deploying the Telegram AI Content Bot on Render.com.

## Prerequisites

- [Render.com](https://render.com) account (free tier available)
- [GitHub](https://github.com) account
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- OpenAI API Key (from [OpenAI Platform](https://platform.openai.com))

## Step-by-Step Deployment

### Step 1: Prepare Your Code

1. Fork or upload this repository to your GitHub account
2. Ensure all files are committed:
   - `bot.py` - Main bot code
   - `database.py` - Database models
   - `openai_client.py` - OpenAI integration
   - `keep_alive.py` - Health check server
   - `requirements.txt` - Python dependencies
   - `render.yaml` - Render configuration

### Step 2: Create Web Service on Render

1. Log in to [Render Dashboard](https://dashboard.render.com)
2. Click **"New +"** button
3. Select **"Web Service"**

### Step 3: Connect Repository

1. Connect your GitHub account if not already connected
2. Find and select your repository
3. Click **"Connect"**

### Step 4: Configure Service

Fill in the following settings:

| Setting | Value |
|---------|-------|
| **Name** | `telegram-ai-bot` (or your choice) |
| **Environment** | `Python 3` |
| **Region** | Choose closest to your users |
| **Branch** | `main` (or your default branch) |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python bot.py` |
| **Plan** | `Free` or `Standard` ($7/month) |

> **Note**: Free tier has a 15-minute idle timeout. For reliable 24/7 operation, choose Standard plan.

### Step 5: Add Environment Variables

Click **"Advanced"** → **"Add Environment Variable"** and add:

#### Required Variables

| Key | Value | Get From |
|-----|-------|----------|
| `BOT_TOKEN` | Your bot token | [@BotFather](https://t.me/BotFather) |
| `OPENAI_API_KEY` | Your API key | [OpenAI Platform](https://platform.openai.com) |

#### Optional Variables

| Key | Value | Purpose |
|-----|-------|---------|
| `WEBHOOK_URL` | `https://your-service-name.onrender.com` | Webhook mode (auto-set) |
| `DATABASE_URL` | Render PostgreSQL URL | Persistent database |

### Step 6: Deploy

1. Click **"Create Web Service"**
2. Render will automatically build and deploy
3. Wait for deployment to complete (2-3 minutes)
4. Check logs for "Bot initialization complete!"

## Setting Up PostgreSQL (Recommended)

For production use, PostgreSQL provides better reliability than SQLite:

1. In Render Dashboard, click **"New +"** → **"PostgreSQL"**
2. Choose **"Free"** or paid plan
3. Name it `telegram-bot-db`
4. Wait for creation (1-2 minutes)
5. Copy the **"Internal Database URL"**
6. Go to your Web Service → **"Environment"**
7. Add variable: `DATABASE_URL` = copied URL
8. Redeploy the service

## Webhook vs Polling

### Webhook Mode (Recommended for Production)

Automatically enabled when `WEBHOOK_URL` is set.

**Pros:**
- More efficient (no constant polling)
- Better for serverless environments
- Lower latency

**Cons:**
- Requires public URL
- Slightly more complex setup

### Polling Mode (Default)

Used when `WEBHOOK_URL` is not set.

**Pros:**
- Works behind firewalls/NAT
- Simpler setup
- Good for development

**Cons:**
- Higher resource usage
- Slight delay in message delivery

## Verifying Deployment

### Check Logs

1. Go to your service on Render Dashboard
2. Click **"Logs"** tab
3. Look for:
   - `Bot initialization complete!`
   - `Keep-alive server started`
   - No error messages

### Test the Bot

1. Message your bot on Telegram: `/start`
2. You should receive welcome message
3. Add bot to a test channel
4. Send: `/write Test topic`
5. First post should appear within 10 seconds

## Troubleshooting

### "Conflict: terminated by other getUpdates request"

**Cause**: Multiple bot instances running

**Solution**:
1. Stop all running instances
2. Wait 30 seconds
3. Restart only one instance
4. Use webhook mode to prevent this

### "Database is locked" (SQLite)

**Cause**: SQLite doesn't handle concurrent access well

**Solution**: Switch to PostgreSQL (see above)

### Posts not sending after idle period

**Cause**: Render free tier sleeps after 15 minutes

**Solutions**:
1. **Upgrade to Standard plan** ($7/month) - Recommended
2. **Use external ping service** (UptimeRobot, Pingdom)
3. **Deploy to AWS Lambda** (free tier, more complex)

### OpenAI API errors

**Check**:
1. `OPENAI_API_KEY` is correct
2. Account has available credits
3. API key has not expired

## Upgrading to Paid Tier

For reliable 24/7 operation:

1. Go to your service on Render Dashboard
2. Click **"Settings"** → **"Plan"**
3. Select **"Standard"** ($7/month)
4. Benefits:
   - No idle timeout
   - Always-on service
   - More resources
   - Better reliability

## Monitoring

### Health Check Endpoint

The bot exposes a health check at:
```
https://your-service.onrender.com/health
```

Returns: `Bot is running! Time: 2024-01-15T10:30:00`

### Uptime Monitoring

Set up free monitoring with:
- [UptimeRobot](https://uptimerobot.com) (free tier: 5-minute checks)
- [Pingdom](https://pingdom.com) (free tier available)
- [StatusCake](https://statuscake.com) (free tier available)

Configure to ping `/health` endpoint every 5 minutes.

## Backup and Recovery

### Database Backup (PostgreSQL)

Render automatically backs up PostgreSQL:
- Daily backups
- 7-day retention on free tier
- Point-in-time recovery on paid tiers

### Manual Backup

```bash
# Export data
pg_dump $DATABASE_URL > backup.sql

# Import data
psql $DATABASE_URL < backup.sql
```

## Security Checklist

- [ ] `.env` file in `.gitignore`
- [ ] API keys rotated regularly
- [ ] Webhook secret token configured
- [ ] Bot permissions minimized
- [ ] Database access restricted
- [ ] HTTPS only (enforced by Render)

## Cost Estimation

### Free Tier
- Render Web Service: $0
- Render PostgreSQL: $0 (90-day limit)
- OpenAI API: ~$0.10-1.50 per campaign

### Standard Tier
- Render Web Service: $7/month
- Render PostgreSQL: $7/month
- OpenAI API: Variable based on usage

### Example: 10 Active Channels
- Hosting: $14/month (Standard + PostgreSQL)
- OpenAI: ~$1-15/month (GPT-3.5)
- **Total: ~$15-30/month**

## Next Steps

1. [Add bot to your channels](https://telegram.org/blog/channels-2-0)
2. Test with `/write` command
3. Monitor logs for first few posts
4. Set up uptime monitoring
5. Consider upgrading for production use

## Support Resources

- [Render Docs](https://render.com/docs)
- [python-telegram-bot Docs](https://docs.python-telegram-bot.org/)
- [OpenAI API Docs](https://platform.openai.com/docs)
- [Telegram Bot API](https://core.telegram.org/bots/api)

---

**Your bot should now be running on Render! 🎉**
