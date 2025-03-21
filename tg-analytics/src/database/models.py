"""
Модели данных для хранения информации из Telegram
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    Column, 
    DateTime, 
    Float, 
    ForeignKey, 
    Integer, 
    String, 
    Text
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    """Модель пользователя Telegram"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Отношения
    comments = relationship("Comment", back_populates="user")
    
    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"


class Channel(Base):
    """Модель Telegram-канала"""
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(255), nullable=True)
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    member_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Отношения
    posts = relationship("Post", back_populates="channel")
    
    def __repr__(self):
        return f"<Channel(id={self.id}, title={self.title})>"


class Post(Base):
    """Модель поста в Telegram-канале"""
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, nullable=False)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    content = Column(Text, nullable=False)
    posted_at = Column(DateTime, nullable=False)
    views = Column(Integer, default=0)
    forwards = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Отношения
    channel = relationship("Channel", back_populates="posts")
    comments = relationship("Comment", back_populates="post")
    reactions = relationship("Reaction", back_populates="post")
    
    def __repr__(self):
        return f"<Post(id={self.id}, tg_id={self.tg_id}, views={self.views})>"


class Comment(Base):
    """Модель комментария к посту"""
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    content = Column(Text, nullable=False)
    commented_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Отношения
    post = relationship("Post", back_populates="comments")
    user = relationship("User", back_populates="comments")
    reactions = relationship("Reaction", back_populates="comment")
    
    def __repr__(self):
        return f"<Comment(id={self.id}, tg_id={self.tg_id}, user_id={self.user_id})>"


class Reaction(Base):
    """Модель реакции (эмодзи) на пост или комментарий"""
    __tablename__ = "reactions"

    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=True)
    comment_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    reaction_type = Column(String(255), nullable=False)
    count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Отношения
    post = relationship("Post", back_populates="reactions")
    comment = relationship("Comment", back_populates="reactions")
    
    def __repr__(self):
        target_id = self.post_id if self.post_id else self.comment_id
        target_type = "post" if self.post_id else "comment"
        return f"<Reaction(id={self.id}, type={self.reaction_type}, {target_type}_id={target_id})>"


class Analysis(Base):
    """Модель для хранения результатов анализа LLM"""
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=True)
    analysis_type = Column(String(255), nullable=False)  # Тип анализа (контент-план, идеи, инсайты и т.д.)
    content = Column(Text, nullable=False)  # Результат анализа в JSON или другом формате
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Analysis(id={self.id}, type={self.analysis_type})>"


class ContentPlan(Base):
    """Модель для хранения контент-плана"""
    __tablename__ = "content_plans"

    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    planned_date = Column(DateTime, nullable=True)
    content = Column(Text, nullable=False)  # Содержимое поста
    status = Column(String(50), default="draft")  # draft, scheduled, published, etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<ContentPlan(id={self.id}, title={self.title}, status={self.status})>"


class Survey(Base):
    """Модель для опросов аудитории"""
    __tablename__ = "surveys"

    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    questions = Column(Text, nullable=False)  # JSON с вопросами
    status = Column(String(50), default="draft")  # draft, active, completed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Survey(id={self.id}, title={self.title}, status={self.status})>"