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
from database import get_template, update_template
from tpl.emoji import rebuild_text_with_emoji, extract_first_emoji_id

router = Router()

STYLES = ["primary", "success", "danger"]


class TemplateStates(StatesGroup):
    edit_template = State()
    edit_button_text = State()
    edit_button_emoji = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def template_kb() -> IKM:
    return IKM(inline_keyboard=[
        [IKB(text="📝 Редактировать шаблон",
             callback_data="tpl_edit_template")],
        [IKB(text="🔘 Текст кнопки",
             callback_data="tpl_edit_button")],
        [IKB(text="😎 Эмодзи кнопки",
             callback_data="tpl_edit_emoji")],
        [IKB(text="🎨 Стиль кнопки",
             callback_data="tpl_style_menu")],
        [IKB(text="👁 Предпросмотр",
             callback_data="tpl_preview")],
        [IKB(text="⬅️ Назад", callback_data="admin_main")],
    ])


@router.callback_query(F.data == "admin_template")
async def cb_template_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    tpl = get_template()

    text = (
        f"🎨 <b>Шаблон сообщения</b>\n\n"
        f"📝 Шаблон:\n<code>{tpl.get('template', '—')}</code>\n\n"
        f"🔘 Кнопка: {tpl.get('button_text', '—')}\n"
        f"😎 Emoji ID: <code>{tpl.get('button_emoji_id') or '—'}</code>\n"
        f"🎨 Стиль: {tpl.get('button_style') or 'default'}\n\n"
        f"<b>Переменные:</b>\n"
        f"<code>{{type_emoji}}</code> — 🟢/🔴\n"
        f"<code>{{type_text}}</code> — Покупка/Продажа\n"
        f"<code>{{asset}}</code> — USDT\n"
        f"<code>{{fiat}}</code> — RUB\n"
        f"<code>{{fiat_emoji}}</code> — 💵\n"
        f"<code>{{price}}</code> — Курс\n"
        f"<code>{{min}}</code> <code>{{max}}</code> — Лимиты\n"
        f"<code>{{status_emoji}}</code> — 🟢/🔴\n"
        f"<code>{{status_text}}</code> — Открыто/Закрыто\n"
        f"<code>{{user_name}}</code> <code>{{user_rating}}</code>"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=template_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "tpl_edit_template")
async def cb_edit_tpl(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(TemplateStates.edit_template)
    await callback.message.edit_text(
        "📝 Отправьте новый шаблон сообщения.\n"
        "Поддерживается HTML и Premium эмодзи.\n\n"
        "Используйте переменные в фигурных скобках.",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="❌ Отмена", callback_data="admin_template")]
        ])
    )
    await callback.answer()


@router.message(TemplateStates.edit_template, F.chat.type == ChatType.PRIVATE)
async def handle_edit_tpl(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()

    text = rebuild_text_with_emoji(message)
    update_template(template=text)

    await message.answer(
        "✅ Шаблон обновлён!",
        reply_markup=template_kb()
    )


@router.callback_query(F.data == "tpl_edit_button")
async def cb_edit_btn(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(TemplateStates.edit_button_text)
    await callback.message.edit_text(
        "🔘 Введите текст кнопки:",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="❌ Отмена", callback_data="admin_template")]
        ])
    )
    await callback.answer()


@router.message(TemplateStates.edit_button_text, F.chat.type == ChatType.PRIVATE)
async def handle_btn_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    update_template(button_text=message.text.strip())
    await message.answer("✅ Текст кнопки обновлён!", reply_markup=template_kb())


@router.callback_query(F.data == "tpl_edit_emoji")
async def cb_edit_emoji(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(TemplateStates.edit_button_emoji)
    await callback.message.edit_text(
        "😎 Отправьте Premium эмодзи для кнопки.\n"
        "Или <code>clear</code> чтобы убрать.",
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=[
            [IKB(text="❌ Отмена", callback_data="admin_template")]
        ])
    )
    await callback.answer()


@router.message(TemplateStates.edit_button_emoji, F.chat.type == ChatType.PRIVATE)
async def handle_emoji(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()

    if message.text and message.text.strip().lower() == "clear":
        update_template(button_emoji_id="")
        await message.answer("✅ Эмодзи убрано", reply_markup=template_kb())
        return

    emoji_id = extract_first_emoji_id(message)
    if emoji_id:
        update_template(button_emoji_id=emoji_id)
        await message.answer(
            f"✅ Emoji ID: <code>{emoji_id}</code>",
            parse_mode="HTML",
            reply_markup=template_kb()
        )
    else:
        await message.answer(
            "❌ Не нашёл Premium эмодзи. Отправь кастомный эмодзи.",
            reply_markup=template_kb()
        )


@router.callback_query(F.data == "tpl_style_menu")
async def cb_style_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    tpl = get_template()
    current = tpl.get("button_style") or "default"

    buttons = []
    for style in STYLES:
        check = "✅ " if current == style else ""
        buttons.append([
            IKB(
                text=f"{check}{style}",
                callback_data=f"tpl_set_style_{style}"
            )
        ])
    buttons.append([
        IKB(
            text=f"{'✅ ' if current == 'default' else ''}default (убрать)",
            callback_data="tpl_set_style_default"
        )
    ])
    buttons.append([IKB(text="⬅️ Назад", callback_data="admin_template")])

    await callback.message.edit_text(
        f"🎨 <b>Стиль кнопки</b>\n\n"
        f"Текущий: <b>{current}</b>\n\n"
        f"🔵 primary — синяя\n"
        f"🟢 success — зелёная\n"
        f"🔴 danger — красная",
        parse_mode="HTML",
        reply_markup=IKM(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tpl_set_style_"))
async def cb_set_style(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    style = callback.data.replace("tpl_set_style_", "")
    if style == "default":
        update_template(button_style="")
    else:
        update_template(button_style=style)

    await callback.answer(f"✅ {style}")
    await cb_style_menu(callback)


@router.callback_query(F.data == "tpl_preview")
async def cb_preview(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    # Фейковые данные
    from offer_monitor import OfferMonitor
    fake_data = {
        "type": "sell",
        "asset": "USDT",
        "fiat": "RUB",
        "price": "84.44",
        "limits": {"min": "500", "max": "50000"},
        "status": "active",
        "is_visible": True,
        "user": {"name": "TestUser", "rating": 98, "orders": 100}
    }

    # Создаём временный монитор для форматирования
    monitor = OfferMonitor.__new__(OfferMonitor)
    text_open = monitor._build_message(fake_data, is_open=True)
    text_closed = monitor._build_message(fake_data, is_open=False)
    kb = monitor._build_keyboard(2452434)

    await callback.message.answer(
        f"🟢 <b>Открыто:</b>\n\n{text_open}",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.message.answer(
        f"🔴 <b>Закрыто:</b>\n\n{text_closed}",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()
