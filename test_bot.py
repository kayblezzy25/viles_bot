"""
Test script for the Telegram AI Content Bot.
Run this to verify your setup before deployment.
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Test 1: Environment Variables
def test_env_vars():
    """Test that required environment variables are set."""
    print("\n" + "="*50)
    print("TEST 1: Environment Variables")
    print("="*50)
    
    required = ["BOT_TOKEN", "OPENAI_API_KEY"]
    optional = ["WEBHOOK_URL", "DATABASE_URL", "PORT"]
    
    all_good = True
    
    for var in required:
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            masked = value[:10] + "..." + value[-4:] if len(value) > 20 else "***"
            print(f"✅ {var}: {masked}")
        else:
            print(f"❌ {var}: NOT SET (Required)")
            all_good = False
    
    for var in optional:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {value}")
        else:
            print(f"⚠️  {var}: Not set (Optional)")
    
    return all_good


# Test 2: Database Connection
def test_database():
    """Test database connection and initialization."""
    print("\n" + "="*50)
    print("TEST 2: Database Connection")
    print("="*50)
    
    try:
        from database import init_db, ChannelManager, get_db
        
        print("Initializing database...")
        init_db()
        print("✅ Database initialized successfully")
        
        # Test write
        test_channel = ChannelManager.create_or_update_channel(
            chat_id=-1001234567890,
            prompt_text="Test topic for verification",
            posts_total=50
        )
        print(f"✅ Test channel created: {test_channel.chat_id}")
        
        # Test read
        channel = ChannelManager.get_channel(-1001234567890)
        if channel:
            print(f"✅ Test channel retrieved: {channel.prompt_text}")
        
        # Test delete
        ChannelManager.delete_channel(-1001234567890)
        print("✅ Test channel deleted")
        
        return True
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False


# Test 3: OpenAI API
def test_openai():
    """Test OpenAI API connection."""
    print("\n" + "="*50)
    print("TEST 3: OpenAI API")
    print("="*50)
    
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        print("Testing API connection...")
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Say 'OpenAI API is working!'"}],
            max_tokens=20
        )
        
        result = response.choices[0].message.content
        print(f"✅ OpenAI API response: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ OpenAI API error: {e}")
        return False


# Test 4: Telegram Bot Token
def test_telegram():
    """Test Telegram bot token validity."""
    print("\n" + "="*50)
    print("TEST 4: Telegram Bot Token")
    print("="*50)
    
    try:
        import requests
        
        token = os.getenv("BOT_TOKEN")
        url = f"https://api.telegram.org/bot{token}/getMe"
        
        print("Testing bot token...")
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if data.get("ok"):
            bot_info = data["result"]
            print(f"✅ Bot token valid!")
            print(f"   Bot Name: {bot_info.get('first_name')}")
            print(f"   Username: @{bot_info.get('username')}")
            print(f"   Bot ID: {bot_info.get('id')}")
            return True
        else:
            print(f"❌ Invalid bot token: {data.get('description')}")
            return False
            
    except Exception as e:
        print(f"❌ Telegram API error: {e}")
        return False


# Test 5: Content Generation
async def test_content_generation():
    """Test content generation."""
    print("\n" + "="*50)
    print("TEST 5: Content Generation")
    print("="*50)
    
    try:
        from openai_client import ContentGenerator
        
        print("Generating test post...")
        content = await ContentGenerator.generate_post(
            topic="Productivity tips for remote workers",
            post_number=1,
            total_posts=50
        )
        
        if content:
            print(f"✅ Content generated successfully!")
            print(f"   Length: {len(content)} characters")
            print(f"   Preview: {content[:100]}...")
            return True
        else:
            print("❌ Content generation returned None")
            return False
            
    except Exception as e:
        print(f"❌ Content generation error: {e}")
        return False


# Main test runner
async def run_all_tests():
    """Run all tests."""
    print("\n" + "="*50)
    print("TELEGRAM AI BOT - SETUP VERIFICATION")
    print("="*50)
    
    results = []
    
    # Run tests
    results.append(("Environment Variables", test_env_vars()))
    results.append(("Database", test_database()))
    results.append(("OpenAI API", test_openai()))
    results.append(("Telegram Bot", test_telegram()))
    results.append(("Content Generation", await test_content_generation()))
    
    # Summary
    print("\n" + "="*50)
    print("TEST SUMMARY")
    print("="*50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Your bot is ready for deployment.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please fix the issues before deploying.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
