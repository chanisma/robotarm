"""학생용 SO-101 로봇팔 API.

LeRobot 공식 인터페이스(arm_interface.SO101SimFollower = SO101Follower 와 같은 키·단위) 위에
학생이 읽기 쉬운 함수를 얹은 얇은 층이다. 관절은 도(°), 집게는 0(닫힘)~100(열림) %, 위치는 m.

  arm = Arm()
  arm.set_angle("elbow_flex", 30)          # 관절 하나를 30° 로
  arm.move_to("ready", seconds=1)          # 자세 이름 또는 {관절: 각도}
  arm.open() / arm.close()                 # 집게
  arm.move_tip(0.22, 0.08, 0.05)           # 집게 끝을 (x, y, z) m 로 — 역기구학
  arm.find("red")                          # 빨간 상자 위치
  arm.robot                                # 공식 형식(LeRobot)을 직접 쓰고 싶을 때
"""
import atexit
import time

import numpy as np

import live
from arm_interface import KEYS, SO101SimFollower, gripper_pct_to_rad, gripper_rad_to_pct
from arm_sim import JOINTS, OBJECTS, POSES, SIM_DT, ArmSim, solve_ik

TICK = 5                                     # 명령 주기 = 5 스텝 = 10 ms

JOINT_INFO = {   # 쉬운 이름과 부호의 뜻 (팔을 앞으로 쭉 편 0° 자세 기준, 시뮬에서 측정)
    "shoulder_pan": ("허리 돌리기", "+ 값이면 팔 전체가 오른쪽으로 돌아요 (위에서 보면 시계 방향)"),
    "shoulder_lift": ("어깨 숙이기", "+ 값이면 팔이 앞·아래로 숙여지고, − 값이면 뒤·위로 젖혀져요"),
    "elbow_flex": ("팔꿈치 굽히기", "+ 값이면 아래팔이 아래로 접혀요"),
    "wrist_flex": ("손목 굽히기", "+ 값이면 집게가 아래로 숙여져요"),
    "wrist_roll": ("손목 돌리기", "집게가 자기 축을 따라 빙글 돌아요"),
    "gripper": ("집게", "0 % = 닫힘, 100 % = 열림 (LeRobot 과 같은 단위)"),
}


class Arm:
    def __init__(self, mode="mock", viewer=True):
        if mode != "mock":
            raise NotImplementedError("실제 팔은 LeRobot SO101Follower 로 연결해요 (docs 참고)")
        self.viewer = None
        self._live = live.CONTEXT
        if self._live:                                  # 코드 스튜디오: 켜져 있는 시뮬레이터에 연결
            self.sim = self._live.sim
        else:
            self.sim = ArmSim()
            if viewer:
                import mujoco.viewer
                self.viewer = mujoco.viewer.launch_passive(self.sim.model, self.sim.data)
                atexit.register(self._keep_open)
            self._wall0, self._sim0 = time.perf_counter(), self.sim.data.time
        self.robot = SO101SimFollower(self.sim)
        self.robot.connect()

    # ---------- 관절 ----------
    def set_angle(self, joint, deg):
        """관절 하나에 목표 각도(°)를 준다. 모터는 바로 그 각도를 향해 움직인다."""
        self._check(joint)
        if joint == "gripper":
            raise ValueError("집게는 arm.gripper(퍼센트) 또는 arm.open() / arm.close() 로 움직여요")
        self.robot.send_action({f"{joint}.pos": float(deg)})

    def get_angle(self, joint):
        """관절 하나의 현재 각도(°). 집게는 % 로 돌려준다."""
        self._check(joint)
        return round(self.robot.get_observation()[f"{joint}.pos"], 1)

    def get_angles(self):
        return {k[:-4]: round(v, 1) for k, v in self.robot.get_observation().items()}

    def move_to(self, pose, seconds=1.0):
        """여러 관절을 seconds 동안 부드럽게 옮긴다. pose: "rest" / "ready" / "zero" 또는 {관절: 각도}."""
        if isinstance(pose, str):
            if pose not in POSES:
                raise ValueError(f"자세 이름 '{pose}' 은(는) 없어요. 쓸 수 있는 이름: {', '.join(POSES)}")
            goal = np.radians(POSES[pose])
            goal[5] = self.sim.target[5]                 # 자세를 바꿔도 집게는 그대로
        else:
            goal = self.sim.target
            for joint, value in pose.items():
                self._check(joint)
                i = JOINTS.index(joint)
                goal[i] = gripper_pct_to_rad(self.sim, value) if joint == "gripper" else np.radians(value)
        self._glide(goal, seconds)

    # ---------- 집게 ----------
    def gripper(self, percent, seconds=0.5):
        """집게를 percent(0 닫힘 ~ 100 열림) 로."""
        goal = self.sim.target
        goal[5] = gripper_pct_to_rad(self.sim, percent)
        self._glide(goal, seconds)

    def open(self):
        self.gripper(100)

    def close(self):
        self.gripper(0)

    def holding(self):
        """지금 집게로 들고 있는 상자 이름 (없으면 None)."""
        return self.sim.held_object()

    # ---------- 끝점(집게 끝) ----------
    def get_tip(self):
        """집게 끝 위치 (x 앞, y 왼쪽, z 위) [m, 로봇 받침 기준]."""
        return tuple(round(float(v), 4) for v in self.sim.tip_pos())

    def move_tip(self, x, y, z, seconds=1.0, down=True):
        """집게 끝을 (x, y, z) m 로 옮긴다 — 컴퓨터가 관절 각도를 거꾸로 계산(역기구학).
        down=True 면 집게가 바닥을 수직으로 내려다본다(물건 집기 좋은 자세)."""
        q, ok, err = solve_ik(self.sim, (x, y, z), down=down)
        if not ok:
            where = f"({x:.2f}, {y:.2f}, {z:.2f}) m"
            if down and err < 0.005:
                raise ValueError(f"{where} 에는 닿지만, 그 높이에서는 집게를 아래로 향하게 할 수 없어요 (손목 한계). "
                                 "더 낮게 하거나 down=False 로 해 보세요")
            hint = " 더 가까이·더 낮게 하거나 down=False 로 해 보세요" if down else ""
            raise ValueError(f"집게 끝이 {where} 에 닿을 수 없어요. 가장 가까워도 {err * 100:.1f} cm 떨어져요.{hint}")
        q[5] = self.sim.target[5]
        self._glide(q, seconds)

    # ---------- 물체 ----------
    def find(self, name):
        """상자 위치 (x, y, z) m. 이름: red, blue, green"""
        if name not in OBJECTS:
            raise ValueError(f"상자 이름 '{name}' 은(는) 없어요. 쓸 수 있는 이름: {', '.join(OBJECTS)}")
        return tuple(round(float(v), 4) for v in self.sim.object_pos(name))

    # ---------- 시간 ----------
    def wait(self, seconds):
        self._advance(int(seconds / SIM_DT))

    def reset(self, objects=True):
        """팔을 접은 자세로, objects=True 면 상자도 처음 위치로."""
        self.sim.reset(objects=objects)
        self._advance(50)

    # ---------- 내부 ----------
    def _check(self, joint):
        if joint not in JOINTS:
            raise ValueError(f"관절 이름 '{joint}' 은(는) 없어요. 쓸 수 있는 이름: {', '.join(JOINTS)}")

    def _glide(self, goal, seconds):
        start = self.sim.target
        n = max(1, int(seconds / (TICK * SIM_DT)))
        for i in range(1, n + 1):
            self.sim.set_target(start + (goal - start) * i / n)
            self._advance(TICK)
        self._advance(75)                                  # 도착 후 0.15 초 안정

    def _advance(self, steps):
        if self._live:
            self._live.advance(steps)
            return
        self.sim.step(steps)
        if self.viewer:
            if not self.viewer.is_running():
                raise SystemExit("화면을 닫아서 프로그램을 종료합니다.")
            self.viewer.sync()
            lag = (self.sim.data.time - self._sim0) - (time.perf_counter() - self._wall0)
            if lag > 0:
                time.sleep(lag)

    def _keep_open(self):
        if not self.viewer.is_running():
            return
        print("프로그램 끝! 창을 닫으면 종료됩니다.")
        try:
            while True:
                self._advance(TICK)
        except SystemExit:
            pass


__all__ = ["Arm", "JOINT_INFO", "JOINTS", "KEYS", "POSES", "OBJECTS"]
