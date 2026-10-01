from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from aiohttp.test_utils import TestClient, TestServer
from app.main import web_app
from app.config import settings
from app.database.repo import repo


@pytest.mark.asyncio
async def test_webhook_secret_dedupe_and_retry(monkeypatch):
    monkeypatch.setattr(settings, "webhook_secret", "secret_for_test")
    dp = SimpleNamespace(feed_update=AsyncMock())
    monkeypatch.setattr(repo, "is_update_processed", AsyncMock(return_value=False))
    monkeypatch.setattr(repo, "mark_update_processed", AsyncMock())
    app = web_app(None, dp)
    app.on_startup.clear()
    app.on_cleanup.clear()
    async with TestClient(TestServer(app)) as client:
        response = await client.post("/telegram", json={"update_id": 1})
        assert response.status == 403
        dp.feed_update.assert_not_awaited()
        headers = {"X-Telegram-Bot-Api-Secret-Token": "secret_for_test"}
        response = await client.post(
            "/telegram", json={"update_id": 1}, headers=headers
        )
        assert response.status == 200
        repo.mark_update_processed.assert_awaited_once_with(1)
        monkeypatch.setattr(repo, "is_update_processed", AsyncMock(return_value=True))
        response = await client.post(
            "/telegram", json={"update_id": 1}, headers=headers
        )
        assert response.status == 200 and dp.feed_update.await_count == 1
        monkeypatch.setattr(repo, "is_update_processed", AsyncMock(return_value=False))
        dp.feed_update.side_effect = RuntimeError("DB offline")
        response = await client.post(
            "/telegram", json={"update_id": 2}, headers=headers
        )
        assert response.status == 503
        assert repo.mark_update_processed.await_count == 1
