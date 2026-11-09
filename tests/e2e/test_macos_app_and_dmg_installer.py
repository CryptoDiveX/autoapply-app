"""End-to-end verification of the packaged universal AutoApply.app bundle, Apple .pkg installer, DMG installer, bundled Browser + pinned CapSolver extension, and all 7 redesigned screens/workflows.

Verifies:
- T-INS-01: Universal (arm64 + x86_64) native macOS .app bundle + guided Apple .pkg installer + mountable .dmg installer with /Applications link and Install AutoApply.pkg.
- T-INS-02 / T-INS-03: Bundled isolated Python runtime inside Contents/Resources/runtime + python-env + bundled Browser (Chromium.app) + official CapSolver Chrome extension (v1.17.1).
- Code signature verification via `codesign --verify --deep --strict`.
- Clean initial state with zero pre-seeded fake users/jobs/connections and zero confusing technical jargon in user-facing component labels.
- Bundled Browser launch without `--no-sandbox` on macOS, stealth fingerprint flags (`--fingerprint=`), 5 isolated browser profiles, and CapSolver extension (`ggclmcmkbajdnklmbeomooofddmebaef`) automatically loaded and pinned in `<profile>/Default/Preferences`.
- Optional ChatGPT Subscription login for local isolated Hermes logic (`runtime-state/hermes/config.json`) with automatic fallback to OpenRouter when not connected.
- Dedicated Questionable Facts confirmation queue (`resolve_questionable_fact` / `confirm_all_facts`) where user-specified answers are incorporated into Knowledge Base Markdown sections and continuously grow `cover_letter_narratives.md`.
- Rethought Knowledge Base Markdown sections, Profile Picture upload (`upload_profile_photo`), and Voice & Microphone Self-Interview (`save_voice_interview_answer`).
- Redesigned Work Authorization, Desired Work, Smart Filters, and Preferred Compensation Range with `use_highest_listed_range` checkbox.
- Rethought Resumes Studio generating role-specific Tailored Resumes & Cover Letters (PDF + DOCX + visual Markdown preview).
- Live execution of `AutoApply.app/Contents/MacOS/AutoApply --self-test` both from `dist/` and from the mounted `.dmg` volume.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import plistlib
import sqlite3
import subprocess
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_BUNDLE = REPO_ROOT / "dist" / "AutoApply.app"
PKG_INSTALLER = REPO_ROOT / "dist" / "AutoApply-0.1.0-universal.pkg"
UNINSTALL_PKG = REPO_ROOT / "dist" / "AutoApply-Uninstaller-0.1.0.pkg"
UNINSTALL_APP = REPO_ROOT / "dist" / "Uninstall AutoApply.app"
DMG_IMAGE = REPO_ROOT / "dist" / "AutoApply-0.1.0-universal.dmg"
CAPSOLVER_EXTENSION_ID = "ggclmcmkbajdnklmbeomooofddmebaef"
AUTOAPPLY_COMPANION_EXTENSION_ID = "injmdgfjbhjclpefnjccfgcnlmfeacak"


def _invoke_bundled_bridge(action: str, payload: dict[str, object], app_support: Path) -> dict[str, object]:
    bundled_python = APP_BUNDLE / "Contents" / "Resources" / "python-env" / "bin" / "python3"
    bundled_runtime = APP_BUNDLE / "Contents" / "Resources" / "runtime"
    bundled_resources = APP_BUNDLE / "Contents" / "Resources"

    env = {
        "HOME": os.environ.get("HOME", "/tmp"),
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "AUTOAPPLY_APP_SUPPORT": str(app_support),
        "AUTOAPPLY_APP_SUPPORT_DIR": str(app_support),
        "HERMES_HOME": str(app_support / "runtime-state" / "hermes"),
        "PYTHONPATH": str(bundled_runtime),
        "AUTOAPPLY_RESOURCES_DIR": str(bundled_resources),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    proc = subprocess.run(
        [
            str(bundled_python),
            "-s",
            "-m",
            "autoapply.main",
            "--bridge-action",
            action,
            "--bridge-payload",
            json.dumps(payload),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(proc.stdout.strip())


def test_app_bundle_structure_universal_binary_and_codesign() -> None:
    """Verify AutoApply.app exists, contains universal arm64+x86_64 Mach-O binary, bundled Browser, Companion & CapSolver extensions, and valid signature."""
    assert APP_BUNDLE.is_dir(), f"Missing {APP_BUNDLE}; run `make build-dmg` first"

    info_plist = APP_BUNDLE / "Contents" / "Info.plist"
    executable = APP_BUNDLE / "Contents" / "MacOS" / "AutoApply"
    icon_file = APP_BUNDLE / "Contents" / "Resources" / "AppIcon.icns"
    bundled_runtime = APP_BUNDLE / "Contents" / "Resources" / "runtime" / "autoapply" / "main.py"
    bundled_bridge = APP_BUNDLE / "Contents" / "Resources" / "runtime" / "autoapply" / "app_bridge.py"
    bundled_python = APP_BUNDLE / "Contents" / "Resources" / "python-env" / "bin" / "python3"
    bundled_browser = (
        APP_BUNDLE / "Contents" / "Resources" / "Browser" / "AutoApply Browser.app" / "Contents" / "MacOS" / "AutoApply Browser"
    )
    if not bundled_browser.is_file():
        bundled_browser = APP_BUNDLE / "Contents" / "Resources" / "Browser" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
    bundled_capsolver = APP_BUNDLE / "Contents" / "Resources" / "extensions" / "capsolver" / "manifest.json"
    bundled_companion = APP_BUNDLE / "Contents" / "Resources" / "extensions" / "autoapply_companion" / "manifest.json"

    assert info_plist.is_file()
    assert executable.is_file()
    assert icon_file.is_file() and icon_file.stat().st_size > 1024
    assert bundled_runtime.is_file()
    assert bundled_bridge.is_file()
    assert bundled_python.exists()
    assert bundled_browser.is_file(), "Bundled Browser missing inside AutoApply.app/Contents/Resources/Browser"
    assert bundled_capsolver.is_file(), "Bundled CapSolver extension missing inside AutoApply.app/Contents/Resources/extensions/capsolver"
    assert bundled_companion.is_file(), "Bundled AutoApply Companion extension missing inside AutoApply.app/Contents/Resources/extensions/autoapply_companion"

    manifest = json.loads(bundled_capsolver.read_text(encoding="utf-8"))
    assert manifest.get("version") == "1.17.1"
    assert len(str(manifest.get("key", ""))) > 100

    comp_manifest = json.loads(bundled_companion.read_text(encoding="utf-8"))
    assert comp_manifest.get("name") == "AutoApply Companion — Setup & Validation Guide"
    assert len(str(comp_manifest.get("key", ""))) > 100

    plist_data = plistlib.loads(info_plist.read_bytes())
    assert plist_data["CFBundleIdentifier"] == "com.autoapply.macos"
    assert plist_data["CFBundleExecutable"] == "AutoApply"
    assert plist_data["CFBundleShortVersionString"] == "0.1.0"
    assert "NSMicrophoneUsageDescription" in plist_data
    assert "NSSpeechRecognitionUsageDescription" in plist_data

    lipo = subprocess.run(
        ["lipo", "-archs", str(executable)],
        capture_output=True,
        text=True,
        check=True,
    )
    archs = set(lipo.stdout.strip().split())
    assert {"arm64", "x86_64"}.issubset(archs), f"Expected universal binary, got: {archs}"

    codesign = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(APP_BUNDLE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert codesign.returncode == 0, f"codesign verification failed: {codesign.stderr}"


def test_pkg_installer_structure_scripts_and_payload(tmp_path: Path) -> None:
    """Verify guided Apple .pkg installer exists, expands cleanly, and includes welcome/conclusion HTML + postinstall script."""
    assert PKG_INSTALLER.is_file(), f"Missing {PKG_INSTALLER}; run `make build-dmg` first"
    assert PKG_INSTALLER.stat().st_size > 10_000_000

    expand_dir = tmp_path / "expanded_pkg"
    subprocess.run(
        ["pkgutil", "--expand", str(PKG_INSTALLER), str(expand_dir)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert (expand_dir / "Distribution").is_file()
    assert (expand_dir / "Resources" / "welcome.html").is_file()
    assert (expand_dir / "Resources" / "conclusion.html").is_file()
    assert (expand_dir / "AutoApply-component.pkg" / "Scripts" / "postinstall").is_file()
    assert (expand_dir / "AutoApply-component.pkg" / "Payload").is_file()

    postinstall_text = (expand_dir / "AutoApply-component.pkg" / "Scripts" / "postinstall").read_text(encoding="utf-8")
    assert "bootstrap_all" in postinstall_text
    assert "browser-profiles" in postinstall_text


def test_packaged_app_executes_bundled_runtime_selftest() -> None:
    """Run AutoApply.app/Contents/MacOS/AutoApply --self-test and verify bundled Python runtime IPC roundtrip."""
    executable = APP_BUNDLE / "Contents" / "MacOS" / "AutoApply"
    proc = subprocess.run(
        [str(executable), "--self-test"],
        capture_output=True,
        text=True,
        check=False,
        timeout=45,
    )
    assert proc.returncode == 0, f"--self-test failed: {proc.stderr} / {proc.stdout}"
    payload = json.loads(proc.stdout.strip())
    assert payload["status"] == "ok"
    assert payload["bundle_self_test"] == "passed"
    assert payload["bundle_id"] == "com.autoapply.macos"
    assert payload["native_onboarding_ready"] is True
    assert payload["native_policy_broker_allowed"] is True
    assert payload["components_count"] >= 5
    assert payload["kb_sections_count"] >= 11
    assert payload["interview_questions_count"] >= 5
    assert payload["workspace_submitted_jobs"] >= 1
    assert payload["workspace_export_path"].endswith(".json")
    assert "AutoApply.app/Contents/Resources/runtime" in payload["runtime_dir"]
    assert "AutoApply.app/Contents/Resources/python-env/bin/python3" in payload["python_executable"]


def test_clean_initial_state_and_all_redesigned_workflows(tmp_path: Path) -> None:
    """Verify fresh workspace, immediate 5-day trial timer countdown, bundled Browser + Companion & CapSolver extensions, real first/last char key masking, Teal & Gmail App Password URLs, PDF resume import, and Faster-Whisper English transcription."""
    app_support = tmp_path / "AutoApplySupport"

    # 1. Fresh state must have NO fake accounts, NO fake jobs, and NO technical jargon
    s0 = _invoke_bundled_bridge("get_state", {}, app_support)
    assert s0["onboarding"]["current_step"] == "O-01"
    assert s0["onboarding"]["ai_config"]["openrouter_key_configured"] is False
    assert s0["onboarding"]["chatgpt_config"]["connected"] is False
    assert s0["onboarding"]["chatgpt_config"]["optional"] is True
    assert s0["onboarding"]["gmail_config"]["connected"] is False
    assert s0["onboarding"]["teal_config"]["session_connected"] is False
    assert s0["onboarding"]["linkedin_config"]["session_connected"] is False
    assert s0["jobs"] == []
    assert s0["resumes"] == []
    assert s0["candidate_facts"] == []
    assert s0["readiness_matrix"]["can_activate_trial_or_run"] is False

    # Verify zero confusing terminology ("SOPS", "CloakBrowser") in user-facing component names
    for comp in s0["onboarding"]["components"]:
        assert "SOPS" not in comp["name"]
        assert "CloakBrowser" not in comp["name"]

    # 2. Activating 5-day trial MUST start the countdown timer immediately
    s_o02 = _invoke_bundled_bridge("reserve_trial_o02", {}, app_support)
    assert s_o02["onboarding"]["trial_state"] == "active_countdown"
    assert s_o02["onboarding"]["trial_expires_at"] is not None and len(str(s_o02["onboarding"]["trial_expires_at"])) > 10

    # 3. Provision components and verify all 5 Browser profiles have BOTH AutoApply Companion AND CapSolver pinned in Default/Preferences
    s_prov = _invoke_bundled_bridge("provision_components", {}, app_support)
    assert s_prov["readiness_matrix"]["isolated_runtime_ready"] is True
    for partition in ("ats_ephemeral", "google_mail", "teal", "linkedin", "extension_automation"):
        prefs_file = app_support / "browser-profiles" / partition / "Default" / "Preferences"
        assert prefs_file.is_file(), f"Missing Default/Preferences in {partition}"
        prefs_json = json.loads(prefs_file.read_text(encoding="utf-8"))
        assert AUTOAPPLY_COMPANION_EXTENSION_ID in prefs_json["extensions"]["pinned_extensions"]
        assert CAPSOLVER_EXTENSION_ID in prefs_json["extensions"]["pinned_extensions"]
        assert AUTOAPPLY_COMPANION_EXTENSION_ID in prefs_json["extensions"]["toolbar"]
        assert CAPSOLVER_EXTENSION_ID in prefs_json["extensions"]["toolbar"]
    assert (app_support / "extensions" / "capsolver" / "manifest.json").is_file()
    assert (app_support / "extensions" / "autoapply_companion" / "manifest.json").is_file()
    assert (app_support / "extensions" / "autoapply_companion" / "content.js").is_file()

    # 4. Verify Browser launch URLs for Gmail App Passwords & Teal (https://app.tealhq.com/) + Companion & CapSolver loaded
    s_launch_gmail = _invoke_bundled_bridge(
        "launch_browser_session",
        {"target": "gmail_app_password", "dry_run": True},
        app_support,
    )
    launch_info = s_launch_gmail["last_browser_launch"]
    assert launch_info["browser_provider"] == "bundled_browser"
    assert (
        "AutoApply Browser.app/Contents/MacOS/AutoApply Browser" in launch_info["browser_executable"]
        or "Chromium.app/Contents/MacOS/Chromium" in launch_info["browser_executable"]
    )
    assert "--fingerprint=" in launch_info["stealth_args"]
    assert "--fingerprint-platform=macos" in launch_info["stealth_args"]
    assert "--no-sandbox" not in launch_info["stealth_args"]
    assert launch_info["extension_loaded"] == "true"
    assert launch_info["companion_extension_id"] == AUTOAPPLY_COMPANION_EXTENSION_ID
    assert launch_info["extension_id"] == CAPSOLVER_EXTENSION_ID
    assert launch_info["extension_pinned"] == "true"
    assert launch_info["partition"] == "google_mail"
    assert launch_info["url"] == "https://myaccount.google.com/apppasswords"

    s_launch_teal = _invoke_bundled_bridge(
        "launch_browser_session",
        {"target": "teal", "dry_run": True},
        app_support,
    )
    assert s_launch_teal["last_browser_launch"]["url"] == "https://app.tealhq.com/"

    # 5. Verify Optional ChatGPT Subscription login for local isolated Hermes logic (and fallback to OpenRouter)
    s_cg_launch = _invoke_bundled_bridge(
        "launch_browser_session",
        {"target": "chatgpt", "dry_run": True},
        app_support,
    )
    assert s_cg_launch["last_browser_launch"]["url"] == "https://chatgpt.com/auth/login"

    # Seed ChatGPT cookie in extension_automation profile and connect ChatGPT session
    ext_default = app_support / "browser-profiles" / "extension_automation" / "Default"
    ext_default.mkdir(parents=True, exist_ok=True)
    cg_conn = sqlite3.connect(ext_default / "Cookies")
    cg_conn.execute("CREATE TABLE cookies (host_key TEXT, name TEXT)")
    cg_conn.execute("INSERT INTO cookies VALUES ('.chatgpt.com', '__Secure-next-auth.session-token')")
    cg_conn.commit()
    cg_conn.close()

    s_cg_ok = _invoke_bundled_bridge(
        "configure_chatgpt_hermes",
        {"connected": True, "account_email": "plus.user@openai.com"},
        app_support,
    )
    assert s_cg_ok["onboarding"]["chatgpt_config"]["connected"] is True
    assert s_cg_ok["onboarding"]["chatgpt_config"]["logic_provider"] == "chatgpt_subscription"
    hermes_cfg = json.loads((app_support / "runtime-state" / "hermes" / "config.json").read_text(encoding="utf-8"))
    assert hermes_cfg["logic_provider"] == "chatgpt_subscription"

    # Disconnecting ChatGPT falls back cleanly to OpenRouter
    s_cg_off = _invoke_bundled_bridge("configure_chatgpt_hermes", {"connected": False}, app_support)
    assert s_cg_off["onboarding"]["chatgpt_config"]["connected"] is False
    assert s_cg_off["onboarding"]["chatgpt_config"]["logic_provider"] == "openrouter_default"

    # 6. Verify Gmail & Teal validation across profiles
    gmail_default = app_support / "browser-profiles" / "google_mail" / "Default"
    gmail_default.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(gmail_default / "Cookies")
    conn.execute("CREATE TABLE cookies (host_key TEXT, name TEXT)")
    conn.execute("INSERT INTO cookies VALUES ('.google.com', 'SID')")
    conn.execute("INSERT INTO cookies VALUES ('.tealhq.com', 'session')")
    conn.commit()
    conn.close()

    s_gmail_ok = _invoke_bundled_bridge(
        "configure_gmail",
        {"account_email": "candidate.jobs@gmail.com", "app_password": "abcd efgh ijkl mnop", "connected": True},
        app_support,
    )
    assert s_gmail_ok["onboarding"]["gmail_config"]["connected"] is True

    s_teal_ok = _invoke_bundled_bridge(
        "configure_teal_linkedin",
        {"teal_connected": True},
        app_support,
    )
    assert s_teal_ok["onboarding"]["teal_config"]["session_connected"] is True
    assert s_teal_ok["readiness_matrix"]["teal_ready"] is True

    # 7. Upload Profile Picture & Save Identity Header
    dummy_photo = tmp_path / "avatar.png"
    dummy_photo.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    s_photo = _invoke_bundled_bridge(
        "upload_profile_photo",
        {"file_path": str(dummy_photo), "include_on_resume": True},
        app_support,
    )
    assert Path(s_photo["knowledge_base"]["profile_header"]["photo_path"]).is_file()
    assert s_photo["knowledge_base"]["profile_header"]["include_photo_on_resume"] is True

    # 8. Import a real PDF resume file containing /JStest and /LaunchPad font streams -> must succeed without forbidden_active_or_external_content!
    real_pdf = tmp_path / "Candidate_Real_Resume.pdf"
    real_pdf.write_bytes(
        b"%PDF-1.7\n1 0 obj << /Type /Catalog /Font /JStest /LaunchPad 1 >>\n"
        b"(Jordan Taylor) Tj\n(Staff Systems Engineer) Tj\n%%EOF"
    )
    s_imp = _invoke_bundled_bridge(
        "import_resume_file",
        {
            "file_path": str(real_pdf),
            "filename": "Candidate_CV.pdf",
            "extracted_text": (
                "Jordan Taylor\n"
                "jordan.taylor@gmail.com\n"
                "+1 415 890 1234\n"
                "Skills: Python, Swift, Rust, Kubernetes, PostgreSQL\n"
                "Principal Systems Engineer at CloudScale — Designed low-latency storage engine.\n"
                "B.S. Computer Science, Stanford University\n"
            ),
        },
        app_support,
    )
    assert len(s_imp["resumes"]) == 1
    assert s_imp["unconfirmed_count"] >= 3

    # Resolve a questionable fact with a specific user-edited answer and verify it is incorporated into the Knowledge Base & Cover Letter Stories
    highlight_fact = next(f for f in s_imp["candidate_facts"] if not f["confirmed"] and "highlight" in f["key"])
    s_res_one = _invoke_bundled_bridge(
        "resolve_questionable_fact",
        {
            "fact_id": highlight_fact["id"],
            "value": "Principal Systems Engineer at CloudScale (2021–2026) — Cut p99 storage latency by 47% across 12 regions.",
            "kb_section_id": "experience",
        },
        app_support,
    )
    exp_md = next(s["markdown"] for s in s_res_one["knowledge_base"]["sections"] if s["id"] == "experience")
    cl_md = next(s["markdown"] for s in s_res_one["knowledge_base"]["sections"] if s["id"] == "cover_letter_narratives")
    assert "Cut p99 storage latency by 47%" in exp_md
    assert "Cut p99 storage latency by 47%" in cl_md

    # Confirm remaining questionable facts and verify Knowledge Base grows
    s_conf = _invoke_bundled_bridge("confirm_all_facts", {}, app_support)
    assert s_conf["unconfirmed_count"] == 0

    # 9. Synthesize English speech WAV and verify local Faster-Whisper transcription (`transcribe_voice_audio`) + saving
    voice_aiff = tmp_path / "test_speech.aiff"
    voice_wav = tmp_path / "test_speech.wav"
    subprocess.run(
        ["/usr/bin/say", "-o", str(voice_aiff), "I built distributed backend services in Python and Kubernetes."],
        check=True,
    )
    subprocess.run(
        ["/usr/bin/afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(voice_aiff), str(voice_wav)],
        check=True,
    )
    s_whisper = _invoke_bundled_bridge(
        "transcribe_voice_audio",
        {"audio_path": str(voice_wav), "question_id": "career_pitch"},
        app_support,
    )
    transcript_out = str(s_whisper.get("last_voice_transcript", "")).lower()
    assert "python" in transcript_out or "distributed" in transcript_out or "backend" in transcript_out

    s_voice = _invoke_bundled_bridge(
        "save_voice_interview_answer",
        {
            "question_id": "q_achievement",
            "transcript": "Led a zero-downtime migration of 400 microservices to Kubernetes, saving $1.4M/year in cloud compute.",
            "mode": "voice_mic",
            "kb_section_id": "experience",
        },
        app_support,
    )
    cl_md_after_voice = next(
        s["markdown"] for s in s_voice["knowledge_base"]["sections"] if s["id"] == "cover_letter_narratives"
    )
    assert "saving $1.4M/year in cloud compute" in cl_md_after_voice

    # 10. Configure OpenRouter & CapSolver keys and verify REAL first & last characters are shown!
    s_ai = _invoke_bundled_bridge(
        "save_ai_config",
        {
            "openrouter_key": "sk-or-v1-a1b2c3d4e5f6-real-8899",
            "skip_remote_validation": True,
            "per_run_budget_usd": 3.0,
            "daily_budget_usd": 20.0,
        },
        app_support,
    )
    or_masked = s_ai["onboarding"]["ai_config"]["openrouter_key_masked"]
    assert or_masked.startswith("sk-or-v1-a1b2")
    assert "8899 (Verified)" in or_masked
    assert s_ai["readiness_matrix"]["can_activate_trial_or_run"] is True

    s_cap = _invoke_bundled_bridge(
        "save_capsolver_key",
        {"capsolver_key": "CAP-7F3A11223344556677889900", "skip_remote_validation": True},
        app_support,
    )
    cap_masked = s_cap["onboarding"]["ai_config"]["capsolver_key_masked"]
    assert cap_masked.startswith("CAP-7F3A")
    assert "9900 (Verified)" in cap_masked

    s_o13 = _invoke_bundled_bridge("activate_trial_o13", {}, app_support)
    assert s_o13["onboarding"]["trial_state"] == "active_countdown"
    assert s_o13["entitlement"]["can_run_automation"] is True

    # Verify interview questions and saved voice interview answers automatically appear in Standard Q&A Bank (qa_bank)
    qa_bank_md = next(s["markdown"] for s in s_o13["knowledge_base"]["sections"] if s["id"] == "qa_bank")
    assert "# Standard Application Q&A Bank" in qa_bank_md
    assert "saving $1.4M/year in cloud compute" in qa_bank_md

    # 11. Save Work Authorization (including Australia & US PR (Green Card)), US EEO disclosures, Desired Work, Smart Filters & Preferred Compensation Range
    s_prefs = _invoke_bundled_bridge(
        "save_preferences_o10",
        {
            "residence_country": "US",
            "work_auth_by_region": {
                "US": "PR (Green Card)",
                "EU": "Needs Sponsorship",
                "UK": "Authorized",
                "CA": "Citizen",
                "AU": "Remote B2B",
            },
            "eeo_disclosures": {
                "gender": "Decline to Self-Identify",
                "hispanic_latino": "No",
                "race_ethnicity": "White",
                "veteran_status": "I am not a protected veteran",
                "disability_status": "No, I do not have a disability",
                "lgbtq": "Prefer not to say",
            },
            "global_b2b_contractor": True,
            "desired_titles": ["Staff Backend Engineer", "Principal Systems Engineer"],
            "seniority_levels": ["Staff", "Principal"],
            "employment_types": ["Full-Time", "Contract / B2B"],
            "accepted_workplace_modes": ["remote", "hybrid"],
            "minimum_salary_usd": 180000,
            "target_salary_usd": 230000,
            "use_highest_listed_range": True,
            "salary_currency": "USD",
            "must_have_keywords": ["Python", "Distributed Systems"],
            "excluded_keywords": ["Unpaid", "Junior"],
            "excluded_employers": ["BadCorp"],
        },
        app_support,
    )
    assert s_prefs["onboarding"]["preferences"]["use_highest_listed_range"] is True
    assert s_prefs["onboarding"]["preferences"]["minimum_salary_usd"] == 180000
    assert s_prefs["onboarding"]["preferences"]["target_salary_usd"] == 230000
    assert s_prefs["onboarding"]["preferences"]["work_auth_by_region"]["US"] == "PR (Green Card)"
    assert s_prefs["onboarding"]["preferences"]["work_auth_by_region"]["CA"] == "Citizen"
    assert s_prefs["onboarding"]["preferences"]["work_auth_by_region"]["AU"] == "Remote B2B"
    assert s_prefs["onboarding"]["preferences"]["eeo_disclosures"]["veteran_status"] == "I am not a protected veteran"

    # 12. Add jobs, verify highest-range compensation logic & smart filters, generate tailored Resume + Cover Letter
    _invoke_bundled_bridge(
        "add_job_posting",
        {
            "company_name": "BadCorp",
            "title": "Staff Engineer",
            "canonical_url": "https://boards.greenhouse.io/badcorp/jobs/999",
            "workplace_mode": "remote",
            "country": "US",
            "salary_max_usd": 210000,
        },
        app_support,
    )
    s_jobs = _invoke_bundled_bridge(
        "add_job_posting",
        {
            "company_name": "Stripe",
            "title": "Senior Staff Backend Engineer",
            "canonical_url": "https://boards.greenhouse.io/stripe/jobs/101",
            "workplace_mode": "remote",
            "country": "US",
            "salary_max_usd": 265000,
        },
        app_support,
    )
    stripe_job = next(j for j in s_jobs["jobs"] if j["company_name"] == "Stripe")
    badcorp_job = next(j for j in s_jobs["jobs"] if j["company_name"] == "BadCorp")
    assert stripe_job["eligible"] is True
    assert badcorp_job["eligible"] is False
    assert "265,000" in stripe_job["screening_answers"]["Desired Compensation"]

    job_id = stripe_job["job_id"]
    s_doc = _invoke_bundled_bridge("generate_tailored_document", {"job_id": job_id}, app_support)
    doc0 = s_doc["documents"][0]
    assert Path(doc0["pdf_path"]).is_file()
    assert Path(doc0["docx_path"]).is_file()
    assert Path(doc0["pdf_path"]).name == "Alex-Mercer-Resume-Stripe.pdf"
    assert Path(doc0["docx_path"]).name == "Alex-Mercer-Resume-Stripe.docx"
    assert Path(doc0["cover_letter_pdf_path"]).name == "Alex-Mercer-Cover-Letter-Stripe.pdf"
    assert Path(doc0["cover_letter_docx_path"]).name == "Alex-Mercer-Cover-Letter-Stripe.docx"
    assert "Stripe" in doc0["cover_letter_markdown"]
    assert "CloudScale" in doc0["cover_letter_markdown"] or "Cut p99 storage latency by 47%" in doc0["cover_letter_markdown"]
    assert doc0["is_submitted"] is False
    assert "**[PLEASE SPECIFY HERE] | Vancouver, Canada | Full Time**" not in doc0["resume_markdown"]

    # Verify editing an unsubmitted resume & cover letter updates Markdown + regenerates PDF/DOCX on disk
    old_pdf_sha = doc0["pdf_sha256"]
    edited_resume_md = doc0["resume_markdown"] + "\n- Architected multi-region Stripe ledger settlement pipeline with 99.999% availability.\n"
    edited_cl_md = doc0["cover_letter_markdown"].replace("Sincerely,", "With appreciation for Stripe's engineering culture,\n\nSincerely,")
    s_edited = _invoke_bundled_bridge(
        "save_edited_document_package",
        {
            "document_id": doc0["artifact_id"],
            "job_id": job_id,
            "resume_markdown": edited_resume_md,
            "cover_letter_markdown": edited_cl_md,
        },
        app_support,
    )
    doc_edited = s_edited["documents"][0]
    assert "Architected multi-region Stripe ledger settlement pipeline" in doc_edited["resume_markdown"]
    assert "With appreciation for Stripe's engineering culture," in doc_edited["cover_letter_markdown"]
    assert doc_edited["pdf_sha256"] != old_pdf_sha
    assert Path(doc_edited["pdf_path"]).is_file()
    assert Path(doc_edited["docx_path"]).is_file()

    # Verify Sandbox-Installed Hermes AI Agent Chat with attachment staging
    sample_attachment = tmp_path / "stripe_notes.md"
    sample_attachment.write_text("# Stripe Role Notes\nFocus on payment orchestration and AI workflow reliability.\n", encoding="utf-8")
    s_chat = _invoke_bundled_bridge(
        "send_hermes_chat_message",
        {
            "message": "Analyze my attached Stripe notes and summarize how my profile fits.",
            "attachments": [{"path": str(sample_attachment), "name": "stripe_notes.md"}],
        },
        app_support,
    )
    assert s_chat["hermes_chat"]["gateway_online"] is True
    assert len(s_chat["hermes_chat"]["skills"]) >= 8
    active_sess = s_chat["hermes_chat"]["sessions"][0]
    assert len(active_sess["messages"]) >= 3
    assert active_sess["messages"][-1]["role"] == "assistant"
    assert "stripe_notes.md" in active_sess["messages"][-1]["content"]

    s_crash = _invoke_bundled_bridge("simulate_uncertain_crash", {"job_id": job_id}, app_support)
    stripe_uncertain = next(j for j in s_crash["jobs"] if j["job_id"] == job_id)
    assert stripe_uncertain["uncertain_effect"] is True

    s_recon = _invoke_bundled_bridge("reconcile_uncertain_job", {"job_id": job_id}, app_support)
    stripe_recon = next(j for j in s_recon["jobs"] if j["job_id"] == job_id)
    assert stripe_recon["state"] == "submitted_verified"
    assert s_recon["documents"][0]["is_submitted"] is True

    # Verify editing a resume after submission is LOCKED and rejected
    s_locked = _invoke_bundled_bridge(
        "save_edited_document_package",
        {
            "document_id": doc0["artifact_id"],
            "job_id": job_id,
            "resume_markdown": doc_edited["resume_markdown"] + "\n- Attempted post-submission edit\n",
            "cover_letter_markdown": doc_edited["cover_letter_markdown"],
        },
        app_support,
    )
    assert "locked" in str(s_locked.get("error", "")).lower()
    assert "Attempted post-submission edit" not in s_locked["documents"][0]["resume_markdown"]

    # 13. Export ALL user data bundle (Knowledge Base, Configurations, Skills, Secrets, Resumes, Artifacts, DBs)
    # Create a custom skill in runtime-state/hermes/skills and set custom model preferences to verify everything is exported & imported
    _invoke_bundled_bridge(
        "save_ai_model_preferences",
        {
            "logic_model": "~deepseek/deepseek-pro-latest",
            "writer_model": "~deepseek/deepseek-pro-latest",
        },
        app_support,
    )
    custom_skill_dir = app_support / "runtime-state" / "hermes" / "skills" / "custom-executive-pitch"
    custom_skill_dir.mkdir(parents=True, exist_ok=True)
    (custom_skill_dir / "SKILL.md").write_text(
        "---\nname: custom-executive-pitch\ndescription: Custom executive outreach pitch generator\n---\n# Custom Skill\n",
        encoding="utf-8",
    )

    s_exp = _invoke_bundled_bridge("export_user_data_bundle", {}, app_support)
    export_path = Path(str(s_exp["last_export_path"]))
    export_zip_path = Path(str(s_exp["last_export_zip_path"]))
    assert export_path.is_file()
    assert export_zip_path.is_file()
    exported_json = json.loads(export_path.read_text(encoding="utf-8"))
    assert exported_json["backup_format_version"] == "2.0-full-workspace"
    assert len(exported_json["candidate_facts"]) >= 3
    assert "knowledge_base" in exported_json
    assert "workspace_state" in exported_json
    assert "embedded_files_b64" in exported_json
    assert "candidate.sqlite3" in exported_json["embedded_files_b64"]
    assert any(sk["id"] == "custom-executive-pitch" for sk in exported_json["hermes_skills_summary"])

    with zipfile.ZipFile(export_zip_path, "r") as zf:
        zip_names = set(zf.namelist())
        assert "autoapply_backup_manifest.json" in zip_names
        assert "workspace_state.json" in zip_names
        assert "candidate.sqlite3" in zip_names
        assert "knowledge_base/about.md" in zip_names
        assert "runtime-state/hermes/skills/custom-executive-pitch/SKILL.md" in zip_names

    # 14. Reset workspace to clean first-run state
    s_reset = _invoke_bundled_bridge("reset_clean_install_state", {}, app_support)
    assert s_reset["onboarding"]["current_step"] == "O-01"
    assert s_reset["onboarding"]["preferences"]["residence_country"] in ("", "-")
    assert s_reset["onboarding"]["preferences"]["work_auth_by_region"]["AU"] in ("", "-")
    assert s_reset["jobs"] == []
    assert s_reset["resumes"] == []
    assert s_reset["candidate_facts"] == []
    assert not (custom_skill_dir / "SKILL.md").exists()

    # 15. Import ALL data back and verify everything is restored as if nothing ever happened
    s_imp = _invoke_bundled_bridge("import_user_data_bundle", {"source_path": str(export_zip_path)}, app_support)
    assert len(s_imp["jobs"]) >= 1
    assert any(j["state"] == "submitted_verified" for j in s_imp["jobs"])
    assert len(s_imp["resumes"]) >= 1
    assert len(s_imp["documents"]) >= 1
    assert s_imp["documents"][0]["is_submitted"] is True
    assert len(s_imp["candidate_facts"]) >= 3
    assert s_imp["onboarding"]["preferences"]["residence_country"] == "US"
    assert s_imp["onboarding"]["preferences"]["work_auth_by_region"]["CA"] == "Citizen"
    assert s_imp["onboarding"]["preferences"]["work_auth_by_region"]["AU"] == "Remote B2B"
    assert s_imp["onboarding"]["preferences"]["minimum_salary_usd"] == 180000
    assert s_imp["onboarding"]["preferences"]["target_salary_usd"] == 230000
    assert s_imp["onboarding"]["ai_config"]["logic_model"] == "~deepseek/deepseek-pro-latest"
    assert s_imp["onboarding"]["ai_config"]["writer_model"] == "~deepseek/deepseek-pro-latest"
    assert any(sk["id"] == "custom-executive-pitch" for sk in s_imp["hermes_chat"]["skills"])
    assert (custom_skill_dir / "SKILL.md").is_file()


def test_single_uninstaller_app_cleanly_removes_only_autoapply_while_preserving_hermes_and_cloakbrowser(tmp_path: Path) -> None:
    """Verify ONLY Uninstall AutoApply.app is shipped (no duplicate .pkg uninstaller) and removes ONLY AutoApply while keeping ~/.hermes and ~/.cloakbrowser intact."""
    assert UNINSTALL_APP.is_dir(), f"Missing {UNINSTALL_APP}"
    assert not UNINSTALL_PKG.exists(), f"Duplicate uninstaller {UNINSTALL_PKG} should not exist"

    # Simulate a user home with standalone Hermes, Codex, and CloakBrowser alongside AutoApply
    fake_home = tmp_path / "fake_user_home"
    standalone_hermes = fake_home / ".hermes" / "config.yaml"
    standalone_codex = fake_home / ".codex" / "config.json"
    standalone_cloak = fake_home / ".cloakbrowser" / "chromium-145" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
    standalone_hermes.parent.mkdir(parents=True, exist_ok=True)
    standalone_codex.parent.mkdir(parents=True, exist_ok=True)
    standalone_cloak.parent.mkdir(parents=True, exist_ok=True)
    standalone_hermes.write_text("standalone_hermes: preserved\n", encoding="utf-8")
    standalone_codex.write_text('{"standalone_codex": true}\n', encoding="utf-8")
    standalone_cloak.write_text("standalone_cloak_binary", encoding="utf-8")

    # Simulate installed AutoApply files
    fake_app_bundle = tmp_path / "FakeApplications" / "AutoApply.app"
    fake_data_root = fake_home / "Library" / "Application Support" / "AutoApply"
    fake_cache = fake_home / "Library" / "Caches" / "com.autoapply.macos"
    fake_prefs = fake_home / "Library" / "Preferences" / "com.autoapply.macos.plist"
    fake_app_bundle.mkdir(parents=True, exist_ok=True)
    (fake_app_bundle / "Contents").mkdir(parents=True, exist_ok=True)
    fake_data_root.mkdir(parents=True, exist_ok=True)
    (fake_data_root / "onboarding_state.json").write_text("{}", encoding="utf-8")
    fake_cache.mkdir(parents=True, exist_ok=True)
    fake_prefs.parent.mkdir(parents=True, exist_ok=True)
    fake_prefs.write_text("plist", encoding="utf-8")

    uninstaller_bin = UNINSTALL_APP / "Contents" / "MacOS" / "UninstallAutoApply"
    proc = subprocess.run(
        [
            str(uninstaller_bin),
            "--yes",
            "--target-home",
            str(fake_home),
            "--app-path",
            str(fake_app_bundle),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    out = json.loads(proc.stdout.strip())
    assert out["status"] == "uninstalled"

    # Verify AutoApply files are 100% gone
    assert not fake_app_bundle.exists()
    assert not fake_data_root.exists()
    assert not fake_cache.exists()
    assert not fake_prefs.exists()

    # Verify standalone Hermes, Codex, and CloakBrowser are 100% untouched
    assert standalone_hermes.read_text(encoding="utf-8") == "standalone_hermes: preserved\n"
    assert standalone_codex.read_text(encoding="utf-8") == '{"standalone_codex": true}\n'
    assert standalone_cloak.read_text(encoding="utf-8") == "standalone_cloak_binary"


def test_dmg_installer_mounts_and_runs_app_from_mounted_volume() -> None:
    """Mount AutoApply-0.1.0-universal.dmg, verify /Applications symlink + AutoApply.app + Install AutoApply.pkg + Uninstall AutoApply.app, and run self-test from DMG."""
    assert DMG_IMAGE.is_file(), f"Missing {DMG_IMAGE}; run `make build-dmg` first"

    attach = subprocess.run(
        ["hdiutil", "attach", "-nobrowse", "-readonly", "-plist", str(DMG_IMAGE)],
        capture_output=True,
        check=True,
    )
    attach_info = plistlib.loads(attach.stdout)
    mount_point: str | None = None
    device_node: str | None = None
    for entity in attach_info.get("system-entities", []):
        if "mount-point" in entity:
            mount_point = entity["mount-point"]
            device_node = entity.get("dev-entry")
            break

    assert mount_point is not None, "Failed to find mount-point in hdiutil attach output"
    try:
        vol_path = Path(mount_point)
        mounted_app = vol_path / "AutoApply.app"
        mounted_pkg = vol_path / "Install AutoApply.pkg"
        mounted_uninstall_pkg = vol_path / "Uninstall AutoApply.pkg"
        mounted_uninstall_app = vol_path / "Uninstall AutoApply.app"
        apps_symlink = vol_path / "Applications"

        assert mounted_app.is_dir(), "AutoApply.app missing inside mounted DMG"
        assert mounted_pkg.is_file(), "Install AutoApply.pkg missing inside mounted DMG"
        assert not mounted_uninstall_pkg.exists(), "Duplicate Uninstall AutoApply.pkg should not exist inside DMG"
        assert mounted_uninstall_app.is_dir(), "Uninstall AutoApply.app missing inside mounted DMG"
        assert apps_symlink.is_symlink(), "/Applications symlink missing inside mounted DMG"
        assert str(apps_symlink.readlink()) == "/Applications"

        mounted_exec = mounted_app / "Contents" / "MacOS" / "AutoApply"
        proc = subprocess.run(
            [str(mounted_exec), "--self-test"],
            capture_output=True,
            text=True,
            check=False,
            timeout=45,
        )
        assert proc.returncode == 0, f"Mounted DMG app --self-test failed: {proc.stderr}"
        payload = json.loads(proc.stdout.strip())
        assert payload["status"] == "ok"
        assert payload["python_worker_report"]["status"] == "ok"
    finally:
        target = device_node or mount_point
        subprocess.run(["hdiutil", "detach", target, "-force"], capture_output=True, check=False)


def test_companion_browser_extension_live_dom_and_bridge_validation(tmp_path: Path) -> None:
    """Verify the AutoApply Companion extension is preloaded right away in the bundled Browser, renders the Shadow DOM sidebar, and validates onboarding steps via the Companion HTTP bridge."""
    import socket
    import time
    import urllib.request

    app_support = tmp_path / "CompanionTestSupport"
    _invoke_bundled_bridge("provision_components", {}, app_support)

    # 1. Start the Companion HTTP Bridge Server on a free local port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        bridge_port = s.getsockname()[1]

    bundled_python = APP_BUNDLE / "Contents" / "Resources" / "python-env" / "bin" / "python3"
    bundled_runtime = APP_BUNDLE / "Contents" / "Resources" / "runtime"
    env = {
        "HOME": os.environ.get("HOME", "/tmp"),
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "AUTOAPPLY_APP_SUPPORT": str(app_support),
        "AUTOAPPLY_APP_SUPPORT_DIR": str(app_support),
        "PYTHONPATH": str(bundled_runtime),
        "PYTHONNOUSERSITE": "1",
    }
    bridge_proc = subprocess.Popen(
        [
            str(bundled_python),
            "-s",
            "-m",
            "autoapply.app_bridge",
            "--app-support-dir",
            str(app_support),
            "--serve-companion-port",
            str(bridge_port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Wait for HTTP bridge server to listen
        ready = False
        for _ in range(30):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{bridge_port}/api/companion", timeout=0.5) as resp:
                    assert resp.headers.get("Access-Control-Allow-Origin") == "*"
                    initial_state = json.loads(resp.read().decode("utf-8"))
                    assert initial_state["onboarding"]["teal_config"]["session_connected"] is False
                    ready = True
                    break
            except Exception:
                time.sleep(0.1)
        assert ready, "Companion HTTP bridge server did not become ready"

        # Verify Companion POST validation actions (Teal, Gmail, ChatGPT, OpenRouter, CapSolver)
        def _post_companion(action: str, payload: dict[str, object]) -> dict[str, object]:
            req = urllib.request.Request(
                f"http://127.0.0.1:{bridge_port}/api/companion",
                data=json.dumps({"action": action, "payload": payload}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read().decode("utf-8"))

        st_teal = _post_companion("configure_teal_linkedin", {"teal_connected": True, "skip_remote_validation": True})
        assert st_teal["onboarding"]["teal_config"]["session_connected"] is True

        st_gm = _post_companion(
            "configure_gmail",
            {"account_email": "companion.user@gmail.com", "connected": True, "skip_remote_validation": True},
        )
        assert st_gm["onboarding"]["gmail_config"]["connected"] is True
        assert st_gm["onboarding"]["gmail_config"]["account_email"] == "companion.user@gmail.com"

        st_or = _post_companion(
            "save_ai_config",
            {"openrouter_key": "sk-or-v1-companionkey1234569988", "skip_remote_validation": True},
        )
        assert st_or["onboarding"]["ai_config"]["openrouter_key_configured"] is True
        assert st_or["onboarding"]["ai_config"]["openrouter_key_masked"] == "sk-or-v1-comp••••9988 (Verified)"

        # 2. Launch the bundled Browser with the preinstalled Companion + CapSolver extensions and inspect live DOM via CDP
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
            s2.bind(("127.0.0.1", 0))
            cdp_port = s2.getsockname()[1]
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s3:
            s3.bind(("127.0.0.1", 0))
            http_site_port = s3.getsockname()[1]

        site_dir = tmp_path / "test_site"
        site_dir.mkdir(parents=True, exist_ok=True)
        (site_dir / "index.html").write_text(
            "<!DOCTYPE html><html><head><title>Senior Backend Engineer at Stripe</title></head>"
            "<body><h1>Welcome to AutoApply Companion Test Page</h1>"
            "<p>Detected key on page: sk-or-v1-aabbccddeeff001122334455</p></body></html>",
            encoding="utf-8",
        )
        site_proc = subprocess.Popen(
            [str(bundled_python), "-m", "http.server", str(http_site_port), "--bind", "127.0.0.1"],
            cwd=str(site_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        browser_exec = (
            APP_BUNDLE / "Contents" / "Resources" / "Browser" / "AutoApply Browser.app" / "Contents" / "MacOS" / "AutoApply Browser"
        )
        if not browser_exec.is_file():
            browser_exec = APP_BUNDLE / "Contents" / "Resources" / "Browser" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
        comp_dir = app_support / "extensions" / "autoapply_companion"
        cap_dir = app_support / "extensions" / "capsolver"
        profile_dir = app_support / "browser-profiles" / "teal"
        ext_list = f"{comp_dir},{cap_dir}"

        browser_proc = subprocess.Popen(
            [
                str(browser_exec),
                f"--user-data-dir={profile_dir}",
                f"--remote-debugging-port={cdp_port}",
                f"--disable-extensions-except={ext_list}",
                f"--load-extension={ext_list}",
                "--no-first-run",
                "--no-default-browser-check",
                "--window-size=1100,760",
                "--window-position=-2400,-2400",
                f"http://127.0.0.1:{http_site_port}/index.html",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            ws_url = ""
            for _ in range(50):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/list", timeout=0.6) as r:
                        tabs = json.loads(r.read().decode("utf-8"))
                        for t in tabs:
                            if f"127.0.0.1:{http_site_port}" in str(t.get("url", "")) and t.get("webSocketDebuggerUrl"):
                                ws_url = str(t["webSocketDebuggerUrl"])
                                break
                    if ws_url:
                        break
                except Exception:
                    pass
                time.sleep(0.15)
            assert ws_url, "Bundled Browser CDP tab did not become ready"

            # Poll via CDP until the Companion content script injects #autoapply-companion-host
            import textwrap

            eval_script = textwrap.dedent(
                """
                import asyncio, json, sys, websockets
                ws_url = sys.argv[1]
                js = '''
                (() => {
                    const host = document.getElementById('autoapply-companion-host');
                    if (!host || !host.shadowRoot) return { injected: false };
                    const sr = host.shadowRoot;
                    const title = sr.querySelector('.aa-title')?.textContent?.trim() || '';
                    const setupTab = sr.getElementById('aa-tab-setup');
                    if (setupTab) setupTab.click();
                    const items = Array.from(sr.querySelectorAll('.aa-check-name')).map(el => el.textContent.trim());
                    const collapseBtn = sr.getElementById('aa-btn-collapse');
                    if (collapseBtn) collapseBtn.click();
                    const collapsed = sr.querySelector('.aa-sidebar')?.classList.contains('collapsed') || false;
                    const expandBtn = sr.getElementById('aa-pill-expand');
                    if (expandBtn) expandBtn.click();
                    const expandedAgain = !(sr.querySelector('.aa-sidebar')?.classList.contains('collapsed') || false);
                    return { injected: true, title, items, collapsed, expandedAgain };
                })()
                '''
                async def main():
                    for _ in range(25):
                        async with websockets.connect(ws_url) as ws:
                            await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": js, "returnByValue": True}}))
                            msg = json.loads(await ws.recv())
                            val = msg.get("result", {}).get("result", {}).get("value", {})
                            if val.get("injected"):
                                print(json.dumps(val))
                                return
                        await asyncio.sleep(0.2)
                    print(json.dumps({"injected": False}))
                asyncio.run(main())
                """
            )
            cdp_res = subprocess.run(
                [str(bundled_python), "-c", eval_script, ws_url],
                env=env,
                capture_output=True,
                text=True,
                check=True,
                timeout=20,
            )
            dom_info = json.loads(cdp_res.stdout.strip())
            assert dom_info["injected"] is True, "AutoApply Companion extension was not preloaded/injected into page DOM"
            assert dom_info["title"] in ("AutoApply", "AutoApply Companion")
            assert len(dom_info["items"]) == 6
            assert "1. OpenRouter API Key" in dom_info["items"]
            assert "4. Gmail App Password" in dom_info["items"]
            assert any("5. Teal Job Tracker" in x for x in dom_info["items"])
            assert dom_info["collapsed"] is True
            assert dom_info["expandedAgain"] is True

            # Verify Logic & Copywriting model selection (including ~deepseek/deepseek-flash-latest & ~deepseek/deepseek-pro-latest)
            st_models = _post_companion(
                "save_ai_model_preferences",
                {
                    "logic_model": "~deepseek/deepseek-pro-latest",
                    "writer_model": "~deepseek/deepseek-pro-latest",
                },
            )
            assert st_models["onboarding"]["ai_config"]["logic_model"] == "~deepseek/deepseek-pro-latest"
            assert st_models["onboarding"]["ai_config"]["writer_model"] == "~deepseek/deepseek-pro-latest"
            logic_ids = [m["id"] for m in st_models["onboarding"]["ai_config"]["available_logic_models"]]
            writer_ids = [m["id"] for m in st_models["onboarding"]["ai_config"]["available_writer_models"]]
            assert "~deepseek/deepseek-flash-latest" in logic_ids
            assert "~deepseek/deepseek-pro-latest" in logic_ids
            assert "~deepseek/deepseek-pro-latest" in writer_ids

            # Verify background/cron chat message increments unread_count and mark_hermes_chat_read clears it
            st_bg_msg = _post_companion(
                "receive_hermes_background_message",
                {"content": "Scheduled cron update: 2 new remote roles matched your criteria."},
            )
            assert st_bg_msg["hermes_chat"]["unread_count"] >= 1
            st_read = _post_companion("mark_hermes_chat_read", {})
            assert st_read["hermes_chat"]["unread_count"] == 0

            # Verify bundled Browser has matching AutoApply Browser icon & display name
            browser_icon = APP_BUNDLE / "Contents" / "Resources" / "BrowserIcon.icns"
            bundled_chromium = APP_BUNDLE / "Contents" / "Resources" / "Browser" / "AutoApply Browser.app"
            if not bundled_chromium.is_dir():
                bundled_chromium = APP_BUNDLE / "Contents" / "Resources" / "Browser" / "Chromium.app"
            assert browser_icon.is_file() and browser_icon.stat().st_size > 1000
            assert (bundled_chromium / "Contents" / "Resources" / "app.icns").read_bytes() == browser_icon.read_bytes()
            with (bundled_chromium / "Contents" / "Info.plist").open("rb") as pf:
                b_plist = plistlib.load(pf)
            assert b_plist.get("CFBundleDisplayName") == "AutoApply Browser"
            assert b_plist.get("CFBundleName") == "AutoApply Browser"

            # Verify automatic LinkedIn login confirmation via Companion POST
            st_li = _post_companion("configure_teal_linkedin", {"linkedin_connected": True, "skip_remote_validation": True})
            assert st_li["onboarding"]["linkedin_config"]["session_connected"] is True

            # Verify Optional Teal flag and Software Update check/install provisioning
            assert st_teal["onboarding"]["teal_config"]["optional"] is True
            st_upd = _post_companion("check_for_updates", {"channel": "stable", "simulate_update_version": "0.2.0"})
            assert st_upd["onboarding"]["update_config"]["update_available"] is True
            assert st_upd["onboarding"]["update_config"]["latest_version"] == "0.2.0"
            st_inst = _post_companion("install_update", {"target_version": "0.2.0"})
            assert st_inst["onboarding"]["update_config"]["update_available"] is False
            assert st_inst["onboarding"]["update_config"]["current_version"] == "0.2.0"
        finally:
            browser_proc.terminate()
            site_proc.terminate()
            try:
                browser_proc.wait(timeout=5)
            except Exception:
                browser_proc.kill()
            try:
                site_proc.wait(timeout=3)
            except Exception:
                site_proc.kill()
    finally:
        bridge_proc.terminate()
        try:
            bridge_proc.wait(timeout=5)
        except Exception:
            bridge_proc.kill()

