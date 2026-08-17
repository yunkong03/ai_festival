"""FastAPI endpoint 최소 검증."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from dart_detective.graph import DEFAULT_INDEX_PATH

pytestmark = pytest.mark.skipif(
    not Path(DEFAULT_INDEX_PATH).exists(),
    reason="search_index.jsonl 없음 — scripts/build_case_search_index.py 실행 필요",
)


@pytest.fixture(scope="module")
def client():
    os.environ["DART_DETECTIVE_LLM"] = "off"  # 테스트는 항상 결정론적 경로로
    from fastapi.testclient import TestClient

    from dart_detective.api import app

    with TestClient(app) as c:
        yield c


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["action_cost"]["research"] > 0


def test_case_briefing_hides_future_events(client):
    body = client.get("/cases/CASE-001").json()
    assert body["case_id"] == "CASE-001"
    assert "future_events" not in body
    assert body["documents"]


def test_session_flow(client):
    sid = client.post("/sessions", json={"case_id": "CASE-001"}).json()["session_id"]

    r = client.post(f"/sessions/{sid}/actions",
                    json={"action": "research", "question": "현금성자산은 얼마인가"})
    assert r.status_code == 200
    payload = r.json()["response"]
    assert payload["validation"]["status"] in {"SUPPORTED", "PARTIALLY_SUPPORTED"}
    assert all(d["document_date"] <= "2023-05-23" for d in payload["retrieved"])

    # 판단 전 replay는 400
    assert client.post(f"/sessions/{sid}/actions", json={"action": "replay"}).status_code == 400

    assert client.post(f"/sessions/{sid}/actions",
                       json={"action": "decision", "option_id": "O1"}).status_code == 200
    replay = client.post(f"/sessions/{sid}/actions", json={"action": "replay"}).json()
    assert replay["state"]["future_unlocked"] is True
    assert replay["response"]["future_events"]

    trace = client.get(f"/sessions/{sid}/trace").json()["trace"]
    assert any(t["node"] == "research" for t in trace)

    assert client.delete(f"/sessions/{sid}").json()["ended"] is True


def test_unopened_document_is_forbidden(client):
    sid = client.post("/sessions", json={"case_id": "CASE-001"}).json()["session_id"]
    assert client.get(f"/sessions/{sid}/documents/D01").status_code == 403
    client.post(f"/sessions/{sid}/actions",
                json={"action": "open_document", "document_id": "D01"})
    assert client.get(f"/sessions/{sid}/documents/D01").status_code == 200


def test_unknown_session_is_404(client):
    assert client.get("/sessions/nope/state").status_code == 404


# ---------------------------------------------------------------- 웹 데모용 endpoint

def test_web_demo_is_served(client):
    assert client.get("/app/").status_code == 200
    assert "공시 탐정사무소" in client.get("/app/index.html").text
    assert client.get("/", follow_redirects=False).status_code in (307, 302)


def test_evidence_endpoint_returns_only_collected(client):
    sid = client.post("/sessions", json={"case_id": "CASE-001"}).json()["session_id"]
    assert client.get(f"/sessions/{sid}/evidence").json()["evidence"] == []

    doc = client.post(f"/sessions/{sid}/actions",
                      json={"action": "open_document", "document_id": "D01"}).json()
    eid = doc["response"]["evidence_options"][0]["evidence_id"]
    client.post(f"/sessions/{sid}/actions",
                json={"action": "open_document", "document_id": "D01", "collect": [eid]})

    body = client.get(f"/sessions/{sid}/evidence").json()
    assert [e["evidence_id"] for e in body["evidence"]] == [eid]
    assert body["total"] > 1 and body["total_critical"] >= 1
    assert "educational_reason" in body["evidence"][0]


def test_evidence_options_carry_source_text_for_highlighting(client):
    """프론트가 원문에서 형광펜 위치를 찾으려면 source_text가 원문의 부분 문자열이어야 한다."""
    sid = client.post("/sessions", json={"case_id": "CASE-001"}).json()["session_id"]
    doc = client.post(f"/sessions/{sid}/actions",
                      json={"action": "open_document", "document_id": "D01"}).json()["response"]
    assert doc["evidence_options"]
    for opt in doc["evidence_options"]:
        assert opt["source_text"] in doc["original_text"]
        # 프론트가 "출처 D01 …"을 그리려면 document_id가 있어야 한다(없으면 undefined가 찍힌다)
        assert opt["document_id"] == "D01"


def test_points_can_be_disabled_for_demo(client):
    sid = client.post("/sessions",
                      json={"case_id": "CASE-001", "points_enabled": False}).json()["session_id"]
    before = client.get(f"/sessions/{sid}/state").json()["investigation_points"]
    client.post(f"/sessions/{sid}/actions",
                json={"action": "research", "question": "현금성자산은 얼마인가"})
    after = client.get(f"/sessions/{sid}/state").json()
    assert after["investigation_points"] == before
    assert after["points_enabled"] is False


def test_reset_starts_a_clean_session(client):
    sid = client.post("/sessions", json={"case_id": "CASE-001"}).json()["session_id"]
    client.post(f"/sessions/{sid}/actions",
                json={"action": "open_document", "document_id": "D01",
                      "collect": ["E01"]})
    assert client.get(f"/sessions/{sid}/state").json()["found_evidence"] == ["E01"]

    new_sid = client.post(f"/sessions/{sid}/reset").json()["session_id"]
    assert new_sid != sid
    fresh = client.get(f"/sessions/{new_sid}/state").json()
    assert fresh["found_evidence"] == [] and fresh["decision"] is None
    assert fresh["future_unlocked"] is False
