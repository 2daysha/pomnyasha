from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session
from sqlalchemy import select
from database import engine, Event, get_user_creds

TIMEZONE = "Europe/Moscow"

def _service(user_id: int):
    creds = get_user_creds(user_id)
    if not creds:
        return None
    return build("calendar", "v3", credentials=creds)

def create_google_event(user_id: int, event_data: dict) -> str | None:
    svc = _service(user_id)
    if not svc:
        return None
    body = {
        "summary": event_data["title"],
        "description": event_data.get("description", ""),
        "start": {"dateTime": event_data["start"], "timeZone": TIMEZONE},
        "end": {"dateTime": event_data["end"], "timeZone": TIMEZONE},
    }
    created = svc.events().insert(calendarId="primary", body=body).execute()
    return created.get("id")

def update_google_event(user_id: int, event: Event):
    svc = _service(user_id)
    if not svc or not event.external_id_google:
        return
    body = {
        "summary": event.title,
        "description": event.description or "",
        "start": {"dateTime": event.start_time.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": event.end_time.isoformat(), "timeZone": TIMEZONE},
    }
    try:
        svc.events().update(calendarId="primary", eventId=event.external_id_google, body=body).execute()
    except HttpError as e:
        if getattr(e, "resp", None) and e.resp.status == 404:
            db = Session(engine)
            try:
                db.delete(event)
                db.commit()
            finally:
                db.close()

def delete_google_event(user_id: int, event: Event):
    svc = _service(user_id)
    if not svc or not event.external_id_google:
        return
    try:
        svc.events().delete(calendarId="primary", eventId=event.external_id_google).execute()
    except HttpError:
        pass

def _fetch_google_events_window(user_id: int) -> list[dict]:
    svc = _service(user_id)
    if not svc:
        return []
    time_min = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
    time_max = (datetime.utcnow() + timedelta(days=90)).isoformat() + "Z"
    result = svc.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        showDeleted=True,
        orderBy="updated",
        maxResults=250,
    ).execute()
    return result.get("items", [])

def _dt_from_google(val: str) -> datetime:
    return datetime.fromisoformat(val.replace("Z", "+00:00"))

def sync_google_calendar(user_id: int):
    svc = _service(user_id)
    if not svc:
        print("Нет Google авторизации")
        return
    db = Session(engine)
    try:
        google_events = _fetch_google_events_window(user_id)
        g_ids = set()
        for g in google_events:
            g_id = g["id"]
            g_ids.add(g_id)
            g_summary = g.get("summary", "Без названия")
            g_desc = g.get("description", "")
            g_start = g.get("start", {}).get("dateTime")
            g_end = g.get("end", {}).get("dateTime")
            g_deleted = g.get("status") == "cancelled"
            local = db.scalar(select(Event).where(Event.external_id_google == g_id))
            if g_deleted:
                if local:
                    db.delete(local)
                continue
            if not g_start or not g_end:
                continue
            start_dt = _dt_from_google(g_start)
            end_dt = _dt_from_google(g_end)
            if not local:
                new_event = Event(
                    user_id=user_id,
                    title=g_summary,
                    description=g_desc,
                    start_time=start_dt,
                    end_time=end_dt,
                    external_id_google=g_id,
                    source="google",
                )
                db.add(new_event)
            else:
                changed = False
                if local.title != g_summary:
                    local.title = g_summary
                    changed = True
                if (local.description or "") != (g_desc or ""):
                    local.description = g_desc
                    changed = True
                if local.start_time != start_dt or local.end_time != end_dt:
                    local.start_time = start_dt
                    local.end_time = end_dt
                    changed = True
                if changed:
                    db.add(local)
        local_with_g = db.scalars(select(Event).where(Event.external_id_google.is_not(None))).all()
        for e in local_with_g:
            if e.external_id_google not in g_ids:
                db.delete(e)
        db.commit()
        print("Синхронизация Google завершена")
    except Exception as e:
        print("Ошибка синхронизации Google:", e)
    finally:
        db.close()