import json
import re

import requests

import console


class ScheduleDownloader:
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
            console.info(f"Pobieranie planu z: {self.link}")
            response = requests.get(self.link)
            if response.status_code == 200:
                console.success("Plan pobrany.")
                return response.text
            console.error(f"Failed to retrieve schedule. Status code: {response.status_code}")
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

    def fetch(self):
        html = self.get_schedule()
        if not html:
            return []
        return self.parse(html)

    def download_to_json(self, path):
        events = self.fetch()
        data = {
            "source": self.link,
            "events": events,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        console.success(f"Sparsowano {len(events)} zajęć i zapisano do: {path}")
        return events
