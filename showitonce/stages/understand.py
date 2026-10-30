"""[A] Understand: narration + video -> a machine-checkable task spec."""

from __future__ import annotations

import json
from typing import Any

from ..clients import ClientError
from ..contracts import (
    TASK_SPEC_SCHEMA,
    ContractError,
    validate_task_spec,
)
from ..util import iso_now
from .base import StageContext, StageError, StageHandler, StageResult

SYSTEM = (
    "You are the task compiler for a robot-learning system. You turn one human "
    "demonstration into a precise, simulation-checkable task specification. "
    "Return only valid JSON. Never invent objects that are not in the capture."
)


class UnderstandStage(StageHandler):
    name = "understand"

    def run(self, ctx: StageContext) -> StageResult:
        capture = ctx.capture()
        narration = capture.get("narration", "").strip()
        transcript = narration
        video_analysis: dict[str, Any] | None = None
        models: list[str] = []

        if ctx.settings.resolved_mode == "live":
            transcript = self._live_transcript(ctx, capture) or narration
            video_analysis = self._live_video_analysis(ctx)
            spec = self._live_task_spec(ctx, capture, transcript, video_analysis)
            models = []
            if ctx.settings.parakeet_url:
                models.append("parakeet")
            if video_analysis:
                models.append("cosmos-reason-2")
            models.append("nemotron-ultra")
        else:
            spec = self._mock_task_spec(capture, transcript)
            models = ["mock"]

        try:
            validate_task_spec(spec)
        except ContractError as exc:
            raise StageError(str(exc)) from exc

        understanding = {
            "schema_version": "showitonce.understanding/v1",
            "transcript": transcript,
            "video_analysis": video_analysis,
            "task_spec": spec,
            "models": models,
            "created_at": iso_now(),
            "synthetic": ctx.settings.resolved_mode != "live",
        }

        transcript_key = ctx.put_text("transcript.txt", transcript)
        understanding_key = ctx.put_json("understanding.json", understanding)
        spec_key = ctx.put_json("task_spec.json", spec)

        summary = (
            f'{"Mock-compiled" if ctx.settings.resolved_mode != "live" else "Understood"} '
            f'"{spec["instruction"]}" as {len(spec["subtasks"])} steps '
            f'with {len(spec["success_predicates"])} success checks.'
        )
        return StageResult(
            output={
                "transcript": transcript_key,
                "understanding": understanding_key,
                "task_spec": spec_key,
                "task_name": spec["task_name"],
                "instruction": spec["instruction"],
                "objects": [obj["name"] for obj in spec["objects"]],
                "subtask_count": len(spec["subtasks"]),
                "success_predicate_count": len(spec["success_predicates"]),
                "models": models,
            },
            summary=summary,
        )

    # -- live adapters ----------------------------------------------------
    def _live_transcript(self, ctx: StageContext, capture: dict[str, Any]) -> str:
        audio_key = capture.get("files", {}).get("audio")
        if not audio_key or not ctx.settings.parakeet_url:
            return capture.get("narration", "")
        try:
            return ctx.clients.parakeet.transcribe(ctx.storage.get_bytes(audio_key))
        except (ClientError, OSError) as exc:
            raise StageError(f"Parakeet transcription failed: {exc}", retryable=True) from exc

    def _live_video_analysis(self, ctx: StageContext) -> dict[str, Any] | None:
        if not ctx.settings.cosmos_reason_url:
            return None
        frame_keys = [
            key
            for key in ctx.storage.list(f"captures/{ctx.job.capture_id}/frames/")
            if key.lower().endswith((".jpg", ".jpeg", ".png"))
        ][:6]
        if not frame_keys:
            return None
        frames = [ctx.storage.get_bytes(key) for key in frame_keys]
        prompt = (
            "Watch the demonstration. Return JSON with: objects (name, material, "
            "role), steps (action, target, start_s, end_s), physical_constraints, "
            "and a visual success condition. Actions must be one of reach, grasp, "
            "transport, place, release, pour, wipe, fold. Be literal; do not infer "
            "objects that are not visible."
        )
        try:
            return ctx.clients.cosmos_reason.judge(frames, prompt)
        except ClientError as exc:
            raise StageError(f"Cosmos Reason 2 video analysis failed: {exc}", retryable=True) from exc

    def _live_task_spec(
        self,
        ctx: StageContext,
        capture: dict[str, Any],
        transcript: str,
        video_analysis: dict[str, Any] | None,
    ) -> dict[str, Any]:
        prompt = f"""Compile this demonstration into a task spec.

CAPTURE METADATA:
{json.dumps(capture, indent=2, sort_keys=True)}

TRANSCRIPT:
{transcript}

VIDEO ANALYSIS FROM COSMOS REASON 2:
{json.dumps(video_analysis, indent=2, sort_keys=True) if video_analysis else "not available"}

Return exactly one JSON object with these fields:
- schema_version: "{TASK_SPEC_SCHEMA}"
- task_name: short snake_case name
- instruction: one imperative sentence
- objects: list of {{id, name, role, material, mass_kg, friction, dimensions_m}}
- subtasks: list of {{id, action, target, start_s, end_s}}
- success_predicates: list of {{type, ...}} where type is one of object_on_surface,
  object_inside, object_near, object_upright, object_rotated, gripper_released, custom
- constraints: list of {{type, object, ...}} where type is one of upright, max_speed,
  max_force, keep_clear, grasp_at, avoid_collision, custom
- failure_modes: list of short strings
- source: {{transcript, video_model, reasoning_model}}

Every object referenced by a predicate must also appear in objects.
"""
        try:
            spec = ctx.clients.token_factory.chat_json(prompt, tier="reason", system=SYSTEM)
        except ClientError as exc:
            raise StageError(f"Nemotron Ultra task spec failed: {exc}", retryable=True) from exc
        if spec.get("schema_version") != TASK_SPEC_SCHEMA:
            spec["schema_version"] = TASK_SPEC_SCHEMA
        spec.setdefault("source", {})
        spec["source"].update(
            {
                "transcript": transcript,
                "reasoning_model": "nemotron-ultra",
                "video_model": "cosmos-reason-2" if video_analysis else "none",
            }
        )
        return spec

    # -- deterministic compile used by mock mode and tests ----------------
    def _mock_task_spec(self, capture: dict[str, Any], transcript: str) -> dict[str, Any]:
        raw_objects = capture.get("objects") or []
        objects: list[dict[str, Any]] = []
        for index, item in enumerate(raw_objects):
            if isinstance(item, str):
                item = {"name": item}
            role = item.get("role") or ("target" if index == 0 else "support")
            objects.append(
                {
                    "id": item.get("id") or f"obj_{index + 1}",
                    "name": item["name"],
                    "role": role,
                    "material": item.get("material", "plastic"),
                    "mass_kg": float(item.get("mass_kg", 0.28 if role == "target" else 1.0)),
                    "friction": float(item.get("friction", 0.55)),
                    "dimensions_m": item.get(
                        "dimensions_m", [0.08, 0.08, 0.10] if role == "target" else [0.4, 0.4, 0.02]
                    ),
                }
            )
        if not objects:
            objects = [
                {
                    "id": "obj_1",
                    "name": "target object",
                    "role": "target",
                    "material": "plastic",
                    "mass_kg": 0.28,
                    "friction": 0.55,
                    "dimensions_m": [0.08, 0.08, 0.10],
                }
            ]
        target = next((obj for obj in objects if obj["role"] == "target"), objects[0])
        surface = next(
            (obj for obj in objects if obj["role"] in {"surface", "receptacle", "support"}),
            objects[-1],
        )
        instruction = capture.get("task_name", "pick up the object and place it down")
        if not instruction.startswith(("Place", "Pick", "Put", "Move")):
            instruction = f"Place the {target['name']} on the {surface['name']}"
        spec = {
            "schema_version": TASK_SPEC_SCHEMA,
            "task_name": capture.get("skill") or "place_object",
            "instruction": instruction,
            "objects": objects,
            "subtasks": [
                {"id": "reach", "action": "reach", "target": target["name"], "start_s": 0.0, "end_s": 2.0},
                {"id": "grasp", "action": "grasp", "target": target["name"], "start_s": 2.0, "end_s": 2.5},
                {"id": "transport", "action": "transport", "target": target["name"], "start_s": 2.5, "end_s": 7.0},
                {"id": "place", "action": "place", "target": surface["name"], "start_s": 7.0, "end_s": 8.5},
                {"id": "release", "action": "release", "target": target["name"], "start_s": 8.5, "end_s": 9.0},
            ],
            "success_predicates": [
                {
                    "type": "object_on_surface",
                    "object": target["name"],
                    "surface": surface["name"],
                    "threshold_m": 0.06,
                },
                {
                    "type": "object_upright",
                    "object": target["name"],
                    "up_axis": "+Z",
                    "tolerance_deg": 20,
                },
                {"type": "gripper_released", "object": target["name"]},
            ],
            "constraints": [
                {"type": "upright", "object": target["name"], "max_tilt_deg": 20},
                {"type": "max_speed", "value_m_s": 0.5},
                {"type": "avoid_collision", "object": target["name"]},
            ],
            "failure_modes": [
                f"drops or tips over the {target['name']}",
                f"misses the {surface['name']}",
                "collides with another object",
                "stops before releasing the object",
            ],
            "source": {
                "transcript": transcript,
                "reasoning_model": "mock-task-compiler",
                "video_model": "mock",
            },
        }
        return spec
