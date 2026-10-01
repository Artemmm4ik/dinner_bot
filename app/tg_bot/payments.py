import logging
from datetime import timezone
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, PreCheckoutQuery, LabeledPrice
from app.config import settings
from app.database import plus
from app.database.repo import repo
from app.tg_bot.ui import t, kb, home

router = Router()
logger = logging.getLogger(__name__)


async def show_plus(message, uid, lang):
    status = await plus.entitlement(uid)
    end = status["expires_at"] if status else None
    text = t(lang, "💎 Ужин Plus", "💎 Вечеря Plus") + "\n\n"
    text += t(
        lang,
        "Планы на 3, 5 и 7 ужинов. Режимы «Меньше разных продуктов» и «Больше разнообразия», замены блюд и общий список покупок.",
        "Плани на 3, 5 і 7 вечерь. Режими «Менше різних продуктів» та «Більше різноманіття», заміни страв і спільний список покупок.",
    )
    text += t(
        lang,
        "\n\nОбычный подбор рецептов, избранное и покупки остаются бесплатными.",
        "\n\nЗвичайний підбір рецептів, обране й покупки залишаються безкоштовними.",
    )
    rows = []
    if end:
        text += t(lang, "\n\nДоступ до ", "\n\nДоступ до ") + end.astimezone(
            timezone.utc
        ).strftime("%d.%m.%Y %H:%M UTC")
        rows.append(
            [
                (
                    t(lang, "Отключить автопродление", "Вимкнути автоподовження"),
                    "cancel_sub",
                )
            ]
        )
        text += t(
            lang,
            "\nСтатус автопродления также проверяйте в Telegram → Настройки → Мои звёзды.",
            "\nСтатус автоподовження також перевіряйте в Telegram → Налаштування → Мої зірки.",
        )
    else:
        text += t(
            lang,
            f"\n\n{settings.stars_price} ⭐ каждые 30 дней. Автопродление через Telegram; отключается в любой момент. Удаление бота его не отменяет.",
            f"\n\n{settings.stars_price} ⭐ кожні 30 днів. Автоподовження через Telegram; вимикається будь-коли. Видалення бота його не скасовує.",
        )
        if settings.payments_enabled:
            rows.append([(t(lang, "Условия и оплата", "Умови та оплата"), "buy_terms")])
        else:
            text += t(
                lang,
                "\nОплата ещё не включена владельцем.",
                "\nОплату ще не ввімкнув власник.",
            )
        rows.append(
            [
                (
                    t(
                        lang,
                        "Попробовать 3 ужина бесплатно",
                        "Спробувати 3 вечері безкоштовно",
                    ),
                    "demo",
                )
            ]
        )
    text += t(
        lang,
        "\n\nПоддержка и возврат: /paysupport. Условия: /terms.",
        "\n\nПідтримка та повернення: /paysupport. Умови: /terms.",
    )
    await message.answer(text, reply_markup=kb(*rows, home(lang)))


async def terms(message, lang):
    await message.answer(
        t(
            lang,
            f"Plus: {settings.stars_price} ⭐ за 30 дней с автопродлением. Доступ появляется после подтверждения Telegram. Нет гарантии экономии денег или медицинской точности. Планы сохраняются для чтения после окончания доступа. Пробный план бесплатен, доступен один раз и не оформляет подписку. Render Free может отвечать с задержкой после простоя. Отмена автопродления сохраняет оплаченный срок. Для возврата обратитесь в /paysupport; полный возврат отдельного списания отзывает выданный им доступ. Перед покупкой вы принимаете эти условия и /privacy.",
            f"Plus: {settings.stars_price} ⭐ за 30 днів з автоподовженням. Доступ з’являється після підтвердження Telegram. Немає гарантії економії грошей або медичної точності. Плани залишаються для читання після закінчення доступу. Пробний план безкоштовний, доступний один раз і не оформлює підписку. Render Free може відповідати із затримкою після простою. Скасування автоподовження зберігає оплачений термін. Для повернення зверніться до /paysupport; повне повернення окремого списання відкликає наданий ним доступ. Купуючи, ви приймаєте ці умови та /privacy.",
        )
    )


async def buy(message, uid, lang, bot):
    if not settings.payments_enabled or await plus.active(uid):
        return await show_plus(message, uid, lang)
    payload = await plus.new_order(uid, settings.stars_price)
    order = await repo._fetchone(
        "SELECT price FROM plus_orders WHERE payload=$1", payload
    )
    link = await bot.create_invoice_link(
        title=t(lang, "Ужин Plus · 30 дней", "Вечеря Plus · 30 днів"),
        description=t(
            lang,
            "Планы ужинов, замены и список покупок. Автопродление каждые 30 дней.",
            "Плани вечерь, заміни та список покупок. Автоподовження кожні 30 днів.",
        ),
        payload=payload,
        currency="XTR",
        prices=[LabeledPrice(label="Plus", amount=order["price"])],
        subscription_period=plus.PERIOD,
        provider_token="",
    )
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    await message.answer(
        t(
            lang,
            "Счёт только для вашего аккаунта, действует 1 час. Цена указана в форме Telegram. Если платёж не завершён, новый счёт можно получить через час.",
            "Рахунок лише для вашого акаунта, діє 1 годину. Ціна вказана у формі Telegram. Якщо платіж не завершено, новий рахунок можна отримати за годину.",
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t(
                            lang,
                            "Оплатить в Telegram Stars",
                            "Сплатити в Telegram Stars",
                        ),
                        url=link,
                    )
                ]
            ]
        ),
    )


@router.pre_checkout_query()
async def checkout(q: PreCheckoutQuery):
    # No language/profile DB middleware: Telegram requires a response within 10 seconds.
    import asyncio
    from app.locales.manager import detect_language

    lang = detect_language(q.from_user.language_code)
    ok = False
    try:
        async with asyncio.timeout(6):
            ok = settings.payments_enabled and await plus.approve_checkout(q)
    except Exception:
        logger.exception("Pre-checkout failed")
    await q.answer(
        ok=ok,
        error_message=None
        if ok
        else t(
            lang,
            "Счёт устарел, уже использован или сервис временно недоступен. Деньги не списаны. Откройте /plus позже.",
            "Рахунок застарів, уже використаний або сервіс тимчасово недоступний. Гроші не списано. Відкрийте /plus пізніше.",
        ),
    )


@router.message(F.successful_payment)
async def success(message: Message, lang: str):
    await plus.record_payment(message.from_user.id, message.successful_payment)
    await message.answer(
        t(
            lang,
            "✅ Платёж сохранён. Статус доступа: /plus.",
            "✅ Платіж збережено. Статус доступу: /plus.",
        )
    )


@router.message(F.refunded_payment)
async def refunded(message: Message, lang: str):
    await plus.refund_record(
        message.from_user.id, message.refunded_payment.telegram_payment_charge_id
    )
    await message.answer(
        t(
            lang,
            "Возврат сохранён. Доступ пересчитан по оставшимся оплатам. /plus",
            "Повернення збережено. Доступ перераховано за рештою оплат. /plus",
        )
    )


@router.message(Command("paysupport", "support"))
async def support(message: Message, lang: str):
    rows = await repo._fetchall(
        "SELECT charge_id,price,created_at,refunded FROM plus_payments WHERE user_id=$1 ORDER BY created_at DESC LIMIT 5",
        message.from_user.id,
    )
    contact = settings.support_contact or t(
        lang,
        "Контакт владельца ещё не настроен.",
        "Контакт власника ще не налаштовано.",
    )
    lines = [
        t(lang, "Поддержка и возврат: ", "Підтримка та повернення: ") + contact,
        t(lang, "Ваш Telegram ID: ", "Ваш Telegram ID: ") + str(message.from_user.id),
    ]
    for r in rows:
        lines.append(
            f"{r['created_at']:%d.%m.%Y} · {r['price']} ⭐ · {r['charge_id']}"
            + (" ↩" if r["refunded"] else "")
        )
    await message.answer("\n".join(lines))


@router.message(Command("refund"))
async def admin_refund(message: Message, lang: str):
    if message.from_user.id not in settings.admin_ids:
        return
    parts = (message.text or "").split()
    if len(parts) != 3 or not parts[1].isdigit():
        return await message.answer("/refund USER_ID TELEGRAM_PAYMENT_CHARGE_ID")
    uid, charge = int(parts[1]), parts[2]
    row = await repo._fetchone(
        "SELECT * FROM plus_payments WHERE user_id=$1 AND charge_id=$2", uid, charge
    )
    if not row:
        return await message.answer("Payment not found")
    # Explicit second click, with server-side admin/owner recheck in the callback.
    import secrets

    token = secrets.token_hex(8)
    await repo.save_draft(message.from_user.id, {"refund": [uid, charge, token]})
    await message.answer(
        f"Refund {row['price']} Stars to {uid}?",
        reply_markup=kb([("Confirm refund", f"refund:{token}")]),
    )


async def cancel(uid, bot):
    for row in await plus.subscriptions(uid):
        await bot.edit_user_star_subscription(
            user_id=uid, telegram_payment_charge_id=row["charge_id"], is_canceled=True
        )
        await repo._execute(
            "UPDATE plus_payments SET cancel_requested=TRUE WHERE charge_id=$1",
            row["charge_id"],
        )
