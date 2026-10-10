"""ClaimScout server: the HTTPS API the phone pairs with, plus the dashboard on http://127.0.0.1:8788."""
import asyncio
import hmac
import ipaddress
import json
import re
import time
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from . import ai, matcher, pairing, proof
from .collectors import community, topclassactions
from .db import DB

VERSION = "0.1.0"
REFRESH_EVERY = 6 * 3600
WEB = Path(__file__).parent / "web"


class Hub:
    def __init__(self, db: DB, port=8787):
        self.db, self.port = db, port
        self.lock = asyncio.Lock()
        self.task = None

    async def refresh(self, log=print) -> dict:
        """Pull every source, then score what's new (or everything if the profile changed)."""
        async with self.lock:
            report = {"new": 0, "seen": 0, "errors": []}
            sources = [("Top Class Actions", topclassactions.fetch())]
            sources += [(u, community.fetch(u)) for u in self.db.get("feeds", [])]
            for name, job in sources:
                try:
                    for s in await job:
                        report["new" if self.db.upsert_settlement(s) else "seen"] += 1
                except Exception as e:   # one broken source must not stop the others
                    report["errors"].append(f"{name}: {e}")
                    log(f"refresh {name} failed: {e}")
            full = self.db.get("rematch", True)
            self.db.put("rematch", False)   # cleared first: a profile saved during this run sets it again
            report["matching"] = await matcher.run(self.db, only_new=not full, log=log)
            self.db.put("last_refresh", {"at": time.time(), **report})
        if self.db.get("rematch"):
            await self.refresh(log)
        return report

    def refresh_soon(self, rematch=False):
        if rematch:
            self.db.put("rematch", True)
        if not self.lock.locked():
            asyncio.get_running_loop().create_task(self.refresh())

    async def loop(self):
        while True:
            last = (self.db.get("last_refresh") or {}).get("at", 0)
            if time.time() - last >= REFRESH_EVERY:
                try:
                    await self.refresh()
                except Exception as e:
                    print("refresh failed:", e)
            await asyncio.sleep(600)


def _loopback(request: Request) -> bool:
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except (ValueError, AttributeError):
        return False


def create_app(db: DB, port=8787, dashboard=False, hub: Hub | None = None) -> FastAPI:
    hub = hub or Hub(db, port)
    app = FastAPI(title="ClaimScout", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.hub = hub

    def auth(request: Request):
        given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not given or not hmac.compare_digest(given, pairing.token(db)):
            raise HTTPException(401, "not paired")
        if request.method in ("POST", "PUT", "DELETE") and \
                not request.headers.get("content-type", "").startswith("application/json"):
            raise HTTPException(415, "send JSON")

    api = Depends(auth)

    if dashboard:
        @app.get("/", response_class=HTMLResponse)
        def index():
            return FileResponse(WEB / "index.html")

        @app.get("/api/pair", dependencies=[api])
        def pair(request: Request):
            if not _loopback(request):
                raise HTTPException(403, "pairing is only shown on the PC itself")
            link = pairing.link(db, port)
            return {"link": link, "qr": pairing.qr_svg(link), "fingerprint": pairing.fingerprint(),
                    "addresses": pairing.addresses()}

    @app.get("/api/status", dependencies=[api])
    def status():
        n = db.q("""SELECT COUNT(*) n, SUM(m.verdict='likely') likely, SUM(m.verdict='maybe') maybe
                    FROM settlements s LEFT JOIN matches m ON m.settlement_id=s.id
                    WHERE s.deadline IS NULL OR s.deadline >= date('now')""")[0]
        return {"version": VERSION, "open": n["n"], "likely": n["likely"] or 0, "maybe": n["maybe"] or 0,
                "claims": db.q("SELECT COUNT(*) n FROM claims")[0]["n"], "refreshing": hub.lock.locked(),
                "last_refresh": db.get("last_refresh"), "ai": ai.public_settings(db),
                "profile_set": bool(matcher.profile(db)["companies"] or matcher.profile(db)["states"])}

    @app.get("/api/profile", dependencies=[api])
    def get_profile():
        return matcher.profile(db)

    @app.put("/api/profile", dependencies=[api])
    async def put_profile(p: dict = Body(...)):
        clean = {**matcher.PROFILE_DEFAULT}
        for k in ("name", "about"):
            clean[k] = str(p.get(k) or "")[:4000]
        for k in ("states", "past_states"):
            clean[k] = [str(x).upper()[:2] for x in p.get(k) or [] if str(x).strip()][:60]
        clean["companies"] = [str(x).strip()[:80] for x in p.get("companies") or [] if str(x).strip()][:300]
        db.put("profile", clean)
        hub.refresh_soon(rematch=True)
        return clean

    @app.get("/api/ai", dependencies=[api])
    def get_ai():
        return {**ai.public_settings(db), "presets": ai.PRESETS}

    @app.put("/api/ai", dependencies=[api])
    def put_ai(s: dict = Body(...)):
        cur = ai.settings(db)
        prov = s.get("provider", cur["provider"])
        if prov not in ai.PRESETS:
            raise HTTPException(400, "unknown provider")
        new = {"provider": prov, "base_url": str(s.get("base_url") or ai.PRESETS[prov]["base_url"]).strip(),
               "model": str(s.get("model", cur["model"]) or "").strip(),
               # "set" is what we show for a stored key; keep the old one unless a new one was typed
               "api_key": cur["api_key"] if s.get("api_key") in (None, "set") else str(s["api_key"]).strip()}
        db.put("ai", new)
        return ai.public_settings(db)

    @app.post("/api/ai/test", dependencies=[api])
    async def test_ai():
        try:
            reply = await ai.chat(db, "Reply with the single word: ready", "Are you there?", max_tokens=400)
            return {"ok": True, "reply": re.sub(r"<think>.*?</think>", "", reply, flags=re.S).strip()[:100] or "(connected)"}
        except ai.AIError as e:
            return {"ok": False, "error": str(e)}

    @app.get("/api/ai/openrouter-free", dependencies=[api])
    async def or_free():
        try:
            return {"models": await ai.free_openrouter_models()}
        except Exception as e:
            raise HTTPException(502, f"OpenRouter: {e}")

    @app.get("/api/feeds", dependencies=[api])
    def get_feeds():
        return {"feeds": db.get("feeds", [])}

    @app.put("/api/feeds", dependencies=[api])
    def put_feeds(body: dict = Body(...)):
        feeds = [u.strip() for u in body.get("feeds") or [] if str(u).startswith("https://")][:20]
        db.put("feeds", feeds)
        hub.refresh_soon()
        return {"feeds": feeds}

    @app.post("/api/refresh", dependencies=[api])
    async def refresh(body: dict = Body(default={})):
        hub.refresh_soon(rematch=bool(body.get("rematch")))
        return {"started": True}

    def _row(r):
        r["states"] = json.loads(r["states"] or "[]")
        r["proof_plan"] = json.loads(r["proof_plan"]) if r.get("proof_plan") else None
        return r

    @app.get("/api/settlements", dependencies=[api])
    def settlements(view: str = "matches", q: str = ""):
        where = ["(s.deadline IS NULL OR s.deadline >= date('now'))"]
        args = []
        if view == "matches":
            where.append("m.verdict IN ('likely','maybe') AND COALESCE(m.dismissed,0)=0")
        elif view == "claimed":
            where = ["c.id IS NOT NULL"]
        elif view == "noproof":
            where.append("s.proof_needed=0 AND COALESCE(m.verdict,'') != 'unlikely'")
        if q:
            where.append("(s.title LIKE ? OR s.eligibility LIKE ?)")
            args += [f"%{q}%"] * 2
        rows = db.q(f"""SELECT s.id, s.title, s.award, s.deadline, s.proof_needed, s.states, s.source,
                        m.verdict, m.score, m.reason, m.method, m.proof_plan, c.status claim_status,
                        (SELECT COUNT(*) FROM proofs p WHERE p.settlement_id=s.id) proofs
                        FROM settlements s LEFT JOIN matches m ON m.settlement_id=s.id
                        LEFT JOIN claims c ON c.settlement_id=s.id WHERE {' AND '.join(where)}
                        ORDER BY COALESCE(m.score,0) DESC, s.deadline IS NULL, s.deadline LIMIT 500""", args)
        return {"settlements": [_row(r) for r in rows]}

    def _get(sid):
        s = db.settlement(sid)
        if not s:
            raise HTTPException(404, "no such settlement")
        return s

    @app.get("/api/settlements/{sid}", dependencies=[api])
    def settlement(sid: str):
        s = _get(sid)
        m = db.q("SELECT * FROM matches WHERE settlement_id=?", (sid,))
        m = m[0] if m else None
        if m:
            m["proof_plan"] = json.loads(m["proof_plan"]) if m["proof_plan"] else None
        plan = (m or {}).get("proof_plan") or matcher.fallback_plan(db, s)
        claim = db.q("SELECT * FROM claims WHERE settlement_id=?", (sid,))
        return {**s, "match": m, "proof_plan": plan, "claim": claim[0] if claim else None,
                "proofs": db.q("SELECT * FROM proofs WHERE settlement_id=? ORDER BY date", (sid,))}

    @app.post("/api/settlements/{sid}/dismiss", dependencies=[api])
    def dismiss(sid: str, body: dict = Body(default={})):
        _get(sid)
        db.x("INSERT INTO matches(settlement_id, dismissed) VALUES(?,?) ON CONFLICT(settlement_id) "
             "DO UPDATE SET dismissed=excluded.dismissed", (sid, 0 if body.get("undo") else 1))
        return {"ok": True}

    @app.post("/api/settlements/{sid}/match", dependencies=[api])
    async def rematch_one(sid: str):
        s = _get(sid)
        p = matcher.profile(db)
        m = matcher.rule_match(p, s)
        if ai.enabled(db):
            try:
                m = await matcher.ai_match(db, p, s)
            except ai.AIError as e:
                m["reason"] = (m["reason"] + f" (AI unavailable: {e})").strip()
        matcher.save(db, sid, m)
        return m

    @app.post("/api/settlements/{sid}/proof", dependencies=[api])
    async def add_proof(sid: str, body: dict = Body(...)):
        """The phone found these emails with the proof plan; keep the ones that prove something."""
        return {"proofs": await proof.extract(db, _get(sid), body.get("messages"))}

    @app.delete("/api/proofs/{pid}", dependencies=[api])
    def del_proof(pid: int):
        db.x("DELETE FROM proofs WHERE id=?", (pid,))
        return {"ok": True}

    @app.put("/api/claims/{sid}", dependencies=[api])
    def put_claim(sid: str, c: dict = Body(...)):
        _get(sid)
        status = c.get("status") or "filed"
        if status not in ("filed", "approved", "paid", "denied"):
            raise HTTPException(400, "status is filed, approved, paid or denied")
        vals = [str(c.get(k) or "")[:500] for k in ("claim_number", "filed_at", "expected", "paid", "notes")]
        db.x("""INSERT INTO claims(settlement_id,status,claim_number,filed_at,expected,paid,notes,updated_at)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(settlement_id) DO UPDATE SET status=excluded.status,
                claim_number=excluded.claim_number, filed_at=excluded.filed_at, expected=excluded.expected,
                paid=excluded.paid, notes=excluded.notes, updated_at=excluded.updated_at""",
             (sid, status, *vals, time.time()))
        return db.q("SELECT * FROM claims WHERE settlement_id=?", (sid,))[0]

    @app.delete("/api/claims/{sid}", dependencies=[api])
    def del_claim(sid: str):
        db.x("DELETE FROM claims WHERE settlement_id=?", (sid,))
        return {"ok": True}

    @app.get("/api/claims", dependencies=[api])
    def claims():
        return {"claims": db.q("""SELECT c.*, s.title, s.deadline, s.award FROM claims c
                                  JOIN settlements s ON s.id=c.settlement_id ORDER BY c.updated_at DESC""")}

    @app.get("/api/new", dependencies=[api])
    def new(since: float = 0):
        """Likely matches scored after `since` and still open: what the phone notifies about."""
        rows = db.q("""SELECT s.id, s.title, s.deadline, s.award, m.updated_at FROM matches m
                       JOIN settlements s ON s.id=m.settlement_id
                       WHERE m.verdict='likely' AND m.updated_at > ? AND COALESCE(m.dismissed,0)=0
                       AND (s.deadline IS NULL OR s.deadline >= date('now'))
                       AND NOT EXISTS (SELECT 1 FROM claims c WHERE c.settlement_id=s.id)
                       ORDER BY m.updated_at""", (since,))
        return {"new": rows, "now": time.time()}

    return app
