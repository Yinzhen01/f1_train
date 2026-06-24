# SPDX-FileCopyrightText: Copyright (c) 2021 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-FileCopyrightText: Copyright (c) 2021 ETH Zurich, Nikita Rudin
# SPDX-FileCopyrightText: Copyright (c) 2024 Beijing RobotEra TECHNOLOGY CO.,LTD. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# Copyright (c) 2024, AgiBot Inc. All rights reserved.


from humanoid import LEGGED_GYM_ROOT_DIR, LEGGED_GYM_ENVS_DIR
from .base.legged_robot import LeggedRobot

from .x1.x1_dh_stand_config  import X1DHStandCfg, X1DHStandCfgPPO
from .f1.f1_dh_stand_config import (
    F1DHMotionImitationCfg,
    F1DHMotionImitationCfgPPO,
    F1DHStaticStandCfg,
    F1DHStaticStandCfgPPO,
    F1DHStandCfg,
    F1DHStandCfgPPO,
    F1RunCfg,
    F1RunCfgPPO,
    F1RunPhase0Cfg,
    F1RunPhase0CfgPPO,
    F1RunRephaseCfg,
    F1RunRephaseCfgPPO,
    F1RunStaticStandCfg,
    F1RunStaticStandCfgPPO,
)

from .x1.x1_dh_stand_env import X1DHStandEnv
from .f1.f1_dh_stand_env import F1DHStandEnv

from humanoid.utils.task_registry import task_registry

task_registry.register( "x1_dh_stand", X1DHStandEnv, X1DHStandCfg(), X1DHStandCfgPPO() )
task_registry.register( "f1_dh_stand", F1DHStandEnv, F1DHStandCfg(), F1DHStandCfgPPO() )
task_registry.register( "f1_dh_motion_imitation", F1DHStandEnv, F1DHMotionImitationCfg(), F1DHMotionImitationCfgPPO() )
task_registry.register( "f1_dh_static_stand", F1DHStandEnv, F1DHStaticStandCfg(), F1DHStaticStandCfgPPO() )
task_registry.register( "f1_run", F1DHStandEnv, F1RunCfg(), F1RunCfgPPO() )
task_registry.register( "f1_run_phase0", F1DHStandEnv, F1RunPhase0Cfg(), F1RunPhase0CfgPPO() )
task_registry.register( "f1_run_rephase", F1DHStandEnv, F1RunRephaseCfg(), F1RunRephaseCfgPPO() )
task_registry.register( "f1_run_static_stand", F1DHStandEnv, F1RunStaticStandCfg(), F1RunStaticStandCfgPPO() )
