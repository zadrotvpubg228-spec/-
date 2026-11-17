import time
import aiosqlite
from config import START_BALANCE

DB_NAME = "game_bot.db"


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                balance INTEGER DEFAULT 0,
                bonus_income INTEGER DEFAULT 0,
                custom_title TEXT DEFAULT 'Новичок',
                last_collect REAL,
                last_farm REAL DEFAULT 0,
                is_banned INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_cars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                income INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_businesses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                income INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                description TEXT,
                income_bonus INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                reward_type TEXT,
                reward_name TEXT,
                reward_value INTEGER,
                description TEXT,
                max_uses INTEGER,
                used_count INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_activations (
                user_id INTEGER,
                code TEXT,
                PRIMARY KEY (user_id, code)
            )
        """)
        await db.commit()


async def register_or_update_user(user_id: int, username: str | None, full_name: str):
    clean_username = username.lower() if username else ""
    now = time.time()
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row is None:
            await db.execute(
                """
                INSERT INTO users (user_id, username, full_name, balance, last_collect)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, clean_username, full_name, START_BALANCE, now),
            )
        else:
            await db.execute(
                "UPDATE users SET username = ?, full_name = ? WHERE user_id = ?",
                (clean_username, full_name, user_id),
            )
        await db.commit()


async def get_user(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return await cursor.fetchone()


async def find_user(query: str):
    clean = query.strip().lstrip("@").lower()
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        if clean.isdigit():
            cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (int(clean),))
        else:
            cursor = await db.execute("SELECT * FROM users WHERE username = ?", (clean,))
        return await cursor.fetchone()


async def get_user_income_and_counts(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("SELECT bonus_income FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        base_bonus = row[0] if row else 0

        cur = await db.execute(
            "SELECT COUNT(*), COALESCE(SUM(income), 0) FROM user_cars WHERE user_id = ?",
            (user_id,),
        )
        cars_count, cars_income = await cur.fetchone()

        cur = await db.execute(
            "SELECT COUNT(*), COALESCE(SUM(income), 0) FROM user_businesses WHERE user_id = ?",
            (user_id,),
        )
        biz_count, biz_income = await cur.fetchone()

        cur = await db.execute(
            "SELECT COUNT(*), COALESCE(SUM(income_bonus), 0) FROM user_items WHERE user_id = ?",
            (user_id,),
        )
        items_count, items_income = await cur.fetchone()

        total_income = base_bonus + cars_income + biz_income + items_income
        return {
            "total_income": total_income,
            "cars_count": cars_count,
            "cars_income": cars_income,
            "biz_count": biz_count,
            "biz_income": biz_income,
            "items_count": items_count,
            "items_income": items_income,
        }


async def change_balance(user_id: int, delta: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET balance = MAX(0, balance + ?) WHERE user_id = ?",
            (delta, user_id),
        )
        await db.commit()


async def collect_passive_income(user_id: int):
    user = await get_user(user_id)
    if not user:
        return 0, 0
    stats = await get_user_income_and_counts(user_id)
    total_income = stats["total_income"]
    if total_income <= 0:
        return 0, 0

    now = time.time()
    last_collect = user["last_collect"] or now
    elapsed_hours = max(0.0, (now - last_collect) / 3600.0)
    earned = int(elapsed_hours * total_income)

    if earned >= 1:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "UPDATE users SET balance = balance + ?, last_collect = ? WHERE user_id = ?",
                (earned, now, user_id),
            )
            await db.commit()
    return earned, total_income


async def add_car(user_id: int, name: str, income: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO user_cars (user_id, name, income) VALUES (?, ?, ?)",
            (user_id, name, income),
        )
        await db.commit()


async def add_business(user_id: int, name: str, income: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO user_businesses (user_id, name, income) VALUES (?, ?, ?)",
            (user_id, name, income),
        )
        await db.commit()


async def add_custom_item(user_id: int, name: str, description: str, income_bonus: int = 0):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            INSERT INTO user_items (user_id, name, description, income_bonus)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, name, description, income_bonus),
        )
        await db.commit()


async def get_user_assets(user_id: int, table: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(f"SELECT * FROM {table} WHERE user_id = ?", (user_id,))
        return await cursor.fetchall()


async def update_user_field(user_id: int, field: str, value):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
        await db.commit()


async def get_top_balance(limit: int = 10):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT user_id, full_name, custom_title, balance
            FROM users WHERE is_banned = 0
            ORDER BY balance DESC LIMIT ?
            """,
            (limit,),
        )
        return await cursor.fetchall()


async def get_top_income(limit: int = 10):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT u.user_id, u.full_name, u.custom_title,
                   (u.bonus_income
                    + COALESCE((SELECT SUM(income) FROM user_cars WHERE user_id = u.user_id), 0)
                    + COALESCE((SELECT SUM(income) FROM user_businesses WHERE user_id = u.user_id), 0)
                    + COALESCE((SELECT SUM(income_bonus) FROM user_items WHERE user_id = u.user_id), 0)
                   ) AS total_inc
            FROM users u
            WHERE u.is_banned = 0
            ORDER BY total_inc DESC LIMIT ?
            """,
            (limit,),
        )
        return await cursor.fetchall()


async def create_promocode(
    code: str,
    reward_type: str,
    reward_name: str,
    reward_value: int,
    description: str,
    max_uses: int,
):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO promocodes
            (code, reward_type, reward_name, reward_value, description, max_uses, used_count, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 0, 1)
            """,
            (code.upper(), reward_type, reward_name, reward_value, description, max_uses),
        )
        await db.commit()


async def get_all_promocodes():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM promocodes ORDER BY rowid DESC")
        return await cur.fetchall()


async def get_promocode(code: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM promocodes WHERE code = ?", (code.upper(),))
        return await cur.fetchone()


async def set_promo_limit(code: str, new_max_uses: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE promocodes SET max_uses = ? WHERE code = ?",
            (new_max_uses, code.upper()),
        )
        await db.commit()


async def add_promo_limit(code: str, extra: int):
    promo = await get_promocode(code)
    if not promo or promo["max_uses"] == -1:
        return
    new_val = max(promo["used_count"], promo["max_uses"] + extra)
    await set_promo_limit(code, new_val)


async def toggle_promo_status(code: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE promocodes SET is_active = 1 - is_active WHERE code = ?",
            (code.upper(),),
        )
        await db.commit()


async def delete_promocode(code: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM promocodes WHERE code = ?", (code.upper(),))
        await db.execute("DELETE FROM promo_activations WHERE code = ?", (code.upper(),))
        await db.commit()


async def redeem_promocode(user_id: int, code: str):
    code = code.strip().upper()
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM promocodes WHERE code = ?", (code,))
        promo = await cur.fetchone()

        if not promo:
            return False, "❌ Промокод не найден."
        if promo["is_active"] == 0:
            return False, "⏸ Этот промокод временно отключён."
        if promo["max_uses"] != -1 and promo["used_count"] >= promo["max_uses"]:
            return False, "❌ Лимит активаций этого промокода исчерпан."

        cur = await db.execute(
            "SELECT 1 FROM promo_activations WHERE user_id = ? AND code = ?",
            (user_id, code),
        )
        if await cur.fetchone():
            return False, "⚠️ Ты уже активировал этот промокод."

        await db.execute(
            "INSERT INTO promo_activations (user_id, code) VALUES (?, ?)", (user_id, code)
        )
        await db.execute(
            "UPDATE promocodes SET used_count = used_count + 1 WHERE code = ?", (code,)
        )
        await db.commit()

    r_type = promo["reward_type"]
    r_name = promo["reward_name"]
    r_val = promo["reward_value"]
    r_desc = promo["description"]

    if r_type == "stars":
        await change_balance(user_id, r_val)
        return True, f"🎉 Промокод активирован! Получено <b>+{r_val:,} ⭐</b>"
    elif r_type == "car":
        await add_car(user_id, r_name, r_val)
        return True, f"🎉 Промокод активирован! Получена машина: <b>{r_name}</b> (+{r_val:,} ⭐/ч)"
    elif r_type == "biz":
        await add_business(user_id, r_name, r_val)
        return True, f"🎉 Промокод активирован! Получен бизнес: <b>{r_name}</b> (+{r_val:,} ⭐/ч)"
    elif r_type == "item":
        await add_custom_item(user_id, r_name, r_desc, r_val)
        return True, f"🎉 Промокод активирован! Получена прелесть: <b>{r_name}</b> (+{r_val:,} ⭐/ч)"
    elif r_type == "title":
        await update_user_field(user_id, "custom_title", r_name)
        return True, f"🎉 Промокод активирован! Установлен титул: <b>{r_name}</b>"

    return False, "Ошибка типа награды."


async def get_global_stats():
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("SELECT COUNT(*), COALESCE(SUM(balance), 0) FROM users")
        users_cnt, total_bal = await cur.fetchone()
        cur = await db.execute("SELECT COUNT(*) FROM user_cars")
        cars_cnt = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM user_businesses")
        biz_cnt = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM promocodes")
        promo_cnt = (await cur.fetchone())[0]
        cur = await db.execute("SELECT user_id FROM users WHERE is_banned = 0")
        all_ids = [r[0] for r in await cur.fetchall()]
        return users_cnt, total_bal, cars_cnt, biz_cnt, promo_cnt, all_ids
