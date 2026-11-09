"""Synthetic local ATS fixture simulating controlled React inputs, dropdowns, radios, iframes, and idempotent/uncertain submissions (P18, P20).

Used for local integration testing (T-JOB-03..07, T-UX-01..02) without spamming real employers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import uuid


@dataclass
class SyntheticATSField:
    """Controlled field state inside the synthetic ATS form."""

    field_id: str
    label: str
    field_type: str  # "text", "radio", "dropdown", "iframe_text", "file"
    required: bool = True
    allowed_options: tuple[str, ...] = ()
    committed_value: str | None = None
    attached_sha256: str | None = None
    reject_uncommitted_click_only: bool = True


@dataclass
class SyntheticATSFormServer:
    """In-process synthetic ATS server verifying committed field states and single submissions."""

    employer_id: str = "acme_corp"
    canonical_role_id: str = "gh_4002"
    canonical_url: str = "https://boards.greenhouse.io/acme/jobs/4002"
    requires_mfa_challenge: bool = False
    simulate_network_timeout_after_accept: bool = False
    fields: dict[str, SyntheticATSField] = field(default_factory=dict)
    submissions_by_role: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def default_form(cls) -> SyntheticATSFormServer:
        return cls(
            fields={
                "el_full_name": SyntheticATSField(
                    field_id="el_full_name",
                    label="Full Name",
                    field_type="text",
                ),
                "el_work_auth_ca": SyntheticATSField(
                    field_id="el_work_auth_ca",
                    label="Are you legally authorized to work in Canada?",
                    field_type="radio",
                    allowed_options=("Yes", "No"),
                ),
                "el_sponsorship_ca": SyntheticATSField(
                    field_id="el_sponsorship_ca",
                    label="Will you now or in the future require visa sponsorship in Canada?",
                    field_type="dropdown",
                    allowed_options=("Yes", "No"),
                ),
                "el_iframe_eeo": SyntheticATSField(
                    field_id="el_iframe_eeo",
                    label="Voluntary Self-Identification (Iframe)",
                    field_type="iframe_text",
                    required=False,
                ),
                "el_resume_upload": SyntheticATSField(
                    field_id="el_resume_upload",
                    label="Resume/CV",
                    field_type="file",
                ),
            }
        )

    def click_without_committing(self, field_id: str) -> None:
        """Simulates a naive click on a React controlled input that does not commit state."""
        _ = self.fields[field_id]

    def commit_field_value(self, field_id: str, value: str) -> None:
        f = self.fields[field_id]
        if f.allowed_options and value not in f.allowed_options:
            raise ValueError(f"invalid_option_for_{field_id}: {value}")
        f.committed_value = value

    def attach_file(self, field_id: str, file_bytes: bytes) -> str:
        f = self.fields[field_id]
        if f.field_type != "file":
            raise ValueError(f"not_a_file_field: {field_id}")
        digest = hashlib.sha256(file_bytes).hexdigest()
        f.committed_value = f"uploaded:{digest[:12]}.pdf"
        f.attached_sha256 = digest
        return digest

    def read_committed_form_snapshot(self) -> dict[str, str | None]:
        return {fid: f.committed_value for fid, f in self.fields.items()}

    def submit_form(self, *, candidate_account_id: str) -> str:
        if self.requires_mfa_challenge:
            raise RuntimeError("ats_security_or_mfa_challenge_required")

        for fid, f in self.fields.items():
            if f.required and not f.committed_value:
                raise RuntimeError(f"server_validation_failed_missing_{fid}")

        receipt_id = f"ats_rcpt_{uuid.uuid4().hex[:10]}"
        self.submissions_by_role.append(
            {
                "receipt_id": receipt_id,
                "candidate_account_id": candidate_account_id,
                "employer_id": self.employer_id,
                "canonical_role_id": self.canonical_role_id,
                "resume_sha256": self.fields["el_resume_upload"].attached_sha256 or "",
            }
        )
        if self.simulate_network_timeout_after_accept:
            raise TimeoutError("network_timeout_after_server_accepted_submission")
        return receipt_id

    def query_confirmation_receipt(
        self,
        *,
        candidate_account_id: str,
        canonical_role_id: str,
        expected_resume_sha256: str,
    ) -> str | None:
        for sub in self.submissions_by_role:
            if (
                sub["candidate_account_id"] == candidate_account_id
                and sub["canonical_role_id"] == canonical_role_id
                and sub["resume_sha256"] == expected_resume_sha256
            ):
                return sub["receipt_id"]
        return None
