"""예제 공통: 상위 폴더의 arm_api 를 불러오고, --no-view 옵션을 처리한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arm_api import Arm, JOINTS  # noqa: E402,F401

VIEW = "--no-view" not in sys.argv
