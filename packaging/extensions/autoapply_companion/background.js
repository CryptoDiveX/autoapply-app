/**
 * AutoApply Companion — MV3 Service Worker (`background.js`)
 * Repository: https://github.com/CryptoDiveX/autoapply-extension
 *
 * Bridges messages between the Shadow DOM content script (`content.js`) and the
 * local AutoApply Companion HTTP/Native bridge (`http://127.0.0.1:19299/api/companion`).
 *
 * Supported message types:
 * - `COMPANION_GET_STATE`: Fetches full workspace state (`get_state`) and caches
 *   it in `chrome.storage.local` for offline/fallback resilience.
 * - `COMPANION_ACTION`: Executes a named bridge action (`action`, `payload`) and
 *   returns the updated workspace state.
 * - `COMPANION_NAVIGATE`: Navigates the active or sender tab to a target URL.
 */
const BRIDGE_URL = "http://127.0.0.1:19299/api/companion";

async function callLocalBridge(action, payload = {}) {
  try {
    const resp = await fetch(BRIDGE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, payload }),
    });
    if (!resp.ok) {
      const errText = await resp.text();
      return { ok: false, error: errText || `HTTP ${resp.status}` };
    }
    const data = await resp.json();
    if (data && data.onboarding) {
      await chrome.storage.local.set({ autoapply_companion_state: data });
    }
    return { ok: true, data };
  } catch (err) {
    const cached = await chrome.storage.local.get(["autoapply_companion_state"]);
    return {
      ok: false,
      error: String(err && err.message ? err.message : err),
      cached: cached.autoapply_companion_state || null,
    };
  }
}

const recentTabUrls = new Map();

chrome.tabs.onCreated.addListener((tab) => {
  try {
    const rawUrl = (tab && (tab.pendingUrl || tab.url)) || "";
    if (!rawUrl || !rawUrl.startsWith("http") || !tab.id) return;
    const normUrl = rawUrl.split("#")[0];
    const now = Date.now();
    const prev = recentTabUrls.get(normUrl);
    if (prev && prev.tabId !== tab.id && now - prev.ts < 3500) {
      chrome.tabs.remove(tab.id).catch(() => {});
      return;
    }
    recentTabUrls.set(normUrl, { tabId: tab.id, ts: now });
  } catch (_) {}
});

function injectCompanionIntoAllTabs() {
  try {
    chrome.tabs.query({}, (tabs) => {
      for (const tab of tabs || []) {
        if (
          tab &&
          tab.id &&
          tab.url &&
          (tab.url.startsWith("http://") || tab.url.startsWith("https://"))
        ) {
          chrome.scripting
            .executeScript({
              target: { tabId: tab.id, allFrames: true },
              files: ["dialog_guard_main.js"],
              world: "MAIN",
            })
            .catch(() => {});
          chrome.scripting
            .executeScript({
              target: { tabId: tab.id, allFrames: true },
              files: ["content.js"],
            })
            .catch(() => {});
        }
      }
    });
  } catch (_) {}
}

chrome.runtime.onInstalled.addListener(() => {
  callLocalBridge("get_state", {});
  injectCompanionIntoAllTabs();
});

chrome.runtime.onStartup.addListener(() => {
  callLocalBridge("get_state", {});
  injectCompanionIntoAllTabs();
});

injectCompanionIntoAllTabs();

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || !message.type) {
    return false;
  }

  if (message.type === "COMPANION_GET_STATE") {
    callLocalBridge("get_state", {}).then(sendResponse);
    return true;
  }

  if (message.type === "COMPANION_ACTION") {
    callLocalBridge(message.action, message.payload || {}).then(sendResponse);
    return true;
  }

  if (message.type === "COMPANION_ARM_DIALOG_GUARD") {
    const tabId = (sender && sender.tab && sender.tab.id) || message.tabId || null;
    const mode = String(message.mode || "apply").toLowerCase();
    const durationMs = Number(message.durationMs || 60000);
    if (!tabId) {
      sendResponse({ ok: false, error: "Missing tabId" });
      return false;
    }
    chrome.scripting
      .executeScript({
        target: { tabId, allFrames: true },
        files: ["dialog_guard_main.js"],
        world: "MAIN",
      })
      .catch(() => {})
      .finally(() => {
        chrome.scripting
          .executeScript({
            target: { tabId, allFrames: true },
            world: "MAIN",
            func: (m, dur) => {
              if (typeof window.__aaArmDialogGuard === "function") {
                if (m === "idle") {
                  if (typeof window.__aaDisarmDialogGuard === "function") {
                    window.__aaDisarmDialogGuard();
                  }
                } else {
                  window.__aaArmDialogGuard(m, dur);
                }
              }
            },
            args: [mode, durationMs],
          })
          .then(() => sendResponse({ ok: true }))
          .catch((err) => sendResponse({ ok: false, error: String(err) }));
      });
    return true;
  }

  if (message.type === "COMPANION_RECOVER_FROZEN_TAB") {
    const targetUrl = String(message.url || "").trim();
    const frozenTabId = message.tabId || (sender && sender.tab && sender.tab.id) || null;
    if (!targetUrl) {
      sendResponse({ ok: false, error: "Missing URL" });
      return false;
    }
    chrome.tabs.create({ url: targetUrl, active: true }, (newTab) => {
      if (frozenTabId && (!newTab || newTab.id !== frozenTabId)) {
        chrome.tabs.remove(frozenTabId).catch(() => {});
      }
      sendResponse({ ok: true, tabId: newTab ? newTab.id : null });
    });
    return true;
  }

  if (message.type === "COMPANION_OPEN_TAB") {
    const targetUrl = message.url;
    if (targetUrl) {
      chrome.tabs.create({ url: targetUrl, active: true }, (tab) => {
        sendResponse({ ok: true, tabId: tab ? tab.id : null });
      });
      return true;
    }
    sendResponse({ ok: false, error: "Missing URL" });
    return false;
  }

  if (message.type === "COMPANION_ENSURE_EXTERNAL_TAB") {
    const targetUrl = String(message.url || "").trim();
    if (!targetUrl) {
      sendResponse({ ok: false, error: "Missing URL" });
      return false;
    }
    const senderTabId = sender && sender.tab ? sender.tab.id : null;
    let targetHost = "";
    let targetPath = "";
    try {
      const parsed = new URL(targetUrl);
      targetHost = (parsed.hostname || "").toLowerCase();
      targetPath = (parsed.pathname || "").toLowerCase();
    } catch (_) {}

    chrome.tabs.query({}, (tabs) => {
      const allTabs = tabs || [];
      const matchingTab = allTabs.find((t) => {
        if (!t || !t.id || t.id === senderTabId) return false;
        const rawU = String(t.pendingUrl || t.url || "");
        if (!rawU) return false;
        const lowU = rawU.toLowerCase();
        if (lowU === targetUrl.toLowerCase() || lowU.split("?")[0] === targetUrl.toLowerCase().split("?")[0]) {
          return true;
        }
        if (lowU.includes("linkedin.com/safety/go")) {
          return true;
        }
        if (targetHost && lowU.includes(targetHost) && (!targetPath || lowU.includes(targetPath))) {
          return true;
        }
        return false;
      });

      if (matchingTab && matchingTab.id) {
        chrome.tabs.update(matchingTab.id, { active: true }, () => {
          sendResponse({ ok: true, tabId: matchingTab.id, opened: false });
        });
      } else {
        chrome.tabs.create({ url: targetUrl, active: true }, (newTab) => {
          sendResponse({ ok: true, tabId: newTab ? newTab.id : null, opened: true });
        });
      }
    });
    return true;
  }

  if (message.type === "COMPANION_NAVIGATE") {
    const targetUrl = message.url;
    if (sender && sender.tab && sender.tab.id) {
      chrome.tabs.update(sender.tab.id, { url: targetUrl }, () => {
        sendResponse({ ok: true });
      });
    } else {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs && tabs[0] && tabs[0].id) {
          chrome.tabs.update(tabs[0].id, { url: targetUrl }, () => {
            sendResponse({ ok: true });
          });
        } else {
          chrome.tabs.create({ url: targetUrl }, () => {
            sendResponse({ ok: true });
          });
        }
      });
    }
    return true;
  }

  return false;
});
