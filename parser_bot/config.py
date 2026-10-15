import os

BOT_TOKEN = os.getenv("PARSER_BOT_TOKEN", '')
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", '0').split(",")]
DB_PATH = "parser.db"

SEND_TG_API_URL = "https://app.send.tg/internal/v1"
SEND_TG_BASE_URL = "https://app.send.tg"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.1 Safari/537.36"
)

POLL_INTERVAL = 1  # секунды между опросами офферов

# Telethon
TELETHON_API_ID = int(os.getenv("TELETHON_API_ID", '0'))
TELETHON_API_HASH = os.getenv("TELETHON_API_HASH", '')
TELETHON_SESSION_DIR = "sessions"