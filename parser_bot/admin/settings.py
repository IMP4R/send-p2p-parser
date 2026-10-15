from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup as IKM,
    InlineKeyboardButton as IKB
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatType
import logging

from config import ADMIN_IDS
from database import get_setting, set_setting
from api_client import MicroserviceClient

logger = logging.getLogger(__name__)

router = Router(name="settings")


class SettingsStates(StatesGroup):
    micro_ip = State()
    micro_port = State()
    micro_token = State()
    channel_id = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def settings_keyboard() -> IKM:
    return IKM(inline_keyboard=[
        [IKB(text="🌐 IP микросервиса", callback_data="set_micro_ip")],
        [IKB(text="🔌 Порт", callback_data="set_micro_port")],
        [IKB(text="🔑 API токен", callback_data="set_micro_token")],
        [IKB(text="🔗 Проверить связь", callback_data="check_micro")],
        [IKB(text="📺 Канал публикации", callback_data="set_channel")],
        [IKB(text="⬅️ Назад", callback_data="admin_main")],
    ])


@router.callback_query(F.data == "admin_settings")
async def cb_settings(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    ip = get_setting("micro_ip", "не задан")
    port = get_setting("micro_port", "8899")
    token = get_setting("micro_token")
    token_short = (token[:15] + "...") if token else "не задан"
    channel = get_setting("channel_id", "не задан")

    await callback.message.edit_text(
        f"⚙️ <b>Настройки</b>\n\n"
        f"🌐 IP: <code>{ip}</code>\n"
        f"🔌 Порт: <code>{port}</code>\n"
        f"🔑 Токен: <code>{token_short}</code>\n"
        f"📺 Канал: <code>{channel}</code>",
        parse_mode="HTML",
        reply_markup=settings_keyboard()
    )
    await callback.answer()


# ═══ IP ═══

@router.callback_query(F.data == "set_micro_ip")
async def cb_set_ip(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    
    logger.info(f">>> set_micro_ip: setting state")
    await state.set_state(SettingsStates.micro_ip)
    
    current = await state.get_state()
    logger.info(f">>> state after set: {current}")
    
    await callback.message.edit_text(
        "🌐 Введите IP адрес микросервиса:\n"
        "Пример: <code>127.0.0.1</code>",
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="❌ Отмена", callback_data="admin_settings")]
        ])
    )
    await callback.answer()


@router.message(SettingsStates.micro_ip)
async def handle_ip(message: Message, state: FSMContext):
    logger.info(f">>> handle_ip ВЫЗВАН: {message.text}")
    
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    set_setting("micro_ip", message.text.strip())
    await message.answer(
        f"✅ IP: <code>{message.text.strip()}</code>",
        parse_mode="HTML",
        reply_markup=settings_keyboard()
    )


# ═══ PORT ═══

@router.callback_query(F.data == "set_micro_port")
async def cb_set_port(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(SettingsStates.micro_port)
    await callback.message.edit_text(
        "🔌 Введите порт (по умолчанию 8899):",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="❌ Отмена", callback_data="admin_settings")]
        ])
    )
    await callback.answer()


@router.message(SettingsStates.micro_port)
async def handle_port(message: Message, state: FSMContext):
    logger.info(f">>> handle_port ВЫЗВАН: {message.text}")
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    set_setting("micro_port", message.text.strip())
    await message.answer(
        f"✅ Порт: <code>{message.text.strip()}</code>",
        parse_mode="HTML",
        reply_markup=settings_keyboard()
    )


# ═══ TOKEN ═══

@router.callback_query(F.data == "set_micro_token")
async def cb_set_token(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(SettingsStates.micro_token)
    await callback.message.edit_text(
        "🔑 Введите API токен:\n<code>stg_xxxxx...</code>",
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="❌ Отмена", callback_data="admin_settings")]
        ])
    )
    await callback.answer()


@router.message(SettingsStates.micro_token)
async def handle_token(message: Message, state: FSMContext):
    logger.info(f">>> handle_token ВЫЗВАН")
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    set_setting("micro_token", message.text.strip())
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer("✅ Токен сохранён", reply_markup=settings_keyboard())


# ═══ CHECK ═══

@router.callback_query(F.data == "check_micro")
async def cb_check(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    client = MicroserviceClient()
    health = await client.check_connection()
    if not health.get("ok"):
        await callback.answer(
            f"❌ Нет связи: {health.get('error', '?')}", show_alert=True
        )
        return
    auth = await client.check_auth()
    if auth.get("valid"):
        await callback.answer(
            f"✅ OK! user_id={auth.get('user_id')}", show_alert=True
        )
    else:
        await callback.answer("⚠️ Связь есть, токен невалиден", show_alert=True)


# ═══ CHANNEL ═══

@router.callback_query(F.data == "set_channel")
async def cb_set_channel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(SettingsStates.channel_id)
    await callback.message.edit_text(
        "📺 Введите ID канала (с минусом):\n"
        "<code>0</code>\n\n"
        "Или перешлите сообщение из канала",
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="❌ Отмена", callback_data="admin_settings")]
        ])
    )
    await callback.answer()


@router.message(SettingsStates.channel_id)
async def handle_channel(message: Message, state: FSMContext):
    logger.info(f">>> handle_channel ВЫЗВАН: {message.text}")
    if not is_admin(message.from_user.id):
        return
    await state.clear()

    if message.forward_from_chat:
        ch_id = str(message.forward_from_chat.id)
    else:
        ch_id = message.text.strip()

    set_setting("channel_id", ch_id)
    await message.answer(
        f"✅ Канал: <code>{ch_id}</code>",
        parse_mode="HTML",
        reply_markup=settings_keyboard()
    )