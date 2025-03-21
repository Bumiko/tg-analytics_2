"""
Модуль для взаимодействия с LLM (OpenAI) для анализа данных
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

import openai
from sqlalchemy.orm import Session

from src.config.config import settings
from src.database.models import (
    Analysis, 
    Channel, 
    Comment, 
    ContentPlan, 
    Post, 
    Reaction, 
    Survey, 
    User
)

# Настройка логирования
logger = logging.getLogger(__name__)

# Настройка OpenAI API
openai.api_key = settings.OPENAI_API_KEY


class LLMAnalysisService:
    """Сервис для анализа данных с использованием LLM"""

    def __init__(self, db: Session):
        """Инициализация сервиса"""
        self.db = db
        self.model = "gpt-4o"  # Используем современную модель OpenAI

    async def analyze_channel_content(self, channel_id: int) -> Dict:
        """
        Анализ содержимого канала 
        """
        # Получаем последние 50 постов
        posts = (
            self.db.query(Post)
            .filter(Post.channel_id == channel_id)
            .order_by(Post.posted_at.desc())
            .limit(50)
            .all()
        )

        # Если постов нет, возвращаем пустой анализ
        if not posts:
            return {"error": "No posts found for analysis"}

        # Подготовка данных для анализа
        posts_data = []
        for post in posts:
            # Получаем комментарии к посту
            comments = (
                self.db.query(Comment)
                .filter(Comment.post_id == post.id)
                .all()
            )
            
            # Получаем реакции к посту
            reactions = (
                self.db.query(Reaction)
                .filter(Reaction.post_id == post.id)
                .all()
            )

            post_data = {
                "id": post.tg_id,
                "content": post.content,
                "posted_at": post.posted_at.isoformat(),
                "views": post.views,
                "forwards": post.forwards,
                "comments_count": len(comments),
                "comments": [
                    {
                        "id": comment.tg_id,
                        "content": comment.content,
                        "user_id": comment.user_id,
                    }
                    for comment in comments[:10]  # Ограничиваем количество комментариев
                ],
                "reactions": [
                    {
                        "type": reaction.reaction_type,
                        "count": reaction.count,
                    }
                    for reaction in reactions
                ],
            }
            posts_data.append(post_data)

        # Формируем запрос к LLM
        prompt = f"""
        Проанализируй следующие данные из Telegram-канала:
        
        {json.dumps(posts_data, ensure_ascii=False, indent=2)}
        
        Выполни следующие задачи:
        1. Определи основные темы и категории контента
        2. Выяви посты с наибольшим вовлечением (по просмотрам, комментариям и реакциям)
        3. Проанализируй тональность комментариев и общее настроение аудитории
        4. Выяви ключевые запросы и вопросы подписчиков
        5. Предложи 5 идей для новых постов на основе анализа
        6. Определи оптимальное время публикации контента
        7. Выдели сильные и слабые стороны существующего контента
        
        Результат представь в формате JSON со следующими ключами:
        - main_topics
        - top_posts
        - audience_sentiment
        - audience_questions
        - content_ideas
        - optimal_posting_time
        - content_strengths
        - content_weaknesses
        """

        try:
            # Отправляем запрос к OpenAI API
            response = await openai.ChatCompletion.acreate(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Ты аналитик социальных медиа, который анализирует Telegram-каналы и предоставляет инсайты и рекомендации."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            # Получаем результат
            result = response.choices[0].message.content
            
            # Парсим JSON из ответа
            try:
                analysis_data = json.loads(result)
            except json.JSONDecodeError:
                # Если ответ не JSON, возвращаем его как есть в виде текста
                analysis_data = {"analysis": result}
            
            # Сохраняем результат анализа в базу данных
            analysis = Analysis(
                channel_id=channel_id,
                analysis_type="channel_content",
                content=json.dumps(analysis_data, ensure_ascii=False)
            )
            self.db.add(analysis)
            self.db.commit()
            
            return analysis_data
        
        except Exception as e:
            logger.error(f"Error analyzing channel content: {e}")
            return {"error": str(e)}

    async def generate_content_plan(self, channel_id: int, days: int = 7) -> Dict:
        """
        Генерация контент-плана на основе анализа данных
        """
        # Получаем последний анализ канала
        analysis = (
            self.db.query(Analysis)
            .filter(Analysis.channel_id == channel_id)
            .filter(Analysis.analysis_type == "channel_content")
            .order_by(Analysis.created_at.desc())
            .first()
        )
        
        if not analysis:
            # Если анализа нет, делаем его
            analysis_data = await self.analyze_channel_content(channel_id)
        else:
            # Иначе используем существующий
            analysis_data = json.loads(analysis.content)

        # Формируем запрос к LLM для генерации контент-плана
        prompt = f"""
        На основе следующего анализа Telegram-канала:
        
        {json.dumps(analysis_data, ensure_ascii=False, indent=2)}
        
        Создай контент-план на {days} дней. Для каждого дня предложи:
        1. Тему поста
        2. Краткое описание содержания
        3. Тип контента (информационный, развлекательный, опрос, обучающий, интерактивный и т.д.)
        4. Оптимальное время публикации
        5. Ожидаемый отклик аудитории
        
        Результат представь в формате JSON, где ключи - дни (day_1, day_2, ...), а значения - объекты с полями:
        - title
        - description
        - content_type
        - posting_time
        - expected_engagement
        """

        try:
            # Отправляем запрос к OpenAI API
            response = await openai.ChatCompletion.acreate(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Ты контент-менеджер для Telegram-канала, который создает эффективные контент-планы на основе аналитики."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2500
            )
            
            # Получаем результат
            result = response.choices[0].message.content
            
            # Парсим JSON из ответа
            try:
                plan_data = json.loads(result)
            except json.JSONDecodeError:
                return {"error": "Failed to parse response as JSON", "raw_response": result}
            
            # Сохраняем контент-план в базу данных
            today = datetime.utcnow()
            
            for day_key, day_plan in plan_data.items():
                # Определяем день от текущей даты
                day_num = int(day_key.split("_")[1])
                planned_date = today + timedelta(days=day_num-1)
                
                content_plan = ContentPlan(
                    channel_id=channel_id,
                    title=day_plan["title"],
                    description=day_plan["description"],
                    planned_date=planned_date,
                    content=json.dumps(day_plan, ensure_ascii=False),
                    status="draft"
                )
                self.db.add(content_plan)
            
            self.db.commit()
            
            return {"success": True, "content_plan": plan_data}
        
        except Exception as e:
            logger.error(f"Error generating content plan: {e}")
            return {"error": str(e)}

    async def analyze_post_performance(self, post_id: int) -> Dict:
        """
        Анализ эффективности отдельного поста
        """
        # Получаем данные поста
        post = self.db.query(Post).filter(Post.id == post_id).first()
        if not post:
            return {"error": "Post not found"}
        
        # Получаем комментарии к посту
        comments = (
            self.db.query(Comment)
            .filter(Comment.post_id == post_id)
            .all()
        )
        
        # Получаем реакции к посту
        reactions = (
            self.db.query(Reaction)
            .filter(Reaction.post_id == post_id)
            .all()
        )
        
        # Подготавливаем данные для анализа
        post_data = {
            "id": post.tg_id,
            "content": post.content,
            "posted_at": post.posted_at.isoformat(),
            "views": post.views,
            "forwards": post.forwards,
            "comments": [
                {
                    "id": comment.id,
                    "content": comment.content,
                    "user_id": comment.user_id,
                    "commented_at": comment.commented_at.isoformat(),
                }
                for comment in comments
            ],
            "reactions": [
                {
                    "type": reaction.reaction_type,
                    "count": reaction.count,
                }
                for reaction in reactions
            ],
        }
        
        # Формируем запрос к LLM
        prompt = f"""
        Проанализируй эффективность этого поста из Telegram-канала:
        
        {json.dumps(post_data, ensure_ascii=False, indent=2)}
        
        Выполни следующие задачи:
        1. Оцени вовлечение аудитории (высокое, среднее, низкое) с обоснованием
        2. Проанализируй тональность комментариев (позитивная, нейтральная, негативная)
        3. Выяви ключевые вопросы или запросы в комментариях
        4. Предложи, как можно улучшить пост или его подачу
        5. Определи, что в посте сработало хорошо, а что нет
        
        Результат представь в формате JSON со следующими ключами:
        - engagement_level
        - engagement_analysis
        - comments_sentiment
        - key_questions
        - improvement_suggestions
        - pros_and_cons
        """

        try:
            # Отправляем запрос к OpenAI API
            response = await openai.ChatCompletion.acreate(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Ты аналитик социальных медиа, который оценивает эффективность постов в Telegram."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1500
            )
            
            # Получаем результат
            result = response.choices[0].message.content
            
            # Парсим JSON из ответа
            try:
                analysis_data = json.loads(result)
            except json.JSONDecodeError:
                return {"error": "Failed to parse response as JSON", "raw_response": result}
            
            # Сохраняем результат анализа в базу данных
            analysis = Analysis(
                post_id=post_id,
                analysis_type="post_performance",
                content=json.dumps(analysis_data, ensure_ascii=False)
            )
            self.db.add(analysis)
            self.db.commit()
            
            return analysis_data
        
        except Exception as e:
            logger.error(f"Error analyzing post performance: {e}")
            return {"error": str(e)}

    async def generate_survey(self, channel_id: int) -> Dict:
        """
        Генерация опроса для аудитории на основе анализа данных
        """
        # Получаем последний анализ канала
        analysis = (
            self.db.query(Analysis)
            .filter(Analysis.channel_id == channel_id)
            .filter(Analysis.analysis_type == "channel_content")
            .order_by(Analysis.created_at.desc())
            .first()
        )
        
        if not analysis:
            # Если анализа нет, делаем его
            analysis_data = await self.analyze_channel_content(channel_id)
        else:
            # Иначе используем существующий
            analysis_data = json.loads(analysis.content)
        
        # Формируем запрос к LLM для генерации опроса
        prompt = f"""
        На основе следующего анализа Telegram-канала:
        
        {json.dumps(analysis_data, ensure_ascii=False, indent=2)}
        
        Создай опрос для аудитории, который поможет лучше понять их потребности и улучшить контент.
        
        Опрос должен содержать:
        1. Краткое вступление с объяснением цели опроса
        2. 5-7 вопросов разных типов (выбор одного варианта, множественный выбор, открытый вопрос и т.д.)
        3. Благодарность за участие
        
        Вопросы должны касаться:
        - Предпочтений по темам контента
        - Удовлетворенности текущим контентом
        - Пожеланий по новым форматам
        - Демографических данных аудитории (возраст, интересы и т.д.)
        - Частоты взаимодействия с каналом
        
        Результат представь в формате JSON со следующими ключами:
        - title
        - description
        - questions (массив объектов с полями: question_text, question_type, options)
        - thank_you_message
        """

        try:
            # Отправляем запрос к OpenAI API
            response = await openai.ChatCompletion.acreate(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Ты специалист по маркетинговым исследованиям, который создает эффективные опросы для аудитории Telegram-канала."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=2000
            )
            
            # Получаем результат
            result = response.choices[0].message.content
            
            # Парсим JSON из ответа
            try:
                survey_data = json.loads(result)
            except json.JSONDecodeError:
                return {"error": "Failed to parse response as JSON", "raw_response": result}
            
            # Сохраняем опрос в базу данных
            survey = Survey(
                channel_id=channel_id,
                title=survey_data["title"],
                description=survey_data["description"],
                questions=json.dumps(survey_data["questions"], ensure_ascii=False),
                status="draft"
            )
            self.db.add(survey)
            self.db.commit()
            
            return {"success": True, "survey": survey_data}
        
        except Exception as e:
            logger.error(f"Error generating survey: {e}")
            return {"error": str(e)}