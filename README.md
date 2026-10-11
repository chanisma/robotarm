# robotarm — SO-101 로봇팔 교육용 시뮬레이터 (LeRobot)

Hugging Face **LeRobot**의 **SO-101** 로봇팔(서보 6개 = 관절 5개 + 집게)을 고등학생이 코드와 조작 패널로 배울 수 있게 만든 프로젝트다. 같은 저장소 묶음의 `robotdog`(DEEP Robotics Lite3) 스튜디오와 같은 구조로 만들었다.

## 실행
```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1   # 최초 1회: 모델 받기 + 가상환경
studio/run_studio.bat                                       # SO-101 Arm Studio 실행 (더블클릭)
```

## SO-101 Arm Studio
한 창에 **코드 편집기와 출력**(왼쪽), **3D 로봇팔과 조작 패널**(오른쪽)이 함께 있다.
- **▶ 실행(F5)**: 켜져 있는 시뮬레이터에 코드를 바로 보낸다. 팔과 상자 상태가 실행 사이에 이어진다. **■ 정지(Esc)**는 무한 반복도 멈춘다.
- **3D 화면**: 실제 SO-101 형상과 색, 상자 3개(빨강·파랑·초록), 노란 목표 구역, **집게 끝 자취**(공중에 그린 선)가 보인다. 화면 위에 집게 끝 위치, 집게 열림 %, 잡은 상자, **모터 부하**(최대 힘 대비 %)가 표시된다.
- **조작 패널**: 슬라이더와 숫자 칸(Enter, ↑/↓)으로 값을 바꾸며 움직임을 확인한다.
  - ① 관절 하나씩: 6개 관절, 옆·위에서 본 팔 그림
  - ② 집게 끝 옮기기: 역기구학. 위에서 본 그림에서 목표를 끌어 놓고, 닿는 범위를 확인
  - ③ 집기: 집게, 상자 목록과 "위로 가기"
- **코드로 쓰면**: 방금 바꾼 값을 학생 코드 한 줄과 **LeRobot 공식 형식**(`robot.send_action({"elbow_flex.pos": 30.0})`)으로 보여 준다.

## 학생 코드
```python
from arm_api import Arm
arm = Arm()
arm.move_to("ready")                 # 자세: rest / ready / zero
arm.set_angle("elbow_flex", 30)      # 관절 하나 (°)
arm.open(); arm.close()              # 집게 (arm.gripper(0~100))
x, y, z = arm.find("red")            # 상자 위치 (m)
arm.move_tip(x, y, 0.08)             # 집게 끝을 그 위 8 cm 로 (역기구학)
print(arm.get_tip(), arm.holding())
robot = arm.robot                    # LeRobot SO101Follower 와 같은 사용법: get_observation() / send_action()
```
샘플: `studio/lessons/`의 A1–A5와 `lerobot_style.py` → [`docs/plan/curriculum.md`](docs/plan/curriculum.md)

## 구조
```
studio/
  arm_sim.py        MuJoCo 모델 (Menagerie SO-101 + 바닥·상자·목표 구역), 역기구학
  arm_interface.py  LeRobot SO101Follower 와 같은 키·단위의 시뮬 인터페이스
  arm_api.py        학생용 API (Arm)
  sim_server.py     라이브 시뮬레이터 (코드 실행, 조작 패널, 상태·화면 스트림)
  live.py           학생 코드 스레드 ↔ 물리 루프 동기화
  studio_web.py     웹 서버 + 앱 창 (aiohttp, pywebview)
  web/              화면 (three.js, CodeMirror, 오프라인용 라이브러리 포함)
  lessons/          샘플 코드
docs/knowledge/so101.md   하드웨어, LeRobot API, 시뮬 ↔ 실제 대응
docs/plan/curriculum.md   교육 과정
```

## 라이선스와 출처
로봇 모델은 MuJoCo Menagerie `robotstudio_so101`과 TheRobotStudio SO-ARM100(둘 다 Apache-2.0)을 쓴다. `scripts/setup.ps1`이 `third_party/`로 받는다.
