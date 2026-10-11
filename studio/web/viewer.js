// 3D 화면: MuJoCo 모델의 시각용 메시·색으로 SO-101 과 상자를 만들고, 시뮬레이터가 보내는 바디 자세(frame)를 적용한다.
// 좌표계는 MuJoCo 와 같은 Z-up. 1 칸 = 5 cm 격자.
import * as THREE from "three";
import { OrbitControls } from "/web/vendor/OrbitControls.js";

const TRAIL_MAX = 600;   // 자취 점 개수 (30 Hz 로 약 20 초)

export class Viewer {
  constructor(el) {
    this.el = el;
    this.bodies = [];
    this.showTrail = true;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    el.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.Fog(0x10141a, 1.6, 4.5);
    this.camera = new THREE.PerspectiveCamera(38, 1, 0.005, 20);
    this.camera.up.set(0, 0, 1);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.maxPolarAngle = Math.PI * 0.495;
    this.controls.minDistance = 0.15;
    this.controls.maxDistance = 2.5;
    this.resetView();
    this._lights();
    this._floor();
    this._trail();
    new ResizeObserver(() => this._resize()).observe(el);
    this._resize();
    this.renderer.setAnimationLoop(() => { this.controls.update(); this.renderer.render(this.scene, this.camera); });
  }

  _lights() {
    this.scene.add(new THREE.HemisphereLight(0xdfe8ff, 0x1a1d22, 1.0));
    const key = new THREE.DirectionalLight(0xffffff, 2.3);
    key.position.set(0.8, -0.7, 1.4);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    const sc = key.shadow.camera;
    sc.left = -0.6; sc.right = 0.6; sc.top = 0.6; sc.bottom = -0.6; sc.near = 0.2; sc.far = 4;
    key.shadow.bias = -0.0003;
    key.shadow.radius = 3;
    this.scene.add(key);
    const rim = new THREE.DirectionalLight(0x8fb4ff, 0.7);
    rim.position.set(-1, 1, 0.8);
    this.scene.add(rim);
  }

  _floor() {
    const ground = new THREE.Mesh(new THREE.CircleGeometry(6, 64),
      new THREE.MeshStandardMaterial({ color: 0x161b22, roughness: 0.95 }));
    ground.receiveShadow = true;
    this.scene.add(ground);
    for (const [size, div, c1, c2, z] of [[3, 60, 0x2c3542, 0x212833, 0.0006], [3, 15, 0x3a4658, 0x2a3341, 0.0007]]) {
      const g = new THREE.GridHelper(size, div, c1, c2);
      g.rotation.x = Math.PI / 2;
      g.position.z = z;
      this.scene.add(g);
    }
  }

  _trail() {
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(new Float32Array(TRAIL_MAX * 3), 3));
    geom.setAttribute("color", new THREE.BufferAttribute(new Float32Array(TRAIL_MAX * 3), 3));
    geom.setDrawRange(0, 0);
    this.trailPts = [];
    this.trailLine = new THREE.Line(geom, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.95 }));
    this.trailLine.frustumCulled = false;
    this.scene.add(this.trailLine);
    this.tipDot = new THREE.Mesh(new THREE.SphereGeometry(0.006, 16, 12),
      new THREE.MeshBasicMaterial({ color: 0xff5d6c, depthTest: false, transparent: true }));
    this.tipDot.renderOrder = 10;
    this.scene.add(this.tipDot);
  }

  clearTrail() { this.trailPts = []; this._drawTrail(); }

  setTrailVisible(on) {
    this.showTrail = on;
    this.trailLine.visible = on;
    this.tipDot.visible = on;
  }

  _drawTrail() {
    const pos = this.trailLine.geometry.attributes.position, col = this.trailLine.geometry.attributes.color;
    const n = this.trailPts.length;
    for (let i = 0; i < n; i++) {
      const p = this.trailPts[i], a = 0.15 + 0.85 * (i / Math.max(1, n - 1));   // 오래된 점일수록 흐리게
      pos.setXYZ(i, p[0], p[1], p[2]);
      col.setXYZ(i, 1.0 * a, 0.36 * a, 0.42 * a);
    }
    pos.needsUpdate = col.needsUpdate = true;
    this.trailLine.geometry.setDrawRange(0, n);
  }

  async load() {
    const scene = await (await fetch("/api/scene")).json();
    const meshCache = {};
    const loadMesh = (mid) => (meshCache[mid] ??= fetch(`/api/mesh/${mid}`).then((r) => r.arrayBuffer()).then((buf) => {
      const [nv, nf] = new Uint32Array(buf, 0, 2);
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(buf, 8, nv * 3), 3));
      g.setIndex(new THREE.BufferAttribute(new Uint32Array(buf, 8 + nv * 12, nf * 3), 1));
      g.computeVertexNormals();
      return g;
    }));
    for (let i = 0; i < scene.nbody; i++) {
      const grp = new THREE.Group();
      this.scene.add(grp);
      this.bodies.push(grp);
    }
    const mats = {};
    const matFor = (rgba) => {
      const key = rgba.join(",");
      if (!mats[key]) {
        const dark = rgba[0] < 0.3;
        mats[key] = new THREE.MeshStandardMaterial({
          color: new THREE.Color(rgba[0], rgba[1], rgba[2]), transparent: rgba[3] < 1, opacity: rgba[3],
          metalness: dark ? 0.35 : 0.05, roughness: dark ? 0.45 : 0.6,
        });
      }
      return mats[key];
    };
    for (const g of scene.geoms) {
      let geom;
      if (g.type === "mesh") geom = await loadMesh(g.mesh);
      else if (g.type === "box") geom = new THREE.BoxGeometry(2 * g.size[0], 2 * g.size[1], 2 * g.size[2]);
      else if (g.type === "cylinder") geom = new THREE.CylinderGeometry(g.radius, g.radius, 2 * g.half, 48).rotateX(Math.PI / 2);
      else geom = new THREE.SphereGeometry(g.radius, 24, 16);
      const mesh = new THREE.Mesh(geom, matFor(g.rgba));
      mesh.position.set(...g.pos);
      mesh.quaternion.set(g.quat[1], g.quat[2], g.quat[3], g.quat[0]);
      mesh.castShadow = g.type !== "cylinder";
      mesh.receiveShadow = true;
      this.bodies[g.body].add(mesh);
    }
  }

  applyFrame(p, q, tip) {
    for (let i = 0; i < this.bodies.length; i++) {
      const b = this.bodies[i];
      b.position.set(p[3 * i], p[3 * i + 1], p[3 * i + 2]);
      b.quaternion.set(q[4 * i + 1], q[4 * i + 2], q[4 * i + 3], q[4 * i]);
    }
    if (tip) {
      this.tipDot.position.set(...tip);
      const last = this.trailPts[this.trailPts.length - 1];
      if (!last || Math.hypot(tip[0] - last[0], tip[1] - last[1], tip[2] - last[2]) > 0.002) {
        this.trailPts.push(tip);
        if (this.trailPts.length > TRAIL_MAX) this.trailPts.shift();
        if (this.showTrail) this._drawTrail();
      }
    }
  }

  resetView() {
    this.camera.position.set(0.62, -0.55, 0.42);
    this.controls.target.set(0.14, 0.0, 0.08);
  }

  _resize() {
    const w = this.el.clientWidth, h = this.el.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.renderer.domElement.style.width = w + "px";
    this.renderer.domElement.style.height = h + "px";
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }
}
