import asyncio
import logging
from aiogram import Bot, Dispatcher
from app.config import settings
from app.database.core import init_db
from app.tg_bot.middlewares import UserLanguageMiddleware
from app.tg_bot.handlers import base, search, recipe, shopping, history

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

async def main():
    if not settings.bot_token or settings.bot_token == "your_telegram_bot_token_here":
        logger.error("BOT_TOKEN is missing or invalid. Please check your .env file or Render environment variables.")
        return
        
    await init_db()
    
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    
    # Check for webhook and remove if exists (prevent conflict)
    try:
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url:
            logger.info("Found webhook. Deleting it to use long polling...")
            await bot.delete_webhook(drop_pending_updates=False)
    except Exception as e:
        logger.warning(f"Failed to check/delete webhook: {e}")
    
    dp.update.middleware(UserLanguageMiddleware())
    
    dp.include_router(base.router)
    dp.include_router(search.router)
    dp.include_router(recipe.router)
    dp.include_router(shopping.router)
    dp.include_router(history.router)
    
    logger.info("Starting bot...")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
