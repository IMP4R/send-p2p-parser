from fastapi import FastAPI, Header, HTTPException, BackgroundTasks
from pydantic import BaseModel
import uvicorn
import json

from database import (
    init_db, validate_token, save_cookie_session,
    get_cookie_session
)
from cookie_manager import refresh_cookies_playwright, save_cookies_to_file
from config import HOST, PORT

app = FastAPI(title="Send.TG Cookie Microservice")


class RefreshRequest(BaseModel):
    phone: str
    headless: bool = True


class CookieResponse(BaseModel):
    success: bool
    message: str = ""
    cookies: list | None = None


def auth_token(authorization: str = Header(...)) -> dict:
    token = authorization.replace("Bearer ", "")
    data = validate_token(token)
    if not data:
        raise HTTPException(401, "Invalid or inactive token")
    return data


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/auth/check")
async def check_auth(authorization: str = Header(...)):
    data = auth_token(authorization)
    return {
        "valid": True,
        "user_id": data["user_id"],
        "label": data["label"]
    }


@app.post("/api/cookies/refresh", response_model=CookieResponse)
async def api_refresh_cookies(
    req: RefreshRequest,
    authorization: str = Header(...)
):
    token_data = auth_token(authorization)
    token = authorization.replace("Bearer ", "")

    try:
        cookies = await refresh_cookies_playwright(
            req.phone, req.headless
        )
    except Exception as e:
        save_cookie_session(token, req.phone, [], f"error: {e}")
        return CookieResponse(success=False, message=str(e))

    if not cookies:
        save_cookie_session(token, req.phone, [], "timeout")
        return CookieResponse(
            success=False, message="Auth timeout (120s)"
        )

    save_cookie_session(token, req.phone, cookies, "ok")
    session_id = f"{token_data['id']}_{req.phone.replace('+', '')}"
    save_cookies_to_file(session_id, cookies)

    return CookieResponse(
        success=True,
        message=f"Got {len(cookies)} cookies",
        cookies=cookies
    )


@app.get("/api/cookies/get")
async def api_get_cookies(
    phone: str,
    authorization: str = Header(...)
):
    token_data = auth_token(authorization)
    token = authorization.replace("Bearer ", "")

    session = get_cookie_session(token, phone)
    if not session:
        raise HTTPException(404, "No cookies found for this phone")

    return {
        "phone": phone,
        "status": session["status"],
        "cookies": json.loads(session["cookies"]) if session["cookies"] else [],
        "updated_at": session["updated_at"]
    }


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
