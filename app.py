import os
import json
import time
import threading
from datetime import datetime
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text
from dotenv import load_dotenv

from database import get_db, Event, create_tables
from google_calendar import (
    build_oauth_flow,
    credentials_from_token,
    token_from_credentials,
    get_events as google_get_events,
    create_event as google_create_event,
    update_event as google_update_event,
    delete_event as google_delete_event,
)
from yandex_calendar import (
    build_oauth_url as yandex_oauth_url,
    exchange_code_for_token as yandex_token_exchange,
    get_events as yandex_get_events,
    create_event as yandex_create_event,
    update_event as yandex_update_event,
    delete_event as yandex_delete_event,
)

load_dotenv()
app = FastAPI(title="Помняша — календарь с синхронизацией Google и Яндекс")
app.mount("/static", StaticFiles(directory="frontend"), name="static")
create_tables()

@app.get("/")
def root():
    return FileResponse(os.path.join("frontend", "calendar.html"))

@app.get("/oauth2/google/login")
def google_login():
    flow = build_oauth_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    return RedirectResponse(auth_url)


@app.get("/oauth2/google/callback")
def google_callback(request: Request, db: Session = Depends(get_db)):
    code = request.query_params.get("code")
    if not code:
        return JSONResponse({"error": "Missing code"}, status_code=400)

    try:
        flow = build_oauth_flow()
        flow.fetch_token(code=code)
        creds = flow.credentials
        token_json = token_from_credentials(creds)

        db.execute(
            text("""
                INSERT INTO oauth_tokens (user_id, provider, token_json)
                VALUES (:uid, 'google', :token)
                ON CONFLICT(user_id, provider)
                DO UPDATE SET token_json=:token
            """),
            {"uid": 1, "token": token_json},
        )
        db.commit()
        print("✅ Авторизация Google успешно завершена.")
        return RedirectResponse("/")
    except Exception as e:
        print("❌ Ошибка Google OAuth:", e)
        raise HTTPException(status_code=500, detail="Ошибка Google OAuth")


@app.get("/oauth2/yandex/login")
def yandex_login():
    return RedirectResponse(yandex_oauth_url())


@app.get("/oauth2/yandex/callback")
def yandex_callback(request: Request, db: Session = Depends(get_db)):
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Отсутствует код авторизации")

    token_data = yandex_token_exchange(code)
    if not token_data:
        raise HTTPException(status_code=400, detail="Не удалось получить токен")

    db.execute(
        text("""
            INSERT INTO oauth_tokens (user_id, provider, token_json)
            VALUES (:uid, 'yandex', :token)
            ON CONFLICT(user_id, provider)
            DO UPDATE SET token_json=:token
        """),
        {"uid": 1, "token": json.dumps(token_data)},
    )
    db.commit()
    print("✅ Авторизация Яндекс успешно завершена.")
    return RedirectResponse("/")

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
def create_event(event: dict, db: Session = Depends(get_db)):
    try:
        new_event = Event(
            title=event["title"],
            description=event.get("description"),
            start_time=event["start"],
            end_time=event["end"],
            source="local",
        )
        db.add(new_event)
        db.commit()
        db.refresh(new_event)

        # Мгновенная синхронизация
        threading.Thread(target=sync_to_external, args=(new_event, "add")).start()
        return {"status": "ok", "event": {"id": new_event.id}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/events/{event_id}")
def update_event(event_id: int, event: dict, db: Session = Depends(get_db)):
    ev = db.query(Event).filter(Event.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Событие не найдено")

    ev.title = event.get("title", ev.title)
    ev.description = event.get("description", ev.description)
    ev.start_time = event.get("start", ev.start_time)
    ev.end_time = event.get("end", ev.end_time)
    db.commit()

    threading.Thread(target=sync_to_external, args=(ev, "update")).start()
    return {"status": "updated"}


@app.delete("/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    ev = db.query(Event).filter(Event.id == event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Событие не найдено")

    db.delete(ev)
    db.commit()

    threading.Thread(target=sync_to_external, args=(ev, "delete")).start()
    return {"status": "deleted"}



def sync_to_external(event: Event, action: str):
    """Мгновенная синхронизация событий"""
    with next(get_db()) as db:
    
        g_row = db.execute(
            text("SELECT token_json FROM oauth_tokens WHERE provider='google'")
        ).fetchone()
        if g_row:
            creds = credentials_from_token(g_row[0])
            body = {
                "summary": event.title,
                "description": event.description or "",
                "start": {"dateTime": str(event.start_time), "timeZone": "Europe/Moscow"},
                "end": {"dateTime": str(event.end_time), "timeZone": "Europe/Moscow"},
            }
            if action == "add":
                google_create_event(creds, body)
            elif action == "update" and event.external_id:
                google_update_event(creds, event.external_id, body)
            elif action == "delete" and event.external_id:
                google_delete_event(creds, event.external_id)

    
        y_row = db.execute(
            text("SELECT token_json FROM oauth_tokens WHERE provider='yandex'")
        ).fetchone()
        if y_row:
            token_data = json.loads(y_row[0])
            token = token_data.get("access_token")
            if token:
                body = {
                    "summary": event.title,
                    "description": event.description or "",
                    "start": {"dateTime": str(event.start_time)},
                    "end": {"dateTime": str(event.end_time)},
                }
                if action == "add":
                    yandex_create_event(token, body)
                elif action == "update" and event.external_id:
                    yandex_update_event(token, event.external_id, body)
                elif action == "delete" and event.external_id:
                    yandex_delete_event(token, event.external_id)


def sync_from_external(db: Session):
    """Двухсторонняя синхронизация из Google и Яндекс"""

    g_row = db.execute(
        text("SELECT token_json FROM oauth_tokens WHERE provider='google'")
    ).fetchone()
    if g_row:
        creds = credentials_from_token(g_row[0])
        g_events = google_get_events(creds)
        for ev in g_events:
            eid = ev.get("id")
            title = ev.get("summary", "Без названия")
            start = ev.get("start", {}).get("dateTime")
            end = ev.get("end", {}).get("dateTime")
            existing = db.query(Event).filter_by(external_id=eid, source="google").first()
            if not existing and start and end:
                db.add(Event(title=title, start_time=start, end_time=end, source="google", external_id=eid))


    y_row = db.execute(
        text("SELECT token_json FROM oauth_tokens WHERE provider='yandex'")
    ).fetchone()
    if y_row:
        token_data = json.loads(y_row[0])
        token = token_data.get("access_token")
        if token:
            y_events = yandex_get_events(token)
            for ev in y_events:
                eid = ev.get("id")
                title = ev.get("summary", "Без названия")
                start = ev.get("start", {}).get("dateTime")
                end = ev.get("end", {}).get("dateTime")
                existing = db.query(Event).filter_by(external_id=eid, source="yandex").first()
                if not existing and start and end:
                    db.add(Event(title=title, start_time=start, end_time=end, source="yandex", external_id=eid))
    db.commit()


def auto_sync():
    """Автосинхронизация каждые 30 секунд"""
    while True:
        with next(get_db()) as db:
            sync_from_external(db)
        print("🔁 Автоматическая синхронизация выполнена.")
        time.sleep(30)


# Запускаем авто-синхронизацию в отдельном потоке
threading.Thread(target=auto_sync, daemon=True).start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)