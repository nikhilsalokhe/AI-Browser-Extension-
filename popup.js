// popup.js - Bulletproof controller for AI Browser Agent Popup

(function () {
  console.log("[AI Browser Agent] popup.js loaded");

  // Safe storage adapter: works in extension context (chrome.storage) AND fallback (localStorage)
  const safeStorage = {
    async get(keys) {
      if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
        return new Promise((resolve) => {
          try {
            chrome.storage.local.get(keys, (res) => resolve(res || {}));
          } catch (e) {
            console.warn("[Storage] chrome.storage.local.get failed:", e);
            resolve({});
          }
        });
      } else {
        const result = {};
        for (const k of keys) {
          try {
            const raw = localStorage.getItem(k);
            result[k] = raw ? JSON.parse(raw) : null;
          } catch (e) {
            result[k] = localStorage.getItem(k);
          }
        }
        return result;
      }
    },

    async set(obj) {
      if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
        return new Promise((resolve) => {
          try {
            chrome.storage.local.set(obj, () => resolve());
          } catch (e) {
            console.warn("[Storage] chrome.storage.local.set failed:", e);
            resolve();
          }
        });
      } else {
        for (const [k, v] of Object.entries(obj)) {
          try {
            localStorage.setItem(k, typeof v === "object" ? JSON.stringify(v) : String(v));
          } catch (e) {}
        }
      }
    }
  };

  async function initPopup() {
    console.log("[AI Browser Agent] initPopup starting...");

    // UI Elements
    const apiKeyInput = document.getElementById("api-key");
    const toggleKeyVisibilityBtn = document.getElementById("toggle-key-visibility");
    const testKeyBtn = document.getElementById("test-key-btn");
    const saveKeyBtn = document.getElementById("save-key-btn");
    const keySavedMsg = document.getElementById("key-saved-msg");
    const modelSelect = document.getElementById("model-select");
    const maxStepsInput = document.getElementById("max-steps");
    const showHudCheckbox = document.getElementById("show-hud-checkbox");
    const settingsDrawer = document.getElementById("settings-drawer");
    const uiBanner = document.getElementById("ui-banner");

    const taskInput = document.getElementById("task-input");
    const runBtn = document.getElementById("run-btn");
    const runBtnText = document.getElementById("run-btn-text");
    const runBtnIcon = document.getElementById("run-btn-icon");
    const stopBtn = document.getElementById("stop-btn");
    const statusPill = document.getElementById("status-pill");
    const stepIndicator = document.getElementById("step-indicator");
    const logContainer = document.getElementById("log-container");
    const resultCard = document.getElementById("result-card");
    const resultTitle = document.getElementById("result-title");
    const resultContent = document.getElementById("result-content");
    const copyResultBtn = document.getElementById("copy-result-btn");

    function showBanner(message, type = "info", autoHideMs = 4000) {
      if (!uiBanner) return;
      uiBanner.className = `ui-banner ${type}`;
      uiBanner.textContent = message;
      uiBanner.classList.remove("hidden");
      if (autoHideMs > 0) {
        setTimeout(() => {
          uiBanner.classList.add("hidden");
        }, autoHideMs);
      }
    }

    // Check if running in browser file:// mode instead of extension context
    const isExtensionContext = typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.id;
    if (!isExtensionContext) {
      showBanner(
        "⚠️ Warning: Opened as standalone file. To control your browser, load this folder via chrome://extensions -> 'Load unpacked', then click the extension icon in your browser toolbar.",
        "error",
        0
      );
    }

    // 1. Load saved settings
    try {
      const stored = await safeStorage.get([
        "gemini_api_key",
        "gemini_model",
        "max_steps",
        "show_hud",
        "agent_state"
      ]);

      if (stored.gemini_api_key) {
        apiKeyInput.value = stored.gemini_api_key;
      }

      if (stored.gemini_model && modelSelect) {
        modelSelect.value = stored.gemini_model;
      } else if (modelSelect) {
        modelSelect.value = "free";
      }

      if (stored.max_steps && maxStepsInput) {
        maxStepsInput.value = stored.max_steps;
      }
      if (typeof stored.show_hud === "boolean" && showHudCheckbox) {
        showHudCheckbox.checked = stored.show_hud;
      }

      if (stored.agent_state) {
        renderState(stored.agent_state);
      }
    } catch (e) {
      console.error("[AI Browser Agent] Error loading stored state:", e);
    }

    // 2. Toggle API Key visibility
    if (toggleKeyVisibilityBtn && apiKeyInput) {
      toggleKeyVisibilityBtn.onclick = () => {
        apiKeyInput.type = apiKeyInput.type === "password" ? "text" : "password";
      };
    }

    // 3. Save Settings Handler
    const saveSettings = async (showFeedback = true) => {
      console.log("[AI Browser Agent] Saving settings...");
      const key = (apiKeyInput?.value || "").trim();
      const model = modelSelect?.value || "gemini-2.0-flash";
      const maxSteps = parseInt(maxStepsInput?.value || "15", 10) || 15;
      const showHud = showHudCheckbox ? showHudCheckbox.checked : true;

      await safeStorage.set({
        gemini_api_key: key,
        gemini_model: model,
        max_steps: maxSteps,
        show_hud: showHud
      });

      if (showFeedback) {
        if (keySavedMsg) {
          keySavedMsg.classList.remove("hidden");
          setTimeout(() => keySavedMsg.classList.add("hidden"), 2500);
        }
        showBanner("✓ API Key & settings saved successfully!", "success", 3000);
      }
    };

    if (saveKeyBtn) {
      saveKeyBtn.onclick = () => saveSettings(true);
    }
    if (modelSelect) modelSelect.onchange = () => saveSettings(false);
    if (maxStepsInput) maxStepsInput.onchange = () => saveSettings(false);
    if (showHudCheckbox) showHudCheckbox.onchange = () => saveSettings(false);

    // 4. Test Key Button (tests both v1beta and v1 endpoints)
    if (testKeyBtn) {
      testKeyBtn.onclick = async () => {
        const key = (apiKeyInput?.value || "").trim();
        if (!key) {
          showBanner("⚠️ Please paste your API key in the field first.", "error", 4000);
          apiKeyInput?.focus();
          return;
        }

        testKeyBtn.disabled = true;
        testKeyBtn.textContent = "...";

        try {
          let success = false;
          let lastMsg = "";

          // Check available models from Google API
          for (const ver of ["v1beta", "v1"]) {
            try {
              const listRes = await fetch(`https://generativelanguage.googleapis.com/${ver}/models?key=${key}`);
              if (listRes.ok) {
                const data = await listRes.json();
                const count = (data.models || []).length;
                if (count > 0) {
                  success = true;
                  showBanner(`✓ Connected! Found ${count} available models on ${ver}.`, "success", 4000);
                  await saveSettings(false);
                  break;
                }
              } else {
                const errData = await listRes.json().catch(() => ({}));
                lastMsg = errData.error?.message || `HTTP ${listRes.status}`;
              }
            } catch (err) {
              lastMsg = err.message;
            }
          }

          if (!success) {
            showBanner(`❌ Gemini API Error: ${lastMsg}`, "error", 6000);
          }
        } catch (e) {
          showBanner(`❌ Connection failed: ${e.message}`, "error", 6000);
        } finally {
          testKeyBtn.disabled = false;
          testKeyBtn.textContent = "Test";
        }
      };
    }

    // 5. Quick suggestion chips
    document.querySelectorAll(".chip").forEach((chip) => {
      chip.onclick = () => {
        if (taskInput && chip.dataset.task) {
          taskInput.value = chip.dataset.task;
          taskInput.focus();
        }
      };
    });

    // 6. Run Command Handler
    if (runBtn) {
      runBtn.onclick = async () => {
        console.log("[AI Browser Agent] Run Command clicked!");

        const key = (apiKeyInput?.value || "").trim();
        const selectedModel = modelSelect?.value || "free";

        const task = (taskInput?.value || "").trim();
        if (!task) {
          showBanner("⚠️ Please enter a command in the text box.", "error", 4000);
          if (taskInput) taskInput.focus();
          return;
        }

        if (!isExtensionContext) {
          showBanner(
            "⚠️ Cannot automate from a standalone file! Open Chrome -> chrome://extensions -> Click the AI Browser Agent icon in your toolbar.",
            "error",
            8000
          );
          return;
        }

        // Auto-save settings
        await saveSettings(false);

        // Immediate UI updates
        if (resultCard) resultCard.classList.add("hidden");
        if (uiBanner) uiBanner.classList.add("hidden");
        if (logContainer) {
          logContainer.innerHTML =
            '<div class="log-entry"><span class="log-icon">🚀</span><div class="log-text">Starting AI Browser Agent...</div></div>';
        }
        setRunningUI(true);

        try {
          chrome.runtime.sendMessage(
            { type: "RUN_TASK", task },
            (response) => {
              if (chrome.runtime.lastError) {
                console.error("Runtime message error:", chrome.runtime.lastError);
                showBanner(`Extension Service Worker error: ${chrome.runtime.lastError.message}`, "error", 6000);
                setRunningUI(false);
              } else if (response && response.status === "already_running") {
                showBanner("Agent is already running. Click Stop to cancel previous task.", "info", 4000);
              }
            }
          );
        } catch (err) {
          console.error("Run error:", err);
          showBanner("Failed to communicate with service worker: " + err.message, "error", 6000);
          setRunningUI(false);
        }
      };
    }

    // 7. Stop Button
    if (stopBtn) {
      stopBtn.onclick = () => {
        if (isExtensionContext) {
          chrome.runtime.sendMessage({ type: "STOP_TASK" });
        }
        setRunningUI(false);
      };
    }

    // 8. Copy Result
    if (copyResultBtn && resultContent) {
      copyResultBtn.onclick = () => {
        navigator.clipboard.writeText(resultContent.textContent || "");
        copyResultBtn.textContent = "✓ Copied!";
        setTimeout(() => {
          copyResultBtn.textContent = "📋 Copy";
        }, 2000);
      };
    }

    // 9. Storage and Message Listeners for Real-Time Sync
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.onChanged) {
      chrome.storage.onChanged.addListener((changes, area) => {
        if (area === "local" && changes.agent_state) {
          renderState(changes.agent_state.newValue);
        }
      });
    }

    if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
      chrome.runtime.onMessage.addListener((msg) => {
        if (msg.type === "STATE_UPDATED" && msg.state) {
          renderState(msg.state);
        }
      });

      // Poll current state on popup open
      chrome.runtime.sendMessage({ type: "GET_STATE" }, (res) => {
        if (res && res.state) {
          renderState(res.state);
        }
      });
    }

    function setRunningUI(isRunning) {
      if (runBtn) runBtn.disabled = isRunning;
      if (stopBtn) stopBtn.disabled = !isRunning;
      if (isRunning) {
        if (runBtnText) runBtnText.textContent = "Running...";
        if (runBtnIcon) runBtnIcon.textContent = "⚡";
        if (statusPill) {
          statusPill.className = "status-pill running";
          statusPill.textContent = "Running";
        }
      } else {
        if (runBtnText) runBtnText.textContent = "Run Command";
        if (runBtnIcon) runBtnIcon.textContent = "🚀";
      }
    }

    function renderState(state) {
      if (!state) return;
      const { isRunning, status, currentStep, maxSteps, logs, result, error, currentTask } = state;

      if (currentTask && taskInput && !taskInput.value) {
        taskInput.value = currentTask;
      }

      setRunningUI(isRunning);

      if (statusPill) {
        statusPill.className = `status-pill ${isRunning ? "running" : (status || "idle").toLowerCase()}`;
        statusPill.textContent = isRunning ? "Running" : (status || "Idle");
      }

      if (stepIndicator) {
        stepIndicator.textContent = `Step ${currentStep || 0} / ${maxSteps || 15}`;
      }

      if (logContainer) {
        if (logs && logs.length > 0) {
          logContainer.innerHTML = logs
            .map((log) => {
              let icon = "⚡";
              if (log.action === "click") icon = "👆";
              else if (log.action === "type") icon = "✍️";
              else if (log.action === "navigate") icon = "🌐";
              else if (log.action === "scroll") icon = "📜";
              else if (log.action === "wait") icon = "⏳";
              else if (log.action === "done") icon = "🎯";
              else if (log.action === "fail") icon = "❌";

              return `
                <div class="log-entry">
                  <span class="log-icon">${icon}</span>
                  <div class="log-text">
                    <div><strong>${escapeHtml(log.actionName || log.action)}:</strong> ${escapeHtml(log.message || "")}</div>
                    ${log.thought ? `<div class="log-thought">"${escapeHtml(log.thought)}"</div>` : ""}
                  </div>
                </div>
              `;
            })
            .join("");
          logContainer.scrollTop = logContainer.scrollHeight;
        } else if (!isRunning) {
          logContainer.innerHTML = '<div class="log-empty">Ready. Enter a command above to start browser automation.</div>';
        }
      }

      if (resultCard && resultContent) {
        if (result) {
          resultCard.classList.remove("hidden", "is-error");
          if (resultTitle) resultTitle.textContent = "🎯 Task Result";
          resultContent.textContent = result;
        } else if (error) {
          resultCard.classList.remove("hidden");
          resultCard.classList.add("is-error");
          if (resultTitle) resultTitle.textContent = "❌ Error Occurred";
          resultContent.textContent = error;
        } else {
          resultCard.classList.add("hidden");
        }
      }
    }

    function escapeHtml(text) {
      if (!text) return "";
      return text
        .toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }

    console.log("[AI Browser Agent] initPopup completed successfully!");
  }

  // Run initialization regardless of whether DOMContentLoaded already fired or not
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPopup);
  } else {
    initPopup();
  }
})();