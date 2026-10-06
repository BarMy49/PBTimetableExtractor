from fetch import ScheduleDownloader
from edit import ScheduleEditor
from export import GoogleCalendarExporter
from view import TimetableViewer

JSON_PATH = "schedule.json"
LINK = "https://degra.wi.pb.edu.pl/rozklady/rozklad.php?page=student&studia=INF2&semestr=2&spec=ITI&grw=1&grcw=1&grps=1&grp=1&grl=1&grj=1&grs=1&grwf=1"
CALENDAR_ID = "fb71fba1febe4271f784c839e1c5b73d01e417d257c9036ae04c54d0d6565187@group.calendar.google.com"


def main():
    downloader = ScheduleDownloader(LINK)
    downloader.download_to_json(JSON_PATH)

    editor = ScheduleEditor(JSON_PATH)
    editor.load()
    editor.set_semester("2026-10-01", "2027-02-03")
    editor.add_free_days([
        "2026-10-31",
        "2026-11-1", "2026-11-9", "2026-11-10", "2026-11-11",
        "2026-12-24", "2026-12-25", "2026-12-26", "2026-12-27", "2026-12-28", "2026-12-29", "2026-12-30", "2026-12-31",
        "2027-01-01", "2027-01-02", "2027-01-03", "2027-01-04", "2027-01-05", "2027-01-06", "2027-01-07", "2027-01-08",
    ])
    # czwartki do 19 listopada (włącznie) mają mieć tyg I a potem do końca tyg II
    # day_overrides = {
    #     "2026-10-01": {"week": "tyg. I"},
    #     "2026-10-08": {"week": "tyg. I"},
    #     "2026-10-15": {"week": "tyg. I"},
    #     "2026-10-22": {"week": "tyg. I"},
    #     "2026-10-29": {"week": "tyg. I"},
    #     "2026-11-05": {"week": "tyg. I"},
    #     "2026-11-12": {"week": "tyg. I"},
    #     "2026-11-19": {"week": "tyg. I"},
    #     "2026-11-26": {"week": "tyg. II"},
    #     "2026-12-03": {"week": "tyg. II"},
    #     "2026-12-10": {"week": "tyg. II"},
    #     "2026-12-17": {"week": "tyg. II"},
    #     "2026-12-24": {"week": "tyg. II"},
    #     "2026-12-31": {"week": "tyg. II"},
    #     "2027-01-07": {"week": "tyg. II"},
    #     "2027-01-14": {"week": "tyg. II"},
    #     "2027-01-21": {"week": "tyg. II"},
    #     "2027-01-28": {"week": "tyg. II"},
    # }
    # for day, override in day_overrides.items():
    #     editor.set_day_override(day, week=override.get("week"), day_of_plan=override.get("day"))

    # Przedmiot trwający tylko część semestru — zakres dat zamiast tyg. I/II:
    editor.set_subject_date_range("Zaawansowane systemy sztucznej inteligencji", "wykład", "2026-10-01", "2026-11-19")
    editor.set_subject_date_range("Zaawansowany internet rzeczy", "wykład", "2026-10-01", "2026-11-19")
    editor.set_subject_date_range("Proseminarium", "seminarium", "2026-11-26", "2027-02-03")
    editor.set_subject_date_range("Zaawansowany internet rzeczy", "projekt", "2026-11-17", "2027-02-03")

    editor.save()

    # Wizualizacja planu: siatka na konsolę + zapis do PDF
    viewer = TimetableViewer(editor.to_dict())
    print(viewer.render())
    viewer.save_pdf("schedule.pdf")

    # Google Calendar (po OAuth2)
    exporter = GoogleCalendarExporter("credentials.json", "token.pickle", "PBTimetableExtractor")
    exporter.sync(calendar_id=CALENDAR_ID, data=editor.to_dict())

    # Alternatywnie eksport do pliku .ics:
    # from export import IcsExporter
    # IcsExporter().export(editor.to_dict(), "schedule.ics")


if __name__ == "__main__":
    main()
