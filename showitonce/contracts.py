"""Versioned data contracts that every stage reads and writes.

These are intentionally plain dictionaries with explicit validators: the same JSON
crosses the phone, the orchestrator, serverless jobs and the dashboard, so the wire
format is the source of truth rather than a Python class.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CAPTURE_SCHEMA = "showitonce.capture/v1"
TASK_SPEC_SCHEMA = "showitonce.task_spec/v1"
DEMO_SCHEMA = "showitonce.demo_object_centric/v1"
ROBOT_DEMO_SCHEMA = "showitonce.robot_demo/v1"
EVAL_SCHEMA = "showitonce.eval/v1"
SKILL_SCHEMA = "showitonce.skill/v1"

JOB_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled"}
STAGE_STATUSES = {"pending", "running", "succeeded", "failed", "skipped"}

SUBTASK_ACTIONS = {
    "reach",
    "grasp",
    "transport",
    "place",
    "release",
    "push",
    "pull",
    "open",
    "close",
    "pour",
    "wipe",
    "fold",
    "stack",
    "press",
    "rotate",
}
PREDICATE_TYPES = {
    "object_on_surface",
    "object_inside",
    "object_near",
    "object_upright",
    "object_rotated",
    "gripper_released",
    "all_objects_moved",
    "custom",
}
CONSTRAINT_TYPES = {
    "upright",
    "max_speed",
    "max_force",
    "keep_clear",
    "grasp_at",
    "avoid_collision",
    "custom",
}


class ContractError(ValueError):
    """Raised when a stage emits an artifact that does not match its contract."""

    def __init__(self, artifact: str, errors: list[str]):
        self.artifact = artifact
        self.errors = errors
        super().__init__(f"{artifact} failed validation: " + "; ".join(errors))


@dataclass(frozen=True)
class StageDef:
    name: str
    letter: str
    title: str
    description: str


STAGES: tuple[StageDef, ...] = (
    StageDef("understand", "A", "Understand", "Narration and video become a task spec."),
    StageDef("reconstruct", "B", "Reconstruct", "The room becomes a physics-ready digital twin."),
    StageDef("extract", "C", "Extract motion", "Hands and objects become an object-centric demo."),
    StageDef("retarget", "D", "Retarget", "The demo becomes motion for this robot."),
    StageDef("verify", "E", "Verify", "The twin proves the motion works before training."),
    StageDef("multiply", "F", "Multiply", "Mimic, Dreams and Transfer grow one demo into thousands."),
    StageDef("train", "G", "Train", "GR00T N1.6 learns a per-skill LoRA adapter."),
    StageDef("evaluate", "H", "Evaluate", "Isaac Lab-Arena measures every data addition."),
    StageDef("deploy", "I", "Deploy", "The skill is packaged with four safety layers."),
    StageDef("library", "K", "Library", "The skill is versioned for another robot and room."),
)
STAGE_NAMES: tuple[str, ...] = tuple(s.name for s in STAGES)
STAGE_BY_NAME = {s.name: s for s in STAGES}
STAGE_LETTERS = {s.name: s.letter for s in STAGES}


def validate_capture(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if data.get("schema_version") != CAPTURE_SCHEMA:
        errors.append(f"schema_version must be {CAPTURE_SCHEMA}")
    for key in ("capture_id", "task_name", "narration", "room", "objects"):
        if not data.get(key):
            errors.append(f"missing required field: {key}")
    if not isinstance(data.get("objects"), list):
        errors.append("objects must be a list")
    if not isinstance(data.get("room"), dict):
        errors.append("room must be an object")
    files = data.get("files", {})
    if not isinstance(files, dict):
        errors.append("files must be an object mapping kind -> object key")
    duration = data.get("duration_s", 0)
    if not isinstance(duration, (int, float)) or duration < 0:
        errors.append("duration_s must be a non-negative number")
    if errors:
        raise ContractError("capture.json", errors)
    return data


def validate_task_spec(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if data.get("schema_version") != TASK_SPEC_SCHEMA:
        errors.append(f"schema_version must be {TASK_SPEC_SCHEMA}")
    for key in ("task_name", "instruction", "objects", "subtasks", "success_predicates"):
        if key not in data or data[key] in (None, "", []):
            errors.append(f"missing required field: {key}")

    objects = data.get("objects", [])
    if isinstance(objects, list):
        for index, obj in enumerate(objects):
            if not isinstance(obj, dict):
                errors.append(f"objects[{index}] must be an object")
                continue
            if not obj.get("name"):
                errors.append(f"objects[{index}].name is required")
            if not obj.get("role"):
                errors.append(f"objects[{index}].role is required")
            if "mass_kg" in obj and not isinstance(obj["mass_kg"], (int, float)):
                errors.append(f"objects[{index}].mass_kg must be numeric")
            if "friction" in obj and not isinstance(obj["friction"], (int, float)):
                errors.append(f"objects[{index}].friction must be numeric")
    elif "objects" in data:
        errors.append("objects must be a list")

    subtasks = data.get("subtasks", [])
    if isinstance(subtasks, list):
        for index, task in enumerate(subtasks):
            if not isinstance(task, dict):
                errors.append(f"subtasks[{index}] must be an object")
                continue
            if not task.get("id"):
                errors.append(f"subtasks[{index}].id is required")
            if task.get("action") not in SUBTASK_ACTIONS:
                errors.append(
                    f"subtasks[{index}].action must be one of {sorted(SUBTASK_ACTIONS)}"
                )
            if not task.get("target"):
                errors.append(f"subtasks[{index}].target is required")
    elif "subtasks" in data:
        errors.append("subtasks must be a list")

    predicates = data.get("success_predicates", [])
    if isinstance(predicates, list):
        for index, predicate in enumerate(predicates):
            if not isinstance(predicate, dict):
                errors.append(f"success_predicates[{index}] must be an object")
                continue
            if predicate.get("type") not in PREDICATE_TYPES:
                errors.append(
                    f"success_predicates[{index}].type must be one of "
                    f"{sorted(PREDICATE_TYPES)}"
                )
    elif "success_predicates" in data:
        errors.append("success_predicates must be a list")

    constraints = data.get("constraints", [])
    if isinstance(constraints, list):
        for index, constraint in enumerate(constraints):
            if isinstance(constraint, dict) and constraint.get("type") not in CONSTRAINT_TYPES:
                errors.append(
                    f"constraints[{index}].type must be one of {sorted(CONSTRAINT_TYPES)}"
                )
    elif "constraints" in data:
        errors.append("constraints must be a list")

    if not isinstance(data.get("failure_modes", []), list):
        errors.append("failure_modes must be a list")
    if errors:
        raise ContractError("task_spec.json", errors)
    return data


def validate_demo_meta(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if data.get("schema_version") != DEMO_SCHEMA:
        errors.append(f"schema_version must be {DEMO_SCHEMA}")
    for key in ("capture_id", "objects", "events", "fps", "num_frames"):
        if key not in data:
            errors.append(f"missing required field: {key}")
    if not isinstance(data.get("objects"), list) or not data.get("objects"):
        errors.append("objects must be a non-empty list")
    if not isinstance(data.get("events"), list):
        errors.append("events must be a list")
    if not isinstance(data.get("fps"), (int, float)) or data.get("fps", 0) <= 0:
        errors.append("fps must be a positive number")
    if not isinstance(data.get("num_frames"), int) or data.get("num_frames", 0) <= 0:
        errors.append("num_frames must be a positive integer")
    if errors:
        raise ContractError("demo_object_centric.json", errors)
    return data


def validate_robot_demo(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if data.get("schema_version") != ROBOT_DEMO_SCHEMA:
        errors.append(f"schema_version must be {ROBOT_DEMO_SCHEMA}")
    for key in ("robot", "joint_names", "num_frames", "verified"):
        if key not in data:
            errors.append(f"missing required field: {key}")
    if not isinstance(data.get("joint_names"), list) or not data.get("joint_names"):
        errors.append("joint_names must be a non-empty list")
    if not isinstance(data.get("num_frames"), int) or data.get("num_frames", 0) <= 0:
        errors.append("num_frames must be a positive integer")
    if errors:
        raise ContractError("robot_demo.json", errors)
    return data


def validate_eval_report(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if data.get("schema_version") != EVAL_SCHEMA:
        errors.append(f"schema_version must be {EVAL_SCHEMA}")
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        errors.append("rows must be a non-empty list")
    else:
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"rows[{index}] must be an object")
                continue
            if not row.get("policy"):
                errors.append(f"rows[{index}].policy is required")
            for axis in ("pose", "instance", "lighting", "scene"):
                if row.get(axis) is None:
                    continue
                if not 0 <= float(row[axis]) <= 1:
                    errors.append(f"rows[{index}].{axis} must be between 0 and 1")
    if errors:
        raise ContractError("eval.json", errors)
    return data


def stage_index(name: str) -> int:
    try:
        return STAGE_NAMES.index(name)
    except ValueError as exc:
        raise KeyError(f"unknown stage: {name}") from exc


def next_stage(name: str | None) -> str | None:
    if name is None:
        return STAGE_NAMES[0]
    index = stage_index(name)
    return STAGE_NAMES[index + 1] if index + 1 < len(STAGE_NAMES) else None
