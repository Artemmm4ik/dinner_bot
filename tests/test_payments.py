from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from aiogram.types import SuccessfulPayment
from app.database.plus import validate_payment, record_payment
from app.database import plus
from app.tg_bot import payments


def payment(**kwargs):
    args = dict(
        currency="XTR",
        total_amount=149,
        invoice_payload="dinner:test",
        telegram_payment_charge_id="charge1",
        provider_payment_charge_id="",
        subscription_expiration_date=int(
            (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
        ),
        is_recurring=True,
        is_first_recurring=True,
    )
    args.update(kwargs)
    return SuccessfulPayment(**args)


def test_subscription_dates_from_telegram():
    p = payment()
    assert validate_payment(
        p, {"user_id": 1, "price": 149}, 1
    ) == datetime.fromtimestamp(p.subscription_expiration_date, timezone.utc)


@pytest.mark.parametrize(
    "change",
    [
        {"currency": "USD"},
        {"total_amount": 1},
        {"is_recurring": False},
        {"subscription_expiration_date": None},
    ],
)
def test_tampered_payment_rejected(change):
    with pytest.raises(ValueError):
        validate_payment(payment(**change), {"user_id": 1, "price": 149}, 1)


def test_wrong_owner_rejected():
    with pytest.raises(ValueError):
        validate_payment(payment(), {"user_id": 2, "price": 149}, 1)


class Context:
    def __init__(self, obj):
        self.obj = obj

    async def __aenter__(self):
        return self.obj

    async def __aexit__(self, *args):
        pass


class Ledger:
    def __init__(self):
        self.rows = {}

    def transaction(self):
        return Context(self)

    async def fetchrow(self, *args):
        return {"user_id": 1, "price": 149}

    async def fetchval(self, *args):
        return False

    async def execute(self, sql, *params):
        if "pg_advisory_xact_lock" in sql:
            return "SELECT 1"
        assert "ON CONFLICT(charge_id) DO NOTHING" in sql
        charge = params[0]
        if charge in self.rows:
            return "INSERT 0 0"
        self.rows[charge] = params
        return "INSERT 0 1"


@pytest.mark.asyncio
async def test_payment_replay_is_noop(monkeypatch):
    ledger = Ledger()
    monkeypatch.setattr(
        plus,
        "get_db_pool",
        AsyncMock(return_value=SimpleNamespace(acquire=lambda: Context(ledger))),
    )
    assert await record_payment(1, payment()) is True
    assert await record_payment(1, payment()) is False
    assert len(ledger.rows) == 1


@pytest.mark.asyncio
async def test_checkout_db_error_returns_negative_answer(monkeypatch):
    monkeypatch.setattr(payments.settings, "payments_enabled", True)
    monkeypatch.setattr(
        plus,
        "approve_checkout",
        AsyncMock(side_effect=RuntimeError("database offline")),
    )
    q = SimpleNamespace(
        from_user=SimpleNamespace(language_code="ru"), answer=AsyncMock()
    )
    await payments.checkout(q)
    assert q.answer.call_args.kwargs["ok"] is False


@pytest.mark.asyncio
async def test_subscription_cancel_uses_initial_charge(monkeypatch):
    monkeypatch.setattr(
        plus, "subscriptions", AsyncMock(return_value=[{"charge_id": "initial"}])
    )
    monkeypatch.setattr(payments.repo, "_execute", AsyncMock())
    bot = SimpleNamespace(edit_user_star_subscription=AsyncMock())
    await payments.cancel(42, bot)
    bot.edit_user_star_subscription.assert_awaited_once_with(
        user_id=42, telegram_payment_charge_id="initial", is_canceled=True
    )


@pytest.mark.asyncio
async def test_invoice_is_stars_recurring_and_has_single_price(monkeypatch):
    monkeypatch.setattr(payments.settings, "payments_enabled", True)
    monkeypatch.setattr(plus, "active", AsyncMock(return_value=False))
    monkeypatch.setattr(plus, "new_order", AsyncMock(return_value="dinner:test"))
    monkeypatch.setattr(
        payments.repo, "_fetchone", AsyncMock(return_value={"price": 149})
    )
    bot = SimpleNamespace(
        create_invoice_link=AsyncMock(return_value="https://t.me/$test")
    )
    msg = SimpleNamespace(answer=AsyncMock())
    await payments.buy(msg, 42, "ru", bot)
    args = bot.create_invoice_link.call_args.kwargs
    assert args["currency"] == "XTR" and args["subscription_period"] == 2592000
    assert args["provider_token"] == "" and len(args["prices"]) == 1
    assert args["prices"][0].amount == 149
