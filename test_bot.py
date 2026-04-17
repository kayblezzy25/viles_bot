import os
import asyncio
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

async def test_bot():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not found in environment")
        return
    
    print(f"Testing bot with token: {token[:10]}...")
    
    try:
        bot = Bot(token=token)
        me = await bot.get_me()
        print(f"✅ Bot is working! Bot name: {me.first_name} (@{me.username})")
    except Exception as e:
        print(f"❌ Bot test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_bot())
