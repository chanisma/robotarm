"""LeRobot SO-101 팔로워 인터페이스의 시뮬레이터 구현.

실제 팔은 LeRobot 의 `lerobot.robots.so_follower.SO101Follower` 로 움직인다. 이 클래스는 그와
함수 이름·키·단위를 똑같이 맞춰서, 시뮬에서 짠 코드를 실제 팔 코드로 바로 옮길 수 있게 한다.

  키: "shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos", "wrist_flex.pos", "wrist_roll.pos", "gripper.pos"
  단위: 관절은 도(°) — LeRobot use_degrees=True(기본값)와 같다. 집게는 0(닫힘) ~ 100(열림).
  영점: 관절 0° = LeRobot 'new calib' 영점 = MJCF 0 rad. (LeRobot 자체도 deg↔rad 를 오프셋 없이 변환함)

실제 팔로 옮길 때:
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
    robot = SO101Follower(SO101FollowerConfig(port="COM3", id="my_arm"))
    robot.connect()
    robot.send_action({"elbow_flex.pos": 30.0})
"""
import numpy as np

from arm_sim import JOINTS

KEYS = [f"{j}.pos" for j in JOINTS]


def gripper_pct_to_rad(sim, pct):
    """집게 0~100 → 시뮬 관절각. 0 = 닫힘(관절 하한), 100 = 열림(상한). (LeRobot 은 선형 대응을 쓰지 않으므로 근사)"""
    pct = float(np.clip(pct, 0, 100))
    return sim.lower[5] + pct / 100 * (sim.upper[5] - sim.lower[5])


def gripper_rad_to_pct(sim, rad):
    return float((rad - sim.lower[5]) / (sim.upper[5] - sim.lower[5]) * 100)


class SO101SimFollower:
    """SO101Follower 와 같은 사용법: connect() → get_observation() / send_action() → disconnect()."""

    name = "so101_follower"

    def __init__(self, sim, max_relative_target=None):
        self.sim = sim
        self.max_relative_target = max_relative_target
        self.is_connected = False

    @property
    def observation_features(self):
        return {k: float for k in KEYS}

    @property
    def action_features(self):
        return {k: float for k in KEYS}

    def connect(self, calibrate=True):
        self.is_connected = True

    def disconnect(self):
        self.is_connected = False

    def get_observation(self):
        q = self.sim.q
        obs = {f"{j}.pos": float(np.degrees(q[i])) for i, j in enumerate(JOINTS[:5])}
        obs["gripper.pos"] = gripper_rad_to_pct(self.sim, q[5])
        return obs

    def send_action(self, action):
        """action 에 있는 관절만 목표로 보낸다. 실제로 보낸 값(범위로 잘린 값)을 돌려준다 — LeRobot 과 같음."""
        target = self.sim.target
        sent = {}
        for key, value in action.items():
            if key not in KEYS:
                raise KeyError(f"모르는 키예요: {key}. 쓸 수 있는 키: {', '.join(KEYS)}")
            i = KEYS.index(key)
            if i == 5:
                rad = gripper_pct_to_rad(self.sim, value)
            else:
                rad = np.radians(float(value))
            if self.max_relative_target is not None:
                lim = np.radians(self.max_relative_target) if i < 5 else self.max_relative_target / 100 * (
                    self.sim.upper[5] - self.sim.lower[5])
                rad = np.clip(rad, self.sim.q[i] - lim, self.sim.q[i] + lim)
            target[i] = np.clip(rad, self.sim.lower[i], self.sim.upper[i])
            sent[key] = gripper_rad_to_pct(self.sim, target[i]) if i == 5 else float(np.degrees(target[i]))
        self.sim.set_target(target)
        return sent
