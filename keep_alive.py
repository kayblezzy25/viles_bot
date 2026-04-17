"""
Keep-alive mechanism for Render.com free tier.
Prevents the bot from sleeping by making periodic requests.
Note: For reliable 24/7 operation, consider upgrading to paid tier.
"""

import asyncio
import logging
from aiohttp import web
from datetime import datetime

logger = logging.getLogger(__name__)


async def health_check(request):
    """Simple health check endpoint."""
    return web.Response(
        text=f"Bot is running! Time: {datetime.utcnow().isoformat()}",
        status=200
    )


async def start_keep_alive_server(port=10000):
    """Start a simple HTTP server for health checks."""
    app = web.Application()
    app.router.add_get("/health", health_check)
    app.router.add_get("/", health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    logger.info(f"Keep-alive server started on port {port}")
    return runner


class SelfHealingScheduler:
    """
    Self-healing job scheduler that recovers jobs after restarts.
    Works with the database to restore scheduled tasks.
    """
    
    def __init__(self, application):
        self.application = application
        self.job_queue = application.job_queue
    
    async def restore_jobs(self):
        """Restore scheduled jobs from database after restart."""
        from database import ChannelManager
        
        logger.info("Restoring scheduled jobs from database...")
        
        channels = ChannelManager.get_active_channels()
        restored_count = 0
        
        for channel in channels:
            if channel.posts_remaining > 0:
                # Remove any existing jobs for this channel
                existing_jobs = self.job_queue.get_jobs_by_name(f"channel_{channel.chat_id}")
                for job in existing_jobs:
                    job.schedule_removal()
                
                # Calculate time until next post
                from datetime import datetime, timedelta
                from bot import post_callback
                
                now = datetime.utcnow()
                
                if channel.next_post_at and channel.next_post_at > now:
                    # Schedule at the originally planned time
                    first_run = channel.next_post_at - now
                else:
                    # If missed, start in 1 minute
                    first_run = timedelta(minutes=1)
                
                # Schedule the job
                self.job_queue.run_repeating(
                    callback=post_callback,
                    interval=timedelta(minutes=20),
                    first=first_run,
                    chat_id=channel.chat_id,
                    name=f"channel_{channel.chat_id}",
                    data={
                        "prompt": channel.prompt_text,
                        "chat_id": channel.chat_id
                    }
                )
                
                restored_count += 1
                logger.info(f"Restored job for channel {channel.chat_id}")
        
        logger.info(f"Restored {restored_count} scheduled jobs")
        return restored_count
    
    async def daily_reset_job(self, context):
        """Reset daily post counters at midnight UTC."""
        from database import ChannelManager
        
        logger.info("Running daily counter reset...")
        
        channels = ChannelManager.get_active_channels()
        for channel in channels:
            ChannelManager.reset_daily_counter(channel.chat_id)
        
        logger.info(f"Reset daily counters for {len(channels)} channels")
    
    def schedule_daily_reset(self):
        """Schedule the daily reset job to run at midnight UTC."""
        from datetime import time
        
        self.job_queue.run_daily(
            callback=self.daily_reset_job,
            time=time(hour=0, minute=0),
            name="daily_reset"
        )
        
        logger.info("Scheduled daily counter reset at midnight UTC")


async def setup_self_healing(application):
    """Setup self-healing scheduler for the application."""
    scheduler = SelfHealingScheduler(application)
    
    # Restore jobs from database
    await scheduler.restore_jobs()
    
    # Schedule daily reset
    scheduler.schedule_daily_reset()
    
    return scheduler
