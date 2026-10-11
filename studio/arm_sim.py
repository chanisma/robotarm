"""SO-101 로봇팔 3D 시뮬레이터 (MuJoCo, Windows 지원, 순수 Python).

로봇 모델은 MuJoCo Menagerie 의 robotstudio_so101(Apache-2.0)을 쓴다. TheRobotStudio/SO-ARM100 의 공식 MJCF
(so101_new_calib.xml, LeRobot 'new calib' 기준)에서 유도됐고 영점·관절 범위가 같으며, 물건을 집을 수 있도록
집게에 단순 충돌 도형(상자·구)을 넣은 버전이다. (원본 메시 충돌은 볼록 껍질 때문에 두 턱 사이가 막혀 집을 수 없음)
여기에 바닥, 집기 실험용 상자, 목표 구역을 MjSpec 으로 덧붙인다.
관절마다 STS3215 서보를 흉내 낸 '위치 제어' 액추에이터가 있어서 목표 각도(ctrl)를 주면 모터가 그 각도로 간다.
"""
from pathlib import Path

import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SO101_XML = ROOT / "third_party/mujoco_menagerie/robotstudio_so101/so101.xml"

JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
TIP_SITE = "gripperframe"
OBJECTS = {            # 이름: (색 rgba, 처음 위치 x, y) — 한 변 3 cm 상자
    "red": ((0.93, 0.27, 0.27, 1), 0.22, 0.08),
    "blue": ((0.25, 0.52, 0.96, 1), 0.25, -0.06),
    "green": ((0.20, 0.78, 0.45, 1), 0.17, -0.14),
}
CUBE = 0.015           # 상자 반쪽 크기 (m)
ZONE = (0.16, 0.18)    # 목표 구역 중심 (x, y) — 바닥의 노란 원
SIM_DT = 0.002


def load_model():
    spec = mujoco.MjSpec.from_file(str(SO101_XML))
    wb = spec.worldbody
    spec.option.timestep = SIM_DT
    wb.add_geom(name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[1, 1, 0.05], rgba=[0.12, 0.14, 0.17, 1],
                friction=[1.0, 0.005, 0.0001])
    for name, (rgba, x, y) in OBJECTS.items():
        b = wb.add_body(name=f"obj_{name}", pos=[x, y, CUBE + 0.001])
        b.add_freejoint(name=f"obj_{name}_free")
        b.add_geom(name=f"obj_{name}", type=mujoco.mjtGeom.mjGEOM_BOX, size=[CUBE] * 3, rgba=list(rgba), mass=0.03,
                   friction=[1.5, 0.01, 0.0005], condim=4, group=2)
    wb.add_geom(name="zone", type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[0.045, 0.0005, 0], pos=[ZONE[0], ZONE[1], 0.0005],
                rgba=[1.0, 0.82, 0.4, 0.35], contype=0, conaffinity=0, group=2)
    return spec.compile()


class ArmSim:
    def __init__(self):
        self.model = load_model()
        self.data = mujoco.MjData(self.model)
        m = self.model
        self.qadr = np.array([m.jnt_qposadr[m.joint(j).id] for j in JOINTS])
        self.dadr = np.array([m.jnt_dofadr[m.joint(j).id] for j in JOINTS])
        self.act = np.array([m.actuator(j).id for j in JOINTS])
        self.lower = np.array([m.jnt_range[m.joint(j).id][0] for j in JOINTS])
        self.upper = np.array([m.jnt_range[m.joint(j).id][1] for j in JOINTS])
        self.tip = m.site(TIP_SITE).id
        self.obj_body = {n: m.body(f"obj_{n}").id for n in OBJECTS}
        self.obj_qadr = {n: m.jnt_qposadr[m.joint(f"obj_{n}_free").id] for n in OBJECTS}
        self.reset()

    # ---------- 상태 ----------
    def reset(self, objects=True):
        """팔을 접은 자세로 되돌린다. objects=True 면 상자도 처음 위치로, False 면 상자는 그대로 둔다."""
        saved = None if objects else self.data.qpos.copy()
        mujoco.mj_resetData(self.model, self.data)
        if saved is not None:
            keep = np.ones(self.model.nq, bool)
            keep[self.qadr] = False
            self.data.qpos[keep] = saved[keep]
        self.data.qpos[self.qadr] = REST_RAD
        self.data.ctrl[self.act] = REST_RAD
        mujoco.mj_forward(self.model, self.data)

    def reset_objects(self):
        for name, (_, x, y) in OBJECTS.items():
            a = self.obj_qadr[name]
            self.data.qpos[a:a + 7] = [x, y, CUBE + 0.001, 1, 0, 0, 0]
            dof = self.model.jnt_dofadr[self.model.joint(f"obj_{name}_free").id]
            self.data.qvel[dof:dof + 6] = 0
        mujoco.mj_forward(self.model, self.data)

    @property
    def q(self):
        return self.data.qpos[self.qadr].copy()

    @property
    def target(self):
        return self.data.ctrl[self.act].copy()

    @property
    def torque(self):
        return self.data.actuator_force[self.act].copy()

    def set_target(self, q):
        self.data.ctrl[self.act] = np.clip(q, self.lower, self.upper)

    def tip_pos(self):
        return self.data.site_xpos[self.tip].copy()

    def tip_zaxis(self):
        return self.data.site_xmat[self.tip].reshape(3, 3)[:, 2].copy()

    def object_pos(self, name):
        return self.data.xpos[self.obj_body[name]].copy()

    def held_object(self):
        """집게의 두 턱(고정 턱과 움직이는 턱)이 동시에 닿아 있는 상자 = 집은 상자 이름 (없으면 None)."""
        m, d = self.model, self.data
        jaw = m.body("moving_jaw_so101_v1").id
        fixed = m.body("gripper").id
        touching = {}
        for i in range(d.ncon):
            c = d.contact[i]
            bodies = {m.geom_bodyid[c.geom1], m.geom_bodyid[c.geom2]}
            for name, ob in self.obj_body.items():
                if ob in bodies:
                    touching.setdefault(name, set()).update(bodies & {jaw, fixed})
        for name, parts in touching.items():
            if parts == {jaw, fixed}:
                return name
        return None

    def step(self, n=1):
        for _ in range(n):
            mujoco.mj_step(self.model, self.data)


# 자세 (도) — JOINTS 순서
POSES = {
    "rest":  [0, -100, 90, 50, 0, 0],      # 접기 (LeRobot 휴식 자세와 비슷, 집게 끝이 바닥 위 4.5 cm)
    "ready": [0, -30, 50, 60, 0, 20],      # 준비: 집게가 앞 아래를 봄
    "zero":  [0, 0, 0, 0, 0, 0],           # 모든 관절 0° (new calib 기준)
}
REST_RAD = np.radians(POSES["rest"])


# ---------- 역기구학 (끝점 위치 → 관절 각도) ----------
ARM_DOF = 5                                    # 집게를 뺀 팔 관절 5개


def _solve_ik(sim, target, down=True, q_start=None, iters=400, w_rot=0.3):
    """집게 끝(gripperframe)을 target(x, y, z, m)에 놓는 팔 관절 5개의 각도(rad)를 찾는다.
    down=True 이면 집게가 바닥을 수직으로 내려다보게(집게 방향 = −z) 한다. 감쇠 최소제곱(DLS) 반복법.
    반환: (관절 6개 rad, 성공 여부, 남은 위치 오차 m)"""
    m = sim.model
    d = mujoco.MjData(m)
    d.qpos[:] = sim.data.qpos
    q = sim.q if q_start is None else np.array(q_start, float)
    target = np.asarray(target, float)
    jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
    cols = sim.dadr[:ARM_DOF]
    err_p = np.inf
    history = []
    for k in range(iters):
        d.qpos[sim.qadr] = q
        mujoco.mj_kinematics(m, d)
        mujoco.mj_comPos(m, d)
        pos = d.site_xpos[sim.tip]
        err_p = target - pos
        e, J = [err_p], [None]
        mujoco.mj_jacSite(m, d, jp, jr, sim.tip)
        J[0] = jp[:, cols]
        if down:
            finger = d.site_xmat[sim.tip].reshape(3, 3)[:, 0]          # 집게가 가리키는 방향
            err_r = np.cross(finger, [0, 0, -1.0])
            e.append(w_rot * err_r)
            J.append(w_rot * jr[:, cols])
        e, J = np.concatenate(e), np.vstack(J)
        history.append(float(np.linalg.norm(e)))
        if k >= 30 and history[-30] - history[-1] < 1e-5:     # 30 번 동안 거의 나아지지 않으면 그만
            break
        if np.linalg.norm(err_p) < 1e-3 and (not down or np.linalg.norm(err_r) < 0.01):
            break
        # 한계에 닿은 관절이 더 밖으로 가려 하면 그 관절은 이번 걸음에서 빼고 나머지로 다시 푼다 (활성 집합)
        free = np.ones(ARM_DOF, bool)
        for _ in range(ARM_DOF):
            Jf = J * free
            dq = Jf.T @ np.linalg.solve(Jf @ Jf.T + 1e-4 * np.eye(len(e)), e)
            stuck = free & (((q[:ARM_DOF] >= sim.upper[:ARM_DOF] - 1e-6) & (dq > 0)) |
                            ((q[:ARM_DOF] <= sim.lower[:ARM_DOF] + 1e-6) & (dq < 0)))
            if not stuck.any():
                break
            free &= ~stuck
        q[:ARM_DOF] = np.clip(q[:ARM_DOF] + np.clip(dq * free, -0.2, 0.2), sim.lower[:ARM_DOF], sim.upper[:ARM_DOF])
    ok = np.linalg.norm(err_p) < 5e-3
    return q, ok, float(np.linalg.norm(err_p))


def tilt_deg(sim, q):
    """관절 q 에서 집게가 수직 아래(−z)에서 몇 도 기울었는지."""
    m = sim.model
    d = mujoco.MjData(m)
    d.qpos[:] = sim.data.qpos
    d.qpos[sim.qadr] = q
    mujoco.mj_kinematics(m, d)
    finger = d.site_xmat[sim.tip].reshape(3, 3)[:, 0]
    return float(np.degrees(np.arccos(np.clip(-finger[2], -1, 1))))


MAX_TILT = 30.0          # down=True 인데 정확히 수직이 안 되면, 이만큼까지 기울어도 허용 (상자 집기에 충분)


_DOWN_TABLE = None


def _down_table(sim):
    """허리 0° 일 때 집게가 거의 수직 아래(10° 이내)를 보는 (어깨, 팔꿈치, 손목) 조합과 그때 집게 끝 (앞 거리, 높이).
    한 번만 계산해 두고 역기구학의 시작 자세로 쓴다 (손목이 한계 근처일 때 반복법이 길을 잃는 것 방지)."""
    global _DOWN_TABLE
    if _DOWN_TABLE is None:
        m = sim.model
        d = mujoco.MjData(m)
        rows = []
        for a in np.radians(np.arange(-100, 101, 4)):
            for b in np.radians(np.arange(-96, 97, 4)):
                for c in np.radians(np.arange(-94, 95, 4)):
                    d.qpos[sim.qadr[:4]] = [0, a, b, c]
                    mujoco.mj_kinematics(m, d)
                    if -d.site_xmat[sim.tip].reshape(3, 3)[2, 0] > np.cos(np.radians(10)):
                        p = d.site_xpos[sim.tip]
                        rows.append((p[0], p[2], a, b, c))
        _DOWN_TABLE = np.array(rows)
    return _DOWN_TABLE


def _down_seed(sim, target, roll):
    """목표 (x, y, z) 에 가장 가까운 '집게 아래' 표 항목 → 시작 자세 (관절 5개, rad)."""
    x, y, z = target
    pan_axis_x = sim.model.body("shoulder").pos[0]                # 허리 회전축은 받침 원점보다 약 3.9 cm 앞
    pan = -np.arctan2(y, x - pan_axis_x)                         # 허리 + = 오른쪽(−y)
    r = pan_axis_x + np.hypot(x - pan_axis_x, y)
    t = _down_table(sim)
    i = np.argmin((t[:, 0] - r) ** 2 + (t[:, 1] - z) ** 2)
    return [np.degrees(pan), *np.degrees(t[i, 2:5]), np.degrees(roll)]


IK_SEEDS = [[0, -30, 50, 60, 0], [0, 20, -20, 80, 0], [0, 40, -60, 90, 0], [0, -60, 80, 40, 0], [0, 0, 0, 0, 0]]


def solve_ik(sim, target, down=True, q_start=None):
    """여러 시작 자세에서 풀어 보고 가장 정확한 답을 고른다 (팔꿈치 방향 등 국소해에 갇히는 것 방지).
    down=True 이면 먼저 '정확히 수직 아래'로 풀고, 안 되면 집게 기울기를 MAX_TILT 까지 허용해 다시 푼다."""
    base = sim.q if q_start is None else np.array(q_start, float)
    pan = np.arctan2(target[1], target[0])                       # 허리는 목표 쪽을 향하게 시작

    seeds = [None] + ([("table", _down_seed(sim, target, base[4]))] if down else []) + IK_SEEDS

    def search(w_rot):
        best = None
        for seed in seeds:
            q0 = base.copy()
            if isinstance(seed, tuple):                          # 표에서 고른 시작 자세 (허리 각도 포함)
                q0[:ARM_DOF] = np.radians(seed[1])
            elif seed is not None:
                q0[:ARM_DOF] = np.radians(seed)
                q0[0] = pan
            q, ok, err = _solve_ik(sim, target, down, q0, w_rot=w_rot)
            if down and ok and tilt_deg(sim, q) > MAX_TILT:
                ok = False
            if best is None or (ok and not best[1]) or (ok == best[1] and err < best[2] - 1e-4):
                best = (q, ok, err)
            if ok:
                break                                            # 처음 찾은 답 사용 (지금 자세 → 표 → 일반 순서라 움직임이 작은 답이 먼저)
        return best

    best = search(0.3)
    if down and not best[1]:
        relaxed = search(0.03)                                   # 수직 조건을 약하게 → 위치 우선
        if relaxed[1] or relaxed[2] < best[2]:
            best = relaxed
    return best
