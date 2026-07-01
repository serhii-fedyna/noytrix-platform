# auth/models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, UniqueConstraint
from datetime import datetime, timedelta
from db import Base

def in_minutes(mins=15):
    return datetime.utcnow() + timedelta(minutes=mins)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    nick = Column(String, nullable=True)
    name = Column(String, nullable=True)
    password_hash = Column(String, nullable=True)
    provider = Column(String, nullable=True)   # 'local' | 'google'
    email_verified = Column(Boolean, default=False)
    avatar = Column(String, nullable=True)
    role = Column(String, default="Трейдер")
    plan = Column(String, default="Free")
    created_at = Column(DateTime, default=datetime.utcnow)

class EmailCode(Base):
    __tablename__ = "email_codes"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    code_hash = Column(String, nullable=False)
    purpose = Column(String, nullable=False)   # 'register' | 'reset'
    expires_at = Column(DateTime, nullable=False)
    __table_args__ = (UniqueConstraint('email', 'purpose', name='uniq_email_purpose'),)

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
