#!/usr/bin/env python3
"""Simple Stroop task: name the INK color of the displayed word.

Cross-platform (macOS / Linux / Windows).  Only depends on the Python
standard library — no pip install needed.  Each session writes a CSV into
a 'data/' folder next to this script.  Files are made world-readable on
Unix-like systems so the data is easy to share.

Run with:   python3 StroopTaskSimple.py
"""
import csv
import datetime as dt
import os
import random
import re
import time
import tkinter as tk
from pathlib import Path

COLORS = ["red", "green", "blue", "yellow"]
KEYS = {"r": "red", "g": "green", "b": "blue", "y": "yellow"}
DATA_DIR = Path(__file__).resolve().parent / "data"


def _make_public(path):
    """Best-effort world-readable permissions; no-op on Windows."""
    if os.name != "posix":
        return
    try:
        os.chmod(path, 0o755 if path.is_dir() else 0o644)
    except OSError:
        pass


def build_trials(n, rng):
    """Return n (word, ink) pairs, exactly half congruent, then shuffled."""
    n_cong = n // 2
    n_inc = n - n_cong
    trials = []
    for _ in range(n_cong):
        c = rng.choice(COLORS)
        trials.append((c, c))
    for _ in range(n_inc):
        word = rng.choice(COLORS)
        ink = rng.choice([c for c in COLORS if c != word])
        trials.append((word, ink))
    rng.shuffle(trials)
    return trials


def sanitize(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_") or "anon"


# ---------- setup screen -----------------------------------------------

class SetupFrame(tk.Frame):
    def __init__(self, root, on_start):
        super().__init__(root, bg="black")
        self.root = root
        self.on_start = on_start
        self._build()

    @staticmethod
    def _only_digits(value):
        return value == "" or value.isdigit()

    def _build(self):
        tk.Label(self, text="Stroop Task",
                 fg="white", bg="black",
                 font=("Helvetica", 24, "bold")).pack(pady=(30, 20))

        digits_vcmd = (self.root.register(self._only_digits), "%P")

        for label, attr, default, numeric in [
            ("Participant name:", "name_entry",   "",   False),
            ("Participant ID:",   "id_entry",     "",   True),
            ("Number of trials:", "trials_entry", "30", True),
        ]:
            row = tk.Frame(self, bg="black"); row.pack(pady=5)
            tk.Label(row, text=label, fg="white", bg="black",
                     font=("Helvetica", 13), width=18,
                     anchor="e").pack(side="left")
            e = tk.Entry(row, font=("Helvetica", 13), width=24)
            if numeric:
                e.config(validate="key", validatecommand=digits_vcmd)
            if default:
                e.insert(0, default)
            e.pack(side="left", padx=6)
            setattr(self, attr, e)

        tk.Button(self, text="Start", command=self._start,
                  bg="#88dd88", fg="black",
                  highlightbackground="#228833",
                  activeforeground="black",
                  font=("Helvetica", 14, "bold"),
                  width=18, height=2).pack(pady=(25, 10))

        self.msg = tk.Label(self, text="", fg="#ffaa44", bg="black",
                            font=("Helvetica", 12))
        self.msg.pack(pady=5)

        self.name_entry.focus_set()

    def _start(self):
        name = self.name_entry.get().strip()
        if not name:
            self.msg.config(text="Please enter a name.")
            return
        pid = self.id_entry.get().strip()
        if not pid:
            self.msg.config(text="Please enter a numeric ID.")
            return
        try:
            n = int(self.trials_entry.get())
            if n <= 0:
                raise ValueError
        except ValueError:
            self.msg.config(text="Trials must be a positive integer.")
            return
        if n % 2:
            n += 1
        self.on_start(name=name, pid=pid, n_trials=n)


# ---------- task -------------------------------------------------------

class StroopTask:
    def __init__(self, root, name, pid, n_trials, on_reset=None):
        self.root = root
        self.name = name
        self.pid = pid
        self.n_trials = n_trials
        self.on_reset = on_reset
        self.rng = random.Random()

        self.trial_idx = 0
        self.trial_list = []
        self.current = None
        self.start_time = None
        self.results = []
        self.awaiting_start = True

        self.frame = tk.Frame(root, bg="black")
        self.frame.pack(fill="both", expand=True)
        self.label = tk.Label(self.frame, text="",
                              font=("Helvetica", 64, "bold"),
                              bg="black", fg="white")
        self.label.pack(expand=True)
        self.info = tk.Label(self.frame, text="", font=("Helvetica", 16),
                             fg="white", bg="black", justify="center")
        self.info.pack(pady=20)

        self._show_start()
        root.bind("<Key>", self.on_key)

    def _show_start(self):
        self.label.config(text="")
        self.info.config(text=(
            "Press the first letter of the INK color\n"
            "(r / g / b / y).\n\n"
            "Press SPACE to begin."))
        self.awaiting_start = True

    def _begin(self):
        self.trial_list = build_trials(self.n_trials, self.rng)
        self.trial_idx = 0
        self.awaiting_start = False
        self._countdown(3)

    def _countdown(self, n):
        if n <= 0:
            self.label.config(text="+", fg="white")
            self.info.config(text="")
            self.root.after(500, self.next_trial)
            return
        self.label.config(text=str(n), fg="white")
        self.info.config(text="Get ready...")
        self.root.after(1000, lambda: self._countdown(n - 1))

    def next_trial(self):
        if self.trial_idx >= self.n_trials:
            self._finish()
            return
        word, ink = self.trial_list[self.trial_idx]
        self.current = (word, ink)
        self.label.config(text=word.upper(), fg=ink)
        self.info.config(
            text=f"Trial {self.trial_idx + 1} / {self.n_trials}")
        self.start_time = time.perf_counter()

    def on_key(self, event):
        key = event.keysym.lower()
        if self.awaiting_start:
            if key == "space":
                self._begin()
            return
        if self.current is None or key not in KEYS:
            return
        rt = (time.perf_counter() - self.start_time) * 1000
        word, ink = self.current
        response = KEYS[key]
        correct = response == ink
        self.results.append({
            "timestamp": dt.datetime.now().isoformat(timespec="milliseconds"),
            "trial": self.trial_idx + 1,
            "word": word, "ink": ink, "congruent": word == ink,
            "response": response, "correct": correct, "rt_ms": rt,
        })
        self.trial_idx += 1
        self.current = None
        self.label.config(text="+", fg="white")
        self.root.after(self.rng.randint(400, 800), self.next_trial)

    def _finish(self):
        self.root.unbind("<Key>")
        path = self._save()
        n = len(self.results)
        n_correct = sum(1 for r in self.results if r["correct"])
        cong = [r["rt_ms"] for r in self.results
                if r["correct"] and r["congruent"]]
        inc = [r["rt_ms"] for r in self.results
               if r["correct"] and not r["congruent"]]
        lines = [f"Done!  {n_correct}/{n} correct ({n_correct/n:.0%})"]
        if cong:
            lines.append(f"Congruent RT: {sum(cong)/len(cong):.0f} ms")
        if inc:
            lines.append(f"Incongruent RT: {sum(inc)/len(inc):.0f} ms")
        if cong and inc:
            lines.append(
                f"Stroop effect: "
                f"{sum(inc)/len(inc) - sum(cong)/len(cong):+.0f} ms")
        lines.append(f"\nSaved to:\n{path}")
        self.label.config(text="")
        self.info.config(text="\n".join(lines))

    def _save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _make_public(DATA_DIR)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = DATA_DIR / f"{self.pid}_{sanitize(self.name)}_{stamp}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["participant_id", "participant_name", "timestamp",
                        "trial", "word", "ink", "congruent",
                        "response", "correct", "rt_ms"])
            for r in self.results:
                w.writerow([
                    self.pid, self.name, r["timestamp"], r["trial"],
                    r["word"], r["ink"],
                    "yes" if r["congruent"] else "no",
                    r["response"],
                    "yes" if r["correct"] else "no",
                    round(r["rt_ms"], 1),
                ])
        _make_public(path)
        return path

        if self.on_reset is not None:
            row = tk.Frame(self.frame, bg="black"); row.pack(pady=20)
            tk.Button(row, text="New Session", command=self.on_reset,
                      bg="#88dd88", fg="black",
                      highlightbackground="#228833",
                      activeforeground="black",
                      font=("Helvetica", 14, "bold"),
                      width=16, height=2).pack(side="left", padx=10)
            tk.Button(row, text="Quit", command=self.root.destroy,
                      fg="black", activeforeground="black",
                      font=("Helvetica", 12),
                      width=10, height=2).pack(side="left", padx=10)

# ---------- entry point ------------------------------------------------

def main():
    root = tk.Tk()
    root.title("Stroop Task — Simple")
    root.geometry("600x440")
    root.configure(bg="black")

    def show_setup():
        for child in root.winfo_children():
            child.destroy()
        root.unbind("<Key>")
        SetupFrame(root, on_start).pack(fill="both", expand=True)

    def on_start(name, pid, n_trials):
        for child in root.winfo_children():
            child.destroy()
        StroopTask(root, name, pid, n_trials, on_reset=show_setup)

    show_setup()
    root.mainloop()


if __name__ == "__main__":
    main()
