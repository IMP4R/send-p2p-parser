import aiohttp
import logging
from database import get_setting

logger = logging.getLogger(__name__)


class MicroserviceClient:
    def get_url(self) -> str:
        ip = get_setting("micro_ip", "127.0.0.1")
        port = get_setting("micro_port", "8899")
        return f"http://{ip}:{port}"

    def get_token(self) -> str:
        return get_setting("micro_token", "")

    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.get_token()}"}

    async def check_connection(self) -> dict:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{self.get_url()}/api/health", timeout=aiohttp.ClientTimeout(total=5)
                ) as r:
                    return {"ok": r.status == 200, "status": r.status}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def check_auth(self) -> dict:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{self.get_url()}/api/auth/check",
                    headers=self.headers(),
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as r:
                    return await r.json()
        except Exception as e:
            return {"valid": False, "error": str(e)}

    async def refresh_cookies(self, phone: str) -> dict:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"{self.get_url()}/api/cookies/refresh",
                    json={"phone": phone, "headless": True},
                    headers=self.headers(),
                    timeout=aiohttp.ClientTimeout(total=180)
                ) as r:
                    return await r.json()
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def get_cookies(self, phone: str) -> dict:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{self.get_url()}/api/cookies/get",
                    params={"phone": phone},
                    headers=self.headers(),
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    return await r.json()
        except Exception as e:
            return {"error": str(e)}
