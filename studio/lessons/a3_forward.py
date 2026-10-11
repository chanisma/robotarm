"""A3. 각도 → 집게 끝 위치 (정기구학).

관절 각도를 정하면 집게 끝이 어디에 있게 되는지 정해진다. 3D 화면의 빨간 점이 집게 끝이고, 지나간 길이 자취로 남는다.
"""
from _setup import Arm, VIEW

arm = Arm(viewer=VIEW)
arm.reset()
arm.move_to("zero", seconds=1.5)
print("영점 자세 집게 끝 (x 앞, y 왼쪽, z 높이) m:", arm.get_tip())
arm.move_to({"shoulder_lift": -40}, seconds=0.8)     # 어깨를 들어 올려 두기 (팔꿈치를 굽혀도 바닥에 안 닿게)

# 팔꿈치만 0° → 90° 로 바꾸며 집게 끝이 어떻게 움직이는지 기록
for elbow in range(0, 91, 15):
    arm.move_to({"elbow_flex": elbow}, seconds=0.4)
    x, y, z = arm.get_tip()
    print(f"팔꿈치 {elbow:3d}° → 집게 끝 앞 {x * 100:5.1f} cm, 높이 {z * 100:5.1f} cm")

# 허리만 돌리면? 높이는 그대로, 원을 그린다 (팔꿈치 45° — 집게가 공중에 있게)
arm.move_to({"elbow_flex": 45}, seconds=0.6)
for pan in (-60, -30, 0, 30, 60):
    arm.move_to({"shoulder_pan": pan}, seconds=0.5)
    x, y, z = arm.get_tip()
    print(f"허리 {pan:4d}° → (앞 {x * 100:5.1f}, 왼쪽 {y * 100:5.1f}, 높이 {z * 100:5.1f}) cm")

# 생각해 보기: 허리를 돌릴 때 (앞, 왼쪽) 값이 그리는 모양은? 반지름은?  (힌트: √(x²+y²))
