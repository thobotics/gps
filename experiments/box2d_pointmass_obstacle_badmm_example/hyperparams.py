""" Hyperparameters for Box2d Point Mass."""
from __future__ import division

import os.path
from datetime import datetime
import numpy as np

from gps import __file__ as gps_filepath
from gps.agent.box2d.agent_box2d import AgentBox2D
from gps.agent.box2d.point_mass_world_obstacle import PointMassWorldObstacle
from gps.algorithm.algorithm_badmm import AlgorithmBADMM
from gps.algorithm.cost.cost_obstacles import CostObstacle
from gps.algorithm.cost.cost_state import CostState
from gps.algorithm.cost.cost_action import CostAction
from gps.algorithm.cost.cost_sum import CostSum
from gps.algorithm.dynamics.dynamics_lr_prior import DynamicsLRPrior
from gps.algorithm.dynamics.dynamics_prior_gmm import DynamicsPriorGMM
from gps.algorithm.policy.policy_prior_gmm import PolicyPriorGMM
from gps.algorithm.traj_opt.traj_opt_lqr_python import TrajOptLQRPython
from gps.algorithm.policy_opt.policy_opt_caffe import PolicyOptCaffe
from gps.algorithm.policy.lin_gauss_init import init_pd
from gps.gui.config import generate_experiment_info
from gps.proto.gps_pb2 import END_EFFECTOR_POINTS, END_EFFECTOR_POINT_VELOCITIES, ACTION, POSITION_NEAREST_OBSTACLE

SENSOR_DIMS = {
    END_EFFECTOR_POINTS: 3,
    END_EFFECTOR_POINT_VELOCITIES: 3,
    ACTION: 2
}

BASE_DIR = '/'.join(str.split(gps_filepath, '/')[:-2])
EXP_DIR = BASE_DIR + '/../experiments/box2d_pointmass_obstacle_badmm_example/'


common = {
    'experiment_name': 'box2d_pointmass_obstacle_badmm_example' + '_' + \
            datetime.strftime(datetime.now(), '%m-%d-%y_%H-%M'),
    'experiment_dir': EXP_DIR,
    'data_files_dir': EXP_DIR + 'data_files/',
    'log_filename': EXP_DIR + 'log.txt',
    'conditions': 4,
    'use_mpc': False,
}

if not os.path.exists(common['data_files_dir']):
    os.makedirs(common['data_files_dir'])

world_info = {
		'obstacles': [np.array([-5, 13, 4, 1]),
           np.array([10, 13, 4, 1]),
           np.array([-9, 20, 4, 1]),
           np.array([15, 20, 4, 1]),
           np.array([3, 20, 1.5, 1]),
          ],
}

x0_test = [np.array([0, 5, 0, 0, 0, 0]),
           np.array([0, 8, 0, 0, 0, 0]),
           np.array([0, 11, 0, 0, 0, 0]),
           np.array([0, 14, 0, 0, 0, 0]),
          ]

agent = {
    'type': AgentBox2D,
    'target_state' : np.array([3, 35, 0]),
    "world" : PointMassWorldObstacle,
    'world_info': world_info,
    'render' : False,
    'x0': [np.array([0, 5, 0, 0, 0, 0]),
           np.array([2, 3, 0, 0, 0, 0]),
           np.array([7, 3, 0, 0, 0, 0]),
           np.array([-5, 3, 0, 0, 0, 0]),
          ],
    'rk': 0,
    'dt': 0.05,
    'substeps': 1,
    'conditions': common['conditions'],
    'pos_body_idx': np.array([]),
    'pos_body_offset': np.array([]),
    'T': 100,
    'use_mpc': common['use_mpc'],
    'M': 5,
    'sensor_dims': SENSOR_DIMS,
    'state_include': [END_EFFECTOR_POINTS, END_EFFECTOR_POINT_VELOCITIES],
    'obs_include': [END_EFFECTOR_POINTS, END_EFFECTOR_POINT_VELOCITIES],
}

algorithm = {
    'type': AlgorithmBADMM,
    'conditions': common['conditions'],
    'iterations': 10,
    'lg_step_schedule': np.array([1e-4, 1e-3, 1e-2, 1e-2]),
    'policy_dual_rate': 0.2,
    'ent_reg_schedule': np.array([1e-3, 1e-3, 1e-2, 1e-1]),
    'fixed_lg_step': 3,
    'kl_step': 5.0,
    'min_step_mult': 0.01,
    'max_step_mult': 1.0,
    'sample_decrease_var': 0.05,
    'sample_increase_var': 0.1,
    'use_mpc': common['use_mpc'],
}

algorithm['init_traj_distr'] = {
    'type': init_pd,
    'init_var': 5.0,
    'pos_gains': 0.0,
    'dQ': SENSOR_DIMS[ACTION],
    'dt': agent['dt'],
    'T': agent['T'],
}

algorithm['init_mpc'] = {
    'type': init_pd,
    'init_var': 5.0,
    'pos_gains': 0.0,
    'dQ': SENSOR_DIMS[ACTION],
    'dt': agent['dt'],
    'T': agent['M'],
}

action_cost = {
    'type': CostAction,
    'wu': np.array([5e-5, 5e-5])
}

state_cost = {
    'type': CostState,
    'data_types' : {
        END_EFFECTOR_POINTS: {
            'wp': np.ones(SENSOR_DIMS[END_EFFECTOR_POINTS]),
            'target_state': agent["target_state"],
        },
    },
}

obstacle_cost = {
    'type': CostObstacle,
    'obstacle_type' : POSITION_NEAREST_OBSTACLE,
    'position_type': END_EFFECTOR_POINTS,
		'wp': np.ones(SENSOR_DIMS[END_EFFECTOR_POINTS]),
		'd_safe': 1.0
}

algorithm['cost'] = {
    'type': CostSum,
    'costs': [action_cost, state_cost, obstacle_cost],
    'weights': [1.0, 1.2, 10.0],
}

algorithm['dynamics'] = {
    'type': DynamicsLRPrior,
    'regularization': 1e-6,
    'prior': {
        'type': DynamicsPriorGMM,
        'max_clusters': 20,
        'min_samples_per_cluster': 40,
        'max_samples': 20,
    },
}

algorithm['traj_opt'] = {
    'type': TrajOptLQRPython,
}

algorithm['policy_opt'] = {
    'type': PolicyOptCaffe,
    'weights_file_prefix': EXP_DIR + 'policy',
}

algorithm['policy_prior'] = {
    'type': PolicyPriorGMM,
    'max_clusters': 20,
    'min_samples_per_cluster': 40,
    'max_samples': 20,
}

config = {
    'iterations': algorithm['iterations'],
    'num_samples': 10,
    'verbose_trials': 5,
    'verbose_policy_trials': 0,
    'common': common,
    'agent': agent,
    'gui_on': True,
    'algorithm': algorithm,
}

common['info'] = generate_experiment_info(config)
