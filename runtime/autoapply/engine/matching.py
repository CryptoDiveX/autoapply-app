"""Job eligibility evaluation and preference matching (P16).

Enforces AA-JOB-001, AA-JOB-002:
- Checks role openness before any paid model/writing work.
- Separates residence country, work authorization by country, and visa sponsorship.
- Never equates a 'remote' workplace label with worldwide employment eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobPosting:
    """Normalized job posting snapshot."""

    job_id: str
    direct_employer_id: str
    canonical_role_id: str
    canonical_url: str
    title: str
    workplace_mode: str
    eligible_countries: tuple[str, ...]
    sponsorship_offered: bool
    is_open: bool
    salary_max_usd: int | None = None


@dataclass(frozen=True)
class CandidateJobPreferences:
    """Confirmed candidate location, work-authorization, and workplace rules."""

    residence_country: str
    authorized_countries: dict[str, bool]
    requires_sponsorship_by_country: dict[str, bool]
    accepted_workplace_modes: set[str]
    minimum_salary_usd: int | None = None
    excluded_employers: set[str] | None = None


@dataclass(frozen=True)
class EligibilityResult:
    """Structured eligibility verdict before paid document generation."""

    eligible: bool
    exclusion_reason: str | None = None


def evaluate_job_eligibility(
    job: JobPosting,
    prefs: CandidateJobPreferences,
) -> EligibilityResult:
    if not job.is_open:
        return EligibilityResult(eligible=False, exclusion_reason="role_closed")

    if prefs.excluded_employers and job.direct_employer_id in prefs.excluded_employers:
        return EligibilityResult(eligible=False, exclusion_reason="employer_excluded_by_user")

    if job.workplace_mode not in prefs.accepted_workplace_modes:
        return EligibilityResult(eligible=False, exclusion_reason="workplace_mode_mismatch")

    # Remote does NOT imply worldwide eligibility: candidate residence must be in eligible_countries
    if prefs.residence_country not in job.eligible_countries:
        return EligibilityResult(
            eligible=False,
            exclusion_reason="country_residence_or_location_ineligible",
        )

    country = prefs.residence_country
    is_authorized = prefs.authorized_countries.get(country, False)
    needs_sponsorship = prefs.requires_sponsorship_by_country.get(country, not is_authorized)

    if needs_sponsorship and not job.sponsorship_offered:
        return EligibilityResult(
            eligible=False,
            exclusion_reason="sponsorship_required_but_not_offered",
        )

    if not is_authorized and not needs_sponsorship:
        return EligibilityResult(
            eligible=False,
            exclusion_reason="work_authorization_missing",
        )

    if (
        prefs.minimum_salary_usd is not None
        and job.salary_max_usd is not None
        and job.salary_max_usd < prefs.minimum_salary_usd
    ):
        return EligibilityResult(
            eligible=False,
            exclusion_reason="below_minimum_salary",
        )

    return EligibilityResult(eligible=True, exclusion_reason=None)
