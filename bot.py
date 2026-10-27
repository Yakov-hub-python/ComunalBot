import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    FSInputFile,
)

from storage import (
    load_data,
    save_data,
    get_current_month_key,
    month_key_to_name,
    month_key_to_date,
    get_sorted_month_keys,
    get_last_meter_reading,
    get_last_meter_month,
    add_meter_readings,
    add_receipt,
    delete_receipt,
    is_setup_complete,
    has_initial_readings,
    HEATING_COEFFICIENT,
)
from calculations import calculate_receipt, validate_readings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── FSM ──────────────────────────────────────

class SetupInitialReadings(StatesGroup):
    waiting_hvs = State()
    waiting_gvs = State()
    waiting_gas = State()
    waiting_electricity = State()

class SetupTariffs(StatesGroup):
    waiting_water = State()
    waiting_sewage = State()
    waiting_gas = State()
    waiting_electricity = State()
    waiting_heating = State()

class InputReadings(StatesGroup):
    waiting_hvs = State()
    waiting_gvs = State()
    waiting_gas = State()
    waiting_electricity = State()

class ChangeTariffs(StatesGroup):
    waiting_selection = State()
    waiting_value = State()

class DeleteReceiptState(StatesGroup):
    waiting_month = State()
    waiting_confirm = State()

# ── Форматирование ───────────────────────────

def fmt_money(val: float) -> str:
    s = f"{val:,.2f}".replace(",", " ")
    return f"{s} ₽"

def fmt_num(val: float) -> str:
    return str(int(val)) if val == int(val) else str(val)

# ── Клавиатуры ───────────────────────────────

def period_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Месяц", callback_data="period_month"),
            InlineKeyboardButton(text="📅 Полгода", callback_data="period_half_year"),
        ],
        [
            InlineKeyboardButton(text="📅 Год", callback_data="period_year"),
            InlineKeyboardButton(text="📅 Всё время", callback_data="period_all"),
        ],
    ])

def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes"),
            InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no"),
        ]
    ])

def tariff_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💧 Водоснабжение", callback_data="tariff_water")],
        [InlineKeyboardButton(text="🚿 Водоотведение", callback_data="tariff_sewage")],
        [InlineKeyboardButton(text="🔥 Газ", callback_data="tariff_gas")],
        [InlineKeyboardButton(text="💡 Электро", callback_data="tariff_electricity")],
        [InlineKeyboardButton(text="♨️ Подогрев", callback_data="tariff_heating")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")],
    ])

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Показания", callback_data="cmd_readings")],
        [
            InlineKeyboardButton(text="💰 Расчёт", callback_data="cmd_calc"),
            InlineKeyboardButton(text="📈 Итого", callback_data="cmd_total"),
        ],
        [
            InlineKeyboardButton(text="📜 История", callback_data="cmd_history"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data="cmd_delete"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Тарифы", callback_data="cmd_tariffs"),
            InlineKeyboardButton(text="📤 Экспорт", callback_data="cmd_export"),
        ],
    ])

# ── Хелперы ──────────────────────────────────

async def show_main_menu(message: Message):
    await message.answer(
        "🏠 <b>Главное меню</b>\n\nВыберите действие:",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )

def get_period_months(period: str) -> list[str]:
    """Возвращает список ключей месяцев для периода."""
    now = datetime.now()
    keys = []
    if period == "month":
        keys = [now.strftime("%m.%Y")]
    elif period == "half_year":
        for i in range(6):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            keys.append(f"{m:02d}.{y}")
    elif period == "year":
        for i in range(12):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            keys.append(f"{m:02d}.{y}")
    elif period == "all":
        keys = None  # Все месяцы
    return keys


# ── Хендлеры ──────────────────────────────────

async def cmd_start(message: Message, state: FSMContext):
    data = load_data()
    if not is_setup_complete(data) or not has_initial_readings(data):
        await message.answer(
            "👋 Добро пожаловать!\n\n"
            "Для начала работы необходимо настроить бота.\n"
            "Введите начальные показания счётчиков.\n\n"
            "📏 <b>Показание ХВС</b> (м³):",
            parse_mode="HTML",
        )
        await state.set_state(SetupInitialReadings.waiting_hvs)
        return

    await message.answer(
        "👋 С возвращением!",
        parse_mode="HTML",
    )
    await show_main_menu(message)


async def setup_hvs(message: Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        if val < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное положительное число.")
        return
    await state.update_data(hvs=val)
    await message.answer("📏 <b>Показание ГВС</b> (м³):", parse_mode="HTML")
    await state.set_state(SetupInitialReadings.waiting_gvs)


async def setup_gvs(message: Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        if val < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное положительное число.")
        return
    await state.update_data(gvs=val)
    await message.answer("📏 <b>Показание Газ</b> (м³):", parse_mode="HTML")
    await state.set_state(SetupInitialReadings.waiting_gas)


async def setup_gas(message: Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        if val < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное положительное число.")
        return
    await state.update_data(gas=val)
    await message.answer("📏 <b>Показание Электро</b> (кВт·ч):", parse_mode="HTML")
    await state.set_state(SetupInitialReadings.waiting_electricity)


async def setup_electricity(message: Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        if val < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное положительное число.")
        return

    fs_data = await state.get_data()
    fs_data["electricity"] = val

    data = load_data()
    month_key = get_current_month_key()

    readings = {
        "hvs": fs_data["hvs"],
        "gvs": fs_data["gvs"],
        "gas": fs_data["gas"],
        "electricity": val,
    }

    add_meter_readings(month_key, readings, data)
    save_data(data)

    await message.answer(
        "✅ Начальные показания сохранены!\n\n"
        "Теперь введите тарифы.\n\n"
        "💧 <b>Тариф водоснабжения</b> (₽/м³):",
        parse_mode="HTML",
    )
    await state.set_state(SetupTariffs.waiting_water)


async def setup_tariff_water(message: Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        if val <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное положительное число.")
        return
    await state.update_data(tariff_water=val)
    await message.answer("🚿 <b>Тариф водоотведения</b> (₽/м³):", parse_mode="HTML")
    await state.set_state(SetupTariffs.waiting_sewage)


async def setup_tariff_sewage(message: Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        if val <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное положительное число.")
        return
    await state.update_data(tariff_sewage=val)
    await message.answer("🔥 <b>Тариф газа</b> (₽/м³):", parse_mode="HTML")
    await state.set_state(SetupTariffs.waiting_gas)


async def setup_tariff_gas(message: Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        if val <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное положительное число.")
        return
    await state.update_data(tariff_gas=val)
    await message.answer("💡 <b>Тариф электро</b> (₽/кВт·ч):", parse_mode="HTML")
    await state.set_state(SetupTariffs.waiting_electricity)


async def setup_tariff_electricity(message: Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        if val <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное положительное число.")
        return
    await state.update_data(tariff_electricity=val)
    await message.answer("♨️ <b>Тариф подогрева</b> (₽/м³):", parse_mode="HTML")
    await state.set_state(SetupTariffs.waiting_heating)


async def setup_tariff_heating(message: Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        if val <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное положительное число.")
        return

    fs_data = await state.get_data()

    data = load_data()
    data["tariffs"] = {
        "water": fs_data["tariff_water"],
        "sewage": fs_data["tariff_sewage"],
        "gas": fs_data["tariff_gas"],
        "electricity": fs_data["tariff_electricity"],
        "heating": val,
    }
    save_data(data)

    await message.answer(
        "✅ <b>Настройка завершена!</b>\n\n"
        "Тарифы сохранены:\n"
        f"💧 Водоснабжение: {fmt_money(fs_data['tariff_water'])}/м³\n"
        f"🚿 Водоотведение: {fmt_money(fs_data['tariff_sewage'])}/м³\n"
        f"🔥 Газ: {fmt_money(fs_data['tariff_gas'])}/м³\n"
        f"💡 Электро: {fmt_money(fs_data['tariff_electricity'])}/кВт·ч\n"
        f"♨️ Подогрев: {fmt_money(val)}/м³\n\n"
        "Используйте меню ниже 👇",
        parse_mode="HTML",
    )
    await state.clear()
    await show_main_menu(message)


# ── /показания ───────────────────────────────

async def cmd_readings_start(callback: CallbackQuery, state: FSMContext):
    data = load_data()
    if not is_setup_complete(data):
        await callback.message.answer("⚠️ Сначала завершите настройку (/старт).")
        await callback.answer()
        return

    prev_hvs = get_last_meter_reading("hvs", data)
    await callback.message.answer(
        f"📊 <b>Ввод показаний за {month_key_to_name(get_current_month_key())}</b>\n\n"
        f"📏 <b>ХВС</b> (м³)\nПредыдущее: {fmt_num(prev_hvs)}\nВведите текущее:",
        parse_mode="HTML",
    )
    await state.set_state(InputReadings.waiting_hvs)
    await callback.answer()


async def input_hvs(message: Message, state: FSMContext):
    data = load_data()
    prev = get_last_meter_reading("hvs", data)
    try:
        val = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("❌ Введите корректное число.")
        return
    if not validate_readings(val, prev):
        await message.answer(
            f"❌ Показание ({fmt_num(val)}) должно быть больше предыдущего ({fmt_num(prev)}). Повторите ввод."
        )
        return

    await state.update_data(hvs=val)
    prev_gvs = get_last_meter_reading("gvs", data)
    await message.answer(
        f"📏 <b>ГВС</b> (м³)\nПредыдущее: {fmt_num(prev_gvs)}\nВведите текущее:",
        parse_mode="HTML",
    )
    await state.set_state(InputReadings.waiting_gvs)


async def input_gvs(message: Message, state: FSMContext):
    data = load_data()
    prev = get_last_meter_reading("gvs", data)
    try:
        val = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("❌ Введите корректное число.")
        return
    if not validate_readings(val, prev):
        await message.answer(
            f"❌ Показание ({fmt_num(val)}) должно быть больше предыдущего ({fmt_num(prev)}). Повторите ввод."
        )
        return

    await state.update_data(gvs=val)
    prev_gas = get_last_meter_reading("gas", data)
    await message.answer(
        f"🔥 <b>Газ</b> (м³)\nПредыдущее: {fmt_num(prev_gas)}\nВведите текущее:",
        parse_mode="HTML",
    )
    await state.set_state(InputReadings.waiting_gas)


async def input_gas(message: Message, state: FSMContext):
    data = load_data()
    prev = get_last_meter_reading("gas", data)
    try:
        val = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("❌ Введите корректное число.")
        return
    if not validate_readings(val, prev):
        await message.answer(
            f"❌ Показание ({fmt_num(val)}) должно быть больше предыдущего ({fmt_num(prev)}). Повторите ввод."
        )
        return

    await state.update_data(gas=val)
    prev_ee = get_last_meter_reading("electricity", data)
    await message.answer(
        f"💡 <b>Электро</b> (кВт·ч)\nПредыдущее: {fmt_num(prev_ee)}\nВведите текущее:",
        parse_mode="HTML",
    )
    await state.set_state(InputReadings.waiting_electricity)


async def input_electricity(message: Message, state: FSMContext):
    data = load_data()
    prev = get_last_meter_reading("electricity", data)
    try:
        val = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("❌ Введите корректное число.")
        return
    if not validate_readings(val, prev):
        await message.answer(
            f"❌ Показание ({fmt_num(val)}) должно быть больше предыдущего ({fmt_num(prev)}). Повторите ввод."
        )
        return

    fs_data = await state.get_data()
    readings = {
        "hvs": fs_data["hvs"],
        "gvs": fs_data["gvs"],
        "gas": fs_data["gas"],
        "electricity": val,
    }

    prev_readings = {
        "hvs": get_last_meter_reading("hvs", data),
        "gvs": get_last_meter_reading("gvs", data),
        "gas": get_last_meter_reading("gas", data),
        "electricity": get_last_meter_reading("electricity", data),
    }

    tariffs = data["tariffs"]
    month_key = get_current_month_key()

    # Сохраняем показания
    add_meter_readings(month_key, readings, data)

    # Рассчитываем квитанцию
    receipt = calculate_receipt(readings, prev_readings, tariffs)
    add_receipt(month_key, receipt, data)
    save_data(data)

    # Формируем сообщение
    c = receipt["consumption"]
    text = (
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Квитанция за {month_key_to_name(month_key)}</b>\n\n"
        f"💧 Водоснабжение:  <b>{fmt_money(receipt['water'])}</b>\n"
        f"🚿 Водоотведение:  <b>{fmt_money(receipt['sewage'])}</b>\n"
        f"🔥 Газ:            <b>{fmt_money(receipt['gas'])}</b>\n"
        f"💡 Электро:        <b>{fmt_money(receipt['electricity'])}</b>\n"
        f"♨️ Подогрев:       <b>{fmt_money(receipt['heating'])}</b>\n"
        f"───────────────────────\n"
        f"💰 <b>Итого: {fmt_money(receipt['total'])}</b>\n\n"
        f"📊 <b>Расход:</b>\n"
        f"  ХВС: {fmt_num(c['hvs'])} м³ | ГВС: {fmt_num(c['gvs'])} м³\n"
        f"  Газ: {fmt_num(c['gas'])} м³ | Электро: {fmt_num(c['electricity'])} кВт·ч\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ Квитанция сохранена!"
    )
    await message.answer(text, parse_mode="HTML")
    await state.clear()
    await show_main_menu(message)


# ── /расчёт ──────────────────────────────────

async def cmd_calc(callback: CallbackQuery):
    data = load_data()
    receipts = data.get("receipts", {})
    if not receipts:
        await callback.message.answer("📭 Нет сохранённых квитанций.")
        await callback.answer()
        return

    last_key = get_sorted_month_keys(receipts)[-1]
    r = receipts[last_key]

    c = r.get("consumption", {})
    text = (
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Последняя квитанция ({month_key_to_name(last_key)})</b>\n\n"
        f"💧 Водоснабжение:  <b>{fmt_money(r['water'])}</b>\n"
        f"🚿 Водоотведение:  <b>{fmt_money(r['sewage'])}</b>\n"
        f"🔥 Газ:            <b>{fmt_money(r['gas'])}</b>\n"
        f"💡 Электро:        <b>{fmt_money(r['electricity'])}</b>\n"
        f"♨️ Подогрев:       <b>{fmt_money(r['heating'])}</b>\n"
        f"───────────────────────\n"
        f"💰 <b>Итого: {fmt_money(r['total'])}</b>\n"
    )
    if c:
        text += (
            f"\n📊 <b>Расход:</b>\n"
            f"  ХВС: {fmt_num(c.get('hvs', 0))} м³ | ГВС: {fmt_num(c.get('gvs', 0))} м³\n"
            f"  Газ: {fmt_num(c.get('gas', 0))} м³ | Электро: {fmt_num(c.get('electricity', 0))} кВт·ч\n"
        )
    text += "━━━━━━━━━━━━━━━━━━━━━"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


# ── /итого ───────────────────────────────────

async def cmd_total(callback: CallbackQuery):
    await callback.message.answer(
        "📈 <b>Итого</b>\n\nВыберите период:",
        reply_markup=period_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


async def period_selected(callback: CallbackQuery):
    data = load_data()
    receipts = data.get("receipts", {})
    if not receipts:
        await callback.message.answer("📭 Нет сохранённых квитанций.")
        await callback.answer()
        return

    period = callback.data.replace("period_", "")
    all_keys = get_sorted_month_keys(receipts)

    if period == "all":
        keys = all_keys
        period_name = "всё время"
    else:
        from datetime import datetime
        now = datetime.now()
        keys = []
        months_back = {"month": 1, "half_year": 6, "year": 12}.get(period, 12)
        for i in range(months_back):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            key = f"{m:02d}.{y}"
            if key in receipts:
                keys.append(key)
        period_names = {"month": "месяц", "half_year": "полгода", "year": "год"}
        period_name = period_names.get(period, "период")

    if not keys:
        await callback.message.answer(f"📭 Нет квитанций за {period_name}.")
        await callback.answer()
        return

    # По месяцам
    monthly_lines = []
    sum_water = sum_sewage = sum_gas = sum_ee = sum_heating = sum_total = 0

    for key in keys:
        r = receipts[key]
        monthly_lines.append(f"  {month_key_to_name(key)}: <b>{fmt_money(r['total'])}</b>")
        sum_water += r.get("water", 0)
        sum_sewage += r.get("sewage", 0)
        sum_gas += r.get("gas", 0)
        sum_ee += r.get("electricity", 0)
        sum_heating += r.get("heating", 0)
        sum_total += r.get("total", 0)

    # По категориям
    categories = [
        ("💧 Водоснабжение", sum_water),
        ("🚿 Водоотведение", sum_sewage),
        ("🔥 Газ", sum_gas),
        ("💡 Электро", sum_ee),
        ("♨️ Подогрев", sum_heating),
    ]

    cat_lines = []
    for name, val in categories:
        pct = (val / sum_total * 100) if sum_total else 0
        cat_lines.append(f"  {name}: <b>{fmt_money(val)}</b> ({pct:.1f}%)")

    text = (
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Отчёт за {period_name}</b>\n\n"
        f"<b>По месяцам:</b>\n" + "\n".join(monthly_lines) + "\n\n"
        f"<b>По категориям:</b>\n" + "\n".join(cat_lines) + "\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Общая сумма: {fmt_money(sum_total)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


# ── /история ─────────────────────────────────

async def cmd_history(callback: CallbackQuery):
    data = load_data()
    receipts = data.get("receipts", {})
    if not receipts:
        await callback.message.answer("📭 Нет сохранённых квитанций.")
        await callback.answer()
        return

    keys = get_sorted_month_keys(receipts)
    lines = []
    for key in keys:
        r = receipts[key]
        lines.append(f"  {month_key_to_name(key)}: <b>{fmt_money(r['total'])}</b>")

    total_all = sum(r.get("total", 0) for r in receipts.values())

    text = (
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📜 <b>История квитанций</b>\n\n"
        + "\n".join(lines) +
        f"\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Всего: {fmt_money(total_all)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 Для деталей введите <code>/детали ММ.ГГГГ</code>\n"
        f"   Например: <code>/детали 01.2025</code>"
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


# ── /детали ММ.ГГГГ ──────────────────────────

async def cmd_details(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "ℹ️ Использование: <code>/детали ММ.ГГГГ</code>\n"
            "Например: <code>/детали 01.2025</code>",
            parse_mode="HTML",
        )
        return

    month_key = parts[1].strip()
    data = load_data()
    receipts = data.get("receipts", {})

    if month_key not in receipts:
        await message.answer(f"❌ Квитанция за {month_key} не найдена.")
        return

    r = receipts[month_key]
    c = r.get("consumption", {})
    t = r.get("tariffs_used", {})

    text = (
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Квитанция за {month_key_to_name(month_key)}</b>\n\n"
        f"💧 Водоснабжение:  <b>{fmt_money(r['water'])}</b>\n"
        f"🚿 Водоотведение:  <b>{fmt_money(r['sewage'])}</b>\n"
        f"🔥 Газ:            <b>{fmt_money(r['gas'])}</b>\n"
        f"💡 Электро:        <b>{fmt_money(r['electricity'])}</b>\n"
        f"♨️ Подогрев:       <b>{fmt_money(r['heating'])}</b>\n"
        f"───────────────────────\n"
        f"💰 <b>Итого: {fmt_money(r['total'])}</b>\n"
    )

    if c:
        text += (
            f"\n📊 <b>Расход:</b>\n"
            f"  ХВС: {fmt_num(c.get('hvs', 0))} м³ | ГВС: {fmt_num(c.get('gvs', 0))} м³\n"
            f"  Газ: {fmt_num(c.get('gas', 0))} м³ | Электро: {fmt_num(c.get('electricity', 0))} кВт·ч\n"
        )

    if t:
        text += (
            f"\n⚙️ <b>Тарифы:</b>\n"
            f"💧 {fmt_money(t.get('water', 0))}/м³ | 🚿 {fmt_money(t.get('sewage', 0))}/м³\n"
            f"🔥 {fmt_money(t.get('gas', 0))}/м³ | 💡 {fmt_money(t.get('electricity', 0))}/кВт·ч\n"
            f"♨️ {fmt_money(t.get('heating', 0))}/м³\n"
        )

    text += "━━━━━━━━━━━━━━━━━━━━━"
    await message.answer(text, parse_mode="HTML")


# ── /удалить ─────────────────────────────────

async def cmd_delete(callback: CallbackQuery, state: FSMContext):
    data = load_data()
    if not data.get("receipts"):
        await callback.message.answer("📭 Нет квитанций для удаления.")
        await callback.answer()
        return

    await callback.message.answer(
        "🗑 <b>Удаление квитанции</b>\n\n"
        "Введите месяц и год в формате <code>ММ.ГГГГ</code>:\n"
        "Например: <code>01.2025</code>",
        parse_mode="HTML",
    )
    await state.set_state(DeleteReceiptState.waiting_month)
    await callback.answer()


async def delete_month_input(message: Message, state: FSMContext):
    month_key = message.text.strip()
    data = load_data()

    if month_key not in data.get("receipts", {}):
        await message.answer(
            f"❌ Квитанция за {month_key} не найдена.\n"
            f"Введите <code>ММ.ГГГГ</code> (например, <code>01.2025</code>):",
            parse_mode="HTML",
        )
        return

    r = data["receipts"][month_key]
    await state.update_data(delete_month=month_key)

    await message.answer(
        f"⚠️ <b>Удалить квитанцию за {month_key_to_name(month_key)}</b>\n"
        f"Итого: <b>{fmt_money(r['total'])}</b>\n\n"
        f"Вы уверены?",
        reply_markup=confirm_keyboard(),
        parse_mode="HTML",
    )
    await state.set_state(DeleteReceiptState.waiting_confirm)


async def delete_confirm(callback: CallbackQuery, state: FSMContext):
    if callback.data == "confirm_yes":
        fs_data = await state.get_data()
        month_key = fs_data.get("delete_month")
        data = load_data()
        if delete_receipt(month_key, data):
            save_data(data)
            await callback.message.answer(
                f"✅ Квитанция за {month_key_to_name(month_key)} удалена."
            )
        else:
            await callback.message.answer("❌ Ошибка при удалении.")
    else:
        await callback.message.answer("❎ Удаление отменено.")

    await state.clear()
    await callback.answer()
    await show_main_menu(callback.message)


# ── Тарифы ───────────────────────────────────

async def cmd_tariffs(callback: CallbackQuery, state: FSMContext):
    data = load_data()
    t = data["tariffs"]

    text = (
        f"⚙️ <b>Текущие тарифы</b>\n\n"
        f"💧 Водоснабжение:  <b>{fmt_money(t['water'])}</b>/м³\n"
        f"🚿 Водоотведение:  <b>{fmt_money(t['sewage'])}</b>/м³\n"
        f"🔥 Газ:            <b>{fmt_money(t['gas'])}</b>/м³\n"
        f"💡 Электро:        <b>{fmt_money(t['electricity'])}</b>/кВт·ч\n"
        f"♨️ Подогрев:       <b>{fmt_money(t['heating'])}</b>/м³\n\n"
        f"Выберите тариф для изменения:"
    )
    await callback.message.answer(text, reply_markup=tariff_keyboard(), parse_mode="HTML")
    await callback.answer()


async def tariff_selected(callback: CallbackQuery, state: FSMContext):
    tariff_key = callback.data.replace("tariff_", "")
    names = {
        "water": "водоснабжения (₽/м³)",
        "sewage": "водоотведения (₽/м³)",
        "gas": "газа (₽/м³)",
        "electricity": "электро (₽/кВт·ч)",
        "heating": "подогрева (₽/м³)",
    }
    await state.update_data(tariff_key=tariff_key)
    await callback.message.answer(
        f"Введите новый тариф {names.get(tariff_key, tariff_key)}:"
    )
    await state.set_state(ChangeTariffs.waiting_value)
    await callback.answer()


async def tariff_value_input(message: Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        if val <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное положительное число.")
        return

    fs_data = await state.get_data()
    tariff_key = fs_data.get("tariff_key")

    data = load_data()
    data["tariffs"][tariff_key] = val
    save_data(data)

    names = {
        "water": "💧 Водоснабжение",
        "sewage": "🚿 Водоотведение",
        "gas": "🔥 Газ",
        "electricity": "💡 Электро",
        "heating": "♨️ Подогрев",
    }
    await message.answer(
        f"✅ Тариф {names.get(tariff_key, tariff_key)} обновлён: <b>{fmt_money(val)}</b>",
        parse_mode="HTML",
    )
    await state.clear()


# ── Экспорт ──────────────────────────────────

async def cmd_export(callback: CallbackQuery):
    data_file = "data.json"
    if not os.path.exists(data_file):
        await callback.message.answer("❌ Файл данных не найден.")
        await callback.answer()
        return

    file = FSInputFile(data_file, filename="data.json")
    await callback.message.answer_document(
        document=file,
        caption="📤 <b>Экспорт данных</b>",
        parse_mode="HTML",
    )
    await callback.answer()


# ── Помощь ───────────────────────────────────

async def cmd_help(message: Message):
    text = (
        "📖 <b>Справка</b>\n\n"
        "<b>Команды:</b>\n"
        "/старт — запуск / главное меню\n"
        "/показания — ввод текущих показаний счётчиков\n"
        "/расчёт — показать последнюю квитанцию\n"
        "/итого — сумма за период (месяц / полгода / год / всё)\n"
        "/история — история квитанций\n"
        "/детали ММ.ГГГГ — детали конкретной квитанции\n"
        "/удалить — удалить квитанцию\n"
        "/тариф — показать / изменить тарифы\n"
        "/экспорт — скачать данные (data.json)\n"
        "/помощь — эта справка\n\n"
        "<b>Формулы расчёта:</b>\n"
        "💧 Водоснабжение = (ΔХВС + ΔГВС) × тариф\n"
        "🚿 Водоотведение = (ΔХВС + ΔГВС) × тариф\n"
        "🔥 Газ = ΔГаз × тариф\n"
        "💡 Электро = ΔЭлектро × тариф\n"
        "♨️ Подогрев = ΔГВС × тариф × 0.0609\n"
        "💰 Итого = сумма всех категорий\n\n"
        "<b>Валидация:</b>\n"
        "Текущие показания счётчиков должны быть больше предыдущих."
    )
    await message.answer(text, parse_mode="HTML")


# ── Callback: назад / главное меню ───────────

async def back_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_main_menu(callback.message)
    await callback.answer()


# ── Callback: кнопка «Показания» ─────────────

async def cmd_readings_message(message: Message, state: FSMContext):
    """Обработчик текстовой команды /показания."""
    data = load_data()
    if not is_setup_complete(data):
        await message.answer("⚠️ Сначала завершите настройку (/старт).")
        return

    prev_hvs = get_last_meter_reading("hvs", data)
    await message.answer(
        f"📊 <b>Ввод показаний за {month_key_to_name(get_current_month_key())}</b>\n\n"
        f"📏 <b>КХВС</b> (м³)\nПредыдущее: {fmt_num(prev_hvs)}\nВведите текущее:",
        parse_mode="HTML",
    )
    await state.set_state(InputReadings.waiting_hvs)


# ── Callback: кнопка «Расчёт» ────────────────

async def cmd_calc_message(message: Message):
    data = load_data()
    receipts = data.get("receipts", {})
    if not receipts:
        await message.answer("📭 Нет сохранённых квитанций.")
        return

    last_key = get_sorted_month_keys(receipts)[-1]
    r = receipts[last_key]
    c = r.get("consumption", {})

    text = (
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Последняя квитанция ({month_key_to_name(last_key)})</b>\n\n"
        f"💧 Водоснабжение:  <b>{fmt_money(r['water'])}</b>\n"
        f"🚿 Водоотведение:  <b>{fmt_money(r['sewage'])}</b>\n"
        f"🔥 Газ:            <b>{fmt_money(r['gas'])}</b>\n"
        f"💡 Электро:        <b>{fmt_money(r['electricity'])}</b>\n"
        f"♨️ Подогрев:       <b>{fmt_money(r['heating'])}</b>\n"
        f"───────────────────────\n"
        f"💰 <b>Итого: {fmt_money(r['total'])}</b>\n"
    )
    if c:
        text += (
            f"\n📊 <b>Расход:</b>\n"
            f"  ХВС: {fmt_num(c.get('hvs', 0))} м³ | ГВС: {fmt_num(c.get('gvs', 0))} м³\n"
            f"  Газ: {fmt_num(c.get('gas', 0))} м³ | Электро: {fmt_num(c.get('electricity', 0))} кВт·ч\n"
        )
    text += "━━━━━━━━━━━━━━━━━━━━━"
    await message.answer(text, parse_mode="HTML")


# ── Callback: кнопка «Итого» ─────────────────

async def cmd_total_message(message: Message):
    await message.answer(
        "📈 <b>Итого</b>\n\nВыберите период:",
        reply_markup=period_keyboard(),
        parse_mode="HTML",
    )


# ── Callback: кнопка «История» ───────────────

async def cmd_history_message(message: Message):
    data = load_data()
    receipts = data.get("receipts", {})
    if not receipts:
        await message.answer("📭 Нет сохранённых квитанций.")
        return

    keys = get_sorted_month_keys(receipts)
    lines = []
    for key in keys:
        r = receipts[key]
        lines.append(f"  {month_key_to_name(key)}: <b>{fmt_money(r['total'])}</b>")

    total_all = sum(r.get("total", 0) for r in receipts.values())

    text = (
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📜 <b>История квитанций</b>\n\n"
        + "\n".join(lines) +
        f"\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Всего: {fmt_money(total_all)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 Для деталей: <code>/детали ММ.ГГГГ</code>"
    )
    await message.answer(text, parse_mode="HTML")


# ── Callback: кнопка «Удалить» ───────────────

async def cmd_delete_message(message: Message, state: FSMContext):
    data = load_data()
    if not data.get("receipts"):
        await message.answer("📭 Нет квитанций для удаления.")
        return

    await message.answer(
        "🗑 <b>Удаление квитанции</b>\n\n"
        "Введите месяц и год в формате <code>ММ.ГГГГ</code>:\n"
        "Например: <code>01.2025</code>",
        parse_mode="HTML",
    )
    await state.set_state(DeleteReceiptState.waiting_month)


# ── Callback: кнопка «Тарифы» ────────────────

async def cmd_tariffs_message(message: Message):
    data = load_data()
    t = data["tariffs"]

    text = (
        f"⚙️ <b>Текущие тарифы</b>\n\n"
        f"💧 Водоснабжение:  <b>{fmt_money(t['water'])}</b>/м³\n"
        f"🚿 Водоотведение:  <b>{fmt_money(t['sewage'])}</b>/м³\n"
        f"🔥 Газ:            <b>{fmt_money(t['gas'])}</b>/м³\n"
        f"💡 Электро:        <b>{fmt_money(t['electricity'])}</b>/кВт·ч\n"
        f"♨️ Подогрев:       <b>{fmt_money(t['heating'])}</b>/м³\n\n"
        f"Выберите тариф для изменения:"
    )
    await message.answer(text, reply_markup=tariff_keyboard(), parse_mode="HTML")


# ── Callback: кнопка «Экспорт» ───────────────

async def cmd_export_message(message: Message):
    data_file = "data.json"
    if not os.path.exists(data_file):
        await message.answer("❌ Файл данных не найден.")
        return

    file = FSInputFile(data_file, filename="data.json")
    await message.answer_document(
        document=file,
        caption="📤 <b>Экспорт данных</b>",
        parse_mode="HTML",
    )


# ── Регистрация хендлеров ────────────────────

def register_handlers(dp: Dispatcher):
    # Команды
    dp.message.register(cmd_start, Command("старт", "start"))
    dp.message.register(cmd_readings_message, Command("показания", "readings"))
    dp.message.register(cmd_calc_message, Command("расчёт", "расчет", "calc"))
    dp.message.register(cmd_total_message, Command("итого", "total"))
    dp.message.register(cmd_history_message, Command("история", "history"))
    dp.message.register(cmd_details, Command("детали", "details"))
    dp.message.register(cmd_delete_message, Command("удалить", "delete"))
    dp.message.register(cmd_tariffs_message, Command("тариф", "tariff"))
    dp.message.register(cmd_export_message, Command("экспорт", "export"))
    dp.message.register(cmd_help, Command("помощь", "help"))

    # FSM: настройка начальных показаний
    dp.message.register(setup_hvs, SetupInitialReadings.waiting_hvs)
    dp.message.register(setup_gvs, SetupInitialReadings.waiting_gvs)
    dp.message.register(setup_gas, SetupInitialReadings.waiting_gas)
    dp.message.register(setup_electricity, SetupInitialReadings.waiting_electricity)

    # FSM: настройка тарифов
    dp.message.register(setup_tariff_water, SetupTariffs.waiting_water)
    dp.message.register(setup_tariff_sewage, SetupTariffs.waiting_sewage)
    dp.message.register(setup_tariff_gas, SetupTariffs.waiting_gas)
    dp.message.register(setup_tariff_electricity, SetupTariffs.waiting_electricity)
    dp.message.register(setup_tariff_heating, SetupTariffs.waiting_heating)

    # FSM: ввод показаний
    dp.message.register(input_hvs, InputReadings.waiting_hvs)
    dp.message.register(input_gvs, InputReadings.waiting_gvs)
    dp.message.register(input_gas, InputReadings.waiting_gas)
    dp.message.register(input_electricity, InputReadings.waiting_electricity)

    # FSM: изменение тарифов
    dp.message.register(tariff_value_input, ChangeTariffs.waiting_value)

    # FSM: удаление квитанции
    dp.message.register(delete_month_input, DeleteReceiptState.waiting_month)

    # Callback-кнопки
    dp.callback_query.register(cmd_readings_start, F.data == "cmd_readings")
    dp.callback_query.register(cmd_calc, F.data == "cmd_calc")
    dp.callback_query.register(cmd_total, F.data == "cmd_total")
    dp.callback_query.register(period_selected, F.data.startswith("period_"))
    dp.callback_query.register(cmd_history, F.data == "cmd_history")
    dp.callback_query.register(cmd_delete, F.data == "cmd_delete")
    dp.callback_query.register(delete_confirm, F.data.in_({"confirm_yes", "confirm_no"}))
    dp.callback_query.register(cmd_tariffs, F.data == "cmd_tariffs")
    dp.callback_query.register(tariff_selected, F.data.startswith("tariff_"))
    dp.callback_query.register(cmd_export, F.data == "cmd_export")
    dp.callback_query.register(back_main, F.data == "back_main")