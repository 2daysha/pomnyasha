import os
import secrets
from datetime import datetime
from typing import Dict, Any

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest

from database import get_db, create_tables, Event, get_user_creds, save_user_creds
from google_calendar import (
    create_google_event,
    update_google_event,
    delete_google_event,
    sync_google_calendar,
)

app = FastAPI(title="Помняша")

# Путь к client_secret.json (положи файл в ./secrets/client_secret.json)
CLIENT_SECRETS_FILE = os.path.join("secrets", "client_secret.json")
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]
REDIRECT_URI = "http://127.0.0.1:8000/oauth2/callback"


def _get_or_create_session_user_id(request: Request) -> tuple[int, bool]:
    sid_cookie = request.cookies.get("sid")
    if sid_cookie and sid_cookie.isdigit():
        return int(sid_cookie), False
    new_sid = secrets.randbits(63)
    return int(new_sid), True


# ---------- OAuth ----------
@app.get("/oauth2/login")
def oauth2_login(request: Request):
    user_id, need_cookie = _get_or_create_session_user_id(request)
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    resp = RedirectResponse(auth_url)
    if need_cookie:
        resp.set_cookie("sid", str(user_id), httponly=True, samesite="Lax")
    return resp


@app.get("/oauth2/callback")
def oauth2_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return JSONResponse({"error": "Missing code"}, status_code=400)

    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
        user_id, need_cookie = _get_or_create_session_user_id(request)
        save_user_creds(user_id, creds)
        print(f"✅ Google токен сохранён для пользователя {user_id}")

        # моментально подтянем из Google всё в локальный календарь
        sync_google_calendar(user_id)

        resp = RedirectResponse("/calendar")
        if need_cookie:
            resp.set_cookie("sid", str(user_id), httponly=True, samesite="Lax")
        return resp
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/me")
def me(request: Request):
    user_id_cookie = request.cookies.get("sid")
    user_id = int(user_id_cookie) if user_id_cookie and user_id_cookie.isdigit() else None
    creds = get_user_creds(user_id)
    if not creds:
        return {"authorized": False}
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            save_user_creds(user_id, creds)
        else:
            return {"authorized": False}
    return {"authorized": True}


# ---------- CRUD локальных событий ----------
@app.get("/events")
def get_events(db: Session = Depends(get_db)):
    events = db.query(Event).all()
    return [
        {
            "id": e.id,
            "title": e.title,
            "description": e.description,
            "start": e.start_time,
            "end": e.end_time,
            "source": e.source,
        }
        for e in events
    ]


@app.post("/events")
def create_event(event: dict, request: Request, db: Session = Depends(get_db)):
    user_id, _ = _get_or_create_session_user_id(request)
new_event = Event(
        title=event["title"],
        description=event.get("description"),
        start_time=datetime.fromisoformat(event["start"]),
        end_time=datetime.fromisoformat(event["end"]),
        source="local",
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)

    # мгновенно отправим в Google и сохраним external_id
    g_id = create_google_event(user_id, event)
    if g_id:
        new_event.external_id = g_id
        new_event.source = "google"
        db.commit()

    # и сразу же подтянем изменения из Google (на случай, если Google их трансформировал)
    sync_google_calendar(user_id)

    return {"status": "ok", "event": {"id": new_event.id}}


@app.put("/events/{event_id}")
def update_event(event_id: int, data: dict, request: Request, db: Session = Depends(get_db)):
    user_id, _ = _get_or_create_session_user_id(request)
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Событие не найдено")

    event.title = data.get("title", event.title)
    event.description = data.get("description", event.description)
    event.start_time = datetime.fromisoformat(data["start"])
    event.end_time = datetime.fromisoformat(data["end"])
    db.commit()
    db.refresh(event)

    update_google_event(user_id, event)

    # и подхватим из Google обратно (на случай корректировок)
    sync_google_calendar(user_id)
    return {"status": "updated"}


@app.delete("/events/{event_id}")
def delete_event(event_id: int, request: Request, db: Session = Depends(get_db)):
    user_id, _ = _get_or_create_session_user_id(request)
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Событие не найдено")

    delete_google_event(user_id, event)
    db.delete(event)
    db.commit()

    # потом синкнемся, чтобы очистить состояние
    sync_google_calendar(user_id)
    return {"status": "deleted"}


# ---------- ручной синк ----------
@app.get("/sync")
def sync(request: Request):
    user_id, _ = _get_or_create_session_user_id(request)
    sync_google_calendar(user_id)
    return {"status": "ok"}


# ---------- страницы ----------
@app.get("/")
def root(request: Request):
    user_id, need_cookie = _get_or_create_session_user_id(request)
    resp = FileResponse(os.path.join("frontend", "index.html"))
    if need_cookie:
        resp.set_cookie("sid", str(user_id), httponly=True, samesite="Lax")
    return resp


@app.get("/calendar")
def calendar_page(request: Request):
    user_id, need_cookie = _get_or_create_session_user_id(request)
    resp = FileResponse(os.path.join("frontend", "my_calendar.html"))
    if need_cookie:
        resp.set_cookie("sid", str(user_id), httponly=True, samesite="Lax")
    return resp


# ---------- статика и старт ----------
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.on_event("startup")
def startup_event():
    create_tables()


if name == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)