"""Writer role routing and budget guard for resumes, cover letters, and screening answers (P13).

Enforces AA-DOC-001, C-03:
- Uses exact model 'anthropic/claude-sonnet-5.5' via writer.primary route.
- Never silently falls back to Dolphin or another unapproved model for copywriting.
- Enforces per-run and daily USD budget caps before generation.
"""

from __future__ import annotations

from autoapply.providers.registry import (
    SONNET_WRITER_MODEL_ID,
    BudgetTracker,
    ProviderCapabilityError,
    ProviderRegistry,
    ProviderRole,
)


class WriterError(RuntimeError):
    """Raised when writer routing or budget authorization fails."""


class DocumentWriterService:
    """Manages writer-role model routing and spend authorization."""

    def __init__(self, *, registry: ProviderRegistry, budget: BudgetTracker) -> None:
        self._registry = registry
        self._budget = budget
        self._route = self._registry.get_route(ProviderRole.WRITER_PRIMARY)
        if self._route.model_id != SONNET_WRITER_MODEL_ID:
            raise WriterError(f"unapproved_writer_model: {self._route.model_id}")

    @property
    def active_model_id(self) -> str:
        return self._route.model_id

    def verify_model_override(self, requested_model_id: str) -> str:
        if requested_model_id != SONNET_WRITER_MODEL_ID:
            raise WriterError(
                f"unapproved_writer_model: expected '{SONNET_WRITER_MODEL_ID}', got '{requested_model_id}'"
            )
        return self._route.model_id

    def authorize_generation_spend(self, *, estimated_cost_usd: float) -> None:
        try:
            self._budget.record_And_authorize(estimated_cost_usd=estimated_cost_usd)
        except ProviderCapabilityError as exc:
            raise WriterError(str(exc)) from exc
