"""[D] Retarget: object-centric demo -> this robot's joint trajectory."""

from __future__ import annotations

import json

import numpy as np

from ..artifacts import read_object_demo, write_robot_demo
from ..contracts import ROBOT_DEMO_SCHEMA, ContractError, validate_demo_meta, validate_robot_demo
from ..robots import get_profile, retarget_trajectory
from ..util import iso_now
from .base import StageContext, StageError, StageHandler, StageResult


class RetargetStage(StageHandler):
    name = "retarget"

    def run(self, ctx: StageContext) -> StageResult:
        try:
            profile = get_profile(ctx.job.robot)
        except KeyError as exc:
            raise StageError(str(exc)) from exc
        demo_meta = ctx.get_json(ctx.previous("extract")["demo_meta"])
        try:
            validate_demo_meta(demo_meta)
        except ContractError as exc:
            raise StageError(str(exc)) from exc

        local_npz = ctx.local("demo_object_centric.npz")
        local_npz.write_bytes(ctx.storage.get_bytes(ctx.previous("extract")["demo"]))
        local_json = ctx.local("demo_object_centric.json")
        local_json.write_text(json.dumps(demo_meta, indent=2, sort_keys=True) + "\n")
        arrays, _ = read_object_demo(local_npz)
        target = next(
            (obj for obj in demo_meta["objects"] if obj.get("role") == "target"),
            demo_meta["objects"][0],
        )
        names = [str(name) for name in arrays["object_names"]]
        target_index = names.index(target["name"])
        positions = arrays["object_poses"][:, target_index, :3]
        right_hand = arrays["contacts"][:, target_index, 0]
        joints = retarget_trajectory(
            profile, positions, right_hand, fps=float(demo_meta["fps"])
        )
        actions = np.diff(joints, axis=0, prepend=joints[:1]).astype(np.float32)
        metadata = {
            "schema_version": ROBOT_DEMO_SCHEMA,
            "robot": profile.robot,
            "robot_label": profile.label,
            "joint_names": list(profile.joint_names),
            "num_frames": int(len(joints)),
            "fps": float(demo_meta["fps"]),
            "verified": False,
            "source_demo": ctx.previous("extract")["demo"],
            "method": "object path + analytic parallel-jaw retarget",
            "units": "radians (gripper in meters)",
            "limits": {
                "lower": list(profile.lower),
                "upper": list(profile.upper),
            },
            "gripper_index": profile.gripper_index,
            "synthetic": ctx.settings.resolved_mode != "live",
            "created_at": iso_now(),
        }
        try:
            validate_robot_demo(metadata)
        except ContractError as exc:
            raise StageError(str(exc)) from exc

        hdf5 = ctx.local(f"demo_{profile.robot}.hdf5")
        write_robot_demo(
            hdf5,
            robot=profile.robot,
            joint_names=list(profile.joint_names),
            positions=joints,
            actions=actions,
            object_poses=arrays["object_poses"],
            times=arrays["times"],
            metadata=metadata,
        )
        hdf5_key = ctx.put_file(f"demo_{profile.robot}.hdf5", hdf5)
        json_key = ctx.put_json("robot_demo.json", metadata)
        max_step = float(np.max(np.abs(actions)))
        summary = (
            f"Retargeted the object path to a {profile.label}: "
            f"{profile.dof} joints over {len(joints)} frames "
            f"{'(mock input)' if ctx.settings.resolved_mode != 'live' else ''}."
        )
        return StageResult(
            output={
                "robot_demo": hdf5_key,
                "robot_demo_meta": json_key,
                "robot": profile.robot,
                "joint_names": list(profile.joint_names),
                "num_frames": int(len(joints)),
                "max_abs_step": round(max_step, 5),
                "source_demo": ctx.previous("extract")["demo"],
                "method": metadata["method"],
            },
            summary=summary,
        )
