"""
browser_agent.py  —  AI Browser Agent
  • If a Groq API key is set: Groq LLM plans every step, Playwright executes them.
  • If no key: built-in autonomous heuristics handle everything locally.
  • Persistent memory: remembers every page, task and fact across sessions.
No external dependencies beyond playwright and the standard library.
"""

import sys
sys.dont_write_bytecode = True

import json
import os
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Callable, Dict, Any, List, Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from memory import get_memory


# ══════════════════════════════════════════════════════════════════════
#  Config helpers
# ══════════════════════════════════════════════════════════════════════
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULTS: Dict[str, Any] = {
    "groq_api_key":  "",
    "groq_model":    "llama3-8b-8192",
    "gemini_api_key": "",
    "browser":       "chrome",
    "max_steps":     15,
    "step_delay":    1.2,
}


def load_config() -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(config: Dict[str, Any]) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Config save error: {e}")


# ══════════════════════════════════════════════════════════════════════
#  Groq Planner  —  LLM generates the browser plan
# ══════════════════════════════════════════════════════════════════════
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

GROQ_SYSTEM_PROMPT = """You are an expert browser automation AI.
Your job is to create a precise step-by-step browser plan to fulfill a user's command.

You MUST respond with ONLY valid JSON (no markdown, no explanation, just JSON).
Use this exact structure:

{
  "plan_summary": "One sentence: what you will do",
  "steps": [
    {
      "step": 1,
      "action": "navigate",
      "url": "https://...",
      "description": "Why this step"
    }
  ]
}

AVAILABLE ACTIONS (use exactly these names):
  navigate          → go to a URL            (needs: "url")
  search            → type in search box     (needs: "query")
  click_top_result  → click first result     (no extra fields)
  click_element     → click by text          (needs: "text")
  scroll_down       → scroll page down       (optional: "amount" pixels)
  read_page         → read & summarize page  (no extra fields)
  wait              → pause briefly          (optional: "seconds")

RULES:
- For web searches: use navigate to bing.com, then search action.
- For Amazon: navigate to amazon.com, then search.
- For YouTube: navigate to youtube.com, then search.
- For Wikipedia: navigate to wikipedia.org, then search.
- Always end with read_page if the goal is to get information.
- Use at most 6 steps. Keep it simple and direct.
- Never use Google (it blocks bots). Use Bing for general search.
"""


def call_groq(api_key: str, model: str, task: str,
              log_fn: Optional[Callable] = None,
              memory_context: str = "") -> Optional[Dict[str, Any]]:
    """
    Call Groq API to generate a browser plan with past session memory.
    Returns parsed plan dict or None on failure.
    """
    if log_fn:
        log_fn("groq", "Groq AI", f"Asking {model} to plan your task...")

    prompt = f'User command: "{task}"'
    if memory_context:
        prompt += f"\n\n{memory_context}\n(Use the remembered pages/history above if the user is referring to them or asking to re-visit them.)"
    prompt += '\n\nGenerate the browser automation plan as JSON.'

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": GROQ_SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens":  800,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")

    req = urllib.request.Request(
        GROQ_ENDPOINT,
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw  = data["choices"][0]["message"]["content"]
            plan = json.loads(raw)
            if log_fn:
                log_fn("groq", "Groq Plan Ready",
                       f"📋 {plan.get('plan_summary', 'Plan generated')} "
                       f"({len(plan.get('steps', []))} steps)")
            return plan
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        if log_fn:
            log_fn("error", "Groq Error", f"HTTP {e.code}: {body[:200]}")
        return None
    except Exception as e:
        if log_fn:
            log_fn("error", "Groq Error", str(e))
        return None


# ══════════════════════════════════════════════════════════════════════
#  Fallback: Built-in Autonomous Heuristic Engine
# ══════════════════════════════════════════════════════════════════════
class AutonomousIntelligenceEngine:
    """
    Local heuristic engine — used when no Groq API key is set.
    Parses intent and drives the browser step by step.
    """

    PLATFORM_URLS = {
        "youtube":       "https://www.youtube.com",
        "amazon":        "https://www.amazon.com",
        "wikipedia":     "https://www.wikipedia.org",
        "github":        "https://www.github.com",
        "reddit":        "https://www.reddit.com",
        "twitter":       "https://www.x.com",
        "instagram":     "https://www.instagram.com",
        "facebook":      "https://www.facebook.com",
        "netflix":       "https://www.netflix.com",
        "linkedin":      "https://www.linkedin.com",
        "stackoverflow": "https://stackoverflow.com",
        "flipkart":      "https://www.flipkart.com",
        "google":        "https://www.bing.com",
        "bing":          "https://www.bing.com",
    }

    SEARCH_PAGE_PATTERNS = [
        "bing.com/search", "google.com/search", "/search?", "/search/?",
        "amazon.com/s?", "amazon.com/s/", "youtube.com/results",
        "wikipedia.org/w/index.php?search=", "reddit.com/search",
        "github.com/search", "flipkart.com/search",
    ]

    SKIP_RESULT_TERMS = [
        "sign in", "log in", "login", "settings", "privacy", "terms",
        "feedback", "help", "google apps", "cache", "translate",
        "sponsored", " ad ", "advertisement", "javascript:", "#",
        "bing.com", "google.com", "microsoft.com/en-us/bing",
    ]

    def __init__(self, task: str):
        self.raw_task = task.strip()
        self.intent_data = self._analyze_intent(self.raw_task)
        self.has_clicked_result = False

    def _analyze_intent(self, task: str) -> Dict[str, Any]:
        t = task.lower()

        url_m = re.search(
            r'(?<![/@])\b(https?://[^\s]+|www\.[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?)\b',
            task, re.I)
        direct_url = None
        if url_m:
            u = url_m.group(1)
            direct_url = u if u.startswith("http") else f"https://{u}"

        intent_type = "search_and_open"
        if direct_url and re.search(r'\b(go to|open|visit|navigate to)\b', t):
            intent_type = "direct_navigation"
        elif re.search(r'\b(summarize|summary|read this page|explain this page)\b', t):
            intent_type = "summarize"
        elif re.search(r'\b(scroll down|scroll up)\b', t):
            intent_type = "scroll"
        elif re.search(r'\b(click|press|tap)\b', t) and not re.search(r'\b(search|find)\b', t):
            intent_type = "click_target"

        target_platform, nav_target = None, "https://www.bing.com"
        for name, url in self.PLATFORM_URLS.items():
            if re.search(r'\b' + re.escape(name) + r'\b', t):
                target_platform, nav_target = name, url
                break

        if direct_url and intent_type == "direct_navigation":
            nav_target = direct_url

        # Check memory: if user asks to continue, resume, or return to earlier session/page
        mem = get_memory()
        last_session = mem.get_last_session()
        is_resume_cmd = any(w in t for w in [
            "continue", "go back", "back to that", "resume", "repeat", "do it again",
            "last page", "previous page", "that site", "last site", "last time", "again",
            "redo", "from where we left"
        ])
        if is_resume_cmd and last_session and last_session.get("last_page", {}).get("url"):
            lp = last_session["last_page"]
            direct_url = lp["url"]
            nav_target = direct_url
            intent_type = "direct_navigation"
        else:
            matched = mem.search_pages(task, n=1)
            if matched and any(w in t for w in ["again", "earlier", "before", "remember", "previous", "that site", "that page"]):
                direct_url = matched[0]["url"]
                nav_target = direct_url
                intent_type = "direct_navigation"

        clean_query = self._extract_query(task, target_platform)
        return {
            "intent_type": intent_type, "target_platform": target_platform,
            "nav_target": nav_target, "clean_query": clean_query, "direct_url": direct_url,
        }

    def _extract_query(self, task: str, platform: Optional[str]) -> str:
        q = task
        for _ in range(3):
            prev = q
            q = re.sub(
                r'^(please\s+)?(can you\s+)?'
                r'(go to|open|visit|navigate to|search for|search|look for|'
                r'find|look up|google|check|show me|tell me about|tell me|'
                r'what is|who is|how to|get me|show)\s+',
                '', q, flags=re.I).strip()
            q = re.sub(
                r'^(youtube|amazon|wikipedia|github|reddit|twitter|instagram|'
                r'facebook|linkedin|flipkart|stackoverflow|bing|google)\s+'
                r'(and\s+)?(search\s+for|search|look\s+for|find|look\s+up)?\s*',
                '', q, flags=re.I).strip()
            if q == prev:
                break
        q = re.sub(
            r'\s+(on|using|via|in|at|from|with)\s+'
            r'(google|bing|youtube|amazon|wikipedia|github|reddit|twitter|'
            r'instagram|facebook|linkedin|flipkart|stackoverflow)\s*$',
            '', q, flags=re.I).strip()
        q = re.sub(r'^(the|a|an)\s+', '', q, flags=re.I).strip()
        q = re.sub(r'\s+(for me|please|now|today)\s*$', '', q, flags=re.I).strip()
        return q if q else task

    def decide_next_step(self, dom_data: Dict[str, Any],
                         history: List[Dict[str, Any]], step: int) -> Dict[str, Any]:
        url        = (dom_data.get("url") or "").lower()
        title      = dom_data.get("title") or ""
        excerpt    = dom_data.get("textExcerpt") or ""
        elements   = dom_data.get("elements") or []
        top_result = dom_data.get("topSearchResult") or {}
        intent     = self.intent_data
        query      = intent["clean_query"] or self.raw_task
        nav_target = intent["nav_target"]

        is_search_page  = any(p in url for p in self.SEARCH_PAGE_PATTERNS)
        is_on_known_site = any(p in url for p in [
            "bing.com", "google.com", "youtube.com", "amazon.com",
            "wikipedia.org", "github.com", "reddit.com", "x.com",
            "twitter.com", "instagram.com", "facebook.com",
            "netflix.com", "linkedin.com", "stackoverflow.com", "flipkart.com",
        ])

        if intent["intent_type"] == "summarize" and excerpt:
            return {"action": "done", "thought": "Summarized.",
                    "summary": self._make_summary(title, excerpt, dom_data.get("url"))}

        if intent["intent_type"] == "scroll":
            d = "up" if "up" in self.raw_task.lower() else "down"
            return {"action": "scroll", "direction": d, "amount": 700, "thought": f"Scrolling {d}."}

        if intent["intent_type"] == "direct_navigation" and intent["direct_url"]:
            if intent["direct_url"].lower() not in url:
                return {"action": "navigate", "url": intent["direct_url"],
                        "thought": f"Navigating to {intent['direct_url']}."}
            if excerpt:
                return {"action": "done", "thought": "Reached destination.",
                        "summary": self._make_summary(title, excerpt, dom_data.get("url"))}

        if not is_on_known_site:
            return {"action": "navigate", "url": nav_target,
                    "thought": f"Opening {nav_target} to search for '{query}'."}

        if not is_search_page and not self.has_clicked_result:
            sid = self._find_search_input(elements)
            if sid:
                return {"action": "type", "elementId": sid, "text": query,
                        "pressEnter": True, "thought": f"Typing '{query}'."}
            return {"action": "scroll", "direction": "up", "amount": 400,
                    "thought": "Looking for search box."}

        if is_search_page and not self.has_clicked_result:
            if top_result and top_result.get("href"):
                self.has_clicked_result = True
                return {"action": "click", "elementId": top_result.get("elementId"),
                        "href": top_result["href"],
                        "thought": f"Clicking: '{top_result.get('title', '')}'"}
            fb = self._find_best_result_link(elements)
            if fb:
                self.has_clicked_result = True
                return {"action": "click", "elementId": fb["elementId"],
                        "href": fb.get("href"), "thought": f"Clicking: '{fb['title']}'"}
            return {"action": "scroll", "direction": "down", "amount": 500,
                    "thought": "Scrolling to find result links."}

        if self.has_clicked_result and not is_search_page and excerpt:
            return {"action": "done", "thought": f"Opened '{title}'.",
                    "summary": self._make_summary(title, excerpt, dom_data.get("url"))}

        if step >= 8 and excerpt:
            return {"action": "done", "thought": "Step limit.",
                    "summary": self._make_summary(title, excerpt, dom_data.get("url"))}

        return {"action": "scroll", "direction": "down", "amount": 600, "thought": "Loading..."}

    def _find_search_input(self, elements):
        priority = ['name="q"', 'name="query"', 'name="search_query"', 'type="search"',
                    'placeholder="search', 'aria-label="search', 'searchbox']
        for el in elements:
            m = re.match(r"\[(\d+)\]", el)
            if m and ("<input" in el.lower() or "<textarea" in el.lower()):
                if any(k in el.lower() for k in priority):
                    return int(m.group(1))
        for el in elements:
            m = re.match(r"\[(\d+)\]", el)
            if m and "<input" in el.lower() and re.search(r'type="(text|search|)"', el.lower()):
                return int(m.group(1))
        return None

    def _find_best_result_link(self, elements):
        for el in elements:
            if not re.match(r"\[\d+\]\s*<a", el, re.I):
                continue
            m = re.match(r"\[(\d+)\]", el)
            if not m:
                continue
            hm = re.search(r'href="([^"]+)"', el, re.I)
            if not hm:
                continue
            href = hm.group(1)
            if not href.startswith("http"):
                continue
            if any(s in el.lower() for s in self.SKIP_RESULT_TERMS):
                continue
            if any(d in href.lower() for d in ["bing.com", "google.com", "microsoft.com/en-us/bing"]):
                continue
            tm = re.search(r'>([^<]{4,})</', el)
            return {"elementId": int(m.group(1)), "title": tm.group(1).strip() if tm else href, "href": href}
        return None

    def _make_summary(self, title, text, url):
        clean = re.sub(r'\s+', ' ', (text or "")).strip()
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', clean) if len(s.strip()) > 20]
        body = "\n• " + "\n• ".join(sentences[:7]) if sentences else clean[:700]
        return f"📌 Page: {title}\n🌐 URL:  {url}\n\n📝 Key Findings:\n{body}\n"


# ══════════════════════════════════════════════════════════════════════
#  BrowserAgent  —  Playwright controller
# ══════════════════════════════════════════════════════════════════════
class BrowserAgent:
    """
    Main agent class.
    1. If Groq key is set → asks Groq to plan → executes plan in browser.
    2. Otherwise         → uses AutonomousIntelligenceEngine locally.
    """

    def __init__(self, api_key: str = "", groq_api_key: str = "",
                 groq_model: str = "llama3-8b-8192",
                 model: str = "free", browser_type: str = "chrome"):
        self.api_key      = (api_key or "").strip()
        self.groq_api_key = (groq_api_key or "").strip()
        self.groq_model   = groq_model or "llama3-8b-8192"
        self.model        = model or "free"
        self.browser_type = browser_type or "chrome"
        self.max_steps    = 15
        self.step_delay   = 1.0

        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_running     = False
        self.stop_requested = False

    # ── Browser lifecycle ──────────────────────────────────────────────
    def start_browser(self):
        if self.page and not self.page.is_closed():
            return
        self.playwright = sync_playwright().start()
        channel = self.browser_type if self.browser_type in ["chrome", "msedge"] else "chrome"
        profile_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "browser_profile"))
        os.makedirs(profile_dir, exist_ok=True)

        try:
            # Persistent context retains logins, cookies, history and cache across runs
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                channel=channel,
                headless=False,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
            )
        except Exception as e:
            print(f"Could not launch persistent {channel}: {e} — using bundled Chromium with profile.")
            try:
                self.context = self.playwright.chromium.launch_persistent_context(
                    user_data_dir=profile_dir,
                    headless=False,
                    args=["--start-maximized"]
                )
            except Exception:
                self.browser = self.playwright.chromium.launch(headless=False, args=["--start-maximized"])
                self.context = self.browser.new_context(no_viewport=True)

        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def _save_browser_state(self) -> Dict[str, Any]:
        """Saves cookies and session storage state to disk and returns a summary."""
        cookies_summary = {"count": 0, "domains": []}
        try:
            if self.context:
                profile_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "browser_profile"))
                os.makedirs(profile_dir, exist_ok=True)
                storage_file = os.path.join(profile_dir, "storage_state.json")
                self.context.storage_state(path=storage_file)
                cookies = self.context.cookies()
                domains = list({c.get("domain", "").lstrip(".") for c in cookies if c.get("domain")})
                cookies_summary = {"count": len(cookies), "domains": sorted(domains)[:10]}
        except Exception:
            pass
        return cookies_summary

    def close_browser(self):
        try:
            self._save_browser_state()
        except Exception:
            pass
        for attr in ["page", "context", "browser"]:
            obj = getattr(self, attr, None)
            if obj:
                try: obj.close()
                except Exception: pass
                setattr(self, attr, None)
        if self.playwright:
            try: self.playwright.stop()
            except Exception: pass
            self.playwright = None
        self.is_running = False

    def stop(self):
        self.stop_requested = True
        self.is_running     = False

    # ── Main entry point ───────────────────────────────────────────────
    def run_task(self, task: str,
                 log_callback: Optional[Callable[[str, str, str], None]] = None
                 ) -> Dict[str, Any]:

        def emit(action: str, title: str, message: str, thought: str = ""):
            if log_callback:
                log_callback(action, f"{title}: {message}", thought)
            else:
                print(f"[{title}] {message}")

        self.is_running     = True
        self.stop_requested = False
        mem = get_memory()
        visited_pages: List[Dict[str, str]] = []
        platform_journey: List[str] = []
        step_trace: List[Dict[str, Any]] = []

        def track_platform(url_str: str):
            if not url_str or url_str.startswith("about:"):
                return
            m = re.search(r'https?://(?:www\.)?([a-zA-Z0-9\-]+)\.', url_str)
            p_name = m.group(1).lower() if m else "web"
            if not platform_journey or platform_journey[-1] != p_name:
                platform_journey.append(p_name)

        try:
            # Show memory hint if related past operations / pages exist
            mem_hint = mem.build_context_for_heuristic(task)
            if mem_hint:
                emit("status", "Memory Recall", mem_hint)

            # ── STEP 1: Plan with Groq (if key set) ───────────────────
            if self.groq_api_key:
                emit("status", "AI Planner", "🤖 Groq AI is reading your command + operation memory...")
                mem_context = mem.build_context_for_groq(task)
                plan = call_groq(self.groq_api_key, self.groq_model, task, emit, memory_context=mem_context)
                if plan and plan.get("steps"):
                    emit("status", "Starting Browser",
                         f"Launching {self.browser_type.title()} (persistent cookies & sessions active)...")
                    self.start_browser()
                    result = self._execute_groq_plan(plan, task, emit, mem, visited_pages, platform_journey, step_trace, track_platform)
                    cookies_info = self._save_browser_state()
                    last_dom = self._extract_dom_state()
                    last_page = {"url": last_dom.get("url", ""), "title": last_dom.get("title", "")}
                    mem.record_task(task, result.get("result", ""), visited_pages, step_trace, platform_journey, cookies_info, last_page)
                    return result
                else:
                    emit("status", "Groq Fallback",
                         "⚠️ Groq planning failed — using built-in intelligence.")

            # ── STEP 2: Fallback to built-in heuristic engine ─────────
            emit("status", "Built-in AI",
                 "🧠 Using autonomous intelligence (with session memory)...")
            engine  = AutonomousIntelligenceEngine(task)
            intent  = engine.intent_data
            emit("status", "Plan",
                 f"Intent='{intent['intent_type']}' | "
                 f"Query='{intent['clean_query']}' | "
                 f"Target='{intent['nav_target']}'")

            self.start_browser()
            emit("navigate", "Opening", intent["nav_target"])
            track_platform(intent["nav_target"])
            self.page.goto(intent["nav_target"], wait_until="domcontentloaded", timeout=20000)
            time.sleep(1.5)
            result = self._heuristic_loop(engine, task, emit, mem, visited_pages, platform_journey, step_trace, track_platform)
            cookies_info = self._save_browser_state()
            last_dom = self._extract_dom_state()
            last_page = {"url": last_dom.get("url", ""), "title": last_dom.get("title", "")}
            mem.record_task(task, result.get("result", ""), visited_pages, step_trace, platform_journey, cookies_info, last_page)
            return result

        except Exception as e:
            emit("error", "Fatal Error", str(e))
            return {"success": False, "error": str(e)}
        finally:
            self.is_running = False

    # ══════════════════════════════════════════════════════════════════
    #  Groq plan execution
    # ══════════════════════════════════════════════════════════════════
    def _execute_groq_plan(self, plan: Dict[str, Any], task: str,
                           emit: Callable, mem: Any, visited_pages: List[Dict[str, str]],
                           platform_journey: List[str], step_trace: List[Dict[str, Any]],
                           track_platform: Callable) -> Dict[str, Any]:
        steps  = plan.get("steps", [])
        summary_text = plan.get("plan_summary", "")
        history: List[Dict] = []

        emit("status", "Plan", f"📋 {summary_text}")
        for s in steps:
            emit("status", f"Step {s['step']}/{len(steps)}",
                 f"[{s['action'].upper()}] {s.get('description','')}")

        for s in steps:
            if self.stop_requested:
                return {"success": False, "status": "stopped"}

            action = s.get("action", "")
            desc   = s.get("description", "")
            step_n = s.get("step", "?")

            emit("status", f"▶ Step {step_n}", f"{action.upper()} — {desc}")

            result = self._run_groq_step(s, emit)
            history.append({"step": step_n, "action": action, "result": result})

            # Check and record page in memory & track platform
            dom = self._extract_dom_state()
            p_url = dom.get("url", "")
            p_title = dom.get("title", "")
            p_excerpt = dom.get("textExcerpt", "")
            if p_url and not p_url.startswith("about:"):
                track_platform(p_url)
                mem.record_page(p_url, p_title, p_excerpt)
                if not any(v.get("url") == p_url for v in visited_pages):
                    visited_pages.append({"url": p_url, "title": p_title})

            step_trace.append({
                "step": step_n,
                "action": action,
                "description": desc,
                "url": p_url,
                "platform": platform_journey[-1] if platform_journey else ""
            })

            if result.get("done"):
                final = result.get("summary", "Task completed.")
                emit("done", "✅ Done", final)
                return {"success": True, "result": final, "history": history}

            time.sleep(self.step_delay)

        # After all steps, read the current page
        emit("status", "Reading Page", "Extracting final page content...")
        dom = self._extract_dom_state()
        summary = self._make_summary(
            dom.get("title", ""),
            dom.get("textExcerpt", "No content found."),
            dom.get("url", "")
        )
        if dom.get("url") and not dom.get("url").startswith("about:"):
            track_platform(dom.get("url"))
            mem.record_page(dom.get("url"), dom.get("title", ""), summary)
            if not any(v.get("url") == dom.get("url") for v in visited_pages):
                visited_pages.append({"url": dom.get("url"), "title": dom.get("title", "")})

        emit("done", "✅ Completed", summary)
        return {"success": True, "result": summary, "history": history}

    def _run_groq_step(self, step: Dict[str, Any], emit: Callable) -> Dict[str, Any]:
        """Execute a single Groq-planned step. Returns {"done": bool, "summary": str}."""
        action  = step.get("action", "")
        dom     = self._extract_dom_state()
        url     = dom.get("url", "")
        title   = dom.get("title", "")
        excerpt = dom.get("textExcerpt", "")
        elements = dom.get("elements", [])
        top_result = dom.get("topSearchResult") or {}

        # ── navigate ──────────────────────────────────────────────────
        if action == "navigate":
            nav_url = step.get("url", "")
            emit("navigate", "Navigate", f"→ {nav_url}")
            try:
                self.page.goto(nav_url, wait_until="domcontentloaded", timeout=20000)
                time.sleep(1.5)
            except Exception as e:
                emit("error", "Navigate Error", str(e))
            return {"done": False}

        # ── search ────────────────────────────────────────────────────
        if action == "search":
            query = step.get("query", "")
            emit("type", "Search", f"'{query}'")
            engine_inst = AutonomousIntelligenceEngine.__new__(AutonomousIntelligenceEngine)
            search_id = engine_inst._find_search_input(elements) if elements else None
            if search_id:
                selector = f'[data-ai-id="{search_id}"]'
                self._highlight(selector)
                try:
                    loc = self.page.locator(selector).first
                    loc.fill(query, timeout=5000)
                    loc.press("Enter")
                    time.sleep(2.5)
                    return {"done": False}
                except Exception:
                    pass
            # Fallback: keyboard shortcut
            try:
                self.page.keyboard.press("Control+l")
                time.sleep(0.3)
                current_url = self.page.url.lower()
                if "bing.com" in current_url:
                    search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
                    self.page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
                    time.sleep(2.0)
            except Exception as e:
                emit("error", "Search Error", str(e))
            return {"done": False}

        # ── click_top_result ──────────────────────────────────────────
        if action == "click_top_result":
            emit("click", "Click", "Opening top search result...")
            if top_result and top_result.get("href"):
                href = top_result["href"]
                el_id = top_result.get("elementId")
                emit("click", "Result", f"'{top_result.get('title','')}' → {href}")
                if el_id:
                    self._click_element_id(el_id, href)
                else:
                    self.page.goto(href, wait_until="domcontentloaded", timeout=18000)
                    time.sleep(2.0)
                return {"done": False}

            # Fallback: scan elements
            engine_inst = AutonomousIntelligenceEngine.__new__(AutonomousIntelligenceEngine)
            engine_inst.SKIP_RESULT_TERMS = AutonomousIntelligenceEngine.SKIP_RESULT_TERMS
            fb = engine_inst._find_best_result_link(elements)
            if fb:
                emit("click", "Result", f"'{fb['title']}' → {fb.get('href','')}")
                self._click_element_id(fb["elementId"], fb.get("href"))
                return {"done": False}

            emit("error", "Click", "Could not find a result link to click.")
            return {"done": False}

        # ── click_element (by text) ───────────────────────────────────
        if action == "click_element":
            text = step.get("text", "")
            emit("click", "Click Element", f"Looking for '{text}'...")
            for el in elements:
                m = re.match(r"\[(\d+)\]", el)
                if m and text.lower() in el.lower():
                    self._click_element_id(int(m.group(1)))
                    return {"done": False}
            emit("error", "Click Element", f"Could not find element with text '{text}'")
            return {"done": False}

        # ── scroll_down ───────────────────────────────────────────────
        if action == "scroll_down":
            amount = step.get("amount", 600)
            emit("scroll", "Scroll", f"Down {amount}px")
            self.page.evaluate(f"window.scrollBy({{top:{amount}, behavior:'smooth'}});")
            time.sleep(0.8)
            return {"done": False}

        # ── read_page → done ─────────────────────────────────────────
        if action == "read_page":
            emit("status", "Reading", "Extracting page content...")
            time.sleep(1.0)
            dom2 = self._extract_dom_state()
            summary = self._make_summary(
                dom2.get("title", title),
                dom2.get("textExcerpt", excerpt),
                dom2.get("url", url)
            )
            return {"done": True, "summary": summary}

        # ── wait ──────────────────────────────────────────────────────
        if action == "wait":
            secs = min(step.get("seconds", 2), 5)
            emit("wait", "Wait", f"{secs}s")
            time.sleep(secs)
            return {"done": False}

        return {"done": False}

    # ══════════════════════════════════════════════════════════════════
    #  Heuristic loop (fallback, no Groq)
    # ══════════════════════════════════════════════════════════════════
    def _heuristic_loop(self, engine: AutonomousIntelligenceEngine,
                        task: str, emit: Callable,
                        mem: Optional[Any] = None,
                        visited_pages: Optional[List[Dict[str, str]]] = None,
                        platform_journey: Optional[List[str]] = None,
                        step_trace: Optional[List[Dict[str, Any]]] = None,
                        track_platform: Optional[Callable] = None) -> Dict[str, Any]:
        history: List[Dict[str, Any]] = []
        if mem is None:
            mem = get_memory()
        if visited_pages is None:
            visited_pages = []
        if platform_journey is None:
            platform_journey = []
        if step_trace is None:
            step_trace = []

        for step in range(1, self.max_steps + 1):
            if self.stop_requested:
                return {"success": False, "status": "stopped"}

            emit("status", f"Step {step}/{self.max_steps}", "Analysing page...")
            dom_data    = self._extract_dom_state()

            # Record page into memory & track platform
            p_url = dom_data.get("url", "")
            p_title = dom_data.get("title", "")
            p_excerpt = dom_data.get("textExcerpt", "")
            if p_url and not p_url.startswith("about:"):
                if track_platform:
                    track_platform(p_url)
                mem.record_page(p_url, p_title, p_excerpt)
                if not any(v.get("url") == p_url for v in visited_pages):
                    visited_pages.append({"url": p_url, "title": p_title})

            action_plan = engine.decide_next_step(dom_data, history, step)

            if self.stop_requested:
                break

            thought  = action_plan.get("thought", "")
            action   = action_plan.get("action", "")
            summary  = action_plan.get("summary", "")

            history.append({**action_plan, "step": step})

            step_trace.append({
                "step": step,
                "action": action,
                "description": thought or action,
                "url": p_url,
                "platform": platform_journey[-1] if platform_journey else ""
            })

            if action == "done":
                result = summary or thought or "Task completed."
                emit("done", "✅ Done", result, thought)
                return {"success": True, "result": result, "history": history}

            self._execute_heuristic_action(action_plan, emit)
            time.sleep(self.step_delay)

        return {"success": True, "result": "Max steps reached.", "history": history}

    # ══════════════════════════════════════════════════════════════════
    #  DOM extraction (shared)
    # ══════════════════════════════════════════════════════════════════
    def _extract_dom_state(self) -> Dict[str, Any]:
        script = r"""
        () => {
            const url   = window.location.href;
            const title = document.title || "Untitled";
            let clone = document.body ? document.body.cloneNode(true)
                                      : document.createElement('div');
            clone.querySelectorAll('script,style,noscript,svg,iframe').forEach(e=>e.remove());
            const textExcerpt = (clone.innerText||"").replace(/\s+/g,' ').trim().slice(0,3000);

            const candidates = Array.from(document.querySelectorAll(
                'a[href],button,input,textarea,select,[role="button"],[role="link"],' +
                '[role="textbox"],[role="tab"],[role="menuitem"],[onclick],' +
                '[tabindex]:not([tabindex="-1"])'
            ));
            const elements = [];
            let idx = 1;
            for (const el of candidates) {
                const r = el.getBoundingClientRect();
                if (r.width===0||r.height===0) continue;
                const cs = window.getComputedStyle(el);
                if (cs.display==='none'||cs.visibility==='hidden'||cs.opacity==='0') continue;
                el.setAttribute('data-ai-id', String(idx));
                const tag=el.tagName.toLowerCase(),
                      type=el.getAttribute('type')||'',
                      name=el.getAttribute('name')||'',
                      ph=el.getAttribute('placeholder')||'',
                      aria=el.getAttribute('aria-label')||el.getAttribute('title')||'',
                      href=tag==='a'?(el.getAttribute('href')||''):'',
                      text=(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim().slice(0,60),
                      val=el.value?el.value.slice(0,40):'',
                      role=el.getAttribute('role')||'';
                let d=`[${idx}] <${tag}`;
                if(type) d+=` type="${type}"`;
                if(name) d+=` name="${name}"`;
                if(ph)   d+=` placeholder="${ph}"`;
                if(aria) d+=` aria-label="${aria}"`;
                if(role) d+=` role="${role}"`;
                if(href) d+=` href="${href.slice(0,100)}"`;
                if(val)  d+=` value="${val}"`;
                d+='>';
                if(text) d+=` ${text}</${tag}>`;
                elements.push(d);
                idx++;
                if(idx>80) break;
            }

            const SKIP=['sign in','log in','settings','privacy','terms','feedback',
                        'help','google apps','cache','translate','advertisement',
                        'bing.com','google.com','microsoft.com'];
            const SELS=['.b_algo h2 a','#rso h3 a','#search h3 a','h3 a[href]',
                        'h2 a[href]','[data-component-type="s-search-result"] h2 a',
                        'ytd-video-renderer a#video-title','.mw-search-result-heading a'];
            let topSearchResult=null;
            for(const sel of SELS){
                const anchors=document.querySelectorAll(sel);
                for(const a of anchors){
                    const h=a.href||'',txt=(a.innerText||'').trim();
                    if(h.startsWith('http')&&txt.length>2&&
                       !SKIP.some(s=>(h+txt).toLowerCase().includes(s))){
                        topSearchResult={
                            elementId:parseInt(a.getAttribute('data-ai-id')||'0',10)||null,
                            title:txt, href:h};
                        break;
                    }
                }
                if(topSearchResult) break;
            }
            return {url,title,textExcerpt,elements,topSearchResult};
        }
        """
        try:
            return self.page.evaluate(script)
        except Exception:
            return {"url": self.page.url, "title": self.page.title(),
                    "textExcerpt": "", "elements": [], "topSearchResult": None}

    # ══════════════════════════════════════════════════════════════════
    #  Low-level action helpers
    # ══════════════════════════════════════════════════════════════════
    def _highlight(self, selector: str):
        try:
            self.page.evaluate(f"""() => {{
                const el = document.querySelector('{selector}');
                if(el){{
                    el.scrollIntoView({{behavior:'smooth',block:'center'}});
                    el.style.outline='4px solid #3b82f6';
                    el.style.boxShadow='0 0 20px rgba(59,130,246,0.9)';
                }}
            }}""")
            time.sleep(0.3)
        except Exception:
            pass

    def _click_element_id(self, element_id: int, href: str = ""):
        selector = f'[data-ai-id="{element_id}"]'
        self._highlight(selector)
        initial_url = self.page.url
        try:
            self.page.locator(selector).first.click(timeout=5000)
        except Exception:
            try:
                self.page.evaluate(
                    f"()=>{{const e=document.querySelector('{selector}');if(e)e.click();}}")
            except Exception:
                pass
        time.sleep(2.0)
        if href and href.startswith("http") and "javascript:" not in href:
            if self.page.url == initial_url:
                try:
                    self.page.goto(href, wait_until="domcontentloaded", timeout=18000)
                    time.sleep(2.0)
                except Exception:
                    pass
            else:
                try:
                    self.page.wait_for_load_state("domcontentloaded", timeout=8000)
                except Exception:
                    pass

    def _execute_heuristic_action(self, plan: Dict[str, Any], emit: Callable):
        action     = plan.get("action")
        thought    = plan.get("thought", "")
        element_id = plan.get("elementId")
        href       = plan.get("href", "")

        if action == "navigate":
            nav_url = plan.get("url", "")
            emit("navigate", "Navigate", f"→ {nav_url}", thought)
            self.page.goto(nav_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(1.2)
            return

        if action == "scroll":
            d, amt = plan.get("direction", "down"), plan.get("amount", 500)
            emit("scroll", "Scroll", f"{d} {amt}px", thought)
            delta = amt if d == "down" else -amt
            self.page.evaluate(f"window.scrollBy({{top:{delta},behavior:'smooth'}});")
            time.sleep(0.6)
            return

        if action == "wait":
            secs = min(plan.get("seconds", 2), 5)
            emit("wait", "Wait", f"{secs}s", thought)
            time.sleep(secs)
            return

        selector = f'[data-ai-id="{element_id}"]' if element_id else None
        if selector:
            self._highlight(selector)

        if action == "click" and selector:
            emit("click", "Click", f"Element [{element_id}]", thought)
            self._click_element_id(element_id, href)

        elif action == "type" and selector:
            text        = plan.get("text", "")
            press_enter = plan.get("pressEnter", False)
            emit("type", "Type", f"'{text}'" + (" + Enter" if press_enter else ""), thought)
            try:
                loc = self.page.locator(selector).first
                loc.fill(text, timeout=5000)
                if press_enter:
                    loc.press("Enter")
            except Exception:
                try:
                    self.page.evaluate(f"""()=>{{
                        const el=document.querySelector('{selector}');
                        if(el){{el.focus();el.value={json.dumps(text)};
                        el.dispatchEvent(new Event('input',{{bubbles:true}}));
                        el.dispatchEvent(new Event('change',{{bubbles:true}}));}}
                    }}""")
                    if press_enter:
                        self.page.keyboard.press("Enter")
                except Exception:
                    pass
            if press_enter:
                time.sleep(2.2)

        elif action == "press_key":
            key = plan.get("key", "Enter")
            emit("key", "Key", key, thought)
            self.page.keyboard.press(key)

    @staticmethod
    def _make_summary(title: str, text: str, url: str) -> str:
        clean = re.sub(r'\s+', ' ', (text or "")).strip()
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', clean) if len(s.strip()) > 20]
        body = "\n• " + "\n• ".join(sentences[:7]) if sentences else clean[:700]
        return f"📌 Page: {title}\n🌐 URL:  {url}\n\n📝 Key Findings:\n{body}\n"


# Fix missing import used in search fallback
import urllib.parse
