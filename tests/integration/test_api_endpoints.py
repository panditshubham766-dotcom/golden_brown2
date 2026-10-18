"""Comprehensive end-to-end API test suite for LexiGuard FastAPI backend.

Tests every route:
- POST /api/session (launch code exchange)
- GET /api/health (token-guarded health check)
- POST /api/documents (document upload and ingestion)
- GET /api/documents (document listing)
- GET /api/documents/{id}/pages/{num} (source viewer)
- POST /api/documents/{id}/ask (Single-Pass RAG QA)
- POST /api/documents/{id}/review (Core 10 risk assessment)
- POST /api/documents/{id}/summarize (structured document overview)
- DELETE /api/documents/{id} (forensic-aware document deletion)
"""
from __future__ import annotations

import io
from pathlib import Path
from fastapi.testclient import TestClient

from backend.app.main import create_app
import backend.app.main as main_mod


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

        # 6. Test Single-Pass RAG Ask: Parties question
        ask_payload = {
            "question": "Highlight the parts (if any) of this contract related to 'Parties' (the entities entering the agreement)."
        }
        ask_res = client.post(f"/api/documents/{doc_id}/ask", headers=headers, json=ask_payload)
        assert ask_res.status_code == 200, ask_res.text
        answer = ask_res.json()

        # Validate Single-Pass RAG response shape
        assert "status" in answer
        assert answer["status"] in ("ANSWERED", "NOT_LOCATED")
        assert "answer" in answer
        assert isinstance(answer["answer"], str)
        assert "citations" in answer
        assert isinstance(answer["citations"], list)
        assert answer["legal_verdict"] is None  # Non-verdict policy

        # If answered, citations must have page numbers
        if answer["status"] == "ANSWERED" and answer["citations"]:
            first_cit = answer["citations"][0]
            assert "page" in first_cit
            assert isinstance(first_cit["page"], int)
            assert first_cit["page"] >= 1
            assert "snippet" in first_cit

        # Verify parties content appears somewhere in the answer or citations
        full_text = answer["answer"] + " ".join(
            c.get("snippet", "") for c in answer.get("citations", [])
        )
        assert (
            "Ramesh" in full_text
            or "Priya" in full_text
            or "Licensor" in full_text
            or "Licensee" in full_text
        ), f"Expected party names in response; got: {full_text[:200]}"

        # 7. Test Ask: Governing Law question
        gov_payload = {
            "question": "Highlight the parts (if any) of this contract related to 'Governing Law'."
        }
        gov_res = client.post(f"/api/documents/{doc_id}/ask", headers=headers, json=gov_payload)
        assert gov_res.status_code == 200
        gov_answer = gov_res.json()
        assert gov_answer["status"] in ("ANSWERED", "NOT_LOCATED")
        if gov_answer["status"] == "ANSWERED":
            assert "Page" in gov_answer["answer"] or any(
                c["page"] >= 1 for c in gov_answer.get("citations", [])
            ), "Governing law answer should cite a page"

        # 8. Test Ask: NOT_LOCATED case (nonsense query)
        nonsense_res = client.post(
            f"/api/documents/{doc_id}/ask",
            headers=headers,
            json={"question": "xyzzy frobnicator oblique quorum"},
        )
        assert nonsense_res.status_code == 200
        nonsense_answer = nonsense_res.json()
        # Should return NOT_LOCATED or ANSWERED with empty citations
        assert nonsense_answer["status"] in ("ANSWERED", "NOT_LOCATED")

        # 8b. Test Review Endpoint: Core 10 Topics
        review_res = client.post(f"/api/documents/{doc_id}/review", headers=headers)
        assert review_res.status_code == 200, review_res.text
        review_data = review_res.json()
        assert "topics" in review_data
        assert len(review_data["topics"]) > 0
        assert "professional_questions" in review_data

        # Each topic must have required fields
        for topic in review_data["topics"]:
            assert "topic_id" in topic
            assert "label" in topic
            assert "status" in topic
            assert topic["status"] in ("FOUND", "NOT_FOUND", "AMBIGUOUS", "NOT_ASSESSED")
            assert "evidence" in topic

        # 8c. Test Summarize Endpoint: extractive fallback (Ollama not running in CI)
        summarize_res = client.post(f"/api/documents/{doc_id}/summarize", headers=headers)
        assert summarize_res.status_code == 200, summarize_res.text
        summary_data = summarize_res.json()

        # Validate SummaryResponse shape
        assert "document_id" in summary_data
        assert summary_data["document_id"] == doc_id
        assert "summary_markdown" in summary_data
        assert isinstance(summary_data["summary_markdown"], str)
        assert len(summary_data["summary_markdown"]) > 0
        assert "key_points" in summary_data
        assert isinstance(summary_data["key_points"], list)
        assert "referenced_pages" in summary_data
        assert isinstance(summary_data["referenced_pages"], list)
        assert "model_used" in summary_data
        assert "fallback" in summary_data
        # In CI without Ollama, should use extractive fallback
        if summary_data["fallback"]:
            assert summary_data["model_used"] == "extractive-bm25"

        # key_points must have label and value fields
        for kp in summary_data["key_points"]:
            assert "label" in kp
            assert "value" in kp
            assert "page_refs" in kp
            assert isinstance(kp["page_refs"], list)

        # 9. Verify 404 for non-existent document on all routes
        missing_ask = client.post(
            "/api/documents/does-not-exist-123/ask",
            headers=headers,
            json={"question": "test"},
        )
        assert missing_ask.status_code == 404

        missing_summarize = client.post(
            "/api/documents/does-not-exist-123/summarize",
            headers=headers,
        )
        assert missing_summarize.status_code == 404

    finally:
        # 10. Test Document Deletion
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

    # Quick ask smoke test on txt file
    ask_res = client.post(
        f"/api/documents/{doc_id}/ask",
        headers=headers,
        json={"question": "What is the governing law?"},
    )
    assert ask_res.status_code == 200
    ask_data = ask_res.json()
    assert ask_data["status"] in ("ANSWERED", "NOT_LOCATED")
    if ask_data["status"] == "ANSWERED":
        assert "India" in ask_data["answer"] or any(
            "India" in c.get("snippet", "") for c in ask_data.get("citations", [])
        )

    # Quick summarize smoke test on txt file
    summarize_res = client.post(f"/api/documents/{doc_id}/summarize", headers=headers)
    assert summarize_res.status_code == 200
    sum_data = summarize_res.json()
    assert sum_data["document_id"] == doc_id
    assert isinstance(sum_data["summary_markdown"], str)

    del_res = client.delete(f"/api/documents/{doc_id}", headers=headers)
    assert del_res.status_code == 200
