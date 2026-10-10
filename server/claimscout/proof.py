"""Turn emails the phone found into proof for a claim: what it is, when, how much, order number.

The phone sends only the messages its search matched, each trimmed to MAX_CHARS. We keep the extracted
facts and the message reference (to reopen it on the phone), not the email body.
"""
import re
import time

from . import ai, mailfilter
from .logos import defendant

MAX_CHARS = 4000
MAX_MESSAGES = 15

SYSTEM = ("You read a person's emails to find proof for a class action claim: receipts, order confirmations, "
          "account/membership emails, subscription bills, or data breach notices. Reply with JSON only.")

_ORDER = re.compile(r"\b(?:order|confirmation|invoice|receipt)\s*(?:number|no\.?|#|id)?\s*[:#]?\s*(?=[A-Z0-9-]*\d)([A-Z0-9][A-Z0-9-]{4,24})\b", re.I)
_AMOUNT = re.compile(r"(?:total|amount|charged|paid)[^$\n]{0,30}(\$\s?\d[\d,]*(?:\.\d{2})?)", re.I)
_KINDS = [("breach_notice", r"data (security )?(breach|incident)|notice of data|unauthorized access"),
          ("receipt", r"receipt|order|invoice|purchase|your payment|thank you for (your )?(order|purchase)|shipped"),
          ("subscription", r"subscription|renewal|membership|billing statement|your bill"),
          ("account", r"welcome|account|verify your email|sign[- ]?in")]


def clean(messages):
    out = []
    for m in (messages or [])[:MAX_MESSAGES]:
        out.append({"account": str(m.get("account", ""))[:200], "id": str(m.get("id", ""))[:300],
                    "from": str(m.get("from", ""))[:200], "subject": str(m.get("subject", ""))[:300],
                    "date": str(m.get("date", ""))[:40], "text": str(m.get("text", ""))[:MAX_CHARS]})
    return out


def company(s) -> tuple[list[str], list[str]]:
    """(names, domains) the company behind a settlement goes by."""
    names = [x for x in (s.get("company"), defendant(s.get("summary")), s.get("label")) if x]
    return names, [d for d in (s.get("domain"),) if d]


def from_company(m, s) -> bool:
    """Proof comes from the company itself, or (breach notices) a settlement administrator."""
    from .payouts import ADMINISTRATORS
    names, domains = company(s)
    return mailfilter.sender_is(m, names, domains + ADMINISTRATORS)


def heuristic(m, s=None) -> dict | None:
    if mailfilter.is_marketing(m) or (s is not None and not from_company(m, s)):
        return None
    blob = f"{m['subject']}\n{m['text']}"
    kind = next((k for k, pat in _KINDS if re.search(pat, blob, re.I)), None)
    if not kind:
        return None
    order = _ORDER.search(blob)
    amount = _AMOUNT.search(blob)
    return {"kind": kind, "order_number": order.group(1) if order else None,
            "amount": amount.group(1).replace(" ", "") if amount else None,
            "summary": m["subject"][:160], "date": m["date"]}


async def extract(db, s, messages) -> list[dict]:
    # newsletters advertising settlements mention every company and are never proof
    msgs = [m for m in clean(messages) if not mailfilter.is_marketing(m)]
    if not msgs:
        return []
    found = {}
    if ai.enabled(db):
        listing = "\n\n".join(f"[{i}] From: {m['from']}\nDate: {m['date']}\nSubject: {m['subject']}\n{m['text']}"
                              for i, m in enumerate(msgs))
        user = (f"SETTLEMENT: {s['title']}\nEligibility: {s.get('eligibility') or '-'}\n"
                f"Proof the claim needs: {s.get('proof') or 'unknown'}\n\nEMAILS\n{listing}\n\n"
                'Return a JSON array, one entry per email that is useful proof for THIS settlement:\n'
                '[{"index": 0, "kind": "receipt|account|subscription|breach_notice|other", "date": "YYYY-MM-DD", '
                '"amount": "$12.34 or null", "order_number": "or null", "summary": "what it proves, one line"}]\n'
                "Only count emails the company itself (or a settlement administrator) sent to this person: receipts, "
                "order or account emails, statements, breach notices. Newsletters or ads about settlements are never "
                "proof. Leave out unrelated emails. Return [] if none help.")
        try:
            rows = await ai.ask_json(db, SYSTEM, user, max_tokens=1200)
            for r in rows if isinstance(rows, list) else []:
                i = r.get("index")
                if isinstance(i, int) and 0 <= i < len(msgs):
                    found[i] = {k: (str(r[k])[:200] if r.get(k) not in (None, "null", "") else None)
                                for k in ("kind", "date", "amount", "order_number", "summary")}
        except ai.AIError:
            found = {}
    if not found:
        found = {i: h for i, m in enumerate(msgs) if (h := heuristic(m, s))}
    out = []
    for i, f in sorted(found.items()):
        m = msgs[i]
        row = {"settlement_id": s["id"], "account": m["account"], "message_id": m["id"], "sender": m["from"],
               "subject": m["subject"], "date": f.get("date") or m["date"], "kind": f.get("kind"),
               "amount": f.get("amount"), "order_number": f.get("order_number"), "summary": f.get("summary")}
        db.x("""INSERT INTO proofs(settlement_id,account,message_id,sender,subject,date,kind,amount,order_number,summary,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(settlement_id,account,message_id) DO UPDATE SET
                kind=excluded.kind, amount=excluded.amount, order_number=excluded.order_number,
                summary=excluded.summary, date=excluded.date""",
             (*row.values(), time.time()))
        out.append(row)
    return out


def plan_for(s, plan: dict | None) -> dict:
    """Search the company's own mail when we know its website (a receipt comes from equifax.com, a newsletter
    that mentions Equifax doesn't)."""
    plan = dict(plan or {})
    if s.get("domain") and not plan.get("senders"):
        plan["senders"] = [s["domain"]]
    return plan
