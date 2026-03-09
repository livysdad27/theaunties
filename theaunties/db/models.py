"""SQLAlchemy models for theAunties."""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    user_intent = Column(Text, nullable=False)
    schedule = Column(String(50), nullable=False, default="0 6 * * *")
    status = Column(String(50), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    sources = relationship("Source", back_populates="topic", cascade="all, delete-orphan")
    runs = relationship("Run", back_populates="topic", cascade="all, delete-orphan")
    context_logs = relationship("ContextLog", back_populates="topic", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="topic", cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)
    url = Column(String(2048), nullable=False)
    source_type = Column(String(50), nullable=False)  # REST API, CSV feed, JSON endpoint, etc.
    data_format = Column(String(50), nullable=False)  # json, csv, xml, etc.
    description = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="active")
    last_checked = Column(DateTime(timezone=True))
    last_success = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    topic = relationship("Topic", back_populates="sources")


class Run(Base):
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    completed_at = Column(DateTime(timezone=True))
    status = Column(String(50), nullable=False, default="running")  # running, completed, failed
    sources_queried = Column(Integer, default=0)
    sources_failed = Column(Integer, default=0)
    doc_url = Column(String(2048))

    topic = relationship("Topic", back_populates="runs")


class ContextLog(Base):
    __tablename__ = "context_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    change_type = Column(String(50), nullable=False)  # created, updated, refined, compressed
    change_detail = Column(Text, nullable=False)

    topic = relationship("Topic", back_populates="context_logs")


class ChatMessage(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)  # null for general chat
    role = Column(String(20), nullable=False)  # user, assistant
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    topic = relationship("Topic", back_populates="chat_messages")
