"""LeRobot 공식 형식으로 움직이기 — 실제 SO-101 에서도 거의 그대로 쓸 수 있는 코드.

arm.robot 은 LeRobot 의 SO101Follower 와 같은 함수·키·단위를 가진 시뮬레이터 인터페이스다.
실제 팔에서는 아래 두 줄만 바꾸면 된다:
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
    robot = SO101Follower(SO101FollowerConfig(port="COM3", id="my_arm")); robot.connect()
"""
from _setup import Arm, VIEW

arm = Arm(viewer=VIEW)
arm.reset()
robot = arm.robot                 # ← 실제 팔에서는 SO101Follower

print("관측 키:", list(robot.get_observation().keys()))

action = {
    "shoulder_pan.pos": 20.0,     # 관절은 도(°)
    "shoulder_lift.pos": -20.0,
    "elbow_flex.pos": 40.0,
    "wrist_flex.pos": 50.0,
    "wrist_roll.pos": 0.0,
    "gripper.pos": 80.0,          # 집게는 0(닫힘) ~ 100(열림)
}
sent = robot.send_action(action)  # 실제로 보낸 값(범위로 잘린 값)을 돌려준다
arm.wait(1.5)
obs = robot.get_observation()
for key in action:
    print(f"{key:18s} 보냄 {sent[key]:7.1f}  →  지금 {obs[key]:7.1f}")

# 범위를 넘으면? (elbow_flex 범위 약 ±97°)
print("범위 밖 요청 결과:", robot.send_action({"elbow_flex.pos": 150.0}))
