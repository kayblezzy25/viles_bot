import os
import asyncio
import logging
from datetime import datetime
from typing import Dict
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from openai import OpenAI

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_api_key = os.getenv('OPENAI_API_KEY')
if openai_api_key:
    openai_client = OpenAI(api_key=openai_api_key)
else:
    logger.error("OPENAI_API_KEY not found in environment variables")
    openai_client = None

class ChannelPostScheduler:
    def __init__(self):
        self.active_channels: Dict[int, Dict] = {}
        
    def add_channel(self, chat_id: int, topic: str, content_plan: str):
        self.active_channels[chat_id] = {
            'topic': topic,
            'content_plan': content_plan,
            'start_time': datetime.now(),
            'posts_today': 0,
            'total_posts': 0,
            'day_number': 1,
            'last_post_time': None,
            'daily_count': 0,
            'current_day': 1
        }
        logger.info(f"Channel {chat_id} added to schedule with topic: {topic}")
    
    def remove_channel(self, chat_id: int):
        if chat_id in self.active_channels:
            del self.active_channels[chat_id]
            logger.info(f"Channel {chat_id} removed from schedule")
    
    def can_post(self, chat_id: int) -> bool:
        if chat_id not in self.active_channels:
            return False
            
        channel_data = self.active_channels[chat_id]
        
        if channel_data['daily_count'] >= 10:
            return False
            
        if channel_data['total_posts'] >= 50:
            return False
            
        if channel_data['last_post_time']:
            days_passed = (datetime.now() - channel_data['start_time']).days
            if days_passed >= channel_data['current_day']:
                channel_data['current_day'] = days_passed + 1
                channel_data['daily_count'] = 0
                
        return True
    
    def record_post(self, chat_id: int):
        if chat_id in self.active_channels:
            self.active_channels[chat_id]['last_post_time'] = datetime.now()
            self.active_channels[chat_id]['daily_count'] += 1
            self.active_channels[chat_id]['total_posts'] += 1
            logger.info(f"Post recorded for channel {chat_id}. Daily: {self.active_channels[chat_id]['daily_count']}/10, Total: {self.active_channels[chat_id]['total_posts']}/50")
    
    def get_status(self, chat_id: int) -> Dict:
        if chat_id in self.active_channels:
            return self.active_channels[chat_id]
        return None

# Initialize scheduler
scheduler = ChannelPostScheduler()

async def generate_post_content(topic: str, content_plan: str, post_number: int) -> str:
    if not openai_client:
        return f"📝 Post #{post_number}\n\n📌 Topic: {topic}\n\n💡 {content_plan}\n\n_This is a template post. Configure OpenAI API for AI-generated content._"
    
    try:
        prompt = f"""Create an engaging Telegram channel post about: {topic}
        
Content guidelines: {content_plan}

Post #{post_number} in a series of 50 posts.
Make it informative, engaging, and suitable for a Telegram channel.
Keep it between 200-400 words.
Include relevant emojis where appropriate.
Don't use markdown formatting that might not render well."""
        
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a professional content creator for Telegram channels. Create engaging, well-structured posts."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.7
        )
        
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error generating content: {e}")
        return f"📝 Post #{post_number}\n\n📌 Topic: {topic}\n\n💡 {content_plan}\n\n_Error generating AI content - using template_"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - Works everywhere"""
    chat_type = update.effective_chat.type
    logger.info(f"Start command received in {chat_type} chat: {update.effective_chat.id}")
    
    welcome_message = (
        "🤖 *Channel Content Bot is Active!*\n\n"
        "I'm ready to help you automate content posting!\n\n"
        "📝 *Available Commands:*\n"
        "/start - Show this welcome message\n"
        "/write - Start content setup (use in channel/group)\n"
        "/status - Check posting status\n"
        "/stop - Stop posting schedule\n\n"
        "💡 *How to use:*\n"
        "1. Add me as admin to your channel\n"
        "2. Send /write in the channel\n"
        "3. Answer the setup questions\n"
        "4. I'll start posting automatically!\n\n"
        "_In groups/channels, use commands like: /start@viles2_bot_"
    )
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def write(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /write command - Start content setup"""
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    user_id = update.effective_user.id
    
    logger.info(f"Write command received from user {user_id} in chat {chat_id} (type: {chat_type})")
    
    # Store chat_id for the setup process
    context.user_data['setup_stage'] = 'awaiting_topic'
    context.user_data['channel_id'] = chat_id
    
    setup_message = (
        "📝 *Content Setup Started!*\n\n"
        "I'll ask you a few questions to set up automated posting for this channel.\n\n"
        "✨ *Question 1 of 2:*\n"
        "What is the main *topic/theme* of this channel?\n\n"
        "_Reply with your answer below_"
    )
    
    await update.message.reply_text(setup_message, parse_mode='Markdown')

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check posting status for the channel"""
    chat_id = update.effective_chat.id
    
    channel_data = scheduler.get_status(chat_id)
    
    if channel_data:
        status_message = (
            f"📊 *Current Posting Status*\n\n"
            f"📌 *Topic:* {channel_data['topic']}\n"
            f"📝 *Daily Posts:* {channel_data['daily_count']}/10\n"
            f"📈 *Total Posts:* {channel_data['total_posts']}/50\n"
            f"📅 *Current Day:* {channel_data['current_day']}/5\n"
            f"⏰ *Started:* {channel_data['start_time'].strftime('%Y-%m-%d %H:%M')}\n\n"
        )
        
        if scheduler.can_post(chat_id):
            next_post_time = "Ready now"
            if channel_data['last_post_time']:
                time_since_last = datetime.now() - channel_data['last_post_time']
                if time_since_last.seconds < 1200:
                    minutes_left = 20 - (time_since_last.seconds // 60)
                    next_post_time = f"in ~{minutes_left} minutes"
            status_message += f"⏭ *Next Post:* {next_post_time}"
        else:
            if channel_data['daily_count'] >= 10:
                status_message += "⏸ *Status:* Daily limit reached (10/10 posts today)"
            elif channel_data['total_posts'] >= 50:
                status_message += "✅ *Status:* Completed all 50 posts!"
                
        await update.message.reply_text(status_message, parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "❌ *No active posting schedule*\n\n"
            "Use /write to set up automated posting for this channel.",
            parse_mode='Markdown'
        )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop posting in the channel"""
    chat_id = update.effective_chat.id
    
    if scheduler.get_status(chat_id):
        scheduler.remove_channel(chat_id)
        await update.message.reply_text(
            "🛑 *Posting Schedule Stopped*\n\n"
            "Automated posting has been stopped for this channel.\n"
            "Use /write to start a new schedule.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "ℹ️ No active posting schedule to stop.",
            parse_mode='Markdown'
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-command messages during setup"""
    # Check if we're in setup mode
    if 'setup_stage' not in context.user_data:
        # If not in setup, check if it's a group/channel mention
        if update.effective_chat.type in ['group', 'supergroup']:
            # Bot was mentioned but not with a command
            if update.message.text and '@viles2_bot' in update.message.text:
                await update.message.reply_text(
                    "👋 *Hello! I'm active and ready!*\n\n"
                    "Use these commands to control me:\n"
                    "/start@viles2_bot - Welcome message\n"
                    "/write@viles2_bot - Setup content posting\n"
                    "/status@viles2_bot - Check status\n"
                    "/stop@viles2_bot - Stop posting\n\n"
                    "_Make sure I'm an admin to post messages!_",
                    parse_mode='Markdown'
                )
        return
        
    stage = context.user_data['setup_stage']
    message_text = update.message.text
    chat_id = context.user_data.get('channel_id')
    
    if stage == 'awaiting_topic':
        context.user_data['topic'] = message_text
        context.user_data['setup_stage'] = 'awaiting_plan'
        
        await update.message.reply_text(
            "✅ *Topic saved!*\n\n"
            "✨ *Question 2 of 2:*\n"
            "What *type of content* should I create?\n\n"
            "📋 *Examples:*\n"
            "• Educational posts with tips and tricks\n"
            "• Daily news updates and analysis\n"
            "• Inspirational quotes and motivation\n"
            "• Product reviews and recommendations\n"
            "• Industry insights and trends\n\n"
            "_Describe your content plan below_",
            parse_mode='Markdown'
        )
    
    elif stage == 'awaiting_plan':
        topic = context.user_data['topic']
        content_plan = message_text
        
        # Add channel to scheduler
        scheduler.add_channel(chat_id, topic, content_plan)
        
        await update.message.reply_text(
            f"🎉 *Content Schedule Created Successfully!*\n\n"
            f"📌 *Topic:* {topic}\n"
            f"💡 *Content Plan:* {content_plan}\n\n"
            f"📊 *Posting Schedule:*\n"
            f"• 📝 10 posts per day\n"
            f"• ⏰ Every 20 minutes\n"
            f"• 🎯 Total 50 posts over 5 days\n\n"
            f"🚀 *First post coming in 1 minute!*\n\n"
            f"_Use /status to check progress_",
            parse_mode='Markdown'
        )
        
        # Clear setup data
        context.user_data.clear()
        
        # Start posting loop
        asyncio.create_task(posting_loop(chat_id, context))

async def posting_loop(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Main posting loop for a channel"""
    await asyncio.sleep(60)  # Wait 1 minute before first post
    
    bot = context.bot
    
    while True:
        channel_data = scheduler.get_status(chat_id)
        if not channel_data:
            break
            
        if scheduler.can_post(chat_id):
            post_number = channel_data['total_posts'] + 1
            
            try:
                content = await generate_post_content(
                    channel_data['topic'],
                    channel_data['content_plan'],
                    post_number
                )
                
                await bot.send_message(
                    chat_id=chat_id,
                    text=content,
                    disable_web_page_preview=True
                )
                
                scheduler.record_post(chat_id)
                logger.info(f"✅ Posted #{post_number} to channel {chat_id}")
                
                updated_data = scheduler.get_status(chat_id)
                if updated_data and updated_data['total_posts'] >= 50:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="🎉 *Schedule Complete!*\n\nAll 50 posts have been sent successfully!\n\nThank you for using Channel Content Bot! 🚀",
                        parse_mode='Markdown'
                    )
                    scheduler.remove_channel(chat_id)
                    break
                    
            except Exception as e:
                logger.error(f"Error posting to channel {chat_id}: {e}")
        
        await asyncio.sleep(1200)  # 20 minutes

def main():
    """Start the bot"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN not set!")
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")
    
    logger.info("🤖 Starting Channel Content Bot...")
    
    # Create application
    application = Application.builder().token(token).build()
    
    # Add command handlers - they will work with or without bot username
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("write", write))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("stop", stop))
    
    # Add message handler for setup process and mentions
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("✅ Bot is running and polling for updates...")
    
    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
# Add to main.py temporarily for debugging
async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Debug command to check if bot is receiving messages"""
    info = f"""
📊 Debug Info:
Chat ID: {update.effective_chat.id}
Chat Type: {update.effective_chat.type}
User ID: {update.effective_user.id if update.effective_user else 'N/A'}
Message: {update.message.text if update.message else 'N/A'}
    """
    await update.message.reply_text(info)
    logger.info(f"Debug command received: {info}")

# Add to handlers
application.add_handler(CommandHandler("debug", debug))
