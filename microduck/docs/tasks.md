# Tasks

Two environments, both in `src/microduck/sim/`. Both follow the gymnasium
5-tuple convention (`obs, reward, terminated, truncated, info`) without
depending on gymnasium.

## Walking (`MicroduckEnv`)

Velocity-tracking locomotion. The policy is given a commanded
`(vx, vy, wz)` and rewarded for matching it while staying upright and keeping
the gait clean.

- **Observation (56)**: projected gravity (3), base angular velocity (3), joint
  positions (15) and velocities (15) relative to the standing pose, previous
  action (15), command (3), gait-phase clock (2).
- **Action (15)**: joint-position residuals around the standing pose, scaled by
  `ACTUATION.action_scale` (0.35 rad) and clipped.
- **Episode**: 12 s, ending early on a fall (torso below 7.5 cm or tilted past
  ~56 degrees).

The gait-phase clock is what stops a learned walk from degenerating into a
shuffle; it comes from the same `ScriptedGait` that provides the baseline
controller.

## Fetch (`MicroduckFetchEnv`)

Walk to the ball, pick it up with the beak, carry it back to the start, drop it.
Four phases, advanced by the environment and shown to the policy as a one-hot:

| phase | ends when |
|---|---|
| `APPROACH` | the beak is within `grasp_radius` (5.5 cm) of the ball |
| `GRASP` | the beak has closed on the ball and lifted it past `lift_height` |
| `RETURN` | the ball is within `home_radius` (9 cm) of the starting spot |
| `RELEASE` | the beak opens and the ball settles on the pad -- success |

There is **one** policy and one network; the phases only shape the reward and
the observation. Every locomotion reward from the walking task still applies
throughout, so the policy cannot buy task reward by dragging itself along on
its chest.

- **Observation (67)**: the 56 walking channels, in the same order, plus ball
  position in the base frame (3), home position in the base frame (3), phase
  one-hot (4) and grasp flag (1). The prefix ordering is deliberate -- it is
  what makes warm-starting from a walking checkpoint exact.
- **Episode**: 25 s, ending on a fall, on success, or if the ball is knocked
  more than 1.2 m away.

### Two design decisions worth understanding

**Grasping.** `grasp_mode="weld"` (default) latches a MuJoCo weld constraint
when the beak closes on the ball and releases it when the beak opens.
Frictional grasping with a 1-DoF beak and a smooth sphere is genuinely hard to
stabilise at this scale, and a policy that spends its whole sample budget
rediscovering contact mechanics learns the task far more slowly.
`grasp_mode="contact"` uses real friction between the two jaw geoms and the
ball, and is the honest setting if the gripper itself is what you are studying
-- expect it to need considerably more samples.

**Navigation.** With `heading_command=True` (default) the environment writes a
desired base velocity towards the active target into the same command channel
the walking task uses. That makes this a waypoint-conditioned
locomotion-and-manipulation policy: the environment navigates, the policy walks
and grasps. With `heading_command=False` the command channel is zeroed and the
policy has to learn navigation from the relative-position channels too -- a
harder and more interesting problem, and a much longer run.

### Reward budget

Per-step terms are multiplied by ~1250 steps; one-time bonuses are not. Getting
that ratio wrong is the easiest way to make the task unlearnable, so
`FetchConfig.rewards` lowers the shared `alive`, `upright` and `base_height`
weights well below the walking task's. A do-nothing episode scores ~200; the
one-time bonuses for a complete fetch add ~208 plus ~70 of progress reward.
`tests/test_envs.py::test_doing_nothing_scores_far_below_a_completed_fetch`
guards this, and is worth re-running after any reward edit.

## Domain randomisation

On by default in both tasks, and the reason a trained policy has any chance on
hardware. Per episode: body masses (±18%) and a torso payload, centre-of-mass
shifts, floor friction, servo `kp`/`kd`/torque limits and joint friction,
command latency (4-22 ms), joint-position bias, sensor noise on the IMU and
encoders, perception noise on the ball and pad positions, and random shoves to
the base every 2-6 s. Disable with `RandomizationConfig(enabled=False)` for
debugging -- never for a run you intend to deploy.
