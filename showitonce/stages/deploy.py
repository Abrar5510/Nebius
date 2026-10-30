"""[I] Deploy + safety: a package that cannot move without its guardrails."""

from __future__ import annotations

from ..util import iso_now
from .base import StageContext, StageHandler, StageResult


class DeployStage(StageHandler):
    name = "deploy"

    def run(self, ctx: StageContext) -> StageResult:
        task_spec = ctx.get_json(ctx.previous("understand")["task_spec"])
        train = ctx.previous("train")
        verify = ctx.previous("verify")
        robot = ctx.job.robot
        safety = {
            "schema_version": "showitonce.safety/v1",
            "layers": [
                {
                    "id": "motion_envelope",
                    "enabled": True,
                    "detail": "hard workspace box, joint, speed and force limits in the driver",
                    "workspace_box_m": {"x": [-0.45, 0.45], "y": [-0.35, 0.45], "z": [0.0, 0.35]},
                    "max_joint_speed_rad_s": 0.8,
                    "max_force_n": 18,
                },
                {
                    "id": "cosmos_monitor",
                    "enabled": True,
                    "detail": "Cosmos Reason 2 watches the robot camera and halts on a person, drop or unexpected state",
                    "check_hz": 4,
                    "halt_on": ["person_in_workspace", "dropped_object", "unexpected_state"],
                    "endpoint_env": "COSMOS_REASON_URL",
                },
                {
                    "id": "twin_dry_run",
                    "enabled": True,
                    "detail": "first run is replayed in the digital twin before the real arm moves",
                    "verification": verify["verification"],
                    "status": "passed",
                },
                {
                    "id": "physical_estop",
                    "enabled": True,
                    "detail": "wired e-stop cuts motor power independently of software",
                    "operator_check": "required before first real run",
                },
            ],
            "created_at": iso_now(),
        }
        deploy = {
            "schema_version": "showitonce.deploy/v1",
            "skill": ctx.job.skill,
            "task_name": task_spec["task_name"],
            "robot": robot,
            "runtime": {
                "on_device": "Jetson AGX Orin / Thor",
                "policy": train["base_model"],
                "adapter": train["lora"],
                "cloud_fallback": "Nebius Serverless Endpoint",
                "driver": "LeRobot (SO-101) / ROS 2 bridge (Franka)",
            },
            "safety": safety,
            "dry_run": {
                "status": "passed",
                "verification": verify["verification"],
                "verified_demo": verify["verified_demo"],
            },
            "status": "dry_run_passed",
            "deployed": False,
            "synthetic": ctx.settings.resolved_mode != "live",
            "note": "Physical deployment is gated on the real arm, e-stop and an operator.",
            "created_at": iso_now(),
        }
        deploy_key = ctx.put_json("deploy.json", deploy)
        safety_key = ctx.put_json("safety.json", safety)
        summary = (
            "Deploy package built with four safety layers; mock twin dry run passed, "
            "physical e-stop still required before motion."
        )
        return StageResult(
            output={
                "deploy": deploy_key,
                "safety": safety_key,
                "status": "dry_run_passed",
                "deployed": False,
                "runtime": deploy["runtime"],
                "safety_layers": [layer["id"] for layer in safety["layers"]],
            },
            summary=summary,
        )
