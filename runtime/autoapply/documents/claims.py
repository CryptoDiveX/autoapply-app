"""Factual claim verification against confirmed CandidateStore records (P13).

Enforces AA-DOC-003, AA-KB-002, C-11:
- Every tailored resume/cover-letter/screening claim must cite one or more confirmed fact IDs.
- Rejects claims referencing unconfirmed or nonexistent facts.
- Verifies claimed employer names and quantitative metrics against the referenced fact values.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Sequence

from autoapply.candidate.store import CandidateStore


class ClaimVerificationError(RuntimeError):
    """Raised when a generated document claim is unsupported by confirmed candidate facts."""


@dataclass(frozen=True)
class DraftClaim:
    """Structured claim emitted by the writer role with supporting fact references."""

    statement: str
    supporting_fact_ids: tuple[str, ...]
    claimed_employer: str | None = None
    claimed_metric: str | None = None


@dataclass(frozen=True)
class FactualDiffReport:
    """Evidence mapping report returned by claim verification."""

    all_supported: bool
    verified_claim_count: int
    referenced_fact_ids: tuple[str, ...]


def verify_claims_against_confirmed_facts(
    claims: Sequence[DraftClaim],
    *,
    candidate_store: CandidateStore,
) -> FactualDiffReport:
    referenced_ids: list[str] = []

    for claim in claims:
        if not claim.supporting_fact_ids:
            raise ClaimVerificationError("claim_missing_supporting_fact_ids")

        combined_fact_text = ""
        for fid in claim.supporting_fact_ids:
            row = candidate_store._conn.execute(
                "SELECT * FROM candidate_facts WHERE id = ? AND confirmed = 1 AND superseded_by_id IS NULL",
                (fid,),
            ).fetchone()
            if row is None:
                raise ClaimVerificationError(
                    f"claim_references_unconfirmed_or_missing_fact: {fid}"
                )
            referenced_ids.append(fid)
            combined_fact_text += " " + str(row["value_json"])

        if claim.claimed_employer and claim.claimed_employer not in combined_fact_text:
            raise ClaimVerificationError(
                f"unsupported_metric_or_employer_in_claim: employer '{claim.claimed_employer}' not in confirmed fact"
            )

        if claim.claimed_metric and claim.claimed_metric not in combined_fact_text:
            raise ClaimVerificationError(
                f"unsupported_metric_or_employer_in_claim: metric '{claim.claimed_metric}' not in confirmed fact"
            )

    return FactualDiffReport(
        all_supported=True,
        verified_claim_count=len(claims),
        referenced_fact_ids=tuple(sorted(set(referenced_ids))),
    )
