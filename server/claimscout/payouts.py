"""Payout watcher: find settlement payment emails (virtual cards, "choose your payment" links, PayPal/Venmo
payments, mailed checks, requests for more information) before they expire, including in Spam.

The phone searches its inboxes with the plan from `watch_plan` every few hours and sends what it finds here.
We work out what each email is, the amount and the expiry date, and keep the facts plus a link to reopen it.
"""
import datetime as dt
import re
import time

from . import ai, mailfilter
from .text import all_dates, max_amount, parse_date

# Settlement administrators and the payment services they use. Community additions welcome.
ADMINISTRATORS = [
    "epiqglobal.com", "epiqsystems.com", "kroll.com", "ra.kroll.com", "angeiongroup.com", "jndla.com",
    "simpluris.com", "rustconsulting.com", "gilardi.com", "abdata.com", "cptgroup.com", "atticusadmin.com",
    "veritaglobal.com", "veritaconnect.com", "analyticsllc.com", "ilymgroup.com", "kccllc.net", "kccllc.com",
    "apexclassaction.com", "pnclassaction.com", "ksacms.com", "aplsconnect.com", "strategicclaims.net",
    "classactionadmin.com", "settlementadministrator.com", "dahladmin.com", "heffler.com", "eisnerampergroup.com",
    "americanlegalclaims.com", "classaction.org",
    # payment services used for settlement payouts
    "digitaldisbursements.com", "tangocard.com", "prepaiddigitalsolutions.com", "virtualrewardcenter.com",
    "paymentservicesnetwork.com", "payments.epiqglobal.com", "myprepaidcenter.com", "epiqnotice.com",
    "e.paypal.com", "paypal.com", "venmo.com",
]
# A debt collector's "payment options" are money you'd pay, not money you're owed.
DEBT = re.compile(r"debt collector|collection agency|attempt to collect a debt|past due|amount (you )?owe|balance (due|owed)|"
                  r"payment plan|trueaccord|settle (your|this) (account|balance|debt)|scheduling options", re.I)
# A class notice goes to everyone who *might* be in the class ("Legal Notice", "Settlement Notice", "you may be
# eligible"). It isn't a payment, unless it's about your own claim (a deficiency notice, a claim ID, your payment).
CLASS_NOTICE = re.compile(r"(legal|settlement|class action|court.ordered|important) notice|notice of (proposed |pending )?"
                          r"(class action )?settlement|you (may|might) (be|qualify)|if you (bought|purchased|paid|used|were)", re.I)
OWN_CLAIM = re.compile(r"deficien|your claim|claim (id|number|no\.?|#)|claimant id|your (settlement )?payment|payment for your claim|"
                       r"your (virtual|prepaid|digital) (card|payment)", re.I)
# Talk that only an email about a class action claim has (a wallet or bank "your card" email doesn't).
SETTLEMENT_TALK = re.compile(r"settlement|class action|litigation|your claim|claim (id|number|no\.?|#)|claimant", re.I)
PHRASES = ["settlement administrator", "class action settlement", "virtual prepaid card", "virtual card",
           "settlement payment", "payment election", "select your payment", "choose your payment",
           "digital payment", "claim number", "notice of deficiency", "settlement check"]

KINDS = {   # first match wins; order matters (a virtual card email also says "settlement payment")
    "virtual_card": r"virtual (prepaid )?(card|mastercard|visa)|prepaid (mastercard|visa|card)|reward card|card number",
    "payment_choice": r"(select|choose|elect|pick) (your |a )?(payment|how you|method)|payment election|digital payment (option|choice)|"
                      r"redeem your (payment|settlement)|claim your (payment|money|funds)",
    "deficiency": r"deficien|missing information|incomplete claim|additional (information|documentation)|cure (the|your) claim",
    "digital_payment": r"(paypal|venmo|zelle|cash app|ach|direct deposit).{0,80}(payment|sent|deposit)|"
                       r"(payment|deposit).{0,80}(paypal|venmo|zelle|cash app)",
    "check": r"check (was|has been|will be) (mailed|issued|sent)|settlement check|check enclosed|cash your check",
    "denied": r"(claim|submission) (has been |was )?(denied|rejected)|not (an )?eligible|ineligible",
    "claim_update": r"claim (has been |was )?(received|submitted|approved|accepted)|confirmation|claim (id|number)",
}
ACTION = {"virtual_card", "payment_choice", "deficiency", "digital_payment", "check"}
LABELS = {"virtual_card": "Virtual card", "payment_choice": "Choose your payment", "deficiency": "More info needed",
          "digital_payment": "Payment sent", "check": "Check", "denied": "Claim denied", "claim_update": "Claim update",
          "other": "Settlement email"}


def watch_plan(db, since: float | None) -> dict:
    """What the phone should search for: administrator senders, settlement site domains, phrases, and from when."""
    sites = set()
    for r in db.q("SELECT claim_url, website FROM settlements"):
        for u in (r["claim_url"], r["website"]):
            host = re.sub(r"^https?://(www\.)?", "", (u or "").lower()).split("/")[0]
            if host and "." in host:
                sites.add(".".join(host.split(".")[-2:]))
    first = since is None
    after = dt.date.today() - (dt.timedelta(days=730) if first else
                               dt.timedelta(days=max(2, int((time.time() - since) / 86400) + 2)))
    return {"senders": sorted(set(ADMINISTRATORS) | sites), "phrases": PHRASES, "after": after.isoformat(),
            "first_run": first}


def _from_administrator(sender: str) -> bool:
    host = (re.search(r"@([\w.-]+)", sender or "") or [None, ""])[1].lower()
    return any(host == d or host.endswith("." + d) for d in ADMINISTRATORS if d not in ("paypal.com", "e.paypal.com", "venmo.com"))


def classify(m: dict) -> dict:
    blob = f"{m.get('subject', '')}\n{m.get('text', '')}"
    # Ads are never payouts: a store promo ("win a $200 Virtual Visa Prepaid Card!") or a settlement newsletter
    # ("Claim your share of $380M!"). A payout comes from an administrator or talks about *your* claim.
    if mailfilter.is_marketing(m) or DEBT.search(blob) or not (
            _from_administrator(m.get("from", "")) or (mailfilter.is_personal(m) and SETTLEMENT_TALK.search(blob))):
        return {"kind": "other", "amount": None, "expires": None, "settlement": None}
    if CLASS_NOTICE.search(m.get("subject", "")) and not OWN_CLAIM.search(blob):
        return {"kind": "other", "amount": None, "expires": None, "settlement": None}
    # the subject says what the email is for; the body often lists every payment option
    kind = next((k for hay in (m.get("subject", ""), blob) for k, pat in KINDS.items()
                 if re.search(pat, hay, re.I | re.S)), "other")
    expires = None
    if e := re.search(r"(expire[sd]?|valid (until|through)|redeem by|must be (cashed|redeemed|claimed) by|deadline|"
                      r"(respond|reply|submit[^.\n]{0,30}) (by|no later than))"
                      r"[^.\n]{0,60}", blob, re.I):
        expires = (all_dates(e.group(0)) or [None])[0]
        if not expires and (d := re.search(r"within (\d{1,3}) days", e.group(0), re.I)) and parse_date(m.get("date", "")):
            expires = (dt.date.fromisoformat(parse_date(m["date"])) + dt.timedelta(days=int(d.group(1)))).isoformat()
    if not expires and (d := re.search(r"(expire|void)[^.\n]{0,30}(\d{2,3}) days", blob, re.I)) and parse_date(m.get("date", "")):
        expires = (dt.date.fromisoformat(parse_date(m["date"])) + dt.timedelta(days=int(d.group(2)))).isoformat()
    name = settlement_name(m)
    return {"kind": kind, "amount": (lambda a: f"${a:,.2f}".replace(".00", "") if a else None)(max_amount(blob)),
            "expires": expires, "settlement": name[:80] if name else None}


_NOT_NAMES = {"sincerely", "court", "the", "this", "your", "our", "a", "an", "dear", "notice", "important", "re", "fwd"}


def _good_name(n: str | None) -> str | None:
    n = (n or "").strip(" -–:,")
    words = re.findall(r"[A-Za-z][\w&'’.-]*", n)
    if not words or n.endswith((".", ",")) and len(words) == 1 or all(w.lower().strip(".,") in _NOT_NAMES for w in words):
        return None
    return n[:80]


def settlement_name(m: dict) -> str | None:
    """Which settlement an email is about, best source first."""
    sender, subject, text = m.get("from", ""), m.get("subject", ""), m.get("text", "")[:600]
    # "Dr. Squatch Settlement Administrator" <notice@...>, "Homebuyer Antitrust Litigation" <...>
    if s := re.search(r'^"?\s*([^"<]+?)\s+(?:Class Action\s+)?(?:Settlement|Litigation)\b[^"<]*"?\s*<', sender, re.I):
        if n := _good_name(s.group(1)):
            return n
    # "Haney v. Costa Del Mar, Inc. – Claim Submission Confirmation" -> the defendant
    if s := re.search(r"\bv(?:s)?\.\s+([A-Z][\w&'’ .-]{1,60}?)(?:,?\s+(?:Inc|LLC|Corp|Co)\b\.?)?\s*(?:[–—:-]|$)", subject):
        if n := _good_name(s.group(1)):
            return n
    for src in (subject, text):
        # "... from the T-Mobile Data Breach Settlement" names it best
        if s := re.search(r"\bthe ([A-Z][\w&'’.\- ]{2,60}?)\s+(?i:class action\s+)?(?i:settlement)\b", src):
            if n := _good_name(s.group(1)):
                return n
        if s := re.search(r"([A-Z][\w&'’.,\- ]{2,80}?)\s+(?i:class action\s+)?(?i:settlement)\b", src):
            if n := _good_name(re.sub(r"^(re|fwd?|your|the|important|action required|reminder)[:\s-]+", "",
                                      s.group(1).strip(), flags=re.I)):
                return n
    return None


SYSTEM = ("You read settlement emails for one person and say whether money is waiting for them and what they must do. "
          "Reply with JSON only.")


async def scan(db, messages: list[dict], log=print) -> list[dict]:
    """Classify and store payout emails. Returns the new or changed ones."""
    msgs = [{k: str(m.get(k, ""))[:4000 if k == "text" else 400] for k in
             ("account", "id", "from", "subject", "date", "text", "link", "folder")} for m in (messages or [])[:60]]
    if not msgs:
        return []
    facts = [classify(m) for m in msgs]
    if ai.enabled(db):
        for start in range(0, len(msgs), 6):
            chunk = msgs[start:start + 6]
            listing = "\n\n".join(f"[{i}] From: {m['from']}\nDate: {m['date']}\nSubject: {m['subject']}\n{m['text'][:2500]}"
                                  for i, m in enumerate(chunk, start))
            user = (f"{listing}\n\nFor each email return an object in a JSON array: "
                    '{"index": n, "kind": one of ' + str(list(LABELS)) + ', "settlement": "which settlement or company", '
                    '"amount": "$ amount or null", "expires": "YYYY-MM-DD the payment/link expires, or null", '
                    '"action": "what the person must do, one short sentence, or null"}. '
                    'Use kind "other" for emails not about a settlement payment or claim.')
            try:
                rows = await ai.ask_json(db, SYSTEM, user, max_tokens=1500)
            except ai.AIError as e:
                log(f"payout AI skipped: {e}")
                continue
            for r in rows if isinstance(rows, list) else []:
                i = r.get("index")
                if isinstance(i, int) and 0 <= i < len(msgs):
                    f = facts[i]
                    if r.get("kind") in LABELS:
                        f["kind"] = r["kind"]
                    for k in ("settlement", "amount", "action"):
                        if r.get(k) not in (None, "", "null"):
                            f[k] = str(r[k])[:200]
                    if parse_date(str(r.get("expires") or "")):
                        f["expires"] = parse_date(str(r["expires"]))
    out = []
    for m, f in zip(msgs, facts):
        if f["kind"] == "other":
            continue
        new = not db.q("SELECT 1 FROM payouts WHERE account=? AND message_id=?", (m["account"], m["id"]))
        db.x("""INSERT INTO payouts(account,message_id,link,sender,subject,date,folder,kind,settlement,amount,expires,action,status,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'new',?) ON CONFLICT(account,message_id) DO UPDATE SET
                kind=excluded.kind, settlement=excluded.settlement, amount=excluded.amount, expires=excluded.expires,
                action=excluded.action, link=excluded.link, folder=excluded.folder""",
             (m["account"], m["id"], m["link"] or None, m["from"], m["subject"], parse_date(m["date"]) or m["date"],
              m["folder"] or None, f["kind"], f.get("settlement"), f.get("amount"), f.get("expires"),
              f.get("action"), time.time()))
        if new:
            out.append(db.q("SELECT * FROM payouts WHERE account=? AND message_id=?", (m["account"], m["id"]))[0])
    return [_present(p) for p in out]


def _present(p: dict) -> dict:
    p["label"] = LABELS.get(p["kind"], "Settlement email")
    p["needs_action"] = p["kind"] in ACTION and p["status"] == "new"
    return p


def listing(db, include_done=False) -> list[dict]:
    rows = db.q(f"""SELECT * FROM payouts {'' if include_done else "WHERE status='new'"}
                    ORDER BY (kind IN ('virtual_card','payment_choice','deficiency','digital_payment','check')) DESC,
                    expires IS NULL, expires, date DESC LIMIT 300""")
    return [_present(p) for p in rows]
