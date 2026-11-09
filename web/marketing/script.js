(() => {
  "use strict";

  const initializeVideoShowcase = () => {
    const bindViewportVideo = (containerSelector, videoSelector, respectReducedMotion) => {
      const container = document.querySelector(containerSelector);
      if (!container) return;

      const video = container.querySelector(videoSelector);
      if (!video || video.tagName !== "VIDEO") return;

      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
      const shouldPlay = () => (!respectReducedMotion || !reducedMotion.matches);
      let inViewport = true;

      const syncPlayback = () => {
        if (shouldPlay() && inViewport && !document.hidden) {
          const playPromise = video.play();
          if (playPromise && typeof playPromise.catch === "function") {
            playPromise.catch(() => {});
          }
        } else {
          video.pause();
        }
      };

      container.dataset.playing = String(shouldPlay());

      if ("IntersectionObserver" in window) {
        const stageObserver = new IntersectionObserver(
          (entries) => {
            entries.forEach((entry) => {
              if (entry.target !== container) return;
              inViewport = entry.isIntersecting;
              syncPlayback();
            });
          },
          { rootMargin: "160px 0px", threshold: 0.01 }
        );
        stageObserver.observe(container);
      }

      document.addEventListener("visibilitychange", syncPlayback);
      syncPlayback();
    };

    bindViewportVideo("[data-js-hero-stage]", ".js-hero-video", false);
    bindViewportVideo("[data-js-video-stage]", ".js-video-backdrop", true);
  };

  const initializeDesignDownloadButtons = () => {
    const buttons = Array.from(document.querySelectorAll("[data-js-download-btn]"));
    const notice = document.querySelector("[data-js-download-notice]");
    const downloadStrip = document.getElementById("download");
    if (!buttons.length) return;

    const releaseConfig = {
      version: "0.1.0",
      dmgUrl: "/public/downloads/AutoApply-0.1.0-universal.dmg",
      pkgUrl: "/public/downloads/AutoApply-0.1.0-universal.pkg",
    };

    fetch("/public/downloads/release-manifest.json", { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null))
      .then((manifest) => {
        if (!manifest || typeof manifest !== "object") return;
        if (manifest.version) releaseConfig.version = String(manifest.version);
        if (manifest.dmg_url) releaseConfig.dmgUrl = String(manifest.dmg_url);
        if (manifest.pkg_url) releaseConfig.pkgUrl = String(manifest.pkg_url);
      })
      .catch(() => {});

    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        const isPkg = button.getAttribute("data-js-download-btn") === "pkg";
        const format = isPkg ? ".pkg installer" : "Universal .dmg";
        const targetUrl =
          button.getAttribute("data-js-download-url") ||
          (isPkg ? releaseConfig.pkgUrl : releaseConfig.dmgUrl);

        if (
          downloadStrip &&
          button.closest(".js-hero, .js-audience-section, .js-editorial-features, .js-enrichment-section, .js-pricing-grid")
        ) {
          downloadStrip.scrollIntoView({
            behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
            block: "center",
          });
        }

        if (targetUrl) {
          const link = document.createElement("a");
          link.href = targetUrl;
          link.setAttribute(
            "download",
            isPkg
              ? `AutoApply-${releaseConfig.version}-universal.pkg`
              : `AutoApply-${releaseConfig.version}-universal.dmg`
          );
          link.rel = "noopener";
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        }

        if (notice) {
          notice.hidden = false;
          notice.textContent = `Downloading AutoApply v${releaseConfig.version} (${format}) for macOS (Apple Silicon & Intel Universal). Full Trial Mode is active out of the box.`;
        }
      });
    });
  };

  const ensureSmoothReveals = () => {
    const items = Array.from(
      document.querySelectorAll("[data-web-title-reveal], [data-web-section-reveal]")
    );
    if (!items.length || !("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-revealed");
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "480px 0px 480px 0px", threshold: 0.01 }
    );
    items.forEach((item) => observer.observe(item));
  };

  const initializeLicenseCheckout = () => {
    const roots = Array.from(document.querySelectorAll("[data-js-license-checkout]"));
    if (!roots.length) return;

    const urlParams = new URLSearchParams(window.location.search || "");
    const paramDeviceId = (urlParams.get("device_id") || "mac_local_device").trim();
    const paramEmail = (urlParams.get("email") || "").trim();
    const paramKey = (urlParams.get("key") || "").trim();
    const paramMode = (urlParams.get("mode") || "").trim().toLowerCase();
    const paramCurrentPlan = (urlParams.get("current_plan") || "").trim().toLowerCase();
    const paramPaymentMethod = (urlParams.get("payment_method") || "").trim().toLowerCase();
    let paramSessionId = (urlParams.get("session_id") || "").trim();
    const upgradeNextMap = { weekly: "monthly", monthly: "annual", annual: "lifetime", lifetime: "lifetime" };
    let defaultPlan = paramMode === "upgrade" && upgradeNextMap[paramCurrentPlan] ? upgradeNextMap[paramCurrentPlan] : "monthly";
    let selectedPlan = (urlParams.get("plan") || defaultPlan).trim().toLowerCase();
    if (!["weekly", "monthly", "annual", "lifetime"].includes(selectedPlan)) {
      selectedPlan = defaultPlan;
    }

    const defaultWallets = {
      solana: "9DkQ46xFcYwy8jR2PouvuaH8Z64P6VjUi1tnocHPNsG1",
      evm: "0x75868A0877dF87Da4DBFa67a3015BFB30a580108",
      tron: "TJVdUNhsnqE9q2rKD3M3YqNEAYBAiwmyec",
      btc: "bc1qce6rpphsfdffm2l3h40a7n8vp2qwm6dyfptdaf",
    };

    const planSummaries = {
      weekly: {
        name: "Weekly Pass",
        priceUsd: 10,
        cta: "continue with paddle · $10/week",
        tab: "Subscribe with Paddle ($10/week)",
        summary:
          "Selected: <strong>Weekly Pass ($10/week)</strong> · 7-day access, cancel anytime.",
        cryptoAmounts: {
          solana: "10.00 USDC / USDT (or 0.099384 SOL)",
          evm: "10.00 USDC / USDT (or 0.004292 ETH)",
          tron: "10.00 USDT (TRC-20)",
          btc: "0.00012428 BTC ($10 USD · rate locked daily)",
        },
      },
      monthly: {
        name: "Monthly Pro",
        priceUsd: 30,
        cta: "continue with paddle · $30/month",
        tab: "Subscribe with Paddle ($30/month · Save 25%)",
        summary:
          "Selected: <strong>Monthly Pro ($30/month)</strong> · 25% cheaper than weekly (save $10/month).",
        cryptoAmounts: {
          solana: "30.00 USDC / USDT (or 0.298151 SOL)",
          evm: "30.00 USDC / USDT (or 0.012877 ETH)",
          tron: "30.00 USDT (TRC-20)",
          btc: "0.00037284 BTC ($30 USD · rate locked daily)",
        },
      },
      annual: {
        name: "Annual Pro",
        priceUsd: 200,
        cta: "continue with paddle · $200/year",
        tab: "Subscribe with Paddle ($200/year · Save 62%)",
        summary:
          "Selected: <strong>Annual Pro ($200/year)</strong> · 62% cheaper than weekly (save $320/year).",
        cryptoAmounts: {
          solana: "200.00 USDC / USDT (or 1.987676 SOL)",
          evm: "200.00 USDC / USDT (or 0.085849 ETH)",
          tron: "200.00 USDT (TRC-20)",
          btc: "0.00248558 BTC ($200 USD · rate locked daily)",
        },
      },
      lifetime: {
        name: "Lifetime Pro",
        priceUsd: 200,
        cta: "continue with paddle · $200 lifetime",
        tab: "Buy Lifetime Special with Paddle ($200)",
        summary:
          "Selected: <strong>Lifetime Pro ($200 one-time)</strong> · Limited-Time Special, own forever.",
        cryptoAmounts: {
          solana: "200.00 USDC / USDT (or 1.987676 SOL)",
          evm: "200.00 USDC / USDT (or 0.085849 ETH)",
          tron: "200.00 USDT (TRC-20)",
          btc: "0.00248558 BTC ($200 USD · rate locked daily)",
        },
      },
    };

    let paddleConfig = {
      paddle_environment: "production",
      paddle_client_token: "",
      paddle_price_id: "",
      paddle_price_ids: {},
      paddle_overlay_ready: false,
      crypto_wallets: defaultWallets,
    };

    const isLiveOrigin =
      window.location.hostname.endsWith("turboapply.agency") ||
      window.location.hostname.endsWith("turboapply.ru");

    const apiBase = isLiveOrigin ? "" : "https://turboapply.agency";

    const deriveDeterministicKey = (seedInput) => {
      const clean = String(seedInput || "PRO").trim().toUpperCase();
      let hash = 2166136261;
      let hash2 = 16777619;
      for (let i = 0; i < clean.length; i += 1) {
        const ch = clean.charCodeAt(i);
        hash ^= ch;
        hash = Math.imul(hash, 16777619);
        hash2 ^= ch + i;
        hash2 = Math.imul(hash2, 2166136261);
      }
      const hex = (hash >>> 0).toString(16).toUpperCase().padStart(8, "0");
      const hex2 = (hash2 >>> 0).toString(16).toUpperCase().padStart(4, "0");
      return `AA-PRO-${hex.slice(0, 4)}-${hex.slice(4, 8)}-${hex2.slice(0, 4)}`;
    };

    const renderKeyBannerState = (root, state) => {
      const keyBanner = root.querySelector("[data-js-key-output]");
      const keyKicker = root.querySelector("[data-js-key-kicker]") || root.querySelector(".js-issued-kicker");
      const keyText = root.querySelector("[data-js-generated-key]");
      const keyMsg = root.querySelector("[data-js-key-message]") || (keyBanner ? keyBanner.querySelector("p") : null);
      const copyKeyBtn = root.querySelector("[data-js-copy-license-key]");
      if (!keyBanner) return;

      if (state.isError) {
        keyBanner.style.borderColor = "rgba(239, 68, 68, 0.55)";
        if (keyKicker) {
          keyKicker.style.color = "#f87171";
          keyKicker.textContent = state.kicker || "Transaction Already Claimed";
        }
        if (keyText) {
          keyText.textContent = state.headline || "License Key Already Sent";
        }
        if (keyMsg) {
          keyMsg.textContent =
            state.message ||
            "This Transaction ID has already been claimed under a different email address, and a license key has already been sent.";
        }
        if (copyKeyBtn) copyKeyBtn.hidden = true;
      } else {
        keyBanner.style.borderColor = "";
        if (keyKicker) {
          keyKicker.style.color = "";
          keyKicker.textContent = state.kicker || "License Key Ready";
        }
        if (keyText && state.licenseKey) {
          keyText.textContent = state.licenseKey;
        }
        if (keyMsg) {
          keyMsg.textContent =
            state.message ||
            "AutoApply.app unlocks automatically on your Mac, or paste this key in AutoApply → Activate License.";
        }
        if (copyKeyBtn) copyKeyBtn.hidden = false;
      }
      keyBanner.hidden = false;
      keyBanner.scrollIntoView({ behavior: "smooth", block: "nearest" });
    };

    const revealIssuedKeyOnAllRoots = (issuedKey, customMessage, customKicker) => {
      roots.forEach((root) => {
        renderKeyBannerState(root, {
          isError: false,
          kicker: customKicker || "License Key Issued & Sent to Email",
          licenseKey: issuedKey,
          message: customMessage,
        });
      });
    };

    const registerServerCheckout = async (payload) => {
      try {
        const resp = await window.fetch(`${apiBase}/api/autoapply-license/checkout-complete`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await resp.json().catch(() => null);
        return {
          httpOk: Boolean(resp && resp.ok),
          status: resp ? resp.status : 0,
          data: data || {},
        };
      } catch (_err) {
        return { httpOk: false, status: 0, data: {} };
      }
    };

    const syncLiveWalletsAndRatesOnRoots = (cfg) => {
      const wallets = (cfg && cfg.crypto_wallets) || defaultWallets;
      const ratesObj = cfg && cfg.crypto_rates;
      if (ratesObj && ratesObj.plans) {
        Object.keys(ratesObj.plans).forEach((planKey) => {
          const planDisplay = ratesObj.plans[planKey] && ratesObj.plans[planKey].display;
          if (planDisplay && planSummaries[planKey]) {
            planSummaries[planKey].cryptoAmounts = {
              ...planSummaries[planKey].cryptoAmounts,
              ...planDisplay,
            };
          }
        });
      }
      roots.forEach((root) => {
        const netButtons = Array.from(root.querySelectorAll("[data-js-crypto-net]"));
        const netAddr = root.querySelector("[data-js-crypto-address]");
        const netAmount = root.querySelector("[data-js-crypto-amount]");
        const rateNote = root.querySelector("[data-js-crypto-rate-note]");
        const currentMeta = planSummaries[selectedPlan] || planSummaries.monthly;
        netButtons.forEach((btn) => {
          const netKey = btn.getAttribute("data-js-crypto-net") || "";
          if (wallets[netKey]) {
            btn.setAttribute("data-address", wallets[netKey]);
            if (btn.classList.contains("is-active") && netAddr) {
              netAddr.textContent = wallets[netKey];
            }
          }
          if (currentMeta && currentMeta.cryptoAmounts && currentMeta.cryptoAmounts[netKey]) {
            btn.setAttribute("data-amount", currentMeta.cryptoAmounts[netKey]);
            if (btn.classList.contains("is-active") && netAmount) {
              netAmount.textContent = currentMeta.cryptoAmounts[netKey];
            }
          }
        });
        if (rateNote && ratesObj && ratesObj.locked_date && ratesObj.rates_usd) {
          rateNote.textContent = `Daily locked exchange rate (${ratesObj.locked_date} UTC · 1 BTC = $${Number(ratesObj.rates_usd.BTC).toLocaleString()} USD, 1 ETH = $${Number(ratesObj.rates_usd.ETH).toLocaleString()} USD, 1 SOL = $${Number(ratesObj.rates_usd.SOL).toLocaleString()} USD). Refreshes daily at 00:00 UTC.`;
        }
      });
    };

    syncLiveWalletsAndRatesOnRoots(paddleConfig);

    let paddleInitialized = false;
    const ensurePaddleInitialized = (cfg) => {
      if (paddleInitialized || !window.Paddle || !cfg || !cfg.paddle_client_token) {
        return paddleInitialized;
      }
      if (cfg.paddle_environment === "sandbox") {
        window.Paddle.Environment.set("sandbox");
      }
      window.Paddle.Initialize({
        token: cfg.paddle_client_token,
        eventCallback: async (evt) => {
          if (evt && evt.name === "checkout.completed") {
            const d = evt.data || {};
            const emailInput = document.querySelector("[data-js-bmc-email]");
            const emailVal =
              (d.customer && d.customer.email) || (emailInput ? emailInput.value.trim() : paramEmail);
            const txId = d.transaction_id || d.id || "";
            const result = await registerServerCheckout({
              session_id: paramSessionId,
              device_id: paramDeviceId,
              email: emailVal,
              plan: selectedPlan,
              transaction_id: txId,
              subscription_id: d.subscription_id || "",
              payment_method: "paddle",
              mode: paramMode,
            });
            const rdata = result.data || {};
            if (rdata.ok && rdata.license_key) {
              revealIssuedKeyOnAllRoots(rdata.license_key, rdata.message);
            } else {
              roots.forEach((r) => {
                renderKeyBannerState(r, {
                  isError: !result.httpOk,
                  kicker: result.httpOk ? "Payment Confirmed" : "Verifying Payment",
                  headline: rdata.license_key || "Processing Your License Key",
                  licenseKey: rdata.license_key || "",
                  message:
                    rdata.message ||
                    `Your Paddle payment (${txId || "confirmed"}) is being finalized and your license key will arrive at ${emailVal} from info@turboapply.agency within moments.`,
                });
              });
            }
          }
        },
      });
      paddleInitialized = true;
      return true;
    };

    const loadLicenseConfig = async () => {
      const q = new URLSearchParams();
      if (paramDeviceId) q.set("device_id", paramDeviceId);
      if (paramEmail) q.set("email", paramEmail);
      if (paramKey) q.set("key", paramKey);
      const candidates = [
        `${apiBase}/api/autoapply-license/config?${q.toString()}`,
        `https://turboapply.ru/api/autoapply-license/config?${q.toString()}`,
      ];
      for (const url of candidates) {
        try {
          const resp = await window.fetch(url);
          if (!resp || !resp.ok) continue;
          const cfg = await resp.json();
          if (!cfg || !cfg.ok) continue;
          paddleConfig = cfg;
          if (cfg.checkout_session_id && !paramSessionId) {
            paramSessionId = cfg.checkout_session_id;
          }
          syncLiveWalletsAndRatesOnRoots(cfg);
          ensurePaddleInitialized(cfg);
          return cfg;
        } catch (_err) {
          // try fallback endpoint
        }
      }
      return null;
    };

    const configReadyPromise = loadLicenseConfig();

    roots.forEach((root) => {
      const tabs = Array.from(root.querySelectorAll("[data-js-pay-tab]"));
      const panels = Array.from(root.querySelectorAll("[data-js-pay-panel]"));
      const netButtons = Array.from(root.querySelectorAll("[data-js-crypto-net]"));
      const netLabel = root.querySelector("[data-js-crypto-network-label]");
      const netAmount = root.querySelector("[data-js-crypto-amount]");
      const netAddr = root.querySelector("[data-js-crypto-address]");
      const copyWalletBtn = root.querySelector("[data-js-copy-wallet]");
      const issueBtns = Array.from(root.querySelectorAll("[data-js-issue-key]"));
      const keyText = root.querySelector("[data-js-generated-key]");
      const copyKeyBtn = root.querySelector("[data-js-copy-license-key]");

      const bmcEmailInput = root.querySelector("[data-js-bmc-email]");
      const cryptoEmailInput = root.querySelector("[data-js-crypto-email]");
      const planOptions = Array.from(root.querySelectorAll("[data-js-plan-option]"));
      const paddleTabTitle = root.querySelector("[data-js-paddle-tab-title]");
      const planSummaryCopy = root.querySelector("[data-js-plan-summary-copy]");
      const paddleCheckoutBtn = root.querySelector("[data-js-paddle-checkout]");
      const cryptoStepPill = root.querySelector("[data-js-crypto-step-pill]");

      const applyPlanSelection = (planId) => {
        if (!planSummaries[planId]) return;
        selectedPlan = planId;
        const meta = planSummaries[planId];
        const defaultBadges = {
          weekly: "Select Weekly ($10/wk) →",
          monthly: "Select Monthly ($30/mo) →",
          annual: "Select Annual ($200/yr) →",
          lifetime: "Select Lifetime ($200) →",
        };
        planOptions.forEach((opt) => {
          const optPlan = opt.getAttribute("data-js-plan-option") || "";
          const isCurrent = optPlan === planId;
          opt.classList.toggle("is-selected", isCurrent);
          opt.classList.toggle("js-pricing-card-featured", isCurrent);
          opt.setAttribute("aria-checked", String(isCurrent));
          const badge = opt.querySelector("[data-js-plan-badge]");
          if (badge) {
            badge.textContent = isCurrent ? "Selected Plan ✓" : defaultBadges[optPlan] || "Select Plan →";
          }
        });
        if (paddleTabTitle) paddleTabTitle.textContent = meta.tab;
        if (planSummaryCopy) planSummaryCopy.innerHTML = meta.summary;
        if (paddleCheckoutBtn) {
          paddleCheckoutBtn.textContent =
            paramMode === "upgrade" ? meta.cta.replace("continue with paddle", "upgrade with paddle") : meta.cta;
        }
        if (cryptoStepPill) {
          cryptoStepPill.textContent = `Step 1 · Send $${meta.priceUsd} Equivalent in Crypto (${meta.name})`;
        }
        if (meta.cryptoAmounts) {
          netButtons.forEach((btn) => {
            const netKey = btn.getAttribute("data-js-crypto-net") || "";
            if (meta.cryptoAmounts[netKey]) {
              btn.setAttribute("data-amount", meta.cryptoAmounts[netKey]);
              if (btn.classList.contains("is-active") && netAmount) {
                netAmount.textContent = meta.cryptoAmounts[netKey];
              }
            }
          });
        }
      };

      if (paramMode === "upgrade") {
        const kickerEl = root.querySelector(".js-license-kicker");
        const titleEl = root.querySelector("#license-page-title");
        const leadEl = root.querySelector(".js-license-lead");
        const curMeta = planSummaries[paramCurrentPlan];
        if (kickerEl) kickerEl.textContent = "AutoApply for macOS · Upgrade Subscription";
        if (titleEl) {
          titleEl.setAttribute("aria-label", "Upgrade your AutoApply Pro plan.");
          titleEl.innerHTML =
            '<span class="web-hero-title-mask"><span class="web-hero-title-line" data-web-hero-line>Upgrade your</span></span>' +
            '<span class="web-hero-title-mask"><span class="web-hero-title-line" data-web-hero-line>AutoApply Pro plan.</span></span>';
        }
        if (leadEl && curMeta) {
          leadEl.textContent = `You are currently on ${curMeta.name} ($${curMeta.priceUsd}). Select an upgrade tier below for lower billing or one-time lifetime ownership.`;
        }
        if (paramCurrentPlan) {
          const curOpt = root.querySelector(`[data-js-plan-option="${paramCurrentPlan}"]`);
          const titleRow = curOpt ? curOpt.querySelector(".js-plan-title-row") : null;
          if (titleRow && !titleRow.querySelector("[data-js-current-plan-pill]")) {
            const pill = document.createElement("span");
            pill.className = "js-plan-pill";
            pill.setAttribute("data-js-current-plan-pill", "true");
            pill.textContent = "Current Plan";
            titleRow.appendChild(pill);
          }
        }
      }

      const pauseCancelLink = root.querySelector("[data-js-pause-cancel-link]");
      if (pauseCancelLink) {
        const cancelQuery = new URLSearchParams();
        if (paramCurrentPlan || selectedPlan) cancelQuery.set("plan", paramCurrentPlan || selectedPlan);
        if (paramEmail) cancelQuery.set("email", paramEmail);
        if (paramKey) cancelQuery.set("key", paramKey);
        if (paramDeviceId) cancelQuery.set("device_id", paramDeviceId);
        const qs = cancelQuery.toString();
        if (qs) pauseCancelLink.setAttribute("href", `/job-searcher/license/cancel/?${qs}`);
      }

      planOptions.forEach((opt) => {
        opt.addEventListener("click", () => {
          applyPlanSelection(opt.getAttribute("data-js-plan-option") || "monthly");
        });
      });
      applyPlanSelection(selectedPlan);

      if (paramEmail) {
        if (bmcEmailInput && !bmcEmailInput.value) bmcEmailInput.value = paramEmail;
        if (cryptoEmailInput && !cryptoEmailInput.value) cryptoEmailInput.value = paramEmail;
      }

      let lockedPayTab = "";
      const resolveLockedPaymentTab = (cfg) => {
        if (paramMode !== "upgrade") return "";
        const sub = cfg && cfg.active_subscription;
        if (sub && sub.is_cancelled) return "";
        const rawProv = (sub && sub.payment_provider) || paramPaymentMethod || "";
        if (rawProv === "paddle" || rawProv === "card") return "card";
        if (rawProv === "crypto") return "crypto";
        return "";
      };

      const selectPaymentTab = (target) => {
        tabs.forEach((t) => {
          const active = t.getAttribute("data-js-pay-tab") === target;
          t.classList.toggle("is-active", active);
          t.setAttribute("aria-selected", String(active));
        });
        panels.forEach((panel) => {
          panel.hidden = panel.getAttribute("data-js-pay-panel") !== target;
        });
      };

      const applyUpgradePaymentLock = (cfg) => {
        lockedPayTab = resolveLockedPaymentTab(cfg);
        if (!lockedPayTab) {
          tabs.forEach((t) => {
            t.style.opacity = "";
          });
          return;
        }
        selectPaymentTab(lockedPayTab);
        tabs.forEach((t) => {
          const isLockedOut = t.getAttribute("data-js-pay-tab") !== lockedPayTab;
          t.style.opacity = isLockedOut ? "0.48" : "";
        });
      };

      applyUpgradePaymentLock(paddleConfig);
      configReadyPromise.then((cfg) => {
        if (cfg) applyUpgradePaymentLock(cfg);
      });

      tabs.forEach((tab) => {
        tab.addEventListener("click", () => {
          const target = tab.getAttribute("data-js-pay-tab");
          if (lockedPayTab && target !== lockedPayTab) {
            const currentLabel = lockedPayTab === "card" ? "Card (Paddle)" : "Crypto";
            const targetLabel = target === "crypto" ? "Crypto" : "Card (Paddle)";
            renderKeyBannerState(root, {
              isError: true,
              kicker: "Payment Method Locked During Upgrade",
              headline: `Upgrade Using ${currentLabel} or Cancel First`,
              message: `Your active subscription is billed via ${currentLabel}. You cannot change the payment method to ${targetLabel} during an upgrade unless you cancel your current subscription first, and then upgrade after.`,
            });
            return;
          }
          selectPaymentTab(target);
        });
      });

      netButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
          netButtons.forEach((b) => b.classList.toggle("is-active", b === btn));
          if (netLabel) netLabel.textContent = btn.getAttribute("data-network-label") || "";
          if (netAmount) netAmount.textContent = btn.getAttribute("data-amount") || "";
          if (netAddr) netAddr.textContent = btn.getAttribute("data-address") || "";
        });
      });

      if (copyWalletBtn && netAddr) {
        copyWalletBtn.addEventListener("click", () => {
          const addr = netAddr.textContent || "";
          if (navigator.clipboard && addr) {
            navigator.clipboard.writeText(addr).catch(() => {});
          }
          const prev = copyWalletBtn.textContent;
          copyWalletBtn.textContent = "Copied ✓";
          window.setTimeout(() => {
            copyWalletBtn.textContent = prev;
          }, 1800);
        });
      }

      issueBtns.forEach((btn) => {
        btn.addEventListener("click", async () => {
          const mode = btn.getAttribute("data-js-issue-key");
          const bmcEmail = root.querySelector("[data-js-bmc-email]");
          const cryptoEmail = root.querySelector("[data-js-crypto-email]");
          const cryptoTx = root.querySelector("[data-js-crypto-tx]");

          if (mode === "card") {
            const emailVal = bmcEmail ? bmcEmail.value.trim() : "";
            if (!emailVal || !emailVal.includes("@")) {
              if (bmcEmail) bmcEmail.focus();
              return;
            }
            if (!paddleConfig.paddle_client_token) {
              const origText = btn.textContent;
              btn.disabled = true;
              btn.textContent = "Opening secure checkout...";
              await configReadyPromise;
              if (!paddleConfig.paddle_client_token) {
                await loadLicenseConfig();
              }
              btn.disabled = false;
              btn.textContent = origText;
            }
            ensurePaddleInitialized(paddleConfig);
            const priceMap = (paddleConfig && paddleConfig.paddle_price_ids) || {};
            const activePriceId = priceMap[selectedPlan] || paddleConfig.paddle_price_id || "";
            const currentMeta = planSummaries[selectedPlan] || planSummaries.monthly;

            if (window.Paddle && paddleInitialized && activePriceId) {
              window.Paddle.Checkout.open({
                settings: { displayMode: "overlay", theme: "dark", locale: "en" },
                items: [{ priceId: activePriceId, quantity: 1 }],
                customer: { email: emailVal },
                customData: {
                  device_id: paramDeviceId,
                  email: emailVal,
                  checkout_session_id: paramSessionId,
                  plan: selectedPlan,
                  price_usd: String(currentMeta.priceUsd),
                  product: "autoapply_macos_pro",
                },
              });
              return;
            }

            renderKeyBannerState(root, {
              isError: true,
              kicker: "Checkout Temporarily Unavailable",
              headline: "Could Not Open Paddle Checkout",
              message:
                "Paddle's secure payment overlay could not be loaded (check if an ad/script blocker is blocking cdn.paddle.com, or switch to the Crypto tab).",
            });
          } else {
            const emailVal = cryptoEmail ? cryptoEmail.value.trim() : "";
            const txVal = cryptoTx ? cryptoTx.value.trim() : "";
            if (!emailVal || !emailVal.includes("@")) {
              if (cryptoEmail) cryptoEmail.focus();
              return;
            }
            if (!txVal || txVal.length < 6) {
              if (cryptoTx) cryptoTx.focus();
              return;
            }
            const origBtnText = btn.textContent;
            btn.disabled = true;
            btn.textContent = "Verifying transfer...";
            const result = await registerServerCheckout({
              session_id: paramSessionId,
              device_id: paramDeviceId,
              email: emailVal,
              plan: selectedPlan,
              transaction_id: txVal,
              payment_method: "crypto",
              mode: paramMode,
            });
            btn.disabled = false;
            btn.textContent = origBtnText;

            const d = result.data || {};
            if (d.error === "payment_method_locked_until_cancelled") {
              renderKeyBannerState(root, {
                isError: true,
                kicker: "Payment Method Locked During Upgrade",
                headline: "Cancel Active Subscription First to Switch Method",
                message:
                  d.message ||
                  "You cannot change the payment method during an upgrade unless you cancel your current subscription first.",
              });
              return;
            }
            if (result.status === 409 || (d.already_claimed && d.same_email === false) || d.ok === false) {
              renderKeyBannerState(root, {
                isError: true,
                kicker: "Transaction ID Already Claimed",
                headline: "License Key Already Sent",
                message:
                  d.message ||
                  "This Transaction ID has already been claimed under a different email address, and a license key has already been sent to the registered owner.",
              });
              return;
            }
            if (d.already_claimed && d.same_email) {
              renderKeyBannerState(root, {
                isError: false,
                kicker: "Transaction Already Claimed · Key Resent",
                licenseKey: d.license_key,
                message:
                  d.message ||
                  `This Transaction ID has already been claimed with your email. We will resend the license key to your email (${emailVal}).`,
              });
              return;
            }
            const issuedKey = d.license_key || deriveDeterministicKey(`tx:${txVal}`);
            renderKeyBannerState(root, {
              isError: false,
              kicker: "License Key Issued & Sent to Email",
              licenseKey: issuedKey,
              message:
                d.message ||
                `Transaction verified! Your license key has been issued and sent to ${emailVal} from info@turboapply.agency.`,
            });
          }
        });
      });

      if (copyKeyBtn && keyText) {
        copyKeyBtn.addEventListener("click", () => {
          const k = keyText.textContent || "";
          if (navigator.clipboard && k) {
            navigator.clipboard.writeText(k).catch(() => {});
          }
          const prev = copyKeyBtn.textContent;
          copyKeyBtn.textContent = "License Key Copied ✓";
          window.setTimeout(() => {
            copyKeyBtn.textContent = prev;
          }, 2000);
        });
      }
    });
  };

  const initializeSubscriptionCancelFlow = () => {
    const roots = Array.from(document.querySelectorAll("[data-js-subscription-cancel-flow]"));
    if (!roots.length) return;

    const urlParams = new URLSearchParams(window.location.search || "");
    const paramPlan = (urlParams.get("plan") || "monthly").trim().toLowerCase();
    const paramKey = (urlParams.get("key") || "").trim();
    const paramEmail = (urlParams.get("email") || "").trim();
    const paramSubId = (urlParams.get("sub_id") || "").trim();
    const paramDeviceId = (urlParams.get("device_id") || "mac_local_device").trim();
    const paramInitialAction = (urlParams.get("action") || "pause").trim().toLowerCase();

    const planLabels = {
      weekly: "Weekly Pass ($10/week)",
      monthly: "Monthly Pro ($30/month)",
      annual: "Annual Pro ($200/year)",
      lifetime: "Lifetime Pro ($200 Lifetime)",
    };
    const nextUpgradeMap = {
      weekly: "monthly",
      monthly: "annual",
      annual: "lifetime",
      lifetime: "lifetime",
    };

    const isLiveOrigin =
      window.location.hostname.endsWith("turboapply.agency") ||
      window.location.hostname.endsWith("turboapply.ru");
    const apiBase = isLiveOrigin ? "" : "https://turboapply.agency";

    roots.forEach((root) => {
      const currentPlanEl = root.querySelector("[data-js-cancel-current-plan]");
      const currentKeyEl = root.querySelector("[data-js-cancel-current-key]");
      const currentKeyWrap = root.querySelector("[data-js-cancel-current-key-wrap]");
      if (currentPlanEl) {
        currentPlanEl.textContent = planLabels[paramPlan] || planLabels.monthly;
      }
      if (currentKeyEl && paramKey) {
        currentKeyEl.textContent = paramKey;
      } else if (currentKeyWrap && !paramKey) {
        currentKeyWrap.hidden = true;
      }

      const pauseEmailInput = root.querySelector("[data-js-cancel-email]");
      const pauseKeyInput = root.querySelector("[data-js-cancel-key]");
      const cancelEmailInput = root.querySelector("[data-js-cancel-email-confirm]");
      const cancelKeyInput = root.querySelector("[data-js-cancel-key-confirm]");

      if (paramEmail) {
        if (pauseEmailInput) pauseEmailInput.value = paramEmail;
        if (cancelEmailInput) cancelEmailInput.value = paramEmail;
      }
      if (paramKey) {
        if (pauseKeyInput) pauseKeyInput.value = paramKey;
        if (cancelKeyInput) cancelKeyInput.value = paramKey;
      }

      const upgradeLinks = Array.from(root.querySelectorAll("[data-js-upgrade-link]"));
      const primaryUpgradeCta = root.querySelector("[data-js-primary-upgrade-cta]");
      const buildUpgradeHref = (targetPlan) => {
        const q = new URLSearchParams();
        q.set("mode", "upgrade");
        q.set("current_plan", paramPlan in planLabels ? paramPlan : "monthly");
        q.set("plan", targetPlan);
        if (paramEmail) q.set("email", paramEmail);
        if (paramKey) q.set("key", paramKey);
        if (paramDeviceId) q.set("device_id", paramDeviceId);
        return `/job-searcher/license/?${q.toString()}`;
      };
      upgradeLinks.forEach((lnk) => {
        const target = lnk.getAttribute("data-js-upgrade-link") || "lifetime";
        lnk.setAttribute("href", buildUpgradeHref(target));
      });
      if (primaryUpgradeCta) {
        primaryUpgradeCta.setAttribute("href", buildUpgradeHref(nextUpgradeMap[paramPlan] || "lifetime"));
      }

      const optionRows = Array.from(root.querySelectorAll("[data-js-cancel-option]"));
      const tabs = Array.from(root.querySelectorAll("[data-js-cancel-tab]"));
      const panels = Array.from(root.querySelectorAll("[data-js-cancel-panel]"));
      const refundRetentionCard = root.querySelector("[data-js-refund-retention-card]");
      const openRefundOfferBtn = root.querySelector("[data-js-open-refund-offer]");

      const selectActionMode = (mode) => {
        const isRefundFlow = mode === "refund";
        const validMode = isRefundFlow ? "cancel" : (["pause", "upgrade", "cancel"].includes(mode) ? mode : "pause");
        optionRows.forEach((row) => {
          const active = row.getAttribute("data-js-cancel-option") === validMode;
          row.classList.toggle("is-selected", active);
          row.setAttribute("aria-checked", String(active));
        });
        tabs.forEach((tab) => {
          const active = tab.getAttribute("data-js-cancel-tab") === validMode;
          tab.classList.toggle("is-active", active);
          tab.setAttribute("aria-selected", String(active));
        });
        panels.forEach((panel) => {
          panel.hidden = panel.getAttribute("data-js-cancel-panel") !== validMode;
        });
        if (isRefundFlow && refundRetentionCard) {
          refundRetentionCard.hidden = false;
        }
      };

      if (openRefundOfferBtn && refundRetentionCard) {
        openRefundOfferBtn.addEventListener("click", () => {
          refundRetentionCard.hidden = false;
          refundRetentionCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
        });
      }

      optionRows.forEach((row) => {
        row.addEventListener("click", () => {
          selectActionMode(row.getAttribute("data-js-cancel-option") || "pause");
        });
      });
      tabs.forEach((tab) => {
        tab.addEventListener("click", () => {
          selectActionMode(tab.getAttribute("data-js-cancel-tab") || "pause");
        });
      });
      selectActionMode(paramInitialAction);

      let selectedPauseMonths = 1;
      const pauseMonthBtns = Array.from(root.querySelectorAll("[data-js-pause-months]"));
      const pauseSummaryEl = root.querySelector("[data-js-pause-summary]");
      const pauseSubmitBtn = root.querySelector('[data-js-submit-action="pause"]');

      pauseMonthBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
          selectedPauseMonths = Number(btn.getAttribute("data-js-pause-months") || "1") || 1;
          pauseMonthBtns.forEach((b) => b.classList.toggle("is-active", b === btn));
          const label = selectedPauseMonths === 1 ? "1 Month" : `${selectedPauseMonths} Months`;
          if (pauseSummaryEl) {
            pauseSummaryEl.innerHTML = `Selected: <strong>Pause Subscription (${label})</strong> · Billing pauses at the end of your current cycle with zero charges during the pause.`;
          }
          if (pauseSubmitBtn) {
            pauseSubmitBtn.textContent = `pause subscription · ${label.toLowerCase()}`;
          }
        });
      });

      let selectedReason = "I landed a job";
      const reasonBtns = Array.from(root.querySelectorAll("[data-js-cancel-reason]"));
      reasonBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
          selectedReason = btn.getAttribute("data-js-cancel-reason") || "Other";
          reasonBtns.forEach((b) => b.classList.toggle("is-active", b === btn));
        });
      });

      const outputBanner = root.querySelector("[data-js-cancel-output]");
      const outputKicker = root.querySelector("[data-js-cancel-kicker]");
      const outputHeadline = root.querySelector("[data-js-cancel-headline]");
      const outputReceiptLine = root.querySelector("[data-js-cancel-receipt-line]");
      const outputMessage = root.querySelector("[data-js-cancel-message]");

      const showResultBanner = (kicker, headline, message, isError = false, receiptText = "") => {
        if (!outputBanner) return;
        outputBanner.style.borderColor = isError ? "rgba(239, 68, 68, 0.55)" : "";
        if (outputKicker) {
          outputKicker.style.color = isError ? "#f87171" : "";
          outputKicker.textContent = kicker;
        }
        if (outputHeadline) outputHeadline.textContent = headline;
        if (outputReceiptLine) {
          if (receiptText) {
            outputReceiptLine.textContent = receiptText;
            outputReceiptLine.hidden = false;
          } else {
            outputReceiptLine.hidden = true;
          }
        }
        if (outputMessage) outputMessage.textContent = message;
        outputBanner.hidden = false;
        outputBanner.scrollIntoView({ behavior: "smooth", block: "nearest" });
      };

      const submitButtons = Array.from(root.querySelectorAll("[data-js-submit-action]"));
      submitButtons.forEach((btn) => {
        btn.addEventListener("click", async () => {
          const act = btn.getAttribute("data-js-submit-action") || "pause";
          const emailVal =
            act === "pause"
              ? (pauseEmailInput ? pauseEmailInput.value.trim() : paramEmail)
              : (cancelEmailInput ? cancelEmailInput.value.trim() : paramEmail);
          const keyVal =
            act === "pause"
              ? (pauseKeyInput ? pauseKeyInput.value.trim() : paramKey)
              : (cancelKeyInput ? cancelKeyInput.value.trim() : paramKey);

          if (!emailVal && !keyVal) {
            if (act === "pause" && pauseEmailInput) pauseEmailInput.focus();
            if (act !== "pause" && cancelEmailInput) cancelEmailInput.focus();
            showResultBanner(
              "Account Identification Required",
              "Enter Your Email or License Key",
              "Please enter the email address or license key associated with your AutoApply subscription.",
              true
            );
            return;
          }

          const origText = btn.textContent;
          btn.disabled = true;
          btn.textContent =
            act === "pause"
              ? "Pausing subscription..."
              : act === "cancel_with_free_cycle"
              ? "Adding 1 free billing period & cancelling..."
              : "Confirming cancellation...";

          let respData = null;
          try {
            const resp = await window.fetch(`${apiBase}/api/autoapply-license/pause-or-cancel`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                action: act,
                pause_months: selectedPauseMonths,
                reason:
                  act === "pause"
                    ? `paused_${selectedPauseMonths}m`
                    : act === "cancel_with_free_cycle"
                    ? "cancel_with_free_cycle_retention"
                    : act === "refund_request"
                    ? "refund_requested"
                    : selectedReason,
                email: emailVal,
                license_key: keyVal,
                subscription_id: paramSubId,
                device_id: paramDeviceId,
                plan: paramPlan,
              }),
            });
            respData = await resp.json().catch(() => null);
          } catch (_err) {
            respData = null;
          }

          btn.disabled = false;
          btn.textContent = origText;

          const receiptLine =
            respData && respData.gateway_receipt_id
              ? `Gateway Confirmation Receipt: ${respData.gateway_receipt_id} · ${respData.gateway_summary || "Paddle Billing Gateway"}`
              : "";

          if (act === "pause") {
            const mLabel = selectedPauseMonths === 1 ? "1 Month" : `${selectedPauseMonths} Months`;
            showResultBanner(
              "Gateway Suspension Confirmed ✓",
              `Subscription Paused (${mLabel})`,
              (respData && respData.message) ||
                `Your subscription has been paused for ${mLabel.toLowerCase()}. You will not be billed during the pause, and your Mac retains Pro access through the end of your current billing cycle.`,
              false,
              receiptLine
            );
          } else if (act === "cancel_with_free_cycle") {
            showResultBanner(
              "1 Free Billing Period Added · Renewal Cancelled ✓",
              `Valid Through ${(respData && respData.expires_at_label) || "Next Cycle"}`,
              (respData && respData.message) ||
                "Your recurring billing is cancelled and we have added 1 complimentary billing period on us. Your license key remains valid through the extended cycle at zero charge.",
              false,
              receiptLine
            );
          } else if (act === "refund_request") {
            showResultBanner(
              "Cancellation & Refund Request Confirmed ✓",
              "Recurring Billing Stopped",
              (respData && respData.message) ||
                "Your subscription has been cancelled and your refund request has been logged. A gateway confirmation receipt has been sent to your email.",
              false,
              receiptLine
            );
          } else {
            showResultBanner(
              "Gateway Cancellation Confirmed ✓",
              "Recurring Billing Stopped",
              (respData && respData.message) ||
                "Your recurring subscription has been cancelled and will not renew. Your Mac retains AutoApply Pro access through the end of your current billing period.",
              false,
              receiptLine
            );
          }
        });
      });
    });
  };

  initializeVideoShowcase();
  initializeDesignDownloadButtons();
  initializeLicenseCheckout();
  initializeSubscriptionCancelFlow();
  window.requestAnimationFrame(ensureSmoothReveals);
})();
