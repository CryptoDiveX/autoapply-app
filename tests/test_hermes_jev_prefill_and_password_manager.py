from __future__ import annotations

import base64
from pathlib import Path

from autoapply.app_bridge import AppWorkspaceManager


def test_password_generator_20_char_default_and_12_char_adjustment(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    res_20 = bridge.execute_action("generate_site_password", {"length": 20})
    pwd_20 = res_20["generated_password"]
    assert len(pwd_20) == 20
    assert res_20["generated_password_length"] == 20
    assert pwd_20[0].isalpha()
    assert any(ch.isupper() for ch in pwd_20)
    assert any(ch.islower() for ch in pwd_20)
    assert any(ch.isdigit() for ch in pwd_20)
    assert any(ch in "!@#$%^&*()-_=+" for ch in pwd_20)

    # Automatic adjustment to 12 chars when platform max_length < 20
    res_hint = bridge.execute_action("generate_site_password", {"length": 20, "max_length": 16})
    pwd_12 = res_hint["generated_password"]
    assert len(pwd_12) == 12
    assert res_hint["generated_password_length"] == 12
    assert any(ch.isupper() for ch in pwd_12)
    assert any(ch.islower() for ch in pwd_12)
    assert any(ch.isdigit() for ch in pwd_12)
    assert any(ch in "!@#$%^&*()-_=+" for ch in pwd_12)


def test_password_vault_auto_register_totp_and_12_char_fallback(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    # 1. Auto-register on a Workday site (defaults to 20-char password)
    reg = bridge.execute_action(
        "companion_auto_register_site",
        {
            "website_name": "Synack (Workday)",
            "website_url": "https://synack.wd5.myworkdayjobs.com/en-US/Synack_Careers/job/Senior-AI-PM",
            "username": "alex.mercer@example.com",
            "totp_token": "JBSWY3DPEHPK3PXP",
            "description": "Auto-registered for Senior AI Product Manager at Synack",
        },
    )
    entry = reg["saved_password_entry"]
    assert entry["website_name"] == "Synack (Workday)"
    assert entry["username"] == "alex.mercer@example.com"
    assert len(entry["password"]) == 20
    assert entry["password_length"] == 20
    assert entry["auto_registered"] is True
    assert len(entry["totp_current_code"]) == 6
    assert entry["totp_current_code"].isdigit()

    # 2. Platform rejects 20-char password -> automatically adjust to 12 chars
    adj = bridge.execute_action(
        "adjust_password_entry_to_12_chars",
        {
            "id": entry["id"],
            "website_url": entry["website_url"],
            "username": entry["username"],
        },
    )
    adj_entry = adj["saved_password_entry"]
    assert adj_entry["id"] == entry["id"]
    assert len(adj_entry["password"]) == 12
    assert adj_entry["password_length"] == 12
    assert "12-char" in adj_entry["description"]

    # Verify full workspace state exposes password_vault
    state = bridge.get_full_workspace_state()
    vault = state["password_vault"]
    assert len(vault) == 1
    assert vault[0]["id"] == entry["id"]
    assert len(vault[0]["password"]) == 12


def test_synack_greenhouse_prefill_uses_kb_grounding_jev_and_pdf_preview_urls(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    synack_fields = [
        {"field_id": "first_name", "label": "First Name *", "tag": "input", "type": "text", "required": True},
        {"field_id": "last_name", "label": "Last Name *", "tag": "input", "type": "text", "required": True},
        {"field_id": "email", "label": "Email *", "tag": "input", "type": "email", "required": True},
        {"field_id": "phone", "label": "Phone *", "tag": "input", "type": "tel", "required": True},
        {
            "field_id": "question_37220263002",
            "label": "LinkedIn Profile *",
            "tag": "input",
            "type": "text",
            "required": True,
        },
        {
            "field_id": "question_37220264002",
            "label": "How many years of experience do you have in Product Management? *",
            "tag": "input",
            "type": "text",
            "required": True,
        },
        {
            "field_id": "question_37220265002",
            "label": "How many years of experience do you have in the cyber security industry? *",
            "tag": "input",
            "type": "text",
            "required": True,
        },
        {
            "field_id": "question_37220266002",
            "label": "Please describe an AI product or feature you have delivered in 3 sentences or less. *",
            "tag": "textarea",
            "type": "textarea",
            "required": True,
        },
        {
            "field_id": "question_37220267002",
            "label": "Do you have a technical degree (Engineering, Computer Science, etc.)? *",
            "tag": "input",
            "type": "combobox",
            "is_combobox": True,
            "required": True,
        },
    ]

    state = bridge.execute_action(
        "companion_prepare_and_prefill_job",
        {
            "canonical_url": "https://job-boards.greenhouse.io/synack/jobs/4672891002",
            "title": "Senior AI Product Manager",
            "company_name": "Synack",
            "description": "Senior AI Product Manager building autonomous pentesting & AI security workflows.",
            "detected_fields": synack_fields,
        },
    )
    pkg = state["prefill_package"]
    assert pkg["jev_verification"]["model"] == "~typesafe/jev-latest"
    assert pkg["jev_verification"]["passed"] is True

    mapped = pkg["field_values"]
    assert mapped["first_name"] in ("Alex", "Alexander")
    assert mapped["last_name"] == "Mercer"
    assert mapped["email"] == "alex.mercer@example.com"
    # Never hallucinate "10+" for cyber security or PM experience!
    assert mapped["question_37220264002"] == "6"
    assert mapped["question_37220265002"] == "0"
    assert mapped["question_37220267002"] == "Yes"
    assert len(mapped["question_37220266002"]) > 30
    assert "10+" not in mapped.values()

    # Verify tailored 2-page Resume PDF and 1-page Cover Letter PDF are generated with preview URLs
    resume_doc = pkg["documents"]["resume"]
    cover_doc = pkg["documents"]["cover_letter"]
    assert resume_doc["filename"].endswith(".pdf")
    assert cover_doc["filename"].endswith(".pdf")
    assert resume_doc["preview_url"].startswith("http://127.0.0.1:19299/documents/")
    assert cover_doc["preview_url"].startswith("http://127.0.0.1:19299/documents/")
    assert base64.b64decode(resume_doc["base64"]).startswith(b"%PDF-")
    assert base64.b64decode(cover_doc["base64"]).startswith(b"%PDF-")


def test_sandbox_hermes_yolo_mode_and_live_model_verification(tmp_path: Path) -> None:
    import json

    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    # Select ~deepseek/deepseek-flash-latest with medium reasoning effort
    state = bridge.execute_action(
        "save_model_selection",
        {
            "logic_model": "~deepseek/deepseek-flash-latest",
            "logic_reasoning_effort": "medium",
            "writer_model": "~anthropic/claude-sonnet-latest",
            "writer_reasoning_effort": "medium",
        },
    )
    hc = state["hermes_chat"]
    assert hc["yolo_mode"] is True
    assert hc["logic_model"] == "~deepseek/deepseek-flash-latest"
    # Customer-facing labels must be plain and jargon-free
    assert hc["model_name"] == "DeepSeek Flash"
    assert "YOLO" not in hc["model_name"]
    assert "YOLO" not in hc["provider_label"]
    welcome = hc["messages"][0]["content"]
    for banned in ("Hermes", "Sandbox", "YOLO", "JEV", "jev-latest"):
        assert banned not in welcome

    hermes_dir = tmp_path / "app_support" / "runtime-state" / "hermes"
    cfg_yaml = (hermes_dir / "config.yaml").read_text(encoding="utf-8")
    assert "default: ~deepseek/deepseek-flash-latest" in cfg_yaml
    assert "mode: 'off'" in cfg_yaml
    assert "yolo: true" in cfg_yaml
    assert "require_approvals: false" in cfg_yaml
    assert "subagent_auto_approve: true" in cfg_yaml

    cfg_json = json.loads((hermes_dir / "config.json").read_text(encoding="utf-8"))
    assert cfg_json["yolo_mode"] is True
    assert cfg_json["approvals_mode"] == "off"
    assert cfg_json["require_approvals"] is False
    assert cfg_json["logic_model"] == "~deepseek/deepseek-flash-latest"
    assert cfg_json["quality_gate_model"] == "~typesafe/jev-latest"

    # Ask the agent what model it is running on: plain, friendly answer with zero internal jargon
    res = bridge.execute_action(
        "send_hermes_chat_message",
        {"message": "What language model are you using?"},
    )
    last_msg = res["hermes_chat"]["messages"][-1]
    assert "DeepSeek Flash" in last_msg["content"]
    assert "Claude Sonnet" in last_msg["content"]
    for banned in ("Hermes", "Sandbox", "YOLO", "JEV", "jev-latest", "Telemetry", "HERMES_HOME"):
        assert banned not in last_msg["content"]
    assert all(not tc.get("summary") for tc in last_msg.get("tool_calls", []))

    # Internal agent policy must never instruct the agent to call itself Hermes
    agents_md = (hermes_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert "You are **AutoApply**" in agents_md
    assert "You are **Hermes" not in agents_md

    # Verify preinstalled CloakBrowser & Browser-Use skills are provisioned in sandbox Hermes
    skills_dir = hermes_dir / "skills"
    for required_skill in (
        "agent-browser",
        "browser-harness",
        "cloakbrowser-automation",
        "blocked-page-recovery",
        "computer-use",
        "vb-job-application-operator",
        "career-application-documents",
        "job-application-sprint-operations",
    ):
        assert (skills_dir / required_skill / "SKILL.md").exists(), f"Missing preinstalled skill {required_skill}"
        assert required_skill in cfg_json["allowed_skills"]


def test_manual_form_edits_saved_to_knowledge_base_and_reused_in_prefill(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    # Simulate user manually editing fields on a job application form and clicking "Update Knowledge Base"
    save_res = bridge.execute_action(
        "save_manual_form_edits_to_kb",
        {
            "job_title": "Principal AI Product Manager",
            "company_name": "Relativity",
            "canonical_url": "https://www.linkedin.com/jobs/view/4192837465/",
            "edited_fields": [
                {
                    "field_id": "custom_q_relativity_1",
                    "label": "How many years of experience do you have with eDiscovery or legal tech platforms?",
                    "value": "4",
                },
                {
                    "field_id": "custom_q_relativity_2",
                    "label": "What is your preferred notice period to start?",
                    "value": "Immediate (within 2 weeks)",
                },
            ],
        },
    )
    assert save_res["kb_update_result"]["saved_count"] == 2

    # Subsequent prefill for a form asking those questions must return the user's updated KB answers
    prefill = bridge.execute_action(
        "companion_prepare_and_prefill_job",
        {
            "canonical_url": "https://www.linkedin.com/jobs/view/4192837465/",
            "title": "Principal AI Product Manager",
            "company_name": "Relativity",
            "description": "Lead AI product strategy for legal tech and eDiscovery.",
            "detected_fields": [
                {
                    "field_id": "q_ediscovery",
                    "label": "How many years of experience do you have with eDiscovery or legal tech platforms? *",
                    "tag": "input",
                    "type": "text",
                    "required": True,
                },
                {
                    "field_id": "q_notice",
                    "label": "What is your preferred notice period to start? *",
                    "tag": "input",
                    "type": "text",
                    "required": True,
                },
            ],
        },
    )
    mapped = prefill["prefill_package"]["field_values"]
    assert mapped["q_ediscovery"] == "4"
    assert mapped["q_notice"] == "Immediate (within 2 weeks)"


def test_extension_ui_simplification_and_mic_and_kb_buttons_present() -> None:
    content_js = Path("packaging/extensions/autoapply_companion/content.js").read_text(encoding="utf-8")
    # Verify redundant UI elements and jargon are removed from Co-Pilot UI
    assert "Connections Active" not in content_js
    assert "Synced with AutoApply" not in content_js
    assert "JEV Verified" not in content_js
    # Verify Update Knowledge Base button and Chat Microphone button are present
    assert "aa-btn-update-kb" in content_js
    assert "Update Knowledge Base" in content_js
    assert "save_manual_form_edits_to_kb" in content_js
    assert "aa-chat-mic" in content_js
    assert "cdp_cloakbrowser_interact" in content_js

    # Verify Passwords tab UI/UX modal editor, compact rows, and delete confirmation alerts
    main_swift = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert "PasswordVaultEditorModalView" in main_swift
    assert "PasswordVaultCompactRow" in main_swift
    assert "\"Delete Login?\"" in main_swift
    assert "\"Delete Job?\"" in main_swift
    assert "\"Delete Resume?\"" in main_swift
    assert "\"Delete Conversation?\"" in main_swift

    # No internal jargon labels in the AI Agent chat UI
    for banned in ("YOLO Mode • Max Powers", "Verify Model", "AutoApply AI • Sandbox Hermes", "Sandbox Hermes"):
        assert banned not in main_swift





def test_voice_interview_saves_reviewed_summary_not_raw_transcript(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    q = next(q for q in bridge._get_all_interview_questions(bridge._load_raw_state()) if q["id"] == "q_accomplishments")

    # A fake leftover audio file must NOT cause the reviewed summary to be replaced by a raw re-transcription
    fake_audio = tmp_path / "leftover.wav"
    fake_audio.write_bytes(b"RIFF0000WAVEfmt not really audio")
    summary_text = (
        "I led an IoT platform launch that cut service workload and sped up parts ordering.\n\n"
        "- Built a mobile app for manuals and quick-start guides\n"
        "- Routed service tickets and parts requests through the app"
    )
    state = bridge.execute_action(
        "save_voice_interview_answer",
        {
            "question_id": q["id"],
            "transcript": summary_text,
            "mode": "voice_mic",
            "audio_path": str(fake_audio),
            "rewrite_with_llm": False,
            "kb_section_id": q["kb_section_id"],
        },
    )
    raw = bridge._load_raw_state()
    saved = raw["onboarding"]["interview_answers"][q["id"]]
    assert saved["transcript"] == summary_text
    assert saved["summarized"] is True

    sections = {s["id"]: s["markdown"] for s in state["knowledge_base"]["sections"]}
    target_md = sections[q["kb_section_id"]]
    assert f"## Interview Notes: {q['title']}\nI led an IoT platform launch" in target_md
    assert "- **Organization:**" not in target_md.split("Interview Notes:")[1]
    assert "- Built a mobile app for manuals and quick-start guides" in target_md

    cl_md = sections["cover_letter_narratives"]
    cl_line = next(ln for ln in cl_md.splitlines() if ln.startswith(f"- **{q['title']}:**"))
    assert cl_line == f"- **{q['title']}:** I led an IoT platform launch that cut service workload and sped up parts ordering."

    qa_md = sections["qa_bank"]
    assert "- **Answer:** I led an IoT platform launch that cut service workload and sped up parts ordering." in qa_md
    assert "  - Routed service tickets and parts requests through the app" in qa_md


def test_legacy_raw_voice_answers_are_repaired_into_clean_blocks(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    raw = bridge._load_raw_state()
    q = next(q for q in bridge._get_all_interview_questions(raw) if q["id"] == "q_accomplishments")
    legacy = "Alright, so I had the project, it was an IOT project\nthat had helped the company improve\nday-to-day"
    raw["onboarding"]["interview_answers"][q["id"]] = {
        "status": "saved", "mode": "voice_mic", "transcript": legacy, "kb_section_id": q["kb_section_id"],
    }
    for sec in raw["knowledge_base"]["sections"]:
        if sec["id"] == "cover_letter_narratives":
            sec["markdown"] += f"\n- **{q['title']}:** {legacy}\n"
    bridge._save_raw_state(raw)

    state = bridge.execute_action("resummarize_voice_interview_answers", {})
    sections = {s["id"]: s["markdown"] for s in state["knowledge_base"]["sections"]}
    assert legacy not in sections["cover_letter_narratives"]
    cl_lines = [ln for ln in sections["cover_letter_narratives"].splitlines() if ln.startswith(f"- **{q['title']}:**")]
    assert len(cl_lines) == 1 and "\n" not in cl_lines[0]
    assert f"## Interview Notes: {q['title']}" in sections[q["kb_section_id"]]
    fixed = bridge._load_raw_state()["onboarding"]["interview_answers"][q["id"]]
    assert fixed["summarized"] is True and fixed["raw_transcript"] == legacy


def test_cover_letter_strips_verified_job_noise_placeholders_and_stays_one_page(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    # Inject noisy confirmed facts (placeholders, spoken transcript, wrapped resume fragment)
    bridge._upsert_confirmed_fact(
        key="quantified_scope_and_impact_highlights",
        category="work_history",
        value="Led product launch achieving [PLEASE SPECIFY HERE] revenue growth",
        source_ref="test",
    )
    bridge._upsert_confirmed_fact(
        key="verified_experience_1",
        category="work_history",
        value="traded manufacturer. Ran 10 projects concurrently across 12 departments",
        source_ref="test",
    )
    bridge._upsert_confirmed_fact(
        key="verified_accomplishment_metric",
        category="interview_confirmed",
        value="Alright, so I had the project, it was an IoT project that helped the company.",
        source_ref="test",
    )

    s_jobs = bridge.execute_action(
        "add_job_posting",
        {
            "company_name": "Product Manager - AI Evaluations Tooling (Verified job)",
            "title": "Product Manager - AI Evaluations Tooling (Verified job)",
            "canonical_url": "https://www.linkedin.com/jobs/view/999999",
            "workplace_mode": "remote",
            "country": "CA",
            "salary_max_usd": 210000,
        },
    )
    job = s_jobs["jobs"][0]
    assert job["title"] == "Product Manager - AI Evaluations Tooling"
    assert job["company_name"] == ""

    s_doc = bridge.execute_action("generate_tailored_document", {"job_id": job["job_id"]})
    cl_md = s_doc["documents"][0]["cover_letter_markdown"]
    assert "[PLEASE SPECIFY" not in cl_md
    assert "Alright, so" not in cl_md
    assert "traded manufacturer" not in cl_md
    assert "(Verified job)" not in cl_md
    assert "Dear Hiring Team," in cl_md
    assert "Dear Product Manager" not in cl_md
    body_words = sum(len(p.split()) for p in s_doc["documents"][0]["vb_template_payload"]["cover_letter"]["paragraphs"])
    assert body_words <= 310


def test_hermes_orchestrator_accessible_when_asked_and_executes_actions(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    res = bridge.execute_action(
        "send_hermes_chat_message",
        {"message": "ARE YOU HERMES? WHAT SKILLS DO YOU HAVE AS AN ORCHISTRATOR?"},
    )
    reply = res["hermes_chat"]["messages"][-1]["content"]
    assert "Hermes orchestrator" in reply
    assert "career-application-documents" in reply
    assert "I'm not AutoApply" not in reply

    # Ask the orchestrator to generate a cover letter for a saved job
    bridge.execute_action(
        "add_job_posting",
        {
            "company_name": "Anthropic",
            "title": "Product Manager, Evaluations",
            "canonical_url": "https://boards.greenhouse.io/anthropic/jobs/123",
            "workplace_mode": "remote",
            "country": "CA",
            "salary_max_usd": 240000,
        },
    )
    res2 = bridge.execute_action(
        "send_hermes_chat_message",
        {"message": "Please regenerate the cover letter and resume for Anthropic"},
    )
    assert len(res2["documents"]) >= 1
    assert any(tc["name"] == "career-application-documents" for tc in res2["hermes_chat"]["messages"][-1]["tool_calls"])


def test_smart_knowledge_base_ingestion_auto_routes_text_dumps_and_files(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    extra_file = tmp_path / "notes.md"
    extra_file.write_text(
        "## AWS Certified Solutions Architect\nEarned AWS Certified Solutions Architect credential in 2025.\n\n"
        "## Why do you want to work in AI evaluations?\nI enjoy building deterministic quality gates and evaluation harnesses for LLM products.\n",
        encoding="utf-8",
    )
    dump_text = (
        "Alright, so I led the global ERP migration — reducing order processing latency by 42% across 6 warehouses.\n\n"
        "Skills: Python, SQL, Looker, BigQuery, PyTorch, LangChain, FastAPI"
    )
    state = bridge.execute_action(
        "ingest_knowledge_into_kb",
        {
            "raw_text": dump_text,
            "file_paths": [str(extra_file)],
            "auto_route": True,
        },
    )
    res = state["kb_ingestion_result"]
    assert res["qc_passed"] is True
    assert res["items_integrated"] >= 3
    assert len(res["files_processed"]) == 1
    assert "experience" in res["sections_updated"]
    assert "skills" in res["sections_updated"]
    assert "certifications" in res["sections_updated"]
    assert "qa_bank" in res["sections_updated"]

    sec_map = {s["id"]: s["markdown"] for s in state["knowledge_base"]["sections"]}
    assert "42%" in sec_map["experience"]
    assert "—" not in sec_map["experience"]
    assert "LangChain" in sec_map["skills"]
    assert "AWS Certified Solutions Architect" in sec_map["certifications"]
    assert "deterministic quality gates" in sec_map["qa_bank"]


def test_trulioo_ashby_wrapper_title_and_canada_work_auth_and_skill_sync(tmp_path: Path) -> None:
    app_support = tmp_path / "app_support"
    bridge = AppWorkspaceManager(app_support_dir=app_support)

    # 1. Verify 'Work at Trulioo' / 'Work' wrapper title is cleaned and preserves real LinkedIn job title
    t1, c1 = bridge._clean_job_title_and_company("Work at Trulioo", "")
    assert t1 == ""
    assert c1 == "Trulioo"
    t2, c2 = bridge._clean_job_title_and_company("Work", "Trulioo")
    assert t2 == ""
    assert c2 == "Trulioo"

    # First save the LinkedIn job ('Director, Product (KYB)' at 'Trulioo'), then prefill on the Trulioo wrapper URL
    bridge.execute_action(
        "add_job_posting",
        {
            "company_name": "Trulioo",
            "title": "Director, Product (KYB)",
            "canonical_url": "https://www.linkedin.com/jobs/view/4312345678/",
            "workplace_mode": "remote",
            "country": "CA",
            "salary_max_usd": 220000,
        },
    )

    trulioo_fields = [
        {"field_id": "_systemfield_name", "label": "Name", "type": "text", "tag": "input", "required": True},
        {"field_id": "_systemfield_email", "label": "Email", "type": "email", "tag": "input", "required": True},
        {"field_id": "phone", "label": "Phone", "type": "text", "tag": "input", "required": True},
        {
            "field_id": "5773691d-3558-4365-8b12-cc91b73480af",
            "label": "Are you legally eligible to work in Canada or the USA?",
            "type": "radio",
            "tag": "input",
            "required": True,
            "options": [
                "Yes - I am legally eligible to work in Canada",
                "Yes - I am legally eligible to work in the USA",
                "No - I am not legally eligible to work in Canada or the USA",
            ],
        },
        {
            "field_id": "bbcc362c-c5f6-49d0-9848-33bff2f7e88b",
            "label": "Will you now or in the future require Trulioo to sponsor your employment authorization to work in this location?",
            "type": "radio",
            "tag": "input",
            "required": True,
            "options": [
                "Yes, I currently require sponsorship",
                "No, I do not currently require sponsorship, but I will require sponsorship in the future.",
                "No, I do not require sponsorship now or in the future.",
            ],
        },
        {
            "field_id": "question_14259392004",
            "label": "Are you comfortable working a remote role?",
            "type": "radio",
            "tag": "input",
            "required": True,
            "options": ["Yes", "No"],
        },
        {
            "field_id": "question_14259394004",
            "label": "How did you hear about this opportunity?",
            "type": "combobox",
            "tag": "input",
            "required": True,
            "options": ["LinkedIn", "Indeed", "Company Website", "Other"],
        },
        {
            "field_id": "question_14259395004",
            "label": "What are your preferred pronouns?",
            "type": "text",
            "tag": "input",
            "required": False,
        },
    ]

    state = bridge.execute_action(
        "companion_prepare_and_prefill_job",
        {
            "mode": "prefill",
            "canonical_url": "https://www.trulioo.com/apply?ashby_jid=f645625c-7910-43a5-960e-40f4999d6066&utm_source=LinkedIn",
            "title": "Work at Trulioo",
            "company_name": "Trulioo",
            "form_fields": trulioo_fields,
        },
    )
    pkg = state["prefill_package"]
    assert pkg["title"] == "Director, Product (KYB)"
    assert pkg["company_name"] == "Trulioo"
    fv = pkg["field_values"]
    assert fv["_systemfield_name"] == "Alex Mercer"
    assert fv["5773691d-3558-4365-8b12-cc91b73480af"] == "Yes - I am legally eligible to work in Canada"
    assert fv["bbcc362c-c5f6-49d0-9848-33bff2f7e88b"] == "No, I do not require sponsorship now or in the future."
    assert fv["question_14259392004"] == "Yes"
    assert fv["question_14259395004"] == "He/Him"

    # 2. Verify vb-jobs skills, references, and scripts are provisioned into runtime-state/hermes
    ref_file = app_support / "runtime-state" / "hermes" / "skills" / "vb-job-application-operator" / "references" / "ashby-radio-commit-and-geography.md"
    assert ref_file.is_file()
    script_file = app_support / "runtime-state" / "hermes" / "scripts" / "native_multipart_candidate_audit.py"
    assert script_file.is_file()


def test_extension_docked_border_no_select_labels_48khz_voice_and_application_issue_notes(tmp_path: Path) -> None:
    import io
    import wave
    import numpy as np

    content_js = Path("packaging/extensions/autoapply_companion/content.js").read_text(encoding="utf-8")

    # 1. Docked browser border (viewport width shrink + fixed navbar/drawer docking + WeakSet anti-detection + no left clipping)
    assert "calc(100vw - ${sidebarW})" in content_js
    assert "ensureNoLeftClipping" in content_js
    assert "clearAllJobHighlights" in content_js
    assert "queryAllDeep" in content_js
    assert "getModalStepSignature" in content_js
    assert "aa-dismiss-issue-btn" in content_js
    assert "/^i['’]?m interested$/i" not in content_js
    assert "aa-viewport-dock-style" in content_js
    assert "programmaticTypingSet = new WeakSet()" in content_js
    assert 'dataset.aaProgrammaticTyping = "1"' not in content_js

    # 2. Stupid "Selected" / "Select" badges removed from job feed items
    assert '${isSel ? "Selected" : "Select"}' not in content_js

    # 3. 48kHz WAV resampling & silence noise rejection (no "How? How? How? How?" hallucination)
    buf = io.BytesIO()
    sr_48k = 48000
    t = np.linspace(0, 1.0, sr_48k, endpoint=False)
    sine_pcm = (np.sin(2 * np.pi * 440.0 * t) * 12000).astype(np.int16)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr_48k)
        wf.writeframes(sine_pcm.tobytes())
    resampled_16k = AppWorkspaceManager._decode_wav_bytes_to_16k_float32(buf.getvalue())
    assert 15900 <= resampled_16k.size <= 16100

    # Low-energy room noise must return empty string instead of Whisper "How? How? How? How?" hallucination
    noise_buf = io.BytesIO()
    quiet_pcm = (np.sin(2 * np.pi * 60.0 * t) * 12).astype(np.int16)
    with wave.open(noise_buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr_48k)
        wf.writeframes(quiet_pcm.tobytes())

    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    assert bridge._transcribe_raw_wav_bytes(noise_buf.getvalue()) == ""

    # 4. Geo-block error heading rejection & application problem note recording
    cleaned_title, cleaned_co = bridge._clean_job_title_and_company(
        "Ladders is currently available only in the United States and Canada. We're sorry for the inconvenience.",
        "Ladders",
    )
    assert "available only in" not in cleaned_title.lower()

    issue_state = bridge.execute_action(
        "record_job_application_issue",
        {
            "canonical_url": "https://www.theladders.com/linkedin/89510643?src=LinkedIn",
            "title": "Lead Product Manager",
            "company_name": "Ladders",
            "location": "United States (Remote)",
            "reason": "Geo-restricted or region-blocked page: Ladders is currently available only in the United States and Canada.",
            "kind": "geo_restricted",
        },
    )
    assert issue_state["recorded_issue"]["kind"] == "geo_restricted"
    ladders_job = next(j for j in issue_state["jobs"] if j["company_name"] == "Ladders")
    assert ladders_job["title"] == "Lead Product Manager"
    assert "Geo-restricted" in ladders_job["application_issue"]["reason"]
    assert "Issue: Geo-restricted" in ladders_job["filter_summary"]
    assert "Application Issue / Note" in ladders_job["screening_answers"]


def test_dawn_apply_cta_gmail_otp_registration_and_target_company_pdf_regeneration(tmp_path: Path) -> None:
    content_js = Path("packaging/extensions/autoapply_companion/content.js").read_text(encoding="utf-8")

    # 1. Career portal CTA button recognition ("Apply to this Job", ".jvl-btn-apply", arrow stripping)
    assert "/^apply to this job$/i" in content_js
    assert ".jvl-btn-apply" in content_js
    assert "dawnjobapp.com" in content_js

    # 2. Registration & Gmail OTP verification flow in content.js
    assert "async function maybeHandleRegistrationAndEmailOtpFlow" in content_js
    assert "fetch_gmail_verification_code" in content_js
    assert ".dsp-code-box-new" in content_js

    # 3. Skip image-only / video-only file inputs when attaching Resume PDF
    assert "isImageOrVideoOnly" in content_js

    # 4. Placeholder "Target Company" / "Employer" never overwrites real company & regenerates PDF with real company name
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    state1 = bridge.execute_action(
        "companion_prepare_and_prefill_job",
        {
            "url": "https://dawnjobapp.com/job/post/9995",
            "title": "Senior Product Manager, AI-enabled EdTech Solutions",
            "company": "Target Company",
            "description": "Senior Product Manager role.",
        },
    )
    pkg1 = state1["prefill_package"]
    assert "Target-Company" not in pkg1["documents"]["resume"]["filename"]
    assert "Application" in pkg1["documents"]["resume"]["filename"]

    # Subsequent call on the same canonical job with real company name "Impacter Pathway" must update company & regenerate PDF
    state2 = bridge.execute_action(
        "companion_prepare_and_prefill_job",
        {
            "url": "https://dawnjobapp.com/job/post/9995",
            "title": "Senior Product Manager, AI-enabled EdTech Solutions",
            "company": "Impacter Pathway",
            "description": "Senior Product Manager at Impacter Pathway.",
        },
    )
    pkg2 = state2["prefill_package"]
    assert pkg2["company_name"] == "Impacter Pathway"
    assert "Impacter-Pathway" in pkg2["documents"]["resume"]["filename"]


def test_jobs_subtabs_pipeline_eligibility_and_followup_outreach_tracker(tmp_path: Path) -> None:
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")

    # 1. Verify top Subtabs in JobsWorkspaceView and Messages section
    assert '"Job Tracker"' in swift_src
    assert '"Messages"' in swift_src
    assert '"Job Boards"' in swift_src

    # 2. Verify Pipeline Stages (NOT APPLIED, APPLYING, SUBMITTED, FAILED) & Eligibility (Eligible, Not Eligible)
    assert '"NOT APPLIED"' in swift_src
    assert '"APPLYING"' in swift_src
    assert '"SUBMITTED"' in swift_src
    assert '"FAILED"' in swift_src
    assert '"STAGE"' in swift_src
    assert "Revert to" in swift_src
    assert "Not Eligible" in swift_src

    # 3. Verify Follow-Up & Outreach Tracker actions and pipeline stages in AppWorkspaceManager
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    st = bridge.execute_action(
        "add_job_posting",
        {
            "canonical_url": "https://boards.greenhouse.io/acme/jobs/12345",
            "company_name": "Acme AI",
            "title": "Senior Product Manager",
            "workplace_mode": "remote",
            "country": "US",
            "salary_max_usd": 220000,
        },
    )
    job = st["jobs"][0]
    job_id = job["job_id"]
    assert job["pipeline_stage"] == "not_applied"
    assert job["eligibility_status"] == "eligible"

    # Transition pipeline stage: not_applied -> applying -> failed -> submitted
    st_applying = bridge.execute_action("set_job_pipeline_stage", {"job_id": job_id, "pipeline_stage": "applying"})
    assert st_applying["jobs"][0]["pipeline_stage"] == "applying"

    st_failed = bridge.execute_action(
        "set_job_pipeline_stage",
        {"job_id": job_id, "pipeline_stage": "failed", "reason": "CAPTCHA / OTP portal timeout"},
    )
    assert st_failed["jobs"][0]["pipeline_stage"] == "failed"
    assert "CAPTCHA" in st_failed["jobs"][0]["failure_reason"]

    st_inelig = bridge.execute_action(
        "set_job_eligibility",
        {"job_id": job_id, "eligible": False, "reason": "US on-site required"},
    )
    assert st_inelig["jobs"][0]["eligible"] is False
    assert st_inelig["jobs"][0]["eligibility_status"] == "not_eligible"

    # Log a direct reachout event and verify it appears in outreach_tracker
    st_outreach = bridge.execute_action(
        "log_outreach_event",
        {
            "company": "Acme AI",
            "role": "Senior Product Manager",
            "contact_name": "Jane Doe",
            "channel": "linkedin_dm",
            "contact_value": "https://www.linkedin.com/in/janedoe/",
            "subject": "Senior Product Manager role at Acme AI",
            "message_text": "Hi Jane, thanks for connecting! I applied for the Senior PM role at Acme AI.",
            "status_category": "verified_sent",
        },
    )
    ot = st_outreach["outreach_tracker"]
    assert ot["summary"]["verified_sent_count"] >= 1
    assert any(e["contact_name"] == "Jane Doe" and e["company"] == "Acme AI" for e in ot["events"])

    # 4. Verify Settings tab cleanup: no ugly badges ("Auto-Saved", "Configured", salary range badge),
    # collapsible Danger Zone for Workspace Data & Uninstaller, and no "(CapSolver pinned)" action notice
    assert 'badgeText: "Auto-Saved"' not in swift_src
    assert 'StatusBadge(text: "Auto-Saved"' not in swift_src
    assert 'itemId: "workspace_danger_zone"' in swift_src
    assert '"DANGER ZONE"' in swift_src
    assert "isDangerZone: true" in swift_src
    assert "struct WizardStepFooterBar: View" in swift_src
    assert "struct LanguageModelsAccordionCard: View" in swift_src
    assert 'itemId: "language_models"' in swift_src
    assert "LanguageModelsAccordionCard(store: store, expandedId: $store.expandedWorkPrefItemId)" in swift_src
    assert 'title: "Master Resume"' in swift_src
    assert 'title: "My Resumes"' in swift_src
    assert 'title: "Generate Resume"' in swift_src
    assert "struct EllipsisActionMenuButton" in swift_src
    assert '"Facts Used"' not in swift_src

    st_browser = bridge.execute_action("launch_browser_session", {"target": "job_search", "dry_run": True})
    assert "CapSolver pinned" not in str(st_browser.get("action_notice") or "")

    # 5. Verify KB ingestion progress bar, top-level '# Interview Notes' header, and unified Standard Q&A Bank
    assert "kbIngestProgressFraction" in swift_src
    assert "kbIngestProgressMessage" in swift_src
    qa_sec = next(s for s in st_browser["knowledge_base"]["sections"] if s["id"] == "qa_bank")
    qa_md = qa_sec["markdown"]
    assert "# Standard Application Q&A Bank" in qa_md
    assert "# Interview & Screening Q&A" in qa_md
    assert "## Interview & Screening Q&A" not in qa_md
    assert "### " not in qa_md


def test_job_pipeline_stage_revert_from_submitted_and_dedupe_timeline(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    st0 = bridge.execute_action(
        "add_job_posting",
        {
            "canonical_url": "https://boards.greenhouse.io/dawn/jobs/99999",
            "company_name": "Dawn",
            "title": "AI Product Manager",
            "workplace_mode": "remote",
            "country": "US",
            "salary_max_usd": 200000,
        },
    )
    job_id = st0["jobs"][0]["job_id"]

    # Move to applying, then submitted
    st1 = bridge.execute_action("set_job_pipeline_stage", {"job_id": job_id, "pipeline_stage": "applying"})
    job1 = next(j for j in st1["jobs"] if j["job_id"] == job_id)
    assert job1["pipeline_stage"] == "applying"

    st2 = bridge.execute_action("set_job_pipeline_stage", {"job_id": job_id, "pipeline_stage": "submitted"})
    job2 = next(j for j in st2["jobs"] if j["job_id"] == job_id)
    assert job2["pipeline_stage"] == "submitted"
    assert job2["previous_pipeline_stage"] == "applying"
    assert job2["remote_receipt_id"] is not None

    # Revert back to previous stage (applying)
    st3 = bridge.execute_action("revert_job_pipeline_stage", {"job_id": job_id})
    job3 = next(j for j in st3["jobs"] if j["job_id"] == job_id)
    assert job3["pipeline_stage"] == "applying"
    assert job3["remote_receipt_id"] is None

    # Also test clicking not_applied directly after submitted
    bridge.execute_action("set_job_pipeline_stage", {"job_id": job_id, "pipeline_stage": "submitted"})
    st4 = bridge.execute_action("set_job_pipeline_stage", {"job_id": job_id, "pipeline_stage": "not_applied"})
    job4 = next(j for j in st4["jobs"] if j["job_id"] == job_id)
    assert job4["pipeline_stage"] == "not_applied"
    assert job4["remote_receipt_id"] is None
    stage_moves = [t for t in job4["timeline"] if "pipeline stage to" in t]
    assert len(stage_moves) == 1


def test_job_boards_catalog_operational_checkbox_and_exclusion(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    st0 = bridge.get_full_workspace_state()
    boards = st0["job_boards"]
    assert len(boards) == 56

    operational = [b for b in boards if not b["excluded"] and b["operational"]]
    primary_needs_setup = [b for b in boards if not b["excluded"] and not b["operational"] and b["is_primary"]]
    other_boards = [b for b in boards if not b["excluded"] and not b["operational"] and not b["is_primary"]]
    excluded = [b for b in boards if b["excluded"]]

    assert len(operational) == 5
    assert {b["id"] for b in operational} == {"linkedin", "hh", "greenhouse", "lever", "ashby"}
    assert len(primary_needs_setup) == 21
    assert len(other_boards) == 30
    assert len(excluded) == 0

    # Toggle Wellfound from primary_needs_setup -> operational
    st1 = bridge.execute_action("toggle_job_board_operational", {"board_id": "wellfound", "operational": True})
    wf1 = next(b for b in st1["job_boards"] if b["id"] == "wellfound")
    assert wf1["operational"] is True
    assert wf1["excluded"] is False

    # Exclude Wellfound from Agent -> moves to excluded
    st2 = bridge.execute_action("set_job_board_excluded", {"board_id": "wellfound", "excluded": True})
    wf2 = next(b for b in st2["job_boards"] if b["id"] == "wellfound")
    assert wf2["excluded"] is True
    assert wf2["operational"] is False

    # Re-include Wellfound back into Agent
    st3 = bridge.execute_action("set_job_board_excluded", {"board_id": "wellfound", "excluded": False, "operational": True})
    wf3 = next(b for b in st3["job_boards"] if b["id"] == "wellfound")
    assert wf3["excluded"] is False
    assert wf3["operational"] is True


def test_followup_tracker_main_tab_chat_aggregator_and_jev_classification(tmp_path: Path) -> None:
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")

    # 1. Verify Messages (FollowUpTrackerWorkspaceView) is a dedicated top-level NavigationSection and standalone view
    assert 'case followUpTracker = "Messages"' in swift_src
    assert "struct FollowUpTrackerWorkspaceView: View" in swift_src
    assert "FollowUpTrackerWorkspaceView(store: store)" in swift_src
    assert "AI Draft Follow-Up" in swift_src
    assert "Queue to Send" in swift_src
    assert "Send Follow-Up" in swift_src
    assert "Sync Messages" in swift_src
    assert "Blocked Addresses" in swift_src

    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    # 2. Send an initial Email reachout via send_or_queue_thread_message
    st1 = bridge.execute_action(
        "send_or_queue_thread_message",
        {
            "company": "Anthropic",
            "role": "Staff AI Product Manager",
            "contact_name": "Sarah Chen",
            "contact_handle": "sarah.chen@anthropic.com",
            "channel": "email",
            "subject": "Staff AI Product Manager — Alex Mercer",
            "message_text": "Hi Sarah, I recently applied for the Staff AI Product Manager position at Anthropic.",
            "mode": "send_now",
        },
    )
    threads1 = st1["outreach_tracker"]["threads"]
    anth_thread = next(t for t in threads1 if t["company"] == "Anthropic")
    thread_id = anth_thread["id"]
    assert anth_thread["channel"] == "email"
    assert len(anth_thread["messages"]) == 1
    assert anth_thread["messages"][0]["sender_role"] == "me"
    assert anth_thread["action_required"] is False

    # 3. Simulate an inbound reply from Sarah asking to schedule an interview call & run JEV classification
    st2 = bridge.execute_action(
        "scan_and_classify_inbound_messages",
        {
            "inbound_message": {
                "thread_id": thread_id,
                "company": "Anthropic",
                "role": "Staff AI Product Manager",
                "contact_name": "Sarah Chen",
                "contact_handle": "sarah.chen@anthropic.com",
                "channel": "email",
                "subject": "Re: Staff AI Product Manager — Alex Mercer",
                "body": "Hi Alex, thanks for reaching out! Would you have availability for a 30-minute intro interview call this week?",
            }
        },
    )
    anth_thread2 = next(t for t in st2["outreach_tracker"]["threads"] if t["id"] == thread_id)
    assert len(anth_thread2["messages"]) == 2
    assert anth_thread2["messages"][1]["sender_role"] == "them"
    assert anth_thread2["action_required"] is True
    assert anth_thread2["jev_model"] == "~typesafe/jev-latest"
    assert "action_required" in anth_thread2["jev_classification"]
    assert anth_thread2["jev_label"] in ("Real Interview", "Action Required")

    # 4. Generate an AI follow-up / reply draft from the control panel
    st3 = bridge.execute_action("draft_thread_followup", {"thread_id": thread_id})
    anth_thread3 = next(t for t in st3["outreach_tracker"]["threads"] if t["id"] == thread_id)
    assert "Sarah" in anth_thread3["draft_text"]
    assert "Anthropic" in anth_thread3["draft_text"]

    # 5. Queue a user-edited reply on LinkedIn and verify multi-message thread + queue status
    st4 = bridge.execute_action(
        "send_or_queue_thread_message",
        {
            "thread_id": thread_id,
            "company": "Anthropic",
            "role": "Staff AI Product Manager",
            "contact_name": "Sarah Chen",
            "contact_handle": "sarah.chen@anthropic.com",
            "channel": "email",
            "subject": anth_thread3["draft_subject"],
            "message_text": anth_thread3["draft_text"],
            "mode": "queue",
        },
    )
    anth_thread4 = next(t for t in st4["outreach_tracker"]["threads"] if t["id"] == thread_id)
    assert len(anth_thread4["messages"]) == 3
    assert anth_thread4["messages"][2]["sender_role"] == "me"
    assert "Queued" in anth_thread4["messages"][2]["delivery_status"]
    assert anth_thread4["action_required"] is False
    assert st4["outreach_tracker"]["summary"]["queued_messages_count"] >= 1


def test_linkedin_inline_expand_button_next_to_save_and_apply_when_collapsed() -> None:
    content_js = Path("packaging/extensions/autoapply_companion/content.js").read_text(encoding="utf-8")
    assert "function syncLinkedInInlineExpandButtons()" in content_js
    assert "aa-linkedin-inline-expand-btn" in content_js
    assert "function syncCollapsedExpandPill()" in content_js
    assert 'button.jobs-save-button' in content_js
    assert 'isCollapsed && !hasInlineExpandBtn ? "visible" : ""' in content_js


def test_desktop_feedback_bug_improvement_screenshots_and_media_submission(tmp_path: Path) -> None:
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert 'Label("Share Feedback", systemImage: "megaphone.fill")' in swift_src
    assert "struct FeedbackSubmissionModalView: View" in swift_src
    assert "capture_feedback_context_screenshots" in swift_src
    assert "submit_user_feedback" in swift_src

    app_support = tmp_path / "app_support"
    bridge = AppWorkspaceManager(app_support_dir=app_support)

    # Create sample Desktop & Browser screenshots and user-appended image + video files
    desktop_shot = tmp_path / "desktop_shot.png"
    desktop_shot.write_bytes(b"\x89PNG\r\n\x1a\nDESKTOP_MOCK")
    browser_shot = tmp_path / "browser_shot.png"
    browser_shot.write_bytes(b"\x89PNG\r\n\x1a\nBROWSER_MOCK")
    user_video = tmp_path / "screen_recording.mp4"
    user_video.write_bytes(b"\x00\x00\x00\x18ftypmp42VIDEO_MOCK")
    user_image = tmp_path / "extra_note.png"
    user_image.write_bytes(b"\x89PNG\r\n\x1a\nEXTRA_IMAGE")

    st1 = bridge.execute_action(
        "capture_feedback_context_screenshots",
        {
            "desktop_screenshot_path": str(desktop_shot),
            "app_section": "Jobs",
        },
    )
    assert st1["feedback_staging"]["desktop_screenshot_path"] == str(desktop_shot)

    st2 = bridge.execute_action(
        "submit_user_feedback",
        {
            "classification": "improvement",
            "comment": "Please add a keyboard shortcut for the Share Feedback modal and keep both screenshots.",
            "app_section": "Jobs",
            "browser_url": "https://www.linkedin.com/jobs/collections/recommended/",
            "browser_title": "Recommended Jobs | LinkedIn",
            "include_desktop_screenshot": True,
            "include_browser_screenshot": True,
            "desktop_screenshot_path": str(desktop_shot),
            "browser_screenshot_path": str(browser_shot),
            "attachments": [
                {"path": str(user_video), "name": "screen_recording.mp4", "kind": "video"},
                {"path": str(user_image), "name": "extra_note.png", "kind": "image"},
            ],
        },
    )
    submissions = st2["feedback_submissions"]
    assert len(submissions) == 1
    sub = submissions[0]
    assert sub["classification"] == "improvement"
    assert sub["classification_label"] == "Improvement"
    assert "keyboard shortcut" in sub["comment"]
    assert len(sub["attachments"]) == 4  # Desktop screenshot + Browser screenshot + video + image
    kinds = [a["kind"] for a in sub["attachments"]]
    assert "video" in kinds
    assert "image" in kinds
    manifest_file = Path(sub["bundle_path"]) / "manifest.json"
    assert manifest_file.exists()


def test_openai_codex_model_catalog_and_exact_provider_awareness(tmp_path: Path) -> None:
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert "static let codexCatalog: [AIModelChoiceItem]" in swift_src
    assert '"openai-codex/gpt-6.1-sol"' in swift_src
    assert '"openai-codex/gpt-6-astra"' in swift_src
    assert '"openai-codex/gpt-6.1-terra"' in swift_src
    assert '"openai-codex/gpt-6-sol"' in swift_src
    assert '"openai-codex/gpt-6-luna"' in swift_src
    assert '"openai-codex/gpt-5.6-sol"' in swift_src
    assert '"openai-codex/gpt-5.6-terra"' in swift_src
    assert '"openai-codex/gpt-5.6-luna"' in swift_src
    assert 'Provider: OpenAI Codex (ChatGPT Subscription — $0 Token Cost)' in swift_src

    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    assert bridge._normalize_codex_model_id("openai-codex/gpt-5.4") == "openai-codex/gpt-6.1-sol"
    assert bridge._normalize_codex_model_id("openai-codex/gpt-6-astra") == "openai-codex/gpt-6-astra"
    assert bridge._codex_wire_slug("openai-codex/gpt-6.1-sol") == "gpt-6.1-sol"

    bridge.execute_action(
        "save_model_selection",
        {"logic_model": "openai-codex/gpt-6.1-sol", "logic_reasoning_effort": "medium"},
    )
    st = bridge.execute_action(
        "send_hermes_chat_message",
        {
            "message": "are you using with open router or through codex? And what is the exact model that you are using for logic? And what is the context window?"
        },
    )
    sessions = st["hermes_chat"]["sessions"]
    last_msg = sessions[0]["messages"][-1]["content"]
    assert "OpenAI Codex (ChatGPT Subscription OAuth" in last_msg
    assert "openai-codex/gpt-6.1-sol" in last_msg
    assert "500,000 tokens" in last_msg


def test_messages_header_layout_simplified_labels_and_robot_gmail_folders(tmp_path: Path) -> None:
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert 'title: "Submitted"' in swift_src
    assert 'Text("Submitted")' in swift_src
    assert 'Text("Rejected")' in swift_src
    assert "Submitted Confirmation · Folder:" not in swift_src
    assert "Rejected · Folder:" not in swift_src
    assert "Company: \\(cleanComp)" not in swift_src

    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    sub_cls = bridge._jev_classify_conversation_thread(
        channel="email",
        company="RepSpark",
        role="Product Manager - Integrations",
        contact_name="Repspark Hiring Team",
        subject="Re: Application: Product Manager - Integrations - Alex Mercer",
        messages=[
            {
                "id": "m1",
                "sender_role": "me",
                "subject": "Application: Product Manager - Integrations - Alex Mercer",
                "body": "I am applying for the Product Manager - Integrations role.",
            },
            {
                "id": "m2",
                "sender_role": "them",
                "subject": "Re: Application: Product Manager - Integrations - Alex Mercer",
                "body": "Hi there, Thank you for reaching out and for your interest in opportunities with RepSpark!",
            },
        ],
        delivery_state="sent",
    )
    assert sub_cls["jev_classification"] == "submitted_confirmation"
    assert sub_cls["jev_label"] == "Submitted"
    assert sub_cls["gmail_folder"] == "🤖 Job Application Submitted"
    assert sub_cls["action_required"] is False

    rej_cls = bridge._jev_classify_conversation_thread(
        channel="email",
        company="PostHog",
        role="Product Manager",
        contact_name="PostHog Hiring Team",
        subject="Update on your application",
        messages=[
            {
                "id": "r1",
                "sender_role": "them",
                "subject": "Update on your application",
                "body": "Thank you for applying to PostHog. Unfortunately we will not be moving forward with your application.",
            }
        ],
        delivery_state="sent",
    )
    assert rej_cls["jev_classification"] == "rejected"
    assert rej_cls["jev_label"] == "Rejected"
    assert rej_cls["gmail_folder"] == "🤖 Job Application Rejected"
    assert rej_cls["action_required"] is False


def test_email_quote_stripping_and_context_menu_removal_for_threads_and_resumes(tmp_path: Path) -> None:
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert 'Label("Remove Thread from List", systemImage: "trash")' in swift_src
    assert 'Label("Remove Resume from List", systemImage: "trash")' in swift_src
    assert "private func stripQuotedEmailReply(_ rawBody: String) -> String" in swift_src
    assert "private func threadRowContextMenuItems(_ thread: OutreachThreadItem)" in swift_src
    assert "private func myResumeRowContextMenuItems(_ doc: DocumentArtifactItem)" in swift_src

    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    # 1. Verify quoted reply stripping on exact Alivo / Max Meade message format
    raw_alivo_reply = (
        "Hey Alex,\n\n"
        "Nice to meet you and thank you for reaching out. Can you tell me what interests you about Alivo and what compensation you are looking for?\n\n"
        "Thank you,\n\n"
        "Max Meade\n"
        "CPO at Alivo\n\n"
        "On Wed, Oct 14, 2026 at 4:36 AM, < alex.mercer@example.com <mailto:alex.mercer@example.com> > wrote:\n\n"
        "> \n"
        "> Hello,\n"
        "> \n"
        "> Please find my resume and cover letter attached for the Product Manager /\n"
        "> Product Analyst role at Alivo.\n"
    )
    cleaned = bridge._sanitize_email_body_text(raw_alivo_reply)
    assert "Can you tell me what interests you about Alivo" in cleaned
    assert "Max Meade" in cleaned
    assert "On Wed, Oct 14, 2026" not in cleaned
    assert "Please find my resume and cover letter attached" not in cleaned
    assert "<mailto:" not in cleaned

    # 2. Verify thread deletion (delete_outreach_thread) removes from list and persists in removed_outreach_threads
    st_logged = bridge.execute_action(
        "send_or_queue_thread_message",
        {
            "thread_id": "thr_email_alivo_max_meade",
            "company": "Alivo",
            "role": "Product Manager",
            "contact_name": "Max Meade",
            "contact_handle": "max@alivo.ai",
            "channel": "email",
            "subject": "Re: Product Manager / Product Analyst — Alex Mercer",
            "message_text": raw_alivo_reply,
            "mode": "queue",
        },
    )
    threads_before = st_logged["outreach_tracker"]["threads"]
    alivo_th = next((t for t in threads_before if t["id"] == "thr_email_alivo_max_meade"), None)
    assert alivo_th is not None
    assert "On Wed, Oct 14, 2026" not in alivo_th["messages"][-1]["body"]

    st_after_del = bridge.execute_action("delete_outreach_thread", {"thread_id": "thr_email_alivo_max_meade"})
    threads_after = st_after_del["outreach_tracker"]["threads"]
    assert not any(t["id"] == "thr_email_alivo_max_meade" for t in threads_after)

    # 3. Verify generated resume deletion (delete_generated_document) removes from documents list
    raw_state = bridge._load_raw_state()
    raw_state.setdefault("documents", []).append(
        {
            "artifact_id": "doc_test_alivo_pm",
            "job_id": "job_test_alivo",
            "title": "Product Manager — Alivo",
            "created_at": "2026-10-28 12:00",
            "estimated_pages": 2,
            "resume_markdown": "# Alex Mercer\nProduct Manager",
            "cover_letter_markdown": "Dear Alivo Team,",
            "pdf_path": "",
            "docx_path": "",
        }
    )
    bridge._save_raw_state(raw_state)
    docs_before = bridge.get_full_workspace_state()["documents"]
    assert any(d["artifact_id"] == "doc_test_alivo_pm" for d in docs_before)
    st_after_doc_del = bridge.execute_action("delete_generated_document", {"document_id": "doc_test_alivo_pm"})
    docs_after = st_after_doc_del["documents"]
    assert not any(d["artifact_id"] == "doc_test_alivo_pm" for d in docs_after)

    # 4. Verify Companion extension hh.ru viewport fitting (no sidebar overlay) and automatic cookie banner acceptance
    ext_src = Path("packaging/extensions/autoapply_companion/content.js").read_text(encoding="utf-8")
    assert "function autoAcceptCookieBanners()" in ext_src
    assert 'data-qa="cookies-policy-informer-accept"' in ext_src
    assert '[class*="magritte-grid-container"]' in ext_src
    assert ".bloko-columns-wrapper" in ext_src
    assert "rect.right > availW" in ext_src


def test_separate_action_required_vs_followup_and_context_aware_drafting(tmp_path: Path) -> None:
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert "public var isFollowUp: Bool" in swift_src
    assert 'case "followup": matchesAction = th.isFollowUp' in swift_src
    assert 'id: "followup"' in swift_src
    assert "Text(thread.actionRequiredDisplayLabel)" in swift_src
    assert 'Text("Follow-Up")' in swift_src

    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    # 1. Xwiki scenario: Alex applied/messaged first ('me'), then received an auto-response / acknowledgment ('them')
    #    mentioning "we will contact you within a maximum of 15 days to schedule a first discussion".
    #    Must be classified as Follow-Up (waiting on them), NOT Action Required, and its drafted follow-up
    #    must ask if there are any updates/news or if they need anything from Alex's end.
    xwiki_messages = [
        {
            "id": "m1",
            "sender_role": "me",
            "sender_name": "Alex Mercer",
            "sender_handle": "alex.mercer@example.com",
            "subject": "Application for Product Manager — Alex Mercer",
            "body": "Hello XWiki SAS Hiring Team,\n\nPlease find my resume and cover letter attached for the Product Manager position at XWiki SAS.",
            "timestamp": "2026-10-14 04:41",
            "delivery_status": "Verified Sent",
        },
        {
            "id": "m2",
            "sender_role": "them",
            "sender_name": "Alexandra Moraru-Popovici",
            "sender_handle": "jobs@xwiki.com",
            "subject": "Re: Application for Product Manager — Alex Mercer",
            "body": (
                "Hello,\n\n"
                "Thank you for your interest in the Product Manager position at XWiki.\n\n"
                "We will now take a close look at your profile. If your application is successful, "
                "we will contact you within a maximum of 15 days to schedule a first discussion.\n\n"
                "Best regards,\n"
                "Alexandra Moraru-Popovici\n"
                "HR & Recruitment Officer at XWiki SAS"
            ),
            "timestamp": "2026-10-14 04:41",
            "delivery_status": "Inbound Reply",
        },
    ]
    xwiki_cls = bridge._jev_classify_conversation_thread(
        channel="email",
        company="Xwiki",
        role="Product Manager",
        contact_name="Alexandra Moraru-Popovici",
        subject="Re: Application for Product Manager — Alex Mercer",
        messages=xwiki_messages,
        delivery_state="replied",
    )
    assert xwiki_cls["action_required"] is False
    assert xwiki_cls["followup_needed"] is True
    assert xwiki_cls["jev_classification"] == "followup_after_ack"
    assert xwiki_cls["jev_label"] == "Follow-Up"

    # Seed Xwiki thread into conversation_threads with chronological [me, them] messages and stale draft
    raw = bridge._load_raw_state()
    raw["conversation_threads"] = [
        {
            "id": "thr_email_xwiki_alexandra_moraru_popovici",
            "company": "Xwiki",
            "role": "Product Manager",
            "contact_name": "Alexandra Moraru-Popovici",
            "contact_handle": "jobs@xwiki.com",
            "channel": "email",
            "subject": "Re: Application for Product Manager — Alex Mercer",
            "messages": xwiki_messages,
            "draft_text": "Hi Alexandra,\n\nThank you for reaching out regarding the Product Manager role at Xwiki. I would be glad to connect for a call.",
        }
    ]
    bridge._save_raw_state(raw)

    # Verify stale "Thank you for reaching out regarding ... I would be glad to connect for a call" draft is cleared automatically
    tracker_state = bridge.get_full_workspace_state()["outreach_tracker"]
    xwiki_thread = next(t for t in tracker_state["threads"] if t["company"].lower() == "xwiki")
    assert xwiki_thread["action_required"] is False
    assert xwiki_thread["followup_needed"] is True
    assert xwiki_thread["jev_classification"] == "followup_after_ack"
    assert "Thank you for reaching out regarding" not in xwiki_thread["draft_text"]

    # Draft fresh context-aware follow-up for Xwiki
    drafted_state = bridge.execute_action(
        "draft_thread_followup",
        {
            "thread_id": xwiki_thread["id"],
            "company": "Xwiki",
            "role": "Product Manager",
            "contact_name": "Alexandra Moraru-Popovici",
            "channel": "email",
            "subject": "Re: Application for Product Manager — Alex Mercer",
        },
    )
    updated_xwiki = next(t for t in drafted_state["outreach_tracker"]["threads"] if t["company"].lower() == "xwiki")
    draft = updated_xwiki["draft_text"]
    assert "Thank you for reaching out regarding" not in draft
    assert "I would be glad to connect for a call" not in draft
    assert "follow up" in draft.lower()
    assert ("updates" in draft.lower() or "news" in draft.lower())
    assert "from my end" in draft.lower()

    # 2. Action Required scenario: Employer explicitly asks candidate to complete a portal/video step or answer screening questions
    alivo_cls = bridge._jev_classify_conversation_thread(
        channel="email",
        company="Alivo",
        role="Product Manager",
        contact_name="Max Meade",
        subject="Re: Product Manager / Product Analyst — Alex Mercer",
        messages=[
            {
                "sender_role": "me",
                "body": "Hello, Please find my resume and cover letter attached for the Product Manager role at Alivo.",
            },
            {
                "sender_role": "them",
                "body": "Hey Alex, Nice to meet you! Can you tell me what interests you about Alivo and what compensation you are looking for?",
            },
        ],
        delivery_state="replied",
    )
    assert alivo_cls["action_required"] is True
    assert alivo_cls["followup_needed"] is False
    assert alivo_cls["jev_classification"] == "action_required_details_requested"
    assert alivo_cls["jev_label"] == "Details Requested"

    # 3. Waiting on employer after candidate replied ('them' -> 'me') is Follow-Up, not Action Required
    waiting_cls = bridge._jev_classify_conversation_thread(
        channel="linkedin",
        company="Automindz",
        role="AI Product Manager",
        contact_name="Niklas Huetzen",
        subject="AI Product Manager at Automindz",
        messages=[
            {
                "sender_role": "them",
                "body": "Hi Alex, would you be open to sharing your CV for our AI Product Manager role?",
            },
            {
                "sender_role": "me",
                "body": "Hi Niklas, thanks for reaching out! I have attached my CV and would be happy to discuss.",
            },
        ],
        delivery_state="replied",
    )
    assert waiting_cls["action_required"] is False
    assert waiting_cls["followup_needed"] is True
    assert waiting_cls["jev_classification"] == "followup_waiting_reply"
    assert waiting_cls["jev_label"] == "Follow-Up"

    # 4. Verify automatic password capture on login, 10-second countdown overlay with Don't Save CTA, and login autofill
    ext_src = Path("packaging/extensions/autoapply_companion/content.js").read_text(encoding="utf-8")
    assert "aa-pwd-countdown-overlay" in ext_src
    assert "Password will be saved in ${remainingSec} second" in ext_src
    assert 'id="aa-pwd-dont-save-btn"' in ext_src
    assert "Don't Save" in ext_src
    assert "function startTenSecondPasswordSaveCountdown(" in ext_src
    assert "function commitPendingPasswordToVault(" in ext_src
    assert "function maybeAutofillSavedSiteLogin(" in ext_src
    assert 'id="aa-btn-preview-kb"' in ext_src
    assert 'id="aa-btn-dismiss-kb"' in ext_src
    assert "data-remove-kb-field=" in ext_src
    assert "function buildKbUpdateBoxHTML(" in ext_src

    hh_save_st = bridge.execute_action(
        "save_password_entry",
        {
            "website_name": "hh.ru",
            "website_url": "https://hh.ru/account/login?backurl=%2F",
            "username": "alex.mercer@example.com",
            "password": "HhLoginPass!2026",
            "description": "Auto-saved after login on hh.ru",
            "auto_registered": False,
        },
    )
    saved_hh = hh_save_st["saved_password_entry"]
    assert saved_hh["website_name"] == "HeadHunter (hh.ru)"
    assert saved_hh["website_url"] == "https://hh.ru"
    assert saved_hh["username"] == "alex.mercer@example.com"
    assert saved_hh["password"] == "HhLoginPass!2026"

    # 5. Verify AI Chat rename, Activity tab right under AI Chat, Automations & Activity History tabs (no "Worker Lanes" or "LIVE 5" clutter), and Board View drag-and-drop
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert 'case agentChat = "AI Chat"\n    case activity = "Activity"' in swift_src
    assert "ActivityWorkspaceView(store: store)" in swift_src
    assert 'title: "Automations"' in swift_src
    assert 'title: "Activity History"' in swift_src
    assert "Worker Lanes & Periodic Tasks" not in swift_src
    assert "LIVE • " not in swift_src
    assert "struct KanbanColumnDropDelegate: DropDelegate" in swift_src
    assert "public func moveJobToStage(" in swift_src
    assert "delegate: KanbanColumnDropDelegate(columnKey: col.key, store: store)" in swift_src

    # Seed one submitted job, one filled-not-submitted job, and one outreach message
    st1 = bridge.execute_action(
        "add_job_posting",
        {
            "company_name": "Anthropic",
            "title": "Product Manager, Claude Code",
            "canonical_url": "https://boards.greenhouse.io/anthropic/jobs/4001",
        },
    )
    sub_jid = st1["jobs"][0]["job_id"]
    bridge.execute_action(
        "set_job_pipeline_stage",
        {
            "job_id": sub_jid,
            "pipeline_stage": "submitted",
        },
    )
    st2 = bridge.execute_action(
        "add_job_posting",
        {
            "company_name": "Stripe",
            "title": "Senior Product Manager, Billing",
            "canonical_url": "https://jobs.lever.co/stripe/9002",
        },
    )
    fill_jid = st2["jobs"][0]["job_id"]
    bridge.execute_action(
        "set_job_pipeline_stage",
        {
            "job_id": fill_jid,
            "pipeline_stage": "applying",
        },
    )
    bridge.execute_action(
        "log_outreach_event",
        {
            "company": "Linear",
            "role": "Product Manager",
            "contact_name": "Karri Saarinen",
            "channel": "linkedin_dm",
            "message_text": "Hi Karri, excited about the Product Manager role at Linear!",
            "status": "Verified Sent",
        },
    )

    full_state = bridge.get_full_workspace_state()
    ac = full_state["activity_center"]
    assert ac["engine_status"]["is_running"] is True
    assert ac["engine_status"]["status_label"] == "Running"
    assert ac["summary"]["applied_count"] >= 1
    assert ac["summary"]["filled_not_submitted_count"] >= 1
    assert ac["summary"]["messaged_count"] >= 1
    assert len(ac["worker_lanes"]) >= 5

    for lane in ac["worker_lanes"]:
        assert "cron" not in lane["title"].lower()
        assert "cron" not in lane["frequency_label"].lower()
        assert "cron" not in lane["category"].lower()

    categories_present = {item["category"] for item in ac["activities"]}
    assert "applied" in categories_present
    assert "filled_not_submitted" in categories_present
    assert "messaged" in categories_present

    # Toggle a periodic worker lane and verify override state
    first_lane_id = ac["worker_lanes"][0]["id"]
    first_lane_enabled = ac["worker_lanes"][0]["enabled"]
    toggled_state = bridge.execute_action(
        "toggle_periodic_task",
        {"task_id": first_lane_id, "enabled": not first_lane_enabled},
    )
    updated_lane = next(w for w in toggled_state["activity_center"]["worker_lanes"] if w["id"] == first_lane_id)
    assert updated_lane["enabled"] is (not first_lane_enabled)


def test_messages_aggregator_hh_imessage_and_ui_layout(tmp_path: Path, monkeypatch) -> None:
    import sqlite3

    # 1. Create a synthetic macOS Messages `chat.db` with both plain `text` and `attributedBody` binary streamtyped messages,
    #    plus a 2FA OTP shortcode message that should be filtered out.
    fake_chat_db = tmp_path / "chat.db"
    conn = sqlite3.connect(str(fake_chat_db))
    conn.execute("CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT)")
    conn.execute("CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, chat_identifier TEXT, display_name TEXT)")
    conn.execute(
        """
        CREATE TABLE message (
            ROWID INTEGER PRIMARY KEY,
            handle_id INTEGER,
            text TEXT,
            attributedBody BLOB,
            is_from_me INTEGER,
            date INTEGER,
            service TEXT
        )
        """
    )
    conn.execute("CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER)")

    conn.execute("INSERT INTO handle (ROWID, id) VALUES (1, '+14155550166')")
    conn.execute("INSERT INTO handle (ROWID, id) VALUES (2, '88291')")  # shortcode -> must be ignored
    conn.execute("INSERT INTO chat (ROWID, chat_identifier, display_name) VALUES (1, '+14155550166', 'Brett Crosby')")
    conn.execute("INSERT INTO chat (ROWID, chat_identifier, display_name) VALUES (2, '88291', '')")

    # Outbound text message
    conn.execute(
        "INSERT INTO message (ROWID, handle_id, text, attributedBody, is_from_me, date, service) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            10,
            1,
            "Hi Brett, I'm Alex Mercer. Following up on the Head of Growth role at AdZen AI.",
            None,
            1,
            782480000000000000,
            "iMessage",
        ),
    )
    conn.execute("INSERT INTO chat_message_join (chat_id, message_id) VALUES (1, 10)")

    # Inbound attributedBody message asking for a call (simulating macOS Ventura/Sonoma/Sequoia attributedBody storage)
    inbound_txt = "Hi Alex, this is Brett Crosby from AdZen AI. Let's schedule a quick call via Zoom this week!"
    inbound_bytes = inbound_txt.encode("utf-8")
    attr_blob = b"\x04\x0bstreamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x08NSString\x01\x94\x84\x01+" + bytes([len(inbound_bytes)]) + inbound_bytes + b"\x86\x84\x02iI"
    conn.execute(
        "INSERT INTO message (ROWID, handle_id, text, attributedBody, is_from_me, date, service) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (11, 1, None, attr_blob, 0, 782481000000000000, "iMessage"),
    )
    conn.execute("INSERT INTO chat_message_join (chat_id, message_id) VALUES (1, 11)")

    # 2FA OTP noise message
    conn.execute(
        "INSERT INTO message (ROWID, handle_id, text, attributedBody, is_from_me, date, service) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (12, 2, "Your verification code is 491029. Do not share this code.", None, 0, 782482000000000000, "SMS"),
    )
    conn.execute("INSERT INTO chat_message_join (chat_id, message_id) VALUES (2, 12)")
    conn.commit()
    conn.close()

    monkeypatch.setenv("AUTOAPPLY_MESSAGES_DB_PATH", str(fake_chat_db))
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    # 2. Send/log an HH chat message and an iMessage follow-up
    st_hh = bridge.execute_action(
        "send_or_queue_thread_message",
        {
            "company": "Метр квадратный",
            "role": "Product Manager",
            "contact_name": "Метр квадратный (Чат HH.ru)",
            "contact_handle": "https://hh.ru/vacancy/129963060",
            "channel": "hh",
            "subject": "HH.ru Чат • Product Manager",
            "message_text": "Здравствуйте! Откликнулся на вакансию Product Manager в Метр квадратный на hh.ru.",
            "mode": "send_now",
        },
    )
    threads = st_hh["outreach_tracker"]["threads"]

    hh_thread = next((t for t in threads if t["channel"] == "hh"), None)
    assert hh_thread is not None
    assert hh_thread["channel_label"] == "HH"
    assert hh_thread["company"] == "Метр квадратный"

    im_thread = next((t for t in threads if t["channel"] == "imessage"), None)
    assert im_thread is not None
    assert im_thread["channel_label"] == "iMessage"
    assert im_thread["contact_name"] == "Brett Crosby"
    assert len(im_thread["messages"]) == 2
    assert "Zoom" in im_thread["messages"][1]["body"]
    # Analyzed inbound text message asking for a Zoom call -> Action Required (Real Interview)!
    assert im_thread["action_required"] is True
    assert im_thread["jev_classification"] == "action_required_real_interview"
    assert im_thread["jev_label"] == "Real Interview"

    # Draft follow-up for HH and iMessage threads
    st_draft_hh = bridge.execute_action("draft_thread_followup", {"thread_id": hh_thread["id"]})
    assert "HH follow-up drafted" in st_draft_hh["action_notice"]

    st_draft_im = bridge.execute_action("draft_thread_followup", {"thread_id": im_thread["id"]})
    assert "iMessage follow-up drafted" in st_draft_im["action_notice"]

    # 3. Verify Swift UI changes for HH, iMessage, full-width top status filter bar, and frameless/dotless Activate License tab
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert 'title: "HH"' in swift_src
    assert 'title: "iMessage"' in swift_src
    assert 'Text("HH").tag("hh")' in swift_src
    assert 'Text("iMessage").tag("imessage")' in swift_src
    assert 'case "hh": matchesChannel = th.channel == "hh"' in swift_src
    assert 'case "imessage": matchesChannel = th.channel == "imessage"' in swift_src
    assert "Full-Width Status Filter Categories (Outside the narrow left column" in swift_src
    assert "Clean frameless row, no dot before countdown" in swift_src


def test_continuous_eligible_job_discovery_and_georgia_b2b_eligibility(tmp_path: Path) -> None:
    import json

    bridge = AppWorkspaceManager(tmp_path)
    raw = bridge._load_raw_state()
    bridge._upgrade_state_schema(raw)

    # Simulate candidate in Batumi, Georgia with empty residence_country and global_b2b_contractor=True
    raw["knowledge_base"]["profile_header"]["location"] = "Batumi, Georgia"
    prefs = raw["onboarding"]["preferences"]
    prefs["residence_country"] = ""
    prefs["authorized_countries"] = {"US": False, "CA": False, "UK": False, "EU": False, "DE": False, "AU": False}
    prefs["global_b2b_contractor"] = True
    prefs["work_auth_by_region"]["CA"] = "Citizen"

    raw["jobs"] = [
        {
            "job_id": "job_ge_remote_1",
            "direct_employer_id": "morpheus",
            "company_name": "Morpheus Talent Solutions",
            "title": "Senior Product Manager",
            "canonical_url": "https://www.linkedin.com/jobs/view/4428151535",
            "workplace_mode": "remote",
            "eligible_countries": ["GE"],
            "sponsorship_offered": True,
            "is_open": True,
            "salary_max_usd": 215000,
            "eligible": False,
            "eligibility_status": "not_eligible",
            "exclusion_reason": "Location or country of residence is not eligible for this role",
            "state": "ineligible",
            "pipeline_stage": "not_applied",
            "timeline": ["Discovered on LinkedIn"],
        },
        {
            "job_id": "job_us_only_1",
            "direct_employer_id": "anthropic",
            "company_name": "Anthropic",
            "title": "Product Manager, Claude Code",
            "canonical_url": "https://job-boards.greenhouse.io/anthropic/jobs/4985912008",
            "workplace_mode": "remote",
            "eligible_countries": ["US"],
            "sponsorship_offered": False,
            "is_open": True,
            "salary_max_usd": 240000,
            "eligible": False,
            "eligibility_status": "not_eligible",
            "exclusion_reason": "Work authorization is required for this role's location",
            "state": "ineligible",
            "pipeline_stage": "not_applied",
            "timeline": ["Discovered on Greenhouse"],
        },
    ]
    bridge._save_raw_state(raw)

    # Create a mock VB Jobs directory with verified-submissions.jsonl and prospects.jsonl
    vb_base = tmp_path / "vb_jobs_mock"
    vb_cont = vb_base / "continuation-20261015"
    vb_cont.mkdir(parents=True, exist_ok=True)
    (vb_cont / "verified-submissions.jsonl").write_text(
        json.dumps(
            {
                "status": "verified_submitted",
                "company": "Haut.AI",
                "role": "Lead Product Manager",
                "url": "https://haut.ai/careers/lead-product-manager",
                "platform": "Direct email",
                "submitted_at": "2026-10-28T09:33:33+00:00",
                "gmail_message_id": "1a181db949d26996",
                "outreach_result": "Sent verified",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (vb_cont / "prospects.jsonl").write_text(
        json.dumps(
            {
                "company": "Itransition",
                "role": "Technical Product Owner (TPO)",
                "url": "https://www.itransition.com/careers/technical-product-owner-tpo",
                "status": "public_preflight_candidate",
                "eligible_for_next_preflight": True,
                "discovered_utc": "2026-10-28T10:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    res = bridge.execute_action(
        "discover_and_sync_eligible_jobs",
        {
            "run_live_discovery": False,
            "vb_jobs_dir": str(vb_base),
            "discovered_jobs": [
                {
                    "company_name": "PostHog",
                    "title": "Product Manager — AI Platform",
                    "canonical_url": "https://jobs.ashbyhq.com/posthog/pm-ai",
                    "pipeline_stage": "not_applied",
                    "eligible": True,
                    "eligible_countries": ["GE", "CA"],
                }
            ],
        },
    )

    jobs_by_company = {j["company_name"]: j for j in res["jobs"]}
    # 1. Morpheus Talent Solutions (GE remote) is now Eligible!
    assert jobs_by_company["Morpheus Talent Solutions"]["eligible"] is True
    assert jobs_by_company["Morpheus Talent Solutions"]["eligibility_status"] == "eligible"
    assert jobs_by_company["Morpheus Talent Solutions"]["state"] == "ready_to_submit"

    # 2. Anthropic (US-only without sponsorship) remains Not Eligible
    assert jobs_by_company["Anthropic"]["eligible"] is False
    assert jobs_by_company["Anthropic"]["eligibility_status"] == "not_eligible"

    # 3. Synced verified submission (Haut.AI) and discovered eligible prospects (Itransition, PostHog) are Eligible
    assert jobs_by_company["Haut.AI"]["eligible"] is True
    assert jobs_by_company["Haut.AI"]["pipeline_stage"] == "submitted"
    assert jobs_by_company["Itransition"]["eligible"] is True
    assert jobs_by_company["Itransition"]["pipeline_stage"] == "not_applied"
    assert jobs_by_company["PostHog"]["eligible"] is True
    assert jobs_by_company["PostHog"]["pipeline_stage"] == "not_applied"

    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert "startPeriodicJobDiscoveryTimer()" in swift_src
    assert '"discover_and_sync_eligible_jobs"' in swift_src


def test_feedback_submission_posts_to_server_backend_without_client_bot_tokens(
    tmp_path: Path, monkeypatch
) -> None:
    import base64
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    bridge_src = Path("runtime/autoapply/app_bridge.py").read_text(encoding="utf-8")
    assert "AUTOAPPLY_FEEDBACK_TELEGRAM_BOT_TOKEN" not in bridge_src
    assert "telegram_bot_token" not in bridge_src
    assert "https://turboapply.ru/api/autoapply-feedback" in bridge_src

    received_requests: list[dict] = []

    class MockFeedbackHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or "0")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            received_requests.append({"path": self.path, "body": body})
            resp = json.dumps(
                {
                    "ok": True,
                    "feedback_id": body.get("feedback_id"),
                    "stored": True,
                    "notified_subscribers": 1,
                    "bot_username": "AutoApplyFeedbackBot",
                    "subscribe_url": "https://t.me/AutoApplyFeedbackBot",
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

    server = HTTPServer(("127.0.0.1", 0), MockFeedbackHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        monkeypatch.setenv("AUTOAPPLY_FEEDBACK_BACKEND_URL", f"http://127.0.0.1:{port}/api/autoapply-feedback")
        monkeypatch.setenv("AUTOAPPLY_FEEDBACK_ALLOW_TEST_HTTP", "1")

        shot_path = tmp_path / "desktop_shot.png"
        shot_bytes = b"\x89PNG\r\n\x1a\nfeedback-test-screenshot"
        shot_path.write_bytes(shot_bytes)

        bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
        state = bridge.execute_action(
            "submit_user_feedback",
            {
                "classification": "bug",
                "comment": "Verify server-side Telegram bot dispatch and persistent issue tracking.",
                "app_section": "Activity",
                "browser_url": "https://www.linkedin.com/jobs/",
                "browser_title": "Jobs | LinkedIn",
                "include_desktop_screenshot": True,
                "include_browser_screenshot": False,
                "desktop_screenshot_path": str(shot_path),
            },
        )
    finally:
        server.shutdown()
        server.server_close()

    assert len(received_requests) == 1
    req = received_requests[0]
    assert req["path"] == "/api/autoapply-feedback"
    payload = req["body"]
    assert payload["classification"] == "bug"
    assert payload["app_section"] == "Activity"
    assert "server-side Telegram bot dispatch" in payload["comment"]
    assert len(payload["attachments"]) == 1
    assert base64.b64decode(payload["attachments"][0]["data_base64"]) == shot_bytes

    sub = state["feedback_submissions"][0]
    assert sub["transmitted_remote"] is True
    assert sub["delivery_status"] == "Submitted to AutoApply Feedback Server (@AutoApplyFeedbackBot)"
    assert sub["subscribe_url"] == "https://t.me/AutoApplyFeedbackBot"
    assert sub["notified_subscribers"] == 1


def test_force_update_view_only_lock_and_daily_optional_update_prompt(tmp_path: Path) -> None:
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert "public var isForceUpdateLocked: Bool" in swift_src
    assert "startDailyUpdateCheckTimer()" in swift_src
    assert '"Required Update Available (v\\(store.latestAppVersion))"' in swift_src
    assert '"Remind Me Tomorrow"' in swift_src

    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    # 1. Non-required (optional) update: shows update available + daily prompt, does NOT block execution
    st_opt = bridge.execute_action(
        "check_for_updates",
        {
            "simulate_update_version": "0.2.0",
            "required": False,
            "release_notes": "Optional feature improvements.",
        },
    )
    upd_opt = st_opt["onboarding"]["update_config"]
    assert upd_opt["update_available"] is True
    assert upd_opt["update_required"] is False
    assert upd_opt["force_update_required"] is False
    assert upd_opt["should_prompt_daily"] is True
    assert st_opt["entitlement"]["force_update_required"] is False

    # Dismissing the daily prompt snoozes it for today without blocking anything
    st_dismissed = bridge.execute_action("dismiss_daily_update_prompt", {})
    assert st_dismissed["onboarding"]["update_config"]["should_prompt_daily"] is False

    # Adding a job is allowed during an optional update
    st_job_added = bridge.execute_action(
        "add_job_posting",
        {
            "company_name": "Linear",
            "title": "Staff Product Manager",
            "canonical_url": "https://linear.app/careers/pm",
            "workplace_mode": "remote",
            "country": "CA",
        },
    )
    assert any(j["company_name"] == "Linear" for j in st_job_added["jobs"])

    # 2. Required (Force) update: blocks app execution, pauses automations, allows Settings + View-Only access
    st_req = bridge.execute_action(
        "check_for_updates",
        {
            "simulate_update_version": "0.3.0",
            "required": True,
            "minimum_required_version": "0.3.0",
            "release_notes": "Critical security and ATS protocol update required.",
        },
    )
    upd_req = st_req["onboarding"]["update_config"]
    assert upd_req["update_available"] is True
    assert upd_req["update_required"] is True
    assert upd_req["force_update_required"] is True
    assert st_req["entitlement"]["force_update_required"] is True
    assert st_req["entitlement"]["view_only_mode"] is True
    assert st_req["entitlement"]["can_run_automation"] is False
    assert st_req["onboarding"]["operating_policy"]["emergency_stop_active"] is True

    # Execution/mutation actions outside Settings are blocked
    jobs_before = len(st_req["jobs"])
    st_blocked = bridge.execute_action(
        "add_job_posting",
        {
            "company_name": "BlockedCorp",
            "title": "Blocked Role",
            "canonical_url": "https://example.com/blocked",
        },
    )
    assert st_blocked.get("blocked_by_force_update") is True
    assert len(st_blocked["jobs"]) == jobs_before
    assert not any(j["company_name"] == "BlockedCorp" for j in st_blocked["jobs"])

    # Settings actions & view-only state inspection remain allowed
    st_settings = bridge.execute_action(
        "save_preferences_o10",
        {"minimum_salary_usd": 175000, "residence_country": "Georgia"},
    )
    assert st_settings.get("blocked_by_force_update") is not True
    assert st_settings["onboarding"]["preferences"]["minimum_salary_usd"] == 175000

    # 3. Installing the required update unlocks the app and restores normal operation
    st_installed = bridge.execute_action(
        "install_update",
        {"target_version": "0.3.0", "apply_in_place": True},
    )
    upd_after = st_installed["onboarding"]["update_config"]
    assert upd_after["current_version"] == "0.3.0"
    assert upd_after["update_available"] is False
    assert upd_after["update_required"] is False
    assert st_installed["entitlement"]["force_update_required"] is False
    assert st_installed["onboarding"]["operating_policy"]["emergency_stop_active"] is False

    # Normal execution works again after updating
    st_unblocked = bridge.execute_action(
        "add_job_posting",
        {
            "company_name": "Raycast",
            "title": "Principal Product Manager",
            "canonical_url": "https://raycast.com/jobs/pm",
            "workplace_mode": "remote",
            "country": "CA",
        },
    )
    assert any(j["company_name"] == "Raycast" for j in st_unblocked["jobs"])


def test_paddle_subscription_checkout_webhook_and_device_auto_activation(
    tmp_path: Path, monkeypatch
) -> None:
    from datetime import datetime, timezone
    import hashlib
    import hmac
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlparse

    from autoapply.licensing import (
        EntitlementService,
        derive_paddle_license_key,
        normalize_paddle_webhook_payload,
        verify_paddle_webhook_signature,
    )

    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert "Subscribe ($30/mo · Save 25%)" in swift_src
    assert "Subscribe ($10/wk)" in swift_src
    assert "Subscribe ($200/yr · Save 62%)" in swift_src
    assert "Buy Lifetime ($200 Special)" in swift_src
    assert "checkSubscriptionStatusNow" in swift_src
    assert "startSubscriptionCheckoutPolling()" in swift_src
    assert "Buy Me a Coffee" not in swift_src

    # 1. Verify Paddle webhook HMAC-SHA256 signature verification & payload normalization
    secret = "pdl_ntfset_test_secret_123"
    raw_webhook = json.dumps(
        {
            "event_id": "evt_01paddle_test",
            "event_type": "subscription.activated",
            "data": {
                "id": "sub_01paddle999",
                "transaction_id": "txn_01paddle888",
                "customer_id": "ctm_01paddle777",
                "status": "active",
                "custom_data": {
                    "device_id": "mac_local_device",
                    "support_code": "AA-TEST-1234",
                    "email": "alex@turboapply.ai",
                },
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")
    ts = "1793200000"
    sig = hmac.new(secret.encode("utf-8"), f"{ts}:".encode("utf-8") + raw_webhook, hashlib.sha256).hexdigest()
    header = f"ts={ts};h1={sig}"
    assert (
        verify_paddle_webhook_signature(
            raw_body=raw_webhook,
            signature_header=header,
            webhook_secret=secret,
            tolerance_seconds=0,
        )
        is True
    )
    assert (
        verify_paddle_webhook_signature(
            raw_body=raw_webhook,
            signature_header="ts=1793200000;h1=deadbeef",
            webhook_secret=secret,
            tolerance_seconds=0,
        )
        is False
    )

    normalized = normalize_paddle_webhook_payload(json.loads(raw_webhook.decode("utf-8")))
    assert normalized["internal_event_type"] == "subscription.purchased"
    assert normalized["subscription_id"] == "sub_01paddle999"
    assert normalized["device_id"] == "mac_local_device"
    assert normalized["support_code"] == "AA-TEST-1234"
    assert normalized["license_key"].startswith("AA-LIVE-20USD-")

    # 2. Verify local EntitlementService processes Paddle activation & cancellation webhooks
    now = datetime(2026, 10, 28, 18, 0, tzinfo=timezone.utc)
    svc = EntitlementService(tmp_path / "entitlement.db", signing_secret="test_lease_secret")
    res_act = svc.process_paddle_webhook(
        payload=json.loads(raw_webhook.decode("utf-8")),
        server_now=now,
        raw_body=raw_webhook,
        signature_header=header,
        webhook_secret=secret,
    )
    assert res_act["outcome"].status == "active"
    assert res_act["lease"] is not None
    access_act = svc.evaluate_access(device_id="mac_local_device", current_time=now)
    assert access_act.status == "active"
    assert access_act.can_run_automation is True

    cancel_webhook = {
        "event_id": "evt_02paddle_cancel",
        "event_type": "subscription.canceled",
        "data": {
            "id": "sub_01paddle999",
            "status": "canceled",
            "custom_data": {"device_id": "mac_local_device"},
        },
    }
    res_cancel = svc.process_paddle_webhook(payload=cancel_webhook, server_now=now)
    assert res_cancel["outcome"].status == "expired"
    access_cancel = svc.evaluate_access(device_id="mac_local_device", current_time=now)
    assert access_cancel.status == "expired"
    assert access_cancel.can_run_automation is False

    # 3. Verify AppWorkspaceManager prepare_subscription_checkout + check_subscription_status auto-activates Pro
    issued_key = derive_paddle_license_key("sub_live_auto_01")

    class MockLicenseServerHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path.endswith("/device-status"):
                qs = parse_qs(parsed.query)
                resp = json.dumps(
                    {
                        "ok": True,
                        "active": True,
                        "status": "active",
                        "license_key": issued_key,
                        "subscription_id": "sub_live_auto_01",
                        "device_id": (qs.get("device_id") or [""])[0],
                        "support_code": (qs.get("support_code") or [""])[0],
                        "plan_code": "AA-PRO-20USD-MONTHLY",
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:
            resp = json.dumps(
                {
                    "ok": True,
                    "valid": True,
                    "status": "active",
                    "license_key": issued_key,
                    "plan_code": "AA-PRO-20USD-MONTHLY",
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

    server = HTTPServer(("127.0.0.1", 0), MockLicenseServerHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        monkeypatch.setenv("AUTOAPPLY_LICENSE_API_URL", f"http://127.0.0.1:{port}/api/autoapply-license")
        monkeypatch.setenv("AUTOAPPLY_LICENSE_ALLOW_TEST_HTTP", "1")

        bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
        prep_state = bridge.execute_action("prepare_subscription_checkout", {})
        assert "device_id=mac_local_device" in prep_state["entitlement"]["checkout_url"]
        assert "support_code=" not in prep_state["entitlement"]["checkout_url"]

        polled_state = bridge.execute_action("check_subscription_status", {"silent": False})
        assert polled_state["onboarding"]["trial_state"] in ("paid_active", "paid_key_active")
        assert polled_state["entitlement"]["status"] == "paid_active"
        assert polled_state["entitlement"]["can_run_automation"] is True
        assert polled_state["onboarding"]["subscription_id"] == "sub_live_auto_01"
    finally:
        server.shutdown()
        server.server_close()


def test_thread_followup_pending_until_sent_and_queue_with_estimate_update_cancel(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    # 1. Send Follow-Up when delivery is not yet confirmed -> must be marked "Pending" (NOT Verified Sent)
    pending_state = bridge.execute_action(
        "send_or_queue_thread_message",
        {
            "thread_id": "thr_email_alivo_max",
            "message_id": "msg_pending_01",
            "company": "Alivo",
            "role": "Product Manager / Product Analyst",
            "contact_name": "Max Meade",
            "contact_handle": "max@alivo.ai",
            "channel": "email",
            "subject": "Re: Application: Product Manager / Product Analyst - Alex Mercer",
            "message_text": "Hi Max,\n\nI wanted to follow up on my application.",
            "mode": "send_now",
            "simulate_delivery_pending": True,
        },
    )
    alivo_thread = next(t for t in pending_state["outreach_tracker"]["threads"] if t["id"] == "thr_email_alivo_max")
    assert alivo_thread["delivery_state"] == "pending"
    pending_msg = next(m for m in alivo_thread["messages"] if m["id"] == "msg_pending_01")
    assert pending_msg["delivery_status"] == "Pending"

    # Retrying Send Now when delivery succeeds transitions the message from "Pending" to "Verified Sent"
    sent_state = bridge.execute_action(
        "send_queued_thread_message_now",
        {
            "thread_id": "thr_email_alivo_max",
            "message_id": "msg_pending_01",
            "company": "Alivo",
            "contact_name": "Max Meade",
            "contact_handle": "max@alivo.ai",
            "channel": "email",
        },
    )
    alivo_sent_thread = next(t for t in sent_state["outreach_tracker"]["threads"] if t["id"] == "thr_email_alivo_max")
    assert alivo_sent_thread["delivery_state"] == "sent"
    sent_msg = next(m for m in alivo_sent_thread["messages"] if m["id"] == "msg_pending_01")
    assert sent_msg["delivery_status"] == "Verified Sent"

    # 2. Queue to Send -> shows "Queued" status with scheduled_for and queue_estimate
    queued_state = bridge.execute_action(
        "send_or_queue_thread_message",
        {
            "thread_id": "thr_email_amen_sec",
            "message_id": "msg_queued_02",
            "company": "Amen Security",
            "role": "Product Manager",
            "contact_name": "Amen Security Hiring Team",
            "contact_handle": "info@amensecurity.ca",
            "channel": "email",
            "subject": "Re: CRM Product Manager Application – Trial Collaboration Opportunity",
            "message_text": "Hi Amen Security Team,\n\nSharing my trial plan.",
            "mode": "queue",
        },
    )
    amen_thread = next(t for t in queued_state["outreach_tracker"]["threads"] if t["id"] == "thr_email_amen_sec")
    assert amen_thread["delivery_state"] == "queued"
    queued_msg = next(m for m in amen_thread["messages"] if m["id"] == "msg_queued_02")
    assert queued_msg["delivery_status"] == "Queued"
    assert queued_msg["scheduled_for"] != ""
    assert "Est." in queued_msg["queue_estimate"]

    # 3. Update queued message -> updates subject and body in-place while remaining in queue
    updated_state = bridge.execute_action(
        "update_queued_thread_message",
        {
            "thread_id": "thr_email_amen_sec",
            "message_id": "msg_queued_02",
            "company": "Amen Security",
            "contact_name": "Amen Security Hiring Team",
            "subject": "Re: Updated Trial Plan – Alex Mercer",
            "message_text": "Hi Amen Security Team,\n\nSharing my updated trial plan with milestones.",
        },
    )
    amen_updated_thread = next(t for t in updated_state["outreach_tracker"]["threads"] if t["id"] == "thr_email_amen_sec")
    updated_msg = next(m for m in amen_updated_thread["messages"] if m["id"] == "msg_queued_02")
    assert updated_msg["subject"] == "Re: Updated Trial Plan – Alex Mercer"
    assert "updated trial plan with milestones" in updated_msg["body"]
    assert updated_msg["delivery_status"] == "Queued"

    # 4. Cancel queued message -> removes from thread/queue and restores to draft_text & draft_subject
    cancelled_state = bridge.execute_action(
        "cancel_queued_thread_message",
        {
            "thread_id": "thr_email_amen_sec",
            "message_id": "msg_queued_02",
            "company": "Amen Security",
            "contact_name": "Amen Security Hiring Team",
            "restore_to_draft": True,
        },
    )
    amen_cancelled_thread = next(
        (t for t in cancelled_state["outreach_tracker"]["threads"] if t["id"] == "thr_email_amen_sec"),
        None,
    )
    if amen_cancelled_thread is not None:
        assert not any(m["id"] == "msg_queued_02" for m in amen_cancelled_thread["messages"])
        assert "updated trial plan with milestones" in amen_cancelled_thread["draft_text"]
        assert amen_cancelled_thread["draft_subject"] == "Re: Updated Trial Plan – Alex Mercer"


def test_online_assessment_links_and_action_required_narrow_subcategories(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    # 1. HTML hyperlink preservation and tracking URL unwrapping (e.g. Veeva Rembrandt Portrait via Lever)
    html_email = (
        "<p>When ready to begin, click on the following link to take the assessment:</p>"
        '<p><a href="https://t.lever-analytics.com/email-link?dest=https%3A%2F%2Fapp.rembrandtadvantage.com%2Fportraits-link%2F57dad20b-ccd1-4344-a2e5-9e1f26ddab08&amp;token=xyz">'
        "Rembrandt Portrait</a></p>"
    )
    sanitized = bridge._sanitize_email_body_text(html_email)
    assert "[Rembrandt Portrait](https://app.rembrandtadvantage.com/portraits-link/57dad20b-ccd1-4344-a2e5-9e1f26ddab08)" in sanitized

    # 2. Narrow Subcategory 1: Online Assessment (task, personality/coding assessment, or one-way video interview)
    veeva_cls = bridge._jev_classify_conversation_thread(
        channel="email",
        company="Veeva Systems",
        role="Senior Product Manager",
        contact_name="Veeva Systems",
        subject="Next Steps for Your Veeva Application",
        messages=[
            {
                "sender_role": "them",
                "subject": "Next Steps for Your Veeva Application",
                "body": sanitized,
            }
        ],
        delivery_state="action_required",
    )
    assert veeva_cls["action_required"] is True
    assert veeva_cls["jev_classification"] == "action_required_online_assessment"
    assert veeva_cls["jev_label"] == "Online Assessment"

    # 3. Narrow Subcategory 2: Real Interview (phone call, Zoom/Google Meet/Calendly call, or in-person interview)
    interview_cls = bridge._jev_classify_conversation_thread(
        channel="email",
        company="BrightAxis AI",
        role="Senior Product Manager",
        contact_name="BrightAxis Recruiting",
        subject="Interview Invitation — Senior Product Manager",
        messages=[
            {
                "sender_role": "them",
                "subject": "Interview Invitation — Senior Product Manager",
                "body": "Hi Alex, would you be available to schedule a call on Zoom or Google Meet this week?",
            }
        ],
        delivery_state="action_required",
    )
    assert interview_cls["action_required"] is True
    assert interview_cls["jev_classification"] == "action_required_real_interview"
    assert interview_cls["jev_label"] == "Real Interview"

    # 4. Narrow Subcategory 3: Details Requested (documents, resume/CV, references, visa/salary, intake form)
    details_cls = bridge._jev_classify_conversation_thread(
        channel="email",
        company="Orizon",
        role="Project Manager",
        contact_name="Orizon",
        subject="Project Manager role at Orizon",
        messages=[
            {
                "sender_role": "them",
                "subject": "Project Manager role at Orizon",
                "body": "Please complete the form below: https://coda.io/form/Were-excited-to-hear-from-you_dAoX3oBdeRV",
            }
        ],
        delivery_state="action_required",
    )
    assert details_cls["action_required"] is True
    assert details_cls["jev_classification"] == "action_required_details_requested"
    assert details_cls["jev_label"] == "Details Requested"

    # 5. Generic Fallback: Action Required (when none of the 3 narrower categories match)
    generic_cls = bridge._jev_classify_conversation_thread(
        channel="email",
        company="Acme Corp",
        role="Product Manager",
        contact_name="Recruiting Team",
        subject="Update regarding your inquiry",
        messages=[
            {
                "sender_role": "them",
                "subject": "Update regarding your inquiry",
                "body": "Hi Alex, please let us know how you would like to proceed before Friday.",
            }
        ],
        delivery_state="action_required",
    )
    assert generic_cls["action_required"] is True
    assert generic_cls["jev_classification"] == "action_required"
    assert generic_cls["jev_label"] == "Action Required"


def test_generate_recommended_interview_answer_for_hr_questions(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    # 1. Generate recommended answer for Standard Screening Q&A (q_leadership)
    st1 = bridge.execute_action(
        "generate_recommended_interview_answer",
        {
            "question_id": "q_leadership",
            "question_title": "Standard Screening Q&A",
            "question_prompt": "How do you answer common questions like 'Why are you looking for a new role?' or 'Describe your leadership style'?",
            "kb_section_id": "qa_bank",
        },
    )
    ans1 = st1.get("last_voice_transcript", "")
    assert st1.get("last_voice_question_id") == "q_leadership"
    assert "leadership style" in ans1.lower() or "14-person" in ans1.lower()
    assert "Apex Industrial" in ans1
    assert "\n- " in ans1

    # 2. Clicking a second time cycles to a fresh variation
    st2 = bridge.execute_action(
        "generate_recommended_interview_answer",
        {
            "question_id": "q_leadership",
            "question_title": "Standard Screening Q&A",
            "question_prompt": "How do you answer common questions like 'Why are you looking for a new role?' or 'Describe your leadership style'?",
            "kb_section_id": "qa_bank",
        },
    )
    ans2 = st2.get("last_voice_transcript", "")
    assert ans2 and ans2 != ans1

    # 3. Saving the generated answer persists cleanly to the Knowledge Base & Standard Q&A Bank
    st_saved = bridge.execute_action(
        "save_voice_interview_answer",
        {
            "question_id": "q_leadership",
            "transcript": ans1,
            "mode": "typed",
            "kb_section_id": "qa_bank",
        },
    )
    saved_entry = st_saved["onboarding"]["interview_answers"]["q_leadership"]
    assert saved_entry["status"] == "saved"
    assert "Apex Industrial" in saved_entry["transcript"]

    # 4. Verify Swift UI button wiring
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert "AI Recommended Answer" in swift_src
    assert "generateRecommendedInterviewAnswer(for: q)" in swift_src
    assert '"generate_recommended_interview_answer"' in swift_src


def test_pricing_plans_savings_and_two_day_free_trial(tmp_path: Path) -> None:
    from datetime import datetime, timedelta, timezone
    from autoapply.licensing import PRICING_PLANS, TRIAL_DURATION_DAYS, TRIAL_DURATION_HOURS

    # 1. Verify 2-day (48-hour) free trial constants and pricing plans
    assert TRIAL_DURATION_HOURS == 48
    assert TRIAL_DURATION_DAYS == 2
    assert set(PRICING_PLANS.keys()) == {"weekly", "monthly", "annual", "lifetime"}
    assert PRICING_PLANS["weekly"]["price_usd"] == 10
    assert PRICING_PLANS["weekly"]["period_days"] == 7
    assert PRICING_PLANS["monthly"]["price_usd"] == 30
    assert PRICING_PLANS["monthly"]["period_days"] == 30
    assert PRICING_PLANS["monthly"]["savings_percent"] == 25
    assert "save $10/month" in PRICING_PLANS["monthly"]["savings_detail"].lower()
    assert PRICING_PLANS["annual"]["price_usd"] == 200
    assert PRICING_PLANS["annual"]["period_days"] == 365
    assert PRICING_PLANS["annual"]["savings_percent"] == 62
    assert "save $320/yr" in PRICING_PLANS["annual"]["savings_detail"].lower()
    assert PRICING_PLANS["lifetime"]["price_usd"] == 200
    assert PRICING_PLANS["lifetime"]["period_days"] == 36500
    assert PRICING_PLANS["lifetime"]["is_limited_time"] is True
    assert "limited-time-only special" in PRICING_PLANS["lifetime"]["savings_detail"].lower()

    # 2. Verify AppWorkspaceManager starts a 2-day trial and clamps any legacy >48h trial expiry
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    st_trial = bridge.execute_action("reserve_trial_o02", {})
    assert "2-day free trial activated" in str(st_trial.get("action_notice") or "")
    assert st_trial["entitlement"]["trial_duration_days"] == 2
    assert len(st_trial["entitlement"]["pricing_plans"]) == 4

    # Simulate a legacy 5-day trial timestamp and verify _upgrade_state_schema clamps it to <= 48h
    raw = bridge._load_raw_state()
    raw["onboarding"]["trial_expires_at"] = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    bridge._save_raw_state(raw)
    st_clamped = bridge.get_full_workspace_state()
    exp_dt = datetime.fromisoformat(st_clamped["onboarding"]["trial_expires_at"].replace("Z", "+00:00"))
    rem_hours = (exp_dt - datetime.now(timezone.utc)).total_seconds() / 3600.0
    assert 47.0 <= rem_hours <= 48.1

    # 3. Verify Swift UI & OnboardingCoordinator reflect 2-day free trial and 4 pricing plans
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    coord_src = Path("apps/macos/AutoApply/Onboarding/OnboardingCoordinator.swift").read_text(encoding="utf-8")
    assert "public static let trialDurationSeconds: Int64 = 48 * 3600" in coord_src
    assert "return max(0, min(2, days))" in swift_src
    assert "2-Day Free Trial" in swift_src
    assert "LIMITED-TIME SPECIAL" in swift_src


def test_companion_prefill_order_linkedin_messaging_exclusion_and_feed_fallback(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    # 1. Verify companion_prepare_and_prefill_job on https://www.linkedin.com/jobs/ never fails or throws
    #    and honors skip_doc_regen=True (prefilling form fields first without generating PDFs prematurely)
    res_fast = bridge.execute_action(
        "companion_prepare_and_prefill_job",
        {
            "mode": "prefill",
            "skip_doc_regen": True,
            "canonical_url": "https://www.linkedin.com/jobs/",
            "title": "Product Owner",
            "company_name": "Jonas Software",
            "location": "Canada (Remote)",
            "description": "Product Owner role at Jonas Software.",
            "form_fields": [
                {
                    "field_id": "phone_num",
                    "label": "Mobile phone number",
                    "type": "tel",
                    "tag": "input",
                    "required": True,
                }
            ],
        },
    )
    pkg_fast = res_fast.get("prefill_package")
    assert pkg_fast is not None
    assert pkg_fast["title"] == "Product Owner"
    assert pkg_fast["company_name"] == "Jonas Software"
    # With skip_doc_regen=True on a brand-new job, no PDF should be generated yet
    assert pkg_fast["documents"].get("resume") is None

    # 2. When the open form step actually has a document upload input, skip_doc_regen=False & skip_field_llm=True
    #    generates and returns the tailored Resume & Cover Letter PDFs on demand
    res_docs = bridge.execute_action(
        "companion_prepare_and_prefill_job",
        {
            "mode": "prefill",
            "skip_doc_regen": False,
            "skip_field_llm": True,
            "canonical_url": "https://www.linkedin.com/jobs/",
            "title": "Product Owner",
            "company_name": "Jonas Software",
            "location": "Canada (Remote)",
            "description": "Product Owner role at Jonas Software.",
            "form_fields": [],
        },
    )
    pkg_docs = res_docs.get("prefill_package")
    assert pkg_docs is not None
    assert pkg_docs["documents"]["resume"] is not None
    assert pkg_docs["documents"]["resume"]["base64"]

    # 3. Verify content.js excludes LinkedIn Messaging chat bubbles (#msg-overlay / .msg-overlay-conversation-bubble)
    #    and enforces Step 1 (open card) -> Step 2 (click Apply / external tab) -> Step 3 (prefill fields first, then docs)
    content_js = Path("packaging/extensions/autoapply_companion/content.js").read_text(encoding="utf-8")
    bg_js = Path("packaging/extensions/autoapply_companion/background.js").read_text(encoding="utf-8")
    assert "msg-overlay-conversation-bubble" in content_js
    assert "msg-form__attachment-upload-input" in content_js
    assert "extractExternalApplyUrl" in content_js
    assert "COMPANION_ENSURE_EXTERNAL_TAB" in content_js
    assert "COMPANION_ENSURE_EXTERNAL_TAB" in bg_js
    assert "findDocumentFileInputsInScope" in content_js
    assert "{ skipFiles: true }" in content_js
    assert "{ onlyFiles: true }" in content_js


def test_activate_license_screen_redesign_and_feedback_states(tmp_path: Path) -> None:
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")

    # 1. Verify separate, clean sections for trial status, subscription plans, and license key activation
    assert "struct LicenseTrialStatusCardView: View" in swift_src
    assert "struct SubscriptionPlansCardView: View" in swift_src
    assert "struct LicenseKeyActivationCardView: View" in swift_src
    assert "public var statusBannerIcon: String" in swift_src
    assert "public var statusBannerColor: Color" in swift_src
    assert "public var selectedSubscriptionPlanTitle: String" in swift_src

    # 2. Verify technical jargon removed from user-facing placeholders/buttons
    assert "Enter license key (e.g. AA-LIVE-...)" not in swift_src
    assert "via Paddle\"" not in swift_src

    # 3. Verify check_subscription_status when no subscription is active returns clean user-facing copy
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    st_check = bridge.execute_action("check_subscription_status", {"silent": False})
    notice = str(st_check.get("action_notice") or "")
    assert "No active subscription found yet" in notice
    assert "Paddle checkout" not in notice
    assert "AA-LIVE-" not in notice


def test_resume_draft_and_submitted_indicator_and_manual_toggle(tmp_path: Path) -> None:
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")

    # 1. Verify single non-redundant visual indicator pill and menu items in ResumesStudioView
    assert "private func resumeSubmissionStatusPill(isSubmitted: Bool, compact: Bool = false) -> some View" in swift_src
    assert 'Label("Mark as Submitted", systemImage: "checkmark.circle")' in swift_src
    assert 'Label("Mark as Draft", systemImage: "arrow.uturn.backward.circle")' in swift_src
    assert "public func setDocumentSubmittedStatus(_ doc: DocumentArtifactItem, isSubmitted: Bool)" in swift_src
    assert 'Text("Locked (Submitted)")' not in swift_src

    # 2. Verify backend action set_document_submitted_status toggles Draft <-> Submitted and syncs linked job
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    raw = bridge._load_raw_state()
    jobs = raw.get("jobs", [])
    job_id = jobs[0]["job_id"] if jobs else "job_udemy_pm"
    doc_id = "doc_test_udemy_pm"
    raw.setdefault("documents", []).append(
        {
            "artifact_id": doc_id,
            "job_id": job_id,
            "job_label": "Senior Product Manager, Applied AI @ Udemy",
            "company_name": "Udemy",
            "role_title": "Senior Product Manager, Applied AI",
            "created_at": "2026-10-28 20:35",
            "is_submitted": False,
        }
    )
    bridge._save_raw_state(raw)

    st_sub = bridge.execute_action(
        "set_document_submitted_status",
        {"document_id": doc_id, "job_id": job_id, "is_submitted": True},
    )
    updated_doc = next(d for d in st_sub["documents"] if d["artifact_id"] == doc_id)
    assert updated_doc["is_submitted"] is True
    assert updated_doc["locked_submitted"] is True
    if job_id:
        linked_job = next((j for j in st_sub["jobs"] if j["job_id"] == job_id), None)
        if linked_job:
            assert linked_job["pipeline_stage"] == "submitted"
            assert linked_job["state"] == "submitted_verified"

    st_draft = bridge.execute_action(
        "set_document_submitted_status",
        {"document_id": doc_id, "job_id": job_id, "is_submitted": False},
    )
    reverted_doc = next(d for d in st_draft["documents"] if d["artifact_id"] == doc_id)
    assert reverted_doc["is_submitted"] is False
    assert reverted_doc["locked_submitted"] is False


def test_compact_top_right_toast_notification_and_feedback_copy(tmp_path: Path) -> None:
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")

    # 1. Verify top-right toast overlay, 5-second auto-dismiss, and title/subtitle parser
    assert "struct ToastNotificationOverlayView: View" in swift_src
    assert ".overlay(alignment: .topTrailing)" in swift_src
    assert "ToastNotificationOverlayView(store: store)" in swift_src
    assert "static func parsedTitleAndSubtitle(from raw: String, icon: String, color: Color)" in swift_src
    assert "DispatchQueue.main.asyncAfter(deadline: .now() + 5.0)" in swift_src

    # 2. Verify submit_user_feedback returns clean Title + Subtitle without server/bot names
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    shot1 = tmp_path / "shot1.png"
    shot1.write_bytes(b"\x89PNG\r\n\x1a\nSHOT1")
    shot2 = tmp_path / "shot2.png"
    shot2.write_bytes(b"\x89PNG\r\n\x1a\nSHOT2")

    st = bridge.execute_action(
        "submit_user_feedback",
        {
            "classification": "improvement",
            "comment": "Test compact toast notification",
            "app_section": "Resumes",
            "include_desktop_screenshot": True,
            "include_browser_screenshot": True,
            "desktop_screenshot_path": str(shot1),
            "browser_screenshot_path": str(shot2),
            "attachments": [],
        },
    )
    notice = str(st.get("action_notice") or "")
    assert notice == "Feedback sent successfully\nYour feedback and 2 attachments have been submitted."
    assert "@AutoApplyFeedbackBot" not in notice
    assert "Feedback Server" not in notice


def test_knowledge_base_generic_placeholders_and_profile_header_protection(tmp_path: Path) -> None:
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")

    # 1. Verify generic placeholders in kbProfileHeaderBar (no personal name/number/location placeholders)
    assert 'kbProfileField(label: "Full Name", placeholder: "Full name"' in swift_src
    assert 'kbProfileField(label: "Pronouns", placeholder: "Pronouns"' in swift_src
    assert 'kbProfileField(label: "Professional Headline", placeholder: "Role or professional headline"' in swift_src
    assert 'kbProfileField(label: "Location", placeholder: "City, Country"' in swift_src
    assert 'kbProfileField(label: "Email", placeholder: "email@domain.com"' in swift_src
    assert 'kbProfileField(label: "Phone", placeholder: "+1 (555) 000-0000"' in swift_src
    assert 'kbProfileField(label: "LinkedIn URL", placeholder: "https://linkedin.com/in/username"' in swift_src
    assert 'kbProfileField(label: "GitHub / Portfolio", placeholder: "https://github.com/username"' in swift_src
    assert 'placeholder: "Mr. Alexander Mercer"' not in swift_src
    assert 'placeholder: "+1 555 234 5670"' not in swift_src
    assert 'placeholder: "Batumi, Georgia"' not in swift_src

    # 2. Verify save_profile_header protects against accidental empty-string overwrites and self-heals from candidate_facts
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    st_saved = bridge.execute_action(
        "save_profile_header",
        {
            "full_name": "Jane Candidate",
            "pronouns": "She / Her",
            "headline": "Staff Product Manager",
            "email": "jane@example.com",
            "phone": "+1 415 555 0199",
            "location": "San Francisco, CA",
            "linkedin_url": "https://linkedin.com/in/janecandidate",
            "github_url": "https://github.com/janecandidate",
            "include_photo_on_resume": True,
        },
    )
    hdr = st_saved["knowledge_base"]["profile_header"]
    assert hdr["full_name"] == "Jane Candidate"
    assert hdr["phone"] == "+1 415 555 0199"

    # Attempt accidental blank overwrite (such as an uninitialized UI auto-save)
    st_after_blank = bridge.execute_action(
        "save_profile_header",
        {
            "full_name": "",
            "pronouns": "",
            "headline": "",
            "email": "",
            "phone": "",
            "location": "",
            "linkedin_url": "",
            "github_url": "",
        },
    )
    hdr_after = st_after_blank["knowledge_base"]["profile_header"]
    assert hdr_after["full_name"] == "Jane Candidate"
    assert hdr_after["email"] == "jane@example.com"
    assert hdr_after["phone"] == "+1 415 555 0199"
    assert hdr_after["location"] == "San Francisco, CA"


def test_voice_interview_ai_recommended_speech_silence_guard_and_bounded_editor(tmp_path: Path) -> None:
    import wave

    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")

    # 1. AI Recommended Answer is enabled in Conversation Mode and speaks varied female start + done cues aloud
    assert "audioId: startCue.id" in swift_src
    assert "audioId: doneCue.id" in swift_src
    assert (
        '"Okay, here\'s what a good response would look like based on your background."'
        in swift_src
    )
    assert '"There you go. Go ahead and speak whenever you\'re ready to add more."' in swift_src
    assert ".disabled(recorder.isTranscribing || store.isGeneratingInterviewAnswer)" in swift_src
    assert Path("packaging/interview_audio/ai_recommend_start.mp3").is_file()
    assert Path("packaging/interview_audio/ai_recommend_done.mp3").is_file()

    # 2. Voice Interview view is rendered outside outer ScrollView with bounded TextEditor so bottom buttons always fit
    assert "} else if store.selectedSection == .voiceInterview {" in swift_src
    assert ".frame(minHeight: 120, maxHeight: .infinity)" in swift_src
    assert "hasDetectedSpeechSinceLastChunk" in swift_src

    # 3. Repetition hallucination stripper removes Whisper decoder loops
    hallucinated = (
        "I'm going to do it. I'm going to do it. I'm going to do it. "
        "I'm going to do a little bit of the same thing. I'm going to do a little bit of the same thing. "
        "I'm going to do a little bit of the same thing. I'm going to do a little bit of the same thing."
    )
    assert AppWorkspaceManager._strip_whisper_repetition_hallucinations(hallucinated) == ""

    # 4. Pre-populated / pre-typed text is preserved untouched when microphone records silence
    silent_wav = tmp_path / "silence.wav"
    with wave.open(str(silent_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * 16000)

    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    pre_typed = "Pre-populated answer about cross-functional product leadership."
    res_silent = bridge.execute_action(
        "transcribe_voice_audio",
        {
            "audio_path": str(silent_wav),
            "draft_text": pre_typed,
            "pre_typed_text": pre_typed,
            "question_id": "q_standard_qa",
        },
    )
    assert res_silent["last_voice_transcript"] == pre_typed


def test_hh_chat_thread_url_resolution_and_labels_without_circle_dots(tmp_path):
    """Verify clicking Open HH Chat resolves to the real HH Chat URL for the thread and status labels have no circle dots."""
    from pathlib import Path
    from autoapply.app_bridge import AppWorkspaceManager

    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    # 1. Fortune P. (vacancy 138447409) resolves to its real HH chat URL https://hh.ru/chat/5708780568
    url_fortune = bridge._resolve_hh_thread_url_for_outreach(
        custom_url="https://hh.ru/applicant/negotiations",
        payload={
            "company": "Fortune P.",
            "contact_handle": "https://hh.ru/vacancy/138447409",
            "profile_url": "https://hh.ru/vacancy/138447409",
            "channel": "hh",
        },
    )
    assert url_fortune == "https://hh.ru/chat/5708780568"

    # 2. Метр квадратный resolves to its real HH chat URL https://hh.ru/chat/5710269573
    url_metr = bridge._resolve_hh_thread_url_for_outreach(
        custom_url="https://chatik.hh.ru",
        payload={"company": "Метр квадратный", "channel": "hh"},
    )
    assert url_metr == "https://hh.ru/chat/5710269573"

    # 3. Finstar Financial Group resolves to its specific vacancy URL (not generic /applicant/negotiations)
    url_finstar = bridge._resolve_hh_thread_url_for_outreach(
        custom_url="https://hh.ru/applicant/negotiations",
        payload={"company": "Finstar Financial Group", "channel": "hh"},
    )
    assert url_finstar == "https://hh.ru/vacancy/138278608"

    # 4. launch_browser_session with dry_run=True for an HH outreach thread opens the real HH chat URL
    state = bridge.execute_action(
        "launch_browser_session",
        {
            "target": "outreach_thread",
            "channel": "hh",
            "company": "Fortune P.",
            "contact_handle": "https://hh.ru/vacancy/138447409",
            "url": "https://hh.ru/applicant/negotiations",
            "dry_run": True,
        },
    )
    assert state["last_browser_launch"]["url"] == "https://hh.ru/chat/5708780568"

    # 5. Swift UI: statusFilterChip and conversationThreadRow status badges no longer render Circle() dots next to Follow-Up or other labels
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    filter_chip_block = swift_src.split("private func statusFilterChip(")[1].split("private func stripQuotedEmailReply(")[0]
    assert "Circle()" not in filter_chip_block
    thread_status_block = swift_src.split("Text(snippetText)")[1].split("threadRowContextMenuItems(thread)")[0]
    assert "Circle()" not in thread_status_block


def test_outlook_style_empty_selection_state_for_messages_resumes_and_jobs() -> None:
    """Verify Messages, Resumes, and Jobs open with no item auto-selected and render the Outlook-style empty selection view."""
    from pathlib import Path

    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert "struct OutlookStyleEmptySelectionView: View" in swift_src
    assert 'title: "No Conversation Selected"' in swift_src
    assert 'subtitle: "Select a conversation to read."' in swift_src
    assert 'title: "No Resume Selected"' in swift_src
    assert 'subtitle: "Select a resume to read."' in swift_src
    assert 'title: "No Job Selected"' in swift_src
    assert 'subtitle: "Select a job to read."' in swift_src
    assert "private func activateMainSidebarSection(_ newSection: NavigationSection)" in swift_src


def test_autofill_and_submit_thread_form_coda_and_messages_button(tmp_path: Path) -> None:
    """Verify Messages thread form detection, KB-grounded Coda/Greenhouse form answering, thread resolution, and Autofill Form UI button."""
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    raw = bridge._load_raw_state()
    orizon_thread = {
        "id": "thr_orizon_coda_1",
        "company": "Orizon",
        "role": "Project Manager role",
        "contact_name": "Orizon Design",
        "contact_handle": "careers@orizon.co",
        "channel": "email",
        "subject": "Re: Project Manager role at Orizon",
        "jev_classification": "action_required_details_requested",
        "action_required": True,
        "messages": [
            {
                "id": "m_out_1",
                "sender_role": "you",
                "sender_name": "You",
                "body": "https://www.linkedin.com/in/alexander-mercer/\nhttps://turboapply.agency/",
                "timestamp": "2026-10-18 09:15",
            },
            {
                "id": "m_in_1",
                "sender_role": "them",
                "sender_name": "Orizon Design",
                "body": (
                    "Thank you so much for your interest in joining Orizon\n"
                    "1. Complete your application\n"
                    "https://coda.io/form/Were-excited-to-hear-from-you_dAoX3oBdeRV\n"
                    "2. Stay connected\n"
                    "Dribbble https://dribbble.com/Orizon\n"
                    "Twitter https://twitter.com/orizondesign\n"
                    "LinkedIn https://www.linkedin.com/company/orizon-design/"
                ),
                "timestamp": "2026-10-18 09:15",
            },
        ],
    }
    raw.setdefault("conversation_threads", []).append(orizon_thread)
    bridge._save_raw_state(raw)

    extracted_url = bridge._extract_thread_form_url(orizon_thread)
    assert extracted_url == "https://coda.io/form/Were-excited-to-hear-from-you_dAoX3oBdeRV"

    state = bridge.execute_action(
        "autofill_and_submit_thread_form",
        {
            "thread_id": "thr_orizon_coda_1",
            "company_name": "Orizon",
            "title": "Project Manager role",
            "submit": True,
            "form_fields": [
                {"field_id": "coda_cell_0", "label": "Full Name *", "type": "text", "tag": "div", "required": True},
                {"field_id": "coda_cell_1", "label": "Email *", "type": "text", "tag": "div", "required": True},
                {"field_id": "coda_cell_2", "label": "Where are you based? (City and country) *", "type": "text", "tag": "div", "required": True},
                {
                    "field_id": "coda_cell_3",
                    "label": "What position are you interested in? *",
                    "type": "combobox",
                    "tag": "div",
                    "required": True,
                    "options": ["Project Manager", "Product Designer", "Account Manager"],
                },
                {"field_id": "coda_cell_4", "label": "What is your hourly rate?", "type": "text", "tag": "div", "required": False},
                {"field_id": "coda_cell_6", "label": "Tell us more about you *", "type": "text", "tag": "div", "required": True},
            ],
        },
    )
    assert "Form autofilled & submitted for Orizon" in state["action_notice"]
    updated_raw = bridge._load_raw_state()
    updated_thread = next(c for c in updated_raw["conversation_threads"] if c["id"] == "thr_orizon_coda_1")
    assert updated_thread["override_action_required"] is False
    assert updated_thread["form_submitted_url"] == "https://coda.io/form/Were-excited-to-hear-from-you_dAoX3oBdeRV"
    assert any(m.get("delivery_status") == "Form Submitted" for m in updated_thread["messages"])

    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert "public func autofillAndSubmitThreadForm(" in swift_src
    assert "private func extractFormSubmissionLink(for thread: OutreachThreadItem)" in swift_src
    assert 'Text(isAutofilling ? "Autofilling Form..." : "Autofill Form")' in swift_src


def test_ai_draft_followup_regenerate_and_generating_dots_indicator(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    raw = bridge._load_raw_state()
    raw.setdefault("conversation_threads", []).append(
        {
            "id": "thr_techdigital_anjalika",
            "company": "Techdigitalcorp",
            "role": "Job Opening - Robotic Test Engineer | W2 Only | Onsite",
            "contact_name": "Anjalika Momin",
            "contact_handle": "anjalika@techdigitalcorp.com",
            "channel": "email",
            "subject": "Job Opening - Robotic Test Engineer | W2 Only | Onsite",
            "messages": [
                {
                    "id": "msg_anj_1",
                    "sender_role": "them",
                    "sender_name": "Anjalika Momin",
                    "sender_handle": "anjalika@techdigitalcorp.com",
                    "subject": "Job Opening - Robotic Test Engineer | W2 Only | Onsite",
                    "body": (
                        "Hi, I'm Anjalika and I'm a US IT Recruiter at TechDigital Corporation. "
                        "I came across your resume in the internet job sites and I'm very much interested in presenting your resume to my client."
                    ),
                    "timestamp": "2026-10-01 10:39",
                }
            ],
        }
    )
    bridge._save_raw_state(raw)

    # 1. Initial AI Draft Follow-Up
    res_1 = bridge.execute_action(
        "draft_thread_followup",
        {
            "thread_id": "thr_techdigital_anjalika",
            "company": "Techdigitalcorp",
            "role": "Job Opening - Robotic Test Engineer | W2 Only | Onsite",
            "contact_name": "Anjalika Momin",
            "channel": "email",
            "subject": "Job Opening - Robotic Test Engineer | W2 Only | Onsite",
            "current_draft": "",
            "regenerate": False,
        },
    )
    assert "Follow-up draft ready" in res_1["action_notice"]
    assert "Email follow-up drafted" in res_1["action_notice"]
    th_1 = next(t for t in res_1["outreach_tracker"]["threads"] if t["id"] == "thr_techdigital_anjalika")
    draft_1 = th_1["draft_text"]
    assert draft_1.strip()
    assert th_1["ai_drafted"] is True

    # 2. First Regenerate click produces a genuinely fresh draft
    res_2 = bridge.execute_action(
        "draft_thread_followup",
        {
            "thread_id": "thr_techdigital_anjalika",
            "company": "Techdigitalcorp",
            "role": "Job Opening - Robotic Test Engineer | W2 Only | Onsite",
            "contact_name": "Anjalika Momin",
            "channel": "email",
            "subject": "Job Opening - Robotic Test Engineer | W2 Only | Onsite",
            "current_draft": draft_1,
            "regenerate": True,
        },
    )
    assert "Follow-up regenerated" in res_2["action_notice"]
    th_2 = next(t for t in res_2["outreach_tracker"]["threads"] if t["id"] == "thr_techdigital_anjalika")
    draft_2 = th_2["draft_text"]
    assert draft_2.strip()
    assert draft_2.strip() != draft_1.strip()
    assert th_2["draft_regeneration_count"] == 1

    # 3. Second Regenerate click produces a third distinct variant
    res_3 = bridge.execute_action(
        "draft_thread_followup",
        {
            "thread_id": "thr_techdigital_anjalika",
            "company": "Techdigitalcorp",
            "role": "Job Opening - Robotic Test Engineer | W2 Only | Onsite",
            "contact_name": "Anjalika Momin",
            "channel": "email",
            "subject": "Job Opening - Robotic Test Engineer | W2 Only | Onsite",
            "current_draft": draft_2,
            "regenerate": True,
        },
    )
    th_3 = next(t for t in res_3["outreach_tracker"]["threads"] if t["id"] == "thr_techdigital_anjalika")
    draft_3 = th_3["draft_text"]
    assert draft_3.strip() != draft_2.strip()
    assert draft_3.strip() != draft_1.strip()
    assert th_3["draft_regeneration_count"] == 2

    # 4. Clearing draft resets ai_drafted state so UI reverts back to "AI Draft Follow-Up"
    bridge.execute_action(
        "clear_thread_draft",
        {
            "thread_id": "thr_techdigital_anjalika",
            "company": "Techdigitalcorp",
            "contact_name": "Anjalika Momin",
            "channel": "email",
        },
    )
    cleared_raw = bridge._load_raw_state()
    cleared_th = next(c for c in cleared_raw["conversation_threads"] if c["id"] == "thr_techdigital_anjalika")
    assert cleared_th["draft_text"] == ""
    assert cleared_th["ai_drafted"] is False

    # 5. Verify Swift UI switches AI Draft Follow-Up -> Regenerate and renders animated GeneratingDotsView
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert "struct GeneratingDotsView: View" in swift_src
    assert "struct GeneratingProgressLabel: View" in swift_src
    assert 'Label("Regenerate", systemImage: "arrow.clockwise")' in swift_src
    assert 'Label("AI Draft Follow-Up", systemImage: "sparkles")' in swift_src
    assert "@Published public var draftingFollowUpThreadId: String" in swift_src
    assert "@Published public var aiGeneratedDraftThreadIds: Set<String>" in swift_src
    assert "@Published public var isGeneratingTailoredDocument: Bool" in swift_src
    assert "public func generateTailoredDocument(payload: [String: Any], clearInputsOnSuccess: Bool = false)" in swift_src


def test_real_browser_form_filling_enforces_85_to_145ms_human_typing_cadence() -> None:
    content_js = Path("packaging/extensions/autoapply_companion/content.js").read_text(encoding="utf-8")
    bridge_py = Path("runtime/autoapply/app_bridge.py").read_text(encoding="utf-8")

    # 1. Companion Chrome extension uses 85-145ms natural human typing cadence (85 + Math.floor(Math.random() * 61))
    assert "function humanTypingCadenceMs()" in content_js
    assert "return 85 + Math.floor(Math.random() * 61);" in content_js
    assert "await new Promise((r) => setTimeout(r, humanTypingCadenceMs()));" in content_js
    assert "const baseDelay = totalLen > 120 ? 18 : totalLen > 45 ? 26 : 38;" not in content_js

    # 2. CDP CloakBrowser interact & direct CDP form fillers use 85-145ms natural human typing cadence
    assert "async def _type_human_cadence(val_str: str) -> None:" in bridge_py
    assert "await _type_human_cadence(ans_val)" in bridge_py
    assert "typeNativeTextHumanCadence" in bridge_py
    assert "random.uniform(0.085, 0.145)" in bridge_py
    assert "random.uniform(0.018, 0.036)" not in bridge_py


def test_profile_to_job_match_scoring_discriminates_archetypes_skills_eligibility_and_kb_invalidation(
    tmp_path: Path,
) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    bridge.execute_action(
        "save_kb_header",
        {
            "full_name": "Alex Mercer",
            "headline": "Software Product Manager | AI Business Automation",
            "location": "Batumi, Georgia",
            "email": "alex.mercer@example.com",
        },
    )
    for sec_id, sec_md in (
        (
            "about",
            "Project manager with six years leading cross-functional software, IoT, and AI automation products from 0-to-1 inception to launch. Led 14-person multidisciplinary team.",
        ),
        (
            "experience",
            "## Software Product Manager, R&D — Apex Industrial\n- Owned product roadmap, backlog prioritization, user stories, acceptance criteria, pricing, and Scrum execution.\n- Built IoT-enabled B2B SaaS platform.\n## Delivery Lead — TurboApply Agency\n- Built autonomous AI agents, RAG knowledge base retrieval, workflow automation, Python services, REST APIs, and Salesforce CRM integrations.",
        ),
        (
            "education",
            "## Bachelor of Engineering, Electrical and Electronics Engineering\n- British Columbia Institute of Technology",
        ),
        (
            "skills",
            "Product roadmap, user stories, Agile, Scrum, KPIs, retention analysis, Applied AI, LLM product requirements, AI agents, RAG, workflow automation, REST APIs, webhooks, Python, SQL, Salesforce CRM, Jira, Figma.",
        ),
    ):
        bridge.execute_action("save_kb_section", {"section_id": sec_id, "markdown": sec_md})

    raw = bridge._load_raw_state()
    prefs = raw.setdefault("onboarding", {}).setdefault("preferences", {})
    prefs["residence_country"] = "GE"
    prefs["global_b2b_contractor"] = True
    prefs["minimum_salary_usd"] = 150000
    prefs["target_salary_usd"] = 200000
    prefs["desired_titles"] = ["Software Product Manager", "AI Business Automation"]

    raw["jobs"] = [
        {
            "job_id": "job_ai_pm_strong",
            "direct_employer_id": "emp_posthog",
            "company_name": "PostHog",
            "title": "Senior Product Manager, Applied AI & Workflow Automation",
            "canonical_url": "https://careers.posthog.com/ai-pm",
            "workplace_mode": "remote",
            "location_label": "Worldwide Remote (B2B engagement)",
            "eligible_countries": ["GE", "GLOBAL"],
            "sponsorship_offered": False,
            "is_open": True,
            "salary_max_usd": 210000,
            "eligible": True,
            "eligibility_manual_override": True,
            "state": "ready_to_submit",
            "pipeline_stage": "not_applied",
            "description": (
                "We are hiring a Senior Product Manager for Applied AI & Workflow Automation.\n"
                "Requirements:\n"
                "- 5+ years of experience in product management owning product roadmap, user stories, and Agile Scrum delivery.\n"
                "- Hands-on experience shipping LLM products, AI agents, RAG retrieval, REST APIs, Python, and B2B SaaS integrations.\n"
                "- Bachelor's of Engineering or Computer Science technical degree.\n"
                "Worldwide remote with B2B contractor support."
            ),
        },
        {
            "job_id": "job_cse_good",
            "direct_employer_id": "emp_serpapi",
            "company_name": "SerpApi",
            "title": "Customer Success Engineer",
            "canonical_url": "https://serpapi.com/careers/cse",
            "workplace_mode": "remote",
            "location_label": "Remote (Global)",
            "eligible_countries": ["GE", "GLOBAL"],
            "sponsorship_offered": False,
            "is_open": True,
            "salary_max_usd": 175000,
            "eligible": True,
            "eligibility_manual_override": True,
            "state": "ready_to_submit",
            "pipeline_stage": "not_applied",
            "description": (
                "Customer Success Engineer supporting enterprise B2B SaaS customers with REST APIs, webhooks, Python scripting, and customer onboarding."
            ),
        },
        {
            "job_id": "job_us_only_ai_pm",
            "direct_employer_id": "emp_udemy",
            "company_name": "Udemy",
            "title": "Senior Product Manager, Generative AI",
            "canonical_url": "https://careers.udemy.com/ai-pm",
            "workplace_mode": "remote",
            "location_label": "Remote (US)",
            "eligible_countries": ["US"],
            "sponsorship_offered": False,
            "is_open": True,
            "salary_max_usd": 200000,
            "eligible": False,
            "eligibility_manual_override": True,
            "exclusion_reason": "Role requires US residence (Remote - USA)",
            "state": "ineligible",
            "pipeline_stage": "not_applied",
            "description": (
                "Lead Generative AI product roadmap, LLMs, cross-functional teams, and product KPIs. 5+ years of experience."
            ),
        },
        {
            "job_id": "job_accounting_low",
            "direct_employer_id": "emp_acct",
            "company_name": "LedgerCorp",
            "title": "Financial Controller & Accounting Operations Lead",
            "canonical_url": "https://ledgercorp.com/controller",
            "workplace_mode": "onsite",
            "location_label": "Atlanta, GA - Onsite",
            "eligible_countries": ["US"],
            "sponsorship_offered": False,
            "is_open": True,
            "salary_max_usd": 160000,
            "eligible": False,
            "eligibility_manual_override": True,
            "exclusion_reason": "Onsite W2 Only in Atlanta, GA",
            "state": "ineligible",
            "pipeline_stage": "not_applied",
            "description": (
                "Requirements:\n"
                "- 12+ years of experience in accounting operations, GAAP, CPA license, SOX compliance, general ledger, and month-end close."
            ),
        },
    ]
    bridge._save_raw_state(raw)

    state = bridge.get_full_workspace_state()
    by_id = {j["job_id"]: j for j in state["jobs"]}

    strong = by_id["job_ai_pm_strong"]
    good = by_id["job_cse_good"]
    inelig_pm = by_id["job_us_only_ai_pm"]
    low_acct = by_id["job_accounting_low"]

    assert strong["match_score_pct"] >= 84
    assert strong["match_tier"] == "Strong Match"
    assert strong["match_breakdown"]["role_fit_pct"] >= 90
    assert strong["match_breakdown"]["skills_fit_pct"] >= 80
    assert any("AI" in s or "Automation" in s for s in strong["matched_skills"])

    assert 65 <= good["match_score_pct"] < strong["match_score_pct"]
    assert good["match_tier"] in ("Good Match", "Strong Match")

    assert inelig_pm["match_breakdown"]["role_fit_pct"] >= 88
    assert inelig_pm["match_breakdown"]["logistics_fit_pct"] <= 35
    assert inelig_pm["match_score_pct"] <= 68
    assert any("US Residence" in g for g in inelig_pm["missing_gaps"])

    assert low_acct["match_score_pct"] < 45
    assert low_acct["match_tier"] == "Low Match"
    assert any("Accounting" in g for g in low_acct["missing_gaps"])

    # Verify KB edit invalidates match_cache_key and recomputes automatically
    old_cache_key = strong["match_cache_key"]
    bridge.execute_action(
        "save_kb_header",
        {
            "full_name": "Alex Mercer",
            "headline": "Financial Controller & CPA Accounting Lead",
            "location": "Batumi, Georgia",
            "email": "alex.mercer@example.com",
        },
    )
    raw_after = bridge._load_raw_state()
    raw_after["onboarding"]["preferences"]["desired_titles"] = ["Financial Controller", "Accounting Operations"]
    bridge._save_raw_state(raw_after)

    state_2 = bridge.get_full_workspace_state()
    by_id_2 = {j["job_id"]: j for j in state_2["jobs"]}
    assert by_id_2["job_ai_pm_strong"]["match_cache_key"] != old_cache_key


def test_score_jobs_with_jev_calibrates_via_openrouter_decisions_and_wires_macos_and_companion_ui(
    tmp_path: Path, monkeypatch
) -> None:
    import io
    import json
    import urllib.request

    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-jev-key")
    bridge.execute_action(
        "save_kb_header",
        {
            "full_name": "Alex Mercer",
            "headline": "Software Product Manager | AI Business Automation",
            "location": "Batumi, Georgia",
            "email": "alex.mercer@example.com",
        },
    )
    bridge.execute_action(
        "save_kb_section",
        {
            "section_id": "skills",
            "markdown": "Product roadmap, Applied AI, LLM product requirements, AI agents, workflow automation, developer platform, KPIs.",
        },
    )

    raw = bridge._load_raw_state()
    raw.setdefault("onboarding", {}).setdefault("preferences", {})["desired_titles"] = [
        "Software Product Manager",
        "AI Business Automation",
    ]
    raw["jobs"] = [
        {
            "job_id": "job_jev_1",
            "direct_employer_id": "emp_gitlab",
            "company_name": "GitLab",
            "title": "Senior Product Manager, AI Powered Duo",
            "canonical_url": "https://about.gitlab.com/jobs/ai-pm",
            "workplace_mode": "remote",
            "location_label": "Remote (Global)",
            "eligible_countries": ["GE", "GLOBAL"],
            "sponsorship_offered": False,
            "is_open": True,
            "salary_max_usd": 205000,
            "eligible": True,
            "eligibility_manual_override": True,
            "state": "ready_to_submit",
            "pipeline_stage": "not_applied",
            "description": "Own GitLab Duo AI agents, LLM workflows, developer platform roadmap, and product KPIs.",
        }
    ]
    bridge._save_raw_state(raw)

    captured_jev_payloads: list[dict] = []

    class _FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    real_urlopen = urllib.request.urlopen

    def _mock_urlopen(req, timeout=12.0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "openrouter.ai/api/alpha/decisions" in url:
            body = json.loads(req.data.decode("utf-8"))
            captured_jev_payloads.append(body)
            mock_ans = {
                "model": "typesafe/jev-1.14-20261014",
                "answers": {
                    "role_scope_match": {"noul": 0.88},
                    "skills_domain_match": {"noul": 0.84},
                    "experience_seniority_match": {"noul": 0.82},
                    "logistics_work_auth_match": {"noul": 0.91},
                },
            }
            return _FakeResp(json.dumps(mock_ans).encode("utf-8"))
        return real_urlopen(req, timeout=timeout)

    monkeypatch.setattr(urllib.request, "urlopen", _mock_urlopen)

    res = bridge.execute_action("score_jobs_with_jev", {"job_id": "job_jev_1"})
    assert len(captured_jev_payloads) == 1
    sent = captured_jev_payloads[0]
    assert sent["model"] == "~typesafe/jev-latest"
    assert set(sent["questions"].keys()) == {
        "role_scope_match",
        "skills_domain_match",
        "experience_seniority_match",
        "logistics_work_auth_match",
    }

    scored_job = res["jobs"][0]
    assert scored_job["match_jev_verified"] is True
    assert scored_job["match_model"] == "typesafe/jev-1.14-20261014"
    assert scored_job["match_score_pct"] >= 85
    assert scored_job["match_jev_scores"]["role_scope_match"] == 0.88

    # Verify macOS Swift UI and Chrome Companion Extension wiring
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert "public let matchScorePct: Int" in swift_src
    assert '@Published public var jobSortOrder: String = "newest"' in swift_src
    assert "public func scoreJobsWithJev(" in swift_src
    assert "private func compactMatchScorePill(for job: JobItem)" in swift_src
    assert "private func profileMatchInspectorCard(_ job: JobItem)" in swift_src

    content_js = Path("packaging/extensions/autoapply_companion/content.js").read_text(encoding="utf-8")
    assert "function renderMatchBadgeHTML(pct, isJev)" in content_js
    assert "function estimateClientMatchPct(" in content_js


def test_submit_resume_package_flushes_draft_edits_submits_and_locks_document_and_job(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    bridge.execute_action(
        "save_profile_header",
        {
            "full_name": "Alex Mercer",
            "headline": "Senior Product Manager | AI Business Automation",
            "email": "alex.mercer@example.com",
            "phone": "+1 555 234 5670",
            "location": "Batumi, Georgia",
            "linkedin_url": "https://www.linkedin.com/in/alexander-mercer/",
        },
    )
    added = bridge.execute_action(
        "add_job_posting",
        {
            "title": "Senior Product Manager, Applied AI",
            "company_name": "Udemy",
            "canonical_url": "https://boards.greenhouse.io/udemy/jobs/987654",
            "description": (
                "Lead Applied AI product strategy, LLM workflows, cross-functional engineering delivery, "
                "and measurable learner engagement outcomes."
            ),
        },
    )
    udemy_job = next(j for j in added["jobs"] if j["company_name"] == "Udemy")
    state = bridge.execute_action(
        "generate_tailored_document",
        {"job_id": udemy_job["job_id"]},
    )
    assert len(state["documents"]) >= 1
    draft_doc = state["documents"][0]
    assert draft_doc["is_submitted"] is False
    doc_id = draft_doc["artifact_id"]
    job_id = draft_doc["job_id"]
    orig_sha = draft_doc["pdf_sha256"]

    edited_resume_md = draft_doc["resume_markdown"].replace(
        "## SUMMARY\n",
        "## SUMMARY\nCustom draft note verified before clicking Submit Package.\n",
        1,
    )

    submitted_state = bridge.execute_action(
        "submit_resume_package",
        {
            "document_id": doc_id,
            "job_id": job_id,
            "company_name": "Udemy",
            "role_title": "Senior Product Manager, Applied AI",
            "resume_markdown": edited_resume_md,
            "cover_letter_markdown": draft_doc["cover_letter_markdown"],
            "dry_run": True,
        },
    )

    updated_doc = next(d for d in submitted_state["documents"] if d["artifact_id"] == doc_id)
    assert updated_doc["is_submitted"] is True
    assert "Custom draft note verified before clicking Submit Package." in updated_doc["resume_markdown"]
    assert Path(updated_doc["pdf_path"]).is_file()
    assert Path(updated_doc["cover_letter_pdf_path"]).is_file()
    assert updated_doc["pdf_sha256"] != orig_sha

    updated_job = next(j for j in submitted_state["jobs"] if j["job_id"] == job_id)
    assert updated_job["pipeline_stage"] == "submitted"
    assert updated_job["state"] == "submitted_verified"
    assert updated_job["remote_receipt_id"].startswith("ATS-")
    assert "Submitted tailored Resume & Cover Letter package for Udemy" in submitted_state["action_notice"]


def test_draft_and_filter_labels_have_no_circular_dots_and_submit_package_button_wired() -> None:
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")

    # 1. Primary Submit Package button + background submission action wired for Draft resumes
    assert '@Published public var submittingDocumentId: String = ""' in swift_src
    assert "public func submitResumePackage(_ doc: DocumentArtifactItem)" in swift_src
    assert '"submit_resume_package"' in swift_src
    assert 'Text("Submit Package")' in swift_src
    assert 'Label("Submit Package", systemImage: "paperplane.fill")' in swift_src

    # 2. resumeSubmissionStatusPill has zero Circle() dots next to "Draft" or "Submitted"
    pill_start = swift_src.index("private func resumeSubmissionStatusPill(")
    pill_end = swift_src.index("private func myResumeListRow(", pill_start)
    pill_body = swift_src[pill_start:pill_end]
    assert 'Text("Draft")' in pill_body
    assert "Circle()" not in pill_body

    # 3. Other label/filter pills also have zero Circle() dots
    for fn_sig, next_sig in [
        ("private func compactKpiChip(", "private func workerLanesSection"),
        ("private func jobBoardFilterPill(", "private func jobBoardsSectionCard("),
    ]:
        if fn_sig in swift_src and next_sig in swift_src:
            s_idx = swift_src.index(fn_sig)
            e_idx = swift_src.index(next_sig, s_idx)
            assert "Circle()" not in swift_src[s_idx:e_idx]


def test_dual_tier_webp_icon_compression_preserves_high_res_originals(tmp_path: Path) -> None:
    """Verify profile photo and contact/company avatars generate low-res 96x96 WebP icons while preserving high-res originals."""
    from PIL import Image

    app_support = tmp_path / "app_support"
    bridge = AppWorkspaceManager(app_support_dir=app_support)

    # 1. Create a realistic high-resolution 1200x1200 RGBA PNG profile image
    src_photo = tmp_path / "highres_headshot.png"
    hi_img = Image.new("RGBA", (1200, 1200), (36, 98, 210, 255))
    for y in range(0, 1200, 24):
        for x in range(0, 1200, 24):
            hi_img.putpixel((x, y), ((x * 7) % 255, (y * 5) % 255, 180, 255))
    hi_img.save(src_photo, format="PNG")

    upload_state = bridge.execute_action("upload_profile_photo", {"file_path": str(src_photo)})
    hdr = upload_state["knowledge_base"]["profile_header"]
    orig_path = Path(hdr["photo_path"])
    thumb_path = Path(hdr["photo_thumb_path"])

    assert orig_path.exists()
    assert thumb_path.exists()
    assert thumb_path.suffix == ".webp"
    assert thumb_path.name == "profile_avatar_icon_96.webp"

    # Full-resolution 1200x1200 original is preserved intact for high-DPI PDF/DOCX resume export
    with Image.open(orig_path) as preserved_orig:
        assert preserved_orig.size == (1200, 1200)

    # Low-res WebP icon is <= 96x96, valid RIFF/WEBP, and dramatically smaller
    raw_webp = thumb_path.read_bytes()
    assert raw_webp[:4] == b"RIFF" and raw_webp[8:12] == b"WEBP"
    with Image.open(thumb_path) as webp_thumb:
        assert webp_thumb.size == (96, 96)
    assert thumb_path.stat().st_size < orig_path.stat().st_size

    # 2. Seed a legacy high-res flat contact avatar in avatars/ and verify migration to avatars/originals + avatars/thumbs_96/*.webp
    avatars_dir = app_support / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)
    legacy_flat = avatars_dir / "person_jane_doe.jpg"
    contact_hi = Image.new("RGB", (800, 800), (180, 72, 95))
    contact_hi.save(legacy_flat, format="JPEG", quality=95)

    st_logged = bridge.execute_action(
        "send_or_queue_thread_message",
        {
            "thread_id": "thr_webp_jane_doe",
            "company": "Stripe",
            "role": "Senior Product Manager",
            "contact_name": "Jane Doe",
            "contact_handle": "jane.doe@stripe.com",
            "channel": "email",
            "subject": "Senior Product Manager",
            "message_text": "Hi Jane, reaching out regarding the Senior PM role.",
            "mode": "send_now",
        },
    )
    jane_thread = next(t for t in st_logged["outreach_tracker"]["threads"] if t["contact_name"] == "Jane Doe")
    av_thumb = Path(jane_thread["avatar_path"])
    av_orig = Path(jane_thread["avatar_original_path"])

    assert av_thumb.exists()
    assert av_thumb.suffix == ".webp"
    assert av_thumb.parent.name == "thumbs_96"
    assert av_orig.exists()
    assert av_orig.parent.name == "originals"

    with Image.open(av_orig) as orig_im:
        assert orig_im.size == (800, 800)
    with Image.open(av_thumb) as thumb_im:
        assert thumb_im.size == (96, 96)

    # 3. Removing profile photo cleans up both original and WebP thumbnail
    removed_state = bridge.execute_action("upload_profile_photo", {"remove": True})
    removed_hdr = removed_state["knowledge_base"]["profile_header"]
    assert removed_hdr["photo_path"] == ""
    assert removed_hdr["photo_thumb_path"] == ""
    assert not orig_path.exists()
    assert not thumb_path.exists()


def test_messages_preview_responsiveness_pagination_and_off_main_thread_thumbnails() -> None:
    """Verify Swift Messages tab uses ImageIO off-main-thread thumbnail caching, O(1) filter snapshots, Equatable subviews, and progressive infinite-scroll pagination."""
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")

    # 1. Off-main-thread ImageIO downsampling & WebP thumbnail cache
    assert "public final class FastThumbnailCache" in swift_src
    assert "CGImageSourceCreateThumbnailAtIndex" in swift_src
    assert "kCGImageSourceShouldCacheImmediately" in swift_src
    assert "public struct CachedAvatarImageView: View, Equatable" in swift_src
    assert '@Published public var profilePhotoThumbPath: String = ""' in swift_src

    # 2. Precompiled regex & NSCache text/link processor + Equatable row & bubble subviews
    assert "public enum MessageTextProcessor" in swift_src
    assert "private struct OutreachConversationRowView: View, Equatable" in swift_src
    assert "private struct OutreachMessageBubbleView: View, Equatable" in swift_src

    # 3. Single-pass O(1) outreach filtering & counts (no O(N^2) per-row filteredOutreachThreads scan)
    assert "public struct OutreachCountsSnapshot: Equatable" in swift_src
    assert "private func rebuildOutreachCaches(resetPagination: Bool)" in swift_src
    assert "isSelected: store.selectedOutreachThreadId == thread.id" in swift_src

    # 4. Progressive infinite-scroll pagination for both conversation list and long message transcripts
    assert "public static let outreachPageSize: Int = 40" in swift_src
    assert "public static let transcriptPageSize: Int = 30" in swift_src
    assert "@Published public var outreachVisiblePageLimit: Int = 40" in swift_src
    assert "@Published public var transcriptVisibleMessageLimit: Int = 30" in swift_src
    assert "public func loadMoreOutreachThreadsIfNeeded(currentIndex: Int)" in swift_src
    assert "public func loadNextOutreachThreadsPage()" in swift_src
    assert "public func loadEarlierTranscriptMessages(totalCount: Int)" in swift_src
    assert "ForEach(threads.prefix(250))" not in swift_src

    # 5. Zero synchronous main-thread NSImage(contentsOfFile:) inside FollowUpTrackerWorkspaceView or ProfileAvatarThumbnail
    followup_start = swift_src.index("struct FollowUpTrackerWorkspaceView: View")
    followup_end = swift_src.index("private var blockedAddressesWorkspaceView: some View", followup_start)
    assert "NSImage(contentsOfFile:" not in swift_src[followup_start:followup_end]

    profile_thumb_start = swift_src.index("struct ProfileAvatarThumbnail: View")
    profile_thumb_end = swift_src.index("struct ToastNotificationOverlayView: View", profile_thumb_start)
    assert "NSImage(contentsOfFile:" not in swift_src[profile_thumb_start:profile_thumb_end]


def test_native_browser_dialog_guard_main_world_and_cdp_decision_engine() -> None:
    """Verify native JS pop-ups (`alert`, `confirm`, `prompt`, `beforeunload`) never freeze automation and follow intent-aware safety rules."""
    import json as _json
    import subprocess as _subprocess

    from autoapply.app_bridge import _decide_js_dialog_action, _load_companion_dialog_guard_js

    # 1. Verify manifest.json injects dialog_guard_main.js at document_start in world: MAIN across all_frames
    manifest = _json.loads(Path("packaging/extensions/autoapply_companion/manifest.json").read_text(encoding="utf-8"))
    cs_list = manifest["content_scripts"]
    assert cs_list[0]["js"] == ["dialog_guard_main.js"]
    assert cs_list[0]["run_at"] == "document_start"
    assert cs_list[0]["world"] == "MAIN"
    assert cs_list[0]["all_frames"] is True

    # 2. Verify Python CDP dialog decision engine
    gh_msg = "Answers cannot be changed once submitted. Are you ready to submit?"
    assert _decide_js_dialog_action("alert", "Application saved.") == (True, None)
    assert _decide_js_dialog_action("beforeunload", "Changes you made may not be saved.") == (True, None)
    assert _decide_js_dialog_action("confirm", gh_msg, allow_submit=True) == (True, None)
    assert _decide_js_dialog_action("confirm", gh_msg, allow_submit=False) == (False, None)
    assert _decide_js_dialog_action("confirm", gh_msg, allow_submit=True, has_unanswered_required=True) == (False, None)
    assert _decide_js_dialog_action("confirm", "Are you sure you want to withdraw your application?", allow_submit=True) == (
        False,
        None,
    )
    assert _decide_js_dialog_action("confirm", "Discard changes and leave without saving?", allow_submit=True) == (
        False,
        None,
    )
    assert _decide_js_dialog_action("prompt", 'Please type "CONFIRM" to proceed', allow_submit=True) == (
        True,
        "CONFIRM",
    )
    assert _decide_js_dialog_action("prompt", "Type DELETE to remove your account", allow_submit=True) == (
        False,
        None,
    )

    # 3. Execute dialog_guard_main.js in Node with a Greenhouse CandidateFacing.Form DOM fixture
    guard_js = _load_companion_dialog_guard_js()
    assert "installAutoApplyMainWorldDialogGuard" in guard_js

    node_harness = r"""
const fs = require("fs");
const vm = require("vm");
const code = fs.readFileSync("packaging/extensions/autoapply_companion/dialog_guard_main.js", "utf8");

const radioYes = {
  disabled: false,
  checked: false,
  required: false,
  name: "",
  value: "Yes",
  hidden: false,
  getAttribute: () => null,
  getBoundingClientRect: () => ({ width: 16, height: 16 }),
};
const radioNo = {
  disabled: false,
  checked: false,
  required: false,
  name: "",
  value: "No",
  hidden: false,
  getAttribute: () => null,
  getBoundingClientRect: () => ({ width: 16, height: 16 }),
};
const fieldset = {
  id: "28915165005",
  hidden: false,
  getAttribute: () => null,
  getBoundingClientRect: () => ({ width: 420, height: 90 }),
  querySelector: (sel) => (sel === "legend" ? { innerText: "Please confirm that you received the video interview link. Thank you!" } : null),
  querySelectorAll: (sel) => (sel.includes("radio") ? [radioYes, radioNo] : []),
};
const ghRoot = {
  getAttribute: (attr) =>
    attr === "data-react-props"
      ? JSON.stringify({ questions: [{ id: 28915165005, required: true, name_key: "question_28915165005" }] })
      : null,
};

const attrs = new Map();
const storage = new Map();
const listeners = new Map();

const docEl = {
  setAttribute: (k, v) => attrs.set(k, String(v)),
  getAttribute: (k) => (attrs.has(k) ? attrs.get(k) : null),
};

const win = {
  location: { href: "https://app5.greenhouse.io/application_form/50c885be9782b5c0d70afd6a685b2366?utm_medium=email" },
  alert: () => { throw new Error("NATIVE_ALERT_BLOCKED"); },
  confirm: () => { throw new Error("NATIVE_CONFIRM_BLOCKED"); },
  prompt: () => { throw new Error("NATIVE_PROMPT_BLOCKED"); },
  getComputedStyle: () => ({ display: "block", visibility: "visible", opacity: "1" }),
  addEventListener: (type, fn) => {
    if (!listeners.has(type)) listeners.set(type, []);
    listeners.get(type).push(fn);
  },
  dispatchEvent: (ev) => {
    for (const fn of listeners.get(ev.type) || []) fn(ev);
    return true;
  },
  CustomEvent: function(type, init) { this.type = type; this.detail = (init && init.detail) || {}; },
  sessionStorage: {
    getItem: (k) => (storage.has(k) ? storage.get(k) : null),
    setItem: (k, v) => storage.set(k, String(v)),
    removeItem: (k) => storage.delete(k),
  },
  CSS: { escape: (s) => s },
};

const doc = {
  readyState: "complete",
  documentElement: docEl,
  querySelector: (sel) => (sel.includes("CandidateFacing.Form") ? ghRoot : null),
  querySelectorAll: (sel) => {
    if (sel.includes("fieldset")) return [fieldset];
    return [];
  },
};
win.document = doc;

const ctx = vm.createContext({
  window: win,
  document: doc,
  CustomEvent: win.CustomEvent,
  CSS: win.CSS,
  Date,
  Math,
  Number,
  String,
  Boolean,
  Array,
  Object,
  Map,
  Set,
  RegExp,
  JSON,
});
vm.runInContext(code, ctx);

const ghMsg = "Answers cannot be changed once submitted. Are you ready to submit?";

// A. Armed in apply mode, but required radio is still unchecked -> must return false (fail-closed) without calling native confirm
win.__aaArmDialogGuard("apply", 60000);
const blankSubmitRes = win.confirm(ghMsg);

// B. Radio 'Yes' checked in apply mode -> must return true immediately
radioYes.checked = true;
const filledSubmitRes = win.confirm(ghMsg);

// C. Prefill mode -> must cancel submit finality confirm
win.__aaArmDialogGuard("prefill", 60000);
const prefillSubmitRes = win.confirm(ghMsg);

// D. Destructive confirm in apply mode -> must return false
win.__aaArmDialogGuard("apply", 60000);
const destructiveRes = win.confirm("Are you sure you want to withdraw your application?");

// E. Alert & token prompt -> non-blocking
const alertRes = win.alert("Receipt confirmed.");
const promptRes = win.prompt('Type "YES" to confirm receipt', "");

// F. onbeforeunload neutralized while armed, restored when disarmed
const unloadFn = () => "Leave?";
win.onbeforeunload = unloadFn;
const whileArmedUnload = win.onbeforeunload;
win.__aaDisarmDialogGuard();
const afterDisarmUnload = win.onbeforeunload === unloadFn;

console.log(JSON.stringify({
  blankSubmitRes,
  filledSubmitRes,
  prefillSubmitRes,
  destructiveRes,
  alertRes: alertRes === undefined,
  promptRes,
  whileArmedUnload,
  afterDisarmUnload,
  reasons: win.__aaHandledDialogs.map((d) => d.reason),
}));
"""
    proc = _subprocess.run(["node", "-e", node_harness], capture_output=True, text=True, check=True)
    out = _json.loads(proc.stdout.strip())
    assert out["blankSubmitRes"] is False
    assert out["filledSubmitRes"] is True
    assert out["prefillSubmitRes"] is False
    assert out["destructiveRes"] is False
    assert out["alertRes"] is True
    assert out["promptRes"] == "YES"
    assert out["whileArmedUnload"] is None
    assert out["afterDisarmUnload"] is True
    assert out["reasons"] == [
        "blocked_unanswered_required_controls",
        "accepted_submit_finality_confirm",
        "cancelled_submit_in_prefill_mode",
        "dismissed_destructive_confirm",
        "auto_accepted_alert",
        "accepted_prompt_token",
    ]


def test_greenhouse_receipt_confirmation_radio_dedup_and_jev_option_enforcement(tmp_path: Path) -> None:
    """Verify Greenhouse CandidateFacing.Form unnamed <fieldset><legend> radio groups deduplicate to 1 field and JEV strictly enforces 'Yes' within ['Yes', 'No']."""
    content_js = Path("packaging/extensions/autoapply_companion/content.js").read_text(encoding="utf-8")
    background_js = Path("packaging/extensions/autoapply_companion/background.js").read_text(encoding="utf-8")

    # 1. Companion main-world arming & unnamed <fieldset><legend> radio group deduplication
    assert "function armMainWorldDialogGuard(" in content_js
    assert "COMPANION_ARM_DIALOG_GUARD" in content_js
    assert "COMPANION_ARM_DIALOG_GUARD" in background_js
    assert "COMPANION_RECOVER_FROZEN_TAB" in background_js
    assert "const radioGroupFieldMap = new Map();" in content_js

    # 2. Verify Greenhouse Receipt Confirmation form schema produces deterministic 'Yes'
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    gh_fields = [
        {
            "field_id": "aa_field_0_28915165005",
            "field_key": "aa_field_0_28915165005",
            "id": "28915165005",
            "name": "28915165005",
            "tag": "input",
            "type": "radio",
            "label": "Please confirm that you received the video interview link. Thank you!",
            "required": True,
            "options": ["Yes", "No"],
        }
    ]
    st = bridge.execute_action(
        "companion_prepare_and_prefill_job",
        {
            "mode": "apply",
            "skip_doc_regen": True,
            "canonical_url": "https://app5.greenhouse.io/application_form/50c885be9782b5c0d70afd6a685b2366?utm_medium=email",
            "title": "Receipt confirmation",
            "company_name": "Greenhouse",
            "form_fields": gh_fields,
        },
    )
    pkg = st["prefill_package"]
    assert pkg["field_values"]["aa_field_0_28915165005"] == "Yes"

    # 3. Even if an ungrounded LLM candidate answer produced 'N/A' or '0', JEV must enforce valid option 'Yes'
    jev_check = bridge._verify_form_answers_with_jev(
        api_key=None,
        kb_ground_truth="Alex Mercer - Senior Product Manager",
        detected_fields=gh_fields,
        candidate_answers={"aa_field_0_28915165005": "N/A"},
        baseline_answers={"aa_field_0_28915165005": "Yes"},
        standard_profile={"email": "alex.mercer@example.com", "linkedin_url": "https://www.linkedin.com/in/alexander-mercer/"},
    )
    assert jev_check["verified_answers"]["aa_field_0_28915165005"] == "Yes"
    assert jev_check["corrections_made"]


def test_mark_action_required_thread_as_replied_or_followup_and_wake_on_new_inbound(tmp_path: Path) -> None:
    """Verify marking an Action Required (Details Requested) thread as Replied or Follow-Up when waiting on employer, plus auto-wakeup on a new inbound reply."""
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    raw = bridge._load_raw_state()
    anjalika_thread = {
        "id": "thr_techdigital_anjalika_1",
        "company": "Techdigitalcorp",
        "role": "Job Opening - Robotic Test Engineer | W2 Only | Onsite",
        "contact_name": "Anjalika Momin",
        "contact_handle": "anjalika@techdigitalcorp.com",
        "channel": "email",
        "subject": "Job Opening - Robotic Test Engineer | W2 Only | Onsite",
        "last_activity_at": "2026-10-01 10:39",
        "messages": [
            {
                "id": "msg_in_1",
                "sender_role": "them",
                "sender_name": "Anjalika Momin",
                "sender_handle": "anjalika@techdigitalcorp.com",
                "subject": "Job Opening - Robotic Test Engineer | W2 Only | Onsite",
                "body": (
                    "Hi, I'm Anjalika and I'm a US IT Recruiter at TechDigital Corporation. "
                    "Please have a look at the below job description and let me know your interest and availability."
                ),
                "timestamp": "2026-10-01 10:39",
            }
        ],
    }
    raw.setdefault("conversation_threads", []).append(anjalika_thread)
    bridge._save_raw_state(raw)

    initial_state = bridge.execute_action("get_state", {})
    th0 = next(t for t in initial_state["outreach_tracker"]["threads"] if t["id"] == "thr_techdigital_anjalika_1")
    assert th0["action_required"] is True
    assert th0["jev_classification"] == "action_required_details_requested"
    assert th0["jev_label"] == "Details Requested"

    # 1. Mark as Replied (user provided details and is waiting for them to get back)
    st_replied = bridge.execute_action(
        "set_outreach_thread_status",
        {"thread_id": "thr_techdigital_anjalika_1", "status": "replied"},
    )
    assert "Marked as Replied" in st_replied["action_notice"]
    th_rep = next(t for t in st_replied["outreach_tracker"]["threads"] if t["id"] == "thr_techdigital_anjalika_1")
    assert th_rep["action_required"] is False
    assert th_rep["followup_needed"] is False
    assert th_rep["jev_classification"] == "replied_waiting"
    assert th_rep["jev_label"] == "Replied"
    assert th_rep["status_badge"] == "Replied"
    assert th_rep["delivery_state"] == "replied"
    assert th_rep["last_activity_at"] == "2026-10-01 10:39"

    # 2. Mark as Follow-Up (user wants thread tracked under Follow-Up while waiting on them)
    st_followup = bridge.execute_action(
        "set_outreach_thread_status",
        {"thread_id": "thr_techdigital_anjalika_1", "status": "followup"},
    )
    assert "Marked as Follow-Up" in st_followup["action_notice"]
    th_fu = next(t for t in st_followup["outreach_tracker"]["threads"] if t["id"] == "thr_techdigital_anjalika_1")
    assert th_fu["action_required"] is False
    assert th_fu["followup_needed"] is True
    assert th_fu["jev_classification"] == "followup_manual"
    assert th_fu["jev_label"] == "Follow-Up"
    assert th_fu["status_badge"] == "Follow-Up"
    assert th_fu["delivery_state"] == "followup_due"

    # 3. Mark back as Action Required preserves detected subtype (Details Requested)
    st_ar = bridge.execute_action(
        "set_outreach_thread_status",
        {"thread_id": "thr_techdigital_anjalika_1", "status": "action_required"},
    )
    assert "Marked as Action Required" in st_ar["action_notice"]
    th_ar = next(t for t in st_ar["outreach_tracker"]["threads"] if t["id"] == "thr_techdigital_anjalika_1")
    assert th_ar["action_required"] is True
    assert th_ar["followup_needed"] is False
    assert th_ar["jev_classification"] == "action_required_details_requested"
    assert th_ar["jev_label"] == "Details Requested"

    # 4. Mark as Replied again, then simulate a NEW inbound recruiter reply -> must automatically wake back up into Action Required!
    bridge.execute_action(
        "set_outreach_thread_status",
        {"thread_id": "thr_techdigital_anjalika_1", "status": "replied"},
    )
    raw_after = bridge._load_raw_state()
    persisted = next(c for c in raw_after["conversation_threads"] if c["id"] == "thr_techdigital_anjalika_1")
    persisted["messages"].append(
        {
            "id": "msg_in_2",
            "sender_role": "them",
            "sender_name": "Anjalika Momin",
            "sender_handle": "anjalika@techdigitalcorp.com",
            "subject": "Re: Job Opening - Robotic Test Engineer | W2 Only | Onsite",
            "body": "Thanks for sending your details! Are you available to schedule a Zoom call tomorrow afternoon?",
            "timestamp": "2026-10-29 14:10",
        }
    )
    bridge._save_raw_state(raw_after)

    woken_state = bridge.execute_action("get_state", {})
    th_woken = next(t for t in woken_state["outreach_tracker"]["threads"] if t["id"] == "thr_techdigital_anjalika_1")
    assert th_woken["action_required"] is True
    assert th_woken["jev_classification"] == "action_required_real_interview"
    assert th_woken["jev_label"] == "Real Interview"

    # 5. Verify macOS Swift UI exposes Mark as Replied & Mark as Follow-Up buttons + context menu actions
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert "public func setOutreachThreadStatus(" in swift_src
    assert "public func withManualStatus(" in swift_src
    assert '"set_outreach_thread_status"' in swift_src
    assert 'Label("Mark as Replied"' in swift_src
    assert 'Label("Mark as Follow-Up"' in swift_src
    assert "private struct ActionRowFlowLayout: Layout" in swift_src







def test_voice_interview_female_ava_voice_parity_and_varied_recommend_cues(tmp_path: Path) -> None:
    """Verify every AI Recommended Answer cue uses the exact same female voice pitch/timbre as original questions and rotates variations."""
    import subprocess
    import numpy as np

    audio_dir = Path("packaging/interview_audio")
    expected_recommend_files = (
        [f"ai_recommend_{i}.mp3" for i in range(12)]
        + [f"ai_recommend_done_{i}.mp3" for i in range(6)]
        + ["ai_recommend_start.mp3", "ai_recommend_done.mp3", "q_leadership.mp3"]
    )
    for fname in expected_recommend_files:
        fpath = audio_dir / fname
        assert fpath.is_file(), f"Missing interview audio clip: {fname}"
        assert fpath.stat().st_size > 8000, f"Audio clip unexpectedly small: {fname}"

    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    def _median_f0_hz(mp3_path: Path) -> float:
        wav_tmp = tmp_path / f"{mp3_path.stem}.wav"
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(mp3_path), str(wav_tmp)],
            check=True,
        )
        arr = bridge._decode_wav_bytes_to_16k_float32(wav_tmp.read_bytes())
        assert arr is not None and arr.size > 4000
        sr = 16000
        frame = int(0.04 * sr)
        hop = int(0.015 * sr)
        min_lag = int(sr / 340)
        max_lag = int(sr / 75)
        f0s: list[float] = []
        for s in range(0, len(arr) - frame, hop):
            seg = arr[s : s + frame]
            if float(np.sqrt(np.mean(seg * seg))) < 0.025:
                continue
            seg = seg - float(np.mean(seg))
            ac = np.correlate(seg, seg, mode="full")[frame - 1 :]
            if ac[0] <= 0:
                continue
            ac = ac / ac[0]
            window = ac[min_lag:max_lag]
            pk_idx = int(np.argmax(window)) + min_lag
            if ac[pk_idx] > 0.35:
                f0s.append(sr / pk_idx)
        assert f0s, f"No voiced frames detected in {mp3_path.name}"
        return float(np.median(f0s))

    orig_f0 = _median_f0_hz(audio_dir / "q_leadership.mp3")
    assert 175.0 <= orig_f0 <= 240.0

    # Verify representative start/done cues match the female (~200 Hz) voice and are NEVER male (~110-135 Hz)
    for sample_name in (
        "ai_recommend_start.mp3",
        "ai_recommend_done.mp3",
        "ai_recommend_0.mp3",
        "ai_recommend_5.mp3",
        "ai_recommend_11.mp3",
        "ai_recommend_done_0.mp3",
        "ai_recommend_done_3.mp3",
    ):
        cue_f0 = _median_f0_hz(audio_dir / sample_name)
        assert 175.0 <= cue_f0 <= 245.0, f"{sample_name} had non-female pitch {cue_f0:.1f} Hz"
        assert abs(cue_f0 - orig_f0) <= 32.0

    # Repeated clicks on AI Recommended Answer produce distinct answer variations without repeating back-to-back
    seen_drafts: list[str] = []
    cur_draft = ""
    for _ in range(3):
        st = bridge.execute_action(
            "generate_recommended_interview_answer",
            {
                "question_id": "q_leadership",
                "question_title": "Standard Screening Q&A",
                "question_prompt": "How do you answer common questions like 'Why are you looking for a new role?' or 'Describe your leadership style'?",
                "kb_section_id": "interview_qa",
                "current_draft": cur_draft,
            },
        )
        ans = st["last_voice_transcript"].strip()
        assert ans
        if seen_drafts:
            assert ans != seen_drafts[-1]
        seen_drafts.append(ans)
        cur_draft = ans
    assert len(set(seen_drafts)) == 3


def test_voice_interview_live_transcription_without_onnxruntime_and_single_newline_append(
    tmp_path: Path, monkeypatch
) -> None:
    """Verify Whisper live transcription works without onnxruntime even on quiet -40 dB speech and appends on a single new line below AI answers."""
    import importlib.util
    import subprocess
    import wave
    import numpy as np
    from faster_whisper import WhisperModel

    real_find_spec = importlib.util.find_spec

    def _no_onnx_find_spec(name: str, package=None):
        if name == "onnxruntime":
            return None
        return real_find_spec(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", _no_onnx_find_spec)

    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    model = WhisperModel("base", device="cpu", compute_type="int8")

    # 1. Pure room hum / silence returns "" with zero hallucinations
    rng = np.random.default_rng(42)
    silence = rng.normal(0.0, 0.0005, 16000 * 3).astype(np.float32)
    assert AppWorkspaceManager._transcribe_numpy_with_whisper_model(model, silence) == ""

    # 2. Quiet -40 dB speech embedded in 8 seconds of dead air transcribes accurately without onnxruntime
    wav_speech = tmp_path / "ava_source.wav"
    subprocess.run(
        [
            "afconvert",
            "-f",
            "WAVE",
            "-d",
            "LEI16@16000",
            "-c",
            "1",
            "packaging/interview_audio/ai_recommend_0.mp3",
            str(wav_speech),
        ],
        check=True,
    )
    arr = bridge._decode_wav_bytes_to_16k_float32(wav_speech.read_bytes())
    assert arr is not None
    quiet_embedded = np.concatenate(
        [
            np.zeros(16000 * 3, dtype=np.float32),
            (arr * 0.06).astype(np.float32),
            np.zeros(16000 * 5, dtype=np.float32),
        ]
    )
    live_txt = AppWorkspaceManager._transcribe_numpy_with_whisper_model(model, quiet_embedded)
    assert "good response" in live_txt.lower()

    # 3. Write quiet_embedded as a 16-bit PCM WAV and verify transcribe_voice_live + single-newline transcribe_voice_audio
    quiet_wav = tmp_path / "quiet_user_turn.wav"
    pcm16 = np.clip(quiet_embedded * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(quiet_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(pcm16.tobytes())

    live_res = bridge.execute_action("transcribe_voice_live", {"audio_path": str(quiet_wav)})
    assert "good response" in live_res["transcript"].lower()

    ai_answer = "I am seeking a senior Software Product Manager role where technical execution drives revenue."
    final_state = bridge.execute_action(
        "transcribe_voice_audio",
        {
            "audio_path": str(quiet_wav),
            "draft_text": ai_answer,
            "pre_typed_text": ai_answer,
            "question_id": "q_leadership",
        },
    )
    combined = final_state["last_voice_transcript"]
    assert combined.startswith(ai_answer + "\n")
    assert not combined.startswith(ai_answer + "\n\n")
    second_line = combined[len(ai_answer) + 1 :]
    assert "good response" in second_line.lower()


def test_voice_interview_swift_auto_resume_recorder_varied_cues_and_live_draft_guard() -> None:
    """Verify Swift Voice Interview wires 12 varied female cues, auto-resumes microphone capture, single-newline live typing, and background poll protection."""
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")

    # 1. Varied 12-cue start deck + 6-cue done deck + female voice fallback
    assert "private static let recommendStartCues: [(id: String, text: String)]" in swift_src
    assert '"ai_recommend_0"' in swift_src and '"ai_recommend_11"' in swift_src
    assert '"ai_recommend_done_0"' in swift_src and '"ai_recommend_done_5"' in swift_src
    assert "private func nextRecommendStartCue() -> (id: String, text: String)" in swift_src
    assert '"synthesize_interview_tts"' in swift_src
    assert "v.gender == .female" in swift_src

    # 2. Auto-resume microphone after AI Recommended Answer finishes speaking unless user explicitly stopped
    assert "@Published public var userExplicitlyStoppedSession: Bool = false" in swift_src
    assert "self.voiceRecorder.beginMicrophoneCapture(store: self, preserveDuration: true)" in swift_src

    # 3. Single-newline formatting below previously generated AI answer & sensitive desk-mic dB threshold
    assert 'let formattedWithNewline = cleaned + "\\n"' in swift_src
    assert 'let separator = preRecordingDraftText.hasSuffix("\\n\\n") ? "\\n\\n" : "\\n"' in swift_src
    assert "if power > -50.0 || peak > -36.0 {" in swift_src
    assert "let softSpeechPeriodicProbe =" in swift_src

    # 4. Background get_state polling guard so live transcription is never overwritten
    assert "allowVoiceDraftUpdate: Bool = false" in swift_src
    assert 'allowVoiceDraftUpdate: (action == "transcribe_voice_audio" || action == "generate_recommended_interview_answer")' in swift_src


def test_messages_sorted_by_date_descending_and_hourly_stale_sync_analysis(tmp_path: Path) -> None:
    """Verify messages are strictly sorted newest-first across all channels/filters, and stale/hourly sync_and_analyze_messages updates immediately."""
    import json
    import re
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    # Inject multiple threads with out-of-order RFC2822 and ISO dates + a consumer noise email
    injected_gmail_threads = {
        "thr_oct01": [
            {
                "id": "m_oct01",
                "from": "Anjalika Momin <anjalika@techdigitalcorp.com>",
                "to": "alex.mercer@example.com",
                "subject": "Job Opening - Robotic Test Engineer | W2 Only",
                "date": "Thu, 01 Oct 2026 10:39:00 +0400",
                "snippet": "Please have a look at the job description and let me know your availability.",
                "body": "Hi Alex, Please have a look at the job description and let me know your availability.",
            }
        ],
        "thr_nov02": [
            {
                "id": "m_nov02_1",
                "from": "Alex Mercer <alex.mercer@example.com>",
                "to": "Kateryna Recruiter <kateryna@infuse.com>",
                "subject": "Application: Senior Product Manager at INFUSE",
                "date": "2026-10-28T11:00:00+04:00",
                "snippet": "Hello Kateryna, I submitted my application.",
                "body": "Hello Kateryna, I submitted my application for Senior Product Manager.",
            },
            {
                "id": "m_nov02_2",
                "from": "Kateryna Recruiter <kateryna@infuse.com>",
                "to": "alex.mercer@example.com",
                "subject": "Re: Application: Senior Product Manager at INFUSE",
                "date": "Mon, 02 Nov 2026 15:45:00 +0400",
                "snippet": "Hi Alex, Please complete our short online assessment to move forward.",
                "body": "Hi Alex, Please complete our short online assessment at https://infuse.com/test to move forward.",
            },
        ],
        "thr_oct16": [
            {
                "id": "m_oct16",
                "from": "Veeva Recruiting <recruiting@veeva.com>",
                "to": "alex.mercer@example.com",
                "subject": "Interview invitation — Senior Product Manager at Veeva",
                "date": "Fri, 16 Oct 2026 14:20:00 +0400",
                "snippet": "We would love to schedule a 30-minute interview with you.",
                "body": "Hi Alex, We would love to schedule a 30-minute interview with you via Calendly.",
            }
        ],
        "thr_noise": [
            {
                "id": "m_noise",
                "from": "Google Cloud Platform <payments-noreply@google.com>",
                "to": "alex.mercer@example.com",
                "subject": "Google Cloud Platform & APIs: Payment received",
                "date": "Mon, 02 Nov 2026 16:00:00 +0400",
                "snippet": "Payment received",
                "body": "Thank you for your payment.",
            }
        ],
    }

    state = bridge.execute_action(
        "sync_and_analyze_messages",
        {
            "force": True,
            "fetched_gmail_threads": injected_gmail_threads,
        },
    )
    ot = state["outreach_tracker"]
    assert ot.get("last_message_analysis_at")
    threads = ot["threads"]
    assert len(threads) >= 3

    # Consumer noise must be excluded
    assert not any("payments-noreply@google.com" in str(t.get("contact_handle", "")).lower() for t in threads)

    # All threads must be sorted in descending order by normalized YYYY-MM-DD HH:MM last_activity_at
    timestamps = [t["last_activity_at"] for t in threads if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", str(t.get("last_activity_at") or ""))]
    assert timestamps == sorted(timestamps, reverse=True), f"Expected descending dates, got: {timestamps}"
    assert timestamps[0].startswith("2026-11-02 ")

    # Action Required subset must also be sorted newest first
    action_req = [t for t in threads if t.get("action_required")]
    ar_timestamps = [t["last_activity_at"] for t in action_req]
    assert ar_timestamps == sorted(ar_timestamps, reverse=True)

    # Freshness check: calling with if_stale_only=True right after sync should recognize it is fresh (<3600s)
    raw_loaded = json.loads((bridge.root / "workspace_state.json").read_text(encoding="utf-8"))
    from datetime import datetime, timezone, timedelta
    assert bridge._is_message_analysis_stale(raw_loaded, now=datetime.now(timezone.utc), max_age_seconds=3600) is False
    # After 3601 seconds have elapsed, _is_message_analysis_stale must return True so opening the app triggers immediate sync
    assert bridge._is_message_analysis_stale(
        raw_loaded,
        now=datetime.now(timezone.utc) + timedelta(seconds=3605),
        max_age_seconds=3600,
    ) is True


def test_jobs_sorted_by_date_newest_first_in_bridge_and_swift_ui(tmp_path: Path) -> None:
    """Verify jobs are sorted by posted_at date descending (newest at the top) in both backend state and Swift UI."""
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    state = bridge.execute_action(
        "discover_and_sync_eligible_jobs",
        {
            "run_live_discovery": False,
            "discovered_jobs": [
                {
                    "company_name": "OlderRoleCorp",
                    "title": "Senior Product Manager",
                    "canonical_url": "https://jobs.olderrolecorp.com/pm",
                    "pipeline_stage": "submitted",
                    "eligible": True,
                    "posted_at": "2026-10-16",
                },
                {
                    "company_name": "NewestRoleCorp",
                    "title": "AI Product Manager",
                    "canonical_url": "https://jobs.newestrolecorp.com/ai-pm",
                    "pipeline_stage": "submitted",
                    "eligible": True,
                    "posted_at": "2026-11-02",
                },
                {
                    "company_name": "MidRoleCorp",
                    "title": "Staff Product Manager",
                    "canonical_url": "https://jobs.midrolecorp.com/staff-pm",
                    "pipeline_stage": "submitted",
                    "eligible": True,
                    "posted_at": "2026-10-29",
                },
            ],
        },
    )
    jobs = state["jobs"]
    posted_dates = [j["posted_at"] for j in jobs if j.get("company_name") in {"OlderRoleCorp", "NewestRoleCorp", "MidRoleCorp"}]
    assert posted_dates == ["2026-11-02", "2026-10-29", "2026-10-16"]

    all_dates = [str(j.get("posted_at") or "")[:10] for j in jobs]
    assert all_dates == sorted(all_dates, reverse=True)

    # Verify Swift UI wiring for newest-first jobs sorting, newest-first messages cache sorting, and hourly/stale message analysis timer
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert '@Published public var jobSortOrder: String = "newest"' in swift_src
    assert "private static func threadSortTimestampKey(_ rawTs: String) -> String" in swift_src
    assert "public func isMessageAnalysisStale(maxAgeSeconds: TimeInterval = 3600) -> Bool" in swift_src
    assert "public func syncAndAnalyzeMessagesIfNeeded(force: Bool = false, maxAgeSeconds: TimeInterval = 3600, silent: Bool = true)" in swift_src
    assert "private func startHourlyMessageAnalysisTimer()" in swift_src
    assert "hourlyMessageAnalysisTimer = Timer.scheduledTimer(withTimeInterval: 3600.0, repeats: true)" in swift_src


def test_voice_interview_female_tts_synthesis_and_skip_without_popup_keeps_conversation_mode(tmp_path: Path, monkeypatch) -> None:
    """Verify AI-tailored questions synthesize female TTS without AttributeError and Skip during Conversation Mode skips immediately without popup while keeping conversation live."""
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    assert bridge.app_support_dir == bridge.root

    # Mock edge_tts save so unit test verifies _synthesize_interview_tts_female writes to self.root / "interview_audio"
    out_dir = bridge.root / "interview_audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    cached_mp3 = out_dir / "ai_role_metrics_deep_dive_eb70.mp3"
    cached_mp3.write_bytes(b"ID3" + b"\x00" * 2048)

    res = bridge.execute_action(
        "synthesize_interview_tts",
        {
            "question_id": "ai_role_metrics_deep_dive_eb70",
            "text": "Looking at Software Product Manager, R&D Apex Industrial — Vancouver, Canada | Full Time, what specific before-and-after metrics prove your impact?",
        },
    )
    assert res["status"] == "ok"
    assert res["audio_path"] == str(cached_mp3)

    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert "private func synthesizeNaturalQuestionFallback(questionId: String, prompt: String, repoRootDir: URL?)" in swift_src
    assert 'store.requestInterruptableAction {\n                                store.skipCurrentInterviewQuestion(q)\n                            }' not in swift_src
    assert "public func skipCurrentInterviewQuestion(_ q: InterviewQuestionItem)" in swift_src
    assert "if wasInConversation, let nextQ = nextSelectedQuestion {" in swift_src


def test_subscription_plan_display_pause_and_upgrade_flows(tmp_path: Path) -> None:
    """Verify active subscription plan display, Pause Subscription website cancellation flow, and Upgrade Plan flow."""
    import sqlite3
    import threading
    from services.licensing.api import licensing_routes

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db_lock = threading.Lock()
    licensing_routes.init_licensing_tables(conn)

    # 1. Activate a Monthly Pro license on server and verify plan metadata
    code, act_res = licensing_routes.activate_license_on_server(
        conn,
        db_lock,
        license_key="AA-LIVE-30USD-0001",
        device_id="mac_local_device",
    )
    assert code == 200
    assert act_res["plan"] == "monthly"
    assert act_res["plan_name"] == "Monthly Pro"
    assert act_res["plan_label"] == "Monthly Pro ($30/month)"
    assert act_res["can_upgrade"] is True
    assert act_res["recommended_upgrade_plan"] == "annual"

    # 2. Pause subscription for 2 months via pause_or_cancel_subscription
    p_code, p_res = licensing_routes.pause_or_cancel_subscription(
        conn,
        db_lock,
        action="pause",
        pause_months=2,
        license_key="AA-LIVE••••0001",
        device_id="mac_local_device",
    )
    assert p_code == 200
    assert p_res["ok"] is True
    assert p_res["subscription_state"] == "paused"
    assert p_res["pause_months"] == 2
    assert p_res["plan_label"] == "Monthly Pro ($30/month)"

    # 3. Cancel subscription via pause_or_cancel_subscription
    c_code, c_res = licensing_routes.pause_or_cancel_subscription(
        conn,
        db_lock,
        action="cancel",
        reason="I landed a job",
        license_key="AA-LIVE-30USD-0001",
        device_id="mac_local_device",
    )
    assert c_code == 200
    assert c_res["ok"] is True
    assert c_res["subscription_state"] == "cancel_scheduled"

    # 4. Verify AppWorkspaceManager entitlement state exposes active_plan, pause_subscription_url, and upgrade_subscription_url
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    state = bridge.execute_action(
        "activate_license_key",
        {"license_key": "AA-LIVE-30USD-0001", "skip_remote_validation": True},
    )
    ent = state["entitlement"]
    assert ent["active_plan"] == "monthly"
    assert ent["active_plan_name"] == "Monthly Pro"
    assert ent["active_plan_label"] == "Monthly Pro ($30/month)"
    assert ent["can_upgrade_plan"] is True
    assert ent["recommended_upgrade_plan"] == "annual"
    assert "https://turboapply.agency/job-searcher/license/cancel/" in ent["pause_subscription_url"]
    assert "mode=upgrade" in ent["upgrade_subscription_url"]

    # 5. Verify Swift UI displays subscription type, Upgrade Plan, and Pause Subscription instead of Manage Subscription
    swift_src = Path("apps/macos/AutoApply/Executable/main.swift").read_text(encoding="utf-8")
    assert '"Pro License Active — \\(planLabel)"' in swift_src
    assert 'Label("Pause Subscription", systemImage: "pause.circle")' in swift_src
    assert 'Label(store.upgradeSubscriptionButtonLabel, systemImage: "arrow.up.forward.circle.fill")' in swift_src
    assert "public func openUpgradeLicenseWebsite(targetPlan: String? = nil)" in swift_src
    assert "public func openPauseSubscriptionWebsite()" in swift_src
    assert 'Label("Manage Subscription"' not in swift_src


def test_lifecycle_emails_gateway_receipts_payment_lock_and_free_cycle_retention(monkeypatch) -> None:
    """Verify:
    1. Gateway confirmation receipt (ID + provider + email + Telegram) on pause/suspension and cancellation.
    2. Payment method lock on upgrade: paid by card (paddle) cannot upgrade via crypto unless cancelled first.
    3. All 7 editorial lifecycle emails (purchase_thank_you, trial_expiring, trial_expired, subscription_paused,
       subscription_cancelled, subscription_renewing_soon with greyed-out cancel link next to unsubscribe,
       and subscription_renewed with hidden 2-day revert link).
    4. Renewal revert / refund retention flow ('cancel_with_free_cycle') granting +1 full billing period on us.
    """
    import sqlite3
    import threading
    from services.licensing.api import licensing_routes

    sent_emails: list[dict] = []
    tg_messages: list[str] = []

    def fake_deliver_smtp_email(*, to_addr: str, subject: str, text_body: str, html_body: str):
        sent_emails.append(
            {
                "to": to_addr,
                "subject": subject,
                "text": text_body,
                "html": html_body,
            }
        )
        return True, "info@turboapply.agency", ""

    monkeypatch.setattr(licensing_routes, "_deliver_smtp_email", fake_deliver_smtp_email)

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db_lock = threading.Lock()
    licensing_routes.init_licensing_tables(conn)

    # 1. Purchase subscription with Card (Paddle) -> sends thank-you license email
    code, claim_res = licensing_routes.process_checkout_claim(
        conn,
        db_lock,
        customer_email="buyer@example.com",
        transaction_id="txn_card_monthly_001",
        subscription_id="sub_card_001",
        payment_provider="paddle",
        plan_id="monthly",
        device_id="mac_buyer_1",
        send_telegram_fn=tg_messages.append,
    )
    assert code == 200
    assert claim_res["ok"] is True
    assert claim_res["payment_provider"] == "paddle"
    assert claim_res["plan"] == "monthly"
    assert len(sent_emails) == 1
    assert "Thank you" in sent_emails[-1]["subject"]
    assert "Thank you. Your AutoApply license." in sent_emails[-1]["html"]

    # 2. Attempt to upgrade to Annual using Crypto while Card subscription is still active -> rejected (409)
    up_code, up_res = licensing_routes.process_checkout_claim(
        conn,
        db_lock,
        customer_email="buyer@example.com",
        transaction_id="0xabc123456789crypto",
        payment_provider="crypto",
        plan_id="annual",
        device_id="mac_buyer_1",
        mode="upgrade",
    )
    assert up_code == 409
    assert up_res["ok"] is False
    assert up_res["error"] == "payment_method_locked_until_cancelled"
    assert up_res["locked_payment_method"] == "paddle"
    assert "cancel your current subscription first" in up_res["message"]

    # 3. Pause subscription -> generates Gateway Suspension Receipt (PAD-SUSP-...) and emails receipt
    p_code, p_res = licensing_routes.pause_or_cancel_subscription(
        conn,
        db_lock,
        action="pause",
        pause_months=2,
        customer_email="buyer@example.com",
        license_key=claim_res["license_key"],
        send_telegram_fn=tg_messages.append,
    )
    assert p_code == 200
    assert p_res["gateway_receipt_id"].startswith("PAD-SUSP-")
    assert p_res["gateway_provider"] == "Paddle Billing Gateway"
    assert p_res["gateway_status"] == "SUSPENDED"
    assert p_res["email_sent"] is True
    assert sent_emails[-1]["subject"] == "Subscription paused — confirmation receipt"
    assert p_res["gateway_receipt_id"] in sent_emails[-1]["html"]
    assert any(p_res["gateway_receipt_id"] in m for m in tg_messages)

    # 4. Cancel with "1 Billing Period On Us" retention offer (cancel_with_free_cycle)
    orig_expires = claim_res["expires_at"]
    f_code, f_res = licensing_routes.pause_or_cancel_subscription(
        conn,
        db_lock,
        action="cancel_with_free_cycle",
        customer_email="buyer@example.com",
        license_key=claim_res["license_key"],
        send_telegram_fn=tg_messages.append,
    )
    assert f_code == 200
    assert f_res["free_cycle_added"] is True
    assert f_res["added_period_days"] == 30
    assert f_res["expires_at"] > orig_expires
    assert f_res["gateway_receipt_id"].startswith("PAD-FREE1-")
    assert f_res["email_sent"] is True
    assert sent_emails[-1]["subject"] == "Subscription cancelled — confirmation receipt"
    assert "Sorry to see you go." in sent_emails[-1]["html"]
    assert "1 complimentary billing period on us" in sent_emails[-1]["html"]
    assert "Offer: Explore New Plans" in sent_emails[-1]["html"]

    # 5. Now that subscription is cancelled, upgrading via Crypto is allowed!
    up2_code, up2_res = licensing_routes.process_checkout_claim(
        conn,
        db_lock,
        customer_email="buyer@example.com",
        transaction_id="0xabc123456789crypto",
        payment_provider="crypto",
        plan_id="annual",
        device_id="mac_buyer_1",
        mode="upgrade",
    )
    assert up2_code == 200
    assert up2_res["ok"] is True
    assert up2_res["payment_provider"] == "crypto"
    assert up2_res["plan"] == "annual"

    # 6. Verify remaining lifecycle email templates: trial_expiring, trial_expired, subscription_renewing_soon, subscription_renewed
    for tpl in ("trial_expiring", "trial_expired", "subscription_renewing_soon", "subscription_renewed"):
        res = licensing_routes.send_lifecycle_email(
            template_type=tpl,
            recipient_email="buyer@example.com",
            license_key=claim_res["license_key"],
            plan_id="monthly",
            expires_at="2026-12-05T00:00:00Z",
            force_send=True,
            conn=conn,
            db_lock=db_lock,
        )
        assert res["ok"] is True

    all_html = "\n".join(e["html"] for e in sent_emails)
    assert "Your 2-day trial ends soon." in all_html
    assert "Your free trial has ended." in all_html
    assert "Renewing in 2 days." in all_html
    assert ">Unsubscribe</a> &middot; <a href=" in all_html
    assert ">Cancel subscription</a>" in all_html
    assert "Thank you for your support." in all_html
    assert "let us know within 2 days of this email and we will revert it" in all_html
    assert "action=refund" in all_html


def test_open_linkedin_resolves_specific_thread_or_profile_never_wrong_person(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    # 1. Niklas Huetzen resolves to his exact LinkedIn messaging thread URL with searchTerm
    niklas_url = bridge._resolve_linkedin_thread_url_for_outreach(
        custom_url="https://www.linkedin.com/messaging/",
        payload={
            "thread_id": "thr_linkedin_automindz_niklas_huetzen",
            "company": "Automindz / hyreflow",
            "contact_name": "Niklas Huetzen",
            "contact_handle": "linkedin.com/in/niklas-huetzen",
            "profile_url": "linkedin.com/in/niklas-huetzen",
        },
    )
    assert "linkedin.com/messaging/thread/2-ZjVkMDBlMzUtZDk0OC00ZDM2LThkYjItNjZhMDEwYzFjMjFkXzEwMA==" in niklas_url
    assert "searchTerm=Niklas%20Huetzen" in niklas_url
    assert niklas_url.rstrip("/") != "https://www.linkedin.com/messaging"

    # 2. Contact with bare linkedin.com/in/<slug> and generic /messaging/ thread_url resolves to https://www.linkedin.com/in/<slug>
    prof_url = bridge._resolve_linkedin_thread_url_for_outreach(
        custom_url="https://www.linkedin.com/messaging/",
        payload={
            "thread_id": "thr_linkedin_arize_ben",
            "company": "Arize AI",
            "contact_name": "Ben Redfern",
            "contact_handle": "linkedin.com/in/ben-redfern",
            "profile_url": "linkedin.com/in/ben-redfern",
        },
    )
    assert prof_url == "https://www.linkedin.com/in/ben-redfern"

    # 3. Contact without /messaging/thread/ or /in/ URL resolves to people search for that contact + company (never bare /messaging/)
    search_url = bridge._resolve_linkedin_thread_url_for_outreach(
        custom_url="https://simplifier.io/en/career/po",
        payload={
            "thread_id": "thr_linkedin_simplifier_tanya",
            "company": "Simplifier AG",
            "contact_name": "Tanya Gogova-Stang",
            "contact_handle": "",
            "profile_url": "",
        },
    )
    assert search_url == "https://www.linkedin.com/search/results/people/?keywords=Tanya%20Gogova-Stang%20Simplifier%20AG"


def test_queue_to_send_persists_in_chat_history_and_survives_concurrent_sync_and_filter_tabs(tmp_path: Path) -> None:
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    raw_init = bridge._load_raw_state()
    raw_init["conversation_threads"] = [
        {
            "id": "thr_linkedin_automindz_niklas_huetzen",
            "company": "Automindz / hyreflow",
            "role": "Senior AI Product Manager",
            "contact_name": "Niklas Huetzen",
            "contact_handle": "https://www.linkedin.com/in/niklas-huetzen",
            "profile_url": "https://www.linkedin.com/in/niklas-huetzen",
            "channel": "linkedin",
            "channel_label": "LinkedIn",
            "subject": "Senior AI Product Manager — Automindz / hyreflow",
            "thread_url": "https://www.linkedin.com/messaging/",
            "delivery_state": "replied",
            "last_activity_at": "2026-10-16 21:13",
            "manual_status": "followup",
            "messages": [
                {
                    "id": "niklas_msg_1",
                    "sender_role": "me",
                    "sender_name": "Alex Mercer",
                    "sender_handle": "linkedin.com/in/alex-mercer",
                    "subject": "Application",
                    "body": "Hi Niklas, thanks for connecting.",
                    "timestamp": "2026-10-16 11:44",
                    "delivery_status": "Verified Sent (LinkedIn DM)",
                },
                {
                    "id": "niklas_msg_2",
                    "sender_role": "them",
                    "sender_name": "Niklas Huetzen",
                    "sender_handle": "https://www.linkedin.com/in/niklas-huetzen",
                    "subject": "Re: Application",
                    "body": "Hi Alex, thanks for reaching out! Do you have a CV to pop over?",
                    "timestamp": "2026-10-16 15:54",
                    "delivery_status": "Inbound LinkedIn Reply",
                },
            ],
        }
    ]
    bridge._save_raw_state(raw_init)

    # Simulate a slow background task loading state BEFORE the user clicks "Queue to Send"
    stale_background_raw = bridge._load_raw_state()

    # User clicks "Queue to Send"
    queued_msg_text = "Hi Niklas, wanted to follow up on the CV I shared last week and see if you'd be open to a quick chat."
    res_after_queue = bridge.execute_action(
        "send_or_queue_thread_message",
        {
            "thread_id": "thr_linkedin_automindz_niklas_huetzen",
            "message_id": "msg_queued_niklas_99",
            "company": "Automindz / hyreflow",
            "role": "Senior AI Product Manager",
            "contact_name": "Niklas Huetzen",
            "contact_handle": "https://www.linkedin.com/in/niklas-huetzen",
            "channel": "linkedin",
            "subject": "Re: Senior AI Product Manager — Automindz / hyreflow",
            "message_text": queued_msg_text,
            "mode": "queue",
        },
    )

    # Now the slow background task finishes and calls _save_raw_state with its stale snapshot
    stale_background_raw["last_message_analysis_at"] = "2026-11-05 01:55:00"
    bridge._save_raw_state(stale_background_raw)

    # Reload full workspace state and verify the queued message was NOT wiped out and stays in Follow-Up + Queued
    final_state = bridge.get_full_workspace_state()
    threads = final_state["outreach_tracker"]["threads"]
    niklas_thread = next(t for t in threads if t["id"] == "thr_linkedin_automindz_niklas_huetzen")

    assert niklas_thread["delivery_state"] == "queued"
    assert niklas_thread["jev_classification"].startswith("followup_")
    assert "linkedin.com/messaging/thread/" in niklas_thread["thread_url"]

    queued_msgs = [m for m in niklas_thread["messages"] if m["id"] == "msg_queued_niklas_99"]
    assert len(queued_msgs) == 1
    q_msg = queued_msgs[0]
    assert q_msg["body"] == queued_msg_text
    assert q_msg["delivery_status"] == "Queued"
    assert "Est." in q_msg["queue_estimate"]


def test_reclassify_dropdown_and_arize_citeralabs_epsilonsolutions_classifications(tmp_path: Path) -> None:
    """
    Regression test for:
    1. Arize AI Hiring Team application confirmation ("We'll review your application, and if there's a fit,
       you can expect to hear from a member of our team soon to set up an intro call.") -> Submitted (`submitted_confirmation`), NOT Real Interview.
    2. Citeralabs — Mohammad Hamarsheh Web Summit networking message ("Thanks for connecting on the Web Summit app...
       Would you be up for a quick coffee or a 15-minute chat while we're there?") -> Resolved (`resolved_monitoring`), NOT Real Interview.
    3. Epsilonsolutions — Himanshu Jain cold IT recruiter JD outreach ("Immediate Interview :: Project Manager IT-related Level 2 ...
       My name is Himanshu and I'm an IT recruiter at Epsilon Solutions. Our records show that you are an experienced IT professional with experience in ____")
       -> Details Requested (`action_required_details_requested`), NOT Real Interview.
    4. Reclassify dropdown in thread actions menu (`Reclassify` submenu) supporting manual reclassification across all categories
       (`details_requested`, `online_assessment`, `real_interview`, `action_required`, `followup`, `submitted`, `rejected`, `replied`, `resolved`, and `auto`).
    """
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    arize_cls = bridge._jev_classify_conversation_thread(
        channel="email",
        company="Arize AI",
        role="AI Sales Engineer, EMEA",
        contact_name="Arize AI Hiring Team",
        subject="Thank you for your application to Arize AI!",
        delivery_state="received",
        messages=[
            {
                "sender": "Arize AI Hiring Team",
                "sender_role": "them",
                "body": (
                    "Hey Alex,\n\n"
                    "Thank you so much for your interest in a career at Arize AI! We appreciate the time and "
                    "effort you put into the application process for the AI Sales Engineer, EMEA role and it makes "
                    "our day to know you want to join our team. We'll review your application, and if there's a fit, "
                    "you can expect to hear from a member of our team soon to set up an intro call."
                ),
            }
        ],
    )
    assert arize_cls["jev_classification"] == "submitted_confirmation"
    assert arize_cls["action_required"] is False

    citeralabs_cls = bridge._jev_classify_conversation_thread(
        channel="email",
        company="Citeralabs",
        role="Meeting up at Web Summit Lisbon?",
        contact_name="Citeralabs — Mohammad Hamarsheh",
        subject="Meeting up at Web Summit Lisbon?",
        delivery_state="received",
        messages=[
            {
                "sender": "Mohammad Hamarsheh",
                "sender_role": "them",
                "body": (
                    "Hi Alexander,\n\n"
                    "Thanks for connecting on the Web Summit app. I'm Mohammad, co-founder of Citera. "
                    "We help brands show up in AI answers.\n\n"
                    "As a fellow founder building with AI, I'd enjoy swapping notes on AI automation.\n\n"
                    "I'll be at Web Summit Lisbon from Nov 9 to 12. Would you be up for a quick coffee or a "
                    "15-minute chat while we're there? Let me know a time that works."
                ),
            }
        ],
    )
    assert citeralabs_cls["jev_classification"] == "resolved_monitoring"
    assert citeralabs_cls["action_required"] is False

    epsilon_cls = bridge._jev_classify_conversation_thread(
        channel="email",
        company="Epsilonsolutions",
        role="Immediate Interview :: Project Manager IT-related Level 2",
        contact_name="Epsilonsolutions — Himanshu Jain",
        subject="Immediate Interview :: Project Manager IT-related Level 2",
        delivery_state="received",
        messages=[
            {
                "sender": "Himanshu Jain",
                "sender_role": "them",
                "body": (
                    "Dear Alex,\n\n"
                    "My name is Himanshu and I'm an IT recruiter at Epsilon Solutions. Our records show that "
                    "you are an experienced IT professional with experience in ______________. This experience "
                    "is relevant to one of my current openings.\n\n"
                    "Project Manager IT-related Level 2\n"
                    "Office Location: 620 Superior St. Victoria, British Columbia\n"
                    "Term: Contract\n\n"
                    "General Requirements\n"
                    "In addition to the qualifications and demonstrated expertise on projects..."
                ),
            }
        ],
    )
    assert epsilon_cls["jev_classification"] == "action_required_details_requested"
    assert epsilon_cls["action_required"] is True

    # Test manual reclassification via set_outreach_thread_status across all categories
    raw = bridge._load_raw_state()
    raw["conversation_threads"] = [
        {
            "id": "thr_email_reclassify_test",
            "channel": "email",
            "company": "Epsilonsolutions",
            "role": "Project Manager IT-related Level 2",
            "contact_name": "Himanshu Jain",
            "contact_role": "IT Recruiter",
            "contact_handle": "himanshu.j@epsilonsolutions.ca",
            "direction": "inbound",
            "subject": "Immediate Interview :: Project Manager IT-related Level 2",
            "last_message_snippet": "Dear Alex, My name is Himanshu...",
            "last_activity": "Oct 19",
            "status_badge": "Details Requested",
            "action_required": True,
            "unread": False,
            "starred": False,
            "delivery_state": "received",
            "thread_url": "https://mail.google.com/mail/u/0/#inbox/199fd4d9a613ed86",
            "messages": [
                {
                    "id": "msg_eps_1",
                    "sender": "Himanshu Jain",
                    "sender_role": "them",
                    "timestamp": "Oct 19, 18:03",
                    "direction": "inbound",
                    "body": "Dear Alex, My name is Himanshu and I'm an IT recruiter at Epsilon Solutions.",
                    "delivery_status": "Received",
                }
            ],
        }
    ]
    bridge._save_raw_state(raw)

    expected_classifications = {
        "details_requested": ("action_required_details_requested", True, "Details Requested"),
        "online_assessment": ("action_required_online_assessment", True, "Online Assessment"),
        "real_interview": ("action_required_real_interview", True, "Real Interview"),
        "followup": ("followup_manual", False, "Follow-Up"),
        "submitted": ("submitted_confirmation", False, "Submitted"),
        "rejected": ("rejected", False, "Rejected"),
        "replied": ("replied_waiting", False, "Replied"),
        "resolved": ("resolved_monitoring", False, "Resolved"),
        "action_required": ("action_required_details_requested", True, "Details Requested"),
    }

    for status_key, (expected_jev, expected_action, expected_badge) in expected_classifications.items():
        res = bridge.execute_action(
            "set_outreach_thread_status",
            {"thread_id": "thr_email_reclassify_test", "status": status_key},
        )
        threads = res["outreach_tracker"]["threads"]
        target = next(t for t in threads if t["id"] == "thr_email_reclassify_test")
        assert target["jev_classification"] == expected_jev
        assert target["action_required"] is expected_action
        assert target["status_badge"] == expected_badge

    # Verify reset to auto-classify
    res_auto = bridge.execute_action(
        "set_outreach_thread_status",
        {"thread_id": "thr_email_reclassify_test", "status": "auto"},
    )
    assert "outreach_tracker" in res_auto
    raw_after = bridge._load_raw_state()
    raw_target = next(t for t in raw_after["conversation_threads"] if t["id"] == "thr_email_reclassify_test")
    assert raw_target.get("manual_status", "") == ""

    # Verify Swift UI contains the Reclassify submenu and composer programmatic clearing guard
    main_swift = (Path(__file__).resolve().parents[1] / "apps" / "macos" / "AutoApply" / "Executable" / "main.swift").read_text(encoding="utf-8")
    assert 'Label("Reclassify", systemImage: "tag")' in main_swift
    assert "private func reclassifyThreadMenuItems(_ thread: OutreachThreadItem)" in main_swift
    assert "if !store.isClearingComposerProgrammatically {" in main_swift


def test_full_html_email_body_extraction_and_open_email_hash_preservation(tmp_path: Path) -> None:
    """
    Regression test for:
    1. Multipart/mixed and root text/html Gmail payloads (like Gikash Ray TSI2727 and Rahul Roy TechDigital)
       must extract the full HTML body text instead of failing with NameError on `html.unescape` and falling back
       to the ~200-char Gmail snippet.
    2. Forwarded emails ("---------- Forwarded message ---------") must not have their forwarded content stripped.
    3. Opening an email in AutoApply Browser must percent-encode `#` (`%23`) when calling `/json/new?...` and
       navigate existing Gmail tabs directly to `#all/<threadId>` (with `#search/<subject>` fallback) so `#all/<threadId>`
       is never stripped as an HTTP URI fragment.
    """
    import base64
    import urllib.parse
    import urllib.request

    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")

    html_body = (
        "<html><body>"
        "<p>Hi ,</p><p>Hope you are doing well.</p>"
        "<p>This is Gikash from Tanisha Systems, I have an urgent requirement which is given below. "
        "If you are interested, please share me your updated resume ASAP.</p>"
        "<p>Position: Hardware Design Engineer<br/>Location: Bartlesville, OK (Onsite)</p>"
        "<p>Job Description &amp; Skill Requirement:</p>"
        "<ul>"
        "<li>Define and develop hardware architecture.</li>"
        "<li>Provide technical expertise for electro-mechanical interfacing, schematics, and PCB development.</li>"
        "<li>Perform or review routine and complex electrical engineering tasks using current technology.</li>"
        "</ul>"
        "</body></html>"
    )
    b64_html = base64.urlsafe_b64encode(html_body.encode("utf-8")).decode("ascii").rstrip("=")
    multipart_payload = {
        "mimeType": "multipart/mixed",
        "body": {},
        "parts": [
            {
                "mimeType": "text/html",
                "body": {"data": b64_html, "size": len(html_body)},
            }
        ],
    }

    extracted = bridge._extract_gmail_payload_body(multipart_payload)
    assert "Position: Hardware Design Engineer" in extracted
    assert "Location: Bartlesville, OK (Onsite)" in extracted
    assert "Job Description & Skill Requirement:" in extracted
    assert "Provide technical expertise for electro-mechanical interfacing, schematics, and PCB development." in extracted
    assert len(extracted) > 350

    # Verify forwarded message preservation in _sanitize_email_body_text
    fwd_raw = (
        "---------- Forwarded message ---------\n"
        "From: Anish Singh <Anish.Singh@tanishasystems.com>\n"
        "Date: Thu, Sep 24, 2026 at 1:57 PM\n"
        "Subject: All Visa Accepted || Board Level Test Engineer || Santa Clara, CA\n"
        "To: <alex.mercer@example.com>\n\n"
        "Hi Alex,\nKey Responsibilities:\n- Perform first-level hardware triage and troubleshooting."
    )
    sanitized_fwd = bridge._sanitize_email_body_text(fwd_raw)
    assert "Perform first-level hardware triage and troubleshooting." in sanitized_fwd

    # Verify Gmail thread URL resolution and HTTP selector preservation (%23 for #all/<id>)
    resolved_url = bridge._resolve_gmail_thread_url_for_outreach(
        custom_url="https://mail.google.com/mail/u/0/#all/1a1ad273e8955057",
        payload={
            "thread_id": "thr_email_gmail_1a1ad273e8955057",
            "channel": "email",
            "company": "Tanishasystems",
            "contact_name": "Gikash Ray (TSI2727)",
            "contact_handle": "Gikash.Ray@tanishasystems.com",
            "subject": "Hardware Design Engineer || Bartlesville, OK (Onsite)",
        },
    )
    assert resolved_url == "https://mail.google.com/mail/u/0/#all/1a1ad273e8955057"

    encoded_url = urllib.parse.quote(resolved_url, safe=":/?&=%")
    req = urllib.request.Request(f"http://127.0.0.1:19225/json/new?{encoded_url}", method="PUT")
    assert "%23all/1a1ad273e8955057" in req.selector


def test_linkedin_connection_monitoring_and_automatic_followup_classification(tmp_path: Path) -> None:
    """Verify LinkedIn connection monitoring automatically upgrades connected invites and direct DMs to Follow-Up."""
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    raw = bridge._load_raw_state()
    raw["outreach_events"] = [
        {
            "id": "li_inv_lusine",
            "company": "Samako",
            "role": "AI Automation Specialist",
            "contact_name": "Lusine Manukyan",
            "channel": "linkedin_invite",
            "contact_value": "https://www.linkedin.com/in/lusine-manukyan-45b310209/",
            "contact_url": "https://www.linkedin.com/in/lusine-manukyan-45b310209/",
            "thread_url": "https://www.linkedin.com/in/lusine-manukyan-45b310209/",
            "subject": "AI Automation Specialist at Samako",
            "message_text": "",
            "status": "pending_invitation",
            "status_category": "pending_invite",
            "sent_at": "2026-10-30 06:28",
        },
        {
            "id": "li_inv_tony",
            "company": "Kodaris",
            "role": "Customer Account Manager",
            "contact_name": "Tony Zakula",
            "channel": "linkedin_invite",
            "contact_value": "https://www.linkedin.com/in/tonyzakula/",
            "contact_url": "https://www.linkedin.com/in/tonyzakula/",
            "thread_url": "https://www.linkedin.com/in/tonyzakula/",
            "subject": "Customer Account Manager at Kodaris",
            "message_text": "",
            "status": "pending_invitation",
            "status_category": "pending_invite",
            "sent_at": "2026-10-30 09:37",
        },
        {
            "id": "li_dm_cihub",
            "company": "CI HUB",
            "role": "Product Manager - Platform & Creative Products",
            "contact_name": "Andreas Michalski",
            "channel": "linkedin_dm",
            "contact_value": "https://www.linkedin.com/in/andreas-michalski-cihub/",
            "contact_url": "https://www.linkedin.com/in/andreas-michalski-cihub/",
            "thread_url": "https://www.linkedin.com/in/andreas-michalski-cihub/",
            "subject": "Product Manager at CI HUB",
            "message_text": "Hi Andreas, I'm Alex. I applied for the Product Manager - Platform & Creative Products role at CI HUB.",
            "status": "draft_followup",
            "status_category": "followup_needed_linkedin",
            "sent_at": "2026-11-06 01:24",
        },
    ]
    bridge._save_raw_state(raw)

    # 1. Before Lusine connects, Lusine and Tony are invite_pending (awaiting_connection), while Andreas is followup_due
    initial_tracker = bridge._build_outreach_tracker_state(bridge._load_raw_state())
    threads_before = {t["contact_name"]: t for t in initial_tracker["threads"] if t["channel"] == "linkedin"}
    assert threads_before["Lusine Manukyan"]["delivery_state"] == "invite_pending"
    assert threads_before["Lusine Manukyan"]["jev_classification"] == "awaiting_connection"
    assert threads_before["Tony Zakula"]["delivery_state"] == "invite_pending"
    assert threads_before["Andreas Michalski"]["delivery_state"] == "followup_due"
    assert threads_before["Andreas Michalski"]["jev_classification"] == "followup_due"
    assert threads_before["Andreas Michalski"]["followup_needed"] is True

    # 2. When sync_and_analyze_messages observes Lusine Manukyan connected on LinkedIn, she is upgraded to Follow-Up
    st_synced = bridge.execute_action(
        "sync_and_analyze_messages",
        {
            "force": True,
            "fetched_linkedin_connections": [
                {
                    "profile_url": "https://www.linkedin.com/in/lusine-manukyan-45b310209/",
                    "contact_name": "Lusine Manukyan",
                    "company": "Samako",
                    "role": "AI Automation Specialist",
                    "status": "accepted_observed_live_card",
                    "sent_at": "2026-11-04 14:00",
                }
            ],
        },
    )
    threads_after = {t["contact_name"]: t for t in st_synced["outreach_tracker"]["threads"] if t["channel"] == "linkedin"}
    assert threads_after["Lusine Manukyan"]["delivery_state"] == "followup_due"
    assert threads_after["Lusine Manukyan"]["jev_classification"] == "followup_due"
    assert threads_after["Lusine Manukyan"]["followup_needed"] is True
    assert any("Connected with Lusine Manukyan" in m["body"] for m in threads_after["Lusine Manukyan"]["messages"])
    # Tony remains in Invites (invite_pending) since he has not connected yet
    assert threads_after["Tony Zakula"]["delivery_state"] == "invite_pending"
    assert threads_after["Tony Zakula"]["jev_classification"] == "awaiting_connection"


def test_non_job_email_threads_filtered_out_of_messages(tmp_path: Path) -> None:
    """Verify consumer/banking/shopping/GitHub/marketing emails are filtered out while genuine job emails remain."""
    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support_email_filter")

    injected_gmail_threads = {
        "1a1b498ce22a8d13": [
            {
                "id": "m_newton",
                "from": "Newton <noreply@newton.co>",
                "to": "alex.mercer@example.com",
                "subject": "Action required: Please confirm your details",
                "date": "Sat, 07 Nov 2026 08:01:00 +0000",
                "snippet": "Personal details, Experience in crypto investing, Trusted Contact Person (TCP)",
                "body": "Just a friendly reminder that you are required to log in to update your information on file: Experience in crypto investing, Trusted Contact Person (TCP).",
            }
        ],
        "1a1b3eac240d492c": [
            {
                "id": "m_eqbank",
                "from": "alert@eqbank.ca",
                "to": "alex.mercer@example.com",
                "subject": "EQ Bank: Pre-authorized withdrawal",
                "date": "Sat, 07 Nov 2026 04:51:00 +0000",
                "snippet": "On 06 NOV 2026 a pre-authorized withdrawal of $55.00 was debited from your account",
                "body": "On 06 NOV 2026 a pre-authorized withdrawal of $55.00 was debited from your account ending in 6487. Thank you for banking with EQ Bank.",
            }
        ],
        "1a1b23dd01809301": [
            {
                "id": "m_brentwood",
                "from": "The Amazing Brentwood <connect@info.theamazingbrentwood.com>",
                "to": "alex.mercer@example.com",
                "subject": "Your Picture Perfect Holiday at The Amazing Brentwood",
                "date": "Fri, 06 Nov 2026 19:10:00 +0000",
                "snippet": "96 BOOK NOW for Photos with Santa and Family Portraits",
                "body": "BOOK NOW for Photos with Santa and printed for you to take home.",
            }
        ],
        "1a1b1a2a56cc02f7": [
            {
                "id": "m_hitch",
                "from": "Hitch <will-hitchplayerfinders.com@shared1.ccsend.com>",
                "to": "alex.mercer@example.com",
                "subject": "Find Partners, Coaches & Open Play FREE 👥🧢🎾",
                "date": "Fri, 06 Nov 2026 18:13:00 +0000",
                "snippet": "Email from Hitch Player Finder NEW Get less",
                "body": "Find Partners, Coaches & Open Play FREE.",
            }
        ],
        "1a1af241ff33d928": [
            {
                "id": "m_github",
                "from": "GitHub <noreply@github.com>",
                "to": "alex.mercer@example.com",
                "subject": "[GitHub] Claude is requesting updated permissions",
                "date": "Fri, 06 Nov 2026 06:35:00 +0000",
                "snippet": "A GitHub App, Claude, installed on your organization",
                "body": "A GitHub App, Claude, installed on your organization is requesting updated permissions.",
            }
        ],
        "1a1validjob000001": [
            {
                "id": "m_cresta",
                "from": "Cresta Hiring Team <recruiting@cresta.ai>",
                "to": "alex.mercer@example.com",
                "subject": "Update on your application: Forward Deployed Product Manager",
                "date": "Fri, 06 Nov 2026 20:38:00 +0000",
                "snippet": "Thank you for applying to Cresta for the Forward Deployed Product Manager role.",
                "body": "Thank you for applying to Cresta for the Forward Deployed Product Manager role. Would you have time for an intro call next week?",
            }
        ],
    }

    st = bridge.execute_action(
        "sync_and_analyze_messages",
        {
            "force": True,
            "fetched_gmail_threads": injected_gmail_threads,
        },
    )
    email_threads = [t for t in st["outreach_tracker"]["threads"] if t["channel"] == "email"]
    handles = {t["contact_handle"] for t in email_threads}
    companies = {t["company"] for t in email_threads}

    assert "recruiting@cresta.ai" in handles
    assert "Newton" not in companies
    assert "Eqbank" not in companies
    assert "The Amazing Brentwood" not in companies
    assert "Shared1" not in companies
    assert "GitHub" not in companies


def test_linkedin_multi_bubble_message_group_parsing() -> None:
    """Verify multi-bubble LinkedIn Messaging DOM events (paragraph + continuation URL bubble with empty sender) merge into the full message."""
    dom_events = [
        {
            "sender": "Alex Mercer",
            "time": "4:02 PM",
            "bodyText": "Hi Anna, thanks for connecting. I applied today to the Senior AI Strategist role at BrainHackathon.",
        },
        {
            "sender": "Anna Drobakha",
            "time": "4:06 PM",
            "bodyText": "Hi Alex, thanks for your message. Let’s plan an intro call in the upcoming week(s). Please book any convenient time slot via Calendly. Looking forward to connecting with you and learning more about you. Anna",
        },
        {
            "sender": "",
            "time": "",
            "bodyText": "https://calendly.com/hi-brainhackathon/30min",
        },
    ]
    parsed = AppWorkspaceManager._parse_linkedin_messaging_dom_events(
        dom_events,
        contact_name="Anna Drobakha",
        contact_handle="https://www.linkedin.com/in/adrobakha/",
        subject="Senior AI Strategist at BrainHackathon",
    )
    assert len(parsed) == 2
    assert parsed[0]["sender_role"] == "me"
    assert parsed[1]["sender_role"] == "them"
    assert parsed[1]["sender_name"] == "Anna Drobakha"
    assert parsed[1]["sender_handle"] == "linkedin.com/in/adrobakha"
    assert "Let’s plan an intro call in the upcoming week(s)." in parsed[1]["body"]
    assert "https://calendly.com/hi-brainhackathon/30min" in parsed[1]["body"]








