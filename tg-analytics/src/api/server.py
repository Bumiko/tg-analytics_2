"""
FastAPI сервер для API
"""
import logging
from typing import Dict

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import router
from src.config.config import settings
from src.database.db import init_db

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Создание приложения FastAPI
app = FastAPI(
    title=settings.APP_NAME,
    description="API для аналитики Telegram-каналов",
    version=settings.APP_VERSION,
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене следует ограничить список разрешенных источников
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутера с API-эндпоинтами
app.include_router(router, prefix=settings.API_PREFIX)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Глобальный обработчик исключений
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "message": str(exc)},
    )


@app.on_event("startup")
async def startup_event():
    """
    Действия при запуске сервера
    """
    logger.info("Starting up API server")
    # Инициализация базы данных
    init_db()


@app.on_event("shutdown")
async def shutdown_event():
    """
    Действия при остановке сервера
    """
    logger.info("Shutting down API server")


@app.get("/")
async def root():
    """
    Корневой эндпоинт
    """
    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }


def run_server():
    """
    Запуск сервера
    """
    uvicorn.run(
        "src.api.server:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
    )


if __name__ == "__main__":
    run_server()