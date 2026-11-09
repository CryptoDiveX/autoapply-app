"""Unit tests for canonical job matching, remote-vs-country eligibility, and 30-day employer dedupe (P16).

Covers: AA-JOB-001, AA-JOB-002, AA-JOB-003
Scenarios: T-JOB-01, T-JOB-02
"""

from __future__ import annotations

from pathlib import Path
import pytest

from autoapply.engine.dedupe import (
    DedupeConflictError,
    EmployerDedupeLedger,
    normalize_job_url,
)
from autoapply.engine.matching import (
    CandidateJobPreferences,
    JobPosting,
    evaluate_job_eligibility,
)


def test_remote_label_does_not_imply_worldwide_eligibility_and_checks_sponsorship() -> None:
    """T-JOB-01 / AA-JOB-002: Remote (US-only) or no-sponsorship roles are excluded before paid writing."""
    candidate_prefs = CandidateJobPreferences(
        residence_country="CA",
        authorized_countries={"CA": True, "US": False},
        requires_sponsorship_by_country={"CA": False, "US": True},
        accepted_workplace_modes={"remote", "hybrid"},
        minimum_salary_usd=150000,
        excluded_employers={"blocked_corp"},
    )

    # 1. "Remote" job restricted to US residents fails eligibility for a CA resident
    us_remote_job = JobPosting(
        job_id="job_us_remote",
        direct_employer_id="acme_corp",
        canonical_role_id="gh_4001",
        canonical_url="https://boards.greenhouse.io/acme/jobs/4001",
        title="Staff Backend Engineer (Remote - US)",
        workplace_mode="remote",
        eligible_countries=("US",),
        sponsorship_offered=True,
        is_open=True,
        salary_max_usd=185000,
    )
    res_us = evaluate_job_eligibility(us_remote_job, candidate_prefs)
    assert res_us.eligible is False
    assert res_us.exclusion_reason == "country_residence_or_location_ineligible"

    # 2. Eligible country ("CA") + no sponsorship needed in CA + open role passes
    ca_remote_job = JobPosting(
        job_id="job_ca_remote",
        direct_employer_id="acme_corp",
        canonical_role_id="gh_4002",
        canonical_url="https://boards.greenhouse.io/acme/jobs/4002",
        title="Staff Backend Engineer (Remote - Canada)",
        workplace_mode="remote",
        eligible_countries=("CA", "US"),
        sponsorship_offered=False,
        is_open=True,
        salary_max_usd=185000,
    )
    res_ca = evaluate_job_eligibility(ca_remote_job, candidate_prefs)
    assert res_ca.eligible is True

    # 3. Closed role is excluded before spending on document writing
    closed_job = JobPosting(**{**ca_remote_job.__dict__, "is_open": False})
    assert evaluate_job_eligibility(closed_job, candidate_prefs).exclusion_reason == "role_closed"


def test_dedupe_across_url_aliases_end_client_and_rolling_30_day_employer_window(
    tmp_path: Path,
) -> None:
    """T-JOB-02 / AA-JOB-003: Normalize URL tracking params, recruiter end-client, and 30d window."""
    assert (
        normalize_job_url("https://boards.greenhouse.io/Acme/jobs/4002/?utm_source=linkedin&gh_jid=4002#apply")
        == "https://boards.greenhouse.io/acme/jobs/4002"
    )

    ledger = EmployerDedupeLedger(db_path=tmp_path / "dedupe.db", rolling_window_days=30)

    # First reservation for direct employer 'acme_corp' at day 0 succeeds
    res1 = ledger.reserve_job(
        job_id="job_1",
        direct_employer_id="acme_corp",
        canonical_role_id="gh_4002",
        canonical_url="https://boards.greenhouse.io/acme/jobs/4002?utm_source=x",
        owner_id="worker_1",
        now_epoch_seconds=1_760_000_000,
    )
    assert res1.direct_employer_id == "acme_corp"

    # Duplicate role/URL alias via a recruiter agency for the same end-client 'acme_corp' is blocked
    with pytest.raises(DedupeConflictError, match="duplicate_role_or_rolling_employer_window"):
        ledger.reserve_job(
            job_id="job_2_recruiter_alias",
            direct_employer_id="acme_corp",
            canonical_role_id="gh_4002",
            canonical_url="https://boards.greenhouse.io/Acme/jobs/4002/",
            owner_id="worker_1",
            now_epoch_seconds=1_760_000_100,
        )

    # Different role at the same direct employer within the 30-day window is blocked when policy=30d
    with pytest.raises(DedupeConflictError, match="duplicate_role_or_rolling_employer_window"):
        ledger.reserve_job(
            job_id="job_3_same_employer_10d_later",
            direct_employer_id="acme_corp",
            canonical_role_id="gh_9999",
            canonical_url="https://boards.greenhouse.io/acme/jobs/9999",
            owner_id="worker_1",
            now_epoch_seconds=1_760_000_000 + (10 * 86400),
        )

    # After 31 days (> 30-day rolling window), applying to a new role at 'acme_corp' is permitted
    res_after_window = ledger.reserve_job(
        job_id="job_4_after_31d",
        direct_employer_id="acme_corp",
        canonical_role_id="gh_9999",
        canonical_url="https://boards.greenhouse.io/acme/jobs/9999",
        owner_id="worker_1",
        now_epoch_seconds=1_760_000_000 + (31 * 86400),
    )
    assert res_after_window.canonical_role_id == "gh_9999"
