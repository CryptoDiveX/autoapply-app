const ITEMS = [
  { id: "openrouter", title: "1. OpenRouter API Key", url: "https://openrouter.ai/settings/keys" },
  { id: "chatgpt", title: "2. ChatGPT Login (Optional)", url: "https://chatgpt.com/auth/login" },
  { id: "capsolver", title: "3. CapSolver Auto-Captcha", url: "https://dashboard.capsolver.com/passport/login" },
  { id: "gmail", title: "4. Gmail App-Specific Password", url: "https://myaccount.google.com/apppasswords" },
  { id: "teal", title: "5. Teal HQ Job Tracker", url: "https://app.tealhq.com/" },
  { id: "linkedin", title: "6. LinkedIn Session", url: "https://www.linkedin.com/login" },
];

function isItemDone(id, onb) {
  if (!onb) return false;
  const ai = onb.ai_config || {};
  const cg = onb.chatgpt_config || {};
  const gm = onb.gmail_config || {};
  const tl = onb.teal_config || {};
  const li = onb.linkedin_config || {};
  if (id === "openrouter") return Boolean(ai.openrouter_key_configured);
  if (id === "chatgpt") return Boolean(cg.connected);
  if (id === "capsolver") return Boolean(ai.capsolver_key_configured);
  if (id === "gmail") return Boolean(gm.connected);
  if (id === "teal") return Boolean(tl.session_connected);
  if (id === "linkedin") return Boolean(li.session_connected);
  return false;
}

function render(onb) {
  const list = document.getElementById("checklist");
  list.innerHTML = "";
  let doneCount = 0;
  ITEMS.forEach((item) => {
    const done = isItemDone(item.id, onb);
    if (done) doneCount++;
    const row = document.createElement("div");
    row.className = "item" + (done ? " done" : "");
    row.innerHTML = `
      <div class="item-left">
        <div class="check">${done ? "✓" : "•"}</div>
        <div class="item-title">${item.title}</div>
      </div>
      <div class="item-status">${done ? "✓ Validated" : "Open →"}</div>
    `;
    row.addEventListener("click", () => {
      chrome.tabs.create({ url: item.url });
      window.close();
    });
    list.appendChild(row);
  });
  const badge = document.getElementById("progress-badge");
  badge.textContent = `${doneCount}/${ITEMS.length} Validated`;
}

chrome.runtime.sendMessage({ type: "COMPANION_GET_STATE" }, (res) => {
  const state = (res && (res.data || res.cached)) || {};
  render(state.onboarding || {});
});

document.getElementById("toggle-panel-btn").addEventListener("click", () => {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs && tabs[0] && tabs[0].id) {
      chrome.tabs.reload(tabs[0].id);
    }
    window.close();
  });
});
