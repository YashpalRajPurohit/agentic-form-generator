import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.database.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    oauth_token = relationship("OAuthToken", uselist=False, back_populates="user", cascade="all, delete-orphan")
    threads = relationship("Thread", back_populates="user", cascade="all, delete-orphan")


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    # Added ondelete="CASCADE" to automatically clean up tokens if a user is deleted
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    refresh_token = Column(String, nullable=False) # Essential for longterm api access
    access_token = Column(String, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="oauth_token")


class Thread(Base):
    __tablename__ = "threads"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))

    # The crucial link to LangGraph's internal state tracking
    thread_id = Column(String, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    
    # UI Metadata for the frontend sidebar
    title = Column(String, default="New Form Generation")

    # Populated only after the final graph node executes
    google_form_id = Column(String, nullable=True) 
    is_published = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))    
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="threads")
    messages = relationship("Message", back_populates="thread", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    thread_id = Column(String, ForeignKey("threads.id", ondelete="CASCADE"), nullable=False)
    
    # Identifies who sent the message (e.g., "user", "ai", "system")
    role = Column(String, nullable=False)
    
    # The actual text content of the message
    content = Column(Text, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationship back to the parent thread
    thread = relationship("Thread", back_populates="messages")