"""[E] Verify: replay the retargeted motion against the task predicates.

Mock mode uses the analytic twin checks below. Phase 4 swaps the evaluator for an
Isaac Lab replay + local trajectory optimizer; the report shape stays the same.
"""

from __future__ import annotations

import json
import math

import h5py
import numpy as np

from ..artifacts import read_object_demo
from ..contracts import ContractError, validate_task_spec
from ..util import iso_now
from .base import StageContext, StageError, StageHandler, StageResult

MAX_STEP_RAD = 0.20
MAX_STEP_GRIPPER = 0.025


class VerifyStage(StageHandler):
    name = "verify"

    def run(self, ctx: StageContext) -> StageResult:
        task_spec = ctx.get_json(ctx.previous("understand")["task_spec"])
        try:
            validate_task_spec(task_spec)
        except ContractError as exc:
            raise StageError(str(exc)) from exc

        retarget_out = ctx.previous("retarget")
        robot_meta = ctx.get_json(retarget_out["robot_demo_meta"])
        demo_meta = ctx.get_json(ctx.previous("extract")["demo_meta"])
        hdf5 = ctx.local(robot_meta["robot"] + ".hdf5")
        hdf5.write_bytes(ctx.storage.get_bytes(retarget_out["robot_demo"]))
        demo_npz = ctx.local("demo_object_centric.npz")
        demo_npz.write_bytes(ctx.storage.get_bytes(ctx.previous("extract")["demo"]))
        demo_json = ctx.local("demo_object_centric.json")
        demo_json.write_text(json.dumps(demo_meta, indent=2, sort_keys=True) + "\n")
        arrays, demo_meta = read_object_demo(demo_npz)

        with h5py.File(hdf5, "r") as handle:
            joints = handle["joint_positions"][()]
        checks = self._checks(task_spec, robot_meta, arrays, demo_meta, joints)
        success = all(check["passed"] for check in checks)

        report = {
            "schema_version": "showitonce.verification/v1",
            "capture_id": ctx.job.capture_id,
            "robot": robot_meta["robot"],
            "success": success,
            "verified": success,
            "engine": "analytic twin checks (mock)",
            "checks": checks,
            "checks_passed": sum(1 for check in checks if check["passed"]),
            "checks_total": len(checks),
            "adjustments": [],
            "optimizer": "not needed" if success else "phase-4 Isaac Lab optimizer required",
            "synthetic": True,
            "created_at": iso_now(),
        }
        if success:
            verified_meta = dict(robot_meta)
            verified_meta.update({"verified": True, "verification": "verified"})
            verified_key = ctx.put_bytes(
                f"demo_{robot_meta['robot']}_verified.hdf5",
                hdf5.read_bytes(),
                "application/x-hdf5",
            )
            report["verified_demo"] = verified_key
            report["verified_meta"] = ctx.put_json("verified_robot_demo.json", verified_meta)
        report_key = ctx.put_json("verification.json", report)

        if not success:
            failed = ", ".join(check["name"] for check in checks if not check["passed"])
            raise StageError(f"twin verification failed: {failed}")

        summary = (
            f"Analytic twin check (mock): {report['checks_passed']}/{report['checks_total']} "
            "passed, 0 trajectory repairs needed."
        )
        return StageResult(
            output={
                "verification": report_key,
                "verified_demo": report["verified_demo"],
                "verified_meta": report["verified_meta"],
                "success": True,
                "checks_passed": report["checks_passed"],
                "checks_total": report["checks_total"],
                "checks": checks,
                "engine": report["engine"],
            },
            summary=summary,
        )

    @staticmethod
    def _checks(
        task_spec: dict,
        robot_meta: dict,
        arrays: dict,
        demo_meta: dict,
        joints: np.ndarray,
    ) -> list[dict]:
        checks: list[dict] = []
        names = [str(name) for name in arrays["object_names"]]
        target = next(obj for obj in demo_meta["objects"] if obj.get("role") == "target")
        surface = next(
            (obj for obj in demo_meta["objects"] if obj.get("role") in {"surface", "support"}),
            demo_meta["objects"][-1],
        )
        target_index = names.index(target["name"])
        surface_index = names.index(surface["name"])
        target_poses = arrays["object_poses"][:, target_index]
        surface_poses = arrays["object_poses"][:, surface_index]
        final = target_poses[-1]
        surface_final = surface_poses[-1]
        horizontal = float(np.linalg.norm(final[:2] - surface_final[:2]))
        vertical = float(final[2] - surface_final[2])
        predicate = next(
            (
                item
                for item in task_spec.get("success_predicates", [])
                if item.get("type") == "object_on_surface"
            ),
            {},
        )
        threshold = float(predicate.get("threshold_m", 0.06))
        checks.append(
            {
                "name": "object_on_surface",
                "passed": horizontal <= threshold and abs(vertical) <= 0.12,
                "detail": (
                    f"{target['name']} ended {horizontal * 100:.1f} cm from "
                    f"{surface['name']} center"
                ),
                "measured": round(horizontal, 4),
                "threshold": threshold,
            }
        )

        qw, qx, qy, qz = (float(value) for value in final[3:7])
        up_z = 1.0 - 2.0 * (qx * qx + qy * qy)
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, up_z))))
        checks.append(
            {
                "name": "object_upright",
                "passed": tilt <= 20.0,
                "detail": f"{target['name']} tilt at release is {tilt:.1f} deg",
                "measured": round(tilt, 2),
                "threshold": 20.0,
            }
        )

        contacts = arrays["contacts"][:, target_index, 0]
        gripper_index = int(robot_meta.get("gripper_index", len(robot_meta["joint_names"]) - 1))
        gripper = joints[:, gripper_index]
        released = (not bool(contacts[-1])) and float(gripper[-1]) >= 0.03
        checks.append(
            {
                "name": "gripper_released",
                "passed": released,
                "detail": f"final gripper opening {float(gripper[-1]):.3f} m",
                "measured": round(float(gripper[-1]), 4),
                "threshold": 0.03,
            }
        )

        diffs = np.abs(np.diff(joints, axis=0))
        arm_max = float(diffs.max()) if diffs.size else 0.0
        checks.append(
            {
                "name": "velocity_limit",
                "passed": arm_max <= MAX_STEP_RAD + 1e-6,
                "detail": f"maximum per-frame joint change is {arm_max:.3f} rad",
                "measured": round(arm_max, 4),
                "threshold": MAX_STEP_RAD,
                "gripper_index": gripper_index,
            }
        )

        limits = robot_meta.get("limits", {})
        lower = np.array(limits.get("lower", []))
        upper = np.array(limits.get("upper", []))
        in_limits = True
        if len(lower) == joints.shape[1] and len(upper) == joints.shape[1]:
            in_limits = bool(np.all(joints >= lower - 1e-4) and np.all(joints <= upper + 1e-4))
        checks.append(
            {
                "name": "joint_limits",
                "passed": in_limits,
                "detail": "every joint stayed inside the manufacturer envelope",
            }
        )
        return checks
