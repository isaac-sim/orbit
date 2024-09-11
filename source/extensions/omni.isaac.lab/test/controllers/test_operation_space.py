# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Launch Isaac Sim Simulator first."""

from omni.isaac.lab.app import AppLauncher, run_tests

# launch omniverse app
simulation_app = AppLauncher(headless=True).app

"""Rest everything follows."""

import torch
import unittest

import omni.isaac.core.utils.prims as prim_utils
import omni.isaac.core.utils.stage as stage_utils
from omni.isaac.cloner import GridCloner

import omni.isaac.lab.sim as sim_utils
from omni.isaac.lab.assets import Articulation
from omni.isaac.lab.controllers import OperationSpaceController, OperationSpaceControllerCfg
from omni.isaac.lab.utils.math import compute_pose_error, subtract_frame_transforms, \
    quat_rotate_inverse, combine_frame_transforms, apply_delta_pose
from omni.isaac.lab.markers import VisualizationMarkers
from omni.isaac.lab.markers.config import FRAME_MARKER_CFG
from omni.isaac.lab.sensors import ContactSensorCfg, ContactSensor

##
# Pre-defined configs
##
from omni.isaac.lab_assets import FRANKA_PANDA_CFG  # isort:skip


class TestOperationSpaceController(unittest.TestCase):
    """Test fixture for checking that differential IK controller tracks commands properly."""

    def setUp(self):
        """Create a blank new stage for each test."""
        # Wait for spawning
        stage_utils.create_new_stage()
        # Constants
        self.num_envs = 16
        # Load kit helper
        sim_cfg = sim_utils.SimulationCfg(dt=0.01)
        self.sim = sim_utils.SimulationContext(sim_cfg)
        # TODO: Remove this once we have a better way to handle this.
        self.sim._app_control_on_stop_handle = None

        # Create a ground plane
        cfg = sim_utils.GroundPlaneCfg()
        cfg.func("/World/GroundPlane", cfg)

        # Markers
        frame_marker_cfg = FRAME_MARKER_CFG.copy()
        frame_marker_cfg.markers["frame"].scale = (0.1, 0.1, 0.1)
        self.ee_marker = VisualizationMarkers(frame_marker_cfg.replace(prim_path="/Visuals/ee_current"))
        self.goal_marker = VisualizationMarkers(frame_marker_cfg.replace(prim_path="/Visuals/ee_goal"))

        light_cfg = sim_utils.DistantLightCfg(intensity=5.0, exposure=10.0)
        light_cfg.func("/Light", light_cfg, translation=[0, 0, 1],)

        # Create interface to clone the scene
        cloner = GridCloner(spacing=2.0)
        cloner.define_base_env("/World/envs")
        self.env_prim_paths = cloner.generate_paths("/World/envs/env", self.num_envs)
        # create source prim
        prim_utils.define_prim(self.env_prim_paths[0], "Xform")
        # clone the env xform
        self.env_origins = cloner.clone(
            source_prim_path=self.env_prim_paths[0],
            prim_paths=self.env_prim_paths,
            replicate_physics=True,
        )

        self.robot_cfg = FRANKA_PANDA_CFG.replace(prim_path="/World/envs/env_.*/Robot")
        self.robot_cfg.actuators["panda_shoulder"].stiffness = 0.0
        self.robot_cfg.actuators["panda_shoulder"].damping = 0.0
        self.robot_cfg.actuators["panda_forearm"].stiffness = 0.0
        self.robot_cfg.actuators["panda_forearm"].damping = 0.0
        self.robot_cfg.spawn.rigid_props.disable_gravity = True

        # Define the ContactSensor
        self.contact_forces = None

        ee_goal_abs_pos_set = torch.tensor([
            [0.5, 0.5, 0.7],
            [0.5, -0.4, 0.6],
            [0.5, 0, 0.5],
        ], device=self.sim.device)
        ee_goal_abs_quad_set = torch.tensor([
            [0.707, 0.0, 0.707, 0.0],
            [0.707, 0.707, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ], device=self.sim.device)
        ee_goal_rel_pos_set = torch.tensor([
            [0.2, 0.0, 0.0],
            [0.2, 0.2, 0.0],
            [0.2, 0.2, -0.2],
        ], device=self.sim.device)
        ee_goal_rel_angleaxis_set = torch.tensor([
            [0.0, torch.pi / 2, 0.0],  # for [0.707, 0, 0.707, 0]
            [torch.pi / 2, 0.0, 0.0],  # for [0.707, 0.707, 0, 0]
            [torch.pi, 0.0, 0.0],  # for [0.0, 1.0, 0, 0]
        ], device=self.sim.device)
        ee_goal_abs_wrench_set = torch.tensor([
            [0.0, 0.0, 10.0, 0.0, -1.0, 0.0],
            [0.0, 10.0, 0.0, 0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        ], device=self.sim.device)
        kp_set = torch.tensor([
            [500.0, 500.0, 500.0, 500.0, 500.0, 500.0],
            [600.0, 600.0, 600.0, 600.0, 600.0, 600.0],
            [400.0, 400.0, 400.0, 400.0, 400.0, 400.0],
        ], device=self.sim.device)
        d_ratio_set = torch.tensor([
            [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            [1.1, 1.1, 1.1, 1.1, 1.1, 1.1],
            [0.9, 0.9, 0.9, 0.9, 0.9, 0.9],
        ], device=self.sim.device)
        ee_goal_hybrid_set = torch.tensor([
            [0.6, 0.2, 0.5, 0.0, 0.707, 0.0, 0.707, 10.0, 10.0, 10.0, 0.0, 0.0, 0.0],
            [0.6, -0.3, 0.6, 0.0, 0.707, 0.0, 0.707, 10.0, 10.0, 10.0, 0.0, 0.0, 0.0],
            [0.6, -0.1, 0.8, 0.0, 0.5774, 0.0, 0.8165, 10.0, 10.0, 10.0, 0.0, 0.0, 0.0],
        ], device=self.sim.device)

        # Define goals for the arm [xyz]
        self.target_abs_pos_set = ee_goal_abs_pos_set.clone()
        # Define goals for the arm [xyz + quat_wxyz]
        self.target_abs_pose_set = torch.cat([ee_goal_abs_pos_set, ee_goal_abs_quad_set], dim=-1)
        # Define goals for the arm [xyz]
        self.target_rel_pos_set = ee_goal_rel_pos_set.clone()
        # Define goals for the arm [xyz + angle-axis]
        self.target_rel_pose_b_set = torch.cat([ee_goal_rel_pos_set, ee_goal_rel_angleaxis_set], dim=-1)
        # Define goals for the arm [force_xyz + torque_xyz]
        self.target_abs_wrench_set = ee_goal_abs_wrench_set.clone()
        # Define goals for the arm [xyz + quat_wxyz] and variable kp [kp_xyz + kp_rot_xyz]
        self.target_abs_pose_variable_kp_set = torch.cat([self.target_abs_pose_set, kp_set], dim=-1)
        # Define goals for the arm [xyz + quat_wxyz] and the variable imp. [kp_xyz + kp_rot_xyz + d_xyz + d_rot_xyz]
        self.target_abs_pose_variable_set = torch.cat([self.target_abs_pose_set, kp_set, d_ratio_set], dim=-1)
        # Define goals for the arm pose [xyz + quat_wxyz] and wrench [force_xyz + torque_xyz]
        self.target_hybrid_set = ee_goal_hybrid_set.clone()
        # Define goals for the arm pose, and wrench, and kp
        self.target_hybrid_variable_kp_set = torch.cat([self.target_hybrid_set, kp_set * 0.25], dim=-1)

    def tearDown(self):
        """Stops simulator after each test."""
        # stop simulation
        self.sim.stop()
        self.sim.clear()  # FIXME: This hangs the test for some reason when LIVESTREAM is not enabled.
        self.sim.clear_all_callbacks()
        self.sim.clear_instance()

    """
    Test fixtures.
    """

    def test_franka_pose_abs_fixed_impedance_without_inertial_compensation(self):
        """Test absolute pose control with fixed impedance and without inertial compensation."""
        robot = Articulation(cfg=self.robot_cfg)
        opc_cfg = OperationSpaceControllerCfg(command_types=["pose_abs"], impedance_mode="fixed",
                                              inertial_compensation=False,
                                              gravity_compensation=False,
                                              stiffness=[400.0, 400.0, 400.0, 100.0, 100.0, 100.0],
                                              damping_ratio=[5.0, 5.0, 5.0, 0.001, 0.001, 0.001])
        opc = OperationSpaceController(opc_cfg, num_envs=self.num_envs, device=self.sim.device)

        self._run_op_space_controller(robot, opc, "panda_hand", ["panda_joint.*"], self.target_abs_pose_set)

    def test_franka_pose_abs_fixed_impedance_with_decoupled_inertial_compensation(self):
        """Test absolute pose control with fixed impedance and decoupled inertial compensation."""
        robot = Articulation(cfg=self.robot_cfg)
        opc_cfg = OperationSpaceControllerCfg(command_types=["pose_abs"], impedance_mode="fixed",
                                              inertial_compensation=True,
                                              uncouple_motion_wrench=True,
                                              gravity_compensation=False,
                                              stiffness=1000.0, damping_ratio=1.0)
        opc = OperationSpaceController(opc_cfg, num_envs=self.num_envs, device=self.sim.device)

        self._run_op_space_controller(robot, opc, "panda_hand", ["panda_joint.*"], self.target_abs_pose_set)

    def test_franka_pose_abs_fixed_impedance_with_full_inertial_and_gravity_compensation(self):
        """Test absolute pose control with fixed impedance, full inertial and gravity compensation."""
        self.robot_cfg.spawn.rigid_props.disable_gravity = False
        robot = Articulation(cfg=self.robot_cfg)
        opc_cfg = OperationSpaceControllerCfg(command_types=["pose_abs"], impedance_mode="fixed",
                                              inertial_compensation=True,
                                              uncouple_motion_wrench=False,
                                              gravity_compensation=True,
                                              stiffness=500.0, damping_ratio=1.0)
        opc = OperationSpaceController(opc_cfg, num_envs=self.num_envs, device=self.sim.device)

        self._run_op_space_controller(robot, opc, "panda_hand", ["panda_joint.*"], self.target_abs_pose_set)

    def test_franka_pose_abs_fixed_impedance_with_full_inertial_compensation(self):
        """Test absolute pose control with fixed impedance and full inertial compensation."""
        robot = Articulation(cfg=self.robot_cfg)
        opc_cfg = OperationSpaceControllerCfg(command_types=["pose_abs"], impedance_mode="fixed",
                                              inertial_compensation=True,
                                              uncouple_motion_wrench=False,
                                              gravity_compensation=False,
                                              stiffness=500.0, damping_ratio=1.0)
        opc = OperationSpaceController(opc_cfg, num_envs=self.num_envs, device=self.sim.device)

        self._run_op_space_controller(robot, opc, "panda_hand", ["panda_joint.*"], self.target_abs_pose_set)

    def test_franka_pose_rel_fixed_impedance_with_full_inertial_compensation(self):
        """Test relative pose control with fixed impedance and full inertial compensation."""
        robot = Articulation(cfg=self.robot_cfg)
        opc_cfg = OperationSpaceControllerCfg(command_types=["pose_rel"], impedance_mode="fixed",
                                              inertial_compensation=True,
                                              uncouple_motion_wrench=False,
                                              gravity_compensation=False,
                                              stiffness=500.0, damping_ratio=1.0)
        opc = OperationSpaceController(opc_cfg, num_envs=self.num_envs, device=self.sim.device)

        self._run_op_space_controller(robot, opc, "panda_hand", ["panda_joint.*"], self.target_rel_pose_b_set)

    def test_franka_position_abs_fixed_impedance_with_full_inertial_compensation(self):
        """Test absolute position control with fixed impedance and full inertial compensation."""
        robot = Articulation(cfg=self.robot_cfg)
        opc_cfg = OperationSpaceControllerCfg(command_types=["position_abs"], impedance_mode="fixed",
                                              inertial_compensation=True,
                                              uncouple_motion_wrench=False,
                                              gravity_compensation=False,
                                              stiffness=500.0, damping_ratio=1.0)
        opc = OperationSpaceController(opc_cfg, num_envs=self.num_envs, device=self.sim.device)

        self._run_op_space_controller(robot, opc, "panda_hand", ["panda_joint.*"], self.target_abs_pos_set)

    def test_franka_position_rel_fixed_impedance_with_full_inertial_compensation(self):
        """Test relative position control with fixed impedance and full inertial compensation."""
        robot = Articulation(cfg=self.robot_cfg)
        opc_cfg = OperationSpaceControllerCfg(command_types=["position_rel"], impedance_mode="fixed",
                                              inertial_compensation=True,
                                              uncouple_motion_wrench=False,
                                              gravity_compensation=False,
                                              stiffness=500.0, damping_ratio=1.0)
        opc = OperationSpaceController(opc_cfg, num_envs=self.num_envs, device=self.sim.device)

        self._run_op_space_controller(robot, opc, "panda_hand", ["panda_joint.*"], self.target_rel_pos_set)

    def test_franka_pose_abs_variable_kp_impedance_with_full_inertial_compensation(self):
        """Test absolute pose control with variable kp impedance and full inertial compensation."""
        robot = Articulation(cfg=self.robot_cfg)
        opc_cfg = OperationSpaceControllerCfg(command_types=["pose_abs"], impedance_mode="variable_kp",
                                              inertial_compensation=True,
                                              uncouple_motion_wrench=False,
                                              gravity_compensation=False,
                                              stiffness=500.0, damping_ratio=1.0)
        opc = OperationSpaceController(opc_cfg, num_envs=self.num_envs, device=self.sim.device)

        self._run_op_space_controller(robot, opc, "panda_hand", ["panda_joint.*"], self.target_abs_pose_variable_kp_set)

    def test_franka_pose_abs_variable_impedance_with_full_inertial_compensation(self):
        """Test absolute pose control with variable impedance and full inertial compensation."""
        robot = Articulation(cfg=self.robot_cfg)
        opc_cfg = OperationSpaceControllerCfg(command_types=["pose_abs"], impedance_mode="variable",
                                              inertial_compensation=True,
                                              uncouple_motion_wrench=False,
                                              gravity_compensation=False,
                                              stiffness=500.0, damping_ratio=1.0)
        opc = OperationSpaceController(opc_cfg, num_envs=self.num_envs, device=self.sim.device)

        self._run_op_space_controller(robot, opc, "panda_hand", ["panda_joint.*"], self.target_abs_pose_variable_set)

    def test_franka_wrench_abs_open_loop(self):
        """Test open loop absolute force control."""
        robot = Articulation(cfg=self.robot_cfg)

        obstacle_spawn_cfg = sim_utils.CuboidCfg(
            size=(0.7, 0.7, 0.01),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(1.0, 0.0, 0.0), opacity=0.1),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            activate_contact_sensors=True,
        )
        obstacle_spawn_cfg.func(
            "/World/envs/env_.*/obstacle1", obstacle_spawn_cfg, translation=(0.2, 0.0, 0.93), orientation=(0.9848, 0.0, -0.1736, 0.0)
        )
        obstacle_spawn_cfg.func(
            "/World/envs/env_.*/obstacle2", obstacle_spawn_cfg, translation=(0.2, 0.35, 0.7), orientation=(0.707, 0.707, 0.0, 0.0)
        )
        obstacle_spawn_cfg.func(
            "/World/envs/env_.*/obstacle3", obstacle_spawn_cfg, translation=(0.55, 0.0, 0.7), orientation=(0.707, 0.0, 0.707, 0.0)
        )
        contact_forces_cfg = ContactSensorCfg(
            prim_path="/World/envs/env_.*/obstacle.*", update_period=0.0, history_length=50, debug_vis=False, force_threshold=0.1
        )
        self.contact_forces = ContactSensor(contact_forces_cfg)

        opc_cfg = OperationSpaceControllerCfg(command_types=["wrench_abs"],
                                              impedance_mode="fixed",
                                              stiffness=500.0,
                                              damping_ratio=1.0,
                                              motion_control_axes=[0, 0, 0, 0, 0, 0],
                                              wrench_control_axes=[1, 1, 1, 1, 1, 1],
                                              gravity_compensation=False)
        opc = OperationSpaceController(opc_cfg, num_envs=self.num_envs, device=self.sim.device)

        self._run_op_space_controller(robot, opc, "panda_hand", ["panda_joint.*"], self.target_abs_wrench_set)
        self.contact_forces = None  # Make contact_forces None after the test otherwise other tests give warning

    def test_franka_wrench_abs_closed_loop(self):
        """Test closed loop absolute force control."""
        robot = Articulation(cfg=self.robot_cfg)

        obstacle_spawn_cfg = sim_utils.CuboidCfg(
            size=(0.7, 0.7, 0.01),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(1.0, 0.0, 0.0), opacity=0.1),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            activate_contact_sensors=True,
        )
        obstacle_spawn_cfg.func(
            "/World/envs/env_.*/obstacle1", obstacle_spawn_cfg, translation=(0.2, 0.0, 0.93), orientation=(0.9848, 0.0, -0.1736, 0.0)
        )
        obstacle_spawn_cfg.func(
            "/World/envs/env_.*/obstacle2", obstacle_spawn_cfg, translation=(0.2, 0.35, 0.7), orientation=(0.707, 0.707, 0.0, 0.0)
        )
        obstacle_spawn_cfg.func(
            "/World/envs/env_.*/obstacle3", obstacle_spawn_cfg, translation=(0.55, 0.0, 0.7), orientation=(0.707, 0.0, 0.707, 0.0)
        )
        contact_forces_cfg = ContactSensorCfg(
            prim_path="/World/envs/env_.*/obstacle.*", update_period=0.0, history_length=2, debug_vis=False, force_threshold=0.1
        )
        self.contact_forces = ContactSensor(contact_forces_cfg)

        opc_cfg = OperationSpaceControllerCfg(command_types=["wrench_abs"],
                                              impedance_mode="fixed",
                                              stiffness=500.0,
                                              damping_ratio=1.0,
                                              wrench_stiffness=[0.2, 0.2, 0.2, 0.0, 0.0, 0.0],  # Zero torque feedback as we cannot contact torque
                                              motion_control_axes=[0, 0, 0, 0, 0, 0],
                                              wrench_control_axes=[1, 1, 1, 1, 1, 1],
                                              gravity_compensation=False)
        opc = OperationSpaceController(opc_cfg, num_envs=self.num_envs, device=self.sim.device)

        self._run_op_space_controller(robot, opc, "panda_hand", ["panda_joint.*"], self.target_abs_wrench_set)
        self.contact_forces = None  # Make contact_forces None after the test otherwise other tests give warning

    def test_franka_hybrid_fixed_impedance_with_full_inertial_compensation(self):
        """Test hybrid control with fixed impedance and full inertial compensation."""
        robot = Articulation(cfg=self.robot_cfg)

        obstacle_spawn_cfg = sim_utils.CuboidCfg(
            size=(1.0, 1.0, 0.01),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(1.0, 0.0, 0.0), opacity=0.1),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            activate_contact_sensors=True,
        )
        obstacle_spawn_cfg.func(
            "/World/envs/env_.*/obstacle1", obstacle_spawn_cfg, translation=(self.target_hybrid_set[0, 0] + 0.05, 0.0, 0.7), orientation=(0.707, 0.0, 0.707, 0.0)
        )
        contact_forces_cfg = ContactSensorCfg(
            prim_path="/World/envs/env_.*/obstacle.*", update_period=0.0, history_length=2, debug_vis=False, force_threshold=0.1
        )
        self.contact_forces = ContactSensor(contact_forces_cfg)

        opc_cfg = OperationSpaceControllerCfg(command_types=["pose_abs", "wrench_abs"],
                                              impedance_mode="fixed",
                                              inertial_compensation=True,
                                              uncouple_motion_wrench=False,
                                              gravity_compensation=False,
                                              stiffness=100.0, damping_ratio=1.0,
                                              wrench_stiffness=[0.2, 0.0, 0.0, 0.0, 0.0, 0.0],
                                              motion_control_axes=[0, 1, 1, 1, 1, 1],
                                              wrench_control_axes=[1, 0, 0, 0, 0, 0],
                                              )
        opc = OperationSpaceController(opc_cfg, num_envs=self.num_envs, device=self.sim.device)

        self._run_op_space_controller(robot, opc, "panda_leftfinger", ["panda_joint.*"], self.target_hybrid_set)
        self.contact_forces = None  # Make contact_forces None after the test otherwise other tests give warning

    def test_franka_hybrid_variable_kp_impedance_with_full_inertial_compensation(self):
        """Test hybrid control with variable kp impedance and full inertial compensation."""
        robot = Articulation(cfg=self.robot_cfg)

        obstacle_spawn_cfg = sim_utils.CuboidCfg(
            size=(1.0, 1.0, 0.01),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(1.0, 0.0, 0.0), opacity=0.1),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            activate_contact_sensors=True,
        )
        obstacle_spawn_cfg.func(
            "/World/envs/env_.*/obstacle1", obstacle_spawn_cfg, translation=(self.target_hybrid_set[0, 0] + 0.05, 0.0, 0.7), orientation=(0.707, 0.0, 0.707, 0.0)
        )
        contact_forces_cfg = ContactSensorCfg(
            prim_path="/World/envs/env_.*/obstacle.*", update_period=0.0, history_length=2, debug_vis=False, force_threshold=0.1
        )
        self.contact_forces = ContactSensor(contact_forces_cfg)

        opc_cfg = OperationSpaceControllerCfg(command_types=["pose_abs", "wrench_abs"],
                                              impedance_mode="variable_kp",
                                              inertial_compensation=True,
                                              uncouple_motion_wrench=False,
                                              gravity_compensation=False,
                                              stiffness=100.0, damping_ratio=1.2,
                                              wrench_stiffness=[0.1, 0.0, 0.0, 0.0, 0.0, 0.0],
                                              motion_control_axes=[0, 1, 1, 1, 1, 1],
                                              wrench_control_axes=[1, 0, 0, 0, 0, 0],
                                              )
        opc = OperationSpaceController(opc_cfg, num_envs=self.num_envs, device=self.sim.device)

        self._run_op_space_controller(robot, opc, "panda_leftfinger", ["panda_joint.*"], self.target_hybrid_variable_kp_set)
        self.contact_forces = None  # Make contact_forces None after the test otherwise other tests give warning

    """
    Helper functions
    """

    def _run_op_space_controller(
        self,
        robot: Articulation,
        opc: OperationSpaceController,
        ee_frame_name: str,
        arm_joint_names: list[str],
        target_set: torch.tensor,
    ):
        # Initialize the masks for evaluating target convergence according to selection matrices
        self.pos_mask = torch.tensor(opc.cfg.motion_control_axes[:3], device=self.sim.device).view(1, 3)
        self.rot_mask = torch.tensor(opc.cfg.motion_control_axes[3:], device=self.sim.device).view(1, 3)
        self.wrench_mask = torch.tensor(opc.cfg.wrench_control_axes, device=self.sim.device).view(1, 6)
        self.force_mask = self.wrench_mask[:, 0:3]  # Take only the force components as we can measure only these

        # Define simulation stepping
        sim_dt = self.sim.get_physics_dt()
        # Play the simulator
        self.sim.reset()

        # Obtain the frame index of the end-effector
        ee_frame_idx = robot.find_bodies(ee_frame_name)[0][0]
        # Obtain joint indices
        arm_joint_ids = robot.find_joints(arm_joint_names)[0]

        # Update existing buffers
        # Note: We need to update buffers before the first step for the controller.
        robot.update(dt=sim_dt)

        # get the updated states
        jacobian, mass_matrix, gravity, ee_pose_b, ee_vel_b, root_pose_w, ee_pose_w, ee_force_w = self._update_states(robot, ee_frame_idx, arm_joint_ids)

        # Track the given target command
        current_goal_idx = 0  # Current goal index for the arm
        ee_target_b = torch.zeros(self.num_envs, opc.action_dim, device=self.sim.device)  # Generic target command, which can be pose, position, force, etc.
        ee_target_pose_b = torch.zeros(self.num_envs, 7, device=self.sim.device)  # Target pose in the body frame
        ee_target_pose_w = torch.zeros(self.num_envs, 7, device=self.sim.device)  # Target pose in the world frame (for marker)

        # Set joint efforts to zero
        zero_joint_efforts = torch.zeros(self.num_envs, robot.num_joints, device=self.sim.device)
        joint_efforts = torch.zeros(self.num_envs, len(arm_joint_ids), device=self.sim.device)

        # Now we are ready!
        for count in range(1501):
            # reset every 500 steps
            if count % 500 == 0:
                # check that we converged to the goal
                if count > 0:
                    self._check_convergence(opc, ee_pose_b, ee_target_pose_b, ee_force_w, ee_target_b)
                # reset joint state to default
                default_joint_pos = robot.data.default_joint_pos.clone()
                default_joint_vel = robot.data.default_joint_vel.clone()
                robot.write_joint_state_to_sim(default_joint_pos, default_joint_vel)
                robot.set_joint_effort_target(zero_joint_efforts)  # Set zero torques in the initial step
                robot.write_data_to_sim()
                robot.reset()
                # reset target pose
                robot.update(sim_dt)
                _, _, _, ee_pose_b, _, _, _, _ = self._update_states(robot, ee_frame_idx, arm_joint_ids)  # at reset, the jacobians are not updated to the latest state
                ee_target_b, ee_target_pose_b, ee_target_pose_w, current_goal_idx = self._update_target(opc, root_pose_w, ee_pose_b, target_set, current_goal_idx)
                # set the opc command
                opc.reset()
                opc.set_command(ee_target_b, ee_pose_b)
            else:
                # get the updated states
                jacobian, mass_matrix, gravity, ee_pose_b, ee_vel_b, root_pose_w, ee_pose_w, ee_force_w = self._update_states(robot, ee_frame_idx, arm_joint_ids)
                # compute the joint commands
                joint_efforts = opc.compute(jacobian=jacobian, ee_pose=ee_pose_b, ee_vel=ee_vel_b, ee_force=ee_force_w, mass_matrix=mass_matrix, gravity=gravity)
                robot.set_joint_effort_target(joint_efforts, joint_ids=arm_joint_ids)
                robot.write_data_to_sim()

            # update marker positions
            self.ee_marker.visualize(ee_pose_w[:, 0:3], ee_pose_w[:, 3:7])
            self.goal_marker.visualize(ee_target_pose_w[:, 0:3], ee_target_pose_w[:, 3:7])

            # perform step
            self.sim.step(render=False)
            # update buffers
            robot.update(sim_dt)

    def _update_states(
        self,
        robot: Articulation,
        ee_frame_idx: int,
        arm_joint_ids: list[int],
    ):
        ee_jacobi_idx = ee_frame_idx - 1
        # obtain quantities from simulation
        jacobian = robot.root_physx_view.get_jacobians()[:, ee_jacobi_idx, :, arm_joint_ids]
        mass_matrix = robot.root_physx_view.get_mass_matrices()[:, arm_joint_ids, :][:, :, arm_joint_ids]
        gravity = robot.root_physx_view.get_generalized_gravity_forces()[:, arm_joint_ids]

        # Compute current pose of the end-effector
        ee_pose_w = robot.data.body_state_w[:, ee_frame_idx, 0:7]
        root_pose_w = robot.data.root_state_w[:, 0:7]
        ee_pos_b, ee_quat_b = subtract_frame_transforms(
            root_pose_w[:, 0:3], root_pose_w[:, 3:7], ee_pose_w[:, 0:3], ee_pose_w[:, 3:7]
        )
        ee_pose_b = torch.cat([ee_pos_b, ee_quat_b], dim=-1)

        # Compute the current velocity of the end-effector
        ee_vel_w = robot.data.body_vel_w[:, ee_frame_idx, :]  # Extract end-effector velocity in the world frame
        root_vel_w = robot.data.root_vel_w  # Extract root velocity in the world frame
        relative_vel_w = ee_vel_w - root_vel_w  # Compute the relative velocity in the world frame
        ee_lin_vel_b = quat_rotate_inverse(robot.data.root_quat_w, relative_vel_w[:, 0:3])  # From world to root frame
        ee_ang_vel_b = quat_rotate_inverse(robot.data.root_quat_w, relative_vel_w[:, 3:6])
        ee_vel_b = torch.cat([ee_lin_vel_b, ee_ang_vel_b], dim=-1)

        # Calculate the contact force
        ee_force_w = torch.zeros(self.num_envs, 3, device=self.sim.device)
        if self.contact_forces is not None:  # Only modify if it exist
            sim_dt = self.sim.get_physics_dt()
            self.contact_forces.update(sim_dt)  # update contact sensor
            # Calculate the contact force by averaging over last four time steps (i.e., to smoothen) and
            # taking the max of three surfaces as only one should be the contact of interest
            ee_force_w, _ = torch.max(torch.mean(self.contact_forces.data.net_forces_w_history, dim=1), dim=1)

        return jacobian, mass_matrix, gravity, ee_pose_b, ee_vel_b, root_pose_w, ee_pose_w, ee_force_w

    def _update_target(
        self,
        opc: OperationSpaceController,
        root_pose_w: torch.tensor,
        ee_pose_b: torch.tensor,
        target_set: torch.tensor,
        current_goal_idx: int,
    ):
        # update the ee desired command
        ee_target_b = torch.zeros(self.num_envs, opc.action_dim, device=self.sim.device)
        ee_target_b[:] = target_set[current_goal_idx]

        # update the ee desired pose
        ee_target_pose_b = torch.zeros(self.num_envs, 7, device=self.sim.device)
        for command_type in opc.cfg.command_types:
            if command_type == "pose_abs":
                ee_target_pose_b[:] = ee_target_b[:, :7]
            elif command_type == "pose_rel":
                ee_target_pose_b[:, 0:3], ee_target_pose_b[:, 3:7] = apply_delta_pose(ee_pose_b[:, :3], ee_pose_b[:, 3:], ee_target_b[:, :7])
            elif command_type == "position_abs":
                ee_target_pose_b[:, 0:3] = ee_target_b[:, :3]
            elif command_type == "position_rel":
                ee_target_pose_b[:, 0:3] = ee_pose_b[:, 0:3] + ee_target_b[:, :3]
            elif command_type == "wrench_abs":
                pass  # ee_target_pose_b could stay at the robot base for force control, what matters is ee_target_b
            else:
                raise ValueError("Undefined command_type within _update_target().")

        # update the target desired pose in world frame (for marker)
        ee_target_pos_w, ee_target_quat_w = combine_frame_transforms(
            root_pose_w[:, 0:3], root_pose_w[:, 3:7], ee_target_pose_b[:, 0:3], ee_target_pose_b[:, 3:7]
        )
        ee_target_pose_w = torch.cat([ee_target_pos_w, ee_target_quat_w], dim=-1)

        next_goal_idx = (current_goal_idx + 1) % len(target_set)

        return ee_target_b, ee_target_pose_b, ee_target_pose_w, next_goal_idx

    def _check_convergence(
        self,
        opc: OperationSpaceController,
        ee_pose_b: torch.tensor,
        ee_target_pose_b: torch.tensor,
        ee_force_w: torch.tensor,
        ee_target_b: torch.tensor,
    ):
        cmd_idx = 0
        for command_type in opc.cfg.command_types:
            if command_type == "pose_abs" :
                pos_error, rot_error = compute_pose_error(
                    ee_pose_b[:, 0:3], ee_pose_b[:, 3:7], ee_target_pose_b[:, 0:3], ee_target_pose_b[:, 3:7]
                )
                pos_error_norm = torch.norm(pos_error * self.pos_mask, dim=-1)
                rot_error_norm = torch.norm(rot_error * self.rot_mask, dim=-1)
                # desired error (zer)
                des_error = torch.zeros_like(pos_error_norm)
                # check convergence
                torch.testing.assert_close(pos_error_norm, des_error, rtol=0.0, atol=0.1)
                torch.testing.assert_close(rot_error_norm, des_error, rtol=0.0, atol=0.1)
                cmd_idx += 7
            elif command_type == "pose_rel":
                pos_error, rot_error = compute_pose_error(
                    ee_pose_b[:, 0:3], ee_pose_b[:, 3:7], ee_target_pose_b[:, 0:3], ee_target_pose_b[:, 3:7]
                )
                pos_error_norm = torch.norm(pos_error * self.pos_mask, dim=-1)
                rot_error_norm = torch.norm(rot_error * self.rot_mask, dim=-1)
                # desired error (zer)
                des_error = torch.zeros_like(pos_error_norm)
                # check convergence
                torch.testing.assert_close(pos_error_norm, des_error, rtol=0.0, atol=0.1)
                torch.testing.assert_close(rot_error_norm, des_error, rtol=0.0, atol=0.1)
                cmd_idx += 6
            elif command_type == "position_abs" or command_type == "position_rel":
                pos_error = ee_pose_b[:, 0:3] - ee_target_pose_b[:, 0:3]
                pos_error_norm = torch.norm(pos_error * self.pos_mask, dim=-1)
                # desired error (zer)
                des_error = torch.zeros_like(pos_error_norm)
                # check convergence
                torch.testing.assert_close(pos_error_norm, des_error, rtol=0.0, atol=0.1)
                cmd_idx += 3
            elif command_type == "wrench_abs":
                force_error = ee_force_w - ee_target_b[:, cmd_idx:cmd_idx + 3]
                force_error_norm = torch.norm(force_error * self.force_mask, dim=-1)  # ignore torque part as we cannot measure it
                des_error = torch.zeros_like(force_error_norm)
                # check convergence: big threshold here as the force control is not precise when the robot moves
                torch.testing.assert_close(force_error_norm, des_error, rtol=0.0, atol=1.0)
                cmd_idx += 6
            else:
                raise ValueError("Undefined command_type within _check_convergence().")


if __name__ == "__main__":
    run_tests()
