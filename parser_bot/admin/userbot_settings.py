from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup as IKM,
    InlineKeyboardButton as IKB
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatType
import time
import logging

from config import ADMIN_IDS, TELETHON_API_ID, TELETHON_API_HASH
from database import get_setting, get_stats_for_period
from channel_poster import ChannelPoster
from userbot import userbot
from stats_utils import (
    get_current_day_start, calc_stats,
    format_volume, format_price, now_msk
)
from database import get_report_template

logger = logging.getLogger(__name__)

router = Router()


class UserbotStates(StatesGroup):
    phone = State()
    code = State()
    password = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def userbot_kb(is_active: bool) -> IKM:
    if is_active:
        return IKM(inline_keyboard=[
            [IKB(text="🔄 Проверить", callback_data="ub_check")],
            [IKB(text="📤 Тестовое сообщение",
                 callback_data="ub_test_send")],
            [IKB(text="📊 Тестовая статистика",
                 callback_data="ub_test_stats")],
            [IKB(text="🗑 Удалить сессию",
                 callback_data="ub_delete_confirm")],
            [IKB(text="⬅️ Назад", callback_data="admin_main")],
        ])
    else:
        return IKM(inline_keyboard=[
            [IKB(text="📝 Авторизовать",
                 callback_data="ub_auth_start")],
            [IKB(text="⬅️ Назад", callback_data="admin_main")],
        ])


@router.callback_query(F.data == "admin_userbot")
async def cb_userbot_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    has_api = bool(TELETHON_API_ID and TELETHON_API_HASH)
    has_session = bool(get_setting("telethon_session"))

    if not has_api:
        await callback.message.edit_text(
            "🤖 <b>Юзербот (Telethon)</b>\n\n"
            "❌ <code>TELETHON_API_ID</code> и "
            "<code>TELETHON_API_HASH</code> не заданы!\n\n"
            "Установите их в переменных окружения или в config.py\n"
            "Получить: <a href='https://my.telegram.org'>my.telegram.org</a>",
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=IKM(inline_keyboard=[
                [IKB(text="⬅️ Назад", callback_data="admin_main")]
            ])
        )
        await callback.answer()
        return

    if has_session:
        auth = await userbot.check_auth()
        if auth.get("ok"):
            premium = "✅" if auth.get("premium") else "❌"
            await callback.message.edit_text(
                f"🤖 <b>Юзербот (Telethon)</b>\n\n"
                f"✅ Авторизован\n"
                f"👤 {auth.get('name', '?')}\n"
                f"🆔 <code>{auth.get('user_id', '?')}</code>\n"
                f"📱 <code>{auth.get('phone', '?')}</code>\n"
                f"⭐️ Premium: {premium}\n\n"
                f"📤 Постинг через юзербот: <b>активен</b>\n"
                f"<i>При ошибке → fallback на бота</i>",
                parse_mode="HTML",
                reply_markup=userbot_kb(True)
            )
        else:
            await callback.message.edit_text(
                f"🤖 <b>Юзербот (Telethon)</b>\n\n"
                f"⚠️ Сессия есть, но авторизация не прошла:\n"
                f"<code>{auth.get('error', '?')}</code>\n\n"
                f"Переавторизуйтесь:",
                parse_mode="HTML",
                reply_markup=userbot_kb(False)
            )
    else:
        await callback.message.edit_text(
            "🤖 <b>Юзербот (Telethon)</b>\n\n"
            "📡 Сессия не найдена\n\n"
            "Юзербот нужен для:\n"
            "• Отправки Premium эмодзи в канал\n"
            "• Обхода ограничений Bot API\n\n"
            "Если юзербот не настроен — постинг идёт "
            "через обычного бота.",
            parse_mode="HTML",
            reply_markup=userbot_kb(False)
        )
    await callback.answer()


# ═══ Авторизация ═══

@router.callback_query(F.data == "ub_auth_start")
async def cb_auth_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(UserbotStates.phone)
    await callback.message.edit_text(
        "📱 Введите номер телефона с +\n"
        "Пример: <code>+0</code>\n\n"
        "⚠️ Это номер для юзербота, "
        "через который будет постинг в канал.",
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="❌ Отмена", callback_data="admin_userbot")]
        ])
    )
    await callback.answer()


@router.message(UserbotStates.phone, F.chat.type == ChatType.PRIVATE)
async def handle_ub_phone(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    phone = message.text.strip()
    if not phone.startswith("+"):
        await message.answer("❌ Номер должен начинаться с +")
        return

    status_msg = await message.answer("⏳ Отправляю код...")

    result = await userbot.create_session(phone)

    if result.get("error"):
        await state.clear()
        await status_msg.edit_text(
            f"❌ Ошибка: <code>{result['error']}</code>",
            parse_mode="HTML",
            reply_markup=IKM(inline_keyboard=[
                [IKB(text="🔄 Повторить",
                     callback_data="ub_auth_start")],
                [IKB(text="⬅️ Назад", callback_data="admin_userbot")]
            ])
        )
        return

    if result.get("stage") == "code_sent":
        await state.set_state(UserbotStates.code)
        await state.update_data(phone=phone)
        await status_msg.edit_text(
            f"📨 Код отправлен на <code>{phone}</code>\n\n"
            "Введите код из Telegram 1 2 3 4 5 через пробел:",
            parse_mode="HTML",
            reply_markup=IKM(inline_keyboard=[
                [IKB(text="❌ Отмена", callback_data="admin_userbot")]
            ])
        )


@router.message(UserbotStates.code, F.chat.type == ChatType.PRIVATE)
async def handle_ub_code(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    # Remove spaces from the code (allow input like "1 2 3 4 5" or "12345")
    code = message.text.strip().replace(" ", "")
    
    # Validate code is numeric
    if not code.isdigit():
        await message.answer(
            "❌ Код должен содержать только цифры\n"
            "Введите код из Telegram (например: 12345 или 1 2 3 4 5)",
            reply_markup=IKM(inline_keyboard=[
                [IKB(text="❌ Отмена", callback_data="admin_userbot")]
            ])
        )
        return

    # Delete the message with the code
    try:
        await message.delete()
    except Exception:
        pass

    status_msg = await message.answer("⏳ Проверяю код...")

    result = await userbot.confirm_code(code)

    if result.get("stage") == "need_password":
        await state.set_state(UserbotStates.password)
        await status_msg.edit_text(
            "🔐 Аккаунт защищён двухфакторной аутентификацией.\n"
            "Введите пароль 2FA:",
            reply_markup=IKM(inline_keyboard=[
                [IKB(text="❌ Отмена", callback_data="admin_userbot")]
            ])
        )
        return

    if result.get("error"):
        await state.clear()
        await status_msg.edit_text(
            f"❌ Ошибка: <code>{result['error']}</code>",
            parse_mode="HTML",
            reply_markup=IKM(inline_keyboard=[
                [IKB(text="🔄 Повторить",
                     callback_data="ub_auth_start")],
                [IKB(text="⬅️ Назад", callback_data="admin_userbot")]
            ])
        )
        return

    if result.get("ok"):
        await state.clear()
        premium = "✅" if result.get("premium") else "❌"
        await status_msg.edit_text(
            f"✅ Юзербот авторизован!\n\n"
            f"👤 {result.get('name', '?')}\n"
            f"🆔 <code>{result.get('user_id', '?')}</code>\n"
            f"⭐️ Premium: {premium}",
            parse_mode="HTML",
            reply_markup=userbot_kb(True)
        )


@router.message(UserbotStates.password, F.chat.type == ChatType.PRIVATE)
async def handle_ub_password(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    password = message.text.strip()

    try:
        await message.delete()
    except Exception:
        pass

    status_msg = await message.answer("⏳ Проверяю пароль...")

    # Используем confirm_code с паролем
    result = await userbot.confirm_code(password=password)

    await state.clear()

    if result.get("ok"):
        premium = "✅" if result.get("premium") else "❌"
        await status_msg.edit_text(
            f"✅ Юзербот авторизован!\n\n"
            f"👤 {result.get('name', '?')}\n"
            f"🆔 <code>{result.get('user_id', '?')}</code>\n"
            f"⭐️ Premium: {premium}",
            parse_mode="HTML",
            reply_markup=userbot_kb(True)
        )
    elif result.get("stage") == "need_password":
        # Если снова просит пароль (не должно случиться, но на всякий случай)
        await status_msg.edit_text(
            "🔐 Введите пароль 2FA:",
            reply_markup=IKM(inline_keyboard=[
                [IKB(text="❌ Отмена", callback_data="admin_userbot")]
            ])
        )
    else:
        await status_msg.edit_text(
            f"❌ {result.get('error', 'Неизвестная ошибка')}",
            reply_markup=IKM(inline_keyboard=[
                [IKB(text="🔄 Повторить", callback_data="ub_auth_start")],
                [IKB(text="⬅️ Назад", callback_data="admin_userbot")]
            ])
        )

from telethon import TelegramClient
async def confirm_2fa_password(self, password: str, phone: str = None):
    """Подтверждение пароля 2FA"""
    try:
        if not self.client or not self.client.is_connected():
            self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)
            await self.client.connect()
        
        # Если уже есть код запроса, используем его
        # Иначе отправляем новый запрос
        if phone:
            await self.client.send_code_request(phone)
        
        # Подтверждаем пароль
        await self.client.sign_in(password=password)
        
        # Получаем информацию о пользователе
        me = await self.client.get_me()
        
        # Сохраняем сессию
        await self.client.disconnect()
        
        return {
            "ok": True,
            "name": me.first_name or "",
            "user_id": me.id,
            "phone": me.phone,
            "premium": getattr(me, "premium", False)
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══ Проверка ═══

@router.callback_query(F.data == "ub_check")
async def cb_check(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    auth = await userbot.check_auth()
    if auth.get("ok"):
        await callback.answer(
            f"✅ OK: {auth.get('name')} "
            f"(premium={'yes' if auth.get('premium') else 'no'})",
            show_alert=True
        )
    else:
        await callback.answer(
            f"❌ {auth.get('error', '?')}",
            show_alert=True
        )


# ═══ Тестовая отправка ═══

@router.callback_query(F.data == "ub_test_send")
async def cb_test_send(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    channel_id = get_setting("channel_id")
    if not channel_id:
        await callback.answer("❌ Канал не настроен", show_alert=True)
        return

    test_text = (
        "🧪 <b>Тестовое сообщение</b>\n\n"
        "Отправлено через юзербот (Telethon)\n"
        f"⏰ {now_msk().strftime('%H:%M:%S MSK')}"
    )

    result = await userbot.send_message(
        int(channel_id), test_text
    )

    if result.get("ok"):
        await callback.answer(
            f"✅ Отправлено! msg_id={result['message_id']}",
            show_alert=True
        )
    else:
        await callback.answer(
            f"❌ {result.get('error', '?')}",
            show_alert=True
        )


# ═══ Тестовая статистика ═══

@router.callback_query(F.data == "ub_test_stats")
async def cb_test_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    channel_id = get_setting("channel_id")
    if not channel_id:
        await callback.answer("❌ Канал не настроен", show_alert=True)
        return

    # Собираем реальную статистику за текущий день
    day_start = get_current_day_start()
    now = time.time()
    stats = get_stats_for_period(day_start, now)
    c = calc_stats(stats)

    report_tpl = get_report_template()
    template = report_tpl.get("template", "")

    if not template:
        template = (
            "✉️\n\n"
            "Статистика за 24ч :\n\n"
            "⚠️ Кол-во ордеров: <b>{order_count}</b>\n"
            "⚠️ Сумма средств: <b>{total_volume}</b>\n"
            "🛍 Средний курс: <b>{avg_price}</b>\n\n"
            "Увидимся завтра👍"
        )

    text = template.replace(
        "{order_count}", str(c["order_count"])
    ).replace(
        "{total_volume}", format_volume(c["total_volume"])
    ).replace(
        "{avg_price}", format_price(c["avg_price"])
    ).replace(
        "{period}", "текущий день (тест)"
    )

    # Отправляем как HTML, без парсинга entities
    try:
        msg = await userbot._client.send_message(
            int(channel_id),
            text,
            parse_mode="html",
            link_preview=False
        )
        await callback.answer(
            f"✅ Статистика отправлена через юзербот! msg={msg.id}",
            show_alert=True
        )
    except Exception as e:
        logger.error(f"Send error: {e}")
        # Fallback через бота
        try:
            from aiogram import Bot
            bot = callback.bot
            msg = await bot.send_message(
                chat_id=int(channel_id),
                text=text,
                parse_mode="HTML"
            )
            await callback.answer(
                f"⚠️ Юзербот не смог, отправлено через бота. msg={msg.message_id}",
                show_alert=True
            )
        except Exception as e2:
            await callback.answer(f"❌ Ошибка: {e2}", show_alert=True)


# ═══ Удаление ═══

@router.callback_query(F.data == "ub_delete_confirm")
async def cb_delete_confirm(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "⚠️ <b>Удалить сессию юзербота?</b>\n\n"
        "Постинг будет только через обычного бота.\n"
        "Premium эмодзи перестанут работать в канале.",
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=[
            [
                IKB(text="🗑 Да, удалить",
                    callback_data="ub_delete_yes"),
                IKB(text="❌ Отмена",
                    callback_data="admin_userbot"),
            ]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "ub_delete_yes")
async def cb_delete_yes(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    await userbot.remove_session()

    await callback.message.edit_text(
        "🗑 Сессия удалена.\n"
        "Постинг через обычного бота.",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="⬅️ Назад", callback_data="admin_main")]
        ])
    )
    await callback.answer()