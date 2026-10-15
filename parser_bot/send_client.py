import requests
import json
import logging
from config import SEND_TG_API_URL, SEND_TG_BASE_URL, USER_AGENT
from database import get_account

logger = logging.getLogger(__name__)


class SendTGClient:
    def __init__(self):
        self.session = requests.Session()
        self._loaded = False

    def load(self) -> bool:
        account = get_account()
        if not account or not account["is_active"]:
            logger.warning("Нет активного аккаунта")
            return False

        cookies_data = json.loads(account["cookies"])

        self.session.cookies.clear()
        if isinstance(cookies_data, list):
            for c in cookies_data:
                self.session.cookies.set(
                    c["name"],
                    c["value"],
                    domain=c.get("domain", "app.send.tg"),
                    path=c.get("path", "/"),
                )
        elif isinstance(cookies_data, dict):
            for name, value in cookies_data.items():
                self.session.cookies.set(name, value)

        self.session.headers.update({
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "referer": f"{SEND_TG_BASE_URL}/",
            "user-agent": USER_AGENT,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        })
        self._loaded = True
        return True

    def check_auth(self) -> bool:
        if not self._loaded:
            self.load()
        try:
            resp = self.session.get(
                f"{SEND_TG_API_URL}/wallet/balance", timeout=10
            )
            return resp.status_code == 200
        except Exception:
            return False

    def get_offer(self, offer_id: int) -> dict | None:
        if not self._loaded:
            if not self.load():
                return None

        try:
            resp = self.session.get(
                f"{SEND_TG_API_URL}/p2p/offers/{offer_id}",
                timeout=10
            )

            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 404:
                return {"statusCode": 404, "error": "NotFoundError",
                        "message": "OFFER_NOT_FOUND"}
            elif resp.status_code == 401:
                return {"statusCode": 401, "error": "Unauthorized"}
            elif resp.status_code == 429:
                return {"statusCode": 429, "error": "RateLimit"}
            else:
                return {"statusCode": resp.status_code,
                        "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            logger.error(f"Offer {offer_id} error: {e}")
            return None
