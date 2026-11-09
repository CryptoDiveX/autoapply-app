"""Contract tests for provider capability registry, role routing, and Dolphin action adapter (P02).

Covers: AA-AUTH-001, AA-AUTH-002, AA-DOC-001, AA-JOB-004, NFR-03, C-03
Scenarios: T-AUTH-02, T-MODEL-01, T-MODEL-02, T-MODEL-03
"""

from __future__ import annotations

from pathlib import Path
import pytest

from autoapply.providers.registry import (
    DOLPHIN_FALLBACK_MODEL_ID,
    SONNET_WRITER_MODEL_ID,
    AuthStatus,
    BudgetTracker,
    DolphinActionProposalAdapter,
    ProviderCapabilityError,
    ProviderRegistry,
    ProviderRole,
)


CATALOG_SNAPSHOT = (
    Path(__file__).resolve().parents[2] / "docs" / "evidence" / "model-catalog-snapshot.json"
)


def test_exact_model_identifiers_and_catalog_capabilities() -> None:
    """T-MODEL-01: Preserve exact model IDs and reflect actual catalog capabilities."""
    registry = ProviderRegistry.from_catalog_snapshot(CATALOG_SNAPSHOT)

    assert SONNET_WRITER_MODEL_ID == "anthropic/claude-sonnet-5.5"
    assert DOLPHIN_FALLBACK_MODEL_ID == "cognitivecomputations/dolphin-mistral-24b-venice-edition"

    writer = registry.get_route(ProviderRole.WRITER_PRIMARY)
    assert writer.model_id == "anthropic/claude-sonnet-5.5"
    assert writer.supports_native_tools is True
    assert writer.supports_vision is True
    assert writer.supports_structured_outputs is True

    fallback = registry.get_route(ProviderRole.ORCHESTRATOR_FALLBACK)
    assert fallback.model_id == "cognitivecomputations/dolphin-mistral-24b-venice-edition"
    assert fallback.supports_native_tools is False
    assert fallback.supports_vision is False
    assert fallback.supports_structured_outputs is False


def test_rejects_silent_free_variant_or_unapproved_model_substitution() -> None:
    """T-MODEL-01 / T-MODEL-02: Never normalize to :free or silently swap models."""
    registry = ProviderRegistry.from_catalog_snapshot(CATALOG_SNAPSHOT)

    with pytest.raises(ProviderCapabilityError, match="unapproved_model_identifier"):
        registry.validate_requested_model(
            ProviderRole.ORCHESTRATOR_FALLBACK,
            "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
        )

    with pytest.raises(ProviderCapabilityError, match="unapproved_model_identifier"):
        registry.validate_requested_model(
            ProviderRole.ORCHESTRATOR_FALLBACK,
            "anthropic/claude-sonnet-5.5",
        )


def test_routing_semantics_for_missing_vs_expired_auth_and_commercial_gate() -> None:
    """C-03 / T-AUTH-02 / T-MODEL-02: Separate missing auth, expired auth, and G-02 gate."""
    registry = ProviderRegistry.from_catalog_snapshot(CATALOG_SNAPSHOT)

    # 1. Commercial gate G-02 closed: primary ChatGPT route cannot be used directly
    with pytest.raises(ProviderCapabilityError, match="gate_G_02_unapproved"):
        registry.resolve_orchestrator(
            codex_auth_status=AuthStatus.AUTHENTICATED,
            codex_commercial_gate_approved=False,
            openrouter_configured=True,
            requires_vision=False,
        )

    # 2. Missing ChatGPT auth routes to Dolphin fallback when OpenRouter is configured
    route = registry.resolve_orchestrator(
        codex_auth_status=AuthStatus.NOT_CONFIGURED,
        codex_commercial_gate_approved=False,
        openrouter_configured=True,
        requires_vision=False,
    )
    assert route.model_id == DOLPHIN_FALLBACK_MODEL_ID

    # 3. Expired/revoked ChatGPT auth demands reconnect rather than silent paid fallback
    with pytest.raises(ProviderCapabilityError, match="reconnect_required"):
        registry.resolve_orchestrator(
            codex_auth_status=AuthStatus.EXPIRED,
            codex_commercial_gate_approved=True,
            openrouter_configured=True,
            requires_vision=False,
        )

    # 4. Vision-dependent step on text-only Dolphin fails closed (C-03)
    with pytest.raises(ProviderCapabilityError, match="vision_capability_unsupported"):
        registry.resolve_orchestrator(
            codex_auth_status=AuthStatus.NOT_CONFIGURED,
            codex_commercial_gate_approved=False,
            openrouter_configured=True,
            requires_vision=True,
        )


def test_dolphin_typed_action_adapter_enforces_strict_schema_and_progress() -> None:
    """C-03 / T-MODEL-02: Validate Dolphin DOM text action proposals deterministically."""
    adapter = DolphinActionProposalAdapter(max_identical_proposals=2)

    valid_raw = (
        '{"action": "fill_field", "target_element_id": "el_first_name", '
        '"fact_id": "fact_given_name", "value": "Alex", "rationale": "Match confirmed name"}'
    )
    proposal = adapter.parse_and_validate(valid_raw, allowed_element_ids={"el_first_name"})
    assert proposal.action == "fill_field"
    assert proposal.target_element_id == "el_first_name"

    # Reject unknown fields or arbitrary shell/eval attempts
    with pytest.raises(ProviderCapabilityError, match="unknown_or_forbidden_fields"):
        adapter.parse_and_validate(
            '{"action": "fill_field", "target_element_id": "el_first_name", "shell": "rm -rf /"}',
            allowed_element_ids={"el_first_name"},
        )

    # Reject unauthorized action types
    with pytest.raises(ProviderCapabilityError, match="unsupported_action_type"):
        adapter.parse_and_validate(
            '{"action": "execute_javascript", "target_element_id": "el_first_name"}',
            allowed_element_ids={"el_first_name"},
        )

    # Reject hallucinated DOM element IDs not present in the inspected page projection
    with pytest.raises(ProviderCapabilityError, match="target_element_not_in_dom"):
        adapter.parse_and_validate(
            '{"action": "click_element", "target_element_id": "el_nonexistent"}',
            allowed_element_ids={"el_first_name"},
        )

    # Detect no-progress loops when identical action is proposed repeatedly
    adapter.parse_and_validate(valid_raw, allowed_element_ids={"el_first_name"})
    with pytest.raises(ProviderCapabilityError, match="no_progress_limit_exceeded"):
        adapter.parse_and_validate(valid_raw, allowed_element_ids={"el_first_name"})


def test_budget_tracker_pauses_billable_work_on_cap_exhaustion() -> None:
    """T-MODEL-03: Per-run and daily USD budgets pause before overspending."""
    budget = BudgetTracker(per_run_limit_usd=0.50, daily_limit_usd=2.00)
    budget.record_And_authorize(estimated_cost_usd=0.30)
    with pytest.raises(ProviderCapabilityError, match="budget_exhausted"):
        budget.record_And_authorize(estimated_cost_usd=0.25)
