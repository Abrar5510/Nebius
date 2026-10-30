"""[C] Extract: RGB-D + hands + FoundationPose -> object-centric demo."""

from __future__ import annotations

import json

from ..artifacts import (
    build_object_centric_demo,
    read_object_demo,
    validate_demo_arrays,
    write_object_demo,
)
from ..contracts import ContractError, validate_demo_meta, validate_task_spec
from ..storage import StorageNotFound
from ..util import iso_now
from .base import StageContext, StageError, StageHandler, StageResult


class ExtractStage(StageHandler):
    name = "extract"

    def run(self, ctx: StageContext) -> StageResult:
        task_spec = ctx.get_json(ctx.previous("understand")["task_spec"])
        try:
            validate_task_spec(task_spec)
        except ContractError as exc:
            raise StageError(str(exc)) from exc

        if ctx.settings.resolved_mode == "live":
            return self._live(ctx)

        arrays, meta = build_object_centric_demo(ctx.job.capture_id, task_spec)
        meta.update({"extractor": "mock 21-keypoint + metric pose synthesizer", "created_at": iso_now()})
        self._validate(meta, arrays)

        npz = ctx.local("demo_object_centric.npz")
        write_object_demo(npz, arrays, meta)
        npz_key = ctx.put_file("demo_object_centric.npz", npz)
        meta_key = ctx.put_json("demo_object_centric.json", meta)

        num_frames = meta["num_frames"]
        events = len(meta["events"])
        summary = (
            f"Synthesized a mock object-centric demo: {len(meta['objects'])} objects "
            f"across {num_frames} RGB-D frames with {events} contact events."
        )
        return StageResult(
            output={
                "demo": npz_key,
                "demo_meta": meta_key,
                "object_count": len(meta["objects"]),
                "num_frames": num_frames,
                "fps": meta["fps"],
                "events": meta["events"],
                "source": "mock",
            },
            summary=summary,
        )

    def _live(self, ctx: StageContext) -> StageResult:
        """Consume the output of an external FoundationPose/HaMeR extractor.

        Keeping this boundary explicit means the GPU-heavy extractor can run as its own
        Serverless Job and this stage never hides a missing model behind fake arrays.
        """
        base = f"captures/{ctx.job.capture_id}"
        try:
            npz_bytes = ctx.storage.get_bytes(f"{base}/demo_object_centric.npz")
            meta = ctx.get_json(f"{base}/demo_object_centric.json")
        except StorageNotFound as exc:
            raise StageError(
                "no object-centric demo found for this capture; run the FoundationPose/"
                "HaMeR extractor job first",
                retryable=False,
            ) from exc
        local_npz = ctx.local("demo_object_centric.npz")
        local_npz.write_bytes(npz_bytes)
        local_json = ctx.local("demo_object_centric.json")
        local_json.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
        arrays, _ = read_object_demo(local_npz)
        self._validate(meta, arrays)
        npz_key = ctx.put_file("demo_object_centric.npz", local_npz)
        meta_key = ctx.put_json("demo_object_centric.json", meta)
        return StageResult(
            output={
                "demo": npz_key,
                "demo_meta": meta_key,
                "object_count": len(meta["objects"]),
                "num_frames": meta["num_frames"],
                "fps": meta["fps"],
                "events": meta["events"],
                "source": "foundationpose+wilor",
            },
            summary=(
                f"Loaded {len(meta['objects'])} tracked objects across "
                f"{meta['num_frames']} frames from the RGB-D extractor."
            ),
        )

    @staticmethod
    def _validate(meta: dict, arrays: dict) -> None:
        try:
            validate_demo_meta(meta)
            validate_demo_arrays(arrays)
        except (ContractError, ValueError) as exc:
            raise StageError(f"object-centric demo failed validation: {exc}") from exc
