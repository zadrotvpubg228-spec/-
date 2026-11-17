import asyncio
import html
import random
import time

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from config import ADMIN_ID, DB_PATH
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from admin import admin_router
from config import (
    ADMIN_IDS,
    BIZ_CATALOG,
    BOT_TOKEN,
    CARS_CATALOG,
    CASES_CATALOG,
    FARM_COOLDOWN,
    FARM_REWARD,
)
ADMIN_IDS = 8526008350
ADMIN_ID = ADMIN_IDS
import database as db

user_router = Router()


class UserStates(StatesGroup):
    waiting_promo = State()


# Квадратное меню в 2 колонки — Страница 1
def menu_page_1_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="💵 Собрать прибыль")],
            [KeyboardButton(text="💰 Работа (100 ⭐)"), KeyboardButton(text="📦 Кейсы")],
            [KeyboardButton(text="🏎 Автосалон"), KeyboardButton(text="🏢 Бизнесы")],
            [KeyboardButton(text="🏆 Топы"), KeyboardButton(text="➡️ Страница 2")],
        ],
        resize_keyboard=True,
    )


# Квадратное меню в 2 колонки — Страница 2
def menu_page_2_kb(user_id: int) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="✨ Мои прелести"), KeyboardButton(text="🎟 Промокод")],
        [KeyboardButton(text="🏎 Мой гараж"), KeyboardButton(text="🏢 Мои бизнесы")],
    ]
    if user_id in ADMIN_IDS:
        rows.append([KeyboardButton(text="👑 Админ-панель"), KeyboardButton(text="⬅️ Страница 1")])
    else:
        rows.append([KeyboardButton(text="⬅️ Страница 1")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


async def ensure_active_user(message: Message) -> bool:
    u = message.from_user
    await db.register_or_update_user(u.id, u.username, u.full_name)
    record = await db.get_user(u.id)
    if record and record["is_banned"]:
        await message.answer("🚫 Твой аккаунт заблокирован администратором.")
        return False
    return True


@user_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    if not await ensure_active_user(message):
        return
    name = html.escape(message.from_user.first_name)
    await message.answer(
        f"👋 Привет, <b>{name}</b>!\n\n"
        f"• Жми <b>💰 Работа (100 ⭐)</b> каждые 10 минут\n"
        f"• Покупай тачки, бизнесы и открывай <b>📦 Кейсы</b>\n"
        f"• Используй кнопки внизу (переключай <b>Страницу 1 / 2</b>)",
        reply_markup=menu_page_1_kb(),
    )


# --- ПЕРЕКЛЮЧЕНИЕ СТРАНИЦ МЕНЮ ---
@user_router.message(F.text == "➡️ Страница 2")
async def to_page_2(message: Message, state: FSMContext):
    await state.clear()
    if not await ensure_active_user(message):
        return
    await message.answer("📄 <b>Страница 2</b>", reply_markup=menu_page_2_kb(message.from_user.id))


@user_router.message(F.text == "⬅️ Страница 1")
async def to_page_1(message: Message, state: FSMContext):
    await state.clear()
    if not await ensure_active_user(message):
        return
    await message.answer("📄 <b>Страница 1</b>", reply_markup=menu_page_1_kb())


# --- ПРОФИЛЬ ---
@user_router.message(F.text == "👤 Профиль")
async def show_profile(message: Message, state: FSMContext):
    await state.clear()
    if not await ensure_active_user(message):
        return
    uid = message.from_user.id
    user = await db.get_user(uid)
    stats = await db.get_user_income_and_counts(uid)

    now = time.time()
    elapsed_hours = max(0.0, (now - (user["last_collect"] or now)) / 3600.0)
    pending = int(elapsed_hours * stats["total_income"])

    name = html.escape(user["full_name"])
    title = html.escape(user["custom_title"] or "Новичок")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏎 Мой гараж", callback_data="my_cars"),
                InlineKeyboardButton(text="🏢 Мои бизнесы", callback_data="my_biz"),
            ]
        ]
    )

    await message.answer(
        f"👤 <b>Профиль игрока</b>\n\n"
        f"📛 Имя: <b>{name}</b>\n"
        f"🏷 Статус: <b>{title}</b>\n"
        f"🆔 ID: <code>{uid}</code>\n\n"
        f"💰 Баланс: <b>{user['balance']:,} ⭐</b>\n"
        f"📈 Пассивный доход: <b>{stats['total_income']:,} ⭐/ч</b>\n"
        f"⏳ Накоплено в сейфе: <b>{pending:,} ⭐</b>\n\n"
        f"🏎 Машин в гараже: <b>{stats['cars_count']}</b> ({stats['cars_income']:,} ⭐/ч)\n"
        f"🏢 Бизнесов: <b>{stats['biz_count']}</b> ({stats['biz_income']:,} ⭐/ч)\n"
        f"✨ Прелестей: <b>{stats['items_count']}</b> ({stats['items_income']:,} ⭐/ч)",
        reply_markup=kb,
    )


@user_router.message(F.text == "🏎 Мой гараж")
async def msg_my_cars(message: Message, state: FSMContext):
    await state.clear()
    if not await ensure_active_user(message):
        return
    cars = await db.get_user_assets(message.from_user.id, "user_cars")
    if not cars:
        await message.answer("🏎 В твоём гараже пока пусто!")
        return
    lines = [f"• <b>{c['name']}</b> — +{c['income']:,} ⭐/ч" for c in cars[:30]]
    extra = f"\n<i>...и ещё {len(cars) - 30} авто</i>" if len(cars) > 30 else ""
    await message.answer("🏎 <b>Твой гараж:</b>\n\n" + "\n".join(lines) + extra)


@user_router.message(F.text == "🏢 Мои бизнесы")
async def msg_my_biz(message: Message, state: FSMContext):
    await state.clear()
    if not await ensure_active_user(message):
        return
    bizes = await db.get_user_assets(message.from_user.id, "user_businesses")
    if not bizes:
        await message.answer("🏢 У тебя пока нет бизнесов!")
        return
    lines = [f"• <b>{b['name']}</b> — +{b['income']:,} ⭐/ч" for b in bizes[:30]]
    extra = f"\n<i>...и ещё {len(bizes) - 30} бизнесов</i>" if len(bizes) > 30 else ""
    await message.answer("🏢 <b>Твои бизнесы:</b>\n\n" + "\n".join(lines) + extra)


@user_router.callback_query(F.data == "my_cars")
async def cb_my_cars(call: CallbackQuery):
    cars = await db.get_user_assets(call.from_user.id, "user_cars")
    if not cars:
        await call.answer("В твоём гараже пока пусто!", show_alert=True)
        return
    lines = [f"• <b>{c['name']}</b> — +{c['income']:,} ⭐/ч" for c in cars[:30]]
    extra = f"\n<i>...и ещё {len(cars) - 30} авто</i>" if len(cars) > 30 else ""
    await call.message.answer("🏎 <b>Твой гараж:</b>\n\n" + "\n".join(lines) + extra)
    await call.answer()


@user_router.callback_query(F.data == "my_biz")
async def cb_my_biz(call: CallbackQuery):
    bizes = await db.get_user_assets(call.from_user.id, "user_businesses")
    if not bizes:
        await call.answer("У тебя пока нет бизнесов!", show_alert=True)
        return
    lines = [f"• <b>{b['name']}</b> — +{b['income']:,} ⭐/ч" for b in bizes[:30]]
    extra = f"\n<i>...и ещё {len(bizes) - 30} бизнесов</i>" if len(bizes) > 30 else ""
    await call.message.answer("🏢 <b>Твои бизнесы:</b>\n\n" + "\n".join(lines) + extra)
    await call.answer()


# --- РАБОТА (100 ⭐ КАЖДЫЕ 10 МИНУТ) ---
@user_router.message(F.text.startswith("💰 Работа"))
async def farm_stars(message: Message, state: FSMContext):
    await state.clear()
    if not await ensure_active_user(message):
        return
    uid = message.from_user.id
    user = await db.get_user(uid)
    now = time.time()
    diff = now - (user["last_farm"] or 0)

    if diff < FARM_COOLDOWN:
        rem = int(FARM_COOLDOWN - diff)
        mins, secs = divmod(rem, 60)
        await message.answer(
            f"⏳ Работа на перезарядке!\n"
            f"Следующие <b>{FARM_REWARD} ⭐</b> будут доступны через <b>{mins} мин. {secs} сек.</b>"
        )
        return

    await db.change_balance(uid, FARM_REWARD)
    await db.update_user_field(uid, "last_farm", now)
    updated = await db.get_user(uid)
    await message.answer(
        f"💵 Ты поработал и получил <b>+{FARM_REWARD} ⭐</b>!\n"
        f"💰 Баланс: <b>{updated['balance']:,} ⭐</b>\n"
        f"⏱ Следующая смена через <b>10 минут</b>."
    )


@user_router.message(F.text == "💵 Собрать прибыль")
async def collect_income(message: Message, state: FSMContext):
    await state.clear()
    if not await ensure_active_user(message):
        return
    uid = message.from_user.id
    earned, total_inc = await db.collect_passive_income(uid)

    if total_inc <= 0:
        await message.answer(
            "📉 У тебя пока нет машин или бизнесов, приносящих доход.\n"
            "Загляни в <b>🏎 Автосалон</b>, <b>🏢 Бизнесы</b> или <b>📦 Кейсы</b>!"
        )
        return

    if earned < 1:
        await message.answer(
            f"⏳ В сейфе пока меньше <b>1 ⭐</b>.\n"
            f"Твой общий доход: <b>{total_inc:,} ⭐/ч</b>. Зайди чуть позже!"
        )
        return

    user = await db.get_user(uid)
    await message.answer(
        f"✅ Собрано с гаража и бизнесов: <b>+{earned:,} ⭐</b>!\n"
        f"💰 Баланс: <b>{user['balance']:,} ⭐</b>"
    )


# --- 📦 КЕЙСЫ ---
def cases_menu_markup() -> tuple[str, InlineKeyboardMarkup]:
    lines = ["📦 <b>Магазин кейсов</b>\nИспытай удачу и выбей редкие тачки, бизнесы или джекпот:\n"]
    buttons = []
    for key, c in CASES_CATALOG.items():
        lines.append(f"<b>{c['name']}</b> — <b>{c['price']:,} ⭐</b>\n<i>{c['info']}</i>\n")
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"Открыть {c['name']} ({c['price']:,} ⭐)",
                    callback_data=f"open_case:{key}",
                )
            ]
        )
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


@user_router.message(F.text == "📦 Кейсы")
async def open_cases_shop(message: Message, state: FSMContext):
    await state.clear()
    if not await ensure_active_user(message):
        return
    text, kb = cases_menu_markup()
    await message.answer(text, reply_markup=kb)


@user_router.callback_query(F.data.startswith("open_case:"))
async def cb_open_case(call: CallbackQuery):
    uid = call.from_user.id
    await db.register_or_update_user(uid, call.from_user.username, call.from_user.full_name)
    user = await db.get_user(uid)
    if user["is_banned"]:
        await call.answer("Аккаунт заблокирован.", show_alert=True)
        return

    key = call.data.split(":")[1]
    if key not in CASES_CATALOG:
        await call.answer("Кейс не найден.", show_alert=True)
        return

    case = CASES_CATALOG[key]
    price = case["price"]
    if user["balance"] < price:
        await call.answer(f"❌ Не хватает звёзд! Нужно {price:,} ⭐", show_alert=True)
        return

    await db.change_balance(uid, -price)
    drops = case["drops"]
    weights = [d[4] for d in drops]
    d_type, d_name, d_val, d_desc, _ = random.choices(drops, weights=weights, k=1)[0]

    if d_type == "stars":
        await db.change_balance(uid, d_val)
        prize_text = f"💰 <b>+{d_val:,} ⭐</b> на баланс!"
    elif d_type == "car":
        await db.add_car(uid, d_name, d_val)
        prize_text = f"🏎 Машина: <b>{d_name}</b> (+{d_val:,} ⭐/ч)!"
    elif d_type == "biz":
        await db.add_business(uid, d_name, d_val)
        prize_text = f"🏢 Бизнес: <b>{d_name}</b> (+{d_val:,} ⭐/ч)!"
    else:
        await db.add_custom_item(uid, d_name, d_desc, d_val)
        prize_text = f"✨ Редкая прелесть: <b>{d_name}</b> (+{d_val:,} ⭐/ч)!"

    updated = await db.get_user(uid)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🔄 Открыть ещё ({price:,} ⭐)",
                    callback_data=f"open_case:{key}",
                )
            ]
        ]
    )
    await call.message.answer(
        f"🎉 Ты открыл <b>{case['name']}</b>!\n\n"
        f"🎁 Выпало: {prize_text}\n"
        f"💰 Твой баланс: <b>{updated['balance']:,} ⭐</b>",
        reply_markup=kb,
    )
    await call.answer()


# --- АВТОСАЛОН ---
@user_router.message(F.text == "🏎 Автосалон")
async def open_car_shop(message: Message, state: FSMContext):
    await state.clear()
    if not await ensure_active_user(message):
        return
    lines = ["🏎 <b>Автосалон</b>\nПокупай тачки, чтобы увеличить пассивный доход:\n"]
    buttons = []
    for key, (name, price, inc) in CARS_CATALOG.items():
        lines.append(f"{name}\nЦена: <b>{price:,} ⭐</b> | Доход: <b>+{inc:,} ⭐/ч</b>\n")
        buttons.append(
            [InlineKeyboardButton(text=f"Купить {name} ({price:,} ⭐)", callback_data=f"buy_car:{key}")]
        )
    await message.answer(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@user_router.callback_query(F.data.startswith("buy_car:"))
async def cb_buy_car(call: CallbackQuery):
    uid = call.from_user.id
    await db.register_or_update_user(uid, call.from_user.username, call.from_user.full_name)
    user = await db.get_user(uid)
    if user["is_banned"]:
        await call.answer("Аккаунт заблокирован.", show_alert=True)
        return

    key = call.data.split(":")[1]
    if key not in CARS_CATALOG:
        await call.answer("Машина не найдена.", show_alert=True)
        return

    name, price, inc = CARS_CATALOG[key]
    if user["balance"] < price:
        await call.answer(f"❌ Не хватает звёзд! Нужно {price:,} ⭐", show_alert=True)
        return

    await db.change_balance(uid, -price)
    await db.add_car(uid, name, inc)
    await call.answer(f"🎉 Куплено: {name} (+{inc:,} ⭐/ч)!", show_alert=True)


# --- БИЗНЕСЫ ---
@user_router.message(F.text == "🏢 Бизнесы")
async def open_biz_shop(message: Message, state: FSMContext):
    await state.clear()
    if not await ensure_active_user(message):
        return
    lines = ["🏢 <b>Магазин бизнесов</b>\nИнвестируй звёзды в предприятия:\n"]
    buttons = []
    for key, (name, price, inc) in BIZ_CATALOG.items():
        lines.append(f"{name}\nЦена: <b>{price:,} ⭐</b> | Доход: <b>+{inc:,} ⭐/ч</b>\n")
        buttons.append(
            [InlineKeyboardButton(text=f"Купить {name} ({price:,} ⭐)", callback_data=f"buy_biz:{key}")]
        )
    await message.answer(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@user_router.callback_query(F.data.startswith("buy_biz:"))
async def cb_buy_biz(call: CallbackQuery):
    uid = call.from_user.id
    await db.register_or_update_user(uid, call.from_user.username, call.from_user.full_name)
    user = await db.get_user(uid)
    if user["is_banned"]:
        await call.answer("Аккаунт заблокирован.", show_alert=True)
        return

    key = call.data.split(":")[1]
    if key not in BIZ_CATALOG:
        await call.answer("Бизнес не найден.", show_alert=True)
        return

    name, price, inc = BIZ_CATALOG[key]
    if user["balance"] < price:
        await call.answer(f"❌ Не хватает звёзд! Нужно {price:,} ⭐", show_alert=True)
        return

    await db.change_balance(uid, -price)
    await db.add_business(uid, name, inc)
    await call.answer(f"🎉 Куплен бизнес: {name} (+{inc:,} ⭐/ч)!", show_alert=True)


# --- МОИ ПРЕЛЕСТИ (ИНВЕНТАРЬ) ---
@user_router.message(F.text == "✨ Мои прелести")
async def show_items(message: Message, state: FSMContext):
    await state.clear()
    if not await ensure_active_user(message):
        return
    items = await db.get_user_assets(message.from_user.id, "user_items")
    if not items:
        await message.answer(
            "✨ <b>Твои прелести</b>\n\n"
            "Пока пусто. Эксклюзивные предметы можно выбить в <b>📦 Кейсах</b>, "
            "получить по промокоду или от администрации!"
        )
        return

    lines = ["✨ <b>Твои эксклюзивные прелести:</b>\n"]
    for it in items:
        bonus_str = f" (+{it['income_bonus']:,} ⭐/ч)" if it["income_bonus"] > 0 else ""
        lines.append(f"• <b>{it['name']}</b>{bonus_str}\n  <i>{it['description']}</i>")
    await message.answer("\n".join(lines))


# --- ТАБЛИЦА ЛИДЕРОВ ---
def top_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💰 По балансу", callback_data="top_bal"),
                InlineKeyboardButton(text="📈 По доходу/ч", callback_data="top_inc"),
            ]
        ]
    )


@user_router.message(F.text == "🏆 Топы")
async def show_leaderboard(message: Message, state: FSMContext):
    await state.clear()
    if not await ensure_active_user(message):
        return
    rows = await db.get_top_balance(10)
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>Топ-10 богачей по балансу:</b>\n"]
    for idx, r in enumerate(rows):
        prefix = medals[idx] if idx < 3 else f"<b>{idx + 1}.</b>"
        name = html.escape(r["full_name"] or "Игрок")
        title = html.escape(r["custom_title"] or "")
        lines.append(f"{prefix} {name} [{title}] — <b>{r['balance']:,} ⭐</b>")
    await message.answer("\n".join(lines), reply_markup=top_kb())


@user_router.callback_query(F.data == "top_bal")
async def cb_top_bal(call: CallbackQuery):
    rows = await db.get_top_balance(10)
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>Топ-10 богачей по балансу:</b>\n"]
    for idx, r in enumerate(rows):
        prefix = medals[idx] if idx < 3 else f"<b>{idx + 1}.</b>"
        name = html.escape(r["full_name"] or "Игрок")
        title = html.escape(r["custom_title"] or "")
        lines.append(f"{prefix} {name} [{title}] — <b>{r['balance']:,} ⭐</b>")
    try:
        await call.message.edit_text("\n".join(lines), reply_markup=top_kb())
    except TelegramBadRequest:
        pass
    await call.answer()


@user_router.callback_query(F.data == "top_inc")
async def cb_top_inc(call: CallbackQuery):
    rows = await db.get_top_income(10)
    medals = ["🥇", "🥈", "🥉"]
    lines = ["📈 <b>Топ-10 по пассивному доходу:</b>\n"]
    for idx, r in enumerate(rows):
        prefix = medals[idx] if idx < 3 else f"<b>{idx + 1}.</b>"
        name = html.escape(r["full_name"] or "Игрок")
        title = html.escape(r["custom_title"] or "")
        lines.append(f"{prefix} {name} [{title}] — <b>{r['total_inc']:,} ⭐/ч</b>")
    try:
        await call.message.edit_text("\n".join(lines), reply_markup=top_kb())
    except TelegramBadRequest:
        pass
    await call.answer()


# --- АКТИВАЦИЯ ПРОМОКОДА ---
@user_router.message(F.text == "🎟 Промокод")
async def ask_promocode(message: Message, state: FSMContext):
    if not await ensure_active_user(message):
        return
    await state.set_state(UserStates.waiting_promo)
    await message.answer("🎟 Введи промокод:")


@user_router.message(UserStates.waiting_promo)
async def process_promocode(message: Message, state: FSMContext):
    if not await ensure_active_user(message):
        return
    await state.clear()
    _, reply = await db.redeem_promocode(message.from_user.id, message.text or "")
    await message.answer(reply, reply_markup=menu_page_1_kb())


from aiogram.types import FSInputFile
from aiogram.filters import Command
from config import ADMIN_ID, DB_PATH

@dp.message(Command("backup"))
async def cmd_backup(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        await message.answer_document(
            FSInputFile(DB_PATH),
            caption="💾 Резервная копия базы игроков (ответь на этот файл командой /restore, чтобы восстановить её).",
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка бэкапа: {e}")

@dp.message(Command("restore"))
async def cmd_restore(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.answer("❌ Ответь командой <code>/restore</code> на присланный ботом файл <code>game_bot.db</code>.")
    file_id = message.reply_to_message.document.file_id
    file = await bot.get_file(file_id)
    await bot.download_file(file.file_path, DB_PATH)
    await message.answer("✅ База данных успешно восстановлена! Все звёзды, машины и бизнесы игроков на месте.")

async def auto_backup_loop():
    while True:
        await asyncio.sleep(21600)  # Каждые 6 часов шлёт копию базы админу
        try:
            await bot.send_document(
                ADMIN_ID,
                FSInputFile(DB_PATH),
                caption="🔄 Автобэкап базы <b>Mining & Farm</b> (на случай переноса или перезапуска сервера).",
            )
        except Exception:
            pass

async def main():
    await db.init_db()
    asyncio.create_task(auto_backup_loop())
    print("Бот успешно запущен!")
    while True:
        try:
            await dp.start_polling(bot, drop_pending_updates=True)
        except Exception as e:
            print(f"[Переподключение через 3 сек]: {e}")
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
    
