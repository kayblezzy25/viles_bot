"""
Telegram Channel Auto-Poster Bot — Fixed for Render Deployment
"""

import os
import sys
import json
import logging
import asyncio
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ChatMemberHandler,
    ContextTypes,
)
from openai import AsyncOpenAI

# Force flush stdout/stderr immediately
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

load_dotenv()

# ── Logging (force immediate output) ──────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],  # Explicitly output to stdout
)
logger = logging.getLogger("bot")

# Log immediately so we know the script started
logger.info("=" * 60)
logger.info("BOT STARTING UP...")
logger.info("=" * 60)

# ── Environment ───────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")

logger.info(f"TELEGRAM_BOT_TOKEN present: {bool(TELEGRAM_BOT_TOKEN)}")
logger.info(f"OPENAI_API_KEY present: {bool(OPENAI_API_KEY)}")

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN is not set!")
    sys.exit(1)
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY is not set!")
    sys.exit(1)

# Campaign constants (override via env vars if needed)
POST_INTERVAL_MIN = int(os.getenv("POST_INTERVAL_MINUTES", "20"))
POSTS_PER_DAY     = int(os.getenv("POSTS_PER_DAY",         "10"))
MAX_DAYS          = int(os.getenv("MAX_DAYS",               "5"))
MAX_TOTAL         = POSTS_PER_DAY * MAX_DAYS  # 50

logger.info(f"Config: {POST_INTERVAL_MIN}min, {POSTS_PER_DAY}posts/day, {MAX_DAYS}days")

# OpenAI
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ── Persistence ───────────────────────────────────────────────────────────────

# Use absolute path for Render disk or local fallback
if os.path.exists("/opt/render/project/src/data"):
    DATA_DIR = "/opt/render/project/src/data"
else:
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

_DATA_FILE = os.path.join(DATA_DIR, "channels.json")

logger.info(f"Data directory: {DATA_DIR}")
logger.info(f"Data file: {_DATA_FILE}")

def _ensure_data_dir():
    """Ensure data directory exists"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        logger.info(f"Data directory verified: {DATA_DIR}")
        return True
    except Exception as e:
        logger.error(f"Failed to create data directory: {e}")
        return False

def _load() -> dict:
    """Load channel data from JSON file"""
    if not os.path.exists(_DATA_FILE):
        logger.info(f"Data file not found, starting fresh")
        return {}
    try:
        with open(_DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
            logger.info(f"Loaded {len(data)} channel(s) from disk")
            return data
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to load data file: {e}")
        return {}

def _dump(data: dict) -> None:
    """Save channel data to JSON file"""
    try:
        _ensure_data_dir()
        with open(_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.debug(f"Saved {len(data)} channel(s) to disk")
    except Exception as e:
        logger.error(f"Failed to save data: {e}")

def _get(chat_id: int) -> dict | None:
    return _load().get(str(chat_id))

def _set(chat_id: int, record: dict) -> None:
    data = _load()
    data[str(chat_id)] = record
    _dump(data)

def _delete(chat_id: int) -> None:
    data = _load()
    data.pop(str(chat_id), None)
    _dump(data)


# ── OpenAI content generation ──────────────────────────────────────────────────

_THEMES = [
    "an educational fact, concept, or beginner tip",
    "a practical how-to, tool, or actionable step",
    "a motivational story, case study, or success example",
    "a news-style trend or recent development",
    "an advanced insight or expert-level perspective",
]

async def _generate_post(topic: str, post_num: int) -> str:
    """Generate one unique post via OpenAI GPT-4o-mini."""
    theme = _THEMES[(post_num - 1) % len(_THEMES)]
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional Telegram channel content writer. "
                        "Write engaging posts with relevant emojis. "
                        "150–270 words, short paragraphs, no titles or post numbers."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Channel topic: {topic}\n\n"
                        f"Write post #{post_num} of {MAX_TOTAL}. "
                        f"Focus this post on: {theme}. "
                        f"Make it feel completely fresh and distinct."
                    ),
                },
            ],
            max_tokens=550,
            temperature=0.85,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return f"📝 {topic}\n\nPost #{post_num} of {MAX_TOTAL}\n\nStay tuned for more insights!"


# ── Scheduler job ───────────────────────────────────────────────────────────

async def _posting_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id: int = context.job.chat_id  # type: ignore[assignment]
    record = _get(chat_id)

    if not record or not record.get("active"):
        context.job.schedule_removal()
        logger.info(f"[{chat_id}] Job removed — campaign inactive.")
        return

    total_sent = record["total_sent"]

    if total_sent >= MAX_TOTAL:
        record["active"] = False
        _set(chat_id, record)
        context.job.schedule_removal()
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "🎉 *Campaign complete!*\n\n"
                    f"All {MAX_TOTAL} posts published over {MAX_DAYS} days.\n\n"
                    "Use /write to start a new campaign anytime."
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"[{chat_id}] Completion message failed: {e}")
        return

    # Daily post limit
    today = str(date.today())
    if record.get("last_post_date") != today:
        record["posts_today"]    = 0
        record["last_post_date"] = today
        _set(chat_id, record)
        logger.info(f"[{chat_id}] New day — daily counter reset.")

    if record["posts_today"] >= POSTS_PER_DAY:
        logger.info(f"[{chat_id}] Daily limit ({POSTS_PER_DAY}) reached — skipping.")
        return

    # Generate and post
    post_num = total_sent + 1
    try:
        text = await _generate_post(record["topic"], post_num)
        await context.bot.send_message(chat_id=chat_id, text=text)

        record["total_sent"]     += 1
        record["posts_today"]    += 1
        record["last_post_date"]  = today
        record["last_post_time"]  = datetime.utcnow().isoformat()
        _set(chat_id, record)

        day = min(record["total_sent"] // POSTS_PER_DAY + 1, MAX_DAYS)
        logger.info(
            f"[{chat_id}] Post {record['total_sent']}/{MAX_TOTAL} sent — "
            f"day {day}/{MAX_DAYS}, today {record['posts_today']}/{POSTS_PER_DAY}"
        )

    except Exception as e:
        logger.error(f"[{chat_id}] Failed to send post #{post_num}: {e}")
        if any(k in str(e) for k in ("kicked", "Forbidden", "chat not found", "blocked")):
            logger.warning(f"[{chat_id}] Bot removed from channel — deactivating.")
            record["active"] = False
            _set(chat_id, record)
            context.job.schedule_removal()


def _register_job(app: Application, chat_id: int) -> None:
    """Register the repeating job for a channel."""
    # Remove any existing job first
    for job in app.job_queue.get_jobs_by_name(str(chat_id)):
        job.schedule_removal()

    app.job_queue.run_repeating(
        callback=_posting_job,
        interval=POST_INTERVAL_MIN * 60,
        first=POST_INTERVAL_MIN * 60,
        chat_id=chat_id,
        name=str(chat_id),
    )
    logger.info(f"[{chat_id}] Job registered — every {POST_INTERVAL_MIN} min.")


# ── Command handlers ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    msg = (
        "👋 *Hello! I'm your AI Channel Manager Bot.*\n\n"
        "Add me as admin to any channel, then use:\n\n"
        "`/write [describe your channel]`\n\n"
        "I'll generate AI content and post automatically:\n"
        f"• Every {POST_INTERVAL_MIN} minutes\n"
        f"• {POSTS_PER_DAY} posts/day × {MAX_DAYS} days = {MAX_TOTAL} total\n\n"
        "Works in every channel you add me to — independently."
    )
    if chat.type != "private":
        msg = (
            "👋 *Bot is ready in this channel!*\n\n"
            "Use:\n`/write [describe your channel]`\n\n"
            f"I'll post every {POST_INTERVAL_MIN} min — "
            f"{POSTS_PER_DAY}/day for {MAX_DAYS} days ({MAX_TOTAL} total)."
        )
    await update.effective_message.reply_text(msg, parse_mode="Markdown")


async def cmd_write(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    msg  = update.effective_message

    # Validate bot permissions
    try:
        member = await chat.get_member(context.bot.id)
        if not getattr(member, "can_post_messages", True):
            await msg.reply_text(
                "❌ I need *Post Messages* admin permission.\n"
                "Please update my admin settings and try again.",
                parse_mode="Markdown",
            )
            return
    except Exception as e:
        logger.warning(f"[{chat.id}] Could not check permissions: {e}")

    topic = " ".join(context.args).strip() if context.args else ""

    if len(topic) < 10:
        await msg.reply_text(
            "❌ Please describe your channel after /write.\n\n"
            "*Example:*\n"
            "`/write A daily crypto channel covering Bitcoin and DeFi "
            "for beginner traders — tips, analysis, and market insights`",
            parse_mode="Markdown",
        )
        return

    # Block if a campaign is already running
    existing = _get(chat.id)
    if existing and existing.get("active") and existing["total_sent"] < MAX_TOTAL:
        sent = existing["total_sent"]
        day  = min(sent // POSTS_PER_DAY + 1, MAX_DAYS)
        await msg.reply_text(
            "⚠️ *Campaign already running!*\n\n"
            f"📬 Posts sent: {sent}/{MAX_TOTAL}\n"
            f"📅 Day: {day}/{MAX_DAYS}\n\n"
            "Use /stop to cancel it first, then /write again.",
            parse_mode="Markdown",
        )
        return

    # Save record and start scheduler
    record = {
        "chat_id":        chat.id,
        "topic":          topic,
        "total_sent":     0,
        "posts_today":    0,
        "last_post_date": None,
        "last_post_time": None,
        "active":         True,
        "started_at":     datetime.utcnow().isoformat(),
    }
    _set(chat.id, record)
    _register_job(context.application, chat.id)

    await msg.reply_text(
        "✅ *Campaign started!*\n\n"
        f"📌 Topic: _{topic}_\n\n"
        f"📦 {MAX_TOTAL} posts queued\n"
        f"📅 {POSTS_PER_DAY} posts/day × {MAX_DAYS} days\n"
        f"⏰ One post every {POST_INTERVAL_MIN} minutes\n\n"
        f"🚀 First post in {POST_INTERVAL_MIN} minutes!",
        parse_mode="Markdown",
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat   = update.effective_chat
    record = _get(chat.id)

    if not record:
        await update.effective_message.reply_text(
            "ℹ️ No campaign found for this channel.\nUse /write to start one."
        )
        return

    sent      = record["total_sent"]
    today_cnt = record.get("posts_today", 0)
    remaining = MAX_TOTAL - sent
    day       = min(sent // POSTS_PER_DAY + 1, MAX_DAYS)
    status    = "🟢 Running" if record.get("active") else "🔴 Stopped"

    next_str = f"~{POST_INTERVAL_MIN} min"
    if record.get("last_post_time"):
        try:
            last = datetime.fromisoformat(record["last_post_time"])
            nxt  = last + timedelta(minutes=POST_INTERVAL_MIN)
            mins = max(0, int((nxt - datetime.utcnow()).total_seconds() / 60))
            next_str = f"~{mins} min"
        except Exception:
            pass

    topic_short = record["topic"][:100] + ("…" if len(record["topic"]) > 100 else "")
    await update.effective_message.reply_text(
        f"📊 *Campaign Status*\n\n"
        f"🔖 _{topic_short}_\n\n"
        f"{status}\n\n"
        f"📬 Total sent: {sent}/{MAX_TOTAL}\n"
        f"📅 Today: {today_cnt}/{POSTS_PER_DAY}\n"
        f"🗓 Day: {day}/{MAX_DAYS}\n"
        f"⏳ Remaining: {remaining} posts\n"
        f"⏰ Next post in: {next_str}",
        parse_mode="Markdown",
    )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat   = update.effective_chat
    record = _get(chat.id)

    if not record or not record.get("active"):
        await update.effective_message.reply_text("ℹ️ No active campaign to stop.")
        return

    record["active"] = False
    _set(chat.id, record)
    for job in context.job_queue.get_jobs_by_name(str(chat.id)):
        job.schedule_removal()

    await update.effective_message.reply_text(
        f"🛑 *Campaign stopped.*\n\n"
        f"Posts sent: {record['total_sent']}/{MAX_TOTAL}\n\n"
        f"Use /write to start a new campaign.",
        parse_mode="Markdown",
    )


async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    for job in context.job_queue.get_jobs_by_name(str(chat.id)):
        job.schedule_removal()
    _delete(chat.id)
    await update.effective_message.reply_text(
        "🔄 *Campaign cleared.*\n\nUse /write to start a fresh campaign.",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "📖 *Commands*\n\n"
        "/start — Welcome and instructions\n"
        "/write \\[topic\\] — Start a new campaign\n"
        "/status — Check campaign progress\n"
        "/stop — Pause the current campaign\n"
        "/restart — Clear everything and start fresh\n"
        "/help — Show this message\n\n"
        "*How to use:*\n"
        "1\\. Add me as admin with Post Messages permission\n"
        "2\\. In the channel: `/write Daily crypto tips for beginners`\n"
        f"3\\. I post every {POST_INTERVAL_MIN} min — "
        f"{POSTS_PER_DAY}/day for {MAX_DAYS} days \\({MAX_TOTAL} total\\)",
        parse_mode="MarkdownV2",
    )


# ── Bot membership events ──────────────────────────────────────────────────────

async def on_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detect bot being added or removed from channels."""
    if not update.my_chat_member:
        return

    status = update.my_chat_member.new_chat_member.status
    chat   = update.effective_chat

    if status == "administrator":
        logger.info(f"Bot added as admin to: {getattr(chat, 'title', chat.id)} ({chat.id})")
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    "🎉 *Thanks for adding me!*\n\n"
                    "I'm ready to post content. Use:\n"
                    "`/write [describe your channel]`"
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"[{chat.id}] Welcome message failed: {e}")

    elif status in ("left", "kicked"):
        logger.info(f"Bot removed from: {getattr(chat, 'title', chat.id)} ({chat.id})")
        record = _get(chat.id)
        if record:
            record["active"] = False
            _set(chat.id, record)
        for job in context.job_queue.get_jobs_by_name(str(chat.id)):
            job.schedule_removal()


# ── Error handler ──────────────────────────────────────────────────────────────

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Unhandled error: {context.error}", exc_info=context.error)


# ── Startup: resume all active campaigns ─────────────────────────────────────

async def on_startup(app: Application) -> None:
    """Called once after PTB initializes. Resumes all active campaigns."""
    logger.info("=" * 60)
    logger.info("ON_STARTUP CALLED - Resuming campaigns...")
    logger.info("=" * 60)
    
    all_records = _load()
    resumed = 0
    for chat_id_str, record in all_records.items():
        if record.get("active") and record["total_sent"] < MAX_TOTAL:
            _register_job(app, int(chat_id_str))
            logger.info(
                f"[{chat_id_str}] Resumed — "
                f"{record['total_sent']}/{MAX_TOTAL} posts sent."
            )
            resumed += 1
    logger.info(f"Startup complete — resumed {resumed} active campaign(s).")
    logger.info("Bot is now running and listening for commands!")


# ── Entry point ────────────────────────────────────────────────────────────────

async def main_async() -> None:
    """Async main function to run the bot"""
    logger.info("Building application...")
    
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(on_startup)
        .build()
    )

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("write",   cmd_write))
    app.add_handler(CommandHandler("status",  cmd_status))
    app.add_handler(CommandHandler("stop",    cmd_stop))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(ChatMemberHandler(on_member_update))
    app.add_error_handler(on_error)

    logger.info("Starting bot polling...")
    await app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


def main() -> None:
    """Synchronous entry point for Render"""
    logger.info("=" * 60)
    logger.info("BOT MAIN FUNCTION CALLED")
    logger.info("=" * 60)
    
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
