// === Procurement Pilot — SPECTACULAR Intro Animation ===
// 10 visual layers: floaters w/ trails, rotating geometry, data rain,
// energy waves, network pulses, constellations, vortex convergence,
// radiant core, circuit traces, grid overlay
// Total duration: ~9 seconds

function launchChatbot() {
    window.location.href = 'http://localhost:8501/';
}

// --- Canvas Setup ---
const canvas = document.getElementById('anim-canvas');
const ctx = canvas.getContext('2d');
let w, h;

function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
    initHexGrid();
    initDataRain();
}
window.addEventListener('resize', resize);
// resize() called at end of file after all const declarations

// --- Constants ---
const ACCENT = '#76b900';
const ACCENT_RGB = '118,185,0';
const ACCENT_DIM = 'rgba(118,185,0,0.15)';
const ACCENT_MID = 'rgba(118,185,0,0.4)';
const TAU = Math.PI * 2;

// ════════════════════════════════════════════════════════
// 0. 3D GLOBE — wireframe Earth with shipping routes
// ════════════════════════════════════════════════════════
const GLOBE_RADIUS_RATIO = 0.52; // dominant background element
const GLOBE_TILT = 0.35; // X-axis tilt in radians
const GLOBE_SPIN = 0.06; // Y-axis rotation speed (rad/s)
const LAT_LINES = 12;
const LON_LINES = 18;
const POINTS_PER_LINE = 80;

// Supplier node locations (lat, lon in radians)
// Approximate positions: US, Germany, Japan, China, Taiwan, S.Korea, India, UK, Singapore, Mexico, Brazil, Thailand, Vietnam, Malaysia, Indonesia
const SUPPLIER_NODES = [
    { lat: 0.65, lon: -1.3 },   // US East
    { lat: 0.60, lon: -2.0 },   // US West
    { lat: 0.85, lon: 0.17 },   // Germany
    { lat: 0.63, lon: 2.4 },    // Japan
    { lat: 0.55, lon: 1.9 },    // Shanghai
    { lat: 0.40, lon: 2.1 },    // Taiwan
    { lat: 0.60, lon: 2.2 },    // S. Korea
    { lat: 0.35, lon: 1.35 },   // India
    { lat: 0.90, lon: -0.02 },  // UK
    { lat: 0.02, lon: 1.75 },   // Singapore
    { lat: 0.37, lon: -1.7 },   // Mexico
    { lat: -0.25, lon: -0.76 }, // Brazil
    { lat: 0.25, lon: 1.78 },   // Thailand
    { lat: 0.18, lon: 1.85 },   // Vietnam
    { lat: 0.05, lon: 1.93 },   // Malaysia
];

// Shipping routes (pairs of indices into SUPPLIER_NODES)
const SHIPPING_ROUTES = [
    [0, 2], [0, 3], [1, 5], [1, 6], [2, 7], [2, 8],
    [3, 5], [3, 6], [4, 5], [4, 9], [5, 6], [5, 1],
    [7, 9], [9, 4], [10, 0], [11, 2], [12, 13], [13, 14],
    [14, 9], [6, 3], [8, 0], [1, 10],
];

// 3D projection helpers
function latLonToXYZ(lat, lon, r) {
    return {
        x: r * Math.cos(lat) * Math.sin(lon),
        y: r * Math.sin(lat),
        z: r * Math.cos(lat) * Math.cos(lon),
    };
}

function rotateY(p, angle) {
    const c = Math.cos(angle), s = Math.sin(angle);
    return { x: p.x * c + p.z * s, y: p.y, z: -p.x * s + p.z * c };
}

function rotateX(p, angle) {
    const c = Math.cos(angle), s = Math.sin(angle);
    return { x: p.x, y: p.y * c - p.z * s, z: p.y * s + p.z * c };
}

function project3D(p, cx, cy) {
    // Weak perspective
    const scale = 1.0;
    return { x: cx + p.x * scale, y: cy - p.y * scale, z: p.z };
}

function drawGlobe(sec) {
    const globeR = Math.min(w, h) * GLOBE_RADIUS_RATIO;
    const cx = w * 0.5;
    const cy = h * 0.45; // centered slightly above middle
    const yRot = sec * GLOBE_SPIN;

    // Fade in over 2 seconds, persistent — never fades out
    let alpha = Math.min(1, sec / 2);

    ctx.save();

    // ── Atmospheric glow ──
    const glowGrad = ctx.createRadialGradient(cx, cy, globeR * 0.85, cx, cy, globeR * 1.3);
    glowGrad.addColorStop(0, 'rgba(118,185,0,0)');
    glowGrad.addColorStop(0.5, 'rgba(118,185,0,0.03)');
    glowGrad.addColorStop(1, 'rgba(118,185,0,0)');
    ctx.fillStyle = glowGrad;
    ctx.globalAlpha = alpha;
    ctx.fillRect(cx - globeR * 1.4, cy - globeR * 1.4, globeR * 2.8, globeR * 2.8);

    // ── Latitude lines ──
    for (let i = 1; i < LAT_LINES; i++) {
        const lat = -Math.PI / 2 + (Math.PI / LAT_LINES) * i;
        const isEquator = Math.abs(lat) < 0.15;
        ctx.beginPath();
        let started = false;
        for (let j = 0; j <= POINTS_PER_LINE; j++) {
            const lon = (TAU / POINTS_PER_LINE) * j;
            let p = latLonToXYZ(lat, lon, globeR);
            p = rotateY(p, yRot);
            p = rotateX(p, GLOBE_TILT);
            if (p.z < 0) { started = false; continue; }
            const proj = project3D(p, cx, cy);
            if (!started) { ctx.moveTo(proj.x, proj.y); started = true; }
            else ctx.lineTo(proj.x, proj.y);
        }
        ctx.strokeStyle = isEquator ? 'rgba(118,185,0,0.08)' : 'rgba(255,255,255,0.035)';
        ctx.globalAlpha = alpha;
        ctx.lineWidth = isEquator ? 1 : 0.5;
        ctx.stroke();
    }

    // ── Longitude lines ──
    for (let i = 0; i < LON_LINES; i++) {
        const lon = (TAU / LON_LINES) * i;
        ctx.beginPath();
        let started = false;
        for (let j = 0; j <= POINTS_PER_LINE; j++) {
            const lat = -Math.PI / 2 + (Math.PI / POINTS_PER_LINE) * j;
            let p = latLonToXYZ(lat, lon, globeR);
            p = rotateY(p, yRot);
            p = rotateX(p, GLOBE_TILT);
            if (p.z < 0) { started = false; continue; }
            const proj = project3D(p, cx, cy);
            if (!started) { ctx.moveTo(proj.x, proj.y); started = true; }
            else ctx.lineTo(proj.x, proj.y);
        }
        ctx.strokeStyle = 'rgba(255,255,255,0.04)';
        ctx.globalAlpha = alpha;
        ctx.lineWidth = 0.5;
        ctx.stroke();
    }

    // ── Globe outline circle ──
    ctx.beginPath();
    ctx.arc(cx, cy, globeR, 0, TAU);
    ctx.strokeStyle = 'rgba(118,185,0,0.1)';
    ctx.globalAlpha = alpha;
    ctx.lineWidth = 1;
    ctx.stroke();
    // Second faint outer ring
    ctx.beginPath();
    ctx.arc(cx, cy, globeR + 3, 0, TAU);
    ctx.strokeStyle = 'rgba(118,185,0,0.04)';
    ctx.lineWidth = 0.5;
    ctx.stroke();

    // ── Supplier nodes ──
    const projectedNodes = SUPPLIER_NODES.map(n => {
        let p = latLonToXYZ(n.lat, n.lon, globeR);
        p = rotateY(p, yRot);
        p = rotateX(p, GLOBE_TILT);
        const proj = project3D(p, cx, cy);
        return { ...proj, visible: p.z > 0 };
    });

    projectedNodes.forEach((n, ni) => {
        if (!n.visible) return;
        // Pulse based on index
        const pulse = 0.7 + 0.3 * Math.sin(sec * 2 + ni * 0.9);
        // Outer glow
        ctx.beginPath();
        ctx.arc(n.x, n.y, 10, 0, TAU);
        ctx.fillStyle = '#76b900';
        ctx.globalAlpha = alpha * 0.06 * pulse;
        ctx.fill();
        // Inner glow
        ctx.beginPath();
        ctx.arc(n.x, n.y, 5, 0, TAU);
        ctx.fillStyle = '#76b900';
        ctx.globalAlpha = alpha * 0.15 * pulse;
        ctx.fill();
        // Core dot
        ctx.beginPath();
        ctx.arc(n.x, n.y, 2.5, 0, TAU);
        ctx.fillStyle = '#76b900';
        ctx.globalAlpha = alpha * 0.7;
        ctx.fill();
    });

    // ── Shipping route arcs ──
    SHIPPING_ROUTES.forEach((route, ri) => {
        const a = projectedNodes[route[0]];
        const b = projectedNodes[route[1]];
        if (!a || !b) return;
        if (!a.visible && !b.visible) return;

        // Draw arc (elevated bezier curve between the two points)
        const mx = (a.x + b.x) / 2;
        const my = (a.y + b.y) / 2;
        const dist = Math.hypot(b.x - a.x, b.y - a.y);
        const lift = dist * 0.25; // arc height

        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.quadraticCurveTo(mx, my - lift, b.x, b.y);
        ctx.strokeStyle = 'rgba(118,185,0,0.18)';
        ctx.globalAlpha = alpha * (a.visible && b.visible ? 1 : 0.3);
        ctx.lineWidth = 1;
        ctx.stroke();

        // Two flowing dots per route (staggered)
        for (let di = 0; di < 2; di++) {
            const speed = 0.12 + (ri % 5) * 0.04;
            const t = ((sec * speed + ri * 0.3 + di * 0.5) % 1);
            const u = 1 - t;
            const dx = u * u * a.x + 2 * u * t * mx + t * t * b.x;
            const dy = u * u * a.y + 2 * u * t * (my - lift) + t * t * b.y;

            if ((a.visible && t < 0.5) || (b.visible && t >= 0.5) || (a.visible && b.visible)) {
                // Glow
                ctx.beginPath();
                ctx.arc(dx, dy, 6, 0, TAU);
                ctx.fillStyle = '#76b900';
                ctx.globalAlpha = alpha * 0.12;
                ctx.fill();
                // Bright dot
                ctx.beginPath();
                ctx.arc(dx, dy, 1.8, 0, TAU);
                ctx.fillStyle = di === 0 ? '#76b900' : '#ffffff';
                ctx.globalAlpha = alpha * (di === 0 ? 0.7 : 0.4);
                ctx.fill();
            }
        }
    });

    ctx.restore();
}

// ════════════════════════════════════════════════════════
// 1. FLOATING PARTICLES with TRAILS + PARALLAX DEPTH
// ════════════════════════════════════════════════════════
const FLOAT_COUNT = 320;
const floaters = [];

for (let i = 0; i < FLOAT_COUNT; i++) {
    // depth: 0 = far background, 1 = foreground
    const depth = Math.random();
    const speedMult = 0.3 + depth * 1.2;  // foreground particles move faster
    const sizeMult = 0.5 + depth * 3.5;   // foreground particles are bigger (0.5 to 4px)
    floaters.push({
        x: Math.random() * 3000 - 500,
        y: Math.random() * 2000 - 200,
        vx: (Math.random() - 0.3) * 0.6 * speedMult,
        vy: (Math.random() - 0.5) * 0.4 * speedMult,
        size: sizeMult,
        depth,
        alpha: 0,
        targetAlpha: (0.1 + depth * 0.5) * (0.15 + Math.random() * 0.45),
        pulse: Math.random() * TAU,
        pulseSpeed: 0.5 + Math.random() * 2,
        trail: [],
        trailMax: Math.floor(3 + depth * 8), // foreground = longer trails
    });
}

function updateFloaters(sec) {
    for (const p of floaters) {
        // Store trail position before moving
        p.trail.push({ x: p.x, y: p.y });
        if (p.trail.length > p.trailMax) p.trail.shift();

        p.x += p.vx;
        p.y += p.vy;

        // Wrap around
        if (p.x > w + 50) { p.x = -50; p.trail.length = 0; }
        if (p.x < -50) { p.x = w + 50; p.trail.length = 0; }
        if (p.y > h + 50) { p.y = -50; p.trail.length = 0; }
        if (p.y < -50) { p.y = h + 50; p.trail.length = 0; }

        // Fade in over first 2 seconds
        const fadeIn = Math.min(1, sec / 2);
        const pulse = 0.7 + 0.3 * Math.sin(sec * p.pulseSpeed + p.pulse);
        p.alpha = p.targetAlpha * fadeIn * pulse;
    }
}

function drawFloaters() {
    for (const p of floaters) {
        if (p.alpha < 0.01) continue;

        // Draw trail (fading tail behind particle)
        if (p.trail.length > 1) {
            for (let t = 0; t < p.trail.length; t++) {
                const tp = p.trail[t];
                const ratio = t / p.trail.length;
                const trailAlpha = ratio * p.alpha * 0.35;
                if (trailAlpha < 0.005) continue;
                ctx.beginPath();
                ctx.arc(tp.x, tp.y, p.size * (0.3 + ratio * 0.5), 0, TAU);
                ctx.fillStyle = ACCENT;
                ctx.globalAlpha = trailAlpha;
                ctx.fill();
            }
        }

        // Draw particle
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, TAU);
        ctx.fillStyle = ACCENT;
        ctx.globalAlpha = p.alpha;
        ctx.fill();

        // Glow for larger particles
        if (p.size > 2.5) {
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size * 4, 0, TAU);
            ctx.fillStyle = ACCENT;
            ctx.globalAlpha = p.alpha * 0.06;
            ctx.fill();
        }
    }
    ctx.globalAlpha = 1;
}

// ════════════════════════════════════════════════════════
// 2. ROTATING GEOMETRIC SHAPES (wireframe polygons)
// ════════════════════════════════════════════════════════
const GEOM_COUNT = 18;
const geometrics = [];

for (let i = 0; i < GEOM_COUNT; i++) {
    const sides = [3, 5, 6, 8][Math.floor(Math.random() * 4)]; // tri, pent, hex, oct
    geometrics.push({
        x: Math.random() * 3000 - 500,
        y: Math.random() * 2000 - 200,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.2,
        radius: 15 + Math.random() * 50,
        sides,
        rotation: Math.random() * TAU,
        rotSpeed: (Math.random() - 0.5) * 0.008,
        alpha: 0,
        targetAlpha: 0.04 + Math.random() * 0.12,
    });
}

function updateGeometrics(sec) {
    for (const g of geometrics) {
        g.x += g.vx;
        g.y += g.vy;
        g.rotation += g.rotSpeed;

        if (g.x > w + 100) g.x = -100;
        if (g.x < -100) g.x = w + 100;
        if (g.y > h + 100) g.y = -100;
        if (g.y < -100) g.y = h + 100;

        const fadeIn = Math.min(1, sec / 2.5);
        let fadeOut = 1;
        if (sec > 5.5) fadeOut = Math.max(0, 1 - (sec - 5.5) / 2);
        g.alpha = g.targetAlpha * fadeIn * fadeOut;
    }
}

function drawGeometrics() {
    ctx.lineWidth = 1;
    for (const g of geometrics) {
        if (g.alpha < 0.005) continue;
        ctx.strokeStyle = ACCENT;
        ctx.globalAlpha = g.alpha;
        ctx.beginPath();
        for (let i = 0; i <= g.sides; i++) {
            const angle = (TAU / g.sides) * i + g.rotation;
            const px = g.x + g.radius * Math.cos(angle);
            const py = g.y + g.radius * Math.sin(angle);
            if (i === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
        }
        ctx.closePath();
        ctx.stroke();
    }
    ctx.globalAlpha = 1;
}

// ════════════════════════════════════════════════════════
// 3. DATA RAIN (sparse Matrix-style vertical dot columns)
// ════════════════════════════════════════════════════════
const DATA_COLUMNS = 40;
const dataRain = [];

function initDataRain() {
    dataRain.length = 0;
    for (let i = 0; i < DATA_COLUMNS; i++) {
        const col = {
            x: Math.random() * w,
            drops: [],
            speed: 1 + Math.random() * 2.5,
            spacing: 12 + Math.random() * 20,
            length: 4 + Math.floor(Math.random() * 8),
        };
        // Initialize drops
        const startY = -Math.random() * h;
        for (let d = 0; d < col.length; d++) {
            col.drops.push({ y: startY - d * col.spacing, alpha: 1 - d / col.length });
        }
        dataRain.push(col);
    }
}

function updateDataRain(sec) {
    if (sec > 6) return; // fade out by convergence
    for (const col of dataRain) {
        for (const drop of col.drops) {
            drop.y += col.speed;
            if (drop.y > h + 50) {
                drop.y = -30 - Math.random() * 200;
            }
        }
    }
}

function drawDataRain(sec) {
    if (sec > 6) return;
    const fadeIn = Math.min(1, sec / 1.5);
    let fadeOut = 1;
    if (sec > 4.5) fadeOut = Math.max(0, 1 - (sec - 4.5) / 1.5);
    const masterAlpha = fadeIn * fadeOut * 0.25;
    if (masterAlpha < 0.005) return;

    for (const col of dataRain) {
        for (const drop of col.drops) {
            if (drop.y < 0 || drop.y > h) continue;
            ctx.beginPath();
            ctx.arc(col.x, drop.y, 1.2, 0, TAU);
            ctx.fillStyle = ACCENT;
            ctx.globalAlpha = masterAlpha * drop.alpha;
            ctx.fill();
        }
    }
    ctx.globalAlpha = 1;
}

// ════════════════════════════════════════════════════════
// 4. ENERGY WAVES (radar pulses from center)
// ════════════════════════════════════════════════════════
const energyWaves = [];
const WAVE_INTERVAL = 0.8; // new wave every 0.8s
let lastWaveTime = -WAVE_INTERVAL;

function updateEnergyWaves(sec) {
    // Spawn new waves
    if (sec >= 1.5 && sec < 7 && sec - lastWaveTime >= WAVE_INTERVAL) {
        energyWaves.push({ born: sec, radius: 0 });
        lastWaveTime = sec;
    }

    // Update existing waves
    for (let i = energyWaves.length - 1; i >= 0; i--) {
        const wave = energyWaves[i];
        const age = sec - wave.born;
        wave.radius = age * 180; // expand speed
        wave.alpha = Math.max(0, 0.2 - age * 0.04);
        if (wave.alpha <= 0) {
            energyWaves.splice(i, 1);
        }
    }
}

function drawEnergyWaves() {
    ctx.lineWidth = 1.5;
    for (const wave of energyWaves) {
        if (wave.alpha < 0.005) continue;
        ctx.beginPath();
        ctx.arc(w / 2, h / 2, wave.radius, 0, TAU);
        ctx.strokeStyle = ACCENT;
        ctx.globalAlpha = wave.alpha;
        ctx.stroke();

        // Second thinner ring slightly behind
        if (wave.radius > 20) {
            ctx.beginPath();
            ctx.arc(w / 2, h / 2, wave.radius - 8, 0, TAU);
            ctx.globalAlpha = wave.alpha * 0.3;
            ctx.lineWidth = 0.5;
            ctx.stroke();
            ctx.lineWidth = 1.5;
        }
    }
    ctx.globalAlpha = 1;
}

// ════════════════════════════════════════════════════════
// 5. HEXAGONAL GRID (geometric layer)
// ════════════════════════════════════════════════════════
const hexagons = [];
const HEX_RADIUS = 40;

function initHexGrid() {
    hexagons.length = 0;
    const cols = Math.ceil(w / (HEX_RADIUS * 1.8)) + 2;
    const rows = Math.ceil(h / (HEX_RADIUS * 1.6)) + 2;

    for (let r = -1; r < rows; r++) {
        for (let c = -1; c < cols; c++) {
            const offsetX = (r % 2) * HEX_RADIUS * 0.9;
            const cx = c * HEX_RADIUS * 1.8 + offsetX;
            const cy = r * HEX_RADIUS * 1.6;
            const dist = Math.hypot(cx - w / 2, cy - h / 2);

            hexagons.push({
                cx, cy,
                radius: HEX_RADIUS,
                dist,
                alpha: 0,
                highlight: Math.random() < 0.08,
            });
        }
    }
    hexagons.sort((a, b) => a.dist - b.dist);
}

function drawHexagonPath(cx, cy, r) {
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 3) * i - Math.PI / 6;
        const x = cx + r * Math.cos(angle);
        const y = cy + r * Math.sin(angle);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.closePath();
}

function updateHexagons(sec) {
    for (let i = 0; i < hexagons.length; i++) {
        const hex = hexagons[i];
        const revealTime = hex.dist / (Math.max(w, h) * 0.7) * 3;
        const progress = Math.max(0, Math.min(1, (sec - revealTime) / 0.8));

        let fadeOut = 1;
        if (sec > 5) {
            fadeOut = Math.max(0, 1 - (sec - 5) / 2);
        }

        hex.alpha = progress * fadeOut * (hex.highlight ? 0.25 : 0.06);
    }
}

function drawHexagons() {
    ctx.lineWidth = 1;
    for (const hex of hexagons) {
        if (hex.alpha < 0.005) continue;

        ctx.strokeStyle = ACCENT;
        ctx.globalAlpha = hex.alpha;
        drawHexagonPath(hex.cx, hex.cy, hex.radius);
        ctx.stroke();

        if (hex.highlight && hex.alpha > 0.1) {
            ctx.fillStyle = ACCENT;
            ctx.globalAlpha = hex.alpha * 0.15;
            drawHexagonPath(hex.cx, hex.cy, hex.radius);
            ctx.fill();
        }
    }
    ctx.globalAlpha = 1;
}

// ════════════════════════════════════════════════════════
// 6. CIRCUIT TRACES with FLOWING DATA PULSES
// ════════════════════════════════════════════════════════
const traces = [];
const TRACE_COUNT = 25;

for (let i = 0; i < TRACE_COUNT; i++) {
    const segments = [];
    let x = Math.random() * 3000 - 500;
    let y = Math.random() * 2000 - 200;
    const segCount = 3 + Math.floor(Math.random() * 4);

    for (let s = 0; s < segCount; s++) {
        const horizontal = s % 2 === 0;
        const length = 60 + Math.random() * 200;
        const dir = Math.random() > 0.5 ? 1 : -1;
        const ex = horizontal ? x + length * dir : x;
        const ey = horizontal ? y : y + length * dir;
        segments.push({ x1: x, y1: y, x2: ex, y2: ey });
        x = ex;
        y = ey;
    }

    traces.push({
        segments,
        progress: 0,
        speed: 0.15 + Math.random() * 0.25,
        delay: Math.random() * 4,
        alpha: 0.1 + Math.random() * 0.2,
        hasNode: Math.random() < 0.5,
        // Flowing pulse data
        pulseCount: 1 + Math.floor(Math.random() * 3),
        pulsePhases: Array.from({ length: 3 }, () => Math.random()),
    });
}

function drawTraces(sec) {
    for (const trace of traces) {
        const elapsed = sec - trace.delay;
        if (elapsed < 0) continue;

        trace.progress = Math.min(1, elapsed * trace.speed);

        let fade = 1;
        if (sec > 5) fade = Math.max(0, 1 - (sec - 5) / 2);
        if (fade < 0.005) continue;

        const totalLength = trace.segments.reduce((sum, seg) => {
            return sum + Math.hypot(seg.x2 - seg.x1, seg.y2 - seg.y1);
        }, 0);
        let drawnLength = trace.progress * totalLength;

        // Draw base trace line
        ctx.strokeStyle = ACCENT;
        ctx.lineWidth = 1;
        ctx.globalAlpha = trace.alpha * fade;
        ctx.beginPath();

        let lastX, lastY;
        for (const seg of trace.segments) {
            const segLen = Math.hypot(seg.x2 - seg.x1, seg.y2 - seg.y1);
            if (drawnLength <= 0) break;

            const drawRatio = Math.min(1, drawnLength / segLen);
            const ex = seg.x1 + (seg.x2 - seg.x1) * drawRatio;
            const ey = seg.y1 + (seg.y2 - seg.y1) * drawRatio;

            ctx.moveTo(seg.x1, seg.y1);
            ctx.lineTo(ex, ey);
            lastX = ex;
            lastY = ey;
            drawnLength -= segLen;
        }
        ctx.stroke();

        // Draw flowing data pulses along the trace
        if (trace.progress > 0.3) {
            for (let p = 0; p < trace.pulseCount; p++) {
                const pulsePos = ((sec * 0.4 + trace.pulsePhases[p]) % 1) * trace.progress;
                let remainDist = pulsePos * totalLength;
                for (const seg of trace.segments) {
                    const segLen = Math.hypot(seg.x2 - seg.x1, seg.y2 - seg.y1);
                    if (remainDist <= segLen) {
                        const ratio = remainDist / segLen;
                        const px = seg.x1 + (seg.x2 - seg.x1) * ratio;
                        const py = seg.y1 + (seg.y2 - seg.y1) * ratio;
                        ctx.beginPath();
                        ctx.arc(px, py, 2.5, 0, TAU);
                        ctx.fillStyle = '#fff';
                        ctx.globalAlpha = trace.alpha * fade * 1.2;
                        ctx.fill();
                        // Glow around pulse
                        ctx.beginPath();
                        ctx.arc(px, py, 6, 0, TAU);
                        ctx.fillStyle = ACCENT;
                        ctx.globalAlpha = trace.alpha * fade * 0.2;
                        ctx.fill();
                        break;
                    }
                    remainDist -= segLen;
                }
            }
        }

        // Draw node (small diamond) at trace head
        if (trace.hasNode && lastX !== undefined && trace.progress < 1) {
            const nodeSize = 3;
            ctx.fillStyle = ACCENT;
            ctx.globalAlpha = trace.alpha * fade * 1.5;
            ctx.beginPath();
            ctx.moveTo(lastX, lastY - nodeSize);
            ctx.lineTo(lastX + nodeSize, lastY);
            ctx.lineTo(lastX, lastY + nodeSize);
            ctx.lineTo(lastX - nodeSize, lastY);
            ctx.closePath();
            ctx.fill();
        }
    }
    ctx.globalAlpha = 1;
}

// ════════════════════════════════════════════════════════
// 7. GEOMETRIC CONSTELLATIONS (shapes that form & dissolve)
// ════════════════════════════════════════════════════════
const CONSTELLATION_COUNT = 6;
const constellations = [];

for (let i = 0; i < CONSTELLATION_COUNT; i++) {
    const cx = Math.random() * 2400 - 200;
    const cy = Math.random() * 1600 - 100;
    const sides = [3, 4, 5][Math.floor(Math.random() * 3)]; // triangle, diamond, pentagon
    const radius = 30 + Math.random() * 60;
    const points = [];
    for (let s = 0; s < sides; s++) {
        const angle = (TAU / sides) * s - Math.PI / 2;
        points.push({
            x: cx + radius * Math.cos(angle),
            y: cy + radius * Math.sin(angle),
        });
    }
    constellations.push({
        cx, cy,
        points,
        rotation: Math.random() * TAU,
        rotSpeed: (Math.random() - 0.5) * 0.005,
        bornTime: 0.5 + Math.random() * 3,
        lifespan: 2 + Math.random() * 2,
        radius,
    });
}

function drawConstellations(sec) {
    for (const con of constellations) {
        const age = sec - con.bornTime;
        if (age < 0 || age > con.lifespan) continue;

        // Fade in and out
        const halfLife = con.lifespan / 2;
        let alpha;
        if (age < 0.5) alpha = age / 0.5;
        else if (age > con.lifespan - 0.8) alpha = (con.lifespan - age) / 0.8;
        else alpha = 1;
        alpha *= 0.2;

        con.rotation += con.rotSpeed;
        const cosR = Math.cos(con.rotation);
        const sinR = Math.sin(con.rotation);

        // Compute rotated points
        const rotated = con.points.map(p => {
            const dx = p.x - con.cx;
            const dy = p.y - con.cy;
            return {
                x: con.cx + dx * cosR - dy * sinR,
                y: con.cy + dx * sinR + dy * cosR,
            };
        });

        // Draw constellation dots
        for (const rp of rotated) {
            ctx.beginPath();
            ctx.arc(rp.x, rp.y, 2, 0, TAU);
            ctx.fillStyle = ACCENT;
            ctx.globalAlpha = alpha * 0.8;
            ctx.fill();
        }

        // Draw connecting lines
        ctx.strokeStyle = ACCENT;
        ctx.lineWidth = 0.8;
        ctx.globalAlpha = alpha * 0.4;
        ctx.beginPath();
        for (let i = 0; i < rotated.length; i++) {
            const p1 = rotated[i];
            const p2 = rotated[(i + 1) % rotated.length];
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
        }
        ctx.stroke();
    }
    ctx.globalAlpha = 1;
}

// ════════════════════════════════════════════════════════
// 8. VORTEX CONVERGENCE (stage 3: dramatic spiral inward)
// ════════════════════════════════════════════════════════
const CONVERGE_COUNT = 200;
const convergers = [];

for (let i = 0; i < CONVERGE_COUNT; i++) {
    const angle = Math.random() * TAU;
    const dist = 200 + Math.random() * 700;
    convergers.push({
        baseAngle: angle,
        baseDist: dist,
        angularSpeed: 0.5 + Math.random() * 2.5,   // spiral rotation speed
        speed: 1 + Math.random() * 3,
        size: 0.8 + Math.random() * 2.5,
        alpha: 0,
        trail: [],
        trailMax: 12 + Math.floor(Math.random() * 8),
        x: undefined,
        y: undefined,
    });
}

function updateConvergers(sec) {
    if (sec < 4.5) return;
    const progress = Math.min(1, (sec - 4.5) / 3);
    const eased = 1 - Math.pow(1 - progress, 2.5); // accelerating ease

    for (const p of convergers) {
        const currentDist = p.baseDist * (1 - eased * 0.97);
        // Spiral: angular speed increases as distance decreases
        const spiralAccel = 1 + (1 - currentDist / p.baseDist) * 4;
        const currentAngle = p.baseAngle + sec * p.angularSpeed * spiralAccel * 0.3;

        const newX = w / 2 + Math.cos(currentAngle) * currentDist;
        const newY = h / 2 + Math.sin(currentAngle) * currentDist;

        // Store trail before updating position
        if (p.x !== undefined) {
            p.trail.push({ x: p.x, y: p.y });
            if (p.trail.length > p.trailMax) p.trail.shift();
        }

        p.x = newX;
        p.y = newY;
        p.alpha = Math.min(0.9, progress * 1.8) * (1 - progress * 0.3);
    }
}

function drawConvergers() {
    for (const p of convergers) {
        if (p.alpha < 0.01 || p.x === undefined) continue;

        // Draw speed trails (elongated, fading)
        if (p.trail.length > 2) {
            ctx.beginPath();
            ctx.moveTo(p.trail[0].x, p.trail[0].y);
            for (let t = 1; t < p.trail.length; t++) {
                ctx.lineTo(p.trail[t].x, p.trail[t].y);
            }
            ctx.lineTo(p.x, p.y);
            ctx.strokeStyle = ACCENT;
            ctx.lineWidth = p.size * 0.6;
            ctx.globalAlpha = p.alpha * 0.15;
            ctx.stroke();
        }

        // Draw individual trail dots (fading)
        for (let t = 0; t < p.trail.length; t++) {
            const tp = p.trail[t];
            const ratio = t / p.trail.length;
            const trailAlpha = ratio * p.alpha * 0.25;
            if (trailAlpha < 0.005) continue;
            ctx.beginPath();
            ctx.arc(tp.x, tp.y, p.size * (0.2 + ratio * 0.5), 0, TAU);
            ctx.fillStyle = ACCENT;
            ctx.globalAlpha = trailAlpha;
            ctx.fill();
        }

        // Draw particle
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, TAU);
        ctx.fillStyle = ACCENT;
        ctx.globalAlpha = p.alpha;
        ctx.fill();

        // Bright leading glow
        if (p.size > 1.5) {
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size * 2.5, 0, TAU);
            ctx.fillStyle = ACCENT;
            ctx.globalAlpha = p.alpha * 0.08;
            ctx.fill();
        }
    }
    ctx.globalAlpha = 1;
}

// ════════════════════════════════════════════════════════
// 9. RADIANT CORE (stage 3-4: multi-layered energy core)
// ════════════════════════════════════════════════════════
function drawCore(sec) {
    if (sec < 5.5) return;

    const age = sec - 5.5;
    const coreAlpha = Math.min(1, age / 0.4);
    const pulse1 = 0.6 + 0.4 * Math.sin(sec * 8);
    const pulse2 = 0.5 + 0.5 * Math.sin(sec * 12 + 1);
    const pulse3 = 0.7 + 0.3 * Math.sin(sec * 5 + 2.5);
    const cx = w / 2;
    const cy = h / 2;

    // --- Radiating light rays ---
    const rayCount = 16;
    for (let i = 0; i < rayCount; i++) {
        const angle = (TAU / rayCount) * i + sec * 0.15;
        const innerR = 8;
        const outerR = 60 + 30 * pulse3;
        const spread = 0.015;

        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(angle - spread) * innerR, cy + Math.sin(angle - spread) * innerR);
        ctx.lineTo(cx + Math.cos(angle) * outerR, cy + Math.sin(angle) * outerR);
        ctx.lineTo(cx + Math.cos(angle + spread) * innerR, cy + Math.sin(angle + spread) * innerR);
        ctx.closePath();
        ctx.fillStyle = ACCENT;
        ctx.globalAlpha = coreAlpha * 0.06 * pulse1;
        ctx.fill();
    }

    // --- Outer diffuse glow ---
    const gradient0 = ctx.createRadialGradient(cx, cy, 0, cx, cy, 120);
    gradient0.addColorStop(0, 'rgba(' + ACCENT_RGB + ',0.15)');
    gradient0.addColorStop(0.5, 'rgba(' + ACCENT_RGB + ',0.04)');
    gradient0.addColorStop(1, 'rgba(' + ACCENT_RGB + ',0)');
    ctx.fillStyle = gradient0;
    ctx.globalAlpha = coreAlpha * pulse3;
    ctx.fillRect(cx - 120, cy - 120, 240, 240);

    // --- Multiple layered rings ---
    const rings = [
        { r: 50, width: 1.0, a: 0.08 },
        { r: 38, width: 1.5, a: 0.12 },
        { r: 26, width: 1.0, a: 0.15 },
        { r: 18, width: 2.0, a: 0.20 },
        { r: 12, width: 1.5, a: 0.25 },
    ];
    for (const ring of rings) {
        const animR = ring.r + Math.sin(sec * 4 + ring.r) * 3;
        ctx.beginPath();
        ctx.arc(cx, cy, animR, 0, TAU);
        ctx.strokeStyle = ACCENT;
        ctx.lineWidth = ring.width;
        ctx.globalAlpha = coreAlpha * ring.a * pulse1;
        ctx.stroke();
    }

    // --- Rotating partial arcs ---
    for (let a = 0; a < 3; a++) {
        const arcRadius = 30 + a * 14;
        const startAngle = sec * (1.5 + a * 0.7) + a * 2;
        ctx.beginPath();
        ctx.arc(cx, cy, arcRadius, startAngle, startAngle + Math.PI * 0.4);
        ctx.strokeStyle = ACCENT;
        ctx.lineWidth = 1.5;
        ctx.globalAlpha = coreAlpha * 0.2 * pulse2;
        ctx.stroke();
    }

    // --- Inner core gradient (green to white-hot center) ---
    const gradient1 = ctx.createRadialGradient(cx, cy, 0, cx, cy, 10);
    gradient1.addColorStop(0, '#ffffff');
    gradient1.addColorStop(0.3, '#dfffb0');
    gradient1.addColorStop(0.7, ACCENT);
    gradient1.addColorStop(1, 'rgba(' + ACCENT_RGB + ',0)');
    ctx.beginPath();
    ctx.arc(cx, cy, 10, 0, TAU);
    ctx.fillStyle = gradient1;
    ctx.globalAlpha = coreAlpha * pulse1 * 0.9;
    ctx.fill();

    // --- White-hot center dot ---
    ctx.beginPath();
    ctx.arc(cx, cy, 3.5, 0, TAU);
    ctx.fillStyle = '#ffffff';
    ctx.globalAlpha = coreAlpha * pulse1 * 0.95;
    ctx.fill();

    // --- Second white glow layer ---
    ctx.beginPath();
    ctx.arc(cx, cy, 6, 0, TAU);
    ctx.fillStyle = '#ffffff';
    ctx.globalAlpha = coreAlpha * pulse2 * 0.15;
    ctx.fill();

    // --- Expanding line (stage 4 transition) ---
    if (sec > 7.5) {
        const lineProgress = Math.min(1, (sec - 7.5) / 1.0);
        const lineWidth = w * 0.85 * lineProgress;
        const lineFade = Math.max(0, 1 - (sec - 8.2) / 0.8);
        const lineEase = 1 - Math.pow(1 - lineProgress, 3);

        // Main line
        ctx.strokeStyle = ACCENT;
        ctx.globalAlpha = lineFade * 0.6;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(cx - lineWidth * lineEase / 2, cy);
        ctx.lineTo(cx + lineWidth * lineEase / 2, cy);
        ctx.stroke();

        // Bright center flash on line
        const flashGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, 50);
        flashGrad.addColorStop(0, 'rgba(255,255,255,0.3)');
        flashGrad.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.fillStyle = flashGrad;
        ctx.globalAlpha = lineFade * lineEase * 0.6;
        ctx.fillRect(cx - 50, cy - 50, 100, 100);
    }

    ctx.globalAlpha = 1;
}

// ════════════════════════════════════════════════════════
// 10. SCANLINE + GRID OVERLAY (subtle tech texture)
// ════════════════════════════════════════════════════════
function drawGridOverlay(sec) {
    if (sec > 5) return;
    const gridAlpha = 0.025 * Math.min(1, sec / 1);

    ctx.strokeStyle = ACCENT;
    ctx.lineWidth = 0.5;
    ctx.globalAlpha = gridAlpha;

    // Vertical lines
    const spacing = 80;
    for (let x = 0; x < w; x += spacing) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
    }
    // Horizontal lines
    for (let y = 0; y < h; y += spacing) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
    }

    // Moving scanline
    const scanY = (sec * 150) % h;
    ctx.fillStyle = ACCENT;
    ctx.globalAlpha = 0.04;
    ctx.fillRect(0, scanY, w, 2);
    ctx.globalAlpha = 0.015;
    ctx.fillRect(0, scanY - 30, w, 30);

    ctx.globalAlpha = 1;
}

// ════════════════════════════════════════════════════════
// DOM: LOADING SCREEN → HERO REVEAL
// ════════════════════════════════════════════════════════
const loadingScreen = document.getElementById('loading-screen');
const mainContent = document.getElementById('main-content');
const counterEl = document.getElementById('counter');
const progressBar = document.getElementById('progress-bar');
const cyclingWordEl = document.getElementById('cycling-word');
const roleWordEl = document.getElementById('role-word');

const LOADING_DURATION = 2700; // ms
const cyclingWords = ['Initializing', 'Calibrating', 'Connecting', 'Optimizing', 'Ready'];
const heroRoles = ['Forecasting', 'Optimization', 'Risk Analysis', 'Supply Chain'];
let loadingDone = false;
let heroRevealed = false;
let roleIndex = 0;

// Cycling words during loading
let wordIndex = 0;
const wordInterval = setInterval(function() {
    wordIndex = (wordIndex + 1) % cyclingWords.length;
    cyclingWordEl.textContent = cyclingWords[wordIndex];
    cyclingWordEl.style.animation = 'none';
    cyclingWordEl.offsetHeight; // trigger reflow
    cyclingWordEl.style.animation = 'role-fade-in 0.4s ease-out';
}, 600);

// Hero role cycling
setInterval(function() {
    roleIndex = (roleIndex + 1) % heroRoles.length;
    if (roleWordEl) {
        roleWordEl.textContent = heroRoles[roleIndex];
        roleWordEl.style.animation = 'none';
        roleWordEl.offsetHeight;
        roleWordEl.style.animation = 'role-fade-in 0.4s ease-out';
    }
}, 2000);

let globalStage = 1;
const START_TIME = performance.now();

function updateDOMStages(sec) {
    const elapsed = sec * 1000;

    // Loading counter + boot log
    if (!loadingDone) {
        const count = Math.min(100, Math.floor((elapsed / LOADING_DURATION) * 100));
        counterEl.textContent = String(count).padStart(3, '0');
        progressBar.style.width = count + '%';

        // Reveal boot log lines at thresholds
        var thresholds = [15, 35, 55, 75, 90];
        for (var bi = 0; bi < thresholds.length; bi++) {
            if (count >= thresholds[bi]) {
                var bootEl = document.getElementById('boot-' + bi);
                if (bootEl && !bootEl.classList.contains('visible')) {
                    bootEl.classList.add('visible');
                }
            }
        }

        if (count >= 100) {
            loadingDone = true;
            clearInterval(wordInterval);
            setTimeout(function() {
                loadingScreen.classList.add('fade-out');
                mainContent.classList.remove('hidden');
                // Trigger blur-in reveals with stagger
                setTimeout(revealHero, 200);
            }, 400);
        }
    }
}

function revealHero() {
    if (heroRevealed) return;
    heroRevealed = true;
    // Reveal title first
    var title = document.querySelector('.name-reveal');
    if (title) title.classList.add('visible');
    // Stagger blur-in elements
    var blurEls = document.querySelectorAll('.blur-in');
    blurEls.forEach(function(el, i) {
        setTimeout(function() { el.classList.add('visible'); }, 150 + i * 120);
    });
}

// ════════════════════════════════════════════════════════
// MAIN RENDER LOOP
// ════════════════════════════════════════════════════════
function loop(time) {
    const elapsed = time - START_TIME;
    const sec = elapsed / 1000;

    if (sec < 2) globalStage = 1;
    else if (sec < 5) globalStage = 2;
    else if (sec < 7.5) globalStage = 3;
    else globalStage = 4;

    updateDOMStages(sec);

    // Clear with subtle trail effect for motion blur
    ctx.fillStyle = 'rgba(0, 0, 0, 0.1)';
    ctx.fillRect(0, 0, w, h);

    // Layer 0: 3D Globe (background, lowest layer)
    drawGlobe(sec);

    // Layer 1: Grid overlay (subtle background texture)
    drawGridOverlay(sec);

    // Layer 2: Data rain (sparse vertical dot columns)
    updateDataRain(sec);
    drawDataRain(sec);

    // Layer 3: Hexagonal grid (reveals from center)
    updateHexagons(sec);
    drawHexagons();

    // Layer 4: Rotating geometric shapes (wireframe polygons)
    updateGeometrics(sec);
    drawGeometrics();

    // Layer 5: Geometric constellations
    drawConstellations(sec);

    // Layer 6: Circuit traces with flowing pulses
    drawTraces(sec);

    // Layer 7: Floating particles with trails + depth
    updateFloaters(sec);
    drawFloaters();

    // Layer 8: Energy waves (radar pulses)
    updateEnergyWaves(sec);
    drawEnergyWaves();

    // Layer 9: Vortex convergence — REMOVED (user preference)

    // Layer 10: Radiant core — REMOVED

    requestAnimationFrame(loop);
}

// --- Init (must be after all const declarations) ---
resize();
requestAnimationFrame(loop);

// (Number tweening removed — stats are static in the new hero layout)
