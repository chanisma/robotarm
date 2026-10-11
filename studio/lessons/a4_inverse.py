"""A4. 집게 끝 옮기기 (역기구학) — 위치를 정하면 컴퓨터가 관절 각도를 거꾸로 계산한다.

공중에 정사각형 그리기. 3D 화면의 '집게 끝 자취'를 켜고 보자.
"""
from _setup import Arm, VIEW

arm = Arm(viewer=VIEW)
arm.reset()
arm.move_to("ready", seconds=1.5)

SIZE = 0.08              # 정사각형 한 변 (m) = 8 cm
CX, CY, Z = 0.22, 0.0, 0.10   # 정사각형 중심과 높이

corners = [(CX - SIZE / 2, CY - SIZE / 2), (CX + SIZE / 2, CY - SIZE / 2),
           (CX + SIZE / 2, CY + SIZE / 2), (CX - SIZE / 2, CY + SIZE / 2)]
for x, y in corners + corners[:1]:
    arm.move_tip(x, y, Z, seconds=0.8)
    print("집게 끝:", arm.get_tip(), " 관절:", arm.get_angles())

# 닿지 않는 곳을 주면?
try:
    arm.move_tip(0.45, 0.0, 0.05)
except ValueError as e:
    print("오류:", e)

# 도전: 원 그리기 (math.cos, math.sin 사용), 높이를 바꿔 가며 계단 그리기
