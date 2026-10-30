"""[G] Train: verified + multiplied data -> a per-skill GR00T LoRA adapter."""

from __future__ import annotations

import math

from ..artifacts import write_safetensors_stub
from ..util import iso_now
from .base import StageContext, StageError, StageHandler, StageResult


class TrainStage(StageHandler):
    name = "train"

    def run(self, ctx: StageContext) -> StageResult:
        if ctx.settings.resolved_mode == "live":
            raise StageError(
                "live GR00T LoRA training is not implemented in this Phase 1 build; "
                "the Serverless Job entrypoint is wired, but there is no training image "
                "or checkpoint yet. Run mock mode to exercise the contract.",
                retryable=False,
            )
        task_spec = ctx.get_json(ctx.previous("understand")["task_spec"])
        multiply = ctx.previous("multiply")
        counts = multiply["counts"]
        robot = ctx.job.robot
        base_model = "nvidia/GR00T-N1.6-3B"
        steps = 3200
        loss_curve = [
            {
                "step": step,
                "loss": round(0.92 * math.exp(-step / 950.0) + 0.075 + 0.012 * math.sin(step / 130), 4),
            }
            for step in range(0, steps + 1, 400)
        ]
        dataset = {
            "schema_version": "showitonce.training_set/v1",
            "format": "LeRobot v2",
            "robot": robot,
            "cameras": ["front", "wrist"],
            "task_name": task_spec["task_name"],
            "episodes": counts["training_clips"],
            "frames": counts["training_clips"] * 120,
            "sources": {
                "verified_demo": {"clips": 1, "weight": 8.0},
                "mimic": {"clips": counts["mimic"], "weight": 1.0},
                "dreams": {"clips": counts["dreams"], "weight": 0.8},
                "transfer": {"clips": counts["transfer"], "weight": 0.9},
            },
            "upweighted_verified_demo": True,
            "created_at": iso_now(),
        }
        report = {
            "schema_version": "showitonce.train/v1",
            "skill": ctx.job.skill,
            "robot": robot,
            "base_model": base_model,
            "method": "LoRA",
            "lora": {
                "rank": 16,
                "alpha": 32,
                "target_modules": ["q_proj", "v_proj", "k_proj", "o_proj"],
                "trainable_params": 18_874_368,
            },
            "data": {
                "episodes": counts["training_clips"],
                "batch_size": 64,
                "steps": steps,
                "learning_rate": 1e-4,
                "warmup_steps": 160,
            },
            "compute": {
                "backend": ctx.settings.execution,
                "gpu": "Nebius Serverless Job (L40S-class for LoRA)",
                "duration_s": 1842,
            },
            "loss_curve": loss_curve,
            "final_loss": loss_curve[-1]["loss"],
            "status": "succeeded",
            "synthetic": ctx.settings.resolved_mode != "live",
            "created_at": iso_now(),
        }
        local_lora = ctx.local(f"lora_{robot}.safetensors")
        write_safetensors_stub(local_lora, {"base_model": base_model, "skill": ctx.job.skill})
        dataset_key = ctx.put_json("dataset.json", dataset)
        report_key = ctx.put_json("train_report.json", report)
        lora_key = ctx.put_file(f"lora_{robot}.safetensors", local_lora)
        summary = (
            f"Mock training report: GR00T N1.6 LoRA on {counts['training_clips']:,} "
            f"synthetic clips for {steps:,} steps, final loss {report['final_loss']:.3f}. "
            "No model weights were trained."
        )
        return StageResult(
            output={
                "dataset": dataset_key,
                "train_report": report_key,
                "lora": lora_key,
                "base_model": base_model,
                "episodes": counts["training_clips"],
                "steps": steps,
                "final_loss": report["final_loss"],
            },
            summary=summary,
        )
