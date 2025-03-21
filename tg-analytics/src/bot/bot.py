"""
Модуль для Telegram-бота
"""
import asyncio
import logging
from typing import Dict, List, Optional, Union

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.config.config import settings
from src.database.db import SessionLocal
from src.analysis.llm_service import LLMAnalysisService

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=getattr(logging, settings.LOG_LEVEL)
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
(
    MENU, 
    ANALYZE_CHANNEL, 
    GENERATE_CONTENT_PLAN, 
    ANALYZE_POST, 
    CREATE_SURVEY,
    WAITING_FOR_CONFIRMATION
) = range(6)


class TelegramBot:
    """
    Класс для Telegram-бота
    """
    def __init__(self, token: Optional[str] = None):
        """
        Инициализация бота
        """
        self.token = token or settings.TG_BOT_TOKEN
        self.application = Application.builder().token(self.token).build()
        self._setup_handlers()
    
    def _setup_handlers(self):
        """
        Настройка обработчиков команд и сообщений
        """
        # Основные команды
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        
        # Обработчики для аналитики
        conversation_handler = ConversationHandler(
            entry_points=[CommandHandler("menu", self.menu_command)],
            states={
                MENU: [
                    MessageHandler(filters.Regex("^Анализ канала$"), self.analyze_channel),
                    MessageHandler(filters.Regex("^Генерация контент-плана$"), self.generate_content_plan),
                    MessageHandler(filters.Regex("^Анализ поста$"), self.analyze_post),
                    MessageHandler(filters.Regex("^Создать опрос$"), self.create_survey),
                ],
                ANALYZE_CHANNEL: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_channel_analysis),
                ],
                GENERATE_CONTENT_PLAN: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_content_plan),
                ],
                ANALYZE_POST: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_post_analysis),
                ],
                CREATE_SURVEY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_survey_creation),
                ],
                WAITING_FOR_CONFIRMATION: [
                    MessageHandler(filters.Regex("^Да$"), self.confirm_action),
                    MessageHandler(filters.Regex("^Нет$"), self.cancel_action),
                ],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )
        self.application.add_handler(conversation_handler)
        
        # Обработчик для неизвестных команд
        self.application.add_handler(MessageHandler(filters.COMMAND, self.unknown_command))
        
        # Обработчик ошибок
        self.application.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработка команды /start
        """
        await update.message.reply_text(
            f"Привет! Я бот для аналитики Telegram-каналов.\n\n"
            f"Я могу помочь анализировать контент, генерировать идеи для постов "
            f"и создавать опросы для вашей аудитории.\n\n"
            f"Введите /menu, чтобы увидеть доступные команды."
        )
        return ConversationHandler.END
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработка команды /help
        """
        help_text = (
            "Доступные команды:\n\n"
            "/start - Начать работу с ботом\n"
            "/menu - Открыть меню с функциями\n"
            "/help - Показать это сообщение\n"
            "/cancel - Отменить текущую операцию\n\n"
            "Через меню вы можете:\n"
            "- Анализировать контент канала\n"
            "- Генерировать контент-план\n"
            "- Анализировать отдельные посты\n"
            "- Создавать опросы для аудитории\n"
        )
        await update.message.reply_text(help_text)
        return ConversationHandler.END
    
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Отображение меню с доступными функциями
        """
        from telegram import ReplyKeyboardMarkup
        
        reply_keyboard = [
            ["Анализ канала"],
            ["Генерация контент-плана"],
            ["Анализ поста"],
            ["Создать опрос"],
        ]
        
        await update.message.reply_text(
            "Выберите действие:",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return MENU
    
    async def analyze_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Начало процесса анализа канала
        """
        await update.message.reply_text(
            "Пожалуйста, введите username канала для анализа (например, @channel_name):"
        )
        return ANALYZE_CHANNEL
    
    async def process_channel_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработка запроса на анализ канала
        """
        channel_username = update.message.text.strip()
        
        # Удаляем @ если есть
        if channel_username.startswith('@'):
            channel_username = channel_username[1:]
        
        # Сохраняем канал в контексте
        context.user_data["channel_username"] = channel_username
        
        # Спрашиваем подтверждение
        from telegram import ReplyKeyboardMarkup
        
        await update.message.reply_text(
            f"Вы хотите проанализировать канал @{channel_username}?",
            reply_markup=ReplyKeyboardMarkup(
                [["Да", "Нет"]], one_time_keyboard=True, resize_keyboard=True
            ),
        )
        
        # Сохраняем действие для подтверждения
        context.user_data["pending_action"] = "analyze_channel"
        
        return WAITING_FOR_CONFIRMATION
    
    async def generate_content_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Начало процесса генерации контент-плана
        """
        await update.message.reply_text(
            "Пожалуйста, введите username канала для генерации контент-плана (например, @channel_name):"
        )
        return GENERATE_CONTENT_PLAN
    
    async def process_content_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработка запроса на генерацию контент-плана
        """
        channel_username = update.message.text.strip()
        
        # Удаляем @ если есть
        if channel_username.startswith('@'):
            channel_username = channel_username[1:]
        
        # Сохраняем канал в контексте
        context.user_data["channel_username"] = channel_username
        
        # Спрашиваем подтверждение
        from telegram import ReplyKeyboardMarkup
        
        await update.message.reply_text(
            f"Вы хотите сгенерировать контент-план для канала @{channel_username}?",
            reply_markup=ReplyKeyboardMarkup(
                [["Да", "Нет"]], one_time_keyboard=True, resize_keyboard=True
            ),
        )
        
        # Сохраняем действие для подтверждения
        context.user_data["pending_action"] = "generate_content_plan"
        
        return WAITING_FOR_CONFIRMATION
    
    async def analyze_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Начало процесса анализа поста
        """
        await update.message.reply_text(
            "Пожалуйста, введите ID поста для анализа (например, 123):"
        )
        return ANALYZE_POST
    
    async def process_post_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработка запроса на анализ поста
        """
        try:
            post_id = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text(
                "Неверный формат ID поста. Пожалуйста, введите число."
            )
            return ANALYZE_POST
        
        # Сохраняем ID поста в контексте
        context.user_data["post_id"] = post_id
        
        # Спрашиваем подтверждение
        from telegram import ReplyKeyboardMarkup
        
        await update.message.reply_text(
            f"Вы хотите проанализировать пост с ID {post_id}?",
            reply_markup=ReplyKeyboardMarkup(
                [["Да", "Нет"]], one_time_keyboard=True, resize_keyboard=True
            ),
        )
        
        # Сохраняем действие для подтверждения
        context.user_data["pending_action"] = "analyze_post"
        
        return WAITING_FOR_CONFIRMATION
    
    async def create_survey(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Начало процесса создания опроса
        """
        await update.message.reply_text(
            "Пожалуйста, введите username канала для создания опроса (например, @channel_name):"
        )
        return CREATE_SURVEY
    
    async def process_survey_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработка запроса на создание опроса
        """
        channel_username = update.message.text.strip()
        
        # Удаляем @ если есть
        if channel_username.startswith('@'):
            channel_username = channel_username[1:]
        
        # Сохраняем канал в контексте
        context.user_data["channel_username"] = channel_username
        
        # Спрашиваем подтверждение
        from telegram import ReplyKeyboardMarkup
        
        await update.message.reply_text(
            f"Вы хотите создать опрос для аудитории канала @{channel_username}?",
            reply_markup=ReplyKeyboardMarkup(
                [["Да", "Нет"]], one_time_keyboard=True, resize_keyboard=True
            ),
        )
        
        # Сохраняем действие для подтверждения
        context.user_data["pending_action"] = "create_survey"
        
        return WAITING_FOR_CONFIRMATION
    
    async def confirm_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработка подтверждения действия
        """
        from telegram import ReplyKeyboardRemove
        
        action = context.user_data.get("pending_action")
        
        if not action:
            await update.message.reply_text(
                "Произошла ошибка. Пожалуйста, начните заново.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return ConversationHandler.END
        
        await update.message.reply_text(
            f"Выполняю запрос... Это может занять некоторое время.",
            reply_markup=ReplyKeyboardRemove(),
        )
        
        # Выполняем соответствующее действие
        if action == "analyze_channel":
            result = await self._perform_channel_analysis(update, context)
        elif action == "generate_content_plan":
            result = await self._perform_content_plan_generation(update, context)
        elif action == "analyze_post":
            result = await self._perform_post_analysis(update, context)
        elif action == "create_survey":
            result = await self._perform_survey_creation(update, context)
        else:
            result = {"error": "Неизвестное действие"}
        
        # Отправляем результат пользователю
        if "error" in result:
            await update.message.reply_text(
                f"Произошла ошибка: {result['error']}\n\n"
                f"Пожалуйста, попробуйте еще раз или свяжитесь с администратором."
            )
        else:
            await update.message.reply_text(
                f"Задача выполнена успешно!\n\n{result['message']}"
            )
        
        return ConversationHandler.END
    
    async def cancel_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Отмена текущего действия
        """
        from telegram import ReplyKeyboardRemove
        
        await update.message.reply_text(
            "Действие отменено.", 
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработка команды /cancel
        """
        from telegram import ReplyKeyboardRemove
        
        await update.message.reply_text(
            "Операция отменена.", 
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    async def unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработка неизвестных команд
        """
        await update.message.reply_text(
            "Извините, я не знаю такой команды. Используйте /help, чтобы увидеть список доступных команд."
        )
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработка ошибок
        """
        logger.error(f"Exception while handling an update: {context.error}")
        
        # Если у нас есть объект update, сообщаем пользователю об ошибке
        if update and hasattr(update, "effective_message"):
            await update.effective_message.reply_text(
                "Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже."
            )
    
    async def _perform_channel_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Dict:
        """
        Выполнение анализа канала
        """
        try:
            channel_username = context.user_data.get("channel_username")
            
            if not channel_username:
                return {"error": "Не указано имя канала"}
            
            # Получаем или создаем запись о канале в базе данных
            db = SessionLocal()
            
            # Здесь должна быть логика получения ID канала
            # Для простоты примера используем 1
            channel_id = 1
            
            # Создаем сервис для анализа
            llm_service = LLMAnalysisService(db)
            
            # Выполняем анализ
            result = await llm_service.analyze_channel_content(channel_id)
            
            db.close()
            
            if "error" in result:
                return {"error": result["error"]}
            
            # Формируем сообщение с результатами
            main_topics = ", ".join(result.get("main_topics", []))
            top_posts_count = len(result.get("top_posts", []))
            sentiment = result.get("audience_sentiment", "")
            ideas_count = len(result.get("content_ideas", []))
            
            message = (
                f"Анализ канала @{channel_username} завершен!\n\n"
                f"Основные темы: {main_topics}\n"
                f"Выявлено {top_posts_count} постов с наибольшим вовлечением\n"
                f"Настроение аудитории: {sentiment}\n"
                f"Создано {ideas_count} идей для новых постов\n\n"
                f"Полные результаты доступны в веб-интерфейсе."
            )
            
            return {"message": message}
        
        except Exception as e:
            logger.error(f"Error performing channel analysis: {e}")
            return {"error": str(e)}
    
    async def _perform_content_plan_generation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Dict:
        """
        Выполнение генерации контент-плана
        """
        try:
            channel_username = context.user_data.get("channel_username")
            
            if not channel_username:
                return {"error": "Не указано имя канала"}
            
            # Получаем или создаем запись о канале в базе данных
            db = SessionLocal()
            
            # Здесь должна быть логика получения ID канала
            # Для простоты примера используем 1
            channel_id = 1
            
            # Создаем сервис для анализа
            llm_service = LLMAnalysisService(db)
            
            # Выполняем генерацию контент-плана на 7 дней
            result = await llm_service.generate_content_plan(channel_id, days=7)
            
            db.close()
            
            if "error" in result:
                return {"error": result["error"]}
            
            # Формируем сообщение с результатами
            plan_data = result.get("content_plan", {})
            days_count = len(plan_data)
            
            message = (
                f"Контент-план для канала @{channel_username} на {days_count} дней создан!\n\n"
                f"Примеры тем:\n"
            )
            
            # Добавляем первые 3 темы из плана
            for i, (day_key, day_data) in enumerate(list(plan_data.items())[:3]):
                message += f"• День {i+1}: {day_data.get('title')}\n"
            
            message += "\nПолный контент-план доступен в веб-интерфейсе."
            
            return {"message": message}
        
        except Exception as e:
            logger.error(f"Error generating content plan: {e}")
            return {"error": str(e)}
    
    async def _perform_post_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Dict:
        """
        Выполнение анализа поста
        """
        try:
            post_id = context.user_data.get("post_id")
            
            if not post_id:
                return {"error": "Не указан ID поста"}
            
            # Инициализируем сессию базы данных
            db = SessionLocal()
            
            # Создаем сервис для анализа
            llm_service = LLMAnalysisService(db)
            
            # Выполняем анализ поста
            result = await llm_service.analyze_post_performance(post_id)
            
            db.close()
            
            if "error" in result:
                return {"error": result["error"]}
            
            # Формируем сообщение с результатами
            engagement = result.get("engagement_level", "")
            sentiment = result.get("comments_sentiment", "")
            pros = result.get("pros_and_cons", {}).get("pros", [])
            cons = result.get("pros_and_cons", {}).get("cons", [])
            
            message = (
                f"Анализ поста ID {post_id} завершен!\n\n"
                f"Уровень вовлечения: {engagement}\n"
                f"Тональность комментариев: {sentiment}\n\n"
                f"Сильные стороны:\n"
            )
            
            for pro in pros[:3]:  # Первые 3 преимущества
                message += f"• {pro}\n"
            
            message += "\nСлабые стороны:\n"
            
            for con in cons[:3]:  # Первые 3 недостатка
                message += f"• {con}\n"
            
            message += "\nПолные результаты анализа доступны в веб-интерфейсе."
            
            return {"message": message}
        
        except Exception as e:
            logger.error(f"Error analyzing post: {e}")
            return {"error": str(e)}
    
    async def _perform_survey_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Dict:
        """
        Выполнение создания опроса
        """
        try:
            channel_username = context.user_data.get("channel_username")
            
            if not channel_username:
                return {"error": "Не указано имя канала"}
            
            # Получаем или создаем запись о канале в базе данных
            db = SessionLocal()
            
            # Здесь должна быть логика получения ID канала
            # Для простоты примера используем 1
            channel_id = 1
            
            # Создаем сервис для анализа
            llm_service = LLMAnalysisService(db)
            
            # Создаем опрос
            result = await llm_service.generate_survey(channel_id)
            
            db.close()
            
            if "error" in result:
                return {"error": result["error"]}
            
            # Формируем сообщение с результатами
            survey_data = result.get("survey", {})
            questions_count = len(survey_data.get("questions", []))
            
            message = (
                f"Опрос для аудитории канала @{channel_username} создан!\n\n"
                f"Название: {survey_data.get('title')}\n"
                f"Количество вопросов: {questions_count}\n\n"
                f"Примеры вопросов:\n"
            )
            
            # Добавляем первые 3 вопроса
            for i, question in enumerate(survey_data.get("questions", [])[:3]):
                message += f"• {question.get('question_text')}\n"
            
            message += "\nОпрос доступен в веб-интерфейсе и готов к публикации."
            
            return {"message": message}
        
        except Exception as e:
            logger.error(f"Error creating survey: {e}")
            return {"error": str(e)}
    
    async def run(self):
        """
        Запуск бота
        """
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        try:
            # Держим бота запущенным до прерывания
            await asyncio.Event().wait()
        finally:
            # Корректное завершение работы бота
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()


async def main():
    """
    Основная функция для запуска бота
    """
    bot = TelegramBot()
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())