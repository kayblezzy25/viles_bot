import os
import asyncio
import logging
from datetime import datetime
from typing import Dict
from dotenv import load_dotenv
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from openai import OpenAI
import sys

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_api_key = os.getenv('OPENAI_API_KEY')
if openai_api_key:
    openai_client = OpenAI(api_key=openai_api_key)
    logger.info("✅ OpenAI client initialized")
else:
    logger.warning("⚠️ OPENAI_API_KEY not found - using template content")
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
        logger.info(f"✅ Channel {chat_id} added to schedule")
    
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
    
    def get_status(self, chat_id: int) -> Dict:
        if chat_id in self.active_channels:
            return self.active_channels[chat_id]
        return None

scheduler = ChannelPostScheduler()

async def generate_post_content(topic: str, content_plan: str, post_number: int) -> str:
    if not openai_client:
        return f"📝 Post #{post_number}\n\n📌 Topic: {topic}\n\n💡 {content_plan}"
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a professional content creator for Telegram channels."},
                {"role": "user", "content": f"Create post #{post_number} about {topic}. Guidelines: {content_plan}"}
            ],
            max_tokens=500,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return f"📝 Post #{post_number}\n\n📌 Topic: {topic}\n\n💡 {content_plan}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    logger.info(f"📨 /start from chat_id: {update.effective_chat.id}")
    
    await update.message.reply_text(
        "🤖 **Bot is Active!**\n\n"
        "✅ I'm working properly!\n\n"
        "**Commands:**\n"
        "/start - This message\n"
        "/write - Setup auto-posting\n"
        "/status - Check progress\n"
        "/stop - Stop posting\n\n"
        "Add me as admin to a channel and use /write to begin!",
        parse_mode='Markdown'
    )

async def write(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /write command"""
    chat_id = update.effective_chat.id
    logger.info(f"📨 /write from chat_id: {chat_id}")
    
    context.user_data['setup_stage'] = 'awaiting_topic'
    context.user_data['channel_id'] = chat_id
    
    await update.message.reply_text(
        "📝 **Setup Started**\n\n"
        "What is the main **topic/theme** of this channel?",
        parse_mode='Markdown'
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check posting status"""
    chat_id = update.effective_chat.id
    channel_data = scheduler.get_status(chat_id)
    
    if channel_data:
        status_text = (
            f"📊 **Status**\n"
            f"Topic: {channel_data['topic']}\n"
            f"Daily: {channel_data['daily_count']}/10\n"
            f"Total: {channel_data['total_posts']}/50\n"
            f"Day: {channel_data['current_day']}/5"
        )
    else:
        status_text = "❌ No active schedule. Use /write to start."
    
    await update.message.reply_text(status_text, parse_mode='Markdown')

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop posting"""
    chat_id = update.effective_chat.id
    
    if scheduler.get_status(chat_id):
        scheduler.remove_channel(chat_id)
        await update.message.reply_text("🛑 Posting stopped.")
    else:
        await update.message.reply_text("No active schedule.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages during setup"""
    if 'setup_stage' not in context.user_data:
        return
        
    stage = context.user_data['setup_stage']
    message_text = update.message.text
    chat_id = context.user_data.get('channel_id')
    
    if stage == 'awaiting_topic':
        context.user_data['topic'] = message_text
        context.user_data['setup_stage'] = 'awaiting_plan'
        await update.message.reply_text(
            "✅ Topic saved!\n\n"
            "What type of content should I create?\n"
            "(e.g., 'Daily tips and tutorials')",
            parse_mode='Markdown'
        )
    
    elif stage == 'awaiting_plan':
        topic = context.user_data['topic']
        content_plan = message_text
        
        scheduler.add_channel(chat_id, topic, content_plan)
        
        await update.message.reply_text(
            f"🎉 **Schedule Created!**\n\n"
            f"Topic: {topic}\n"
            f"Plan: {content_plan}\n\n"
            f"First post in 1 minute!",
            parse_mode='Markdown'
        )
        
        context.user_data.clear()
        asyncio.create_task(posting_loop(chat_id, context))

async def posting_loop(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Main posting loop"""
    await asyncio.sleep(60)
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
                
                await bot.send_message(chat_id=chat_id, text=content)
                scheduler.record_post(chat_id)
                logger.info(f"✅ Posted #{post_number} to {chat_id}")
                
                updated_data = scheduler.get_status(chat_id)
                if updated_data and updated_data['total_posts'] >= 50:
                    await bot.send_message(chat_id=chat_id, text="🎉 All 50 posts completed!")
                    scheduler.remove_channel(chat_id)
                    break
                    
            except Exception as e:
                logger.error(f"Post error: {e}")
        
        await asyncio.sleep(1200)

def main():
    """Start the bot"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN not set!")
        sys.exit(1)
    
    logger.info(f"🤖 Starting bot...")
    
    # Create application with increased timeout for Render
    application = (
        Application.builder()
        .token(token)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("write", write))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("✅ Bot configured, starting polling...")
    
    # Start polling with error handling
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        poll_interval=1.0,
        timeout=30
    )

if __name__ == '__main__':
    main()
