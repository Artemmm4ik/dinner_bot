import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from app.config import settings
from app.database.core import init_db, close_db
from app.tg_bot.middlewares import UserLanguageMiddleware, IdempotencyMiddleware
from app.tg_bot.handlers import base, search, recipe, shopping, history

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

async def on_startup(bot: Bot):
    await init_db()
    if settings.bot_mode == 'webhook':
        if not settings.webhook_base_url or not settings.webhook_secret:
            logger.error("Webhook settings (WEBHOOK_BASE_URL, WEBHOOK_SECRET) are missing!")
            return
        
        url = f"{settings.webhook_base_url.rstrip('/')}/telegram/webhook"
        logger.info(f"Setting webhook: {url}")
        await bot.set_webhook(
            url=url,
            secret_token=settings.webhook_secret,
            drop_pending_updates=False # Important: do not drop updates (e.g. payments)
        )
    else:
        logger.info("Running in polling mode. Removing webhook if any...")
        await bot.delete_webhook(drop_pending_updates=False)

async def on_shutdown(bot: Bot):
    await close_db()
    # Note: We intentionally do NOT delete the webhook on shutdown in webhook mode.
    # This ensures that while the free tier container is sleeping, Telegram holds the updates.

async def healthz_handler(request):
    return web.Response(text="OK", status=200)

def main():
    if not settings.bot_token or settings.bot_token == "your_telegram_bot_token_here":
        logger.error("BOT_TOKEN is missing or invalid.")
        return

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    
    # Setup middlewares. Idempotency must wrap the whole update flow.
    dp.update.outer_middleware(IdempotencyMiddleware())
    dp.update.middleware(UserLanguageMiddleware())
    
    dp.include_router(base.router)
    dp.include_router(search.router)
    dp.include_router(recipe.router)
    dp.include_router(shopping.router)
    dp.include_router(history.router)
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    if settings.bot_mode == 'webhook':
        app = web.Application()
        # Add healthcheck endpoint for Render
        app.router.add_get('/healthz', healthz_handler)
        
        # Configure Aiogram webhook request handler
        webhook_requests_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            secret_token=settings.webhook_secret,
        )
        webhook_requests_handler.register(app, path='/telegram/webhook')
        setup_application(app, dp, bot=bot)
        
        logger.info(f"Starting web application on port {settings.port}...")
        web.run_app(app, host='0.0.0.0', port=settings.port)
    else:
        logger.info("Starting bot in long-polling mode...")
        asyncio.run(dp.start_polling(bot))

if __name__ == "__main__":
    main()
