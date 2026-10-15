import re
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
    add_offer, remove_offer, set_offer_tracking,
    get_all_offers, get_offer
)

router = Router()

OFFER_RE = re.compile(r'(?:t\.me/send\?start=O|offers/)(\d+)')


class OfferStates(StatesGroup):
    add_offer = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def offers_main_kb() -> IKM:
    return IKM(inline_keyboard=[
        [IKB(text="➕ Добавить оффер", callback_data="add_offer")],
        [IKB(text="📋 Список офферов", callback_data="list_offers")],
        [IKB(text="⬅️ Назад", callback_data="admin_main")],
    ])


@router.callback_query(F.data == "admin_offers")
async def cb_offers_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    offers = get_all_offers()
    total = len(offers)
    tracking = sum(1 for o in offers if o["is_tracking"])
    open_count = sum(1 for o in offers if o["is_open"])

    await callback.message.edit_text(
        f"📦 <b>Офферы</b>\n\n"
        f"📊 Всего: {total}\n"
        f"👁 Отслеживается: {tracking}\n"
        f"🟢 Открыто: {open_count}",
        parse_mode="HTML",
        reply_markup=offers_main_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "add_offer")
async def cb_add_offer(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(OfferStates.add_offer)
    await callback.message.edit_text(
        "📎 Отправьте ссылку на оффер:\n\n"
        "<code>https://t.me/send?start=O2452434</code>\n"
        "или просто ID: <code>2452434</code>",
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="❌ Отмена", callback_data="admin_offers")]
        ])
    )
    await callback.answer()


@router.message(OfferStates.add_offer, F.chat.type == ChatType.PRIVATE)
async def handle_add_offer(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()

    text = message.text.strip()

    # Парсим offer_id
    match = OFFER_RE.search(text)
    if match:
        offer_id = int(match.group(1))
    elif text.isdigit():
        offer_id = int(text)
    else:
        await message.answer(
            "❌ Не удалось найти ID оффера",
            reply_markup=offers_main_kb()
        )
        return

    existing = get_offer(offer_id)
    if existing:
        await message.answer(
            f"⚠️ Оффер #{offer_id} уже добавлен",
            reply_markup=offers_main_kb()
        )
        return

    add_offer(offer_id)
    await message.answer(
        f"✅ Оффер <b>#{offer_id}</b> добавлен!\n"
        f"🔗 <code>https://t.me/send?start=O{offer_id}</code>",
        parse_mode="HTML",
        reply_markup=offers_main_kb()
    )


@router.callback_query(F.data == "list_offers")
async def cb_list_offers(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    offers = get_all_offers()
    if not offers:
        await callback.message.edit_text(
            "📦 Нет офферов",
            reply_markup=offers_main_kb()
        )
        await callback.answer()
        return

    buttons = []
    for o in offers[:20]:
        status = "🟢" if o["is_open"] else "🔴"
        tracking = "👁" if o["is_tracking"] else "💤"
        price = o.get("last_price") or "?"

        buttons.append([
            IKB(
                text=f"{status}{tracking} #{o['offer_id']} | {price}",
                callback_data=f"offer_detail_{o['offer_id']}"
            )
        ])

    buttons.append([
        IKB(text="⬅️ Назад", callback_data="admin_offers")
    ])

    await callback.message.edit_text(
        "📋 <b>Офферы:</b>",
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("offer_detail_"))
async def cb_offer_detail(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    offer_id = int(callback.data.split("_")[2])
    o = get_offer(offer_id)
    if not o:
        await callback.answer("Не найден", show_alert=True)
        return

    status = "🟢 Открыт" if o["is_open"] else "🔴 Закрыт"
    tracking = "👁 Отслеживается" if o["is_tracking"] else "💤 Приостановлен"

    text = (
        f"📦 <b>Оффер #{o['offer_id']}</b>\n\n"
        f"{status}\n"
        f"{tracking}\n"
        f"💰 Цена: {o.get('last_price') or '?'}\n"
        f"📊 Лимиты: {o.get('last_limits_min', '?')} — "
        f"{o.get('last_limits_max', '?')}\n"
        f"🏷 API статус: {o.get('last_status', '?')}\n"
        f"👁 is_visible: {bool(o.get('last_is_visible'))}\n"
        f"💬 msg_id: {o.get('channel_message_id', '0')}"
    )

    track_btn = (
        IKB(text="💤 Приостановить",
            callback_data=f"offer_pause_{offer_id}")
        if o["is_tracking"]
        else IKB(text="👁 Возобновить",
                 callback_data=f"offer_resume_{offer_id}")
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=[
            [track_btn],
            [IKB(text="🔄 Опросить сейчас",
                 callback_data=f"offer_poll_{offer_id}")],
            [IKB(text="🗑 Удалить",
                 callback_data=f"offer_delete_{offer_id}")],
            [IKB(text="⬅️ К списку", callback_data="list_offers")],
        ])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("offer_pause_"))
async def cb_pause(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    oid = int(callback.data.split("_")[2])
    set_offer_tracking(oid, False)
    await callback.answer("💤 Приостановлен")
    callback.data = f"offer_detail_{oid}"
    await cb_offer_detail(callback)


@router.callback_query(F.data.startswith("offer_resume_"))
async def cb_resume(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    oid = int(callback.data.split("_")[2])
    set_offer_tracking(oid, True)
    await callback.answer("👁 Возобновлен")
    callback.data = f"offer_detail_{oid}"
    await cb_offer_detail(callback)


@router.callback_query(F.data.startswith("offer_delete_"))
async def cb_delete(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    oid = int(callback.data.split("_")[2])
    remove_offer(oid)
    await callback.answer("🗑 Удалён")
    await cb_list_offers(callback)
