import json
import os
import logging
from config import COOKIES_DIR

logger = logging.getLogger(__name__)


def save_cookies_to_file(session_id: str, cookies: list):
    path = os.path.join(COOKIES_DIR, f"session_{session_id}.json")
    with open(path, "w") as f:
        json.dump(cookies, f, indent=2)
    logger.info(f"💾 Куки: {path}")


def load_cookies_from_file(session_id: str) -> list | None:
    path = os.path.join(COOKIES_DIR, f"session_{session_id}.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None


async def refresh_cookies_playwright(
    phone: str, headless: bool = True
) -> list | None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("playwright not installed")

    cookies = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-gpu", "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/127.0.0.1 Safari/537.36"
            ),
        )
        page = await context.new_page()

        try:
            await page.goto(
                "https://app.send.tg/", wait_until="networkidle"
            )

            auth_btn = page.locator('[data-test-id="auth-button"]')
            await auth_btn.wait_for(state="visible", timeout=15000)
            await auth_btn.click()
            await page.wait_for_timeout(3000)

            login_page = page
            if len(context.pages) > 1:
                login_page = context.pages[-1]

            code_input = login_page.locator("#login-phone-code")
            await code_input.wait_for(state="visible", timeout=15000)

            clean = phone.lstrip("+")
            if clean.startswith("7") and len(clean) == 11:
                c_code, p_number = "7", clean[1:]
            elif clean.startswith("1") and len(clean) == 11:
                c_code, p_number = "1", clean[1:]
            elif clean.startswith("380"):
                c_code, p_number = "380", clean[3:]
            elif clean.startswith("375"):
                c_code, p_number = "375", clean[3:]
            else:
                c_code, p_number = clean[0], clean[1:]

            await login_page.evaluate(f'''
                const f = document.getElementById("login-phone-code");
                const s = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, "value").set;
                s.call(f, "+{c_code}");
                f.dispatchEvent(new Event("input", {{bubbles:true}}));
                f.dispatchEvent(new Event("change", {{bubbles:true}}));
            ''')
            await login_page.wait_for_timeout(300)

            await login_page.evaluate(f'''
                const f = document.getElementById("login-phone");
                const s = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, "value").set;
                s.call(f, "{p_number}");
                f.dispatchEvent(new Event("input", {{bubbles:true}}));
                f.dispatchEvent(new Event("change", {{bubbles:true}}));
            ''')
            await login_page.wait_for_timeout(500)

            await login_page.locator(
                'button[type="submit"]'
            ).first.click()

            authorized = False
            for i in range(120):
                await login_page.wait_for_timeout(1000)

                for btn_text in [
                    "Принять", "Accept", "Confirm", "Log In"
                ]:
                    btn = login_page.locator(
                        f'button:has-text("{btn_text}")'
                    )
                    try:
                        if (await btn.count() > 0
                                and await btn.first.is_visible()):
                            await btn.first.click()
                            await login_page.wait_for_timeout(3000)
                            authorized = True
                            break
                    except Exception:
                        pass

                if authorized:
                    break

                main_url = context.pages[0].url
                if ("send.tg" in main_url
                        and "oauth" not in main_url
                        and "telegram" not in main_url):
                    await page.wait_for_timeout(2000)
                    authorized = True
                    break

            if not authorized:
                await browser.close()
                return None

            await page.wait_for_timeout(3000)
            cookies = await context.cookies()

        except Exception as e:
            logger.error(f"❌ {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

    return cookies
