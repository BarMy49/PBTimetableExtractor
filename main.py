import requests
import re
import json
import os
import pickle
import time
from datetime import datetime, date, timedelta
import uuid
from collections import defaultdict
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

REQUEST_DELAY = 0.5
MAX_RETRIES = 5

class ScheduleParser:
    def __init__(self, link=None):
        self._pattern = re.compile(
            r"<li>\s*godz\.\s*<b>(?P<time>[^<]+)</b>.*?"
            r"(?:\((?P<week>tyg\.\s*[IVX]+)\)\s*)?"
            r"(?P<class_type>[^<]*?)\s*z\s*<q>(?P<subject>[^<]+)</q>,\s*prowadzący\s*(?P<lecturer>[^<]+?)\s*w sali\s*(?P<room>[^,<]+)"
            r"(?:,\s*grupa\s*nr\s*(?P<group>\d+))?",
            re.IGNORECASE | re.DOTALL,
        )
        self._day_pattern = re.compile(
            r"<li>\s*(?P<day>[^<]+)\s*<ul>(?P<body>.*?)</ul>\s*</li>",
            re.IGNORECASE | re.DOTALL,
        )
        self._day_map = {
            "poniedziałek": 0,
            "wtorek": 1,
            "środa": 2,
            "czwartek": 3,
            "piątek": 4,
        }
        self.link = link

    def get_schedule(self):
        if self.link is not None:
            print(f"Pobieranie planu z: {self.link}")
            response = requests.get(self.link)
            if response.status_code == 200:
                print("Plan pobrany.")
                return response.text
            print(f"Failed to retrieve schedule. Status code: {response.status_code}")
        return None

    def parse(self, html):
        results = []
        for day_match in self._day_pattern.finditer(html):
            day_name = day_match.group("day").strip().lower()
            day = self._day_map.get(day_name)
            body = day_match.group("body")
            for m in self._pattern.finditer(body):
                time = m.group("time").strip()
                start, end = [t.strip() for t in time.split("-", 1)] if "-" in time else (time, "")
                class_type = m.group("class_type").strip()
                week = m.group("week").strip() if m.group("week") else None
                if not week:
                    week_match = re.search(r"\(tyg\.\s*[IVX]+\)", class_type, re.IGNORECASE)
                    if week_match:
                        week = week_match.group(0).strip("()").strip()
                class_type = re.sub(r"\(tyg\.\s*[IVX]+\)\s*", "", class_type, flags=re.IGNORECASE).strip()
                results.append({
                    "day": day,
                    "start": start,
                    "end": end,
                    "week": week,
                    "class_type": class_type,
                    "subject": m.group("subject").strip(),
                    "lecturer": m.group("lecturer").strip(),
                    "room": m.group("room").strip(),
                    "group": m.group("group") if m.group("group") else None,
                })
        return results

    def parse_from_link(self):
        html = self.get_schedule()
        if not html:
            return []
        return self.parse(html)


class IcsBuilder:
    def __init__(self):
        self._week_map = {
            "tyg. i": 0,
            "tyg. ii": 1,
        }

    def _week_parity(self, d: date, semester_start: date) -> int:
        start_of_week = semester_start - timedelta(days=semester_start.weekday())
        return ((d - start_of_week).days // 7) % 2

    def _matches_week(self, week_value, parity: int) -> bool:
        if week_value is None:
            return True
        return self._week_map.get(str(week_value).lower()) == parity

    def _iter_dates(self, start: date, end: date):
        current = start
        while current <= end:
            yield current
            current += timedelta(days=1)

    def _normalize_week(self, week_value):
        if week_value is None:
            return None
        if isinstance(week_value, int):
            return week_value
        return self._week_map.get(str(week_value).lower())

    def build_google(self, events, semester_start: str, semester_end: str, free_days=None, day_overrides=None):
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
        for d in self._iter_dates(start_date, end_date):
            if d in free_set:
                continue
            override = overrides.get(d, {})
            parity = self._normalize_week(override.get("week"))
            if parity is None:
                parity = self._week_parity(d, start_date)
            target_day = override.get("day", d.weekday())

            for e in events:
                if e.get("day") != target_day:
                    continue
                if not self._matches_week(e.get("week"), parity):
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

    def build(self, events, semester_start: str, semester_end: str, free_days=None, day_overrides=None) -> str:
        occurrences = self.expand_occurrences(
            events=events,
            semester_start=semester_start,
            semester_end=semester_end,
            free_days=free_days,
            day_overrides=day_overrides,
        )

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
        return "\n".join(lines)

    def write_file(self, path: str, ics_content: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write(ics_content)


class GCalendarBuilder:
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

    def sync(self, calendar_id: str, occurrences, timezone="Europe/Warsaw", purge_managed=True):
        if purge_managed:
            print("Pobieranie starych wydarzeń planu...")
            managed = list(self._iter_managed_events(calendar_id))
            total = len(managed)
            if total == 0:
                print("Brak starych wydarzeń do usunięcia.")
            for i, ev in enumerate(managed, 1):
                self._execute(
                    lambda ev=ev: self.service.events().delete(
                        calendarId=calendar_id, eventId=ev["id"]
                    ).execute()
                )
                print(f"\rUsuwanie ({i}/{total}): {ev.get('summary')}", end="", flush=True)
                time.sleep(REQUEST_DELAY)
            if total:
                print(f"\nUsunięto: {total}")

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


if __name__ == "__main__":
    link = "https://degra.wi.pb.edu.pl/rozklady/rozklad.php?page=student&studia=INF2&semestr=2&spec=ITI&grw=1&grcw=1&grps=1&grp=1&grl=1&grj=1&grs=1&grwf=1"
    parser = ScheduleParser(link)
    classes = parser.parse_from_link()
    print(f"Sparsowano {len(classes)} zajęć.")
    print(json.dumps(classes, ensure_ascii=False, indent=2))

    # Generowanie pliku .ics:
    # ics_builder = IcsBuilder()
    # ics_content = ics_builder.build(
    #     classes,
    #     semester_start="2026-10-01",
    #     semester_end="2027-02-01",
    # )
    # ics_builder.write_file("schedule.ics", ics_content)

    # Generowanie wydarzeń google
    ics_builer = IcsBuilder()
    occurrences = ics_builer.build_google(
        events=classes,
        semester_start="2026-10-01",
        semester_end="2027-02-03",
        free_days=[
            "2026-10-31",
            "2026-11-1","2026-11-9","2026-11-10","2026-11-11",
            "2026-12-24","2026-12-25","2026-12-26","2026-12-27","2026-12-28","2026-12-29","2026-12-30","2026-12-31",
            "2027-01-01","2027-01-02","2027-01-03","2027-01-04","2027-01-05","2027-01-06","2027-01-07","2027-01-08"
        ],
        day_overrides={
            # czwartki do 19 listopada (włącznie) mają mieć tyg I a potem do końca tyg II
            "2026-10-01": {"week": "tyg. I"},
            "2026-10-08": {"week": "tyg. I"},
            "2026-10-15": {"week": "tyg. I"},
            "2026-10-22": {"week": "tyg. I"},
            "2026-10-29": {"week": "tyg. I"},
            "2026-11-05": {"week": "tyg. I"},
            "2026-11-12": {"week": "tyg. I"},
            "2026-11-19": {"week": "tyg. I"},
            "2026-11-26": {"week": "tyg. II"},
            "2026-12-03": {"week": "tyg. II"},
            "2026-12-10": {"week": "tyg. II"},
            "2026-12-17": {"week": "tyg. II"},
            "2026-12-24": {"week": "tyg. II"},
            "2026-12-31": {"week": "tyg. II"},
            "2027-01-07": {"week": "tyg. II"},
            "2027-01-14": {"week": "tyg. II"},
            "2027-01-21": {"week": "tyg. II"},
            "2027-01-28": {"week": "tyg. II"},
        }
    )
    print(f"Wygenerowano {len(occurrences)} terminów.")

    calendar_id = "fb71fba1febe4271f784c839e1c5b73d01e417d257c9036ae04c54d0d6565187@group.calendar.google.com"
    gcalendar_builder = GCalendarBuilder("credentials.json", "token.pickle", "PBTimetableExtractor")
    gcalendar_builder.sync(calendar_id=calendar_id, occurrences=occurrences)