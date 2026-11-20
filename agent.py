"""
agent.py - Command Line Interface for AI Browser Agent
Usage:
    python agent.py
    python agent.py "search google for latest AI news"
"""

import sys
sys.dont_write_bytecode = True

import os
from browser_agent import BrowserAgent, load_config, save_config


def main():
    print("=" * 60)
    print("🤖 AI BROWSER AGENT (Self-Intelligence Edition)")
    print("=" * 60)

    config = load_config()
    api_key = config.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", "")

    print("\n✨ Self-Intelligence Engine Active (100% Local • Zero API Keys Required)")

    # Task input
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        print("\nWhat would you like the AI to do in your browser?")
        print("Example: 'Search Google for latest tech news today'")
        print("Example: 'Find the price of iPhone 16 on Amazon'")
        task = input("\n👉 Enter Command: ").strip()

    if not task:
        print("No task entered. Exiting.")
        return

    model = config.get("gemini_model", "gemini-2.0-flash")
    browser = config.get("browser", "chrome")

    print(f"\n🚀 Launching {browser.title()} with {model}...")
    print(f"Goal: '{task}'\n")

    agent = BrowserAgent(api_key=api_key, model=model, browser_type=browser)

    def log_handler(action, msg, thought=""):
        icon = "⚡"
        if action == "click":
            icon = "👆"
        elif action == "type":
            icon = "✍️"
        elif action == "navigate":
            icon = "🌐"
        elif action == "scroll":
            icon = "📜"
        elif action == "done":
            icon = "🎯"
        elif action == "error":
            icon = "❌"

        print(f"{icon} {msg}")
        if thought:
            print(f"   ↳ Thought: {thought}")

    try:
        result = agent.run_task(task, log_callback=log_handler)
        if result.get("success"):
            print("\n" + "=" * 60)
            print("🎯 FINAL RESULT:")
            print(result.get("result", ""))
            print("=" * 60)
        else:
            print(f"\n❌ Execution finished with error: {result.get('error')}")
    except KeyboardInterrupt:
        print("\nInterrupted by user. Closing browser...")
        agent.close_browser()


if __name__ == "__main__":
    main()
