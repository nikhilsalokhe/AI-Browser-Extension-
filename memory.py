"""
memory.py  —  Persistent Memory & Operation History for AI Browser Agent
Remembers every command, every browser operation, platform journey, cookies,
and pages visited. Restores full state when returning to past tasks.
"""

import sys
sys.dont_write_bytecode = True

import json
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.json")
MAX_TASKS   = 150   # keep last 150 tasks
MAX_PAGES   = 500   # keep last 500 unique pages


class MemoryManager:
    """
    Persistent memory that survives between app restarts.
    Stores:
      - tasks:  detailed history of every command, steps taken, platform transitions & cookies
      - pages:  every page visited with title, summary, url, timestamp, visit count
      - facts:  short key facts extracted from pages
    """

    def __init__(self):
        self._data: Dict[str, Any] = {
            "tasks": [],
            "pages": {},
            "facts": [],
        }
        self.load()

    # ── Persistence ───────────────────────────────────────────────────
    def load(self):
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self._data["tasks"] = saved.get("tasks", [])
                    self._data["pages"] = saved.get("pages", {})
                    self._data["facts"] = saved.get("facts", [])
            except Exception:
                pass

    def save(self):
        try:
            self._data["tasks"] = self._data["tasks"][-MAX_TASKS:]
            if len(self._data["pages"]) > MAX_PAGES:
                sorted_pages = sorted(
                    self._data["pages"].items(),
                    key=lambda kv: kv[1].get("last_visited", ""),
                    reverse=True
                )
                self._data["pages"] = dict(sorted_pages[:MAX_PAGES])
            self._data["facts"] = self._data["facts"][-200:]
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Memory save error: {e}")

    # ── Task recording ────────────────────────────────────────────────
    def record_task(
        self,
        command: str,
        result: str,
        pages_visited: List[Dict],
        step_trace: Optional[List[Dict]] = None,
        platform_journey: Optional[List[str]] = None,
        cookies_info: Optional[Dict] = None,
        last_page: Optional[Dict] = None
    ):
        task = {
            "id":               len(self._data["tasks"]) + 1,
            "timestamp":        datetime.now().isoformat(timespec="seconds"),
            "command":          command,
            "result":           result[:1000],
            "platform_journey": platform_journey or [],
            "step_trace":       step_trace or [],
            "cookies_info":     cookies_info or {},
            "last_page":        last_page or {},
            "pages_visited": [
                {"url": p.get("url",""), "title": p.get("title","")}
                for p in pages_visited
            ]
        }
        self._data["tasks"].append(task)
        self.save()

    # ── Page recording ────────────────────────────────────────────────
    def record_page(self, url: str, title: str, summary: str):
        if not url or url.startswith("about:") or url.startswith("chrome://"):
            return
        clean_url = url.split("?")[0].rstrip("/")
        existing = self._data["pages"].get(clean_url, {})
        self._data["pages"][clean_url] = {
            "url":          url,
            "title":        title or existing.get("title", ""),
            "summary":      summary[:600] if summary else existing.get("summary", ""),
            "last_visited": datetime.now().isoformat(timespec="seconds"),
            "visit_count":  existing.get("visit_count", 0) + 1,
        }
        if summary:
            self._extract_facts(title, summary)
        self.save()

    def _extract_facts(self, title: str, text: str):
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text)
                     if 20 < len(s.strip()) < 200]
        for s in sentences[:3]:
            fact = f"[From '{title}']: {s}"
            if fact not in self._data["facts"]:
                self._data["facts"].append(fact)

    # ── Retrieval ─────────────────────────────────────────────────────
    def get_last_session(self) -> Optional[Dict]:
        """Return the most recent task session if available."""
        if self._data["tasks"]:
            return self._data["tasks"][-1]
        return None

    def recent_tasks(self, n: int = 8) -> List[Dict]:
        return list(reversed(self._data["tasks"][-n:]))

    def search_pages(self, query: str, n: int = 5) -> List[Dict]:
        keywords = [w.lower() for w in query.split() if len(w) > 2]
        scored = []
        for page in self._data["pages"].values():
            text = (page.get("title","") + " " + page.get("summary","")).lower()
            score = sum(text.count(k) for k in keywords)
            if score > 0:
                scored.append((score, page))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:n]]

    def related_facts(self, query: str, n: int = 6) -> List[str]:
        keywords = [w.lower() for w in query.split() if len(w) > 2]
        matches = []
        for fact in reversed(self._data["facts"]):
            if any(k in fact.lower() for k in keywords):
                matches.append(fact)
            if len(matches) >= n:
                break
        return matches

    def build_context_for_groq(self, command: str) -> str:
        parts = []

        # 1. Last session / operation trace (for continuation / back actions)
        last_session = self.get_last_session()
        if last_session:
            journey_str = " -> ".join(last_session.get("platform_journey", [])) or "None"
            lp = last_session.get("last_page", {})
            lp_url = lp.get("url") or "None"
            lp_title = lp.get("title") or "None"
            ck = last_session.get("cookies_info", {})
            ck_domains = ", ".join(ck.get("domains", [])) or "None"

            parts.append(
                f"PREVIOUS SESSION & OPERATIONS:\n"
                f"  • Last Command: \"{last_session.get('command','')}\"\n"
                f"  • Platform Journey: {journey_str}\n"
                f"  • Last Active Page: {lp_title} ({lp_url})\n"
                f"  • Active Cookies/Sessions: {ck_domains}\n"
                f"  (If user wants to resume, go back, repeat, or perform operation on that platform, continue from this page!)"
            )

            # Last step operations trace
            steps = last_session.get("step_trace", [])
            if steps:
                step_lines = []
                for s in steps[:6]:
                    act = s.get("action", "")
                    detail = s.get("query") or s.get("url") or s.get("text") or s.get("description") or ""
                    step_lines.append(f"    - Step {s.get('step', '?')}: [{act}] {detail}")
                parts.append("  • Steps executed in previous session:\n" + "\n".join(step_lines))

        # 2. Related pages already visited
        related_pages = self.search_pages(command, n=4)
        if related_pages:
            parts.append("\nPAGES ALREADY VISITED IN HISTORY (stored in session):")
            for p in related_pages:
                parts.append(
                    f"  • [{p.get('last_visited','')[:10]}] {p.get('title','')} "
                    f"— {p.get('url','')}"
                )
                if p.get("summary"):
                    parts.append(f"    Summary: {p['summary'][:180]}")

        # 3. Related facts
        facts = self.related_facts(command, n=5)
        if facts:
            parts.append("\nLEARNED FACTS & DATA FROM BROWSING:")
            for f in facts:
                parts.append(f"  • {f[:180]}")

        # 4. Recent tasks
        recent = self.recent_tasks(n=4)
        if recent:
            parts.append("\nRECENT COMMAND HISTORY:")
            for t in recent:
                parts.append(
                    f"  • [{t.get('timestamp','')[:16]}] \"{t.get('command','')}\" "
                    f"→ {t.get('result','')[:80]}..."
                )

        if not parts:
            return ""

        return (
            "\n\n--- MEMORY & OPERATION HISTORY ---\n"
            + "\n".join(parts)
            + "\n--- END OF MEMORY ---\n"
        )

    def build_context_for_heuristic(self, command: str) -> str:
        lines = []
        last = self.get_last_session()
        if last:
            lp = last.get("last_page", {})
            j = " -> ".join(last.get("platform_journey", []))
            if j:
                lines.append(f"📚 Previous Journey: {j}")
            if lp.get("title"):
                lines.append(f"   Last Page: {lp.get('title')} ({lp.get('url','')[:60]})")

        pages = self.search_pages(command, n=2)
        if pages:
            lines.append("   Related in memory:")
            for p in pages:
                lines.append(f"   • {p.get('title','')} ({p.get('url','')[:50]})")
        return "\n".join(lines) if lines else ""

    # ── Stats ─────────────────────────────────────────────────────────
    def stats(self) -> Dict[str, int]:
        return {
            "total_tasks":  len(self._data["tasks"]),
            "total_pages":  len(self._data["pages"]),
            "total_facts":  len(self._data["facts"]),
        }

    def all_tasks(self) -> List[Dict]:
        return list(reversed(self._data["tasks"]))

    def clear(self):
        self._data = {"tasks": [], "pages": {}, "facts": []}
        self.save()


_memory: Optional[MemoryManager] = None

def get_memory() -> MemoryManager:
    global _memory
    if _memory is None:
        _memory = MemoryManager()
    return _memory
