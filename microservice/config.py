import os

BOT_TOKEN = os.getenv("MICRO_BOT_TOKEN", '')
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", '0').split(",")]
DB_PATH = "microservice.db"
COOKIES_DIR = ''
HOST = "0.0.0.0"
PORT = 8899

os.makedirs(COOKIES_DIR, exist_ok=True)
