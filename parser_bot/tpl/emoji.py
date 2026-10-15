import re
from aiogram.types import Message

CUSTOM_EMOJI_RE = re.compile(r'<tg-emoji\s+emoji-id=["\'](\d+)["\']>')


def extract_emoji_ids(text: str) -> list[str]:
    return CUSTOM_EMOJI_RE.findall(text)


def _utf16_offset_to_python(text: str, utf16_offset: int) -> int:
    current_utf16 = 0
    for i, char in enumerate(text):
        if current_utf16 >= utf16_offset:
            return i
        if ord(char) > 0xFFFF:
            current_utf16 += 2
        else:
            current_utf16 += 1
    return len(text)


def rebuild_text_with_emoji(message: Message) -> str:
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []

    emojis = [
        {
            "utf16_offset": e.offset,
            "utf16_length": e.length,
            "id": e.custom_emoji_id
        }
        for e in entities
        if e.type == "custom_emoji" and e.custom_emoji_id
    ]

    if not emojis:
        return text

    for ce in emojis:
        ce["start"] = _utf16_offset_to_python(text, ce["utf16_offset"])
        ce["end"] = _utf16_offset_to_python(
            text, ce["utf16_offset"] + ce["utf16_length"]
        )

    for ce in sorted(emojis, key=lambda x: x["start"], reverse=True):
        s, e = ce["start"], ce["end"]
        visible = text[s:e]
        text = (
            text[:s]
            + f'<tg-emoji emoji-id="{ce["id"]}">{visible}</tg-emoji>'
            + text[e:]
        )

    return text


def extract_first_emoji_id(message: Message) -> str | None:
    entities = message.entities or []
    for e in entities:
        if e.type == "custom_emoji" and e.custom_emoji_id:
            return e.custom_emoji_id
    return None
