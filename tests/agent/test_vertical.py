"""Vertical slice tests: T-CITE-ROLE-01, T-LEGAL-FP-01, provenance, and bounded runtime."""
from __future__ import annotations

import sqlite3
from pathlib import Path
import pytest

from backend.app.agent.router import Route, route_query
from backend.app.agent.runtime import BoundedRuntime
from backend.app.agent.schema import ModelAnswer, ModelPoint
from backend.app.store.db import open_doc_db
from backend.app.validation.legal_policy import scan_verdict
from backend.app.validation.literal import validate_restatement
from backend.app.validation.provenance import validate_provenance


@pytest.fixture
def runtime_db(tmp_path: Path) -> sqlite3.Connection:
    """Create test SQLite database with sentences."""
    db_file = tmp_path / "runtime_doc.sqlite3"
    con = open_doc_db(db_file)

    con.execute(
        """
        INSERT INTO document (document_id, sha256, file_type, page_count, has_unread_pages, status)
        VALUES ('doc_slice', 'sha_abc', 'pdf', 2, 0, 'ready')
        """
    )
    for p in range(1, 3):
        con.execute(
            """
            INSERT INTO pages (page_num, norm_text, text_hash, is_readable, lang_supported)
            VALUES (?, ?, ?, 1, 1)
            """,
            (p, f"Page {p} content", f"hash_{p}"),
        )

    # Insert sample sentences
    con.execute(
        """
        INSERT INTO sentences (sid, page_num, section, start_offset, end_offset, sentence_text)
        VALUES ('s_rent_1', 1, '1. Rent', 0, 75, 'The tenant shall pay a monthly rent of Rs. 25,000 to the landlord.')
        """
    )
    con.execute(
        """
        INSERT INTO sentences (sid, page_num, section, start_offset, end_offset, sentence_text)
        VALUES ('s_notice_1', 2, '2. Termination', 0, 80, 'The tenant must provide thirty days written notice before vacating.')
        """
    )
    con.commit()
    yield con
    con.close()


# ── T-CITE-ROLE-01: Role swap validation ────────────────────────────────────────

def test_cite_role_01_valid_role():
    """T-CITE-ROLE-01: Valid restatement preserving roles is accepted."""
    source_sentence = "The tenant shall pay monthly rent of Rs. 25,000 to the landlord."
    point = ModelPoint(
        point_id="p1",
        kind="RESTATEMENT",
        text="The tenant must pay 25,000 monthly rent.",
        sids=["s1"],
    )
    ok, reason = validate_restatement(point, [source_sentence])
    assert ok is True
    assert "Valid" in reason


def test_cite_role_01_role_swap_rejected():
    """T-CITE-ROLE-01: Role swap (tenant obligation attributed to landlord) is rejected."""
    source_sentence = "The tenant shall pay monthly rent of Rs. 25,000 to the landlord."
    # Swap: saying landlord must pay rent
    swapped_point = ModelPoint(
        point_id="p1",
        kind="RESTATEMENT",
        text="The landlord must pay 25,000 monthly rent.",
        sids=["s1"],
    )
    ok, reason = validate_restatement(swapped_point, [source_sentence])
    assert ok is False
    assert "T-CITE-ROLE-01" in reason or "Role swap" in reason


def test_cite_role_01_invented_role_rejected():
    """T-CITE-ROLE-01: Introducing a party not present in cited text is rejected."""
    source_sentence = "The tenant shall pay monthly rent of Rs. 25,000."
    point = ModelPoint(
        point_id="p1",
        kind="RESTATEMENT",
        text="The landlord must pay 25,000.",
        sids=["s1"],
    )
    ok, reason = validate_restatement(point, [source_sentence])
    assert ok is False


# ── Provenance & Forged SID Tests ───────────────────────────────────────────────

def test_forged_sid_rejected():
    """Assert any sid not in approved_sids is stripped; point dropped if no citations remain."""
    approved_sids = {"s_valid_1", "s_valid_2"}
    answer = ModelAnswer(
        points=[
            ModelPoint(point_id="p1", kind="STATED", text="Real fact", sids=["s_valid_1"]),
            ModelPoint(point_id="p2", kind="STATED", text="Forged fact", sids=["s_fake_999"]),
        ]
    )

    valid_points, dropped = validate_provenance(answer, approved_sids)
    assert len(valid_points) == 1
    assert valid_points[0].point_id == "p1"
    assert any("forged/unapproved" in d for d in dropped)


# ── T-LEGAL-FP-01: Verdict Scanner Corpus (>=40 must-block, >=40 must-pass) ────

MUST_BLOCK_STRINGS = [
    "This clause is legally invalid.",
    "This agreement is completely void.",
    "This term is unenforceable under contract law.",
    "This clause is illegal.",
    "This provision violates the tenancy act.",
    "The landlord cannot legally evict you without court order.",
    "The notice period is against the law.",
    "This clause is unfair and unconscionable.",
    "This contract is legally binding in court.",
    "The condition is voidable at your option.",
    "You can sue the landlord for damages.",
    "You will win in court easily.",
    "You cannot sue under this agreement.",
    "The court will strike down this penalty.",
    "The judge will decide in your favour.",
    "You should not sign this contract.",
    "Do not sign this document.",
    "It is safe to sign this lease.",
    "You do not need a lawyer for this.",
    "There is no need for a lawyer.",
    "This is standard market practice.",
    "This fee is normal industry standard.",
    "This penalty clause is unreasonable.",
    "This forfeiture is excessive.",
    "This lock-in clause is draconian.",
    "The police will evict the tenant.",
    "You can file an FIR against the landlord.",
    "This agreement is unlawful.",
    "The landlord has no legal right to enter.",
    "This clause holds up in court.",
    "You will lose in court.",
    "This agreement is not legally valid.",
    "This section is legally void.",
    "The court will order the deposit refunded.",
    "You should sue for recovery of deposit.",
    "This lock-in is unenforceable.",
    "The owner cannot legally withhold the keys.",
    "This term violates local rent laws.",
    "This agreement is unfair to the tenant.",
    "You can take the landlord to court.",
    "This rule is not legally allowed.",
    "This document is invalid in law.",
]

MUST_PASS_STRINGS = [
    "This agreement is valid for 11 months from commencement.",
    "The tenant must provide a valid ID proof.",
    "The lease is valid for 2 years.",
    "A valid passport copy must be submitted.",
    "The legal heirs of the licensor shall inherit rights.",
    "The legal representatives of the parties are bound.",
    "The premises shall be used for lawful purposes only.",
    "The tenant shall carry out only lawful activities.",
    "The security deposit is fifty thousand rupees.",
    "Rent is payable on or before the fifth day of each month.",
    "The lock-in period is six months.",
    "Notice period shall be thirty days in writing.",
    "The tenant shall maintain the premises in good condition.",
    "The landlord is responsible for structural repairs.",
    "Subletting the premises is strictly prohibited.",
    "A sum of money paid by the tenant to cover potential damages.",
    "A specified minimum timeframe during which neither party may terminate.",
    "The amount of advance written notice that either party must provide.",
    "A contractual clause excusing performance due to extraordinary events.",
    "A periodic increase in the rent amount over time.",
    "An arrangement where the tenant leases property to a third party.",
    "An obligation where one party compensates the other for specified loss.",
    "Permission to occupy property without creating a tenancy right.",
    "This clause places maintenance obligations on the tenant; consider asking about structural repairs.",
    "The agreement provides for a 10% rent escalation after 12 months.",
    "Both parties agree to submit to the jurisdiction of courts in Mumbai.",
    "Payment shall be made by electronic bank transfer.",
    "The tenant shall pay electricity and water utility bills directly.",
    "The licensor agrees to hand over possession on the commencement date.",
    "A refundable interest-free security deposit of Rs. 100,000.",
    "Either party may terminate the agreement after the lock-in period.",
    "The agreement commences on the first of April.",
    "The licensee shall not keep pets on the premises without consent.",
    "Painting charges will be deducted from the security deposit upon vacating.",
    "The tenant shall permit inspection upon 24 hours prior notice.",
    "Key handover shall occur upon full refund of deposit.",
    "Late payment charges of 18% per annum will apply to arrears.",
    "All notices shall be delivered by registered post or email.",
    "The tenant is valid for occupancy starting from June.",
    "The legal counsel contact information is noted in schedule A.",
    "The licensee has legal right to occupy the licensed premises.",
    "The property is leased for residential purposes only.",
]


def test_t_legal_fp_01_corpus():
    """
    T-LEGAL-FP-01:
    - >= 40 must-block strings
    - >= 40 must-pass strings
    - Target: 0 missed must-block cases (100% block recall).
    - Target: <= 5% false-block rate on must-pass cases.
    """
    assert len(MUST_BLOCK_STRINGS) >= 40
    assert len(MUST_PASS_STRINGS) >= 40

    missed_blocks = []
    for s in MUST_BLOCK_STRINGS:
        ok, reason = scan_verdict(s, kind="ASSISTANT")
        if ok:
            missed_blocks.append(s)

    false_blocks = []
    for s in MUST_PASS_STRINGS:
        ok, reason = scan_verdict(s, kind="ASSISTANT")
        if not ok:
            false_blocks.append((s, reason))

    assert len(missed_blocks) == 0, f"Missed {len(missed_blocks)} must-block strings: {missed_blocks}"
    false_block_rate = len(false_blocks) / len(MUST_PASS_STRINGS)
    assert false_block_rate <= 0.05, f"False block rate {false_block_rate:.2%} exceeded 5%: {false_blocks}"


def test_source_echo_exception():
    """In STATED or RESTATEMENT, verbatim echo of a source clause containing legal words passes."""
    source_sentence = "This clause is void if rent remains unpaid for 3 months."
    echo_text = "This clause is void if rent remains unpaid for 3 months."

    # When marked as STATED and citing the source, the source-echo exception allows it
    ok, reason = scan_verdict(echo_text, kind="STATED", cited_sources=[source_sentence])
    assert ok is True

    # But without cited source backing, it is blocked
    ok_no_source, reason = scan_verdict(echo_text, kind="INTERPRETATION", cited_sources=[])
    assert ok_no_source is False


# ── Router & Runtime Integration Tests ──────────────────────────────────────────

def test_router_limitation():
    """Verify verdict questions are routed to LEGAL_CONCLUSION."""
    q = "Is this agreement legally valid and enforceable in court?"
    decision = route_query(q)
    assert decision.is_limitation is True
    assert decision.route == Route.LEGAL_CONCLUSION


def test_runtime_fast_path(runtime_db: sqlite3.Connection):
    """Verify BoundedRuntime produces verified RenderedAnswer with null legal_verdict."""
    runtime = BoundedRuntime(con=runtime_db, provider=None)
    result = runtime.run("What is the monthly rent?")

    assert result.status == "ANSWERED"
    assert result.legal_verdict is None
    assert len(result.claims) > 0
    assert result.claims[0].evidence[0].quote == "The tenant shall pay a monthly rent of Rs. 25,000 to the landlord."
    assert result.claims[0].evidence[0].page == 1
    assert result.claims[0].evidence[0].section == "1. Rent"
