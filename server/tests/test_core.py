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


def test_labels_and_categories():
    from claimscout.questions import rule_category, rule_label
    assert rule_label("$600K Crossroads Trading data breach") == "Crossroads Trading"
    assert rule_label("Toyota air bag control units $78.5M") == "Toyota"
    assert rule_label("$117M pork price-fixing") == "Pork"
    assert rule_category({"title": "$600K Crossroads Trading data breach"}) == "Data breaches & privacy"
    assert rule_category({"title": "$23.9M Costa Del Mar sunglasses repair"}) == "Home & products"
    assert rule_category({"title": "$4.5M Hearthside Food Solutions child labor"}) == "Work"
    assert rule_category({"title": "Mystery thing", "summary": "Owners of a Kia vehicle"}) == "Cars"


def test_questionnaire_flow(db, monkeypatch):
    from claimscout import questions
    [s] = topclassactions.parse_feed(FEED)
    db.upsert_settlement(s)
    c = TestClient(create_app(db))
    h = {"Authorization": "Bearer " + pairing.token(db)}
    monkeypatch.setattr("claimscout.app.Hub.refresh_soon", lambda self, rematch=False: None)
    q = c.get("/api/questionnaire", headers=h).json()
    assert q["count"] == 1 and q["groups"][0]["items"][0]["label"] == "Acme Widget"
    assert c.get("/api/status", headers=h).json()["unanswered"] == 1
    # someone who only ever lived in Texas never sees the Illinois-only one
    c.put("/api/profile", json={"states": ["TX"]}, headers=h)
    assert c.get("/api/questionnaire", headers=h).json()["count"] == 0
    c.put("/api/profile", json={"states": ["IL"]}, headers=h)
    r = c.post("/api/answers", json={"answers": {s["id"]: "yes", "bogus": "yes"}, "used": ["Acme Widget"]}, headers=h).json()
    assert r["saved"] == 1 and r["status"]["likely"] == 1 and r["status"]["unanswered"] == 0
    d = c.get(f"/api/settlements/{s['id']}", headers=h).json()
    assert d["match"]["method"] == "answer" and d["proof_plan"]["keywords"]   # a yes still gets an email plan
    assert "Acme Widget" in c.get("/api/profile", headers=h).json()["companies"]
    c.post("/api/answers", json={"answers": {s["id"]: "unused"}}, headers=h)
    assert c.get("/api/settlements", headers=h).json()["settlements"] == []
    c.request("DELETE", "/api/answers", json={}, headers=h)
    assert c.get("/api/questionnaire", headers=h).json()["count"] == 1


def test_enrich_with_ai(db, monkeypatch):
    from claimscout import questions
    [s] = topclassactions.parse_feed(FEED)
    db.upsert_settlement(s)
    db.put("ai", {"provider": "local", "base_url": "http://x/v1"})
    async def fake(db_, system, user, max_tokens=900):
        return json.dumps([{"id": s["id"], "label": "Acme Widgets", "category": "Home & products",
                            "question": "Did you buy an Acme Widget in Illinois between 2020 and 2023?"}])
    monkeypatch.setattr(ai, "chat", fake)
    assert asyncio.run(questions.enrich(db)) == 1
    item = questions.build(db, matcher.PROFILE_DEFAULT)["groups"][0]
    assert item["category"] == "Home & products" and item["items"][0]["question"].startswith("Did you buy")


def test_amounts_and_defendants():
    from claimscout.logos import _us_first, defendant
    from claimscout.text import max_amount
    assert max_amount("Up to $5,000 for documented losses and $100 pro rata") == 5000
    assert max_amount("Estimated $25 to $95") == 95
    assert max_amount("$20.5M fund; up to $10 each") == 10
    assert max_amount("TBD") is None
    assert defendant("CVS Pharmacy Inc. agreed to pay $20.5 million") == "CVS Pharmacy"
    assert defendant("Visa and Mastercard agreed to a settlement") == "Visa"
    assert defendant("Navy Federal Credit Union (NFCU) has agreed to") == "Navy Federal Credit Union"
    assert sorted(["https://www.amazon.it/", "https://www.amazon.com/"], key=_us_first)[0] == "https://www.amazon.com/"


def test_logo_endpoint(db, tmp_path, monkeypatch):
    from claimscout import logos
    monkeypatch.setattr(logos, "DIR", tmp_path)
    [s] = topclassactions.parse_feed(FEED)
    db.upsert_settlement(s)
    c = TestClient(create_app(db))
    h = {"Authorization": "Bearer " + pairing.token(db)}
    assert c.get(f"/api/logo/{s['id']}", headers=h).status_code == 404
    (tmp_path / "acme.png").write_bytes(b"\x89PNG fake")
    db.x("UPDATE settlements SET logo='acme.png' WHERE id=?", (s["id"],))
    assert c.get(f"/api/logo/{s['id']}", headers=h).content.startswith(b"\x89PNG")
    assert c.get("/api/settlements?view=all", headers=h).json()["settlements"][0]["logo"] is True
    db.x("UPDATE settlements SET logo=? WHERE id=?", ("../" * 30 + "etc/passwd", s["id"]))   # never serve outside the folder
    assert c.get(f"/api/logo/{s['id']}", headers=h).status_code == 404


def test_payout_classify():
    from claimscout.payouts import classify
    f = classify({"subject": "Equinox Data Breach Settlement - Your Virtual Prepaid Card", "date": "2026-03-01",
                  "text": "Your $104.12 virtual prepaid Mastercard is ready. This card expires on September 1, 2026."})
    assert f["kind"] == "virtual_card" and f["amount"] == "$104.12" and f["expires"] == "2026-09-01"
    assert f["settlement"].startswith("Equinox")
    f = classify({"subject": "Action required: select your payment method", "date": "2026-01-10",
                  "text": "To receive your payment from the Acme Settlement, choose PayPal, Venmo or a virtual card. "
                          "This link will expire within 90 days."})
    assert f["kind"] == "payment_choice" and f["expires"] == "2026-04-10" and f["settlement"] == "Acme"
    f = classify({"subject": "Notice of deficiency - Lands End Settlement", "date": "2026-10-02",
                  "text": "Your claim is missing information. Please respond by November 1, 2026."})
    assert f["kind"] == "deficiency" and f["expires"] == "2026-11-01"
    assert classify({"subject": "Notice of deficiency", "text": "Your claim is missing information"})["kind"] == "deficiency"
    assert classify({"subject": "Lunch?", "text": "hi"})["kind"] == "other"
    # a store promo found in the user's real inbox must not raise a "money waiting" alert
    assert classify({"from": "email@seller.etsy.com", "subject": "We'd love to hear from you",
                     "text": "A chance to win a $200 Virtual Visa Prepaid Card!"})["kind"] == "other"
    # the same words from an administrator are a payout
    assert classify({"from": "noreply@digitaldisbursements.com", "subject": "Your virtual prepaid card",
                     "text": "Your $200 Virtual Visa Prepaid Card is ready."})["kind"] == "virtual_card"


def test_payout_flow(db):
    c = TestClient(create_app(db))
    h = {"Authorization": "Bearer " + pairing.token(db)}
    [s] = topclassactions.parse_feed(FEED)
    db.upsert_settlement(s)
    plan = c.get("/api/payouts/plan", headers=h).json()
    assert plan["first_run"] and "epiqglobal.com" in plan["senders"] and "acmesettlement.example" in plan["senders"]
    msg = {"account": "me@gmail.com", "id": "gmail:spam:1", "from": "noreply@digitaldisbursements.com", "folder": "spam",
           "subject": "Acme Settlement: your virtual card", "date": "2026-02-01", "link": "https://mail.google.com/x",
           "text": "Your $25 virtual card expires 08/01/2026."}
    new = c.post("/api/payouts/scan", json={"messages": [msg, {**msg, "id": "2", "subject": "hi", "text": "hello"}]}, headers=h).json()["new"]
    assert len(new) == 1 and new[0]["needs_action"] and new[0]["folder"] == "spam"
    assert c.post("/api/payouts/scan", json={"messages": [msg]}, headers=h).json()["new"] == []   # seen before: no repeat alert
    assert c.get("/api/status", headers=h).json()["money_waiting"] == 1
    pid = c.get("/api/payouts", headers=h).json()["payouts"][0]["id"]
    c.post(f"/api/payouts/{pid}", json={"status": "done"}, headers=h)
    assert c.get("/api/payouts", headers=h).json()["payouts"] == []
    assert not c.get("/api/payouts/plan?since=1", headers=h).json()["first_run"]
