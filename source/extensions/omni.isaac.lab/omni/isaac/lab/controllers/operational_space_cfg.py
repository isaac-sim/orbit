# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

from collections.abc import Sequence
from dataclasses import MISSING

from omni.isaac.lab.utils import configclass

from .operational_space import OperationalSpaceController


@configclass
class OperationalSpaceControllerCfg:
    """Configuration for operational-space controller."""

    class_type: type = OperationalSpaceController
    """The associated controller class."""

    target_types: Sequence[str] = MISSING
    """Type of task-space targets.

    It has two sub-strings joined by underscore:
        - type of task-space target: "pose", "wrench"
        - reference for the task-space targets: "abs" (absolute), "rel" (relative, only for pose)
    """

    impedance_mode: str = "fixed"
    """Type of gains for motion control: "fixed", "variable", "variable_kp"."""

    uncouple_motion_wrench: bool = False
    """Whether to decouple the wrench computation from task-space pose (motion) error."""

    motion_control_axes: Sequence[int] = (1, 1, 1, 1, 1, 1)
    """Motion direction to control. Mark as 0/1 for each axis."""
    wrench_control_axes: Sequence[int] = (0, 0, 0, 0, 0, 0)
    """Wrench direction to control. Mark as 0/1 for each axis."""

    inertial_compensation: bool = False
    """Whether to perform inertial compensation for motion control (inverse dynamics)."""

    gravity_compensation: bool = False
    """Whether to perform gravity compensation."""

    stiffness: float | Sequence[float] = (100.0, 100.0, 100.0, 100.0, 100.0, 100.0)
    """The positional gain for determining wrenches based on task-space pose error."""

    damping_ratio: float | Sequence[float] = (1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    """The damping ratio is used in-conjunction with positional gain to compute wrenches
    based on task-space velocity error.

    The following math operation is performed for computing velocity gains:
        :math:`d_gains = 2 * sqrt(p_gains) * damping_ratio`.
    """

    stiffness_limits: tuple[float, float] = (0, 1000)
    """Minimum and maximum values for positional gains.

    Note: Used only when :obj:`impedance_mode` is "variable" or "variable_kp".
    """

    damping_ratio_limits: tuple[float, float] = (0, 100)
    """Minimum and maximum values for damping ratios used to compute velocity gains.

    Note: Used only when :obj:`impedance_mode` is "variable".
    """

    wrench_stiffness: float | Sequence[float] = None
    """The positional gain for determining wrenches for closed-loop force control.

    If obj:`None`, then open-loop control of desired wrench is performed.

    Note: since only the linear forces could be measured at the moment,
    only the first three elements are used.
    """