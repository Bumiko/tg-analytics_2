"""
Модуль для сбора данных из Telegram API
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.types import (
    Channel,
    Message,
    MessageReactions,
    PeerChannel,
    User,
)

from src.config.config import settings
from src.database.db import SessionLocal, engine
from src.database.models import Base, Comment, Post, Reaction, User as UserModel

logger = logging.getLogger(__name__)


class TelegramDataCollector:
    """Класс для сбора данных из Telegram-канала"""

    def __init__(self):
        """Инициализация клиента Telegram"""
        self.api_id = settings.TG_API_ID
        self.api_hash = settings.TG_API_HASH
        self.phone = settings.TG_PHONE
        self.channel_username = settings.CHANNEL_USERNAME
        self.client = None
        Base.metadata.create_all(bind=engine)

    async def start(self):
        """Запуск клиента Telegram"""
        self.client = TelegramClient('tg_analytics_session', self.api_id, self.api_hash)
        await self.client.start(phone=self.phone)
        logger.info("Telegram client started")

    async def stop(self):
        """Остановка клиента Telegram"""
        if self.client:
            await self.client.disconnect()
            logger.info("Telegram client disconnected")

    async def get_channel_info(self, channel_username: Optional[str] = None) -> Dict:
        """Получение информации о канале"""
        if not channel_username:
            channel_username = self.channel_username

        entity = await self.client.get_entity(channel_username)
        if isinstance(entity, Channel):
            return {
                "id": entity.id,
                "title": entity.title,
                "username": entity.username,
                "description": getattr(entity, "about", None),
                "member_count": getattr(entity, "participants_count", None),
            }
        return {}

    async def get_posts(
        self, 
        channel_username: Optional[str] = None, 
        limit: int = 100,
        offset_date: Optional[datetime] = None
    ) -> List[Dict]:
        """Получение сообщений из канала"""
        if not channel_username:
            channel_username = self.channel_username

        entity = await self.client.get_entity(channel_username)
        posts = []

        # Получаем историю сообщений
        history = await self.client(
            GetHistoryRequest(
                peer=entity,
                limit=limit,
                offset_date=offset_date,
                offset_id=0,
                max_id=0,
                min_id=0,
                add_offset=0,
                hash=0,
            )
        )

        # Сохраняем сообщения в базу данных
        with SessionLocal() as db:
            for message in history.messages:
                if not message.message:  # Пропускаем пустые сообщения
                    continue

                # Преобразуем сообщение в словарь
                post_data = {
                    "id": message.id,
                    "date": message.date,
                    "text": message.message,
                    "views": getattr(message, "views", 0),
                    "forwards": getattr(message, "forwards", 0),
                }
                posts.append(post_data)

                # Сохраняем пост в базу данных
                post = Post(
                    tg_id=message.id,
                    channel_id=entity.id,
                    content=message.message,
                    posted_at=message.date,
                    views=getattr(message, "views", 0),
                    forwards=getattr(message, "forwards", 0),
                )
                db.add(post)
                
                # Получаем и сохраняем реакции к посту
                await self._save_reactions(message, post, db)
            
            db.commit()

        return posts

    async def get_comments(
        self, 
        channel_username: Optional[str] = None, 
        post_id: Optional[int] = None, 
        limit: int = 100
    ) -> List[Dict]:
        """Получение комментариев к посту"""
        if not channel_username:
            channel_username = self.channel_username

        entity = await self.client.get_entity(channel_username)
        comments = []

        # Если указан ID поста, получаем комментарии только для этого поста
        if post_id:
            message = await self.client.get_messages(entity, ids=post_id)
            if message:
                replies = await self.client.get_messages(
                    entity, reply_to=message.id, limit=limit
                )
                
                # Сохраняем комментарии в базу данных
                with SessionLocal() as db:
                    for reply in replies:
                        if not reply.message:  # Пропускаем пустые сообщения
                            continue
                            
                        # Получаем информацию о пользователе
                        user_info = None
                        if reply.from_id:
                            try:
                                user = await self.client.get_entity(reply.from_id)
                                if isinstance(user, User):
                                    user_info = {
                                        "id": user.id,
                                        "username": user.username,
                                        "first_name": user.first_name,
                                        "last_name": user.last_name,
                                    }
                                    
                                    # Сохраняем пользователя в базу данных
                                    db_user = UserModel(
                                        tg_id=user.id,
                                        username=user.username,
                                        first_name=user.first_name,
                                        last_name=user.last_name,
                                    )
                                    db.merge(db_user)
                            except Exception as e:
                                logger.error(f"Error getting user info: {e}")
                        
                        # Преобразуем комментарий в словарь
                        comment_data = {
                            "id": reply.id,
                            "post_id": post_id,
                            "date": reply.date,
                            "text": reply.message,
                            "user": user_info,
                        }
                        comments.append(comment_data)
                        
                        # Сохраняем комментарий в базу данных
                        comment = Comment(
                            tg_id=reply.id,
                            post_id=post_id,
                            user_id=user_info["id"] if user_info else None,
                            content=reply.message,
                            commented_at=reply.date,
                        )
                        db.add(comment)
                        
                        # Получаем и сохраняем реакции к комментарию
                        await self._save_reactions(reply, comment, db)
                    
                    db.commit()

        return comments

    async def _save_reactions(
    self, 
    message: Message, 
    entity: Union[Post, Comment],
    db_session
):
    """Сохранение реакций к сообщению"""
    if hasattr(message, "reactions") and message.reactions:
        reactions = message.reactions
        if isinstance(reactions, MessageReactions):
            for reaction in reactions.results:
                # Преобразуем тип реакции в строковое представление
                if hasattr(reaction.reaction, "emoticon"):
                    reaction_type = reaction.reaction.emoticon
                elif hasattr(reaction.reaction, "document_id"):
                    reaction_type = f"custom_{reaction.reaction.document_id}"
                else:
                    reaction_type = str(reaction.reaction)
                
                reaction_model = Reaction(
                    reaction_type=reaction_type,
                    count=reaction.count,
                    post_id=entity.id if isinstance(entity, Post) else None,
                    comment_id=entity.id if isinstance(entity, Comment) else None,
                )
                db_session.add(reaction_model)


async def main():
    """Основная функция для тестирования коллектора данных"""
    collector = TelegramDataCollector()
    try:
        await collector.start()
        
        # Получаем информацию о канале
        channel_info = await collector.get_channel_info()
        print(f"Channel info: {channel_info}")
        
        # Получаем последние 10 постов
        posts = await collector.get_posts(limit=10)
        print(f"Got {len(posts)} posts")
        
        # Для первого поста получаем комментарии
        if posts:
            comments = await collector.get_comments(post_id=posts[0]["id"], limit=20)
            print(f"Got {len(comments)} comments for post {posts[0]['id']}")
        
    finally:
        await collector.stop()


if __name__ == "__main__":
    asyncio.run(main())