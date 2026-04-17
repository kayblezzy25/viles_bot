import os
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio

app = Flask(__name__)

# Your bot token
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = Bot(token=TOKEN)

# Get the webhook URL from environment
WEBHOOK_URL = os.getenv('RENDER_EXTERNAL_URL', 'https://your-app.onrender.com')

# Initialize bot application
application = Application.builder().token(TOKEN).build()

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming updates from Telegram"""
    if request.method == 'POST':
        update = Update.de_json(request.get_json(force=True), bot)
        asyncio.run(application.process_update(update))
        return 'OK', 200
    return 'Method not allowed', 405

@app.route('/')
def index():
    return 'Bot is running!'

async def setup_webhook():
    """Set webhook URL"""
    webhook_url = f"{WEBHOOK_URL}/webhook"
    await bot.set_webhook(webhook_url)
    print(f"Webhook set to: {webhook_url}")

if __name__ == '__main__':
    # Set webhook on startup
    asyncio.run(setup_webhook())
    # Start Flask server
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
