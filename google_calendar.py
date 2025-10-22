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
    if not svc or not event.external_id:
        return
    body = {
        "summary": event.title,
        "description": event.description or "",
        "start": {"dateTime": event.start_time.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": event.end_time.isoformat(), "timeZone": TIMEZONE},
    }
    try:
        svc.events().update(calendarId="primary", eventId=event.external_id, body=body).execute()
    except HttpError as e:
        if e.resp.status == 404:
            db = Session(engine)
            db.delete(event)
            db.commit()
            db.close()


def delete_google_event(user_id: int, event: Event):
    svc = _service(user_id)
    if not svc or not event.external_id:
        return
    try:
        svc.events().delete(calendarId="primary", eventId=event.external_id).execute()
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
        print("❌ Нет Google авторизации")
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
            g_updated = g.get("updated")
            g_deleted = g.get("status") == "cancelled"

            local = db.scalar(select(Event).where(Event.external_id == g_id))
            if g_deleted:
                if local:
                    print(f"🗑 Удалено в Google — удаляем локально: {local.title}")
                    db.delete(local)
                continue

            if not g_start or not g_end:
                continue

            start_dt = _dt_from_google(g_start)
            end_dt = _dt_from_google(g_end)

            if not local:
                # Добавляем новое из Google
                new_event = Event(
                    user_id=user_id,
                    title=g_summary,
                    description=g_desc,
                    start_time=start_dt,
                    end_time=end_dt,
                    external_id=g_id,
                    source="google",
                )
                db.add(new_event)
                print(f"Добавлено из Google: {g_summary}")
            else:
                # Проверяем, есть ли изменения
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
                    print(f"🔁 Обновлено из Google: {g_summary}")
                    db.add(local)

        # Удаляем локальные, которых нет в Google
        local_with_g = db.scalars(select(Event).where(Event.external_id.is_not(None))).all()
        for e in local_with_g:
            if e.external_id not in g_ids:
                print(f"🗑 Событие {e.title} удалено в Google — удаляем локально.")
                db.delete(e)

        db.commit()
        print("✅ Полная синхронизация завершена.")
    except Exception as e:
        print("❌ Ошибка синхронизации:", e)
    finally:
        db.close()