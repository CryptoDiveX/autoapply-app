"""Browser form field commitment and readback verification (P18).

Enforces AA-JOB-004, 06-VB-JOBS-PARITY-AND-LESSONS.md (Lesson 17):
- Controlled inputs, dropdowns, radios, iframes, and file inputs are verified by reading back
  their actual committed DOM state after edit, never by click return alone.
"""

from __future__ import annotations

from typing import Protocol


class ATSFormDriverProtocol(Protocol):
    """Protocol for interacting with an ATS DOM form."""

    def commit_field_value(self, field_id: str, value: str) -> None: ...

    def read_committed_form_snapshot(self) -> dict[str, str | None]: ...


class FieldVerificationError(RuntimeError):
    """Raised when a form field's readback value does not match the intended committed value."""


class BrowserFieldCommitter:
    """Commits form field values and verifies actual post-edit DOM state."""

    def __init__(self, driver: ATSFormDriverProtocol) -> None:
        self._driver = driver

    def verify_field_committed(self, field_id: str, *, expected_value: str) -> None:
        snapshot = self._driver.read_committed_form_snapshot()
        actual = snapshot.get(field_id)
        if actual != expected_value:
            raise FieldVerificationError(
                f"field_value_not_committed: field '{field_id}' expected {expected_value!r}, "
                f"read back {actual!r}"
            )

    def fill_and_verify(self, field_id: str, value: str) -> None:
        self._driver.commit_field_value(field_id, value)
        self.verify_field_committed(field_id, expected_value=value)
