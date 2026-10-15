import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup as IKM,
    InlineKeyboardButton as IKB
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatType

from config import BOT_TOKEN, ADMIN_IDS
from database import (
    init_db, create_request, get_pending_requests,
    approve_request, reject_request,
    get_all_tokens, toggle_token, delete_token
)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


class RequestStates(StatesGroup):
    reason = State()


class AdminStates(StatesGroup):
    reject_note = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ═══════════════════════════════════════
#  ПОЛЬЗОВАТЕЛЬСКАЯ ЧАСТЬ: заявка на токен
# ═══════════════════════════════════════

@dp.message(Command("start"), F.chat.type == ChatType.PRIVATE)
async def cmd_start(message: Message):
    if is_admin(message.from_user.id):
        await message.answer(
            "👑 <b>Admin Panel</b>\n\n"
            "/admin — управление\n"
            "/tokens — все токены\n"
            "/requests — заявки",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "👋 <b>Cookie Microservice</b>\n\n"
            "Для доступа к API нужен токен.\n"
            "Нажми кнопку чтобы подать заявку:",
            parse_mode="HTML",
            reply_markup=IKM(inline_keyboard=[
                [IKB(text="📝 Запросить токен", callback_data="request_token")]
            ])
        )


@dp.callback_query(F.data == "request_token")
async def cb_request_token(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RequestStates.reason)
    await callback.message.edit_text(
        "📝 Напиши причину / для чего нужен токен:"
    )
    await callback.answer()


@dp.message(RequestStates.reason, F.chat.type == ChatType.PRIVATE)
async def handle_reason(message: Message, state: FSMContext):
    await state.clear()

    req = create_request(
        message.from_user.id,
        message.from_user.username or "",
        message.text
    )

    await message.answer(
        f"✅ Заявка #{req['id']} отправлена!\n"
        "Ожидай одобрения администратором."
    )

    # Уведомляем админов
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📬 <b>Новая заявка #{req['id']}</b>\n\n"
                f"👤 {message.from_user.full_name}\n"
                f"🆔 <code>{message.from_user.id}</code>\n"
                f"📛 @{message.from_user.username or '—'}\n"
                f"📝 {message.text}",
                parse_mode="HTML",
                reply_markup=IKM(inline_keyboard=[
                    [
                        IKB(
                            text="✅ Одобрить",
                            callback_data=f"approve_{req['id']}"
                        ),
                        IKB(
                            text="❌ Отклонить",
                            callback_data=f"reject_{req['id']}"
                        )
                    ]
                ])
            )
        except Exception:
            pass


# ═══════════════════════════════════════
#  АДМИН: обработка заявок
# ═══════════════════════════════════════

@dp.callback_query(F.data.startswith("approve_"))
async def cb_approve(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    req_id = int(callback.data.split("_")[1])
    token_data = approve_request(req_id)

    if not token_data:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        callback.message.text + "\n\n✅ <b>ОДОБРЕНО</b>",
        parse_mode="HTML"
    )

    # Отправляем токен пользователю
    try:
        await bot.send_message(
            token_data["user_id"],
            f"🎉 <b>Заявка одобрена!</b>\n\n"
            f"🔑 Ваш API токен:\n"
            f"<code>{token_data['token']}</code>\n\n"
            f"⚠️ Храни в безопасности, не передавай третьим лицам!",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await callback.answer("Одобрено ✅")


@dp.callback_query(F.data.startswith("reject_"))
async def cb_reject(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌", show_alert=True)
        return

    req_id = int(callback.data.split("_")[1])
    reject_request(req_id)

    await callback.message.edit_text(
        callback.message.text + "\n\n❌ <b>ОТКЛОНЕНО</b>",
        parse_mode="HTML"
    )
    await callback.answer("Отклонено ❌")


# ═══════════════════════════════════════
#  АДМИН: управление токенами
# ═══════════════════════════════════════

@dp.message(Command("admin"), F.chat.type == ChatType.PRIVATE)
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "👑 <b>Админ-панель</b>",
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="🔑 Токены", callback_data="admin_tokens")],
            [IKB(text="📬 Заявки", callback_data="admin_requests")],
            [IKB(
                text="➕ Создать токен вручную",
                callback_data="admin_create_token"
            )],
        ])
    )


@dp.callback_query(F.data == "admin_tokens")
async def cb_admin_tokens(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    tokens = get_all_tokens()
    if not tokens:
        await callback.message.edit_text("🔑 Нет токенов")
        return

    lines = ["🔑 <b>Все токены:</b>\n"]
    buttons = []

    for t in tokens[:20]:
        status = "🟢" if t["is_active"] else "🔴"
        short = t["token"][:20] + "..."
        lines.append(
            f"{status} #{t['id']} | <code>{short}</code>\n"
            f"   👤 {t['username'] or t['user_id']} | {t['label']}"
        )
        buttons.append([
            IKB(
                text=f"{'🔴 Выкл' if t['is_active'] else '🟢 Вкл'} #{t['id']}",
                callback_data=f"toggle_token_{t['id']}_{1 if not t['is_active'] else 0}"
            ),
            IKB(
                text=f"🗑 #{t['id']}",
                callback_data=f"del_token_{t['id']}"
            )
        ])

    buttons.append([IKB(text="⬅️ Назад", callback_data="admin_back")])

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=buttons)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("toggle_token_"))
async def cb_toggle_token(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    parts = callback.data.split("_")
    token_id = int(parts[2])
    active = bool(int(parts[3]))
    toggle_token(token_id, active)
    await callback.answer(
        f"{'Включен' if active else 'Выключен'} ✅"
    )
    await cb_admin_tokens(callback)


@dp.callback_query(F.data.startswith("del_token_"))
async def cb_del_token(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    token_id = int(callback.data.split("_")[2])
    delete_token(token_id)
    await callback.answer("Удалён 🗑")
    await cb_admin_tokens(callback)


@dp.callback_query(F.data == "admin_requests")
async def cb_admin_requests(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    reqs = get_pending_requests()
    if not reqs:
        await callback.message.edit_text(
            "📬 Нет ожидающих заявок",
            reply_markup=IKM(inline_keyboard=[
                [IKB(text="⬅️ Назад", callback_data="admin_back")]
            ])
        )
        await callback.answer()
        return

    for r in reqs:
        await callback.message.answer(
            f"📬 <b>Заявка #{r['id']}</b>\n"
            f"👤 {r['username'] or r['user_id']}\n"
            f"📝 {r['reason']}",
            parse_mode="HTML",
            reply_markup=IKM(inline_keyboard=[
                [
                    IKB(text="✅", callback_data=f"approve_{r['id']}"),
                    IKB(text="❌", callback_data=f"reject_{r['id']}")
                ]
            ])
        )
    await callback.answer()


@dp.callback_query(F.data == "admin_create_token")
async def cb_create_manual(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    from database import create_token
    t = create_token(
        callback.from_user.id,
        callback.from_user.username or "",
        "manual"
    )
    await callback.message.answer(
        f"✅ Токен создан:\n<code>{t['token']}</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_back")
async def cb_back(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await cmd_admin(callback.message)
    await callback.answer()


# Игнор остальных
@dp.message(F.chat.type == ChatType.PRIVATE)
async def ignore(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Используй кнопки ☝️")


async def main():
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
