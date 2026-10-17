"""Near Miss pipeline CLI.

  nearmiss plan  footage/*.mp4 --city Karachi   # Nemotron reads each street, plans hazards (Tavily-grounded)
  nearmiss prep  footage/*.mp4 [--cut 5]        # writes Cosmos job inputs to out/cosmos/
  jobs/submit.sh <in-bucket> <out-bucket>       # Cosmos Predict 2.5 renders hazards on a Nebius GPU
  nearmiss label out/gen                        # stitch + Cosmos Reason answer keys, rejects bad renders
  nearmiss build --name karachi --title "..."   # writes web/packs/<name>/ for the player
"""

import argparse
import json
import shutil
from pathlib import Path

from . import media

OUT = Path("out")
ROOT = Path(__file__).resolve().parent.parent

# Used by `prep` when a clip has no plan yet: the day-1 go/no-go needs only Cosmos, no other model.
GENERIC = [
    {"hazard_type": "child runs out", "clue": "a ball rolls out from behind a parked vehicle",
     "cosmos_prompt": "The dashcam keeps driving forward along the same street at the same steady speed. A red ball "
     "rolls out from behind a parked vehicle on the left, and a moment later a small boy in a white shirt runs out "
     "after it, straight into the path of the camera. Natural daylight, realistic handheld dashcam footage."},
    {"hazard_type": "motorbike cuts across", "clue": "a motorbike's front wheel nosing out of a side lane",
     "cosmos_prompt": "The dashcam keeps driving forward along the same street at the same steady speed. A man on a "
     "small motorbike emerges from a narrow side lane on the right without slowing and cuts diagonally across the "
     "road in front of the camera. Natural daylight, realistic handheld dashcam footage."},
    {"hazard_type": "vehicle pulls out", "clue": "a parked car's wheels turning towards the lane",
     "cosmos_prompt": "The dashcam keeps driving forward along the same street at the same steady speed. A parked "
     "white car ahead on the left suddenly pulls out from the kerb into the camera's lane without indicating. "
     "Natural daylight, realistic handheld dashcam footage."},
]


def _plan_path(clip: Path) -> Path:
    return OUT / "plan" / f"{clip.stem}.json"


def plan(a):
    from . import models

    for clip in map(Path, a.footage):
        scene = models.read_scene(media.keyframes(clip))
        hazards = models.direct(scene, a.city, n=a.n)
        _plan_path(clip).parent.mkdir(parents=True, exist_ok=True)
        _plan_path(clip).write_text(json.dumps({"scene": scene, "hazards": hazards, "city": a.city}, indent=2))
        print(f"{clip.name}: " + ", ".join(h["hazard_type"] for h in hazards))


def prep(a):
    dst = OUT / "cosmos"
    dst.mkdir(parents=True, exist_ok=True)
    meta = {}
    for clip in map(Path, a.footage):
        lead = dst / f"{clip.stem}_lead.mp4"
        media.normalize(clip, lead, start=a.start, length=a.cut)
        p = _plan_path(clip)
        hazards = json.loads(p.read_text())["hazards"] if p.exists() else GENERIC
        for i, h in enumerate(hazards):
            name = f"{clip.stem}_h{i}"
            sample = {"inference_type": "video2world", "name": name, "input_path": lead.name,
                      "prompt": h["cosmos_prompt"], "seed": i}
            (dst / f"{name}.json").write_text(json.dumps(sample, indent=2))
            meta[name] = {**h, "lead": lead.name, "lead_s": media.duration(lead)}
    shutil.copy(ROOT / "jobs" / "cosmos_generate.sh", dst)
    (OUT / "samples.json").write_text(json.dumps(meta, indent=2))
    print(f"{len(meta)} samples in {dst}/ -> upload that folder to your input bucket, then run jobs/submit.sh")


def label(a):
    from . import models

    meta = json.loads((OUT / "samples.json").read_text())
    (OUT / "clips").mkdir(exist_ok=True)
    results = {}
    for name, m in meta.items():
        gen = Path(a.gen_dir) / f"{name}.mp4"
        if not gen.exists():
            print(f"skip {name}: not generated")
            continue
        clip = OUT / "clips" / f"{name}.mp4"
        media.stitch(OUT / "cosmos" / m["lead"], gen, clip)
        key = models.label(clip.read_bytes(), m["lead_s"], m["hazard_type"])
        key["keep"] = bool(key.get("hazard_visible") and key.get("physically_plausible")
                           and key.get("onset_s", 0) >= m["lead_s"] - 0.5)
        results[name] = {**m, **key}
        print(f"{name}: {'KEEP' if key['keep'] else 'reject'}  onset={key.get('onset_s')}  {key.get('artifacts')}")
    (OUT / "labels.json").write_text(json.dumps(results, indent=2))


def build(a):
    labels = json.loads((OUT / "labels.json").read_text())
    dst = ROOT / "web" / "packs" / a.name
    dst.mkdir(parents=True, exist_ok=True)
    clips = []
    for name, l in labels.items():
        if not l["keep"]:
            continue
        shutil.copy(OUT / "clips" / f"{name}.mp4", dst / f"{name}.mp4")
        clips.append({k: l.get(k) for k in ("hazard_type", "clue", "why_here", "description", "clue_s", "onset_s",
                                            "lead_s", "sources")} | {"src": f"{name}.mp4"})
    (dst / "pack.json").write_text(json.dumps({"id": a.name, "title": a.title, "city": a.city, "clips": clips}, indent=2))
    index = ROOT / "web" / "packs" / "index.json"
    packs = [p for p in (json.loads(index.read_text()) if index.exists() else []) if p["id"] != a.name]
    index.write_text(json.dumps(packs + [{"id": a.name, "title": a.title, "city": a.city, "n": len(clips)}], indent=2))
    print(f"{len(clips)} clips -> {dst}")


def main():
    p = argparse.ArgumentParser(prog="nearmiss", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(required=True)
    s = sub.add_parser("plan"); s.add_argument("footage", nargs="+"); s.add_argument("--city", required=True)
    s.add_argument("-n", type=int, default=3); s.set_defaults(fn=plan)
    s = sub.add_parser("prep"); s.add_argument("footage", nargs="+"); s.add_argument("--start", type=float, default=0)
    s.add_argument("--cut", type=float, default=5, help="seconds of real lead-in before the hazard"); s.set_defaults(fn=prep)
    s = sub.add_parser("label"); s.add_argument("gen_dir"); s.set_defaults(fn=label)
    s = sub.add_parser("build"); s.add_argument("--name", required=True); s.add_argument("--title", required=True)
    s.add_argument("--city", default=""); s.set_defaults(fn=build)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
