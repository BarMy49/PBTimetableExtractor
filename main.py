import requests
import re
import json

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
        self.link = link

    def get_schedule(self):
        if link is not None:
            response = requests.get(self.link)
            if response.status_code == 200:
                return response.text
            print(f"Failed to retrieve schedule. Status code: {response.status_code}")
        return None

    def parse(self, html):
        results = []
        for m in self._pattern.finditer(html):
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


if __name__ == "__main__":
    parser = ScheduleParser(link)
    schedule = parser.get_schedule()
    if schedule:
        classes = parser.parse(schedule)
        print(json.dumps(classes, ensure_ascii=False, indent=2))
