import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    oauth_token = relationship("OAuthToken", uselist=False, back_populates="user")
    form_sessions = relationship("FormSession", back_populates="user")

class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    refresh_token = Column(String, nullable=False) # Essentail for longterm api access
    access_token = Column(String, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="oauth_token")

class FormSession(Base):
    __tablename__ = "form_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))

    # The crucial link to langgraph's internal state tracking
    thread_id = Column(String, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    # Populated only after the final graph node executes
    google_form_id = Column(String, nullable=True) 
    is_published = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))    

    user = relationship("User", back_populates="form_sessions")





