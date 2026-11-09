"""Transactional SQLite CandidateStore with provenance, scoping, conflict resolution, and undo (P10).

Enforces AA-KB-001..005, C-11:
- Stores confirmed vs unconfirmed facts with source provenance, confidence, scope, and version.
- Never returns unconfirmed extracted facts for autofill or document claims.
- Detects contradictions within matching scope, supports explicit supersession and reversible undo.
- Enforces country/employer/form scoping so US authorization never leaks to UK/CA or other employers.
- Rejects passwords, OTPs, MFA codes, security answers, and prompt-injection strings from answer memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid


FORBIDDEN_LEARNING_PATTERNS: tuple[str, ...] = (
    "password",
    "passcode",
    "one-time",
    "otp",
    "verification code",
    "mfa",
    "2fa",
    "security question",
    "maiden name",
    "ignore previous instructions",
    "system prompt",
    "export all keys",
)


class CandidateStoreError(RuntimeError):
    """Raised on candidate fact conflict, forbidden learning input, or invalid supersession."""


class ScopeLevel(str, Enum):
    """Explicit reuse scope for facts and learned form answers (AA-KB-005, C-11)."""

    THIS_FORM = "this_form"
    EMPLOYER = "employer"
    COUNTRY = "country"
    GLOBAL = "global"


@dataclass(frozen=True)
class FactScope:
    """Scope descriptor for a candidate fact or answer record."""

    level: ScopeLevel
    country: str | None = None
    employer_id: str | None = None
    form_id: str | None = None


@dataclass(frozen=True)
class CandidateFactInput:
    """Input payload for creating a candidate fact."""

    key: str
    category: str
    value: Any
    source_type: str
    source_ref: str
    confidence: float
    confirmed: bool
    scope: FactScope
    effective_from: str


@dataclass(frozen=True)
class CandidateFactRecord:
    """Stored candidate fact row."""

    id: str
    key: str
    category: str
    value: Any
    source_type: str
    source_ref: str
    confidence: float
    confirmed: bool
    scope: FactScope
    effective_from: str
    supersedes_id: str | None
    superseded_by_id: str | None
    version: int


@dataclass(frozen=True)
class QuestionAnswerProposal:
    """Human form correction proposed as reusable scoped answer memory (AA-KB-005, C-11)."""

    question_text: str
    answer_value: str
    locale: str
    country: str | None
    employer_id: str | None
    form_id: str | None
    proposed_scope: FactScope
    sensitive: bool = False


def _normalize_question(text: str) -> str:
    return " ".join(text.strip().lower().split())


class CandidateStore:
    """SQLite-backed canonical candidate fact and question memory store."""

    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path.resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS candidate_facts (
                    id TEXT PRIMARY KEY,
                    key TEXT NOT NULL,
                    category TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    confirmed INTEGER NOT NULL,
                    scope_level TEXT NOT NULL,
                    scope_country TEXT,
                    scope_employer_id TEXT,
                    scope_form_id TEXT,
                    effective_from TEXT NOT NULL,
                    supersedes_id TEXT,
                    superseded_by_id TEXT,
                    version INTEGER NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS question_memory (
                    id TEXT PRIMARY KEY,
                    normalized_question TEXT NOT NULL,
                    raw_question TEXT NOT NULL,
                    answer_value TEXT NOT NULL,
                    locale TEXT NOT NULL,
                    scope_level TEXT NOT NULL,
                    scope_country TEXT,
                    scope_employer_id TEXT,
                    scope_form_id TEXT,
                    sensitive INTEGER NOT NULL,
                    confirmed INTEGER NOT NULL
                )
                """
            )

    def _row_to_fact(self, row: sqlite3.Row) -> CandidateFactRecord:
        return CandidateFactRecord(
            id=row["id"],
            key=row["key"],
            category=row["category"],
            value=json.loads(row["value_json"]),
            source_type=row["source_type"],
            source_ref=row["source_ref"],
            confidence=float(row["confidence"]),
            confirmed=bool(row["confirmed"]),
            scope=FactScope(
                level=ScopeLevel(row["scope_level"]),
                country=row["scope_country"],
                employer_id=row["scope_employer_id"],
                form_id=row["scope_form_id"],
            ),
            effective_from=row["effective_from"],
            supersedes_id=row["supersedes_id"],
            superseded_by_id=row["superseded_by_id"],
            version=int(row["version"]),
        )

    def add_fact(self, fact_in: CandidateFactInput, *, version: int = 1, supersedes_id: str | None = None) -> str:
        fact_id = f"fact_{uuid.uuid4().hex[:12]}"
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO candidate_facts (
                    id, key, category, value_json, source_type, source_ref,
                    confidence, confirmed, scope_level, scope_country,
                    scope_employer_id, scope_form_id, effective_from,
                    supersedes_id, superseded_by_id, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    fact_id,
                    fact_in.key,
                    fact_in.category,
                    json.dumps(fact_in.value, sort_keys=True),
                    fact_in.source_type,
                    fact_in.source_ref,
                    fact_in.confidence,
                    1 if fact_in.confirmed else 0,
                    fact_in.scope.level.value,
                    fact_in.scope.country,
                    fact_in.scope.employer_id,
                    fact_in.scope.form_id,
                    fact_in.effective_from,
                    supersedes_id,
                    version,
                ),
            )
        return fact_id

    def confirm_fact(self, fact_id: str) -> CandidateFactRecord:
        with self._conn:
            self._conn.execute(
                """
                UPDATE candidate_facts
                SET confirmed = 1,
                    source_type = CASE
                        WHEN source_type = 'resume_extracted_unconfirmed' THEN 'user_confirmed_resume'
                        ELSE source_type
                    END
                WHERE id = ?
                """,
                (fact_id,),
            )
        row = self._conn.execute("SELECT * FROM candidate_facts WHERE id = ?", (fact_id,)).fetchone()
        if row is None:
            raise CandidateStoreError(f"fact_not_found: {fact_id}")
        return self._row_to_fact(row)

    def get_active_confirmed_fact(
        self,
        key: str,
        *,
        country: str | None = None,
        employer_id: str | None = None,
        form_id: str | None = None,
    ) -> CandidateFactRecord | None:
        rows = self._conn.execute(
            """
            SELECT * FROM candidate_facts
            WHERE key = ? AND confirmed = 1 AND superseded_by_id IS NULL
            ORDER BY version DESC
            """,
            (key,),
        ).fetchall()
        for row in rows:
            fact = self._row_to_fact(row)
            if self._scope_matches(fact.scope, country=country, employer_id=employer_id, form_id=form_id):
                return fact
        return None

    def detect_conflicts(
        self,
        *,
        key: str,
        proposed_value: Any,
        scope: FactScope,
    ) -> list[CandidateFactRecord]:
        rows = self._conn.execute(
            """
            SELECT * FROM candidate_facts
            WHERE key = ? AND confirmed = 1 AND superseded_by_id IS NULL
            """,
            (key,),
        ).fetchall()
        conflicts: list[CandidateFactRecord] = []
        proposed_json = json.dumps(proposed_value, sort_keys=True)
        for row in rows:
            fact = self._row_to_fact(row)
            if (
                fact.scope == scope
                and json.dumps(fact.value, sort_keys=True) != proposed_json
            ):
                conflicts.append(fact)
        return conflicts

    def supersede_fact(self, *, prior_fact_id: str, new_input: CandidateFactInput) -> str:
        prior_row = self._conn.execute(
            "SELECT * FROM candidate_facts WHERE id = ?", (prior_fact_id,)
        ).fetchone()
        if prior_row is None:
            raise CandidateStoreError(f"prior_fact_not_found: {prior_fact_id}")
        prior = self._row_to_fact(prior_row)
        new_id = self.add_fact(
            new_input,
            version=prior.version + 1,
            supersedes_id=prior.id,
        )
        with self._conn:
            self._conn.execute(
                "UPDATE candidate_facts SET superseded_by_id = ? WHERE id = ?",
                (new_id, prior.id),
            )
        return new_id

    def undo_supersession(self, superseding_fact_id: str) -> CandidateFactRecord:
        row = self._conn.execute(
            "SELECT * FROM candidate_facts WHERE id = ?", (superseding_fact_id,)
        ).fetchone()
        if row is None or not row["supersedes_id"]:
            raise CandidateStoreError(f"cannot_undo_fact: {superseding_fact_id}")
        prior_id = row["supersedes_id"]
        with self._conn:
            self._conn.execute("DELETE FROM candidate_facts WHERE id = ?", (superseding_fact_id,))
            self._conn.execute(
                "UPDATE candidate_facts SET superseded_by_id = NULL WHERE id = ?",
                (prior_id,),
            )
        prior_row = self._conn.execute(
            "SELECT * FROM candidate_facts WHERE id = ?", (prior_id,)
        ).fetchone()
        return self._row_to_fact(prior_row)

    def propose_learned_answer(self, proposal: QuestionAnswerProposal) -> str:
        combined = f"{proposal.question_text} {proposal.answer_value}".lower()
        for pattern in FORBIDDEN_LEARNING_PATTERNS:
            if pattern in combined:
                raise CandidateStoreError(
                    f"forbidden_candidate_learning_input: matched '{pattern}'"
                )

        q_id = f"qmem_{uuid.uuid4().hex[:12]}"
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO question_memory (
                    id, normalized_question, raw_question, answer_value, locale,
                    scope_level, scope_country, scope_employer_id, scope_form_id,
                    sensitive, confirmed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    q_id,
                    _normalize_question(proposal.question_text),
                    proposal.question_text,
                    proposal.answer_value,
                    proposal.locale,
                    proposal.proposed_scope.level.value,
                    proposal.proposed_scope.country,
                    proposal.proposed_scope.employer_id,
                    proposal.proposed_scope.form_id,
                    1 if proposal.sensitive else 0,
                ),
            )
        return q_id

    def confirm_learned_answer(self, proposal_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE question_memory SET confirmed = 1 WHERE id = ?",
                (proposal_id,),
            )

    def lookup_reusable_answer(
        self,
        question_text: str,
        *,
        country: str | None = None,
        employer_id: str | None = None,
        form_id: str | None = None,
    ) -> str | None:
        norm = _normalize_question(question_text)
        rows = self._conn.execute(
            "SELECT * FROM question_memory WHERE normalized_question = ? AND confirmed = 1",
            (norm,),
        ).fetchall()
        for row in rows:
            scope = FactScope(
                level=ScopeLevel(row["scope_level"]),
                country=row["scope_country"],
                employer_id=row["scope_employer_id"],
                form_id=row["scope_form_id"],
            )
            if self._scope_matches(scope, country=country, employer_id=employer_id, form_id=form_id):
                return str(row["answer_value"])
        return None

    @staticmethod
    def _scope_matches(
        scope: FactScope,
        *,
        country: str | None,
        employer_id: str | None,
        form_id: str | None,
    ) -> bool:
        if scope.level == ScopeLevel.GLOBAL:
            return True
        if scope.level == ScopeLevel.COUNTRY:
            return scope.country is not None and scope.country == country
        if scope.level == ScopeLevel.EMPLOYER:
            return scope.employer_id is not None and scope.employer_id == employer_id
        if scope.level == ScopeLevel.THIS_FORM:
            return scope.form_id is not None and scope.form_id == form_id
        return False
