"""Robot embodiment profiles and the analytic retargeter used by [D].

The first implementation targets the SO-101 because it is the affordable arm in the
build plan. Franka is included for the same object-centric path. Humanoid whole-body
retargeting through SONIC is a later phase and is intentionally not faked here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RobotProfile:
    robot: str
    label: str
    joint_names: tuple[str, ...]
    lower: tuple[float, ...]
    upper: tuple[float, ...]
    gripper_index: int
    description: str

    @property
    def dof(self) -> int:
        return len(self.joint_names)


SO101 = RobotProfile(
    robot="so101",
    label="SO-101",
    joint_names=(
        "shoulder_pan",
        "shoulder_lift",
        "elbow_flex",
        "wrist_flex",
        "wrist_roll",
        "gripper",
    ),
    lower=(-1.9, -1.5, -1.6, -1.8, -2.8, 0.0),
    upper=(1.9, 1.5, 1.6, 1.8, 2.8, 0.058),
    gripper_index=5,
    description="6-DoF printed arm with a parallel jaw gripper",
)

FRANKA = RobotProfile(
    robot="franka",
    label="Franka Emika Panda",
    joint_names=(
        "panda_joint1",
        "panda_joint2",
        "panda_joint3",
        "panda_joint4",
        "panda_joint5",
        "panda_joint6",
        "panda_joint7",
        "panda_finger_joint1",
    ),
    lower=(-2.9, -1.7, -2.9, -3.0, -2.9, -0.01, -2.9, 0.0),
    upper=(2.9, 1.7, 2.9, -0.1, 2.9, 3.7, 2.9, 0.04),
    gripper_index=7,
    description="7-DoF research arm with a parallel jaw gripper",
)

PROFILES = {profile.robot: profile for profile in (SO101, FRANKA)}


def get_profile(robot: str) -> RobotProfile:
    if robot not in PROFILES:
        raise KeyError(
            f"no retarget profile for {robot!r}; available: {', '.join(sorted(PROFILES))}"
        )
    return PROFILES[robot]


def _smooth(values: np.ndarray, window: int = 7) -> np.ndarray:
    if window <= 1:
        return values
    kernel = np.ones(window, dtype=np.float32) / window
    padded = np.pad(values, (window // 2, window // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")[: len(values)]


def retarget_trajectory(
    profile: RobotProfile,
    target_positions: np.ndarray,
    contacts: np.ndarray,
    *,
    fps: float,
) -> np.ndarray:
    """Map an object path to joint positions with a simple, deterministic analytic IK.

    This is a real baseline retargeter for a parallel-jaw arm: the object's path is the
    source of truth, and the arm's joint goals are fitted to that path. Phase 4 replaces
    the analytic fit with the full Isaac Lab IK + trajectory optimizer.
    """
    if target_positions.ndim != 2 or target_positions.shape[1] != 3:
        raise ValueError("target_positions must have shape (T, 3)")
    num_frames = len(target_positions)
    if num_frames < 2:
        raise ValueError("need at least two frames")

    x = target_positions[:, 0]
    y = target_positions[:, 1]
    z = target_positions[:, 2]
    radial = np.sqrt(x * x + y * y)
    pan = np.arctan2(y, x + 1e-6)
    lift = 1.05 - 1.7 * z + 0.22 * radial
    elbow = 0.95 - 1.6 * radial + 0.8 * z
    wrist_flex = 0.55 - 1.2 * (z - 0.08)
    wrist_roll = 0.30 * np.clip((radial - radial.min()) / (np.ptp(radial) + 1e-6), 0, 1)
    finger = np.where(contacts, 0.012, 0.055)

    base = np.stack([pan, lift, elbow, wrist_flex, wrist_roll], axis=1)
    if profile.robot == "franka":
        extra = np.stack(
            [
                -0.25 * pan,
                0.15 * wrist_roll,
            ],
            axis=1,
        )
        base = np.concatenate([base, extra], axis=1)
    base = np.clip(base, np.array(profile.lower[: profile.gripper_index]), np.array(profile.upper[: profile.gripper_index]))
    base = np.stack([_smooth(base[:, index]) for index in range(base.shape[1])], axis=1)
    gripper = finger.reshape(-1, 1)
    joints = np.concatenate([base, gripper], axis=1).astype(np.float32)
    assert joints.shape == (num_frames, profile.dof)
    # Enforce a conservative per-frame change; this is the sim-side velocity gate.
    for index in range(1, num_frames):
        delta = joints[index] - joints[index - 1]
        cap = np.where(
            np.arange(profile.dof) == profile.gripper_index,
            0.02,
            0.18,
        )
        joints[index] = joints[index - 1] + np.clip(delta, -cap, cap)
    return joints
