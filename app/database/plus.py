"""Financial ledger: unique charges, server-side ownership, transactional writes."""

import json
import secrets
from datetime import datetime, timezone
from app.database.core import get_db_pool
from app.database.repo import repo

PERIOD = 2592000


def validate_payment(payment, order, uid):
    if not order or order["user_id"] != uid:
        raise ValueError("Unknown order or owner mismatch")
    if payment.currency != "XTR" or payment.total_amount != order["price"]:
        raise ValueError("Currency or amount mismatch")
    expiry = payment.subscription_expiration_date
    if not expiry or not payment.is_recurring:
        raise ValueError("Expected a recurring subscription payment")
    return (
        expiry
        if isinstance(expiry, datetime)
        else datetime.fromtimestamp(expiry, timezone.utc)
    )


async def entitlement(uid):
    return await repo._fetchone(
        """SELECT max(expires_at) AS expires_at FROM plus_payments
        WHERE user_id=$1 AND NOT refunded AND expires_at>now()""",
        uid,
    )


async def active(uid):
    row = await entitlement(uid)
    return bool(row and row["expires_at"])


async def new_order(uid, price):
    # Retain and reuse a recent order: repeated clicks must not create independent subscriptions.
    pool = await get_db_pool()
    async with pool.acquire() as c, c.transaction():
        await c.execute("SELECT pg_advisory_xact_lock($1)", uid)
        row = await c.fetchrow(
            """SELECT payload FROM plus_orders WHERE user_id=$1
            AND created_at>now()-interval '1 hour' ORDER BY created_at DESC LIMIT 1""",
            uid,
        )
        if row:
            return row["payload"]
        payload = "dinner:" + secrets.token_urlsafe(18)
        await c.execute(
            "INSERT INTO plus_orders(payload,user_id,price) VALUES($1,$2,$3)",
            payload,
            uid,
            price,
        )
        return payload


async def approve_checkout(q):
    pool = await get_db_pool()
    async with pool.acquire() as c, c.transaction():
        await c.execute("SELECT pg_advisory_xact_lock($1)", q.from_user.id)
        row = await c.fetchrow(
            "SELECT * FROM plus_orders WHERE payload=$1 FOR UPDATE", q.invoice_payload
        )
        if (
            not row
            or row["user_id"] != q.from_user.id
            or q.currency != "XTR"
            or q.total_amount != row["price"]
        ):
            return False
        if (datetime.now(timezone.utc) - row["created_at"]).total_seconds() > 3600:
            return False
        paid = await c.fetchval(
            "SELECT EXISTS(SELECT 1 FROM plus_payments WHERE user_id=$1 AND NOT refunded AND expires_at>now())",
            q.from_user.id,
        )
        if row["accepted_at"]:
            return row["checkout_id"] == q.id
        if paid:
            return False
        await c.execute(
            "UPDATE plus_orders SET accepted_at=now(),checkout_id=$2 WHERE payload=$1",
            q.invoice_payload,
            q.id,
        )
        return True


async def record_payment(uid, payment):
    pool = await get_db_pool()
    async with pool.acquire() as c, c.transaction():
        await c.execute("SELECT pg_advisory_xact_lock($1)", uid)
        order = await c.fetchrow(
            "SELECT * FROM plus_orders WHERE payload=$1", payment.invoice_payload
        )
        expiry = validate_payment(payment, order, uid)
        refunded = await c.fetchval(
            "SELECT EXISTS(SELECT 1 FROM plus_refunds WHERE charge_id=$1 AND user_id=$2)",
            payment.telegram_payment_charge_id,
            uid,
        )
        result = await c.execute(
            """INSERT INTO plus_payments(charge_id,payload,user_id,price,expires_at,initial,refunded)
            VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT(charge_id) DO NOTHING""",
            payment.telegram_payment_charge_id,
            payment.invoice_payload,
            uid,
            payment.total_amount,
            expiry,
            bool(payment.is_first_recurring),
            refunded,
        )
        return result == "INSERT 0 1"


async def refund_record(uid, charge):
    pool = await get_db_pool()
    async with pool.acquire() as c, c.transaction():
        await c.execute("SELECT pg_advisory_xact_lock($1)", uid)
        await c.execute(
            "INSERT INTO plus_refunds(charge_id,user_id) VALUES($1,$2) ON CONFLICT DO NOTHING",
            charge,
            uid,
        )
        await c.execute(
            "UPDATE plus_payments SET refunded=TRUE WHERE charge_id=$1 AND user_id=$2",
            charge,
            uid,
        )


async def subscriptions(uid):
    return await repo._fetchall(
        """SELECT DISTINCT ON (p.payload) p.* FROM plus_payments p
        WHERE p.user_id=$1 AND p.initial
        AND EXISTS(SELECT 1 FROM plus_payments x WHERE x.payload=p.payload AND x.expires_at>now())
        ORDER BY p.payload,p.created_at""",
        uid,
    )


async def create_plan(uid, body, demo=False):
    pool = await get_db_pool()
    async with pool.acquire() as c, c.transaction():
        await c.execute("SELECT pg_advisory_xact_lock($1)", uid)
        if demo:
            r = await c.fetchval(
                "INSERT INTO plus_trials(user_id) VALUES($1) ON CONFLICT DO NOTHING RETURNING user_id",
                uid,
            )
            if not r:
                return None
        elif not await c.fetchval(
            "SELECT EXISTS(SELECT 1 FROM plus_payments WHERE user_id=$1 AND NOT refunded AND expires_at>now())",
            uid,
        ):
            return None
        return await c.fetchval(
            "INSERT INTO meal_plans(user_id,body,demo) VALUES($1,$2,$3) RETURNING id",
            uid,
            json.dumps(body, ensure_ascii=False),
            demo,
        )


async def plan(uid, pid):
    row = await repo._fetchone(
        "SELECT * FROM meal_plans WHERE id=$1 AND user_id=$2", pid, uid
    )
    if row:
        row["body"] = json.loads(row["body"])
    return row


async def update_plan(uid, pid, revision, body, swap=False):
    # Compare-and-swap prevents stale keyboards from overwriting a newer plan.
    return await repo._fetchone(
        """UPDATE meal_plans SET body=$1,revision=revision+1,swaps=swaps+$2
        WHERE id=$3 AND user_id=$4 AND revision=$5
        AND (EXISTS(SELECT 1 FROM plus_payments WHERE user_id=$4 AND NOT refunded AND expires_at>now())
             OR (demo AND swaps<2)) RETURNING id""",
        json.dumps(body, ensure_ascii=False),
        int(swap),
        pid,
        uid,
        revision,
    )


async def add_cart(uid, source, items):
    pool = await get_db_pool()
    async with pool.acquire() as c, c.transaction():
        await c.execute("SELECT pg_advisory_xact_lock($1)", uid)
        inserted = await c.fetchval(
            "INSERT INTO cart_sources(user_id,source) VALUES($1,$2) ON CONFLICT DO NOTHING RETURNING source",
            uid,
            source,
        )
        if not inserted:
            return False
        for item in items:
            row = await c.fetchrow(
                "SELECT id FROM shopping_list WHERE user_id=$1 AND ingredient_id=$2 AND unit=$3 AND NOT is_bought LIMIT 1 FOR UPDATE",
                uid,
                item["id"],
                item["unit"],
            )
            if row:
                await c.execute(
                    "UPDATE shopping_list SET amount=amount+$1 WHERE id=$2",
                    item["amount"],
                    row["id"],
                )
            else:
                await c.execute(
                    "INSERT INTO shopping_list(user_id,ingredient_id,ingredient_name,amount,unit) VALUES($1,$2,$3,$4,$5)",
                    uid,
                    item["id"],
                    item["name_ru"],
                    item["amount"],
                    item["unit"],
                )
        return True
