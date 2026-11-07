import gymnasium as gym

from . import agents

gym.register(
    id="Isaac-G1-Backflip-Direct-v0",
    entry_point=f"{__name__}.g1_backflip_env:G1BackflipEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_backflip_env_cfg:G1BackflipEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:G1BackflipPPORunnerCfg",
    },
)

gym.register(
    id="Isaac-G1-Backflip-Direct-Play-v0",
    entry_point=f"{__name__}.g1_backflip_env:G1BackflipEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_backflip_env_cfg:G1BackflipEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:G1BackflipPPORunnerCfg",
    },
)
