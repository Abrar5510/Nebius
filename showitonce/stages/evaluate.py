"""[H] Evaluate: Isaac Lab-Arena suites and the ablation table."""

from __future__ import annotations

from ..contracts import ContractError, validate_eval_report
from ..util import iso_now
from .base import StageContext, StageError, StageHandler, StageResult


class EvaluateStage(StageHandler):
    name = "evaluate"

    def run(self, ctx: StageContext) -> StageResult:
        if ctx.settings.resolved_mode == "live":
            raise StageError(
                "live evaluation needs Isaac Lab-Arena results and real-robot trials, "
                "which are not implemented in this Phase 1 build; run mock mode or "
                "attach an external evaluation report",
                retryable=False,
            )
        task_spec = ctx.get_json(ctx.previous("understand")["task_spec"])
        rows = [
            {
                "policy": "GR00T zero-shot",
                "data": "none",
                "data_clips": 0,
                "pose": 0.08,
                "instance": 0.06,
                "lighting": 0.05,
                "scene": 0.04,
            },
            {
                "policy": "+ 1 verified demo",
                "data": "1",
                "data_clips": 1,
                "pose": 0.31,
                "instance": 0.28,
                "lighting": 0.26,
                "scene": 0.21,
            },
            {
                "policy": "+ Mimic",
                "data": "~1k sim",
                "data_clips": 1001,
                "pose": 0.58,
                "instance": 0.54,
                "lighting": 0.49,
                "scene": 0.42,
            },
            {
                "policy": "+ Dreams",
                "data": "+ neural trajectories",
                "data_clips": 1059,
                "pose": 0.66,
                "instance": 0.62,
                "lighting": 0.59,
                "scene": 0.50,
            },
            {
                "policy": "+ Transfer",
                "data": "+ photoreal variants",
                "data_clips": 2043,
                "pose": 0.79,
                "instance": 0.75,
                "lighting": 0.71,
                "scene": 0.66,
            },
            {
                "policy": "Real robot",
                "data": "full mix",
                "data_clips": 2043,
                "pose": None,
                "instance": None,
                "lighting": None,
                "scene": None,
                "status": "pending hardware protocol",
            },
        ]
        for row in rows:
            values = [row[axis] for axis in ("pose", "instance", "lighting", "scene") if row[axis] is not None]
            row["overall"] = round(sum(values) / len(values), 3) if values else None
        report = {
            "schema_version": "showitonce.eval/v1",
            "skill": ctx.job.skill,
            "robot": ctx.job.robot,
            "task_name": task_spec["task_name"],
            "benchmark": "Isaac Lab-Arena held-out variations",
            "rows": rows,
            "axes": ["pose", "instance", "lighting", "scene"],
            "real_robot_protocol": {
                "trials": 20,
                "layouts": 5,
                "judge": "Cosmos Reason 2, confirmed by a human",
                "status": "not_run",
            },
            "synthetic": ctx.settings.resolved_mode != "live",
            "created_at": iso_now(),
        }
        try:
            validate_eval_report(report)
        except ContractError as exc:
            raise StageError(str(exc)) from exc

        markdown = self._markdown(report)
        report_key = ctx.put_json("eval.json", report)
        table_key = ctx.put_text("eval_table.md", markdown)
        transfer = next(row for row in rows if row["policy"] == "+ Transfer")
        summary = (
            "Mock evaluation only: held-out pose rises from 8% zero-shot to "
            f"{transfer['pose'] * 100:.0f}% with Transfer in simulation; "
            "real-robot trials are pending."
        )
        return StageResult(
            output={
                "eval": report_key,
                "eval_table": table_key,
                "rows": rows,
                "best_sim_overall": transfer["overall"],
                "real_robot": "pending",
            },
            summary=summary,
        )

    @staticmethod
    def _markdown(report: dict) -> str:
        lines = [
            f"# Evaluation: {report['task_name']}",
            "",
            "| Policy | Data | Pose | Instance | Lighting | Scene | Overall |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in report["rows"]:
            cells = [row["policy"], row["data"]]
            for axis in ("pose", "instance", "lighting", "scene", "overall"):
                value = row.get(axis)
                cells.append("—" if value is None else f"{value * 100:.0f}%")
            lines.append("| " + " | ".join(cells) + " |")
        lines.extend(
            [
                "",
                "Real-robot protocol: 20 trials x 5 fixed layouts, judged by Cosmos Reason 2 "
                "and confirmed by a human.",
                "",
            ]
        )
        return "\n".join(lines)
