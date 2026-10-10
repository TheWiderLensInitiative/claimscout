"""Telling real settlement mail apart from marketing about settlements.

Newsletters like "LAST CHANCE: Claim a Share of $380M Settlement!" mention companies, settlements, breaches and
"no proof needed" all day long. They are never proof of a purchase and never a payout. Real proof comes from
the company itself (a receipt from equifax.com); real payouts come from the administrator and talk about
*your* claim.
"""
import re

# Senders that advertise settlements to everyone (newsletters, deal sites, claim-finder apps' marketing).
SETTLEMENT_NEWS = ["modemobile.com", "topclassactions.com", "classaction.org", "openclassactions.com",
                   "classactionrebates.com", "claimdepot.com", "lawsuitlegit.com", "classactionlawsuitsinthenews.com"]

_PROMO = re.compile(r"claim (a|your) share|last chance|final hours|don.t miss|\bfree\b|airdrop|\bearn\b|get cash|"
                    r"sweepstakes|\bwin (a|\$)|giveaway|\d+% off|\bsale\b|samples?\b|did you buy this|you could be owed|"
                    r"settlements? (today|this week|roundup)|new settlements|open settlements", re.I)
# Things only a message about one person's own claim says.
_PERSONAL = re.compile(r"your claim|claim (id|number|no\.?|#)|claimant (id|number)|unique (id|claim)|"
                       r"you (submitted|filed) a claim|your (settlement )?payment|payment for your claim|"
                       r"notice id|your (virtual |prepaid |digital )+(card|mastercard|visa|payment)|deficien", re.I)


def host(sender: str) -> str:
    m = re.search(r"@([\w.-]+)", sender or "")
    return m.group(1).lower() if m else ""


def _in(h: str, domains) -> bool:
    return any(h == d or h.endswith("." + d) for d in domains)


def is_marketing(m: dict) -> bool:
    if _in(host(m.get("from", "")), SETTLEMENT_NEWS):
        return True
    return bool(_PROMO.search(m.get("subject", "")))


def is_personal(m: dict) -> bool:
    return bool(_PERSONAL.search(f"{m.get('subject', '')}\n{m.get('text', '')}"))


def sender_is(m: dict, names: list[str], domains: list[str]) -> bool:
    """Did the company itself send it? Its domain, or its name in the sender's address or display name."""
    sender = (m.get("from") or "").lower()
    h = host(sender)
    if h and _in(h, [d.lower() for d in domains if d]):
        return True
    for n in names:
        for word in re.findall(r"[a-z0-9]{4,}", (n or "").lower()):
            if word not in {"settlement", "class", "action", "health", "group", "bank", "data", "breach", "company",
                            "services", "system", "systems", "center", "national", "american", "united", "insurance"} \
                    and word in sender:
                return True
    return False
