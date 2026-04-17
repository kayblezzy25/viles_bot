import os
import asyncio
import logging
from datetime import datetime, timedelta
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
        # Store active channels and their posting schedules
        self.active_channels: Dict[int, Dict] = {}
        
    def add_channel(self, chat_id: int, topic: str, content_plan: str):
        """Add a channel to the posting schedule"""
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
        """Remove a channel from the posting schedule"""
        if chat_id in self.active_channels:
            del self.active_channels[chat_id]
            logger.info(f"Channel {chat_id} removed from schedule")
    
    def can_post(self, chat_id: int) -> bool:
        """Check if a post can be made in the channel"""
        if chat_id not in self.active_channels:
            return False
            
        channel_data = self.active_channels[chat_id]
        
        # Check daily limit (10 posts per day)
        if channel_data['daily_count'] >= 10:
            return False
            
        # Check total limit (50 posts in 5 days)
        if channel_data['total_posts'] >= 50:
            return False
            
        # Check if we need to reset daily count
        if channel_data['last_post_time']:
            days_passed = (datetime.now() - channel_data['start_time']).days
            if days_passed >= channel_data['current_day']:
                channel_data['current_day'] = days_passed + 1
                channel_data['daily_count'] = 0
                logger.info(f"Reset daily count for channel {chat_id} to day {channel_data['current_day']}")
                
        return True
    
    def record_post(self, chat_id: int):
        """Record that a post was made"""
        if chat_id in self.active_channels:
            self.active_channels[chat_id]['last_post_time'] = datetime.now()
            self.active_channels[chat_id]['daily_count'] += 1
            self.active_channels[chat_id]['total_posts'] += 1
            
            logger.info(f"Post recorded for channel {chat_id}. Daily: {self.active_channels[chat_id]['daily_count']}/10, Total: {self.active_channels[chat_id]['total_posts']}/50")
    
    def get_status(self, chat_id: int) -> Dict:
        """Get status for a channel"""
        if chat_id in self.active_channels:
            return self.active_channels[chat_id]
        return None

# Initialize scheduler
scheduler = ChannelPostScheduler()

async def generate_post_content(topic: str, content_plan: str, post_number: int) -> str:
    """Generate post content using OpenAI"""
    if not openai_client:
        return f"📝 Post #{post_number}\n\nTopic: {topic}\n\n{content_plan}\n\n(OpenAI API key not configured - using template content)"
    
    try:
        prompt = f"""Create an engaging Telegram channel post about: {topic}
        
Content guidelines: {content_plan}

Post #{post_number} in a series of 50 posts.
Make it informative, engaging, and suitable for a Telegram channel.
Keep it between 200-400 words.
Include relevant emojis where appropriate."""
        
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
        return f"📝 Post #{post_number}\n\nTopic: {topic}\n\n{content_plan}\n\n(Error generating AI content - using template)"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_message = (
        "🤖 *Channel Content Bot*\n\n"
        "I can help you automate content posting in your channels!\n\n"
        "📝 *Commands:*\n"
        "/write - Start the content setup process\n"
        "/status - Check current posting status\n"
        "/stop - Stop posting in this channel\n\n"
        "To use me, add me as an admin to your channel and use /write to set up content."
    )
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def write(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /write command - Start content setup"""
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    
    logger.info(f"Write command received in chat {chat_id} of type {chat_type}")
    
    # Store chat_id in user_data for the setup process
    context.user_data['setup_stage'] = 'topic'
    context.user_data['channel_id'] = chat_id
    
    await update.message.reply_text(
        "📝 *Content Setup*\n\n"
        "I'll ask you a few questions to set up content for this channel.\n\n"
        "First question: *What is the main topic/theme of this channel?*",
        parse_mode='Markdown'
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check posting status for the channel"""
    chat_id = update.effective_chat.id
    
    channel_data = scheduler.get_status(chat_id)
    
    if channel_data:
        status_message = (
            f"📊 *Posting Status*\n\n"
            f"*Topic:* {channel_data['topic']}\n"
            f"*Daily Posts:* {channel_data['daily_count']}/10\n"
            f"*Total Posts:* {channel_data['total_posts']}/50\n"
            f"*Current Day:* {channel_data['current_day']}/5\n"
            f"*Started:* {channel_data['start_time'].strftime('%Y-%m-%d %H:%M')}\n\n"
        )
        
        if scheduler.can_post(chat_id):
            status_message += "✅ Ready for next post"
        else:
            if channel_data['daily_count'] >= 10:
                status_message += "⏸ Daily limit reached"
            elif channel_data['total_posts'] >= 50:
                status_message += "✅ Completed all 50 posts"
                
        await update.message.reply_text(status_message, parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "No active posting schedule for this channel. Use /write to set one up."
        )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop posting in the channel"""
    chat_id = update.effective_chat.id
    
    if scheduler.get_status(chat_id):
        scheduler.remove_channel(chat_id)
        await update.message.reply_text("🛑 Posting schedule stopped for this channel.")
    else:
        await update.message.reply_text("No active posting schedule to stop.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-command messages during setup"""
    if 'setup_stage' not in context.user_data:
        return
        
    stage = context.user_data['setup_stage']
    message_text = update.message.text
    chat_id = context.user_data.get('channel_id')
    
    logger.info(f"Setup stage: {stage}, Chat ID: {chat_id}")
    
    if stage == 'topic':
        context.user_data['topic'] = message_text
        context.user_data['setup_stage'] = 'content_plan'
        await update.message.reply_text(
            "Great! Now, *what type of content should I create?*\n\n"
            "Examples:\n"
            "• Educational posts with tips and tricks\n"
            "• News updates and analysis\n"
            "• Inspirational quotes and motivation\n"
            "• Product reviews and recommendations\n\n"
            "Describe your content plan:",
            parse_mode='Markdown'
        )
    
    elif stage == 'content_plan':
        topic = context.user_data['topic']
        content_plan = message_text
        
        # Add channel to scheduler
        scheduler.add_channel(chat_id, topic, content_plan)
        
        await update.message.reply_text(
            f"✅ *Content Schedule Created!*\n\n"
            f"*Topic:* {topic}\n"
            f"*Content Plan:* {content_plan}\n\n"
            f"📅 *Schedule:*\n"
            f"• 10 posts per day\n"
            f"• Every 20 minutes\n"
            f"• Total 50 posts over 5 days\n\n"
            f"The first post will be sent in 1 minute!",
            parse_mode='Markdown'
        )
        
        # Clear setup data
        context.user_data.clear()
        
        # Start posting loop for this channel
        asyncio.create_task(posting_loop(chat_id, context))

async def posting_loop(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Main posting loop for a channel"""
    bot = context.bot
    
    # Wait 1 minute before first post
    await asyncio.sleep(60)
    
    while True:
        channel_data = scheduler.get_status(chat_id)
        if not channel_data:
            logger.info(f"Channel {chat_id} no longer in scheduler, stopping posting loop")
            break
            
        if scheduler.can_post(chat_id):
            post_number = channel_data['total_posts'] + 1
            
            try:
                # Generate content
                content = await generate_post_content(
                    channel_data['topic'],
                    channel_data['content_plan'],
                    post_number
                )
                
                # Send to channel
                await bot.send_message(
                    chat_id=chat_id,
                    text=content,
                    disable_web_page_preview=True
                )
                
                # Record the post
                scheduler.record_post(chat_id)
                logger.info(f"Posted content #{post_number} to channel {chat_id}")
                
                # Check if completed
                updated_data = scheduler.get_status(chat_id)
                if updated_data and updated_data['total_posts'] >= 50:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="🎉 *Completed!*\n\nAll 50 posts have been sent over the past 5 days. Thank you for using Channel Content Bot!",
                        parse_mode='Markdown'
                    )
                    scheduler.remove_channel(chat_id)
                    break
                    
            except Exception as e:
                logger.error(f"Error in posting loop for channel {chat_id}: {e}")
        
        # Wait 20 minutes before next check
        await asyncio.sleep(1200)  # 20 minutes in seconds

def main():
    """Start the bot"""
    # Get bot token from environment
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is not set")
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")
    
    logger.info("Starting bot...")
    
    # Create application
    application = Application.builder().token(token).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("write", write))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("stop", stop))
    
    # Add message handler for setup process
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the bot
    logger.info("Bot started successfully! Polling for updates...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
