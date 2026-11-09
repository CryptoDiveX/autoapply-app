/**
 * AutoApply Companion — Main-World Native Browser Dialog Guard (`dialog_guard_main.js`)
 *
 * Injected at `document_start` in `world: "MAIN"` across `all_frames: true` so native
 * blocking JavaScript modal pop-ups (`window.alert`, `window.confirm`, `window.prompt`,
 * and `beforeunload`) never freeze the Chromium renderer thread during automated
 * prefill, multi-step navigation, or final application submission.
 */
(function installAutoApplyMainWorldDialogGuard() {
  if (typeof window === "undefined") return;
  if (window.__aaNativeDialogGuardInstalled) return;
  window.__aaNativeDialogGuardInstalled = true;

  const POLICY_ATTR = "data-aa-dialog-policy";
  const UNTIL_ATTR = "data-aa-automation-until";
  const LAST_DIALOG_ATTR = "data-aa-last-dialog";
  const SESSION_KEY = "__aa_dialog_policy_v1";

  const origAlert = typeof window.alert === "function" ? window.alert.bind(window) : () => {};
  const origConfirm = typeof window.confirm === "function" ? window.confirm.bind(window) : () => true;
  const origPrompt = typeof window.prompt === "function" ? window.prompt.bind(window) : (_m, d) => d ?? "";
  const origAddEventListener =
    typeof window.addEventListener === "function" ? window.addEventListener.bind(window) : null;

  window.__aaHandledDialogs = Array.isArray(window.__aaHandledDialogs) ? window.__aaHandledDialogs : [];
  window.__aaDialogPolicyState = { mode: "idle", until: 0 };

  const DESTRUCTIVE_RE =
    /\b(delete|remove|withdraw|discard|cancel\s+(?:your\s+|this\s+)?application|clear\s+(?:all|form|answers)|reset\s+form|unsubscribe|revoke|deactivate|close\s+account|leave\s+without\s+saving)\b/i;

  const SUBMIT_FINALITY_RE =
    /\b(ready\s+to\s+submit|cannot\s+be\s+changed\s+once\s+submitted|answers\s+cannot\s+be\s+changed|once\s+submitted|submit\s+(?:your\s+|this\s+|the\s+)?(?:application|form|answers|response)|confirm\s+submission|finalize\s+(?:your\s+)?(?:application|submission)|want\s+to\s+submit|proceed\s+with\s+submission)\b/i;

  const PROMPT_TOKEN_RE = /(?:type|enter|write|input)\s+["'`]([A-Za-z0-9 _-]{2,24})["'`]/i;

  function readActivePolicyMode() {
    const now = Date.now();
    if (
      window.__aaDialogPolicyState &&
      window.__aaDialogPolicyState.mode &&
      window.__aaDialogPolicyState.mode !== "idle" &&
      Number(window.__aaDialogPolicyState.until || 0) > now
    ) {
      return String(window.__aaDialogPolicyState.mode);
    }

    try {
      const root = document.documentElement;
      if (root) {
        const attrMode = (root.getAttribute(POLICY_ATTR) || "").trim().toLowerCase();
        const attrUntil = Number(root.getAttribute(UNTIL_ATTR) || "0");
        if (attrMode && attrMode !== "idle" && attrUntil > now) {
          return attrMode;
        }
      }
    } catch (_) {}

    try {
      const raw = window.sessionStorage && window.sessionStorage.getItem(SESSION_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && parsed.mode && parsed.mode !== "idle" && Number(parsed.until || 0) > now) {
          return String(parsed.mode).toLowerCase();
        }
      }
    } catch (_) {}

    return "idle";
  }

  function armDialogGuard(mode = "apply", durationMs = 60000) {
    const cleanMode = String(mode || "apply").trim().toLowerCase() || "apply";
    const until = Date.now() + Math.max(1000, Number(durationMs) || 60000);
    window.__aaDialogPolicyState = { mode: cleanMode, until };
    try {
      if (document.documentElement) {
        document.documentElement.setAttribute(POLICY_ATTR, cleanMode);
        document.documentElement.setAttribute(UNTIL_ATTR, String(until));
      }
    } catch (_) {}
    try {
      if (window.sessionStorage) {
        window.sessionStorage.setItem(SESSION_KEY, JSON.stringify({ mode: cleanMode, until }));
      }
    } catch (_) {}
    return { mode: cleanMode, until };
  }

  function disarmDialogGuard() {
    window.__aaDialogPolicyState = { mode: "idle", until: 0 };
    try {
      if (document.documentElement) {
        document.documentElement.setAttribute(POLICY_ATTR, "idle");
        document.documentElement.setAttribute(UNTIL_ATTR, "0");
      }
    } catch (_) {}
    try {
      if (window.sessionStorage) {
        window.sessionStorage.removeItem(SESSION_KEY);
      }
    } catch (_) {}
  }

  function isElementVisible(el) {
    if (!el || typeof el.getBoundingClientRect !== "function") return false;
    if (el.hidden || el.getAttribute("aria-hidden") === "true") return false;
    try {
      const style = window.getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) {
        return false;
      }
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    } catch (_) {
      return true;
    }
  }

  function hasUnansweredRequiredFormControls() {
    try {
      if (!document || !document.querySelectorAll) return false;

      // 1. Check required radio groups (including Greenhouse CandidateFacing.Form unnamed <fieldset> radios)
      const fieldsets = Array.from(document.querySelectorAll("fieldset, [role='radiogroup']"));
      let ghRequiredIds = new Set();
      const ghFormRoot = document.querySelector("[data-react-class='CandidateFacing.Form'][data-react-props]");
      if (ghFormRoot) {
        try {
          const props = JSON.parse(ghFormRoot.getAttribute("data-react-props") || "{}");
          for (const q of props.questions || []) {
            if (q && q.required) {
              if (q.id !== undefined && q.id !== null) ghRequiredIds.add(String(q.id));
              if (q.name_key) ghRequiredIds.add(String(q.name_key));
            }
          }
        } catch (_) {}
      }

      for (const fs of fieldsets) {
        if (!isElementVisible(fs)) continue;
        const radios = Array.from(fs.querySelectorAll("input[type='radio']")).filter((r) => !r.disabled);
        if (radios.length === 0) continue;
        const legendText = ((fs.querySelector("legend") && fs.querySelector("legend").innerText) || "").trim();
        const fsId = String(fs.id || "");
        const matchesGhRequired =
          ghRequiredIds.size > 0 &&
          (ghRequiredIds.has(fsId) || Array.from(ghRequiredIds).some((qid) => fsId.includes(qid)));
        const isGroupRequired =
          matchesGhRequired ||
          radios.some((r) => r.required || r.getAttribute("aria-required") === "true") ||
          fs.getAttribute("aria-required") === "true" ||
          legendText.includes("*") ||
          (ghFormRoot && ghRequiredIds.size > 0 && fieldsets.length === 1);
        if (isGroupRequired && !radios.some((r) => r.checked)) {
          return true;
        }
      }

      // 2. Check named required radio groups outside fieldsets
      const namedRequiredRadios = new Map();
      for (const r of Array.from(document.querySelectorAll("input[type='radio'][required], input[type='radio'][aria-required='true']"))) {
        if (r.disabled || !isElementVisible(r) || !r.name) continue;
        if (!namedRequiredRadios.has(r.name)) {
          namedRequiredRadios.set(r.name, []);
        }
        namedRequiredRadios.get(r.name).push(r);
      }
      for (const [, group] of namedRequiredRadios.entries()) {
        const allSameName = Array.from(
          document.querySelectorAll(`input[type="radio"][name="${CSS.escape(group[0].name)}"]`)
        );
        if (!allSameName.some((r) => r.checked)) {
          return true;
        }
      }
    } catch (_) {}
    return false;
  }

  function decideNativeDialog(type, message, defaultValue = "", explicitMode = "") {
    const msg = String(message ?? "").trim();
    const activeMode = (explicitMode || readActivePolicyMode() || "idle").toLowerCase();
    const isDestructive = DESTRUCTIVE_RE.test(msg) && !SUBMIT_FINALITY_RE.test(msg);
    const isSubmitFinality = SUBMIT_FINALITY_RE.test(msg);

    if (type === "alert") {
      return {
        intercept: true,
        outcome: undefined,
        accepted: true,
        reason: "auto_accepted_alert",
        mode: activeMode,
      };
    }

    if (type === "confirm") {
      const shouldIntercept =
        activeMode === "apply" ||
        activeMode === "prefill" ||
        activeMode === "auto" ||
        (typeof document !== "undefined" && document.readyState === "loading");

      if (!shouldIntercept) {
        return {
          intercept: false,
          outcome: null,
          accepted: false,
          reason: "passthrough_manual_confirm",
          mode: activeMode,
        };
      }

      if (isDestructive) {
        return {
          intercept: true,
          outcome: false,
          accepted: false,
          reason: "dismissed_destructive_confirm",
          mode: activeMode,
        };
      }

      if (activeMode === "prefill" && isSubmitFinality) {
        return {
          intercept: true,
          outcome: false,
          accepted: false,
          reason: "cancelled_submit_in_prefill_mode",
          mode: activeMode,
        };
      }

      if (isSubmitFinality && hasUnansweredRequiredFormControls()) {
        return {
          intercept: true,
          outcome: false,
          accepted: false,
          reason: "blocked_unanswered_required_controls",
          mode: activeMode,
        };
      }

      return {
        intercept: true,
        outcome: true,
        accepted: true,
        reason: isSubmitFinality ? "accepted_submit_finality_confirm" : "accepted_workflow_confirm",
        mode: activeMode,
      };
    }

    if (type === "prompt") {
      const shouldIntercept =
        activeMode === "apply" ||
        activeMode === "prefill" ||
        activeMode === "auto" ||
        (typeof document !== "undefined" && document.readyState === "loading");

      if (!shouldIntercept) {
        return {
          intercept: false,
          outcome: null,
          accepted: false,
          reason: "passthrough_manual_prompt",
          mode: activeMode,
        };
      }

      if (isDestructive) {
        return {
          intercept: true,
          outcome: null,
          accepted: false,
          reason: "dismissed_destructive_prompt",
          mode: activeMode,
        };
      }

      const tokenMatch = msg.match(PROMPT_TOKEN_RE);
      if (tokenMatch && tokenMatch[1]) {
        return {
          intercept: true,
          outcome: tokenMatch[1].trim(),
          accepted: true,
          reason: "accepted_prompt_token",
          mode: activeMode,
        };
      }

      const fallbackVal = defaultValue !== undefined && defaultValue !== null ? String(defaultValue) : "";
      return {
        intercept: true,
        outcome: fallbackVal,
        accepted: true,
        reason: "accepted_prompt_default",
        mode: activeMode,
      };
    }

    return {
      intercept: false,
      outcome: null,
      accepted: false,
      reason: "unknown_dialog_type",
      mode: activeMode,
    };
  }

  function recordHandledDialog(type, message, decision) {
    const entry = {
      type,
      message: String(message ?? "").slice(0, 500),
      accepted: Boolean(decision.accepted),
      reason: String(decision.reason || ""),
      mode: String(decision.mode || ""),
      url: String((window.location && window.location.href) || ""),
      ts: Date.now(),
    };
    try {
      window.__aaHandledDialogs.push(entry);
      if (window.__aaHandledDialogs.length > 40) {
        window.__aaHandledDialogs.splice(0, window.__aaHandledDialogs.length - 40);
      }
    } catch (_) {}
    try {
      if (document.documentElement) {
        document.documentElement.setAttribute(LAST_DIALOG_ATTR, JSON.stringify(entry));
      }
    } catch (_) {}
    try {
      window.dispatchEvent(new CustomEvent("aa:native-dialog-handled", { detail: entry }));
    } catch (_) {}
    return entry;
  }

  window.alert = function autoApplyGuardedAlert(message) {
    const decision = decideNativeDialog("alert", message);
    recordHandledDialog("alert", message, decision);
    return undefined;
  };

  window.confirm = function autoApplyGuardedConfirm(message) {
    const decision = decideNativeDialog("confirm", message);
    if (!decision.intercept) {
      return origConfirm(message);
    }
    recordHandledDialog("confirm", message, decision);
    return Boolean(decision.outcome);
  };

  window.prompt = function autoApplyGuardedPrompt(message, defaultValue) {
    const decision = decideNativeDialog("prompt", message, defaultValue);
    if (!decision.intercept) {
      return origPrompt(message, defaultValue);
    }
    recordHandledDialog("prompt", message, decision);
    return decision.outcome;
  };

  // Prevent `beforeunload` ("Leave site? Changes you made may not be saved.") from deadlocking automated navigation
  if (origAddEventListener) {
    window.addEventListener = function autoApplyGuardedAddEventListener(type, listener, options) {
      if (String(type).toLowerCase() === "beforeunload" && typeof listener === "function") {
        const wrappedBeforeUnload = function (ev) {
          const mode = readActivePolicyMode();
          if (mode === "apply" || mode === "prefill" || mode === "auto") {
            try {
              if (ev && typeof ev.stopImmediatePropagation === "function") {
                ev.stopImmediatePropagation();
              }
            } catch (_) {}
            return undefined;
          }
          return listener.apply(this, arguments);
        };
        return origAddEventListener(type, wrappedBeforeUnload, options);
      }
      return origAddEventListener(type, listener, options);
    };

    origAddEventListener("aa:arm-dialog-guard", (ev) => {
      const detail = (ev && ev.detail) || {};
      if (detail.mode === "idle" || detail.disarm) {
        disarmDialogGuard();
      } else {
        armDialogGuard(detail.mode || "apply", detail.durationMs || 60000);
      }
    });
  }

  try {
    let customOnBeforeUnload = null;
    Object.defineProperty(window, "onbeforeunload", {
      configurable: true,
      enumerable: true,
      get() {
        const mode = readActivePolicyMode();
        if (mode === "apply" || mode === "prefill" || mode === "auto") {
          return null;
        }
        return customOnBeforeUnload;
      },
      set(fn) {
        customOnBeforeUnload = typeof fn === "function" ? fn : null;
      },
    });
  } catch (_) {}

  window.__aaArmDialogGuard = armDialogGuard;
  window.__aaDisarmDialogGuard = disarmDialogGuard;
  window.__aaDecideNativeDialog = decideNativeDialog;
})();
