"""Comprehensive end-to-end API test suite for LexiGuard FastAPI backend.

Tests every route:
- POST /api/session (launch code exchange)
- GET /api/health (token-guarded health check)
- POST /api/documents (document upload and ingestion)
- GET /api/documents (document listing)
- GET /api/documents/{id}/pages/{num} (source viewer)
- POST /api/documents/{id}/ask (CUAD and factual QA)
- DELETE /api/documents/{id} (forensic-aware document deletion)
"""
from __future__ import annotations

import io
from pathlib import Path
from fastapi.testclient import TestClient

from backend.app.main import create_app
import backend.app.main as main_mod
from backend.app.config import get_settings


def test_api_full_lifecycle(tmp_path: Path):
    """Test entire API flow from launch code exchange to deletion."""
    app = create_app()
    client = TestClient(app)

    # 1. Test Session Launch Code Exchange
    code = main_mod.token_store.issue_launch_code()
    session_res = client.post("/api/session", json={"code": code})
    assert session_res.status_code == 200, session_res.text
    session_data = session_res.json()
    assert "token" in session_data
    token = session_data["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify invalid code fails
    bad_session = client.post("/api/session", json={"code": "invalid_code"})
    assert bad_session.status_code == 401

    # 2. Test Health Endpoint
    health_unauth = client.get("/api/health")
    assert health_unauth.status_code == 401  # Token is required

    health_res = client.get("/api/health", headers=headers)
    assert health_res.status_code == 200
    assert health_res.json()["ok"] is True
    assert health_res.json()["fts5"] is True

    # 3. Test Document Upload (Ingest)
    fixture_path = Path("fixtures/synthetic_rental_simple.txt")
    assert fixture_path.exists(), "Test fixture must exist"
    fixture_bytes = fixture_path.read_bytes()

    files = {"file": ("synthetic_agreement.txt", io.BytesIO(fixture_bytes), "text/plain")}
    upload_res = client.post("/api/documents", headers=headers, files=files)
    assert upload_res.status_code == 201, upload_res.text
    upload_data = upload_res.json()
    assert "document_id" in upload_data
    doc_id = upload_data["document_id"]
    assert upload_data["page_count"] >= 1
    assert upload_data["status"] in ("ready", "partial")

    try:
        # 4. Test List Documents
        list_res = client.get("/api/documents", headers=headers)
        assert list_res.status_code == 200
        docs = list_res.json()
        assert any(d["document_id"] == doc_id for d in docs)

        # 5. Test Page Text Source Viewer
        page_res = client.get(f"/api/documents/{doc_id}/pages/1", headers=headers)
        assert page_res.status_code == 200
        assert "LEAVE AND LICENCE AGREEMENT" in page_res.text
        assert page_res.headers.get("cache-control") == "no-store"

        # 6. Test Ask Endpoint: CUAD Parties Question
        ask_payload = {
            "question": "Highlight the parts (if any) of this contract related to 'Parties' (the entities entering the agreement)."
        }
        ask_res = client.post(f"/api/documents/{doc_id}/ask", headers=headers, json=ask_payload)
        assert ask_res.status_code == 200, ask_res.text
        answer = ask_res.json()
        assert answer["status"] == "ANSWERED"
        assert answer["legal_verdict"] is None
        assert len(answer["claims"]) > 0

        # Verify parties are in the evidence
        all_quotes = " ".join(
            ev["quote"]
            for claim in answer["claims"]
            for ev in claim["evidence"]
        )
        assert "Ramesh Kumar Sharma" in all_quotes or "Licensor" in all_quotes
        assert "Priya Agarwal" in all_quotes or "Licensee" in all_quotes

        # 7. Test Ask Endpoint: CUAD Governing Law Question
        gov_payload = {
            "question": "Highlight the parts (if any) of this contract related to 'Governing Law' (jurisdiction governing interpretation)."
        }
        gov_res = client.post(f"/api/documents/{doc_id}/ask", headers=headers, json=gov_payload)
        assert gov_res.status_code == 200
        gov_answer = gov_res.json()
        assert gov_answer["status"] == "ANSWERED"
        gov_quotes = " ".join(
            ev["quote"]
            for claim in gov_answer["claims"]
            for ev in claim["evidence"]
        )
        assert "Maharashtra" in gov_quotes or "arbitration" in gov_quotes

        # 8. Test Ask Endpoint: Limitation / Verdict Scanner
        verdict_payload = {
            "question": "Is this penalty clause legally valid and enforceable in court?"
        }
        verdict_res = client.post(f"/api/documents/{doc_id}/ask", headers=headers, json=verdict_payload)
        assert verdict_res.status_code == 200
        verdict_answer = verdict_res.json()
        assert verdict_answer["status"] == "LEGAL_LIMIT"
        assert verdict_answer["legal_verdict"] is None
        # 8b. Test Review Endpoint: Core 10 Topics
        review_res = client.post(f"/api/documents/{doc_id}/review", headers=headers)
        assert review_res.status_code == 200, review_res.text
        review_data = review_res.json()
        assert "topics" in review_data
        assert len(review_data["topics"]) > 0
        assert "professional_questions" in review_data

    finally:
        # 9. Test Document Deletion
        del_res = client.delete(f"/api/documents/{doc_id}", headers=headers)
        assert del_res.status_code == 200, del_res.text
        del_data = del_res.json()
        assert del_data["app_files_removed"] is True
        assert del_data["directory_absent"] is True

        # Verify document is gone
        get_gone = client.get(f"/api/documents/{doc_id}/pages/1", headers=headers)
        assert get_gone.status_code == 404


def test_upload_pdf_lifecycle():
    """Verify that the upload endpoint correctly accepts and processes PDF documents."""
    import pypdfium2 as pdfium
    app = create_app()
    client = TestClient(app)

    code = main_mod.token_store.issue_launch_code()
    session_res = client.post("/api/session", json={"code": code})
    assert session_res.status_code == 200
    token = session_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create a small valid PDF in memory
    doc = pdfium.PdfDocument.new()
    doc.new_page(width=200, height=200)
    bio = io.BytesIO()
    doc.save(bio)
    pdf_bytes = bio.getvalue()

    files = {"file": ("test_doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    upload_res = client.post("/api/documents", headers=headers, files=files)
    assert upload_res.status_code == 201, upload_res.text
    data = upload_res.json()
    assert "document_id" in data
    assert data["page_count"] == 1
    doc_id = data["document_id"]

    # Clean up
    del_res = client.delete(f"/api/documents/{doc_id}", headers=headers)
    assert del_res.status_code == 200


def test_upload_raw_txt_file():
    """Verify that raw .txt files are accepted and parsed into virtual pages."""
    app = create_app()
    client = TestClient(app)

    code = main_mod.token_store.issue_launch_code()
    session_res = client.post("/api/session", json={"code": code})
    assert session_res.status_code == 200
    token = session_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    raw_text = (
        "CONFIDENTIALITY AND NON-DISCLOSURE AGREEMENT\n\n"
        "This Non-Disclosure Agreement is entered into on January 1, 2025.\n\n"
        "1. DEFINITION OF CONFIDENTIAL INFORMATION\n\n"
        "All proprietary technical and business information disclosed by either party.\n\n"
        "2. GOVERNING LAW\n\n"
        "This agreement shall be governed by the laws of India.\n"
    ).encode("utf-8")

    files = {"file": ("simple_nda.txt", io.BytesIO(raw_text), "text/plain")}
    upload_res = client.post("/api/documents", headers=headers, files=files)
    assert upload_res.status_code == 201, upload_res.text
    data = upload_res.json()
    assert "document_id" in data
    assert data["page_count"] >= 1
    assert data["status"] in ("ready", "partial")

    doc_id = data["document_id"]
    del_res = client.delete(f"/api/documents/{doc_id}", headers=headers)
    assert del_res.status_code == 200

