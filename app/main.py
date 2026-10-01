"""Render Free: real HTTP webhook; financial updates committed before HTTP 200."""

import asyncio
import hmac
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import Update, BotCommand
from app.config import settings
from app.database.core import init_db, close_db
from app.database.repo import repo
from app.tg_bot.middlewares import UserLanguageMiddleware
from app.tg_bot import payments, internet
from app.tg_bot.handlers import app as handlers

logger = logging.getLogger(__name__)


def make_dispatcher():
    dp = Dispatcher()
    dp.message.outer_middleware(UserLanguageMiddleware())
    dp.callback_query.outer_middleware(UserLanguageMiddleware())
    dp.include_router(payments.router)
    dp.include_router(internet.router)
    dp.include_router(handlers.router)
    return dp


async def setup(bot):
    await init_db()
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Menu / Меню"),
            BotCommand(command="plus", description="Plus / Subscription"),
            BotCommand(command="paysupport", description="Payment support / Підтримка"),
            BotCommand(command="terms", description="Terms / Умови"),
            BotCommand(command="privacy", description="Privacy / Приватність"),
            BotCommand(
                command="delete_me", description="Delete food data / Видалити дані"
            ),
        ]
    )


def web_app(bot, dp):
    app = web.Application(client_max_size=1024 * 1024)
    regular_lock = asyncio.Lock()

    async def dispatch(update):
        if await repo.is_update_processed(update.update_id):
            return
        await dp.feed_update(bot, update)
        await repo.mark_update_processed(update.update_id)

    async def webhook(request):
        supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(supplied, settings.webhook_secret or ""):
            raise web.HTTPForbidden()
        try:
            update = Update.model_validate(await request.json(), context={"bot": bot})
        except (ValueError, TypeError):
            raise web.HTTPBadRequest() from None
        try:
            if update.pre_checkout_query:
                await dp.feed_update(bot, update)
            else:
                async with regular_lock:
                    await dispatch(update)
        except Exception:
            logger.error(
                "Update %s failed; returning 503 for Telegram retry", update.update_id
            )
            raise web.HTTPServiceUnavailable() from None
        return web.Response(text="ok")

    async def health(request):
        return web.json_response({"status": "ok"})

    async def startup(app):
        await setup(bot)
        await bot.set_webhook(
            settings.webhook_base_url.rstrip("/") + "/telegram",
            secret_token=settings.webhook_secret,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=False,
            max_connections=2,
        )
        await repo._execute(
            "DELETE FROM search_requests WHERE created_at<now()-interval '2 days'"
        )
        await repo._execute(
            "DELETE FROM processed_updates WHERE processed_at<now()-interval '7 days'"
        )

    async def cleanup(app):
        await close_db()
        await bot.session.close()

    app.router.add_post("/telegram", webhook)
    app.router.add_get("/healthz", health)
    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)
    return app


async def polling(bot, dp):
    try:
        await setup(bot)
        info = await bot.get_webhook_info()
        if info.url:
            raise RuntimeError(
                "Webhook exists. Use a separate test bot; polling will not delete a live webhook."
            )
        await dp.start_polling(
            bot, handle_as_tasks=False, allowed_updates=dp.resolve_used_update_types()
        )
    finally:
        await close_db()
        await bot.session.close()


def main():
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bot = Bot(settings.bot_token)
    dp = make_dispatcher()
    if settings.bot_mode == "webhook":
        web.run_app(
            web_app(bot, dp), host="0.0.0.0", port=settings.port, access_log=None
        )
    else:
        asyncio.run(polling(bot, dp))


if __name__ == "__main__":
    main()
