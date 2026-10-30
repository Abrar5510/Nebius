from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
import pytest

from showitonce.artifacts import (
    build_object_centric_demo,
    read_object_demo,
    validate_demo_arrays,
    write_object_demo,
    write_safetensors_stub,
)
from showitonce.robots import SO101, get_profile, retarget_trajectory

TASK_SPEC = {
    "task_name": "place_cup",
    "objects": [
        {"id": "mug", "name": "red mug", "role": "target"},
        {"id": "coaster", "name": "wooden coaster", "role": "surface"},
    ],
}


def test_object_demo_round_trip(tmp_path: Path) -> None:
    arrays, meta = build_object_centric_demo("cap_1", TASK_SPEC, num_frames=24, fps=12)
    path = tmp_path / "demo_object_centric.npz"
    write_object_demo(path, arrays, meta)
    loaded, loaded_meta = read_object_demo(path)
    assert loaded_meta == meta
    assert loaded["object_poses"].shape == (24, 2, 7)
    assert loaded["object_names"].tolist() == ["red mug", "wooden coaster"]
    assert [event["type"] for event in loaded_meta["events"]] == ["grasp", "release"]
    assert np.all(np.isfinite(loaded["object_poses"]))


def test_demo_validation_rejects_bad_shapes() -> None:
    arrays, _ = build_object_centric_demo("cap_1", TASK_SPEC, num_frames=12)
    validate_demo_arrays(arrays)
    broken = dict(arrays)
    broken["hand_poses"] = arrays["hand_poses"][:, :, :19]
    with pytest.raises(ValueError, match="hand_poses"):
        validate_demo_arrays(broken)
    broken = dict(arrays)
    broken["contacts"] = arrays["contacts"][:, :1]
    with pytest.raises(ValueError, match="contacts"):
        validate_demo_arrays(broken)
    broken = dict(arrays)
    broken["object_poses"] = arrays["object_poses"].copy()
    broken["object_poses"][0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        validate_demo_arrays(broken)


def test_safetensors_stub_is_a_valid_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "lora.safetensors"
    write_safetensors_stub(path, {"skill": "place_cup"})
    raw = path.read_bytes()
    header_len = struct.unpack("<Q", raw[:8])[0]
    header = json.loads(raw[8 : 8 + header_len])
    assert raw[8 + header_len :] == b""
    metadata = header["__metadata__"]
    assert metadata["mock"] == "true"
    assert metadata["skill"] == "place_cup"
    assert metadata["format"] == "pt"
    assert len(header) == 1


def test_retarget_produces_a_bounded_robot_trajectory() -> None:
    arrays, meta = build_object_centric_demo("cap_1", TASK_SPEC, num_frames=120)
    target_index = [str(name) for name in arrays["object_names"]].index("red mug")
    positions = arrays["object_poses"][:, target_index, :3]
    contacts = arrays["contacts"][:, target_index, 0]
    joints = retarget_trajectory(SO101, positions, contacts, fps=float(meta["fps"]))
    assert joints.shape == (120, SO101.dof)
    assert np.all(joints >= np.array(SO101.lower) - 1e-4)
    assert np.all(joints <= np.array(SO101.upper) + 1e-4)
    steps = np.abs(np.diff(joints, axis=0))
    assert steps[:, SO101.gripper_index].max() <= 0.0201
    assert steps[:, : SO101.gripper_index].max() <= 0.1801
    assert joints[-1, SO101.gripper_index] > 0.03


def test_retarget_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="shape"):
        retarget_trajectory(SO101, np.zeros((10, 2)), np.zeros(10), fps=10)
    with pytest.raises(ValueError, match="two frames"):
        retarget_trajectory(SO101, np.zeros((1, 3)), np.zeros(1), fps=10)
    with pytest.raises(KeyError, match="available"):
        get_profile("robot-arm-9000")
