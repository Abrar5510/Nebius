"""Starter: a runtime call to Nebius Token Factory with NVIDIA Nemotron.

Fast tier (Nano/Super) for everyday calls, Ultra for heavy reasoning, as the Track 2 brief asks.
Model ids are resolved from Token Factory's live catalog, so they never go stale.

    python app.py check              # preflight: key, catalog, models resolve, one live call
    python app.py models             # list NVIDIA models on Token Factory
    python app.py ask "question"     # fast tier
    python app.py think "question"   # reasoning tier
"""

import os
import sys
from functools import cache
from pathlib import Path

from openai import OpenAI

TOKEN_FACTORY = "https://api.tokenfactory.nebius.com/v1/"
FAST = ("nano", "super")  # first tier found wins
REASON = ("ultra", "super")

ENV = Path(__file__).with_name(".env")
for line in ENV.read_text().splitlines() if ENV.exists() else []:
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


@cache
def client() -> OpenAI:
    key = os.environ.get("NEBIUS_API_KEY") or sys.exit("NEBIUS_API_KEY missing: copy .env.example to .env")
    return OpenAI(base_url=TOKEN_FACTORY, api_key=key)


@cache
def nvidia_models() -> list[str]:
    return sorted(m.id for m in client().models.list() if m.id.lower().startswith("nvidia/"))


def pick(ids: list[str], tiers: tuple[str, ...]) -> str:
    """Shortest Nemotron id matching the first tier that exists (shortest = base, not a variant)."""
    for tier in tiers:
        hits = [i for i in ids if "nemotron" in i.lower() and tier in i.lower()]
        if hits:
            return min(hits, key=len)
    raise SystemExit(f"No Nemotron model for tiers {tiers}. Available: {ids}")


def ask(prompt: str, tiers=FAST) -> str:
    r = client().chat.completions.create(
        model=pick(nvidia_models(), tiers), messages=[{"role": "user", "content": prompt}]
    )
    return r.choices[0].message.content


def main(cmd="check", *args):
    if cmd == "models":
        print("\n".join(nvidia_models()))
    elif cmd in ("ask", "think"):
        print(ask(" ".join(args), FAST if cmd == "ask" else REASON))
    elif cmd == "check":
        ids = nvidia_models()
        print(f"Token Factory OK, {len(ids)} NVIDIA models")
        print("fast  :", pick(ids, FAST))
        print("reason:", pick(ids, REASON))
        print("live  :", ask("Reply with exactly: pong")[:80])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    assert pick(["nvidia/Nemotron-3-Nano-30B", "nvidia/Nemotron-3-Nano-30B-FP8", "meta/x"], FAST) == "nvidia/Nemotron-3-Nano-30B"
    assert pick(["nvidia/Nemotron-3-Super"], REASON) == "nvidia/Nemotron-3-Super"  # falls back when no Ultra
    main(*sys.argv[1:])
