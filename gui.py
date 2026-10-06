import calendar
import contextlib
import io
import math
import os
import queue
import re
import threading
import traceback
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import fetch
import edit
import export
import view


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_LINK = (
    "https://degra.wi.pb.edu.pl/rozklady/rozklad.php?page=student&studia=INF2&"
    "semestr=2&spec=ITI&grw=1&grcw=1&grps=1&grp=1&grl=1&grj=1&grs=1&grwf=1"
)
DEFAULT_CALENDAR_ID = (
    "fb71fba1febe4271f784c839e1c5b73d01e417d257c9036ae04c54d0d6565187"
    "@group.calendar.google.com"
)

MONTHS = (
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
    "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
)
WEEKDAYS = ("Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Niedz")
POLISH_WEEKDAYS = (
    "Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela",
)
WEEK_OPTIONS = {
    "Automatycznie": None,
    "Tydzień I": "tyg. I",
    "Tydzień II": "tyg. II",
}
DAY_OPTIONS = {
    "Jak w kalendarzu": None,
    "Poniedziałek": 0,
    "Wtorek": 1,
    "Środa": 2,
    "Czwartek": 3,
    "Piątek": 4,
}
COLORS = {
    "background": "#f2f5f4",
    "panel": "#ffffff",
    "text": "#23333a",
    "muted": "#718087",
    "accent": "#16796f",
    "accent_hover": "#12665e",
    "semester": "#e7f2eb",
    "free": "#fff0ed",
    "override": "#f0ecf8",
    "selected": "#d8eeea",
    "today": "#d67b48",
    "border": "#dce4e1",
    "input": "#fbfcfc",
    "hover": "#edf3f1",
    "danger": "#b84e4c",
    "danger_hover": "#9c3e3c",
    "subtle": "#f2f5f4",
}
DARK_COLORS = {
    "background": "#151c20",
    "panel": "#202a2f",
    "text": "#e8eef0",
    "muted": "#a0afb5",
    "accent": "#54c5b2",
    "accent_hover": "#3daf9e",
    "semester": "#2b3c34",
    "free": "#452f32",
    "override": "#373149",
    "selected": "#254a46",
    "today": "#e7a16c",
    "border": "#35444a",
    "input": "#192226",
    "hover": "#2a373c",
    "danger": "#b95255",
    "danger_hover": "#9d4246",
    "subtle": "#29363b",
}


def _squircle_coords(x1, y1, x2, y2, radius=12, steps=8):
    radius = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    corners = (
        (x2 - radius, y1 + radius, -90, 0),
        (x2 - radius, y2 - radius, 0, 90),
        (x1 + radius, y2 - radius, 90, 180),
        (x1 + radius, y1 + radius, 180, 270),
    )
    points = []
    for cx, cy, start, end in corners:
        for index in range(steps + 1):
            angle = math.radians(start + (end - start) * index / steps)
            cosine, sine = math.cos(angle), math.sin(angle)
            x = cx + radius * math.copysign(abs(cosine) ** 0.5, cosine)
            y = cy + radius * math.copysign(abs(sine) ** 0.5, sine)
            points.extend((x, y))
    return points


class RoundedPanel(tk.Canvas):
    def __init__(self, master, colors, padding=10, **kwargs):
        super().__init__(master, bg=colors["background"], highlightthickness=0, bd=0, **kwargs)
        self.colors = colors
        self.padding = padding
        self.content = ttk.Frame(self, style="Panel.TFrame")
        self._window = self.create_window((padding, padding), window=self.content, anchor="nw")
        self.bind("<Configure>", self._resize)

    def _resize(self, event):
        self._draw_panel(event.width, event.height)
        self.itemconfigure(
            self._window,
            width=max(1, event.width - 2 * self.padding),
            height=max(1, event.height - 2 * self.padding),
        )

    def _draw_panel(self, width, height):
        self.delete("panel-shape")
        self.create_polygon(
            _squircle_coords(1, 1, max(2, width - 1), max(2, height - 1), 18),
            fill=self.colors["panel"],
            outline="",
            tags="panel-shape",
        )
        self.tag_lower("panel-shape")

    def set_colors(self, colors):
        self.colors = colors
        self.configure(bg=colors["background"])
        self._draw_panel(self.winfo_width(), self.winfo_height())


class SquircleButton(tk.Canvas):
    def __init__(self, master, text, command, kind, colors, width=180, height=38):
        super().__init__(master, width=width, height=height, bg=colors["panel"], highlightthickness=0, bd=0, cursor="hand2")
        self.text = text
        self.command = command
        self.kind = kind
        self.colors = colors
        self.enabled = True
        self.hovered = False
        self.bind("<Configure>", self._draw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._activate)
        self.bind("<Return>", self._activate)
        self.bind("<space>", self._activate)
        self._draw()

    def _button_colors(self):
        if not self.enabled:
            return self.colors["border"], self.colors["muted"]
        if self.kind == "primary":
            return self.colors["accent_hover" if self.hovered else "accent"], "#ffffff"
        if self.kind == "danger":
            return self.colors["danger_hover" if self.hovered else "danger"], "#ffffff"
        return self.colors["hover" if self.hovered else "subtle"], self.colors["text"]

    def _draw(self, _event=None):
        self.delete("all")
        fill, text_color = self._button_colors()
        width, height = max(2, self.winfo_width()), max(2, self.winfo_height())
        self.create_polygon(_squircle_coords(1, 1, width - 1, height - 1, int(min(12, height // 2))), fill=fill, outline="")
        self.create_text(width / 2, height / 2, text=self.text, fill=text_color, font=("Segoe UI Semibold", 9), justify="center")

    def _on_enter(self, _event=None):
        self.hovered = True
        self._draw()

    def _on_leave(self, _event=None):
        self.hovered = False
        self._draw()

    def _activate(self, _event=None):
        if self.enabled:
            self.command()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def set_colors(self, colors):
        self.colors = colors
        self.configure(bg=colors["panel"])
        self._draw()


class CalendarCell(tk.Canvas):
    def __init__(self, master, label, fill, foreground, outline, selected, today, colors, command):
        super().__init__(master, bg=colors["panel"], highlightthickness=0, bd=0, cursor="hand2", takefocus=True)
        self.label = label
        self.fill = fill
        self.foreground = foreground
        self.outline = outline
        self.selected = selected
        self.today = today
        self.colors = colors
        self.command = command
        self.hovered = False
        self.bind("<Configure>", self._draw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._activate)
        self.bind("<Return>", self._activate)
        self.bind("<space>", self._activate)

    def _draw(self, _event=None):
        self.delete("all")
        width, height = max(2, self.winfo_width()), max(2, self.winfo_height())
        fill = self.colors["hover"] if self.hovered else self.fill
        self.create_polygon(_squircle_coords(2, 2, width - 2, height - 2, 13), fill=fill, outline="")
        if self.selected or self.today:
            self.create_polygon(
                _squircle_coords(2, 2, width - 2, height - 2, 13),
                fill="",
                outline=self.outline,
                width=1.5 if self.selected else 1,
            )
        font = ("Segoe UI Semibold" if self.selected else "Segoe UI", 10)
        self.create_text(width / 2, height / 2, text=self.label, fill=self.foreground, font=font, justify="center")

    def _on_enter(self, _event=None):
        self.hovered = True
        self._draw()

    def _on_leave(self, _event=None):
        self.hovered = False
        self._draw()

    def _activate(self, _event=None):
        self.command()


class QueueWriter(io.TextIOBase):
    def __init__(self, output_queue):
        self.output_queue = output_queue

    def write(self, text):
        if text:
            self.output_queue.put(("log", text))
        return len(text)

    def flush(self):
        pass


class TimetableGui:
    def __init__(self, root):
        self.root = root
        self.root.title("PB Timetable Extractor")
        self.root.geometry("1060x700")
        self.root.minsize(900, 600)
        self.root.resizable(True, True)
        self.colors = COLORS
        self.dark_mode = False
        self.root.configure(bg=self.colors["background"])

        self.today = date.today()
        self.visible_year = self.today.year
        self.visible_month = self.today.month
        self.selected_date = self.today
        self.free_days = set()
        self.day_overrides = {}
        self.subject_ranges = {}
        self.subject_options = {}
        self.job_queue = queue.Queue()
        self.job_running = False
        self.fullscreen = False

        self.link_var = tk.StringVar(value=DEFAULT_LINK)
        self.calendar_id_var = tk.StringVar(value=DEFAULT_CALENDAR_ID)
        self.semester_start_var = tk.StringVar(value="2026-10-01")
        self.semester_end_var = tk.StringVar(value="2027-02-03")
        self.date_mode_var = tk.StringVar(value="select")
        self.week_var = tk.StringVar(value="Automatycznie")
        self.day_var = tk.StringVar(value="Jak w kalendarzu")
        self.free_day_var = tk.BooleanVar(value=False)
        self.subjects_var = tk.StringVar(value="")
        self.range_start_var = tk.StringVar(value="")
        self.range_end_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Gotowy")
        self.dark_mode_var = tk.BooleanVar(value=False)

        self._configure_styles()
        self._build_layout()
        self.semester_start_var.trace_add("write", self._on_semester_date_change)
        self.semester_end_var.trace_add("write", self._on_semester_date_change)
        self._draw_calendar()
        self._update_selected_date_panel()
        self.root.bind("<Escape>", self._toggle_fullscreen)
        self.root.bind("<F11>", self._toggle_fullscreen)
        self.root.after(100, self._poll_job_queue)

    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        colors = self.colors
        style.configure("TFrame", background=colors["background"])
        style.configure("Panel.TFrame", background=colors["panel"])
        style.configure("TLabel", background=colors["background"], foreground=colors["text"], font=("Segoe UI", 10))
        style.configure("Panel.TLabel", background=colors["panel"], foreground=colors["text"], font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 18), foreground=colors["text"])
        style.configure("Section.TLabel", background=colors["panel"], font=("Segoe UI Semibold", 10), foreground=colors["text"])
        style.configure("Muted.TLabel", background=colors["panel"], foreground=colors["muted"], font=("Segoe UI", 9))
        style.configure("HeaderMuted.TLabel", background=colors["background"], foreground=colors["muted"], font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 9), padding=(8, 6), borderwidth=0)
        style.configure("Primary.TButton", background=colors["accent"], foreground="#ffffff", font=("Segoe UI Semibold", 9), padding=(10, 8))
        style.map("Primary.TButton", background=[("active", colors["accent_hover"]), ("disabled", colors["border"])])
        style.configure("Danger.TButton", background=colors["danger"], foreground="#ffffff", padding=(9, 7))
        style.map("Danger.TButton", background=[("active", colors["danger_hover"]), ("disabled", colors["border"])])
        style.configure("TEntry", padding=(7, 5), fieldbackground=colors["input"], foreground=colors["text"])
        style.configure("TCombobox", padding=(6, 4), fieldbackground=colors["input"], foreground=colors["text"])
        style.configure("TRadiobutton", background=colors["panel"], foreground=colors["text"], font=("Segoe UI", 9))
        style.configure("TCheckbutton", background=colors["background"], foreground=colors["text"], font=("Segoe UI", 9))
        style.configure("Panel.TCheckbutton", background=colors["panel"], foreground=colors["text"], font=("Segoe UI", 9))
        style.configure("TScrollbar", background=colors["subtle"], troughcolor=colors["panel"], arrowcolor=colors["muted"], bordercolor=colors["panel"], relief="flat")

    def _build_layout(self):
        outer = ttk.Frame(self.root, padding=(16, 12, 16, 10))
        outer.pack(fill="both", expand=True)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Plan zajęć", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.status_var, style="HeaderMuted.TLabel").grid(row=0, column=1, sticky="e", padx=(10, 14))
        ttk.Checkbutton(
            header,
            text="Ciemny motyw",
            variable=self.dark_mode_var,
            command=self._toggle_theme,
            style="TCheckbutton",
        ).grid(row=0, column=2, sticky="e")

        content = ttk.Frame(outer)
        content.grid(row=1, column=0, sticky="nsew")
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=0)

        self.calendar_card = RoundedPanel(content, self.colors, padding=12)
        self.calendar_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        calendar_panel = self.calendar_card.content
        calendar_panel.rowconfigure(1, weight=1)
        calendar_panel.columnconfigure(0, weight=1)

        month_header = ttk.Frame(calendar_panel, style="Panel.TFrame")
        month_header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        month_header.columnconfigure(1, weight=1)
        self.previous_button = SquircleButton(month_header, "‹", lambda: self._move_month(-1), "neutral", self.colors, width=38, height=32)
        self.previous_button.grid(row=0, column=0, sticky="w")
        self.month_label = ttk.Label(month_header, text="", style="Section.TLabel", anchor="center")
        self.month_label.grid(row=0, column=1, sticky="ew", padx=8)
        self.next_button = SquircleButton(month_header, "›", lambda: self._move_month(1), "neutral", self.colors, width=38, height=32)
        self.next_button.grid(row=0, column=2, sticky="e")

        self.calendar_grid = ttk.Frame(calendar_panel, style="Panel.TFrame")
        self.calendar_grid.grid(row=1, column=0, sticky="nsew")
        for col in range(7):
            self.calendar_grid.columnconfigure(col, weight=1, uniform="weekday")
        self.calendar_grid.rowconfigure(0, weight=0, minsize=24)
        for row in range(1, 7):
            self.calendar_grid.rowconfigure(row, weight=1, uniform="week")

        legend = ttk.Frame(calendar_panel, style="Panel.TFrame")
        legend.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.legend_swatches = []
        for text, color_key in (("Semestr", "semester"), ("Dzień wolny", "free"), ("Nadpisanie", "override")):
            item = ttk.Frame(legend, style="Panel.TFrame")
            item.pack(side="left", padx=(0, 16))
            swatch = tk.Label(item, bg=self.colors[color_key], width=2, height=1, relief="flat", bd=0)
            swatch.pack(side="left", padx=(0, 6))
            self.legend_swatches.append((swatch, color_key))
            ttk.Label(item, text=text, style="Muted.TLabel").pack(side="left")

        self.sidebar_card = RoundedPanel(content, self.colors, padding=10, width=342)
        self.sidebar_card.grid(row=0, column=1, sticky="nsew")
        self.sidebar_card.content.rowconfigure(0, weight=1)
        self.sidebar_card.content.columnconfigure(0, weight=1)
        self.sidebar_canvas = tk.Canvas(self.sidebar_card.content, bg=self.colors["panel"], highlightthickness=0, bd=0)
        self.sidebar_canvas.grid(row=0, column=0, sticky="nsew")
        self.sidebar_scrollbar = ttk.Scrollbar(self.sidebar_card.content, orient="vertical", command=self.sidebar_canvas.yview)
        self.sidebar_scrollbar.grid(row=0, column=1, sticky="ns", padx=(3, 0))
        self.sidebar_canvas.configure(yscrollcommand=self.sidebar_scrollbar.set)
        side = ttk.Frame(self.sidebar_canvas, style="Panel.TFrame", padding=(2, 2, 5, 6))
        self.sidebar_window = self.sidebar_canvas.create_window((0, 0), window=side, anchor="nw")
        side.bind("<Configure>", self._update_sidebar_scrollregion)
        self.sidebar_canvas.bind("<Configure>", self._resize_sidebar_content)
        self.side_panel = side
        side.columnconfigure(0, weight=1)

        ttk.Label(side, text="Źródło i kalendarz", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Label(side, text="Link do planu", style="Panel.TLabel").grid(row=1, column=0, sticky="w")
        self.link_entry = ttk.Entry(side, textvariable=self.link_var)
        self.link_entry.grid(row=2, column=0, sticky="ew", pady=(4, 9))
        ttk.Label(side, text="calendar_id", style="Panel.TLabel").grid(row=3, column=0, sticky="w")
        ttk.Entry(side, textvariable=self.calendar_id_var).grid(row=4, column=0, sticky="ew", pady=(4, 13))

        ttk.Separator(side).grid(row=5, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(side, text="Semestr", style="Section.TLabel").grid(row=6, column=0, sticky="w", pady=(0, 7))
        ttk.Label(side, text="Początek (RRRR-MM-DD)", style="Panel.TLabel").grid(row=7, column=0, sticky="w")
        ttk.Entry(side, textvariable=self.semester_start_var).grid(row=8, column=0, sticky="ew", pady=(4, 7))
        ttk.Radiobutton(side, text="Wybierz początek w kalendarzu", variable=self.date_mode_var, value="start", command=self._draw_calendar).grid(row=9, column=0, sticky="w")
        ttk.Label(side, text="Koniec (RRRR-MM-DD)", style="Panel.TLabel").grid(row=10, column=0, sticky="w", pady=(7, 0))
        ttk.Entry(side, textvariable=self.semester_end_var).grid(row=11, column=0, sticky="ew", pady=(4, 7))
        ttk.Radiobutton(side, text="Wybierz koniec w kalendarzu", variable=self.date_mode_var, value="end", command=self._draw_calendar).grid(row=12, column=0, sticky="w")

        ttk.Separator(side).grid(row=13, column=0, sticky="ew", pady=12)
        self.selected_label = ttk.Label(side, text="", style="Section.TLabel")
        self.selected_label.grid(row=14, column=0, sticky="w", pady=(0, 7))
        ttk.Radiobutton(side, text="Wybieraj dni i wyjątki", variable=self.date_mode_var, value="select", command=self._draw_calendar).grid(row=15, column=0, sticky="w", pady=(0, 5))
        self.free_day_check = ttk.Checkbutton(side, text="Dzień wolny od zajęć", variable=self.free_day_var, command=self._toggle_free_day, style="Panel.TCheckbutton")
        self.free_day_check.grid(row=16, column=0, sticky="w", pady=(0, 8))
        ttk.Label(side, text="Tydzień", style="Panel.TLabel").grid(row=17, column=0, sticky="w")
        self.week_combo = ttk.Combobox(side, textvariable=self.week_var, values=tuple(WEEK_OPTIONS), state="readonly")
        self.week_combo.grid(row=18, column=0, sticky="ew", pady=(4, 8))
        self.week_combo.bind("<<ComboboxSelected>>", self._save_override)
        ttk.Label(side, text="Dzień planu", style="Panel.TLabel").grid(row=19, column=0, sticky="w")
        self.day_combo = ttk.Combobox(side, textvariable=self.day_var, values=tuple(DAY_OPTIONS), state="readonly")
        self.day_combo.grid(row=20, column=0, sticky="ew", pady=(4, 5))
        self.day_combo.bind("<<ComboboxSelected>>", self._save_override)
        ttk.Label(side, text="Dzień wolny pomija ustawione nadpisanie.", style="Muted.TLabel", wraplength=310).grid(row=21, column=0, sticky="w", pady=(0, 11))

        ttk.Separator(side).grid(row=22, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(side, text="Zakres przedmiotu", style="Section.TLabel").grid(row=23, column=0, sticky="w", pady=(0, 7))
        self.fetch_subjects_button = SquircleButton(side, "Pobierz przedmioty", self._fetch_subjects, "neutral", self.colors, height=30)
        self.fetch_subjects_button.grid(row=24, column=0, sticky="ew", pady=(0, 7))
        self.subjects_combo = ttk.Combobox(side, textvariable=self.subjects_var, values=(), state="readonly")
        self.subjects_combo.grid(row=25, column=0, sticky="ew", pady=(0, 7))
        ttk.Label(side, text="Od (RRRR-MM-DD)", style="Panel.TLabel").grid(row=26, column=0, sticky="w")
        ttk.Entry(side, textvariable=self.range_start_var).grid(row=27, column=0, sticky="ew", pady=(4, 7))
        ttk.Label(side, text="Do (RRRR-MM-DD)", style="Panel.TLabel").grid(row=28, column=0, sticky="w")
        ttk.Entry(side, textvariable=self.range_end_var).grid(row=29, column=0, sticky="ew", pady=(4, 7))
        self.apply_range_button = SquircleButton(side, "Ustaw zakres", self._apply_subject_range, "neutral", self.colors, height=32)
        self.apply_range_button.grid(row=30, column=0, sticky="ew", pady=(0, 5))
        self.remove_range_button = SquircleButton(side, "Wyczyść zakres", self._clear_subject_range, "neutral", self.colors, height=30)
        self.remove_range_button.grid(row=31, column=0, sticky="ew", pady=(0, 7))
        ttk.Label(side, text="Zakres dat zastępuje tydzień (tyg. I/II) dla wybranego przedmiotu.", style="Muted.TLabel", wraplength=310).grid(row=32, column=0, sticky="w", pady=(0, 11))

        self.show_plan_button = SquircleButton(side, "Pokaż plan", self._show_plan, "neutral", self.colors, height=36)
        self.show_plan_button.grid(row=33, column=0, sticky="ew", pady=(0, 7))
        self.sync_button = SquircleButton(side, "Synchronizuj z Google Calendar", self._sync_calendar, "primary", self.colors, height=40)
        self.sync_button.grid(row=34, column=0, sticky="ew", pady=(4, 7))
        self.clear_button = SquircleButton(side, "Usuń wygenerowane wydarzenia", self._clear_calendar, "danger", self.colors, height=38)
        self.clear_button.grid(row=35, column=0, sticky="ew")

        log_frame = ttk.Frame(outer, padding=(0, 10, 0, 0))
        log_frame.grid(row=2, column=0, sticky="ew")
        log_frame.columnconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=2, wrap="word", state="disabled", bg=self.colors["panel"], fg=self.colors["muted"], relief="flat", font=("Consolas", 9), padx=8, pady=5)
        self.log.grid(row=0, column=0, sticky="ew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)
        self.root.bind_all("<MouseWheel>", self._on_sidebar_mousewheel)
        self.root.bind_all("<Button-4>", lambda event: self._scroll_sidebar(event, -1))
        self.root.bind_all("<Button-5>", lambda event: self._scroll_sidebar(event, 1))

    def _toggle_fullscreen(self, _event=None):
        if not self.fullscreen:
            self.windowed_geometry = self.root.geometry()
            self.fullscreen = True
            self.root.attributes("-fullscreen", True)
        else:
            self.fullscreen = False
            self.root.attributes("-fullscreen", False)
            self.root.geometry(getattr(self, "windowed_geometry", "1060x700"))

    def _toggle_theme(self):
        self.dark_mode = self.dark_mode_var.get()
        self.colors = DARK_COLORS if self.dark_mode else COLORS
        self.root.configure(bg=self.colors["background"])
        self._configure_styles()
        self.calendar_card.set_colors(self.colors)
        self.sidebar_card.set_colors(self.colors)
        self.sidebar_canvas.configure(bg=self.colors["panel"])
        self.previous_button.set_colors(self.colors)
        self.next_button.set_colors(self.colors)
        self.sync_button.set_colors(self.colors)
        self.clear_button.set_colors(self.colors)
        self.fetch_subjects_button.set_colors(self.colors)
        self.apply_range_button.set_colors(self.colors)
        self.remove_range_button.set_colors(self.colors)
        self.show_plan_button.set_colors(self.colors)
        self.log.configure(bg=self.colors["panel"], fg=self.colors["muted"])
        for swatch, color_key in self.legend_swatches:
            swatch.configure(bg=self.colors[color_key])
        self._draw_calendar()

    def _update_sidebar_scrollregion(self, _event=None):
        self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all"))

    def _resize_sidebar_content(self, event):
        self.sidebar_canvas.itemconfigure(self.sidebar_window, width=event.width)

    def _pointer_over_sidebar(self, event):
        left = self.sidebar_canvas.winfo_rootx()
        top = self.sidebar_canvas.winfo_rooty()
        return left <= event.x_root <= left + self.sidebar_canvas.winfo_width() and top <= event.y_root <= top + self.sidebar_canvas.winfo_height()

    def _on_sidebar_mousewheel(self, event):
        if not self._pointer_over_sidebar(event):
            return None
        units = int(-event.delta / 120)
        if units == 0:
            units = -1 if event.delta > 0 else 1
        self.sidebar_canvas.yview_scroll(units, "units")
        return "break"

    def _scroll_sidebar(self, event, units):
        if self._pointer_over_sidebar(event):
            self.sidebar_canvas.yview_scroll(units, "units")
            return "break"
        return None

    def _move_month(self, delta):
        index = self.visible_year * 12 + self.visible_month - 1 + delta
        self.visible_year, month_index = divmod(index, 12)
        self.visible_month = month_index + 1
        self._draw_calendar()

    def _on_semester_date_change(self, *_args):
        self._draw_calendar()

    def _read_semester_dates(self):
        start = datetime.strptime(self.semester_start_var.get().strip(), "%Y-%m-%d").date()
        end = datetime.strptime(self.semester_end_var.get().strip(), "%Y-%m-%d").date()
        if start > end:
            raise ValueError("Początek semestru musi przypadać przed jego końcem.")
        return start, end

    def _draw_calendar(self):
        self.month_label.configure(text=f"{MONTHS[self.visible_month - 1].capitalize()} {self.visible_year}")
        for child in self.calendar_grid.winfo_children():
            child.destroy()

        for col, weekday in enumerate(WEEKDAYS):
            ttk.Label(self.calendar_grid, text=weekday, style="Muted.TLabel", anchor="center").grid(row=0, column=col, sticky="nsew", pady=(0, 5))

        try:
            semester_start, semester_end = self._read_semester_dates()
        except ValueError:
            semester_start = semester_end = None
        start_mark = self._parse_optional_date(self.semester_start_var.get())
        end_mark = self._parse_optional_date(self.semester_end_var.get())
        month_rows = calendar.Calendar(firstweekday=0).monthdatescalendar(self.visible_year, self.visible_month)
        while len(month_rows) < 6:
            last_day = month_rows[-1][-1]
            month_rows.append([last_day.fromordinal(last_day.toordinal() + offset) for offset in range(1, 8)])

        for row, week in enumerate(month_rows, start=1):
            for col, day in enumerate(week):
                bg = self.colors["panel"]
                fg = self.colors["text"]
                if day.month != self.visible_month:
                    bg, fg = self.colors["subtle"], self.colors["muted"]
                elif day.weekday() >= 5:
                    fg = self.colors["muted"]
                if semester_start and semester_end and semester_start <= day <= semester_end:
                    bg = self.colors["semester"]
                if day.isoformat() in self.day_overrides:
                    bg = self.colors["override"]
                if day in self.free_days:
                    bg = self.colors["free"]
                if day == self.selected_date:
                    bg = self.colors["selected"]
                    fg = self.colors["text"]
                if day == start_mark or day == end_mark:
                    fg = self.colors["accent"]
                label = str(day.day)
                if day == start_mark:
                    label += "\nPoczątek"
                elif day == end_mark:
                    label += "\nKoniec"
                elif day in self.free_days:
                    label += "\nWolne"
                elif day.isoformat() in self.day_overrides:
                    label += "\nZmiana"
                outline = self.colors["border"]
                if day == self.today:
                    outline = self.colors["today"]
                elif day == self.selected_date:
                    outline = self.colors["accent"]
                cell = CalendarCell(
                    self.calendar_grid,
                    label,
                    bg,
                    fg,
                    outline,
                    day == self.selected_date,
                    day == self.today,
                    self.colors,
                    lambda selected=day: self._select_date(selected),
                )
                cell.grid(row=row, column=col, sticky="nsew", padx=3, pady=3)

    @staticmethod
    def _parse_optional_date(value):
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except (ValueError, AttributeError):
            return None

    def _select_date(self, selected):
        mode = self.date_mode_var.get()
        if mode == "start":
            self.semester_start_var.set(selected.isoformat())
        elif mode == "end":
            self.semester_end_var.set(selected.isoformat())
        self.selected_date = selected
        self.visible_year = selected.year
        self.visible_month = selected.month
        self.date_mode_var.set("select")
        self._update_selected_date_panel()
        self._draw_calendar()

    def _update_selected_date_panel(self):
        weekday_name = POLISH_WEEKDAYS[self.selected_date.weekday()]
        self.selected_label.configure(text=f"{weekday_name}, {self.selected_date:%d.%m.%Y}")
        self.free_day_var.set(self.selected_date in self.free_days)
        override = self.day_overrides.get(self.selected_date.isoformat(), {})
        week_value = override.get("week")
        self.week_var.set(next((label for label, value in WEEK_OPTIONS.items() if value == week_value), "Automatycznie"))
        day_value = override.get("day")
        if day_value is None or day_value == self.selected_date.weekday():
            day_label = "Jak w kalendarzu"
        else:
            day_label = next((label for label, value in DAY_OPTIONS.items() if value == day_value), "Jak w kalendarzu")
        self.day_var.set(day_label)

    def _toggle_free_day(self):
        if self.free_day_var.get():
            self.free_days.add(self.selected_date)
        else:
            self.free_days.discard(self.selected_date)
        self._draw_calendar()

    def _save_override(self, _event=None):
        values = {}
        week_value = WEEK_OPTIONS[self.week_var.get()]
        day_value = DAY_OPTIONS[self.day_var.get()]
        if week_value is not None:
            values["week"] = week_value
        if day_value is not None and day_value != self.selected_date.weekday():
            values["day"] = day_value
        date_key = self.selected_date.isoformat()
        if values:
            self.day_overrides[date_key] = values
        else:
            self.day_overrides.pop(date_key, None)
        self._draw_calendar()

    def _fetch_subjects(self):
        link = self.link_var.get().strip()
        if not link:
            messagebox.showerror("Nieprawidłowe dane", "Podaj link do planu zajęć.", parent=self.root)
            return

        def operation():
            downloader = fetch.ScheduleDownloader(link)
            classes = downloader.fetch()
            if not classes:
                raise ValueError("Nie udało się pobrać zajęć z planu.")
            self.job_queue.put(("subjects", classes))

        self._start_job("Pobieranie przedmiotów", operation)

    def _update_subjects(self, classes):
        pairs = sorted({(event.get("subject"), event.get("class_type")) for event in classes})
        self.subject_options = {f'{subject} ({class_type})': (subject, class_type) for subject, class_type in pairs}
        labels = list(self.subject_options)
        self.subjects_combo.configure(values=labels)
        self.subjects_var.set(labels[0] if labels else "")

    def _selected_subject_key(self):
        label = self.subjects_var.get()
        if label not in self.subject_options:
            raise ValueError("Wybierz przedmiot z listy (najpierw kliknij „Pobierz przedmioty”).")
        return self.subject_options[label]

    def _read_range_dates(self):
        start_text = self.range_start_var.get().strip()
        end_text = self.range_end_var.get().strip()
        if not start_text or not end_text:
            raise ValueError("Podaj datę początku i końca zakresu (RRRR-MM-DD).")
        start = datetime.strptime(start_text, "%Y-%m-%d").date()
        end = datetime.strptime(end_text, "%Y-%m-%d").date()
        if start > end:
            raise ValueError("Początek zakresu musi przypadać przed jego końcem.")
        return start_text, end_text

    def _apply_subject_range(self):
        try:
            subject, class_type = self._selected_subject_key()
            start_text, end_text = self._read_range_dates()
        except ValueError as error:
            messagebox.showerror("Nieprawidłowe dane", str(error), parent=self.root)
            return
        self.subject_ranges[(subject, class_type)] = {"start": start_text, "end": end_text}
        self._append_log(f"Zakres {subject} ({class_type}): {start_text} – {end_text}\n")

    def _clear_subject_range(self):
        try:
            subject, class_type = self._selected_subject_key()
        except ValueError as error:
            messagebox.showerror("Nieprawidłowe dane", str(error), parent=self.root)
            return
        if (subject, class_type) in self.subject_ranges:
            del self.subject_ranges[(subject, class_type)]
            self._append_log(f"Usunięto zakres dla: {subject} ({class_type})\n")

    def _show_plan(self):
        link = self.link_var.get().strip()
        if not link:
            messagebox.showerror("Nieprawidłowe dane", "Podaj link do planu zajęć.", parent=self.root)
            return
        try:
            start, end = self._read_semester_dates()
        except ValueError as error:
            messagebox.showerror("Nieprawidłowe dane", str(error), parent=self.root)
            return
        free_days = sorted(day.isoformat() for day in self.free_days)
        day_overrides = {key: value.copy() for key, value in self.day_overrides.items()}
        subject_ranges = {key: value.copy() for key, value in self.subject_ranges.items()}

        def operation():
            downloader = fetch.ScheduleDownloader(link)
            classes = downloader.fetch()
            if not classes:
                raise ValueError("Nie udało się pobrać zajęć z planu.")
            for (subject, class_type), date_range in subject_ranges.items():
                edit.apply_subject_date_range(classes, subject, class_type, date_range["start"], date_range["end"])
            data = {
                "source": link,
                "events": classes,
                "semester_start": start.isoformat(),
                "semester_end": end.isoformat(),
                "free_days": free_days,
                "day_overrides": day_overrides,
            }
            self.job_queue.put(("view", data))

        self._start_job("Przygotowywanie widoku planu", operation)

    def _open_plan_window(self, data):
        window = tk.Toplevel(self.root)
        window.title("Podgląd planu")
        window.geometry("1250x800")
        window.configure(bg=self.colors["background"])

        toolbar = ttk.Frame(window)
        toolbar.pack(fill="x", padx=12, pady=(10, 6))
        save_button = SquircleButton(toolbar, "Zapisz PDF", lambda: self._save_view_pdf(window, data), "primary", self.colors, width=160, height=36)
        save_button.pack(side="left", padx=(0, 8))
        close_button = SquircleButton(toolbar, "Zamknij", window.destroy, "neutral", self.colors, width=120, height=36)
        close_button.pack(side="left")

        text_frame = ttk.Frame(window)
        text_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        text = tk.Text(text_frame, wrap="none", bg=self.colors["panel"], fg=self.colors["text"], relief="flat", font=("Consolas", 9), padx=10, pady=8)
        text.pack(side="left", fill="both", expand=True)
        y_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=text.yview)
        y_scroll.pack(side="right", fill="y")
        x_scroll = ttk.Scrollbar(window, orient="horizontal", command=text.xview)
        x_scroll.pack(fill="x", padx=12, pady=(0, 10))
        text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        rendered = view.TimetableViewer(data).render()
        text.insert("1.0", re.sub(r"\x1b\[[0-9;]*m", "", rendered))
        text.configure(state="disabled")

    def _save_view_pdf(self, parent, data):
        path = filedialog.asksaveasfilename(
            parent=parent,
            title="Zapisz plan jako PDF",
            defaultextension=".pdf",
            initialfile="schedule.pdf",
            filetypes=[("Plik PDF", "*.pdf")],
        )
        if not path:
            return
        try:
            view.TimetableViewer(data).save_pdf(path)
        except Exception as error:
            messagebox.showerror("Błąd zapisu", str(error), parent=parent)

    def _validate_inputs(self):
        link = self.link_var.get().strip()
        calendar_id = self.calendar_id_var.get().strip()
        if not link:
            raise ValueError("Podaj link do planu zajęć.")
        if not calendar_id:
            raise ValueError("Podaj calendar_id.")
        start, end = self._read_semester_dates()
        return link, calendar_id, start, end

    def _sync_calendar(self):
        try:
            link, calendar_id, start, end = self._validate_inputs()
        except ValueError as error:
            messagebox.showerror("Nieprawidłowe dane", str(error), parent=self.root)
            return
        if not messagebox.askyesno(
            "Potwierdź synchronizację",
            "Synchronizacja zastąpi wydarzenia wygenerowane wcześniej przez tę aplikację. Kontynuować?",
            parent=self.root,
        ):
            return

        free_days = sorted(day.isoformat() for day in self.free_days)
        day_overrides = {key: value.copy() for key, value in self.day_overrides.items()}
        subject_ranges = {key: value.copy() for key, value in self.subject_ranges.items()}
        self._start_job("Synchronizacja planu", lambda: self._do_sync(link, calendar_id, start, end, free_days, day_overrides, subject_ranges))

    @staticmethod
    def _do_sync(link, calendar_id, start, end, free_days, day_overrides, subject_ranges=None):
        downloader = fetch.ScheduleDownloader(link)
        classes = downloader.fetch()
        if not classes:
            raise ValueError("Nie udało się pobrać zajęć z planu. Kalendarz nie został zmieniony.")
        for (subject, class_type), date_range in (subject_ranges or {}).items():
            edit.apply_subject_date_range(classes, subject, class_type, date_range["start"], date_range["end"])
        data = {
            "events": classes,
            "semester_start": start.isoformat(),
            "semester_end": end.isoformat(),
            "free_days": free_days,
            "day_overrides": day_overrides,
        }
        occurrences = export.expand_occurrences(
            events=classes,
            semester_start=start.isoformat(),
            semester_end=end.isoformat(),
            free_days=free_days,
            day_overrides=day_overrides,
        )
        if not occurrences:
            raise ValueError("Brak wydarzeń w wybranym zakresie. Kalendarz nie został zmieniony.")
        exporter = export.GoogleCalendarExporter(
            str(BASE_DIR / "credentials.json"),
            str(BASE_DIR / "token.pickle"),
            "PBTimetableExtractor",
        )
        exporter.sync(calendar_id=calendar_id, data=data, purge_managed=True)

    def _clear_calendar(self):
        calendar_id = self.calendar_id_var.get().strip()
        if not calendar_id:
            messagebox.showerror("Nieprawidłowe dane", "Podaj calendar_id.", parent=self.root)
            return
        if not messagebox.askyesno(
            "Potwierdź usunięcie",
            "Usunąć wszystkie wydarzenia oznaczone jako wygenerowane przez tę aplikację?",
            parent=self.root,
        ):
            return
        exporter = export.GoogleCalendarExporter(
            str(BASE_DIR / "credentials.json"),
            str(BASE_DIR / "token.pickle"),
            "PBTimetableExtractor",
        )
        self._start_job("Usuwanie wygenerowanych wydarzeń", lambda: exporter.clear(calendar_id))

    def _start_job(self, label, operation):
        if self.job_running:
            return
        self.job_running = True
        self.status_var.set(label + "…")
        self.sync_button.set_enabled(False)
        self.clear_button.set_enabled(False)
        self.show_plan_button.set_enabled(False)
        self._append_log(label + "…\n")

        def run():
            try:
                with contextlib.redirect_stdout(QueueWriter(self.job_queue)):
                    operation()
                self.job_queue.put(("done", None))
            except Exception as error:
                self.job_queue.put(("done", (str(error), traceback.format_exc())))

        threading.Thread(target=run, daemon=True).start()

    def _poll_job_queue(self):
        try:
            while True:
                kind, payload = self.job_queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "subjects":
                    self._update_subjects(payload)
                elif kind == "view":
                    self._open_plan_window(payload)
                elif kind == "done":
                    self.job_running = False
                    self.sync_button.set_enabled(True)
                    self.clear_button.set_enabled(True)
                    self.show_plan_button.set_enabled(True)
                    if payload is None:
                        self.status_var.set("Zakończono")
                        self._append_log("Gotowe.\n")
                    else:
                        error, details = payload
                        self.status_var.set("Operacja nie powiodła się")
                        self._append_log(error + "\n")
                        self._append_log(details)
                        messagebox.showerror("Błąd operacji", error, parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_job_queue)

    def _append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")


def main():
    os.chdir(BASE_DIR)
    root = tk.Tk()
    TimetableGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
