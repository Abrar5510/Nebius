"""Artifact writers and the synthetic demo generator used by mock mode.

Mock mode is not a slideshow: it emits the real file formats from the build plan
(``.npz``, ``.hdf5``, ``.safetensors``, JSON) with physically plausible trajectories,
so every later stage and the dashboard exercise the production contracts.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

import h5py
import numpy as np


def smoothstep(t: np.ndarray) -> np.ndarray:
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _quat_yaw(yaw: float) -> tuple[float, float, float, float]:
    return (float(np.cos(yaw / 2)), 0.0, 0.0, float(np.sin(yaw / 2)))


def _pose(x: float, y: float, z: float, yaw: float = 0.0) -> list[float]:
    qw, qx, qy, qz = _quat_yaw(yaw)
    return [x, y, z, qw, qx, qy, qz]


def build_object_centric_demo(
    capture_id: str,
    task_spec: dict[str, Any],
    *,
    num_frames: int = 120,
    fps: float = 10.0,
    seed: int = 7,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Create a deterministic, object-centric demonstration of a pick-and-place.

    The generated motion is intentionally object-first: the mug's pose is the source
    of truth, and the hand is drawn around it. That is exactly the representation a
    gripper, a dexterous hand or a humanoid can consume.
    """
    rng = np.random.default_rng(seed)
    objects = task_spec.get("objects", [])
    target = next((obj for obj in objects if obj.get("role") == "target"), None)
    surface = next(
        (obj for obj in objects if obj.get("role") in {"surface", "receptacle", "support"}),
        None,
    )
    target_name = (target or {}).get("name", "target object")
    surface_name = (surface or {}).get("name", "table")
    object_names = [target_name, surface_name]
    object_ids = [(target or {}).get("id", "target"), (surface or {}).get("id", "surface")]

    times = np.arange(num_frames, dtype=np.float32) / fps
    t = np.linspace(0.0, 1.0, num_frames, dtype=np.float32)
    start = np.array([-0.18, -0.04, 0.045], dtype=np.float32)
    lift = np.array([-0.18, -0.04, 0.20], dtype=np.float32)
    over = np.array([0.16, 0.22, 0.20], dtype=np.float32)
    place = np.array([0.16, 0.22, 0.045], dtype=np.float32)

    positions = np.zeros((num_frames, 3), dtype=np.float32)
    # 0-20% approach, 20-35% lift, 35-70% transport, 70-82% lower, hold.
    for i in range(num_frames):
        phase = t[i]
        if phase < 0.20:
            a = smoothstep(np.array((phase - 0.0) / 0.20))
            positions[i] = start + (lift - start) * 0.08 * a
        elif phase < 0.35:
            a = smoothstep(np.array((phase - 0.20) / 0.15))
            positions[i] = start + (lift - start) * (0.08 + 0.92 * a)
        elif phase < 0.70:
            a = smoothstep(np.array((phase - 0.35) / 0.35))
            positions[i] = lift + (over - lift) * a
        elif phase < 0.82:
            a = smoothstep(np.array((phase - 0.70) / 0.12))
            positions[i] = over + (place - over) * a
        else:
            positions[i] = place
    positions += rng.normal(0.0, 0.0008, size=positions.shape).astype(np.float32)

    target_poses = np.zeros((num_frames, 7), dtype=np.float32)
    target_poses[:, :3] = positions
    progress = np.clip((positions[:, 0] - start[0]) / (over[0] - start[0]), 0.0, 1.0)
    yaw = 0.35 * progress
    target_poses[:, 3] = np.cos(yaw / 2.0)
    target_poses[:, 6] = np.sin(yaw / 2.0)

    surface_poses = np.zeros((num_frames, 7), dtype=np.float32)
    surface_poses[:] = _pose(0.16, 0.22, 0.012)
    object_poses = np.stack([target_poses, surface_poses], axis=1)

    # A plausible 21-keypoint right hand tracks the mug; the left stays in view.
    hand_poses = np.zeros((num_frames, 2, 21, 3), dtype=np.float32)
    palm = positions + np.array([0.0, -0.06, 0.02], dtype=np.float32)
    for i in range(num_frames):
        hand_poses[i, 0] = _hand_shape(palm[i])
        hand_poses[i, 1] = _hand_shape(
            np.array([-0.32, -0.10, 0.16], dtype=np.float32)
        )
    contacts = np.zeros((num_frames, 2, 2), dtype=bool)
    grasp_start, grasp_end = int(num_frames * 0.20), int(num_frames * 0.70)
    contacts[grasp_start:grasp_end, 0, 0] = True
    contacts[grasp_start:grasp_end, 0, 1] = False

    events = [
        {
            "time": round(float(times[grasp_start]), 3),
            "type": "grasp",
            "object": target_name,
            "hand": "right",
            "approach": "top",
            "contact_confidence": 0.94,
        },
        {
            "time": round(float(times[grasp_end]), 3),
            "type": "release",
            "object": target_name,
            "hand": "right",
            "surface": surface_name,
            "contact_confidence": 0.91,
        },
    ]
    meta = {
        "schema_version": "showitonce.demo_object_centric/v1",
        "capture_id": capture_id,
        "task_name": task_spec.get("task_name", "pick and place"),
        "fps": fps,
        "num_frames": num_frames,
        "duration_s": round(num_frames / fps, 3),
        "objects": [
            {"id": object_ids[0], "name": target_name, "role": "target"},
            {"id": object_ids[1], "name": surface_name, "role": "surface"},
        ],
        "events": events,
        "hand_model": "synthetic 21-keypoint hand",
        "metric_scale": "meters",
        "synthetic": True,
    }
    arrays = {
        "times": times,
        "object_poses": object_poses,
        "object_names": np.array(object_names, dtype="U64"),
        "hand_poses": hand_poses,
        "contacts": contacts,
    }
    validate_demo_arrays(arrays)
    return arrays, meta


def _hand_shape(palm: np.ndarray) -> np.ndarray:
    points = np.zeros((21, 3), dtype=np.float32)
    points[0] = palm
    finger_starts = [
        np.array([-0.035, 0.012, 0.0]),
        np.array([-0.012, 0.018, 0.0]),
        np.array([0.012, 0.018, 0.0]),
        np.array([0.034, 0.012, 0.0]),
        np.array([0.052, -0.006, 0.0]),
    ]
    finger_lengths = [0.055, 0.062, 0.058, 0.050, 0.042]
    for finger, (start, length) in enumerate(zip(finger_starts, finger_lengths, strict=True)):
        base = 1 + finger * 4
        for joint in range(4):
            points[base + joint] = palm + start + np.array(
                [0.0, 0.0, -length * (joint + 1) / 4.0], dtype=np.float32
            )
    return points


def validate_demo_arrays(arrays: dict[str, np.ndarray]) -> None:
    required = {"times", "object_poses", "object_names", "hand_poses", "contacts"}
    missing = required - set(arrays)
    if missing:
        raise ValueError(f"demo is missing arrays: {sorted(missing)}")
    poses = arrays["object_poses"]
    if poses.ndim != 3 or poses.shape[2] != 7:
        raise ValueError("object_poses must have shape (T, N, 7)")
    if arrays["hand_poses"].ndim != 4 or arrays["hand_poses"].shape[-2:] != (21, 3):
        raise ValueError("hand_poses must have shape (T, hands, 21, 3)")
    if arrays["contacts"].shape != (poses.shape[0], poses.shape[1], arrays["hand_poses"].shape[1]):
        raise ValueError("contacts must have shape (T, N, hands)")
    if not np.all(np.isfinite(poses)):
        raise ValueError("object_poses contains non-finite values")


def write_object_demo(path: Path, arrays: dict[str, np.ndarray], meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)
    path.with_suffix(".json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")


def read_object_demo(path: Path) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    arrays = {key: value for key, value in np.load(path, allow_pickle=False).items()}
    meta = json.loads(path.with_suffix(".json").read_text())
    return arrays, meta


def write_robot_demo(
    path: Path,
    *,
    robot: str,
    joint_names: list[str],
    positions: np.ndarray,
    actions: np.ndarray,
    object_poses: np.ndarray,
    times: np.ndarray,
    metadata: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        handle.attrs["robot"] = robot
        handle.attrs["format"] = "showitonce.robot_demo/v1"
        handle.attrs["metadata"] = json.dumps(metadata, sort_keys=True)
        handle.create_dataset("joint_positions", data=positions)
        handle.create_dataset("actions", data=actions)
        handle.create_dataset("object_poses", data=object_poses)
        handle.create_dataset("timestamps", data=times)
        handle.create_dataset(
            "joint_names", data=np.array(joint_names, dtype=h5py.string_dtype())
        )


def read_robot_demo(path: Path) -> dict[str, np.ndarray]:
    with h5py.File(path, "r") as handle:
        return {key: handle[key][()] for key in handle}


def write_safetensors_stub(path: Path, metadata: dict[str, Any] | None = None) -> None:
    """Write a valid, empty safetensors file carrying mock metadata.

    This is deliberately not a fake trained model: it has zero tensors and says so in
    its metadata, while exercising the same packaging and checksum path as a real LoRA.
    """
    header = {"__metadata__": {"format": "pt", "mock": "true", **(metadata or {})}}
    raw = json.dumps(header, separators=(",", ":")).encode("utf-8")
    padded = (8 - len(raw) % 8) % 8
    header_bytes = raw + b" " * padded
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(struct.pack("<Q", len(header_bytes)))
        handle.write(header_bytes)
