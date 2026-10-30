"""[K] Skill library: package, version and publish the skill for another robot."""

from __future__ import annotations

from typing import Any

from ..contracts import SKILL_SCHEMA
from ..storage import StorageNotFound
from ..util import iso_now, sha256_bytes, slugify
from .base import StageContext, StageError, StageHandler, StageResult


class LibraryStage(StageHandler):
    name = "library"

    def run(self, ctx: StageContext) -> StageResult:
        understand = ctx.previous("understand")
        extract = ctx.previous("extract")
        retarget = ctx.previous("retarget")
        verify = ctx.previous("verify")
        train = ctx.previous("train")
        evaluate = ctx.previous("evaluate")
        deploy = ctx.previous("deploy")

        skill_name = slugify(ctx.job.skill)
        index = self._read_index(ctx)
        entry = index["skills"].setdefault(skill_name, {"versions": []})
        version = self._pick_version(ctx, entry)
        package = f"library/{skill_name}/{version}"

        sources: list[tuple[str, str]] = [
            ("task_spec.json", understand["task_spec"]),
            ("demo_object_centric.npz", extract["demo"]),
            ("demo_object_centric.json", extract["demo_meta"]),
            (f"demo_{ctx.job.robot}.hdf5", verify.get("verified_demo", retarget["robot_demo"])),
            (f"lora_{ctx.job.robot}.safetensors", train["lora"]),
            ("verification.json", verify["verification"]),
            ("eval.json", evaluate["eval"]),
            ("deploy.json", deploy["deploy"]),
        ]
        files: list[dict[str, Any]] = []
        for name, source_key in sources:
            try:
                data = ctx.storage.get_bytes(source_key)
            except StorageNotFound as exc:
                raise StageError(f"cannot package missing artifact {source_key}") from exc
            target = f"{package}/{name}"
            ctx.storage.put_bytes(target, data)
            files.append(
                {
                    "path": name,
                    "bytes": len(data),
                    "sha256": sha256_bytes(data),
                }
            )

        manifest = {
            "schema_version": SKILL_SCHEMA,
            "name": skill_name,
            "version": version,
            "task_name": understand["task_name"],
            "instruction": understand["instruction"],
            "created_at": iso_now(),
            "source_job": ctx.job.id,
            "source_capture": ctx.job.capture_id,
            "synthetic": ctx.settings.resolved_mode != "live",
            "robot_embodiments": [ctx.job.robot],
            "files": files,
            "privacy": {
                "faces_blurred_at_capture": True,
                "raw_video_included": False,
                "shared_object_centric_demo_only": True,
            },
            "adapt_on_install": {
                "inputs": ["10-second room scan"],
                "steps": ["reconstruct new twin", "verify", "multiply", "fine-tune LoRA 200 steps"],
                "requires_new_demonstration": False,
            },
        }
        manifest_key = ctx.storage.put_json(f"{package}/skill.json", manifest)

        entry.update(
            {
                "latest": version,
                "task_name": understand["task_name"],
                "instruction": understand["instruction"],
                "robot_embodiments": sorted(
                    set(entry.get("robot_embodiments", [])) | {ctx.job.robot}
                ),
                "updated_at": iso_now(),
                "source_job": ctx.job.id,
            }
        )
        if version not in entry["versions"]:
            entry["versions"].append(version)
        index["updated_at"] = iso_now()
        index_key = ctx.storage.put_json("library/index.json", index)

        summary = (
            f'Published {"mock " if ctx.settings.resolved_mode != "live" else ""}'
            f'"{skill_name}" {version} to the library: spec, demo, '
            f"{ctx.job.robot} LoRA and eval, with raw video left private."
        )
        return StageResult(
            output={
                "skill": manifest_key,
                "index": index_key,
                "package": package,
                "name": skill_name,
                "version": version,
                "files": [item["path"] for item in files],
                "shared": True,
            },
            summary=summary,
        )

    @staticmethod
    def _read_index(ctx: StageContext) -> dict[str, Any]:
        try:
            data = ctx.storage.get_json("library/index.json")
            if not isinstance(data, dict):
                raise ValueError
            data.setdefault("skills", {})
            return data
        except (StorageNotFound, ValueError):
            return {
                "schema_version": "showitonce.library/v1",
                "updated_at": iso_now(),
                "skills": {},
            }

    @staticmethod
    def _pick_version(ctx: StageContext, entry: dict[str, Any]) -> str:
        # Idempotent rerun of the same job keeps its version; a new job bumps the patch.
        existing = entry.get("versions", [])
        if entry.get("source_job") == ctx.job.id and entry.get("latest"):
            return str(entry["latest"])
        if not existing:
            return "0.1.0"
        latest = max(existing, key=LibraryStage._semver)
        major, minor, patch = (int(part) for part in latest.split("."))
        return f"{major}.{minor}.{patch + 1}"

    @staticmethod
    def _semver(value: str) -> tuple[int, int, int]:
        try:
            major, minor, patch = (int(part) for part in value.split("."))
            return major, minor, patch
        except (ValueError, AttributeError):
            return 0, 0, 0
