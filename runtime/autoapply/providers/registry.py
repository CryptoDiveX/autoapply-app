"""Provider capability registry, role routing, and Dolphin typed-action proposal adapter (P02).

Enforces AA-AUTH-001, AA-AUTH-002, AA-DOC-001, AA-JOB-004, NFR-03, C-03:
- Preserves exact model IDs ('anthropic/claude-sonnet-5.5' and
  'cognitivecomputations/dolphin-mistral-24b-venice-edition').
- Never silently normalizes to ':free' or substitutes another paid model.
- Separates missing auth, expired/revoked auth, and commercial gate G-02.
- Validates Dolphin text-only DOM action proposals via strict schema, element allowlist,
  and no-progress loop detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any


SONNET_WRITER_MODEL_ID = "anthropic/claude-sonnet-5.5"
DOLPHIN_FALLBACK_MODEL_ID = "cognitivecomputations/dolphin-mistral-24b-venice-edition"
CODEX_PRIMARY_MODEL_ID = "openai/codex-commercial-session"

ALLOWED_DOLPHIN_ACTIONS: frozenset[str] = frozenset(
    {
        "fill_field",
        "select_option",
        "click_element",
        "attach_approved_artifact",
        "request_human_takeover",
        "propose_submit",
    }
)

ALLOWED_PROPOSAL_FIELDS: frozenset[str] = frozenset(
    {
        "action",
        "target_element_id",
        "fact_id",
        "value",
        "artifact_id",
        "rationale",
    }
)


class ProviderCapabilityError(RuntimeError):
    """Raised when a model/provider route violates capability, gate, or budget constraints."""


class ProviderRole(str, Enum):
    """Distinct role bindings per 02-TECHNICAL-SPECIFICATION.md (§8) and C-03."""

    ORCHESTRATOR_PRIMARY = "orchestrator.primary"
    ORCHESTRATOR_FALLBACK = "orchestrator.fallback"
    WRITER_PRIMARY = "writer.primary"
    HELPER_COMPRESSION_AND_QA = "helper.compression_and_qa"


class AuthStatus(str, Enum):
    """Authentication status for a provider connector."""

    NOT_CONFIGURED = "not_configured"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass(frozen=True)
class ProviderRoute:
    """Capability-checked route definition."""

    role_id: ProviderRole
    provider: str
    model_id: str
    credential_ref: str
    supports_native_tools: bool
    supports_vision: bool
    supports_structured_outputs: bool
    context_length: int
    gate_id: str | None = None


class ProviderRegistry:
    """Capability-checked provider registry loaded from verified catalog metadata."""

    def __init__(self, routes: dict[ProviderRole, ProviderRoute]) -> None:
        self._routes = dict(routes)

    @classmethod
    def from_catalog_snapshot(cls, snapshot_path: Path) -> ProviderRegistry:
        raw = json.loads(snapshot_path.read_text(encoding="utf-8"))
        by_id: dict[str, dict[str, Any]] = {
            entry["id"]: entry for entry in raw.get("matching_models", [])
        }
        if SONNET_WRITER_MODEL_ID not in by_id or DOLPHIN_FALLBACK_MODEL_ID not in by_id:
            raise ProviderCapabilityError("catalog_snapshot_missing_required_models")

        sonnet_meta = by_id[SONNET_WRITER_MODEL_ID]
        sonnet_params = set(sonnet_meta.get("supported_parameters", []))
        sonnet_inputs = set(sonnet_meta.get("architecture", {}).get("input_modalities", []))

        dolphin_meta = by_id[DOLPHIN_FALLBACK_MODEL_ID]
        dolphin_params = set(dolphin_meta.get("supported_parameters", []))
        dolphin_inputs = set(dolphin_meta.get("architecture", {}).get("input_modalities", []))

        routes = {
            ProviderRole.ORCHESTRATOR_PRIMARY: ProviderRoute(
                role_id=ProviderRole.ORCHESTRATOR_PRIMARY,
                provider="openai_chatgpt_commercial",
                model_id=CODEX_PRIMARY_MODEL_ID,
                credential_ref="cred_chatgpt_commercial_oauth",
                supports_native_tools=True,
                supports_vision=True,
                supports_structured_outputs=True,
                context_length=128000,
                gate_id="G-02",
            ),
            ProviderRole.ORCHESTRATOR_FALLBACK: ProviderRoute(
                role_id=ProviderRole.ORCHESTRATOR_FALLBACK,
                provider="openrouter",
                model_id=DOLPHIN_FALLBACK_MODEL_ID,
                credential_ref="cred_openrouter_api_key",
                supports_native_tools="tools" in dolphin_params and "tool_choice" in dolphin_params,
                supports_vision="image" in dolphin_inputs,
                supports_structured_outputs="structured_outputs" in dolphin_params,
                context_length=int(dolphin_meta.get("context_length", 128000)),
                gate_id="G-03",
            ),
            ProviderRole.WRITER_PRIMARY: ProviderRoute(
                role_id=ProviderRole.WRITER_PRIMARY,
                provider="openrouter",
                model_id=SONNET_WRITER_MODEL_ID,
                credential_ref="cred_openrouter_api_key",
                supports_native_tools="tools" in sonnet_params and "tool_choice" in sonnet_params,
                supports_vision="image" in sonnet_inputs,
                supports_structured_outputs="structured_outputs" in sonnet_params,
                context_length=int(sonnet_meta.get("context_length", 1000000)),
                gate_id=None,
            ),
        }
        return cls(routes)

    def get_route(self, role: ProviderRole) -> ProviderRoute:
        if role not in self._routes:
            raise ProviderCapabilityError(f"unknown_provider_role: {role}")
        return self._routes[role]

    def validate_requested_model(self, role: ProviderRole, requested_model_id: str) -> ProviderRoute:
        route = self.get_route(role)
        if requested_model_id != route.model_id:
            raise ProviderCapabilityError(
                f"unapproved_model_identifier: role '{role.value}' requires exact model "
                f"'{route.model_id}', got '{requested_model_id}'"
            )
        return route

    def resolve_orchestrator(
        self,
        *,
        codex_auth_status: AuthStatus,
        codex_commercial_gate_approved: bool,
        openrouter_configured: bool,
        requires_vision: bool,
    ) -> ProviderRoute:
        if codex_auth_status in (AuthStatus.EXPIRED, AuthStatus.REVOKED):
            raise ProviderCapabilityError(
                f"reconnect_required: primary ChatGPT/Codex auth is {codex_auth_status.value}"
            )

        if codex_auth_status == AuthStatus.AUTHENTICATED:
            if not codex_commercial_gate_approved:
                raise ProviderCapabilityError(
                    "gate_G_02_unapproved: commercial ChatGPT/Codex client registration is not approved"
                )
            return self.get_route(ProviderRole.ORCHESTRATOR_PRIMARY)

        # Missing ChatGPT auth -> use exact requested Dolphin fallback if OpenRouter is configured
        if not openrouter_configured:
            raise ProviderCapabilityError("no_orchestration_credential_configured")

        fallback = self.get_route(ProviderRole.ORCHESTRATOR_FALLBACK)
        if requires_vision and not fallback.supports_vision:
            raise ProviderCapabilityError(
                f"vision_capability_unsupported: model '{fallback.model_id}' is text-only"
            )
        return fallback


@dataclass(frozen=True)
class TypedDomActionProposal:
    """Validated deterministic action proposal produced from DOM text inspection."""

    action: str
    target_element_id: str | None
    fact_id: str | None = None
    value: str | None = None
    artifact_id: str | None = None
    rationale: str | None = None


class DolphinActionProposalAdapter:
    """Validates plain-text JSON action proposals from Dolphin before PolicyBroker evaluation."""

    def __init__(self, *, max_identical_proposals: int = 2) -> None:
        self._max_identical_proposals = max_identical_proposals
        self._recent_fingerprints: list[str] = []

    def parse_and_validate(
        self,
        raw_response: str,
        *,
        allowed_element_ids: set[str],
    ) -> TypedDomActionProposal:
        try:
            payload = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise ProviderCapabilityError(f"malformed_action_proposal_json: {exc}") from exc

        if not isinstance(payload, dict):
            raise ProviderCapabilityError("action_proposal_must_be_json_object")

        unknown = set(payload.keys()) - ALLOWED_PROPOSAL_FIELDS
        if unknown:
            raise ProviderCapabilityError(
                f"unknown_or_forbidden_fields: {sorted(unknown)}"
            )

        action = payload.get("action")
        if not isinstance(action, str) or action not in ALLOWED_DOLPHIN_ACTIONS:
            raise ProviderCapabilityError(f"unsupported_action_type: {action!r}")

        target_id = payload.get("target_element_id")
        if action in ("fill_field", "select_option", "click_element", "attach_approved_artifact"):
            if not isinstance(target_id, str) or target_id not in allowed_element_ids:
                raise ProviderCapabilityError(
                    f"target_element_not_in_dom: {target_id!r}"
                )

        fingerprint = json.dumps(payload, sort_keys=True)
        identical_count = sum(1 for fp in self._recent_fingerprints if fp == fingerprint)
        if identical_count >= self._max_identical_proposals:
            raise ProviderCapabilityError("no_progress_limit_exceeded")
        self._recent_fingerprints.append(fingerprint)

        return TypedDomActionProposal(
            action=action,
            target_element_id=target_id,
            fact_id=payload.get("fact_id"),
            value=payload.get("value"),
            artifact_id=payload.get("artifact_id"),
            rationale=payload.get("rationale"),
        )


class BudgetTracker:
    """Enforces per-run and daily USD spending caps before dispatching billable model calls."""

    def __init__(self, *, per_run_limit_usd: float, daily_limit_usd: float) -> None:
        self._per_run_limit_usd = per_run_limit_usd
        self._daily_limit_usd = daily_limit_usd
        self._run_spent_usd = 0.0
        self._daily_spent_usd = 0.0

    def record_And_authorize(self, *, estimated_cost_usd: float) -> None:
        if estimated_cost_usd < 0:
            raise ProviderCapabilityError("negative_cost_invalid")
        if (
            self._run_spent_usd + estimated_cost_usd > self._per_run_limit_usd
            or self._daily_spent_usd + estimated_cost_usd > self._daily_limit_usd
        ):
            raise ProviderCapabilityError(
                "budget_exhausted: estimated spend exceeds configured per-run or daily cap"
            )
        self._run_spent_usd += estimated_cost_usd
        self._daily_spent_usd += estimated_cost_usd
