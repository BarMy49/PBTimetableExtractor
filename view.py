import os
from datetime import datetime

WEEKDAY_NAMES = ("Pon", "Wt", "Śr", "Czw", "Pt")
WEEKDAY_LONG = ("Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek")
WEEK_NAMES = ("Tydzień I", "Tydzień II")

_WEEK_PARITY = {"tyg. i": 0, "tyg. ii": 1}

FONT_REGULAR_CANDIDATES = (
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
)
FONT_BOLD_CANDIDATES = (
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\calibrib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
)

TIME_W = 13
DAY_W = 22


class TimetableViewer:
    def __init__(self, data):
        self.data = data

    def _week_matches(self, event, parity):
        if event.get("date_range"):
            return True
        week = event.get("week")
        if not week:
            return True
        return _WEEK_PARITY.get(str(week).lower()) == parity

    @staticmethod
    def _range_label(date_range):
        start = date_range.get("start") or "…"
        end = date_range.get("end") or "…"
        return f"[zakres: {start} – {end}]"

    def _cell_lines(self, event):
        lines = [f'{event.get("subject", "")} ({event.get("class_type", "")})'.strip()]
        details = f'sala {event.get("room", "")}'
        if event.get("lecturer"):
            details += f", {event["lecturer"]}"
        if event.get("group"):
            details += f", gr. {event["group"]}"
        lines.append(details)
        if event.get("date_range"):
            lines.append(self._range_label(event["date_range"]))
        return lines

    def _build_week(self, parity):
        events = self.data.get("events", [])
        slots = sorted(
            {(e.get("start"), e.get("end")) for e in events if e.get("start")},
            key=lambda slot: (datetime.strptime(slot[0], "%H:%M"), datetime.strptime(slot[1], "%H:%M")),
        )
        grid = {slot: {day: [] for day in range(5)} for slot in slots}
        for event in events:
            if not self._week_matches(event, parity):
                continue
            day = event.get("day")
            slot = (event.get("start"), event.get("end"))
            if day is None or slot not in grid:
                continue
            cell = grid[slot][day]
            if cell:
                cell.append("")
            cell.extend(self._cell_lines(event))
        return slots, grid

    @staticmethod
    def _pad(text, width):
        text = text[:width]
        return text + " " * (width - len(text))

    def _render_grid(self, parity):
        slots, grid = self._build_week(parity)
        width = TIME_W + DAY_W * 5
        separator = "-" * width
        lines = [
            self._pad("", TIME_W) + "".join(self._pad(day, DAY_W) for day in WEEKDAY_NAMES),
            separator,
        ]
        for slot in slots:
            time_label = f"{slot[0]}–{slot[1]}"
            cells = [grid[slot][day] or [""] for day in range(5)]
            height = max(len(cell) for cell in cells)
            for i in range(height):
                line = self._pad(time_label if i == 0 else "", TIME_W)
                for day in range(5):
                    text = cells[day][i] if i < len(cells[day]) else ""
                    line += self._pad(text, DAY_W)
                lines.append(line.rstrip())
            lines.append(separator)
        return "\n".join(lines)

    def _collect_subject_ranges(self):
        ranges = {}
        for event in self.data.get("events", []):
            date_range = event.get("date_range")
            if not date_range:
                continue
            key = (event.get("subject"), event.get("class_type"))
            ranges[key] = (date_range.get("start"), date_range.get("end"))
        return [(subject, class_type, start, end) for (subject, class_type), (start, end) in sorted(ranges.items())]

    def _modification_lines(self):
        lines = []
        free_days = sorted(self.data.get("free_days") or [])
        if free_days:
            lines.append(f"Dni wolne ({len(free_days)}):")
            lines.append("  " + ", ".join(free_days))
        else:
            lines.append("Dni wolne: brak")

        overrides = self.data.get("day_overrides") or {}
        if overrides:
            lines.append(f"Nadpisania dni ({len(overrides)}):")
            for day, override in sorted(overrides.items()):
                parts = []
                if override.get("week") is not None:
                    parts.append(f'tydzień: {override["week"]}')
                if override.get("day") is not None:
                    parts.append(f'dzień planu: {WEEKDAY_LONG[override["day"]]}')
                lines.append(f"  {day} -> {', '.join(parts)}")
        else:
            lines.append("Nadpisania dni: brak")

        ranges = self._collect_subject_ranges()
        if ranges:
            lines.append(f"Zakresy przedmiotów ({len(ranges)}):")
            for subject, class_type, start, end in ranges:
                lines.append(f"  {subject} ({class_type}): {start or '…'} – {end or '…'}")
        else:
            lines.append("Zakresy przedmiotów: brak")
        return lines

    def render(self):
        parts = ["PLAN ZAJĘĆ"]
        for parity, week_name in enumerate(WEEK_NAMES):
            parts.append("")
            parts.append(week_name.upper())
            parts.append(self._render_grid(parity))
        parts.append("")
        parts.append("MODYFIKACJE")
        parts.extend(self._modification_lines())
        return "\n".join(parts)

    @staticmethod
    def _find_font(candidates):
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
        return None

    def save_pdf(self, path):
        try:
            from fpdf import FPDF
            from fpdf import FontFace
        except ImportError:
            raise ImportError("Brak biblioteki fpdf2. Zainstaluj: pip install fpdf2")

        pdf = FPDF(orientation="L", unit="mm", format="A4")
        regular = self._find_font(FONT_REGULAR_CANDIDATES)
        bold = self._find_font(FONT_BOLD_CANDIDATES) or regular
        if regular:
            pdf.add_font("Arial", "", regular)
            pdf.add_font("Arial", "B", bold)
            font_family = "Arial"
        else:
            print("Ostrzeżenie: nie znaleziono czcionki TTF — polskie znaki mogą nie wyświetlać się poprawnie.")
            font_family = "helvetica"

        pdf.set_auto_page_break(auto=True, margin=12)
        pdf.add_page()
        pdf.set_font(font_family, "B", 16)
        pdf.cell(0, 10, "Plan zajęć", new_x="LMARGIN", new_y="NEXT", align="C")

        for parity, week_name in enumerate(WEEK_NAMES):
            if parity > 0:
                pdf.add_page()
            pdf.set_font(font_family, "B", 13)
            pdf.cell(0, 8, week_name, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
            self._draw_pdf_grid(pdf, font_family, parity)

        pdf.add_page()
        pdf.set_font(font_family, "B", 13)
        pdf.cell(0, 8, "Modyfikacje", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font(font_family, "", 9)
        for line in self._modification_lines():
            pdf.multi_cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")

        pdf.output(path)
        print(f"Zapisano plik PDF: {path}")

    def _draw_pdf_grid(self, pdf, font_family, parity):
        from fpdf import FontFace

        slots, grid = self._build_week(parity)
        pdf.set_font(font_family, "", 9)
        if not slots:
            pdf.cell(0, 6, "(brak zajęć)", new_x="LMARGIN", new_y="NEXT")
            return

        col_widths = [24] + [47] * 5
        base_size = 9.0
        base_line_height = 4.6
        cell_width = col_widths[1] - 2

        row_lines = []
        for slot in slots:
            max_lines = 1
            for day in range(5):
                text = "\n".join(grid[slot][day]) if grid[slot][day] else ""
                if not text:
                    continue
                pdf.set_font(font_family, "", base_size)
                lines = pdf.multi_cell(cell_width, base_line_height, text, dry_run=True, output="LINES")
                max_lines = max(max_lines, len(lines))
            row_lines.append(max_lines)

        available = pdf.h - pdf.t_margin - pdf.b_margin - 22
        total = (1 + sum(row_lines)) * base_line_height + 2
        scale = min(1.0, available / total)
        size = max(5.0, base_size * scale)
        line_height = base_line_height * scale

        header_style = FontFace(family=font_family, emphasis="BOLD", size_pt=size, fill_color=(226, 239, 235))
        pdf.set_font(font_family, "", size)
        with pdf.table(col_widths=col_widths, borders_layout="ALL", line_height=line_height, repeat_headings=1) as table:
            header = table.row()
            header.cell("Godzina", style=header_style)
            for day_name in WEEKDAY_NAMES:
                header.cell(day_name, style=header_style)
            for slot in slots:
                row = table.row()
                row.cell(f"{slot[0]}–{slot[1]}")
                for day in range(5):
                    row.cell("\n".join(grid[slot][day]) if grid[slot][day] else "")
        pdf.ln(4)
