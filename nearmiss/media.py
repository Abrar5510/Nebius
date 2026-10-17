"""ffmpeg helpers. Everything is normalised to Cosmos Predict's native 1280x720 @ 16 fps
so real lead-ins and generated continuations concatenate without a visible seam."""

import base64
import json
import subprocess
import tempfile
from pathlib import Path

FPS = 16
SIZE = "1280:720"
COND_FRAMES = 5  # Cosmos video2world conditions on the last 4*(2-1)+1 frames of its input


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *map(str, args)], check=True)


def duration(path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def normalize(src, dst, start=0.0, length=None):
    """Crop/scale to 16:9 720p, 16 fps, no audio. Optional trim."""
    trim = ["-ss", start] + (["-t", length] if length else [])
    vf = f"scale={SIZE}:force_original_aspect_ratio=increase,crop={SIZE},fps={FPS}"
    _ff(*trim, "-i", src, "-vf", vf, "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", dst)


def keyframes(src, n=4) -> list[bytes]:
    """n evenly spaced JPEG frames, for the scene-reading model."""
    d = duration(src)
    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            out = Path(tmp) / f"{i}.jpg"
            _ff("-ss", d * (i + 0.5) / n, "-i", src, "-frames:v", 1, "-vf", "scale=960:-2", out)
            frames.append(out.read_bytes())
    return frames


def stitch(lead_in, generated, dst):
    """Real lead-in + generated continuation, dropping the generated copy of the conditioning frames."""
    _ff(
        "-i", lead_in, "-i", generated, "-filter_complex",
        f"[1:v]trim=start_frame={COND_FRAMES},setpts=PTS-STARTPTS,fps={FPS},scale={SIZE}[g];"
        f"[0:v][g]concat=n=2:v=1:a=0[v]",
        "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", "-movflags", "+faststart", dst,
    )


def data_url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode()
