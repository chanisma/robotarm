"""A5. 집어서 옮기기 (픽 앤 플레이스) — 빨간 상자를 노란 목표 구역으로.

순서: 상자 찾기 → 집게 열기 → 상자 위로 → 내려가기 → 집기 → 들어 올리기 → 목표 위로 → 내려놓기
"""
from _setup import Arm, VIEW

ZONE = (0.16, 0.18)              # 노란 목표 구역 (x, y) m

arm = Arm(viewer=VIEW)
arm.reset()                       # 팔을 접고 상자를 처음 위치로
arm.move_to("ready", seconds=1.5)

x, y, z = arm.find("red")
print("빨간 상자 위치:", (x, y, z))

arm.open()
arm.move_tip(x, y, 0.08)          # 상자 위 8 cm
arm.move_tip(x, y, 0.02)          # 내려가기 (상자 높이 3 cm 의 가운데쯤)
arm.close()
print("잡았나?", arm.holding())

arm.move_tip(x, y, 0.10)          # 들어 올리기
arm.move_tip(ZONE[0], ZONE[1], 0.10)
arm.move_tip(ZONE[0], ZONE[1], 0.04)
arm.open()
arm.move_tip(ZONE[0], ZONE[1], 0.10)
arm.move_to("ready", seconds=1.0)

print("빨간 상자 새 위치:", arm.find("red"))

# 도전 1: 함수 pick_and_place(name, x, y) 를 만들어 세 상자를 모두 목표 구역으로 옮기자.
# 도전 2: 파란 상자를 빨간 상자 위에 쌓아 보자 (내려놓는 높이를 바꿔야 해요).
