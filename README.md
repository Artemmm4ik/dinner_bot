# Що на вечерю? (dinner_bot)

Telegram-бот для вибору повсякденної їжі. 
**Архітектура (Безкоштовна версія):** Render Free Web Service + Telegram webhook + Neon Free PostgreSQL.

## 🚀 Локальний запуск (Polling або Webhook)

1. **Встановіть залежності:** `pip install -r requirements.txt`
2. **Налаштуйте PostgreSQL:** Вам знадобиться доступна база PostgreSQL (локально або Neon).
3. **Заповніть конфігурацію `.env`:**
   ```env
   BOT_TOKEN=your_token
   DATABASE_URL=postgresql://user:password@host/dbname
   # Для локального тестування краще використовувати polling:
   BOT_MODE=polling
   ```
4. **Запустіть бота:** `python -m app.main`

## ☁️ Розміщення на Render Free + Neon

Платформа Render пропонує **Free Web Service**, який може засинати через 15 хвилин бездіяльності. База даних буде розміщена на **Neon (Free)**, що забезпечить надійне збереження даних незалежно від перезапусків або зупинок Render.

### Покрокова інструкція:

1. **Створіть Neon Free PostgreSQL:**
   - Зареєструйтесь на [Neon.tech](https://neon.tech/).
   - Створіть новий проєкт і базу даних (Postgres).
   - Скопіюйте рядок підключення (`Connection string`), який виглядає як `postgresql://user:password@ep-...neon.tech/dbname?sslmode=require`.

2. **Завантажте проєкт у свій GitHub репозиторій.**

3. **Створіть Render Free Web Service:**
   - Зареєструйтесь на [Render.com](https://render.com/).
   - Створіть **New ➔ Blueprint**, вкажіть ваш репозиторій з файлом `render.yaml`.
   - Render підхопить налаштування:
     - Тип: **Web Service**
     - План: **Free**
     - Health Check: `/healthz`
   - Render попросить вас заповнити змінні оточення (Environment Variables).

4. **Заповніть змінні в Render:**
   - `BOT_TOKEN` — ваш токен Telegram.
   - `DATABASE_URL` — вставте рядок з Neon (з кроку 1).
   - `ADMIN_IDS` — ваш Telegram ID (або кілька через кому).
   - `WEBHOOK_BASE_URL` — вставте URL вашого сервісу на Render (наприклад, `https://dinner-bot-abc1.onrender.com`). URL можна побачити після створення сервісу.
   - `WEBHOOK_SECRET` — вигадайте випадковий складний рядок (пароль для webhook), наприклад, `MySecretWebhookToken123`.

5. **Збережіть та дочекайтесь Deploy.**
   Під час першого старту сервіс автоматично підключиться до Neon, створить таблиці та зареєструє webhook у Telegram.

### 📦 Міграція з SQLite на Neon PostgreSQL

Якщо ви раніше використовували локальну базу SQLite (`dinner_bot.sqlite3`), перенесіть дані на Neon перед запуском. Зі свого локального ПК (на якому лежить файл `.sqlite3`), виконайте:

```bash
export PYTHONPATH=.
python scripts/migrate_sqlite_to_pg.py data/dinner_bot.sqlite3 "ваша_url_бази_neon"
```

## ⚠️ Обмеження Free версії

- **Сон через 15 хвилин:** На тарифі Render Free ваш сервіс буде засинати, якщо немає запитів. Коли користувач надішле повідомлення сплячому боту, Telegram відправить запит на Render. Пробудження може займати 30-60 секунд. 
- Telegram повторюватиме відправку запиту (Webhook), поки бот не прокинеться. Впроваджено перевірку дублікатів (Idempotency), щоб одне повідомлення не оброблялося двічі.
- **Підписки/платежі:** Наразі платежі зі сплячого стану можуть працювати із затримкою, обробка `pre_checkout_query` вимагає миттєвої відповіді. Рекомендуємо тимчасово тестувати оплати, коли бот активний. `PAYMENTS_ENABLED` встановлено у `False` за замовчуванням.
- **Neon Limit:** Безкоштовний тариф Neon має обмеження за обсягом сховища та кількістю обчислень. Для звичайного бота цього достатньо на кілька тижнів/місяців роботи.
