import requests
import re
import json
import os
import pickle
from datetime import datetime, date, timedelta
import uuid
from collections import defaultdict
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

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
            response = requests.get(self.link)
            if response.status_code == 200:
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
        return ((d - semester_start).days // 7) % 2

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

    def expand_occurrences(self, events, semester_start: str, semester_end: str, free_days=None, day_overrides=None):
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
        creds = None
        if self.token_path and os.path.exists(self.token_path):
            with open(self.token_path, "rb") as token_file:
                creds = pickle.load(token_file)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, self.SCOPES)
                creds = flow.run_local_server(port=0)

            with open(self.token_path, "wb") as token_file:
                pickle.dump(creds, token_file)

        return build("calendar", "v3", credentials=creds)

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
            resp = self.service.events().list(
                calendarId=calendar_id,
                maxResults=2500,
                singleEvents=False,
                pageToken=page_token,
                privateExtendedProperty="pbte=1",
            ).execute()
            for item in resp.get("items", []):
                yield item
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    def sync(self, calendar_id: str, occurrences, timezone="Europe/Warsaw", purge_managed=True):
        if purge_managed:
            for ev in self._iter_managed_events(calendar_id):
                self.service.events().delete(calendarId=calendar_id, eventId=ev["id"]).execute()

        grouped = self._group_for_series(occurrences)

        for (summary, location, description, start_time, end_time), items in grouped.items():
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

            self.service.events().insert(calendarId=calendar_id, body=body).execute()


if __name__ == "__main__":
    link = "https://degra.wi.pb.edu.pl/rozklady/rozklad.php?page=student&studia=INF2&semestr=1&spec=X&grw=1&grcw=2&grps=4&grp=1&grl=4&grj=1&grs=1&grwf=1"
    parser = ScheduleParser(link)
    classes = parser.parse_from_link()
    print(json.dumps(classes, ensure_ascii=False, indent=2))

    # Generowanie pliku .ics:

    ics_builder = IcsBuilder()
    ics_content = ics_builder.build(
        classes,
        semester_start="2026-02-23",
        semester_end="2026-06-19",
        free_days=["2026-04-03", "2026-04-04", "2026-04-05", "2026-04-06", "2026-04-07", "2026-04-10", "2026-04-11",
                   "2026-04-12", "2026-04-13", "2026-04-14", "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-24",
                   "2026-06-04", "2026-04-05"],
        day_overrides={
            "2026-04-08": {"day": 4, "week": "tyg. II"},
            "2026-05-08": {"day": 4, "week": "tyg. II"},
            "2026-05-22": {"day": 4, "week": "tyg. II"},
            "2026-06-03": {"day": 4, "week": "tyg. II"},
            "2026-04-30": {"day": 4, "week": "tyg. I"},
            "2026-05-15": {"day": 4, "week": "tyg. I"},
            "2026-05-29": {"day": 4, "week": "tyg. I"},
            "2026-06-12": {"day": 4, "week": "tyg. I"}
        },
    )
    ics_builder.write_file("schedule.ics", ics_content)

    # Upload do Google Calendar (odkomentuj po konfiguracji OAuth):
    occurrences = ics_builder.expand_occurrences(
        classes,
        semester_start="2026-02-23",
        semester_end="2026-06-19",
        free_days=["2026-04-03", "2026-04-04", "2026-04-05", "2026-04-06", "2026-04-07", "2026-04-10", "2026-04-11",
                   "2026-04-12", "2026-04-13", "2026-04-14", "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-24",
                   "2026-06-04", "2026-04-05"],
        day_overrides={
            "2026-04-08": {"day": 4, "week": "tyg. II"},
            "2026-05-08": {"day": 4, "week": "tyg. II"},
            "2026-05-22": {"day": 4, "week": "tyg. II"},
            "2026-06-03": {"day": 4, "week": "tyg. II"},
            "2026-04-30": {"day": 4, "week": "tyg. I"},
            "2026-05-15": {"day": 4, "week": "tyg. I"},
            "2026-05-29": {"day": 4, "week": "tyg. I"},
            "2026-06-12": {"day": 4, "week": "tyg. I"}
        },
    )
    gcal = GCalendarBuilder(credentials_path="credentials.json", token_path="token.pickle")
    gcal.sync(calendar_id="8d2531d4acdb3ec2b84565f33372d00b60085e617ca3d31843f4a101b214d27e@group.calendar.google.com", occurrences=occurrences, timezone="Europe/Warsaw")
