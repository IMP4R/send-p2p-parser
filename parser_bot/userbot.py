import os
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (
    MessageEntityCustomEmoji,
    MessageEntityBold,
    MessageEntityItalic,
    MessageEntityCode,
    MessageEntityPre,
    MessageEntityTextUrl,
    MessageEntityUnderline,
    MessageEntityStrike,
)
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
import re

from config import TELETHON_API_ID, TELETHON_API_HASH, TELETHON_SESSION_DIR
from database import get_setting, set_setting

logger = logging.getLogger(__name__)

# Паттерн для парсинга tg-emoji тегов
TG_EMOJI_RE = re.compile(
    r'<tg-emoji\s+emoji-id=["\'](\d+)["\']>(.*?)</tg-emoji>'
)

# HTML теги
HTML_TAGS = {
    "b": MessageEntityBold,
    "strong": MessageEntityBold,
    "i": MessageEntityItalic,
    "em": MessageEntityItalic,
    "code": MessageEntityCode,
    "u": MessageEntityUnderline,
    "s": MessageEntityStrike,
    "strike": MessageEntityStrike,
    "del": MessageEntityStrike,
}


class UserbotClient:
    def __init__(self):
        self._client: TelegramClient | None = None
        self._connected = False

    @property
    def is_available(self) -> bool:
        """Проверяет, настроен ли юзербот."""
        session = get_setting("telethon_session")
        return bool(
            session
            and TELETHON_API_ID
            and TELETHON_API_HASH
        )

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    async def connect(self) -> bool:
        """Подключиться используя сохранённую сессию."""
        if self._connected and self._client:
            return True

        session_str = get_setting("telethon_session")
        if not session_str or not TELETHON_API_ID or not TELETHON_API_HASH:
            logger.warning("Telethon not configured")
            return False

        try:
            self._client = TelegramClient(
                StringSession(session_str),
                TELETHON_API_ID,
                TELETHON_API_HASH
            )
            await self._client.connect()

            if not await self._client.is_user_authorized():
                logger.warning("Telethon session expired")
                self._connected = False
                return False

            self._connected = True
            me = await self._client.get_me()
            logger.info(
                f"✅ Telethon connected: "
                f"{me.first_name} (id={me.id})"
            )
            return True

        except Exception as e:
            logger.error(f"Telethon connect error: {e}")
            self._connected = False
            return False

    async def disconnect(self):
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                pass
        self._connected = False
        self._client = None

    async def check_auth(self) -> dict:
        """Проверить авторизацию."""
        try:
            if not await self.connect():
                return {"ok": False, "error": "Not connected"}

            me = await self._client.get_me()
            return {
                "ok": True,
                "user_id": me.id,
                "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
                "phone": me.phone,
                "premium": getattr(me, "premium", False),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _parse_html_with_emoji(self, html_text: str):
        """
        Парсит HTML текст с поддержкой <tg-emoji> в текст + entities.
        """
        logger.info(f"[PARSE] === START PARSING ===")
        logger.info(f"[PARSE] Input text:\n{html_text}")
        logger.info(f"[PARSE] Input length: {len(html_text)}")
        
        # 1. Находим все tg-emoji и заменяем их на уникальные маркеры
        emoji_list = []
        temp_text = html_text
        offset_correction = 0
        
        matches = list(TG_EMOJI_RE.finditer(html_text))
        logger.info(f"[PARSE] Found {len(matches)} emoji tags")
        
        for idx, match in enumerate(matches):
            emoji_id = int(match.group(1))
            visible = match.group(2)
            
            # Создаем уникальный маркер
            marker = f"__EMOJI_{idx}__"
            
            # Запоминаем данные об эмодзи
            emoji_list.append({
                "marker": marker,
                "emoji_id": emoji_id,
                "visible": visible,
                "original_start": match.start(),
                "original_end": match.end()
            })
            
            logger.info(f"[PARSE] Emoji {idx}: id={emoji_id}, visible='{visible}', marker='{marker}'")
            
            # Заменяем в тексте на маркер
            start = match.start() - offset_correction
            end = match.end() - offset_correction
            temp_text = temp_text[:start] + marker + temp_text[end:]
            offset_correction += (match.end() - match.start()) - len(marker)
        
        logger.info(f"[PARSE] Text with markers:\n{temp_text}")
        
        # 2. Парсим HTML теги из текста с маркерами
        result_text = ""
        result_entities = []
        tag_stack = []
        i = 0
        
        while i < len(temp_text):
            if temp_text[i] == '<':
                end = temp_text.find('>', i)
                if end == -1:
                    result_text += temp_text[i]
                    i += 1
                    continue
                
                tag_content = temp_text[i+1:end].strip()
                
                # Закрывающий тег
                if tag_content.startswith('/'):
                    tag_name = tag_content[1:].strip().lower()
                    # Ищем парный открывающий тег
                    for j in range(len(tag_stack) - 1, -1, -1):
                        if tag_stack[j]["tag"] == tag_name:
                            entry = tag_stack.pop(j)
                            offset = entry["offset"]
                            length = len(result_text) - offset
                            
                            if tag_name in HTML_TAGS:
                                result_entities.append(
                                    HTML_TAGS[tag_name](
                                        offset=offset,
                                        length=length
                                    )
                                )
                            elif tag_name == "a" and entry.get("url"):
                                result_entities.append(
                                    MessageEntityTextUrl(
                                        offset=offset,
                                        length=length,
                                        url=entry["url"]
                                    )
                                )
                            break
                    i = end + 1
                    continue
                
                # Открывающий тег
                tag_name = tag_content.split()[0].lower()
                if tag_name.endswith('/'):
                    tag_name = tag_name[:-1]
                
                entry = {
                    "tag": tag_name,
                    "offset": len(result_text),
                }
                
                # Извлекаем href для ссылок
                if tag_name == "a":
                    href_match = re.search(r'href=["\']([^"\']+)["\']', tag_content)
                    if href_match:
                        entry["url"] = href_match.group(1)
                
                tag_stack.append(entry)
                i = end + 1
                continue
            
            # Обрабатываем HTML entities
            if temp_text[i:].startswith('&lt;'):
                result_text += '<'
                i += 4
            elif temp_text[i:].startswith('&gt;'):
                result_text += '>'
                i += 4
            elif temp_text[i:].startswith('&amp;'):
                result_text += '&'
                i += 5
            else:
                result_text += temp_text[i]
                i += 1
        
        logger.info(f"[PARSE] After HTML parsing:\n{result_text}")
        logger.info(f"[PARSE] Found {len(result_entities)} HTML entities")
        
        final_text = result_text
        final_entities = list(result_entities)
        
        for idx, emoji in enumerate(emoji_list):
            marker = emoji["marker"]
            pos = final_text.find(marker)
            
            if pos >= 0:
                visible = emoji["visible"]
                visible_len = len(visible)
                emoji_id = emoji["emoji_id"]
                
                # Если эмодзи имеет длину 1, добавляем вариационный селектор
                if visible_len == 1:
                    # Добавляем \uFE0F чтобы сделать его составным
                    visible_with_variant = visible + "\uFE0F"
                    final_text = final_text[:pos] + visible_with_variant + final_text[pos + len(marker):]
                    final_entities.append(
                        MessageEntityCustomEmoji(
                            offset=pos,
                            length=2,  # теперь длина 2
                            document_id=emoji_id
                        )
                    )
                    logger.info(f"[PARSE] Emoji {idx}: added variant selector, now length=2")
                else:
                    final_text = final_text[:pos] + visible + final_text[pos + len(marker):]
                    final_entities.append(
                        MessageEntityCustomEmoji(
                            offset=pos,
                            length=visible_len,
                            document_id=emoji_id
                        )
                    )
                
                logger.info(f"[PARSE] Emoji {idx}: added entity at offset={pos}, length={visible_len if visible_len > 1 else 2}, id={emoji_id}")
            else:
                logger.warning(f"[PARSE] Emoji {idx}: marker '{marker}' NOT FOUND!")
        
        # Сортируем entities по offset
        final_entities.sort(key=lambda e: e.offset)
        
        return final_text, final_entities

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup=None,
        parse_html: bool = False  # по умолчанию False
    ) -> dict:
        if not await self.connect():
            return {"ok": False, "error": "Not connected"}

        try:
            if parse_html:
                parsed_text, entities = self._parse_html_with_emoji(text)
            else:
                parsed_text = text
                entities = None

            buttons = None
            if reply_markup:
                buttons = self._convert_markup(reply_markup)

            msg = await self._client.send_message(
                chat_id,
                parsed_text,
                formatting_entities=entities if entities else None,
                buttons=buttons,
                link_preview=False,
                parse_mode="html" if not entities else None  # добавляем parse_mode
            )

            return {"ok": True, "message_id": msg.id}
        except Exception as e:
            logger.error(f"Userbot send error: {e}", exc_info=True)
            return {"ok": False, "error": str(e)}

    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup=None
    ) -> dict:
        """Редактировать сообщение через юзербот."""
        if not await self.connect():
            return {"ok": False, "error": "Not connected"}

        try:
            parsed_text, entities = self._parse_html_with_emoji(text)
            buttons = None
            if reply_markup:
                buttons = self._convert_markup(reply_markup)

            await self._client.edit_message(
                chat_id,
                message_id,
                parsed_text,
                formatting_entities=entities if entities else None,
                buttons=buttons,
                link_preview=False
            )
            return {"ok": True}

        except Exception as e:
            error_str = str(e).lower()
            if "not modified" in error_str:
                return {"ok": True}
            logger.error(f"Userbot edit error: {e}", exc_info=True)
            return {"ok": False, "error": str(e)}

    def _convert_markup(self, aiogram_markup):
        """Конвертирует aiogram InlineKeyboardMarkup в telethon buttons."""
        from telethon.tl.types import (
            KeyboardButtonUrl,
            KeyboardButtonCallback,
        )
        from telethon.tl.types import ReplyInlineMarkup, KeyboardButtonRow

        if not aiogram_markup or not aiogram_markup.inline_keyboard:
            return None

        rows = []
        for row in aiogram_markup.inline_keyboard:
            buttons = []
            for btn in row:
                if btn.url:
                    buttons.append(KeyboardButtonUrl(
                        text=btn.text,
                        url=btn.url
                    ))
                elif btn.callback_data:
                    buttons.append(KeyboardButtonCallback(
                        text=btn.text,
                        data=btn.callback_data.encode()
                    ))
            if buttons:
                rows.append(KeyboardButtonRow(buttons=buttons))

        return rows if rows else None

    async def create_session(self, phone: str) -> dict:
        """
        Создать новую сессию.
        Возвращает {"stage": "code_sent"} или {"error": ...}
        """
        if not TELETHON_API_ID or not TELETHON_API_HASH:
            return {"error": "API_ID/API_HASH не настроены"}

        try:
            client = TelegramClient(
                StringSession(),
                TELETHON_API_ID,
                TELETHON_API_HASH
            )
            await client.connect()
            result = await client.send_code_request(phone)

            # Сохраняем временно
            self._pending_client = client
            self._pending_phone = phone
            self._pending_hash = result.phone_code_hash

            return {"stage": "code_sent", "phone_code_hash": result.phone_code_hash}

        except Exception as e:
            return {"error": str(e)}

    async def confirm_code(self, code: str = "", password: str = None) -> dict:
        """Подтвердить код и сохранить сессию."""
        if not hasattr(self, '_pending_client'):
            return {"error": "Сначала запросите код"}

        try:
            if password:
                # Если есть пароль - используем его
                await self._pending_client.sign_in(password=password)
            else:
                # Если есть код - используем код
                await self._pending_client.sign_in(
                    self._pending_phone,
                    code,
                    phone_code_hash=self._pending_hash
                )
        except Exception as e:
            error_str = str(e)
            if "Two-steps verification" in error_str or "SessionPasswordNeeded" in error_str or "PASSWORD_HASH_INVALID" in error_str:
                if password:
                    return {"error": "Неверный пароль"}
                return {"stage": "need_password"}
            return {"error": error_str}

        try:
            session_str = self._pending_client.session.save()
            set_setting("telethon_session", session_str)

            me = await self._pending_client.get_me()

            # Переключаем основной клиент
            if self._client:
                await self.disconnect()
            self._client = self._pending_client
            self._connected = True

            # Очищаем pending
            del self._pending_client
            del self._pending_phone
            del self._pending_hash

            return {
                "ok": True,
                "user_id": me.id,
                "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
                "premium": getattr(me, "premium", False),
            }

        except Exception as e:
            return {"error": str(e)}

    async def remove_session(self):
        """Удалить сессию."""
        await self.disconnect()
        set_setting("telethon_session", "")


# Глобальный экземпляр
userbot = UserbotClient()