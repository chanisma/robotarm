"""SO-101 라이브 시뮬레이터 서버 — 켜 둔 채로 코드 스튜디오가 보내는 코드를 실행한다.

stdin  (한 줄에 JSON 하나): {"cmd": "run", "code": "..."} | {"cmd": "stop"} | {"cmd": "reset"} | {"cmd": "quit"}
       조작 패널: {"cmd": "panel", "op": "joints", "values": [관절 5개 °, 집게 %]} | {"op": "pose", "name": "ready"}
                 | {"op": "tip", "x": .., "y": .., "z": .., "down": true} | {"op": "reset_objects"}
stdout: 학생 코드 print 출력 + EVENT_PREFIX 로 시작하는 알림 줄
        ready / run_start / run_end / reset_done / busy / notice / ik / state(10 Hz) / frame(30 Hz, --stream)
학생 코드는 작업 스레드, 물리 계산과 화면 갱신은 메인 스레드 (live.py 의 동기화 규칙).
"""
import ctypes
import json
import queue
import sys
import threading
import time
import traceback

import numpy as np

import live
from arm_interface import SO101SimFollower, gripper_pct_to_rad
from arm_sim import JOINTS, OBJECTS, POSES, SIM_DT, ArmSim, solve_ik

EVENT_PREFIX = "\x01EVT "
CODE_NAME = "내 코드"
IDLE_CHUNK = 5                         # 10 ms 씩 진행
PANEL_RATE = np.radians(120) * IDLE_CHUNK * SIM_DT     # 패널: 관절 최대 120°/s
STATE_EVERY = 0.1
FRAME_EVERY = 1 / 30
ARM_POINTS = ["upper_arm", "lower_arm", "wrist", "gripper"]   # 패널 옆모습 그림용 관절 위치


def emit(event, **data):
    sys.stdout.write(EVENT_PREFIX + json.dumps({"event": event, **data}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


class Server:
    def __init__(self, headless=False, stream=False):
        self.sim = ArmSim()
        self.robot = SO101SimFollower(self.sim)
        self.ctx = live.LiveContext(self.sim)
        live.CONTEXT = self.ctx
        self.commands = queue.Queue()
        self.worker = None
        self.code_running = False
        self.stop_requested_at = None
        self.injected = False
        self.panel_goal = None
        self.stream = stream
        self.last_state = self.last_frame = 0.0
        self.viewer = None
        if not headless and not stream:
            import mujoco.viewer
            self.viewer = mujoco.viewer.launch_passive(self.sim.model, self.sim.data)

    # ---------- 명령 ----------
    def _read_stdin(self):
        for line in sys.stdin:
            if line.strip():
                self.commands.put(json.loads(line))
        self.commands.put({"cmd": "quit"})

    def _handle(self, msg):
        cmd = msg.get("cmd")
        busy = self.code_running
        if cmd == "run":
            if busy:
                emit("busy")
            else:
                self.panel_goal = None
                self.code_running = True
                self.worker = threading.Thread(target=self._run_code, args=(msg["code"],), daemon=True)
                self.worker.start()
        elif cmd == "stop" and busy:
            self.ctx.stop_flag = True
            self.stop_requested_at = time.perf_counter()
            self.injected = False
        elif cmd == "reset":
            if busy:
                emit("busy")
            else:
                with self.ctx.lock:
                    self.sim.reset(objects=True)
                    self.panel_goal = None
                emit("reset_done")
        elif cmd == "panel":
            if busy:
                emit("busy")
            else:
                with self.ctx.lock:
                    self._panel(msg)
        elif cmd == "quit":
            return False
        return True

    # ---------- 조작 패널 ----------
    def _panel(self, msg):
        op = msg.get("op")
        if op == "joints":
            v = msg["values"]
            goal = np.radians(np.asarray(v[:5], float))
            self.panel_goal = np.append(goal, gripper_pct_to_rad(self.sim, v[5]))
        elif op == "pose":
            goal = np.radians(POSES[msg["name"]])
            goal[5] = self.sim.target[5]
            self.panel_goal = goal
        elif op == "tip":
            q, ok, err = solve_ik(self.sim, (msg["x"], msg["y"], msg["z"]), down=msg.get("down", True))
            emit("ik", ok=bool(ok), err=round(err * 100, 1),
                 deg=[round(float(a), 1) for a in np.degrees(q[:5])])
            if ok:
                q[5] = self.sim.target[5]
                self.panel_goal = q
        elif op == "reset_objects":
            self.sim.reset_objects()

    def _panel_tick(self):
        if self.panel_goal is None:
            return
        cur = self.sim.target
        self.sim.set_target(cur + np.clip(self.panel_goal - cur, -PANEL_RATE, PANEL_RATE))

    # ---------- 상태 알림 ----------
    def _emit_state(self):
        obs = self.robot.get_observation()
        tgt = self.sim.target
        d, m = self.sim.data, self.sim.model
        emit("state",
             obs=[round(obs[f"{j}.pos"], 1) for j in JOINTS],
             target=[round(float(np.degrees(a)), 1) for a in tgt[:5]] +
                    [round(float((tgt[5] - self.sim.lower[5]) / (self.sim.upper[5] - self.sim.lower[5]) * 100), 1)],
             tip=[round(float(a), 4) for a in self.sim.tip_pos()],
             finger=[round(float(a), 3) for a in self.sim.data.site_xmat[self.sim.tip].reshape(3, 3)[:, 0]],
             points=[[round(float(a), 4) for a in d.xpos[m.body(b).id]] for b in ARM_POINTS],
             torque=[round(float(t), 2) for t in self.sim.torque],
             held=self.sim.held_object(),
             objects={n: [round(float(a), 4) for a in self.sim.object_pos(n)] for n in OBJECTS})

    def _emit_frame(self):
        d = self.sim.data
        emit("frame", p=np.round(d.xpos, 4).reshape(-1).tolist(), q=np.round(d.xquat, 4).reshape(-1).tolist(),
             tip=[round(float(a), 4) for a in self.sim.tip_pos()])

    # ---------- 학생 코드 ----------
    def _run_code(self, code):
        self.ctx.lock.acquire()
        self.ctx.stop_flag = False
        self.stop_requested_at = None
        emit("run_start")
        status = "ok"
        try:
            exec(compile(code, CODE_NAME, "exec"), {"__name__": "__main__"})
        except live.StopRun:
            status = "stopped"
        except SystemExit:
            pass
        except BaseException as e:
            status = "error"
            traceback.print_exception(type(e), e, e.__traceback__.tb_next, file=sys.stdout)
        finally:
            self.ctx.stop_flag = False
            self.code_running = False
            self.ctx.lock.release()
            sys.stdout.flush()
            emit("run_end", status=status)

    def _force_stop_if_stuck(self):
        if (self.stop_requested_at is None or self.injected or not self.code_running):
            return
        if time.perf_counter() - self.stop_requested_at > 0.5 and self.ctx.remaining == 0 and self.ctx.stop_flag:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(self.worker.ident), ctypes.py_object(live.StopRun))
            self.injected = True

    # ---------- 메인 루프 ----------
    def loop(self):
        threading.Thread(target=self._read_stdin, daemon=True).start()
        emit("ready")
        wall0, sim0 = time.perf_counter(), self.sim.data.time
        while self.viewer is None or self.viewer.is_running():
            try:
                while True:
                    if not self._handle(self.commands.get_nowait()):
                        return
            except queue.Empty:
                pass
            self._force_stop_if_stuck()
            if not self.ctx.lock.acquire(timeout=0.005):
                continue
            try:
                busy = self.code_running
                if not busy:
                    self._panel_tick()
                n = min(IDLE_CHUNK, self.ctx.remaining) if busy else IDLE_CHUNK
                self.sim.step(n)
                if busy and n:
                    self.ctx.remaining -= n
                    if self.ctx.remaining == 0:
                        self.ctx.done.set()
                if self.viewer:
                    self.viewer.sync()
                now = time.perf_counter()
                if self.stream and now - self.last_frame > FRAME_EVERY:
                    self.last_frame = now
                    self._emit_frame()
                if now - self.last_state > STATE_EVERY:
                    self.last_state = now
                    self._emit_state()
            finally:
                self.ctx.lock.release()
            if self.viewer is None and not self.stream:
                continue
            lag = (self.sim.data.time - sim0) - (time.perf_counter() - wall0)
            if lag > 0:
                time.sleep(lag)
            elif lag < -0.2:
                wall0, sim0 = time.perf_counter(), self.sim.data.time
            if n == 0:
                time.sleep(0.001)


if __name__ == "__main__":
    Server(headless="--headless" in sys.argv, stream="--stream" in sys.argv).loop()
