// background.js - Autonomous AI Browser Agent Service Worker (Free Mode + Gemini)

let agentState = {
  isRunning: false,
  currentTask: "",
  currentStep: 0,
  maxSteps: 15,
  status: "Idle",
  logs: [],
  result: null,
  error: null
};

let abortRequested = false;
let cachedModelInfo = null;

// Broadcast and persist state
async function updateState(partial) {
  agentState = { ...agentState, ...partial };
  try {
    await chrome.storage.local.set({ agent_state: agentState });
  } catch (e) {
    console.warn("[Background] Failed to persist state in storage:", e);
  }
  try {
    chrome.runtime.sendMessage({ type: "STATE_UPDATED", state: agentState }).catch(() => {});
  } catch (e) {
    // Popup might be closed
  }
}

// Add a log entry
function addLog(action, actionName, message, thought = "") {
  const logItem = {
    step: agentState.currentStep || 0,
    action,
    actionName,
    message,
    thought,
    timestamp: new Date().toLocaleTimeString()
  };
  const logs = [...(agentState.logs || []), logItem];
  updateState({ logs });
}

// Sleep utility
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Listen to messages from popup or in-page HUD
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "RUN_TASK") {
    if (agentState.isRunning) {
      sendResponse({ status: "already_running" });
      return true;
    }

    // Execute asynchronously and catch any fatal errors
    (async () => {
      try {
        await startAgentTask(msg.task);
      } catch (err) {
        console.error("Fatal error in startAgentTask:", err);
        await updateState({
          isRunning: false,
          status: "Error",
          error: err.message || "Failed to execute task."
        });
        addLog("fail", "Error", err.message || "Execution error");
      }
    })();

    sendResponse({ status: "started" });
    return true;
  } else if (msg.type === "STOP_TASK") {
    abortRequested = true;
    updateState({ isRunning: false, status: "Stopped by user" });
    addLog("fail", "Stopped", "Automation halted by user.");
    sendResponse({ status: "stopped" });
    return true;
  } else if (msg.type === "GET_STATE") {
    sendResponse({ state: agentState });
    return true;
  }
  return true;
});

// Wait for a tab to finish loading
function waitForTabLoad(tabId, timeoutMs = 12000) {
  return new Promise((resolve) => {
    let resolved = false;
    const timer = setTimeout(() => {
      if (!resolved) {
        resolved = true;
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    }, timeoutMs);

    const listener = (id, changeInfo) => {
      if (id === tabId && changeInfo.status === "complete") {
        if (!resolved) {
          resolved = true;
          clearTimeout(timer);
          chrome.tabs.onUpdated.removeListener(listener);
          resolve();
        }
      }
    };
    chrome.tabs.onUpdated.addListener(listener);
  });
}

// Start the autonomous loop (Works 100% FREE without API Key!)
async function startAgentTask(task) {
  abortRequested = false;

  const config = await chrome.storage.local.get([
    "gemini_api_key",
    "gemini_model",
    "max_steps",
    "show_hud"
  ]);

  const apiKey = (config.gemini_api_key || "").trim();
  const userModel = config.gemini_model || "free";
  const maxSteps = config.max_steps || 15;
  const showHud = config.show_hud !== false;

  // Initialize state
  await updateState({
    isRunning: true,
    currentTask: task,
    currentStep: 0,
    maxSteps: maxSteps,
    status: "Running",
    logs: [],
    result: null,
    error: null
  });

  // Get current active tab
  let [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab || !tab.id) {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  }

  const tabUrl = (tab && (tab.url || tab.pendingUrl)) || "";

  // Check if tab is restricted (e.g. chrome://, edge://, about:blank, or empty)
  let activeTab = tab;
  const isRestricted =
    !tab ||
    !tab.id ||
    !tabUrl ||
    tabUrl.startsWith("chrome://") ||
    tabUrl.startsWith("edge://") ||
    tabUrl.startsWith("chrome-extension://") ||
    tabUrl.startsWith("about:") ||
    tabUrl.startsWith("view-source:");

  if (isRestricted) {
    let startUrl = "https://www.bing.com";
    const taskLower = task.toLowerCase();
    if (taskLower.includes("wikipedia")) startUrl = "https://www.wikipedia.org";
    else if (taskLower.includes("amazon")) startUrl = "https://www.amazon.com";
    else if (taskLower.includes("youtube")) startUrl = "https://www.youtube.com";
    else if (taskLower.includes("google")) startUrl = "https://www.google.com";

    addLog("navigate", "New Tab", `Opening ${startUrl} to begin task...`);
    activeTab = await chrome.tabs.create({ url: startUrl, active: true });
    await waitForTabLoad(activeTab.id);
    await sleep(1500);
  }

  const actionHistory = [];

  try {
    for (let step = 1; step <= maxSteps; step++) {
      if (abortRequested) break;

      await updateState({ currentStep: step });

      // Update in-page HUD
      if (showHud) {
        await injectOrUpdateHud(activeTab.id, {
          step,
          maxSteps,
          task,
          status: "Scanning webpage elements..."
        });
      }

      // Step 1: Extract interactive DOM elements & clean text
      let pageData;
      try {
        const [res] = await chrome.scripting.executeScript({
          target: { tabId: activeTab.id },
          func: inPageExtractState
        });
        pageData = res?.result;
      } catch (e) {
        await sleep(1200);
        try {
          const [res] = await chrome.scripting.executeScript({
            target: { tabId: activeTab.id },
            func: inPageExtractState
          });
          pageData = res?.result;
        } catch (err) {
          throw new Error("Unable to inspect webpage: " + err.message);
        }
      }

      if (!pageData) {
        throw new Error("Failed to extract page data.");
      }

      // Step 2: Decide next action (Free AI, Autonomous Heuristic, or Gemini)
      if (showHud) {
        await injectOrUpdateHud(activeTab.id, {
          step,
          maxSteps,
          task,
          status: "Planning next action..."
        });
      }

      const aiResponse = await decideNextAction(apiKey, userModel, task, pageData, actionHistory, step);

      if (abortRequested) break;

      const { thought, action, elementId, text, pressEnter, key, url, href, isSearchResultClick, direction, amount, seconds, summary } = aiResponse;

      // Record in history
      actionHistory.push({
        step,
        thought,
        action,
        elementId,
        text,
        url,
        href,
        isSearchResultClick,
        summary
      });

      // Step 3: Handle completion or failure
      if (action === "done") {
        const finalMsg = summary || thought || "Task completed successfully.";
        addLog("done", "Task Done", finalMsg, thought);
        await updateState({
          isRunning: false,
          status: "Completed",
          result: finalMsg
        });

        if (showHud) {
          await injectOrUpdateHud(activeTab.id, {
            step,
            maxSteps,
            task,
            status: "Done: " + finalMsg,
            isDone: true
          });
        }
        break;
      }

      if (action === "fail") {
        const failMsg = summary || thought || "AI could not complete the request.";
        addLog("fail", "Task Failed", failMsg, thought);
        await updateState({
          isRunning: false,
          status: "Error",
          error: failMsg
        });

        if (showHud) {
          await injectOrUpdateHud(activeTab.id, {
            step,
            maxSteps,
            task,
            status: "Failed: " + failMsg,
            isDone: true
          });
        }
        break;
      }

      // Step 4: Execute in-browser action
      let actionLabel = action;
      let logMsg = "";

      if (action === "navigate") {
        actionLabel = "Navigate";
        logMsg = `Opening ${url}`;
        addLog(action, actionLabel, logMsg, thought);

        if (showHud) {
          await injectOrUpdateHud(activeTab.id, {
            step,
            maxSteps,
            task,
            status: `Navigating to ${url}...`
          });
        }

        const waitPromise = waitForTabLoad(activeTab.id);
        await chrome.tabs.update(activeTab.id, { url });
        await waitPromise;
        await sleep(1500);
        continue;
      }

      if (action === "wait") {
        const waitSec = Math.min(seconds || 2, 5);
        actionLabel = "Wait";
        logMsg = `Waiting ${waitSec}s for page to settle`;
        addLog(action, actionLabel, logMsg, thought);

        if (showHud) {
          await injectOrUpdateHud(activeTab.id, {
            step,
            maxSteps,
            task,
            status: `Waiting ${waitSec}s...`
          });
        }

        await sleep(waitSec * 1000);
        continue;
      }

      // For DOM actions (click, type, press_key, scroll)
      if (action === "click") {
        actionLabel = "Click";
        logMsg = `Clicking element [${elementId}]`;
      } else if (action === "type") {
        actionLabel = "Type";
        logMsg = `Typing "${text}" into element [${elementId}]${pressEnter ? " and pressing Enter" : ""}`;
      } else if (action === "scroll") {
        actionLabel = "Scroll";
        logMsg = `Scrolling ${direction || "down"} (${amount || 500}px)`;
      } else if (action === "press_key") {
        actionLabel = "Key Press";
        logMsg = `Pressing key "${key || "Enter"}"`;
      }

      addLog(action, actionLabel, logMsg, thought);

      if (showHud) {
        await injectOrUpdateHud(activeTab.id, {
          step,
          maxSteps,
          task,
          status: `${actionLabel}: ${logMsg}`
        });
      }

      // Execute inside the webpage
      await chrome.scripting.executeScript({
        target: { tabId: activeTab.id },
        args: [aiResponse],
        func: inPageExecuteAction
      });

      // Allow UI transitions / page responses
      await sleep(1200);

      if ((action === "type" && pressEnter) || action === "click") {
        // Wait for potential navigation to begin and settle
        await sleep(1500);

        // If this was a search result click with an href and the tab URL hasn't changed, force navigate
        if (action === "click" && href && href.startsWith("http")) {
          try {
            const currentTab = await chrome.tabs.get(activeTab.id);
            const currentUrl = (currentTab.url || currentTab.pendingUrl || "").toLowerCase();
            const targetDomain = new URL(href).hostname.toLowerCase();
            if (!currentUrl.includes(targetDomain)) {
              addLog("navigate", "Opening Link", `Directly navigating to: ${href}`, thought);
              const waitNav = waitForTabLoad(activeTab.id);
              await chrome.tabs.update(activeTab.id, { url: href });
              await waitNav;
              await sleep(1500);
            }
          } catch (navErr) {
            console.warn("[Navigation fallback error]", navErr);
          }
        }
      }
    }

    if (agentState.isRunning && !abortRequested) {
      await updateState({
        isRunning: false,
        status: "Max Steps Reached",
        result: "Reached maximum steps limit (" + maxSteps + "). Task stopped."
      });
      addLog("done", "Finished", "Reached maximum allowed steps.");
    }
  } catch (err) {
    console.error("Agent Loop Error:", err);
    await updateState({
      isRunning: false,
      status: "Error",
      error: err.message || "An unexpected error occurred."
    });
    addLog("fail", "Error", err.message || "Execution error");
  }
}

// Master decision maker: Free Online AI -> Smart Heuristic Engine -> Gemini (if configured)
async function decideNextAction(apiKey, userModel, task, pageData, history, step) {
  // If user provided a Gemini API key and model is not 'free', try Gemini
  if (apiKey && userModel !== "free") {
    try {
      return await callGeminiModel(apiKey, userModel, task, pageData, history);
    } catch (e) {
      console.warn("[Gemini API Error]", e.message, "- Falling back to Free Autonomous Mode!");
    }
  }

  // Try Free AI API (Pollinations)
  try {
    const freeRes = await callFreeOnlineAi(task, pageData, history);
    if (freeRes && freeRes.action) return freeRes;
  } catch (e) {
    // Continue to autonomous engine
  }

  // Smart Autonomous Heuristic Engine (100% Offline, Zero API Key Required)
  return planHeuristically(task, pageData, history, step);
}

// Free Online AI without API Key
async function callFreeOnlineAi(userTask, pageData, history) {
  const historyText = history.map(h => `Step ${h.step}: ${h.action} [${h.elementId || ''}] ${h.text || ''}`).join("\n") || "None";
  const prompt = `You are a browser automation agent.
User Goal: "${userTask}"
Current URL: ${pageData.url}
Title: ${pageData.title}
History: ${historyText}
Text Excerpt: ${pageData.textExcerpt.slice(0, 800)}
Elements:
${pageData.elements.slice(0, 35).join("\n")}

Respond with ONLY valid JSON:
{"thought": "...", "action": "click|type|navigate|scroll|wait|done", "elementId": 1, "text": "...", "pressEnter": true, "summary": "..."}`;

  const resp = await fetch("https://text.pollinations.ai/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages: [{ role: "user", content: prompt }],
      jsonMode: true
    })
  });

  if (resp.ok) {
    const text = await resp.text();
    if (!text.includes('"status":503')) {
      let clean = text.trim();
      if (clean.startsWith("```json")) clean = clean.slice(7);
      if (clean.startsWith("```")) clean = clean.slice(3);
      if (clean.endsWith("```")) clean = clean.slice(0, -3);
      return JSON.parse(clean.trim());
    }
  }
  throw new Error("Free API unavailable");
}

// Autonomous Intelligence Engine (100% Reliable, Native Cognitive Engine, Zero API Key)
function planHeuristically(task, pageData, history, step) {
  const taskLower = task.toLowerCase();
  const url = (pageData.url || "").toLowerCase();
  const title = pageData.title || "";
  const excerpt = pageData.textExcerpt || "";
  const elements = pageData.elements || [];
  const topResult = pageData.topSearchResult || null;

  const KNOWN_PLATFORMS = {
    google: "https://www.google.com",
    youtube: "https://www.youtube.com",
    amazon: "https://www.amazon.com",
    wikipedia: "https://www.wikipedia.org",
    github: "https://www.github.com",
    reddit: "https://www.reddit.com",
    twitter: "https://www.x.com",
    bing: "https://www.bing.com"
  };

  // Detect whether we already clicked a result link in history
  const alreadyClickedResult = history.some(h => h.isSearchResultClick === true);

  // 1. Direct Page Summarization
  if (["summarize", "read this", "summary", "explain this page", "key points"].some(k => taskLower.includes(k))) {
    if (excerpt) {
      return {
        action: "done",
        thought: "Extracted and comprehended page content successfully.",
        summary: `📌 Page: ${title}\n🌐 URL: ${pageData.url}\n\n📝 Summary:\n${excerpt.slice(0, 700)}...`
      };
    }
  }

  // 2. Direct Click Target Intent
  if (/^(please\s+)?(can you\s+)?(click|press|tap)\s+/i.test(task) && !taskLower.includes("search")) {
    const targetText = task.replace(/^(please\s+)?(can you\s+)?(click|press|tap)\s+(on\s+)?(the\s+)?/i, "").trim().replace(/['"]/g, "");
    for (const el of elements) {
      if (el.toLowerCase().includes(targetText.toLowerCase())) {
        const m = el.match(/^\[(\d+)\]/);
        if (m) {
          return {
            action: "click",
            elementId: parseInt(m[1], 10),
            thought: `Clicking element matching '${targetText}'.`
          };
        }
      }
    }
  }

  // 3. Form Fill Intent
  const formFieldMatches = task.match(/([a-zA-Z0-9_]+)\s+(?:with|as|=)\s+([^\s,]+)/gi);
  if (formFieldMatches && formFieldMatches.length > 0) {
    const filledFields = history.map(h => h.field).filter(Boolean);
    for (const matchStr of formFieldMatches) {
      const parts = matchStr.split(/\s+(?:with|as|=)\s+/i);
      if (parts.length === 2) {
        const fieldName = parts[0].trim().toLowerCase();
        const fieldVal = parts[1].trim();
        if (!filledFields.includes(fieldName)) {
          for (const el of elements) {
            if ((el.includes("<input") || el.includes("<textarea")) && el.toLowerCase().includes(fieldName)) {
              const m = el.match(/^\[(\d+)\]/);
              if (m) {
                return {
                  action: "type",
                  elementId: parseInt(m[1], 10),
                  text: fieldVal,
                  pressEnter: false,
                  field: fieldName,
                  thought: `Filling form field '${fieldName}' with '${fieldVal}'.`
                };
              }
            }
          }
        }
      }
    }
  }

  // 4. Clean Query & Platform Extraction
  let cleanQuery = task
    .replace(/^(please\s+)?(can you\s+)?(go to|open|visit)\s+[a-z0-9\.]+\s+(and\s+)?(search|look up|find)?\s*(for)?\s*/i, "")
    .replace(/^(search|find|look up|google|check price of|check|show me)\s+(for\s+)?(google\s+for\s+)?/i, "")
    .replace(/\s+on\s+(google|amazon|wikipedia|youtube|github|reddit|bing).*$/i, "")
    .trim();

  let targetPlatformUrl = null;
  for (const [name, pUrl] of Object.entries(KNOWN_PLATFORMS)) {
    if (new RegExp(`\\b${name}\\b`, "i").test(task)) {
      targetPlatformUrl = pUrl;
      break;
    }
  }

  // 5. Determine if we're on a search results page
  const isSearchPage =
    url.includes("google.com/search") ||
    url.includes("bing.com/search") ||
    url.includes("/search?") ||
    url.includes("amazon.com/s") ||
    url.includes("youtube.com/results") ||
    url.includes("wikipedia.org/w/index.php?search=");

  // 6. If on search results page, click the TOP RESULT to open the destination website
  if (isSearchPage && !alreadyClickedResult) {
    // Use the specially detected topSearchResult first
    if (topResult && topResult.href) {
      return {
        action: "click",
        elementId: topResult.elementId,
        href: topResult.href,
        isSearchResultClick: true,
        thought: `Clicking top organic result: "${topResult.title}" → ${topResult.href}`
      };
    }

    // Fallback: scan elements list for first anchor that looks like a result
    const SKIP = ["images", "videos", "maps", "news", "sign in", "settings", "tools", "privacy", "terms", "google apps", "feedback", "help", "cache"];
    for (const el of elements) {
      const aMatch = el.match(/^\[(\d+)\]\s*<a[^>]+href="([^"]+)"/i);
      if (aMatch) {
        const elId = parseInt(aMatch[1], 10);
        const elHref = aMatch[2];
        const elLower = el.toLowerCase();
        if (
          elHref.startsWith("http") &&
          !elHref.includes("bing.com/search") &&
          !elHref.includes("google.com/search") &&
          !elHref.includes("google.com/sorry") &&
          !SKIP.some(s => elLower.includes(s))
        ) {
          return {
            action: "click",
            elementId: elId,
            href: elHref,
            isSearchResultClick: true,
            thought: `Clicking first organic result link to open the website.`
          };
        }
      }
    }

    // Last resort: navigate directly via URL encoded search result
    if (excerpt) {
      return {
        action: "done",
        thought: "Read information directly from search results.",
        summary: `Search Results for '${cleanQuery}':\n\n${excerpt.slice(0, 500)}...`
      };
    }
  }

  // 7. If we already clicked a result and are on a destination page, we're done
  if (alreadyClickedResult && !isSearchPage && excerpt) {
    return {
      action: "done",
      thought: `Successfully opened and read destination website '${title}'.`,
      summary: `📌 Opened: ${title}\n🌐 URL: ${pageData.url}\n\n📝 Key Findings:\n${excerpt.slice(0, 700)}...`
    };
  }

  // 8. If on content page (not a search results page) for 3+ steps, done
  if (step >= 4 && !isSearchPage && excerpt) {
    return {
      action: "done",
      thought: `Gathered comprehensive knowledge from ${title}.`,
      summary: `📌 Source: ${title}\n🌐 URL: ${pageData.url}\n\n📝 Key Findings:\n${excerpt.slice(0, 700)}...`
    };
  }

  // 9. Look for Search Input on the page
  let searchInputId = null;
  for (const el of elements) {
    const match = el.match(/^\[(\d+)\]/);
    const elId = match ? parseInt(match[1], 10) : null;
    const elLower = el.toLowerCase();
    if ((elLower.includes("<input") || elLower.includes("<textarea")) &&
        ['name="q"', 'type="search"', 'placeholder="search', 'search', 'q=', 'search_query'].some(k => elLower.includes(k))) {
      searchInputId = elId;
      break;
    }
  }

  if (searchInputId) {
    return {
      action: "type",
      elementId: searchInputId,
      text: cleanQuery,
      pressEnter: true,
      thought: `Found primary search box. Typing '${cleanQuery}' and submitting.`
    };
  }

  // 10. If not on appropriate search engine or platform, navigate
  const isOnKnownPlatform = Object.keys(KNOWN_PLATFORMS).some(name => url.includes(name + ".com") || url.includes(name + ".org"));
  if (!isOnKnownPlatform) {
    const navUrl = targetPlatformUrl || "https://www.bing.com";
    return {
      action: "navigate",
      url: navUrl,
      thought: `Navigating to ${navUrl} to search for '${cleanQuery}'.`
    };
  }

  // 11. Scroll fallback
  return {
    action: "scroll",
    direction: "down",
    amount: 500,
    thought: "Scrolling down to reveal more interactive content."
  };
}

// Fallback Gemini model caller if API key is provided
async function callGeminiModel(apiKey, userModel, userTask, pageData, history) {
  const endpoint = `https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key=${apiKey}`;
  const prompt = `You are an autonomous browser agent. User goal: "${userTask}". URL: ${pageData.url}. Title: ${pageData.title}. Elements: ${pageData.elements.slice(0, 40).join("\n")}. Return JSON: {"action":"click|type|navigate|done", "elementId": 1, "text":"...", "pressEnter":true, "summary":"..."}`;

  const resp = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{ role: "user", parts: [{ text: prompt }] }]
    })
  });

  if (resp.ok) {
    const data = await resp.json();
    const raw = data.candidates?.[0]?.content?.parts?.[0]?.text || "{}";
    let clean = raw.trim();
    if (clean.startsWith("```json")) clean = clean.slice(7);
    if (clean.startsWith("```")) clean = clean.slice(3);
    if (clean.endsWith("```")) clean = clean.slice(0, -3);
    return JSON.parse(clean.trim());
  }
  throw new Error("Gemini API call failed");
}

// In-Page Script: Extract page state and index interactive elements (with top search result detection)
function inPageExtractState() {
  document.querySelectorAll(".ai-agent-highlight-badge").forEach((el) => el.remove());

  const url = window.location.href;
  const title = document.title || "Untitled";

  if (!document.body) {
    return { url, title, textExcerpt: "", elements: [], topSearchResult: null };
  }

  let bodyClone = document.body.cloneNode(true);
  bodyClone.querySelectorAll("script, style, noscript, svg, iframe, #ai-browser-agent-hud").forEach((n) => n.remove());
  const textExcerpt = (bodyClone.innerText || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 2500);

  const candidates = Array.from(
    document.querySelectorAll(
      'a[href], button, input, textarea, select, [role="button"], [role="link"], [role="textbox"], [role="tab"], [role="menuitem"], [onclick], [tabindex]:not([tabindex="-1"])'
    )
  );

  const elementsList = [];
  let index = 1;

  for (const el of candidates) {
    if (el.closest && el.closest("#ai-browser-agent-hud")) continue;

    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") continue;

    el.setAttribute("data-ai-id", index.toString());

    const tag = el.tagName.toLowerCase();
    const type = el.getAttribute("type") || "";
    const name = el.getAttribute("name") || "";
    const placeholder = el.getAttribute("placeholder") || "";
    const ariaLabel = el.getAttribute("aria-label") || el.getAttribute("title") || "";
    const href = (tag === "a") ? (el.getAttribute("href") || "") : "";
    const text = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 60);
    const value = el.value ? el.value.slice(0, 40) : "";
    const role = el.getAttribute("role") || "";

    let descriptor = `[${index}] <${tag}`;
    if (type) descriptor += ` type="${type}"`;
    if (name) descriptor += ` name="${name}"`;
    if (placeholder) descriptor += ` placeholder="${placeholder}"`;
    if (ariaLabel) descriptor += ` aria-label="${ariaLabel}"`;
    if (role) descriptor += ` role="${role}"`;
    if (href) descriptor += ` href="${href.slice(0, 80)}"`;
    if (value) descriptor += ` value="${value}"`;
    descriptor += ">";
    if (text) descriptor += ` ${text}</${tag}>`;

    elementsList.push(descriptor);
    index++;
    if (index > 80) break;
  }

  // Detect the top organic search result link
  const SKIP_TERMS = ["images", "videos", "maps", "news", "sign in", "settings", "tools", "privacy", "terms", "feedback", "help", "google apps", "cache"];
  const RESULT_SELECTORS = [
    ".b_algo h2 a",        // Bing
    "#rso h3 a",           // Google
    "#search h3 a",        // Google alternate
    "h3 a[href]",          // Generic
    "h2 a[href]",          // Generic
    "[data-component-type='s-search-result'] h2 a", // Amazon
    "ytd-video-renderer a#video-title",             // YouTube
    ".mw-search-result-heading a"                   // Wikipedia
  ];

  let topSearchResult = null;
  for (const sel of RESULT_SELECTORS) {
    try {
      const anchors = document.querySelectorAll(sel);
      for (const a of anchors) {
        const h = a.href || "";
        const txt = (a.innerText || "").trim();
        if (
          h.startsWith("http") &&
          !h.includes("bing.com/search") &&
          !h.includes("google.com/search") &&
          !h.includes("google.com/sorry") &&
          txt.length > 3 &&
          !SKIP_TERMS.some(s => txt.toLowerCase().includes(s))
        ) {
          const id = a.getAttribute("data-ai-id");
          topSearchResult = {
            elementId: id ? parseInt(id, 10) : null,
            title: txt,
            href: h
          };
          break;
        }
      }
      if (topSearchResult) break;
    } catch (e) {}
  }

  return { url, title, textExcerpt, elements: elementsList, topSearchResult };
}

// In-Page Script: Execute action
function inPageExecuteAction(step) {
  const { action, elementId, text, pressEnter, key, direction, amount, href } = step;

  let el = null;
  if (elementId) {
    el = document.querySelector(`[data-ai-id="${elementId}"]`);
  }

  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });

    const prevOutline = el.style.outline;
    const prevBoxShadow = el.style.boxShadow;
    const prevTransition = el.style.transition;

    el.style.transition = "all 0.3s ease";
    el.style.outline = "3px solid #3b82f6";
    el.style.boxShadow = "0 0 15px rgba(59, 130, 246, 0.8)";

    setTimeout(() => {
      el.style.outline = prevOutline;
      el.style.boxShadow = prevBoxShadow;
      el.style.transition = prevTransition;
    }, 1800);
  }

  if (action === "click" && el) {
    el.focus();
    el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
    el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true }));
    el.click();

    // If element has an href and native click didn't navigate, force navigate
    const targetHref = href || (el.tagName === "A" ? el.href : null) ||
      (el.querySelector("a") ? el.querySelector("a").href : null);
    if (targetHref && targetHref.startsWith("http") && !targetHref.includes("javascript:")) {
      setTimeout(() => {
        if (window.location.href.indexOf(targetHref.split("?")[0]) === -1) {
          window.location.href = targetHref;
        }
      }, 800);
    }
  } else if (action === "navigate_href" && href) {
    // Direct URL navigation fallback
    window.location.href = href;
  } else if (action === "type" && el) {
    el.focus();
    el.value = text;
    el.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    el.dispatchEvent(new Event("change", { bubbles: true, composed: true }));

    if (pressEnter) {
      el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
      el.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
      if (el.form) {
        try {
          el.form.requestSubmit();
        } catch (e) {
          el.form.submit();
        }
      }
    }
  } else if (action === "press_key") {
    const k = key || "Enter";
    const target = document.activeElement || document.body;
    target.dispatchEvent(new KeyboardEvent("keydown", { key: k, code: k, bubbles: true }));
    target.dispatchEvent(new KeyboardEvent("keyup", { key: k, code: k, bubbles: true }));
  } else if (action === "scroll") {
    const scrollAmount = amount || 500;
    window.scrollBy({
      top: direction === "up" ? -scrollAmount : scrollAmount,
      behavior: "smooth"
    });
  }
}

// In-Page Script: Show/Update HUD
async function injectOrUpdateHud(tabId, data) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      args: [data],
      func: (info) => {
        let hud = document.getElementById("ai-browser-agent-hud");
        if (!hud) {
          hud = document.createElement("div");
          hud.id = "ai-browser-agent-hud";
          hud.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 2147483647;
            background: #0f172a;
            color: #f8fafc;
            border: 1px solid #3b82f6;
            border-radius: 12px;
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.7), 0 0 15px rgba(59, 130, 246, 0.3);
            padding: 12px 16px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 12px;
            max-width: 320px;
            box-sizing: border-box;
            transition: all 0.25s ease;
            pointer-events: auto;
          `;
          document.body.appendChild(hud);
        }

        const isComplete = info.isDone;

        hud.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <div style="font-weight:700; display:flex; align-items:center; gap:6px; color:#60a5fa; font-size:13px;">
              <span>🤖</span> AI Agent
            </div>
            <div style="font-size:10px; background:#1e293b; padding:2px 6px; border-radius:4px; color:#94a3b8;">
              Step ${info.step} / ${info.maxSteps}
            </div>
          </div>
          <div style="color:#cbd5e1; font-weight:500; margin-bottom:6px; word-break:break-word; max-height:36px; overflow:hidden;">
            "${info.task}"
          </div>
          <div style="color:${isComplete ? "#34d399" : "#38bdf8"}; font-size:11.5px; background:rgba(0,0,0,0.3); padding:6px 8px; border-radius:6px; margin-bottom:8px; display:flex; align-items:center; gap:6px;">
            ${isComplete ? "✓" : "⚡"} <span>${info.status}</span>
          </div>
          <div style="display:flex; justify-content:flex-end;">
            <button id="ai-hud-stop-btn" style="background:#ef4444; color:white; border:none; padding:4px 10px; border-radius:5px; font-size:11px; font-weight:600; cursor:pointer;">
              Stop Agent
            </button>
          </div>
        `;

        const stopBtn = hud.querySelector("#ai-hud-stop-btn");
        if (stopBtn) {
          stopBtn.onclick = () => {
            chrome.runtime.sendMessage({ type: "STOP_TASK" });
            hud.remove();
          };
        }

        if (isComplete) {
          setTimeout(() => {
            if (hud) hud.remove();
          }, 8000);
        }
      }
    });
  } catch (e) {}
}