"""
Конфигурация приложения
"""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Загрузка переменных окружения из файла .env
env_path = Path(".") / ".env"
load_dotenv(dotenv_path=env_path)


class Settings(BaseSettings):
    """
    Настройки приложения
    """
    # Название приложения
    APP_NAME: str = "TG Analytics"
    APP_VERSION: str = "0.1.0"
    
    # Режим отладки
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
    
    # Уровень логирования
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # База данных
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./tg_analytics.db")
    
    # Telegram API
    TG_API_ID: int = int(os.getenv("TG_API_ID", "0"))
    TG_API_HASH: str = os.getenv("TG_API_HASH", "")
    TG_BOT_TOKEN: str = os.getenv("TG_BOT_TOKEN", "")
    TG_PHONE: str = os.getenv("TG_PHONE", "")
    CHANNEL_USERNAME: str = os.getenv("CHANNEL_USERNAME", "")
    
    # OpenAI API
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # API настройки
    API_PREFIX: str = "/api/v1"
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    
    class Config:
        """
        Настройки класса
        """
        env_file = ".env"
        env_file_encoding = "utf-8"


# Создание экземпляра настроек
settings = Settings()