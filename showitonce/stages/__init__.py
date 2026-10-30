"""Stage registry. The DAG order is the build-plan order."""

from __future__ import annotations

from .base import StageContext, StageError, StageHandler, StageResult
from .deploy import DeployStage
from .evaluate import EvaluateStage
from .extract import ExtractStage
from .library import LibraryStage
from .multiply import MultiplyStage
from .reconstruct import ReconstructStage
from .retarget import RetargetStage
from .train import TrainStage
from .understand import UnderstandStage
from .verify import VerifyStage

__all__ = [
    "StageContext",
    "StageError",
    "StageHandler",
    "StageResult",
    "build_registry",
]

_HANDLERS = (
    UnderstandStage,
    ReconstructStage,
    ExtractStage,
    RetargetStage,
    VerifyStage,
    MultiplyStage,
    TrainStage,
    EvaluateStage,
    DeployStage,
    LibraryStage,
)


def build_registry() -> dict[str, StageHandler]:
    registry = {handler.name: handler for handler in (cls() for cls in _HANDLERS)}
    return registry
