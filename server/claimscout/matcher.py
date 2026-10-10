"""Does the user probably qualify? Keyword rules first (instant, free), then an optional AI read.

Verdicts: likely | maybe | unknown | unlikely. A settlement limited to states the user never lived in is
"unlikely" and never reaches the AI.
"""
import json
import re
import time

from . import ai, questions

PROFILE_DEFAULT = {"name": "", "states": [], "past_states": [], "companies": [], "about": ""}

SYSTEM = (
    "You help one person decide whether they belong to a class action settlement. Be strict: a claim is "
    "sworn under penalty of perjury, so only say 'likely' when the profile clearly fits the eligibility "
    "text. Reply with JSON only."
)


def profile(db) -> dict:
    return {**PROFILE_DEFAULT, **(db.get("profile") or {})}


def _states(p):
    return {s.upper() for s in (p.get("states") or []) + (p.get("past_states") or [])}


def _hits(p, s) -> list[str]:
    hay = " ".join(filter(None, [s["title"], s.get("eligibility"), s.get("case_name"), s.get("summary")])).lower()
    out = []
    for c in p.get("companies") or []:
        c = c.strip()
        if len(c) >= 2 and re.search(r"(?<![a-z0-9])" + re.escape(c.lower()) + r"(?![a-z0-9])", hay):
            out.append(c)
    return out


def class_period(s) -> tuple[str | None, str | None]:
    from .text import all_dates
    d = sorted(all_dates(s.get("eligibility") or ""))
    return (d[0], d[-1]) if d else (None, None)


def rule_match(p, s) -> dict:
    after, before = class_period(s)
    if s["states"] and _states(p) and not (_states(p) & set(s["states"])):
        return {"score": 0.0, "verdict": "unlikely", "method": "rules",
                "reason": f"Only for people in {', '.join(s['states'])}.", "proof_plan": None}
    hits = _hits(p, s)
    plan = {"senders": [], "keywords": hits, "after": after, "before": before} if hits else None
    if hits:
        return {"score": 0.7, "verdict": "likely", "method": "rules", "proof_plan": plan,
                "reason": f"You listed {', '.join(hits)}."}
    if s["states"] and _states(p) & set(s["states"]):
        return {"score": 0.3, "verdict": "maybe", "method": "rules", "proof_plan": None,
                "reason": f"Limited to {', '.join(s['states'])}, where you've lived."}
    return {"score": 0.1, "verdict": "unknown", "method": "rules", "proof_plan": None, "reason": ""}


def _prompt(p, s) -> str:
    return f"""PROFILE
States lived in: {', '.join(sorted(_states(p))) or 'unknown'}
Companies, products and services used: {', '.join(p.get('companies') or []) or 'none listed'}
About: {p.get('about') or '-'}

SETTLEMENT: {s['title']}
Eligibility: {s.get('eligibility') or '-'}
Proof required: {s.get('proof') or 'unknown'}
Summary: {s.get('summary') or '-'}

Return JSON:
{{"verdict": "likely" | "maybe" | "unlikely",
  "reason": "one short sentence for the user",
  "proof_plan": {{"senders": ["email domains that would have sent a receipt/notice, e.g. apple.com"],
                 "keywords": ["words to search their email for"],
                 "after": "YYYY-MM-DD or null", "before": "YYYY-MM-DD or null"}} }}
Use proof_plan null when email could not help (e.g. it's about where they lived only)."""


async def ai_match(db, p, s) -> dict:
    d = await ai.ask_json(db, SYSTEM, _prompt(p, s))
    verdict = d.get("verdict") if d.get("verdict") in ("likely", "maybe", "unlikely") else "maybe"
    plan = d.get("proof_plan") if isinstance(d.get("proof_plan"), dict) else None
    if plan:
        plan = {"senders": [str(x) for x in plan.get("senders") or []][:6],
                "keywords": [str(x) for x in plan.get("keywords") or []][:8],
                "after": plan.get("after"), "before": plan.get("before")}
    return {"score": {"likely": 0.9, "maybe": 0.5, "unlikely": 0.05}[verdict], "verdict": verdict,
            "reason": str(d.get("reason") or "")[:300], "method": "ai", "proof_plan": plan}


def save(db, sid, m):
    db.x("""INSERT INTO matches(settlement_id,score,verdict,reason,method,proof_plan,updated_at) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(settlement_id) DO UPDATE SET score=excluded.score, verdict=excluded.verdict,
            reason=excluded.reason, method=excluded.method, proof_plan=excluded.proof_plan, updated_at=excluded.updated_at""",
         (sid, m["score"], m["verdict"], m["reason"], m["method"], json.dumps(m["proof_plan"]), time.time()))


async def run(db, use_ai=True, only_new=False, log=print) -> dict:
    """Score every open settlement. AI reads the ones the rules didn't rule out."""
    p = profile(db)
    done = {r["settlement_id"]: r["method"] for r in db.q("SELECT settlement_id, method FROM matches")}
    given = questions.answers(db)
    counts = {"rules": 0, "ai": 0, "ai_errors": 0, "answers": 0}
    for s in db.settlements():
        if only_new and s["id"] in done:
            continue
        m = await match_one(db, p, s, given.get(s["id"]), use_ai, counts, log)
        save(db, s["id"], m)
    return counts


async def match_one(db, p, s, answer=None, use_ai=True, counts=None, log=print) -> dict:
    """The user's own answer decides; rules and AI only fill in the rest (and the email search plan for a yes)."""
    counts = counts if counts is not None else {"rules": 0, "ai": 0, "ai_errors": 0, "answers": 0}
    direct = questions.answer_match(answer)
    if direct and direct["verdict"] == "unlikely":
        counts["answers"] += 1
        return direct
    m = rule_match(p, s)
    if use_ai and ai.enabled(db) and (m["verdict"] != "unlikely" or direct):
        try:
            m = await ai_match(db, p, s)
            counts["ai"] += 1
        except ai.AIError as e:
            counts["ai_errors"] += 1
            log(f"AI skipped {s['id']}: {e}")
    else:
        counts["rules"] += 1
    if direct:   # a yes: keep the search plan, trust the answer
        counts["answers"] += 1
        m = {**m, "score": direct["score"], "verdict": "likely", "method": "answer", "reason": direct["reason"],
             "proof_plan": m.get("proof_plan") or fallback_plan(db, s)}
    return m


def fallback_plan(db, s) -> dict:
    """A search plan when no match stored one: the defendant/company words from the title, plus the class period."""
    after, before = class_period(s)
    words = re.sub(r"^\$[\d.,]+[MBK]?\s+", "", s["title"]).split()
    stop = {"data", "breach", "class", "action", "settlement", "false", "advertising", "insurance", "fees",
            "privacy", "violation", "bipa", "website", "tracking", "lawsuit", "unauthorized"}
    kw = [w for w in words if w.lower().strip(",") not in stop][:2]
    return {"senders": [], "keywords": [" ".join(kw)] if kw else [], "after": after, "before": before}
