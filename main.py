import requests
import re
import json
from datetime import datetime, date, timedelta
import uuid

link = "https://degra.wi.pb.edu.pl/rozklady/rozklad.php?page=student&studia=INF2&semestr=1&spec=X&grw=1&grcw=2&grps=4&grp=1&grl=4&grj=1&grs=1&grwf=1"


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

    def build(self, events, semester_start: str, semester_end: str, free_days=None) -> str:
        start_date = datetime.strptime(semester_start, "%Y-%m-%d").date()
        end_date = datetime.strptime(semester_end, "%Y-%m-%d").date()
        free_set = {
            datetime.strptime(d, "%Y-%m-%d").date()
            for d in (free_days or [])
        }
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//PBTimetableExtractor//PL",
            "CALSCALE:GREGORIAN",
        ]

        for d in self._iter_dates(start_date, end_date):
            if d in free_set:
                continue
            parity = self._week_parity(d, start_date)
            for e in events:
                if e.get("day") != d.weekday():
                    continue
                if not self._matches_week(e.get("week"), parity):
                    continue
                start_dt = datetime.combine(d, datetime.strptime(e["start"], "%H:%M").time())
                end_dt = datetime.combine(d, datetime.strptime(e["end"], "%H:%M").time())
                summary = f'{e["subject"]} ({e["class_type"]})'.strip()
                description = f'Prowadzący: {e["lecturer"]}'
                if e.get("group"):
                    description += f', grupa {e["group"]}'
                lines.extend([
                    "BEGIN:VEVENT",
                    f"UID:{uuid.uuid4()}",
                    f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}",
                    f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}",
                    f"SUMMARY:{summary}",
                    f"LOCATION:{e['room']}",
                    f"DESCRIPTION:{description}",
                    "END:VEVENT",
                ])

        lines.append("END:VCALENDAR")
        return "\n".join(lines)

    def write_file(self, path: str, ics_content: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write(ics_content)


if __name__ == "__main__":
    parser = ScheduleParser(link)
    classes = parser.parse_from_link()
    print(json.dumps(classes, ensure_ascii=False, indent=2))

    ics_builder = IcsBuilder()
    ics_content = ics_builder.build(
        classes,
        semester_start="2026-02-23",
        semester_end="2026-06-19",
        free_days=["2026-04-03", "2026-04-04", "2026-04-05", "2026-04-06", "2026-04-07", "2026-04-10", "2026-04-11",
                   "2026-04-12", "2026-04-13", "2026-04-14", "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-24",
                   "2026-06-04", "2026-04-05"],
    )
    ics_builder.write_file("schedule.ics", ics_content)
