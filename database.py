"""
Database models and operations for the Telegram Multi-Channel AI Bot.
Handles channel state persistence, post tracking, and scheduling metadata.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine, Column, BigInteger, Integer, String, Text, DateTime, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot.db")

# Handle Render.com PostgreSQL URL format
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

Base = declarative_base()

# Create engine with appropriate settings for the database type
if DATABASE_URL and DATABASE_URL.startswith("postgresql"):
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=300
    )
else:
    # SQLite settings
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(bind=engine)


class Channel(Base):
    """Channel state and configuration storage."""
    __tablename__ = "channels"
    
    chat_id = Column(BigInteger, primary_key=True)
    prompt_text = Column(Text, nullable=False)
    posts_total = Column(Integer, default=50)
    posts_remaining = Column(Integer, nullable=False)
    posts_today = Column(Integer, default=0)
    status = Column(String(20), default="active")  # active, paused, completed, failed
    timezone = Column(String(50), default="UTC")
    start_time = Column(DateTime, default=func.now())
    next_post_at = Column(DateTime, nullable=True)
    last_post_at = Column(DateTime, nullable=True)
    job_metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "prompt_text": self.prompt_text,
            "posts_total": self.posts_total,
            "posts_remaining": self.posts_remaining,
            "posts_today": self.posts_today,
            "status": self.status,
            "timezone": self.timezone,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "next_post_at": self.next_post_at.isoformat() if self.next_post_at else None,
            "last_post_at": self.last_post_at.isoformat() if self.last_post_at else None,
        }


class Post(Base):
    """Individual post tracking for idempotency and audit."""
    __tablename__ = "posts"
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, nullable=False, index=True)
    post_number = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    scheduled_at = Column(DateTime, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="pending")  # pending, sent, failed
    telegram_message_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=func.now())


# Initialize database tables
def init_db():
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


# Channel operations
class ChannelManager:
    """Manages channel CRUD operations and state transitions."""
    
    @staticmethod
    def create_or_update_channel(
        chat_id: int,
        prompt_text: str,
        posts_total: int = 50,
        timezone: str = "UTC"
    ) -> Channel:
        """Create or reactivate a channel with new campaign settings."""
        db = get_db()
        try:
            channel = db.query(Channel).filter_by(chat_id=chat_id).first()
            
            now = datetime.utcnow()
            next_post = now + timedelta(minutes=20)
            
            if channel:
                # Update existing channel (new campaign)
                channel.prompt_text = prompt_text
                channel.posts_total = posts_total
                channel.posts_remaining = posts_total
                channel.posts_today = 0
                channel.status = "active"
                channel.timezone = timezone
                channel.start_time = now
                channel.next_post_at = next_post
                channel.last_post_at = None
            else:
                # Create new channel
                channel = Channel(
                    chat_id=chat_id,
                    prompt_text=prompt_text,
                    posts_total=posts_total,
                    posts_remaining=posts_total,
                    posts_today=0,
                    status="active",
                    timezone=timezone,
                    start_time=now,
                    next_post_at=next_post,
                )
                db.add(channel)
            
            db.commit()
            db.refresh(channel)
            return channel
        finally:
            db.close()
    
    @staticmethod
    def get_channel(chat_id: int) -> Optional[Channel]:
        """Get channel by chat_id."""
        db = get_db()
        try:
            return db.query(Channel).filter_by(chat_id=chat_id).first()
        finally:
            db.close()
    
    @staticmethod
    def get_active_channels() -> List[Channel]:
        """Get all active channels with posts remaining."""
        db = get_db()
        try:
            return db.query(Channel).filter(
                Channel.status == "active",
                Channel.posts_remaining > 0
            ).all()
        finally:
            db.close()
    
    @staticmethod
    def decrement_post_counter(chat_id: int) -> Optional[Channel]:
        """Decrement remaining posts counter after successful post."""
        db = get_db()
        try:
            channel = db.query(Channel).filter_by(chat_id=chat_id).first()
            if channel and channel.posts_remaining > 0:
                channel.posts_remaining -= 1
                channel.posts_today += 1
                channel.last_post_at = datetime.utcnow()
                
                # Schedule next post (20 minutes later)
                if channel.posts_remaining > 0:
                    channel.next_post_at = datetime.utcnow() + timedelta(minutes=20)
                else:
                    channel.status = "completed"
                    channel.next_post_at = None
                
                db.commit()
                db.refresh(channel)
            return channel
        finally:
            db.close()
    
    @staticmethod
    def reset_daily_counter(chat_id: int) -> Optional[Channel]:
        """Reset daily post counter (called at midnight)."""
        db = get_db()
        try:
            channel = db.query(Channel).filter_by(chat_id=chat_id).first()
            if channel:
                channel.posts_today = 0
                db.commit()
                db.refresh(channel)
            return channel
        finally:
            db.close()
    
    @staticmethod
    def update_status(chat_id: int, status: str) -> Optional[Channel]:
        """Update channel status."""
        db = get_db()
        try:
            channel = db.query(Channel).filter_by(chat_id=chat_id).first()
            if channel:
                channel.status = status
                db.commit()
                db.refresh(channel)
            return channel
        finally:
            db.close()
    
    @staticmethod
    def pause_channel(chat_id: int) -> Optional[Channel]:
        """Pause channel posting."""
        return ChannelManager.update_status(chat_id, "paused")
    
    @staticmethod
    def resume_channel(chat_id: int) -> Optional[Channel]:
        """Resume channel posting."""
        channel = ChannelManager.get_channel(chat_id)
        if channel and channel.posts_remaining > 0:
            return ChannelManager.update_status(chat_id, "active")
        return channel
    
    @staticmethod
    def delete_channel(chat_id: int) -> bool:
        """Delete channel and all its posts."""
        db = get_db()
        try:
            # Delete posts first
            db.query(Post).filter_by(chat_id=chat_id).delete()
            # Delete channel
            result = db.query(Channel).filter_by(chat_id=chat_id).delete()
            db.commit()
            return result > 0
        finally:
            db.close()
    
    @staticmethod
    def get_all_channels() -> List[Channel]:
        """Get all channels for admin overview."""
        db = get_db()
        try:
            return db.query(Channel).all()
        finally:
            db.close()


# Post operations
class PostManager:
    """Manages post tracking and audit."""
    
    @staticmethod
    def create_post(chat_id: int, post_number: int, content: str, scheduled_at: datetime) -> Post:
        """Record a scheduled post."""
        db = get_db()
        try:
            post = Post(
                chat_id=chat_id,
                post_number=post_number,
                content=content,
                scheduled_at=scheduled_at,
                status="pending"
            )
            db.add(post)
            db.commit()
            db.refresh(post)
            return post
        finally:
            db.close()
    
    @staticmethod
    def mark_post_sent(post_id: int, telegram_message_id: int) -> Optional[Post]:
        """Mark post as successfully sent."""
        db = get_db()
        try:
            post = db.query(Post).filter_by(id=post_id).first()
            if post:
                post.status = "sent"
                post.sent_at = datetime.utcnow()
                post.telegram_message_id = telegram_message_id
                db.commit()
                db.refresh(post)
            return post
        finally:
            db.close()
    
    @staticmethod
    def mark_post_failed(post_id: int) -> Optional[Post]:
        """Mark post as failed."""
        db = get_db()
        try:
            post = db.query(Post).filter_by(id=post_id).first()
            if post:
                post.status = "failed"
                db.commit()
                db.refresh(post)
            return post
        finally:
            db.close()
    
    @staticmethod
    def get_channel_posts(chat_id: int) -> List[Post]:
        """Get all posts for a channel."""
        db = get_db()
        try:
            return db.query(Post).filter_by(chat_id=chat_id).order_by(Post.post_number).all()
        finally:
            db.close()
    
    @staticmethod
    def get_pending_posts(chat_id: int) -> List[Post]:
        """Get pending posts for a channel."""
        db = get_db()
        try:
            return db.query(Post).filter_by(chat_id=chat_id, status="pending").all()
        finally:
            db.close()


# Initialize database on module load (with error handling)
try:
    init_db()
except Exception as e:
    print(f"Warning: Database initialization error: {e}")
    # Don't crash on import - let the application handle it
