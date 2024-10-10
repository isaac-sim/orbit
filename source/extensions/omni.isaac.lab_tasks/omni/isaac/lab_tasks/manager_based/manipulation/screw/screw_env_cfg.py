# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

from dataclasses import MISSING

import omni.isaac.lab.sim as sim_utils
from omni.isaac.lab.sim.simulation_cfg import PhysxCfg, SimulationCfg
from omni.isaac.lab.assets import ArticulationCfg, AssetBaseCfg, RigidObjectCfg
from omni.isaac.lab.envs import ManagerBasedRLEnvCfg
from omni.isaac.lab.managers import ActionTermCfg as ActionTerm
from omni.isaac.lab.managers import CurriculumTermCfg as CurrTerm
from omni.isaac.lab.managers import EventTermCfg as EventTerm
from omni.isaac.lab.managers import ObservationGroupCfg as ObsGroup
from omni.isaac.lab.managers import ObservationTermCfg as ObsTerm
from omni.isaac.lab.managers import RewardTermCfg as RewTerm
from omni.isaac.lab.managers import SceneEntityCfg
from omni.isaac.lab.managers import TerminationTermCfg as DoneTerm
from omni.isaac.lab.scene import InteractiveSceneCfg
from omni.isaac.lab.sensors import FrameTransformerCfg
from omni.isaac.lab.sensors.frame_transformer.frame_transformer_cfg import OffsetCfg
from omni.isaac.lab.utils import configclass
from omni.isaac.lab.utils.assets import ISAAC_NUCLEUS_DIR
from omni.isaac.lab.utils.noise import AdditiveUniformNoiseCfg as Unoise
from omni.isaac.lab.sim.schemas.schemas_cfg import RigidBodyPropertiesCfg, MassPropertiesCfg
import omni.isaac.lab_tasks.manager_based.manipulation.screw.mdp as mdp
from omni.isaac.lab.markers.visualization_markers import VisualizationMarkersCfg
from omni.isaac.lab.markers.config import FRAME_MARKER_CFG, RED_ARROW_X_MARKER_CFG, DEFORMABLE_TARGET_MARKER_CFG   # isort: skip

##
# Scene definition
##
FRAME_MARKER_SMALL_CFG = FRAME_MARKER_CFG.copy()
FRAME_MARKER_SMALL_CFG.markers["frame"].scale = (0.008, 0.008, 0.008)
PLATE_MARKER_CFG = VisualizationMarkersCfg(
    markers={
        "height": sim_utils.CylinderCfg(
            radius=0.01,
            height=0.001,
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(1.0, 0, 0), opacity=0.5),
            )
    }
)
PLATE_ARROW_CFG = VisualizationMarkersCfg(
    markers={
        # "height": sim_utils.CylinderCfg(
        #     radius=0.01,
        #     height=0.001,
        #     visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(.0, 0, 1), opacity=0.5),
        #     ),
        "frame": sim_utils.UsdFileCfg(
            usd_path=f"{ISAAC_NUCLEUS_DIR}/Props/UIElements/frame_prim.usd",
            scale=(0.008, 0.008, 0.008),
        ),
        # "direction": sim_utils.UsdFileCfg(
        #     usd_path=f"{ISAAC_NUCLEUS_DIR}/Props/UIElements/arrow_x.usd",
        #     scale=(0.015, 0.005, 0.005),
        #     visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(.0, 0.0, 1)),
        # )
    }
)

@configclass
class ScrewSceneCfg(InteractiveSceneCfg):
    """Configuration for the scene with a robotic arm."""

    # world
    ground = AssetBaseCfg(
        prim_path="/World/ground",
        spawn=sim_utils.GroundPlaneCfg(),
        init_state=AssetBaseCfg.InitialStateCfg(pos=(0.0, 0.0, -1.05)),
    )
    origin = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/Origin",
        spawn=sim_utils.SphereCfg(
            radius=1e-3, 
            rigid_props=sim_utils.RigidBodyPropertiesCfg(
                kinematic_enabled=True,
                disable_gravity=True,
            ),
            collision_props=sim_utils.CollisionPropertiesCfg(collision_enabled=True)),
        init_state=RigidObjectCfg.InitialStateCfg(pos=(0.0, 0.0, 0.0)),
    )

    table = AssetBaseCfg(
        prim_path="{ENV_REGEX_NS}/Table",
        spawn=sim_utils.UsdFileCfg(
            usd_path=f"{ISAAC_NUCLEUS_DIR}/Props/Mounts/SeattleLabTable/table_instanceable.usd",
            # usd_path=f"/home/zixuanh/force_tool/assets/table_instanceable.usd",
        ),
        init_state=AssetBaseCfg.InitialStateCfg(pos=(0.55, 0.0, 0.0), rot=(0.70711, 0.0, 0.0, 0.70711)),
    )

    # robots: will be populated by agent env cfg
    robot: ArticulationCfg = MISSING
    # end-effector sensor: will be populated by agent env cfg
    # ee_frame: FrameTransformerCfg = MISSING

    # objects
    nut: RigidObjectCfg = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/Nut",
        spawn=sim_utils.UsdFileCfg(
            usd_path=f"{ISAAC_NUCLEUS_DIR}/Props/Factory/factory_nut_m8_tight/factory_nut_m8_tight.usd",
            # usd_path="/home/zixuanh/force_tool/assets/Factory/factory_nut_m8_tight/factory_nut_m8_tight.usd",
            rigid_props= sim_utils.RigidBodyPropertiesCfg(
            disable_gravity=True, sleep_threshold=0.0, stabilization_threshold=0.0)
        ),
        init_state=RigidObjectCfg.InitialStateCfg(pos=(0.6, 0.0, 0.0065))
    )

    bolt: RigidObjectCfg = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/Bolt",
        spawn=sim_utils.UsdFileCfg(
            # usd_path=f"{ISAAC_NUCLEUS_DIR}/Props/Factory/factory_bolt_m8_tight/factory_bolt_m8_tight.usd",
            usd_path=f"/home/zixuanh/force_tool/assets/Factory/factory_bolt_m8_tight/factory_bolt_m8_tight.usd",
        ),
        init_state=RigidObjectCfg.InitialStateCfg(pos=(0.63, 0.0, 0.0)),
    )

    # lights
    light = AssetBaseCfg(
        prim_path="/World/light",
        spawn=sim_utils.DomeLightCfg(color=(0.75, 0.75, 0.75), intensity=2500.0),
    )
 
    nut_frame= FrameTransformerCfg(
        prim_path="{ENV_REGEX_NS}/Origin",
        debug_vis=True,
        visualizer_cfg=PLATE_ARROW_CFG.replace(prim_path="/Visuals/Nut"),
        target_frames=[
            FrameTransformerCfg.FrameCfg(
                prim_path="{ENV_REGEX_NS}/Nut/factory_nut",
                name="nut",
                offset=OffsetCfg(pos=(0.0, 0.0, 0.011)),
            )
        ])
    
    bolt_frame = FrameTransformerCfg(
        prim_path="{ENV_REGEX_NS}/Origin",
        debug_vis=True,
        visualizer_cfg=PLATE_MARKER_CFG.replace(prim_path="/Visuals/Bolt"),
        target_frames=[
            FrameTransformerCfg.FrameCfg(
                prim_path="{ENV_REGEX_NS}/Bolt/factory_bolt",
                name="bolt_tip",
                offset=OffsetCfg(pos=(0.0, 0.0, 0.0277)),
            ),
            FrameTransformerCfg.FrameCfg(
                prim_path="{ENV_REGEX_NS}/Bolt/factory_bolt",
                name="bolt_bottom",
                offset=OffsetCfg(pos=(0.0, 0.0, 0.012)),
            ),
            
            ]
        )
            

        


##
# MDP settings
##


# @configclass
# class CommandsCfg:
#     """Command terms for the MDP."""

#     ee_pose = mdp.UniformPoseCommandCfg(
#         asset_name="robot",
#         body_name=MISSING,
#         resampling_time_range=(4.0, 4.0),
#         debug_vis=True,
#         ranges=mdp.UniformPoseCommandCfg.Ranges(
#             pos_x=(0.35, 0.65),
#             pos_y=(-0.2, 0.2),
#             pos_z=(0.15, 0.5),
#             roll=(0.0, 0.0),
#             pitch=MISSING,  # depends on end-effector axis
#             yaw=(-3.14, 3.14),
#         ),
#     )


@configclass
class ActionsCfg:
    """Action specifications for the MDP."""

    nut_action: ActionTerm | None = None
    arm_action: ActionTerm | None = None
    gripper_action: ActionTerm | None = None


@configclass
class ObservationsCfg:
    """Observation specifications for the MDP."""

    @configclass
    class PolicyCfg(ObsGroup):
        """Observations for policy group."""

        # observation terms (order preserved)
        # joint_pos = ObsTerm(func=mdp.joint_pos, noise=Unoise(n_min=-0.01, n_max=0.01))
        # joint_vel = ObsTerm(func=mdp.joint_vel, noise=Unoise(n_min=-0.01, n_max=0.01))
        bolt_pose = ObsTerm(func=mdp.root_pos_w, params={"asset_cfg": SceneEntityCfg("bolt")})
        nut_pos = ObsTerm(func=mdp.root_pos_w, params={"asset_cfg": SceneEntityCfg("nut")})
        nut_quat = ObsTerm(func=mdp.root_quat_w, params={"asset_cfg": SceneEntityCfg("nut")})
        nut_lin_vel = ObsTerm(func=mdp.root_lin_vel_w, params={"asset_cfg": SceneEntityCfg("nut")})
        nut_ang_vel = ObsTerm(func=mdp.root_ang_vel_w, params={"asset_cfg": SceneEntityCfg("nut")})
        actions = ObsTerm(func=mdp.last_action)

        def __post_init__(self):
            self.enable_corruption = True
            self.concatenate_terms = True

    # observation groups
    policy: PolicyCfg = PolicyCfg()


@configclass
class EventCfg:
    """Configuration for events."""

    # nut_physics_material = EventTerm(
    #     func=mdp.randomize_rigid_body_material,
    #     mode="startup",
    #     params={
    #         "asset_cfg": SceneEntityCfg("nut"),
    #         "static_friction_range": (0.8, 0.8),
    #         "dynamic_friction_range": (0.6, 0.6),
    #         "restitution_range": (0.0, 0.0),
    #         "num_buckets": 64,
    #     },
    # )

    # bolt_physics_material = EventTerm(
    #     func=mdp.randomize_rigid_body_material,
    #     mode="startup",
    #     params={
    #         "asset_cfg": SceneEntityCfg("bolt"),
    #         "static_friction_range": (0.8, 0.8),
    #         "dynamic_friction_range": (0.6, 0.6),
    #         "restitution_range": (0.0, 0.0),
    #         "num_buckets": 64,
    #     },
    # )

    reset_default = EventTerm(
        func=mdp.reset_scene_to_default,
        mode="reset",
    )

    # reset_robot_joints = EventTerm(
    #     func=mdp.reset_joints_by_scale,
    #     mode="reset",
    #     params={
    #         "position_range": (0.5, 1.5),
    #         "velocity_range": (0.0, 0.0),
    #     },
    # )


@configclass
class RewardsCfg:
    """Reward terms for the MDP."""

    # task terms
    coarse_nut = RewTerm(func=mdp.position_error_forge, 
                         params={"src_body_name": "nut", "tgt_body_name": "bolt", "a":100, "b":2}, weight=1.0)
    fine_nut= RewTerm(func=mdp.position_error_forge, 
                        params={"src_body_name": "nut", "tgt_body_name": "bolt", "a":500, "b":0,}, weight=1.0)
    
    # action penalty
    action_rate = RewTerm(func=mdp.action_rate_l2, weight=-0.00001)
    # joint_vel = RewTerm(
    #     func=mdp.joint_vel_l2,
    #     weight=-0.0001,
    #     params={"asset_cfg": SceneEntityCfg("robot")},
    # )


@configclass
class TerminationsCfg:
    """Termination terms for the MDP."""

    nut_screwed = DoneTerm(func=mdp.nut_fully_screwed, params={"src_body_name":"nut", "tgt_body_name":"bolt", "threshold":0})
    time_out = DoneTerm(func=mdp.time_out, time_out=True)
    


@configclass
class CurriculumCfg:
    """Curriculum terms for the MDP."""

    # action_rate = CurrTerm(
    #     func=mdp.modify_reward_weight, params={"term_name": "action_rate", "weight": -0.005, "num_steps": 4500}
    # )

    # joint_vel = CurrTerm(
    #     func=mdp.modify_reward_weight, params={"term_name": "joint_vel", "weight": -0.001, "num_steps": 4500}
    # )


##
# Environment configuration
##


@configclass
class ScrewEnvCfg(ManagerBasedRLEnvCfg):
    """Configuration for the screw end-effector pose tracking environment."""

    # Scene settings
    scene: ScrewSceneCfg = ScrewSceneCfg(num_envs=4096, env_spacing=2.5)
    # Basic settings
    observations: ObservationsCfg = ObservationsCfg()
    actions: ActionsCfg = ActionsCfg()
    # MDP settings
    rewards: RewardsCfg = RewardsCfg()
    terminations: TerminationsCfg = TerminationsCfg()
    events: EventCfg = EventCfg()
    curriculum: CurriculumCfg = CurriculumCfg()
    
    sim: SimulationCfg = SimulationCfg(
        dt =1./60.,
        physx=PhysxCfg(
            bounce_threshold_velocity=0.2,
            gpu_collision_stack_size=2**31,
            gpu_heap_capacity=2**31,
            gpu_temp_buffer_capacity=2**30,
            gpu_max_rigid_patch_count=2**24,
        ),
    )

    def __post_init__(self):
        """Post initialization."""
        # general settings
        self.decimation = 2
        self.sim.render_interval = self.decimation
        self.episode_length_s = 24.0
        self.viewer.origin_type = "asset_root"
        self.viewer.asset_name = "bolt"
        self.viewer.eye = (0.1, 0, 0.04)
        self.viewer.lookat = (0, 0, 0.02)
        
