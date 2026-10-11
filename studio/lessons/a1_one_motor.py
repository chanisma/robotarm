"""A1. 모터 하나 움직이기 — 목표 각도를 주면 서보 모터가 그 각도로 간다.

SO-101 에는 STS3215 서보 모터 6개가 있다: 허리, 어깨, 팔꿈치, 손목 굽힘, 손목 돌림, 집게.
"""
from _setup import Arm, VIEW

arm = Arm(viewer=VIEW)
arm.reset()                       # 팔을 접은 처음 자세에서 시작
arm.move_to("zero", seconds=1.5)  # 모든 관절 0° — 팔이 앞으로 쭉 뻗은 자세

for joint, goal in [("shoulder_pan", 30), ("shoulder_lift", -20), ("elbow_flex", 40), ("wrist_flex", 30)]:
    before = arm.get_angle(joint)
    arm.set_angle(joint, goal)    # 목표 각도 주기 (LeRobot: robot.send_action({"<관절>.pos": 각도}))
    arm.wait(0.8)
    after = arm.get_angle(joint)  # 현재 각도 읽기
    print(f"{joint:13s}: {before:6.1f}° → 목표 {goal}° → 실제 {after:6.1f}°")

arm.gripper(100)                  # 집게 열기 (0 = 닫힘, 100 = 열림)
print("집게:", arm.get_angle("gripper"), "%")

# 생각해 보기: '+' 각도를 주면 각 관절은 어느 쪽으로 움직였나? 조작 패널 ① 탭의 설명과 비교해 보자.
# 도전: 범위 밖 값(예: elbow_flex 150°)을 주면 어떻게 될까?
