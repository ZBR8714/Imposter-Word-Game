"""
Imposter Word Game - Python/Tkinter port of the original VB.NET WinForms game.

Changes in this version:
  - Cleaned up, lighter/medium color theme with pill-shaped buttons everywhere.
  - The window is a normal, titled, alt-tabbable window (no more overrideredirect
    trick that made it vanish/behave oddly when focus was lost).
  - Word lists now live permanently in a `wordlists/` folder next to this script.
    The app always remembers the most recently used word list (even across
    "Reset" and across separate runs of the program). The old "Import Custom
    Word List" button is now "Change Word List" and opens a small picker that
    lets you switch between any list already in `wordlists/`, or import a new
    CSV (which gets copied into `wordlists/` so it's available next time too).
  - The reveal card on Screen 2 still does its quick flip animation, now drawn
    with rounded corners to match the rest of the UI.

Run with:  python imposter_game.py
"""

import json
import random
import shutil
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox


def _app_dir():
    """Folder the app should treat as 'home' for wordlists/settings.

    When bundled into a .exe with PyInstaller, __file__ points at a temporary
    extraction folder, not where the .exe actually lives - so we use the
    executable's own location instead whenever running frozen.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


SCRIPT_DIR = _app_dir()

# ---------------------------------------------------------------------------------------
# Theme (light/medium palette, pill buttons)
# ---------------------------------------------------------------------------------------
BG = "#F5F8FC"           # app background - soft light blue-grey
CARD_BG = "#FFFFFF"      # cards / entries / reveal card
BORDER = "#D9E2EC"       # subtle border for inputs
TEXT_DARK = "#2B2F45"    # primary text
TEXT_MUTED = "#7A8399"   # secondary / helper text
TEXT_ACCENT = "#5B4FE0"  # the red-text equivalent (category/word highlights)

PURPLE = "#7C6FF0"       # Change word list / +/- player / reveal card border
GREEN_BTN = "#4FCB7A"    # Start Game / Next
YELLOW = "#FFC94D"       # Reset / New Game
RED_BTN = "#FF6F6F"      # Exit

WHITE = "#FFFFFF"

FONT_TITLE = ("Arial", 24, "bold")
FONT_HEADING18B = ("Arial", 18, "bold")
FONT_HEADING18 = ("Arial", 18)
FONT_PLAYERLBL = ("Arial", 14)
FONT_PLAYERTXT = ("Arial", 12)
FONT_BTN15 = ("Arial", 15, "bold")
FONT_BTN18 = ("Arial", 18, "bold")
FONT_BTN24 = ("Arial", 24, "bold")
FONT_LBL12 = ("Arial", 12)

WIDTH, HEIGHT = 484, 861


# ---------------------------------------------------------------------------------------
# Small color helper (used for hover/pressed shades of pill buttons)
# ---------------------------------------------------------------------------------------
def shade(hex_color, factor):
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = max(0, min(255, int(r * factor)))
    g = max(0, min(255, int(g * factor)))
    b = max(0, min(255, int(b * factor)))
    return f"#{r:02x}{g:02x}{b:02x}"


def round_rect_points(x1, y1, x2, y2, radius):
    r = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    r = max(r, 0)
    return [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]


# ---------------------------------------------------------------------------------------
# Pill-shaped button (Canvas based - Tkinter has no native rounded button)
# ---------------------------------------------------------------------------------------
class PillButton(tk.Canvas):
    def __init__(self, master, text, command, w, h, bg, fg="white", font=FONT_BTN15,
                 border=None):
        parent_bg = master["bg"] if "bg" in master.keys() else BG
        super().__init__(master, width=w, height=h, bg=parent_bg,
                          highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.w, self.h = w, h
        self.base_bg = bg
        self.hover_bg = shade(bg, 0.94)
        self.active_bg = shade(bg, 0.85)
        self.fg = fg
        self.font = font
        self.text = text
        self.border = border
        self.enabled = True
        self._draw(self.base_bg)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _draw(self, color):
        self.delete("all")
        radius = self.h / 2
        pts = round_rect_points(1, 1, self.w - 1, self.h - 1, radius)
        outline = self.border if self.border else color
        self.create_polygon(pts, fill=color, outline=outline, smooth=True, width=1.5)
        self.create_text(self.w / 2, self.h / 2, text=self.text, fill=self.fg,
                          font=self.font, justify="center", width=self.w - 14)

    def _on_enter(self, _e):
        if self.enabled:
            self._draw(self.hover_bg)

    def _on_leave(self, _e):
        self._draw(self.base_bg if self.enabled else shade(self.base_bg, 1.0))

    def _on_press(self, _e):
        if self.enabled:
            self._draw(self.active_bg)

    def _on_release(self, _e):
        if self.enabled:
            self._draw(self.hover_bg)
            if self.command:
                self.command()

    def set_text(self, text):
        self.text = text
        self._draw(self.base_bg)

    def set_enabled(self, enabled):
        self.enabled = enabled
        if enabled:
            self.config(cursor="hand2")
            self._draw(self.base_bg)
        else:
            self.config(cursor="arrow")
            self._draw(shade(self.base_bg, 1.15))


def center_x(widget, window_width=WIDTH):
    """Mirrors `lbl.Left = (Me.ClientSize.Width - lbl.Width) / 2`."""
    widget.update_idletasks()
    w = widget.winfo_reqwidth()
    x = max((window_width - w) // 2, 0)
    y = widget.place_info().get("y", 0)
    widget.place(x=x, y=y)


# ---------------------------------------------------------------------------------------
# Word list management - persistent `wordlists/` folder + remembered selection
# ---------------------------------------------------------------------------------------
class WordListManager:
    DIR = SCRIPT_DIR / "wordlists"
    CONFIG_PATH = SCRIPT_DIR / "settings.json"
    _current = None  # filename (str) of the currently selected csv inside DIR

    @classmethod
    def ensure_ready(cls):
        cls.DIR.mkdir(exist_ok=True)
        # Migrate any legacy word lists sitting next to the script into the
        # new folder so existing users don't lose their files.
        if not any(cls.DIR.glob("*.csv")):
            for legacy_name in ("wordlist.csv", "new_wordlist.csv"):
                legacy = SCRIPT_DIR / legacy_name
                if legacy.exists():
                    try:
                        shutil.copy(legacy, cls.DIR / legacy_name)
                    except Exception:  # noqa: BLE001
                        pass

    @classmethod
    def list_files(cls):
        return sorted(cls.DIR.glob("*.csv"), key=lambda p: p.name.lower())

    @classmethod
    def load_last(cls):
        name = None
        try:
            data = json.loads(cls.CONFIG_PATH.read_text(encoding="utf-8"))
            name = data.get("last_wordlist")
        except Exception:  # noqa: BLE001
            name = None
        if name and (cls.DIR / name).exists():
            cls._current = name
            return
        files = cls.list_files()
        cls._current = files[0].name if files else None

    @classmethod
    def save_current(cls):
        try:
            cls.CONFIG_PATH.write_text(
                json.dumps({"last_wordlist": cls._current}), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            pass

    @classmethod
    def current_name(cls):
        return cls._current

    @classmethod
    def current_path(cls):
        if cls._current and (cls.DIR / cls._current).exists():
            return cls.DIR / cls._current
        return None

    @classmethod
    def set_current(cls, name):
        cls._current = name
        cls.save_current()

    @classmethod
    def import_file(cls, src_path):
        """Copies an external CSV into wordlists/, de-duping the filename if needed."""
        src = Path(src_path)
        dest = cls.DIR / src.name
        i = 1
        while dest.exists():
            dest = cls.DIR / f"{src.stem} ({i}){src.suffix}"
            i += 1
        shutil.copy(src, dest)
        return dest.name


# ---------------------------------------------------------------------------------------
# Game data model (Players.vb + GameData.vb)
# ---------------------------------------------------------------------------------------
class Player:
    def __init__(self, name):
        self.name = name
        self.imposter = False
        self.weight = 10


class GameData:
    imposters = 1
    word = ""
    category = ""
    hint = ""
    players = [Player("Player 1"), Player("Player 2"), Player("Player 3")]

    @staticmethod
    def player_count():
        return len(GameData.players)


# ---------------------------------------------------------------------------------------
# CSV / word logic (ReadCSV / RandomWord / SetImposters from Screen1.vb)
# ---------------------------------------------------------------------------------------
def read_csv(path_str):
    """Returns (success, words[], categories[], hints[], has_hints)."""
    words, categories, hints = [], [], []
    has_hints = False
    path = Path(path_str)
    try:
        if not path.exists():
            return False, [], [], [], False
        with open(path, encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
        for line in lines[1:]:  # skip header, mirrors reader.ReadLine() before the loop
            if not line:
                continue
            fields = line.split(",")
            if len(fields) < 2:
                continue
            categories.append(fields[0])
            words.append(fields[1])
            hint = fields[2].strip() if len(fields) >= 3 else ""
            hints.append(hint)
            if hint:
                has_hints = True
        if len(words) == 0:
            messagebox.showinfo("", "File is Empty")
            return False, [], [], [], False
        return True, words, categories, hints, has_hints
    except Exception as ex:  # noqa: BLE001
        messagebox.showerror("", f"An error occured when trying to read this file: \n{ex}")
        return False, [], [], [], False


def random_word(path_str, hints_checked):
    success, words, categories, hints, has_hints = read_csv(path_str)
    if not success:
        return False
    idx = random.randrange(len(words))
    GameData.word = words[idx]
    GameData.category = categories[idx]
    if hints_checked:
        if not hints[idx]:
            messagebox.showinfo(
                "",
                "There is no hint word(s) for the randomly selected word, check your "
                "imported csv file or uncheck 'Hint Words?'",
            )
            return False
        hint_list = [h.strip() for h in hints[idx].split("|")]
        GameData.hint = random.choice(hint_list)
    else:
        GameData.hint = ""
    return True


def set_imposters():
    for p in GameData.players:
        p.imposter = False

    assigned = 0
    while assigned < GameData.imposters:
        total_weight = sum(p.weight for p in GameData.players if not p.imposter)
        roll = random.randint(0, max(total_weight - 1, 0))
        running = 0
        for p in GameData.players:
            if not p.imposter:
                running += p.weight
                if running > roll:
                    p.imposter = True
                    assigned += 1
                    break

    for p in GameData.players:
        if p.imposter:
            p.weight = 10
        else:
            p.weight += 2


# ---------------------------------------------------------------------------------------
# Word list picker dialog
# ---------------------------------------------------------------------------------------
class WordListDialog(tk.Toplevel):
    def __init__(self, master, on_select):
        super().__init__(master)
        self.title("Change Word List")
        self.configure(bg=BG)
        self.geometry("360x480")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.on_select = on_select

        tk.Label(self, text="Choose a Word List", bg=BG, fg=TEXT_DARK,
                 font=FONT_HEADING18B).pack(pady=(22, 4))
        tk.Label(self, text="The selected list stays active between games.",
                 bg=BG, fg=TEXT_MUTED, font=FONT_LBL12).pack(pady=(0, 14))

        list_holder = tk.Frame(self, bg=BG)
        list_holder.pack(fill="both", expand=True, padx=18)

        canvas = tk.Canvas(list_holder, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(list_holder, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw", width=300)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        files = WordListManager.list_files()
        current = WordListManager.current_name()
        if not files:
            tk.Label(inner, text="No word lists found yet.\nImport one below to get started.",
                      bg=BG, fg=TEXT_MUTED, font=FONT_LBL12, justify="center").pack(pady=16)
        for f in files:
            is_current = (f.name == current)
            label = f.stem + ("   \u2713 current" if is_current else "")
            color = GREEN_BTN if is_current else PURPLE
            btn = PillButton(inner, label, (lambda f=f: self._choose(f)),
                              w=300, h=46, bg=color, fg=WHITE, font=FONT_BTN15)
            btn.pack(pady=6)

        bottom = tk.Frame(self, bg=BG)
        bottom.pack(pady=(6, 20))
        PillButton(bottom, "+ Import New Word List", self._import, w=300, h=48,
                    bg=YELLOW, fg=TEXT_DARK, font=FONT_BTN15).pack(pady=(0, 8))
        PillButton(bottom, "Cancel", self.destroy, w=300, h=40,
                    bg=CARD_BG, fg=TEXT_MUTED, font=FONT_LBL12, border=BORDER).pack()

    def _choose(self, f):
        self.on_select(f.name)
        self.destroy()

    def _import(self):
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        success, _w, _c, _h, _has_hints = read_csv(path)
        if not success:
            return
        new_name = WordListManager.import_file(path)
        self.on_select(new_name)
        self.destroy()


# ---------------------------------------------------------------------------------------
# Screen1: Setup
# ---------------------------------------------------------------------------------------
class Screen1(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG, width=WIDTH, height=HEIGHT)
        self.app = app

        tk.Label(self, text="Players", bg=BG, fg=TEXT_DARK, font=FONT_TITLE).place(x=177, y=24)

        self.player_rows = []
        for n in range(1, 9):
            y = 83 + 32 * (n - 1)
            lbl = tk.Label(self, text=f"{n}.", bg=BG, fg=TEXT_DARK, font=FONT_PLAYERLBL)
            var = tk.StringVar()
            txt = tk.Entry(self, textvariable=var, font=FONT_PLAYERTXT, bg=CARD_BG,
                            fg=TEXT_DARK, relief="solid", bd=1,
                            highlightthickness=1, highlightbackground=BORDER,
                            highlightcolor=PURPLE, insertbackground=TEXT_DARK)
            lbl.place(x=31, y=y)
            txt.place(x=62, y=y, width=385, height=26)
            var.trace_add("write", lambda *_, idx=n - 1, v=var: self._name_changed(idx, v))
            self.player_rows.append({"lbl": lbl, "txt": txt, "var": var, "y": y})

        PillButton(self, "+ Player", self.cmd_add_player, w=208, h=39, bg=PURPLE,
                    fg=WHITE, font=("Arial", 16, "bold")).place(x=25, y=347)
        PillButton(self, "- Player", self.cmd_remove_player, w=208, h=39, bg=PURPLE,
                    fg=WHITE, font=("Arial", 16, "bold")).place(x=239, y=347)

        tk.Label(self, text="Imposter(s)", bg=BG, fg=TEXT_DARK, font=FONT_TITLE).place(x=147, y=424)
        self.imposters_var = tk.IntVar(value=GameData.imposters)
        self.nud_imposters = tk.Spinbox(
            self, from_=1, to=max(1, GameData.player_count() - 1),
            textvariable=self.imposters_var, font=FONT_HEADING18, justify="center",
            bg=CARD_BG, fg=TEXT_DARK, relief="solid", bd=1,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=PURPLE,
            command=self._imposters_changed
        )
        self.nud_imposters.place(x=221, y=474, width=41, height=35)

        PillButton(self, "Change Word List", self.cmd_change_wordlist, w=208, h=70,
                    bg=PURPLE, fg=WHITE, font=("Arial", 16, "bold")).place(x=138, y=550)
        PillButton(self, "Start Game", self.cmd_start_game, w=208, h=70,
                    bg=GREEN_BTN, fg=WHITE, font=FONT_BTN18).place(x=138, y=747)
        PillButton(self, "Reset", self.cmd_reset, w=137, h=50,
                    bg=YELLOW, fg=TEXT_DARK, font=FONT_BTN15).place(x=335, y=12)
        PillButton(self, "Exit", self.app.destroy, w=137, h=50,
                    bg=RED_BTN, fg=WHITE, font=FONT_BTN15).place(x=12, y=12)

        self.lbl_wordlist_result = tk.Label(self, text="Word List: ", bg=BG,
                                              fg=TEXT_MUTED, font=FONT_LBL12)
        self.lbl_wordlist_result.place(x=174, y=634)

        self.hints_var = tk.BooleanVar(value=True)
        self.chk_hints = tk.Checkbutton(self, text="Hint Words?", variable=self.hints_var,
                                          bg=BG, fg=TEXT_DARK, font=("Arial", 18, "bold"),
                                          activebackground=BG, selectcolor=CARD_BG,
                                          cursor="hand2")
        self.chk_hints.place(x=155, y=686)

        self._load_players()
        self._refresh_wordlist_ui()

    # -- mirrors LoadPlayers() -----------------------------------------------------
    def _load_players(self):
        max_imposters = max(GameData.player_count() - 1, 1)
        self.nud_imposters.config(to=max_imposters)
        if self.imposters_var.get() > max_imposters:
            self.imposters_var.set(max_imposters)
            GameData.imposters = max_imposters

        for n in range(1, 9):
            row = self.player_rows[n - 1]
            if n <= GameData.player_count():
                row["lbl"].place(x=31, y=row["y"])
                row["txt"].place(x=62, y=row["y"], width=385, height=26)
                row["var"].set(GameData.players[n - 1].name)
            else:
                row["lbl"].place_forget()
                row["txt"].place_forget()

    def _name_changed(self, idx, var):
        if idx < GameData.player_count():
            GameData.players[idx].name = var.get()

    # -- word list UI -----------------------------------------------------------------
    def _refresh_wordlist_ui(self):
        name = WordListManager.current_name()
        if not name:
            self.lbl_wordlist_result.config(text="Word List: none found - click Change Word List")
            self.chk_hints.config(state="disabled")
            self.hints_var.set(False)
            center_x(self.lbl_wordlist_result)
            return

        self.lbl_wordlist_result.config(text=f"Word List: {name}")
        center_x(self.lbl_wordlist_result)

        path = WordListManager.current_path()
        _success, _w, _c, _h, has_hints = read_csv(path)
        if not has_hints:
            self.chk_hints.config(state="disabled")
            self.hints_var.set(False)
        else:
            self.chk_hints.config(state="normal")

    def cmd_change_wordlist(self):
        WordListDialog(self.app, on_select=self._on_wordlist_selected)

    def _on_wordlist_selected(self, name):
        WordListManager.set_current(name)
        self._refresh_wordlist_ui()

    # -- event handlers --------------------------------------------------------------
    def cmd_add_player(self):
        if GameData.player_count() >= 8:
            messagebox.showinfo("", "You cannot have more than 8 players")
        else:
            GameData.players.append(Player(f"Player {GameData.player_count() + 1}"))
        self._load_players()

    def cmd_remove_player(self):
        if GameData.player_count() <= 3:
            messagebox.showinfo("", "You cannot have less than 3 players")
        else:
            GameData.players.pop()
        self._load_players()

    def _imposters_changed(self):
        GameData.imposters = int(self.imposters_var.get())

    def cmd_reset(self):
        # Resets players/imposters only - the selected word list is intentionally
        # left alone, since it should persist between games and app restarts.
        GameData.players = [Player("Player 1"), Player("Player 2"), Player("Player 3")]
        self.imposters_var.set(1)
        GameData.imposters = 1
        self._load_players()
        self._refresh_wordlist_ui()

    def cmd_start_game(self):
        path = WordListManager.current_path()
        if path is None:
            messagebox.showinfo("", "No word list is available. Use 'Change Word List' to import one.")
            return
        if not random_word(path, self.hints_var.get()):
            return
        set_imposters()
        for n in range(1, 9):
            if n <= GameData.player_count():
                if GameData.players[n - 1].name == "":
                    GameData.players[n - 1].name = f"Player {n}"
                    self.player_rows[n - 1]["var"].set(GameData.players[n - 1].name)
        self.app.show_frame("screen2")

    def on_show(self):
        if GameData.player_count() < 3:
            GameData.players = [Player("Player 1"), Player("Player 2"), Player("Player 3")]
        self._load_players()
        self._refresh_wordlist_ui()


# ---------------------------------------------------------------------------------------
# Screen2: Reveal (animated flip card)
# ---------------------------------------------------------------------------------------
class RevealCard(tk.Canvas):
    """A rounded, card-shaped canvas that can 'flip' by shrinking/growing its width."""

    def __init__(self, master, x, y, w, h):
        super().__init__(master, width=w, height=h, bg=BG, highlightthickness=0,
                          bd=0, cursor="hand2")
        self.place(x=x, y=y)
        self.full_w = w
        self.h = h
        self.cur_w = w
        self.text = "HOLD TO\nREVEAL"
        self.text_color = TEXT_DARK
        self._redraw()

    def _redraw(self):
        self.delete("all")
        w = max(self.cur_w, 4)
        x_off = (self.full_w - w) / 2
        radius = min(28, w / 2, self.h / 2)
        pts = round_rect_points(x_off + 2, 2, x_off + w - 2, self.h - 2, radius)
        self.create_polygon(pts, fill=CARD_BG, outline=PURPLE, width=3, smooth=True)
        if w > 60:
            self.create_text(self.full_w / 2, self.h / 2, text=self.text,
                              fill=self.text_color, font=FONT_HEADING18B,
                              width=w - 36, justify="center")

    def set_width(self, w):
        self.cur_w = max(w, 4)
        self._redraw()

    def set_content(self, text, color):
        self.text = text
        self.text_color = color
        self._redraw()


class Screen2(tk.Frame):
    CARD_X, CARD_Y, CARD_W, CARD_H = 75, 136, 333, 536

    def __init__(self, master, app):
        super().__init__(master, bg=BG, width=WIDTH, height=HEIGHT)
        self.app = app
        self.player_idx = 0
        self.holding = False
        self.flip_job = None

        PillButton(self, "New Game", self.cmd_new, w=137, h=50,
                    bg=YELLOW, fg=TEXT_DARK, font=FONT_BTN15).place(x=335, y=12)
        PillButton(self, "Exit", self.app.destroy, w=137, h=50,
                    bg=RED_BTN, fg=WHITE, font=FONT_BTN15).place(x=12, y=12)

        self.lbl_player_name = tk.Label(self, text="Player Name", bg=BG, fg=TEXT_DARK,
                                          font=FONT_HEADING18B)
        self.lbl_player_name.place(x=160, y=81)

        self.reveal_card = RevealCard(self, self.CARD_X, self.CARD_Y, self.CARD_W, self.CARD_H)
        self.reveal_card.bind("<ButtonPress-1>", self._on_press)
        self.reveal_card.bind("<ButtonRelease-1>", self._on_release)

        self.cmd_next = PillButton(self, "Next", self.cmd_next_click, w=223, h=77,
                                     bg=GREEN_BTN, fg=WHITE, font=FONT_BTN24)
        self.cmd_next.place(x=130, y=736)
        self.cmd_next.place_forget()

    # -- flip animation ---------------------------------------------------------------
    def _animate_flip(self, on_midpoint, steps=3, delay=6):
        if self.flip_job:
            return

        def shrink(i):
            w = max(int(self.CARD_W * (1 - i / steps)), 4)
            self.reveal_card.set_width(w)
            if i < steps:
                self.flip_job = self.after(delay, shrink, i + 1)
            else:
                on_midpoint()
                grow(0)

        def grow(i):
            w = max(int(self.CARD_W * (i / steps)), 4)
            self.reveal_card.set_width(w)
            if i < steps:
                self.flip_job = self.after(delay, grow, i + 1)
            else:
                self.reveal_card.set_width(self.CARD_W)
                self.flip_job = None

        shrink(0)

    def _on_press(self, _event):
        if self.holding:
            return
        self.holding = True
        player = GameData.players[self.player_idx]

        def apply_role_face():
            if player.imposter:
                text = f"YOU ARE AN IMPOSTER.\n\nThe category is: {GameData.category}"
                if GameData.hint:
                    text += f"\n\nHINT: {GameData.hint}"
                color = "#E24C4C"
            else:
                text = (f"YOU ARE INNOCENT.\n\nThe category is: {GameData.category}"
                        f"\n\nAnd the word is: {GameData.word}")
                color = "#3E6FE2"
            self.reveal_card.set_content(text, color)

        self._animate_flip(apply_role_face)

    def _on_release(self, _event):
        if not self.holding:
            return
        self.holding = False

        def apply_front_face():
            self.reveal_card.set_content("HOLD TO\nREVEAL", TEXT_DARK)

        self._animate_flip(apply_front_face)
        self.cmd_next.place(x=130, y=736)

    def cmd_next_click(self):
        self.cmd_next.place_forget()
        if self.player_idx < GameData.player_count() - 1:
            self.player_idx += 1
            self._load_player_name()
        else:
            self.app.show_frame("screen3")

    def _load_player_name(self):
        self.lbl_player_name.config(text=GameData.players[self.player_idx].name)
        center_x(self.lbl_player_name)

    def cmd_new(self):
        self.app.show_frame("screen1")

    def on_show(self):
        self.player_idx = 0
        self.holding = False
        self.cmd_next.place_forget()
        self._load_player_name()


# ---------------------------------------------------------------------------------------
# Screen3: Speaking order
# ---------------------------------------------------------------------------------------
class Screen3(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG, width=WIDTH, height=HEIGHT)
        self.app = app

        PillButton(self, "Exit", self.app.destroy, w=137, h=50,
                    bg=RED_BTN, fg=WHITE, font=FONT_BTN15).place(x=12, y=12)
        PillButton(self, "New Game", self.cmd_new, w=137, h=50,
                    bg=YELLOW, fg=TEXT_DARK, font=FONT_BTN15).place(x=335, y=12)

        tk.Label(self, text="The Category is: ", bg=BG, fg=TEXT_DARK, font=FONT_TITLE).place(x=103, y=124)
        self.lbl_category = tk.Label(self, text="....................", bg=BG,
                                       fg=TEXT_ACCENT, font=FONT_HEADING18)
        self.lbl_category.place(x=161, y=173)

        tk.Label(self, text="Speaking Order", bg=BG, fg=TEXT_DARK, font=FONT_TITLE).place(x=114, y=223)
        self.lbl_order = tk.Label(self, text="", bg=BG, fg=TEXT_DARK, font=FONT_HEADING18,
                                    justify="center")
        self.lbl_order.place(x=211, y=260)

        PillButton(self, "Reveal Imposter(s) and Word", self.cmd_reveal_click, w=248, h=87,
                    bg=PURPLE, fg=WHITE, font=("Arial", 16, "bold")).place(x=118, y=587)

    def cmd_reveal_click(self):
        if messagebox.askyesno(
            "", "Are you sure you want to reveal the imposter(s) and secret word?"
        ):
            self.app.show_frame("screen4")

    def cmd_new(self):
        self.app.show_frame("screen1")

    def on_show(self):
        shuffled = GameData.players[:]
        random.shuffle(shuffled)
        text = "\n".join(f"{i + 1}. {p.name}" for i, p in enumerate(shuffled))
        self.lbl_order.config(text=text)
        center_x(self.lbl_order)
        self.lbl_category.config(text=GameData.category)
        center_x(self.lbl_category)


# ---------------------------------------------------------------------------------------
# Screen4: Results
# ---------------------------------------------------------------------------------------
class Screen4(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=BG, width=WIDTH, height=HEIGHT)
        self.app = app

        PillButton(self, "Exit", self.app.destroy, w=137, h=50,
                    bg=RED_BTN, fg=WHITE, font=FONT_BTN15).place(x=12, y=12)
        PillButton(self, "New Game", self.cmd_new, w=137, h=50,
                    bg=YELLOW, fg=TEXT_DARK, font=FONT_BTN15).place(x=335, y=12)

        tk.Label(self, text="The Word is:", bg=BG, fg=TEXT_DARK, font=FONT_TITLE).place(x=136, y=226)
        self.lbl_word = tk.Label(self, text="...................", bg=BG, fg=TEXT_ACCENT,
                                   font=FONT_HEADING18)
        self.lbl_word.place(x=180, y=273)

        tk.Label(self, text="The Imposter(s) are:", bg=BG, fg=TEXT_DARK, font=FONT_TITLE,
                  justify="center").place(x=78, y=334)
        self.lbl_imposter = tk.Label(self, text="...................", bg=BG, fg=TEXT_ACCENT,
                                       font=FONT_HEADING18, justify="center")
        self.lbl_imposter.place(x=180, y=383)

    def cmd_new(self):
        self.app.show_frame("screen1")

    def on_show(self):
        names = "\n".join(p.name for p in GameData.players if p.imposter)
        self.lbl_imposter.config(text=names)
        center_x(self.lbl_imposter)
        self.lbl_word.config(text=GameData.word)
        center_x(self.lbl_word)


# ---------------------------------------------------------------------------------------
# App controller
# ---------------------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Imposter Word Game")
        self.configure(bg=BG)
        # NOTE: intentionally NOT using overrideredirect(True) anymore - that made
        # this a borderless, taskbar-less window that could get stuck behind other
        # windows with no way to bring it back. A normal titled window behaves like
        # every other app: alt-tab works, it has a taskbar entry, etc.
        self.resizable(False, False)
        self.geometry(f"{WIDTH}x{HEIGHT}")

        self.container = tk.Frame(self, width=WIDTH, height=HEIGHT, bg=BG)
        self.container.pack(fill="both", expand=True)
        self.container.pack_propagate(False)

        self.frames = {
            "screen1": Screen1(self.container, self),
            "screen2": Screen2(self.container, self),
            "screen3": Screen3(self.container, self),
            "screen4": Screen4(self.container, self),
        }
        for frame in self.frames.values():
            frame.place(x=0, y=0, width=WIDTH, height=HEIGHT)

        self._center_on_screen()
        self.current = "screen1"
        self.frames["screen1"].on_show()
        self.frames["screen1"].tkraise()

    def _center_on_screen(self):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = int((sw - WIDTH) / 2)
        y = int((sh - HEIGHT) / 2)
        self.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

    def show_frame(self, name):
        self.frames[name].on_show()
        self.frames[name].tkraise()
        self.current = name


if __name__ == "__main__":
    WordListManager.ensure_ready()
    WordListManager.load_last()
    app = App()
    app.mainloop()