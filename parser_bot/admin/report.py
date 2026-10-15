import time
from datetime import datetime
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup as IKM,
    InlineKeyboardButton as IKB
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatType

from config import ADMIN_IDS
from database import (
    get_report_template, update_report_template,
    get_stats_for_period
)
from stats_utils import (
    get_current_day_start, get_current_day_end,
    get_current_week_start, get_current_month_start,
    calc_stats, format_volume, format_price, now_msk
)
from tpl.emoji import rebuild_text_with_emoji

router = Router()


class ReportStates(StatesGroup):
    edit_template = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def report_kb(send_to_channel: bool) -> IKM:
    toggle_text = (
        "📺 В канал: ✅ ВКЛ" if send_to_channel
        else "📺 В канал: ❌ ВЫКЛ"
    )
    return IKM(inline_keyboard=[
        [IKB(text="📝 Редактировать шаблон", callback_data="report_edit_tpl")],
        [IKB(text=toggle_text, callback_data="report_toggle_channel")],
        [IKB(text="👁 Предпросмотр", callback_data="report_preview")],
        [
            IKB(text="📅 День", callback_data="report_stats_day"),
            IKB(text="📆 Неделя", callback_data="report_stats_week"),
            IKB(text="🗓 Месяц", callback_data="report_stats_month"),
        ],
        [IKB(text="⬅️ Назад", callback_data="admin_main")],
    ])


@router.callback_query(F.data == "admin_report")
async def cb_report_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    tpl = get_report_template()
    send_to_channel = bool(tpl.get("send_to_channel", ''))
    template = tpl.get("template", "—")

    current = now_msk()

    await callback.message.edit_text(
        f"📊 <b>Ежедневный отчёт</b>\n\n"
        f"⏰ Отправка: 02:00 MSK\n"
        f"📺 В канал: {'✅' if send_to_channel else '❌'}\n"
        f"🕐 Сейчас: {current.strftime('%H:%M MSK %d.%m')}\n\n"
        f"📝 Шаблон:\n<code>{template}</code>\n\n"
        f"<b>Переменные:</b>\n"
        f"<code>{{order_count}}</code> — кол-во ордеров\n"
        f"<code>{{total_volume}}</code> — сумма средств\n"
        f"<code>{{avg_price}}</code> — средний курс\n"
        f"<code>{{period}}</code> — название периода",
        parse_mode="HTML",
        reply_markup=report_kb(send_to_channel)
    )
    await callback.answer()


@router.callback_query(F.data == "report_edit_tpl")
async def cb_edit_report_tpl(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(ReportStates.edit_template)
    await callback.message.edit_text(
        "📝 Отправьте новый шаблон отчёта.\n"
        "Поддерживается HTML.\n\n"
        "Переменные:\n"
        "<code>{order_count}</code>, <code>{total_volume}</code>, "
        "<code>{avg_price}</code>, <code>{period}</code>",
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="❌ Отмена", callback_data="admin_report")]
        ])
    )
    await callback.answer()


@router.message(ReportStates.edit_template, F.chat.type == ChatType.PRIVATE)
async def handle_edit_report_tpl(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()

    text = rebuild_text_with_emoji(message)
    update_report_template(template=text)

    tpl = get_report_template()
    send_to_channel = bool(tpl.get("send_to_channel", ''))

    await message.answer(
        "✅ Шаблон отчёта обновлён!",
        reply_markup=report_kb(send_to_channel)
    )


@router.callback_query(F.data == "report_toggle_channel")
async def cb_toggle_channel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    tpl = get_report_template()
    current = bool(tpl.get("send_to_channel", ''))
    new_val = 0 if current else 1
    update_report_template(send_to_channel=new_val)

    status = "✅ Включена" if new_val else "❌ Выключена"
    await callback.answer(f"📺 Отправка в канал: {status}", show_alert=True)
    await cb_report_menu(callback)


@router.callback_query(F.data == "report_preview")
async def cb_preview(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    tpl = get_report_template()
    template = tpl.get("template", "")

    if not template:
        await callback.answer("Шаблон пуст", show_alert=True)
        return

    text = template.replace(
        "{order_count}", "42"
    ).replace(
        "{total_volume}", "1 250 000"
    ).replace(
        "{avg_price}", "84.32"
    ).replace(
        "{period}", "24ч"
    )

    await callback.message.answer(
        f"👁 <b>Предпросмотр:</b>\n\n{text}",
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="⬅️ Назад", callback_data="admin_report")]
        ])
    )
    await callback.answer()


# ═══ Статистика по периодам ═══

@router.callback_query(F.data == "report_stats_day")
async def cb_stats_day(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    day_start = get_current_day_start()
    day_end = get_current_day_end()
    stats = get_stats_for_period(day_start, day_end)
    c = calc_stats(stats)

    start_dt = datetime.fromtimestamp(day_start).strftime("%d.%m %H:%M")
    current = now_msk().strftime("%d.%m %H:%M")

    await callback.message.edit_text(
        f"📅 <b>Статистика за текущий день</b>\n"
        f"<i>{start_dt} → {current} MSK</i>\n\n"
        f"⚠️ Кол-во ордеров: <b>{c['order_count']}</b>\n"
        f"⚠️ Сумма средств: <b>{format_volume(c['total_volume'])}</b>\n"
        f"🛍 Средний курс: <b>{format_price(c['avg_price'])}</b>\n\n"
        f"<i>Сброс в 02:00 MSK</i>",
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="🔄 Обновить", callback_data="report_stats_day")],
            [IKB(text="⬅️ Назад", callback_data="admin_report")],
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "report_stats_week")
async def cb_stats_week(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    week_start = get_current_week_start()
    now = time.time()
    stats = get_stats_for_period(week_start, now)
    c = calc_stats(stats)

    start_dt = datetime.fromtimestamp(week_start).strftime("%d.%m %H:%M")
    current = now_msk().strftime("%d.%m %H:%M")

    await callback.message.edit_text(
        f"📆 <b>Статистика за текущую неделю</b>\n"
        f"<i>{start_dt} → {current} MSK</i>\n\n"
        f"⚠️ Кол-во ордеров: <b>{c['order_count']}</b>\n"
        f"⚠️ Сумма средств: <b>{format_volume(c['total_volume'])}</b>\n"
        f"🛍 Средний курс: <b>{format_price(c['avg_price'])}</b>\n\n"
        f"<i>Сброс в понедельник 02:00 MSK</i>",
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="🔄 Обновить", callback_data="report_stats_week")],
            [IKB(text="⬅️ Назад", callback_data="admin_report")],
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "report_stats_month")
async def cb_stats_month(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    month_start = get_current_month_start()
    now = time.time()
    stats = get_stats_for_period(month_start, now)
    c = calc_stats(stats)

    start_dt = datetime.fromtimestamp(month_start).strftime("%d.%m %H:%M")
    current = now_msk().strftime("%d.%m %H:%M")

    await callback.message.edit_text(
        f"🗓 <b>Статистика за текущий месяц</b>\n"
        f"<i>{start_dt} → {current} MSK</i>\n\n"
        f"⚠️ Кол-во ордеров: <b>{c['order_count']}</b>\n"
        f"⚠️ Сумма средств: <b>{format_volume(c['total_volume'])}</b>\n"
        f"🛍 Средний курс: <b>{format_price(c['avg_price'])}</b>\n\n"
        f"<i>Сброс 1-го числа в 02:00 MSK</i>",
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="🔄 Обновить", callback_data="report_stats_month")],
            [IKB(text="⬅️ Назад", callback_data="admin_report")],
        ])
    )
    await callback.answer()