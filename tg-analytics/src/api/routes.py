"""
API эндпоинты для веб-интерфейса
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.database.db import get_db
from src.database.models import (
    Analysis,
    Channel,
    Comment,
    ContentPlan,
    Post,
    Reaction,
    Survey,
)
from src.analysis.llm_service import LLMAnalysisService
from src.data.collector import TelegramDataCollector

# Создание роутера
router = APIRouter()

# Настройка логирования
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check():
    """
    Проверка здоровья API
    """
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@router.get("/channels")
async def get_channels(db: Session = Depends(get_db)):
    """
    Получение списка каналов
    """
    channels = db.query(Channel).all()
    return {"channels": channels}


@router.post("/channels")
async def add_channel(channel_data: Dict, db: Session = Depends(get_db)):
    """
    Добавление нового канала
    """
    try:
        # Инициализация коллектора данных
        collector = TelegramDataCollector()
        await collector.start()
        
        # Получение информации о канале
        channel_username = channel_data.get("username")
        if not channel_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Channel username is required",
            )
        
        # Удаляем @ если есть
        if channel_username.startswith('@'):
            channel_username = channel_username[1:]
        
        channel_info = await collector.get_channel_info(channel_username)
        
        # Создание записи о канале в базе данных
        channel = Channel(
            tg_id=channel_info["id"],
            username=channel_info["username"],
            title=channel_info["title"],
            description=channel_info["description"],
            member_count=channel_info["member_count"],
        )
        db.add(channel)
        db.commit()
        db.refresh(channel)
        
        # Завершаем работу коллектора
        await collector.stop()
        
        return {"success": True, "channel": channel}
    
    except Exception as e:
        logger.error(f"Error adding channel: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/channels/{channel_id}")
async def get_channel(channel_id: int, db: Session = Depends(get_db)):
    """
    Получение информации о канале
    """
    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel with ID {channel_id} not found",
        )
    return {"channel": channel}


@router.get("/channels/{channel_id}/posts")
async def get_channel_posts(
    channel_id: int, 
    limit: int = 50, 
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    Получение постов канала
    """
    posts = (
        db.query(Post)
        .filter(Post.channel_id == channel_id)
        .order_by(Post.posted_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"posts": posts, "total": len(posts)}


@router.post("/channels/{channel_id}/collect")
async def collect_channel_data(
    channel_id: int,
    collection_data: Dict,
    db: Session = Depends(get_db)
):
    """
    Сбор данных из канала
    """
    try:
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if not channel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Channel with ID {channel_id} not found",
            )
        
        # Получаем параметры сбора данных
        limit = collection_data.get("limit", 100)
        
        # Инициализация коллектора данных
        collector = TelegramDataCollector()
        await collector.start()
        
        # Сбор постов
        posts = await collector.get_posts(channel.username, limit=limit)
        
        # Сбор комментариев для каждого поста
        for post in posts[:10]:  # Ограничиваем количество постов для сбора комментариев
            comments = await collector.get_comments(
                channel.username, post_id=post["id"], limit=50
            )
        
        # Завершаем работу коллектора
        await collector.stop()
        
        return {
            "success": True,
            "message": f"Collected {len(posts)} posts and comments from @{channel.username}",
        }
    
    except Exception as e:
        logger.error(f"Error collecting channel data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/posts/{post_id}")
async def get_post(post_id: int, db: Session = Depends(get_db)):
    """
    Получение информации о посте
    """
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with ID {post_id} not found",
        )
    
    # Получаем комментарии к посту
    comments = db.query(Comment).filter(Comment.post_id == post_id).all()
    
    # Получаем реакции к посту
    reactions = db.query(Reaction).filter(Reaction.post_id == post_id).all()
    
    return {
        "post": post,
        "comments": comments,
        "reactions": reactions,
    }


@router.get("/posts/{post_id}/comments")
async def get_post_comments(
    post_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    Получение комментариев к посту
    """
    comments = (
        db.query(Comment)
        .filter(Comment.post_id == post_id)
        .order_by(Comment.commented_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"comments": comments, "total": len(comments)}


@router.post("/channels/{channel_id}/analyze")
async def analyze_channel(channel_id: int, db: Session = Depends(get_db)):
    """
    Анализ содержимого канала
    """
    try:
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if not channel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Channel with ID {channel_id} not found",
            )
        
        # Создаем сервис для анализа
        llm_service = LLMAnalysisService(db)
        
        # Выполняем анализ
        result = await llm_service.analyze_channel_content(channel_id)
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["error"],
            )
        
        return {
            "success": True,
            "analysis": result,
        }
    
    except Exception as e:
        logger.error(f"Error analyzing channel: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/channels/{channel_id}/content-plan")
async def generate_content_plan(
    channel_id: int,
    plan_data: Dict,
    db: Session = Depends(get_db)
):
    """
    Генерация контент-плана
    """
    try:
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if not channel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Channel with ID {channel_id} not found",
            )
        
        # Получаем количество дней для плана
        days = plan_data.get("days", 7)
        
        # Создаем сервис для анализа
        llm_service = LLMAnalysisService(db)
        
        # Генерируем контент-план
        result = await llm_service.generate_content_plan(channel_id, days=days)
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["error"],
            )
        
        return {
            "success": True,
            "content_plan": result["content_plan"],
        }
    
    except Exception as e:
        logger.error(f"Error generating content plan: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/channels/{channel_id}/content-plans")
async def get_content_plans(
    channel_id: int,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    Получение контент-планов канала
    """
    content_plans = (
        db.query(ContentPlan)
        .filter(ContentPlan.channel_id == channel_id)
        .order_by(ContentPlan.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"content_plans": content_plans, "total": len(content_plans)}


@router.post("/posts/{post_id}/analyze")
async def analyze_post(post_id: int, db: Session = Depends(get_db)):
    """
    Анализ эффективности поста
    """
    try:
        post = db.query(Post).filter(Post.id == post_id).first()
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Post with ID {post_id} not found",
            )
        
        # Создаем сервис для анализа
        llm_service = LLMAnalysisService(db)
        
        # Выполняем анализ
        result = await llm_service.analyze_post_performance(post_id)
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["error"],
            )
        
        return {
            "success": True,
            "analysis": result,
        }
    
    except Exception as e:
        logger.error(f"Error analyzing post: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/channels/{channel_id}/survey")
async def create_survey(channel_id: int, db: Session = Depends(get_db)):
    """
    Создание опроса для аудитории
    """
    try:
        channel = db.query(Channel).filter(Channel.id == channel_id).first()
        if not channel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Channel with ID {channel_id} not found",
            )
        
        # Создаем сервис для анализа
        llm_service = LLMAnalysisService(db)
        
        # Создаем опрос
        result = await llm_service.generate_survey(channel_id)
        
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["error"],
            )
        
        return {
            "success": True,
            "survey": result["survey"],
        }
    
    except Exception as e:
        logger.error(f"Error creating survey: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/channels/{channel_id}/surveys")
async def get_surveys(
    channel_id: int,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    Получение опросов канала
    """
    surveys = (
        db.query(Survey)
        .filter(Survey.channel_id == channel_id)
        .order_by(Survey.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"surveys": surveys, "total": len(surveys)}


@router.get("/analyses")
async def get_analyses(
    channel_id: Optional[int] = None,
    post_id: Optional[int] = None,
    analysis_type: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    Получение результатов анализа
    """
    query = db.query(Analysis)
    
    if channel_id:
        query = query.filter(Analysis.channel_id == channel_id)
    
    if post_id:
        query = query.filter(Analysis.post_id == post_id)
    
    if analysis_type:
        query = query.filter(Analysis.analysis_type == analysis_type)
    
    analyses = query.order_by(Analysis.created_at.desc()).offset(offset).limit(limit).all()
    
    # Преобразуем JSON-строки в объекты для ответа
    result_analyses = []
    for analysis in analyses:
        analysis_dict = {
            "id": analysis.id,
            "channel_id": analysis.channel_id,
            "post_id": analysis.post_id,
            "analysis_type": analysis.analysis_type,
            "created_at": analysis.created_at.isoformat(),
        }
        
        try:
            analysis_dict["content"] = json.loads(analysis.content)
        except json.JSONDecodeError:
            analysis_dict["content"] = analysis.content
        
        result_analyses.append(analysis_dict)
    
    return {"analyses": result_analyses, "total": len(result_analyses)}