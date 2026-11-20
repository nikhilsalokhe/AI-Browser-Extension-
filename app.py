"""
app.py - AI Browser Agent Desktop App
Run with: python app.py  or double-click run.bat
"""

import sys
sys.dont_write_bytecode = True

import json
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from browser_agent import BrowserAgent, load_config, save_config
from memory import get_memory


# ══════════════════════════════════════════════════════════════════════
#  Color palette
# ══════════════════════════════════════════════════════════════════════
BG       = "#0f172a"
CARD     = "#1e293b"
CARD2    = "#162032"
BORDER   = "#334155"
TEXT     = "#f8fafc"
MUTED    = "#94a3b8"
PRIMARY  = "#3b82f6"
SUCCESS  = "#10b981"
DANGER   = "#ef4444"
WARN     = "#f59e0b"
PURPLE   = "#8b5cf6"
TEAL     = "#14b8a6"


# ══════════════════════════════════════════════════════════════════════
#  Example commands grouped by category
# ══════════════════════════════════════════════════════════════════════
EXAMPLES = {
    "🔍 Search & Open": [
        ("Latest AI news",          "Find the latest artificial intelligence news"),
        ("Cricket score today",     "search for cricket score today"),
        ("Eiffel Tower info",       "tell me about the Eiffel Tower"),
        ("Python tutorials",        "find Python programming tutorials for beginners"),
        ("Weather today",           "what is the weather today in Delhi"),
        ("Machine learning",        "what is machine learning"),
    ],
    "🛒 Shopping": [
        ("iPhone price on Amazon",  "show me the price of iPhone 15 on Amazon"),
        ("Sony headphones",         "Find the price of Sony WH-1000XM5 headphones on Amazon"),
        ("Laptop deals",            "find best laptop deals under 50000 on Amazon"),
    ],
    "▶️ YouTube": [
        ("Lo-fi music",             "open YouTube and search for lo-fi music"),
        ("Python tutorial video",   "open YouTube and search for Python tutorial for beginners"),
        ("News today",              "search YouTube for news today"),
    ],
    "📖 Wikipedia": [
        ("Python language",         "go to Wikipedia and search for Python programming language"),
        ("World War 2",             "search Wikipedia for World War 2"),
        ("Albert Einstein",         "search Wikipedia for Albert Einstein"),
    ],
    "🌐 Open Any Website": [
        ("Open Google",             "open www.google.com"),
        ("Open GitHub",             "go to www.github.com"),
        ("Open Reddit",             "open Reddit and find programming posts"),
    ],
}


# ══════════════════════════════════════════════════════════════════════
#  Main App Window
# ══════════════════════════════════════════════════════════════════════
class ModernApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("🤖 AI Browser Agent — Autonomous Web Copilot")
        self.geometry("860x760")
        self.minsize(760, 620)
        self.configure(bg=BG)

        self.config_data   = load_config()
        self.agent         = None
        self.worker_thread = None
        self.show_help     = tk.BooleanVar(value=True)   # help panel open by default

        self._setup_styles()
        self._build_ui()
        self._show_welcome()

    # ── Styles ────────────────────────────────────────────────────────
    def _setup_styles(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".",            background=BG,    foreground=TEXT)
        st.configure("TLabel",       background=BG,    foreground=TEXT, font=("Segoe UI", 10))
        st.configure("Card.TLabel",  background=CARD,  foreground=TEXT, font=("Segoe UI", 9))
        st.configure("Muted.TLabel", background=BG,    foreground=MUTED, font=("Segoe UI", 9))
        st.configure("TFrame",       background=BG)
        st.configure("Card.TFrame",  background=CARD)
        st.configure("TCombobox",    fieldbackground="#090d16", background=CARD,
                     foreground=TEXT, selectbackground=PRIMARY)
        st.map("TCombobox", fieldbackground=[("readonly", "#090d16")])

    # ── Full UI layout ────────────────────────────────────────────────
    def _build_ui(self):
        # Root paned window: left=main, right=help panel
        self.root_pane = tk.PanedWindow(self, orient="horizontal", bg=BG,
                                        sashwidth=4, sashrelief="flat", bd=0)
        self.root_pane.pack(fill="both", expand=True)

        # ── LEFT COLUMN ──────────────────────────────────────────────
        left = tk.Frame(self.root_pane, bg=BG)
        self.root_pane.add(left, minsize=440)

        self._build_header(left)
        self._build_settings(left)
        self._build_command_area(left)
        self._build_log_area(left)

        # ── RIGHT COLUMN (help panel) ────────────────────────────────
        self.help_panel = tk.Frame(self.root_pane, bg=CARD2, bd=0)
        self.root_pane.add(self.help_panel, minsize=260)
        self._build_help_panel(self.help_panel)

    # ── Header ───────────────────────────────────────────────────────
    def _build_header(self, parent):
        f = tk.Frame(parent, bg=BG, padx=14, pady=10)
        f.pack(fill="x")

        # Robot icon + title
        tk.Label(f, text="🤖", font=("Segoe UI", 28), bg=BG).pack(side="left", padx=(0, 10))

        info = tk.Frame(f, bg=BG)
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text="AI Browser Agent", font=("Segoe UI", 16, "bold"),
                 bg=BG, fg=TEXT).pack(anchor="w")
        tk.Label(info, text="Type any command in plain English  •  AI controls your browser automatically",
                 font=("Segoe UI", 9), bg=BG, fg=MUTED).pack(anchor="w")

        # Status + buttons on the right
        right = tk.Frame(f, bg=BG)
        right.pack(side="right")

        self.status_pill = tk.Label(right, text="● IDLE", font=("Segoe UI", 9, "bold"),
                                    bg=BORDER, fg=MUTED, padx=10, pady=4, relief="flat")
        self.status_pill.pack(anchor="e", pady=(0, 4))

        btn_box = tk.Frame(right, bg=BG)
        btn_box.pack(anchor="e")

        tk.Button(btn_box, text="🧠 Memory",
                  font=("Segoe UI", 8, "bold"), bg=TEAL, fg="white",
                  bd=0, padx=8, pady=3, cursor="hand2",
                  command=self._open_memory_window).pack(side="left", padx=(0, 4))

        tk.Button(btn_box, text="📖 Help",
                  font=("Segoe UI", 8), bg=PURPLE, fg="white",
                  bd=0, padx=8, pady=3, cursor="hand2",
                  command=self._toggle_help).pack(side="left")

        # Thin divider
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=14)

    # ── Settings ─────────────────────────────────────────────────────
    def _build_settings(self, parent):
        f = tk.LabelFrame(parent, text=" ⚙️ Settings ",
                          font=("Segoe UI", 9, "bold"),
                          bg=CARD, fg=MUTED, bd=1, relief="solid",
                          padx=10, pady=8)
        f.pack(fill="x", padx=14, pady=(10, 0))

        # ── Row 1: Groq API Key (PRIMARY — free & powerful) ───────────
        tk.Label(f, text="🤖 GROQ AI KEY  (Free — groq.com/keys)",
                 font=("Segoe UI", 9, "bold"), bg=CARD, fg=TEAL).pack(anchor="w", pady=(0, 2))

        r0 = tk.Frame(f, bg=CARD)
        r0.pack(fill="x", pady=(0, 4))
        self.groq_key_entry = tk.Entry(r0, show="•", bg="#061a1a", fg="#5eead4",
                                       insertbackground="#5eead4", bd=1, relief="solid",
                                       font=("Segoe UI", 10))
        self.groq_key_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.groq_key_entry.insert(0, self.config_data.get("groq_api_key", ""))

        tk.Button(r0, text="👁", font=("Segoe UI", 8), bg=BORDER, fg="white",
                  bd=0, padx=6, pady=4,
                  command=lambda: self.groq_key_entry.config(
                      show="" if self.groq_key_entry.cget("show") == "•" else "•")
                  ).pack(side="left", padx=(4, 0))

        # Groq model selector
        r0b = tk.Frame(f, bg=CARD)
        r0b.pack(fill="x", pady=(0, 6))
        tk.Label(r0b, text="Groq Model:", font=("Segoe UI", 9),
                 bg=CARD, fg=MUTED).pack(side="left", padx=(0, 6))
        self.groq_model_var = tk.StringVar(value=self.config_data.get("groq_model", "llama3-8b-8192"))
        ttk.Combobox(r0b, textvariable=self.groq_model_var,
                     values=["llama3-8b-8192", "llama3-70b-8192",
                             "mixtral-8x7b-32768", "gemma2-9b-it", "gemma-7b-it"],
                     state="readonly", width=22).pack(side="left")
        tk.Label(r0b, text="  ← Free models, pick any",
                 font=("Segoe UI", 8), bg=CARD, fg=MUTED).pack(side="left")

        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=(0, 6))

        # ── Row 2: Optional Gemini key ────────────────────────────────
        r1 = tk.Frame(f, bg=CARD)
        r1.pack(fill="x", pady=2)
        tk.Label(r1, text="Gemini Key (optional):", font=("Segoe UI", 9),
                 bg=CARD, fg=MUTED, width=20, anchor="w").pack(side="left")
        self.api_key_entry = tk.Entry(r1, show="•", bg="#090d16", fg="#94a3b8",
                                      insertbackground="white", bd=1, relief="solid",
                                      font=("Segoe UI", 9))
        self.api_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=3)
        self.api_key_entry.insert(0, self.config_data.get("gemini_api_key", ""))

        # Save button
        tk.Button(r1, text="💾 Save All", font=("Segoe UI", 9, "bold"), bg=TEAL, fg="white",
                  bd=0, padx=10, pady=2,
                  command=lambda: self._save_settings(show_dialog=True)).pack(side="left")

        # Row 3: Browser
        r2 = tk.Frame(f, bg=CARD)
        r2.pack(fill="x", pady=(6, 2))
        tk.Label(r2, text="Browser:", font=("Segoe UI", 9),
                 bg=CARD, fg=TEXT).pack(side="left", padx=(0, 6))
        self.browser_var = tk.StringVar(value=self.config_data.get("browser", "chrome"))
        ttk.Combobox(r2, textvariable=self.browser_var,
                     values=["chrome", "msedge"],
                     state="readonly", width=10).pack(side="left")
        self.model_var = tk.StringVar(value="free")  # kept for compatibility

        # Info lines
        tk.Label(f,
                 text="✅ With Groq key: AI plans every step intelligently   "
                      "🔵 Without key: built-in intelligence used",
                 font=("Segoe UI", 8), bg=CARD, fg=SUCCESS,
                 wraplength=500, justify="left").pack(anchor="w", pady=(4, 0))
        tk.Label(f,
                 text="🆓 Get your FREE Groq key at: console.groq.com/keys  (takes 30 seconds)",
                 font=("Segoe UI", 8, "bold"), bg=CARD, fg=WARN).pack(anchor="w")

    # ── Command area ─────────────────────────────────────────────────
    def _build_command_area(self, parent):
        f = tk.Frame(parent, bg=BG, padx=14, pady=10)
        f.pack(fill="x")

        # Label row
        lrow = tk.Frame(f, bg=BG)
        lrow.pack(fill="x", pady=(0, 4))
        tk.Label(lrow, text="Your Command:", font=("Segoe UI", 10, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Label(lrow, text="  Type anything in plain English — no special syntax needed",
                 font=("Segoe UI", 9), bg=BG, fg=MUTED).pack(side="left")

        # Text box
        self.cmd_text = tk.Text(f, height=3, bg="#090d16", fg="#fff",
                                insertbackground="white", bd=1, relief="solid",
                                font=("Segoe UI", 11), padx=10, pady=8,
                                wrap="word")
        self.cmd_text.pack(fill="x")
        self.cmd_text.insert("1.0", "Find the latest news about artificial intelligence")
        self.cmd_text.bind("<Return>", lambda e: (self._start_task(), "break")[1])

        # Quick example chips
        chips_outer = tk.Frame(f, bg=BG)
        chips_outer.pack(fill="x", pady=(6, 0))
        tk.Label(chips_outer, text="Quick examples:", font=("Segoe UI", 8),
                 bg=BG, fg=MUTED).pack(side="left", padx=(0, 8))

        quick = [
            ("🔍 AI News",        "Find the latest artificial intelligence news"),
            ("🛒 Amazon",         "show me the price of iPhone 15 on Amazon"),
            ("▶️ YouTube",        "open YouTube and search for lo-fi music"),
            ("📖 Wikipedia",      "search Wikipedia for machine learning"),
            ("🌤 Weather",         "what is the weather today"),
        ]
        for label, cmd in quick:
            tk.Button(chips_outer, text=label, font=("Segoe UI", 8),
                      bg=CARD, fg="#cbd5e1", bd=1, relief="solid",
                      padx=6, pady=2, cursor="hand2",
                      command=lambda c=cmd: self._set_prompt(c)).pack(side="left", padx=(0, 5))

        # Action buttons
        btn_row = tk.Frame(f, bg=BG)
        btn_row.pack(fill="x", pady=(8, 0))

        self.run_btn = tk.Button(
            btn_row,
            text="🚀  Run — AI Opens Your Browser & Fulfills This Command",
            font=("Segoe UI", 11, "bold"),
            bg=PRIMARY, fg="white", bd=0, pady=10, cursor="hand2",
            command=self._start_task
        )
        self.run_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.stop_btn = tk.Button(
            btn_row, text="🛑 Stop",
            font=("Segoe UI", 10, "bold"),
            bg=BORDER, fg=MUTED, bd=0, pady=10, width=8,
            state="disabled", cursor="hand2",
            command=self._stop_task
        )
        self.stop_btn.pack(side="right")

        # Hint under buttons
        tk.Label(f, text="⌨️  Press Enter inside the box to run  •  🛑 Stop anytime",
                 font=("Segoe UI", 8), bg=BG, fg=MUTED).pack(anchor="w", pady=(4, 0))

    # ── Live log area ─────────────────────────────────────────────────
    def _build_log_area(self, parent):
        f = tk.Frame(parent, bg=BG, padx=14, pady=(0, 10))
        f.pack(fill="both", expand=True)

        hdr = tk.Frame(f, bg=BG)
        hdr.pack(fill="x", pady=(0, 4))
        tk.Label(hdr, text="📡  LIVE ACTIVITY LOG", font=("Segoe UI", 9, "bold"),
                 bg=BG, fg=MUTED).pack(side="left")
        tk.Button(hdr, text="Clear", font=("Segoe UI", 8),
                  bg=BORDER, fg=MUTED, bd=0, padx=8, pady=1,
                  command=self._clear_log).pack(side="right")

        self.log_area = scrolledtext.ScrolledText(
            f, bg="#060d1a", fg="#cbd5e1",
            insertbackground="white", bd=1, relief="solid",
            font=("Consolas", 9), padx=10, pady=8, wrap="word"
        )
        self.log_area.pack(fill="both", expand=True)

        self.log_area.tag_config("head",    foreground="#60a5fa", font=("Consolas", 9, "bold"))
        self.log_area.tag_config("ok",      foreground="#34d399", font=("Consolas", 9, "bold"))
        self.log_area.tag_config("err",     foreground="#f87171", font=("Consolas", 9, "bold"))
        self.log_area.tag_config("thought", foreground="#6b7280", font=("Consolas", 8, "italic"))
        self.log_area.tag_config("dim",     foreground="#475569", font=("Consolas", 8))
        self.log_area.tag_config("result",  foreground="#facc15", font=("Consolas", 9))

    # ── Help / examples panel ─────────────────────────────────────────
    def _build_help_panel(self, parent):
        # Scrollable canvas inside the panel
        canvas = tk.Canvas(parent, bg=CARD2, bd=0, highlightthickness=0)
        sb = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=CARD2)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_resize(e):
            canvas.itemconfig(win_id, width=e.width)
        canvas.bind("<Configure>", on_resize)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        # Mouse wheel scroll
        def _scroll(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _scroll)

        pad = dict(padx=12, pady=4)

        # Title
        tk.Label(inner, text="📖  What Can I Say?",
                 font=("Segoe UI", 13, "bold"), bg=CARD2, fg=TEXT).pack(anchor="w", padx=12, pady=(12, 2))
        tk.Label(inner, text="Click any example to load it →",
                 font=("Segoe UI", 8), bg=CARD2, fg=MUTED).pack(anchor="w", **pad)

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", padx=12, pady=6)

        # How it works section
        tk.Label(inner, text="⚡  How It Works",
                 font=("Segoe UI", 10, "bold"), bg=CARD2, fg=WARN).pack(anchor="w", **pad)

        steps = [
            ("1️⃣", "You type a command in plain English"),
            ("2️⃣", "AI opens your browser automatically"),
            ("3️⃣", "AI navigates & searches for you"),
            ("4️⃣", "AI clicks the best result link"),
            ("5️⃣", "AI reads the page & reports back"),
        ]
        for icon, step in steps:
            row = tk.Frame(inner, bg=CARD2)
            row.pack(fill="x", padx=12, pady=1)
            tk.Label(row, text=icon, font=("Segoe UI", 10), bg=CARD2).pack(side="left")
            tk.Label(row, text=" " + step, font=("Segoe UI", 9), bg=CARD2, fg=MUTED,
                     justify="left", wraplength=200).pack(side="left")

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", padx=12, pady=8)

        # Capabilities
        tk.Label(inner, text="✅  Capabilities",
                 font=("Segoe UI", 10, "bold"), bg=CARD2, fg=SUCCESS).pack(anchor="w", **pad)
        caps = [
            "Search any topic on the web",
            "Open & read websites",
            "Find prices on Amazon",
            "Watch videos on YouTube",
            "Look up Wikipedia articles",
            "Open any URL you mention",
            "Scroll, click links, fill forms",
            "Works FREE — no API key needed",
        ]
        for c in caps:
            tk.Label(inner, text="  ✓  " + c, font=("Segoe UI", 9),
                     bg=CARD2, fg="#6ee7b7", anchor="w").pack(anchor="w", padx=12)

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", padx=12, pady=8)

        # Command examples by category
        for category, examples in EXAMPLES.items():
            # Category header
            cat_frame = tk.Frame(inner, bg=CARD, pady=4)
            cat_frame.pack(fill="x", padx=12, pady=(4, 1))
            tk.Label(cat_frame, text=category, font=("Segoe UI", 9, "bold"),
                     bg=CARD, fg=TEXT, padx=8).pack(anchor="w")

            for label, cmd in examples:
                btn_frame = tk.Frame(inner, bg=CARD2, cursor="hand2")
                btn_frame.pack(fill="x", padx=12, pady=1)

                def make_click(c=cmd):
                    return lambda e: self._set_prompt(c)

                lbl = tk.Label(btn_frame, text=f"  › {label}",
                               font=("Segoe UI", 9), bg=CARD2, fg="#93c5fd",
                               anchor="w", cursor="hand2", padx=4, pady=3)
                lbl.pack(side="left", fill="x", expand=True)
                lbl.bind("<Button-1>", make_click())
                lbl.bind("<Enter>", lambda e, w=lbl: w.config(bg="#1e3a5f", fg="white"))
                lbl.bind("<Leave>", lambda e, w=lbl: w.config(bg=CARD2, fg="#93c5fd"))

        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", padx=12, pady=8)

        # Tips section
        tk.Label(inner, text="💡  Tips",
                 font=("Segoe UI", 10, "bold"), bg=CARD2, fg=WARN).pack(anchor="w", **pad)
        tips = [
            "Be specific — 'latest Python news 2024' works better than just 'Python'",
            "Mention the site — 'on Amazon', 'on YouTube', 'on Wikipedia'",
            "Press Enter or click 🚀 Run to start",
            "Press 🛑 Stop anytime to cancel",
            "AI mode 'free' works without any API key",
        ]
        for tip in tips:
            row = tk.Frame(inner, bg=CARD2)
            row.pack(fill="x", padx=12, pady=2)
            tk.Label(row, text="💡", font=("Segoe UI", 9), bg=CARD2).pack(side="left")
            tk.Label(row, text=" " + tip, font=("Segoe UI", 8), bg=CARD2,
                     fg=MUTED, justify="left", wraplength=210).pack(side="left")

        tk.Frame(inner, bg=CARD2, height=20).pack()  # bottom padding

    # ── Helper: welcome message in log ────────────────────────────────
    def _show_welcome(self):
        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "  🤖  AI Browser Agent — Ready!",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            "  TWO MODES:",
            "  🤖 Groq AI Mode  (RECOMMENDED — smarter & more accurate)",
            "     → Paste your FREE Groq key from console.groq.com/keys",
            "     → Groq reads your command and plans every browser step",
            "     → Then AI executes the plan in your real browser",
            "",
            "  🧠 Built-in Mode  (no key needed — works offline)",
            "     → Built-in intelligence handles common tasks",
            "",
            "  EXAMPLE COMMANDS you can try:",
            "    • Find the latest cricket score today",
            "    • Show me iPhone 15 price on Amazon",
            "    • Open YouTube and search for lo-fi music",
            "    • Search Wikipedia for Albert Einstein",
            "    • What is machine learning?",
            "    • Find cheap flights from Delhi to Mumbai",
            "    • Tell me about the Eiffel Tower",
            "",
            "  💡 Get FREE Groq key → console.groq.com/keys",
            "  📖 Click 'Help / Examples' button for more →",
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]
        for line in lines:
            self._log(line, "dim" if line.startswith("━") else None)

    # ── Event handlers ────────────────────────────────────────────────
    def _toggle_help(self):
        """Show or hide the right help panel."""
        panes = self.root_pane.panes()
        if self.help_panel in [self.root_pane.nametowidget(p) for p in panes]:
            self.root_pane.forget(self.help_panel)
        else:
            self.root_pane.add(self.help_panel, minsize=260)

    def _open_memory_window(self):
        mem = get_memory()
        stats = mem.stats()

        win = tk.Toplevel(self)
        win.title("🧠 AI Memory & History")
        win.geometry("700x530")
        win.minsize(600, 420)
        win.configure(bg=BG)

        # Header
        hdr = tk.Frame(win, bg=BG, padx=14, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🧠 Persistent AI Memory", font=("Segoe UI", 14, "bold"), bg=BG, fg=TEXT).pack(anchor="w")
        tk.Label(hdr, text=f"Remembered: {stats['total_pages']} Webpages  •  {stats['total_tasks']} Completed Tasks  •  {stats['total_facts']} Learned Facts",
                 font=("Segoe UI", 9), bg=BG, fg=TEAL).pack(anchor="w")

        # Tabs for Pages, Tasks and Facts
        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=14, pady=6)

        # Tab 1: Visited Webpages
        pages_frame = tk.Frame(notebook, bg=CARD, padx=8, pady=8)
        notebook.add(pages_frame, text="🌐 Visited Webpages")

        pages_tree = ttk.Treeview(pages_frame, columns=("title", "url", "visits", "last_visited"), show="headings", height=12)
        pages_tree.heading("title", text="Page Title")
        pages_tree.heading("url", text="URL")
        pages_tree.heading("visits", text="Visits")
        pages_tree.heading("last_visited", text="Last Visited")

        pages_tree.column("title", width=220)
        pages_tree.column("url", width=250)
        pages_tree.column("visits", width=55, anchor="center")
        pages_tree.column("last_visited", width=120)
        pages_tree.pack(fill="both", expand=True, side="left")

        sb1 = ttk.Scrollbar(pages_frame, orient="vertical", command=pages_tree.yview)
        sb1.pack(side="right", fill="y")
        pages_tree.configure(yscrollcommand=sb1.set)

        for p in mem._data.get("pages", {}).values():
            pages_tree.insert("", "end", values=(
                p.get("title", "Untitled"),
                p.get("url", ""),
                p.get("visit_count", 1),
                p.get("last_visited", "")[:16].replace("T", " ")
            ))

        # Tab 2: Task History & Operations Trace
        tasks_frame = tk.Frame(notebook, bg=CARD, padx=8, pady=8)
        notebook.add(tasks_frame, text="📋 Task History & Operations")

        tasks_txt = scrolledtext.ScrolledText(tasks_frame, bg="#060d1a", fg=TEXT, font=("Consolas", 9), padx=8, pady=8, wrap="word")
        tasks_txt.pack(fill="both", expand=True)

        for t in mem.all_tasks():
            ts = t.get('timestamp','')[:16].replace("T", " ")
            tasks_txt.insert(tk.END, f"━" * 60 + "\n", "sep")
            tasks_txt.insert(tk.END, f"[{ts}] COMMAND: {t.get('command','')}\n", "cmd")

            journey = " -> ".join(t.get("platform_journey", []))
            if journey:
                tasks_txt.insert(tk.END, f"   🌐 Platform Journey: {journey}\n", "journey")

            ck = t.get("cookies_info", {})
            if ck and ck.get("count", 0) > 0:
                domains = ", ".join(ck.get("domains", []))
                tasks_txt.insert(tk.END, f"   🍪 Cookies Saved: {ck['count']} cookies ({domains})\n", "cookie")

            lp = t.get("last_page", {})
            if lp and lp.get("title"):
                tasks_txt.insert(tk.END, f"   📍 Last Active Page: {lp.get('title')} ({lp.get('url','')[:60]})\n", "page")

            steps = t.get("step_trace", [])
            if steps:
                tasks_txt.insert(tk.END, "   ⚡ Operations Performed:\n", "step_head")
                for s in steps:
                    act = s.get("action", "").upper()
                    desc = s.get("description", "")
                    p_name = s.get("platform", "")
                    plat_label = f" [{p_name}]" if p_name else ""
                    tasks_txt.insert(tk.END, f"      Step {s.get('step','?')}{plat_label}: {act} — {desc}\n", "step")

            tasks_txt.insert(tk.END, f"\n   🎯 RESULT:\n   {t.get('result','')}\n\n", "res")

        tasks_txt.tag_config("sep", foreground="#334155")
        tasks_txt.tag_config("cmd", foreground="#60a5fa", font=("Consolas", 9, "bold"))
        tasks_txt.tag_config("journey", foreground="#f59e0b", font=("Consolas", 9, "bold"))
        tasks_txt.tag_config("cookie", foreground="#14b8a6")
        tasks_txt.tag_config("page", foreground="#a78bfa")
        tasks_txt.tag_config("step_head", foreground="#94a3b8", font=("Consolas", 8, "bold"))
        tasks_txt.tag_config("step", foreground="#cbd5e1", font=("Consolas", 8))
        tasks_txt.tag_config("res", foreground="#34d399")
        tasks_txt.configure(state="disabled")

        # Tab 3: Learned Facts
        facts_frame = tk.Frame(notebook, bg=CARD, padx=8, pady=8)
        notebook.add(facts_frame, text="💡 Learned Facts")

        facts_txt = scrolledtext.ScrolledText(facts_frame, bg="#060d1a", fg="#fde047", font=("Consolas", 9), padx=8, pady=8, wrap="word")
        facts_txt.pack(fill="both", expand=True)
        for f in mem._data.get("facts", []):
            facts_txt.insert(tk.END, f"• {f}\n\n")
        facts_txt.configure(state="disabled")

        # Bottom actions
        bbar = tk.Frame(win, bg=BG, padx=14, pady=8)
        bbar.pack(fill="x")

        def load_selected_page():
            sel = pages_tree.selection()
            if sel:
                item = pages_tree.item(sel[0])
                url = item["values"][1]
                self._set_prompt(f"open {url}")
                win.destroy()

        tk.Button(bbar, text="🌐 Open Selected Page", font=("Segoe UI", 9, "bold"), bg=PRIMARY, fg="white", bd=0, padx=10, pady=4, command=load_selected_page).pack(side="left", padx=(0, 6))

        def resume_last():
            last = mem.get_last_session()
            if last and last.get("last_page", {}).get("url"):
                url = last["last_page"]["url"]
                self._set_prompt(f"continue from {url}")
                win.destroy()
            elif last:
                self._set_prompt(f"repeat: {last.get('command','')}")
                win.destroy()
            else:
                messagebox.showinfo("No History", "No previous session found to resume.")

        tk.Button(bbar, text="🔄 Resume Last Session", font=("Segoe UI", 9, "bold"), bg=TEAL, fg="white", bd=0, padx=10, pady=4, command=resume_last).pack(side="left")

        def clear_mem():
            if messagebox.askyesno("Clear Memory", "Are you sure you want to clear all memorized pages, tasks, and facts?"):
                mem.clear()
                win.destroy()
                self._log("🧠 Memory has been reset.", "dim")

        tk.Button(bbar, text="🗑 Clear Memory", font=("Segoe UI", 8), bg=BORDER, fg=MUTED, bd=0, padx=8, pady=4, command=clear_mem).pack(side="right")

    def _toggle_key(self):
        current = self.api_key_entry.cget("show")
        self.api_key_entry.config(show="" if current == "•" else "•")

    def _save_settings(self, show_dialog: bool = False):
        self.config_data["gemini_api_key"] = self.api_key_entry.get().strip()
        self.config_data["groq_api_key"]   = self.groq_key_entry.get().strip()
        self.config_data["groq_model"]     = self.groq_model_var.get()
        self.config_data["browser"]        = self.browser_var.get()
        save_config(self.config_data)
        if show_dialog:
            messagebox.showinfo("Saved ✅", "Settings saved successfully!")

    def _set_prompt(self, text: str):
        self.cmd_text.delete("1.0", tk.END)
        self.cmd_text.insert("1.0", text)
        self.cmd_text.focus_set()

    def _clear_log(self):
        self.log_area.configure(state="normal")
        self.log_area.delete("1.0", tk.END)
        self.log_area.configure(state="disabled")

    def _log(self, message: str, tag: str = None, thought: str = ""):
        self.log_area.configure(state="normal")
        ts = __import__("datetime").datetime.now().strftime("%H:%M:%S")
        prefix = f"[{ts}] " if tag not in ("dim", None) else ""
        full = prefix + message + "\n"
        self.log_area.insert(tk.END, full, tag or "")
        if thought:
            self.log_area.insert(tk.END, f"         ↳ {thought}\n", "thought")
        self.log_area.see(tk.END)
        self.log_area.configure(state="disabled")

    def _set_running_state(self, is_running: bool):
        if is_running:
            self.status_pill.config(text="● RUNNING", bg="#1e3a6e", fg="#60a5fa")
            self.run_btn.config(state="disabled", bg="#475569",
                                text="⏳  Running — AI is controlling your browser...")
            self.stop_btn.config(state="normal", bg=DANGER, fg="white")
        else:
            self.status_pill.config(text="● IDLE", bg=BORDER, fg=MUTED)
            self.run_btn.config(state="normal", bg=PRIMARY,
                                text="🚀  Run — AI Opens Your Browser & Fulfills This Command")
            self.stop_btn.config(state="disabled", bg=BORDER, fg=MUTED)

    def _start_task(self):
        task = self.cmd_text.get("1.0", tk.END).strip()
        if not task:
            messagebox.showwarning("Empty Command",
                                   "Please type a command!\n\nExample:\n  Find the latest AI news")
            return

        self._save_settings(show_dialog=False)
        groq_key   = self.groq_key_entry.get().strip()
        groq_model = self.groq_model_var.get()
        api_key    = self.api_key_entry.get().strip()

        self._clear_log()
        self._set_running_state(True)

        if groq_key:
            self._log(f"🤖 Groq AI ({groq_model}) will plan your task:", "head")
        else:
            self._log("🧠 Built-in Intelligence mode (no API key):", "head")
        self._log(f"   Command: {task}", "dim")
        self._log(f"   Browser: {self.browser_var.get()}", "dim")
        self._log("", None)

        self.worker_thread = threading.Thread(
            target=self._run_thread,
            args=(api_key, groq_key, groq_model, task),
            daemon=True
        )
        self.worker_thread.start()

    def _run_thread(self, api_key: str, groq_key: str, groq_model: str, task: str):
        self.agent = BrowserAgent(
            api_key=api_key,
            groq_api_key=groq_key,
            groq_model=groq_model,
            browser_type=self.browser_var.get()
        )

        def callback(action: str, msg: str, thought: str = ""):
            if action in ("done", "groq"):
                tag = "ok"
            elif action in ("error", "fail"):
                tag = "err"
            elif action in ("navigate", "head"):
                tag = "head"
            else:
                tag = None
            self.after(0, self._log, msg, tag, thought)

        try:
            result = self.agent.run_task(task, log_callback=callback)
            if result.get("success"):
                final = result.get("result", "")
                self.after(0, self._log, "\n" + "─" * 55, "dim")
                self.after(0, self._log, "🎯  RESULT:", "ok")
                self.after(0, self._log, final, "result")
                self.after(0, self._log, "─" * 55, "dim")
            else:
                err = result.get("error", "Unknown error")
                self.after(0, self._log, f"❌ Failed: {err}", "err")
        except Exception as e:
            self.after(0, self._log, f"❌ Error: {e}", "err")
        finally:
            self.after(0, self._set_running_state, False)

    def _stop_task(self):
        if self.agent:
            self.agent.stop()
        self._log("🛑 Stop requested — finishing current action...", "err")


# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = ModernApp()
    app.mainloop()
