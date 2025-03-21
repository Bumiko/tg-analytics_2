"""
Основной модуль для запуска приложения
"""
import argparse
import asyncio
import logging
import signal
import sys
from typing import List, Optional

from src.api.server import run_server
from src.bot.bot import TelegramBot
from src.config.config import settings
from src.data.collector import TelegramDataCollector
from src.database.db import init_db

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_bot():
    """
    Запуск Telegram-бота
    """
    logger.info("Starting Telegram bot")
    bot = TelegramBot()
    await bot.run()


def run_api():
    """
    Запуск API-сервера
    """
    logger.info("Starting API server")
    run_server()


async def collect_data(channel_username: str, limit: int = 100):
    """
    Сбор данных из канала
    """
    logger.info(f"Collecting data from channel: {channel_username}")
    collector = TelegramDataCollector()
    try:
        await collector.start()
        
        # Получаем информацию о канале
        channel_info = await collector.get_channel_info(channel_username)
        logger.info(f"Channel info: {channel_info}")
        
        # Получаем последние посты
        posts = await collector.get_posts(channel_username, limit=limit)
        logger.info(f"Collected {len(posts)} posts")
        
        # Для первых 10 постов получаем комментарии
        for post in posts[:10]:
            comments = await collector.get_comments(
                channel_username, post_id=post["id"], limit=50
            )
            logger.info(
                f"Collected {len(comments)} comments for post {post['id']}"
            )
        
    finally:
        await collector.stop()
    
    logger.info("Data collection completed")


async def init_database():
    """
    Инициализация базы данных
    """
    logger.info("Initializing database")
    init_db()
    logger.info("Database initialized")


def parse_args():
    """
    Разбор аргументов командной строки
    """
    parser = argparse.ArgumentParser(description="TG Analytics Application")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["bot", "api", "collector", "all"],
        default="all",
        help="Run mode (bot, api, collector, all)",
    )
    parser.add_argument(
        "--channel",
        type=str,
        help="Channel username for collector mode",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Limit of posts to collect (collector mode)",
    )
    
    return parser.parse_args()


async def main():
    """
    Основная функция
    """
    args = parse_args()
    
    # Инициализация базы данных
    await init_database()
    
    if args.mode == "bot":
        # Запуск только бота
        await run_bot()
    
    elif args.mode == "api":
        # Запуск только API
        run_api()
    
    elif args.mode == "collector":
        # Запуск только коллектора данных
        if not args.channel:
            logger.error("Channel username is required for collector mode")
            sys.exit(1)
            
        await collect_data(args.channel, args.limit)
    
    else:  # all
        # Запуск и бота, и API
        # В продакшене лучше запускать их отдельно
        
        # Для запуска API в отдельном процессе используем multiprocessing
        import multiprocessing
        
        # Запускаем API в отдельном процессе
        api_process = multiprocessing.Process(target=run_api)
        api_process.start()
        
        # Запускаем бота в текущем процессе
        try:
            await run_bot()
        finally:
            # При завершении останавливаем API
            api_process.terminate()
            api_process.join()


if __name__ == "__main__":
    # Настройка обработки сигналов для корректного завершения
    loop = asyncio.get_event_loop()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: loop.stop())
    
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()