"""
Telegram Channel Auto-Poster Bot — Definitive Version
======================================================
Synthesizes every bug found and fixed across all versions reviewed:

FIXED FROM ORIGINAL SHARED DOCUMENT (Python version):
  [B1] threading.Lock deadlock — APScheduler sync thread called async bot.send_message()
  [B2] Async/sync mismatch — coroutine never awaited, posts never sent
  [B3] openai.api_key = ... is v0 syntax, silently ignored by openai v1.x
  [B4] render.yaml type: web requires HTTP port binding — crashes on Render
  [B5] All state in-memory — any restart wipes all running campaigns

FIXED FROM KIMI AGENT ZIP:
  [B6] Two-step /write captured ANY admin's next message as topic — race condition
  [B7] No daily post limit — all 50 posts fired in ~17 hours, not 5 days
  [B8] Redundant APScheduler pin conflicted with PTB's bundled version

ARCHITECTURE DECISIONS (from best-of all versions):
  - PTB's native job_queue (no APScheduler at all — eliminates B1, B2, B8)
  - AsyncOpenAI (correct v1.x — eliminates B3)
  - render.yaml type: worker (eliminates B4)
  - JSON persistence + startup resume (eliminates B5)
  - /write [topic] inline args (eliminates B6)
  - Date-aware daily counter (eliminates B7)
  - ChatMemberHandler — auto-cleanup when bot is removed from a channel
"""

import os
import json
import logging
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

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bot")

# ── Environment ───────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")

if not TELEGRAM_BOT_TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN is not set.")
if not OPENAI_API_KEY:
    raise SystemExit("OPENAI_API_KEY is not set.")

# Campaign constants (override via env vars if needed)
POST_INTERVAL_MIN = int(os.getenv("POST_INTERVAL_MINUTES", "20"))
POSTS_PER_DAY     = int(os.getenv("POSTS_PER_DAY",         "10"))
MAX_DAYS          = int(os.getenv("MAX_DAYS",               "5"))
MAX_TOTAL         = POSTS_PER_DAY * MAX_DAYS  # 50

# OpenAI (FIX B3: correct AsyncOpenAI v1.x — no module-level api_key assignment)
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ── Persistence ───────────────────────────────────────────────────────────────
# (FIX B5: JSON file replaces pure in-memory dict)

_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "channels.json")


def _load() -> dict:
    os.makedirs(os.path.dirname(_DATA_FILE), exist_ok=True)
    if not os.path.exists(_DATA_FILE):
        return {}
    try:
        with open(_DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _dump(data: dict) -> None:
    os.makedirs(os.path.dirname(_DATA_FILE), exist_ok=True)
    with open(_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


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


# ── Scheduler job (runs every POST_INTERVAL_MIN minutes per channel) ───────────
# FIX B1+B2: PTB's native job_queue runs this as a proper async coroutine on
# the same event loop — no threading, no APScheduler, no unawaited coroutines.

async def _posting_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id: int = context.job.chat_id  # type: ignore[assignment]
    record = _get(chat_id)

    # ── Guard: deactivated externally ────────────────────────────────────────
    if not record or not record.get("active"):
        context.job.schedule_removal()
        logger.info(f"[{chat_id}] Job removed — campaign inactive.")
        return

    total_sent = record["total_sent"]

    # ── Guard: campaign complete ──────────────────────────────────────────────
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

    # ── FIX B7: Daily post limit ──────────────────────────────────────────────
    today = str(date.today())
    if record.get("last_post_date") != today:
        record["posts_today"]    = 0
        record["last_post_date"] = today
        _set(chat_id, record)
        logger.info(f"[{chat_id}] New day — daily counter reset.")

    if record["posts_today"] >= POSTS_PER_DAY:
        logger.info(f"[{chat_id}] Daily limit ({POSTS_PER_DAY}) reached — skipping tick.")
        return

    # ── Generate and post ─────────────────────────────────────────────────────
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
        # Bot was kicked or banned — deactivate cleanly
        if any(k in str(e) for k in ("kicked", "Forbidden", "chat not found", "blocked")):
            logger.warning(f"[{chat_id}] Bot removed from channel — deactivating.")
            record["active"] = False
            _set(chat_id, record)
            context.job.schedule_removal()


def _register_job(app: Application, chat_id: int) -> None:
    """Register (or re-register) the 20-min repeating job for a channel."""
    # Remove any existing job first
    for job in app.job_queue.get_jobs_by_name(str(chat_id)):
        job.schedule_removal()

    app.job_queue.run_repeating(
        callback=_posting_job,
        interval=POST_INTERVAL_MIN * 60,
        first=POST_INTERVAL_MIN * 60,   # First post after 20 min
        chat_id=chat_id,
        name=str(chat_id),
    )
    logger.info(f"[{chat_id}] Job registered — every {POST_INTERVAL_MIN} min.")


# ── /start ─────────────────────────────────────────────────────────────────────

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


# ── /write ─────────────────────────────────────────────────────────────────────
# FIX B6: Topic is read from inline args (/write [topic]), NOT from a subsequent
# message. The two-step flow had a race condition — any admin's next message in
# the channel would be silently captured as the topic.

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


# ── /status ────────────────────────────────────────────────────────────────────

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


# ── /stop ──────────────────────────────────────────────────────────────────────

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


# ── /restart ───────────────────────────────────────────────────────────────────

async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    for job in context.job_queue.get_jobs_by_name(str(chat.id)):
        job.schedule_removal()
    _delete(chat.id)
    await update.effective_message.reply_text(
        "🔄 *Campaign cleared.*\n\nUse /write to start a fresh campaign.",
        parse_mode="Markdown",
    )


# ── /help ──────────────────────────────────────────────────────────────────────

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


# ── Startup: resume all active campaigns (FIX B5) ─────────────────────────────

async def on_startup(app: Application) -> None:
    """
    Called once after PTB initializes.
    Reloads all active channel records from JSON and re-registers their jobs.
    Without this, every Render.com restart would silently abandon all campaigns.
    """
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


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(on_startup)          # Resume campaigns on restart
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

    logger.info("Starting bot (long polling)...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,      # Ignore messages sent while bot was offline
    )


if __name__ == "__main__":
    main()
