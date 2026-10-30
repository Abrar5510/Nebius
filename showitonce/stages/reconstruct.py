"""[B] Reconstruct: phone scan -> USD twin + per-object physics priors."""

from __future__ import annotations

import re
from typing import Any

from ..contracts import ContractError, validate_task_spec
from ..util import iso_now
from .base import StageContext, StageError, StageHandler, StageResult

PHYSICS_PRIORS = {
    "ceramic": {"density_kg_m3": 2300, "friction": 0.55, "restitution": 0.15},
    "glass": {"density_kg_m3": 2500, "friction": 0.40, "restitution": 0.20},
    "cloth": {"density_kg_m3": 300, "friction": 0.75, "restitution": 0.02},
    "plastic": {"density_kg_m3": 950, "friction": 0.45, "restitution": 0.30},
    "metal": {"density_kg_m3": 7800, "friction": 0.35, "restitution": 0.25},
    "wood": {"density_kg_m3": 700, "friction": 0.50, "restitution": 0.20},
}


class ReconstructStage(StageHandler):
    name = "reconstruct"

    def run(self, ctx: StageContext) -> StageResult:
        capture = ctx.capture()
        task_spec = ctx.get_json(ctx.previous("understand")["task_spec"])
        try:
            validate_task_spec(task_spec)
        except ContractError as exc:
            raise StageError(str(exc)) from exc

        if ctx.settings.resolved_mode == "live":
            return self._live(ctx, capture, task_spec)

        room = capture.get("room", {})
        objects = task_spec["objects"]
        physics = {
            "schema_version": "showitonce.physics/v1",
            "capture_id": ctx.job.capture_id,
            "gravity_m_s2": -9.81,
            "objects": [self._physics_for(obj) for obj in objects],
            "source": "Cosmos Reason 2 material priors (mock)",
            "synthetic": True,
            "created_at": iso_now(),
        }
        twin = {
            "schema_version": "showitonce.twin/v1",
            "capture_id": ctx.job.capture_id,
            "scene": {
                "usd_key": ctx.key("scene.usda"),
                "source": "phone LiDAR mesh + ARKit poses (mock)",
                "room": room,
            },
            "objects": [
                {
                    "id": obj["id"],
                    "name": obj["name"],
                    "role": obj["role"],
                    "dimensions_m": obj.get("dimensions_m", [0.08, 0.08, 0.10]),
                    "pose": self._object_pose(obj, room, index),
                }
                for index, obj in enumerate(objects)
            ],
            "units": "meters",
            "up_axis": "Y",
            "synthetic": True,
            "created_at": iso_now(),
        }
        usda = self._usda(room, task_spec["objects"])
        usd_key = ctx.put_text("scene.usda", usda)
        twin_key = ctx.put_json("twin.json", twin)
        physics_key = ctx.put_json("physics.json", physics)
        summary = (
            f"Mock-rebuilt {room.get('name', 'the room')} as a USD twin with "
            f"{len(objects)} tracked objects and physics priors."
        )
        return StageResult(
            output={
                "twin": twin_key,
                "physics": physics_key,
                "scene_usd": usd_key,
                "object_count": len(objects),
                "source": "mock",
            },
            summary=summary,
        )

    def _live(
        self, ctx: StageContext, capture: dict[str, Any], task_spec: dict[str, Any]
    ) -> StageResult:
        """Import the phone mesh when it is present; never pretend NuRec ran."""
        files = capture.get("files", {})
        mesh_key = files.get("mesh")
        if not mesh_key:
            raise StageError(
                "live reconstruction needs capture['files']['mesh'] from the phone scan; "
                "NuRec is configured outside this stage",
                retryable=False,
            )
        mesh_bytes = ctx.storage.get_bytes(mesh_key)
        usd_key = ctx.put_bytes("phone_mesh.usdz", mesh_bytes)
        physics = {
            "schema_version": "showitonce.physics/v1",
            "capture_id": ctx.job.capture_id,
            "gravity_m_s2": -9.81,
            "objects": [self._physics_for(obj) for obj in task_spec["objects"]],
            "source": "capture mesh + Cosmos Reason 2 physics priors",
            "synthetic": False,
            "created_at": iso_now(),
        }
        twin = {
            "schema_version": "showitonce.twin/v1",
            "capture_id": ctx.job.capture_id,
            "scene": {
                "usd_key": usd_key,
                "source": "ARkit LiDAR mesh",
                "room": capture.get("room", {}),
            },
            "objects": [],
            "units": "meters",
            "synthetic": False,
            "created_at": iso_now(),
        }
        return StageResult(
            output={
                "twin": ctx.put_json("twin.json", twin),
                "physics": ctx.put_json("physics.json", physics),
                "scene_usd": usd_key,
                "object_count": len(task_spec["objects"]),
                "source": "capture-mesh",
            },
            summary=f"Imported the phone mesh and {len(task_spec['objects'])} object priors.",
        )

    @staticmethod
    def _physics_for(obj: dict[str, Any]) -> dict[str, Any]:
        material = obj.get("material", "plastic")
        priors = PHYSICS_PRIORS.get(material, PHYSICS_PRIORS["plastic"])
        mass = obj.get("mass_kg", 0.28)
        return {
            "id": obj["id"],
            "name": obj["name"],
            "material": material,
            "mass_kg": mass,
            "friction": obj.get("friction", priors["friction"]),
            "restitution": priors["restitution"],
            "density_kg_m3": priors["density_kg_m3"],
            "provenance": "Cosmos Reason 2 material class -> measured prior",
        }

    @staticmethod
    def _object_pose(obj: dict[str, Any], room: dict[str, Any], index: int) -> dict[str, Any]:
        if "position_m" in obj:
            return {"position_m": obj["position_m"], "rotation_quat": [1, 0, 0, 0]}
        table = room.get("table", {})
        origin = table.get("center_m", [0.0, 0.0, 0.0])
        return {
            "position_m": [
                origin[0] + (-0.18 if index == 0 else 0.16),
                origin[1] + (-0.04 if index == 0 else 0.22),
                origin[2] + 0.045,
            ],
            "rotation_quat": [1, 0, 0, 0],
        }

    @staticmethod
    def _usda(room: dict[str, Any], objects: list[dict[str, Any]]) -> str:
        bounds = room.get("bounds_m", [4.0, 2.5, 3.0])
        table = room.get("table", {})
        table_center = table.get("center_m", [0.0, 0.0, 0.0])
        lines = [
            "#usda 1.0",
            "(",
            '    defaultPrim = "ShowItOnceTwin"',
            "    metersPerUnit = 1",
            '    upAxis = "Y"',
            ")",
            "",
            'def Xform "ShowItOnceTwin"',
            "{",
            f'    def Cube "RoomFloor" {{ size = 1; xformOp:scale = ({bounds[0]}, 0.02, {bounds[2]}) }}',
            f'    def Cube "Table" {{ size = 1; xformOp:scale = (0.9, 0.04, 0.7); '
            f'xformOp:translate = ({table_center[0]}, {table_center[1]}, {table_center[2]}) }}',
        ]
        for index, obj in enumerate(objects):
            ident = re.sub(r"[^A-Za-z0-9_]", "_", obj["name"].title().replace(" ", "_"))
            dims = obj.get("dimensions_m", [0.08, 0.08, 0.10])
            x = table_center[0] + (-0.18 if index == 0 else 0.16)
            y = table_center[1] + (-0.04 if index == 0 else 0.22)
            z = table_center[2] + 0.045 + dims[2] / 2
            lines.append(
                f'    def Cube "{ident}" {{ size = 1; '
                f"xformOp:scale = ({dims[0]}, {dims[2]}, {dims[1]}); "
                f"xformOp:translate = ({x}, {y}, {z}) }}"
            )
        lines.extend(
            [
                '    def DistantLight "Sun" { intensity = 3500; angle = 0.53 }',
                "}",
                "",
            ]
        )
        return "\n".join(lines)
