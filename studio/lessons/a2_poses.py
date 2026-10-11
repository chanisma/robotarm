"""A2. 자세와 동작 — 자세 = 관절 각도의 묶음, 동작 = 자세를 차례로 잇기."""
from _setup import Arm, VIEW

arm = Arm(viewer=VIEW)
arm.reset()

arm.move_to("ready", seconds=1.5)                 # 미리 정해 둔 자세 이름: rest(접기), ready(준비), zero(영점)
print("준비 자세:", arm.get_angles())

# 손 흔들기(인사): 팔을 세우고 손목을 좌우로 3번
arm.move_to({"shoulder_lift": -40, "elbow_flex": -60, "wrist_flex": 0}, seconds=1.0)
for i in range(3):
    arm.move_to({"wrist_flex": 40}, seconds=0.35)
    arm.move_to({"wrist_flex": -40}, seconds=0.35)
arm.move_to({"wrist_flex": 0}, seconds=0.3)

# 고개 끄덕이기: 집게를 위아래로
for i in range(2):
    arm.gripper(80, seconds=0.3)
    arm.gripper(10, seconds=0.3)

arm.move_to("rest", seconds=1.5)
print("끝 — 접기 자세")

# 생각해 보기: seconds 를 0.1 로 줄이면 어떻게 보일까? 실제 모터라면 어떤 문제가 생길까?
# 도전: 허리(shoulder_pan)를 이용해 "아니야" 고개 젓기 동작을 만들어 보자.
