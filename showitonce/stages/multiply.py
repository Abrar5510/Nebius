"""[F] Multiply: one verified demo -> Mimic + Dreams + Transfer + Reason filter."""

from __future__ import annotations

from ..util import iso_now
from .base import StageContext, StageError, StageHandler, StageResult


class MultiplyStage(StageHandler):
    name = "multiply"

    def run(self, ctx: StageContext) -> StageResult:
        if ctx.settings.resolved_mode == "live":
            raise StageError(
                "live data multiplication needs the Isaac Lab Mimic / Cosmos generation "
                "jobs, which are not implemented in this Phase 1 build; run mock mode "
                "or supply an external multiply manifest",
                retryable=False,
            )
        task_spec = ctx.get_json(ctx.previous("understand")["task_spec"])
        verified_demo = ctx.previous("verify")["verified_demo"]
        task = task_spec["task_name"]

        mimic = {
            "schema_version": "showitonce.mimic/v1",
            "task_name": task,
            "source_demo": verified_demo,
            "generator": "Isaac Lab Mimic + SkillGen",
            "requested": 1000,
            "accepted": 1000,
            "axes": {
                "object_pose": {"range_cm": 12, "samples": 1000},
                "object_instance": {"classes": 4, "samples": 250},
                "distractors": {"min": 0, "max": 3},
                "lighting": {"presets": 6},
            },
            "samples": [
                {
                    "id": f"mimic_{index:04d}",
                    "seed": 1000 + index,
                    "object_pose_jitter_cm": round(1.0 + (index % 12), 2),
                    "instance": ["mug", "cup", "beaker", "tumbler"][index % 4],
                    "distractors": index % 4,
                }
                for index in range(8)
            ],
            "created_at": iso_now(),
        }
        dreams = {
            "schema_version": "showitonce.dreams/v1",
            "task_name": task,
            "model": "Cosmos Predict 2.5 (GR00T-Dreams)",
            "requested": 64,
            "accepted": 58,
            "inverse_dynamics": "GR00T action head",
            "prompts": [
                "the same task in a small apartment kitchen",
                "the same task on a wooden dining table",
                "the same task under warm evening light",
                "the same task with a different mug and coaster",
            ],
            "samples": [
                {
                    "id": f"dream_{index:03d}",
                    "seed": 2000 + index,
                    "environment": ["kitchen", "dining", "office", "studio"][index % 4],
                    "lighting": ["day", "warm", "overcast", "night"][index % 4],
                }
                for index in range(4)
            ],
            "created_at": iso_now(),
        }
        transfer = {
            "schema_version": "showitonce.transfer/v1",
            "task_name": task,
            "model": "Cosmos Transfer 2.5",
            "requested": 1000,
            "accepted": 984,
            "control_maps": ["depth", "segmentation", "edges"],
            "style": "room-matched to the capture",
            "samples": [
                {
                    "id": f"transfer_{index:04d}",
                    "seed": 3000 + index,
                    "style": ["capture-room", "bright", "overcast", "warm"][index % 4],
                    "texture_set": ["ceramic", "wood", "stone", "fabric"][index % 4],
                }
                for index in range(8)
            ],
            "created_at": iso_now(),
        }
        reason_filter = {
            "schema_version": "showitonce.reason_filter/v1",
            "model": "Cosmos Reason 2",
            "reviewed": 2064,
            "accepted": 2042,
            "rejected": 22,
            "rejection_reasons": {
                "object_warping": 9,
                "impossible_physics": 6,
                "task_not_completed": 5,
                "hand_or_robot_artifact": 2,
            },
            "kept": {
                "mimic": 1000,
                "dreams": 58,
                "transfer": 984,
            },
            "created_at": iso_now(),
        }
        manifest = {
            "schema_version": "showitonce.multiply/v1",
            "task_name": task,
            "verified_demo": verified_demo,
            "synthetic": True,
            "counts": {
                "seed_demos": 1,
                "mimic": 1000,
                "dreams": 58,
                "transfer": 984,
                "reviewed": 2064,
                "training_clips": 2042,
                "rejected": 22,
            },
            "multiplier": 2042,
            "models": {
                "mimic": "Isaac Lab Mimic / SkillGen",
                "dreams": "Cosmos Predict 2.5 (GR00T-Dreams)",
                "transfer": "Cosmos Transfer 2.5",
                "filter": "Cosmos Reason 2",
            },
            "created_at": iso_now(),
        }
        keys = {
            "manifest": ctx.put_json("multiply.json", manifest),
            "mimic": ctx.put_json("mimic_manifest.json", mimic),
            "dreams": ctx.put_json("dreams_manifest.json", dreams),
            "transfer": ctx.put_json("transfer_manifest.json", transfer),
            "reason_filter": ctx.put_json("reason_filter.json", reason_filter),
        }
        summary = (
            "Mock-multiplied one verified demo into 2,042 synthetic training clips: "
            "1,000 Mimic, 58 Dreams and 984 room-matched Transfer variants."
        )
        return StageResult(
            output={
                **keys,
                "counts": manifest["counts"],
                "multiplier": manifest["multiplier"],
                "models": manifest["models"],
            },
            summary=summary,
        )
