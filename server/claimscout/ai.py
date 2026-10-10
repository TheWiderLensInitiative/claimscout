"""Any OpenAI-compatible chat endpoint: a model on this PC (llama.cpp, Ollama, LM Studio) or OpenRouter.

Settings live in the DB under "ai": {provider, base_url, model, api_key}. provider "off" disables AI;
everything still works on keyword rules.
"""
import json
import re

import httpx

PRESETS = {
    "local": {"base_url": "http://127.0.0.1:8080/v1", "label": "Model on this PC (llama.cpp / Ollama / LM Studio)"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "label": "OpenRouter (cloud; free models available)"},
    "off": {"base_url": "", "label": "No AI (keyword rules only)"},
}
DEFAULT = {"provider": "off", "base_url": "", "model": "", "api_key": ""}


class AIError(Exception):
    pass


def settings(db) -> dict:
    return {**DEFAULT, **(db.get("ai") or {})}


def public_settings(db) -> dict:
    s = settings(db)
    return {**s, "api_key": "set" if s["api_key"] else "", "cloud": s["provider"] == "openrouter"}


def enabled(db) -> bool:
    s = settings(db)
    return s["provider"] != "off" and bool(s["base_url"])


async def chat(db, system: str, user: str, max_tokens=900, client=None) -> str:
    s = settings(db)
    if not enabled(db):
        raise AIError("AI is off")
    headers = {"Content-Type": "application/json"}
    if s["api_key"]:
        headers["Authorization"] = f"Bearer {s['api_key']}"
    if s["provider"] == "openrouter":
        headers |= {"HTTP-Referer": "https://github.com/TheWiderLensInitiative/claimscout", "X-Title": "ClaimScout"}
    body = {"model": s["model"] or "default", "temperature": 0.1, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    own = client is None
    client = client or httpx.AsyncClient(timeout=180)
    try:
        r = await client.post(s["base_url"].rstrip("/") + "/chat/completions", json=body, headers=headers)
    except httpx.HTTPError as e:
        raise AIError(f"can't reach the model at {s['base_url']}: {e}") from e
    finally:
        if own:
            await client.aclose()
    if r.status_code >= 400:
        raise AIError(f"model said {r.status_code}: {r.text[:300]}")
    try:
        return r.json()["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, ValueError) as e:
        raise AIError(f"unexpected reply: {r.text[:300]}") from e


def parse_json(text: str):
    """The first JSON object or array in a model reply (models wrap it in prose or ``` fences)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    # Try each { or [ in order, so an array of objects is returned whole rather than its first object.
    for start in (i for i, c in enumerate(text) if c in "{["):
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c in "{[":
                depth += 1
            elif c in "}]":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except ValueError:
                        break
    raise AIError("no JSON in the model's reply")


async def ask_json(db, system, user, max_tokens=900):
    return parse_json(await chat(db, system, user, max_tokens))


async def free_openrouter_models(client=None) -> list[str]:
    """OpenRouter models that cost nothing per token (rate-limited by OpenRouter)."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=30)
    try:
        r = await client.get("https://openrouter.ai/api/v1/models")
        r.raise_for_status()
        models = r.json().get("data", [])
    finally:
        if own:
            await client.aclose()
    def free(m):
        p = m.get("pricing") or {}
        return str(p.get("prompt", "1")) in ("0", "0.0") and str(p.get("completion", "1")) in ("0", "0.0")
    return sorted(m["id"] for m in models if free(m))
