import os
import pickle
import time
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

REQUEST_DELAY = 0.5
MAX_RETRIES = 5

_WEEK_MAP = {
    "tyg. i": 0,
    "tyg. ii": 1,
}


def _week_parity(d: date, semester_start: date) -> int:
    start_of_week = semester_start - timedelta(days=semester_start.weekday())
    return ((d - start_of_week).days // 7) % 2


def _matches_week(week_value, parity: int) -> bool:
    if week_value is None:
        return True
    return _WEEK_MAP.get(str(week_value).lower()) == parity


def _normalize_week(week_value):
    if week_value is None:
        return None
    if isinstance(week_value, int):
        return week_value
    return _WEEK_MAP.get(str(week_value).lower())


def _iter_dates(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _parse_optional_date(value):
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def expand_occurrences(events, semester_start: str, semester_end: str, free_days=None, day_overrides=None):
    start_date = datetime.strptime(semester_start, "%Y-%m-%d").date()
    end_date = datetime.strptime(semester_end, "%Y-%m-%d").date()
    free_set = {
        datetime.strptime(d, "%Y-%m-%d").date()
        for d in (free_days or [])
    }
    overrides = {
        datetime.strptime(d, "%Y-%m-%d").date(): v
        for d, v in (day_overrides or {}).items()
    }

    occurrences = []
    for d in _iter_dates(start_date, end_date):
        if d in free_set:
            continue
        override = overrides.get(d, {})
        parity = _normalize_week(override.get("week"))
        if parity is None:
            parity = _week_parity(d, start_date)
        target_day = override.get("day", d.weekday())

        for e in events:
            if e.get("day") != target_day:
                continue
            date_range = e.get("date_range")
            if date_range:
                range_start = _parse_optional_date(date_range.get("start"))
                range_end = _parse_optional_date(date_range.get("end"))
                if range_start is not None and d < range_start:
                    continue
                if range_end is not None and d > range_end:
                    continue
            elif not _matches_week(e.get("week"), parity):
                continue

            start_dt = datetime.combine(d, datetime.strptime(e["start"], "%H:%M").time())
            end_dt = datetime.combine(d, datetime.strptime(e["end"], "%H:%M").time())
            summary = f'{e["subject"]} ({e["class_type"]})'.strip()
            description = f'Prowadzący: {e["lecturer"]}'
            if e.get("group"):
                description += f', grupa {e["group"]}'

            occurrences.append({
                "start": start_dt,
                "end": end_dt,
                "summary": summary,
                "location": e["room"],
                "description": description,
                "lecturer": e["lecturer"],
                "group": e.get("group"),
            })

    return occurrences


def _expand_from_data(data):
    return expand_occurrences(
        events=data.get("events", []),
        semester_start=data["semester_start"],
        semester_end=data["semester_end"],
        free_days=data.get("free_days"),
        day_overrides=data.get("day_overrides"),
    )


class IcsExporter:
    def export(self, data, out_path) -> list:
        occurrences = _expand_from_data(data)

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//PBTimetableExtractor//PL",
            "CALSCALE:GREGORIAN",
        ]

        for occ in occurrences:
            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{uuid.uuid4()}",
                f"DTSTART:{occ['start'].strftime('%Y%m%dT%H%M%S')}",
                f"DTEND:{occ['end'].strftime('%Y%m%dT%H%M%S')}",
                f"SUMMARY:{occ['summary']}",
                f"LOCATION:{occ['location']}",
                f"DESCRIPTION:{occ['description']}",
                "END:VEVENT",
            ])

        lines.append("END:VCALENDAR")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"Zapisano plik .ics: {out_path}")
        return occurrences


class GoogleCalendarExporter:
    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    def __init__(self, credentials_path="credentials.json", token_path="token.pickle", app_name="PBTimetableExtractor"):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.app_name = app_name
        self.service = self._build_service()

    def _build_service(self):
        print("Uwierzytelnianie z Google Calendar...")
        creds = None
        if self.token_path and os.path.exists(self.token_path):
            with open(self.token_path, "rb") as token_file:
                creds = pickle.load(token_file)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                print("Odświeżanie tokenu...")
                creds.refresh(Request())
            else:
                print("Zaloguj się w przeglądarce...")
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, self.SCOPES)
                creds = flow.run_local_server(port=0)

            with open(self.token_path, "wb") as token_file:
                pickle.dump(creds, token_file)

        print("Zalogowano pomyślnie.")
        return build("calendar", "v3", credentials=creds)

    def _execute(self, func):
        delay = 1
        for attempt in range(MAX_RETRIES):
            try:
                return func()
            except HttpError as e:
                if e.resp.status not in (403, 429, 500, 502, 503) or attempt == MAX_RETRIES - 1:
                    raise
                print(f"\rBłąd {e.resp.status}, ponawiam za {delay}s...", end="", flush=True)
                time.sleep(delay)
                delay = min(delay * 2, 30)

    def _group_for_series(self, occurrences):
        groups = defaultdict(list)
        for occ in occurrences:
            key = (
                occ["summary"],
                occ["location"],
                occ["description"],
                occ["start"].time().strftime("%H:%M:%S"),
                occ["end"].time().strftime("%H:%M:%S"),
            )
            groups[key].append(occ)
        return groups

    def _iter_managed_events(self, calendar_id: str):
        page_token = None
        while True:
            resp = self._execute(
                lambda: self.service.events().list(
                    calendarId=calendar_id,
                    maxResults=2500,
                    singleEvents=False,
                    pageToken=page_token,
                    privateExtendedProperty="pbte=1",
                ).execute()
            )
            for item in resp.get("items", []):
                yield item
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    def _purge_managed(self, calendar_id: str):
        print("Pobieranie starych wydarzeń planu...")
        managed = list(self._iter_managed_events(calendar_id))
        total = len(managed)
        if total == 0:
            print("Brak starych wydarzeń do usunięcia.")
            return
        for i, ev in enumerate(managed, 1):
            self._execute(
                lambda ev=ev: self.service.events().delete(
                    calendarId=calendar_id, eventId=ev["id"]
                ).execute()
            )
            print(f"\rUsuwanie ({i}/{total}): {ev.get('summary')}", end="", flush=True)
            time.sleep(REQUEST_DELAY)
        print(f"\nUsunięto: {total}")

    def sync(self, calendar_id: str, data, timezone="Europe/Warsaw", purge_managed=True):
        occurrences = _expand_from_data(data)

        if purge_managed:
            self._purge_managed(calendar_id)

        grouped = self._group_for_series(occurrences)
        total_groups = len(grouped)

        for i, ((summary, location, description, start_time, end_time), items) in enumerate(grouped.items(), 1):
            items = sorted(items, key=lambda x: x["start"])
            first = items[0]
            start_iso = first["start"].isoformat()
            end_iso = first["end"].isoformat()

            body = {
                "summary": summary,
                "location": location,
                "description": description,
                "start": {"dateTime": start_iso, "timeZone": timezone},
                "end": {"dateTime": end_iso, "timeZone": timezone},
                "extendedProperties": {
                    "private": {
                        "pbte": "1",
                        "source": self.app_name,
                    }
                },
            }

            if len(items) > 1:
                rdates = ",".join(x["start"].strftime("%Y%m%dT%H%M%S") for x in items[1:])
                body["recurrence"] = [f"RDATE;TZID={timezone}:{rdates}"]

            self._execute(
                lambda body=body: self.service.events().insert(calendarId=calendar_id, body=body).execute()
            )
            print(f"\rDodawanie ({i}/{total_groups}): {summary}", end="", flush=True)
            time.sleep(REQUEST_DELAY)

        if total_groups:
            print(f"\nDodano: {total_groups}")

    def clear(self, calendar_id: str):
        self._purge_managed(calendar_id)
