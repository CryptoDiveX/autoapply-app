/**
 * AutoApply Companion — In-Page Shadow DOM Content Script (`content.js`)
 * Repository: https://github.com/CryptoDiveX/autoapply-extension
 *
 * Responsibilities:
 * 1. Injects an isolated Shadow DOM sidebar (`#autoapply-companion-host`) into
 *    supported browser tabs without leaking CSS into the host page.
 * 2. Detects 35+ job boards and ATS platforms (`detectJobPageParameters`),
 *    extracts structured job metadata (`extractJobMetadataFromPage`) and form
 *    schemas (`extractApplicationFormSchema`), and performs 1-click form prefill
 *    including Resume + Cover Letter file uploads (`runPrefillOrApply`).
 * 3. Automates setup and authentication flows:
 *    - OpenAI Codex Device OAuth (`maybeAutoFillCodexDeviceCode`): handles
 *      `/choose-an-account`, `/sign-in-with-chatgpt/codex/consent`, and the
 *      9-character device code entry page (`/codex/device` & `/deviceauth/callback`)
 *      with human keystroke latency (90-145ms per character) and mouse click
 *      confirmation on the visible `Continue` button.
 *    - OpenRouter & CapSolver API key detection and 1-click save.
 *    - Google App Password creation & auto-capture.
 *    - LinkedIn & Teal authenticated session verification.
 */
(() => {
  // Child-frame ATS bridge for embedded cross-origin forms (Ashby, Greenhouse, Lever, Workable, etc.)
  if (window !== window.top) {
    const frameHost = (window.location.hostname || "").toLowerCase();
    const isAtsFrame = [
      "ashbyhq.com",
      "greenhouse.io",
      "lever.co",
      "workable.com",
      "bamboohr.com",
      "smartrecruiters.com",
      "recruitee.com",
      "jobvite.com",
      "icims.com",
      "myworkdayjobs.com",
    ].some((d) => frameHost === d || frameHost.endsWith("." + d));
    if (!isAtsFrame) return;
    if (window.__autoapplyChildFrameBridgeActive) return;
    window.__autoapplyChildFrameBridgeActive = true;

    const getClean = (el) => (el ? (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim() : "");

    const extractChildState = () => {
      let title = getClean(document.querySelector("h1.ashby-job-posting-heading, h1.app-title, h1"));
      let company_name = "";
      const docTitle = (document.title || "").trim();
      if (docTitle.includes(" @ ")) {
        const parts = docTitle.split(" @ ");
        if (!title || /^(work|careers|jobs)/i.test(title)) title = parts[0].trim();
        company_name = parts.slice(1).join(" @ ").trim();
      }
      const descEl = document.querySelector(".ashby-job-posting-brief-description, [data-testid='job-description'], #content, main");
      const description = descEl ? getClean(descEl).slice(0, 6000) : "";

      const applyTrigger = Array.from(document.querySelectorAll("button, a, [role='tab'], [role='button']")).find((el) => {
        const t = getClean(el);
        return /^(apply for this job|apply now|apply|application|start application)$/i.test(t);
      });

      const formFields = [];
      const ashbyDivs = Array.from(document.querySelectorAll("[data-field-entry-id]"));
      if (ashbyDivs.length > 0) {
        ashbyDivs.forEach((div, idx) => {
          const path = div.getAttribute("data-field-path") || `ashby_field_${idx}`;
          const label = getClean(div.querySelector(".ashby-application-form-question-title, label")) || path;
          const radioOpts = Array.from(div.querySelectorAll(".ashby-application-form-input-radio-group-option label")).map((l) => getClean(l)).filter(Boolean);
          const yesNoBtns = Array.from(div.querySelectorAll("button.ashby-application-form-input-yesno-option")).map((b) => getClean(b)).filter(Boolean);
          const options = radioOpts.length > 0 ? radioOpts : yesNoBtns;
          let type = "text";
          if (div.querySelector("input[type='file']")) type = "file";
          else if (div.querySelector("input[role='combobox']")) type = "combobox";
          else if (options.length > 0) type = "radio";
          else if (div.querySelector("textarea")) type = "textarea";
          formFields.push({
            field_id: path,
            field_key: path,
            id: path,
            name: path,
            label,
            type,
            tag: type === "textarea" ? "textarea" : "input",
            required: true,
            options,
          });
        });
      } else {
        Array.from(document.querySelectorAll("input:not([type='hidden']), textarea, select")).forEach((el, idx) => {
          if (el.name === "g-recaptcha-response" || el.closest(".ashby-application-form-autofill-input-root")) return;
          const id = el.id || el.name || `iframe_field_${idx}`;
          const lbl = el.id ? document.querySelector(`label[for="${CSS.escape(el.id)}"]`) : el.closest("label");
          formFields.push({
            field_id: id,
            field_key: id,
            id,
            name: el.name || id,
            label: getClean(lbl) || el.placeholder || id,
            type: (el.type || el.tagName).toLowerCase(),
            tag: el.tagName.toLowerCase(),
            required: Boolean(el.required),
            options: [],
          });
        });
      }

      return {
        __autoapplyChildFrame: true,
        frameUrl: window.location.href,
        title,
        company_name,
        description,
        hasApplyButton: Boolean(applyTrigger),
        formFields,
      };
    };

    const postChildState = () => {
      try {
        window.top.postMessage(extractChildState(), "*");
      } catch (_) {}
    };

    window.addEventListener("message", async (ev) => {
      const data = ev && ev.data;
      if (!data || !data.__autoapplyParentCmd) return;
      if (data.__autoapplyParentCmd === "OPEN_FORM") {
        const trigger = Array.from(document.querySelectorAll("button, a, [role='tab'], [role='button']")).find((el) => {
          const t = getClean(el);
          return /^(apply for this job|apply now|apply|application|start application)$/i.test(t);
        });
        if (trigger) {
          trigger.click();
          for (let i = 0; i < 10; i++) {
            await new Promise((r) => setTimeout(r, 350));
            const st = extractChildState();
            if (st.formFields && st.formFields.length >= 2) break;
          }
        }
        postChildState();
      }
    });

    postChildState();
    setInterval(postChildState, 1000);
    return;
  }

  // Never inject the Job Co-Pilot sidebar into webmail or Google Workspace apps (e.g. Gmail inbox/sent mail)
  const topHost = (window.location.hostname || "").toLowerCase();
  if (topHost.includes("linkedin.com") && (window.location.pathname || "").includes("/safety/go")) {
    try {
      const targetUrl = new URLSearchParams(window.location.search).get("url");
      if (targetUrl && /^https?:\/\//i.test(targetUrl)) {
        window.location.replace(targetUrl);
        return;
      }
    } catch (_) {}
  }
  const BLOCKED_COMPANION_HOSTS = [
    "mail.google.com",
    "inbox.google.com",
    "calendar.google.com",
    "drive.google.com",
    "docs.google.com",
    "mail.yahoo.com",
    "outlook.live.com",
    "outlook.office.com",
    "outlook.office365.com",
    "mail.proton.me",
  ];
  if (BLOCKED_COMPANION_HOSTS.some((d) => topHost === d || topHost.endsWith("." + d))) {
    const existingHost = document.getElementById("autoapply-companion-host");
    if (existingHost) existingHost.remove();
    if (document.documentElement) document.documentElement.style.marginRight = "";
    if (document.body) document.body.style.marginRight = "";
    return;
  }

  if (document.getElementById("autoapply-companion-host")) return;

  const host = document.createElement("div");
  host.id = "autoapply-companion-host";
  host.setAttribute("data-autoapply-companion", "ready");
  const shadow = host.attachShadow({ mode: "open" });

  let childFrameState = null;
  let crossTabJobHint = null;
  let currentApplicationIssue = null;
  const recordedIssueSignatures = new Set();
  const programmaticTypingSet = new WeakSet();
  const fieldIdWeakMap = new WeakMap();

  try {
    const savedTabHint = sessionStorage.getItem("aa_tab_job_hint");
    if (savedTabHint) {
      crossTabJobHint = JSON.parse(savedTabHint);
    }
  } catch (_) {}

  if (!window.location.hostname.toLowerCase().includes("linkedin.com") && typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
    try {
      chrome.storage.local.get(["aa_cross_tab_agent_action", "aa_last_linkedin_job_context"], (res) => {
        const act = res && res.aa_cross_tab_agent_action;
        const lastLi = res && res.aa_last_linkedin_job_context;
        const isFreshAgentAction = Boolean(act && act.startedAt && Date.now() - act.startedAt < 90000);
        const src =
          (isFreshAgentAction && act) ||
          (lastLi && lastLi.updatedAt && Date.now() - lastLi.updatedAt < 300000 && lastLi) ||
          null;
        if (src && (src.title || src.company_name)) {
          crossTabJobHint = {
            title: src.title || "",
            company_name: src.company_name || "",
            location: src.location || "Remote",
            description: src.description || "",
            isActiveAgentHandoff: isFreshAgentAction,
          };
          render();
        }
      });
    } catch (_) {}
  }

  window.addEventListener("message", (ev) => {
    const d = ev && ev.data;
    if (d && d.__autoapplyChildFrame) {
      const prevTitle = (childFrameState && childFrameState.title) || "";
      const prevDesc = (childFrameState && childFrameState.description) || "";
      childFrameState = {
        ...d,
        title: d.title || prevTitle,
        description: d.description && d.description.length > prevDesc.length ? d.description : prevDesc || d.description || "",
      };
    }
  });

  let isCollapsed = false;
  let activeTab = "copilot"; // "copilot" | "chat" | "setup"
  let userSelectedTab = false;
  let selectedFeedJobIndex = 0;
  let selectedBoardsFilter = "all"; // "all" | "operational" | "primary" | "ats"
  let bridgeState = null;
  let statusBanner = { text: "", kind: "ok" };
  let expandedItemId = null;
  let userSelectedAccordion = false;
  let lastAutoSavedGmPass = "";
  let lastCreateClickAt = 0;
  let autoResetLinkedInDone = false;
  let autoConfirmedLinkedInDone = false;
  let autoConfirmedTealDone = false;
  let autoConfirmedChatGPTDone = false;
  let autoFilledCodexDeviceCode = "";
  let isBusyWorking = false;
  let activeWorkingMode = ""; // "prefill" | "apply" | "chat" | ""
  let busyLabel = "";
  let busyButtonLabel = "";
  let lastPrefillSummary = null;
  let draftChatInput = "";
  let resumedPendingAgentOnce = false;
  let chatPinnedToBottom = true;
  let savedChatScrollTop = 0;
  let savedBodyScrollTop = 0;
  let lastRenderedStateSig = "";
  let lastChatMsgCount = 0;
  let manualFieldEdits = {};
  let isSavingKbEdits = false;
  let isKbEditsPreviewOpen = false;
  let isExtMicRecording = false;
  let isExtMicTranscribing = false;
  let extMicSeconds = 0;
  let extMicTimer = null;
  let extMicStream = null;
  let extMicAudioCtx = null;
  let extMicProcessor = null;
  let extMicPcmChunks = [];
  let preExtMicDraftText = "";
  let isExtMicLiveInFlight = false;

  // Complete catalog of all 56 Job Boards & Direct ATS Platforms from the AutoApply Desktop App
  // (23 Primary Job Boards & Remote Aggregators + 33 Direct ATS Platforms & Career Portals)
  const DESKTOP_JOB_BOARDS_CATALOG = [
    // --- Primary Job Boards & Remote Aggregators (23) ---
    { id: "linkedin", name: "LinkedIn Jobs", slug: "linkedin", domain: "linkedin.com", aliases: [], url: "https://www.linkedin.com/jobs/", auth_url: "https://www.linkedin.com/login", is_primary: true, requires_auth: true, operational: true, excluded: false, operational_note: "Easy Apply & Recruiter Outreach Ready", attention_reason: "Sign in to LinkedIn in AutoApply Browser to enable Easy Apply & Outreach" },
    { id: "hh", name: "HeadHunter (hh.ru)", slug: "hh", domain: "hh.ru", aliases: [], url: "https://hh.ru/", auth_url: "https://hh.ru/account/login", is_primary: true, requires_auth: true, operational: true, excluded: false, operational_note: "Logged-in Resume Profile & 1-Click Responses Ready", attention_reason: "Sign in & verify hh.ru resume visibility for 1-click responses" },
    { id: "welcometothejungle", name: "Welcome to the Jungle (Otta)", slug: "welcometothejungle", domain: "welcometothejungle.com", aliases: ["otta.com"], url: "https://www.welcometothejungle.com/en/jobs", auth_url: "https://app.welcometothejungle.com/login", is_primary: true, requires_auth: true, operational: false, excluded: false, operational_note: "Curated Tech & Remote Roles Operational", attention_reason: "Sign in to Welcome to the Jungle / Otta candidate profile" },
    { id: "theladders", name: "Ladders ($100K+ Club)", slug: "theladders", domain: "theladders.com", aliases: [], url: "https://www.theladders.com/jobs/searchresults-jobs?keywords=Product%20Manager&remoteFlags=Remote", auth_url: "https://www.theladders.com/login", is_primary: true, requires_auth: true, operational: false, excluded: false, operational_note: "Executive & Senior Remote Search Operational", attention_reason: "Sign in to Ladders account in AutoApply Browser" },
    { id: "weworkremotely", name: "We Work Remotely", slug: "weworkremotely", domain: "weworkremotely.com", aliases: [], url: "https://weworkremotely.com/", auth_url: "https://weworkremotely.com/login", is_primary: true, requires_auth: false, operational: false, excluded: false, operational_note: "Direct Remote Job Feed — No Login Required", attention_reason: "Verify We Work Remotely candidate preferences" },
    { id: "remotive", name: "Remotive", slug: "remotive", domain: "remotive.com", aliases: [], url: "https://remotive.com/", auth_url: "https://remotive.com/login", is_primary: true, requires_auth: false, operational: false, excluded: false, operational_note: "Direct Remote Tech Board — No Login Required", attention_reason: "Verify Remotive search filters" },
    { id: "dynamitejobs", name: "Dynamite Jobs", slug: "dynamitejobs", domain: "dynamitejobs.com", aliases: [], url: "https://dynamitejobs.com/remote-jobs", auth_url: "https://dynamitejobs.com/login", is_primary: true, requires_auth: false, operational: false, excluded: false, operational_note: "Remote-First Roles — Operational", attention_reason: "Sign in or verify Dynamite Jobs profile" },
    { id: "himalayas", name: "Himalayas", slug: "himalayas", domain: "himalayas.app", aliases: [], url: "https://himalayas.app/jobs", auth_url: "https://himalayas.app/login", is_primary: true, requires_auth: false, operational: false, excluded: false, operational_note: "Worldwide Remote Tech Directory — Operational", attention_reason: "Sign in to Himalayas candidate profile" },
    { id: "wellfound", name: "Wellfound (AngelList Talent)", slug: "wellfound", domain: "wellfound.com", aliases: ["angel.co"], url: "https://wellfound.com/jobs", auth_url: "https://wellfound.com/login", is_primary: true, requires_auth: true, operational: false, excluded: false, operational_note: "Startup & Founder Direct Apply Ready", attention_reason: "Requires Browser Sign-In & Cloudflare Security Verification" },
    { id: "workatastartup", name: "YC Work at a Startup", slug: "workatastartup", domain: "workatastartup.com", aliases: ["account.ycombinator.com", "ycombinator.com"], url: "https://www.workatastartup.com/", auth_url: "https://account.ycombinator.com/?continue=https%3A%2F%2Fwww.workatastartup.com%2F", is_primary: true, requires_auth: true, operational: false, excluded: false, operational_note: "Y Combinator Founder Direct Messaging Ready", attention_reason: "Requires Y Combinator Account Sign-In to message founders directly" },
    { id: "jobgether", name: "Jobgether", slug: "jobgether", domain: "jobgether.com", aliases: [], url: "https://jobgether.com/search-offers", auth_url: "https://jobgether.com/users/sign_in", is_primary: true, requires_auth: true, operational: false, excluded: false, operational_note: "Flexible & Remote Aggregator Ready", attention_reason: "Requires Jobgether Candidate Account Sign-In & Resume Upload" },
    { id: "indeed", name: "Indeed", slug: "indeed", domain: "indeed.com", aliases: [], url: "https://www.indeed.com/jobs?q=Product+Manager&l=Remote", auth_url: "https://secure.indeed.com/auth", is_primary: true, requires_auth: true, operational: false, excluded: false, operational_note: "Indeed Apply & Employer Redirects Ready", attention_reason: "Requires Indeed Account Sign-In & Cloudflare Session Verification" },
    { id: "glassdoor", name: "Glassdoor", slug: "glassdoor", domain: "glassdoor.com", aliases: [], url: "https://www.glassdoor.com/Job/index.htm", auth_url: "https://www.glassdoor.com/profile/login_input.htm", is_primary: true, requires_auth: true, operational: false, excluded: false, operational_note: "Glassdoor Easy Apply & Salary Insights Ready", attention_reason: "Requires Glassdoor Account Sign-In in Browser" },
    { id: "builtin", name: "Built In", slug: "builtin", domain: "builtin.com", aliases: [], url: "https://builtin.com/jobs/remote", auth_url: "https://builtin.com/login", is_primary: true, requires_auth: true, operational: false, excluded: false, operational_note: "Tech & AI Startup Job Board Ready", attention_reason: "Requires Built In Candidate Account Sign-In" },
    { id: "dice", name: "Dice", slug: "dice", domain: "dice.com", aliases: [], url: "https://www.dice.com/jobs?q=Product+Manager&filters.workplaceTypes=Remote", auth_url: "https://www.dice.com/dashboard/login", is_primary: true, requires_auth: true, operational: false, excluded: false, operational_note: "Dice Easy Apply Tech Profile Ready", attention_reason: "Requires Dice Candidate Profile Sign-In" },
    { id: "ziprecruiter", name: "ZipRecruiter", slug: "ziprecruiter", domain: "ziprecruiter.com", aliases: [], url: "https://www.ziprecruiter.com/Jobs/Remote-Product-Manager", auth_url: "https://www.ziprecruiter.com/authn/login", is_primary: true, requires_auth: true, operational: false, excluded: false, operational_note: "1-Click Apply Profile Ready", attention_reason: "Requires ZipRecruiter Account Sign-In for 1-Click Apply" },
    { id: "monster", name: "Monster", slug: "monster", domain: "monster.com", aliases: [], url: "https://www.monster.com/jobs/search?q=Product+Manager&where=remote", auth_url: "https://www.monster.com/profile/detail", is_primary: true, requires_auth: true, operational: false, excluded: false, operational_note: "Monster Quick Apply Ready", attention_reason: "Requires Monster Candidate Account Sign-In" },
    { id: "careerbuilder", name: "CareerBuilder", slug: "careerbuilder", domain: "careerbuilder.com", aliases: [], url: "https://www.careerbuilder.com/jobs?keywords=Product+Manager&location=Remote", auth_url: "https://www.careerbuilder.com/user/sign-in", is_primary: true, requires_auth: true, operational: false, excluded: false, operational_note: "CareerBuilder Quick Apply Ready", attention_reason: "Requires CareerBuilder Account Sign-In" },
    { id: "remoteok", name: "Remote OK", slug: "remoteok", domain: "remoteok.com", aliases: [], url: "https://remoteok.com/", auth_url: "https://remoteok.com/login", is_primary: true, requires_auth: false, operational: false, excluded: false, operational_note: "Global Remote Aggregator Ready", attention_reason: "Verify Remote OK direct apply preferences & filters" },
    { id: "jobicy", name: "Jobicy", slug: "jobicy", domain: "jobicy.com", aliases: [], url: "https://jobicy.com/jobs", auth_url: "https://jobicy.com/login", is_primary: true, requires_auth: false, operational: false, excluded: false, operational_note: "Curated Remote Tech Roles Ready", attention_reason: "Verify Jobicy account & remote role filters" },
    { id: "remoteonly", name: "RemoteOnly", slug: "remoteonly", domain: "remoteonly.io", aliases: [], url: "https://remoteonly.io/", auth_url: "https://remoteonly.io/", is_primary: true, requires_auth: false, operational: false, excluded: false, operational_note: "100% Remote Job Directory Ready", attention_reason: "Verify RemoteOnly search filters & regions" },
    { id: "arbeitnow", name: "Arbeitnow", slug: "arbeitnow", domain: "arbeitnow.com", aliases: [], url: "https://www.arbeitnow.com/", auth_url: "https://www.arbeitnow.com/", is_primary: true, requires_auth: false, operational: false, excluded: false, operational_note: "European & Remote Tech Board Ready", attention_reason: "Verify Arbeitnow EU/Remote search preferences" },
    { id: "dover", name: "Dover Startup Jobs", slug: "dover", domain: "dover.com", aliases: [], url: "https://app.dover.com/jobs", auth_url: "https://app.dover.com/login", is_primary: true, requires_auth: true, operational: false, excluded: false, operational_note: "Venture-Backed Startup Portal Ready", attention_reason: "Requires Dover Candidate Profile Sign-In" },
    // --- Direct ATS Platforms & Career Portals (33) ---
    { id: "greenhouse", name: "Greenhouse", slug: "greenhouse", domain: "greenhouse.io", aliases: [], url: "https://www.google.com/search?q=site:boards.greenhouse.io+%22Product+Manager%22+remote", auth_url: "https://my.greenhouse.io/users/sign_in", is_primary: false, requires_auth: false, operational: true, excluded: false, operational_note: "Direct ATS Autofill + Gmail Security Code Verification Active", attention_reason: "Verify Gmail security-code autofill for Greenhouse forms" },
    { id: "lever", name: "Lever", slug: "lever", domain: "lever.co", aliases: [], url: "https://www.google.com/search?q=site:jobs.lever.co+%22Product+Manager%22+remote", auth_url: "https://jobs.lever.co/", is_primary: false, requires_auth: false, operational: true, excluded: false, operational_note: "Direct 1-Page ATS Form Autofill & Resume Upload Active", attention_reason: "Verify Lever hCaptcha & form autofill settings" },
    { id: "ashby", name: "Ashby", slug: "ashby", domain: "ashbyhq.com", aliases: [], url: "https://www.google.com/search?q=site:jobs.ashbyhq.com+%22Product+Manager%22+remote", auth_url: "https://jobs.ashbyhq.com/", is_primary: false, requires_auth: false, operational: true, excluded: false, operational_note: "Direct Startup ATS Autofill Active", attention_reason: "Verify Ashby React form autofill defaults" },
    { id: "workable", name: "Workable", slug: "workable", domain: "workable.com", aliases: [], url: "https://www.google.com/search?q=site:apply.workable.com+%22Product+Manager%22+remote", auth_url: "https://my.workable.com/", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "Direct Workable Application Autofill Active", attention_reason: "Sign in to my.workable.com candidate profile (optional)" },
    { id: "teamtailor", name: "Teamtailor", slug: "teamtailor", domain: "teamtailor.com", aliases: [], url: "https://www.google.com/search?q=site:teamtailor.com+%22Product+Manager%22+remote", auth_url: "https://www.teamtailor.com/", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "Direct Career Portal Autofill Active", attention_reason: "Verify Teamtailor Connect profile defaults" },
    { id: "breezy", name: "Breezy HR", slug: "breezy", domain: "breezy.hr", aliases: [], url: "https://www.google.com/search?q=site:breezy.hr+%22Product+Manager%22+remote", auth_url: "https://breezy.hr/", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "Direct Breezy HR Form Autofill Active", attention_reason: "Verify Breezy HR questionnaire autofill defaults" },
    { id: "bamboohr", name: "BambooHR", slug: "bamboohr", domain: "bamboohr.com", aliases: [], url: "https://www.google.com/search?q=site:bamboohr.com/careers+%22Product+Manager%22", auth_url: "https://www.bamboohr.com/", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "Direct BambooHR Careers Autofill Active", attention_reason: "Verify BambooHR application form defaults" },
    { id: "pinpoint", name: "Pinpoint", slug: "pinpoint", domain: "pinpointhq.com", aliases: [], url: "https://www.google.com/search?q=site:pinpointhq.com+%22Product+Manager%22", auth_url: "https://www.pinpointhq.com/", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "Direct Pinpoint ATS Autofill Active", attention_reason: "Verify Pinpoint form prefill settings" },
    { id: "recruitee", name: "Recruitee", slug: "recruitee", domain: "recruitee.com", aliases: [], url: "https://www.google.com/search?q=site:recruitee.com+%22Product+Manager%22+remote", auth_url: "https://recruitee.com/", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "Direct Recruitee Career Form Autofill Active", attention_reason: "Verify Recruitee screening question defaults" },
    { id: "rippling", name: "Rippling ATS", slug: "rippling", domain: "rippling.com", aliases: ["ats.rippling.com"], url: "https://www.google.com/search?q=site:ats.rippling.com+%22Product+Manager%22+remote", auth_url: "https://ats.rippling.com/", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "Direct Rippling ATS Form Autofill Active", attention_reason: "Verify Rippling ATS application defaults" },
    { id: "workday", name: "Workday Careers", slug: "workday", domain: "myworkdayjobs.com", aliases: ["workday.com"], url: "https://www.google.com/search?q=site:myworkdayjobs.com+%22Product+Manager%22+remote", auth_url: "https://www.myworkdayjobs.com/", is_primary: false, requires_auth: true, operational: false, excluded: false, operational_note: "Per-Employer Workday Account & Autofill Ready", attention_reason: "Requires per-employer Workday candidate credentials in Password Manager" },
    { id: "smartrecruiters", name: "SmartRecruiters", slug: "smartrecruiters", domain: "smartrecruiters.com", aliases: [], url: "https://www.google.com/search?q=site:jobs.smartrecruiters.com+%22Product+Manager%22+remote", auth_url: "https://my.smartrecruiters.com/", is_primary: false, requires_auth: true, operational: false, excluded: false, operational_note: "SmartRecruiters 1-Click Candidate Portal Ready", attention_reason: "Sign in to my.smartrecruiters.com candidate portal in Browser" },
    { id: "join", name: "JOIN", slug: "join", domain: "join.com", aliases: [], url: "https://www.google.com/search?q=site:join.com/companies+%22Product+Manager%22", auth_url: "https://join.com/auth/login", is_primary: false, requires_auth: true, operational: false, excluded: false, operational_note: "JOIN European ATS Candidate Profile Ready", attention_reason: "Sign in to join.com candidate account for fast applications" },
    { id: "icims", name: "iCIMS Talent Cloud", slug: "icims", domain: "icims.com", aliases: [], url: "https://www.google.com/search?q=site:icims.com+%22Product+Manager%22+remote", auth_url: "https://www.icims.com/", is_primary: false, requires_auth: true, operational: false, excluded: false, operational_note: "Enterprise iCIMS Portal Autofill Ready", attention_reason: "Requires per-employer iCIMS candidate portal login" },
    { id: "eightfold", name: "Eightfold AI Talent Network", slug: "eightfold", domain: "eightfold.ai", aliases: [], url: "https://www.google.com/search?q=site:eightfold.ai+%22Product+Manager%22+remote", auth_url: "https://eightfold.ai/", is_primary: false, requires_auth: true, operational: false, excluded: false, operational_note: "Eightfold AI Resume Match & Apply Ready", attention_reason: "Requires employer Eightfold talent profile verification" },
    { id: "taleo", name: "Oracle Taleo", slug: "taleo", domain: "taleo.net", aliases: [], url: "https://www.google.com/search?q=site:taleo.net+%22Product+Manager%22+remote", auth_url: "https://www.oracle.com/human-capital-management/taleo/", is_primary: false, requires_auth: true, operational: false, excluded: false, operational_note: "Enterprise Taleo Portal Autofill Ready", attention_reason: "Requires per-employer Taleo candidate portal credentials" },
    { id: "successfactors", name: "SAP SuccessFactors", slug: "successfactors", domain: "successfactors.com", aliases: [], url: "https://www.google.com/search?q=site:successfactors.com+%22Product+Manager%22+remote", auth_url: "https://www.sap.com/products/hcm.html", is_primary: false, requires_auth: true, operational: false, excluded: false, operational_note: "Enterprise SAP Career Portal Ready", attention_reason: "Requires per-employer SAP SuccessFactors candidate profile" },
    { id: "dayforce", name: "Dayforce HCM", slug: "dayforce", domain: "dayforcehcm.com", aliases: ["dayforce.com"], url: "https://www.google.com/search?q=site:dayforcehcm.com+%22Product+Manager%22+remote", auth_url: "https://www.dayforce.com/", is_primary: false, requires_auth: true, operational: false, excluded: false, operational_note: "Dayforce Recruiting Portal Ready", attention_reason: "Requires per-employer Dayforce candidate login" },
    { id: "ukg", name: "UKG / UltiPro Recruiting", slug: "ukg", domain: "ukg.net", aliases: ["ultipro.com", "ukg.com"], url: "https://www.google.com/search?q=site:recruiting.ultipro.com+%22Product+Manager%22+remote", auth_url: "https://www.ukg.com/", is_primary: false, requires_auth: true, operational: false, excluded: false, operational_note: "UKG Pro Recruiting Autofill Ready", attention_reason: "Requires per-employer UKG / UltiPro candidate login" },
    { id: "personio", name: "Personio", slug: "personio", domain: "personio.com", aliases: ["personio.de"], url: "https://www.google.com/search?q=site:jobs.personio.de+%22Product+Manager%22", auth_url: "https://www.personio.com/", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "European Personio Career Portal Ready", attention_reason: "Configure European GDPR consent & document defaults" },
    { id: "jobvite", name: "Jobvite", slug: "jobvite", domain: "jobvite.com", aliases: [], url: "https://www.google.com/search?q=site:jobs.jobvite.com+%22Product+Manager%22", auth_url: "https://my.jobvite.com/", is_primary: false, requires_auth: true, operational: false, excluded: false, operational_note: "Jobvite Candidate Portal Ready", attention_reason: "Sign in to my.jobvite.com candidate portal" },
    { id: "comeet", name: "Comeet", slug: "comeet", domain: "comeet.com", aliases: ["comeet.co"], url: "https://www.google.com/search?q=site:comeet.com/jobs+%22Product+Manager%22", auth_url: "https://www.comeet.com/", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "Comeet Direct ATS Autofill Ready", attention_reason: "Verify Comeet career portal form defaults" },
    { id: "gem", name: "Gem Jobs", slug: "gem", domain: "gem.com", aliases: ["jobs.gem.com"], url: "https://www.google.com/search?q=site:jobs.gem.com+%22Product+Manager%22", auth_url: "https://www.gem.com/", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "Gem Startup ATS Autofill Ready", attention_reason: "Verify Gem Jobs application form defaults" },
    { id: "peopleforce", name: "PeopleForce", slug: "peopleforce", domain: "peopleforce.io", aliases: [], url: "https://www.google.com/search?q=site:peopleforce.io+%22Product+Manager%22", auth_url: "https://peopleforce.io/", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "PeopleForce ATS Autofill Ready", attention_reason: "Verify PeopleForce regional & form defaults" },
    { id: "zohorecruit", name: "Zoho Recruit", slug: "zohorecruit", domain: "zohorecruit.com", aliases: ["zoho.com"], url: "https://www.google.com/search?q=site:zohorecruit.com+%22Product+Manager%22", auth_url: "https://www.zoho.com/recruit/login.html", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "Zoho Recruit Candidate Portal Ready", attention_reason: "Verify Zoho Recruit candidate portal preferences" },
    { id: "manatal", name: "Manatal", slug: "manatal", domain: "manatal.com", aliases: [], url: "https://www.google.com/search?q=site:apply.manatal.com+%22Product+Manager%22", auth_url: "https://www.manatal.com/", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "Manatal Career Page Autofill Ready", attention_reason: "Verify Manatal application form defaults" },
    { id: "recruiterflow", name: "Recruiterflow", slug: "recruiterflow", domain: "recruiterflow.com", aliases: [], url: "https://www.google.com/search?q=site:recruiterflow.com+%22Product+Manager%22", auth_url: "https://recruiterflow.com/", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "Recruiterflow Portal Autofill Ready", attention_reason: "Verify Recruiterflow agency portal rules" },
    { id: "jobdiva", name: "JobDiva", slug: "jobdiva", domain: "jobdiva.com", aliases: [], url: "https://www.google.com/search?q=site:jobdiva.com+%22Product+Manager%22", auth_url: "https://www.jobdiva.com/", is_primary: false, requires_auth: true, operational: false, excluded: false, operational_note: "JobDiva Candidate Portal Ready", attention_reason: "Requires JobDiva candidate portal credentials" },
    { id: "keka", name: "Keka HR", slug: "keka", domain: "keka.com", aliases: [], url: "https://www.google.com/search?q=site:keka.com/careers+%22Product+Manager%22", auth_url: "https://www.keka.com/", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "Keka Career Portal Autofill Ready", attention_reason: "Verify Keka career portal form defaults" },
    { id: "jazzhr", name: "JazzHR (ApplyToJob)", slug: "jazzhr", domain: "jazzhr.com", aliases: ["applytojob.com"], url: "https://www.google.com/search?q=site:applytojob.com+%22Product+Manager%22", auth_url: "https://www.jazzhr.com/", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "JazzHR / ApplyToJob Form Autofill Ready", attention_reason: "Verify JazzHR applytojob.com form defaults" },
    { id: "paylocity", name: "Paylocity Recruiting", slug: "paylocity", domain: "paylocity.com", aliases: [], url: "https://www.google.com/search?q=site:recruiting.paylocity.com+%22Product+Manager%22+remote", auth_url: "https://recruiting.paylocity.com/", is_primary: false, requires_auth: true, operational: false, excluded: false, operational_note: "Paylocity Recruiting Portal Ready", attention_reason: "Requires Paylocity candidate portal verification" },
    { id: "gusto", name: "Gusto Hiring", slug: "gusto", domain: "gusto.com", aliases: ["jobs.gusto.com"], url: "https://www.google.com/search?q=site:jobs.gusto.com+%22Product+Manager%22+remote", auth_url: "https://app.gusto.com/login", is_primary: false, requires_auth: false, operational: false, excluded: false, operational_note: "Gusto Direct Job Board Autofill Ready", attention_reason: "Verify Gusto hiring portal defaults" },
    { id: "avature", name: "Avature Enterprise ATS", slug: "avature", domain: "avature.net", aliases: [], url: "https://www.google.com/search?q=site:avature.net+%22Product+Manager%22+remote", auth_url: "https://www.avature.net/", is_primary: false, requires_auth: true, operational: false, excluded: false, operational_note: "Avature Talent Portal Autofill Ready", attention_reason: "Requires per-employer Avature talent portal login" },
  ];

  // Additional ATS / job domains
  const KNOWN_JOB_HOSTS = Array.from(
    new Set([
      ...DESKTOP_JOB_BOARDS_CATALOG.flatMap((b) => [b.domain, ...(b.aliases || [])]),
      "brassring.com",
      "careerpuck.com",
      "app.careerpuck.com",
      "polymer.co",
      "fountain.com",
      "rippling-ats.com",
      "dawnjobapp.com",
      "djinni.co",
      "dou.ua",
      "habr.com",
      "coda.io",
      "docs.superhuman.com",
      "superhuman.com",
      "hrpartner.io",
      "typeform.com",
      "tally.so",
      "airtable.com",
      "jotform.com",
      "micro1.ai",
    ])
  );

  function getResolvedJobBoardsCatalog() {
    const liveBoards = (bridgeState && Array.isArray(bridgeState.job_boards) && bridgeState.job_boards) || [];
    const liveById = new Map();
    for (const lb of liveBoards) {
      if (lb && lb.id) {
        liveById.set(String(lb.id).toLowerCase(), lb);
      }
    }
    return DESKTOP_JOB_BOARDS_CATALOG.map((base) => {
      const live = liveById.get(base.id);
      if (!live) return { ...base };
      return {
        ...base,
        name: live.name || base.name,
        domain: live.domain || base.domain,
        url: live.url || base.url,
        auth_url: live.auth_url || base.auth_url,
        is_primary: typeof live.is_primary === "boolean" ? live.is_primary : base.is_primary,
        requires_auth: typeof live.requires_auth === "boolean" ? live.requires_auth : base.requires_auth,
        operational: typeof live.operational === "boolean" ? live.operational : base.operational,
        excluded: Boolean(live.excluded),
        operational_note: live.operational_note || base.operational_note,
        attention_reason: live.attention_reason || base.attention_reason,
      };
    });
  }

  function findMatchingDesktopJobBoard(hostname, fullUrl) {
    const h = String(hostname || window.location.hostname || "").toLowerCase();
    const u = String(fullUrl || window.location.href || "").toLowerCase();
    if (!h) return null;
    const catalog = getResolvedJobBoardsCatalog();
    for (const board of catalog) {
      const domains = [board.domain, ...(board.aliases || [])].filter(Boolean).map((d) => d.toLowerCase());
      for (const dom of domains) {
        if (dom === "zoho.com") {
          if ((h === "zoho.com" || h.endsWith(".zoho.com")) && u.includes("/recruit")) {
            return board;
          }
          continue;
        }
        if (dom === "ycombinator.com") {
          if (h === "account.ycombinator.com" || u.includes("workatastartup")) {
            return board;
          }
          continue;
        }
        if (h === dom || h.endsWith("." + dom)) {
          return board;
        }
      }
    }
    return null;
  }

  function getValidatedCrossTabJobHint() {
    if (!crossTabJobHint || (!crossTabJobHint.title && !crossTabJobHint.company_name)) {
      return null;
    }
    if (isUnauthenticatedAuthPage()) {
      return null;
    }
    const matchedBoard = findMatchingDesktopJobBoard();
    // Never leak cross-tab job context onto any Primary Job Board (e.g. hh.ru, Indeed, Glassdoor, LinkedIn, Wellfound, etc.)
    if (matchedBoard && matchedBoard.is_primary) {
      try {
        sessionStorage.removeItem("aa_tab_job_hint");
      } catch (_) {}
      return null;
    }
    const hintedCompany = String(crossTabJobHint.company_name || "")
      .trim()
      .toLowerCase();
    if (!hintedCompany || hintedCompany === "target company" || hintedCompany === "employer" || hintedCompany === "company") {
      return null;
    }
    const companyToken = hintedCompany
      .replace(/[^a-z0-9\u0400-\u04ff\s]/gi, " ")
      .split(/\s+/)
      .filter((w) => w.length >= 3)[0] || hintedCompany;
    const pageHaystack = (
      (window.location.href || "") +
      " " +
      (document.title || "") +
      " " +
      ((document.body && document.body.innerText) || "").slice(0, 4000)
    ).toLowerCase();
    if (companyToken && pageHaystack.includes(companyToken)) {
      return crossTabJobHint;
    }
    if (crossTabJobHint.isActiveAgentHandoff && document.querySelectorAll("input, textarea, select").length >= 3) {
      return crossTabJobHint;
    }
    return null;
  }

  const JOB_URL_PATH_PATTERNS = [
    /\/jobs?\b/i,
    /\/careers?\b/i,
    /\/positions?\b/i,
    /\/openings?\b/i,
    /\/vacanc(?:y|ies)\b/i,
    /\/apply\b/i,
    /\/applyjob\b/i,
    /\/jobsign\b/i,
    /\/job\/post\b/i,
    /\/application\b/i,
    /\/application_form\b/i,
    /\/forms?\b/i,
    /\/questionnaires?\b/i,
    /\/requisitions?\b/i,
    /\/opportunities\b/i,
    /\/roles?\b/i,
    /\/join-us\b/i,
    /\/work-with-us\b/i,
    /\/linkedin\/\d+/i,
  ];

  const JOB_URL_QUERY_PATTERNS = [
    /[?&]gh_jid=/i,
    /[?&]ashby_jid=/i,
    /[?&]job_?id=/i,
    /[?&]vacancy_?id=/i,
    /[?&]req_?id=/i,
    /[?&]requisition_?id=/i,
    /[?&]posting_?id=/i,
    /[?&]currentJobId=/i,
    /[?&]vjk=/i,
    /[?&]jk=/i,
    /[?&]jl=/i,
    /[?&]src=linkedin\b/i,
  ];

  function detectJobPageParameters() {
    const u = (window.location.href || "").toLowerCase();
    const hostName = (window.location.hostname || "").toLowerCase();
    const pathName = (window.location.pathname || "").toLowerCase();
    const searchStr = (window.location.search || "").toLowerCase();

    // Never classify setup/auth provider pages as job application pages
    if (
      hostName.includes("openrouter.ai") ||
      hostName.includes("capsolver.com") ||
      hostName.includes("chatgpt.com") ||
      hostName.includes("openai.com") ||
      (hostName.includes("google.com") && !searchStr.includes("site:")) ||
      hostName.includes("tealhq.com")
    ) {
      return { isJobPage: false, isAuthPage: isUnauthenticatedAuthPage(), reason: "setup_provider", matchedBoard: null };
    }

    const matchedBoard = findMatchingDesktopJobBoard(hostName, u);
    const onAuthPage = isUnauthenticatedAuthPage();

    // Never classify any login / sign-in / registration page as a job posting page!
    if (onAuthPage) {
      return {
        isJobPage: false,
        isAuthPage: true,
        reason: "auth_page",
        platform: (matchedBoard && matchedBoard.name) || hostName || "Sign In",
        matchedBoard,
      };
    }

    if (hostName.includes("linkedin.com")) {
      const feedCards = extractJobCardsFromFeed();
      const specificOpen = isSpecificJobDetailOpen();
      if (pathName.includes("/jobs") && (specificOpen || feedCards.length > 0)) {
        return {
          isJobPage: true,
          isAuthPage: false,
          platform: "LinkedIn Jobs",
          matchedBoard,
          hasUrlMatch: true,
        };
      }
      return {
        isJobPage: false,
        isAuthPage: false,
        reason: "linkedin_non_job",
        platform: "LinkedIn Jobs",
        matchedBoard,
      };
    }

    const matchedHost = KNOWN_JOB_HOSTS.find((h) => hostName === h || hostName.endsWith("." + h));
    const hasPathMatch = JOB_URL_PATH_PATTERNS.some((re) => re.test(pathName));
    const hasQueryMatch = JOB_URL_QUERY_PATTERNS.some((re) => re.test(searchStr));

    // Check DOM parameters: JSON-LD JobPosting, ATS iframes, resume file upload input, or apply buttons
    let hasJsonLdJobPosting = false;
    try {
      const ldScripts = document.querySelectorAll('script[type="application/ld+json"]');
      for (const s of ldScripts) {
        const txt = s.textContent || "";
        if (txt.includes('"JobPosting"') || txt.includes("'JobPosting'")) {
          hasJsonLdJobPosting = true;
          break;
        }
      }
    } catch (_) {}

    let hasAtsIframe = false;
    try {
      const iframes = document.querySelectorAll("iframe[src]");
      for (const f of iframes) {
        const src = (f.getAttribute("src") || "").toLowerCase();
        if (
          src.includes("greenhouse.io") ||
          src.includes("lever.co") ||
          src.includes("ashbyhq.com") ||
          src.includes("workable.com") ||
          src.includes("bamboohr.com") ||
          src.includes("smartrecruiters.com") ||
          src.includes("jobvite.com") ||
          src.includes("recruitee.com") ||
          src.includes("personio") ||
          src.includes("icims.com")
        ) {
          hasAtsIframe = true;
          break;
        }
      }
    } catch (_) {}

    let hasResumeFileInput = false;
    try {
      const fileInputs = document.querySelectorAll('input[type="file"]');
      for (const inp of fileInputs) {
        const meta = (
          (inp.name || "") +
          " " +
          (inp.id || "") +
          " " +
          (inp.getAttribute("aria-label") || "") +
          " " +
          (inp.closest("label")?.innerText || "") +
          " " +
          (inp.parentElement?.innerText || "")
        ).toLowerCase();
        if (
          meta.includes("resume") ||
          meta.includes("cv") ||
          meta.includes("cover") ||
          meta.includes("upload") ||
          meta.includes("attach") ||
          meta.includes("резюме") ||
          fileInputs.length >= 1
        ) {
          hasResumeFileInput = true;
          break;
        }
      }
    } catch (_) {}

    let hasApplyFormOrButton = false;
    try {
      if (document.querySelectorAll(".kr-cell, [data-coda-ui-id='cellView']").length >= 2) {
        hasApplyFormOrButton = true;
      } else {
        const buttons = document.querySelectorAll('button, input[type="submit"], a[role="button"], [role="button"], a[href*="apply"], a[data-qa*="vacancy-response"]');
        for (const b of buttons) {
          const t = (b.innerText || b.value || b.textContent || "").trim().toLowerCase();
          if (
            t === "apply" ||
            t === "apply now" ||
            t === "apply for this job" ||
            t === "submit application" ||
            t === "easy apply" ||
            t === "send application" ||
            t === "submit" ||
            t === "откликнуться"
          ) {
            hasApplyFormOrButton = true;
            break;
          }
        }
      }
    } catch (_) {}

    const specificJobOpen = isSpecificJobDetailOpen();
    const feedCards = extractJobCardsFromFeed();
    const validCrossTab = getValidatedCrossTabJobHint();
    const hasCrossTabJobContext = Boolean(validCrossTab && (validCrossTab.title || validCrossTab.company_name));

    let isJobPage = false;
    if (matchedBoard && matchedBoard.is_primary) {
      // On Primary Job Boards (e.g. hh.ru, Indeed, Glassdoor, Wellfound, Ladders, WeWorkRemotely, etc.),
      // require an actual job detail page, job search feed cards, JSON-LD JobPosting, or resume upload form!
      isJobPage = Boolean(
        specificJobOpen ||
          feedCards.length > 0 ||
          hasJsonLdJobPosting ||
          hasResumeFileInput
      );
    } else if (matchedBoard && !matchedBoard.is_primary) {
      // On Direct ATS Platforms (Greenhouse, Lever, Ashby, Workable, Workday, etc.),
      // require that we're not on the bare marketing homepage and have a job path, query, feed, or form.
      const isBareMarketingRoot =
        (pathName === "/" || pathName === "" || /^\/(pricing|about|product|customers|contact|blog|resources)\b/i.test(pathName)) &&
        !hasQueryMatch &&
        !hasJsonLdJobPosting &&
        !hasResumeFileInput &&
        feedCards.length === 0;
      isJobPage = !isBareMarketingRoot && Boolean(
        specificJobOpen ||
          feedCards.length > 0 ||
          hasJsonLdJobPosting ||
          hasQueryMatch ||
          hasPathMatch ||
          hasResumeFileInput ||
          hasApplyFormOrButton
      );
    } else {
      isJobPage = Boolean(
        hasJsonLdJobPosting ||
          hasAtsIframe ||
          hasQueryMatch ||
          hasCrossTabJobContext ||
          (matchedHost && (specificJobOpen || feedCards.length > 0 || hasResumeFileInput || hasApplyFormOrButton)) ||
          (hasPathMatch && (hasResumeFileInput || hasApplyFormOrButton || hasJsonLdJobPosting || feedCards.length > 0)) ||
          (hasResumeFileInput && hasApplyFormOrButton)
      );
    }

    return {
      isJobPage,
      isAuthPage: false,
      matchedBoard,
      platform:
        (matchedBoard && matchedBoard.name) ||
        matchedHost ||
        (hasJsonLdJobPosting
          ? "Schema JobPosting"
          : hasPathMatch || hasCrossTabJobContext
            ? "Career Portal"
            : "Web Page"),
      hasUrlMatch: Boolean(matchedBoard || matchedHost || hasPathMatch || hasQueryMatch || hasCrossTabJobContext),
      hasResumeFileInput,
      hasApplyFormOrButton,
    };
  }

  function detectContext(urlStr) {
    const u = (urlStr || window.location.href || "").toLowerCase();
    if (u.includes("openrouter.ai")) return "openrouter";
    if (u.includes("capsolver.com")) return "capsolver";
    if (u.includes("chatgpt.com") || u.includes("openai.com")) return "chatgpt";
    if (u.includes("myaccount.google.com/apppasswords")) return "gmail_app_password";
    if (u.includes("accounts.google.com") || u.includes("myaccount.google.com")) return "gmail_app_password";
    if (u.includes("tealhq.com")) return "teal";
    if (u.includes("linkedin.com")) {
      if (
        u.includes("/authwall") ||
        u.includes("/login") ||
        u.includes("/signup") ||
        u.includes("/sign-up") ||
        u.includes("/uas/") ||
        u.includes("/checkpoint") ||
        u.includes("sessionredirect=")
      ) {
        return "linkedin";
      }
      if (u.includes("linkedin.com/jobs")) {
        return isUnauthenticatedAuthPage() ? "linkedin" : "job_board";
      }
      return "linkedin";
    }
    const jobParams = detectJobPageParameters();
    if (jobParams.isJobPage || jobParams.matchedBoard) {
      return "job_board";
    }
    return "general";
  }

  function isUnauthenticatedAuthPage() {
    const href = (window.location.href || "").toLowerCase();
    const hostName = (window.location.hostname || "").toLowerCase();
    const path = (window.location.pathname || "").toLowerCase();
    if (
      path.includes("/sign-up") ||
      path.includes("/signup") ||
      path.includes("/sign_up") ||
      path.includes("/login") ||
      path.includes("/sign-in") ||
      path.includes("/signin") ||
      path.includes("/sign_in") ||
      path.includes("/account/login") ||
      path.includes("/authn/login") ||
      path.includes("/auth/login") ||
      path.includes("/users/sign_in") ||
      path.includes("/user/sign-in") ||
      path.includes("/dashboard/login") ||
      path.includes("/profile/login") ||
      path.includes("/uas/login") ||
      path.includes("/authwall") ||
      path.includes("/checkpoint") ||
      path.includes("/reg/") ||
      path.includes("/register") ||
      path.includes("/registration") ||
      path.includes("/forgot-password") ||
      path.includes("/reset-password") ||
      href.includes("sessionredirect=") ||
      hostName === "account.ycombinator.com" ||
      (hostName === "secure.indeed.com" && path.startsWith("/auth"))
    ) {
      return true;
    }
    const title = (document.title || "").toLowerCase();
    if (
      title.includes("sign in") ||
      title.includes("sign up") ||
      title.includes("log in") ||
      title.includes("join linkedin") ||
      title.includes("вход в личный кабинет") ||
      title.includes("вход на сайт") ||
      title === "вход" ||
      title.startsWith("вход —") ||
      title.startsWith("вход -") ||
      title.startsWith("войти")
    ) {
      return true;
    }
    const h1Text = (document.querySelector("main h1, h1, h2")?.innerText || "").replace(/\s+/g, " ").trim();
    if (
      /^(sign\s*in|log\s*in|login|sign\s*up|create\s+an?\s+account|register|вход|войти|войдите(?:\s+в\s+аккаунт)?|вход\s+в\s+личный\s+кабинет|регистрация|зарегистрироваться|авторизация|connexion|se\s+connecter|anmelden|iniciar\s+sesi[oó]n)$/i.test(
        h1Text
      )
    ) {
      return true;
    }
    const pwInputs = Array.from(document.querySelectorAll('input[type="password"]')).filter(
      (el) => el && el.offsetParent !== null
    );
    const hasFileInputs = document.querySelectorAll('input[type="file"]').length > 0;
    if (pwInputs.length > 0 && !hasFileInputs && !href.includes("myaccount.google.com/apppasswords")) {
      return true;
    }
    const bodyText = ((document.body && document.body.innerText) || "").slice(0, 2000);
    if (
      (bodyText.includes("Join LinkedIn") && bodyText.includes("Agree & Join")) ||
      (bodyText.includes("Welcome to your professional community") && bodyText.includes("Sign in"))
    ) {
      return true;
    }
    return false;
  }

  function isAuthenticatedLinkedInPage() {
    if (!window.location.hostname.toLowerCase().includes("linkedin.com")) return false;
    if (isUnauthenticatedAuthPage()) return false;
    const path = (window.location.pathname || "").toLowerCase();
    if (
      path.startsWith("/feed") ||
      path.startsWith("/mynetwork") ||
      path.startsWith("/messaging") ||
      path.startsWith("/notifications") ||
      path.startsWith("/in/") ||
      path.startsWith("/jobs")
    ) {
      return true;
    }
    if (
      document.querySelector(".global-nav__me, .global-nav__me-photo, .feed-identity-module, [data-control-name='identity_welcome_message']")
    ) {
      return true;
    }
    const bodyText = ((document.body && document.body.innerText) || "").slice(0, 2500);
    if (bodyText.includes("Start a post") || bodyText.includes("My Network") || bodyText.includes("Profile viewers")) {
      return true;
    }
    return false;
  }

  function isAuthenticatedTealPage() {
    if (!window.location.hostname.toLowerCase().includes("app.tealhq.com")) return false;
    if (isUnauthenticatedAuthPage()) return false;
    const path = (window.location.pathname || "").toLowerCase().replace(/\/+$/, "");
    if (path && !["", "/", "/login", "/sign-in", "/signin", "/sign-up", "/signup", "/register", "/auth"].includes(path)) {
      return true;
    }
    return false;
  }

  function isAuthenticatedChatGPTPage() {
    const hostName = window.location.hostname.toLowerCase();
    if (!hostName.includes("chatgpt.com") && !hostName.includes("chat.openai.com")) return false;
    if (isUnauthenticatedAuthPage()) return false;
    if (document.querySelector("#prompt-textarea, [data-testid='profile-button'], nav")) {
      const bodyText = ((document.body && document.body.innerText) || "").slice(0, 1200);
      if (!bodyText.includes("Log in") && !bodyText.includes("Sign up for free")) {
        return true;
      }
    }
    return false;
  }

  let requestedCodexDeviceCodeOnce = false;
  let isTypingCodexDeviceCode = false;
  let autoClickedCodexConsent = false;
  let autoClickedCodexChooseAcct = false;

  function typeCharIntoReactBox(el, ch) {
    if (!el || !ch) return;
    try {
      const rect = el.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      el.dispatchEvent(new MouseEvent("mousemove", { bubbles: true, clientX: cx, clientY: cy }));
      el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, clientX: cx, clientY: cy }));
      el.focus();
      el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, clientX: cx, clientY: cy }));
      el.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: cx, clientY: cy }));

      el.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: ch,
          code: /^[0-9]$/.test(ch) ? `Digit${ch}` : `Key${ch.toUpperCase()}`,
          bubbles: true,
          cancelable: true,
        })
      );
      if (el._valueTracker) {
        el._valueTracker.setValue("");
      }
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
      if (nativeSetter) {
        nativeSetter.call(el, ch);
      } else {
        el.value = ch;
      }
      const reactPropsKey = Object.keys(el).find((k) => k.startsWith("__reactProps$"));
      if (reactPropsKey && el[reactPropsKey] && typeof el[reactPropsKey].onChange === "function") {
        el[reactPropsKey].onChange({ target: { value: ch }, currentTarget: { value: ch } });
      }
      el.dispatchEvent(
        new InputEvent("input", {
          bubbles: true,
          cancelable: true,
          inputType: "insertText",
          data: ch,
        })
      );
      el.dispatchEvent(new Event("change", { bubbles: true }));
      el.dispatchEvent(
        new KeyboardEvent("keyup", {
          key: ch,
          code: /^[0-9]$/.test(ch) ? `Digit${ch}` : `Key${ch.toUpperCase()}`,
          bubbles: true,
          cancelable: true,
        })
      );
    } catch (_) {}
  }

  let handledNativeDialogs = [];

  function armMainWorldDialogGuard(mode = "apply", durationMs = 90000) {
    const cleanMode = String(mode || "apply").trim().toLowerCase() || "apply";
    const disarm = cleanMode === "idle";
    const until = disarm ? 0 : Date.now() + Math.max(1000, Number(durationMs) || 60000);
    try {
      if (document.documentElement) {
        document.documentElement.setAttribute("data-aa-dialog-policy", cleanMode);
        document.documentElement.setAttribute("data-aa-automation-until", String(until));
      }
    } catch (_) {}
    try {
      if (window.sessionStorage) {
        if (disarm) {
          window.sessionStorage.removeItem("__aa_dialog_policy_v1");
        } else {
          window.sessionStorage.setItem("__aa_dialog_policy_v1", JSON.stringify({ mode: cleanMode, until }));
        }
      }
    } catch (_) {}
    try {
      window.dispatchEvent(
        new CustomEvent("aa:arm-dialog-guard", {
          detail: { mode: cleanMode, durationMs, disarm },
        })
      );
    } catch (_) {}
    try {
      if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.sendMessage) {
        chrome.runtime.sendMessage(
          {
            type: "COMPANION_ARM_DIALOG_GUARD",
            mode: cleanMode,
            durationMs,
          },
          () => {
            if (chrome.runtime && chrome.runtime.lastError) {
              // Ignore disconnected tab/frame errors
            }
          }
        );
      }
    } catch (_) {}
  }

  try {
    window.addEventListener("aa:native-dialog-handled", (ev) => {
      const entry = (ev && ev.detail) || null;
      if (!entry) return;
      handledNativeDialogs.push(entry);
      if (handledNativeDialogs.length > 30) {
        handledNativeDialogs.splice(0, handledNativeDialogs.length - 30);
      }
      if (isBusyWorking && typeof updateLiveProgressLabels === "function") {
        const actionWord = entry.accepted ? "Confirmed" : "Dismissed";
        updateLiveProgressLabels(
          `${actionWord} browser ${entry.type || "dialog"} prompt…`,
          entry.accepted ? "Confirmed…" : "Continuing…"
        );
      }
    });
  } catch (_) {}

  function simulateMouseClickOnElement(btn) {
    if (!btn) return false;
    try {
      const rect = btn.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      ["pointerover", "mouseover", "pointermove", "mousemove", "pointerdown", "mousedown"].forEach((evName) => {
        btn.dispatchEvent(new MouseEvent(evName, { bubbles: true, cancelable: true, clientX: cx, clientY: cy, button: 0 }));
      });
      btn.focus();
      ["pointerup", "mouseup"].forEach((evName) => {
        btn.dispatchEvent(new MouseEvent(evName, { bubbles: true, cancelable: true, clientX: cx, clientY: cy, button: 0 }));
      });
      if (typeof btn.click === "function") {
        btn.click();
      } else {
        btn.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, clientX: cx, clientY: cy, button: 0 }));
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  function maybeAutoFillCodexDeviceCode() {
    const href = (window.location.href || "").toLowerCase();
    const hostName = (window.location.hostname || "").toLowerCase();
    if (!hostName.includes("openai.com")) return;

    const bodyText = ((document.body && document.body.innerText) || "").slice(0, 2000);
    if (bodyText.includes("Signed in to Codex") || bodyText.includes("You may now close this page")) {
      const cg = (bridgeState && bridgeState.onboarding && bridgeState.onboarding.chatgpt_config) || {};
      if (!cg.connected && !autoConfirmedChatGPTDone) {
        autoConfirmedChatGPTDone = true;
        sendBridgeAction("configure_chatgpt_hermes", {
          connected: true,
          skip_remote_validation: true,
          account_email: "Signed in via OpenAI Codex OAuth",
        });
      }
      return;
    }

    // Auto-select existing account on /choose-an-account
    if (href.includes("/choose-an-account") && !autoClickedCodexChooseAcct) {
      const acctBtn = document.querySelector('button[name="session_id"]');
      if (acctBtn && !acctBtn.disabled && acctBtn.getAttribute("aria-busy") !== "true") {
        autoClickedCodexChooseAcct = true;
        setTimeout(() => simulateMouseClickOnElement(acctBtn), 420);
      }
      return;
    }

    // Auto-confirm intermediate consent page (/sign-in-with-chatgpt/codex/consent)
    if (href.includes("/codex/consent") && !autoClickedCodexConsent) {
      const consentBtn = document.querySelector('form[action*="/codex/consent"] button[type="submit"], button[data-dd-action-name="Continue"]');
      if (consentBtn && !consentBtn.disabled) {
        autoClickedCodexConsent = true;
        setTimeout(() => simulateMouseClickOnElement(consentBtn), 450);
      }
      return;
    }

    const charBoxes = Array.from(
      document.querySelectorAll('input[name^="character_"], input._codeInput_1r8od_14, input[aria-label*="Code character"]')
    ).filter((el) => el && !host.contains(el) && !el.disabled && !el.readOnly);

    const isCodexDevicePage =
      charBoxes.length >= 6 ||
      href.includes("/codex/device") ||
      (href.includes("/deviceauth/") && bodyText.includes("Use your device code"));

    if (!isCodexDevicePage) return;

    const cg = (bridgeState && bridgeState.onboarding && bridgeState.onboarding.chatgpt_config) || {};
    const code = (cg.pending_user_code || "").trim();
    if (!code) {
      if (!requestedCodexDeviceCodeOnce) {
        requestedCodexDeviceCodeOnce = true;
        sendBridgeAction("start_chatgpt_codex_oauth", {});
      }
      return;
    }
    if (autoFilledCodexDeviceCode === code || isTypingCodexDeviceCode || window.__aaCodexCodeTyped === code) return;

    const cleanChars = code.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
    if (cleanChars.length < 6) return;

    const targetBoxes =
      charBoxes.length >= cleanChars.length
        ? charBoxes
        : Array.from(
            document.querySelectorAll('input[type="text"], input:not([type]), input[inputmode], input[autocomplete="one-time-code"], input[maxlength="1"]')
          ).filter((el) => el && !host.contains(el) && el.offsetParent !== null && !el.disabled && !el.readOnly);

    if (targetBoxes.length === 0) return;

    // Check if boxes are already filled or being typed by CDP worker
    const existingJoined = targetBoxes
      .slice(0, cleanChars.length)
      .map((b) => (b.value || "").trim())
      .join("");
    if (existingJoined.length >= 2) {
      autoFilledCodexDeviceCode = code;
      return;
    }

    isTypingCodexDeviceCode = true;
    window.__aaCodexCodeTyped = code;
    showNotice(`Typing Codex device code ${code}…`, "ok");

    if (targetBoxes.length === 1) {
      fillNativeElementValue(targetBoxes[0], code);
      isTypingCodexDeviceCode = false;
      autoFilledCodexDeviceCode = code;
      setTimeout(() => {
        const continueBtn = document.querySelector(
          'button[data-dd-action-name="Continue"], button[name="decision"][value="grant"]:not([hidden]), form[action*="authorize_code"] button[type="submit"]:not([value="reject"]):not([hidden])'
        );
        if (continueBtn && !continueBtn.disabled) {
          simulateMouseClickOnElement(continueBtn);
        }
      }, 480);
      return;
    }

    // Human-latency sequential typing across all 9 character boxes (90ms-145ms per character)
    let idx = 0;
    const typeNextCharacter = () => {
      if (idx >= cleanChars.length) {
        isTypingCodexDeviceCode = false;
        autoFilledCodexDeviceCode = code;
        showNotice(`Typed ${code} — confirming Continue…`, "ok");
        setTimeout(() => {
          const continueBtn = document.querySelector(
            'button[data-dd-action-name="Continue"], button[name="decision"][value="grant"]:not([hidden]), form[action*="authorize_code"] button[type="submit"]:not([value="reject"]):not([hidden])'
          );
          if (continueBtn) {
            simulateMouseClickOnElement(continueBtn);
          }
        }, 480);
        return;
      }
      const box = targetBoxes[idx];
      const ch = cleanChars[idx];
      if (box) {
        typeCharIntoReactBox(box, ch);
      }
      idx += 1;
      const humanLatencyMs = 90 + Math.floor(Math.random() * 55);
      requestAnimationFrame(() => {
        setTimeout(typeNextCharacter, humanLatencyMs);
      });
    };

    setTimeout(typeNextCharacter, 260);
  }

  // --- Job Feed, Job Details, Modal & Form Extraction ---
  function isSearchOrNavControl(el) {
    if (!el || host.contains(el)) return true;
    if (
      el.closest(
        '#msg-overlay, .msg-overlay-container, .msg-overlay-list-bubble, .msg-overlay-conversation-bubble, .msg-convo-wrapper, .msg-form, [aria-label="Messaging"], [data-test-messaging]'
      )
    ) {
      return true;
    }
    if (
      (el.classList && el.classList.contains("msg-form__attachment-upload-input")) ||
      String(el.id || "").startsWith("attachment-input-")
    ) {
      return true;
    }
    const rect = el.getBoundingClientRect();
    if (rect.width < 6 && rect.height < 6 && (el.getAttribute("type") || "").toLowerCase() !== "file") {
      return true;
    }
    if (
      el.closest(
        'header, nav, [role="navigation"], [role="search"], [role="banner"], .global-nav, .jobs-search-box, [class*="search-box"], [class*="nav-search"], [id*="global-nav"]'
      )
    ) {
      return true;
    }
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (type === "search") return true;
    const meta = [
      el.getAttribute("placeholder") || "",
      el.getAttribute("aria-label") || "",
      el.name || "",
      el.id || "",
    ]
      .join(" ")
      .toLowerCase();
    if (
      /\b(title,\s*skill|city,\s*state|zip\s*code|search\s*jobs|find\s*jobs|job\s*alerts|describe\s*the\s*job)\b/i.test(
        meta
      ) ||
      /^(search|q|keywords)$/i.test((el.name || "").trim())
    ) {
      return true;
    }
    return false;
  }

  function queryAllDeep(selector, root = document) {
    const results = [];
    const visitedRoots = new Set();
    const collect = (scope) => {
      if (!scope || visitedRoots.has(scope) || scope === host || scope === shadow) return;
      visitedRoots.add(scope);
      try {
        const matched = scope.querySelectorAll(selector);
        for (const el of matched) {
          if (el && !host.contains(el)) {
            results.push(el);
          }
        }
      } catch (_) {}
      try {
        const allEls = scope.querySelectorAll("*");
        for (const el of allEls) {
          if (el && el !== host && el.shadowRoot) {
            collect(el.shadowRoot);
          }
        }
      } catch (_) {}
    };
    collect(root);
    return results;
  }

  function findOpenEasyApplyModal() {
    const hostName = (window.location.hostname || "").toLowerCase();
    const modals = queryAllDeep(
      '.jobs-easy-apply-modal, [role="dialog"][aria-labelledby*="easy-apply"], .artdeco-modal[role="dialog"], [data-test-modal], .artdeco-modal, [role="dialog"], [aria-modal="true"], dialog[open]'
    ).filter((el) => {
      if (!el || host.contains(el)) return false;
      if (
        el.closest(
          '#msg-overlay, .msg-overlay-container, .msg-overlay-list-bubble, .msg-overlay-conversation-bubble, .msg-convo-wrapper, .msg-form, [aria-label="Messaging"], header, nav, aside'
        )
      ) {
        return false;
      }
      const ariaLbl = String(el.getAttribute("aria-label") || "").toLowerCase();
      if (ariaLbl === "messaging" || ariaLbl.includes("conversation") || ariaLbl.includes("notifications")) {
        return false;
      }
      try {
        const style = window.getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden" || parseFloat(style.opacity || "1") < 0.1) {
          return false;
        }
      } catch (_) {}
      const rect = el.getBoundingClientRect();
      return rect.width > 180 && rect.height > 120;
    });

    for (const m of modals) {
      const text = (m.innerText || m.textContent || "").toLowerCase();
      const validControls = queryAllDeep("input, select, textarea", m).filter((inp) => {
        if (!inp || inp.disabled || inp.readOnly || isSearchOrNavControl(inp)) return false;
        const t = (inp.getAttribute("type") || inp.tagName.toLowerCase()).toLowerCase();
        return !["hidden", "submit", "button", "reset", "image"].includes(t);
      });
      const isExplicitEasyApplyModal =
        (m.classList &&
          (m.classList.contains("jobs-easy-apply-modal") || m.classList.contains("jobs-easy-apply-content"))) ||
        Boolean(m.querySelector(".jobs-easy-apply-content, .jobs-easy-apply-modal")) ||
        String(m.getAttribute("aria-labelledby") || "")
          .toLowerCase()
          .includes("easy-apply") ||
        String(m.getAttribute("data-test-modal-id") || "")
          .toLowerCase()
          .includes("easy-apply");

      if (hostName.includes("linkedin.com")) {
        const headerText = Array.from(m.querySelectorAll("h1, h2, h3, [id*='modal-header']"))
          .map((h) => (h.innerText || h.textContent || "").trim().toLowerCase())
          .join(" ");
        const hasEasyApplyHeader =
          headerText.includes("apply to ") ||
          headerText.includes("easy apply") ||
          headerText.includes("contact info") ||
          headerText.includes("resume") ||
          headerText.includes("additional questions") ||
          headerText.includes("screening questions") ||
          headerText.includes("review your application") ||
          /\b\d+\s*\/\s*\d+\b/.test(text);
        if (isExplicitEasyApplyModal || (hasEasyApplyHeader && validControls.length > 0)) {
          return m;
        }
        continue;
      }

      const hasApplyKeywords =
        text.includes("apply to ") ||
        text.includes("contact info") ||
        text.includes("resume") ||
        text.includes("work experience") ||
        text.includes("additional questions") ||
        text.includes("screening questions") ||
        text.includes("home address") ||
        text.includes("voluntary self identification") ||
        text.includes("submit application") ||
        text.includes("review your application") ||
        /\b\d+\s*\/\s*\d+\s*pages?\b/i.test(text);
      if (validControls.length > 0 || hasApplyKeywords) {
        return m;
      }
    }
    return null;
  }

  function extractExternalApplyUrl(btn) {
    if (!btn) return "";
    const anchor =
      btn.tagName && btn.tagName.toLowerCase() === "a"
        ? btn
        : btn.closest("a[href]") || btn.querySelector("a[href]");
    if (!anchor) return "";
    const rawHref = (anchor.getAttribute("href") || anchor.href || "").trim();
    if (!rawHref || rawHref.startsWith("#") || rawHref.startsWith("javascript:")) return "";
    try {
      const parsed = new URL(rawHref, window.location.origin);
      if (parsed.pathname.includes("/safety/go")) {
        const innerUrl = parsed.searchParams.get("url");
        if (innerUrl && /^https?:\/\//i.test(innerUrl)) {
          return innerUrl;
        }
      }
      if (parsed.origin !== window.location.origin && /^https?:$/i.test(parsed.protocol)) {
        return parsed.href;
      }
    } catch (_) {}
    return "";
  }

  function findJobDetailApplyButton() {
    const hostName = (window.location.hostname || "").toLowerCase();
    const cleanButtonLabel = (raw) =>
      String(raw || "")
        .replace(/[→↗»›➔➜>-]+/g, " ")
        .replace(/\s+/g, " ")
        .trim();

    const isExcludedActionButton = (el, txt, aria) => {
      const combined = `${txt} ${aria}`.toLowerCase();
      if (
        /\b(interested|express interest|follow|following|save|saved|share|message|alert|dismiss|not interested|show match|match details|premium|post a free job|post a job|show all|learn more|manage this setting)\b/i.test(
          combined
        )
      ) {
        return true;
      }
      if (
        el.closest(
          'header, nav, [role="navigation"], [role="search"], .global-nav, footer, aside, .scaffold-layout__list, [class*="company-interest"], [class*="interest-card"]'
        )
      ) {
        return true;
      }
      return false;
    };

    if (hostName.includes("linkedin.com")) {
      // 1. Direct LinkedIn job apply button selectors (searching light DOM + #interop-outlet shadowRoot)
      const directLiSelectors =
        'button.jobs-apply-button, a.jobs-apply-button, [data-view-name="job-apply-button"], [data-live-test-job-apply-button], .jobs-apply-button--top-card button, .jobs-apply-button--top-card a, .jobs-s-apply button, .jobs-s-apply a, button[aria-label*="Easy Apply"], a[aria-label*="Easy Apply"]';
      const directMatches = queryAllDeep(directLiSelectors).filter((el) => {
        if (!el || el.disabled || host.contains(el)) return false;
        const rect = el.getBoundingClientRect();
        if (rect.width < 36 || rect.height < 18) return false;
        const txt = cleanButtonLabel(el.innerText || el.value || el.textContent || "");
        const aria = cleanButtonLabel(el.getAttribute("aria-label") || "");
        return !isExcludedActionButton(el, txt, aria);
      });
      if (directMatches.length > 0) {
        return directMatches[0];
      }
    }

    const candidates = queryAllDeep(
      'button.jobs-apply-button, button.jvl-btn-apply, [class*="btn-apply"], [class*="apply-btn"], button[aria-label*="Easy Apply"], button[aria-label*="Apply"], a[aria-label*="Easy Apply"], a[aria-label*="Apply"], button, a[role="button"], [role="button"], input[type="submit"], a[href*="apply"], a[href*="job"], .jobs-unified-top-card a, .jobs-search__job-details a, main a'
    ).filter((el) => {
      if (!el || el.disabled || host.contains(el)) return false;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 36 || rect.height <= 18) return false;
      const txt = cleanButtonLabel(el.innerText || el.value || el.textContent || "");
      const aria = cleanButtonLabel(el.getAttribute("aria-label") || "");
      return !isExcludedActionButton(el, txt, aria);
    });

    const patterns = [
      /^(?:in\s+|linkedin\s+)?easy apply$/i,
      /\beasy apply\b/i,
      /^apply to this job$/i,
      /^apply for this job$/i,
      /^apply for this role$/i,
      /^apply for this position$/i,
      /^apply now$/i,
      /^apply on company website$/i,
      /^apply on company site$/i,
      /^apply here$/i,
      /^apply online$/i,
      /^start application$/i,
      /^begin application$/i,
      /^continue to application$/i,
      /^apply$/i,
      /\bapply (?:to|for) this (?:job|role|position)\b/i,
    ];

    for (const re of patterns) {
      const match = candidates.find((el) => {
        const txt = cleanButtonLabel(el.innerText || el.value || el.textContent || "");
        const aria = cleanButtonLabel(el.getAttribute("aria-label") || "");
        if (txt.length > 48) return false;
        return re.test(txt) || (re === patterns[1] && re.test(aria)) || (aria && re.test(aria));
      });
      if (match) return match;
    }
    return null;
  }

  function isSpecificJobDetailOpen() {
    if (isUnauthenticatedAuthPage()) return false;
    const hostName = (window.location.hostname || "").toLowerCase();
    const pathName = (window.location.pathname || "").toLowerCase();
    const searchStr = (window.location.search || "").toLowerCase();

    if (hostName.includes("linkedin.com")) {
      if (findOpenEasyApplyModal()) return true;
      if (pathName.includes("/jobs/view/")) return true;
      if (searchStr.includes("currentjobid=")) return true;
      return false;
    }
    if (hostName === "hh.ru" || hostName.endsWith(".hh.ru")) {
      if (/\/vacancy\/\d+/i.test(pathName) || searchStr.includes("vacancyid=")) return true;
      if (document.querySelector('[data-qa="vacancy-title"], [data-qa="vacancy-description"]')) return true;
      return false;
    }
    if (hostName.includes("welcometothejungle.com") || hostName.includes("otta.com")) {
      return /\/companies\/[^/]+\/jobs\/[^/]+/i.test(pathName) || /\/jobs\/[a-z0-9_-]{6,}/i.test(pathName);
    }
    if (hostName.includes("theladders.com")) {
      return /\/job-listing\//i.test(pathName) || /\/job\/[^/]+/i.test(pathName);
    }
    if (hostName.includes("weworkremotely.com")) {
      return (
        /\/listings\/[^/]+/i.test(pathName) ||
        (/\/remote-jobs\/[a-z0-9-]+/i.test(pathName) && !/^\/remote-jobs\/(search|categories|new|all)\b/i.test(pathName))
      );
    }
    if (hostName.includes("remotive.com")) {
      return /\/remote-jobs\/[^/]+\/[^/]+-\d+/i.test(pathName);
    }
    if (hostName.includes("dynamitejobs.com")) {
      return /\/company\/[^/]+\/remote-job\/[^/]+/i.test(pathName);
    }
    if (hostName.includes("himalayas.app")) {
      return /\/companies\/[^/]+\/jobs\/[^/]+/i.test(pathName);
    }
    if (hostName.includes("wellfound.com") || hostName.includes("angel.co")) {
      return /\/jobs\/\d+/i.test(pathName) || /\/l\/[a-z0-9-]+/i.test(pathName) || searchStr.includes("job_listing_id=");
    }
    if (hostName.includes("workatastartup.com")) {
      return /\/jobs\/\d+/i.test(pathName);
    }
    if (hostName.includes("jobgether.com")) {
      return /\/offer\/[^/]+/i.test(pathName);
    }
    if (hostName.includes("indeed.com")) {
      return (
        pathName.includes("/viewjob") ||
        searchStr.includes("vjk=") ||
        searchStr.includes("jk=") ||
        Boolean(document.querySelector("#jobDescriptionText, .jobsearch-JobComponent"))
      );
    }
    if (hostName.includes("glassdoor.com")) {
      return (
        pathName.includes("/job-listing/") ||
        searchStr.includes("jl=") ||
        Boolean(document.querySelector('[data-test="job-title"], [class*="JobDetails_jobDescription"]'))
      );
    }
    if (hostName.includes("builtin.com")) {
      return /\/job\/[^/]+/i.test(pathName);
    }
    if (hostName.includes("dice.com")) {
      return /\/job-detail\/[^/]+/i.test(pathName);
    }
    if (hostName.includes("ziprecruiter.com")) {
      return /\/c\/[^/]+\/job\//i.test(pathName) || /\/jobs\/[^/]+\/[a-z0-9-]+/i.test(pathName) || searchStr.includes("jid=");
    }
    if (hostName.includes("monster.com")) {
      return /\/job-openings\/[^/]+/i.test(pathName) || searchStr.includes("jobid=");
    }
    if (hostName.includes("careerbuilder.com")) {
      return /\/job\/[^/]+/i.test(pathName);
    }
    if (hostName.includes("remoteok.com")) {
      return /\/remote-jobs\/\d+/i.test(pathName) || /\/l\/[a-z0-9-]+/i.test(pathName);
    }
    if (hostName.includes("jobicy.com")) {
      return /\/jobs\/\d+/i.test(pathName);
    }
    if (hostName.includes("remoteonly.io")) {
      return /\/jobs?\/[a-z0-9-]+/i.test(pathName);
    }
    if (hostName.includes("arbeitnow.com")) {
      return /\/view\/[^/]+/i.test(pathName) || /\/jobs\/[a-z0-9-]+/i.test(pathName);
    }
    if (hostName.includes("dover.com")) {
      return /\/apply\/[^/]+/i.test(pathName) || (/\/jobs\/[a-z0-9-]+/i.test(pathName) && pathName !== "/jobs");
    }

    // For Direct ATS platforms or general career portals, require a non-root job path/query or JSON-LD JobPosting
    if (pathName === "/" || pathName === "") {
      return JOB_URL_QUERY_PATTERNS.some((re) => re.test(searchStr));
    }
    return JOB_URL_PATH_PATTERNS.some((re) => re.test(pathName)) || JOB_URL_QUERY_PATTERNS.some((re) => re.test(searchStr));
  }

  function syncLinkedInInlineExpandButtons() {
    const hostName = (window.location.hostname || "").toLowerCase();
    const existingBtns = queryAllDeep(".aa-linkedin-inline-expand-btn");

    if (!isCollapsed || !hostName.includes("linkedin.com")) {
      existingBtns.forEach((btn) => {
        try {
          btn.remove();
        } catch (_) {}
      });
      return false;
    }

    const cleanLabel = (raw) =>
      String(raw || "")
        .replace(/[→↗»›➔➜>-]+/g, " ")
        .replace(/\s+/g, " ")
        .trim();

    const isSaveOrApplyButton = (el) => {
      if (!el || el.disabled || host.contains(el)) return false;
      if (el.classList && el.classList.contains("aa-linkedin-inline-expand-btn")) return false;
      if (
        el.closest(
          'header.global-nav, nav, [role="navigation"], [role="search"], .global-nav, footer, aside, .scaffold-layout__list, [class*="company-interest"], [class*="interest-card"]'
        )
      ) {
        return false;
      }
      const rect = el.getBoundingClientRect();
      if (rect.width < 44 || rect.height < 22 || rect.height > 60) return false;
      const style = window.getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden" || parseFloat(style.opacity || "1") < 0.1) {
        return false;
      }

      const txt = cleanLabel(el.innerText || el.value || el.textContent || "");
      const aria = cleanLabel(el.getAttribute("aria-label") || "");
      if (txt.length > 32) return false;

      const isSave =
        /^(?:save|saved)$/i.test(txt) ||
        /^(?:save|unsave)\b/i.test(aria) ||
        Boolean(el.classList && el.classList.contains("jobs-save-button"));

      const isApply =
        /^(?:(?:in|linkedin)\s+)?easy apply$/i.test(txt) ||
        /^apply(?:\s+now)?$/i.test(txt) ||
        /^(?:easy\s+)?apply\b/i.test(aria) ||
        Boolean(
          (el.classList && el.classList.contains("jobs-apply-button")) ||
            el.hasAttribute("data-live-test-job-apply-button") ||
            el.getAttribute("data-view-name") === "job-apply-button"
        );

      return isSave || isApply;
    };

    const actionButtons = queryAllDeep(
      'button.jobs-apply-button, a.jobs-apply-button, button.jobs-save-button, [data-view-name="job-apply-button"], [data-live-test-job-apply-button], .jobs-s-apply button, .jobs-s-apply a, button, a[role="button"]'
    ).filter(isSaveOrApplyButton);

    const resolveRowAndAnchor = (btn) => {
      const btnRect = btn.getBoundingClientRect();
      let child = btn;
      let parent = btn.parentElement;
      let depth = 0;
      while (parent && depth < 4) {
        const parentRect = parent.getBoundingClientRect();
        const nonInlineChildren = Array.from(parent.children).filter(
          (c) => !(c.classList && c.classList.contains("aa-linkedin-inline-expand-btn"))
        );
        const isSingleWrapper =
          nonInlineChildren.length <= 1 || parentRect.width <= btnRect.width + 24;
        if (isSingleWrapper && parent.parentElement && parentRect.height <= 80) {
          child = parent;
          parent = parent.parentElement;
          depth += 1;
          continue;
        }
        break;
      }
      return parent ? { rowEl: parent, anchorChild: child, refBtn: btn } : null;
    };

    const rowMap = new Map();
    for (const btn of actionButtons) {
      const resolved = resolveRowAndAnchor(btn);
      if (!resolved || !resolved.rowEl) continue;
      if (!rowMap.has(resolved.rowEl)) {
        rowMap.set(resolved.rowEl, {
          rowEl: resolved.rowEl,
          anchorChildren: [resolved.anchorChild],
          refBtn: resolved.refBtn,
        });
      } else {
        const entry = rowMap.get(resolved.rowEl);
        if (!entry.anchorChildren.includes(resolved.anchorChild)) {
          entry.anchorChildren.push(resolved.anchorChild);
        }
      }
    }

    // Remove any existing inline buttons whose parent is no longer an active row
    existingBtns.forEach((btn) => {
      if (!btn.parentElement || !rowMap.has(btn.parentElement)) {
        try {
          btn.remove();
        } catch (_) {}
      }
    });

    let visibleInlineCount = 0;

    for (const { rowEl, anchorChildren, refBtn } of rowMap.values()) {
      const refRect = refBtn.getBoundingClientRect();
      const btnHeight = refRect.height >= 36 ? Math.round(refRect.height) : 32;
      const fontSize = btnHeight <= 34 ? "14px" : "15px";
      const padX = btnHeight <= 34 ? "12px" : "16px";
      const iconSize = btnHeight <= 34 ? 15 : 16;

      const rowStyle = window.getComputedStyle(rowEl);
      const rowGap = parseFloat(rowStyle.columnGap || rowStyle.gap || "0") || 0;
      const marginLeft = rowGap >= 4 ? "0px" : "8px";

      let inlineBtn = rowEl.querySelector(":scope > .aa-linkedin-inline-expand-btn");
      if (!inlineBtn) {
        inlineBtn = document.createElement("button");
        inlineBtn.type = "button";
        inlineBtn.className = "aa-linkedin-inline-expand-btn";
        inlineBtn.setAttribute("aria-label", "Expand AutoApply Co-Pilot");
        inlineBtn.title = "Open AutoApply Co-Pilot";
        inlineBtn.innerHTML = `
          <svg viewBox="0 0 1024 1024" width="${iconSize}" height="${iconSize}" style="border-radius:4px;flex-shrink:0;display:block;" aria-hidden="true">
            <defs>
              <linearGradient id="aaLiInlineGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="rgb(24,58,165)" />
                <stop offset="100%" stop-color="rgb(54,168,240)" />
              </linearGradient>
            </defs>
            <rect width="1024" height="1024" rx="220" fill="url(#aaLiInlineGrad)" />
            <rect x="240" y="290" width="544" height="104" rx="32" fill="#F5F8FF" />
            <rect x="240" y="460" width="544" height="104" rx="32" fill="#F5F8FF" />
            <rect x="240" y="630" width="544" height="104" rx="32" fill="#F5F8FF" />
          </svg>
          <span>AutoApply</span>
        `;
        inlineBtn.addEventListener("mouseenter", () => {
          inlineBtn.style.backgroundColor = "rgba(10, 102, 194, 0.08)";
          inlineBtn.style.boxShadow = "inset 0 0 0 0.5px #0a66c2";
        });
        inlineBtn.addEventListener("mouseleave", () => {
          inlineBtn.style.backgroundColor = "#ffffff";
          inlineBtn.style.boxShadow = "none";
        });
        inlineBtn.addEventListener("click", (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          isCollapsed = false;
          render();
        });
      }

      inlineBtn.style.cssText = `
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 6px !important;
        height: ${btnHeight}px !important;
        min-height: ${btnHeight}px !important;
        padding: 0 ${padX} !important;
        margin-left: ${marginLeft} !important;
        border-radius: 999px !important;
        border: 1.5px solid #0a66c2 !important;
        background-color: #ffffff !important;
        color: #0a66c2 !important;
        font-family: -apple-system, system-ui, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
        font-size: ${fontSize} !important;
        font-weight: 600 !important;
        line-height: 1 !important;
        white-space: nowrap !important;
        cursor: pointer !important;
        box-sizing: border-box !important;
        flex-shrink: 0 !important;
        vertical-align: middle !important;
        transition: background-color 0.15s ease, box-shadow 0.15s ease !important;
      `;

      const lastAnchor = anchorChildren[anchorChildren.length - 1];
      if (lastAnchor && lastAnchor.parentElement === rowEl) {
        if (inlineBtn.previousElementSibling !== lastAnchor) {
          rowEl.insertBefore(inlineBtn, lastAnchor.nextSibling);
        }
      } else if (inlineBtn.parentElement !== rowEl) {
        rowEl.appendChild(inlineBtn);
      }

      const inlineRect = inlineBtn.getBoundingClientRect();
      if (
        inlineRect.width > 0 &&
        inlineRect.height > 0 &&
        inlineRect.bottom > 0 &&
        inlineRect.top < window.innerHeight
      ) {
        visibleInlineCount += 1;
      }
    }

    return visibleInlineCount > 0;
  }

  function extractJobCardsFromFeed() {
    if (isUnauthenticatedAuthPage()) return [];
    const hostName = (window.location.hostname || "").toLowerCase();
    const cards = [];
    const seenKeys = new Set();

    let selectors =
      'a[href*="/jobs/"], a[href*="/careers/"], a[href*="/positions/"], a[href*="gh_jid="], a[href*="ashby_jid="], [data-job-id] a';
    if (hostName.includes("linkedin.com")) {
      selectors =
        'a[href*="/jobs/view/"], a[href*="currentJobId="], a.job-card-container__link, a.job-card-list__title--link, [data-view-name*="job-card"] a';
    } else if (hostName === "hh.ru" || hostName.endsWith(".hh.ru")) {
      selectors = 'a[data-qa="serp-item__title"], a[href*="/vacancy/"]';
    } else if (hostName.includes("indeed.com")) {
      selectors = 'a.jcs-JobTitle, a[href*="/viewjob"], a[href*="/rc/clk"], a[data-jk]';
    } else if (hostName.includes("glassdoor.com")) {
      selectors = 'a[data-test="job-link"], a[href*="/job-listing/"]';
    } else if (hostName.includes("theladders.com")) {
      selectors = 'a[href*="/job-listing/"], a[href*="/job/"]';
    } else if (hostName.includes("weworkremotely.com")) {
      selectors = 'li.feature a[href*="/remote-jobs/"], section.jobs a[href*="/remote-jobs/"], a[href*="/listings/"]';
    } else if (hostName.includes("remotive.com")) {
      selectors = 'a[href*="/remote-jobs/"]';
    } else if (hostName.includes("dynamitejobs.com")) {
      selectors = 'a[href*="/remote-job/"]';
    } else if (hostName.includes("himalayas.app")) {
      selectors = 'a[href*="/jobs/"]';
    } else if (hostName.includes("wellfound.com") || hostName.includes("angel.co")) {
      selectors = 'a[href*="/jobs/"], a[href*="/l/"]';
    } else if (hostName.includes("jobgether.com")) {
      selectors = 'a[href*="/offer/"]';
    } else if (hostName.includes("builtin.com")) {
      selectors = 'a[href*="/job/"]';
    } else if (hostName.includes("dice.com")) {
      selectors = 'a[href*="/job-detail/"]';
    } else if (hostName.includes("ziprecruiter.com")) {
      selectors = 'a[href*="/Jobs/"], a[href*="/c/"]';
    } else if (hostName.includes("monster.com")) {
      selectors = 'a[href*="/job-openings/"]';
    } else if (hostName.includes("careerbuilder.com")) {
      selectors = 'a[href*="/job/"]';
    } else if (hostName.includes("remoteok.com")) {
      selectors = 'tr.job a[href*="/remote-jobs/"], a.preventLink[href*="/remote-jobs/"]';
    } else if (hostName.includes("jobicy.com")) {
      selectors = 'a[href*="/jobs/"]';
    } else if (hostName.includes("arbeitnow.com")) {
      selectors = 'a[href*="/view/"], a[href*="/jobs/"]';
    } else if (hostName.includes("dover.com")) {
      selectors = 'a[href*="/apply/"], a[href*="/jobs/"]';
    }

    const rawLinks = Array.from(document.querySelectorAll(selectors)).filter((el) => {
      if (!el || host.contains(el)) return false;
      if (el.closest('header, nav, footer, [role="navigation"], .global-nav, .supernova-navi')) return false;
      const href = (el.getAttribute("href") || "").toLowerCase();
      if (
        !href ||
        href === "#" ||
        /\/(login|signin|sign-in|signup|register|account|employer|pricing|about|blog|categories|search\/vacancy\b)/i.test(href)
      ) {
        return false;
      }
      const rect = el.getBoundingClientRect();
      return rect.width > 40 && rect.height > 16;
    });

    const noiseLineRe =
      /^(•|\u2022|promoted|easy apply|actively reviewing applicants|be an early applicant|verified|verified job|posted\s+.*|\d+\s+(?:day|days|week|weeks|month|months|hour|hours|minute|minutes)\s+ago|you['’]d be a top applicant|\d+\s+(?:connection|connections|school alumni|company alumni).*|401\(k\).*|medical.*|vision.*|dental.*|save|hide|dismiss|откликнуться|показать контакты)$/i;

    const cleanTitleString = (s) =>
      String(s || "")
        .replace(/\s*\(verified job\)\s*/gi, "")
        .replace(/\s+with verification$/i, "")
        .replace(/\s+/g, " ")
        .trim();

    for (const a of rawLinks) {
      const href = a.getAttribute("href") || "";
      let fullUrl = href;
      try {
        fullUrl = new URL(href, window.location.origin).href;
      } catch (_) {}

      const idMatch = fullUrl.match(/(?:currentJobId=|\/jobs\/view\/|\/vacancy\/)(\d+)/i);
      const jobId = idMatch ? idMatch[1] : "";
      const viewPathMatch = (window.location.pathname || "").match(/\/jobs\/view\/(\d+)/i);
      if (
        viewPathMatch &&
        jobId === viewPathMatch[1] &&
        !a.closest('.job-card-container, [data-view-name*="job-card"], [data-job-id], [data-occludable-job-id]')
      ) {
        continue;
      }

      let containerEl = a.closest(
        'li, [data-job-id], [data-occludable-job-id], [data-qa*="vacancy-serp__vacancy"], .job-card-container, .job-card-list__entity-lockup, [data-view-name*="job-card"]'
      );
      if (containerEl && containerEl.querySelectorAll('a[href*="/jobs/view/"], a[href*="currentJobId="], a[href*="/vacancy/"]').length > 2) {
        containerEl = null;
      }
      if (!containerEl) {
        let p = a.parentElement;
        for (let depth = 0; depth < 5 && p && p !== document.body; depth++) {
          const linkCount = p.querySelectorAll('a[href*="/jobs/view/"], a[href*="currentJobId="], a[href*="/vacancy/"]').length;
          if (linkCount > 2) break;
          if ((p.innerText || "").trim().split(/\r?\n/).length >= 2) {
            containerEl = p;
          }
          p = p.parentElement;
        }
      }
      if (!containerEl) {
        containerEl = a.parentElement || a;
      }

      const rawText = (containerEl.innerText || a.innerText || "").trim();
      if (!rawText) continue;

      const rawLines = rawText
        .split(/\r?\n/)
        .map((s) => cleanTitleString(s))
        .filter((s) => s && s.length > 1 && !noiseLineRe.test(s));

      // Deduplicate lines that repeat the job title (LinkedIn renders duplicate title spans for screen readers)
      const cleanLines = [];
      for (const line of rawLines) {
        if (cleanLines.length === 0 || cleanLines[cleanLines.length - 1].toLowerCase() !== line.toLowerCase()) {
          cleanLines.push(line);
        }
      }

      if (cleanLines.length === 0) continue;
      let title = cleanTitleString(a.innerText?.split(/\r?\n/)[0] || cleanLines[0]);
      if (!title || title.length < 3) {
        title = cleanLines[0];
      }
      if (
        !title ||
        title.length < 3 ||
        /^(jobs|search|home|my network|messaging|notifications|preferences|my jobs|post a free job|job tracker|show all|remote|hybrid|on-?site|full-?time|part-?time|contract|temporary|internship|volunteer|apply|easy apply|save|saved|share|вход|войти|резюме|вакансии|поиск|отклики)$/i.test(
          title
        )
      ) {
        continue;
      }

      const normTitle = title.toLowerCase();
      const nonTitleLines = cleanLines.filter((l) => {
        const nl = l.toLowerCase();
        return nl !== normTitle && !nl.startsWith(normTitle) && !normTitle.startsWith(nl);
      });

      let company = "";
      let location = "";

      const subEl = containerEl.querySelector(
        ".artdeco-entity-lockup__subtitle, .job-card-container__primary-description, .base-search-card__subtitle, [data-qa='vacancy-serp__vacancy-employer'], [data-testid='company-name'], [class*='company-name']"
      );
      const capEl = containerEl.querySelector(
        ".artdeco-entity-lockup__caption, .job-card-container__metadata-item, .base-search-card__metadata, [data-qa='vacancy-serp__vacancy-address'], [data-testid='text-location']"
      );
      if (subEl && subEl.innerText.trim()) {
        company = cleanTitleString(subEl.innerText);
      }
      if (capEl && capEl.innerText.trim()) {
        location = cleanTitleString(capEl.innerText);
      }

      if (!company && nonTitleLines.length > 0) {
        const firstSub = nonTitleLines[0];
        if (firstSub.includes(" · ")) {
          const parts = firstSub.split(" · ").map((p) => p.trim()).filter(Boolean);
          company = parts[0] || "";
          location = parts.slice(1).join(" • ") || nonTitleLines[1] || "Remote";
        } else {
          company = firstSub;
          location = nonTitleLines[1] || "Remote";
        }
      } else if (company && company.includes(" · ") && !location) {
        const parts = company.split(" · ").map((p) => p.trim()).filter(Boolean);
        company = parts[0] || company;
        location = parts.slice(1).join(" • ") || "Remote";
      }

      if (!company) company = hostName.includes("linkedin.com") ? "Employer" : "Company";
      if (!location) location = nonTitleLines[1] || "Remote";
      if (company.startsWith("•")) company = company.replace(/^[•\s]+/, "").trim();
      if (location.startsWith("•")) location = location.replace(/^[•\s]+/, "").trim();

      const key = jobId || `${title.toLowerCase()}::${company.toLowerCase()}`;
      if (seenKeys.has(key)) continue;
      seenKeys.add(key);

      cards.push({
        jobId,
        title,
        company_name: company,
        location,
        url: jobId && hostName.includes("linkedin.com") ? `https://www.linkedin.com/jobs/view/${jobId}/` : fullUrl,
        fullUrl,
        element: a,
        cardContainer: containerEl || a,
      });

      if (cards.length >= 10) break;
    }

    return cards;
  }

  let activeHighlightTimer = null;

  function clearAllJobHighlights() {
    if (activeHighlightTimer) {
      clearTimeout(activeHighlightTimer);
      activeHighlightTimer = null;
    }
    const highlightedNodes = queryAllDeep("[data-aa-highlighted]");
    for (const node of highlightedNodes) {
      try {
        node.style.boxShadow = node.getAttribute("data-aa-orig-shadow") || "";
        node.style.outline = node.getAttribute("data-aa-orig-outline") || "";
        node.style.transition = node.getAttribute("data-aa-orig-transition") || "";
        node.style.borderRadius = node.getAttribute("data-aa-orig-radius") || "";
        node.removeAttribute("data-aa-highlighted");
        node.removeAttribute("data-aa-orig-shadow");
        node.removeAttribute("data-aa-orig-outline");
        node.removeAttribute("data-aa-orig-transition");
        node.removeAttribute("data-aa-orig-radius");
      } catch (_) {}
    }
    try {
      if (document.activeElement && document.activeElement !== document.body && !host.contains(document.activeElement)) {
        const tag = (document.activeElement.tagName || "").toLowerCase();
        if (tag === "a" || document.activeElement.closest(".job-card-container, [data-view-name*='job-card']")) {
          document.activeElement.blur();
        }
      }
    } catch (_) {}
  }

  function highlightPageElement(el, color = "#3b82f6", autoFadeMs = 0) {
    if (!el) return;
    try {
      clearAllJobHighlights();
      const target =
        el.closest('.job-card-container, [data-view-name*="job-card"], [data-job-id], [data-occludable-job-id], li') ||
        el;
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      if (!target.hasAttribute("data-aa-highlighted")) {
        target.setAttribute("data-aa-orig-transition", target.style.transition || "");
        target.setAttribute("data-aa-orig-shadow", target.style.boxShadow || "");
        target.setAttribute("data-aa-orig-outline", target.style.outline || "");
        target.setAttribute("data-aa-orig-radius", target.style.borderRadius || "");
      }
      target.setAttribute("data-aa-highlighted", "1");
      target.style.transition = "box-shadow 0.2s ease, outline 0.2s ease";
      target.style.boxShadow = `0 0 0 2.5px ${color}, 0 6px 20px rgba(59, 130, 246, 0.32)`;
      target.style.outline = "none";
      if (!target.style.borderRadius) target.style.borderRadius = "10px";
      if (autoFadeMs > 0) {
        activeHighlightTimer = setTimeout(() => {
          clearAllJobHighlights();
        }, autoFadeMs);
      }
    } catch (_) {}
  }

  function extractJobMetadataFromPage() {
    const hostName = (window.location.hostname || "").toLowerCase();
    const feedCards = extractJobCardsFromFeed();
    const specificOpen = isSpecificJobDetailOpen();

    // If on a LinkedIn / Job Feed page without a specific job open, use the selected job card from the feed!
    if (!specificOpen && feedCards.length > 0) {
      const idx = Math.min(Math.max(0, selectedFeedJobIndex), feedCards.length - 1);
      const chosen = feedCards[idx];
      if (hostName.includes("linkedin.com") && chosen.title && chosen.company_name && typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
        try {
          chrome.storage.local.set({
            aa_last_linkedin_job_context: {
              title: chosen.title,
              company_name: chosen.company_name,
              location: chosen.location || "Remote",
              description: `${chosen.title} at ${chosen.company_name} (${chosen.location})`,
              updatedAt: Date.now(),
            },
          });
        } catch (_) {}
      }
      return {
        canonical_url: chosen.url || window.location.href,
        title: chosen.title,
        company_name: chosen.company_name,
        location: chosen.location || "Remote",
        description: `${chosen.title} at ${chosen.company_name} (${chosen.location})`,
        is_feed_selection: true,
        feed_count: feedCards.length,
      };
    }

    let title = "";
    let company = "";
    let location = "";
    let description = "";
    let matchedCardUrl = "";

    // Check if URL has currentJobId on LinkedIn and match against feedCards first
    if (hostName.includes("linkedin.com") && feedCards.length > 0) {
      const curIdMatch = (window.location.search || "").match(/currentJobId=(\d+)/i) || (window.location.pathname || "").match(/\/jobs\/view\/(\d+)/i);
      const curId = curIdMatch ? curIdMatch[1] : "";
      const matchedCard =
        (curId && feedCards.find((c) => c.jobId === curId)) ||
        (!/\/jobs\/view\/\d+/i.test(window.location.pathname || "")
          ? feedCards[Math.min(Math.max(0, selectedFeedJobIndex), feedCards.length - 1)]
          : null);
      if (matchedCard) {
        title = matchedCard.title;
        company = matchedCard.company_name;
        location = matchedCard.location;
        matchedCardUrl = matchedCard.url || matchedCard.fullUrl || "";
      }
    }

    // 1. Check JSON-LD JobPosting
    try {
      const ldScripts = document.querySelectorAll('script[type="application/ld+json"]');
      for (const s of ldScripts) {
        const parsed = JSON.parse(s.textContent || "{}");
        const items = Array.isArray(parsed) ? parsed : parsed["@graph"] || [parsed];
        for (const obj of items) {
          if (obj && obj["@type"] === "JobPosting") {
            title = title || obj.title || obj.name || "";
            if (obj.hiringOrganization) {
              company =
                company ||
                (typeof obj.hiringOrganization === "string"
                  ? obj.hiringOrganization
                  : obj.hiringOrganization.name || "");
            }
            if (obj.jobLocation) {
              const locObj = Array.isArray(obj.jobLocation) ? obj.jobLocation[0] : obj.jobLocation;
              const addr = (locObj && locObj.address) || {};
              location =
                location ||
                [addr.addressLocality, addr.addressRegion, addr.addressCountry].filter(Boolean).join(", ");
            }
            if (obj.description) {
              const tmp = document.createElement("div");
              tmp.innerHTML = String(obj.description);
              description = (tmp.innerText || tmp.textContent || "").trim();
            }
          }
        }
      }
    } catch (_) {}

    // 2. Check embedded ATS child frame state and validated cross-tab handoff hints
    if (!title && childFrameState && childFrameState.title) {
      title = childFrameState.title;
    }
    if (!company && childFrameState && childFrameState.company_name) {
      company = childFrameState.company_name;
    }
    if (!description && childFrameState && childFrameState.description) {
      description = childFrameState.description;
    }
    const validHint = getValidatedCrossTabJobHint();
    if (!title && validHint && validHint.title) {
      title = validHint.title;
    }
    if (!company && validHint && validHint.company_name) {
      company = validHint.company_name;
    }
    if (!location && validHint && validHint.location) {
      location = validHint.location;
    }
    if (!description && validHint && validHint.description) {
      description = validHint.description;
    }

    // 3. Check OpenGraph & page headings (ignoring generic "Jobs | LinkedIn", wrapper headers like "Work at Trulioo", login pages, and error/geo-block banners)
    const ogSite = document.querySelector('meta[property="og:site_name"]')?.getAttribute("content") || "";
    const ogTitle = document.querySelector('meta[property="og:title"]')?.getAttribute("content") || "";
    const detailHeadingEl = document.querySelector(
      "[data-qa='vacancy-title'], .job-details-jobs-unified-top-card__job-title, .jobs-unified-top-card__job-title, [data-testid='jobsearch-JobInfoHeader-title'], [data-test='job-title'], [data-view-name='job-detail'] h1, h1.ashby-job-posting-heading, h1.jvl-job-title, [class*='job-title'] h1, main h1, h1"
    );
    const h1Text = (detailHeadingEl?.innerText || "").trim();

    const isGenericWrapperTitle = (s) => {
      const clean = String(s || "").trim();
      if (!clean) return true;
      if (/^(jobs?|linkedin|feed|search results|work|careers?|openings?|current openings|open positions|search career opportunities|career opportunities|job opportunities|join us|join our team|work with us|apply|application|dawn|returning users|join dawn today|welcome,\s*there|complete your application|sign\s*in|log\s*in|login|register|create account|step:\s*\d+\s*of\s*\d+|вход|войти|войдите|вход в личный кабинет|регистрация|зарегистрироваться|поиск работы|мои резюме|отклики и приглашения|вакансии)$/i.test(clean)) {
        return true;
      }
      if (/^(work|careers?|jobs?|openings?|opportunities|join us|work with us)\s+(at|with|@)\s+/i.test(clean)) {
        return true;
      }
      if (/(available only in|not available in|sorry for the inconvenience|access denied|page not found|\b404\b|\b403\b|forbidden|no longer accepting|no longer available|job has expired|position has been filled|security check|verify you are human|your next role is here)/i.test(clean)) {
        return true;
      }
      return false;
    };

    if (!title || isGenericWrapperTitle(title)) {
      title = "";
      for (const rawSrc of [h1Text, ogTitle, document.title || ""]) {
        if (!rawSrc || isGenericWrapperTitle(rawSrc)) continue;
        const candidateTitle = rawSrc.split(" at ")[0].split(" @ ")[0].split(" | ")[0].split(" - ")[0].split(" — ")[0].trim();
        if (!isGenericWrapperTitle(candidateTitle)) {
          title = candidateTitle;
          break;
        }
      }
    }

    // Parse LinkedIn's standard "<Role Title> | <Company Name> | LinkedIn" document title
    const pipeParts = (document.title || "")
      .split(" | ")
      .map((s) => s.trim())
      .filter(Boolean);
    if (pipeParts.length >= 3 && pipeParts[pipeParts.length - 1].toLowerCase().includes("linkedin")) {
      if (!title || isGenericWrapperTitle(title)) title = pipeParts[0];
      if (!company || ["Featured Employer", "Employer", "Target Company", "Company"].includes(company)) {
        company = pipeParts[1];
      }
    }

    if (!company || ["Featured Employer", "Employer", "Target Company", "Company"].includes(company)) {
      const pathParts = window.location.pathname.split("/").filter(Boolean);
      const liCompanyEl = document.querySelector(
        "[data-qa='vacancy-company-name'], [data-testid='inlineHeader-companyName'], [data-test='employer-name'], .job-details-jobs-unified-top-card__company-name, .jobs-unified-top-card__company-name, .jvl-company-name, [class*='company-name'], [class*='employer-name'], .ajp-company-name"
      );
      if (liCompanyEl && (liCompanyEl.innerText || "").trim()) {
        company = (liCompanyEl.innerText || "").trim();
      } else if (
        (hostName.includes("greenhouse.io") ||
          hostName.includes("lever.co") ||
          hostName.includes("ashbyhq.com") ||
          hostName.includes("workable.com")) &&
        pathParts.length >= 1
      ) {
        const slug = pathParts[0].replace(/[-_]+/g, " ");
        company = slug.replace(/\b\w/g, (c) => c.toUpperCase());
      } else if (!isGenericWrapperTitle(h1Text) && h1Text.toLowerCase().includes(" at ")) {
        company = h1Text.split(/\s+at\s+/i).pop().split("|")[0].split("-")[0].trim();
      } else if (!isGenericWrapperTitle(document.title) && document.title.includes(" at ")) {
        company = document.title.split(" at ").pop().split("|")[0].split("-")[0].trim();
      } else if (ogSite && !["greenhouse", "lever", "ashby", "linkedin", "workday", "dawn", "hh.ru", "headhunter"].includes(ogSite.toLowerCase())) {
        company = ogSite.trim();
      } else if (!isGenericWrapperTitle(document.title) && document.title.includes(" | ")) {
        const candComp = document.title.split(" | ").pop().trim();
        if (candComp && !/^(linkedin|jobs|careers|dawn|hh\.ru|headhunter)$/i.test(candComp)) company = candComp;
      } else if (!isGenericWrapperTitle(document.title) && document.title.includes(" - ")) {
        const candComp = document.title.split(" - ").pop().split("|")[0].trim();
        if (!/^(linkedin|hh\.ru|headhunter)$/i.test(candComp)) company = candComp;
      } else if (hostName.includes("theladders.com")) {
        company = "Ladders";
      }
    }

    if (!location) {
      const locEl = document.querySelector(
        "[data-qa='vacancy-view-location'], [data-qa='vacancy-view-raw-address'], [data-testid='inlineHeader-companyLocation'], [data-test='location']"
      );
      if (locEl && (locEl.innerText || "").trim()) {
        location = (locEl.innerText || "").trim();
      }
    }

    // If bridgeState has a matching job for this URL or company with a real title, use it over "Target Role"
    if ((!title || isGenericWrapperTitle(title)) && bridgeState && Array.isArray(bridgeState.jobs)) {
      const curUrl = (window.location.href || "").split("#")[0].replace(/\/+$/, "");
      const mJid = curUrl.match(/(?:ashby_jid|gh_jid)=([a-zA-Z0-9\-_]+)/i);
      const jidTok = mJid ? mJid[1].toLowerCase() : "";
      const matchedJob = bridgeState.jobs.find((j) => {
        const jUrl = String(j.canonical_url || "").split("#")[0].replace(/\/+$/, "");
        if (jUrl && jUrl === curUrl) return true;
        if (jidTok && jUrl.toLowerCase().includes(jidTok)) return true;
        if (company && String(j.company_name || "").toLowerCase() === company.toLowerCase() && !isGenericWrapperTitle(j.title)) return true;
        return false;
      });
      if (matchedJob && matchedJob.title && !isGenericWrapperTitle(matchedJob.title)) {
        title = matchedJob.title;
      }
      if ((!company || company === "Target Company") && matchedJob && matchedJob.company_name) {
        company = matchedJob.company_name;
      }
    }

    if (!description) {
      const descSelectors = [
        "[data-qa='vacancy-description']",
        "#jobDescriptionText",
        "#job-details",
        ".jobs-description__content",
        "[data-testid*='job-description']",
        ".job-description",
        "#job-description",
        ".posting-requirements",
        ".content-intro",
        "#content",
        "main",
        "article",
      ];
      for (const sel of descSelectors) {
        const el = document.querySelector(sel);
        if (el && (el.innerText || "").trim().length > 200) {
          description = (el.innerText || "").trim().slice(0, 5000);
          break;
        }
      }
      if (!description && document.body) {
        description = (document.body.innerText || "").trim().slice(0, 4500);
      }
    }

    const finalTitle = title || (feedCards[0] && feedCards[0].title) || "Target Role";
    const finalCompany = company || (feedCards[0] && feedCards[0].company_name) || "Target Company";
    const finalLocation = location || (feedCards[0] && feedCards[0].location) || "Remote";

    if (hostName.includes("linkedin.com") && finalTitle !== "Target Role" && finalCompany !== "Target Company" && typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      try {
        chrome.storage.local.set({
          aa_last_linkedin_job_context: {
            title: finalTitle,
            company_name: finalCompany,
            location: finalLocation,
            description: description.slice(0, 3000),
            updatedAt: Date.now(),
          },
        });
      } catch (_) {}
    }

    const resolvedCanonicalUrl =
      hostName.includes("linkedin.com") &&
      !/\/jobs\/view\/\d+/i.test(window.location.pathname || "") &&
      !/currentJobId=\d+/i.test(window.location.search || "") &&
      matchedCardUrl
        ? matchedCardUrl
        : window.location.href;

    return {
      canonical_url: resolvedCanonicalUrl,
      title: finalTitle,
      company_name: finalCompany,
      location: finalLocation,
      description: description.slice(0, 5000),
      is_feed_selection: false,
      feed_count: feedCards.length,
    };
  }

  function detectApplicationPageProblem() {
    if (!document.body) return null;
    const hostName = (window.location.hostname || "").toLowerCase();
    if (
      hostName.includes("linkedin.com") ||
      hostName.includes("google.com") ||
      hostName.includes("gmail.com") ||
      hostName.includes("openrouter.ai") ||
      hostName.includes("capsolver.com") ||
      hostName.includes("chatgpt.com") ||
      hostName.includes("openai.com") ||
      hostName.includes("tealhq.com") ||
      hostName.includes("outlook.") ||
      hostName.includes("office.com") ||
      hostName.includes("live.com") ||
      hostName.includes("proton.me") ||
      hostName.includes("yahoo.com")
    ) {
      return null;
    }
    const jobParams = detectJobPageParameters();
    if (!jobParams || !jobParams.isJobPage) return null;
    const h1Text = (document.querySelector("main h1, h1, h2")?.innerText || "").replace(/\s+/g, " ").trim();
    const bodyText = (document.body.innerText || "").slice(0, 4000).replace(/\s+/g, " ").trim();
    const combined = `${h1Text}\n${bodyText}`;

    // 1. Geo-block / Region restriction (e.g. "Ladders is currently available only in the United States and Canada.")
    const geoMatch = combined.match(
      /([^.\n]{0,90}\b(?:currently available only in|only available in the|not available in your (?:country|region|location)|unavailable in your (?:country|region|location))[^.\n]{0,120}\.?)/i
    );
    if (geoMatch && geoMatch[1]) {
      const sentence = geoMatch[1].trim();
      return {
        kind: "geo_blocked",
        reason: `Geo-restricted: ${sentence}`,
      };
    }

    // 2. Closed / Expired job posting
    const closedMatch = combined.match(
      /([^.\n]{0,80}\b(?:no longer accepting applications|this job is no longer available|position has been filled|job posting has expired|this role is closed|job has expired)[^.\n]{0,80}\.?)/i
    );
    if (closedMatch && closedMatch[1]) {
      return {
        kind: "closed_job",
        reason: `Job Closed: ${closedMatch[1].trim()}`,
      };
    }

    // 3. 404 / Page not found
    if (/\b(404\s+not\s+found|page\s+not\s+found|we\s+couldn['’]t\s+find\s+that\s+page|this\s+page\s+doesn['’]t\s+exist)\b/i.test(combined)) {
      return {
        kind: "not_found",
        reason: "Broken Link (404): Target application page was not found.",
      };
    }

    // 4. Access Denied / Security Block
    if (/\b(access\s+denied|403\s+forbidden)\b/i.test(h1Text)) {
      return {
        kind: "access_blocked",
        reason: `Access Blocked: ${h1Text}`,
      };
    }

    return null;
  }

  function recordApplicationProblemNote(meta, reason, kind = "autofill_problem") {
    if (!reason) return;
    const jobParams = detectJobPageParameters();
    if (!jobParams || !jobParams.isJobPage) return;
    const safeMeta = meta || extractJobMetadataFromPage();
    if (
      !safeMeta ||
      /^(gmail|google|inbox)$/i.test(String(safeMeta.company_name || "").trim()) ||
      /^inbox\b/i.test(String(safeMeta.title || "").trim())
    ) {
      return;
    }
    const cleanReason = String(reason).trim();
    const urlKey = `${(window.location.href || "").split("#")[0]}::${cleanReason}`;
    currentApplicationIssue = {
      reason: cleanReason,
      kind,
      url: window.location.href,
    };
    if (recordedIssueSignatures.has(urlKey)) return;
    recordedIssueSignatures.add(urlKey);
    sendBridgeAction("record_job_application_issue", {
      title: safeMeta.title,
      company_name: safeMeta.company_name,
      canonical_url: safeMeta.canonical_url || window.location.href,
      location: safeMeta.location || "Remote",
      description: safeMeta.description || "",
      reason: cleanReason,
      kind,
      silent_banner: true,
    }).catch(() => {});
  }

  function getFieldLabelText(el) {
    if (!el) return "";
    const parts = [];
    const rootNode = (el.getRootNode && el.getRootNode()) || document;
    const queryRoot = rootNode && rootNode.querySelector ? rootNode : document;
    const rawType = ((el.getAttribute && el.getAttribute("type")) || "").toLowerCase();
    const isRadio = rawType === "radio";
    const radioGroupContainer = isRadio
      ? el.closest("fieldset, [role='radiogroup'], .fb-dash-form-element")
      : null;

    if (isRadio && radioGroupContainer) {
      const legend = radioGroupContainer.querySelector(
        "legend, [data-test-form-builder-radio-button-form-component__title], .field-label, h3, h4"
      );
      if (legend && legend.innerText) {
        parts.push(legend.innerText.trim());
      }
      const groupAriaLabel = radioGroupContainer.getAttribute("aria-label");
      if (groupAriaLabel) {
        parts.push(groupAriaLabel.trim());
      }
      const groupAriaLabelledBy = radioGroupContainer.getAttribute("aria-labelledby");
      if (groupAriaLabelledBy) {
        groupAriaLabelledBy.split(/\s+/).forEach((id) => {
          const ref = (queryRoot.getElementById && queryRoot.getElementById(id)) || document.getElementById(id);
          if (ref && ref.innerText) parts.push(ref.innerText.trim());
        });
      }
      if (parts.length > 0) {
        return Array.from(new Set(parts.filter(Boolean))).join(" / ").slice(0, 220);
      }
    }

    if (el.id) {
      try {
        const lbl =
          queryRoot.querySelector(`label[for="${CSS.escape(el.id)}"]`) ||
          document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (lbl && lbl.innerText) parts.push(lbl.innerText.trim());
      } catch (_) {}
      try {
        const lblById =
          (queryRoot.getElementById && queryRoot.getElementById(`${el.id}-label`)) ||
          document.getElementById(`${el.id}-label`);
        if (lblById && lblById.innerText) parts.push(lblById.innerText.trim());
      } catch (_) {}
    }
    const parentLabel = el.closest("label");
    if (parentLabel && parentLabel.innerText) {
      parts.push(parentLabel.innerText.trim());
    }
    const ariaLabel = el.getAttribute("aria-label");
    if (ariaLabel) parts.push(ariaLabel.trim());
    const ariaLabelledBy = el.getAttribute("aria-labelledby");
    if (ariaLabelledBy) {
      ariaLabelledBy.split(/\s+/).forEach((id) => {
        const ref = (queryRoot.getElementById && queryRoot.getElementById(id)) || document.getElementById(id);
        if (ref && ref.innerText) parts.push(ref.innerText.trim());
      });
    }
    const parentFieldset = el.closest("fieldset");
    if (parentFieldset) {
      const legend = parentFieldset.querySelector("legend, [data-test-form-builder-radio-button-form-component__title]");
      if (legend && legend.innerText) {
        parts.push(legend.innerText.trim());
      }
    }
    // Never include bare 'div' in closest() selector — otherwise it stops at the innermost React-Select / input wrapper div instead of the .field container
    let fieldWrapper = el.closest(
      ".field, .form-group, .application-question, .posting-field, .fb-dash-form-element, .artdeco-text-input, [data-test-form-element], [data-testid*='field'], [data-automation-id*='formField'], [class*='field'], [class*='question'], fieldset, li"
    );
    if (!fieldWrapper) {
      let cur = el.parentElement;
      for (let depth = 0; depth < 6 && cur && cur !== document.body; depth++) {
        if (cur.querySelector && cur.querySelector("label, legend, [id$='-label'], .field-label")) {
          fieldWrapper = cur;
          break;
        }
        cur = cur.parentElement;
      }
    }
    if (fieldWrapper) {
      const heading = fieldWrapper.querySelector(
        isRadio
          ? "legend, [id$='-label'], h3, h4, .field-label"
          : "label, legend, [id$='-label'], h3, h4, .field-label, [class*='label']"
      );
      if (heading && heading.innerText) {
        parts.push(heading.innerText.trim());
      }
    }
    if (el.placeholder) parts.push(el.placeholder.trim());
    return Array.from(new Set(parts.filter(Boolean))).join(" / ").slice(0, 220);
  }

  function extractApplicationFormSchema() {
    if (isUnauthenticatedAuthPage()) return [];
    const hostName = (window.location.hostname || "").toLowerCase();
    let rootScope = document;

    // On LinkedIn, application forms exist inside the Easy Apply modal dialog; never count navbar/page search boxes
    if (hostName.includes("linkedin.com")) {
      const openModal = findOpenEasyApplyModal();
      if (!openModal) return [];
      rootScope = openModal;
    } else {
      // On Primary Job Boards (e.g. hh.ru, Indeed, Glassdoor, Wellfound, Ladders, etc.), never count search/filter/login inputs when no specific job is open
      const matchedBoard = findMatchingDesktopJobBoard(hostName);
      if (matchedBoard && matchedBoard.is_primary && !isSpecificJobDetailOpen()) {
        return [];
      }
    }

    const elements = queryAllDeep("input, textarea, select", rootScope);
    const schema = [];
    const codaCells = Array.from(rootScope.querySelectorAll(".kr-cell, [data-coda-ui-id='cellView']"));
    if (codaCells.length >= 2) {
      codaCells.forEach((cell, idx) => {
        let lbl = "";
        let cur = cell.parentElement;
        for (let d = 0; d < 6 && cur && cur !== document.body; d++) {
          const allText = (cur.innerText || cur.textContent || "").replace(/\s+/g, " ").trim();
          const cellText = (cell.innerText || cell.textContent || "").replace(/\s+/g, " ").trim();
          const diff = cellText ? allText.replace(cellText, "").trim() : allText;
          if (diff.length >= 2 && diff.length < 240) {
            lbl = diff;
            break;
          }
          cur = cur.parentElement;
        }
        const isFile = Boolean(cell.querySelector("input[type='file']") || /choose files|upload|resume|cv/i.test((cell.innerText || "") + " " + lbl));
        const isCombo = Boolean(cell.querySelector("[role='combobox'], [aria-haspopup='listbox']"));
        const fid = `coda_cell_${idx}`;
        schema.push({
          field_id: fid,
          field_key: fid,
          tag: "div",
          type: isFile ? "file" : isCombo ? "combobox" : "text",
          is_combobox: isCombo,
          name: fid,
          id: fid,
          label: lbl || fid,
          placeholder: "",
          max_length: null,
          required: lbl.includes("*"),
          options: isCombo ? ["Project Manager", "Product Manager", "Product Designer", "Account Manager"] : [],
        });
      });
      return schema;
    }
    const radioGroupFieldMap = new Map();
    let ghRequiredIds = new Set();
    try {
      const ghFormRoot = rootScope.querySelector && rootScope.querySelector("[data-react-class='CandidateFacing.Form'][data-react-props]");
      if (ghFormRoot) {
        const ghProps = JSON.parse(ghFormRoot.getAttribute("data-react-props") || "{}");
        for (const q of ghProps.questions || []) {
          if (q && q.required) {
            if (q.id !== undefined && q.id !== null) ghRequiredIds.add(String(q.id));
            if (q.name_key) ghRequiredIds.add(String(q.name_key));
          }
        }
      }
    } catch (_) {}

    elements.forEach((el, idx) => {
      if (!el || el.disabled || el.readOnly) return;
      if (host.contains(el)) return;
      if (isSearchOrNavControl(el)) return;
      if (el.name === "g-recaptcha-response" || el.closest(".ashby-application-form-autofill-input-root")) return;
      const rawType = (el.getAttribute("type") || el.tagName.toLowerCase()).toLowerCase();
      if (["hidden", "submit", "button", "reset", "image"].includes(rawType)) return;
      if (rawType === "radio" && el.closest(".jobs-document-upload-redesign-card__container, [class*='resume-card']")) {
        return;
      }
      const isCombobox =
        el.getAttribute("role") === "combobox" ||
        el.classList.contains("select__input") ||
        Boolean(el.closest(".select__control, [class*='react-select'], [data-test-single-typeahead-entity-form-component]"));
      const type = isCombobox ? "combobox" : rawType;

      const label = getFieldLabelText(el);
      const name = el.name || "";
      const id = el.id || "";
      const placeholder = el.placeholder || "";
      if (!label && !name && !id && !placeholder && type !== "file") return;

      const radioGroupEl =
        type === "radio"
          ? el.closest("fieldset, [role='radiogroup'], .fb-dash-form-element")
          : null;
      if (type === "radio") {
        let radioGroupId = "";
        if (name) {
          radioGroupId = `name:${name}`;
        } else if (radioGroupEl) {
          const firstRadioInGroup = radioGroupEl.querySelector("input[type='radio']") || el;
          radioGroupId = radioGroupEl.id
            ? `fs:${radioGroupEl.id}`
            : `fs_el:${elements.indexOf(firstRadioInGroup)}`;
        } else if (label) {
          radioGroupId = `lbl:${label}`;
        }
        if (radioGroupId && radioGroupFieldMap.has(radioGroupId)) {
          el.setAttribute("data-aa-field-id", radioGroupFieldMap.get(radioGroupId));
          return;
        }
        let fieldKey = el.getAttribute("data-aa-field-id");
        if (!fieldKey) {
          const cleanSeed = (name || (radioGroupEl && radioGroupEl.id) || id || type).replace(/[^a-zA-Z0-9_-]/g, "");
          fieldKey = `aa_field_${idx}_${cleanSeed}`;
        }
        el.setAttribute("data-aa-field-id", fieldKey);
        if (radioGroupId) {
          radioGroupFieldMap.set(radioGroupId, fieldKey);
        }
      }

      let fieldKey = el.getAttribute("data-aa-field-id");
      if (!fieldKey) {
        fieldKey = `aa_field_${idx}_${(name || id || type).replace(/[^a-zA-Z0-9_-]/g, "")}`;
        el.setAttribute("data-aa-field-id", fieldKey);
      }

      let options = [];
      if (el.tagName.toLowerCase() === "select") {
        options = Array.from(el.options || [])
          .map((o) => (o.text || o.value || "").trim())
          .filter(Boolean)
          .slice(0, 25);
      } else if (type === "radio") {
        const fs = radioGroupEl || el.parentElement;
        if (fs) {
          const groupRadios = Array.from(fs.querySelectorAll("input[type='radio']"));
          if (groupRadios.length > 0) {
            options = groupRadios
              .map((r) => {
                let optTxt = "";
                if (r.id) {
                  try {
                    const assoc = fs.querySelector(`label[for="${CSS.escape(r.id)}"]`);
                    if (assoc) optTxt = (assoc.innerText || assoc.textContent || "").trim();
                  } catch (_) {}
                }
                if (!optTxt) {
                  const wrapLbl = r.closest("label");
                  if (wrapLbl) optTxt = (wrapLbl.innerText || wrapLbl.textContent || "").trim();
                }
                return (optTxt || r.value || "").trim();
              })
              .filter(Boolean)
              .slice(0, 12);
          } else {
            options = Array.from(fs.querySelectorAll("label"))
              .map((l) => (l.innerText || l.textContent || "").trim())
              .filter(Boolean)
              .slice(0, 12);
          }
        }
      }

      const maxLenAttr = el.getAttribute("maxlength");
      const parsedMaxLen = maxLenAttr && /^\d+$/.test(maxLenAttr) ? parseInt(maxLenAttr, 10) : null;
      const fsId = String((radioGroupEl && radioGroupEl.id) || "");
      const isGhRequired =
        ghRequiredIds.size > 0 &&
        Boolean(fsId && (ghRequiredIds.has(fsId) || Array.from(ghRequiredIds).some((qid) => fsId.includes(qid))));

      schema.push({
        field_id: fieldKey,
        field_key: fieldKey,
        tag: el.tagName.toLowerCase(),
        type,
        is_combobox: isCombobox,
        name: name || fsId,
        id: id || fsId,
        label,
        placeholder,
        max_length: parsedMaxLen && parsedMaxLen > 0 && parsedMaxLen < 500 ? parsedMaxLen : null,
        required: Boolean(
          el.required ||
            el.getAttribute("aria-required") === "true" ||
            (radioGroupEl && radioGroupEl.getAttribute("aria-required") === "true") ||
            isGhRequired ||
            label.includes("*")
        ),
        options,
      });
    });

    if (schema.length === 0 && childFrameState && Array.isArray(childFrameState.formFields) && childFrameState.formFields.length > 0) {
      return childFrameState.formFields;
    }
    return schema;
  }

  function base64ToUint8Array(b64) {
    const binaryString = window.atob(b64);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes;
  }

  async function scrollElementIntoViewSmoothly(el, highlightColor = "#3b82f6") {
    if (!el) return;
    const target =
      el.closest(".select__control, .field, .form-group, [data-testid*='upload'], [class*='upload'], label") || el;
    try {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (_) {
      try {
        target.scrollIntoView();
      } catch (_) {}
    }
    const prevTransition = target.style.transition;
    const prevBoxShadow = target.style.boxShadow;
    target.style.transition = "box-shadow 0.2s ease, outline 0.2s ease";
    target.style.boxShadow = `0 0 0 3px ${highlightColor}55`;
    await new Promise((r) => setTimeout(r, 175));
    setTimeout(() => {
      try {
        target.style.boxShadow = prevBoxShadow;
        target.style.transition = prevTransition;
      } catch (_) {}
    }, 900);
  }

  function sendCdpCloakBrowserInteract(payload = {}) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(
          { type: "COMPANION_ACTION", action: "cdp_cloakbrowser_interact", payload },
          (resp) => {
            resolve((resp && resp.ok && resp.data) || { cdp_used: false });
          }
        );
      } catch (_) {
        resolve({ cdp_used: false });
      }
    });
  }

  async function cdpClickElement(el) {
    if (!el) return false;
    try {
      const targetUid = `aa_clk_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      el.setAttribute("data-aa-cdp-target", targetUid);
      const rect = el.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      let clicked = false;
      if (rect.width > 4 && rect.height > 4 && cx > 0 && cy > 0) {
        const res = await sendCdpCloakBrowserInteract({
          mode: "click",
          url: window.location.href,
          target_uid: targetUid,
          x: cx,
          y: cy,
        });
        clicked = Boolean(res && res.cdp_used && res.clicked);
      }
      try {
        el.removeAttribute("data-aa-cdp-target");
      } catch (_) {}
      return clicked;
    } catch (_) {
      return false;
    }
  }

  async function clickElementWithAgent(el, useCdpFirst = false) {
    if (!el) return;
    if (useCdpFirst) {
      const cdpOk = await cdpClickElement(el);
      if (cdpOk) return;
    }
    simulateMouseClickOnElement(el);
  }

  function attachPdfToFileInput(fileInput, docObj) {
    if (!fileInput || !docObj || !docObj.base64) return false;
    try {
      programmaticTypingSet.add(fileInput);
      const targetUid = `aa_file_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      fileInput.setAttribute("data-aa-cdp-target", targetUid);
      if (docObj.path) {
        sendCdpCloakBrowserInteract({
          mode: "upload",
          url: window.location.href,
          target_uid: targetUid,
          file_path: docObj.path,
        })
          .catch(() => {})
          .finally(() => {
            try {
              fileInput.removeAttribute("data-aa-cdp-target");
            } catch (_) {}
          });
      } else {
        fileInput.removeAttribute("data-aa-cdp-target");
      }

      const bytes = base64ToUint8Array(docObj.base64);
      const filename = docObj.filename || "Resume.pdf";
      const mimeType = docObj.mime_type || "application/pdf";
      const file = new File([bytes], filename, {
        type: mimeType,
        lastModified: Date.now(),
      });
      const dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;

      fileInput.dispatchEvent(new Event("input", { bubbles: true }));
      fileInput.dispatchEvent(new Event("change", { bubbles: true }));

      const dropzone = fileInput.closest("[class*='drop'], [class*='upload'], [data-testid*='upload'], label, .field");
      if (dropzone) {
        try {
          const dropEvent = new DragEvent("drop", {
            bubbles: true,
            cancelable: true,
            dataTransfer: dt,
          });
          dropzone.dispatchEvent(dropEvent);
        } catch (_) {}
        let badge = dropzone.querySelector(".aa-uploaded-file-pill");
        if (!badge) {
          badge = document.createElement("div");
          badge.className = "aa-uploaded-file-pill";
          badge.style.cssText =
            "margin-top:6px;padding:4px 8px;border-radius:6px;background:rgba(16,185,129,0.16);border:1px solid rgba(16,185,129,0.45);color:#10b981;font-size:11.5px;font-weight:600;display:inline-block;";
          dropzone.appendChild(badge);
        }
        badge.textContent = `✓ Attached: ${filename}`;
      }
      setTimeout(() => {
        programmaticTypingSet.delete(fileInput);
      }, 120);
      return true;
    } catch (err) {
      programmaticTypingSet.delete(fileInput);
      console.warn("AutoApply file attach warning:", err);
      return false;
    }
  }

  function setNativeInputValueStep(el, valStr, chunkStr = "") {
    const tag = el.tagName.toLowerCase();
    const proto = tag === "textarea" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    const nativeSetter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (nativeSetter) {
      nativeSetter.call(el, valStr);
    } else {
      el.value = valStr;
    }
    try {
      el.dispatchEvent(
        new InputEvent("input", {
          bubbles: true,
          cancelable: true,
          inputType: chunkStr ? "insertText" : "deleteContentBackward",
          data: chunkStr || null,
        })
      );
    } catch (_) {
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  function humanTypingCadenceMs() {
    // Natural human typing cadence: 85–145ms per character
    return 85 + Math.floor(Math.random() * 61);
  }

  async function typeTextHumanLike(el, value) {
    if (!el || value === undefined || value === null) return false;
    const strVal = String(value);
    programmaticTypingSet.add(el);
    try {
      await scrollElementIntoViewSmoothly(el, "#3b82f6");
      const targetUid = `aa_inp_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      el.setAttribute("data-aa-cdp-target", targetUid);
      const rect = el.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;

      let cdpTyped = false;
      if (rect.width > 8 && rect.height > 8 && cx > 0 && cy > 0) {
        const cdpRes = await sendCdpCloakBrowserInteract({
          mode: "type",
          url: window.location.href,
          target_uid: targetUid,
          x: cx,
          y: cy,
          text: strVal,
        });
        if (cdpRes && cdpRes.cdp_used && String(el.value || "").trim() === strVal.trim()) {
          cdpTyped = true;
        }
      }
      try {
        el.removeAttribute("data-aa-cdp-target");
      } catch (_) {}

      if (!cdpTyped) {
        simulateMouseClickOnElement(el);
        el.focus();
        el.dispatchEvent(new FocusEvent("focus", { bubbles: true }));

        if (el.value) {
          setNativeInputValueStep(el, "", "");
          await new Promise((r) => setTimeout(r, 35));
        }

        let current = "";
        for (const ch of Array.from(strVal)) {
          const keyCode = ch.charCodeAt(0) || 65;
          current += ch;

          el.dispatchEvent(
            new KeyboardEvent("keydown", {
              key: ch,
              code: /^[0-9]$/.test(ch) ? `Digit${ch}` : `Key${ch.toUpperCase()}`,
              keyCode,
              which: keyCode,
              bubbles: true,
            })
          );
          el.dispatchEvent(
            new KeyboardEvent("keypress", {
              key: ch,
              charCode: keyCode,
              keyCode,
              which: keyCode,
              bubbles: true,
            })
          );
          setNativeInputValueStep(el, current, ch);
          el.dispatchEvent(
            new KeyboardEvent("keyup", {
              key: ch,
              code: /^[0-9]$/.test(ch) ? `Digit${ch}` : `Key${ch.toUpperCase()}`,
              keyCode,
              which: keyCode,
              bubbles: true,
            })
          );

          await new Promise((r) => setTimeout(r, humanTypingCadenceMs()));
        }
      }

      el.dispatchEvent(new Event("change", { bubbles: true }));
      el.dispatchEvent(new FocusEvent("blur", { bubbles: true }));
      if (el.classList && (el.classList.contains("pac-target-input") || (el.name || "").toLowerCase().includes("address"))) {
        await new Promise((r) => setTimeout(r, 750));
        const pacItems = Array.from(document.querySelectorAll(".pac-container .pac-item")).filter(
          (item) => item && item.offsetParent !== null
        );
        if (pacItems.length > 0) {
          const cleanCity = strVal.split(",")[0].trim().toLowerCase();
          const bestPac =
            pacItems.find((item) => {
              const txt = (item.innerText || item.textContent || "").trim().toLowerCase();
              return txt.startsWith(cleanCity) && !txt.includes("station") && !txt.includes("skytrain");
            }) || pacItems[0];
          simulateMouseClickOnElement(bestPac);
          await new Promise((r) => setTimeout(r, 220));
        }
      }
      el.dataset.aaAutoFilledValue = String(el.value || "").trim();
      el.style.outline = "2px solid rgba(16, 185, 129, 0.65)";
      el.style.outlineOffset = "1px";
      await new Promise((r) => setTimeout(r, 140 + Math.floor(Math.random() * 90)));
      return true;
    } catch (_) {
      return false;
    } finally {
      setTimeout(() => {
        programmaticTypingSet.delete(el);
      }, 90);
    }
  }

  async function fillReactSelectCombobox(el, value) {
    if (!el || value === undefined || value === null) return false;
    const targetStr = String(value).trim();
    if (!targetStr) return false;
    const normTarget = targetStr.toLowerCase();
    programmaticTypingSet.add(el);

    try {
      await scrollElementIntoViewSmoothly(el, "#3b82f6");
      const control = el.closest(".select__control, [class*='select__control'], [class*='Select-control']") || el;
      simulateMouseClickOnElement(control);
      el.focus();

      // Per Jobs VB Operator Skill Lesson #7: focus input and dispatch ArrowDown to open React-Select menu
      el.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "ArrowDown",
          code: "ArrowDown",
          keyCode: 40,
          which: 40,
          bubbles: true,
        })
      );
      el.dispatchEvent(
        new KeyboardEvent("keyup", {
          key: "ArrowDown",
          code: "ArrowDown",
          keyCode: 40,
          which: 40,
          bubbles: true,
        })
      );
      await new Promise((r) => setTimeout(r, 160));

      const findMatchingOption = () => {
        const fieldContainer =
          el.closest(".field, .form-group, .select, [class*='select-shell'], [data-testid*='field']") || document;
        let opts = Array.from(
          fieldContainer.querySelectorAll(".select__option, [class*='select__option'], [role='option']")
        );
        if (opts.length === 0) {
          opts = Array.from(document.querySelectorAll(".select__option, [class*='select__option'], [role='option']"));
        }
        if (opts.length === 0) return null;

        let match =
          opts.find((o) => (o.innerText || o.textContent || "").trim().toLowerCase() === normTarget) ||
          opts.find((o) => (o.innerText || o.textContent || "").trim().toLowerCase().startsWith(normTarget)) ||
          opts.find((o) => (o.innerText || o.textContent || "").trim().toLowerCase().includes(normTarget)) ||
          opts.find(
            (o) =>
              normTarget.includes((o.innerText || o.textContent || "").trim().toLowerCase()) &&
              (o.innerText || o.textContent || "").trim().length >= 2
          );

        if (!match) {
          if (["yes", "true", "authorized"].some((k) => normTarget === k || normTarget.startsWith(k))) {
            match = opts.find((o) => /\b(yes|authorized|i have|bachelor)\b/i.test(o.innerText || o.textContent || ""));
          } else if (["no", "false"].some((k) => normTarget === k || normTarget.startsWith(k))) {
            match = opts.find((o) => /\bno\b/i.test(o.innerText || o.textContent || ""));
          }
        }
        return match || null;
      };

      let optionEl = findMatchingOption();
      if (!optionEl) {
        setNativeInputValueStep(el, "", "");
        let typedSoFar = "";
        for (const ch of Array.from(targetStr)) {
          typedSoFar += ch;
          setNativeInputValueStep(el, typedSoFar, ch);
          await new Promise((r) => setTimeout(r, humanTypingCadenceMs()));
        }
        await new Promise((r) => setTimeout(r, 170));
        optionEl = findMatchingOption();
      }

      if (optionEl) {
        const pickedLabel = (optionEl.innerText || optionEl.textContent || targetStr).trim();
        simulateMouseClickOnElement(optionEl);
        await new Promise((r) => setTimeout(r, 110));
        el.dataset.aaAutoFilledValue = pickedLabel;
        if (control && control.style) {
          control.style.outline = "2px solid rgba(16, 185, 129, 0.65)";
          control.style.outlineOffset = "1px";
        }
        return true;
      }

      el.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "Enter",
          code: "Enter",
          keyCode: 13,
          which: 13,
          bubbles: true,
        })
      );
      el.dataset.aaAutoFilledValue = targetStr;
      await new Promise((r) => setTimeout(r, 80));
      return true;
    } catch (_) {
      return false;
    } finally {
      setTimeout(() => {
        programmaticTypingSet.delete(el);
      }, 90);
    }
  }

  function fillNativeElementValue(el, value) {
    if (!el || value === undefined || value === null) return false;
    const strVal = String(value);
    programmaticTypingSet.add(el);
    try {
      el.focus();
      const tag = el.tagName.toLowerCase();
      if (tag === "select") {
        const opts = Array.from(el.options || []);
        const normTarget = strVal.trim().toLowerCase();
        const primaryToken = normTarget.split(/[,(]/)[0].trim();
        let matched =
          opts.find((o) => (o.value || "").trim().toLowerCase() === normTarget) ||
          opts.find((o) => (o.text || "").trim().toLowerCase() === normTarget) ||
          opts.find((o) => (o.text || "").trim().toLowerCase().includes(normTarget)) ||
          opts.find((o) => normTarget.includes((o.text || "").trim().toLowerCase()) && (o.text || "").trim().length > 1) ||
          (primaryToken.length >= 3
            ? opts.find((o) => (o.text || "").trim().toLowerCase().startsWith(primaryToken))
            : null);

        if (!matched) {
          if (["yes", "true", "authorized", "i am authorized"].some((k) => normTarget.includes(k))) {
            matched = opts.find((o) => /\b(yes|authorized|eligible)\b/i.test(o.text || ""));
          } else if (["no", "false"].some((k) => normTarget === k || normTarget.startsWith("no"))) {
            matched = opts.find((o) => /\bno\b/i.test(o.text || ""));
          }
        }
        if (matched) {
          el.value = matched.value;
          el.dataset.aaAutoFilledValue = String(matched.text || matched.value || "").trim();
          el.dispatchEvent(new Event("input", { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));
          el.style.outline = "2px solid rgba(16, 185, 129, 0.65)";
          return true;
        }
        return false;
      }

      setNativeInputValueStep(el, strVal, strVal);
      el.dataset.aaAutoFilledValue = strVal.trim();
      el.dispatchEvent(new Event("change", { bubbles: true }));
      el.dispatchEvent(new Event("blur", { bubbles: true }));
      el.style.outline = "2px solid rgba(16, 185, 129, 0.55)";
      el.style.outlineOffset = "1px";
      return true;
    } catch (_) {
      return false;
    } finally {
      setTimeout(() => {
        programmaticTypingSet.delete(el);
      }, 90);
    }
  }

  function matchStandardCandidateAnswer(metaText, cand, common) {
    const m = (metaText || "").toLowerCase();
    if (!m) return "";

    if (m.includes("first name") || m.includes("given name") || /\bfname\b/.test(m) || m.includes("first_name")) {
      return cand.first_name || "Alex";
    }
    if (m.includes("last name") || m.includes("surname") || m.includes("family name") || /\blname\b/.test(m) || m.includes("last_name")) {
      return cand.last_name || "Mercer";
    }
    if (m.includes("full name") || m === "name" || m === "your name" || m.includes("legal name")) {
      return cand.full_name || "Alex Mercer";
    }
    if (m.includes("email")) return cand.email || "";
    if (m.includes("country code") || m.includes("phone country")) {
      return cand.country || "Canada (+1)";
    }
    if (m.includes("phone") || m.includes("mobile") || m.includes("tel")) return cand.phone || "";
    if (m.includes("linkedin")) return cand.linkedin_url || "https://www.linkedin.com/in/alexander-mercer/";
    if (m.includes("github")) return cand.github_url || "";
    if (m.includes("portfolio") || m.includes("website") || m.includes("personal site") || m.includes("blog")) {
      return cand.website_url || cand.portfolio_url || "https://www.turboapply.ca";
    }
    if (m.includes("technical degree") || m.includes("engineering degree") || m.includes("computer science degree") || m.includes("bachelor")) {
      return cand.has_technical_degree || "Yes";
    }
    if (m.includes("most recent ai") || (m.includes("delivery process") && m.includes("ai")) || (m.includes("2-3 sentences") && m.includes("ai"))) {
      return common.ai_product_delivery_process || common.why_company || "";
    }
    if (m.includes("years") || m.includes("how many years")) {
      const ungroundedDomains = [
        "cyber",
        "security",
        "infosec",
        "penetration",
        "soc ",
        "siem",
        "healthcare",
        "clinical",
        "medical",
        "biotech",
        "pharma",
        "fintech",
        "banking",
        "crypto",
        "blockchain",
        "web3",
        "gaming",
        "legal",
        "tax",
        "accounting",
        "defense",
        "clearance",
      ];
      if (ungroundedDomains.some((d) => m.includes(d))) {
        return "0";
      }
      if (
        ["product", "project", "program", "engineering", "software", "iot", "ai", "automation", "management", "leadership"].some(
          (d) => m.includes(d)
        )
      ) {
        return String(cand.years_of_experience || "6").replace(/[^0-9]/g, "") || "6";
      }
      return String(cand.years_of_experience || "6").replace(/[^0-9]/g, "") || "6";
    }
    if (m.includes("city") && !m.includes("ethnicity")) return cand.city || cand.location || "";
    if (m.includes("country")) return cand.country || "Canada";
    if (m.includes("location") || m.includes("address") || m.includes("where are you based")) return cand.location || "";
    if (m.includes("current company") || m.includes("current employer") || m.includes("organization")) return cand.current_company || "";
    if (m.includes("current title") || m.includes("job title") || m.includes("headline") || m.includes("current role")) return cand.headline || "";
    if (m.includes("salary") || m.includes("compensation") || m.includes("pay expectation") || m.includes("remuneration")) {
      return cand.salary_expectation || "";
    }
    if (m.includes("notice period") || m.includes("start date") || m.includes("when can you start") || m.includes("available to start")) {
      return cand.notice_period || "2 weeks";
    }
    if (m.includes("require sponsorship") || m.includes("need sponsorship") || m.includes("visa sponsorship") || m.includes("future sponsorship")) {
      return cand.requires_sponsorship || "No";
    }
    if (
      m.includes("confirm that you received") ||
      m.includes("confirm you have received") ||
      m.includes("confirm receipt") ||
      m.includes("receipt confirmation") ||
      m.includes("received the video interview") ||
      m.includes("received the test") ||
      m.includes("received the assessment") ||
      m.includes("received the link")
    ) {
      return "Yes";
    }
    if (
      m.includes("legally authorized") ||
      m.includes("work authorization") ||
      m.includes("authorized to work") ||
      m.includes("right to work") ||
      m.includes("eligible to work") ||
      m.includes("comfortable working") ||
      m.includes("commut") ||
      m.includes("relocat") ||
      m.includes("background check") ||
      m.includes("drug test") ||
      m.includes("18 years") ||
      m.includes("fluent") ||
      m.includes("proficiency")
    ) {
      return cand.authorized_to_work || "Yes";
    }
    if (m.includes("cover letter") || m.includes("additional information") || m.includes("anything else")) {
      return common.cover_letter_text || common.summary || "";
    }
    if (m.includes("why do you want") || m.includes("why are you interested") || m.includes("why this role") || m.includes("why join")) {
      return common.why_company || common.why_role || "";
    }
    if (m.includes("tell us about yourself") || m.includes("professional summary") || m.includes("bio")) {
      return common.summary || "";
    }
    if (m.includes("how did you hear") || m.includes("source")) {
      return "LinkedIn";
    }
    return "";
  }

  function detectPasswordValidationErrorOnPage(passwordEls, attemptedPassword) {
    for (const el of passwordEls) {
      if (!el) continue;
      if (attemptedPassword && el.value && el.value.length > 0 && el.value.length < attemptedPassword.length) {
        return true;
      }
      const maxLenAttr = el.getAttribute("maxlength");
      if (maxLenAttr && /^\d+$/.test(maxLenAttr) && parseInt(maxLenAttr, 10) < attemptedPassword.length) {
        return true;
      }
      if (el.validity && (el.validity.tooLong || el.validity.patternMismatch || !el.validity.valid)) {
        return true;
      }
      if (el.getAttribute("aria-invalid") === "true") {
        return true;
      }
      const container = el.closest(".field, .form-group, [data-automation-id], div") || el.parentElement;
      if (container) {
        const txt = (container.innerText || "").toLowerCase();
        if (
          /too long|maximum|max .* characters|8 to 1[2-9]|between .* and 1[2-9]|exceeds|invalid password|password must be/i.test(
            txt
          ) &&
          /error|invalid|must|maximum|limit/i.test(txt)
        ) {
          return true;
        }
      }
    }
    return false;
  }

  async function maybeHandleRegistrationAndEmailOtpFlow(pkg, meta, onProgress) {
    const cand = (pkg && (pkg.candidate || pkg.standard_profile)) || {};
    const siteCreds = (pkg && pkg.site_credentials) || {};
    const emailVal = cand.email || "alex.mercer@example.com";

    // Look for a "Send Code" / "Send Verification Code" button on registration / sign-up pages (e.g. Dawn's Join Dawn Today panel)
    const allButtons = Array.from(document.querySelectorAll('button, [role="button"], input[type="button"]')).filter(
      (b) => b && !b.disabled && !host.contains(b) && b.offsetParent !== null
    );
    const sendCodeBtn = allButtons.find((b) => {
      const txt = (b.innerText || b.value || b.textContent || "").replace(/\s+/g, " ").trim();
      return /^(?:send|get|request)\s+(?:verification\s+|one[- ]time\s+)?code$/i.test(txt);
    });

    if (!sendCodeBtn) {
      return { handled: false, fieldsFilled: 0 };
    }

    // Clear accidental fills in any side-by-side "Returning Users" / Sign-In panel first
    const signInEmail = document.querySelector("#si-email, .dsp-mid input[type='text'], .dsp-mid input[type='email']");
    const signInPass = document.querySelector("#si-password, .dsp-mid input[type='password']");
    if (signInEmail && signInPass) {
      setNativeInputValueStep(signInEmail, "", "");
      setNativeInputValueStep(signInPass, "", "");
      signInEmail.style.outline = "";
      signInPass.style.outline = "";
    }

    // Find the registration email input inside the same registration container as Send Code
    const regPanel =
      sendCodeBtn.closest(".dsp-right, [class*='signup'], [class*='register'], form, section, div") || document;
    const regEmailInput =
      regPanel.querySelector('input[type="email"], input[placeholder*="email" i], input[type="text"]') ||
      document.querySelector('.dsp-right input[type="email"]');

    let filledCount = 0;
    if (regEmailInput) {
      if (onProgress) {
        onProgress(`📨 Entering ${emailVal} for account registration…`, "Registering…");
      }
      await typeTextHumanLike(regEmailInput, emailVal);
      filledCount += 1;
    }

    const otpMinTimestamp = Math.floor(Date.now() / 1000) - 10;
    if (onProgress) {
      onProgress("📨 Requesting one-time verification code…", "Sending Code…");
    }
    await scrollElementIntoViewSmoothly(sendCodeBtn, "#3b82f6");
    simulateMouseClickOnElement(sendCodeBtn);
    await new Promise((r) => setTimeout(r, 1800));

    // Check if the site reported that the account already exists (in which case sign in via Returning Users)
    const pageBodyLower = ((document.body && document.body.innerText) || "").toLowerCase();
    if (
      (pageBodyLower.includes("already registered") ||
        pageBodyLower.includes("already exists") ||
        pageBodyLower.includes("account with this email already") ||
        pageBodyLower.includes("please sign in")) &&
      signInEmail &&
      signInPass &&
      siteCreds.password
    ) {
      if (onProgress) {
        onProgress("🔐 Account already registered — signing in…", "Signing In…");
      }
      await typeTextHumanLike(signInEmail, emailVal);
      await typeTextHumanLike(signInPass, siteCreds.password);
      const signInBtn = allButtons.find((b) =>
        /^(?:sign\s*in|log\s*in)$/i.test((b.innerText || b.value || b.textContent || "").trim())
      );
      if (signInBtn) {
        simulateMouseClickOnElement(signInBtn);
        await new Promise((r) => setTimeout(r, 2800));
      }
      return { handled: true, fieldsFilled: 2 };
    }

    if (onProgress) {
      onProgress(`📬 Checking Gmail (${emailVal}) for verification code…`, "Reading Gmail Code…");
    }
    const otpResp = await sendBridgeAction("fetch_gmail_verification_code", {
      domain: window.location.hostname,
      company_name: (meta && meta.company_name) || "",
      account_email: emailVal,
      min_timestamp: otpMinTimestamp,
      timeout_seconds: 26,
    });

    const otpObj = (otpResp && otpResp.data && otpResp.data.gmail_otp_result) || {};
    const otpCode = String(otpObj.code || "").trim();
    if (!otpCode) {
      return { handled: true, fieldsFilled: filledCount };
    }

    if (onProgress) {
      onProgress(`🔑 Entering verification code ${otpCode} from Gmail…`, `Code ${otpCode}…`);
    }

    const codeBoxes = Array.from(
      document.querySelectorAll(
        'input.dsp-code-box-new, .dsp-code-boxes input, input[class*="code-box"], input[class*="otp"], input[maxlength="1"]'
      )
    ).filter((el) => el && !el.disabled && !host.contains(el) && el.offsetParent !== null);

    if (codeBoxes.length >= otpCode.length) {
      for (let i = 0; i < otpCode.length; i++) {
        typeCharIntoReactBox(codeBoxes[i], otpCode.charAt(i));
        await new Promise((r) => setTimeout(r, 95));
      }
      filledCount += otpCode.length;
    } else {
      const singleOtpInput = Array.from(document.querySelectorAll("input")).find((el) => {
        if (!el || el.disabled || host.contains(el) || el === regEmailInput || el === signInEmail) return false;
        const m = `${getFieldLabelText(el)} ${el.placeholder || ""} ${el.name || ""} ${el.id || ""}`.toLowerCase();
        return m.includes("code") || m.includes("otp") || m.includes("verification");
      });
      if (singleOtpInput) {
        await typeTextHumanLike(singleOtpInput, otpCode);
        filledCount += 1;
      }
    }

    await new Promise((r) => setTimeout(r, 350));
    const confirmBtn = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"]')).find(
      (b) => {
        if (!b || b.disabled || host.contains(b)) return false;
        const txt = (b.innerText || b.value || b.textContent || "").replace(/\s+/g, " ").trim();
        return /^(?:confirm|verify|verify code|continue|submit code)$/i.test(txt);
      }
    );
    if (confirmBtn) {
      if (onProgress) {
        onProgress("✅ Confirming email verification code…", "Confirming…");
      }
      await scrollElementIntoViewSmoothly(confirmBtn, "#10b981");
      simulateMouseClickOnElement(confirmBtn);
      await waitForCondition(
        () =>
          !document.body.innerText.includes("Send Code") ||
          Boolean(document.querySelector('input[name="firstName"], select[name="country"]')),
        4500,
        300
      );
      await new Promise((r) => setTimeout(r, 500));
    }

    return { handled: true, fieldsFilled: filledCount };
  }

  function findDocumentFileInputsInScope(rootScope) {
    return queryAllDeep('input[type="file"]', rootScope || document).filter((el) => {
      if (!el || el.disabled || host.contains(el) || isSearchOrNavControl(el) || el.closest(".ashby-application-form-autofill-input-root")) {
        return false;
      }
      const acceptAttr = (el.getAttribute("accept") || "").toLowerCase();
      const isImageOrVideoOnly =
        (acceptAttr.includes("image/") ||
          acceptAttr.includes("video/") ||
          /\.(png|jpg|jpeg|webp|gif|svg|mp4|mov|avi|webm)\b/.test(acceptAttr)) &&
        !acceptAttr.includes(".pdf") &&
        !acceptAttr.includes("application/pdf") &&
        !acceptAttr.includes(".doc");
      if (isImageOrVideoOnly) return false;
      const metaLabel = (
        getFieldLabelText(el) +
        " " +
        (el.closest(".js-field, .field, .form-group, label")?.innerText || "")
      ).toLowerCase();
      if (/\b(profile photo|profile pic|headshot|avatar|intro video|upload image)\b/i.test(metaLabel) && !metaLabel.includes("resume")) {
        return false;
      }
      return true;
    });
  }

  async function applyPrefillPackageToDOMAsync(pkg, onProgress, options = {}) {
    if (!pkg) return { filesUploaded: 0, fieldsFilled: 0, passwordAdjustedTo12: false };
    const skipFiles = Boolean(options && options.skipFiles);
    const onlyFiles = Boolean(options && options.onlyFiles);
    const hostName = (window.location.hostname || "").toLowerCase();
    let rootScope = document;
    if (hostName.includes("linkedin.com")) {
      const openModal = findOpenEasyApplyModal();
      if (!openModal) return { filesUploaded: 0, fieldsFilled: 0, passwordAdjustedTo12: false };
      rootScope = openModal;
    }

    const cand = pkg.candidate || pkg.standard_profile || {};
    const docs = pkg.documents || pkg.files || {};
    const fieldAnswers = pkg.field_answers || pkg.field_values || {};
    const common = pkg.common_answers || {};
    const siteCreds = pkg.site_credentials || {};

    let filesUploaded = 0;
    let fieldsFilled = 0;
    let passwordAdjustedTo12 = false;

    // 0. If this page has an Email Registration + 1-Time Verification Code (OTP) flow (e.g. Dawn /signin),
    // complete email verification via Gmail IMAP first so Step 2 registration fields open automatically!
    if (!onlyFiles && !hostName.includes("linkedin.com")) {
      const otpFlowRes = await maybeHandleRegistrationAndEmailOtpFlow(pkg, extractJobMetadataFromPage(), onProgress);
      if (otpFlowRes && otpFlowRes.handled) {
        fieldsFilled += otpFlowRes.fieldsFilled || 0;
      }
    }

    // 1. Upload Resume PDF and Cover Letter PDF into document <input type="file"> (skipping image-only Profile Photo or video inputs)
    if (!skipFiles) {
      const fileInputs = findDocumentFileInputsInScope(rootScope);
      let resumeAssigned = false;
      let coverAssigned = false;

      for (let idx = 0; idx < fileInputs.length; idx++) {
        const inp = fileInputs[idx];
        if (inp.getAttribute("data-aa-file-attached") === "1") continue;
        const meta = (
          getFieldLabelText(inp) +
          " " +
          (inp.name || "") +
          " " +
          (inp.id || "") +
          " " +
          (inp.closest(".js-field, .field, .form-group, .jobs-document-upload, [data-testid*='upload'], label")?.innerText || "")
        ).toLowerCase();

        if (meta.includes("cover") && docs.cover_letter && docs.cover_letter.base64) {
          if (onProgress) onProgress("📄 Uploading Cover Letter PDF…", "Uploading Cover Letter…");
          await scrollElementIntoViewSmoothly(inp, "#10b981");
          if (attachPdfToFileInput(inp, docs.cover_letter)) {
            inp.setAttribute("data-aa-file-attached", "1");
            filesUploaded++;
            coverAssigned = true;
            await new Promise((r) => setTimeout(r, 180));
          }
        } else if (
          (meta.includes("resume") || meta.includes("cv") || (!resumeAssigned && idx === 0)) &&
          docs.resume &&
          docs.resume.base64
        ) {
          if (onProgress) onProgress("📄 Uploading Tailored Resume PDF…", "Uploading Resume…");
          await scrollElementIntoViewSmoothly(inp, "#10b981");
          if (attachPdfToFileInput(inp, docs.resume)) {
            inp.setAttribute("data-aa-file-attached", "1");
            filesUploaded++;
            resumeAssigned = true;
            await new Promise((r) => setTimeout(r, 180));
          }
        } else if (!coverAssigned && idx === 1 && docs.cover_letter && docs.cover_letter.base64) {
          if (onProgress) onProgress("📄 Uploading Cover Letter PDF…", "Uploading Cover Letter…");
          await scrollElementIntoViewSmoothly(inp, "#10b981");
          if (attachPdfToFileInput(inp, docs.cover_letter)) {
            inp.setAttribute("data-aa-file-attached", "1");
            filesUploaded++;
            coverAssigned = true;
            await new Promise((r) => setTimeout(r, 180));
          }
        }
      }

      // 1b. LinkedIn Easy Apply Resume Card selection: if LinkedIn shows pre-uploaded resume cards, ensure one is selected
      if (hostName.includes("linkedin.com")) {
        const resumeCardRadios = queryAllDeep(
          '.jobs-document-upload-redesign-card__container input[type="radio"], [class*="resume-card"] input[type="radio"], input[type="radio"][name*="document"]',
          rootScope
        );
        if (resumeCardRadios.length > 0) {
          const anyChecked = resumeCardRadios.some((r) => r.checked);
          if (!anyChecked) {
            const firstRadio = resumeCardRadios[0];
            const cardLabel =
              firstRadio.closest(".jobs-document-upload-redesign-card__container, label") || firstRadio;
            await clickElementWithAgent(cardLabel, true);
            firstRadio.checked = true;
            firstRadio.dispatchEvent(new Event("change", { bubbles: true }));
          }
          if (filesUploaded === 0) filesUploaded++;
        }
      }
    }

    if (onlyFiles) {
      return { filesUploaded, fieldsFilled: 0, passwordAdjustedTo12: false };
    }

    // 2. Scroll to and human-type each form control sequentially (allowing dependent selects like Country -> City to enable dynamically)
    const allControls = queryAllDeep("input, textarea, select", rootScope).filter(
      (el) => el && !el.readOnly && !host.contains(el) && !isSearchOrNavControl(el)
    );

    const actionableControls = allControls.filter((el) => {
      const rawType = (el.getAttribute("type") || el.tagName.toLowerCase()).toLowerCase();
      if (["hidden", "file", "submit", "button", "reset", "image"].includes(rawType)) return false;
      if (el.classList && el.classList.contains("dsp-code-box-new")) return false;
      return true;
    });

    const hasCountryCodeSelect = actionableControls.some((el) => {
      const lbl = getFieldLabelText(el).toLowerCase();
      return lbl.includes("country code") || (el.id || "").toLowerCase().includes("country");
    });

    const passwordElementsFilled = [];
    const answeredRadioGroups = new Set();

    for (let cIdx = 0; cIdx < actionableControls.length; cIdx++) {
      const el = actionableControls[cIdx];
      if (!el || !el.isConnected) continue;
      if (el.disabled) {
        if (el.tagName.toLowerCase() === "select") {
          await waitForCondition(() => !el.disabled && el.options && el.options.length > 1, 2600, 200);
        }
        if (el.disabled) continue;
      }
      const rawType = (el.getAttribute("type") || el.tagName.toLowerCase()).toLowerCase();
      const isCombobox =
        el.getAttribute("role") === "combobox" ||
        el.classList.contains("select__input") ||
        Boolean(el.closest(".select__control, [class*='react-select'], [data-test-single-typeahead-entity-form-component]"));

      const fieldId = el.getAttribute("data-aa-field-id") || "";
      const label = getFieldLabelText(el);
      const shortLabel = (label.split("/")[0] || el.name || el.id || "Field").replace(/\*/g, "").trim().slice(0, 28);
      const meta = `${label} ${el.name || ""} ${el.id || ""} ${el.placeholder || ""}`.trim();
      const lowerMeta = meta.toLowerCase();

      if (rawType === "radio") {
        // Skip LinkedIn resume card radios (handled above)
        if (el.closest(".jobs-document-upload-redesign-card__container, [class*='resume-card']")) {
          continue;
        }
        const radioFs = el.closest("fieldset, [role='radiogroup'], .fb-dash-form-element");
        const groupKey = el.name || (radioFs && (radioFs.id || fieldId)) || fieldId || label;
        if (groupKey && answeredRadioGroups.has(groupKey)) {
          continue;
        }
        const rootNode = (el.getRootNode && el.getRootNode()) || document;
        const queryRoot = rootNode && rootNode.querySelector ? rootNode : document;
        let assocLabel = null;
        let siblingLabelText = "";
        if (el.id) {
          try {
            assocLabel =
              queryRoot.querySelector(`label[for="${CSS.escape(el.id)}"]`) ||
              document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
            if (assocLabel) siblingLabelText = (assocLabel.innerText || assocLabel.textContent || "").trim();
          } catch (_) {}
        }
        if (!assocLabel) {
          assocLabel = el.closest("label");
        }
        const optionLabelText = (siblingLabelText || assocLabel?.innerText || el.value || "").trim();
        const optionLower = optionLabelText.toLowerCase();

        const answer =
          fieldAnswers[fieldId] ||
          (el.name && fieldAnswers[el.name]) ||
          (radioFs && radioFs.id && fieldAnswers[radioFs.id]) ||
          fieldAnswers[label] ||
          matchStandardCandidateAnswer(meta, cand, common) ||
          (lowerMeta.includes("sponsorship") || lowerMeta.includes("visa") ? "No" : "Yes");

        if (answer) {
          const normAns = String(answer).trim().toLowerCase();
          const isAffirmativeAns = ["yes", "true", "1", "confirm", "confirmed", "i confirm"].includes(normAns);
          const isNegativeAns = ["no", "false", "0"].includes(normAns);
          const isMatch =
            optionLower === normAns ||
            (el.value && String(el.value).trim().toLowerCase() === normAns) ||
            ((normAns.startsWith("yes") || isAffirmativeAns) && /^yes\b/i.test(optionLower)) ||
            ((normAns.startsWith("no") || isNegativeAns) && /^no\b/i.test(optionLower)) ||
            (optionLower.length > 1 && normAns.includes(optionLower)) ||
            (normAns.length > 1 && optionLower.includes(normAns));

          if (isMatch) {
            if (!el.checked) {
              await scrollElementIntoViewSmoothly(el, "#3b82f6");
              await clickElementWithAgent(el, true);
              await new Promise((r) => setTimeout(r, 90));
              if (!el.checked && assocLabel) {
                await clickElementWithAgent(assocLabel, true);
                await new Promise((r) => setTimeout(r, 80));
              }
              if (!el.checked) {
                try {
                  if (el._valueTracker && typeof el._valueTracker.setValue === "function") {
                    el._valueTracker.setValue("false");
                  }
                  const nativeCheckedSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype,
                    "checked"
                  )?.set;
                  if (nativeCheckedSetter) {
                    nativeCheckedSetter.call(el, true);
                  } else {
                    el.checked = true;
                  }
                } catch (_) {
                  el.checked = true;
                }
                el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
                el.dispatchEvent(new Event("input", { bubbles: true }));
                el.dispatchEvent(new Event("change", { bubbles: true }));
                await new Promise((r) => setTimeout(r, 60));
              }
            }
            if (groupKey) answeredRadioGroups.add(groupKey);
            fieldsFilled++;
          }
        }
        continue;
      }

      if (rawType === "checkbox") {
        if (
          lowerMeta.includes("privacy") ||
          lowerMeta.includes("terms") ||
          lowerMeta.includes("consent") ||
          lowerMeta.includes("acknowledge") ||
          lowerMeta.includes("certify") ||
          lowerMeta.includes("agree")
        ) {
          if (!el.checked) {
            await scrollElementIntoViewSmoothly(el, "#3b82f6");
            await clickElementWithAgent(el, true);
            el.checked = true;
            el.dispatchEvent(new Event("change", { bubbles: true }));
            fieldsFilled++;
          }
        }
        continue;
      }

      // If an input or select on LinkedIn Easy Apply is ALREADY validly populated (e.g. Email address, Country code, Mobile phone number),
      // keep the valid pre-filled value instead of clobbering it or returning 0 fieldsFilled!
      const existingVal = String(el.value || "").trim();
      if (hostName.includes("linkedin.com") && existingVal && !/^select\b|^choose\b|^--/i.test(existingVal)) {
        if (el.tagName.toLowerCase() === "select") {
          const selOpt = el.options && el.options[el.selectedIndex];
          const selText = ((selOpt && selOpt.text) || existingVal).trim();
          if (selText && !/^select\b|^choose\b|^--/i.test(selText)) {
            fieldsFilled++;
            continue;
          }
        } else if (
          lowerMeta.includes("email") ||
          lowerMeta.includes("phone") ||
          lowerMeta.includes("mobile") ||
          lowerMeta.includes("first name") ||
          lowerMeta.includes("last name")
        ) {
          fieldsFilled++;
          continue;
        }
      }

      let targetValue =
        fieldAnswers[fieldId] ||
        (el.name && fieldAnswers[el.name]) ||
        (el.id && fieldAnswers[el.id]) ||
        (label && fieldAnswers[label]) ||
        matchStandardCandidateAnswer(meta, cand, common);

      if (rawType === "password" && siteCreds.password) {
        targetValue = siteCreds.password;
      }

      // Format phone number cleanly if a separate Phone Country Code dropdown exists (LinkedIn requires digits only without +1 or spaces)
      if (
        targetValue &&
        (lowerMeta.includes("phone") || lowerMeta.includes("mobile") || rawType === "tel") &&
        !lowerMeta.includes("country code")
      ) {
        const digitsOnly = String(targetValue).replace(/\D/g, "");
        if (hasCountryCodeSelect || hostName.includes("linkedin.com")) {
          targetValue =
            digitsOnly.length === 11 && digitsOnly.startsWith("1") ? digitsOnly.slice(1) : digitsOnly || targetValue;
        }
      }

      // Format numeric inputs or "how many years" questions as clean integer numbers (LinkedIn rejects "6 years" in numeric fields)
      if (
        targetValue &&
        (rawType === "number" ||
          lowerMeta.includes("how many years") ||
          lowerMeta.includes("years of experience") ||
          lowerMeta.includes("years of work"))
      ) {
        const numMatch = String(targetValue).match(/\d+/);
        targetValue = numMatch ? numMatch[0] : "5";
      }

      if (!targetValue && el.tagName.toLowerCase() === "select") {
        // Fallback for required <select> dropdowns on multi-page modals
        const validOpts = Array.from(el.options || []).filter((o) => {
          const t = (o.text || o.value || "").trim();
          return t && !/^select\b|^choose\b|^--/i.test(t);
        });
        const yesOpt = validOpts.find((o) => /^yes\b/i.test((o.text || "").trim()));
        const noOpt = validOpts.find((o) => /^no\b/i.test((o.text || "").trim()));
        if ((lowerMeta.includes("sponsorship") || lowerMeta.includes("visa")) && noOpt) {
          targetValue = noOpt.text.trim();
        } else if (yesOpt) {
          targetValue = yesOpt.text.trim();
        } else if (validOpts.length > 0) {
          targetValue = (validOpts[0].text || validOpts[0].value || "").trim();
        }
      }

      if (!targetValue && el.tagName.toLowerCase() === "textarea") {
        if (lowerMeta.includes("ai") && common.ai_product_delivery_process) {
          targetValue = common.ai_product_delivery_process;
        } else {
          targetValue = common.why_company || common.summary || "";
        }
      }

      if (!targetValue && (el.required || el.getAttribute("aria-required") === "true" || label.includes("*"))) {
        targetValue = rawType === "number" ? "5" : cand.location || "Vancouver, BC, Canada";
      }

      if (!targetValue) continue;

      if (onProgress) {
        onProgress(
          `⌨️ Filling "${shortLabel}" (${cIdx + 1}/${actionableControls.length})…`,
          `Filling ${cIdx + 1}/${actionableControls.length}…`
        );
      }

      let ok = false;
      if (isCombobox) {
        ok = await fillReactSelectCombobox(el, targetValue);
      } else if (el.tagName.toLowerCase() === "select") {
        await scrollElementIntoViewSmoothly(el, "#3b82f6");
        ok = fillNativeElementValue(el, targetValue);
      } else {
        ok = await typeTextHumanLike(el, targetValue);
      }

      if (ok) {
        fieldsFilled++;
        if (rawType === "password") {
          passwordElementsFilled.push(el);
        }
      }
    }

    // 2b. Safety completion pass for unanswered <fieldset> / [role="radiogroup"] radio groups (e.g. Greenhouse CandidateFacing.Form unnamed React radios)
    if (!options.onlyFiles) {
      const radioGroups = queryAllDeep("fieldset, [role='radiogroup']", rootScope).filter(
        (fs) =>
          fs &&
          !host.contains(fs) &&
          !fs.closest(".jobs-document-upload-redesign-card__container, [class*='resume-card']")
      );
      for (const fs of radioGroups) {
        const rect = fs.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) continue;
        const radios = Array.from(fs.querySelectorAll("input[type='radio']")).filter((r) => !r.disabled);
        if (radios.length === 0 || radios.some((r) => r.checked)) continue;
        const legendTxt = (
          (fs.querySelector("legend, .field-label, h3, h4")?.innerText || fs.getAttribute("aria-label") || "")
        )
          .trim()
          .toLowerCase();
        const preferNo =
          legendTxt.includes("sponsorship") ||
          legendTxt.includes("visa") ||
          legendTxt.includes("previously worked") ||
          legendTxt.includes("former employee") ||
          legendTxt.includes("government official") ||
          legendTxt.includes("conflict of interest") ||
          legendTxt.includes("relative");
        const desiredPrefix = preferNo ? /^no\b/i : /^yes\b/i;
        const fallbackRadio =
          radios.find((r) => {
            const lbl = (r.closest("label")?.innerText || r.value || "").trim();
            return desiredPrefix.test(lbl);
          }) || radios[0];
        if (fallbackRadio) {
          await scrollElementIntoViewSmoothly(fallbackRadio, "#3b82f6");
          await clickElementWithAgent(fallbackRadio, true);
          await new Promise((r) => setTimeout(r, 90));
          if (!fallbackRadio.checked) {
            const wrapLbl = fallbackRadio.closest("label");
            if (wrapLbl) {
              await clickElementWithAgent(wrapLbl, true);
              await new Promise((r) => setTimeout(r, 80));
            }
          }
          if (!fallbackRadio.checked) {
            try {
              if (fallbackRadio._valueTracker && typeof fallbackRadio._valueTracker.setValue === "function") {
                fallbackRadio._valueTracker.setValue("false");
              }
              const nativeCheckedSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype,
                "checked"
              )?.set;
              if (nativeCheckedSetter) {
                nativeCheckedSetter.call(fallbackRadio, true);
              } else {
                fallbackRadio.checked = true;
              }
            } catch (_) {
              fallbackRadio.checked = true;
            }
            fallbackRadio.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
            fallbackRadio.dispatchEvent(new Event("input", { bubbles: true }));
            fallbackRadio.dispatchEvent(new Event("change", { bubbles: true }));
            await new Promise((r) => setTimeout(r, 60));
          }
          if (fallbackRadio.checked) {
            fieldsFilled++;
          }
        }
      }
    }

    // 3. If password fields were filled with a 20-char password and the platform rejected/truncated it,
    // automatically adjust to the 12-char password and update the Password Manager!
    if (
      passwordElementsFilled.length > 0 &&
      siteCreds.password &&
      siteCreds.password.length > 12 &&
      siteCreds.password_12_fallback
    ) {
      await new Promise((r) => setTimeout(r, 220));
      if (detectPasswordValidationErrorOnPage(passwordElementsFilled, siteCreds.password)) {
        if (onProgress) {
          onProgress(
            "🔐 Platform prefers shorter password — adjusting to 12 chars & updating Password Manager…",
            "Adjusting to 12-char…"
          );
        }
        for (const pwEl of passwordElementsFilled) {
          await typeTextHumanLike(pwEl, siteCreds.password_12_fallback);
        }
        passwordAdjustedTo12 = true;
        try {
          await sendBridgeAction("adjust_password_entry_to_12_chars", {
            id: siteCreds.entry_id || "",
            website_url: window.location.href,
            website_name: siteCreds.website_name || "",
          });
        } catch (_) {}
      }
    }

    return { filesUploaded, fieldsFilled, passwordAdjustedTo12 };
  }

  function findModalStepOrSubmitButton(kind = "submit") {
    const openModal = findOpenEasyApplyModal();
    const scope = openModal || document;
    const candidates = queryAllDeep('button, input[type="submit"], a[role="button"]', scope).filter((el) => {
      if (!el || el.disabled || host.contains(el)) return false;
      if (el.closest('header, nav, [role="navigation"], [role="search"], .global-nav')) return false;
      const rect = el.getBoundingClientRect();
      return rect.width > 30 && rect.height > 16;
    });

    const submitPatterns = [
      /^submit application$/i,
      /^send application$/i,
      /^complete application$/i,
      /^apply now$/i,
      /^submit$/i,
      /submit application/i,
    ];

    const nextStepPatterns = [
      /^let['’]?s go$/i,
      /^create account$/i,
      /^complete registration$/i,
      /^save and continue$/i,
      /^review$/i,
      /^review your application$/i,
      /^continue to next step$/i,
      /^next$/i,
      /^continue$/i,
    ];

    const patterns = kind === "submit" ? submitPatterns : nextStepPatterns;
    for (const re of patterns) {
      const match = candidates.find((el) => {
        const txt = (el.innerText || el.value || el.textContent || "").replace(/\s+/g, " ").trim();
        const aria = (el.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim();
        return re.test(txt) || re.test(aria);
      });
      if (match) return match;
    }

    // LinkedIn primary footer button fallback inside Easy Apply modal
    if (openModal) {
      const primaryFooterBtns = queryAllDeep(
        "footer button.artdeco-button--primary, [data-easy-apply-next-button], [data-live-test-easy-apply-next-button], [data-live-test-easy-apply-review-button], [data-live-test-easy-apply-submit-button]",
        openModal
      ).filter((el) => !el.disabled);
      for (const btn of primaryFooterBtns) {
        const txt = `${btn.innerText || ""} ${btn.getAttribute("aria-label") || ""}`.toLowerCase();
        if (kind === "submit" && txt.includes("submit")) return btn;
        if (kind !== "submit" && (txt.includes("next") || txt.includes("review") || txt.includes("continue"))) {
          return btn;
        }
      }
    }

    return null;
  }

  function getModalStepSignature() {
    const openModal = findOpenEasyApplyModal();
    if (!openModal) return window.location.href;
    const progressText = (
      openModal.querySelector(".artdeco-completeness-meter-linear__progress-element, [class*='progress'], span")?.innerText ||
      ""
    ).trim();
    const headingText = Array.from(openModal.querySelectorAll("h1, h2, h3, legend"))
      .map((h) => (h.innerText || "").trim())
      .filter(Boolean)
      .join("|");
    const controlIds = queryAllDeep("input, select, textarea", openModal)
      .map((c) => c.id || c.name || c.type || "")
      .join(",");
    const btnTexts = queryAllDeep("footer button", openModal)
      .map((b) => (b.innerText || "").trim())
      .join("|");
    return `${progressText}::${headingText}::${controlIds}::${btnTexts}`;
  }

  async function fixModalValidationErrorsInPlace(openModal, pkg) {
    if (!openModal) return 0;
    let fixed = 0;
    const errorEls = queryAllDeep(
      '.artdeco-inline-feedback--error, [id$="-error"], .fb-dash-form-element__error-field, [aria-invalid="true"]',
      openModal
    );
    if (errorEls.length === 0) return 0;

    const cand = (pkg && (pkg.candidate || pkg.standard_profile)) || {};
    const controls = queryAllDeep("input, select, textarea", openModal).filter(
      (el) => el && !el.disabled && !el.readOnly && !host.contains(el)
    );
    for (const el of controls) {
      const rawType = (el.getAttribute("type") || el.tagName.toLowerCase()).toLowerCase();
      const wrapper = el.closest(".fb-dash-form-element, .artdeco-text-input, fieldset, div");
      const hasErr =
        el.getAttribute("aria-invalid") === "true" ||
        Boolean(wrapper && wrapper.querySelector('.artdeco-inline-feedback--error, [id$="-error"]'));
      if (!hasErr && el.value && rawType !== "radio") continue;

      if (el.tagName.toLowerCase() === "select") {
        const validOpts = Array.from(el.options || []).filter((o) => {
          const t = (o.text || o.value || "").trim();
          return t && !/^select\b|^choose\b|^--/i.test(t);
        });
        if (validOpts.length > 0) {
          const pick = validOpts.find((o) => /^yes\b/i.test((o.text || "").trim())) || validOpts[0];
          el.value = pick.value;
          el.dispatchEvent(new Event("input", { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));
          fixed++;
        }
      } else if (rawType === "radio") {
        const fs = el.closest("fieldset") || wrapper;
        if (fs && !fs.querySelector('input[type="radio"]:checked')) {
          const radios = Array.from(fs.querySelectorAll('input[type="radio"]'));
          const targetRadio = radios[0];
          if (targetRadio) {
            const rootNode = (targetRadio.getRootNode && targetRadio.getRootNode()) || document;
            const lbl =
              (targetRadio.id &&
                rootNode.querySelector &&
                rootNode.querySelector(`label[for="${CSS.escape(targetRadio.id)}"]`)) ||
              targetRadio;
            await clickElementWithAgent(lbl, true);
            targetRadio.checked = true;
            targetRadio.dispatchEvent(new Event("change", { bubbles: true }));
            fixed++;
          }
        }
      } else if (rawType === "number" || /number|integer|decimal|years/i.test(wrapper?.innerText || "")) {
        await typeTextHumanLike(el, "5");
        fixed++;
      } else if (!el.value) {
        await typeTextHumanLike(el, cand.location || "Vancouver, BC, Canada");
        fixed++;
      }
    }
    return fixed;
  }

  async function waitForCondition(predicate, timeoutMs = 4200, intervalMs = 320) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const res = predicate();
      if (res) return res;
      await new Promise((r) => setTimeout(r, intervalMs));
    }
    return null;
  }

  function updateLiveProgressLabels(detailText, btnText) {
    busyLabel = detailText || busyLabel;
    if (btnText) busyButtonLabel = btnText;
    const btnId = activeWorkingMode === "apply" ? "aa-btn-apply" : "aa-btn-prefill";
    const btnEl = shadow.getElementById(btnId);
    if (btnEl) {
      const spanEl = btnEl.querySelector("span.aa-btn-label");
      if (spanEl && busyButtonLabel) {
        spanEl.textContent = busyButtonLabel;
      }
    }
    const statusBox = shadow.getElementById("aa-live-agent-status");
    if (statusBox && busyLabel) {
      statusBox.textContent = busyLabel;
    }
  }

  async function runPrefillOrApply(mode = "prefill", fromPendingNav = false) {
    if (isBusyWorking) return;
    isBusyWorking = true;
    activeWorkingMode = mode;
    busyButtonLabel = mode === "apply" ? "Applying…" : "Filling Form…";
    activeTab = "copilot";
    currentApplicationIssue = null;
    statusBanner = { text: "", kind: "" };

    let keepDialogGuardArmedForSubmit = false;
    try {
      armMainWorldDialogGuard(mode === "apply" ? "apply" : "prefill", 90000);
      const hostName = (window.location.hostname || "").toLowerCase();
      const feedCards = extractJobCardsFromFeed();
      const specificOpen = isSpecificJobDetailOpen();

      // STEP 1: If user is on a generic Job Feed page (e.g., linkedin.com/jobs/) with no specific job opened yet,
      // open the selected job card (and navigate directly to /jobs/view/<id>/ if no split pane opens)
      if (!specificOpen && feedCards.length > 0 && !fromPendingNav) {
        const idx = Math.min(Math.max(0, selectedFeedJobIndex), feedCards.length - 1);
        const targetCard = feedCards[idx];
        busyLabel = `Opening "${targetCard.title}" at ${targetCard.company_name}…`;
        busyButtonLabel = "Opening Job…";
        render();

        highlightPageElement(targetCard.element, "#3b82f6");
        const pendingPayload = {
          mode,
          title: targetCard.title,
          company_name: targetCard.company_name,
          location: targetCard.location,
          url: targetCard.url || "",
          startedAt: Date.now(),
        };
        try {
          sessionStorage.setItem("aa_pending_agent_action", JSON.stringify(pendingPayload));
        } catch (_) {}
        if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
          try {
            chrome.storage.local.set({ aa_cross_tab_agent_action: pendingPayload });
          } catch (_) {}
        }

        await new Promise((r) => setTimeout(r, 320));
        await clickElementWithAgent(targetCard.element, true);

        // Wait up to 2.2s in case the page opens a split-pane job detail view via SPA
        const openedInPlace = await waitForCondition(() => isSpecificJobDetailOpen(), 2200, 260);
        const navUrl = targetCard.fullUrl || targetCard.url || "";
        if (!openedInPlace && navUrl && navUrl !== window.location.href) {
          busyLabel = `Navigating to ${targetCard.title} at ${targetCard.company_name}…`;
          render();
          window.location.href = navUrl;
          return;
        }
        if (openedInPlace) {
          // Wait briefly for the newly opened split pane to render its Apply / Easy Apply button
          await waitForCondition(() => Boolean(findJobDetailApplyButton()), 2800, 240);
        }
      }

      try {
        sessionStorage.removeItem("aa_pending_agent_action");
      } catch (_) {}

      // STEP 2: If no application form/modal is open yet, FIRST locate and click the "Easy Apply" / "Apply" button BEFORE generating any resume!
      let currentFields = extractApplicationFormSchema();
      let clickedApplyTrigger = false;
      let clickedExternalApply = false;
      let externalApplyUrl = "";

      if (currentFields.length === 0) {
        // Check if an embedded ATS iframe (Ashby, Greenhouse, Lever, Workable) is present and ask it to open the form
        const atsIframes = Array.from(document.querySelectorAll("iframe"));
        if (atsIframes.length > 0 && !hostName.includes("linkedin.com")) {
          busyLabel = "Opening embedded application form…";
          busyButtonLabel = "Opening Form…";
          render();
          for (const ifr of atsIframes) {
            try {
              if (ifr.contentWindow) {
                ifr.contentWindow.postMessage({ __autoapplyParentCmd: "OPEN_FORM" }, "*");
              }
            } catch (_) {}
          }
          await waitForCondition(() => extractApplicationFormSchema().length > 0, 3500, 300);
          currentFields = extractApplicationFormSchema();
        }
      }

      if (currentFields.length === 0 && !findOpenEasyApplyModal()) {
        const applyTriggerBtn = await waitForCondition(() => findJobDetailApplyButton(), 5500, 260);
        if (applyTriggerBtn) {
          const btnText = (
            applyTriggerBtn.innerText ||
            applyTriggerBtn.getAttribute("aria-label") ||
            "Apply"
          )
            .replace(/\s+/g, " ")
            .trim();
          const ariaLabel = (applyTriggerBtn.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim();
          externalApplyUrl = extractExternalApplyUrl(applyTriggerBtn);
          const isEasyApply =
            /easy apply/i.test(btnText) ||
            /easy apply/i.test(ariaLabel) ||
            Boolean(applyTriggerBtn.querySelector('svg[id*="inbug"]'));
          const hasExternalIcon =
            Boolean(externalApplyUrl) ||
            /company website|external|off linkedin/i.test(ariaLabel) ||
            applyTriggerBtn.getAttribute("target") === "_blank" ||
            Boolean(
              applyTriggerBtn.querySelector(
                'svg[data-test-icon*="launch"], svg[class*="external"], svg[id*="external"], svg[id*="link-external"]'
              )
            ) ||
            Boolean(document.body && /responses managed off linkedin/i.test(document.body.innerText || ""));
          clickedExternalApply = !isEasyApply && hostName.includes("linkedin.com") && (hasExternalIcon || /^apply$/i.test(btnText));

          const curMeta = extractJobMetadataFromPage();
          busyLabel = `Clicking "${btnText}" to open application form…`;
          busyButtonLabel = `Opening Form…`;
          render();

          const handoffPayload = {
            mode,
            title: curMeta.title,
            company_name: curMeta.company_name,
            location: curMeta.location,
            description: curMeta.description,
            sourceUrl: window.location.href,
            expectExternalTab: clickedExternalApply,
            externalUrl: externalApplyUrl || "",
            startedAt: Date.now(),
          };
          crossTabJobHint = {
            title: curMeta.title,
            company_name: curMeta.company_name,
            location: curMeta.location,
            description: curMeta.description,
          };
          try {
            sessionStorage.setItem("aa_tab_job_hint", JSON.stringify(crossTabJobHint));
            if (!clickedExternalApply) {
              sessionStorage.setItem("aa_pending_agent_action", JSON.stringify(handoffPayload));
            }
          } catch (_) {}
          if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
            try {
              chrome.storage.local.set({ aa_cross_tab_agent_action: handoffPayload });
            } catch (_) {}
          }

          highlightPageElement(applyTriggerBtn, "#10b981");
          await new Promise((r) => setTimeout(r, 280));
          // Use hardware CDP click + DOM click fallback to open Easy Apply modal or external ATS tab reliably
          await clickElementWithAgent(applyTriggerBtn, true);
          clickedApplyTrigger = true;

          if (clickedExternalApply) {
            // If we extracted a direct external ATS URL (e.g., from LinkedIn /safety/go/?url=...), ensure the external tab is opened & focused
            if (externalApplyUrl && typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.sendMessage) {
              setTimeout(() => {
                try {
                  chrome.runtime.sendMessage({
                    type: "COMPANION_ENSURE_EXTERNAL_TAB",
                    url: externalApplyUrl,
                  });
                } catch (_) {}
              }, 550);
            }
            // Wait briefly in case an unexpected in-page modal opened; otherwise hand off to the external ATS tab without generating a resume on LinkedIn!
            await new Promise((r) => setTimeout(r, 900));
            if (!findOpenEasyApplyModal()) {
              showNotice(
                `Opened external application tab for ${curMeta.company_name} — prefilling will continue in the new tab.`,
                "ok"
              );
              return;
            }
          } else {
            // Wait up to 4.2s for Easy Apply modal or form fields to appear in place
            await waitForCondition(
              () => Boolean(findOpenEasyApplyModal()) || extractApplicationFormSchema().length > 0,
              4200,
              220
            );
          }

          try {
            sessionStorage.removeItem("aa_pending_agent_action");
          } catch (_) {}
          currentFields = extractApplicationFormSchema();
        }
      }

      // STEP 3: Check for application page blockers (geo-block, closed job, login wall, captcha) before or during prefill
      const meta = extractJobMetadataFromPage();
      const detectedProblem = detectApplicationPageProblem();
      if (detectedProblem && currentFields.length === 0 && !findOpenEasyApplyModal() && !clickedExternalApply) {
        await recordApplicationProblemNote(meta, detectedProblem.reason, detectedProblem.kind);
        return;
      }

      // On LinkedIn, if no Easy Apply modal is open and no form fields exist, never start generating a resume in the background
      if (hostName.includes("linkedin.com") && !findOpenEasyApplyModal() && currentFields.length === 0) {
        showNotice(
          clickedExternalApply
            ? `Opened external application tab for ${meta.company_name} — prefilling will continue in the new tab.`
            : `Click the job's Apply / Easy Apply button first to open the application form.`,
          clickedExternalApply ? "ok" : "err"
        );
        return;
      }

      // FIRST prepare and prefill the interactive form fields (skip_doc_regen: true) so the form is filled immediately
      // BEFORE generating any PDF documents, and inspect what documents actually need to be submitted on each open form step!
      busyLabel =
        currentFields.length > 0
          ? `Preparing & prefilling ${currentFields.length} form field(s) for ${meta.company_name}…`
          : `Inspecting application form for ${meta.company_name}…`;
      busyButtonLabel = mode === "apply" ? "Applying…" : "Filling Form…";
      render();

      const resp = await sendBridgeAction("companion_prepare_and_prefill_job", {
        mode,
        skip_doc_regen: true,
        canonical_url: meta.canonical_url,
        title: meta.title,
        company_name: meta.company_name,
        location: meta.location,
        description: meta.description,
        form_fields: currentFields,
      });

      const data = (resp && resp.data) || bridgeState || {};
      const pkg = data.prefill_package;
      if (!pkg) {
        showNotice("Could not prepare application data. Check AutoApply connection.", "err");
        return;
      }

      if (pkg.title && !/^(product manager|target role|work|careers)$/i.test(pkg.title)) {
        crossTabJobHint = {
          ...(crossTabJobHint || {}),
          title: pkg.title,
          company_name: pkg.company_name || meta.company_name,
        };
      }

      let totalFilesUploaded = 0;
      let totalFieldsFilled = Number(pkg.cdp_filled_count || 0);
      if (totalFieldsFilled > 0) {
        const docsCheck = pkg.documents || pkg.files || {};
        totalFilesUploaded = (docsCheck.resume ? 1 : 0) + (docsCheck.cover_letter ? 1 : 0);
      }
      let passwordAdjusted = false;
      let submitted = false;
      let stepsNavigated = 0;

      // Multi-page wizard progression loop (navigates through Step 1/4 -> 2/4 -> 3/4 -> 4/4 Review/Submit)
      for (let stepIdx = 0; stepIdx < 10; stepIdx++) {
        // On subsequent wizard pages (stepIdx > 0), extract newly mounted form fields and fetch answers from backend (fast skip_doc_regen mode)
        if (stepIdx > 0) {
          const stepFields = extractApplicationFormSchema();
          if (stepFields.length > 0) {
            updateLiveProgressLabels(
              `Analyzing page ${stepIdx + 1} questions (${stepFields.length} field${stepFields.length === 1 ? "" : "s"})…`,
              `Page ${stepIdx + 1}…`
            );
            try {
              const stepResp = await sendBridgeAction("companion_prepare_and_prefill_job", {
                mode: "prefill",
                skip_doc_regen: true,
                canonical_url: meta.canonical_url,
                title: pkg.title || meta.title,
                company_name: pkg.company_name || meta.company_name,
                location: meta.location,
                description: meta.description,
                form_fields: stepFields,
              });
              const stepPkg = stepResp && stepResp.data && stepResp.data.prefill_package;
              if (stepPkg && stepPkg.field_answers) {
                pkg.field_answers = {
                  ...(pkg.field_answers || {}),
                  ...stepPkg.field_answers,
                };
              }
            } catch (_) {}
          }
        }

        // 1. FIRST prefill all interactive text/select/radio/checkbox form fields on this step
        const fieldStats = await applyPrefillPackageToDOMAsync(
          pkg,
          (detailTxt, btnTxt) => {
            updateLiveProgressLabels(detailTxt, btnTxt);
          },
          { skipFiles: true }
        );
        totalFieldsFilled += fieldStats.fieldsFilled;
        if (fieldStats.passwordAdjustedTo12) passwordAdjusted = true;

        // 2. SECOND inspect whether this open form/step actually has document upload inputs (Resume / Cover Letter)
        const stepScope = hostName.includes("linkedin.com") ? findOpenEasyApplyModal() || document : document;
        const stepDocInputs = findDocumentFileInputsInScope(stepScope);
        const hasLinkedInResumeRadio =
          hostName.includes("linkedin.com") &&
          queryAllDeep(
            '.jobs-document-upload-redesign-card__container input[type="radio"], [class*="resume-card"] input[type="radio"], input[type="radio"][name*="document"]',
            stepScope
          ).length > 0;

        if (stepDocInputs.length > 0 || hasLinkedInResumeRadio) {
          const needsCoverDoc = stepDocInputs.some((inp) => {
            const m = (
              getFieldLabelText(inp) +
              " " +
              (inp.name || "") +
              " " +
              (inp.id || "") +
              " " +
              (inp.closest(".js-field, .field, .form-group, .jobs-document-upload, [data-testid*='upload'], label")?.innerText || "")
            ).toLowerCase();
            return m.includes("cover");
          });
          const curDocs = pkg.documents || pkg.files || {};
          const hasResumeReady = Boolean(curDocs.resume && curDocs.resume.base64);
          const hasCoverReady = !needsCoverDoc || Boolean(curDocs.cover_letter && curDocs.cover_letter.base64);

          if (stepDocInputs.length > 0 && (!hasResumeReady || !hasCoverReady)) {
            updateLiveProgressLabels(
              `📄 Tailoring Resume${needsCoverDoc ? " & Cover Letter" : ""} for ${pkg.company_name || meta.company_name}…`,
              "Tailoring PDF…"
            );
            try {
              const docResp = await sendBridgeAction("companion_prepare_and_prefill_job", {
                mode: "prefill",
                skip_doc_regen: false,
                skip_field_llm: true,
                canonical_url: meta.canonical_url,
                title: pkg.title || meta.title,
                company_name: pkg.company_name || meta.company_name,
                location: meta.location,
                description: meta.description,
                form_fields: [],
              });
              const docPkg = docResp && docResp.data && docResp.data.prefill_package;
              if (docPkg && (docPkg.documents || docPkg.files)) {
                pkg.documents = docPkg.documents || docPkg.files;
                pkg.files = pkg.documents;
              }
            } catch (_) {}
          }

          const fileStats = await applyPrefillPackageToDOMAsync(
            pkg,
            (detailTxt, btnTxt) => {
              updateLiveProgressLabels(detailTxt, btnTxt);
            },
            { onlyFiles: true }
          );
          totalFilesUploaded += fileStats.filesUploaded;
        }

        await new Promise((r) => setTimeout(r, 320));

        const finalSubmitBtn = findModalStepOrSubmitButton("submit");
        if (finalSubmitBtn) {
          if (mode === "apply") {
            armMainWorldDialogGuard("apply", 45000);
            keepDialogGuardArmedForSubmit = true;
            updateLiveProgressLabels("Submitting application…", "Submitting…");
            await scrollElementIntoViewSmoothly(finalSubmitBtn, "#10b981");
            await new Promise((r) => setTimeout(r, 260));
            await clickElementWithAgent(finalSubmitBtn, true);
            await new Promise((r) => setTimeout(r, 380));
            submitted = true;
          } else {
            // In Prefill mode, highlight the final Submit button on the Review page so user can review & click Submit
            armMainWorldDialogGuard("prefill", 15000);
            await scrollElementIntoViewSmoothly(finalSubmitBtn, "#10b981");
          }
          break;
        }

        const nextStepBtn = findModalStepOrSubmitButton("next");
        const openModal = findOpenEasyApplyModal();
        if (nextStepBtn && (openModal || fieldStats.fieldsFilled > 0 || totalFilesUploaded > 0)) {
          armMainWorldDialogGuard(mode === "apply" ? "apply" : "prefill", 60000);
          const nextTxt = (
            nextStepBtn.innerText ||
            nextStepBtn.value ||
            nextStepBtn.getAttribute("aria-label") ||
            "Next"
          )
            .replace(/\s+/g, " ")
            .trim();
          updateLiveProgressLabels(`Advancing: "${nextTxt}" (Page ${stepIdx + 1})…`, `${nextTxt}…`);
          await scrollElementIntoViewSmoothly(nextStepBtn, "#3b82f6");
          await new Promise((r) => setTimeout(r, 240));

          const sigBefore = getModalStepSignature();
          const urlBefore = window.location.href;
          await clickElementWithAgent(nextStepBtn, true);

          const advanced = await waitForCondition(
            () => window.location.href !== urlBefore || getModalStepSignature() !== sigBefore,
            1900,
            200
          );

          if (!advanced && openModal) {
            // Check if a required field on the current modal step triggered a validation error, fix it, and click Next again
            const fixedCount = await fixModalValidationErrorsInPlace(openModal, pkg);
            if (fixedCount > 0) {
              totalFieldsFilled += fixedCount;
              await new Promise((r) => setTimeout(r, 240));
              const retryBtn = findModalStepOrSubmitButton("next") || nextStepBtn;
              await clickElementWithAgent(retryBtn, true);
              await waitForCondition(
                () => window.location.href !== urlBefore || getModalStepSignature() !== sigBefore,
                1900,
                200
              );
            }
          }

          if (window.location.href !== urlBefore || getModalStepSignature() !== sigBefore) {
            stepsNavigated++;
            await new Promise((r) => setTimeout(r, 420));
            continue;
          }
        }
        break;
      }

      const docsObj = pkg.documents || pkg.files || {};
      const siteCreds = pkg.site_credentials || {};
      const finalCompany = pkg.company_name || meta.company_name;
      const finalTitle = pkg.title || meta.title;

      if (
        totalFilesUploaded === 0 &&
        totalFieldsFilled === 0 &&
        stepsNavigated === 0 &&
        !submitted &&
        !findOpenEasyApplyModal()
      ) {
        lastPrefillSummary = {
          mode,
          company: finalCompany,
          title: finalTitle,
          filesUploaded: 0,
          fieldsFilled: 0,
          resumeFilename: docsObj.resume?.filename || "Resume.pdf",
          resumePreviewUrl: docsObj.resume?.preview_url || "",
          resumePageCount: docsObj.resume?.page_count || 2,
          coverFilename: docsObj.cover_letter?.filename || "Cover_Letter.pdf",
          coverPreviewUrl: docsObj.cover_letter?.preview_url || "",
          coverPageCount: docsObj.cover_letter?.page_count || 1,
          siteRegistered: false,
          submitted: false,
          docsOnly: true,
        };
        if (clickedExternalApply) {
          showNotice(
            `Opened external application tab for ${finalCompany} — prefilling will continue in the new tab.`,
            "ok"
          );
        } else {
          const fallbackProblem = detectApplicationPageProblem();
          const issueReason = fallbackProblem
            ? fallbackProblem.reason
            : "No interactive form fields were detected on this page. Click the portal's Apply button or sign in first.";
          const issueKind = fallbackProblem ? fallbackProblem.kind : "no_form_fields";
          await recordApplicationProblemNote(
            {
              ...meta,
              title: finalTitle || meta.title,
              company_name: finalCompany || meta.company_name,
            },
            issueReason,
            issueKind
          );
          render();
        }
      } else {
        currentApplicationIssue = null;
        lastPrefillSummary = {
          mode,
          company: finalCompany,
          title: finalTitle,
          filesUploaded: totalFilesUploaded,
          fieldsFilled: totalFieldsFilled,
          resumeFilename: docsObj.resume?.filename || "Resume.pdf",
          resumePreviewUrl: docsObj.resume?.preview_url || "",
          resumePageCount: docsObj.resume?.page_count || 2,
          coverFilename: docsObj.cover_letter?.filename || "Cover_Letter.pdf",
          coverPreviewUrl: docsObj.cover_letter?.preview_url || "",
          coverPageCount: docsObj.cover_letter?.page_count || 1,
          siteRegistered: Boolean(siteCreds && siteCreds.password),
          siteName: siteCreds.website_name || "",
          passwordLength: passwordAdjusted ? 12 : siteCreds.password_length || 0,
          submitted,
          docsOnly: false,
        };
        const pagesNote = stepsNavigated > 0 ? ` across ${stepsNavigated + 1} pages` : "";
        if (mode === "apply") {
          const summaryMsg = submitted
            ? `Applied to ${finalTitle} at ${finalCompany} (${totalFieldsFilled} fields${pagesNote}, ${totalFilesUploaded} PDFs).`
            : `Completed ${totalFieldsFilled} field(s)${pagesNote} & attached ${totalFilesUploaded} PDF(s). Ready to submit.`;
          showNotice(summaryMsg, "ok");
        } else {
          showNotice(
            `Prefilled ${totalFieldsFilled} field(s)${pagesNote} and attached ${totalFilesUploaded} PDF(s) for ${finalCompany}.`,
            "ok"
          );
        }
      }
    } catch (err) {
      const errMsg = String((err && err.message) || err || "Unexpected error during autofill");
      try {
        const meta = extractJobMetadataFromPage();
        await recordApplicationProblemNote(meta, `Autofill error: ${errMsg}`, "autofill_exception");
      } catch (_) {}
      render();
    } finally {
      if (keepDialogGuardArmedForSubmit || mode === "apply") {
        // Keep main-world dialog guard armed for 20s after submit so async XHR callbacks
        // (e.g. Greenhouse validateAddresses -> .then(() => confirm(...))) never block.
        armMainWorldDialogGuard("apply", 20000);
      } else {
        setTimeout(() => {
          if (!isBusyWorking) {
            armMainWorldDialogGuard("idle", 0);
          }
        }, 1200);
      }
      isBusyWorking = false;
      activeWorkingMode = "";
      busyLabel = "";
      busyButtonLabel = "";
      render();
    }
  }

  function maybeResumePendingAgentAction() {
    if (resumedPendingAgentOnce || isBusyWorking) return;
    try {
      const raw = sessionStorage.getItem("aa_pending_agent_action");
      if (raw) {
        const parsed = JSON.parse(raw);
        if (!parsed || !parsed.startedAt || Date.now() - parsed.startedAt > 30000) {
          sessionStorage.removeItem("aa_pending_agent_action");
        } else {
          resumedPendingAgentOnce = true;
          sessionStorage.removeItem("aa_pending_agent_action");
          if (parsed.title || parsed.company_name) {
            crossTabJobHint = {
              title: parsed.title || "",
              company_name: parsed.company_name || "",
              location: parsed.location || "",
              description: parsed.description || "",
            };
            try {
              sessionStorage.setItem("aa_tab_job_hint", JSON.stringify(crossTabJobHint));
            } catch (_) {}
          }
          if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
            try {
              chrome.storage.local.remove("aa_cross_tab_agent_action");
            } catch (_) {}
          }
          setTimeout(() => {
            runPrefillOrApply(parsed.mode || "prefill", true);
          }, 900);
          return;
        }
      }
    } catch (_) {}

    // Also check cross-tab / cross-navigation pending action
    const hostName = (window.location.hostname || "").toLowerCase();
    const isLinkedInDetail = hostName.includes("linkedin.com") && isSpecificJobDetailOpen();
    if ((!hostName.includes("linkedin.com") || isLinkedInDetail) && typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
      try {
        chrome.storage.local.get(["aa_cross_tab_agent_action"], (res) => {
          if (resumedPendingAgentOnce || isBusyWorking) return;
          const act = res && res.aa_cross_tab_agent_action;
          if (!act || !act.startedAt) return;
          if (Date.now() - act.startedAt > 60000) {
            chrome.storage.local.remove("aa_cross_tab_agent_action");
            return;
          }
          // Never let the source tab that initiated the external tab open consume its own cross-tab action
          if (act.sourceUrl && act.sourceUrl === window.location.href) {
            return;
          }
          // If the action was triggered by an external Apply link on LinkedIn, only resume on the external ATS tab, never on another LinkedIn tab!
          if (act.expectExternalTab && hostName.includes("linkedin.com")) {
            return;
          }
          const isExternalRedirectTab = !hostName.includes("linkedin.com");
          const jobParams = detectJobPageParameters();
          if (isLinkedInDetail || isExternalRedirectTab || (jobParams && jobParams.isJobPage)) {
            resumedPendingAgentOnce = true;
            if (act.title || act.company_name) {
              crossTabJobHint = {
                title: act.title || "",
                company_name: act.company_name || "",
                location: act.location || "",
                description: act.description || "",
              };
              try {
                sessionStorage.setItem("aa_tab_job_hint", JSON.stringify(crossTabJobHint));
              } catch (_) {}
            }
            chrome.storage.local.remove("aa_cross_tab_agent_action");
            render();
            setTimeout(() => {
              runPrefillOrApply(act.mode || "prefill", true);
            }, 1400);
          }
        });
      } catch (_) {}
    }
  }

  function detectGoogleAppPasswordOnPage() {
    if (!window.location.hostname.includes("google.com")) return "";
    const candidates = document.querySelectorAll(
      '[role="dialog"] div, [role="dialog"] span, [aria-modal="true"] div, [aria-modal="true"] span, c-wiz div, c-wiz span'
    );
    for (const el of candidates) {
      if (el.children && el.children.length > 0) continue;
      const txt = (el.innerText || el.textContent || "").trim();
      if (/^[a-z]{4}\s+[a-z]{4}\s+[a-z]{4}\s+[a-z]{4}$/.test(txt)) {
        return txt.replace(/\s+/g, " ");
      }
    }
    const bodyText = (document.body && document.body.innerText) || "";
    if (bodyText.includes("Generated app password") || bodyText.includes("Your app password for your device")) {
      const sliceStart = bodyText.indexOf("Your app password for your device");
      const region = sliceStart >= 0 ? bodyText.slice(sliceStart, sliceStart + 350) : bodyText;
      const m = region.match(/\b([a-z]{4}\s+[a-z]{4}\s+[a-z]{4}\s+[a-z]{4})\b/);
      if (m && m[1]) {
        return m[1].replace(/\s+/g, " ");
      }
    }
    return "";
  }

  function detectGoogleEmailOnPage() {
    const emailEl = document.querySelector("[data-email]");
    if (emailEl && emailEl.getAttribute("data-email")) {
      return emailEl.getAttribute("data-email").trim().toLowerCase();
    }
    const bodyText = (document.body && document.body.innerText) || "";
    const m = bodyText.match(/([\w.+-]+@(?:gmail|googlemail)\.com)/i);
    return m ? m[1].toLowerCase() : "";
  }

  function findGoogleAppNameInput() {
    const allInputs = Array.from(
      document.querySelectorAll('c-wiz input, main input, input[type="text"], input:not([type])')
    ).filter((el) => {
      if (!el || el.disabled || el.readOnly) return false;
      const t = (el.getAttribute("type") || "text").toLowerCase();
      if (t !== "text" && t !== "search" && t !== "") return false;
      const rect = el.getBoundingClientRect();
      return rect.width > 40 && rect.height > 12;
    });

    for (const el of allInputs) {
      const ph = (el.getAttribute("placeholder") || "").toLowerCase();
      const al = (el.getAttribute("aria-label") || "").toLowerCase();
      const containerText = (
        (el.closest("label")?.innerText || "") +
        " " +
        (el.parentElement?.parentElement?.innerText || "") +
        " " +
        (el.parentElement?.parentElement?.parentElement?.innerText || "")
      ).toLowerCase();
      if (
        ph.includes("app name") ||
        al.includes("app name") ||
        containerText.includes("app name") ||
        containerText.includes("app-specific password")
      ) {
        return el;
      }
    }
    return allInputs[0] || null;
  }

  function findGoogleCreateButton() {
    const buttons = Array.from(document.querySelectorAll('button, [role="button"]'));
    return (
      buttons.find((btn) => {
        if (!btn) return false;
        const rect = btn.getBoundingClientRect();
        if (rect.width < 20 || rect.height < 12) return false;
        const txt = (btn.innerText || btn.textContent || "").trim().toLowerCase();
        return txt === "create";
      }) || null
    );
  }

  function fillInputForGoogleWiz(inputEl, textValue) {
    inputEl.focus();
    inputEl.click();
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
    if (nativeSetter) {
      nativeSetter.call(inputEl, textValue);
    } else {
      inputEl.value = textValue;
    }
    inputEl.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "A", code: "KeyA" }));
    try {
      inputEl.dispatchEvent(
        new InputEvent("input", {
          bubbles: true,
          cancelable: true,
          inputType: "insertText",
          data: textValue,
        })
      );
    } catch (_) {
      inputEl.dispatchEvent(new Event("input", { bubbles: true }));
    }
    inputEl.dispatchEvent(new Event("change", { bubbles: true }));
    inputEl.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, cancelable: true, key: "y", code: "KeyY" }));
  }

  function autoCreateAndCaptureGoogleAppPassword(forceCreate = false) {
    const href = (window.location.href || "").toLowerCase();
    if (!href.includes("myaccount.google.com/apppasswords")) return;

    const generatedPass = detectGoogleAppPasswordOnPage();
    if (generatedPass) {
      draftInputs.gmPass = generatedPass;
      const passInput = shadow.getElementById("aa-gm-pass");
      if (passInput && passInput.value !== generatedPass) {
        passInput.value = generatedPass;
      }
      const detectedEmail =
        draftInputs.gmEmail ||
        detectGoogleEmailOnPage() ||
        ((bridgeState &&
          bridgeState.onboarding &&
          bridgeState.onboarding.gmail_config &&
          bridgeState.onboarding.gmail_config.account_email) ||
          "");
      if (detectedEmail) {
        draftInputs.gmEmail = detectedEmail;
        const emailInput = shadow.getElementById("aa-gm-email");
        if (emailInput && !emailInput.value) {
          emailInput.value = detectedEmail;
        }
      }
      if (lastAutoSavedGmPass !== generatedPass) {
        lastAutoSavedGmPass = generatedPass;
        sendBridgeAction("configure_gmail", {
          account_email: detectedEmail || "connected@gmail.com",
          app_password: generatedPass,
          connected: true,
        });
      }
      return;
    }

    const nowMs = Date.now();
    if (!forceCreate && sessionStorage.getItem("aa_autoapply_pw_created_once") === "1") {
      return;
    }
    if (!forceCreate && nowMs - lastCreateClickAt < 6000) {
      return;
    }

    const appNameInput = findGoogleAppNameInput();
    if (!appNameInput) return;

    const currentVal = (appNameInput.value || "").trim();
    if (!currentVal || forceCreate) {
      fillInputForGoogleWiz(appNameInput, "AutoApply");
    }

    setTimeout(() => {
      const createBtn = findGoogleCreateButton();
      if (createBtn) {
        const isDisabled = createBtn.disabled || createBtn.getAttribute("aria-disabled") === "true";
        if (!isDisabled) {
          lastCreateClickAt = Date.now();
          sessionStorage.setItem("aa_autoapply_pw_created_once", "1");
          createBtn.click();
          setTimeout(() => autoCreateAndCaptureGoogleAppPassword(false), 600);
          setTimeout(() => autoCreateAndCaptureGoogleAppPassword(false), 1400);
          setTimeout(() => autoCreateAndCaptureGoogleAppPassword(false), 2400);
        }
      }
    }, 350);
  }

  function scanPageForSecrets() {
    const bodyText = (document.body && document.body.innerText) || "";
    const orMatch = bodyText.match(/sk-or-v1-[A-Za-z0-9]{16,}/);
    const capMatch = bodyText.match(/CAP-[A-Za-z0-9]{16,}/);
    const gmPass = detectGoogleAppPasswordOnPage();
    return {
      openrouterKey: orMatch ? orMatch[0] : "",
      capsolverKey: capMatch ? capMatch[0] : "",
      gmailAppPassword: gmPass,
    };
  }

  const clickedCookieButtons = new WeakSet();

  function autoAcceptCookieBanners() {
    if (!document.body) return;
    try {
      const explicitSelectors = [
        '[data-qa="cookies-policy-informer-accept"]',
        '[data-qa="cookies-policy-informer"] button',
        ".cookies-policy-informer button",
        "#onetrust-accept-btn-handler",
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "#CybotCookiebotDialogBodyButtonAccept",
        "#didomi-notice-agree-button",
        ".osano-cm-accept-all",
        ".osano-cm-button--type_accept",
        '[data-tid="banner-accept"]',
        ".cky-btn-accept",
        ".cmplz-accept",
        ".cc-btn.cc-allow",
        ".cc-btn.cc-dismiss",
        "#truste-consent-button",
        '[data-testid="uc-accept-all-button"]',
        '.qc-cmp2-summary-buttons button[mode="primary"]',
        'button[id*="cookie" i][id*="accept" i]',
        'button[id*="cookie" i][id*="allow" i]',
        'button[data-testid*="cookie" i][data-testid*="accept" i]',
        'button[aria-label*="accept cookies" i]',
        'button[aria-label*="accept all cookies" i]',
        'button[aria-label*="allow cookies" i]',
      ];

      for (const sel of explicitSelectors) {
        const nodes = document.querySelectorAll(sel);
        for (const btn of nodes) {
          if (!btn || host.contains(btn) || clickedCookieButtons.has(btn)) continue;
          const rect = btn.getBoundingClientRect();
          if (rect.width <= 0 || rect.height <= 0) continue;
          clickedCookieButtons.add(btn);
          try {
            btn.click();
          } catch (_) {}
          return;
        }
      }

      const acceptLabelRe =
        /^(got it!?|accept|accept all|accept cookies|accept all cookies|allow|allow all|allow all cookies|allow cookies|i agree|agree|agree & proceed|agree and proceed|ok|okay|understood|i understand|acknowledge|continue|dismiss|понятно|принять|принять все|принять всё|согласен|согласна|хорошо|ок|разрешить|разрешить все)$/i;
      const rejectOrSettingsRe =
        /\b(manage|settings|preferences|reject|decline|customize|customise|more info|learn more|policy|настроить|настройки|отклонить|подробнее)\b/i;
      const cookieContextRe =
        /\b(cookies?|куки|файл[а-яё]*\s+cookie|cookie[\s_-]*policy|cookie[\s_-]*banner|cookie[\s_-]*consent|gdpr)\b/i;

      const clickables = document.querySelectorAll(
        'button, a[role="button"], [role="button"], input[type="button"], input[type="submit"]'
      );
      for (const btn of clickables) {
        if (!btn || host.contains(btn) || clickedCookieButtons.has(btn)) continue;
        const rawLabel = (btn.innerText || btn.value || btn.textContent || "").replace(/\s+/g, " ").trim();
        if (!rawLabel || rawLabel.length > 36) continue;
        if (rejectOrSettingsRe.test(rawLabel)) continue;
        if (!acceptLabelRe.test(rawLabel)) continue;

        const rect = btn.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) continue;

        let ancestor = btn.parentElement;
        let matchedBanner = null;
        for (let depth = 0; depth < 6 && ancestor && ancestor !== document.body && ancestor !== document.documentElement; depth++) {
          const aRect = ancestor.getBoundingClientRect();
          if (aRect.height > 0 && aRect.height < 460) {
            const aText = (ancestor.innerText || ancestor.textContent || "").replace(/\s+/g, " ").trim();
            const aMeta = [
              ancestor.id || "",
              typeof ancestor.className === "string" ? ancestor.className : "",
              ancestor.getAttribute("data-qa") || "",
              ancestor.getAttribute("data-testid") || "",
              ancestor.getAttribute("aria-label") || "",
            ].join(" ");
            if ((aText.length > 0 && aText.length < 950 && cookieContextRe.test(aText)) || cookieContextRe.test(aMeta)) {
              matchedBanner = ancestor;
              break;
            }
          }
          ancestor = ancestor.parentElement;
        }

        if (matchedBanner) {
          clickedCookieButtons.add(btn);
          try {
            btn.click();
          } catch (_) {}
          const bannerRef = matchedBanner;
          setTimeout(() => {
            try {
              if (bannerRef && bannerRef.isConnected) {
                const r = bannerRef.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                  bannerRef.style.setProperty("display", "none", "important");
                }
              }
            } catch (_) {}
          }, 450);
          return;
        }
      }
    } catch (_) {}
  }

  function ensureNoLeftClipping() {
    if (isCollapsed || !document.body) return;
    try {
      const sidebarPx = 320;
      const availW = Math.max(320, (window.innerWidth || document.documentElement.clientWidth || 1280) - sidebarPx);
      const candidates = document.querySelectorAll(
        [
          ".scaffold-layout__inner",
          ".global-nav__content",
          ".scaffold-layout-container",
          ".scaffold-layout",
          ".authentication-outlet",
          ".application-outlet",
          "#HH-React-Root",
          ".HH-MainContent",
          ".HH-Supernova-MainContent",
          ".supernova-navi",
          ".supernova-navi-wrapper",
          ".supernova-navi-search-wrapper",
          ".supernova-dashboard",
          ".bloko-columns-wrapper",
          '[data-qa="mainmenu"]',
          '[class*="magritte-grid-container"]',
          '[class*="magritte-grid-layout"]',
          "main",
          "header",
          "nav",
          'header[role="banner"]',
          "body > div:not(#autoapply-companion-host)",
        ].join(", ")
      );
      candidates.forEach((el) => {
        if (!el || el === host || host.contains(el)) return;
        const rect = el.getBoundingClientRect();
        if (rect.width <= 0 && rect.height <= 0) return;
        if (rect.left < -1) {
          el.style.setProperty("margin-left", "0px", "important");
          el.style.setProperty("left", "0px", "important");
          el.style.setProperty("width", "100%", "important");
          el.style.setProperty("max-width", "100%", "important");
          el.style.setProperty("min-width", "0px", "important");
          el.style.setProperty("box-sizing", "border-box", "important");
          if (el.parentElement && el.parentElement !== document.body && el.parentElement !== document.documentElement) {
            const pStyle = window.getComputedStyle(el.parentElement);
            if (pStyle.display.includes("flex") && pStyle.justifyContent === "center") {
              el.parentElement.style.setProperty("justify-content", "flex-start", "important");
            }
          }
        }
        if (rect.right > availW + 2) {
          const cStyle = window.getComputedStyle(el);
          el.style.setProperty("min-width", "0px", "important");
          el.style.setProperty("box-sizing", "border-box", "important");
          if (cStyle.position === "fixed" || cStyle.position === "sticky") {
            if (rect.left <= 32 || rect.width >= availW * 0.65) {
              el.style.setProperty("left", "0px", "important");
              el.style.setProperty("right", `${sidebarPx}px`, "important");
              el.style.setProperty("width", `${availW}px`, "important");
              el.style.setProperty("max-width", `${availW}px`, "important");
            } else {
              const clampedLeft = Math.max(8, Math.round(availW - Math.min(rect.width, availW - 16) - 12));
              el.style.setProperty("left", `${clampedLeft}px`, "important");
              el.style.setProperty("right", "auto", "important");
              el.style.setProperty("max-width", `${availW - 16}px`, "important");
            }
          } else {
            const leftOffset = Math.max(0, Math.round(rect.left));
            const maxAllowed = Math.max(240, availW - leftOffset);
            el.style.setProperty("max-width", `${maxAllowed}px`, "important");
            if (rect.width > maxAllowed) {
              el.style.setProperty("width", "100%", "important");
            }
          }
        }
      });

      // Keep any floating popovers, tooltips, or fixed notification bars from overlapping underneath the right sidebar
      const floatingEls = document.querySelectorAll(
        '[role="dialog"], [role="tooltip"], [data-portal], [class*="popover" i], [class*="tooltip" i], [class*="dropdown" i], [data-qa="cookies-policy-informer"]'
      );
      floatingEls.forEach((el) => {
        if (!el || el === host || host.contains(el)) return;
        const rect = el.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return;
        if (rect.right > availW + 1) {
          const cStyle = window.getComputedStyle(el);
          if (cStyle.position === "fixed" || cStyle.position === "absolute" || cStyle.position === "sticky") {
            if (rect.left <= 32 || rect.width >= availW * 0.65) {
              el.style.setProperty("left", "0px", "important");
              el.style.setProperty("right", `${sidebarPx}px`, "important");
              el.style.setProperty("width", `${availW}px`, "important");
              el.style.setProperty("max-width", `${availW}px`, "important");
              el.style.setProperty("box-sizing", "border-box", "important");
            } else {
              const clampedLeft = Math.max(8, Math.round(availW - Math.min(rect.width, availW - 16) - 12));
              el.style.setProperty("left", `${clampedLeft}px`, "important");
              el.style.setProperty("right", "auto", "important");
              el.style.setProperty("max-width", `${availW - 16}px`, "important");
            }
          }
        }
      });
    } catch (_) {}
  }

  function applyPageMargin() {
    if (!document.documentElement) return;
    const htmlEl = document.documentElement;
    const bodyEl = document.body;
    let dockStyle = document.getElementById("aa-viewport-dock-style");
    const sidebarW = "320px";
    if (isCollapsed) {
      htmlEl.style.removeProperty("width");
      htmlEl.style.removeProperty("max-width");
      htmlEl.style.removeProperty("margin-left");
      htmlEl.style.removeProperty("margin-right");
      htmlEl.style.removeProperty("overflow-x");
      if (bodyEl) {
        bodyEl.style.removeProperty("width");
        bodyEl.style.removeProperty("max-width");
        bodyEl.style.removeProperty("min-width");
        bodyEl.style.removeProperty("margin-left");
        bodyEl.style.removeProperty("margin-right");
      }
      if (dockStyle) {
        dockStyle.textContent = "";
      }
    } else {
      htmlEl.style.setProperty("width", `calc(100vw - ${sidebarW})`, "important");
      htmlEl.style.setProperty("max-width", `calc(100vw - ${sidebarW})`, "important");
      htmlEl.style.setProperty("margin-left", "0px", "important");
      htmlEl.style.setProperty("margin-right", sidebarW, "important");
      htmlEl.style.setProperty("overflow-x", "hidden", "important");
      if (bodyEl) {
        bodyEl.style.setProperty("width", "100%", "important");
        bodyEl.style.setProperty("max-width", `calc(100vw - ${sidebarW})`, "important");
        bodyEl.style.setProperty("min-width", "0px", "important");
        bodyEl.style.setProperty("margin-left", "0px", "important");
        bodyEl.style.setProperty("margin-right", "0px", "important");
      }
      if (!dockStyle && document.head) {
        dockStyle = document.createElement("style");
        dockStyle.id = "aa-viewport-dock-style";
        document.head.appendChild(dockStyle);
      }
      if (dockStyle) {
        dockStyle.textContent = `
          html, body {
            min-width: 0 !important;
            max-width: calc(100vw - ${sidebarW}) !important;
            box-sizing: border-box !important;
          }
          /* Keep top navigation bars aligned to the left edge and sized strictly to the available viewport */
          #global-nav,
          .global-nav,
          header.global-nav,
          .scaffold-layout__sticky-header,
          header[role="banner"],
          .supernova-navi,
          .supernova-navi-wrapper,
          .supernova-navi-search-wrapper,
          [data-qa="mainmenu"] {
            left: 0 !important;
            right: ${sidebarW} !important;
            width: 100% !important;
            max-width: calc(100vw - ${sidebarW}) !important;
            min-width: 0 !important;
            box-sizing: border-box !important;
          }
          /* HeadHunter (hh.ru) Bloko & Magritte responsive fluid layout overrides so fixed 1000px/1320px desktop grids fit cleanly inside calc(100vw - 320px) */
          #HH-React-Root,
          .HH-MainContent,
          .HH-Supernova-MainContent,
          .supernova-dashboard,
          .supernova-dashboard-header,
          .supernova-footer,
          .bloko-columns-wrapper,
          [class*="magritte-grid-container"],
          [class*="magritte-grid-layout"] {
            width: 100% !important;
            max-width: calc(100vw - ${sidebarW}) !important;
            min-width: 0 !important;
            margin-left: 0 !important;
            margin-right: 0 !important;
            box-sizing: border-box !important;
          }
          .bloko-columns-wrapper {
            padding-left: 16px !important;
            padding-right: 16px !important;
          }
          .bloko-columns-row,
          [class*="magritte-grid-row"] {
            display: flex !important;
            flex-wrap: wrap !important;
            width: 100% !important;
            max-width: 100% !important;
            min-width: 0 !important;
            box-sizing: border-box !important;
          }
          .bloko-column,
          [class*="magritte-grid-column"] {
            min-width: 0 !important;
            max-width: 100% !important;
            box-sizing: border-box !important;
            flex-shrink: 1 !important;
          }
          .bloko-column_m-12,
          .bloko-column_l-16,
          [class*="magritte-grid-column_m-12"],
          [class*="magritte-grid-column_l-16"] {
            width: 100% !important;
            max-width: 100% !important;
            flex: 1 1 100% !important;
          }
          .bloko-column_m-9,
          .bloko-column_l-12,
          [class*="magritte-grid-column_m-9"],
          [class*="magritte-grid-column_l-12"] {
            width: calc(74% - 16px) !important;
            max-width: calc(74% - 16px) !important;
            flex: 1 1 0% !important;
          }
          .bloko-column_m-8,
          .bloko-column_l-11,
          [class*="magritte-grid-column_m-8"],
          [class*="magritte-grid-column_l-11"] {
            width: calc(66% - 16px) !important;
            max-width: calc(66% - 16px) !important;
            flex: 1 1 0% !important;
          }
          .bloko-column_m-3,
          .bloko-column_l-4,
          [class*="magritte-grid-column_m-3"],
          [class*="magritte-grid-column_l-4"] {
            width: 24% !important;
            max-width: 235px !important;
            flex: 0 1 215px !important;
          }
          /* Prevent LinkedIn's fixed 1128px centered inner containers from overflowing and clipping the left side */
          .global-nav__content,
          .scaffold-layout-container,
          .scaffold-layout,
          .scaffold-layout__inner,
          .authentication-outlet,
          .application-outlet,
          .jobs-search-two-pane__wrapper,
          .jobs-search-two-pane__container,
          .scaffold-layout__row,
          .scaffold-layout__content,
          .scaffold-layout__list-detail-inner,
          .scaffold-layout__list-detail-container {
            width: 100% !important;
            max-width: calc(100vw - ${sidebarW}) !important;
            min-width: 0 !important;
            margin-left: 0 !important;
            margin-right: 0 !important;
            box-sizing: border-box !important;
          }
          .global-nav__content,
          .scaffold-layout__inner {
            padding-left: 16px !important;
            padding-right: 16px !important;
          }
          /* Hide right-hand promotional aside when Companion sidebar is docked so main content has full room */
          .scaffold-layout__aside {
            display: none !important;
          }
          /* Make LinkedIn sidebar + main grid fluid so neither column is clipped */
          .scaffold-layout__row.scaffold-layout__content--sidebar-main-aside,
          .scaffold-layout__row.scaffold-layout__content--sidebar-main,
          .scaffold-layout__row.scaffold-layout__content--main-aside {
            display: grid !important;
            grid-template-columns: minmax(185px, 23%) minmax(0, 1fr) !important;
            gap: 16px !important;
            width: 100% !important;
            max-width: 100% !important;
          }
          /* Make LinkedIn Jobs split-view (list + detail) fluid so both panes fit cleanly */
          .scaffold-layout--list-detail-inner,
          .scaffold-layout__list-detail-inner {
            display: grid !important;
            grid-template-columns: minmax(250px, 37%) minmax(0, 1fr) !important;
            width: 100% !important;
            max-width: 100% !important;
          }
          .scaffold-layout__sidebar,
          .scaffold-layout__main,
          .scaffold-layout__list,
          .scaffold-layout__detail,
          .jobs-search__job-details,
          .jobs-search__job-details--container {
            min-width: 0 !important;
            max-width: 100% !important;
            box-sizing: border-box !important;
          }
          /* Keep LinkedIn Easy Apply modal overlay centered within the visible page area */
          .artdeco-modal-overlay {
            width: calc(100vw - ${sidebarW}) !important;
            max-width: calc(100vw - ${sidebarW}) !important;
            left: 0 !important;
            right: ${sidebarW} !important;
          }
          #msg-overlay,
          .msg-overlay-container,
          .msg-overlay-list-bubble,
          aside.msg-overlay-container {
            right: ${sidebarW} !important;
          }
        `;
      }
      ensureNoLeftClipping();
    }
  }

  const style = document.createElement("style");
  style.textContent = `
    :host {
      all: initial;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Inter", system-ui, sans-serif !important;
      color: #f8fafc;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }
    .aa-sidebar,
    .aa-sidebar *,
    .aa-sidebar *::before,
    .aa-sidebar *::after,
    .aa-pill-toggle,
    .aa-pill-toggle * {
      box-sizing: border-box;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Inter", system-ui, sans-serif !important;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      letter-spacing: -0.011em;
    }
    .aa-sidebar {
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      width: 320px;
      background: #0b1120;
      border-left: 1px solid #1e293b;
      box-shadow: -1px 0 0 rgba(15, 23, 42, 0.95);
      z-index: 2147483647;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1);
      color: #f8fafc;
    }
    .aa-sidebar.collapsed {
      transform: translateX(320px);
    }
    .aa-pill-toggle {
      position: fixed;
      top: 84px;
      right: 14px;
      z-index: 2147483647;
      background: linear-gradient(135deg, #1d4ed8 0%, #0f766e 100%);
      color: #ffffff;
      border: 1px solid rgba(255, 255, 255, 0.22);
      border-radius: 999px;
      padding: 8px 14px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      box-shadow: 0 8px 24px rgba(2, 6, 23, 0.5);
      display: none;
      align-items: center;
      gap: 7px;
    }
    .aa-pill-toggle.visible {
      display: inline-flex;
    }
    .aa-header {
      padding: 14px 14px 12px 14px;
      background: rgba(15, 23, 42, 0.85);
      backdrop-filter: blur(14px);
      border-bottom: 1px solid rgba(148, 163, 184, 0.12);
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .aa-header-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .aa-brand {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .aa-logo {
      width: 28px;
      height: 28px;
      border-radius: 7px;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      box-shadow: 0 2px 8px rgba(37, 99, 235, 0.4);
      flex-shrink: 0;
    }
    .aa-brand-text {
      display: flex;
      flex-direction: column;
      gap: 1px;
    }
    .aa-title {
      font-size: 13.5px;
      font-weight: 600;
      color: #f8fafc;
      line-height: 1.2;
    }
    .aa-subtitle {
      font-size: 10.5px;
      font-weight: 500;
      color: #64748b;
      line-height: 1.2;
    }
    .aa-collapse-btn {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(148, 163, 184, 0.16);
      color: #94a3b8;
      border-radius: 7px;
      padding: 5px 10px;
      font-size: 11px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .aa-collapse-btn:hover {
      background: rgba(255, 255, 255, 0.1);
      color: #f8fafc;
    }
    .aa-tabs {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 4px;
      background: rgba(2, 6, 23, 0.65);
      padding: 4px;
      border-radius: 9px;
      border: 1px solid rgba(148, 163, 184, 0.12);
    }
    .aa-tab-btn {
      background: transparent;
      border: none;
      color: #94a3b8;
      font-size: 11.5px;
      font-weight: 600;
      padding: 6px 8px;
      border-radius: 6px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 5px;
      transition: all 0.15s ease;
      white-space: nowrap;
    }
    .aa-tab-btn:hover:not(.active) {
      color: #e2e8f0;
      background: rgba(255, 255, 255, 0.04);
    }
    .aa-tab-btn.active {
      background: rgba(37, 99, 235, 0.92);
      color: #ffffff;
      box-shadow: 0 2px 8px rgba(37, 99, 235, 0.35);
    }
    .aa-tab-dot {
      width: 6px;
      height: 6px;
      border-radius: 999px;
      background: #10b981;
      display: inline-block;
      flex-shrink: 0;
    }
    .aa-tab-dot.warn {
      background: #f59e0b;
    }
    .aa-body {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .aa-body.chat-mode {
      overflow: hidden;
    }
    .aa-body::-webkit-scrollbar {
      width: 5px;
    }
    .aa-body::-webkit-scrollbar-thumb {
      background: rgba(148, 163, 184, 0.22);
      border-radius: 999px;
    }
    .aa-banner {
      padding: 9px 11px;
      border-radius: 9px;
      font-size: 11.5px;
      font-weight: 500;
      line-height: 1.4;
      display: none;
    }
    .aa-banner.show {
      display: block;
    }
    .aa-banner.ok {
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.32);
      color: #6ee7b7;
    }
    .aa-banner.err {
      background: rgba(239, 68, 68, 0.14);
      border: 1px solid rgba(239, 68, 68, 0.35);
      color: #fca5a5;
    }
    .aa-copilot-card {
      background: linear-gradient(160deg, rgba(30, 41, 59, 0.78) 0%, rgba(15, 23, 42, 0.92) 100%);
      border: 1px solid rgba(96, 165, 250, 0.28);
      border-radius: 12px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 11px;
      box-shadow: 0 8px 24px rgba(2, 6, 23, 0.35);
    }
    .aa-card-top-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .aa-job-badge {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: #93c5fd;
      background: rgba(37, 99, 235, 0.18);
      border: 1px solid rgba(59, 130, 246, 0.32);
      padding: 3px 8px;
      border-radius: 999px;
    }
    .aa-meta-pill {
      font-size: 10.5px;
      font-weight: 500;
      color: #94a3b8;
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid rgba(148, 163, 184, 0.15);
      padding: 2px 8px;
      border-radius: 999px;
    }
    .aa-job-title {
      font-size: 14.5px;
      font-weight: 600;
      color: #f8fafc;
      line-height: 1.32;
      margin-bottom: 3px;
    }
    .aa-job-company {
      font-size: 12px;
      color: #94a3b8;
      font-weight: 500;
      line-height: 1.35;
    }
    .aa-job-company strong {
      color: #60a5fa;
      font-weight: 600;
    }
    .aa-action-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 2px;
    }
    .aa-btn-prefill {
      background: rgba(37, 99, 235, 0.9);
      color: #ffffff;
      border: 1px solid rgba(147, 197, 253, 0.28);
      border-radius: 9px;
      padding: 9px 11px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25);
      transition: all 0.15s ease;
    }
    .aa-btn-prefill:hover:not(:disabled) {
      background: #2563eb;
      transform: translateY(-1px);
    }
    .aa-btn-apply {
      background: linear-gradient(135deg, #059669 0%, #0d9488 100%);
      color: #ffffff;
      border: 1px solid rgba(110, 231, 183, 0.3);
      border-radius: 9px;
      padding: 9px 11px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      box-shadow: 0 4px 12px rgba(5, 150, 105, 0.28);
      transition: all 0.15s ease;
    }
    .aa-btn-apply:hover:not(:disabled) {
      background: linear-gradient(135deg, #047857 0%, #0f766e 100%);
      transform: translateY(-1px);
    }
    .aa-btn-prefill:disabled, .aa-btn-apply:disabled {
      opacity: 0.55;
      cursor: wait;
    }
    .aa-summary-box {
      background: rgba(15, 23, 42, 0.85);
      border: 1px solid rgba(16, 185, 129, 0.3);
      border-radius: 9px;
      padding: 9px 11px;
      font-size: 11.5px;
      color: #d1fae5;
      line-height: 1.45;
      display: flex;
      flex-direction: column;
      gap: 3px;
    }
    .aa-feed-section {
      display: flex;
      flex-direction: column;
      gap: 7px;
    }
    .aa-section-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 10.5px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #64748b;
      padding: 0 2px;
    }
    .aa-feed-list {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .aa-feed-item {
      background: rgba(15, 23, 42, 0.65);
      border: 1px solid rgba(148, 163, 184, 0.12);
      border-radius: 10px;
      padding: 9px 11px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      cursor: pointer;
      transition: all 0.15s ease;
      text-align: left;
      width: 100%;
    }
    .aa-feed-item:hover {
      background: rgba(30, 41, 59, 0.8);
      border-color: rgba(96, 165, 250, 0.35);
    }
    .aa-feed-item.selected {
      background: rgba(37, 99, 235, 0.14);
      border-color: rgba(59, 130, 246, 0.55);
    }
    .aa-feed-item-info {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
      flex: 1;
    }
    .aa-feed-item-title {
      font-size: 12px;
      font-weight: 600;
      color: #f1f5f9;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .aa-feed-item-sub {
      font-size: 11px;
      color: #94a3b8;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .aa-feed-item-badge {
      font-size: 10px;
      font-weight: 600;
      padding: 3px 7px;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.06);
      color: #cbd5e1;
      flex-shrink: 0;
    }
    .aa-feed-item.selected .aa-feed-item-badge {
      background: rgba(37, 99, 235, 0.3);
      color: #93c5fd;
    }
    .aa-conn-strip {
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(148, 163, 184, 0.12);
      border-radius: 10px;
      padding: 9px 11px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .aa-conn-strip:hover {
      background: rgba(30, 41, 59, 0.75);
      border-color: rgba(148, 163, 184, 0.25);
    }
    .aa-conn-pills {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .aa-conn-pill {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 11px;
      font-weight: 500;
      color: #cbd5e1;
    }
    .aa-setup-summary {
      background: rgba(15, 23, 42, 0.75);
      border: 1px solid rgba(148, 163, 184, 0.14);
      border-radius: 10px;
      padding: 11px 12px;
      display: flex;
      flex-direction: column;
      gap: 7px;
    }
    .aa-progress-track {
      height: 5px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.08);
      overflow: hidden;
    }
    .aa-progress-fill {
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, #3b82f6, #10b981);
      transition: width 0.25s ease;
    }
    .aa-accordion {
      display: flex;
      flex-direction: column;
      gap: 7px;
    }
    .aa-acc-item {
      background: rgba(15, 23, 42, 0.65);
      border: 1px solid rgba(148, 163, 184, 0.12);
      border-radius: 10px;
      overflow: hidden;
      transition: border-color 0.15s ease, background 0.15s ease;
    }
    .aa-acc-item.expanded {
      background: rgba(30, 41, 59, 0.85);
      border-color: rgba(59, 130, 246, 0.45);
    }
    .aa-acc-header {
      width: 100%;
      padding: 10px 12px;
      background: transparent;
      border: none;
      color: inherit;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      cursor: pointer;
      text-align: left;
    }
    .aa-acc-header:hover {
      background: rgba(255, 255, 255, 0.03);
    }
    .aa-check-left {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }
    .aa-check-name {
      font-size: 12px;
      font-weight: 600;
      color: #f1f5f9;
    }
    .aa-check-status {
      font-size: 11px;
      color: #64748b;
      font-weight: 500;
    }
    .aa-check-status.valid {
      color: #34d399;
    }
    .aa-chevron {
      font-size: 11px;
      color: #64748b;
      flex-shrink: 0;
    }
    .aa-acc-content {
      padding: 10px 12px 12px 12px;
      border-top: 1px solid rgba(148, 163, 184, 0.1);
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .aa-desc {
      font-size: 11.5px;
      color: #94a3b8;
      line-height: 1.45;
      margin: 0;
    }
    .aa-desc strong {
      color: #e2e8f0;
      font-weight: 600;
    }
    .aa-input {
      width: 100%;
      background: rgba(2, 6, 23, 0.75);
      border: 1px solid rgba(148, 163, 184, 0.24);
      border-radius: 8px;
      padding: 8px 10px;
      color: #f8fafc;
      font-size: 12px;
      outline: none;
      transition: border-color 0.15s ease;
    }
    .aa-input:focus {
      border-color: #3b82f6;
    }
    .aa-btn {
      width: 100%;
      background: #2563eb;
      color: #ffffff;
      border: none;
      border-radius: 8px;
      padding: 8px 11px;
      font-size: 11.5px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      transition: all 0.15s ease;
    }
    .aa-btn:hover {
      background: #1d4ed8;
    }
    .aa-btn.green {
      background: #059669;
    }
    .aa-btn.green:hover {
      background: #047857;
    }
    .aa-btn.secondary {
      background: rgba(255, 255, 255, 0.06);
      color: #cbd5e1;
      border: 1px solid rgba(148, 163, 184, 0.16);
    }
    .aa-btn.secondary:hover {
      background: rgba(255, 255, 255, 0.11);
      color: #f8fafc;
    }
    .aa-chat-wrap {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-height: 0;
      height: 100%;
      overflow: hidden;
      gap: 10px;
    }
    .aa-chat-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      flex-shrink: 0;
    }
    .aa-chip {
      background: rgba(37, 99, 235, 0.14);
      border: 1px solid rgba(59, 130, 246, 0.3);
      color: #93c5fd;
      border-radius: 999px;
      padding: 4px 9px;
      font-size: 11px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .aa-chip:hover {
      background: rgba(37, 99, 235, 0.28);
      color: #ffffff;
    }
    .aa-chat-messages {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      overscroll-behavior: contain;
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 2px 4px 6px 2px;
    }
    .aa-chat-messages::-webkit-scrollbar {
      width: 5px;
    }
    .aa-chat-messages::-webkit-scrollbar-thumb {
      background: rgba(148, 163, 184, 0.28);
      border-radius: 999px;
    }
    .aa-msg {
      padding: 9px 11px;
      border-radius: 10px;
      font-size: 12px;
      line-height: 1.46;
      word-break: break-word;
      white-space: pre-wrap;
      flex-shrink: 0;
    }
    .aa-msg.user {
      background: #2563eb;
      color: #ffffff;
      align-self: flex-end;
      max-width: 88%;
      border-bottom-right-radius: 3px;
    }
    .aa-msg.assistant {
      background: rgba(30, 41, 59, 0.85);
      border: 1px solid rgba(148, 163, 184, 0.14);
      color: #f1f5f9;
      align-self: flex-start;
      max-width: 94%;
      border-bottom-left-radius: 3px;
      white-space: normal;
    }
    .aa-typing-row {
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }
    .aa-typing-dots {
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .aa-typing-dots span {
      width: 6px;
      height: 6px;
      border-radius: 999px;
      background: #38bdf8;
      display: inline-block;
      animation: aaPulseDot 1.2s infinite ease-in-out;
    }
    .aa-typing-dots span:nth-child(2) {
      animation-delay: 0.2s;
    }
    .aa-typing-dots span:nth-child(3) {
      animation-delay: 0.4s;
    }
    @keyframes aaPulseDot {
      0%, 80%, 100% { transform: scale(0.75); opacity: 0.35; }
      40% { transform: scale(1.2); opacity: 1; }
    }
    .aa-md-table {
      width: 100%;
      border-collapse: collapse;
      margin: 6px 0;
      font-size: 11.5px;
      border: 1px solid rgba(148, 163, 184, 0.28);
      border-radius: 6px;
      overflow: hidden;
    }
    .aa-md-table th {
      background: rgba(56, 189, 248, 0.14);
      color: #f8fafc;
      font-weight: 600;
      text-align: left;
      padding: 5px 8px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.28);
      border-right: 1px solid rgba(148, 163, 184, 0.2);
    }
    .aa-md-table td {
      padding: 5px 8px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.16);
      border-right: 1px solid rgba(148, 163, 184, 0.16);
      color: #e2e8f0;
    }
    .aa-md-table tr:nth-child(even) td {
      background: rgba(255, 255, 255, 0.03);
    }
    .aa-chat-composer {
      display: flex;
      align-items: flex-end;
      gap: 7px;
      padding-top: 8px;
      border-top: 1px solid rgba(148, 163, 184, 0.12);
      flex-shrink: 0;
    }
    .aa-chat-textarea {
      flex: 1;
      min-height: 34px;
      max-height: 84px;
      resize: none;
      padding: 7px 10px;
      border-radius: 9px;
      border: 1px solid rgba(148, 163, 184, 0.24);
      background: rgba(15, 23, 42, 0.85);
      color: #f8fafc;
      font-family: inherit;
      font-size: 12px;
      line-height: 1.4;
      outline: none;
      overflow-y: auto;
    }
    .aa-chat-textarea:focus {
      border-color: #3b82f6;
      box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
    }
    .aa-chat-send-circle {
      width: 32px;
      height: 32px;
      border-radius: 999px;
      border: none;
      background: #2563eb;
      color: #ffffff;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      flex-shrink: 0;
      transition: background 0.15s ease, transform 0.12s ease;
    }
    .aa-chat-send-circle:hover:not(:disabled) {
      background: #1d4ed8;
      transform: translateY(-1px);
    }
    .aa-chat-send-circle:disabled {
      background: rgba(148, 163, 184, 0.25);
      color: rgba(255, 255, 255, 0.5);
      cursor: default;
    }
    .aa-footer {
      padding: 9px 14px;
      background: rgba(9, 14, 26, 0.95);
      border-top: 1px solid rgba(148, 163, 184, 0.12);
      font-size: 11px;
      color: #64748b;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .aa-footer-status {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: #94a3b8;
      font-weight: 500;
    }
    .aa-mini-btn {
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(148, 163, 184, 0.16);
      color: #cbd5e1;
      border-radius: 6px;
      padding: 3px 9px;
      font-size: 11px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .aa-mini-btn:hover {
      background: rgba(255, 255, 255, 0.12);
      color: #ffffff;
    }
    .aa-btn-spinner {
      width: 13px;
      height: 13px;
      border-radius: 999px;
      border: 2px solid rgba(255, 255, 255, 0.3);
      border-top-color: #ffffff;
      animation: aaSpin 0.75s linear infinite;
      flex-shrink: 0;
    }
    @keyframes aaSpin {
      to { transform: rotate(360deg); }
    }
    .aa-btn-prefill.working,
    .aa-btn-apply.working {
      box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.55);
      opacity: 0.96 !important;
      cursor: progress;
    }
    .aa-pdf-preview-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      margin-top: 4px;
    }
    .aa-pdf-preview-btn {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 6px;
      padding: 7px 9px;
      border-radius: 8px;
      background: rgba(15, 23, 42, 0.85);
      border: 1px solid rgba(56, 189, 248, 0.35);
      color: #e0f2fe;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      text-align: left;
      transition: all 0.15s ease;
    }
    .aa-pdf-preview-btn:hover {
      background: rgba(37, 99, 235, 0.25);
      border-color: #38bdf8;
      color: #ffffff;
      transform: translateY(-1px);
    }
    .aa-jev-badge {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 3px 8px;
      border-radius: 6px;
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.4);
      color: #34d399;
      font-size: 10.5px;
      font-weight: 600;
      margin-top: 4px;
    }
    .aa-kb-update-box {
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.45);
      border-radius: 10px;
      padding: 10px 11px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .aa-kb-update-title {
      font-size: 11.5px;
      font-weight: 600;
      color: #6ee7b7;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 6px;
    }
    .aa-kb-preview-btn {
      background: rgba(15, 23, 42, 0.72);
      border: 1px solid rgba(110, 231, 183, 0.38);
      color: #a7f3d0;
      border-radius: 6px;
      padding: 2px 8px;
      font-size: 10.5px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s ease;
      white-space: nowrap;
    }
    .aa-kb-preview-btn:hover {
      background: rgba(16, 185, 129, 0.25);
      color: #ffffff;
      border-color: #6ee7b7;
    }
    .aa-kb-preview-list {
      display: flex;
      flex-direction: column;
      gap: 5px;
      max-height: 150px;
      overflow-y: auto;
      background: rgba(9, 14, 26, 0.78);
      border: 1px solid rgba(148, 163, 184, 0.22);
      border-radius: 8px;
      padding: 7px 8px;
    }
    .aa-kb-preview-item {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 8px;
      padding: 4px 6px;
      border-radius: 6px;
      background: rgba(30, 41, 59, 0.55);
      font-size: 11px;
      line-height: 1.35;
    }
    .aa-kb-preview-meta {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
      flex: 1;
    }
    .aa-kb-preview-label {
      color: #94a3b8;
      font-size: 10px;
      font-weight: 600;
      word-break: break-word;
    }
    .aa-kb-preview-value {
      color: #f8fafc;
      font-size: 11px;
      font-weight: 500;
      word-break: break-word;
    }
    .aa-kb-preview-remove {
      background: transparent;
      border: none;
      color: #94a3b8;
      font-size: 13px;
      line-height: 1;
      padding: 2px 4px;
      border-radius: 4px;
      cursor: pointer;
      flex-shrink: 0;
    }
    .aa-kb-preview-remove:hover {
      color: #f87171;
      background: rgba(239, 68, 68, 0.14);
    }
    .aa-kb-update-actions {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 6px;
      align-items: center;
    }
    .aa-issue-note-box {
      background: linear-gradient(145deg, rgba(245, 158, 11, 0.11) 0%, rgba(15, 23, 42, 0.75) 100%);
      border: 1px solid rgba(245, 158, 11, 0.34);
      border-left: 3px solid #f59e0b;
      border-radius: 10px;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      color: #fef3c7;
      font-size: 11.5px;
      line-height: 1.45;
    }
    .aa-issue-note-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      white-space: nowrap;
    }
    .aa-issue-note-title {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-weight: 600;
      color: #fbbf24;
      font-size: 11.5px;
      letter-spacing: -0.01em;
    }
    .aa-issue-note-actions {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .aa-issue-note-badge {
      font-size: 10px;
      font-weight: 600;
      color: #fcd34d;
      background: rgba(245, 158, 11, 0.16);
      border: 1px solid rgba(245, 158, 11, 0.28);
      padding: 1px 6px;
      border-radius: 999px;
    }
    .aa-issue-dismiss-btn {
      background: transparent;
      border: none;
      color: #94a3b8;
      font-size: 13px;
      line-height: 1;
      padding: 2px 4px;
      border-radius: 4px;
      cursor: pointer;
    }
    .aa-issue-dismiss-btn:hover {
      color: #f8fafc;
      background: rgba(255, 255, 255, 0.08);
    }
    .aa-issue-note-body {
      color: #e2e8f0;
      font-size: 11.5px;
      line-height: 1.45;
      word-break: break-word;
    }
    .aa-chat-mic-circle {
      width: 32px;
      height: 32px;
      border-radius: 999px;
      border: 1px solid rgba(148, 163, 184, 0.28);
      background: rgba(15, 23, 42, 0.85);
      color: #e2e8f0;
      display: inline-flex;
      align-items: center;
      align-content: center;
      justify-content: center;
      cursor: pointer;
      flex-shrink: 0;
      transition: all 0.15s ease;
    }
    .aa-chat-mic-circle:hover {
      background: rgba(30, 41, 59, 0.95);
      border-color: #60a5fa;
      color: #ffffff;
    }
    .aa-chat-mic-circle.recording {
      background: #ef4444;
      border-color: #ef4444;
      color: #ffffff;
      box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.25);
    }
    .aa-mic-rec-pill {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 4px 8px;
      border-radius: 999px;
      background: rgba(239, 68, 68, 0.14);
      border: 1px solid rgba(239, 68, 68, 0.35);
      color: #f87171;
      font-size: 10.5px;
      font-weight: 600;
      white-space: nowrap;
      flex-shrink: 0;
    }
    #aa-pwd-countdown-overlay {
      position: fixed;
      top: 14px;
      right: 14px;
      width: 292px;
      z-index: 2147483647;
      pointer-events: auto;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
    }
    .aa-pwd-countdown-card {
      background: linear-gradient(155deg, rgba(15, 23, 42, 0.98) 0%, rgba(9, 14, 26, 0.98) 100%);
      border: 1px solid rgba(56, 189, 248, 0.55);
      border-radius: 12px;
      padding: 12px 13px;
      box-shadow: 0 14px 36px rgba(0, 0, 0, 0.65), 0 0 0 1px rgba(56, 189, 248, 0.15);
      color: #f8fafc;
      display: flex;
      flex-direction: column;
      gap: 8px;
      backdrop-filter: blur(16px);
    }
    .aa-pwd-countdown-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .aa-pwd-countdown-title {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 700;
      color: #38bdf8;
      letter-spacing: -0.01em;
    }
    .aa-pwd-countdown-badge {
      font-size: 10.5px;
      font-weight: 700;
      color: #fbbf24;
      background: rgba(245, 158, 11, 0.16);
      border: 1px solid rgba(245, 158, 11, 0.36);
      padding: 2px 7px;
      border-radius: 999px;
      font-variant-numeric: tabular-nums;
    }
    .aa-pwd-countdown-site {
      font-size: 11.5px;
      color: #cbd5e1;
      font-weight: 500;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .aa-pwd-countdown-msg {
      font-size: 12px;
      font-weight: 600;
      color: #f8fafc;
      line-height: 1.35;
    }
    .aa-pwd-countdown-progress-track {
      width: 100%;
      height: 4px;
      border-radius: 999px;
      background: rgba(148, 163, 184, 0.22);
      overflow: hidden;
    }
    .aa-pwd-countdown-progress-fill {
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, #38bdf8 0%, #10b981 100%);
      transition: width 0.35s linear;
    }
    .aa-pwd-countdown-actions {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 2px;
    }
    .aa-pwd-btn-dont-save {
      flex: 1;
      padding: 6px 10px;
      border-radius: 8px;
      border: 1px solid rgba(248, 113, 113, 0.45);
      background: rgba(239, 68, 68, 0.14);
      color: #fca5a5;
      font-size: 11.5px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .aa-pwd-btn-dont-save:hover {
      background: rgba(239, 68, 68, 0.28);
      border-color: #f87171;
      color: #ffffff;
    }
    .aa-pwd-btn-save-now {
      flex: 1;
      padding: 6px 10px;
      border-radius: 8px;
      border: 1px solid rgba(16, 185, 129, 0.5);
      background: rgba(16, 185, 129, 0.22);
      color: #6ee7b7;
      font-size: 11.5px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .aa-pwd-btn-save-now:hover {
      background: rgba(16, 185, 129, 0.38);
      border-color: #34d399;
      color: #ffffff;
    }
  `;

  const container = document.createElement("div");
  const pwdCountdownToastHost = document.createElement("div");
  pwdCountdownToastHost.id = "aa-pwd-countdown-overlay";
  shadow.appendChild(style);
  shadow.appendChild(container);
  shadow.appendChild(pwdCountdownToastHost);
  document.documentElement.appendChild(host);

  function showNotice(text, kind = "ok") {
    statusBanner = { text, kind };
    render();
  }

  function sendBridgeAction(action, payload = {}) {
    const handleSuccess = (resp) => {
      if (resp && resp.ok && resp.data) {
        if (resp.data.onboarding) {
          bridgeState = resp.data;
          userSelectedAccordion = false;
        }
        if (resp.data.action_notice) {
          showNotice(resp.data.action_notice, "ok");
        }
      } else if (resp && resp.error) {
        showNotice(resp.error, "err");
      }
      return resp;
    };

    const fallbackDirectFetch = async () => {
      try {
        const r = await fetch("http://127.0.0.1:19299/api/companion", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action, payload }),
        });
        if (r.ok) {
          const data = await r.json();
          return handleSuccess({ ok: true, data });
        }
      } catch (_) {}
      return null;
    };

    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: "COMPANION_ACTION", action, payload }, async (resp) => {
          if (resp && resp.ok && resp.data) {
            resolve(handleSuccess(resp));
            return;
          }
          const directResp = await fallbackDirectFetch();
          if (directResp) {
            resolve(directResp);
            return;
          }
          resolve(handleSuccess(resp));
        });
      } catch (_) {
        fallbackDirectFetch().then((directResp) => resolve(directResp));
      }
    });
  }

  function encodePcm16kWavBase64(float32Chunks, inputSampleRate = 48000) {
    let rawLength = 0;
    for (const c of float32Chunks) rawLength += c.length;
    if (rawLength < 1600) return "";

    const merged = new Float32Array(rawLength);
    let writePos = 0;
    for (const c of float32Chunks) {
      merged.set(c, writePos);
      writePos += c.length;
    }

    const targetRate = 16000;
    const srcRate = inputSampleRate > 0 ? inputSampleRate : 48000;
    let pcmSamples = merged;
    if (Math.abs(srcRate - targetRate) > 100) {
      const ratio = srcRate / targetRate;
      const outLength = Math.max(1, Math.round(merged.length / ratio));
      pcmSamples = new Float32Array(outLength);
      for (let i = 0; i < outLength; i++) {
        const start = Math.floor(i * ratio);
        const end = Math.min(merged.length, Math.max(start + 1, Math.floor((i + 1) * ratio)));
        let sum = 0;
        for (let j = start; j < end; j++) {
          sum += merged[j];
        }
        pcmSamples[i] = sum / (end - start);
      }
    }

    const totalSamples = pcmSamples.length;
    if (totalSamples < 1600) return "";
    const buffer = new ArrayBuffer(44 + totalSamples * 2);
    const view = new DataView(buffer);
    const writeStr = (offset, str) => {
      for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
    };
    writeStr(0, "RIFF");
    view.setUint32(4, 36 + totalSamples * 2, true);
    writeStr(8, "WAVE");
    writeStr(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, targetRate, true);
    view.setUint32(28, targetRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeStr(36, "data");
    view.setUint32(40, totalSamples * 2, true);
    let offset = 44;
    for (let i = 0; i < totalSamples; i++) {
      const s = Math.max(-1, Math.min(1, pcmSamples[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      offset += 2;
    }
    const bytes = new Uint8Array(buffer);
    let binary = "";
    const step = 0x8000;
    for (let i = 0; i < bytes.length; i += step) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + step));
    }
    return btoa(binary);
  }

  function applyExtMicTranscript(transcriptText) {
    const trimmed = String(transcriptText || "").trim();
    if (!trimmed) return;
    const prefix = String(preExtMicDraftText || "").trim();
    const combined = prefix ? `${prefix} ${trimmed}` : trimmed;
    draftChatInput = combined;
    const chatEl = shadow.getElementById("aa-chat-input");
    if (chatEl) {
      chatEl.value = combined;
      chatEl.style.height = "auto";
      chatEl.style.height = `${Math.min(84, Math.max(34, chatEl.scrollHeight))}px`;
    }
  }

  function stopExtChatMicRecording(transcribeFinal = true) {
    if (extMicTimer) {
      clearInterval(extMicTimer);
      extMicTimer = null;
    }
    if (extMicProcessor) {
      try {
        extMicProcessor.disconnect();
      } catch (_) {}
      extMicProcessor = null;
    }
    const sampleRate = (extMicAudioCtx && extMicAudioCtx.sampleRate) || 48000;
    if (extMicAudioCtx) {
      try {
        extMicAudioCtx.close();
      } catch (_) {}
      extMicAudioCtx = null;
    }
    if (extMicStream) {
      try {
        extMicStream.getTracks().forEach((t) => t.stop());
      } catch (_) {}
      extMicStream = null;
    }
    const chunksCopy = extMicPcmChunks.slice();
    extMicPcmChunks = [];
    isExtMicRecording = false;

    if (transcribeFinal && chunksCopy.length > 0) {
      const wavB64 = encodePcm16kWavBase64(chunksCopy, sampleRate);
      if (wavB64) {
        isExtMicTranscribing = true;
        render();
        sendBridgeAction("transcribe_voice_live", { audio_base64: wavB64 }).then((resp) => {
          isExtMicTranscribing = false;
          const text = resp && resp.ok && resp.data && resp.data.transcript;
          if (text) {
            applyExtMicTranscript(text);
          }
          render();
        });
        return;
      }
    }
    isExtMicTranscribing = false;
    render();
  }

  async function toggleExtChatMicRecording() {
    if (isExtMicRecording) {
      stopExtChatMicRecording(true);
      return;
    }
    const chatEl = shadow.getElementById("aa-chat-input");
    preExtMicDraftText = (chatEl ? chatEl.value : draftChatInput) || "";
    extMicPcmChunks = [];
    extMicSeconds = 0;
    isExtMicLiveInFlight = false;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: true,
        },
      });
      extMicStream = stream;
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      const audioCtx = new AudioCtx();
      extMicAudioCtx = audioCtx;
      if (audioCtx.state === "suspended") {
        try {
          await audioCtx.resume();
        } catch (_) {}
      }
      const source = audioCtx.createMediaStreamSource(stream);
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      const silentGain = audioCtx.createGain();
      silentGain.gain.value = 0;
      extMicProcessor = processor;
      processor.onaudioprocess = (e) => {
        if (!isExtMicRecording) return;
        const inputData = e.inputBuffer.getChannelData(0);
        extMicPcmChunks.push(new Float32Array(inputData));
      };
      source.connect(processor);
      processor.connect(silentGain);
      silentGain.connect(audioCtx.destination);
      isExtMicRecording = true;
      render();

      extMicTimer = setInterval(() => {
        if (!isExtMicRecording) return;
        extMicSeconds += 1;
        const recSpan = shadow.getElementById("aa-ext-mic-timer");
        if (recSpan) {
          const mins = Math.floor(extMicSeconds / 60);
          const secs = String(extMicSeconds % 60).padStart(2, "0");
          recSpan.textContent = `${mins}:${secs}`;
        }
        if (extMicSeconds >= 2 && extMicSeconds % 2 === 0 && !isExtMicLiveInFlight && extMicPcmChunks.length > 0) {
          const wavB64 = encodePcm16kWavBase64(extMicPcmChunks, audioCtx.sampleRate || 48000);
          if (wavB64) {
            isExtMicLiveInFlight = true;
            sendBridgeAction("transcribe_voice_live", { audio_base64: wavB64 }).then((resp) => {
              isExtMicLiveInFlight = false;
              const text = resp && resp.ok && resp.data && resp.data.transcript;
              if (isExtMicRecording && text) {
                applyExtMicTranscript(text);
              }
            });
          }
        }
      }, 1000);
    } catch (err) {
      isExtMicRecording = false;
      showNotice("Microphone permission is needed on this page to record voice.", "err");
    }
  }

  function buildKbUpdateBoxHTML() {
    const editsList = Object.values(manualFieldEdits);
    const editCount = editsList.length;
    if (editCount === 0) return "";

    const previewItemsHTML = isKbEditsPreviewOpen
      ? `
        <div class="aa-kb-preview-list">
          ${editsList
            .map(
              (item) => `
              <div class="aa-kb-preview-item">
                <div class="aa-kb-preview-meta">
                  <span class="aa-kb-preview-label">${escapeHtml(item.label)}</span>
                  <span class="aa-kb-preview-value">${escapeHtml(item.value)}</span>
                </div>
                <button class="aa-kb-preview-remove" data-remove-kb-field="${escapeHtml(item.field_key)}" title="Remove this field" type="button">×</button>
              </div>
            `
            )
            .join("")}
        </div>
      `
      : "";

    return `
      <div class="aa-kb-update-box">
        <div class="aa-kb-update-title">
          <span>New information entered (${editCount} field${editCount === 1 ? "" : "s"})</span>
          <button id="aa-btn-preview-kb" class="aa-kb-preview-btn" type="button">
            ${isKbEditsPreviewOpen ? "Hide Preview ▴" : "Preview ▾"}
          </button>
        </div>
        ${previewItemsHTML}
        <div class="aa-kb-update-actions">
          <button id="aa-btn-update-kb" class="aa-btn green" type="button" ${isSavingKbEdits ? "disabled" : ""}>
            ${isSavingKbEdits ? "Updating…" : "Update Knowledge Base"}
          </button>
          <button id="aa-btn-dismiss-kb" class="aa-btn secondary" type="button" style="padding:7px 10px;font-size:11.5px;">
            Dismiss
          </button>
        </div>
      </div>
    `;
  }

  function bindKbUpdateBoxEvents() {
    const updateKbBtn = shadow.getElementById("aa-btn-update-kb");
    if (updateKbBtn) {
      updateKbBtn.onclick = () => saveManualEditsToKnowledgeBase();
    }
    const previewKbBtn = shadow.getElementById("aa-btn-preview-kb");
    if (previewKbBtn) {
      previewKbBtn.onclick = () => {
        isKbEditsPreviewOpen = !isKbEditsPreviewOpen;
        const kbSlot = shadow.getElementById("aa-kb-update-slot");
        if (kbSlot) {
          kbSlot.innerHTML = buildKbUpdateBoxHTML();
          bindKbUpdateBoxEvents();
        } else {
          render();
        }
      };
    }
    const dismissKbBtn = shadow.getElementById("aa-btn-dismiss-kb");
    if (dismissKbBtn) {
      dismissKbBtn.onclick = () => {
        manualFieldEdits = {};
        isKbEditsPreviewOpen = false;
        const kbSlot = shadow.getElementById("aa-kb-update-slot");
        if (kbSlot) {
          kbSlot.innerHTML = "";
        } else {
          render();
        }
      };
    }
    shadow.querySelectorAll("[data-remove-kb-field]").forEach((rmBtn) => {
      rmBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const fKey = rmBtn.getAttribute("data-remove-kb-field");
        if (fKey && manualFieldEdits[fKey]) {
          delete manualFieldEdits[fKey];
        }
        if (Object.keys(manualFieldEdits).length === 0) {
          isKbEditsPreviewOpen = false;
        }
        const kbSlot = shadow.getElementById("aa-kb-update-slot");
        if (kbSlot) {
          kbSlot.innerHTML = buildKbUpdateBoxHTML();
          bindKbUpdateBoxEvents();
        } else {
          render();
        }
      });
    });
  }

  function recordManualFieldEditFromEvent(ev) {
    try {
      if (!ev || ev.isTrusted === false) return;
      const el = ev && ev.target;
      if (!el || !el.tagName || host.contains(el)) return;
      if (isBusyWorking || programmaticTypingSet.has(el)) return;
      const tag = el.tagName.toLowerCase();
      if (!["input", "textarea", "select"].includes(tag)) return;
      if (isSearchOrNavControl(el) || isPasswordLikeInput(el)) return;
      if (
        el.closest(
          'header, nav, aside, [role="navigation"], [role="search"], [class*="chat" i], [data-qa*="chat" i], [class*="filter" i], [data-qa*="search" i]'
        )
      ) {
        return;
      }
      const rawType = (el.getAttribute("type") || tag).toLowerCase();
      if (["hidden", "file", "submit", "button", "reset", "image", "password", "search"].includes(rawType)) return;

      const jobParams = detectJobPageParameters();
      if (!jobParams || !jobParams.isJobPage) return;

      // On primary job boards (hh.ru, LinkedIn, Indeed, Glassdoor, etc.), only capture edits inside an open application modal/form, never on the feed/dashboard!
      if (jobParams.matchedBoard && jobParams.matchedBoard.is_primary) {
        const inAppModalOrForm = Boolean(
          findOpenEasyApplyModal() ||
            jobParams.hasResumeFileInput ||
            el.closest(
              '[data-qa*="vacancy-response"], form[action*="apply" i], [class*="apply-modal" i], .jobs-easy-apply-modal'
            )
        );
        if (!inAppModalOrForm) return;
      }

      let newVal = "";
      if (tag === "select") {
        const selOpt = el.options && el.options[el.selectedIndex];
        newVal = String((selOpt && (selOpt.text || selOpt.value)) || el.value || "").trim();
      } else if (rawType === "checkbox" || rawType === "radio") {
        if (!el.checked) return;
        newVal = String(el.closest("label")?.innerText || el.value || "Yes").trim();
      } else {
        newVal = String(el.value || "").trim();
      }
      if (!newVal) return;

      const prevAutoVal = String(el.dataset.aaAutoFilledValue || "").trim();
      if (prevAutoVal && prevAutoVal === newVal) return;

      const label = (getFieldLabelText(el) || el.name || el.placeholder || el.id || "").replace(/\*/g, "").trim();
      if (!label || label.length < 2) return;
      if (
        /^(?:unread only|непрочитанные|search|поиск|профессия,\s*должность\s*или\s*компания|profession,\s*position\s*or\s*company|remember me|запомнить|show password|показать пароль|sort by|filter|all|все)$/i.test(
          label
        )
      ) {
        return;
      }

      const fieldKey = el.getAttribute("data-aa-field-id") || el.name || el.id || label.toLowerCase();
      manualFieldEdits[fieldKey] = {
        label,
        value: newVal,
        field_key: fieldKey,
        name: el.name || "",
      };

      const kbSlot = shadow.getElementById("aa-kb-update-slot");
      if (kbSlot) {
        kbSlot.innerHTML = buildKbUpdateBoxHTML();
        bindKbUpdateBoxEvents();
      }
    } catch (_) {}
  }

  async function saveManualEditsToKnowledgeBase() {
    const editsList = Object.values(manualFieldEdits);
    if (editsList.length === 0 || isSavingKbEdits) return;
    isSavingKbEdits = true;
    render();
    try {
      const meta = extractJobMetadataFromPage();
      await sendBridgeAction("save_manual_form_edits_to_kb", {
        edits: editsList,
        job_context: {
          title: meta.title,
          company_name: meta.company_name,
          canonical_url: meta.canonical_url,
          location: meta.location,
        },
      });
      manualFieldEdits = {};
      isKbEditsPreviewOpen = false;
    } finally {
      isSavingKbEdits = false;
      render();
    }
  }

  document.addEventListener("change", recordManualFieldEditFromEvent, true);
  document.addEventListener("input", recordManualFieldEditFromEvent, true);

  // =========================================================================
  // Automatic Password Manager Capture, 10-Second Save Countdown & Autofill
  // =========================================================================
  const trackedPasswordInputs = new WeakSet();
  const autofilledPasswordInputs = new WeakSet();
  let pendingPasswordCapture = null;
  let pwdCountdownInterval = null;
  let postSubmitCheckTimer = null;

  function normalizeBaseHost(hostnameStr) {
    let h = String(hostnameStr || window.location.hostname || "")
      .toLowerCase()
      .trim()
      .replace(/^www\./, "");
    if (h === "hh.ru" || h.endsWith(".hh.ru")) return "hh.ru";
    if (h === "indeed.com" || h.endsWith(".indeed.com")) return "indeed.com";
    if (h === "linkedin.com" || h.endsWith(".linkedin.com")) return "linkedin.com";
    if (h === "glassdoor.com" || h.endsWith(".glassdoor.com")) return "glassdoor.com";
    return h;
  }

  function resolveSiteNameAndCanonicalUrl() {
    const rawHost = (window.location.hostname || "").toLowerCase();
    const normHost = normalizeBaseHost(rawHost);
    const board = findMatchingDesktopJobBoard(rawHost, window.location.href);
    if (board && board.name) {
      const cleanOrigin = normHost === "hh.ru" ? "https://hh.ru" : window.location.origin;
      return { website_name: board.name, website_url: cleanOrigin, hostname: normHost };
    }
    const knownNames = {
      "hh.ru": "HeadHunter (hh.ru)",
      "linkedin.com": "LinkedIn",
      "indeed.com": "Indeed",
      "glassdoor.com": "Glassdoor",
      "djinni.co": "Djinni",
      "dou.ua": "DOU",
      "work.ua": "Work.ua",
      "robota.ua": "Robota.ua",
      "rabota.ua": "Robota.ua",
      "wellfound.com": "Wellfound",
      "theladders.com": "Ladders",
      "dice.com": "Dice",
      "ziprecruiter.com": "ZipRecruiter",
      "monster.com": "Monster",
    };
    if (knownNames[normHost]) {
      return {
        website_name: knownNames[normHost],
        website_url: normHost === "hh.ru" ? "https://hh.ru" : window.location.origin,
        hostname: normHost,
      };
    }
    const meta = extractJobMetadataFromPage();
    if (meta && meta.company_name && meta.company_name !== "Target Company") {
      return {
        website_name: `${meta.company_name} Careers`,
        website_url: window.location.origin,
        hostname: normHost,
      };
    }
    return {
      website_name: normHost || "Career Portal",
      website_url: window.location.origin,
      hostname: normHost,
    };
  }

  function isPasswordLikeInput(el) {
    if (!el || el.tagName !== "INPUT" || host.contains(el)) return false;
    const t = String(el.getAttribute("type") || el.type || "").toLowerCase();
    if (t === "password") {
      trackedPasswordInputs.add(el);
      return true;
    }
    if (trackedPasswordInputs.has(el)) return true;
    const ac = String(el.getAttribute("autocomplete") || "").toLowerCase();
    const qa = String(el.getAttribute("data-qa") || "").toLowerCase();
    const nameId = `${el.name || ""} ${el.id || ""}`.toLowerCase();
    if (
      ac.includes("current-password") ||
      ac.includes("new-password") ||
      qa.includes("login-input-password") ||
      qa.includes("password") ||
      /\b(password|passwd|user_password)\b/.test(nameId)
    ) {
      trackedPasswordInputs.add(el);
      return true;
    }
    return false;
  }

  function isUsernameOrLoginInput(el) {
    if (!el || el.tagName !== "INPUT" || host.contains(el) || isPasswordLikeInput(el)) return false;
    const t = String(el.getAttribute("type") || el.type || "text").toLowerCase();
    if (!["text", "email", "tel"].includes(t)) return false;
    const meta = `${el.name || ""} ${el.id || ""} ${el.getAttribute("autocomplete") || ""} ${el.getAttribute("data-qa") || ""} ${el.placeholder || ""} ${el.getAttribute("aria-label") || ""}`.toLowerCase();
    return (
      t === "email" ||
      /email|e-mail|username|login|account|phone|почта|телефон|логин|expandable-login-input/i.test(meta)
    );
  }

  function detectCurrentFormUsername(pwEl) {
    const scope =
      (pwEl && pwEl.closest("form, [role='dialog'], .bloko-modal, [data-qa*='login'], section, main")) ||
      document;
    const inputs = Array.from(scope.querySelectorAll("input"));
    for (const inp of inputs) {
      if (inp === pwEl || isPasswordLikeInput(inp)) continue;
      if (isUsernameOrLoginInput(inp) && inp.value && inp.value.trim().length >= 3) {
        return inp.value.trim();
      }
    }
    const allInputs = Array.from(document.querySelectorAll("input"));
    for (const inp of allInputs) {
      if (inp === pwEl || isPasswordLikeInput(inp)) continue;
      if (isUsernameOrLoginInput(inp) && inp.value && inp.value.trim().length >= 3) {
        return inp.value.trim();
      }
    }
    // Check if the login card displays the entered email/phone in text (e.g. Step 2 on hh.ru)
    const scopeText = (scope && scope.innerText) || "";
    const emailMatch = scopeText.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
    if (emailMatch && emailMatch[0]) {
      return emailMatch[0].trim();
    }
    try {
      const savedUser = sessionStorage.getItem("aa_last_typed_username");
      if (savedUser && savedUser.trim().length >= 3) {
        return savedUser.trim();
      }
    } catch (_) {}
    const candEmail =
      (bridgeState &&
        bridgeState.knowledge_base &&
        bridgeState.knowledge_base.profile_header &&
        bridgeState.knowledge_base.profile_header.email) ||
      "alex.mercer@example.com";
    return candEmail;
  }

  function isCredentialAlreadySavedInVault(normHost, username, password) {
    const vault = (bridgeState && Array.isArray(bridgeState.password_vault) && bridgeState.password_vault) || [];
    for (const entry of vault) {
      if (!entry || !entry.password) continue;
      let entryHost = "";
      try {
        const u = String(entry.website_url || "");
        const parsed = new URL(u.includes("://") ? u : `https://${u}`);
        entryHost = normalizeBaseHost(parsed.hostname);
      } catch (_) {
        entryHost = normalizeBaseHost(entry.website_url || "");
      }
      if (entryHost === normHost && String(entry.password) === String(password)) {
        if (!username || !entry.username || String(entry.username).toLowerCase() === String(username).toLowerCase()) {
          return true;
        }
      }
    }
    return false;
  }

  function persistPendingPasswordCapture(obj) {
    pendingPasswordCapture = obj;
    try {
      if (obj) {
        sessionStorage.setItem("aa_pending_password_capture", JSON.stringify(obj));
      } else {
        sessionStorage.removeItem("aa_pending_password_capture");
      }
    } catch (_) {}
    try {
      if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
        if (obj) {
          chrome.storage.local.set({ aa_pending_password_capture: obj });
        } else {
          chrome.storage.local.remove("aa_pending_password_capture");
        }
      }
    } catch (_) {}
  }

  function recordTypedPasswordCandidate(pwEl, markSubmitted = false) {
    if (!pwEl || !isPasswordLikeInput(pwEl)) return;
    const pwdVal = String(pwEl.value || "").trim();
    if (pwdVal.length < 4) return;
    // Ignore Google App Password generator page (handled separately)
    if ((window.location.href || "").toLowerCase().includes("myaccount.google.com/apppasswords")) return;

    const siteInfo = resolveSiteNameAndCanonicalUrl();
    const userVal = detectCurrentFormUsername(pwEl);
    if (isCredentialAlreadySavedInVault(siteInfo.hostname, userVal, pwdVal)) {
      return;
    }

    const nowTs = Date.now();
    const existing = pendingPasswordCapture || {};
    const updated = {
      website_name: siteInfo.website_name,
      website_url: siteInfo.website_url,
      hostname: siteInfo.hostname,
      username: userVal,
      password: pwdVal,
      login_url: existing.login_url || window.location.href,
      captured_at: nowTs,
      submitted: Boolean(markSubmitted || existing.submitted),
      submitted_at: markSubmitted ? nowTs : existing.submitted_at || 0,
      countdown_started_at: existing.countdown_started_at || 0,
      dont_save: false,
      saved: false,
    };
    persistPendingPasswordCapture(updated);
  }

  function detectLoginErrorMessageOnPage() {
    const errSelectors = [
      '[data-qa="account-login-error"]',
      '[data-qa*="form-helper-error"]',
      '[data-qa*="error"]',
      ".bloko-form-error",
      '[role="alert"]',
      ".form-error",
      ".error-message",
    ];
    for (const sel of errSelectors) {
      const nodes = document.querySelectorAll(sel);
      for (const n of nodes) {
        if (!n || host.contains(n) || n.offsetParent === null) continue;
        const txt = (n.innerText || n.textContent || "").trim().toLowerCase();
        if (
          /неверн|неправильн|ошибка входа|invalid|incorrect|wrong password|authentication failed|login failed/i.test(
            txt
          )
        ) {
          return true;
        }
      }
    }
    return false;
  }

  function isCurrentSiteLoggedInAfterPasswordEntry(pending) {
    if (detectLoginErrorMessageOnPage()) return false;
    const normHost = normalizeBaseHost(window.location.hostname);
    if (normHost === "hh.ru") {
      if (
        document.querySelector(
          '[data-qa="mainmenu_applicantProfile"], [data-qa="mainmenu_myResumes"], [data-qa="mainmenu_vacancyResponses"], a[href*="/applicant/resumes"], a[href*="/applicant/negotiations"], [data-qa="supernova-navi-item-resumes"]'
        )
      ) {
        return true;
      }
    }
    if (normHost === "linkedin.com" && isAuthenticatedLinkedInPage()) return true;
    if (normHost.includes("tealhq.com") && isAuthenticatedTealPage()) return true;

    const visiblePwInputs = Array.from(document.querySelectorAll('input[type="password"]')).filter(
      (el) => el && !host.contains(el) && el.offsetParent !== null
    );
    if (visiblePwInputs.length === 0 && !isUnauthenticatedAuthPage()) {
      return true;
    }
    if (
      pending &&
      pending.login_url &&
      window.location.href !== pending.login_url &&
      visiblePwInputs.length === 0
    ) {
      return true;
    }
    return false;
  }

  function renderPasswordCountdownOverlay() {
    if (!pwdCountdownToastHost) return;
    const p = pendingPasswordCapture;
    if (!p || p.dont_save || p.saved || !p.countdown_started_at) {
      pwdCountdownToastHost.innerHTML = "";
      return;
    }
    const elapsedSec = Math.floor((Date.now() - p.countdown_started_at) / 1000);
    const remainingSec = Math.max(0, 10 - elapsedSec);
    const pct = Math.max(0, Math.min(100, (remainingSec / 10) * 100));

    pwdCountdownToastHost.innerHTML = `
      <div class="aa-pwd-countdown-card" role="status" aria-live="polite">
        <div class="aa-pwd-countdown-header">
          <span class="aa-pwd-countdown-title">🔑 Save Password</span>
          <span class="aa-pwd-countdown-badge">${remainingSec}s</span>
        </div>
        <div class="aa-pwd-countdown-site">${escapeHtml(p.website_name)} · ${escapeHtml(p.username)}</div>
        <div class="aa-pwd-countdown-msg">Password will be saved in ${remainingSec} second${remainingSec === 1 ? "" : "s"}</div>
        <div class="aa-pwd-countdown-progress-track">
          <div class="aa-pwd-countdown-progress-fill" style="width: ${pct}%;"></div>
        </div>
        <div class="aa-pwd-countdown-actions">
          <button id="aa-pwd-dont-save-btn" class="aa-pwd-btn-dont-save" type="button">Don't Save</button>
          <button id="aa-pwd-save-now-btn" class="aa-pwd-btn-save-now" type="button">Save Now</button>
        </div>
      </div>
    `;

    const dontSaveBtn = shadow.getElementById("aa-pwd-dont-save-btn");
    if (dontSaveBtn) {
      dontSaveBtn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (pwdCountdownInterval) {
          clearInterval(pwdCountdownInterval);
          pwdCountdownInterval = null;
        }
        persistPendingPasswordCapture(null);
        pwdCountdownToastHost.innerHTML = "";
        showNotice("Password was not saved.", "ok");
      };
    }

    const saveNowBtn = shadow.getElementById("aa-pwd-save-now-btn");
    if (saveNowBtn) {
      saveNowBtn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        commitPendingPasswordToVault();
      };
    }
  }

  function commitPendingPasswordToVault() {
    const p = pendingPasswordCapture;
    if (!p || p.dont_save || p.saved || !p.password) return;
    if (pwdCountdownInterval) {
      clearInterval(pwdCountdownInterval);
      pwdCountdownInterval = null;
    }
    p.saved = true;
    persistPendingPasswordCapture(null);

    sendBridgeAction("save_password_entry", {
      website_name: p.website_name,
      website_url: p.website_url,
      username: p.username,
      password: p.password,
      description: `Auto-saved after login on ${p.hostname}`,
      auto_registered: false,
    }).then(() => {
      refreshState(true);
    });

    if (pwdCountdownToastHost) {
      pwdCountdownToastHost.innerHTML = `
        <div class="aa-pwd-countdown-card" style="border-color: rgba(16, 185, 129, 0.65);">
          <div class="aa-pwd-countdown-header">
            <span class="aa-pwd-countdown-title" style="color: #34d399;">✅ Password Saved</span>
          </div>
          <div class="aa-pwd-countdown-site">${escapeHtml(p.website_name)} · ${escapeHtml(p.username)}</div>
          <div class="aa-pwd-countdown-msg" style="font-weight: 500; color: #a7f3d0;">Saved to AutoApply Password Manager.</div>
        </div>
      `;
      setTimeout(() => {
        if (pwdCountdownToastHost) pwdCountdownToastHost.innerHTML = "";
      }, 3200);
    }
  }

  function startTenSecondPasswordSaveCountdown(pending) {
    if (!pending || pending.dont_save || pending.saved || !pending.password) return;
    if (isCredentialAlreadySavedInVault(pending.hostname, pending.username, pending.password)) {
      persistPendingPasswordCapture(null);
      return;
    }
    if (!pending.countdown_started_at) {
      pending.countdown_started_at = Date.now();
      persistPendingPasswordCapture(pending);
    }
    renderPasswordCountdownOverlay();
    if (pwdCountdownInterval) clearInterval(pwdCountdownInterval);
    pwdCountdownInterval = setInterval(() => {
      const cur = pendingPasswordCapture;
      if (!cur || cur.dont_save || cur.saved) {
        clearInterval(pwdCountdownInterval);
        pwdCountdownInterval = null;
        if (pwdCountdownToastHost) pwdCountdownToastHost.innerHTML = "";
        return;
      }
      const elapsedSec = Math.floor((Date.now() - cur.countdown_started_at) / 1000);
      if (elapsedSec >= 10) {
        commitPendingPasswordToVault();
      } else {
        renderPasswordCountdownOverlay();
      }
    }, 250);
  }

  function checkAndTriggerPendingPasswordCountdown() {
    const loadCandidate = (cand) => {
      if (!cand || cand.dont_save || cand.saved || !cand.password) return;
      const ageMs = Date.now() - (cand.captured_at || 0);
      if (ageMs > 180000) {
        persistPendingPasswordCapture(null);
        return;
      }
      const curHost = normalizeBaseHost(window.location.hostname);
      if (cand.hostname && curHost && cand.hostname !== curHost) {
        return;
      }
      pendingPasswordCapture = cand;
      if (cand.countdown_started_at) {
        const elapsedSec = Math.floor((Date.now() - cand.countdown_started_at) / 1000);
        if (elapsedSec >= 10) {
          commitPendingPasswordToVault();
        } else {
          startTenSecondPasswordSaveCountdown(cand);
        }
        return;
      }
      if (isCurrentSiteLoggedInAfterPasswordEntry(cand)) {
        startTenSecondPasswordSaveCountdown(cand);
      }
    };

    if (pendingPasswordCapture) {
      loadCandidate(pendingPasswordCapture);
      return;
    }
    try {
      const rawSession = sessionStorage.getItem("aa_pending_password_capture");
      if (rawSession) {
        loadCandidate(JSON.parse(rawSession));
        return;
      }
    } catch (_) {}
    try {
      if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
        chrome.storage.local.get(["aa_pending_password_capture"], (res) => {
          if (res && res.aa_pending_password_capture) {
            loadCandidate(res.aa_pending_password_capture);
          }
        });
      }
    } catch (_) {}
  }

  function schedulePostSubmitLoginVerification() {
    // Capture any currently filled password input on the page first
    const pwEls = Array.from(document.querySelectorAll("input")).filter((el) => isPasswordLikeInput(el) && el.value);
    for (const pwEl of pwEls) {
      recordTypedPasswordCandidate(pwEl, true);
    }
    if (pendingPasswordCapture && !pendingPasswordCapture.submitted) {
      pendingPasswordCapture.submitted = true;
      pendingPasswordCapture.submitted_at = Date.now();
      persistPendingPasswordCapture(pendingPasswordCapture);
    }
    if (postSubmitCheckTimer) clearInterval(postSubmitCheckTimer);
    let checks = 0;
    postSubmitCheckTimer = setInterval(() => {
      checks += 1;
      checkAndTriggerPendingPasswordCountdown();
      if (checks >= 20 || (pendingPasswordCapture && pendingPasswordCapture.countdown_started_at)) {
        clearInterval(postSubmitCheckTimer);
        postSubmitCheckTimer = null;
      }
    }, 450);
  }

  async function maybeAutofillSavedSiteLogin() {
    if (isBusyWorking) return;
    const vault = (bridgeState && Array.isArray(bridgeState.password_vault) && bridgeState.password_vault) || [];
    if (vault.length === 0) return;

    const curHost = normalizeBaseHost(window.location.hostname);
    if (!curHost) return;

    const matchingEntry = vault.find((e) => {
      if (!e || !e.password) return false;
      let eHost = "";
      try {
        const u = String(e.website_url || "");
        const parsed = new URL(u.includes("://") ? u : `https://${u}`);
        eHost = normalizeBaseHost(parsed.hostname);
      } catch (_) {
        eHost = normalizeBaseHost(e.website_url || "");
      }
      return eHost === curHost;
    });
    if (!matchingEntry) return;

    const visiblePwInputs = Array.from(document.querySelectorAll('input[type="password"]')).filter(
      (el) => el && !host.contains(el) && !el.disabled && !el.readOnly && el.offsetParent !== null
    );
    if (visiblePwInputs.length === 0) return;

    let filledAny = false;
    for (const pwEl of visiblePwInputs) {
      if (autofilledPasswordInputs.has(pwEl) || (pwEl.value && pwEl.value.length > 0)) continue;
      autofilledPasswordInputs.add(pwEl);

      const scope =
        pwEl.closest("form, [role='dialog'], .bloko-modal, [data-qa*='login'], section, main") || document;
      const loginInputs = Array.from(scope.querySelectorAll("input")).filter(
        (inp) =>
          inp &&
          inp !== pwEl &&
          !inp.disabled &&
          !inp.readOnly &&
          inp.offsetParent !== null &&
          isUsernameOrLoginInput(inp)
      );
      for (const uEl of loginInputs) {
        if (!uEl.value && matchingEntry.username) {
          await typeTextHumanLike(uEl, matchingEntry.username);
          break;
        }
      }

      await typeTextHumanLike(pwEl, matchingEntry.password);
      filledAny = true;
    }
    if (filledAny) {
      showNotice(`🔐 Autofilled saved login for ${matchingEntry.website_name || curHost}.`, "ok");
    }
  }

  document.addEventListener(
    "input",
    (ev) => {
      const el = ev && ev.target;
      if (!el || !el.tagName || host.contains(el)) return;
      if (programmaticTypingSet.has(el)) return;
      if (isPasswordLikeInput(el)) {
        recordTypedPasswordCandidate(el, false);
      } else if (isUsernameOrLoginInput(el) && el.value && el.value.trim().length >= 3) {
        try {
          sessionStorage.setItem("aa_last_typed_username", el.value.trim());
        } catch (_) {}
        if (pendingPasswordCapture && !pendingPasswordCapture.countdown_started_at) {
          pendingPasswordCapture.username = el.value.trim();
          persistPendingPasswordCapture(pendingPasswordCapture);
        }
      }
    },
    true
  );

  document.addEventListener(
    "change",
    (ev) => {
      const el = ev && ev.target;
      if (!el || !el.tagName || host.contains(el) || programmaticTypingSet.has(el)) return;
      if (isPasswordLikeInput(el)) {
        recordTypedPasswordCandidate(el, false);
      }
    },
    true
  );

  document.addEventListener(
    "keydown",
    (ev) => {
      if (!ev || ev.key !== "Enter") return;
      const el = ev.target;
      if (el && !host.contains(el) && (isPasswordLikeInput(el) || isUsernameOrLoginInput(el))) {
        schedulePostSubmitLoginVerification();
      }
    },
    true
  );

  document.addEventListener(
    "submit",
    (ev) => {
      const form = ev && ev.target;
      if (form && !host.contains(form)) {
        schedulePostSubmitLoginVerification();
      }
    },
    true
  );

  document.addEventListener(
    "click",
    (ev) => {
      const t = ev && ev.target;
      if (!t || !t.closest || host.contains(t)) return;
      const btn = t.closest('button, input[type="submit"], [role="button"], [data-qa*="login"], [data-qa*="submit"]');
      if (btn) {
        const hasPwOnPage = Array.from(document.querySelectorAll("input")).some(
          (inp) => isPasswordLikeInput(inp) && inp.value && inp.value.trim().length >= 4
        );
        if (hasPwOnPage || pendingPasswordCapture) {
          schedulePostSubmitLoginVerification();
        }
      }
    },
    true
  );

  window.addEventListener(
    "beforeunload",
    () => {
      const pwEls = Array.from(document.querySelectorAll("input")).filter(
        (el) => isPasswordLikeInput(el) && el.value && el.value.trim().length >= 4
      );
      for (const pwEl of pwEls) {
        recordTypedPasswordCandidate(pwEl, true);
      }
    },
    { capture: true }
  );

  function navigateTo(url) {
    window.location.href = url;
  }

  let draftInputs = {
    orKey: "",
    capKey: "",
    gmEmail: "",
    gmPass: "",
  };

  function captureDraftInputs() {
    const orEl = shadow.getElementById("aa-or-key");
    if (orEl && orEl.value) draftInputs.orKey = orEl.value;
    const capEl = shadow.getElementById("aa-cap-key");
    if (capEl && capEl.value) draftInputs.capKey = capEl.value;
    const gmEm = shadow.getElementById("aa-gm-email");
    if (gmEm && gmEm.value) draftInputs.gmEmail = gmEm.value;
    const gmPw = shadow.getElementById("aa-gm-pass");
    if (gmPw && gmPw.value) draftInputs.gmPass = gmPw.value;
    const chatEl = shadow.getElementById("aa-chat-input");
    if (chatEl) draftChatInput = chatEl.value;
    const msgBox = shadow.getElementById("aa-chat-messages");
    if (msgBox) {
      const distFromBottom = msgBox.scrollHeight - msgBox.scrollTop - msgBox.clientHeight;
      chatPinnedToBottom = distFromBottom <= 36;
      savedChatScrollTop = msgBox.scrollTop;
    }
    const bodyBox = shadow.querySelector(".aa-body");
    if (bodyBox && activeTab !== "chat") {
      savedBodyScrollTop = bodyBox.scrollTop;
    }
  }

  function computeStateSignature(data) {
    try {
      const onb = (data && data.onboarding) || {};
      const hc = (data && data.hermes_chat) || {};
      const sessions = Array.isArray(hc.sessions) ? hc.sessions : [];
      const activeId = hc.active_session_id || "";
      const activeSess = sessions.find((s) => s && s.id === activeId) || sessions[0] || {};
      const msgs = Array.isArray(activeSess.messages) ? activeSess.messages : [];
      const lastMsg = msgs.length > 0 ? msgs[msgs.length - 1] : null;
      return JSON.stringify({
        href: window.location.href,
        ai: onb.ai_config,
        cg: onb.chatgpt_config,
        gm: onb.gmail_config,
        tl: onb.teal_config,
        li: onb.linkedin_config,
        jb: onb.job_boards_config,
        pvCount: Array.isArray(data && data.password_vault) ? data.password_vault.length : 0,
        activeId,
        msgCount: msgs.length,
        lastMsgId: lastMsg ? lastMsg.id || lastMsg.content : "",
      });
    } catch (_) {
      return String(Date.now());
    }
  }

  function refreshState(forceRender = false) {
    const handleResp = (resp) => {
      maybeAutoFillCodexDeviceCode();
      maybeResumePendingAgentAction();
      checkAndTriggerPendingPasswordCountdown();
      if (
        !forceRender &&
        (isExtMicRecording ||
          isExtMicTranscribing ||
          (shadow.activeElement && ["INPUT", "TEXTAREA"].includes(shadow.activeElement.tagName)))
      ) {
        if (resp && resp.ok && resp.data) {
          bridgeState = resp.data;
          maybeAutofillSavedSiteLogin();
        }
        return;
      }
      if (resp && resp.ok && resp.data) {
        bridgeState = resp.data;
        maybeAutoFillCodexDeviceCode();
        maybeAutofillSavedSiteLogin();
        checkAndTriggerPendingPasswordCountdown();
        const onb = bridgeState.onboarding || {};
        const li = onb.linkedin_config || {};
        const tl = onb.teal_config || {};

        if (
          !autoResetLinkedInDone &&
          li.session_connected &&
          window.location.hostname.includes("linkedin.com") &&
          isUnauthenticatedAuthPage()
        ) {
          autoResetLinkedInDone = true;
          autoConfirmedLinkedInDone = false;
          sendBridgeAction("configure_teal_linkedin", { linkedin_connected: false });
          return;
        }

        if (!autoConfirmedLinkedInDone && !li.session_connected && isAuthenticatedLinkedInPage()) {
          autoConfirmedLinkedInDone = true;
          autoResetLinkedInDone = false;
          sendBridgeAction("configure_teal_linkedin", {
            linkedin_connected: true,
            skip_remote_validation: true,
          });
          return;
        }

        if (!autoConfirmedTealDone && !tl.session_connected && isAuthenticatedTealPage()) {
          autoConfirmedTealDone = true;
          sendBridgeAction("configure_teal_linkedin", {
            teal_connected: true,
            skip_remote_validation: true,
          });
          return;
        }

        const newSig = computeStateSignature(bridgeState);
        if (!forceRender && newSig === lastRenderedStateSig) {
          return;
        }
        lastRenderedStateSig = newSig;
        render();
      } else if (resp && resp.cached) {
        bridgeState = resp.cached;
        const newSig = computeStateSignature(bridgeState);
        if (!forceRender && newSig === lastRenderedStateSig) {
          return;
        }
        lastRenderedStateSig = newSig;
        render();
      }
    };

    const fallbackFetchState = () => {
      fetch("http://127.0.0.1:19299/api/companion/state")
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (data) handleResp({ ok: true, data });
        })
        .catch(() => {});
    };

    try {
      if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.sendMessage) {
        chrome.runtime.sendMessage({ type: "COMPANION_GET_STATE" }, (resp) => {
          if (resp && (resp.ok || resp.cached)) {
            handleResp(resp);
          } else {
            fallbackFetchState();
          }
        });
      } else {
        fallbackFetchState();
      }
    } catch (_) {
      fallbackFetchState();
    }
  }

  function buildExpandedBodyHTML(itemId, ctx, onb, detected) {
    const ai = (onb && onb.ai_config) || {};
    const cg = (onb && onb.chatgpt_config) || {};
    const gm = (onb && onb.gmail_config) || {};
    const tl = (onb && onb.teal_config) || {};
    const li = (onb && onb.linkedin_config) || {};

    if (itemId === "openrouter") {
      const val = draftInputs.orKey || detected.openrouterKey || (ai.openrouter_key_configured ? "••••••••••••••••" : "");
      return `
        <p class="aa-desc">Create an API key on OpenRouter and save it below.</p>
        <input id="aa-or-key" class="aa-input" type="password" autocomplete="off" placeholder="OpenRouter API Key (sk-or-v1-...)" value="${val}" />
        <button id="aa-or-save" class="aa-btn green">Save OpenRouter Key</button>
        ${ctx !== "openrouter" ? `<button class="aa-btn secondary" data-nav-url="https://openrouter.ai/settings/keys">Open OpenRouter Keys →</button>` : ""}
      `;
    }

    if (itemId === "chatgpt") {
      const pendingCode = cg.pending_user_code || "";
      const onCodexDevicePage = (window.location.href || "").toLowerCase().includes("auth.openai.com/codex/device");
      return `
        <p class="aa-desc">Sign in with your ChatGPT account.</p>
        ${
          pendingCode
            ? `<div class="aa-summary-box"><div>Device Code: <strong style="color:#fff;letter-spacing:0.06em;">${escapeHtml(pendingCode)}</strong></div><div>AutoApply types this code automatically on OpenAI's device page.</div></div>`
            : ""
        }
        <button id="aa-cg-start-oauth" class="aa-btn green">${
          cg.connected
            ? "Connected — Re-Authorize Codex OAuth"
            : onCodexDevicePage
              ? "Generate & Auto-Fill Device Code"
              : "Sign in with ChatGPT (Codex OAuth) →"
        }</button>
      `;
    }

    if (itemId === "capsolver") {
      const val = draftInputs.capKey || detected.capsolverKey || (ai.capsolver_key_configured ? "••••••••••••••••" : "");
      return `
        <p class="aa-desc">Optional (Recommended) — add your CapSolver key for automatic captcha solving.</p>
        <input id="aa-cap-key" class="aa-input" type="password" autocomplete="off" placeholder="CapSolver Key (CAP-...)" value="${val}" />
        <button id="aa-cap-save" class="aa-btn green">Save CapSolver Key</button>
        ${ctx !== "capsolver" ? `<button class="aa-btn secondary" data-nav-url="https://dashboard.capsolver.com/passport/login">Open CapSolver Dashboard →</button>` : ""}
      `;
    }

    if (itemId === "gmail_app_password") {
      const emailVal = draftInputs.gmEmail || detectGoogleEmailOnPage() || gm.account_email || "";
      const passVal = draftInputs.gmPass || detected.gmailAppPassword || (gm.connected ? "••••••••••••••••" : "");
      const onAppPwPage = (window.location.href || "").toLowerCase().includes("myaccount.google.com/apppasswords");
      return `
        <p class="aa-desc">${
          onAppPwPage
            ? "AutoApply automatically types 'AutoApply', clicks Create, and captures your 16-character password."
            : "Open Google App Passwords to automatically generate & capture your 'AutoApply' password."
        }</p>
        <input id="aa-gm-email" class="aa-input" type="email" placeholder="yourname@gmail.com" value="${emailVal}" />
        <input id="aa-gm-pass" class="aa-input" type="password" autocomplete="off" placeholder="App Password (•••• •••• •••• ••••)" value="${passVal}" />
        <button id="aa-gm-save" class="aa-btn green">${gm.connected ? "Update Gmail Password" : "Save Gmail Password"}</button>
        ${
          onAppPwPage
            ? `<button id="aa-gm-autogen" class="aa-btn secondary">Auto-Generate 'AutoApply' Password</button>`
            : `<button class="aa-btn secondary" data-nav-url="https://myaccount.google.com/apppasswords">Open Google App Passwords →</button>`
        }
      `;
    }

    if (itemId === "teal") {
      return `
        <p class="aa-desc">Optional — automatically syncs jobs you apply to into your Teal tracker.</p>
        ${
          ctx === "teal"
            ? `<button id="aa-teal-validate" class="aa-btn green">${tl.session_connected ? "Teal Connected" : "Confirm Teal Sign-In"}</button>`
            : `<button class="aa-btn secondary" data-nav-url="https://app.tealhq.com/">Open Teal →</button>`
        }
      `;
    }

    if (itemId === "linkedin") {
      const onLoginOrJoin = window.location.hostname.includes("linkedin.com") && isUnauthenticatedAuthPage();
      const liConnected = !!li.session_connected && !onLoginOrJoin;
      return `
        <p class="aa-desc">Sign in to LinkedIn in this browser to enable 1-click Easy Apply and job feed automation.</p>
        ${
          ctx === "linkedin" || window.location.hostname.includes("linkedin.com")
            ? `<button id="aa-li-validate" class="aa-btn green">${liConnected ? "LinkedIn Connected" : "Confirm LinkedIn Sign-In"}</button>`
            : `<button class="aa-btn secondary" data-nav-url="https://www.linkedin.com/login">Open LinkedIn →</button>`
        }
      `;
    }

    return "";
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function resolveCurrentJobDocumentsPreview(meta) {
    const curCompanyLower = String((meta && meta.company_name) || "").trim().toLowerCase();
    const summaryCompanyLower = String((lastPrefillSummary && lastPrefillSummary.company) || "").trim().toLowerCase();
    if (
      lastPrefillSummary &&
      (!curCompanyLower || !summaryCompanyLower || curCompanyLower === summaryCompanyLower) &&
      (lastPrefillSummary.resumePreviewUrl || lastPrefillSummary.coverPreviewUrl)
    ) {
      return {
        resumeFilename: lastPrefillSummary.resumeFilename || "Resume.pdf",
        resumePreviewUrl:
          lastPrefillSummary.resumePreviewUrl ||
          `http://127.0.0.1:19299/documents/${encodeURIComponent(lastPrefillSummary.resumeFilename || "Resume.pdf")}`,
        resumePageCount: lastPrefillSummary.resumePageCount || 2,
        coverFilename: lastPrefillSummary.coverFilename || "Cover-Letter.pdf",
        coverPreviewUrl:
          lastPrefillSummary.coverPreviewUrl ||
          `http://127.0.0.1:19299/documents/${encodeURIComponent(lastPrefillSummary.coverFilename || "Cover-Letter.pdf")}`,
        coverPageCount: lastPrefillSummary.coverPageCount || 1,
        jevModel: lastPrefillSummary.jevModel || "~typesafe/jev-latest",
      };
    }
    const docsList = (bridgeState && Array.isArray(bridgeState.documents) && bridgeState.documents) || [];
    const jobsList = (bridgeState && Array.isArray(bridgeState.jobs) && bridgeState.jobs) || [];
    const curUrl = (meta && meta.canonical_url) || window.location.href || "";
    const matchedJob = jobsList.find(
      (j) =>
        (j.canonical_url && curUrl && j.canonical_url.split("?")[0] === curUrl.split("?")[0]) ||
        (meta &&
          meta.company_name &&
          j.company_name &&
          j.company_name.toLowerCase() === meta.company_name.toLowerCase())
    );
    const matchedDoc =
      (matchedJob && docsList.find((d) => d.job_id === matchedJob.job_id)) ||
      (meta &&
        meta.company_name &&
        docsList.find(
          (d) => d.company_name && d.company_name.toLowerCase() === meta.company_name.toLowerCase()
        )) ||
      null;
    if (!matchedDoc) return null;
    const resName = (matchedDoc.pdf_path || "").split("/").pop() || "";
    const clName = (matchedDoc.cover_letter_pdf_path || "").split("/").pop() || "";
    if (!resName && !clName) return null;
    return {
      resumeFilename: resName,
      resumePreviewUrl: resName ? `http://127.0.0.1:19299/documents/${encodeURIComponent(resName)}` : "",
      resumePageCount: matchedDoc.page_count || 2,
      coverFilename: clName,
      coverPreviewUrl: clName ? `http://127.0.0.1:19299/documents/${encodeURIComponent(clName)}` : "",
      coverPageCount: matchedDoc.cover_letter_page_count || 1,
      jevModel: (matchedDoc.jev_verification && matchedDoc.jev_verification.model) || "~typesafe/jev-latest",
    };
  }

  function formatCleanIssueSummary(rawReason) {
    const r = String(rawReason || "").trim();
    if (!r) return "";
    if (/could not be opened or detected|no interactive form fields/i.test(r)) {
      return "Open the job's application modal or external portal first, then click Prefill Form.";
    }
    return r;
  }

  function buildNonJobPageCoPilotHTML(jobParams) {
    const matchedBoard = jobParams && jobParams.matchedBoard;
    const isAuthPage = Boolean(jobParams && jobParams.isAuthPage);
    const catalog = getResolvedJobBoardsCatalog().filter((b) => !b.excluded);
    const opCount = catalog.filter((b) => b.operational).length;
    const primaryCount = catalog.filter((b) => b.is_primary).length;
    const atsCount = catalog.filter((b) => !b.is_primary).length;

    const filteredBoards = catalog.filter((b) => {
      if (selectedBoardsFilter === "operational") return b.operational;
      if (selectedBoardsFilter === "primary") return b.is_primary;
      if (selectedBoardsFilter === "ats") return !b.is_primary;
      return true;
    });

    let topCardHTML = "";
    if (matchedBoard) {
      const shortBoardName = String(matchedBoard.name || "").split(" (")[0].trim() || matchedBoard.name;
      const rightPillText = isAuthPage
        ? "Sign-In Page"
        : matchedBoard.excluded
          ? "Excluded"
          : matchedBoard.operational
            ? "● Operational"
            : "○ Needs Setup";
      const rightPillStyle = isAuthPage || !matchedBoard.operational
        ? "color:#fbbf24;background:rgba(245,158,11,0.14);border-color:rgba(245,158,11,0.32);"
        : "color:#34d399;background:rgba(16,185,129,0.14);border-color:rgba(16,185,129,0.32);";

      const headingText = isAuthPage
        ? `Sign in to ${matchedBoard.name}`
        : `No Job Open on ${shortBoardName}`;
      const subText = isAuthPage
        ? matchedBoard.attention_reason ||
          `Sign in to your ${matchedBoard.name} account on the left. Once signed in, open any job listing to prefill or auto-apply.`
        : `No job posting or job feed is open on this page (${matchedBoard.domain}). Open any job listing to activate Co-Pilot resume tailoring, form prefill, and auto-apply.`;

      const primaryBtnHTML =
        isAuthPage || !matchedBoard.operational
          ? `<button class="aa-btn green" data-toggle-board-id="${escapeHtml(matchedBoard.id)}" data-toggle-board-op="true" style="padding:8px 10px;font-size:11.5px;">✓ Confirm ${escapeHtml(shortBoardName)} Connected</button>`
          : `<button class="aa-btn" data-nav-url="${escapeHtml(matchedBoard.url)}" style="padding:8px 10px;font-size:11.5px;">Search Jobs on ${escapeHtml(shortBoardName)} →</button>`;

      const secondaryLeftBtnHTML =
        isAuthPage || !matchedBoard.operational
          ? `<button class="aa-btn secondary" data-nav-url="${escapeHtml(matchedBoard.url)}" style="padding:7px 9px;font-size:11px;">Open Jobs Feed →</button>`
          : matchedBoard.auth_url
            ? `<button class="aa-btn secondary" data-nav-url="${escapeHtml(matchedBoard.auth_url)}" style="padding:7px 9px;font-size:11px;">Account / Sign In →</button>`
            : `<button class="aa-btn secondary" data-toggle-board-id="${escapeHtml(matchedBoard.id)}" data-toggle-board-op="false" style="padding:7px 9px;font-size:11px;">Mark Needs Setup</button>`;

      topCardHTML = `
        <div class="aa-copilot-card">
          <div class="aa-card-top-row">
            <span class="aa-job-badge">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
              <span>${escapeHtml(matchedBoard.name)}</span>
            </span>
            <span class="aa-meta-pill" style="${rightPillStyle}">${escapeHtml(rightPillText)}</span>
          </div>

          <div>
            <div class="aa-job-title">${escapeHtml(headingText)}</div>
            <div class="aa-job-company" style="margin-top:4px;line-height:1.45;">${escapeHtml(subText)}</div>
          </div>

          ${primaryBtnHTML}

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
            ${secondaryLeftBtnHTML}
            <button id="aa-open-chat-tab" class="aa-btn secondary" style="padding:7px 9px;font-size:11px;">Ask Chat →</button>
          </div>
        </div>
      `;
    } else {
      topCardHTML = `
        <div class="aa-copilot-card">
          <div class="aa-card-top-row">
            <span class="aa-job-badge">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
              <span>AutoApply Co-Pilot</span>
            </span>
            <span class="aa-meta-pill">No Job on Page</span>
          </div>

          <div>
            <div class="aa-job-title">No Job Posting on This Page</div>
            <div class="aa-job-company" style="margin-top:4px;line-height:1.45;">Open any job listing or application form to tailor your resume, prefill fields, or auto-apply — or open a job board from your desktop catalog below.</div>
          </div>

          <button id="aa-open-chat-tab" class="aa-btn secondary" style="padding:7px 9px;font-size:11px;">Ask AutoApply Chat →</button>
        </div>
      `;
    }

    const filterBtnStyle = (active) =>
      active
        ? "background:rgba(37,99,235,0.28);border:1px solid rgba(59,130,246,0.55);color:#ffffff;padding:3px 7px;border-radius:6px;font-size:10px;font-weight:600;cursor:pointer;"
        : "background:rgba(15,23,42,0.65);border:1px solid rgba(148,163,184,0.16);color:#94a3b8;padding:3px 7px;border-radius:6px;font-size:10px;font-weight:500;cursor:pointer;";

    return `
      ${topCardHTML}

      <div class="aa-feed-section">
        <div class="aa-section-header">
          <span>Desktop Job Boards</span>
          <span>${opCount}/${catalog.length} Operational</span>
        </div>
        <div style="display:flex;gap:4px;flex-wrap:wrap;">
          <button data-board-filter="all" style="${filterBtnStyle(selectedBoardsFilter === "all")}">All (${catalog.length})</button>
          <button data-board-filter="operational" style="${filterBtnStyle(selectedBoardsFilter === "operational")}">Operational (${opCount})</button>
          <button data-board-filter="primary" style="${filterBtnStyle(selectedBoardsFilter === "primary")}">Boards (${primaryCount})</button>
          <button data-board-filter="ats" style="${filterBtnStyle(selectedBoardsFilter === "ats")}">ATS (${atsCount})</button>
        </div>
        <div class="aa-feed-list">
          ${filteredBoards
            .map((b) => {
              const isCurrentBoard = Boolean(matchedBoard && matchedBoard.id === b.id);
              const targetNavUrl = b.operational || !b.requires_auth ? b.url : b.auth_url || b.url;
              const statusDot = b.operational
                ? `<span style="color:#34d399;font-weight:700;">●</span>`
                : `<span style="color:#fbbf24;font-weight:700;">○</span>`;
              return `
                <div class="aa-feed-item ${isCurrentBoard ? "selected" : ""}" data-nav-url="${escapeHtml(targetNavUrl)}" style="padding:8px 10px;">
                  <div class="aa-feed-item-info">
                    <div class="aa-feed-item-title">${statusDot} ${escapeHtml(b.name)}</div>
                    <div class="aa-feed-item-sub">${escapeHtml(b.domain)} • ${b.is_primary ? "Job Board" : "Direct ATS"} • ${b.operational ? "Operational" : "Setup"}</div>
                  </div>
                  <span class="aa-feed-item-badge">${b.operational || !b.requires_auth ? "Jobs →" : "Sign In →"}</span>
                </div>
              `;
            })
            .join("")}
        </div>
      </div>
    `;
  }

  function buildJobCoPilotCardHTML(jobParams, items) {
    if (!jobParams || !jobParams.isJobPage) {
      return buildNonJobPageCoPilotHTML(jobParams);
    }
    const meta = extractJobMetadataFromPage();
    const feedCards = extractJobCardsFromFeed();
    const specificOpen = isSpecificJobDetailOpen();
    const openModal = findOpenEasyApplyModal();
    const formCount = extractApplicationFormSchema().length;
    const isFeedMode = !specificOpen && feedCards.length > 0;
    const docPreview = resolveCurrentJobDocumentsPreview(meta);
    const manualEditCount = Object.keys(manualFieldEdits).length;

    const livePageProblem =
      jobParams && jobParams.isJobPage && formCount === 0 && !openModal
        ? detectApplicationPageProblem()
        : null;
    if (livePageProblem) {
      recordApplicationProblemNote(meta, livePageProblem.reason, livePageProblem.kind);
    }

    const jobsList = (bridgeState && Array.isArray(bridgeState.jobs) && bridgeState.jobs) || [];
    const curUrl = (meta && meta.canonical_url) || window.location.href || "";
    const matchedJob = jobsList.find(
      (j) =>
        (j.canonical_url && curUrl && j.canonical_url.split("?")[0] === curUrl.split("?")[0]) ||
        (meta &&
          meta.company_name &&
          j.company_name &&
          j.company_name.toLowerCase() === meta.company_name.toLowerCase() &&
          (!meta.title || !j.title || j.title.toLowerCase() === meta.title.toLowerCase()))
    );
    let candidateIssue =
      livePageProblem ||
      currentApplicationIssue ||
      (matchedJob && matchedJob.application_issue && matchedJob.application_issue.reason
        ? matchedJob.application_issue
        : null);

    // Never show a stale "no_form_fields" issue if an Easy Apply modal or Apply button is now present on the page, or if browsing the feed
    if (
      candidateIssue &&
      (openModal ||
        formCount > 0 ||
        (candidateIssue.kind === "no_form_fields" && (isFeedMode || Boolean(findJobDetailApplyButton()))))
    ) {
      candidateIssue = null;
    }

    const activeIssue = candidateIssue;

    const statusRightLabel = activeIssue
      ? "Needs Attention"
      : openModal
        ? `Form Open (${formCount || 1} fields)`
        : formCount > 0
          ? `${formCount} field${formCount === 1 ? "" : "s"}`
          : isFeedMode
            ? `${feedCards.length} jobs`
            : specificOpen
              ? "Job Open"
              : "Ready";

    function estimateClientMatchPct(cardTitle, cardCompany, cardLocation) {
      const t = String(cardTitle || "").toLowerCase();
      if (!t || t === "no job posting on this page") return 0;
      const matched = jobsList.find(
        (j) =>
          (cardCompany &&
            j.company_name &&
            j.company_name.toLowerCase() === String(cardCompany).toLowerCase() &&
            (!j.title || j.title.toLowerCase() === t)) ||
          (j.title && j.title.toLowerCase() === t && (!cardCompany || !j.company_name))
      );
      if (matched && Number(matched.match_score_pct) > 0) {
        return Number(matched.match_score_pct);
      }
      const kbHdr = (bridgeState && bridgeState.knowledge_base && bridgeState.knowledge_base.profile_header) || {};
      const prefs = (bridgeState && bridgeState.onboarding && bridgeState.onboarding.preferences) || {};
      const targetBlob = `${kbHdr.headline || ""} ${(prefs.desired_titles || []).join(" ")}`.toLowerCase();
      let score = 56;
      if (/product\s+manager|product\s+owner|менеджер\s+продукта|группы\s+продуктов/i.test(t)) {
        score = /product/i.test(targetBlob) ? 84 : 72;
      } else if (/workflow\s+automation|ai\s+automation|cx\s+automation|ai\s+delivery/i.test(t)) {
        score = /automation|ai/i.test(targetBlob) ? 85 : 70;
      } else if (/project\s+manager|program\s+manager|delivery\s+lead|руководитель\s+(ит-)?проектов|scrum\s+master/i.test(t)) {
        score = 80;
      } else if (/solutions\s+(engineer|architect|consultant)|customer\s+success\s+engineer|implementation/i.test(t)) {
        score = 74;
      } else if (/customer\s+success\s+manager|account\s+manager|business\s+analyst/i.test(t)) {
        score = 62;
      } else if (/designer|дизайнер|sales|sdr|bdr|accounting|controller|customer\s+(care|support)|support\s+agent|game\s+designer/i.test(t)) {
        score = 38;
      }
      if (/\b(ai|llm|genai|agentic|automation|platform|saas|b2b)\b/i.test(t) && !/support\s+agent/i.test(t)) {
        score += 5;
      }
      if (/director|vp\b|chief/i.test(t)) score -= 6;
      if (/onsite|on-site|w2\s+only/i.test(`${t} ${cardLocation || ""}`)) score -= 18;
      return Math.max(22, Math.min(94, Math.round(score)));
    }

    function renderMatchBadgeHTML(pct, isJev) {
      const n = Number(pct || 0);
      if (!n || n <= 0) return "";
      const color = n >= 80 ? "#34d399" : n >= 65 ? "#60a5fa" : n >= 50 ? "#fbbf24" : "#94a3b8";
      const bg =
        n >= 80
          ? "rgba(16,185,129,0.16)"
          : n >= 65
            ? "rgba(59,130,246,0.16)"
            : n >= 50
              ? "rgba(245,158,11,0.16)"
              : "rgba(148,163,184,0.14)";
      const border =
        n >= 80
          ? "rgba(52,211,153,0.34)"
          : n >= 65
            ? "rgba(96,165,250,0.34)"
            : n >= 50
              ? "rgba(251,191,36,0.34)"
              : "rgba(148,163,184,0.26)";
      return `<span class="aa-match-pill" title="${n}% Profile Match${isJev ? " (JEV Calibrated)" : ""}" style="display:inline-flex;align-items:center;gap:3px;padding:2px 7px;border-radius:999px;font-size:10.5px;font-weight:700;color:${color};background:${bg};border:1px solid ${border};white-space:nowrap;">${isJev ? "✦ " : ""}${n}%</span>`;
    }

    const activeMatchPct =
      (matchedJob && Number(matchedJob.match_score_pct) > 0 && Number(matchedJob.match_score_pct)) ||
      estimateClientMatchPct(meta && meta.title, meta && meta.company_name, meta && meta.location);
    const activeMatchJev = Boolean(matchedJob && matchedJob.match_jev_verified);

    const feedListHTML =
      feedCards.length > 0
        ? `
      <div class="aa-feed-section">
        <div class="aa-section-header">
          <span>${isFeedMode ? "Select Job" : "Jobs on Page"}</span>
          <span>${feedCards.length}</span>
        </div>
        <div class="aa-feed-list">
          ${feedCards
            .slice(0, 5)
            .map((card, idx) => {
              const isSel = idx === Math.min(Math.max(0, selectedFeedJobIndex), feedCards.length - 1);
              const cardPct = estimateClientMatchPct(card.title, card.company_name, card.location);
              return `
                <button class="aa-feed-item ${isSel ? "selected" : ""}" data-feed-idx="${idx}">
                  <div class="aa-feed-item-info" style="flex:1;min-width:0;">
                    <div style="display:flex;align-items:center;justify-content:space-between;gap:6px;">
                      <div class="aa-feed-item-title" style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(card.title)}</div>
                      ${renderMatchBadgeHTML(cardPct, false)}
                    </div>
                    <div class="aa-feed-item-sub">${escapeHtml(card.company_name)} • ${escapeHtml(card.location)}</div>
                  </div>
                </button>
              `;
            })
            .join("")}
        </div>
      </div>
    `
        : "";

    const isPrefillBusy = isBusyWorking && activeWorkingMode === "prefill";
    const isApplyBusy = isBusyWorking && activeWorkingMode === "apply";

    const cleanReasonText = activeIssue && activeIssue.reason ? formatCleanIssueSummary(activeIssue.reason) : "";
    const issueNoteHTML = cleanReasonText
      ? `
          <div class="aa-issue-note-box">
            <div class="aa-issue-note-header">
              <span class="aa-issue-note-title">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                <span>Needs Attention</span>
              </span>
              <span class="aa-issue-note-actions">
                <span class="aa-issue-note-badge">Saved to Notes</span>
                <button id="aa-dismiss-issue-btn" class="aa-issue-dismiss-btn" title="Dismiss notice">×</button>
              </span>
            </div>
            <div class="aa-issue-note-body">${escapeHtml(cleanReasonText)}</div>
          </div>
        `
      : "";

    const pdfPreviewSectionHTML = docPreview
      ? `
        <div class="aa-pdf-preview-grid">
          ${
            docPreview.resumePreviewUrl
              ? `
            <button class="aa-pdf-preview-btn" data-preview-pdf-url="${escapeHtml(docPreview.resumePreviewUrl)}" title="${escapeHtml(docPreview.resumeFilename)} — Open PDF">
              <span>📄 Resume (${docPreview.resumePageCount}p)</span>
              <span style="color:#38bdf8;">↗</span>
            </button>
          `
              : ""
          }
          ${
            docPreview.coverPreviewUrl
              ? `
            <button class="aa-pdf-preview-btn" data-preview-pdf-url="${escapeHtml(docPreview.coverPreviewUrl)}" title="${escapeHtml(docPreview.coverFilename)} — Open PDF">
              <span>✉️ Cover Letter (${docPreview.coverPageCount}p)</span>
              <span style="color:#38bdf8;">↗</span>
            </button>
          `
              : ""
          }
        </div>
      `
      : "";

    const kbUpdateHTML = buildKbUpdateBoxHTML();

    return `
      <div class="aa-copilot-card">
        <div class="aa-card-top-row">
          <span class="aa-job-badge">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            <span>${escapeHtml(jobParams.platform || "Job Co-Pilot")}</span>
          </span>
          <span style="display:inline-flex;align-items:center;gap:5px;">
            ${renderMatchBadgeHTML(activeMatchPct, activeMatchJev)}
            <span class="aa-meta-pill">${escapeHtml(statusRightLabel)}</span>
          </span>
        </div>

        <div>
          <div class="aa-job-title">${escapeHtml(meta.title)}</div>
          <div class="aa-job-company"><strong>${escapeHtml(meta.company_name)}</strong> • ${escapeHtml(meta.location)}</div>
        </div>

        ${issueNoteHTML}

        <div class="aa-action-row">
          <button id="aa-btn-prefill" class="aa-btn-prefill ${isPrefillBusy ? "working" : ""}" ${isBusyWorking ? "disabled" : ""}>
            ${
              isPrefillBusy
                ? `<span class="aa-btn-spinner"></span><span class="aa-btn-label">${escapeHtml(busyButtonLabel || "Filling Form…")}</span>`
                : `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg><span class="aa-btn-label">Prefill Form</span>`
            }
          </button>
          <button id="aa-btn-apply" class="aa-btn-apply ${isApplyBusy ? "working" : ""}" ${isBusyWorking ? "disabled" : ""}>
            ${
              isApplyBusy
                ? `<span class="aa-btn-spinner"></span><span class="aa-btn-label">${escapeHtml(busyButtonLabel || "Applying…")}</span>`
                : `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg><span class="aa-btn-label">Auto-Apply</span>`
            }
          </button>
        </div>

        <div id="aa-kb-update-slot">${kbUpdateHTML}</div>

        ${
          isBusyWorking
            ? `<div class="aa-summary-box"><div id="aa-live-agent-status">${escapeHtml(busyLabel || "Working…")}</div></div>`
            : lastPrefillSummary &&
                !lastPrefillSummary.docsOnly &&
                (!meta.company_name ||
                  !lastPrefillSummary.company ||
                  String(lastPrefillSummary.company).toLowerCase() === String(meta.company_name).toLowerCase())
              ? `
            <div class="aa-summary-box">
              <div><strong>${lastPrefillSummary.submitted ? "Submitted:" : "Filled:"}</strong> ${lastPrefillSummary.fieldsFilled} field(s) • ${lastPrefillSummary.filesUploaded} PDF(s)</div>
              ${
                lastPrefillSummary.siteRegistered
                  ? `<div style="margin-top:3px;color:#93c5fd;font-size:10.5px;">🔐 Saved login to Password Manager</div>`
                  : ""
              }
            </div>
          `
              : ""
        }

        ${pdfPreviewSectionHTML}

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
          <button id="aa-job-import" class="aa-btn secondary" style="padding:7px 9px;font-size:11px;">+ Save to Tracker</button>
          <button id="aa-open-chat-tab" class="aa-btn secondary" style="padding:7px 9px;font-size:11px;">Ask Chat →</button>
        </div>
      </div>

      ${feedListHTML}
    `;
  }

  function buildSetupTabHTML(items, ctx, onb, detected) {
    const connectedCount = items.filter((i) => i.valid).length;
    const pct = Math.round((connectedCount / Math.max(1, items.length)) * 100);

    return `
      <div class="aa-setup-summary">
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <span style="font-size:12px;font-weight:600;color:#f8fafc;">Integration Connections</span>
          <span style="font-size:11px;font-weight:600;color:#34d399;">${connectedCount} of ${items.length} Connected</span>
        </div>
        <div class="aa-progress-track">
          <div class="aa-progress-fill" style="width:${pct}%;"></div>
        </div>
      </div>

      <div class="aa-accordion">
        ${items
          .map((item) => {
            const isExp = expandedItemId === item.id;
            return `
              <div class="aa-acc-item ${isExp ? "expanded" : ""}">
                <button class="aa-acc-header" data-acc-id="${item.id}">
                  <div class="aa-check-left">
                    <div class="aa-check-name">${escapeHtml(item.name)}</div>
                    <div class="aa-check-status ${item.valid ? "valid" : ""}">${item.valid ? "● " : "○ "}${escapeHtml(item.status)}</div>
                  </div>
                  <span class="aa-chevron">${isExp ? "▴" : "▾"}</span>
                </button>
                ${
                  isExp
                    ? `<div class="aa-acc-content">${buildExpandedBodyHTML(item.id, ctx, onb, detected)}</div>`
                    : ""
                }
              </div>
            `;
          })
          .join("")}
      </div>
    `;
  }

  function isMarkdownTableSeparator(line) {
    const t = String(line || "").trim();
    if (!t.includes("|") || !t.includes("-")) return false;
    const stripped = t.replace(/[|\s:-]/g, "");
    return stripped.length === 0;
  }

  function parseMarkdownTableCells(line) {
    let t = String(line || "").trim();
    if (t.startsWith("|")) t = t.slice(1);
    if (t.endsWith("|")) t = t.slice(0, -1);
    return t.split("|").map((c) => c.trim());
  }

  function renderMarkdownHTML(raw) {
    const clean = String(raw || "")
      .replace(/Sandbox Hermes|Hermes Sandbox Agent|Hermes Sandbox|Hermes Agent|Hermes/g, "AutoApply")
      .replace(/\n*-{3}\n#{1,3} Live Sandbox[\s\S]*$/m, "")
      .replace(/VB House Template/g, "Reference Resume Style");
    const lines = clean.split(/\r?\n/);
    const fmtInline = (s) =>
      escapeHtml(s)
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/`([^`]+)`/g, "<code style='background:rgba(255,255,255,0.12);padding:1px 4px;border-radius:4px;font-size:11px;'>$1</code>");

    const htmlParts = [];
    let i = 0;
    while (i < lines.length) {
      const t = lines[i].trim();
      if (t.includes("|") && i + 1 < lines.length && isMarkdownTableSeparator(lines[i + 1])) {
        const headers = parseMarkdownTableCells(t);
        i += 2;
        const rows = [];
        while (i < lines.length) {
          const rLine = lines[i].trim();
          if (!rLine || !rLine.includes("|")) break;
          if (!isMarkdownTableSeparator(rLine)) {
            rows.push(parseMarkdownTableCells(rLine));
          }
          i += 1;
        }
        const thHtml = headers.map((h) => `<th>${fmtInline(h)}</th>`).join("");
        const trsHtml = rows
          .map(
            (r) =>
              `<tr>${headers.map((_, colIdx) => `<td>${fmtInline(r[colIdx] || "")}</td>`).join("")}</tr>`
          )
          .join("");
        htmlParts.push(`<table class="aa-md-table"><thead><tr>${thHtml}</tr></thead><tbody>${trsHtml}</tbody></table>`);
        continue;
      }

      if (!t) {
        htmlParts.push("<div style='height:4px;'></div>");
      } else if (t.startsWith("### ")) {
        htmlParts.push(`<div style="font-weight:600;color:#f8fafc;margin-top:4px;">${fmtInline(t.slice(4))}</div>`);
      } else if (t.startsWith("## ")) {
        htmlParts.push(`<div style="font-weight:600;color:#38bdf8;font-size:12.5px;margin-top:5px;">${fmtInline(t.slice(3))}</div>`);
      } else if (t.startsWith("# ")) {
        htmlParts.push(`<div style="font-weight:600;color:#ffffff;font-size:13px;margin-top:5px;">${fmtInline(t.slice(2))}</div>`);
      } else if (t.startsWith("- ") || t.startsWith("* ") || t.startsWith("• ")) {
        htmlParts.push(`<div style="padding-left:8px;margin-top:2px;"><span style="color:#38bdf8;font-weight:600;">•</span> ${fmtInline(t.slice(2))}</div>`);
      } else {
        htmlParts.push(`<div style="margin-top:2px;">${fmtInline(t)}</div>`);
      }
      i += 1;
    }
    return htmlParts.join("");
  }

  let optimisticChatMessages = [];

  function resolveCompanionChatMessages() {
    const hermesChat = (bridgeState && bridgeState.hermes_chat) || {};
    let baseMessages = [];
    if (Array.isArray(hermesChat.sessions) && hermesChat.sessions.length > 0) {
      const activeId = hermesChat.active_session_id || "";
      const activeSess =
        hermesChat.sessions.find((s) => s && s.id === activeId) || hermesChat.sessions[0];
      if (activeSess && Array.isArray(activeSess.messages)) {
        baseMessages = activeSess.messages;
      }
    } else if (Array.isArray(hermesChat.messages)) {
      baseMessages = hermesChat.messages;
    }

    const combined = baseMessages.slice(-24);
    for (const opt of optimisticChatMessages) {
      const alreadyPresent = combined.some(
        (m) => m && m.role === opt.role && String(m.content || "").trim() === String(opt.content || "").trim()
      );
      if (!alreadyPresent) {
        combined.push(opt);
      }
    }
    if (combined.length > lastChatMsgCount) {
      chatPinnedToBottom = true;
    }
    lastChatMsgCount = combined.length;
    return combined.slice(-24);
  }

  function buildChatTabHTML(jobParams) {
    const isJob = Boolean(jobParams && jobParams.isJobPage);
    const meta = isJob ? extractJobMetadataFromPage() : { title: "", company_name: "" };
    const messages = resolveCompanionChatMessages();

    return `
      <div class="aa-chat-wrap">
        <div class="aa-chat-chips">
          ${
            isJob
              ? `
                <button class="aa-chip" data-chip-prompt="Why am I a strong fit for ${escapeHtml(meta.title || "this role")} at ${escapeHtml(meta.company_name || "this company")}?">Fit Analysis</button>
                <button class="aa-chip" data-chip-prompt="Draft a concise outreach note to the hiring manager for ${escapeHtml(meta.title || "this role")}.">Hiring Manager Note</button>
                <button class="aa-chip" data-chip-action="prefill">Prefill Form</button>
              `
              : `
                <button class="aa-chip" data-chip-prompt="Summarize my top product management achievements from my Knowledge Base.">Resume Highlights</button>
                <button class="aa-chip" data-chip-prompt="Which configured job boards in my AutoApply catalog are best for remote roles?">Best Job Boards</button>
              `
          }
        </div>

        <div id="aa-chat-messages" class="aa-chat-messages">
          ${
            messages.length === 0
              ? isJob && meta.title && meta.company_name
                ? `<div class="aa-msg assistant">Ask anything about <strong>${escapeHtml(meta.title)}</strong> at <strong>${escapeHtml(meta.company_name)}</strong>, or tell me how you want your application tailored.</div>`
                : `<div class="aa-msg assistant">Ask AutoApply AI anything about your resume, knowledge base, or job search.</div>`
              : messages
                  .map(
                    (m) => `
                <div class="aa-msg ${m.role === "user" ? "user" : "assistant"}">${
                  m.role === "user" ? escapeHtml(m.content || "") : renderMarkdownHTML(m.content || "")
                }</div>
              `
                  )
                  .join("")
          }
          ${
            isBusyWorking
              ? `<div class="aa-msg assistant"><div class="aa-typing-row"><span class="aa-typing-dots"><span></span><span></span><span></span></span><span>${escapeHtml(busyLabel || "Working on your response…")}</span></div></div>`
              : ""
          }
        </div>

        <div class="aa-chat-composer">
          <textarea id="aa-chat-input" class="aa-chat-textarea" rows="1" placeholder="Message AutoApply AI…">${escapeHtml(draftChatInput)}</textarea>
          ${
            isExtMicRecording
              ? `<span class="aa-mic-rec-pill"><span style="width:6px;height:6px;border-radius:999px;background:#ef4444;display:inline-block;"></span><span id="aa-ext-mic-timer">0:${String(extMicSeconds % 60).padStart(2, "0")}</span></span>`
              : isExtMicTranscribing
                ? `<span class="aa-mic-rec-pill" style="background:rgba(59,130,246,0.14);border-color:rgba(59,130,246,0.35);color:#93c5fd;">Transcribing…</span>`
                : ""
          }
          ${
            isBusyWorking
              ? `<button id="aa-chat-stop" class="aa-btn" style="width:auto;padding:7px 11px;background:#ef4444;border-radius:999px;">Stop</button>`
              : ""
          }
          <button id="aa-chat-mic" class="aa-chat-mic-circle ${isExtMicRecording ? "recording" : ""}" title="${isExtMicRecording ? "Stop voice recording" : "Record voice message"}">
            ${
              isExtMicRecording
                ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><line x1="4" y1="10" x2="4" y2="14"/><line x1="8" y1="6" x2="8" y2="18"/><line x1="12" y1="3" x2="12" y2="21"/><line x1="16" y1="6" x2="16" y2="18"/><line x1="20" y1="10" x2="20" y2="14"/></svg>`
                : `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>`
            }
          </button>
          <button id="aa-chat-send" class="aa-chat-send-circle" title="Send message (Enter)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>
          </button>
        </div>
      </div>
    `;
  }

  async function sendCompanionChatMessage(messageText) {
    const clean = (messageText || "").trim();
    if (!clean) return;
    const lower = clean.toLowerCase();
    if (lower === "prefill" || lower === "prefill form") {
      await runPrefillOrApply("prefill");
      return;
    }
    if (lower === "apply" || lower === "apply now") {
      await runPrefillOrApply("apply");
      return;
    }

    const liveChatEl = shadow.getElementById("aa-chat-input");
    if (liveChatEl) {
      liveChatEl.value = "";
    }
    draftChatInput = "";
    optimisticChatMessages.push({ role: "user", content: clean });
    isBusyWorking = true;
    busyLabel = "Thinking…";
    chatPinnedToBottom = true;
    render();
    const initialMsgBox = shadow.getElementById("aa-chat-messages");
    if (initialMsgBox) initialMsgBox.scrollTop = initialMsgBox.scrollHeight;

    const jobParams = detectJobPageParameters();
    let jobContextPayload = null;
    if (jobParams && jobParams.isJobPage) {
      const meta = extractJobMetadataFromPage();
      const formFields = extractApplicationFormSchema();
      jobContextPayload = {
        canonical_url: meta.canonical_url,
        title: meta.title,
        company_name: meta.company_name,
        location: meta.location,
        description: meta.description,
        form_fields: formFields,
      };
    }
    await sendBridgeAction("send_hermes_chat_message", {
      message: clean,
      ...(jobContextPayload ? { job_context: jobContextPayload } : {}),
    });
    optimisticChatMessages = [];
    isBusyWorking = false;
    busyLabel = "";
    chatPinnedToBottom = true;
    render();
    const msgBox = shadow.getElementById("aa-chat-messages");
    if (msgBox) msgBox.scrollTop = msgBox.scrollHeight;
  }

  function render() {
    captureDraftInputs();
    applyPageMargin();
    const ctx = detectContext(window.location.href);
    const jobParams = detectJobPageParameters();
    const detected = scanPageForSecrets();
    const onb = (bridgeState && bridgeState.onboarding) || {};
    const ai = onb.ai_config || {};
    const cg = onb.chatgpt_config || {};
    const gm = onb.gmail_config || {};
    const tl = onb.teal_config || {};
    const li = onb.linkedin_config || {};
    const onUnauthLinkedIn = window.location.hostname.includes("linkedin.com") && isUnauthenticatedAuthPage();
    const isLiConnected = !!li.session_connected && !onUnauthLinkedIn;

    const items = [
      {
        id: "openrouter",
        name: "1. OpenRouter API Key",
        valid: !!ai.openrouter_key_configured,
        status: ai.openrouter_key_configured ? "Connected" : "Required",
      },
      {
        id: "chatgpt",
        name: "2. ChatGPT Codex OAuth",
        valid: !!cg.connected,
        status: cg.connected ? "Connected" : "Optional",
      },
      {
        id: "capsolver",
        name: "3. CapSolver API Key",
        valid: !!ai.capsolver_key_configured,
        status: ai.capsolver_key_configured ? "Connected" : "Optional (Recommended)",
      },
      {
        id: "gmail_app_password",
        name: "4. Gmail App Password",
        valid: !!gm.connected,
        status: gm.connected ? `Connected (${gm.account_email || "Gmail"})` : "Optional",
      },
      {
        id: "teal",
        name: "5. Teal Job Tracker",
        valid: !!tl.session_connected,
        status: tl.session_connected ? "Connected" : "Optional",
      },
      {
        id: "linkedin",
        name: "6. LinkedIn Session",
        valid: isLiConnected,
        status: isLiConnected ? "Connected" : "Optional",
      },
    ];

    const isSetupConfigured = Boolean(ai.openrouter_key_configured || cg.connected);
    const isSetupProviderPage =
      ["openrouter", "capsolver", "chatgpt", "gmail_app_password", "teal"].includes(ctx) ||
      (ctx === "linkedin" && !jobParams.isJobPage);
    const onPendingSetupProviderPage =
      ["openrouter", "capsolver", "chatgpt", "gmail_app_password", "teal", "linkedin"].includes(ctx) &&
      items.some((i) => i.id === ctx && !i.valid);

    if (!userSelectedTab && bridgeState) {
      if (onPendingSetupProviderPage || isSetupProviderPage) {
        activeTab = "setup";
      } else if (isSetupConfigured || jobParams.isJobPage || ctx === "job_board") {
        activeTab = "copilot";
      } else {
        activeTab = "setup";
      }
    }

    if (!userSelectedAccordion) {
      const ctxItem = items.find((i) => i.id === ctx);
      if (ctxItem && !ctxItem.valid) {
        expandedItemId = ctx;
      } else {
        const curItem = items.find((i) => i.id === expandedItemId);
        if (!curItem || curItem.valid) {
          const firstIncomplete = items.find((i) => !i.valid);
          expandedItemId = firstIncomplete ? firstIncomplete.id : "";
        }
      }
    }

    const logoSvg28 = `
      <svg viewBox="0 0 1024 1024" width="28" height="28" aria-hidden="true">
        <defs>
          <linearGradient id="aaAppGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="rgb(24,58,165)" />
            <stop offset="100%" stop-color="rgb(54,168,240)" />
          </linearGradient>
        </defs>
        <rect width="1024" height="1024" rx="220" fill="url(#aaAppGrad)" />
        <rect x="240" y="290" width="544" height="96" rx="30" fill="#F5F8FF" />
        <rect x="240" y="464" width="544" height="96" rx="30" fill="#F5F8FF" />
        <rect x="240" y="638" width="544" height="96" rx="30" fill="#F5F8FF" />
      </svg>
    `;

    const logoSvg18 = `
      <svg viewBox="0 0 1024 1024" width="18" height="18" style="border-radius:4px;flex-shrink:0;" aria-hidden="true">
        <rect width="1024" height="1024" rx="220" fill="rgb(24,58,165)" />
        <rect x="240" y="290" width="544" height="104" rx="32" fill="#F5F8FF" />
        <rect x="240" y="460" width="544" height="104" rx="32" fill="#F5F8FF" />
        <rect x="240" y="630" width="544" height="104" rx="32" fill="#F5F8FF" />
      </svg>
    `;

    const bodyContent =
      activeTab === "chat"
        ? buildChatTabHTML(jobParams)
        : activeTab === "setup"
          ? buildSetupTabHTML(items, ctx, onb, detected)
          : buildJobCoPilotCardHTML(jobParams, items);

    const hasInlineExpandBtn = syncLinkedInInlineExpandButtons();

    container.innerHTML = `
      <button id="aa-pill-expand" class="aa-pill-toggle ${isCollapsed && !hasInlineExpandBtn ? "visible" : ""}">
        ${logoSvg18}
        <span>AutoApply</span>
      </button>
      <div class="aa-sidebar ${isCollapsed ? "collapsed" : ""}">
        <div class="aa-header">
          <div class="aa-header-top">
            <div class="aa-brand">
              <div class="aa-logo">${logoSvg28}</div>
              <div class="aa-brand-text">
                <div class="aa-title">AutoApply</div>
                <div class="aa-subtitle">Autonomous Job Co-Pilot</div>
              </div>
            </div>
            <button id="aa-btn-collapse" class="aa-collapse-btn" title="Hide Sidebar">Hide</button>
          </div>
          <div class="aa-tabs">
            <button id="aa-tab-copilot" class="aa-tab-btn ${activeTab === "copilot" ? "active" : ""}">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
              <span>Co-Pilot</span>
            </button>
            <button id="aa-tab-chat" class="aa-tab-btn ${activeTab === "chat" ? "active" : ""}">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
              <span>Chat</span>
            </button>
            <button id="aa-tab-setup" class="aa-tab-btn ${activeTab === "setup" ? "active" : ""}">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
              <span>Setup</span>
            </button>
          </div>
        </div>

        <div class="aa-body ${activeTab === "chat" ? "chat-mode" : ""}">
          <div class="aa-banner ${statusBanner.text ? "show" : ""} ${statusBanner.kind === "err" ? "err" : "ok"}">
            ${escapeHtml(statusBanner.text)}
          </div>

          ${bodyContent}
        </div>
      </div>
    `;

    const collapseBtn = shadow.getElementById("aa-btn-collapse");
    if (collapseBtn) {
      collapseBtn.onclick = () => {
        isCollapsed = true;
        render();
      };
    }

    const expandBtn = shadow.getElementById("aa-pill-expand");
    if (expandBtn) {
      expandBtn.onclick = () => {
        isCollapsed = false;
        render();
      };
    }

    const tabCopilot = shadow.getElementById("aa-tab-copilot");
    if (tabCopilot) {
      tabCopilot.onclick = () => {
        userSelectedTab = true;
        activeTab = "copilot";
        render();
      };
    }

    const tabChat = shadow.getElementById("aa-tab-chat");
    if (tabChat) {
      tabChat.onclick = () => {
        userSelectedTab = true;
        activeTab = "chat";
        chatPinnedToBottom = true;
        render();
      };
    }

    const tabSetup = shadow.getElementById("aa-tab-setup");
    if (tabSetup) {
      tabSetup.onclick = () => {
        userSelectedTab = true;
        activeTab = "setup";
        render();
      };
    }

    const openSetupStrip = shadow.getElementById("aa-open-setup-strip");
    if (openSetupStrip) {
      openSetupStrip.onclick = () => {
        userSelectedTab = true;
        activeTab = "setup";
        render();
      };
    }

    const openChatBtn = shadow.getElementById("aa-open-chat-tab");
    if (openChatBtn) {
      openChatBtn.onclick = () => {
        userSelectedTab = true;
        activeTab = "chat";
        chatPinnedToBottom = true;
        render();
      };
    }

    shadow.querySelectorAll("[data-feed-idx]").forEach((cardBtn) => {
      cardBtn.addEventListener("click", () => {
        const idx = parseInt(cardBtn.getAttribute("data-feed-idx") || "0", 10);
        selectedFeedJobIndex = Number.isNaN(idx) ? 0 : idx;
        currentApplicationIssue = null;
        lastPrefillSummary = null;
        statusBanner = { text: "", kind: "" };
        const feedCards = extractJobCardsFromFeed();
        const chosen = feedCards[selectedFeedJobIndex];
        if (chosen && chosen.element) {
          highlightPageElement(chosen.element, "#3b82f6");
        }
        render();
      });
    });

    const dismissIssueBtn = shadow.getElementById("aa-dismiss-issue-btn");
    if (dismissIssueBtn) {
      dismissIssueBtn.onclick = () => {
        currentApplicationIssue = null;
        statusBanner = { text: "", kind: "" };
        const curMeta = extractJobMetadataFromPage();
        sendBridgeAction("clear_job_application_issue", {
          title: curMeta.title,
          company_name: curMeta.company_name,
          canonical_url: curMeta.canonical_url || window.location.href,
        }).catch(() => {});
        render();
      };
    }

    const prefillBtn = shadow.getElementById("aa-btn-prefill");
    if (prefillBtn) {
      prefillBtn.onclick = () => runPrefillOrApply("prefill");
    }

    const applyBtn = shadow.getElementById("aa-btn-apply");
    if (applyBtn) {
      applyBtn.onclick = () => runPrefillOrApply("apply");
    }

    bindKbUpdateBoxEvents();

    const chatMicBtn = shadow.getElementById("aa-chat-mic");
    if (chatMicBtn) {
      chatMicBtn.onclick = () => toggleExtChatMicRecording();
    }

    shadow.querySelectorAll("[data-acc-id]").forEach((hdr) => {
      hdr.addEventListener("click", () => {
        const id = hdr.getAttribute("data-acc-id");
        userSelectedAccordion = true;
        expandedItemId = expandedItemId === id ? "" : id;
        render();
      });
    });

    shadow.querySelectorAll("[data-nav-url]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const targetUrl = btn.getAttribute("data-nav-url");
        if (targetUrl) navigateTo(targetUrl);
      });
    });

    shadow.querySelectorAll("[data-board-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const f = btn.getAttribute("data-board-filter");
        if (f) {
          selectedBoardsFilter = f;
          render();
        }
      });
    });

    shadow.querySelectorAll("[data-toggle-board-id]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const boardId = btn.getAttribute("data-toggle-board-id");
        const opRaw = btn.getAttribute("data-toggle-board-op");
        if (!boardId) return;
        if (isUnauthenticatedAuthPage() && opRaw === "true") {
          showNotice("Please finish signing in on the page first, then click Confirm Connected.", "err");
          return;
        }
        const operational = opRaw === "true";
        sendBridgeAction("toggle_job_board_operational", {
          board_id: boardId,
          operational,
        });
      });
    });

    shadow.querySelectorAll("[data-preview-pdf-url]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const pdfUrl = btn.getAttribute("data-preview-pdf-url");
        if (!pdfUrl) return;
        try {
          if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.sendMessage) {
            chrome.runtime.sendMessage({ type: "COMPANION_OPEN_TAB", url: pdfUrl }, (resp) => {
              if (!resp || !resp.ok) {
                window.open(pdfUrl, "_blank", "noopener,noreferrer");
              }
            });
          } else {
            window.open(pdfUrl, "_blank", "noopener,noreferrer");
          }
        } catch (_) {
          window.open(pdfUrl, "_blank", "noopener,noreferrer");
        }
      });
    });

    shadow.querySelectorAll("[data-chip-action]").forEach((chip) => {
      chip.addEventListener("click", () => {
        const act = chip.getAttribute("data-chip-action");
        if (act === "prefill" || act === "apply") {
          runPrefillOrApply(act);
        }
      });
    });

    shadow.querySelectorAll("[data-chip-prompt]").forEach((chip) => {
      chip.addEventListener("click", () => {
        const promptText = chip.getAttribute("data-chip-prompt");
        if (promptText) sendCompanionChatMessage(promptText);
      });
    });

    const chatInput = shadow.getElementById("aa-chat-input");
    const chatSend = shadow.getElementById("aa-chat-send");
    const chatStop = shadow.getElementById("aa-chat-stop");
    if (chatStop) {
      chatStop.onclick = () => {
        isBusyWorking = false;
        busyLabel = "";
        sendBridgeAction("stop_hermes_chat_generation", {});
        render();
      };
    }
    if (chatSend && chatInput) {
      chatSend.onclick = () => sendCompanionChatMessage(chatInput.value);
      const syncChatHeight = () => {
        chatInput.style.height = "auto";
        chatInput.style.height = `${Math.min(84, Math.max(34, chatInput.scrollHeight))}px`;
      };
      syncChatHeight();
      chatInput.addEventListener("input", () => {
        draftChatInput = chatInput.value;
        syncChatHeight();
      });
      chatInput.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" && !ev.shiftKey) {
          ev.preventDefault();
          sendCompanionChatMessage(chatInput.value);
        }
      });
    }

    const msgBox = shadow.getElementById("aa-chat-messages");
    if (msgBox) {
      const applyScroll = () => {
        if (chatPinnedToBottom) {
          msgBox.scrollTop = msgBox.scrollHeight;
        } else {
          msgBox.scrollTop = savedChatScrollTop;
        }
      };
      applyScroll();
      requestAnimationFrame(applyScroll);
      msgBox.addEventListener("scroll", () => {
        savedChatScrollTop = msgBox.scrollTop;
        const distFromBottom = msgBox.scrollHeight - msgBox.scrollTop - msgBox.clientHeight;
        chatPinnedToBottom = distFromBottom <= 36;
      });
    } else {
      const bodyBox = shadow.querySelector(".aa-body");
      if (bodyBox) {
        bodyBox.scrollTop = savedBodyScrollTop;
        bodyBox.addEventListener("scroll", () => {
          savedBodyScrollTop = bodyBox.scrollTop;
        });
      }
    }

    const cgStartOauth = shadow.getElementById("aa-cg-start-oauth");
    if (cgStartOauth) {
      cgStartOauth.onclick = async () => {
        autoFilledCodexDeviceCode = "";
        isTypingCodexDeviceCode = false;
        window.__aaCodexCodeTyped = "";
        const resp = await sendBridgeAction("start_chatgpt_codex_oauth", {});
        const data = (resp && resp.data) || bridgeState || {};
        const cgCfg = (data.onboarding && data.onboarding.chatgpt_config) || {};
        const verifyUrl = cgCfg.verification_url || "https://auth.openai.com/codex/device";
        const hasCodeBoxes = document.querySelectorAll('input[name^="character_"], input._codeInput_1r8od_14').length >= 6;
        if (!hasCodeBoxes && !(window.location.href || "").toLowerCase().includes("auth.openai.com/codex/device")) {
          navigateTo(verifyUrl);
        } else {
          maybeAutoFillCodexDeviceCode();
        }
      };
    }

    const orInput = shadow.getElementById("aa-or-key");
    const orSave = shadow.getElementById("aa-or-save");
    if (orSave && orInput) {
      orSave.onclick = () => {
        const val = orInput.value.trim();
        if (!val || val.includes("•")) {
          showNotice("Please enter your OpenRouter API key.", "err");
          return;
        }
        sendBridgeAction("save_ai_config", { openrouter_key: val });
      };
    }

    const capInput = shadow.getElementById("aa-cap-key");
    const capSave = shadow.getElementById("aa-cap-save");
    if (capSave && capInput) {
      capSave.onclick = () => {
        const val = capInput.value.trim();
        if (!val || val.includes("•")) {
          showNotice("Please enter your CapSolver API key.", "err");
          return;
        }
        sendBridgeAction("save_capsolver_key", { capsolver_key: val });
      };
    }

    const cgValidate = shadow.getElementById("aa-cg-validate");
    if (cgValidate) {
      cgValidate.onclick = () => {
        if (isUnauthenticatedAuthPage()) {
          showNotice("Please finish signing in to ChatGPT on the page first.", "err");
          return;
        }
        sendBridgeAction("configure_chatgpt_hermes", {
          connected: true,
          skip_remote_validation: true,
          account_email: "Signed in via Browser",
        });
      };
    }

    const gmPass = shadow.getElementById("aa-gm-pass");
    const gmEmail = shadow.getElementById("aa-gm-email");
    const gmSave = shadow.getElementById("aa-gm-save");
    if (gmSave) {
      gmSave.onclick = () => {
        const emailVal = (gmEmail && gmEmail.value.trim()) || detectGoogleEmailOnPage() || "";
        const rawPassVal = (gmPass && gmPass.value.trim()) || "";
        const passVal = rawPassVal.includes("•") ? "" : rawPassVal;
        sendBridgeAction("configure_gmail", {
          account_email: emailVal || "connected@gmail.com",
          app_password: passVal,
          connected: true,
          skip_remote_validation: !passVal,
        });
      };
    }

    const gmAutoGen = shadow.getElementById("aa-gm-autogen");
    if (gmAutoGen) {
      gmAutoGen.onclick = () => {
        sessionStorage.removeItem("aa_autoapply_pw_created_once");
        autoCreateAndCaptureGoogleAppPassword(true);
      };
    }

    const tealValidate = shadow.getElementById("aa-teal-validate");
    if (tealValidate) {
      tealValidate.onclick = () => {
        if (isUnauthenticatedAuthPage()) {
          showNotice("Please sign in to your Teal account on the left first.", "err");
          return;
        }
        sendBridgeAction("configure_teal_linkedin", {
          teal_connected: true,
          skip_remote_validation: true,
        });
      };
    }

    const liValidate = shadow.getElementById("aa-li-validate");
    if (liValidate) {
      liValidate.onclick = () => {
        if (isUnauthenticatedAuthPage()) {
          showNotice("Please sign in to LinkedIn on the left first (you are currently on the Join/Sign-In page).", "err");
          return;
        }
        sendBridgeAction("configure_teal_linkedin", {
          linkedin_connected: true,
          skip_remote_validation: true,
        });
      };
    }

    const jobImport = shadow.getElementById("aa-job-import");
    if (jobImport) {
      jobImport.onclick = () => {
        const meta = extractJobMetadataFromPage();
        sendBridgeAction("add_job_posting", {
          company_name: meta.company_name,
          title: meta.title,
          canonical_url: meta.canonical_url,
          workplace_mode: "remote",
          country: "US",
        });
      };
    }
  }

  function syncCollapsedExpandPill() {
    const hasInlineExpandBtn = syncLinkedInInlineExpandButtons();
    const expandBtn = shadow.getElementById("aa-pill-expand");
    if (expandBtn) {
      if (isCollapsed && !hasInlineExpandBtn) {
        expandBtn.classList.add("visible");
      } else {
        expandBtn.classList.remove("visible");
      }
    }
  }

  render();
  refreshState(true);
  setTimeout(() => {
    applyPageMargin();
    autoAcceptCookieBanners();
    checkAndTriggerPendingPasswordCountdown();
    maybeAutofillSavedSiteLogin();
  }, 150);
  setTimeout(() => {
    applyPageMargin();
    autoAcceptCookieBanners();
    autoCreateAndCaptureGoogleAppPassword(false);
    checkAndTriggerPendingPasswordCountdown();
    maybeAutofillSavedSiteLogin();
  }, 450);
  setTimeout(() => {
    applyPageMargin();
    autoAcceptCookieBanners();
    autoCreateAndCaptureGoogleAppPassword(false);
    checkAndTriggerPendingPasswordCountdown();
    maybeAutofillSavedSiteLogin();
  }, 1200);
  setTimeout(() => maybeResumePendingAgentAction(), 700);
  setInterval(() => {
    applyPageMargin();
    autoAcceptCookieBanners();
    autoCreateAndCaptureGoogleAppPassword(false);
    maybeAutoFillCodexDeviceCode();
    maybeResumePendingAgentAction();
    checkAndTriggerPendingPasswordCountdown();
    maybeAutofillSavedSiteLogin();
    syncCollapsedExpandPill();
    refreshState(false);
  }, 2200);

  window.addEventListener(
    "resize",
    () => {
      applyPageMargin();
    },
    { passive: true }
  );

  if (document.body) {
    let debounceTimer = null;
    const obs = new MutationObserver(() => {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        applyPageMargin();
        autoAcceptCookieBanners();
        autoCreateAndCaptureGoogleAppPassword(false);
        maybeAutoFillCodexDeviceCode();
        checkAndTriggerPendingPasswordCountdown();
        maybeAutofillSavedSiteLogin();
        syncCollapsedExpandPill();
      }, 220);
    });
    obs.observe(document.body, { childList: true, subtree: true });

    let scrollTimer = null;
    window.addEventListener(
      "scroll",
      () => {
        if (!isCollapsed) return;
        if (scrollTimer) clearTimeout(scrollTimer);
        scrollTimer = setTimeout(() => {
          syncCollapsedExpandPill();
        }, 120);
      },
      { passive: true, capture: true }
    );
  }
})();
