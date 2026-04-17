"""
OpenAI integration for content generation.
Generates engaging Telegram channel posts based on user prompts.
"""

import os
import random
from typing import Optional
from openai import AsyncOpenAI

# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Model configuration
DEFAULT_MODEL = "gpt-3.5-turbo"
MAX_TOKENS = 1000
TEMPERATURE = 0.8


class ContentGenerator:
    """Generates Telegram channel content using OpenAI."""
    
    # Post type variations to keep content diverse
    POST_TYPES = [
        "educational_insight",
        "quick_tip",
        "thought_provoking_question",
        "practical_example",
        "key_takeaway",
        "myth_busting",
        "step_by_step_guide",
        "industry_news_angle",
        "common_mistake_warning",
        "success_story_framework"
    ]
    
    @staticmethod
    def _build_system_prompt() -> str:
        """Build the system prompt for content generation."""
        return """You are an expert content creator for Telegram channels. 
Your task is to create engaging, informative, and valuable posts that keep readers interested.

Guidelines:
- Write in a conversational, engaging tone
- Use relevant emojis naturally (2-4 per post)
- Keep posts between 100-800 characters for optimal readability
- Include a hook at the beginning to grab attention
- End with a question or call-to-action when appropriate
- Format for Telegram (use line breaks for readability)
- Avoid markdown that Telegram doesn't support well
- Be authentic and provide genuine value
- Never use hashtags (Telegram channels don't need them)
"""
    
    @staticmethod
    def _build_user_prompt(
        topic: str,
        post_number: int,
        total_posts: int,
        post_type: str
    ) -> str:
        """Build the user prompt with context."""
        
        post_type_instructions = {
            "educational_insight": "Share a valuable insight or little-known fact about the topic.",
            "quick_tip": "Provide a quick, actionable tip that readers can implement immediately.",
            "thought_provoking_question": "Pose an interesting question that makes readers think deeply about the topic.",
            "practical_example": "Give a concrete real-world example that illustrates the topic.",
            "key_takeaway": "Distill an important concept into a clear, memorable takeaway.",
            "myth_busting": "Debunk a common misconception related to the topic.",
            "step_by_step_guide": "Break down a process into simple, actionable steps.",
            "industry_news_angle": "Discuss a current trend or development in the field.",
            "common_mistake_warning": "Highlight a frequent mistake and how to avoid it.",
            "success_story_framework": "Share a framework or principle that leads to success."
        }
        
        instruction = post_type_instructions.get(
            post_type, 
            "Create engaging content about the topic."
        )
        
        return f"""Topic: {topic}

This is post {post_number} of {total_posts} in a 5-day content series.

Today's content type: {post_type.replace('_', ' ').title()}
Instruction: {instruction}

Create an engaging Telegram post that:
1. Maintains thematic consistency with the overall topic
2. Provides fresh, unique content (different from previous posts)
3. Is formatted beautifully for Telegram
4. Includes relevant emojis naturally
5. Engages the reader

Write only the post content, nothing else."""
    
    @staticmethod
    async def generate_post(
        topic: str,
        post_number: int,
        total_posts: int = 50,
        model: str = DEFAULT_MODEL
    ) -> Optional[str]:
        """
        Generate a single post for a channel.
        
        Args:
            topic: The user's topic/prompt from /write command
            post_number: Current post number (1-50)
            total_posts: Total posts in campaign (default 50)
            model: OpenAI model to use
            
        Returns:
            Generated post content or None if generation failed
        """
        try:
            # Select a post type based on post number to ensure variety
            # Cycle through post types to maintain diversity
            post_type_index = (post_number - 1) % len(ContentGenerator.POST_TYPES)
            post_type = ContentGenerator.POST_TYPES[post_type_index]
            
            # Add some randomness for variety
            if random.random() < 0.3:
                post_type = random.choice(ContentGenerator.POST_TYPES)
            
            system_prompt = ContentGenerator._build_system_prompt()
            user_prompt = ContentGenerator._build_user_prompt(
                topic=topic,
                post_number=post_number,
                total_posts=total_posts,
                post_type=post_type
            )
            
            response = await openai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
            )
            
            content = response.choices[0].message.content.strip()
            
            # Post-processing for Telegram compatibility
            content = ContentGenerator._format_for_telegram(content)
            
            return content
            
        except Exception as e:
            print(f"Error generating post: {e}")
            return None
    
    @staticmethod
    def _format_for_telegram(content: str) -> str:
        """Format content for optimal Telegram display."""
        # Remove excessive line breaks
        while "\n\n\n" in content:
            content = content.replace("\n\n\n", "\n\n")
        
        # Ensure content isn't too long (Telegram limit is 4096)
        if len(content) > 4000:
            content = content[:3997] + "..."
        
        # Clean up any problematic characters
        content = content.replace("\r", "")
        
        return content.strip()
    
    @staticmethod
    async def generate_welcome_message(channel_name: str, topic: str) -> str:
        """Generate a welcome message when campaign starts."""
        return f"""🚀 <b>Content Campaign Started!</b>

Channel: {channel_name}
Topic: {topic}
Schedule: Every 20 minutes
Total Posts: 50 posts over 5 days

First post coming up shortly..."""
    
    @staticmethod
    async def generate_completion_message(channel_name: str, total_posts: int) -> str:
        """Generate a completion message when campaign ends."""
        return f"""✅ <b>Campaign Complete!</b>

Channel: {channel_name}
Total Posts: {total_posts}

All scheduled posts have been delivered. 
Use /write [new topic] to start a new campaign."""


# Fallback content templates for when OpenAI fails
FALLBACK_TEMPLATES = [
    "💡 Here's something interesting about {topic}: The key to mastery is consistent practice. What small step will you take today?",
    "🎯 Did you know? Understanding {topic} deeply can transform how you approach challenges. What's your biggest insight?",
    "🔥 Quick tip about {topic}: Focus on fundamentals first. Advanced techniques build on solid basics. Agree?",
    "💭 Thinking about {topic} today... The best learners stay curious and ask great questions. What questions do you have?",
    "✨ {topic} wisdom: Progress beats perfection. Every expert was once a beginner. Keep going!",
]


def get_fallback_content(topic: str) -> str:
    """Get fallback content when OpenAI generation fails."""
    import random
    template = random.choice(FALLBACK_TEMPLATES)
    return template.format(topic=topic)
