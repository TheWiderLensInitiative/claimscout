"""The onboarding questionnaire, built from the open settlements.

Each settlement gets a short label ("Crossroads Trading"), a category ("Data breaches & privacy") and, when AI
is on, one plain yes/no question ("Did you shop at Crossroads Trading and get a breach notice in 2023?").
The phone shows the labels as chips per category ("Which of these have you used?"), then asks the question
for each one picked. Answers feed straight into matching.
"""
import json
import re
import time

from . import ai

ANSWERS = ("yes", "no", "unsure", "unused")

# (category, prompt shown above its chips, words that put a settlement in it); first match wins
CATEGORIES = [
    ("Data breaches & privacy", "Were you a customer, patient, member or employee of any of these?",
     r"data breach|privacy|tracking|tracker|pixel|bipa|vppa|data sharing|biometric|cyber"),
    ("Cars", "Have you owned or leased any of these?",
     r"\b(kia|hyundai|toyota|jeep|fca|honda|ford|gm|chevrolet|nissan|tesla|bmw|subaru|vehicle|car|airbag|air bag|emissions)\b"),
    ("Insurance", "Have you been insured by any of these?",
     r"insurance|insured|state farm|progressive|geico|allstate|globe life|\bpip\b|umpd|lloyd|anthem|denied benefits|coverage"),
    ("Banking, credit & fees", "Have you used any of these banks, cards, lenders or credit bureaus?",
     r"\bbank|credit|equifax|transunion|experian|\bvisa\b|mastercard|\batm\b|\bloans?\b|tcpa|\bfees?\b|pacer"),
    ("Health & medicine", "Have you used any of these health services or medicines?",
     r"health|medical|hospital|dental|oncology|pharma|\bdrugs?\b|prosthes|clinic|telehealth|probiotic|generic"),
    ("Work", "Have you worked for any of these?", r"\b(wages?|labor|overtime|employees?|workers?|staffing|logistics)\b"),
    ("Home & products", "Have you bought or used any of these products?",
     r"refrigerator|\bpool\b|purifier|shingles|solar|insulation|sunglasses|appliance|recall|defective|iphone|siri|\bapple\b|"
     r"\bpork\b|\bfood\b|steamer|tractor|deere"),
    ("Shopping, services & housing", "Have you used any of these stores, apps or services?",
     r"\b(amazon|cvs|walmart|target|schnucks|rewards|return policy|real estate|realtors?|nar|rent|renters|realpage|"
     r"subscription|streaming)\b"),
]
OTHER = ("Something else", "Do any of these apply to you?")
PROMPTS = dict((c, p) for c, p, _ in CATEGORIES) | {OTHER[0]: OTHER[1]}

_DESCRIPTORS = (r"\b(data breach|class action|settlement|antitrust|price-fixing|false advertising|privacy violations?|"
                r"digital privacy|data privacy|data sharing|website tracking|tracking pixel|wage and hour violations?|"
                r"child labor|bipa violation|bipa|vppa|tcpa|denied benefits|unauthorized loans|return policy|"
                r"inaccurate credit report|hard inquiry dispute|credit reporting|defective|recall|insurance price-fixing|"
                r"soil contamination|safety|repair|delamination|real estate commission|non-bank atm|record fees|"
                r"fee|rewards|car insurance|insurance|period tracker|air bag control units|airbag|emissions warranty|"
                r"settlement offers.*)\b.*$")


def rule_label(title: str) -> str:
    t = re.sub(r"^\$[\d.,]+\s*[MBK]?\b\s*|\s*\$[\d.,]+\s*[MBK]?$", "", title.strip())
    t = re.sub(r"\s+(Illinois|New York|California|Louisiana)\b(?=.*\b(BIPA|insurance|car)\b)", "", t)
    short = re.sub(_DESCRIPTORS, "", t, flags=re.I).strip(" ,-–") or t
    return short[0].upper() + short[1:]


def rule_category(s: dict) -> str:
    """The title decides when it can; the summary only breaks ties ("$4.5M Hearthside Food Solutions child labor")."""
    for hay in (s["title"].lower(), (s.get("summary") or "").lower()):
        for name, _, pat in CATEGORIES:
            if re.search(pat, hay):
                return name
    return OTHER[0]


def ensure_labels(db) -> int:
    """Give every settlement without a label a rule-based one. Returns how many were labelled."""
    rows = db.q("SELECT id, title, summary FROM settlements WHERE label IS NULL")
    for s in rows:
        db.x("UPDATE settlements SET label=?, category=? WHERE id=?", (rule_label(s["title"]), rule_category(s), s["id"]))
    return len(rows)


SYSTEM = ("You turn class action settlements into a friendly questionnaire for ordinary people. Be accurate: keep the "
          "key eligibility conditions (product, place, date range). Reply with JSON only.")


async def enrich(db, batch=8, log=print) -> int:
    """AI rewrites labels/categories and adds one yes/no question per settlement. Safe to call often."""
    if not ai.enabled(db):
        return 0
    todo = db.q("""SELECT id, title, eligibility FROM settlements WHERE COALESCE(enriched,0)=0
                   AND (deadline IS NULL OR deadline >= date('now')) ORDER BY deadline""")
    done = 0
    cats = [c for c, _, _ in CATEGORIES] + [OTHER[0]]
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        listing = "\n\n".join(f"[{s['id']}] {s['title']}\nEligible: {(s['eligibility'] or '')[:900]}" for s in chunk)
        user = (f"{listing}\n\nFor each settlement return an object in a JSON array:\n"
                '{"id": "...", "label": "the company, brand or product people would recognise, max 4 words", '
                f'"category": one of {json.dumps(cats)}, '
                '"question": "one yes/no question, max 30 words, starting with Did/Have/Were/Are, with the dates and places that matter"}')
        try:
            rows = await ai.ask_json(db, SYSTEM, user, max_tokens=2000)
        except ai.AIError as e:
            log(f"questionnaire AI skipped a batch: {e}")
            continue
        ids = {s["id"] for s in chunk}
        for r in rows if isinstance(rows, list) else []:
            if not isinstance(r, dict) or r.get("id") not in ids:
                continue
            label = str(r.get("label") or "").strip()[:60]
            question = str(r.get("question") or "").strip()[:300]
            category = r.get("category") if r.get("category") in cats else None
            db.x("""UPDATE settlements SET label=COALESCE(NULLIF(?,''), label), category=COALESCE(?, category),
                    question=NULLIF(?,''), enriched=1 WHERE id=?""", (label, category, question, r["id"]))
            done += 1
    return done


def answers(db) -> dict:
    return {r["settlement_id"]: r["answer"] for r in db.q("SELECT settlement_id, answer FROM answers")}


def build(db, profile: dict, only_unanswered=True) -> dict:
    """Groups of chips for the phone, skipping settlements limited to states the user never lived in."""
    ensure_labels(db)
    mine = {x.upper() for x in profile.get("states", []) + profile.get("past_states", [])}
    have = answers(db)
    groups: dict[str, list] = {}
    skipped_state = 0
    for s in db.settlements():
        if only_unanswered and s["id"] in have:
            continue
        if mine and s["states"] and not (mine & set(s["states"])):
            skipped_state += 1
            continue
        row = db.q("SELECT label, category, question FROM settlements WHERE id=?", (s["id"],))[0]
        groups.setdefault(row["category"] or OTHER[0], []).append({
            "id": s["id"], "label": row["label"] or s["title"], "title": s["title"], "question": row["question"],
            "eligibility": s.get("eligibility"), "states": s["states"], "deadline": s["deadline"],
            "award": s.get("award"), "proof_needed": s.get("proof_needed"), "answer": have.get(s["id"])})
    order = [c for c, _, _ in CATEGORIES] + [OTHER[0]]
    out = [{"category": c, "prompt": PROMPTS[c], "items": sorted(groups[c], key=lambda x: x["label"].lower())}
           for c in order if c in groups]
    return {"states_known": bool(mine), "groups": out, "count": sum(len(g["items"]) for g in out),
            "skipped_by_state": skipped_state, "answered": len(have)}


def save(db, given: dict) -> int:
    n = 0
    now = time.time()
    for sid, a in (given or {}).items():
        if a in ANSWERS and db.q("SELECT 1 FROM settlements WHERE id=?", (sid,)):
            db.x("INSERT INTO answers(settlement_id, answer, at) VALUES(?,?,?) ON CONFLICT(settlement_id) "
                 "DO UPDATE SET answer=excluded.answer, at=excluded.at", (sid, a, now))
            n += 1
    return n


def answer_match(a: str | None) -> dict | None:
    """A direct answer beats any guess."""
    if a == "yes":
        return {"score": 0.95, "verdict": "likely", "method": "answer", "reason": "You said this applies to you.",
                "proof_plan": None}
    if a in ("no", "unused"):
        return {"score": 0.0, "verdict": "unlikely", "method": "answer", "reason": "You said this doesn't apply to you.",
                "proof_plan": None}
    return None
