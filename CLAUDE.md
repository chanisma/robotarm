# CLAUDE.md

LeRobot SO-101 로봇팔을 활용한 고등학생 교육·연구 프로젝트. 문서는 한국어로 작성한다. 자매 프로젝트는 `../robotdog`(DEEP Robotics Lite3)이고, 스튜디오 구조(웹 UI, 라이브 시뮬, 조작 패널)가 같다.

- 학생은 아주 기초적인 Python만 안다. 학생 코드는 `studio/arm_api.py`의 `Arm`만 쓰고, 값의 뜻은 조작 패널로 먼저 보여 준다.
- 실제 팔과 같은 단위를 지킨다: 관절은 도(°), 집게는 0(닫힘)–100(열림), 키는 LeRobot과 같다(`"elbow_flex.pos"`). 공식 형식은 `arm_interface.SO101SimFollower`(= LeRobot `SO101Follower`)이다.
- 로봇 사실은 `docs/knowledge/so101.md`에 출처와 함께 적는다. 확인되지 않은 값에는 ⚠️를 붙인다.
- `third_party/`는 수정하지 않는다(`scripts/setup.ps1` 참고). 시뮬 모델은 Menagerie `robotstudio_so101`이다. 원본 SO-ARM100 MJCF는 집게 충돌 메시 때문에 물건을 집을 수 없다.
- Windows 콘솔은 cp949다. heredoc으로 Python에 한글 스크립트를 넘길 때는 `PYTHONUTF8=1`을 쓴다.
