// Studio renderer for the Shorts engine.
//   node studio3d.cjs jobs.json
// jobs.json = { objects: [{ out, type, w, h, fps, frames, T0, accent, ...params }], icons: [{ name, size, stroke, out }] }
// 3D hero objects are built with Three.js (studio lighting via RoomEnvironment, ACES tone mapping) and rendered
// frame by frame to transparent PNGs in headless Chromium (WebGL2 / SwiftShader). Icons are Lucide SVGs
// rasterized to white-on-transparent PNGs with an absolute, uniform stroke width.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const NM = path.join(__dirname, 'node_modules');

const HTML = `<!doctype html><html><head><style>html,body{margin:0;background:transparent}</style>
<script type="importmap">{"imports":{
  "three":"/nm/three/build/three.module.js","three/addons/":"/nm/three/examples/jsm/",
  "d3-geo":"/nm/d3-geo/dist/d3-geo.mjs","d3-array":"/nm/d3-array/dist/d3-array.mjs","internmap":"/nm/internmap/src/index.js",
  "topojson-client":"/nm/topojson-client/src/index.js"}}</script></head><body>
<script type="module">
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { geoEquirectangular, geoPath } from 'd3-geo';
import { feature } from 'topojson-client';

let R, S, C, update;
const col = h => new THREE.Color(h);

function base(job) {
  R = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
  R.setPixelRatio(1); R.setSize(job.w, job.h); R.setClearColor(0x000000, 0);
  R.outputColorSpace = THREE.SRGBColorSpace; R.toneMapping = THREE.ACESFilmicToneMapping; R.toneMappingExposure = job.exposure ?? 1.0;
  document.body.innerHTML = ''; document.body.appendChild(R.domElement);
  S = new THREE.Scene();
  const pm = new THREE.PMREMGenerator(R); S.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
  C = new THREE.PerspectiveCamera(job.fov ?? 28, job.w / job.h, 0.1, 100);
  const key = new THREE.DirectionalLight(0xffffff, 2.2); key.position.set(-3, 4, 5); S.add(key);
  const rim = new THREE.DirectionalLight(col(job.accent), 3.5); rim.position.set(4, 1.5, -4); S.add(rim);
  const fill = new THREE.DirectionalLight(0xbfd0ff, 0.35); fill.position.set(3, -2, 3); S.add(fill);
}

function canvasTex(w, h, draw) {
  const c = document.createElement('canvas'); c.width = w; c.height = h; draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}

// ---------------------------------------------------------------- globe (dot-matrix land from Natural Earth)
async function globe(job) {
  const land = await (await fetch('/nm/world-atlas/land-110m.json')).json();
  const W = 2048, H = 1024, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
  const g = cv.getContext('2d'); g.fillStyle = '#fff';
  const proj = geoEquirectangular().fitSize([W, H], { type: 'Sphere' });
  g.beginPath(); geoPath(proj, g)(feature(land, land.objects.land)); g.fill();
  const px = g.getImageData(0, 0, W, H).data;
  const grp = new THREE.Group(); S.add(grp);
  const ocean = new THREE.Mesh(new THREE.SphereGeometry(1, 128, 96),
    new THREE.MeshPhysicalMaterial({ color: 0x08090b, roughness: 0.75, metalness: 0.0, clearcoat: 0.35, clearcoatRoughness: 0.4, envMapIntensity: 0.25 }));
  grp.add(ocean);
  const N = job.dots ?? 16000, pts = [];
  for (let i = 0; i < N; i++) {
    const y = 1 - (i + 0.5) / N * 2, r = Math.sqrt(1 - y * y), th = i * Math.PI * (3 - Math.sqrt(5));
    const x = Math.cos(th) * r, z = Math.sin(th) * r;
    const lat = Math.asin(y) * 180 / Math.PI, lon = Math.atan2(x, z) * 180 / Math.PI;
    const [u, v] = proj([lon, lat]); const k = (Math.min(H - 1, v | 0) * W + Math.min(W - 1, u | 0)) * 4;
    if (px[k] > 128) pts.push(new THREE.Vector3(x, y, z));
  }
  const dot = new THREE.InstancedMesh(new THREE.CircleGeometry(0.0068, 8),
    new THREE.MeshStandardMaterial({ color: 0xf2f2ee, emissive: 0x2a2a2a, roughness: 0.6, side: THREE.DoubleSide }), pts.length);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 0, 1), s = new THREE.Vector3(1, 1, 1);
  pts.forEach((p, i) => { q.setFromUnitVectors(up, p.clone().normalize()); m.compose(p.clone().multiplyScalar(1.003), q, s); dot.setMatrixAt(i, m); });
  grp.add(dot);
  // fresnel atmosphere in the category accent
  const atm = new THREE.Mesh(new THREE.SphereGeometry(1.14, 96, 64), new THREE.ShaderMaterial({
    uniforms: { c: { value: col(job.accent) } }, transparent: true, depthWrite: false, side: THREE.BackSide, blending: THREE.AdditiveBlending,
    vertexShader: 'varying vec3 n; varying vec3 v; void main(){ n=normalize(normalMatrix*normal); vec4 mv=modelViewMatrix*vec4(position,1.); v=normalize(-mv.xyz); gl_Position=projectionMatrix*mv; }',
    fragmentShader: 'uniform vec3 c; varying vec3 n; varying vec3 v; void main(){ float f=pow(clamp(0.82-abs(dot(n,v)),0.0,1.0),3.0)*1.6; gl_FragColor=vec4(c*f, f); }' }));
  S.add(atm);
  // orbital shells: thin rings + satellites (MEO planes inclined ~55°)
  const orb = new THREE.Group(); S.add(orb);
  const planes = job.planes ?? 6, nsat = job.sats ?? 0, rad = job.orbit ?? 1.62, sats = [];
  for (let k = 0; k < planes; k++) {
    const pl = new THREE.Group(); pl.rotation.y = k * Math.PI / planes * 2; pl.rotation.x = 55 * Math.PI / 180; orb.add(pl);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(rad, 0.0025, 6, 256), new THREE.MeshBasicMaterial({ color: 0x8a8a86, transparent: true, opacity: 0.35 }));
    ring.rotation.x = Math.PI / 2; pl.add(ring);
    for (let j = k; j < nsat; j += planes) {
      const sat = new THREE.Mesh(new THREE.SphereGeometry(0.024, 16, 12), new THREE.MeshBasicMaterial({ color: col(job.accent) }));
      const halo = new THREE.Mesh(new THREE.SphereGeometry(0.05, 16, 12), new THREE.MeshBasicMaterial({ color: col(job.accent), transparent: true, opacity: 0.18, depthWrite: false }));
      sat.add(halo); pl.add(sat); sats.push({ sat, j, ph: j / nsat * Math.PI * 2 * 3.7 });
    }
  }
  // markers (lat/lon) and cable arcs (great circles that draw themselves in)
  const ll = (lat, lon, r = 1) => { const a = lat * Math.PI / 180, b = lon * Math.PI / 180; return new THREE.Vector3(Math.cos(a) * Math.sin(b), Math.sin(a), Math.cos(a) * Math.cos(b)).multiplyScalar(r); };
  const marks = [];
  for (const m of job.markers || []) {
    const p = ll(m.lat, m.lon, 1.012);
    const dot = new THREE.Mesh(new THREE.SphereGeometry(0.03, 20, 14), new THREE.MeshBasicMaterial({ color: col(job.accent) }));
    const halo = new THREE.Mesh(new THREE.SphereGeometry(0.075, 20, 14), new THREE.MeshBasicMaterial({ color: col(job.accent), transparent: true, opacity: 0.25, depthWrite: false }));
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.06, 0.07, 48), new THREE.MeshBasicMaterial({ color: col(job.accent), transparent: true, opacity: 0.8, side: THREE.DoubleSide, depthWrite: false }));
    ring.position.copy(p); ring.lookAt(p.clone().multiplyScalar(2));
    dot.position.copy(p); halo.position.copy(p); grp.add(dot, halo, ring); marks.push(ring);
  }
  const arcs = [];
  for (const [la1, lo1, la2, lo2] of job.arcs || []) {
    const A = ll(la1, lo1), B = ll(la2, lo2), pts = [];
    for (let i = 0; i <= 96; i++) { const u = i / 96; const v = new THREE.Vector3().copy(A).lerp(B, u).normalize(); pts.push(v.multiplyScalar(1.006 + 0.05 * Math.sin(Math.PI * u))); }
    const geo = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 160, 0.0065, 6, false);
    const tube = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: col(job.accent) })); grp.add(tube); arcs.push(tube);
  }
  if (job.face_lon !== undefined) job.rot0 = -job.face_lon * Math.PI / 180 - (job.T0 + (job.frames / job.fps) / 2) * (job.speed ?? 0.12);
  C.position.set(0, 0.35, job.dist ?? 5.6); C.lookAt(0, 0, 0);
  grp.rotation.x = 0.38; atm.rotation.copy(grp.rotation);
  update = T => {
    grp.rotation.y = (job.rot0 ?? 0) + T * (job.speed ?? 0.12);
    orb.rotation.y = T * 0.03;
    const t = T - job.T0;
    marks.forEach((r, i) => { const k = ((t * 0.8 + i * 0.3) % 1); r.scale.setScalar(1 + k * 2.2); r.material.opacity = 0.8 * (1 - k); });
    arcs.forEach((a, i) => { const ta = (job.arc_at ?? 0) + i * (job.arc_stagger ?? 0.12); const k = Math.min(1, Math.max(0, (t - ta) / (job.arc_dur ?? 1.2)));
      const n = a.geometry.index.count; a.geometry.setDrawRange(0, Math.floor(n * (1 - Math.pow(1 - k, 3)) / 36) * 36); a.visible = k > 0; });
    for (const s of sats) {
      const a = s.ph + T * 0.35; s.sat.position.set(Math.cos(a) * rad, 0, Math.sin(a) * rad);
      const ti = (job.reveal_at ?? -99) + s.j / Math.max(1, nsat) * (job.reveal_dur ?? 0);
      const k = Math.min(1, Math.max(0, (t - ti) / 0.35)); s.sat.scale.setScalar(Math.max(0.001, k)); s.sat.visible = k > 0;
    }
  };
}

// ---------------------------------------------------------------- satellite
function satellite(job) {
  const g = new THREE.Group(); S.add(g);
  const gold = new THREE.MeshPhysicalMaterial({ color: 0xc8a24a, metalness: 1, roughness: 0.32, clearcoat: 0.3 });
  const silver = new THREE.MeshStandardMaterial({ color: 0xd8d8d4, metalness: 1, roughness: 0.25 });
  const white = new THREE.MeshStandardMaterial({ color: 0x9a9a96, metalness: 0.7, roughness: 0.35 });
  const cells = canvasTex(512, 256, (x, w, h) => {
    x.fillStyle = '#0b0f17'; x.fillRect(0, 0, w, h); x.strokeStyle = 'rgba(150,170,210,0.35)'; x.lineWidth = 2;
    for (let i = 0; i <= 16; i++) { x.beginPath(); x.moveTo(i * w / 16, 0); x.lineTo(i * w / 16, h); x.stroke(); }
    for (let j = 0; j <= 6; j++) { x.beginPath(); x.moveTo(0, j * h / 6); x.lineTo(w, j * h / 6); x.stroke(); }
  });
  const panel = new THREE.MeshPhysicalMaterial({ map: cells, metalness: 0.5, roughness: 0.22, clearcoat: 1, clearcoatRoughness: 0.08 });
  const body = new THREE.Mesh(new RoundedBoxGeometry(0.62, 0.78, 0.62, 4, 0.04), gold); g.add(body);
  for (const sx of [-1, 1]) {
    const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.018, 0.42, 12), silver); arm.rotation.z = Math.PI / 2; arm.position.x = sx * 0.5; g.add(arm);
    const p = new THREE.Mesh(new THREE.BoxGeometry(1.25, 0.56, 0.025), panel); p.position.x = sx * 1.32; g.add(p);
  }
  const dish = new THREE.Mesh(new THREE.LatheGeometry(Array.from({ length: 12 }, (_, i) => new THREE.Vector2(i / 11 * 0.26, (i / 11) ** 2 * 0.1)), 48), white);
  dish.rotation.x = Math.PI; dish.position.y = -0.5; g.add(dish);
  const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.014, 0.014, 0.16, 8), silver); stem.position.y = -0.45; g.add(stem);
  for (const [x, z] of [[0.18, 0.18], [-0.2, -0.15]]) {
    const ant = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.36, 8), silver); ant.position.set(x, 0.56, z); g.add(ant);
  }
  C.position.set(0, 0.6, job.dist ?? 7.2); C.lookAt(0, 0, 0);
  update = T => { g.rotation.y = (job.rot0 ?? 0.6) + T * (job.speed ?? 0.25); g.rotation.z = 0.12 * Math.sin(T * 0.4); g.rotation.x = 0.25; };
}

// ---------------------------------------------------------------- phone
function phone(job) {
  const g = new THREE.Group(); S.add(g);
  const frame = new THREE.MeshPhysicalMaterial({ color: 0x3a3a3c, metalness: 1, roughness: 0.28, clearcoat: 0.4 });
  const glass = new THREE.MeshPhysicalMaterial({ color: 0x050506, metalness: 0.2, roughness: 0.04, clearcoat: 1, clearcoatRoughness: 0.02 });
  g.add(new THREE.Mesh(new RoundedBoxGeometry(0.76, 1.56, 0.085, 8, 0.1), frame));
  const scr = canvasTex(512, 1040, (x, w, h) => {
    const gr = x.createRadialGradient(w / 2, h * 0.42, 10, w / 2, h * 0.42, h * 0.6);
    x.fillStyle = '#060607'; x.fillRect(0, 0, w, h); gr.addColorStop(0, job.accent + '30'); gr.addColorStop(1, job.accent + '00'); x.fillStyle = gr; x.fillRect(0, 0, w, h);
    if (job.screen === 'lock') {          // padlock
      const cx = w / 2, cy = h * 0.44; x.strokeStyle = job.accent; x.lineWidth = 9; x.lineJoin = 'round'; x.lineCap = 'round';
      x.beginPath(); x.roundRect(cx - 80, cy - 20, 160, 130, 22); x.stroke();
      x.beginPath(); x.arc(cx, cy - 20, 52, Math.PI, 0); x.stroke();
      x.beginPath(); x.arc(cx, cy + 40, 10, 0, Math.PI * 2); x.fillStyle = job.accent; x.fill();
    }
    if (job.screen === 'scan') {          // face-scan brackets + simple face
      const cx = w / 2, cy = h * 0.43, s2 = 120, c = 34; x.strokeStyle = job.accent; x.lineWidth = 8; x.lineCap = 'round';
      for (const [sx, sy] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) { x.beginPath(); x.moveTo(cx + sx * s2, cy + sy * (s2 - c)); x.lineTo(cx + sx * s2, cy + sy * s2); x.lineTo(cx + sx * (s2 - c), cy + sy * s2); x.stroke(); }
      x.beginPath(); x.moveTo(cx - 34, cy - 30); x.lineTo(cx - 34, cy - 10); x.moveTo(cx + 34, cy - 30); x.lineTo(cx + 34, cy - 10); x.stroke();
      x.beginPath(); x.arc(cx, cy + 22, 36, 0.15 * Math.PI, 0.85 * Math.PI); x.stroke();
    }
    if (job.screen === 'pin') {           // a lost map pin
      x.strokeStyle = job.accent; x.lineWidth = 6; x.globalAlpha = 0.85; x.lineJoin = 'round'; const cx = w / 2, cy = h * 0.42;
      x.beginPath(); x.arc(cx, cy - 30, 70, Math.PI * 0.85, Math.PI * 0.15, false); x.lineTo(cx, cy + 110); x.closePath(); x.stroke();
      x.font = '500 84px sans-serif'; x.fillStyle = job.accent; x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillText('?', cx, cy - 26);
    }
    x.fillStyle = '#000'; x.beginPath(); x.roundRect(w / 2 - 70, 26, 140, 40, 20); x.fill();   // dynamic island
  });
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(0.69, 1.49), new THREE.MeshBasicMaterial({ map: scr, toneMapped: false }));
  screen.position.z = 0.0435; g.add(screen);
  const back = new THREE.Mesh(new RoundedBoxGeometry(0.3, 0.3, 0.03, 4, 0.06), glass); back.position.set(-0.17, 0.53, -0.055); g.add(back);
  for (const [x, y] of [[-0.23, 0.6], [-0.11, 0.6], [-0.17, 0.47]]) {
    const l = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 0.03, 32), glass); l.rotation.x = Math.PI / 2; l.position.set(x, y, -0.075); g.add(l);
  }
  C.position.set(0, 0, job.dist ?? 5.0); C.lookAt(0, 0, 0);
  update = T => { g.rotation.y = (job.rot0 ?? -0.35) + (job.swing ?? 0.32) * Math.sin(T * (job.speed ?? 0.35)); g.rotation.x = -0.08; g.rotation.z = 0.04; g.position.y = 0.03 * Math.sin(T * 0.8); };
}

// ---------------------------------------------------------------- chip
function chip(job) {
  const g = new THREE.Group(); S.add(g);
  const pkg = new THREE.MeshStandardMaterial({ color: 0x141416, roughness: 0.55, metalness: 0.2 });
  const ihs = new THREE.MeshPhysicalMaterial({ color: 0x8e8e8a, metalness: 1, roughness: 0.38, clearcoat: 0.2 });
  const gold = new THREE.MeshStandardMaterial({ color: 0xd4a94a, metalness: 1, roughness: 0.3 });
  g.add(new THREE.Mesh(new RoundedBoxGeometry(1.7, 0.1, 1.7, 3, 0.03), pkg));
  const top = new THREE.Mesh(new RoundedBoxGeometry(1.15, 0.07, 1.15, 3, 0.04), ihs); top.position.y = 0.08; g.add(top);
  const pin = new THREE.BoxGeometry(0.035, 0.02, 0.12);
  for (let i = 0; i < 18; i++) for (const s of [-1, 1]) {
    const o = -0.76 + i * 0.09;
    const a = new THREE.Mesh(pin, gold); a.position.set(o, -0.02, s * 0.9); g.add(a);
    const b = new THREE.Mesh(pin, gold); b.rotation.y = Math.PI / 2; b.position.set(s * 0.9, -0.02, o); g.add(b);
  }
  C.position.set(0, 3.2, job.dist ?? 4.4); C.lookAt(0, 0, 0);
  update = T => { g.rotation.y = (job.rot0 ?? 0.4) + T * (job.speed ?? 0.2); };
}

// ---------------------------------------------------------------- battery (phone pouch cell)
function battery(job) {
  const g = new THREE.Group(); S.add(g);
  const foil = new THREE.MeshPhysicalMaterial({ color: 0xb8b8b4, metalness: 1, roughness: 0.32, clearcoat: 0.5, clearcoatRoughness: 0.3 });
  const tab = new THREE.MeshStandardMaterial({ color: 0xd9d9d5, metalness: 1, roughness: 0.22 });
  const label = canvasTex(512, 768, (x, w, h) => {
    x.fillStyle = '#121214'; x.fillRect(0, 0, w, h);
    x.fillStyle = job.accent; x.fillRect(0, h * 0.06, w, 6);
    x.fillStyle = '#8a8a86'; x.font = '500 34px sans-serif'; x.textAlign = 'center';
    x.fillText('Li-ion', w / 2, h * 0.52); x.font = '400 24px sans-serif'; x.fillText('3.85 V', w / 2, h * 0.6);
  });
  const body = new THREE.Mesh(new RoundedBoxGeometry(1.0, 1.5, 0.12, 6, 0.06), foil); g.add(body);
  const lab = new THREE.Mesh(new THREE.PlaneGeometry(0.84, 1.26), new THREE.MeshPhysicalMaterial({ map: label, roughness: 0.45, clearcoat: 0.3 }));
  lab.position.z = 0.0615; lab.position.y = -0.04; g.add(lab);
  const seal = new THREE.Mesh(new RoundedBoxGeometry(1.0, 0.12, 0.05, 3, 0.02), foil); seal.position.y = 0.8; g.add(seal);
  for (const sx of [-0.22, 0.22]) {
    const t = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.2, 0.012), tab); t.position.set(sx, 0.92, 0); g.add(t);
  }
  C.position.set(0, 0.1, job.dist ?? 4.6); C.lookAt(0, 0, 0);
  update = T => { g.rotation.y = (job.rot0 ?? -0.45) + (job.swing ?? 0.4) * Math.sin(T * (job.speed ?? 0.35)); g.rotation.x = -0.12; g.rotation.z = 0.05; g.position.y = 0.025 * Math.sin(T * 0.8); };
}

// ---------------------------------------------------------------- router (mesh-Wi-Fi dome with a light ring)
function router(job) {
  const g = new THREE.Group(); S.add(g);
  const shell = new THREE.MeshPhysicalMaterial({ color: 0xecece8, metalness: 0, roughness: 0.62, clearcoat: 0.15, clearcoatRoughness: 0.6, sheen: 0.3 });
  const base = new THREE.MeshStandardMaterial({ color: 0x1b1b1d, metalness: 0.2, roughness: 0.5 });
  const prof = [new THREE.Vector2(0, 0)], R = 0.62, Hh = 0.78;
  for (let i = 0; i <= 40; i++) {                      // softly tapered wall rolling into a dome
    const u = i / 40, y = u * Hh, r = R - 0.06 * u * u;
    prof.push(new THREE.Vector2(r, y));
  }
  for (let i = 1; i <= 40; i++) { const a = i / 40 * Math.PI / 2; prof.push(new THREE.Vector2((R - 0.06) * Math.cos(a), Hh + 0.32 * Math.sin(a))); }
  const body = new THREE.Mesh(new THREE.LatheGeometry(prof, 128), shell); body.position.y = -0.5; g.add(body);
  const foot = new THREE.Mesh(new THREE.CylinderGeometry(0.58, 0.58, 0.05, 96), base); foot.position.y = -0.52; g.add(foot);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.6, 0.012, 12, 160), new THREE.MeshBasicMaterial({ color: col(job.accent) }));
  ring.rotation.x = Math.PI / 2; ring.position.y = -0.465; g.add(ring);
  const glowR = new THREE.Mesh(new THREE.TorusGeometry(0.6, 0.05, 12, 160), new THREE.MeshBasicMaterial({ color: col(job.accent), transparent: true, opacity: 0.18, depthWrite: false }));
  glowR.rotation.x = Math.PI / 2; glowR.position.y = -0.465; g.add(glowR);
  C.position.set(0, 0.55, job.dist ?? 4.6); C.lookAt(0, -0.05, 0);
  update = T => { g.rotation.y = (job.rot0 ?? 0) + T * (job.speed ?? 0.15); glowR.material.opacity = 0.12 + 0.1 * (0.5 + 0.5 * Math.sin(T * 2.2)); };
}

const BUILD = { globe, satellite, phone, chip, battery, router };
window.setupJob = async job => { base(job); await BUILD[job.type](job); return true; };
window.renderAt = T => { update(T); R.render(S, C); return R.domElement.toDataURL('image/png'); };
window.rasterIcon = async (svg, size) => {
  const img = new Image(); img.src = 'data:image/svg+xml;base64,' + btoa(svg); await img.decode();
  const c = document.createElement('canvas'); c.width = c.height = size; c.getContext('2d').drawImage(img, 0, 0, size, size);
  return c.toDataURL('image/png');
};
window.ready = true;
</script></body></html>`;

function savePng(dataUrl, out) {
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, Buffer.from(dataUrl.split(',')[1], 'base64'));
}

async function newPage(browser) {
  const page = await browser.newPage();
  await page.route('http://studio.local/**', route => {
    const u = new URL(route.request().url());
    if (u.pathname === '/') return route.fulfill({ contentType: 'text/html', body: HTML });
    if (u.pathname.startsWith('/nm/')) {
      const f = path.join(NM, decodeURIComponent(u.pathname.slice(4)));
      if (!f.startsWith(NM) || !fs.existsSync(f)) return route.fulfill({ status: 404, body: '' });
      const type = f.endsWith('.json') ? 'application/json' : 'text/javascript';
      return route.fulfill({ contentType: type, body: fs.readFileSync(f) });
    }
    return route.fulfill({ status: 404, body: '' });
  });
  page.on('pageerror', e => console.error('page error:', e.message));
  await page.goto('http://studio.local/');
  await page.waitForFunction(() => window.ready === true);
  return page;
}

(async () => {
  const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  if (jobs.icons && jobs.icons.length) {
    const page = await newPage(browser);
    for (const ic of jobs.icons) {
      let svg = fs.readFileSync(path.join(NM, 'lucide-static/icons', ic.name + '.svg'), 'utf8').replace(/<!--.*?-->/s, '');
      const sw = (ic.stroke ?? 3) * 24 / ic.size;            // absolute stroke width in output pixels
      svg = svg.replace(/stroke-width="[^"]*"/, `stroke-width="${sw.toFixed(3)}"`).replace(/stroke="currentColor"/, 'stroke="#ffffff"')
               .replace(/width="24"/, `width="${ic.size}"`).replace(/height="24"/, `height="${ic.size}"`);
      savePng(await page.evaluate(([s, n]) => window.rasterIcon(s, n), [svg, ic.size]), ic.out);
    }
    await page.close();
  }
  // objects: render several jobs in parallel pages
  const objs = jobs.objects || [], par = Math.max(1, Math.min(objs.length, jobs.parallel || 3));
  let next = 0;
  async function worker() {
    while (next < objs.length) {
      const job = objs[next++]; const t0 = Date.now();
      const page = await newPage(browser);
      await page.evaluate(j => window.setupJob(j), job);
      for (let f = 0; f < job.frames; f++) {
        const T = job.T0 + f / job.fps;
        savePng(await page.evaluate(T => window.renderAt(T), T), path.join(job.out, String(f).padStart(5, '0') + '.png'));
      }
      fs.writeFileSync(path.join(job.out, 'done'), String(job.frames));
      console.log(`3d ${job.type} ${job.frames}f ${job.w}x${job.h} in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
      await page.close();
    }
  }
  await Promise.all(Array.from({ length: par }, worker));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
