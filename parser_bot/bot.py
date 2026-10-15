import asyncio
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup as IKM,
    InlineKeyboardButton as IKB
)
from aiogram.fsm.context import FSMContext
from aiogram.enums import ChatType

from config import BOT_TOKEN, ADMIN_IDS
from database import init_db
from offer_monitor import OfferMonitor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

monitor: OfferMonitor = None

main_router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def admin_main_kb() -> IKM:
    return IKM(inline_keyboard=[
        [IKB(text="⚙️ Настройки API", callback_data="admin_settings")],
        [IKB(text="👤 Аккаунт Send.TG", callback_data="admin_account")],
        [IKB(text="🤖 Юзербот (Telethon)", callback_data="admin_userbot")],
        [IKB(text="📦 Офферы", callback_data="admin_offers")],
        [IKB(text="🎨 Шаблон сообщения", callback_data="admin_template")],
        [IKB(text="📊 Ежедневный отчёт", callback_data="admin_report")],
        [
            IKB(text="▶️ Старт", callback_data="monitor_start"),
            IKB(text="⏹ Стоп", callback_data="monitor_stop"),
        ],
    ])


@main_router.message(Command("start"), F.chat.type == ChatType.PRIVATE)
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        return

    from userbot import userbot
    ub_status = "🟢" if userbot.is_available else "⚪️"

    await message.answer(
        "👑 <b>Send.TG Parser</b>\n\n"
        f"📡 Мониторинг: {'🟢' if monitor and monitor.running else '🔴'}\n"
        f"🤖 Юзербот: {ub_status}",
        parse_mode="HTML",
        reply_markup=admin_main_kb()
    )


@main_router.message(Command("admin"), F.chat.type == ChatType.PRIVATE)
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await cmd_start(message)


@main_router.callback_query(F.data == "admin_main")
async def cb_admin_main(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    from userbot import userbot
    ub_status = "🟢" if userbot.is_available else "⚪️"

    await callback.message.edit_text(
        f"👑 <b>Send.TG Parser</b>\n\n"
        f"📡 Мониторинг: {'🟢' if monitor and monitor.running else '🔴'}\n"
        f"🤖 Юзербот: {ub_status}",
        parse_mode="HTML",
        reply_markup=admin_main_kb()
    )
    await callback.answer()


@main_router.callback_query(F.data == "monitor_start")
async def cb_monitor_start(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    global monitor
    if monitor and monitor.running:
        await callback.answer("Уже запущен", show_alert=True)
        return
    monitor = OfferMonitor(bot)
    monitor.start()
    await callback.answer("▶️ Запущен!")
    await cb_admin_main(callback)


@main_router.callback_query(F.data == "monitor_stop")
async def cb_monitor_stop(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    if monitor:
        monitor.stop()
    await callback.answer("⏹ Остановлен")
    await cb_admin_main(callback)


@main_router.callback_query(F.data.startswith("offer_poll_"))
async def cb_force_poll(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    oid = int(callback.data.split("_")[2])
    if not monitor:
        await callback.answer("Монитор не запущен", show_alert=True)
        return
    result = await monitor.force_poll(oid)
    await callback.answer(result, show_alert=True)


@main_router.message(F.chat.type == ChatType.PRIVATE)
async def fallback(message: Message, state: FSMContext):
    current = await state.get_state()
    logger.warning(
        f"Fallback: user={message.from_user.id}, "
        f"text={message.text!r}, state={current}"
    )
    if not is_admin(message.from_user.id):
        return


async def on_shutdown(dp):
    """Отключаем юзербот при остановке."""
    from userbot import userbot
    await userbot.disconnect()


async def main():
    init_db()

    from admin.settings import router as settings_router
    from admin.account import router as account_router
    from admin.offers import router as offers_router
    from admin.template import router as template_router
    from admin.report import router as report_router
    from admin.userbot_settings import router as userbot_router

    dp.include_router(settings_router)
    dp.include_router(account_router)
    dp.include_router(offers_router)
    dp.include_router(template_router)
    dp.include_router(report_router)
    dp.include_router(userbot_router)

    # Главный роутер ПОСЛЕДНИМ
    dp.include_router(main_router)

    dp.shutdown.register(on_shutdown)

    # Подключаем юзербот если есть сессия
    from userbot import userbot
    if userbot.is_available:
        connected = await userbot.connect()
        if connected:
            logger.info("🤖 Userbot connected on startup")
        else:
            logger.warning("⚠️ Userbot session exists but failed to connect")

    logger.info("🚀 Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())