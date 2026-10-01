import asyncio
import aiosqlite
import asyncpg
import os


async def migrate(sqlite_path: str, pg_url: str):
    if not os.path.exists(sqlite_path):
        print(f"SQLite DB {sqlite_path} does not exist.")
        return

    print("Connecting to PostgreSQL...")
    # Setup PG connection
    pool = await asyncpg.create_pool(pg_url)

    print("Connecting to SQLite...")
    async with aiosqlite.connect(sqlite_path) as sl_db, pool.acquire() as pg_conn:
        sl_db.row_factory = aiosqlite.Row

        # 1. Migrate users
        print("Migrating users...")
        async with sl_db.execute("SELECT * FROM users") as cursor:
            async for row in cursor:
                await pg_conn.execute(
                    """
                    INSERT INTO users (user_id, language_mode, manual_language, last_tg_language, portions, max_time, equipment, excluded_ingredients, allergens, vegetarian, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (user_id) DO NOTHING
                """,
                    row["user_id"],
                    row["language_mode"],
                    row["manual_language"],
                    row["last_tg_language"],
                    row["portions"],
                    row["max_time"],
                    row["equipment"],
                    row["excluded_ingredients"],
                    row["allergens"],
                    bool(row["vegetarian"]),
                    row["created_at"],
                )

        # 2. Migrate shopping_list
        print("Migrating shopping_list...")
        async with sl_db.execute("SELECT * FROM shopping_list") as cursor:
            async for row in cursor:
                # We don't preserve ID from sqlite to avoid sequence issues, unless needed.
                # Actually, let's just insert without ID and let sequence handle it.
                # Wait, if we run it multiple times it might duplicate. Let's just do simple insert for now.
                # A safer approach for idempotency on shopping list:
                # We can just ignore idempotency here and assume the user runs this once.
                await pg_conn.execute(
                    """
                    INSERT INTO shopping_list (user_id, ingredient_id, ingredient_name, amount, unit, is_bought)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """,
                    row["user_id"],
                    row["ingredient_id"],
                    row["ingredient_name"],
                    row["amount"],
                    row["unit"],
                    bool(row["is_bought"]),
                )

        # 3. Migrate favorites
        print("Migrating favorites...")
        async with sl_db.execute("SELECT * FROM favorites") as cursor:
            async for row in cursor:
                await pg_conn.execute(
                    """
                    INSERT INTO favorites (user_id, recipe_id) VALUES ($1, $2)
                    ON CONFLICT ON CONSTRAINT favorites_pkey DO NOTHING
                """,
                    row["user_id"],
                    row["recipe_id"],
                )

        # 4. Migrate history
        print("Migrating history...")
        async with sl_db.execute("SELECT * FROM history") as cursor:
            async for row in cursor:
                await pg_conn.execute(
                    """
                    INSERT INTO history (user_id, recipe_id, portions, rating, created_at)
                    VALUES ($1, $2, $3, $4, $5)
                """,
                    row["user_id"],
                    row["recipe_id"],
                    row["portions"],
                    row["rating"],
                    row["created_at"],
                )

        # 5. Migrate draft_state
        print("Migrating draft_state...")
        async with sl_db.execute("SELECT * FROM draft_state") as cursor:
            async for row in cursor:
                await pg_conn.execute(
                    """
                    INSERT INTO draft_state (user_id, state_data) VALUES ($1, $2)
                    ON CONFLICT (user_id) DO UPDATE SET state_data = $2
                """,
                    row["user_id"],
                    row["state_data"],
                )

        # 6. Migrate analytics
        print("Migrating analytics...")
        async with sl_db.execute("SELECT * FROM analytics") as cursor:
            async for row in cursor:
                await pg_conn.execute(
                    """
                    INSERT INTO analytics (user_id, event_name, event_data, created_at)
                    VALUES ($1, $2, $3, $4)
                """,
                    row["user_id"],
                    row["event_name"],
                    row["event_data"],
                    row["created_at"],
                )

    print("Migration finished successfully!")
    await pool.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python migrate_sqlite_to_pg.py <sqlite_db_path> <postgres_url>")
        sys.exit(1)

    asyncio.run(migrate(sys.argv[1], sys.argv[2]))
