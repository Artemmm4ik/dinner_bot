from datetime import datetime, timezone
from unittest.mock import AsyncMock
from aiogram import Bot
from aiogram.types import Update, Message, Chat, User, CallbackQuery
import pytest
from app.main import make_dispatcher
from app.database.repo import repo
from app.tg_bot.handlers import app as handlers
from app.services.planner import defaults

# The real aiogram router is instantiated once, as in the running application.
dp = make_dispatcher()


@pytest.fixture
def messages(monkeypatch):
    sent = []

    async def emit(self, text, **kwargs):
        sent.append((text, kwargs))
        return None

    monkeypatch.setattr(Message, "answer", emit)
    monkeypatch.setattr(CallbackQuery, "answer", AsyncMock())
    monkeypatch.setattr(
        repo, "get_user", AsyncMock(return_value={"last_tg_language": "uk"})
    )
    monkeypatch.setattr(repo, "create_user", AsyncMock())
    monkeypatch.setattr(repo, "update_user_language", AsyncMock())
    monkeypatch.setattr(repo, "clear_draft", AsyncMock())
    monkeypatch.setattr(repo, "save_draft", AsyncMock())
    monkeypatch.setattr(handlers, "profile", AsyncMock(return_value=defaults()))
    return sent


def callback(data):
    # Message is authored by the BOT (uk), click by a Russian-speaking user.
    return Update(
        update_id=1,
        callback_query=CallbackQuery(
            id="cb1",
            chat_instance="test",
            data=data,
            from_user=User(id=42, is_bot=False, first_name="U", language_code="ru"),
            message=Message(
                message_id=1,
                date=datetime.now(timezone.utc),
                chat=Chat(id=42, type="private"),
                from_user=User(
                    id=123, is_bot=True, first_name="Bot", language_code="uk"
                ),
            ),
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data,expected",
    [
        ("search_edit", "Напишите продукты"),
        ("search_correct", "Варианты на сегодня"),
        ("cancel", "Выберите действие"),
        ("prefs", "Сейчас"),
        ("missing_button", "кнопка устарела"),
        ("recipe:eggs_1:2", "Яичница"),
        ("web_search", "Напишите блюдо"),
    ],
)
async def test_real_callback_routing_and_user_language(data, expected, messages):
    bot = Bot("123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk")
    try:
        await dp.feed_update(bot, callback(data))
        assert any(expected in text for text, _ in messages)
        CallbackQuery.answer.assert_awaited()
    finally:
        await bot.session.close()


@pytest.mark.asyncio
async def test_favorite_menu_not_swallowed(messages, monkeypatch):
    monkeypatch.setattr(repo, "get_favorites", AsyncMock(return_value=["eggs_1"]))
    bot = Bot("123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk")
    try:
        await dp.feed_update(bot, callback("favs"))
        assert any("Ваши рецепты" in text for text, _ in messages)
    finally:
        await bot.session.close()


@pytest.mark.asyncio
async def test_direct_recipe_ingredients_button(messages, monkeypatch):
    monkeypatch.setattr(
        repo,
        "get_draft",
        AsyncMock(
            return_value={
                "token": "abc",
                "web": [
                    {
                        "title": "Суп",
                        "url": "https://shuba.life/recipes/123-soup",
                        "ingredients": ["300 г курицы"],
                    }
                ],
            }
        ),
    )
    bot = Bot("123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk")
    try:
        await dp.feed_update(bot, callback("web_read:abc:0"))
        assert any("300 г курицы" in text for text, _ in messages)
        assert any("https://shuba.life/" in text for text, _ in messages)
    finally:
        await bot.session.close()
