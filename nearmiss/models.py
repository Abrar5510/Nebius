"""Model calls. Nemotron runs on Nebius Token Factory; Cosmos Reason 2 runs on our own
Nebius Serverless Endpoint (vLLM, OpenAI-compatible); Tavily grounds hazards in local crash data."""

import json
import os
import re
import urllib.request
from functools import cache

from openai import OpenAI

from . import media

TOKEN_FACTORY = "https://api.tokenfactory.nebius.com/v1/"


@cache
def token_factory() -> OpenAI:
    return OpenAI(base_url=TOKEN_FACTORY, api_key=os.environ["NEBIUS_API_KEY"])


@cache
def model(name: str) -> str:
    """Resolve a model id by substring from Token Factory's live catalog, so ids never go stale."""
    ids = [m.id for m in token_factory().models.list()]
    hits = [i for i in ids if name in i.lower()]
    if not hits:
        raise SystemExit(f"No Token Factory model matching {name!r}. Available: {ids}")
    return min(hits, key=len)


def _json(text: str):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    m = re.search(r"[\[{].*[\]}]", text, re.S)
    if not m:
        raise ValueError(f"model returned no JSON: {text[:300]}")
    return json.loads(m.group(0))


def ask_json(client, model_id, prompt, images=(), video=None, **extra):
    content = [{"type": "text", "text": prompt}]
    content += [{"type": "image_url", "image_url": {"url": media.data_url(i, "image/jpeg")}} for i in images]
    if video:
        content.append({"type": "video_url", "video_url": {"url": media.data_url(video, "video/mp4")}})
    r = client.chat.completions.create(
        model=model_id, messages=[{"role": "user", "content": content}], temperature=0.4, **extra
    )
    return _json(r.choices[0].message.content)


def tavily(query: str, n=5) -> list[dict]:
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=json.dumps({"query": query, "max_results": n, "search_depth": "advanced"}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return [{"title": x["title"], "url": x["url"], "content": x["content"][:600]} for x in json.load(r)["results"]]


SCENE_PROMPT = """These are 4 frames, in time order, from a forward-facing dashcam on a real street.
Describe what a hazard-perception examiner needs: places where something could appear with little warning.
Return ONLY JSON:
{"road_type": str, "traffic_side": "left"|"right", "speed_context": str,
 "occluders": [{"what": str, "side": "left"|"right"|"ahead"}],
 "side_openings": [{"what": str, "side": "left"|"right"}],
 "road_users": [str], "notable": [str]}"""


def read_scene(frames: list[bytes]) -> dict:
    """Nemotron 3 Nano Omni reads the real street: occluders, side lanes, who uses this road."""
    return ask_json(token_factory(), model("nano-omni"), SCENE_PROMPT, images=frames)


DIRECTOR_PROMPT = """You design hazard-perception test clips, like the UK DVSA test, but for this exact street in {city}.
The clip continues from the real dashcam footage; a world model (NVIDIA Cosmos Predict) will render your scene.

Street (read from the footage): {scene}

What actually causes crashes here (web research): {research}

Write {n} different developing hazards that are realistic FOR THIS STREET: each must use a real occluder,
side opening or road user from the street description, and match local crash causes. Vary the hazard types.
Each cosmos_prompt is 3-5 sentences, present tense, describing ONLY what the camera sees as the drive continues
forward at the same speed: who appears, from where, how it develops. Mention concrete visual details
(clothing colour, vehicle type). No text overlays, no collisions shown, no gore.
Return ONLY JSON: [{{"hazard_type": str, "cosmos_prompt": str,
  "clue": "the first visible sign a skilled driver would notice", "why_here": "one sentence tying it to this street/city, cite the research"}}]"""


def direct(scene: dict, city: str, n=3) -> list[dict]:
    """Nemotron 3 Ultra plans hazards grounded in the street and in local crash causes (Tavily)."""
    research = tavily(f"most common causes of road crashes involving pedestrians and motorcyclists in {city}")
    prompt = DIRECTOR_PROMPT.format(city=city, scene=json.dumps(scene), research=json.dumps(research), n=n)
    plans = ask_json(token_factory(), model("ultra"), prompt)
    for p in plans:
        p["sources"] = [r["url"] for r in research]
    return plans


LABEL_PROMPT = """This is forward-facing dashcam video. The first {lead:.1f} s are real; the rest was generated.
The intended hazard: {hazard}
Watch it as a driving examiner. Answer ONLY JSON:
{{"hazard_visible": bool, "description": str,
  "clue_s": float  (first moment a skilled driver could notice the hazard developing),
  "onset_s": float (moment the driver would need to slow or steer),
  "physically_plausible": bool, "artifacts": str (warping, melting, teleporting objects, or "none")}}"""


@cache
def cosmos_reason() -> OpenAI:
    return OpenAI(base_url=os.environ["COSMOS_REASON_URL"].rstrip("/") + "/v1", api_key=os.getenv("COSMOS_REASON_KEY", "none"))


def label(video: bytes, lead_s: float, hazard: str) -> dict:
    """Cosmos Reason 2 watches the stitched clip: writes the answer key and rejects implausible renders."""
    c = cosmos_reason()
    model_id = c.models.list().data[0].id
    return ask_json(
        c, model_id, LABEL_PROMPT.format(lead=lead_s, hazard=hazard), video=video,
        extra_body={"mm_processor_kwargs": {"fps": 4}}, max_tokens=4096,
    )
