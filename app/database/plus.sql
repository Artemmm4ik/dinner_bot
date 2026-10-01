CREATE TABLE IF NOT EXISTS plus_orders (
    payload TEXT PRIMARY KEY, user_id BIGINT NOT NULL, price INTEGER NOT NULL CHECK(price>0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), accepted_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS plus_payments (
    charge_id TEXT PRIMARY KEY, payload TEXT NOT NULL REFERENCES plus_orders(payload),
    user_id BIGINT NOT NULL, price INTEGER NOT NULL, expires_at TIMESTAMPTZ NOT NULL,
    initial BOOLEAN NOT NULL, refunded BOOLEAN NOT NULL DEFAULT FALSE,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS plus_user_idx ON plus_payments(user_id, expires_at);
CREATE TABLE IF NOT EXISTS plus_refunds (
    charge_id TEXT PRIMARY KEY, user_id BIGINT NOT NULL, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS plus_trials (
    user_id BIGINT PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS meal_plans (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    body TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
    demo BOOLEAN NOT NULL DEFAULT FALSE, swaps INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS cart_sources (
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    source TEXT NOT NULL, PRIMARY KEY(user_id, source)
);
ALTER TABLE users ADD COLUMN IF NOT EXISTS prefs_json TEXT;
CREATE TABLE IF NOT EXISTS cooking_sessions (
    id TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    recipe_id TEXT NOT NULL, portions INTEGER NOT NULL, finished BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS search_budget(month TEXT PRIMARY KEY, amount INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS search_requests(id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL,created_at TIMESTAMPTZ DEFAULT now());
CREATE INDEX IF NOT EXISTS search_requests_user_time ON search_requests(user_id,created_at);
CREATE TABLE IF NOT EXISTS web_saved (
    id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    url TEXT NOT NULL, title TEXT NOT NULL, UNIQUE(user_id,url)
);
CREATE TABLE IF NOT EXISTS web_boards (
    id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    body TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE plus_orders ADD COLUMN IF NOT EXISTS checkout_id TEXT;
CREATE TABLE IF NOT EXISTS scraper_cache(key TEXT PRIMARY KEY,body TEXT NOT NULL,updated_at TIMESTAMPTZ DEFAULT now());
