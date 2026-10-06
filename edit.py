import json


def apply_subject_date_range(events, subject, class_type, start=None, end=None):
    """Ustawia date_range na zdarzeniach o podanym przedmiocie i typie zajęć."""
    changed = 0
    for event in events:
        if event.get("subject") != subject:
            continue
        if event.get("class_type") != class_type:
            continue
        event["date_range"] = {"start": start, "end": end}
        changed += 1
    return changed


class ScheduleEditor:
    def __init__(self, json_path):
        self.path = json_path
        self.data = {}

    def load(self):
        with open(self.path, "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self.data.setdefault("events", [])
        self.data.setdefault("free_days", [])
        self.data.setdefault("day_overrides", {})
        return self

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        return self

    def to_dict(self):
        return self.data

    def set_semester(self, start, end):
        self.data["semester_start"] = start
        self.data["semester_end"] = end
        return self

    def add_free_days(self, days):
        existing = set(self.data.get("free_days", []))
        existing.update(days)
        self.data["free_days"] = sorted(existing)
        return self

    def remove_free_days(self, days):
        existing = set(self.data.get("free_days", []))
        existing.difference_update(days)
        self.data["free_days"] = sorted(existing)
        return self

    def set_day_override(self, day, week=None, day_of_plan=None):
        values = {}
        if week is not None:
            values["week"] = week
        if day_of_plan is not None:
            values["day"] = day_of_plan
        if values:
            self.data.setdefault("day_overrides", {})[day] = values
        else:
            self.data.get("day_overrides", {}).pop(day, None)
        return self

    def remove_day_override(self, day):
        self.data.get("day_overrides", {}).pop(day, None)
        return self

    def add_event(self, event):
        self.data.setdefault("events", []).append(event)
        return self

    def remove_event(self, index):
        del self.data["events"][index]
        return self

    def list_subjects(self):
        subjects = []
        seen = set()
        for event in self.data.get("events", []):
            key = (event.get("subject"), event.get("class_type"))
            if key in seen:
                continue
            seen.add(key)
            subjects.append({"subject": key[0], "class_type": key[1]})
        return sorted(subjects, key=lambda item: (item["subject"], item["class_type"]))

    def set_subject_date_range(self, subject, class_type, start=None, end=None):
        apply_subject_date_range(self.data.get("events", []), subject, class_type, start, end)
        return self

    def remove_subject_date_range(self, subject, class_type):
        for event in self.data.get("events", []):
            if event.get("subject") == subject and event.get("class_type") == class_type:
                event.pop("date_range", None)
        return self
