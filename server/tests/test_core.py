import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from claimscout import ai, matcher, pairing, proof
from claimscout.app import create_app
from claimscout.collectors import community, topclassactions
from claimscout.db import DB
from claimscout.text import parse_date, states_in

BOX = """<p>Acme agreed to pay $5 million.</p>
<h6 class="wp-block-heading">Who’s Eligible</h6><p><span>Illinois residents who bought an Acme Widget between Jan. 1, 2020, and Dec. 31, 2023.</span></p>
<h6>Potential Award</h6><p>Up to $50</p>
<h6>Proof of Purchase</h6><p>N/A</p>
<h6>Claim Form</h6><a class="btn" href="https://acmesettlement.example/claim" target="_blank">CLICK HERE TO FILE A CLAIM »</a>
<h6>Claim Form Deadline</h6><p>12/31/2099</p>
<h6>Case Name</h6><p>Doe v. Acme Corp., Case No. 1:23-cv-1</p>
<h6>Settlement Website</h6><p>AcmeSettlement.example</p>"""

FEED = f"""<?xml version="1.0"?><rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>$5M Acme Widget class action settlement</title><link>https://topclassactions.com/x/acme-widget/</link>
<pubDate>Fri, 09 Oct 2026 17:00:00 +0000</pubDate><content:encoded><![CDATA[{BOX}]]></content:encoded></item>
<item><title>Some news</title><link>https://topclassactions.com/x/news/</link><content:encoded><![CDATA[<p>No box</p>]]></content:encoded></item>
</channel></rss>"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(pairing, "CERT", tmp_path / "cert.pem")
    monkeypatch.setattr(pairing, "KEY", tmp_path / "key.pem")
    return DB(tmp_path / "t.db")


def test_parse_feed():
    [s] = topclassactions.parse_feed(FEED)
    assert s["id"] == "tca:acme-widget"
    assert s["title"] == "$5M Acme Widget"
    assert s["claim_url"] == "https://acmesettlement.example/claim"
    assert s["website"] == "https://AcmeSettlement.example"
    assert s["deadline"] == "2099-12-31"
    assert s["proof_needed"] == 0
    assert s["states"] == ["IL"]
    assert s["award"] == "Up to $50"


@pytest.mark.parametrize("text,iso", [("Nov. 25, 2026", "2026-11-25"), ("11/25/2026", "2026-11-25"),
                                      ("September 3rd, 2025", "2025-09-03"), ("2026-01-02", "2026-01-02"),
                                      ("TBD", None), ("Feb 30, 2026", None)])
def test_dates(text, iso):
    assert parse_date(text) == iso


def test_states():
    assert states_in("Illinois residents who used the app") == ["IL"]
    assert states_in("Washington insureds of State Farm") == ["WA"]
    assert states_in("People in West Virginia who bought it") == ["WV"]
    assert states_in("Anyone in the U.S. who bought from a California company") == []


def test_rule_match(db):
    [s] = topclassactions.parse_feed(FEED)
    db.upsert_settlement(s)
    s = db.settlement(s["id"])
    p = {**matcher.PROFILE_DEFAULT, "states": ["CA"], "companies": ["Acme"]}
    assert matcher.rule_match(p, s)["verdict"] == "unlikely"          # Illinois only
    p["past_states"] = ["IL"]
    m = matcher.rule_match(p, s)
    assert m["verdict"] == "likely" and m["proof_plan"]["keywords"] == ["Acme"]
    assert m["proof_plan"]["after"] == "2020-01-01" and m["proof_plan"]["before"] == "2023-12-31"
    # whole-word only: "Acme" must not match "Acmeville"
    assert matcher.rule_match({**p, "companies": ["Acm"]}, s)["verdict"] == "maybe"


def test_ai_match_and_bad_reply(db, monkeypatch):
    [s] = topclassactions.parse_feed(FEED)
    db.upsert_settlement(s)
    db.put("ai", {"provider": "local", "base_url": "http://x/v1", "model": "m"})
    async def fake(db_, system, user, max_tokens=900):
        return 'Sure!\n```json\n{"verdict":"likely","reason":"You bought a widget.","proof_plan":{"senders":["acme.com"],"keywords":["widget"]}}\n```'
    monkeypatch.setattr(ai, "chat", fake)
    counts = asyncio.run(matcher.run(db))
    assert counts["ai"] == 1
    m = db.q("SELECT * FROM matches")[0]
    assert m["verdict"] == "likely" and json.loads(m["proof_plan"])["senders"] == ["acme.com"]

    async def broken(*a, **k):
        return "I think so"
    monkeypatch.setattr(ai, "chat", broken)
    assert asyncio.run(matcher.run(db))["ai_errors"] == 1               # falls back to rules, keeps going


def test_parse_json_handles_think_and_nesting():
    assert ai.parse_json('<think>{"no"}</think> {"a": {"b": "}"}}') == {"a": {"b": "}"}}
    assert ai.parse_json("[{\"index\": 0}]") == [{"index": 0}]


def test_proof_heuristic(db):
    [s] = topclassactions.parse_feed(FEED)
    db.upsert_settlement(s)
    msgs = [{"account": "me@gmail.com", "id": "1", "from": "orders@acme.com", "subject": "Your Acme order",
             "date": "2021-05-01", "text": "Thanks! Order number: AB-123456. Total charged: $19.99"},
            {"account": "me@gmail.com", "id": "2", "from": "friend@x.com", "subject": "lunch?", "date": "", "text": "hi"}]
    out = asyncio.run(proof.extract(db, db.settlement(s["id"]), msgs))
    assert len(out) == 1 and out[0]["order_number"] == "AB-123456" and out[0]["amount"] == "$19.99"
    asyncio.run(proof.extract(db, db.settlement(s["id"]), msgs))         # same email twice: no duplicate
    assert db.q("SELECT COUNT(*) n FROM proofs")[0]["n"] == 1


def test_community_normalize():
    ok = community.normalize({"id": "X 1", "title": "X", "claim_url": "https://x.example", "deadline": "Jan 5, 2027",
                              "states": ["ca"]}, "Community")
    assert ok["id"] == "c:x-1" and ok["deadline"] == "2027-01-05" and ok["states"] == ["CA"]
    assert community.normalize({"id": "y", "title": "Y", "claim_url": "javascript:alert(1)"}, "C") is None


def test_api(db, monkeypatch):
    [s] = topclassactions.parse_feed(FEED)
    db.upsert_settlement(s)
    c = TestClient(create_app(db))
    assert c.get("/api/status").status_code == 401
    h = {"Authorization": "Bearer " + pairing.token(db)}
    assert c.get("/api/status", headers=h).json()["open"] == 1
    assert c.put("/api/profile", content="{}", headers={**h, "Content-Type": "text/plain"}).status_code == 415
    monkeypatch.setattr("claimscout.app.Hub.refresh_soon", lambda self, rematch=False: None)
    c.put("/api/profile", json={"states": ["il"], "companies": ["Acme", " "]}, headers=h)
    assert c.get("/api/profile", headers=h).json()["companies"] == ["Acme"]
    assert c.post(f"/api/settlements/{s['id']}/match", json={}, headers=h).json()["verdict"] == "likely"
    assert [x["id"] for x in c.get("/api/settlements", headers=h).json()["settlements"]] == [s["id"]]
    d = c.get(f"/api/settlements/{s['id']}", headers=h).json()
    assert d["proof_plan"]["keywords"] == ["Acme"]
    assert len(c.get("/api/new", headers=h).json()["new"]) == 1
    c.put(f"/api/claims/{s['id']}", json={"status": "filed", "claim_number": "C-1"}, headers=h)
    assert c.get("/api/new", headers=h).json()["new"] == []            # already claimed: no nagging
    assert c.get("/api/settlements?view=claimed", headers=h).json()["settlements"][0]["claim_status"] == "filed"
    # AI key is never echoed back
    c.put("/api/ai", json={"provider": "openrouter", "api_key": "sk-secret", "model": "x:free"}, headers=h)
    assert c.get("/api/ai", headers=h).json()["api_key"] == "set"
    c.put("/api/ai", json={"provider": "openrouter", "api_key": "set", "model": "y:free"}, headers=h)
    assert ai.settings(db)["api_key"] == "sk-secret"
    # pairing page is dashboard-only
    assert c.get("/api/pair", headers=h).status_code == 404
