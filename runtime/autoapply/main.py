"""Isolated AutoApply runtime worker entrypoint (P07 / P28).

Runs strictly inside the app-owned environment constructed by RuntimeSupervisor.
Never touches ~/.hermes, ~/.codex, or global user site-packages.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import site
import sys
import tempfile

from autoapply.candidate.store import CandidateFactInput, CandidateStore, FactScope, ScopeLevel
from autoapply.connectors.gmail import GmailConnector, GmailMessage, GmailThread
from autoapply.connectors.networking import LinkedInNetworkingManager
from autoapply.documents.writer import DocumentWriterService
from autoapply.isolation import ALLOWED_PRODUCT_SKILLS, ALLOWED_PRODUCTION_TOOLS
from autoapply.licensing import EntitlementService
from autoapply.policy.broker import OutboundProposalContext, PolicyBroker
from autoapply.providers.registry import (
    SONNET_WRITER_MODEL_ID,
    BudgetTracker,
    ProviderRegistry,
    ProviderRole,
    ProviderRoute,
)


def build_health_payload() -> dict[str, object]:
    app_support = os.environ.get("AUTOAPPLY_APP_SUPPORT", "")
    hermes_home = os.environ.get("HERMES_HOME", "")
    if not app_support or not hermes_home:
        raise RuntimeError("worker_launched_without_isolated_app_support_env")

    hermes_path = Path(hermes_home).resolve()
    app_support_path = Path(app_support).resolve()
    if app_support_path not in hermes_path.parents:
        raise RuntimeError("hermes_home_outside_app_support_root")

    return {
        "status": "healthy",
        "app_support_root": str(app_support_path),
        "hermes_home": str(hermes_path),
        "user_site_disabled": os.environ.get("PYTHONNOUSERSITE") == "1"
        or not site.ENABLE_USER_SITE,
        "allowed_skills": sorted(ALLOWED_PRODUCT_SKILLS),
        "allowed_tools_count": len(ALLOWED_PRODUCTION_TOOLS),
    }


def run_bundle_self_test() -> dict[str, object]:
    health = build_health_payload()
    with tempfile.TemporaryDirectory(prefix="autoapply_selftest_") as tmp_dir:
        tmp = Path(tmp_dir)
        # 1. Verify CandidateStore
        store = CandidateStore(db_path=tmp / "candidate.sqlite3")
        fact_id = store.add_fact(
            CandidateFactInput(
                key="role_title",
                category="work_history",
                value="Senior Staff Engineer",
                source_type="user_entered",
                source_ref="onboarding:O-09",
                confidence=1.0,
                confirmed=True,
                scope=FactScope(level=ScopeLevel.GLOBAL),
                effective_from="2026-10-18",
            )
        )

        # 2. Verify DocumentWriterService (Sonnet 5.5)
        registry = ProviderRegistry(
            {
                ProviderRole.WRITER_PRIMARY: ProviderRoute(
                    role_id=ProviderRole.WRITER_PRIMARY,
                    provider="openrouter",
                    model_id=SONNET_WRITER_MODEL_ID,
                    credential_ref="cred_openrouter_api_key",
                    supports_native_tools=True,
                    supports_vision=True,
                    supports_structured_outputs=True,
                    context_length=200000,
                )
            }
        )
        budget = BudgetTracker(per_run_limit_usd=5.0, daily_limit_usd=25.0)
        writer = DocumentWriterService(registry=registry, budget=budget)

        # 3. Verify PolicyBroker 10-step evaluation
        artifact_bytes = b"Verified Resume Artifact PDF"
        artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()
        broker = PolicyBroker()
        decision = broker.evaluate(
            OutboundProposalContext(
                cancelled=False,
                platform_permissions_granted=True,
                account_identity_matches=True,
                licence_active=True,
                consent_current=True,
                mandate_revision_matches=True,
                facts_all_confirmed=True,
                approved_hash=artifact_sha,
                actual_hash=artifact_sha,
                target_domain_allowed=True,
                recipient_hard_bounced=False,
                dedupe_reservation_held=True,
                within_spend_and_rate_limits=True,
            )
        )

        # 4. Verify EntitlementService (120h trial)
        ent = EntitlementService(tmp / "entitlements.sqlite3", signing_secret="bundle-selftest-secret")
        lease = ent.activate_trial(
            device_id="macos_bundle_selftest",
            automation_ready=True,
            server_now=datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc),
        )

        # 5. Verify Gmail + LinkedIn connectors
        gmail = GmailConnector(account_email="jane@example.com")
        reconciled = gmail.reconcile_threads(
            threads=[
                GmailThread(
                    thread_id="th_1",
                    messages=[
                        GmailMessage(
                            message_id="m_1",
                            sender="no-reply@greenhouse.io",
                            recipient="jane@example.com",
                            subject="Thank you for applying to Acme Corp",
                            body="We received your application.",
                        )
                    ],
                )
            ],
            tracked_applications=[{"application_id": "app_acme", "company_name": "Acme Corp"}],
        )
        linkedin = LinkedInNetworkingManager()
        draft = linkedin.create_outreach_draft(
            application_id="app_acme",
            contact_id="c_1",
            message_body="Hi there!",
        )

    return {
        "status": "ok",
        "health": health,
        "latest_fact_id": fact_id,
        "writer_model": writer.active_model_id,
        "policy_broker_allowed": decision.allowed,
        "trial_hours": lease.trial_duration_hours,
        "lease_ttl_hours": lease.lease_ttl_hours,
        "gmail_reconciled_classification": reconciled["th_1"].classification,
        "linkedin_draft_status": draft.status,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="autoapply-worker")
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Emit isolated runtime health JSON and exit.",
    )
    parser.add_argument(
        "--bundle-self-test",
        action="store_true",
        help="Run end-to-end self-test across bundled runtime modules and emit JSON.",
    )
    parser.add_argument(
        "--bridge-action",
        type=str,
        default=None,
        help="Execute stateful AppWorkspaceManager action and emit JSON state.",
    )
    parser.add_argument(
        "--bridge-payload",
        type=str,
        default="{}",
        help="JSON payload for --bridge-action.",
    )
    args = parser.parse_args(argv)

    if args.health_check:
        payload = build_health_payload()
        sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
        sys.stdout.flush()
        return 0

    if args.bundle_self_test:
        payload = run_bundle_self_test()
        sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
        sys.stdout.flush()
        return 0

    if args.bridge_action:
        from autoapply.app_bridge import AppWorkspaceManager

        app_support = os.environ.get("AUTOAPPLY_APP_SUPPORT", "")
        if not app_support:
            app_support = str(Path.home() / "Library" / "Application Support" / "AutoApply")
        mgr = AppWorkspaceManager(Path(app_support))
        try:
            req_payload = json.loads(args.bridge_payload) if args.bridge_payload else {}
            result = mgr.execute_action(args.bridge_action, req_payload)
        except Exception as exc:
            result = mgr.get_full_workspace_state()
            result["error"] = str(exc)
        sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
        sys.stdout.flush()
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
