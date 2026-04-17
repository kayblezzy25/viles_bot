"""
Telegram Multi-Channel AI Content Bot
Main bot implementation with command handlers and scheduling.
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update, Chat
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    JobQueue,
)
from telegram.constants import ChatType

from database import ChannelManager, PostManager, init_db
from openai_client import ContentGenerator, get_fallback_content
from keep_alive import setup_self_healing

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 10000))

# Campaign settings
POSTS_TOTAL = 50
POSTS_PER_DAY = 10
INTERVAL_MINUTES = 20


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /start command.
    Works in both private chats and channels.
    """
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == ChatType.PRIVATE:
        # Private chat - welcome message
        welcome_text = """👋 <b>Welcome to the AI Content Bot!</b>

I'm your automated content generation assistant for Telegram channels.

<b>How to use me:</b>
1. Add me to any channel as an <b>administrator</b>
2. Give me permission to post messages
3. In the channel, use: <code>/write [your topic/question]</code>

<b>Example:</b>
<code>/write Daily tips about productivity and time management</code>

<b>What I'll do:</b>
• Generate 50 AI-powered posts about your topic
• Post every 20 minutes (10 posts per day)
• Run for 5 days automatically
• No channel ID setup needed!

Ready to get started? Add me to a channel and use /write!"""
        
        await context.bot.send_message(
            chat_id=chat.id,
            text=welcome_text,
            parse_mode="HTML"
        )
    else:
        # Channel or group - verify admin status
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member.status in ["administrator", "creator"]:
                channel = ChannelManager.get_channel(chat.id)
                
                if channel and channel.status == "active":
                    status_text = f"""✅ <b>Bot Active in {chat.title}</b>

Topic: {channel.prompt_text[:50]}...
Posts remaining: {channel.posts_remaining}/50
Posts today: {channel.posts_today}/10
Status: {channel.status}

Use <code>/write [new topic]</code> to start a new campaign."""
                else:
                    status_text = f"""🤖 <b>Bot Ready in {chat.title}</b>

No active campaign. Use <code>/write [topic]</code> to start automated posting.

<b>Example:</b>
<code>/write Tips for healthy living</code>"""
                
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=status_text,
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Error in channel start command: {e}")


async def write_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /write command - the main activation trigger.
    Usage: /write [topic/question]
    """
    chat = update.effective_chat
    user = update.effective_user
    message_text = update.message.text if update.message else ""
    
    # Only work in channels/supergroups
    if chat.type not in [ChatType.CHANNEL, ChatType.SUPERGROUP, ChatType.GROUP]:
        await context.bot.send_message(
            chat_id=chat.id,
            text="⚠️ The /write command only works in channels. Add me to a channel and try again!"
        )
        return
    
    # Verify the user is an admin
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ["administrator", "creator"]:
            await context.bot.send_message(
                chat_id=chat.id,
                text="⚠️ Only channel administrators can use the /write command."
            )
            return
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        await context.bot.send_message(
            chat_id=chat.id,
            text="⚠️ Could not verify admin status. Please try again."
        )
        return
    
    # Verify bot has posting permissions
    try:
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if not bot_member.can_post_messages:
            await context.bot.send_message(
                chat_id=chat.id,
                text="⚠️ I need permission to post messages in this channel. Please make me an admin with posting rights."
            )
            return
    except Exception as e:
        logger.error(f"Error checking bot permissions: {e}")
    
    # Extract prompt from command
    # Remove "/write" from the beginning
    parts = message_text.split(maxsplit=1)
    if len(parts) < 2:
        await context.bot.send_message(
            chat_id=chat.id,
            text="""⚠️ Please provide a topic after /write

<b>Usage:</b>
<code>/write [your topic or question]</code>

<b>Examples:</b>
<code>/write Daily productivity tips</code>
<code>/write Interesting facts about space</code>
<code>/write Marketing strategies for small businesses</code>""",
            parse_mode="HTML"
        )
        return
    
    prompt = parts[1].strip()
    
    if len(prompt) < 5:
        await context.bot.send_message(
            chat_id=chat.id,
            text="⚠️ Topic is too short. Please provide a more detailed description (at least 5 characters)."
        )
        return
    
    if len(prompt) > 500:
        prompt = prompt[:497] + "..."
    
    # Send confirmation message
    confirm_message = await context.bot.send_message(
        chat_id=chat.id,
        text=f"🔄 <b>Starting Campaign</b>\n\nTopic: {prompt}\nGenerating first post...",
        parse_mode="HTML"
    )
    
    # Create/update channel in database
    channel = ChannelManager.create_or_update_channel(
        chat_id=chat.id,
        prompt_text=prompt,
        posts_total=POSTS_TOTAL
    )
    
    # Generate first post immediately
    first_post_content = await ContentGenerator.generate_post(
        topic=prompt,
        post_number=1,
        total_posts=POSTS_TOTAL
    )
    
    if not first_post_content:
        first_post_content = get_fallback_content(prompt)
    
    # Send first post
    try:
        sent_message = await context.bot.send_message(
            chat_id=chat.id,
            text=first_post_content,
            parse_mode="HTML",
            disable_web_page_preview=False
        )
        
        # Record the post
        PostManager.create_post(
            chat_id=chat.id,
            post_number=1,
            content=first_post_content,
            scheduled_at=datetime.utcnow()
        )
        
        # Update channel counter
        ChannelManager.decrement_post_counter(chat.id)
        
        # Update confirmation message
        await context.bot.edit_message_text(
            chat_id=chat.id,
            message_id=confirm_message.message_id,
            text=f"""✅ <b>Campaign Started!</b>

📌 Topic: {prompt}
📊 Posts: 1/{POSTS_TOTAL} sent
⏰ Next post: in {INTERVAL_MINUTES} minutes
📅 Duration: 5 days (10 posts/day)

I'll continue posting automatically every {INTERVAL_MINUTES} minutes.""",
            parse_mode="HTML"
        )
        
        # Schedule the remaining posts
        await schedule_channel_posts(context, chat.id, prompt)
        
    except Exception as e:
        logger.error(f"Error sending first post: {e}")
        await context.bot.edit_message_text(
            chat_id=chat.id,
            message_id=confirm_message.message_id,
            text=f"❌ Error starting campaign: {str(e)}\n\nPlease try again."
        )


async def schedule_channel_posts(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    prompt: str
) -> None:
    """
    Schedule the remaining posts for a channel.
    Uses JobQueue for scheduling.
    """
    job_queue: JobQueue = context.job_queue
    
    # Remove existing jobs for this channel
    current_jobs = job_queue.get_jobs_by_name(f"channel_{chat_id}")
    for job in current_jobs:
        job.schedule_removal()
    
    # Schedule the repeating job
    # First post was already sent, so schedule from post 2
    job_queue.run_repeating(
        callback=post_callback,
        interval=timedelta(minutes=INTERVAL_MINUTES),
        first=timedelta(minutes=INTERVAL_MINUTES),
        chat_id=chat_id,
        name=f"channel_{chat_id}",
        data={
            "prompt": prompt,
            "chat_id": chat_id
        }
    )
    
    logger.info(f"Scheduled posts for channel {chat_id}")


async def post_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Callback function for scheduled posts.
    Called every 20 minutes for active channels.
    """
    job = context.job
    chat_id = job.data["chat_id"]
    prompt = job.data["prompt"]
    
    # Get current channel state
    channel = ChannelManager.get_channel(chat_id)
    
    if not channel:
        logger.warning(f"Channel {chat_id} not found, removing job")
        job.schedule_removal()
        return
    
    if channel.status != "active":
        logger.info(f"Channel {chat_id} is {channel.status}, skipping post")
        return
    
    if channel.posts_remaining <= 0:
        logger.info(f"Channel {chat_id} completed all posts")
        job.schedule_removal()
        
        # Send completion message
        try:
            completion_msg = await ContentGenerator.generate_completion_message(
                channel_name="",
                total_posts=POSTS_TOTAL
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=completion_msg,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Error sending completion message: {e}")
        return
    
    # Check daily limit
    if channel.posts_today >= POSTS_PER_DAY:
        logger.info(f"Channel {chat_id} reached daily limit ({POSTS_PER_DAY} posts)")
        # Don't remove job, just skip this iteration
        # Reset happens at midnight via separate job
        return
    
    # Calculate post number
    post_number = POSTS_TOTAL - channel.posts_remaining + 1
    
    # Generate content
    content = await ContentGenerator.generate_post(
        topic=prompt,
        post_number=post_number,
        total_posts=POSTS_TOTAL
    )
    
    if not content:
        content = get_fallback_content(prompt)
    
    # Send the post
    try:
        sent_message = await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode="HTML",
            disable_web_page_preview=False
        )
        
        # Record post
        PostManager.create_post(
            chat_id=chat_id,
            post_number=post_number,
            content=content,
            scheduled_at=datetime.utcnow()
        )
        
        # Update counter
        ChannelManager.decrement_post_counter(chat_id)
        
        logger.info(f"Posted #{post_number} to channel {chat_id}")
        
    except Exception as e:
        logger.error(f"Error posting to channel {chat_id}: {e}")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Admin command to check bot status.
    Usage: /status
    """
    chat = update.effective_chat
    user = update.effective_user
    
    # Only admins can check status
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ["administrator", "creator"]:
            return
    except:
        return
    
    if chat.type == ChatType.PRIVATE:
        # Show all channels (admin overview)
        channels = ChannelManager.get_all_channels()
        
        if not channels:
            await context.bot.send_message(
                chat_id=chat.id,
                text="No active channels."
            )
            return
        
        status_lines = ["<b>Channel Status Overview</b>\n"]
        for ch in channels:
            status_lines.append(
                f"• {ch.chat_id}: {ch.status} ({ch.posts_remaining} remaining)"
            )
        
        await context.bot.send_message(
            chat_id=chat.id,
            text="\n".join(status_lines),
            parse_mode="HTML"
        )
    else:
        # Show specific channel status
        channel = ChannelManager.get_channel(chat.id)
        
        if not channel:
            await context.bot.send_message(
                chat_id=chat.id,
                text="No active campaign in this channel."
            )
            return
        
        progress_bar = "█" * (POSTS_TOTAL - channel.posts_remaining) + "░" * channel.posts_remaining
        
        status_text = f"""<b>Campaign Status</b>

Topic: {channel.prompt_text[:60]}...
Progress: [{progress_bar}]
Posts: {POSTS_TOTAL - channel.posts_remaining}/{POSTS_TOTAL}
Remaining: {channel.posts_remaining}
Today: {channel.posts_today}/{POSTS_PER_DAY}
Status: {channel.status}

Next post: {channel.next_post_at.strftime('%Y-%m-%d %H:%M UTC') if channel.next_post_at else 'N/A'}"""
        
        await context.bot.send_message(
            chat_id=chat.id,
            text=status_text,
            parse_mode="HTML"
        )


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Stop posting for a channel.
    Usage: /stop
    """
    chat = update.effective_chat
    user = update.effective_user
    
    # Verify admin
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ["administrator", "creator"]:
            return
    except:
        return
    
    if chat.type not in [ChatType.CHANNEL, ChatType.SUPERGROUP, ChatType.GROUP]:
        return
    
    channel = ChannelManager.get_channel(chat.id)
    if not channel:
        await context.bot.send_message(
            chat_id=chat.id,
            text="No active campaign to stop."
        )
        return
    
    # Pause the channel
    ChannelManager.pause_channel(chat.id)
    
    # Remove scheduled jobs
    job_queue: JobQueue = context.job_queue
    jobs = job_queue.get_jobs_by_name(f"channel_{chat.id}")
    for job in jobs:
        job.schedule_removal()
    
    await context.bot.send_message(
        chat_id=chat.id,
        text=f"⏸️ Campaign paused. {channel.posts_remaining} posts remaining.\nUse /write to start a new campaign."
    )


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Resume posting for a channel.
    Usage: /resume
    """
    chat = update.effective_chat
    user = update.effective_user
    
    # Verify admin
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ["administrator", "creator"]:
            return
    except:
        return
    
    if chat.type not in [ChatType.CHANNEL, ChatType.SUPERGROUP, ChatType.GROUP]:
        return
    
    channel = ChannelManager.get_channel(chat.id)
    if not channel or channel.status != "paused":
        await context.bot.send_message(
            chat_id=chat.id,
            text="No paused campaign to resume."
        )
        return
    
    # Resume the channel
    ChannelManager.resume_channel(chat.id)
    
    # Reschedule posts
    await schedule_channel_posts(context, chat.id, channel.prompt_text)
    
    await context.bot.send_message(
        chat_id=chat.id,
        text=f"▶️ Campaign resumed. {channel.posts_remaining} posts remaining."
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors."""
    logger.error(f"Update {update} caused error: {context.error}")


async def post_init(application: Application) -> None:
    """Post-initialization hook to setup self-healing and keep-alive."""
    try:
        # Setup self-healing scheduler (restore jobs from database)
        await setup_self_healing(application)
        logger.info("Self-healing scheduler setup complete!")
    except Exception as e:
        logger.warning(f"Self-healing setup failed (non-critical): {e}")
    
    logger.info("Bot initialization complete!")


def main() -> None:
    """Start the bot."""
    # Initialize database
    init_db()
    
    # Build application
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("write", write_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("resume", resume_command))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Setup webhook or polling based on environment
    if WEBHOOK_URL:
        logger.info(f"Starting bot with webhook: {WEBHOOK_URL}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL,
        )
    else:
        logger.info("Starting bot with polling")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
