import os
import secrets
from datetime import datetime
from typing import Dict, Any
from dateutil import parser as dtparser

from fastapi import FastAPI, Request, Depends, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db, create_tables, Event, get_user_creds, save_user_creds
from google_calendar import (
    create_google_event,
    delete_google_event,
    sync_google_calendar,
    upsert_google_event
)
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest

from ai import ask_gigachat


CLIENT_SECRETS_FILE = os.path.join("secrets", "client_secret.json")
SCOPES = ["https://www.googleapis.com/auth/calendar",
          "https://www.googleapis.com/auth/calendar.events"]
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/oauth2/callback")

app = FastAPI(title="Помняша Backend")


origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-Id"],
)



def _parse_dt(val: str) -> datetime:
    if val.endswith("Z"):
        val = val.replace("Z", "+00:00")
    dt = dtparser.parse(val)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return dt


def _get_or_create_session(request: Request) -> tuple[int, bool]:
    header_sid = request.headers.get("x-session-id")
    if header_sid and header_sid.isdigit():
        return int(header_sid), False

    sid = request.cookies.get("sid")
    if sid and sid.isdigit():
        return int(sid), False

    return secrets.randbits(63), True


def _persist_session(response: Response, sid: int):
    response.set_cookie(
        "sid",
        str(sid),
        httponly=True,
        samesite="Lax",
        secure=False
    )
    response.headers["X-Session-Id"] = str(sid)



@app.get("/oauth2/login")
def oauth_login(request: Request):
    user_id, _ = _get_or_create_session(request)

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )

    resp = RedirectResponse(auth_url)
    _persist_session(resp, user_id)

    return resp


@app.get("/oauth2/callback")
def oauth_callback(request: Request, db: Session = Depends(get_db)):
    code = request.query_params.get("code")
    if not code:
        return JSONResponse({"error": "missing code"}, status_code=400)

    try:
        user_id, _ = _get_or_create_session(request)

        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        flow.fetch_token(code=code)

        creds = flow.credentials
        save_user_creds(user_id, creds)

        sync_google_calendar(user_id)

        local_events = db.query(Event).filter(
            Event.user_id == user_id,
            Event.external_id.is_(None)
        ).all()

        for ev in local_events:
            gid = create_google_event(user_id, {
                "title": ev.title,
                "description": ev.description or "",
                "start": ev.start_time.isoformat(),
                "end": ev.end_time.isoformat()
            })
            if gid:
                ev.external_id = gid
                ev.source = "google"

        db.commit()

        resp = RedirectResponse("http://localhost:3000")
        _persist_session(resp, user_id)

        return resp

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)



@app.get("/me")
def me(request: Request, response: Response):
    sid = request.headers.get("x-session-id")
    if not (sid and sid.isdigit()):
        sid_cookie = request.cookies.get("sid")
        if sid_cookie and sid_cookie.isdigit():
            sid = sid_cookie
        else:
            return {"authorized": False}

    user_id = int(sid)
    creds = get_user_creds(user_id)
    if not creds:
        return {"authorized": False}

    if not creds.valid:
        try:
            creds.refresh(GoogleRequest())
            save_user_creds(user_id, creds)
        except:
            return {"authorized": False}

    _persist_session(response, user_id)
    return {"authorized": True}



@app.get("/events")
def get_events(request: Request, response: Response, db: Session = Depends(get_db)):
    user_id, _ = _get_or_create_session(request)
    _persist_session(response, user_id)

    events = db.query(Event).filter(Event.user_id == user_id).all()

    return [{
        "id": e.id,
        "title": e.title,
        "description": e.description or "",
        "start": e.start_time.isoformat(),
        "end": e.end_time.isoformat(),
        "source": e.source
    } for e in events]


@app.post("/events")
def create_event(
    data: Dict[str, Any],
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    try:
        user_id, _ = _get_or_create_session(request)
        _persist_session(response, user_id)

        title = data.get("title", "Без названия")
        description = data.get("description") or ""

        start = _parse_dt(data["start"])
        end = _parse_dt(data.get("end", data["start"]))

        ev = Event(
            user_id=user_id,
            title=title,
            description=description,
            start_time=start,
            end_time=end,
            source="local"
        )

        db.add(ev)
        db.commit()
        db.refresh(ev)

        gid = upsert_google_event(user_id, ev)
        if gid:
            ev.external_id = gid
            ev.source = "google"
            db.commit()

        sync_google_calendar(user_id)

        return {"status": "ok", "id": ev.id}

    except Exception as e:
        return JSONResponse({"error": f"create_event failed: {e}"}, status_code=400)


@app.put("/events/{event_id}")
def update_event(
    event_id: int,
    data: Dict[str, Any],
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    try:
        user_id, _ = _get_or_create_session(request)
        _persist_session(response, user_id)

        ev = db.query(Event).filter(
            Event.id == event_id,
            Event.user_id == user_id
        ).first()

        if not ev:
            raise HTTPException(status_code=404)

        ev.title = data.get("title", ev.title)
        ev.description = data.get("description", ev.description)

        if "start" in data:
            ev.start_time = _parse_dt(data["start"])
        if "end" in data:
            ev.end_time = _parse_dt(data["end"])

        db.commit()
        db.refresh(ev)

        upsert_google_event(user_id, ev)
        sync_google_calendar(user_id)

        return {"status": "updated"}

    except Exception as e:
        return JSONResponse({"error": f"update_event failed: {e}"}, status_code=400)


@app.delete("/events/{event_id}")
def delete_event(event_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        user_id, _ = _get_or_create_session(request)
        _persist_session(response, user_id)

        ev = db.query(Event).filter(
            Event.id == event_id,
            Event.user_id == user_id
        ).first()

        if not ev:
            raise HTTPException(404)

        delete_google_event(user_id, ev)
        db.delete(ev)
        db.commit()

        sync_google_calendar(user_id)

        return {"status": "deleted"}

    except Exception as e:
        return JSONResponse({"error": f"delete_event failed: {e}"}, status_code=400)



@app.get("/sync")
def do_sync(request: Request, response: Response):
    user_id, _ = _get_or_create_session(request)
    _persist_session(response, user_id)
    sync_google_calendar(user_id)
    return {"status": "ok"}



@app.post("/chat")
def chat_endpoint(data: Dict[str, Any]):
    msg = data.get("message", "")
    return {"reply": ask_gigachat(msg)}



@app.on_event("startup")
def startup():
    create_tables()
    print("База готова")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
