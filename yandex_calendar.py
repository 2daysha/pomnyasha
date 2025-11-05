from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import uuid

from caldav import DAVClient
import vobject

from sqlalchemy.orm import Session
from sqlalchemy import select

from database import engine, Event, get_yandex_creds

CALDAV_URL = "https://caldav.yandex.ru"
TZ = timezone.utc  # Яндекс хранит в ICS; приведём к UTC, фронт уже преобразует локально.


def _client_and_calendar(user_id: int):
    """
    Возвращает (client, principal, calendar) или (None, None, None), если не настроены креды.
    Берём первый доступный календарь (обычно 'Календарь').
    """
    creds = get_yandex_creds(user_id)
    if not creds:
        return None, None, None
    username = creds.get("username")
    password = creds.get("app_password")
    if not (username and password):
        return None, None, None

    client = DAVClient(CALDAV_URL, username=username, password=password)
    principal = client.principal()
    calendars = principal.calendars()
    if not calendars:
        return client, principal, None
    # По умолчанию — первый
    return client, principal, calendars[0]


def _vevent_to_dict(component) -> dict:
    ve = component.vevent
    uid = str(ve.uid.value) if hasattr(ve, "uid") else None
    summary = str(ve.summary.value) if hasattr(ve, "summary") else "Без названия"
    description = str(ve.description.value) if hasattr(ve, "description") else ""
    # dtstart/dtend могут быть date (all-day) или datetime
    def _to_iso(dt):
        if isinstance(dt, datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            else:
                dt = dt.astimezone(TZ)
        else:
            # all-day -> считаем 00:00Z и +1 час для end
            dt = datetime.combine(dt, datetime.min.time(), tzinfo=TZ)
        return dt.isoformat()

    start = _to_iso(ve.dtstart.value)
    end = _to_iso(ve.dtend.value) if hasattr(ve, "dtend") else _to_iso(ve.dtstart.value + timedelta(hours=1))

    return {"id": uid, "title": summary, "description": description, "start": start, "end": end}


def yandex_list_events(user_id: int) -> List[dict]:
    """
    Возвращает список событий (id=UID) за окно [текущие -30д, +90д].
    """
    client, principal, calendar = _client_and_calendar(user_id)
    if not calendar:
        return []

    start = datetime.utcnow().replace(tzinfo=TZ) - timedelta(days=30)
    end = datetime.utcnow().replace(tzinfo=TZ) + timedelta(days=90)
    results = calendar.date_search(start=start, end=end)
    out = []
    for ev in results:
        try:
            comp = vobject.readOne(ev.vcalendar().to_ical())
            out.append(_vevent_to_dict(comp))
        except Exception:
            continue
    return out


def yandex_create_event(user_id: int, data: dict) -> Optional[str]:
    """
    data: {title, description?, start (iso), end (iso)} — создаёт событие, возвращает UID.
    """
    client, principal, calendar = _client_and_calendar(user_id)
    if not calendar:
        return None

    uid = str(uuid.uuid4())
    cal = vobject.iCalendar()
    ve = cal.add('vevent')
    ve.add('uid').value = uid
    ve.add('summary').value = data["title"]
    if data.get("description"):
        ve.add('description').value = data["description"]

    def _parse(dt_iso: str):
        dt = datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
        return dt.astimezone(TZ)

    ve.add('dtstart').value = _parse(data["start"])
    ve.add('dtend').value = _parse(data["end"])

    calendar.add_event(cal.serialize())
    return uid


def yandex_find_event_resource_by_uid(calendar, uid: str):
    """Небыстрый, но надёжный способ: пройтись по событиям и найти по UID."""
    events = calendar.events()
    for ev in events:
        try:
            comp = vobject.readOne(ev.vcalendar().to_ical())
            if hasattr(comp.vevent, "uid") and str(comp.vevent.uid.value) == uid:
                return ev
        except Exception:
            continue
    return None


def yandex_update_event(user_id: int, event: Event) -> None:
    client, principal, calendar = _client_and_calendar(user_id)
    if not calendar or not event.external_id_yandex:
        return

    res = yandex_find_event_resource_by_uid(calendar, event.external_id_yandex)
    if not res:
        # Нет на стороне Яндекс — создаём заново и обновляем UID
        new_uid = yandex_create_event(
            user_id,
            {
                "title": event.title,
                "description": event.description or "",
                "start": event.start_time.isoformat(),
                "end": event.end_time.isoformat(),
            },
        )
        if new_uid:
            db = Session(engine)
            try:
                ev = db.get(Event, event.id)
                if ev:
                    ev.external_id_yandex = new_uid
                    db.commit()
            finally:
                db.close()
        return

    comp = vobject.readOne(res.vcalendar().to_ical())
    ve = comp.vevent
    ve.summary.value = event.title
    ve.description.value = event.description or ""

    def _parse(dt):
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ)

    ve.dtstart.value = _parse(event.start_time)
    ve.dtend.value   = _parse(event.end_time)

    res.set_data(comp.serialize())


def yandex_delete_event(user_id: int, event: Event) -> None:
    client, principal, calendar = _client_and_calendar(user_id)
    if not calendar or not event.external_id_yandex:
        return
    res = yandex_find_event_resource_by_uid(calendar, event.external_id_yandex)
    if res:
        try:
            res.delete()
        except Exception:
            pass