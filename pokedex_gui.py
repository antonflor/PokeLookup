"""PokeLookup — a Pokedex-inspired GUI for pokedex.csv.

Pure tkinter, no third-party packages. Sprites are fetched once from the
PokeAPI sprites repo and cached in a local sprites/ folder; without a
network connection a Poke Ball placeholder is drawn instead.

Usage: python pokedex_gui.py
"""

import csv
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent
POKEDEX = REPO / "pokedex.csv"
SPRITE_DIR = REPO / "sprites"
SPRITE_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{id}.png"

# Pokedex shell colours
RED = "#DC0A2D"
RED_DARK = "#A31226"
SCREEN_BG = "#F7F7F2"
SCREEN_EDGE = "#2B2B2B"
LIST_BG = "#20313A"
LIST_FG = "#E8F4FF"
ACCENT = "#FFCB05"  # Pikachu yellow

TYPE_COLORS = {
    "Normal": "#A8A878", "Fire": "#F08030", "Water": "#6890F0",
    "Electric": "#E0B000", "Grass": "#78C850", "Ice": "#58C0C0",
    "Fighting": "#C03028", "Poison": "#A040A0", "Ground": "#D0A048",
    "Flying": "#A890F0", "Psychic": "#F85888", "Bug": "#A8B820",
    "Rock": "#B8A038", "Ghost": "#705898", "Dragon": "#7038F8",
    "Dark": "#705848", "Steel": "#9090A8", "Fairy": "#EE7CA0",
}

STATS = [
    ("HP", "HP"), ("Attack", "Attack"), ("Defense", "Defense"),
    ("SpAttack", "Sp. Atk"), ("SpDefense", "Sp. Def"), ("Speed", "Speed"),
]


def stat_color(value):
    if value < 50:
        return "#E85242"
    if value < 70:
        return "#F5A742"
    if value < 90:
        return "#EFD545"
    if value < 110:
        return "#8BC84A"
    return "#3FBF8F"


def load_pokedex():
    with open(POKEDEX, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_id = {row["ID"]: row for row in rows}
    return rows, by_id


class PokedexApp:
    def __init__(self, root):
        self.root = root
        self.rows, self.by_id = load_pokedex()
        self.filtered = self.rows
        self.current = None
        self.sprite_image = None  # keep a reference so tk doesn't GC it
        self.sprite_token = 0
        self.sprite_queue = queue.Queue()

        # Reverse evolution map for building chains
        self.pre_evolution = {}
        for row in self.rows:
            for target in row["Evolution"].split(","):
                if target.strip():
                    self.pre_evolution[target.strip()] = row["ID"]

        root.title("PokéLookup")
        root.configure(bg=RED)
        root.geometry("1000x780")
        root.minsize(880, 700)

        self._build_header()
        self._build_body()
        self.search_entry.focus_set()
        self._refresh_list()
        self.listbox.selection_set(0)
        self._show(self.rows[0])
        self.root.after(100, self._poll_sprites)

    # ---------- layout ----------

    def _build_header(self):
        header = tk.Canvas(self.root, height=92, bg=RED, highlightthickness=0)
        header.pack(fill="x")
        # Big blue lens
        header.create_oval(18, 10, 92, 84, fill="white", outline="")
        header.create_oval(24, 16, 86, 78, fill="#28AAFD", outline="#1A6FB0", width=3)
        header.create_oval(38, 26, 56, 44, fill="#8FD4FF", outline="")
        # Indicator lights
        for i, color in enumerate(("#FF5050", "#FFD86B", "#6BF06B")):
            x = 110 + i * 30
            header.create_oval(x, 14, x + 16, 30, fill=color, outline="#7A1020", width=2)
        header.create_text(
            112, 62, anchor="w", text="PokéLookup",
            font=("Segoe UI", 24, "bold"), fill="white",
        )
        header.create_text(
            112, 84, anchor="w", text=f"{len(self.rows)} Pokémon · Kanto to Galar",
            font=("Segoe UI", 10), fill="#FFD9DF",
        )
        # Hinge line on the right
        header.create_rectangle(0, 90, 3000, 92, fill=RED_DARK, outline="")

    def _build_body(self):
        body = tk.Frame(self.root, bg=RED)
        body.pack(fill="both", expand=True, padx=14, pady=12)

        # Left: search + list, framed like a screen
        left_bezel = tk.Frame(body, bg=RED_DARK, padx=6, pady=6)
        left_bezel.pack(side="left", fill="y")
        left = tk.Frame(left_bezel, bg=LIST_BG, padx=8, pady=8)
        left.pack(fill="both", expand=True)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_list())
        self.search_entry = tk.Entry(
            left, textvariable=self.search_var, font=("Segoe UI", 12),
            bg="#31434E", fg=LIST_FG, insertbackground=LIST_FG,
            relief="flat", highlightthickness=2,
            highlightbackground="#31434E", highlightcolor=ACCENT,
        )
        self.search_entry.pack(fill="x", ipady=4)
        self.search_entry.bind("<Return>", lambda _e: self._select_index(0))
        self.search_entry.bind("<Down>", lambda _e: self.listbox.focus_set())

        list_frame = tk.Frame(left, bg=LIST_BG)
        list_frame.pack(fill="both", expand=True, pady=(8, 0))
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        self.listbox = tk.Listbox(
            list_frame, width=24, font=("Consolas", 11),
            bg=LIST_BG, fg=LIST_FG, relief="flat", highlightthickness=0,
            selectbackground=ACCENT, selectforeground="#222222",
            yscrollcommand=scrollbar.set, activestyle="none",
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        # Right: main screen inside a dark bezel
        right_bezel = tk.Frame(body, bg=SCREEN_EDGE, padx=8, pady=8)
        right_bezel.pack(side="left", fill="both", expand=True, padx=(14, 0))
        screen = tk.Frame(right_bezel, bg=SCREEN_BG, padx=16, pady=14)
        screen.pack(fill="both", expand=True)
        self.screen = screen

        top = tk.Frame(screen, bg=SCREEN_BG)
        top.pack(fill="x")

        self.sprite_canvas = tk.Canvas(
            top, width=200, height=200, bg="#EDEDE4", highlightthickness=1,
            highlightbackground="#D5D5C8",
        )
        self.sprite_canvas.pack(side="left")

        info = tk.Frame(top, bg=SCREEN_BG)
        info.pack(side="left", fill="both", expand=True, padx=(18, 0))

        name_row = tk.Frame(info, bg=SCREEN_BG)
        name_row.pack(anchor="w")
        self.name_label = tk.Label(
            name_row, bg=SCREEN_BG, fg="#222222", font=("Segoe UI", 22, "bold")
        )
        self.name_label.pack(side="left")
        self.id_label = tk.Label(
            name_row, bg=SCREEN_BG, fg="#888880", font=("Segoe UI", 14)
        )
        self.id_label.pack(side="left", padx=(10, 0), pady=(6, 0))
        self.genus_label = tk.Label(
            info, bg=SCREEN_BG, fg="#888880", font=("Segoe UI", 11, "italic")
        )
        self.genus_label.pack(anchor="w")

        self.type_frame = tk.Frame(info, bg=SCREEN_BG)
        self.type_frame.pack(anchor="w", pady=(4, 8))

        self.detail_label = tk.Label(
            info, bg=SCREEN_BG, fg="#44443C", font=("Segoe UI", 11),
            justify="left", anchor="w",
        )
        self.detail_label.pack(anchor="w")

        weak_row = tk.Frame(info, bg=SCREEN_BG)
        weak_row.pack(anchor="w", pady=(8, 0))
        tk.Label(
            weak_row, text="Weak to:", bg=SCREEN_BG, fg="#44443C",
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left", padx=(0, 6))
        self.weak_frame = tk.Frame(weak_row, bg=SCREEN_BG)
        self.weak_frame.pack(side="left")

        evo_row = tk.Frame(info, bg=SCREEN_BG)
        evo_row.pack(anchor="w", pady=(8, 0))
        tk.Label(
            evo_row, text="Evolution:", bg=SCREEN_BG, fg="#44443C",
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left", padx=(0, 6))
        self.evo_frame = tk.Frame(evo_row, bg=SCREEN_BG)
        self.evo_frame.pack(side="left")

        # Pokedex bio
        self.bio_label = tk.Label(
            screen, bg=SCREEN_BG, fg="#33332B", font=("Segoe UI", 10, "italic"),
            justify="left", anchor="w", wraplength=640,
        )
        self.bio_label.pack(fill="x", pady=(12, 0))

        # Stats block
        stats_box = tk.LabelFrame(
            screen, text=" Base stats ", bg=SCREEN_BG, fg="#44443C",
            font=("Segoe UI", 11, "bold"), bd=1, relief="groove",
            padx=12, pady=8,
        )
        stats_box.pack(fill="x", pady=(14, 0))
        self.stat_widgets = {}
        for key, label in STATS:
            row = tk.Frame(stats_box, bg=SCREEN_BG)
            row.pack(fill="x", pady=2)
            tk.Label(
                row, text=label, width=8, anchor="w", bg=SCREEN_BG,
                fg="#44443C", font=("Segoe UI", 10),
            ).pack(side="left")
            value_label = tk.Label(
                row, width=4, anchor="e", bg=SCREEN_BG, fg="#222222",
                font=("Consolas", 10, "bold"),
            )
            value_label.pack(side="left")
            bar = tk.Canvas(
                row, height=14, bg="#E4E4D8", highlightthickness=0
            )
            bar.pack(side="left", fill="x", expand=True, padx=(8, 0))
            self.stat_widgets[key] = (value_label, bar)
        total_row = tk.Frame(stats_box, bg=SCREEN_BG)
        total_row.pack(fill="x", pady=(4, 0))
        tk.Label(
            total_row, text="Total", width=8, anchor="w", bg=SCREEN_BG,
            fg="#44443C", font=("Segoe UI", 10, "bold"),
        ).pack(side="left")
        self.total_label = tk.Label(
            total_row, width=4, anchor="e", bg=SCREEN_BG, fg="#222222",
            font=("Consolas", 10, "bold"),
        )
        self.total_label.pack(side="left")

        # "Did you know" fact strip
        fact_bar = tk.Frame(screen, bg="#FFF1BF", padx=10, pady=8)
        fact_bar.pack(fill="x", pady=(12, 0))
        tk.Label(
            fact_bar, text="★", bg="#FFF1BF", fg="#C79A00",
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left", padx=(0, 8), anchor="n")
        self.fact_label = tk.Label(
            fact_bar, bg="#FFF1BF", fg="#5A4500", font=("Segoe UI", 10),
            justify="left", anchor="w", wraplength=600,
        )
        self.fact_label.pack(side="left", fill="x", expand=True)

        # Wrap long text to the actual screen width
        def _rewrap(event):
            self.bio_label.config(wraplength=event.width - 40)
            self.fact_label.config(wraplength=event.width - 80)
        screen.bind("<Configure>", _rewrap)

    # ---------- behaviour ----------

    def _refresh_list(self):
        query = self.search_var.get().strip().lower()
        if query.isdigit():
            self.filtered = [r for r in self.rows if str(int(r["ID"])).startswith(str(int(query)))]
        elif query:
            starts = [r for r in self.rows if r["Name"].lower().startswith(query)]
            contains = [
                r for r in self.rows
                if query in r["Name"].lower() and not r["Name"].lower().startswith(query)
            ]
            self.filtered = starts + contains
        else:
            self.filtered = self.rows
        self.listbox.delete(0, "end")
        for row in self.filtered:
            self.listbox.insert("end", f" #{row['ID']}  {row['Name']}")

    def _select_index(self, index):
        if not self.filtered:
            return
        index = max(0, min(index, len(self.filtered) - 1))
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(index)
        self.listbox.see(index)
        self._show(self.filtered[index])

    def _on_select(self, _event):
        selection = self.listbox.curselection()
        if selection:
            self._show(self.filtered[selection[0]])

    def _jump_to(self, pokemon_id):
        row = self.by_id.get(pokemon_id)
        if not row:
            return
        self.search_var.set("")
        index = self.rows.index(row)
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(index)
        self.listbox.see(index)
        self._show(row)

    def _badge(self, parent, text, color, command=None):
        widget = tk.Label(
            parent, text=text, bg=color, fg="white",
            font=("Segoe UI", 9, "bold"), padx=8, pady=2,
        )
        if command:
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda _e: command())
        widget.pack(side="left", padx=(0, 4))
        return widget

    def _show(self, row):
        self.current = row
        self.name_label.config(text=row["Name"])
        self.id_label.config(text=f"#{row['ID']}")
        self.genus_label.config(text=row.get("Genus", ""))
        self.bio_label.config(text=row.get("Bio", ""))
        self.fact_label.config(text=row.get("Fact", ""))

        for frame in (self.type_frame, self.weak_frame, self.evo_frame):
            for child in frame.winfo_children():
                child.destroy()

        for t in row["Types"].split(","):
            t = t.strip()
            self._badge(self.type_frame, t.upper(), TYPE_COLORS.get(t, "#777777"))
        for t in row["Weaknesses"].split(","):
            t = t.strip()
            if t:
                self._badge(self.weak_frame, t.upper(), TYPE_COLORS.get(t, "#777777"))

        details = []
        if row.get("HeightM"):
            details.append(f"Height  {row['HeightM']} m      Weight  {row['WeightKg']} kg")
        if row.get("Generation"):
            details.append(f"First seen  {row['Generation']} — {row['Region']}")
        if row.get("FirstLocation"):
            details.append(f"Location  {row['FirstLocation']}")
        self.detail_label.config(text="\n".join(details))

        # Evolution chain: walk back to the base form, then forwards
        chain_start = row["ID"]
        visited = {chain_start}
        while chain_start in self.pre_evolution:
            chain_start = self.pre_evolution[chain_start]
            if chain_start in visited:  # guard against bad data cycles
                break
            visited.add(chain_start)
        shown = False
        frontier = [chain_start]
        seen = set()
        while frontier:
            pid = frontier.pop(0)
            if pid in seen or pid not in self.by_id:
                continue
            seen.add(pid)
            member = self.by_id[pid]
            if pid != row["ID"]:
                shown = True
                self._badge(
                    self.evo_frame, member["Name"], "#5A7A9A",
                    command=lambda p=pid: self._jump_to(p),
                )
            frontier.extend(
                t.strip() for t in member["Evolution"].split(",") if t.strip()
            )
        if not shown:
            tk.Label(
                self.evo_frame, text="None", bg=SCREEN_BG, fg="#888880",
                font=("Segoe UI", 10, "italic"),
            ).pack(side="left")

        total = 0
        for key, _label in STATS:
            value_label, bar = self.stat_widgets[key]
            value = int(row[key]) if row.get(key) else 0
            total += value
            value_label.config(text=str(value) if value else "—")
            bar.delete("all")
            width = max(bar.winfo_width(), 200)
            bar.create_rectangle(
                0, 0, width * min(value, 255) / 255, 14,
                fill=stat_color(value), outline="",
            )
        self.total_label.config(text=str(total) if total else "—")

        self._load_sprite(row["ID"])

    # ---------- sprites ----------

    def _load_sprite(self, pokemon_id):
        self.sprite_token += 1
        token = self.sprite_token
        path = SPRITE_DIR / f"{int(pokemon_id)}.png"
        if path.exists():
            self._set_sprite(path, token)
            return
        self._draw_placeholder("Fetching…")

        def worker():
            try:
                SPRITE_DIR.mkdir(exist_ok=True)
                url = SPRITE_URL.format(id=int(pokemon_id))
                with urllib.request.urlopen(url, timeout=10) as resp:
                    data = resp.read()
                path.write_bytes(data)
                self.sprite_queue.put((token, path))
            except Exception:
                self.sprite_queue.put((token, None))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_sprites(self):
        try:
            while True:
                token, path = self.sprite_queue.get_nowait()
                if path is None:
                    self._draw_placeholder("No sprite", token)
                else:
                    self._set_sprite(path, token)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_sprites)

    def _set_sprite(self, path, token):
        if token != self.sprite_token:
            return
        try:
            self.sprite_image = tk.PhotoImage(file=str(path)).zoom(2)
        except tk.TclError:
            self._draw_placeholder("No sprite", token)
            return
        self.sprite_canvas.delete("all")
        self.sprite_canvas.create_image(101, 101, image=self.sprite_image)

    def _draw_placeholder(self, caption, token=None):
        if token is not None and token != self.sprite_token:
            return
        c = self.sprite_canvas
        c.delete("all")
        c.create_oval(60, 60, 140, 140, fill="#E44", outline="#333", width=3)
        c.create_arc(60, 60, 140, 140, start=180, extent=180, fill="white", outline="")
        c.create_line(60, 100, 140, 100, fill="#333", width=3)
        c.create_oval(90, 90, 110, 110, fill="white", outline="#333", width=3)
        c.create_text(100, 165, text=caption, font=("Segoe UI", 10), fill="#888")


def main():
    root = tk.Tk()
    try:
        default_font = tkfont.nametofont("TkDefaultFont")
        default_font.configure(family="Segoe UI", size=10)
    except tk.TclError:
        pass
    PokedexApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
