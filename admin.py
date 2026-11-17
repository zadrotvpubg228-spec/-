import html
import random
import string
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import ADMIN_IDS, BIZ_CATALOG, CARS_CATALOG
import database as db

admin_router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def safe_edit(call: CallbackQuery, text: str, kb: InlineKeyboardMarkup | None = None):
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass
    await call.answer()


class AdminStates(StatesGroup):
    waiting_user_search = State()
    waiting_balance_delta = State()
    waiting_custom_car = State()
    waiting_custom_biz = State()
    waiting_custom_item = State()
    waiting_custom_title = State()
    promo_code = State()
    promo_reward = State()
    promo_limit = State()
    promo_edit_limit = State()
    waiting_broadcast = State()


def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 Управление игроком", callback_data="adm_user")],
            [InlineKeyboardButton(text="🎟 Промокоды (все функции)", callback_data="adm_promos_menu")],
            [InlineKeyboardButton(text="📢 Рассылка всем", callback_data="adm_mail")],
            [InlineKeyboardButton(text="📊 Статистика бота", callback_data="adm_stats")],
        ]
    )


def cancel_kb(back_to: str = "adm_cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=back_to)]]
    )


def player_manage_kb(target_id: int, is_banned: int) -> InlineKeyboardMarkup:
    ban_text = "✅ Разбанить" if is_banned else "🚫 Забанить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Выдать ⭐", callback_data=f"adm_bal_add:{target_id}"),
                InlineKeyboardButton(text="➖ Забрать ⭐", callback_data=f"adm_bal_sub:{target_id}"),
            ],
            [
                InlineKeyboardButton(text="🏎 Авто из каталога", callback_data=f"adm_list_car:{target_id}"),
                InlineKeyboardButton(text="🛠 Кастом авто", callback_data=f"adm_cst_car:{target_id}"),
            ],
            [
                InlineKeyboardButton(text="🏢 Бизнес из каталога", callback_data=f"adm_list_biz:{target_id}"),
                InlineKeyboardButton(text="🏗 Кастом бизнес", callback_data=f"adm_cst_biz:{target_id}"),
            ],
            [
                InlineKeyboardButton(text="✨ Выдать прелесть", callback_data=f"adm_cst_item:{target_id}"),
                InlineKeyboardButton(text="🏷 Сменить титул", callback_data=f"adm_title:{target_id}"),
            ],
            [
                InlineKeyboardButton(text=ban_text, callback_data=f"adm_ban:{target_id}"),
                InlineKeyboardButton(text="🔙 В админку", callback_data="adm_home"),
            ],
        ]
    )


async def render_player_card(target_id: int) -> tuple[str, InlineKeyboardMarkup]:
    user = await db.get_user(target_id)
    stats = await db.get_user_income_and_counts(target_id)
    name = html.escape(user["full_name"] or "Без имени")
    title = html.escape(user["custom_title"] or "Новичок")
    uname = f"@{user['username']}" if user["username"] else "нет"
    status = "🚫 ЗАБАНЕН" if user["is_banned"] else "✅ Активен"

    text = (
        f"👑 <b>Управление игроком</b>\n\n"
        f"🆔 ID: <code>{user['user_id']}</code>\n"
        f"👤 Имя: <b>{name}</b> ({uname})\n"
        f"🏷 Титул: <b>{title}</b>\n"
        f"📌 Статус: {status}\n"
        f"💰 Баланс: <b>{user['balance']:,} ⭐</b>\n"
        f"📈 Доход: <b>{stats['total_income']:,} ⭐/ч</b>\n"
        f"🏎 Машин: <b>{stats['cars_count']}</b> | 🏢 Бизнесов: <b>{stats['biz_count']}</b> | ✨ Прелестей: <b>{stats['items_count']}</b>"
    )
    return text, player_manage_kb(target_id, user["is_banned"])


@admin_router.message(Command("admin"))
@admin_router.message(F.text == "👑 Админ-панель")
async def open_admin_panel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer(
        "👑 <b>Панель администратора</b>\nВыбери раздел:",
        reply_markup=admin_main_kb(),
    )


@admin_router.callback_query(F.data == "adm_home")
async def cb_admin_home(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.clear()
    await safe_edit(call, "👑 <b>Панель администратора</b>\nВыбери раздел:", admin_main_kb())


@admin_router.callback_query(F.data == "adm_cancel")
async def cb_admin_cancel(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.clear()
    await safe_edit(call, "❌ Действие отменено.", admin_main_kb())


# --- ПОИСК ИГРОКА ---
@admin_router.callback_query(F.data == "adm_user")
async def cb_find_user(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_user_search)
    await safe_edit(
        call,
        "🔍 Введи <b>Telegram ID</b> или <b>@username</b> игрока:",
        cancel_kb(),
    )


@admin_router.message(AdminStates.waiting_user_search)
async def process_find_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    user = await db.find_user(message.text or "")
    if not user:
        await message.answer(
            "❌ Игрок не найден в базе. Попробуй другой ID или @username:",
            reply_markup=cancel_kb(),
        )
        return
    await state.clear()
    text, kb = await render_player_card(user["user_id"])
    await message.answer(text, reply_markup=kb)


# --- БАЛАНС ---
@admin_router.callback_query(F.data.startswith("adm_bal_"))
async def cb_balance_ask(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    action, target_str = call.data.split(":")
    sign = 1 if action == "adm_bal_add" else -1
    await state.update_data(target_id=int(target_str), sign=sign)
    await state.set_state(AdminStates.waiting_balance_delta)
    word = "выдать" if sign == 1 else "забрать"
    await safe_edit(call, f"💰 Введи сумму <b>⭐</b>, которую нужно {word}:", cancel_kb())


@admin_router.message(AdminStates.waiting_balance_delta)
async def process_balance_delta(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = (message.text or "").replace(" ", "")
    if not raw.isdigit():
        await message.answer("❌ Введи целое положительное число:", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    target_id = data["target_id"]
    delta = int(raw) * data["sign"]
    await db.change_balance(target_id, delta)
    await state.clear()
    text, kb = await render_player_card(target_id)
    await message.answer(f"✅ Баланс изменён ({delta:+,} ⭐)!\n\n" + text, reply_markup=kb)


# --- СТАНДАРТНЫЕ АВТО / БИЗНЕСЫ ---
@admin_router.callback_query(F.data.startswith("adm_list_car:"))
async def cb_list_cars(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    target_id = int(call.data.split(":")[1])
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{val[0]} (+{val[2]:,}/ч)",
                callback_data=f"adm_gcar:{target_id}:{key}",
            )
        ]
        for key, val in CARS_CATALOG.items()
    ]
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"adm_back:{target_id}")])
    await safe_edit(
        call,
        "🏎 Выбери машину для выдачи:",
        InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@admin_router.callback_query(F.data.startswith("adm_gcar:"))
async def cb_give_std_car(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    _, target_str, key = call.data.split(":")
    target_id = int(target_str)
    car_name, _, car_inc = CARS_CATALOG[key]
    await db.add_car(target_id, car_name, car_inc)
    text, kb = await render_player_card(target_id)
    await safe_edit(call, f"✅ Выдано авто: <b>{car_name}</b>\n\n" + text, kb)


@admin_router.callback_query(F.data.startswith("adm_list_biz:"))
async def cb_list_biz(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    target_id = int(call.data.split(":")[1])
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{val[0]} (+{val[2]:,}/ч)",
                callback_data=f"adm_gbiz:{target_id}:{key}",
            )
        ]
        for key, val in BIZ_CATALOG.items()
    ]
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"adm_back:{target_id}")])
    await safe_edit(
        call,
        "🏢 Выбери бизнес для выдачи:",
        InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@admin_router.callback_query(F.data.startswith("adm_gbiz:"))
async def cb_give_std_biz(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    _, target_str, key = call.data.split(":")
    target_id = int(target_str)
    biz_name, _, biz_inc = BIZ_CATALOG[key]
    await db.add_business(target_id, biz_name, biz_inc)
    text, kb = await render_player_card(target_id)
    await safe_edit(call, f"✅ Выдан бизнес: <b>{biz_name}</b>\n\n" + text, kb)


# --- КАСТОМНОЕ АВТО / БИЗНЕС / ПРЕЛЕСТЬ ---
@admin_router.callback_query(F.data.startswith("adm_cst_car:"))
async def cb_custom_car(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    target_id = int(call.data.split(":")[1])
    await state.update_data(target_id=target_id)
    await state.set_state(AdminStates.waiting_custom_car)
    await safe_edit(
        call,
        "🛠 Отправь данные кастомной машины в формате:\n"
        "<code>Название | Доход в час</code>\n\n"
        "Пример:\n<code>🛸 НЛО Админа | 5000000</code>",
        cancel_kb(),
    )


@admin_router.message(AdminStates.waiting_custom_car)
async def process_custom_car(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    parts = [p.strip() for p in (message.text or "").split("|")]
    if len(parts) != 2 or not parts[1].replace(" ", "").isdigit():
        await message.answer("❌ Формат: <code>Название | Доход</code>", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    target_id = data["target_id"]
    name = html.escape(parts[0])
    inc = int(parts[1].replace(" ", ""))
    await db.add_car(target_id, name, inc)
    await state.clear()
    text, kb = await render_player_card(target_id)
    await message.answer(f"✅ Выдана кастом-машина <b>{name}</b> (+{inc:,} ⭐/ч)!\n\n" + text, reply_markup=kb)


@admin_router.callback_query(F.data.startswith("adm_cst_biz:"))
async def cb_custom_biz(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    target_id = int(call.data.split(":")[1])
    await state.update_data(target_id=target_id)
    await state.set_state(AdminStates.waiting_custom_biz)
    await safe_edit(
        call,
        "🏗 Отправь данные кастомного бизнеса в формате:\n"
        "<code>Название | Доход в час</code>\n\n"
        "Пример:\n<code>🏦 Центробанк | 10000000</code>",
        cancel_kb(),
    )


@admin_router.message(AdminStates.waiting_custom_biz)
async def process_custom_biz(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    parts = [p.strip() for p in (message.text or "").split("|")]
    if len(parts) != 2 or not parts[1].replace(" ", "").isdigit():
        await message.answer("❌ Формат: <code>Название | Доход</code>", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    target_id = data["target_id"]
    name = html.escape(parts[0])
    inc = int(parts[1].replace(" ", ""))
    await db.add_business(target_id, name, inc)
    await state.clear()
    text, kb = await render_player_card(target_id)
    await message.answer(f"✅ Выдан кастом-бизнес <b>{name}</b> (+{inc:,} ⭐/ч)!\n\n" + text, reply_markup=kb)


@admin_router.callback_query(F.data.startswith("adm_cst_item:"))
async def cb_custom_item(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    target_id = int(call.data.split(":")[1])
    await state.update_data(target_id=target_id)
    await state.set_state(AdminStates.waiting_custom_item)
    await safe_edit(
        call,
        "✨ Отправь кастомную прелесть в формате:\n"
        "<code>Название | Описание | Бонус дохода в час</code>\n\n"
        "Пример:\n<code>👑 Золотой пропуск | Эксклюзив от создателя | 250000</code>\n"
        "<i>(если доход не нужен, пиши 0)</i>",
        cancel_kb(),
    )


@admin_router.message(AdminStates.waiting_custom_item)
async def process_custom_item(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    parts = [p.strip() for p in (message.text or "").split("|")]
    if len(parts) != 3 or not parts[2].replace(" ", "").isdigit():
        await message.answer(
            "❌ Формат: <code>Название | Описание | Доход</code>", reply_markup=cancel_kb()
        )
        return
    data = await state.get_data()
    target_id = data["target_id"]
    name = html.escape(parts[0])
    desc = html.escape(parts[1])
    inc = int(parts[2].replace(" ", ""))
    await db.add_custom_item(target_id, name, desc, inc)
    await state.clear()
    text, kb = await render_player_card(target_id)
    await message.answer(f"✅ Выдана прелесть <b>{name}</b>!\n\n" + text, reply_markup=kb)


@admin_router.callback_query(F.data.startswith("adm_title:"))
async def cb_change_title(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    target_id = int(call.data.split(":")[1])
    await state.update_data(target_id=target_id)
    await state.set_state(AdminStates.waiting_custom_title)
    await safe_edit(
        call,
        "🏷 Введи новый титул для игрока (например: <code>💎 VIP Магнат</code>):",
        cancel_kb(),
    )


@admin_router.message(AdminStates.waiting_custom_title)
async def process_change_title(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    target_id = data["target_id"]
    new_title = html.escape((message.text or "Игрок")[:40])
    await db.update_user_field(target_id, "custom_title", new_title)
    await state.clear()
    text, kb = await render_player_card(target_id)
    await message.answer("✅ Титул обновлён!\n\n" + text, reply_markup=kb)


@admin_router.callback_query(F.data.startswith("adm_ban:"))
async def cb_toggle_ban(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    target_id = int(call.data.split(":")[1])
    user = await db.get_user(target_id)
    new_state = 0 if user["is_banned"] else 1
    await db.update_user_field(target_id, "is_banned", new_state)
    text, kb = await render_player_card(target_id)
    await safe_edit(call, text, kb)


@admin_router.callback_query(F.data.startswith("adm_back:"))
async def cb_back_to_player(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    target_id = int(call.data.split(":")[1])
    text, kb = await render_player_card(target_id)
    await safe_edit(call, text, kb)


# ==========================================
# ПОЛНОЕ УПРАВЛЕНИЕ ПРОМОКОДАМИ В АДМИНКЕ
# ==========================================

def promos_hub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать промокод", callback_data="adm_promo_new")],
            [InlineKeyboardButton(text="📋 Список и управление кодами", callback_data="adm_promo_list")],
            [InlineKeyboardButton(text="🔙 В админку", callback_data="adm_home")],
        ]
    )


@admin_router.callback_query(F.data == "adm_promos_menu")
async def cb_promos_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.clear()
    promos = await db.get_all_promocodes()
    await safe_edit(
        call,
        f"🎟 <b>Управление промокодами</b>\n\n"
        f"Всего кодов в базе: <b>{len(promos)}</b>\n"
        f"Создавай лимитные и безлимитные промокоды, добавляй активации, ставь на паузу и удаляй.",
        promos_hub_kb(),
    )


@admin_router.callback_query(F.data == "adm_promo_new")
async def cb_promo_step1(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.promo_code)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎲 Сгенерировать случайный код", callback_data="adm_promo_rand")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="adm_promos_menu")],
        ]
    )
    await safe_edit(
        call,
        "🎟 <b>Шаг 1 из 4:</b> Введи название промокода (например <code>BONUS2026</code>) или нажми кнопку ниже:",
        kb,
    )


def promo_types_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Звёзды (⭐)", callback_data="ptype:stars")],
            [
                InlineKeyboardButton(text="🏎 Машина", callback_data="ptype:car"),
                InlineKeyboardButton(text="🏢 Бизнес", callback_data="ptype:biz"),
            ],
            [
                InlineKeyboardButton(text="✨ Кастом прелесть", callback_data="ptype:item"),
                InlineKeyboardButton(text="🏷 Титул", callback_data="ptype:title"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="adm_promos_menu")],
        ]
    )


@admin_router.callback_query(F.data == "adm_promo_rand")
async def cb_promo_random_code(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    rand_code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    await state.update_data(code=rand_code)
    await state.set_state(AdminStates.promo_reward)
    await safe_edit(
        call,
        f"🎟 Код: <code>{rand_code}</code>\n\n<b>Шаг 2 из 4:</b> Выбери, что будет давать промокод:",
        promo_types_kb(),
    )


@admin_router.message(AdminStates.promo_code)
async def process_promo_step1(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    code = (message.text or "").strip().upper().replace(" ", "")
    if not code or len(code) > 25:
        await message.answer("❌ Код должен быть от 1 до 25 символов без пробелов:")
        return
    await state.update_data(code=code)
    await state.set_state(AdminStates.promo_reward)
    await message.answer(
        f"🎟 Код: <code>{code}</code>\n\n<b>Шаг 2 из 4:</b> Выбери, что будет давать промокод:",
        reply_markup=promo_types_kb(),
    )


@admin_router.callback_query(F.data.startswith("ptype:"))
async def cb_promo_step2(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    rtype = call.data.split(":")[1]
    await state.update_data(rtype=rtype)
    await state.set_state(AdminStates.promo_reward)

    prompts = {
        "stars": "💰 <b>Шаг 3 из 4:</b> Введи количество звёзд <b>⭐</b> (например <code>50000</code>):",
        "car": "🏎 <b>Шаг 3 из 4:</b> Введи машину в формате:\n<code>Название | Доход в час</code>\nПример: <code>🔥 BMW M5 F90 | 90000</code>",
        "biz": "🏢 <b>Шаг 3 из 4:</b> Введи бизнес в формате:\n<code>Название | Доход в час</code>\nПример: <code>🛢 Нефтевышка | 3200000</code>",
        "item": "✨ <b>Шаг 3 из 4:</b> Введи прелесть в формате:\n<code>Название | Описание | Бонус дохода</code>\nПример: <code>👑 Ключ основателя | Редкий трофей | 50000</code>",
        "title": "🏷 <b>Шаг 3 из 4:</b> Введи текст титула (например <code>⚡ Легенда чата</code>):",
    }
    await safe_edit(call, prompts[rtype], cancel_kb("adm_promos_menu"))


@admin_router.message(AdminStates.promo_reward)
async def process_promo_step3(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    rtype = data["rtype"]
    raw = (message.text or "").strip()

    if rtype == "stars":
        num = raw.replace(" ", "")
        if not num.isdigit() or int(num) <= 0:
            await message.answer("❌ Введи положительное число звёзд:")
            return
        await state.update_data(rname="Звёзды", rval=int(num), rdesc="Валюта")
    elif rtype in ("car", "biz"):
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) != 2 or not parts[1].replace(" ", "").isdigit():
            await message.answer("❌ Неверный формат! Пиши так: <code>Название | Доход</code>")
            return
        await state.update_data(
            rname=html.escape(parts[0]),
            rval=int(parts[1].replace(" ", "")),
            rdesc="Эксклюзив",
        )
    elif rtype == "item":
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) != 3 or not parts[2].replace(" ", "").isdigit():
            await message.answer(
                "❌ Неверный формат! Пиши так: <code>Название | Описание | Доход</code>"
            )
            return
        await state.update_data(
            rname=html.escape(parts[0]),
            rdesc=html.escape(parts[1]),
            rval=int(parts[2].replace(" ", "")),
        )
    elif rtype == "title":
        await state.update_data(rname=html.escape(raw[:40]), rval=0, rdesc="Титул")

    await state.set_state(AdminStates.promo_limit)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="♾ Сделать БЕЗЛИМИТНЫМ", callback_data="plimit:unlim")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="adm_promos_menu")],
        ]
    )
    await message.answer(
        "🔢 <b>Шаг 4 из 4 (Лимит активаций):</b>\n\n"
        "Введи число — сколько человек смогут активировать этот промокод (например <code>1</code>, <code>10</code>, <code>100</code>)\n"
        "или нажми кнопку <b>Безлимитный</b>:",
        reply_markup=kb,
    )


@admin_router.callback_query(F.data == "plimit:unlim")
async def cb_promo_unlim(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    data = await state.get_data()
    await db.create_promocode(
        data["code"], data["rtype"], data["rname"], data["rval"], data["rdesc"], -1
    )
    await state.clear()
    await safe_edit(
        call,
        f"✅ Промокод <code>{data['code']}</code> создан!\n"
        f"♾ Лимит: <b>Безлимитный</b> (1 активация на каждого игрока).",
        promos_hub_kb(),
    )


@admin_router.message(AdminStates.promo_limit)
async def process_promo_step4(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = (message.text or "").strip().replace(" ", "")
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("❌ Введи число больше 0 (например 10):")
        return
    limit_val = int(raw)
    data = await state.get_data()
    await db.create_promocode(
        data["code"], data["rtype"], data["rname"], data["rval"], data["rdesc"], limit_val
    )
    await state.clear()
    await message.answer(
        f"✅ Промокод <code>{data['code']}</code> успешно создан!\n"
        f"🔢 Лимит активаций: <b>{limit_val}</b>",
        reply_markup=promos_hub_kb(),
    )


@admin_router.callback_query(F.data == "adm_promo_list")
async def cb_promo_list(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    promos = await db.get_all_promocodes()
    if not promos:
        await safe_edit(call, "📭 Промокодов пока нет.", promos_hub_kb())
        return

    buttons = []
    for p in promos[:25]:
        status_icon = "🟢" if p["is_active"] else "⏸"
        lim_str = "♾" if p["max_uses"] == -1 else f"{p['used_count']}/{p['max_uses']}"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{status_icon} {p['code']} ({lim_str})",
                    callback_data=f"adm_pview:{p['code']}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="adm_promos_menu")])
    await safe_edit(
        call,
        "📋 <b>Выбери промокод для настройки или удаления:</b>",
        InlineKeyboardMarkup(inline_keyboard=buttons),
    )


async def render_promo_card(code: str) -> tuple[str, InlineKeyboardMarkup]:
    p = await db.get_promocode(code)
    status = "🟢 Активен" if p["is_active"] else "⏸ На паузе"
    is_unlim = p["max_uses"] == -1
    lim_text = (
        f"♾ Безлимитный (использован {p['used_count']} раз)"
        if is_unlim
        else f"{p['used_count']} из {p['max_uses']} (осталось {max(0, p['max_uses'] - p['used_count'])})"
    )
    type_names = {
        "stars": f"💰 {p['reward_value']:,} ⭐",
        "car": f"🏎 {p['reward_name']} (+{p['reward_value']:,} ⭐/ч)",
        "biz": f"🏢 {p['reward_name']} (+{p['reward_value']:,} ⭐/ч)",
        "item": f"✨ {p['reward_name']} (+{p['reward_value']:,} ⭐/ч)",
        "title": f"🏷 Титул: {p['reward_name']}",
    }
    toggle_btn = "⏸ Поставить на паузу" if p["is_active"] else "▶️ Включить обратно"

    text = (
        f"🎟 <b>Промокод:</b> <code>{p['code']}</code>\n\n"
        f"🎁 Награда: <b>{type_names.get(p['reward_type'], p['reward_name'])}</b>\n"
        f"📌 Статус: {status}\n"
        f"🔢 Лимит: <b>{lim_text}</b>"
    )

    rows = []
    if is_unlim:
        rows.append([InlineKeyboardButton(text="✏️ Задать числовой лимит", callback_data=f"adm_plim:{code}")])
    else:
        rows.append(
            [
                InlineKeyboardButton(text="✏️ Задать лимит", callback_data=f"adm_plim:{code}"),
                InlineKeyboardButton(text="➕ +10 к лимиту", callback_data=f"adm_padd10:{code}"),
            ]
        )
        rows.append([InlineKeyboardButton(text="♾ Сделать безлимит", callback_data=f"adm_punlim:{code}")])

    rows.append([InlineKeyboardButton(text=toggle_btn, callback_data=f"adm_ptog:{code}")])
    rows.append([InlineKeyboardButton(text="🗑 Удалить промокод", callback_data=f"adm_pdel:{code}")])
    rows.append([InlineKeyboardButton(text="🔙 К списку кодов", callback_data="adm_promo_list")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@admin_router.callback_query(F.data.startswith("adm_pview:"))
async def cb_promo_view(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    code = call.data.split(":")[1]
    text, kb = await render_promo_card(code)
    await safe_edit(call, text, kb)


@admin_router.callback_query(F.data.startswith("adm_padd10:"))
async def cb_promo_add10(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    code = call.data.split(":")[1]
    await db.add_promo_limit(code, 10)
    text, kb = await render_promo_card(code)
    await safe_edit(call, text, kb)


@admin_router.callback_query(F.data.startswith("adm_punlim:"))
async def cb_promo_make_unlim(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    code = call.data.split(":")[1]
    await db.set_promo_limit(code, -1)
    text, kb = await render_promo_card(code)
    await safe_edit(call, text, kb)


@admin_router.callback_query(F.data.startswith("adm_ptog:"))
async def cb_promo_toggle(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    code = call.data.split(":")[1]
    await db.toggle_promo_status(code)
    text, kb = await render_promo_card(code)
    await safe_edit(call, text, kb)


@admin_router.callback_query(F.data.startswith("adm_pdel:"))
async def cb_promo_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    code = call.data.split(":")[1]
    await db.delete_promocode(code)
    await call.answer(f"🗑 Промокод {code} удалён!", show_alert=True)
    await cb_promo_list(call)


@admin_router.callback_query(F.data.startswith("adm_plim:"))
async def cb_promo_edit_limit(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    code = call.data.split(":")[1]
    await state.update_data(edit_code=code)
    await state.set_state(AdminStates.promo_edit_limit)
    await safe_edit(
        call,
        f"✏️ Введи новый общий лимит активаций для промокода <code>{code}</code>:",
        cancel_kb("adm_promo_list"),
    )


@admin_router.message(AdminStates.promo_edit_limit)
async def process_promo_edit_limit(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    raw = (message.text or "").strip().replace(" ", "")
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("❌ Введи целое число больше 0:")
        return
    data = await state.get_data()
    code = data["edit_code"]
    await db.set_promo_limit(code, int(raw))
    await state.clear()
    text, kb = await render_promo_card(code)
    await message.answer("✅ Лимит обновлён!\n\n" + text, reply_markup=kb)


# --- РАССЫЛКА И СТАТИСТИКА ---
@admin_router.callback_query(F.data == "adm_mail")
async def cb_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_broadcast)
    await safe_edit(
        call,
        "📢 Отправь текст сообщения, которое получат все игроки:",
        cancel_kb(),
    )


@admin_router.message(AdminStates.waiting_broadcast)
async def process_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    _, _, _, _, _, all_ids = await db.get_global_stats()
    await state.clear()
    sent = 0
    for uid in all_ids:
        try:
            await message.bot.send_message(uid, f"📢 <b>Объявление:</b>\n\n{message.html_text}")
            sent += 1
        except Exception:
            pass
    await message.answer(
        f"✅ Рассылка завершена! Доставлено: <b>{sent}</b> из <b>{len(all_ids)}</b>.",
        reply_markup=admin_main_kb(),
    )


@admin_router.callback_query(F.data == "adm_stats")
async def cb_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    users_cnt, total_bal, cars_cnt, biz_cnt, promo_cnt, _ = await db.get_global_stats()
    await safe_edit(
        call,
        f"📊 <b>Статистика проекта</b>\n\n"
        f"👥 Всего игроков: <b>{users_cnt}</b>\n"
        f"💰 Валюты в обороте: <b>{total_bal:,} ⭐</b>\n"
        f"🏎 Машин у игроков: <b>{cars_cnt}</b>\n"
        f"🏢 Бизнесов у игроков: <b>{biz_cnt}</b>\n"
        f"🎟 Промокодов в базе: <b>{promo_cnt}</b>",
        admin_main_kb(),
    )
