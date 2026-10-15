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
from database import get_account, save_account, deactivate_account
from api_client import MicroserviceClient
from send_client import SendTGClient

router = Router()

class AccountStates(StatesGroup):
    phone = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@router.callback_query(F.data == "admin_account")
async def cb_account(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    acc = get_account()
    if acc and acc["is_active"]:
        # Проверяем авторизацию
        client = SendTGClient()
        auth_ok = client.check_auth()

        status = "🟢 Активен" if auth_ok else "🔴 Куки истекли"
        phone = acc["phone"]

        await callback.message.edit_text(
            f"👤 <b>Аккаунт Send.TG</b>\n\n"
            f"📱 Телефон: <code>{phone}</code>\n"
            f"📊 Статус: {status}",
            parse_mode="HTML",
            reply_markup=IKM(inline_keyboard=[
                [IKB(
                    text="🔄 Перерегистрировать",
                    callback_data="reregister_account"
                )],
                [IKB(
                    text="🔑 Обновить куки",
                    callback_data="refresh_account"
                )],
                [IKB(
                    text="🗑 Удалить аккаунт",
                    callback_data="delete_account"
                )],
                [IKB(text="⬅️ Назад", callback_data="admin_main")],
            ])
        )
    else:
        await callback.message.edit_text(
            "👤 <b>Аккаунт не зарегистрирован</b>\n\n"
            "Зарегистрируйте аккаунт через микросервис:",
            parse_mode="HTML",
            reply_markup=IKM(inline_keyboard=[
                [IKB(
                    text="📝 Зарегистрировать",
                    callback_data="register_account"
                )],
                [IKB(text="⬅️ Назад", callback_data="admin_main")],
            ])
        )
    await callback.answer()


@router.callback_query(F.data.in_({"register_account", "reregister_account"}))
async def cb_register(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AccountStates.phone)
    await callback.message.edit_text(
        "📱 Введите номер телефона с +\n"
        "Пример: <code>+0</code>",
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="❌ Отмена", callback_data="admin_account")]
        ])
    )
    await callback.answer()


@router.message(AccountStates.phone, F.chat.type == ChatType.PRIVATE)
async def handle_phone(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    phone = message.text.strip()
    if not phone.startswith("+"):
        await message.answer("❌ Номер должен начинаться с +")
        return

    await state.clear()

    status_msg = await message.answer(
        f"⏳ Регистрирую {phone} через микросервис...\n"
        "Подтверди вход в Telegram на этом аккаунте!"
    )

    client = MicroserviceClient()
    result = await client.refresh_cookies(phone)

    if result.get("success"):
        cookies = result.get("cookies", [])
        save_account(phone, cookies)

        # Проверяем
        stg = SendTGClient()
        auth_ok = stg.check_auth()

        await status_msg.edit_text(
            f"✅ Аккаунт зарегистрирован!\n\n"
            f"📱 {phone}\n"
            f"🍪 {len(cookies)} кук\n"
            f"🔐 Авторизация: {'✅' if auth_ok else '❌'}",
            reply_markup=IKM(inline_keyboard=[
                [IKB(text="⬅️ К аккаунту", callback_data="admin_account")]
            ])
        )
    else:
        await status_msg.edit_text(
            f"❌ Ошибка: {result.get('message', '?')}",
            reply_markup=IKM(inline_keyboard=[
                [IKB(text="🔄 Попробовать снова",
                     callback_data="register_account")],
                [IKB(text="⬅️ Назад", callback_data="admin_account")]
            ])
        )


@router.callback_query(F.data == "refresh_account")
async def cb_refresh(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    acc = get_account()
    if not acc:
        await callback.answer("Нет аккаунта", show_alert=True)
        return

    await callback.message.edit_text(
        f"⏳ Обновляю куки для {acc['phone']}...\n"
        "Подтверди вход в Telegram!"
    )

    client = MicroserviceClient()
    result = await client.refresh_cookies(acc["phone"])

    if result.get("success"):
        cookies = result.get("cookies", [])
        save_account(acc["phone"], cookies)
        await callback.message.edit_text(
            f"✅ Куки обновлены! ({len(cookies)} шт)",
            reply_markup=IKM(inline_keyboard=[
                [IKB(text="⬅️", callback_data="admin_account")]
            ])
        )
    else:
        await callback.message.edit_text(
            f"❌ {result.get('message', '?')}",
            reply_markup=IKM(inline_keyboard=[
                [IKB(text="⬅️", callback_data="admin_account")]
            ])
        )


@router.callback_query(F.data == "delete_account")
async def cb_delete(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    deactivate_account()
    await callback.message.edit_text(
        "🗑 Аккаунт деактивирован",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="⬅️", callback_data="admin_main")]
        ])
    )
    await callback.answer()
