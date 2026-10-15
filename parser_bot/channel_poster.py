"""
Единый интерфейс для отправки сообщений в канал.
Приоритет: Userbot (Telethon) → Bot (aiogram).
"""

import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from userbot import userbot

logger = logging.getLogger(__name__)


class ChannelPoster:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup = None
    ) -> int | None:
        """
        Отправить сообщение в канал.
        Возвращает message_id или None.
        """
        # Попытка через userbot
        if userbot.is_available:
            result = await userbot.send_message(
                chat_id, text, reply_markup
            )
            if result.get("ok"):
                logger.info(
                    f"📤 Sent via userbot → msg {result['message_id']}"
                )
                return result["message_id"]
            else:
                logger.warning(
                    f"⚠️ Userbot failed: {result.get('error')}, "
                    f"falling back to bot"
                )

        # Fallback на бота
        try:
            msg = await self.bot.send_message(
                chat_id=str(chat_id),
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            logger.info(f"📤 Sent via bot → msg {msg.message_id}")
            return msg.message_id
        except Exception as e:
            logger.error(f"Bot send error: {e}")
            return None

    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup = None
    ) -> bool:
        """Редактировать сообщение в канале."""
        # Попытка через userbot
        if userbot.is_available:
            result = await userbot.edit_message(
                chat_id, message_id, text, reply_markup
            )
            if result.get("ok"):
                logger.info(
                    f"📝 Edited via userbot → msg {message_id}"
                )
                return True
            else:
                logger.warning(
                    f"⚠️ Userbot edit failed: {result.get('error')}, "
                    f"falling back to bot"
                )

        # Fallback на бота
        try:
            await self.bot.edit_message_text(
                text=text,
                chat_id=str(chat_id),
                message_id=message_id,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            logger.info(f"📝 Edited via bot → msg {message_id}")
            return True
        except Exception as e:
            error_str = str(e).lower()
            if "not modified" in error_str:
                return True
            logger.error(f"Bot edit error: {e}")
            return False

    async def send_text(
        self,
        chat_id: int,
        text: str
    ) -> int | None:
        """Отправить текст без кнопок (для отчётов)."""
        return await self.send_message(chat_id, text, reply_markup=None)