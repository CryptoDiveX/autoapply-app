"""Unit tests for Sonnet 5.5 writer routing and factual claim verification (P13).

Covers: AA-DOC-001, AA-DOC-003, AA-KB-002, C-03, C-11
Scenarios: T-DOC-01, T-MODEL-01, T-MODEL-02
"""

from __future__ import annotations

from pathlib import Path
import pytest

from autoapply.candidate.store import (
    CandidateFactInput,
    CandidateStore,
    FactScope,
    ScopeLevel,
)
from autoapply.documents.claims import (
    ClaimVerificationError,
    DraftClaim,
    verify_claims_against_confirmed_facts,
)
from autoapply.documents.writer import (
    DocumentWriterService,
    WriterError,
)
from autoapply.providers.registry import (
    BudgetTracker,
    ProviderRegistry,
)


CATALOG_SNAPSHOT = (
    Path(__file__).resolve().parents[2] / "docs" / "evidence" / "model-catalog-snapshot.json"
)


def test_writer_enforces_exact_sonnet_5_5_route_and_budget() -> None:
    """AA-DOC-001 / T-MODEL-01: Writer uses anthropic/claude-sonnet-5.5 and pauses on budget exhaustion."""
    registry = ProviderRegistry.from_catalog_snapshot(CATALOG_SNAPSHOT)
    budget = BudgetTracker(per_run_limit_usd=0.05, daily_limit_usd=1.00)
    writer = DocumentWriterService(registry=registry, budget=budget)

    assert writer.active_model_id == "anthropic/claude-sonnet-5.5"

    # Rejects any attempt to route writing through Dolphin or an unapproved model
    with pytest.raises(WriterError, match="unapproved_writer_model"):
        writer.verify_model_override("cognitivecomputations/dolphin-mistral-24b-venice-edition")

    # Exhausting budget blocks writer generation
    writer.authorize_generation_spend(estimated_cost_usd=0.04)
    with pytest.raises(WriterError, match="budget_exhausted"):
        writer.authorize_generation_spend(estimated_cost_usd=0.02)


def test_claim_verifier_rejects_unconfirmed_or_hallucinated_metrics_dates_and_employers(
    tmp_path: Path,
) -> None:
    """T-DOC-01 / AA-DOC-003: Every generated claim must map to a confirmed candidate fact."""
    store = CandidateStore(db_path=tmp_path / "candidate.db")

    confirmed_emp_id = store.add_fact(
        CandidateFactInput(
            key="employment.acme",
            category="employment",
            value={
                "employer": "Acme Corp",
                "title": "Senior Backend Engineer",
                "start": "2022-01",
                "end": "2026-08",
                "metrics": ["Reduced API latency by 40%"],
            },
            source_type="user_confirmed_resume",
            source_ref="res_1",
            confidence=1.0,
            confirmed=True,
            scope=FactScope(level=ScopeLevel.GLOBAL),
            effective_from="2026-10-18",
        )
    )
    unconfirmed_skill_id = store.add_fact(
        CandidateFactInput(
            key="skills.unconfirmed",
            category="skill",
            value=["Rust", "Kubernetes"],
            source_type="resume_extracted_unconfirmed",
            source_ref="res_1",
            confidence=0.60,
            confirmed=False,
            scope=FactScope(level=ScopeLevel.GLOBAL),
            effective_from="2026-10-18",
        )
    )

    # 1. Supported claim backed by confirmed fact passes
    valid_claim = DraftClaim(
        statement="Reduced API latency by 40% as Senior Backend Engineer at Acme Corp (2022-01 to 2026-08).",
        supporting_fact_ids=(confirmed_emp_id,),
        claimed_employer="Acme Corp",
        claimed_metric="Reduced API latency by 40%",
    )
    diff = verify_claims_against_confirmed_facts([valid_claim], candidate_store=store)
    assert diff.all_supported is True
    assert diff.verified_claim_count == 1

    # 2. Claim referencing an unconfirmed fact fails QA
    unconfirmed_claim = DraftClaim(
        statement="Production Rust and Kubernetes expert.",
        supporting_fact_ids=(unconfirmed_skill_id,),
        claimed_employer=None,
        claimed_metric=None,
    )
    with pytest.raises(ClaimVerificationError, match="claim_references_unconfirmed_or_missing_fact"):
        verify_claims_against_confirmed_facts([unconfirmed_claim], candidate_store=store)

    # 3. Hallucinated metric ("90%" instead of "40%") fails QA
    hallucinated_metric = DraftClaim(
        statement="Reduced API latency by 90% at Acme Corp.",
        supporting_fact_ids=(confirmed_emp_id,),
        claimed_employer="Acme Corp",
        claimed_metric="Reduced API latency by 90%",
    )
    with pytest.raises(ClaimVerificationError, match="unsupported_metric_or_employer_in_claim"):
        verify_claims_against_confirmed_facts([hallucinated_metric], candidate_store=store)
