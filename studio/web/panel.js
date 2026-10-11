// 조작 패널: 슬라이더·숫자·그림으로 값을 바꾸며 로봇팔이 어떻게 움직이는지 보고, 같은 동작의 코드를 보여 준다.
const SVGNS = "http://www.w3.org/2000/svg";
const C = { grid: "#1e252f", text: "#7b8596", link: "#f5b301", joint: "#e6e9ef", tip: "#ff5d6c", target: "#7aa8ff", zone: "#ffd166" };
const SEND_MS = 50, TIP_MS = 150;
const rad = (d) => (d * Math.PI) / 180;

function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
function text(svg, x, y, str, attrs = {}) {
  el("text", { x, y, fill: C.text, "font-size": 11, ...attrs }, svg).textContent = str;
}
function esc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;"); }
function colorCode(lines) {
  return lines.map((l) => {
    if (l.trim().startsWith("#")) return `<span class="c">${esc(l)}</span>`;
    let h = esc(l);
    h = h.replace(/("[^"]*")/g, '<span class="s">$1</span>');
    h = h.replace(/((?:arm|robot)\.\w+)/g, '<span class="f">$1</span>');
    h = h.replace(/(?<![\w"])(-?\d+(?:\.\d+)?)(?![\w"])/g, '<span class="n">$1</span>');
    h = h.replace(/(#.*)$/, '<span class="c">$1</span>');
    return h;
  }).join("\n");
}

export class Panel {
  constructor(meta, send, insertCode) {
    this.m = meta;
    this.sendRaw = send;
    this.insertCode = insertCode;
    this.goal = null;            // 관절 5개(°) + 집게(%) — LeRobot 과 같은 단위
    this.state = null;
    this.locked = false;
    this.tab = "joint";
    this.lastJoint = "elbow_flex";
    this.tipTarget = { x: 22, y: 8, z: 6 };   // cm
    this.ik = null;
    this.pending = null; this.timer = null; this.tipTimer = null;
    this._tabs();
    this._joint();
    this._tip();
    this._grip();
    document.querySelectorAll("#pose-seg button").forEach((b) => b.onclick = () => this.pose(b.dataset.pose));
    document.getElementById("btn-insert").onclick = () => this.insertCode(this.codeLines().join("\n") + "\n");
    this.refreshCode();
  }

  // ---------- 공통 ----------
  _tabs() {
    document.querySelectorAll(".tab").forEach((b) => b.onclick = () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
      document.querySelectorAll(".tab-page").forEach((p) => p.classList.toggle("active", p.dataset.page === b.dataset.tab));
      this.tab = b.dataset.tab;
      this.refreshCode();
      if (this.state) this.draw();
    });
  }

  // 슬라이더 + 숫자 칸 (Enter·칸 밖 클릭·↑↓ 로 적용, 범위 밖 값은 맞춰 줌)
  slider(parent, { name, code, min, max, step = 1, value, cls = "", meaning, unit = "", prefix = "", onInput }) {
    const digits = step < 1 ? String(step).split(".")[1].length : 0;
    const wrap = document.createElement("div");
    wrap.className = "slider";
    wrap.innerHTML = `<div class="slider-top"><span class="slider-name">${name}${code ? `<code>${code}</code>` : ""}</span>
      <span class="slider-val">${prefix ? `<span class="muted">${prefix}</span>` : ""}
        <input type="number" class="num" min="${min}" max="${max}" step="${step}" value="${value}" title="숫자를 쓰고 Enter">
        <span class="unit">${unit}</span><span class="extra"></span></span></div>
      <input type="range" class="${cls}" min="${min}" max="${max}" step="${step}" value="${value}">
      ${meaning ? `<div class="slider-meaning">${meaning}</div>` : ""}`;
    parent.appendChild(wrap);
    const input = wrap.querySelector("input[type=range]"), num = wrap.querySelector("input.num"), extra = wrap.querySelector(".extra");
    const show = (v) => { if (document.activeElement !== num) num.value = (+v).toFixed(digits); };
    input.oninput = () => { show(input.value); onInput(+input.value); };
    const apply = () => {
      let v = parseFloat(num.value);
      if (Number.isNaN(v)) { num.value = (+input.value).toFixed(digits); return; }
      const typed = v;
      v = +Math.min(max, Math.max(min, Math.round(v / step) * step)).toFixed(digits);
      num.value = v.toFixed(digits);
      num.classList.toggle("clamped", v !== typed);
      input.value = v;
      onInput(v);
    };
    num.addEventListener("change", apply);
    num.addEventListener("input", () => num.classList.remove("clamped"));
    num.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter") { apply(); num.blur(); }
      if (e.key === "Escape") { num.value = (+input.value).toFixed(digits); num.blur(); }
      if (e.key === "ArrowUp" || e.key === "ArrowDown") setTimeout(apply);
    });
    show(value);
    return { input, num, set: (v) => { input.value = v; show(v); }, readout: (h) => { extra.innerHTML = h; } };
  }

  // ---------- ① 관절 하나씩 ----------
  _joint() {
    const box = document.getElementById("joint-sliders");
    const cls = { shoulder_pan: "pan", shoulder_lift: "thigh", elbow_flex: "shank", wrist_flex: "hipx", wrist_roll: "roll", gripper: "grip" };
    this.jsl = {};
    this.m.joints.forEach((j, i) => {
      const info = this.m.jointInfo[j];
      const [lo, hi] = info.range;
      this.jsl[j] = this.slider(box, {
        name: info.name, code: j, min: Math.round(lo), max: Math.round(hi), value: 0, cls: cls[j], prefix: "목표",
        unit: j === "gripper" ? "%" : "°", meaning: `${info.meaning}  (범위 ${Math.round(lo)} ~ ${Math.round(hi)})`,
        onInput: (v) => this.onJoint(i, v),
      });
    });
  }

  onJoint(i, v) {
    if (!this.goal) return;
    this.goal[i] = v;
    this.lastJoint = this.m.joints[i];
    this.queue({ op: "joints", values: [...this.goal] });
    this.refreshCode();
  }

  syncSliders() {
    if (!this.goal) return;
    this.m.joints.forEach((j, i) => this.jsl[j].set(this.goal[i]));
    this.gsl?.set(this.goal[5]);
  }

  // 옆에서 본 팔 (팔이 놓인 수직 평면) + 위에서 본 팔
  drawArm() {
    const st = this.state;
    const side = document.getElementById("side-view"), top = document.getElementById("top-view");
    side.innerHTML = top.innerHTML = "";
    const pts = [[0, 0, 0.06], ...st.points, st.tip];
    const phi = Math.atan2(st.tip[1], st.tip[0]);
    // 옆모습
    const s = 480, ox = 40, oy = 225;
    for (let cm = 0; cm <= 45; cm += 10) { const x = ox + cm / 100 * s; el("line", { x1: x, y1: 0, x2: x, y2: 250, stroke: C.grid }, side); text(side, x, 246, cm, { "text-anchor": "middle", "font-size": 9 }); }
    for (let cm = 0; cm <= 40; cm += 10) { const y = oy - cm / 100 * s; el("line", { x1: 0, y1: y, x2: 280, y2: y, stroke: C.grid }, side); if (cm) text(side, 4, y - 2, cm, { "font-size": 9 }); }
    el("line", { x1: 0, y1: oy, x2: 280, y2: oy, stroke: "#3a4352", "stroke-width": 2 }, side);
    text(side, 276, 14, "옆에서 (앞 →, cm)", { "text-anchor": "end" });
    const sp = pts.map(([x, y, z]) => [ox + (x * Math.cos(phi) + y * Math.sin(phi)) * s, oy - z * s]);
    el("rect", { x: ox - 18, y: oy - 0.06 * s, width: 36, height: 0.06 * s, rx: 4, fill: "#2a313c" }, side);
    el("polyline", { points: sp.map((p) => p.join(",")).join(" "), fill: "none", stroke: C.link, "stroke-width": 7, "stroke-linecap": "round", "stroke-linejoin": "round" }, side);
    sp.slice(0, -1).forEach(([x, y]) => el("circle", { cx: x, cy: y, r: 4.5, fill: C.joint }, side));
    const [tx, ty] = sp[sp.length - 1];
    el("circle", { cx: tx, cy: ty, r: 6, fill: C.tip }, side);
    text(side, tx + 8, ty - 6, `높이 ${(st.tip[2] * 100).toFixed(1)}`, { fill: C.tip });
    // 위에서
    this.drawTop(top, 220, 250, 440, { compact: true });
  }

  // 위에서 본 그림 (앞 = 위쪽). 상자, 목표 구역, 집게 끝, (선택) 목표점
  drawTop(svg, W, H, s, { target = null, compact = false, reach = false } = {}) {
    const st = this.state;
    svg.innerHTML = "";
    const ox = W / 2, oy = H - 22;
    const P = (x, y) => [ox - y * s, oy - x * s];
    for (let cm = -30; cm <= 30; cm += 10) { const [x] = P(0, cm / 100); el("line", { x1: x, y1: 0, x2: x, y2: H, stroke: C.grid }, svg); }
    for (let cm = 0; cm <= 50; cm += 10) { const [, y] = P(cm / 100, 0); el("line", { x1: 0, y1: y, x2: W, y2: y, stroke: C.grid }, svg); if (!compact && cm) text(svg, 4, y - 2, cm, { "font-size": 9 }); }
    text(svg, W - 4, 12, compact ? "위에서" : "위에서 본 모습 (앞 ↑, cm)", { "text-anchor": "end" });
    if (reach) {
      for (const [r, dash, label] of [[0.34, "5 4", "집게 아래로: 약 34 cm"], [0.47, "2 4", "최대 47 cm"]]) {
        el("circle", { cx: ox, cy: oy, r: r * s, fill: "none", stroke: "#4b5566", "stroke-dasharray": dash }, svg);
        text(svg, ox + r * s * 0.62, oy - r * s * 0.8, label, { "font-size": 9 });
      }
    }
    const [zx, zy] = P(...this.m.zone);
    el("circle", { cx: zx, cy: zy, r: 0.045 * s, fill: "rgba(255,209,102,.18)", stroke: C.zone, "stroke-dasharray": "3 3" }, svg);
    for (const [name, rgb] of Object.entries(this.m.objects)) {
      const p = st.objects[name]; if (!p) continue;
      const [cx, cy] = P(p[0], p[1]), h = this.m.cube * s;
      el("rect", { x: cx - h, y: cy - h, width: 2 * h, height: 2 * h, rx: 2, fill: `rgb(${rgb.map((c) => Math.round(c * 255)).join(",")})`, opacity: p[2] > 0.025 ? 0.55 : 1 }, svg);
    }
    el("rect", { x: ox - 14, y: oy - 10, width: 28, height: 20, rx: 4, fill: "#2a313c" }, svg);
    const pts = [[0, 0], ...st.points.map((p) => [p[0], p[1]]), [st.tip[0], st.tip[1]]].map(([x, y]) => P(x, y));
    el("polyline", { points: pts.map((p) => p.join(",")).join(" "), fill: "none", stroke: C.link, "stroke-width": compact ? 5 : 6, "stroke-linecap": "round", opacity: 0.85 }, svg);
    const [tx, ty] = pts[pts.length - 1];
    el("circle", { cx: tx, cy: ty, r: 5, fill: C.tip }, svg);
    if (target) {
      const [gx, gy] = P(target.x / 100, target.y / 100);
      el("circle", { cx: gx, cy: gy, r: 8, fill: "none", stroke: C.target, "stroke-width": 2 }, svg);
      el("line", { x1: gx - 12, y1: gy, x2: gx + 12, y2: gy, stroke: C.target }, svg);
      el("line", { x1: gx, y1: gy - 12, x2: gx, y2: gy + 12, stroke: C.target }, svg);
    }
    return { toM: (px, py) => [(oy - py) / s, (ox - px) / s] };
  }

  // ---------- ② 집게 끝 옮기기 ----------
  _tip() {
    const box = document.getElementById("tip-sliders");
    const t = this.tipTarget;
    this.tsl = {
      x: this.slider(box, { name: "앞뒤 x", min: 0, max: 45, value: t.x, unit: "cm", cls: "pan", onInput: (v) => { t.x = v; this.onTip(); } }),
      y: this.slider(box, { name: "좌우 y (+왼쪽)", min: -35, max: 35, value: t.y, unit: "cm", cls: "thigh", onInput: (v) => { t.y = v; this.onTip(); } }),
      z: this.slider(box, { name: "높이 z", min: 0, max: 40, value: t.z, unit: "cm", cls: "shank", onInput: (v) => { t.z = v; this.onTip(); } }),
    };
    this.downBox = document.getElementById("tip-down");
    this.downBox.onchange = () => this.onTip();
    this._dragTop("tip-view", 260, 260, 520, (x, y) => {
      t.x = Math.max(0, Math.min(45, Math.round(x * 100))); t.y = Math.max(-35, Math.min(35, Math.round(y * 100)));
      this.tsl.x.set(t.x); this.tsl.y.set(t.y); this.onTip();
    });
  }

  _dragTop(id, W, H, s, onPick) {
    const svg = document.getElementById(id);
    let dragging = false;
    const pick = (e) => {
      const r = svg.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width * W, py = (e.clientY - r.top) / r.height * H;
      onPick((H - 22 - py) / s, (W / 2 - px) / s);
    };
    svg.addEventListener("pointerdown", (e) => { dragging = true; svg.setPointerCapture(e.pointerId); pick(e); });
    svg.addEventListener("pointermove", (e) => dragging && pick(e));
    svg.addEventListener("pointerup", () => { dragging = false; });
  }

  onTip() {
    this.refreshCode();
    if (this.state) this.draw();
    clearTimeout(this.tipTimer);
    this.tipTimer = setTimeout(() => {
      const t = this.tipTarget;
      this.send({ op: "tip", x: t.x / 100, y: t.y / 100, z: t.z / 100, down: this.downBox.checked });
    }, TIP_MS);
  }

  onIk(ev) {
    this.ik = ev;
    const out = document.getElementById("ik-result");
    if (ev.ok) {
      out.className = "ik-result";
      out.innerHTML = `→ 계산된 각도: ${ev.deg.map((d, i) => `<span title="${this.m.joints[i]}">${this.m.jointInfo[this.m.joints[i]].name} ${d.toFixed(0)}°</span>`).join(" · ")}`;
    } else {
      out.className = "ik-result bad";
      out.textContent = this.downBox.checked && ev.err < 0.5
        ? "✖ 위치에는 닿지만, 이 높이에서는 집게를 아래로 향하게 할 수 없어요 (손목 한계) — 더 낮게 하거나 '수직으로 내려다보기'를 끄세요"
        : `✖ 닿을 수 없는 위치예요 (가장 가까워도 ${ev.err} cm 떨어짐)` + (this.downBox.checked ? " — 더 가깝게·낮게 하거나 '수직으로 내려다보기'를 끄세요" : "");
    }
    this.goal = null;          // 다음 상태에서 새 관절 목표를 받아 옴
    this.refreshCode();
  }

  // ---------- ③ 집기 ----------
  _grip() {
    const box = document.getElementById("grip-slider");
    this.gsl = this.slider(box, { name: "집게 벌리기", code: "gripper", min: 0, max: 100, value: 0, unit: "%", cls: "grip",
      meaning: "0 % = 닫힘, 100 % = 열림", onInput: (v) => this.onJoint(5, v) });
    document.getElementById("grip-open").onclick = () => { this.gsl.set(100); this.onJoint(5, 100); };
    document.getElementById("grip-close").onclick = () => { this.gsl.set(0); this.onJoint(5, 0); };
    document.getElementById("objects-reset").onclick = () => this.send({ op: "reset_objects" });
    const list = document.getElementById("objects");
    this.objRows = {};
    const names = { red: "빨강", blue: "파랑", green: "초록" };
    for (const [name, rgb] of Object.entries(this.m.objects)) {
      const row = document.createElement("div");
      row.className = "obj-row";
      row.innerHTML = `<span class="swatch" style="background:rgb(${rgb.map((c) => Math.round(c * 255)).join(",")})"></span>
        <b>${names[name] ?? name}</b> <code class="muted">"${name}"</code><span class="pos"></span>
        <button class="btn tiny ghost">위로 가기</button>`;
      row.querySelector("button").onclick = () => {
        const p = this.state?.objects[name]; if (!p) return;
        Object.assign(this.tipTarget, { x: Math.round(p[0] * 100), y: Math.round(p[1] * 100), z: 8 });
        for (const k of ["x", "y", "z"]) this.tsl[k].set(this.tipTarget[k]);
        this.downBox.checked = true;
        this.lastGoto = name;
        this.onTip();
      };
      list.appendChild(row);
      this.objRows[name] = row.querySelector(".pos");
    }
    this._dragTop("grip-view", 260, 260, 520, () => {});
  }

  // ---------- 그리기 / 코드 ----------
  draw() {
    if (this.tab === "joint") this.drawArm();
    if (this.tab === "tip") this.drawTop(document.getElementById("tip-view"), 260, 260, 520, { target: this.tipTarget, reach: true });
    if (this.tab === "grip") this.drawTop(document.getElementById("grip-view"), 260, 260, 520, {});
  }

  codeLines() {
    if (this.tab === "joint") {
      const j = this.lastJoint, i = this.m.joints.indexOf(j);
      const v = Math.round(this.goal ? this.goal[i] : +this.jsl[j].input.value);
      const name = this.m.jointInfo[j].name;
      const line = j === "gripper" ? `arm.gripper(${v})` : `arm.set_angle("${j}", ${v})`;
      return [`# '${name}' 관절을 ${v}${j === "gripper" ? " %" : "°"} 로`, line,
        `# LeRobot 공식 형식 (실제 SO-101 에서도 같은 코드): robot.send_action({"${j}.pos": ${v.toFixed(1)}})`];
    }
    if (this.tab === "tip") {
      const t = this.tipTarget, x = (t.x / 100).toFixed(2), y = (t.y / 100).toFixed(2), z = (t.z / 100).toFixed(2);
      const down = this.downBox.checked ? "" : ", down=False";
      const lines = [`# 집게 끝을 앞 ${t.x} cm, 왼쪽 ${t.y} cm, 높이 ${t.z} cm 로 (코드는 m 단위: cm ÷ 100)`, `arm.move_tip(${x}, ${y}, ${z}${down})`];
      if (this.ik?.ok) lines.push(`# 컴퓨터가 계산한 관절 각도: ${this.ik.deg.map((d) => d.toFixed(0)).join(", ")} (°, 허리→손목 순)`);
      return lines;
    }
    const g = Math.round(this.goal ? this.goal[5] : 0);
    const lines = [`arm.gripper(${g})          # 0 = 닫힘, 100 = 열림`, `print(arm.holding())      # 집고 있는 상자 이름 (없으면 None)`];
    if (this.lastGoto) lines.unshift(`x, y, z = arm.find("${this.lastGoto}")`, `arm.move_tip(x, y, 0.08)   # 상자 위 8 cm 로`);
    return lines;
  }

  refreshCode() { document.getElementById("code-preview").innerHTML = colorCode(this.codeLines()); }

  // ---------- 보내기 / 받기 ----------
  pose(name) {
    if (this.goal) { const g = this.m.poses[name]; this.goal = [...g.slice(0, 5), this.goal[5]]; this.syncSliders(); }
    this.send({ op: "pose", name });
  }

  queue(msg) {
    this.pending = msg;
    if (!this.timer) this.timer = setTimeout(() => { this.timer = null; if (this.pending) { this.send(this.pending); this.pending = null; } }, SEND_MS);
  }

  send(msg) { if (!this.locked) this.sendRaw({ type: "panel", ...msg }); }

  setLocked(on) { this.locked = on; document.getElementById("panel-pane").classList.toggle("locked", on); }

  resync() { this.goal = null; }

  onState(st) {
    this.state = st;
    if (!this.goal) { this.goal = [...st.target]; this.syncSliders(); this.refreshCode(); }
    this.m.joints.forEach((j, i) => this.jsl[j].readout(`<span class="muted">· 실제</span> <b>${st.obs[i].toFixed(1)}${j === "gripper" ? "%" : "°"}</b>`));
    this.gsl.readout(`<span class="muted">· 실제</span> <b>${st.obs[5].toFixed(0)}%</b>`);
    const held = document.getElementById("held-status");
    held.className = "held" + (st.held ? " on" : "");
    held.textContent = st.held ? `✔ "${st.held}" 상자를 잡고 있어요` : "잡은 상자 없음";
    for (const [name, p] of Object.entries(st.objects)) this.objRows[name].textContent = `(${(p[0] * 100).toFixed(1)}, ${(p[1] * 100).toFixed(1)}, ${(p[2] * 100).toFixed(1)}) cm`;
    this.draw();
  }
}
