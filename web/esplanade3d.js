// MARÉE — l'esplanade en 3D (Three.js), miroir de godot/project/scripts/esplanade.gd.
// Consommateur pur : la géométrie vient du plan reçu dans `hello`, l'état de
// l'instantané affiché. Repère : x monde -> X, y monde -> -Z, le nord s'éloigne
// de la caméra. Les hauteurs sont un choix d'affichage : le moteur reste en 2D,
// aucun chiffre n'en dépend, et les murs du sud restent bas pour ne cacher personne.

import * as THREE from "./vendor/three/three.module.js";

const OBSTACLE_HEIGHTS = { tour: 6, scene: 1.1, stand: 2.3, fontaine: 0.75 };
const SIDE_COLORS = { tour: 0x5b5c66, scene: 0x3a2f28, stand: 0x45464f, fontaine: 0x7c7e88 };
const EXIT_COLORS = { A: 0x56b4e9, B: 0xe69f00, C: 0xcc79a7 };
const NONE_COLOR = 0xa1a1aa;
const CLOSED_COLOR = 0xef4444;
const SMOKE_PUFFS = 130;

function hash2(i, j) {
  const s = Math.sin(i * 127.1 + j * 311.7) * 43758.5453;
  return s - Math.floor(s);
}

function softDisc() {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
}

export function createEsplanade(canvas, assetsBase = "./assets") {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x10131c);
  scene.fog = new THREE.FogExp2(0x141826, 0.0035);
  scene.add(new THREE.AmbientLight(0xaab2cc, 2.3));

  const moon = new THREE.DirectionalLight(0xdfe4ff, 2.6);
  moon.castShadow = true;
  moon.shadow.mapSize.set(2048, 2048);
  moon.shadow.bias = -0.0006;
  moon.shadow.normalBias = 0.03;
  scene.add(moon, moon.target);

  const camera = new THREE.PerspectiveCamera(30, 1, 1, 400);
  const loader = new THREE.TextureLoader();
  const disc = softDisc();
  const textures = {};
  const onTexture = [];
  for (const name of ["paving", "tour", "scene", "stand", "fontaine"]) {
    textures[name] = loader.load(`${assetsBase}/${name}.png`, () => onTexture.forEach((fn) => fn()));
    textures[name].colorSpace = THREE.SRGBColorSpace;
    textures[name].anisotropy = renderer.capabilities.getMaxAnisotropy();
  }

  let root = null;
  let planH = 40;
  let center = new THREE.Vector3();
  let extent = { x: 50, y: 30 };
  let size = { w: 1, h: 1 };
  const orbitState = { yaw: 0, pitch: 54, zoom: 1 };
  let bodies = new Map();
  let gates = new Map();
  let smoke = null;
  let ring = null;
  let density = null;

  const p3 = (x, y, h = 0) => new THREE.Vector3(x, h, planH - y);
  const matte = (color, roughness = 0.9) => new THREE.MeshStandardMaterial({ color, roughness, metalness: 0 });
  const glowing = (color, energy = 0.55) => new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: energy, roughness: 0.6 });

  function box(w, h, d, position, material, shadow = true) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
    mesh.position.copy(position);
    mesh.castShadow = shadow;
    mesh.receiveShadow = true;
    root.add(mesh);
    return mesh;
  }

  function buildGround(b) {
    const far = new THREE.Mesh(new THREE.PlaneGeometry(320, 320), matte(0x14161e));
    far.rotation.x = -Math.PI / 2;
    far.position.copy(center).setY(-0.06);
    root.add(far);

    const paving = textures.paving;
    paving.wrapS = paving.wrapT = THREE.RepeatWrapping;
    paving.repeat.set(b.w / 12.5, b.h / 12.5);
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(b.w, b.h),
      new THREE.MeshStandardMaterial({ map: paving, color: 0xffffff, roughness: 0.82 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.copy(center);
    floor.receiveShadow = true;
    root.add(floor);
  }

  // Quatre murs percés aux sorties, de plus en plus bas vers la caméra.
  function buildWalls(b, exits) {
    const stone = matte(0x5d5f6c);
    const sides = [
      [[b.minX, b.maxY], [b.maxX, b.maxY], 3],
      [[b.minX, b.minY], [b.maxX, b.minY], 0.45],
      [[b.minX, b.minY], [b.minX, b.maxY], 1.6],
      [[b.maxX, b.minY], [b.maxX, b.maxY], 1.6],
    ];
    for (const [a, c, height] of sides) {
      const length = Math.hypot(c[0] - a[0], c[1] - a[1]);
      const dir = [(c[0] - a[0]) / length, (c[1] - a[1]) / length];
      const along = (p) => (p[0] - a[0]) * dir[0] + (p[1] - a[1]) * dir[1];
      const off = (p) => Math.abs((p[0] - a[0]) * dir[1] - (p[1] - a[1]) * dir[0]);
      const cuts = exits
        .filter((ex) => off(ex.a) < 0.05 && off(ex.b) < 0.05)
        .map((ex) => [Math.min(along(ex.a), along(ex.b)), Math.max(along(ex.a), along(ex.b))])
        .sort((p, q) => p[0] - q[0]);
      cuts.push([length, length]);
      let from = 0;
      for (const [to, next] of cuts) {
        if (to - from > 0.01) {
          const mid = (from + to) / 2;
          const at = p3(a[0] + dir[0] * mid, a[1] + dir[1] * mid, height / 2);
          const horizontal = Math.abs(dir[0]) > 0.5;
          box(horizontal ? to - from : 0.5, height, horizontal ? 0.5 : to - from, at, stone);
        }
        from = next;
      }
    }
  }

  function buildObstacle(ob) {
    const poly = ob.polygon || [];
    if (poly.length < 3) return;
    const kind = ob.kind;
    const height = OBSTACLE_HEIGHTS[kind] ?? 1.5;
    const xs = poly.map((p) => p[0]);
    const ys = poly.map((p) => p[1]);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);

    const shape = new THREE.Shape(poly.map((p) => new THREE.Vector2(p[0], p[1])));
    const geometry = new THREE.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false });
    geometry.rotateX(-Math.PI / 2); // (x, y, z) -> (x, z, -y)
    geometry.translate(0, 0, planH);

    // UV du dessus : l'asset couvre l'emprise de l'obstacle.
    const position = geometry.attributes.position;
    const uv = geometry.attributes.uv;
    for (let i = 0; i < position.count; i += 1) {
      uv.setXY(i, (position.getX(i) - minX) / (maxX - minX), (planH - position.getZ(i) - minY) / (maxY - minY));
    }
    const mesh = new THREE.Mesh(geometry, [
      new THREE.MeshStandardMaterial({ map: textures[kind] ?? null, color: 0xffffff, roughness: 0.75 }),
      matte(SIDE_COLORS[kind] ?? 0x45464f),
    ]);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    root.add(mesh);

    // Lumière chaude de la fête, sur les stands et la scène : du décor, pas un signal.
    if (kind === "stand" || kind === "scene") {
      const lamp = new THREE.PointLight(0xffdcb8, kind === "stand" ? 34 : 70, kind === "stand" ? 10 : 14);
      lamp.position.copy(p3((minX + maxX) / 2, (minY + maxY) / 2, height + 1.6));
      root.add(lamp);
    }
  }

  function buildGate(ex, b) {
    const color = EXIT_COLORS[ex.id] ?? NONE_COLOR;
    const material = glowing(color);
    const south = Math.abs((ex.a[1] + ex.b[1]) / 2 - b.minY) < 0.5;
    const height = south ? 0.5 : 3.4;
    for (const p of [ex.a, ex.b]) box(0.45, height, 0.45, p3(p[0], p[1], height / 2), material);
    const horizontal = Math.abs(ex.a[0] - ex.b[0]) > Math.abs(ex.a[1] - ex.b[1]);
    const length = Math.hypot(ex.a[0] - ex.b[0], ex.a[1] - ex.b[1]);
    const mx = (ex.a[0] + ex.b[0]) / 2;
    const my = (ex.a[1] + ex.b[1]) / 2;
    box(horizontal ? length : 0.45, 0.28, horizontal ? 0.45 : length, p3(mx, my, height), material);
    const bar = box(horizontal ? length : 0.16, 1.1, horizontal ? 0.16 : length, p3(mx, my, 0.55), glowing(CLOSED_COLOR, 0.9));
    bar.visible = false;
    const lamp = new THREE.PointLight(color, 26, 9);
    lamp.position.copy(p3(mx, my, 2.2));
    root.add(lamp);
    gates.set(ex.id, { material, bar, lamp, color });
  }

  function buildSmoke() {
    smoke = new THREE.Group();
    for (let i = 0; i < SMOKE_PUFFS; i += 1) {
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: disc, color: 0xbcbec8, transparent: true, opacity: 0, depthWrite: false }));
      sprite.userData = {
        u: hash2(i, 1) * 2 - 1,
        v: hash2(i, 2) * 2 - 1,
        size: 5 + hash2(i, 3) * 5,
        phase: hash2(i, 4),
        life: 7 + hash2(i, 5) * 3,
      };
      smoke.add(sprite);
    }
    smoke.visible = false;
    root.add(smoke);

    ring = new THREE.Mesh(
      new THREE.RingGeometry(0.988, 1, 128),
      new THREE.MeshBasicMaterial({ color: 0xe6e6ea, transparent: true, opacity: 0.4, side: THREE.DoubleSide, depthWrite: false }),
    );
    ring.rotation.x = -Math.PI / 2;
    ring.visible = false;
    root.add(ring);
  }

  function buildDensity() {
    const geometry = new THREE.PlaneGeometry(3.8, 3.8);
    geometry.rotateX(-Math.PI / 2);
    const material = new THREE.MeshBasicMaterial({ map: disc, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
    density = new THREE.InstancedMesh(geometry, material, 400);
    density.count = 0;
    density.frustumCulled = false;
    root.add(density);
  }

  const bodyGeometry = new THREE.CapsuleGeometry(0.3, 0.75, 6, 14);
  const headGeometry = new THREE.SphereGeometry(0.17, 14, 12);
  const headMaterial = matte(0xd9c7b4, 0.6);

  function bodyFor(id) {
    let body = bodies.get(id);
    if (body) return body;
    const group = new THREE.Group();
    const material = new THREE.MeshStandardMaterial({ color: NONE_COLOR, roughness: 0.55 });
    const torso = new THREE.Mesh(bodyGeometry, material);
    torso.position.y = 0.72;
    torso.castShadow = true;
    const head = new THREE.Mesh(headGeometry, headMaterial);
    head.position.y = 1.56;
    head.castShadow = true;
    group.add(torso, head);
    root.add(group);
    body = { group, material, last: null, seed: hash2(id.length, Number(id.replace(/\D/g, "")) || 0) * 7 };
    bodies.set(id, body);
    return body;
  }

  function frame() {
    const aspect = size.w / Math.max(size.h, 1);
    camera.aspect = aspect;
    const vfov = THREE.MathUtils.degToRad(camera.fov);
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * aspect);
    const pitch = THREE.MathUtils.degToRad(orbitState.pitch);
    const yaw = THREE.MathUtils.degToRad(orbitState.yaw);
    const fitW = (extent.x * 1.2) / (2 * Math.tan(hfov / 2));
    const fitH = (extent.y * Math.sin(pitch) * 1.42) / (2 * Math.tan(vfov / 2));
    const distance = Math.max(fitW, fitH) * orbitState.zoom;
    camera.position.set(
      center.x + Math.sin(yaw) * Math.cos(pitch) * distance,
      Math.sin(pitch) * distance,
      center.z + Math.cos(yaw) * Math.cos(pitch) * distance,
    );
    camera.lookAt(center);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
  }

  return {
    onTexture(fn) { onTexture.push(fn); },

    build(plan) {
      if (!plan?.walkable?.length) return;
      if (root) scene.remove(root);
      root = new THREE.Group();
      scene.add(root);
      bodies = new Map();
      gates = new Map();
      planH = plan.height ?? 40;
      const xs = plan.walkable.map((p) => p[0]);
      const ys = plan.walkable.map((p) => p[1]);
      const b = { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
      b.w = b.maxX - b.minX;
      b.h = b.maxY - b.minY;
      extent = { x: b.w, y: b.h };
      center = p3((b.minX + b.maxX) / 2, (b.minY + b.maxY) / 2);

      moon.position.copy(center).add(new THREE.Vector3(-34, 62, 30));
      moon.target.position.copy(center);
      const reach = Math.max(b.w, b.h) * 0.72;
      Object.assign(moon.shadow.camera, { left: -reach, right: reach, top: reach, bottom: -reach, near: 1, far: 180 });
      moon.shadow.camera.updateProjectionMatrix();

      buildGround(b);
      buildWalls(b, plan.exits || []);
      (plan.obstacles || []).forEach(buildObstacle);
      (plan.exits || []).forEach((ex) => buildGate(ex, b));
      buildSmoke();
      buildDensity();
      frame();
    },

    resize(width, height, dpr) {
      size = { w: width, h: height };
      renderer.setPixelRatio(Math.min(dpr, 1.75));
      renderer.setSize(width, height, false);
      frame();
    },

    orbit(deltaYaw, deltaPitch) {
      orbitState.yaw = THREE.MathUtils.clamp(orbitState.yaw + deltaYaw, -70, 70);
      orbitState.pitch = THREE.MathUtils.clamp(orbitState.pitch + deltaPitch, 30, 80);
      frame();
    },

    zoomBy(factor) {
      orbitState.zoom = THREE.MathUtils.clamp(orbitState.zoom * factor, 0.45, 1.2);
      frame();
    },

    resetView() {
      Object.assign(orbitState, { yaw: 0, pitch: 54, zoom: 1 });
      frame();
    },

    // `positions` : id -> [x, y] interpolés. `focus` : la personne mise en avant.
    syncAgents(agents, positions, focus, nowMs, still) {
      if (!root) return;
      const seen = new Set();
      for (const agent of agents) {
        const pos = positions.get(agent.id);
        if (agent.evacuated || !pos) continue;
        seen.add(agent.id);
        const body = bodyFor(agent.id);
        const moved = body.last ? Math.hypot(pos[0] - body.last[0], pos[1] - body.last[1]) : 0;
        let bob = 0;
        if (moved > 0.002) {
          body.group.rotation.y = Math.atan2(pos[0] - body.last[0], -(pos[1] - body.last[1]));
          if (!still) bob = Math.abs(Math.sin(nowMs * 0.009 + body.seed)) * 0.07;
        }
        body.last = pos;
        body.group.position.copy(p3(pos[0], pos[1], bob));
        body.group.visible = true;
        const color = new THREE.Color(EXIT_COLORS[agent.belief] ?? NONE_COLOR);
        const dim = focus && agent.id !== focus;
        body.material.color.copy(color);
        if (dim) body.material.color.multiplyScalar(0.3);
        body.material.emissive.copy(agent.id === focus ? color : new THREE.Color(0));
        body.material.emissiveIntensity = 0.6;
      }
      for (const [id, body] of bodies) if (!seen.has(id)) body.group.visible = false;
    },

    syncWorld(snap, smokeEvent, layers, nowMs, still) {
      if (!root) return;
      const open = snap.exits_open;
      for (const [id, gate] of gates) {
        const isOpen = !open || open.includes(id);
        const color = isOpen ? gate.color : CLOSED_COLOR;
        gate.material.color.set(color);
        gate.material.emissive.set(color);
        gate.lamp.color.set(color);
        gate.bar.visible = !isOpen;
      }

      const active = Boolean(smokeEvent) && layers.smoke;
      smoke.visible = active;
      ring.visible = active;
      if (active) {
        const [sx, sy] = smokeEvent.position;
        const radius = smokeEvent.radius || 12;
        ring.position.copy(p3(sx, sy, 0.04));
        ring.scale.set(radius, radius, 1);
        for (const sprite of smoke.children) {
          const d = sprite.userData;
          const t = still ? 0.45 : ((nowMs / 1000 / d.life) + d.phase) % 1;
          const fade = t < 0.2 ? t / 0.2 : (1 - t) / 0.8;
          sprite.position.copy(p3(sx + d.u * radius * 0.62, sy + d.v * radius * 0.62, 1 + t * 5));
          sprite.scale.setScalar(d.size * (0.6 + t * 0.7));
          sprite.material.opacity = 0.26 * fade;
        }
      }

      let n = 0;
      if (layers.density) {
        const matrix = new THREE.Matrix4();
        const color = new THREE.Color();
        for (const cell of snap.density_grid || []) {
          if ((cell.n ?? 0) < 2 || n >= 400) continue;
          matrix.setPosition(p3(cell.x + 0.5, cell.y + 0.5, 0.05));
          density.setMatrixAt(n, matrix);
          density.setColorAt(n, color.setRGB(0.98, 0.57, 0.23).multiplyScalar(Math.min(0.14 * cell.n, 0.46)));
          n += 1;
        }
        density.instanceMatrix.needsUpdate = true;
        if (density.instanceColor) density.instanceColor.needsUpdate = true;
      }
      density.count = n;
    },

    render() { renderer.render(scene, camera); },

    project(x, y, height = 0) {
      const v = p3(x, y, height).project(camera);
      return { x: (v.x + 1) / 2 * size.w, y: (1 - v.y) / 2 * size.h };
    },

    // Point du sol sous un pixel, en mètres dans le repère du moteur.
    groundAt(px, py) {
      const ndc = new THREE.Vector2((px / size.w) * 2 - 1, 1 - (py / size.h) * 2);
      const ray = new THREE.Raycaster();
      ray.setFromCamera(ndc, camera);
      const hit = ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), new THREE.Vector3());
      return hit ? [hit.x, planH - hit.z] : null;
    },
  };
}
