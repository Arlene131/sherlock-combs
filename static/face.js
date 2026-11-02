import { FaceLandmarker, FilesetResolver } from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
import { setMood } from "/static/mascot.js";

const WASM_URL = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm";
const MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

export const FACE_LABELS = {
  oval: "oval", round: "bulat", square: "kotak", oblong: "lonjong",
  heart: "hati", diamond: "diamond", triangle: "segitiga",
};

const FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400,
  377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109];
const LM = {
  brow: 9, chin: 152, nose: 1, eyeL: 33, eyeR: 263,
  foreheadL: 54, foreheadR: 284,
  cheekL: 234, cheekR: 454,
  jawL: 58, jawR: 288,
};

export const PROTOTYPES = {
  oval:     { taper: -0.0038, jawAngle: 138.72, forehead: 0.8778, jaw: 0.8816 },
  round:    { taper: -0.0235, jawAngle: 133.24, forehead: 0.8615, jaw: 0.8850 },
  square:   { taper: -0.0327, jawAngle: 137.48, forehead: 0.8651, jaw: 0.8978 },
  heart:    { taper:  0.0355, jawAngle: 142.16, forehead: 0.8946, jaw: 0.8591 },
  diamond:  { taper:  0.0323, jawAngle: 142.10, forehead: 0.9075, jaw: 0.8752 },
  oblong:   { taper:  0.0071, jawAngle: 140.96, forehead: 0.8807, jaw: 0.8736 },
  triangle: { taper: -0.0710, jawAngle: 131.23, forehead: 0.8478, jaw: 0.9189 },
};
const SPREAD = { taper: 0.035, jawAngle: 4.0, forehead: 0.0188, jaw: 0.0178 };

export function rankShapes(m) {
  const features = { ...m, taper: m.forehead - m.jaw };
  return Object.entries(PROTOTYPES)
    .map(([shape, p]) => ({
      shape,
      distance: Math.sqrt(Object.keys(SPREAD)
        .reduce((sum, k) => sum + ((features[k] - p[k]) / SPREAD[k]) ** 2, 0)),
    }))
    .sort((a, b) => a.distance - b.distance);
}

export function classify(m) {
  return rankShapes(m)[0].shape;
}
const WINDOW = 20;

let landmarker = null;
async function getLandmarker() {
  if (landmarker) return landmarker;
  const vision = await FilesetResolver.forVisionTasks(WASM_URL);
  landmarker = await FaceLandmarker.createFromOptions(vision, {
    baseOptions: { modelAssetPath: MODEL_URL, delegate: "GPU" },
    runningMode: "VIDEO",
    numFaces: 1,
  });
  return landmarker;
}

const px = (p, w, h) => ({ x: p.x * w, y: p.y * h });
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
function angleAt(b, a, c) {
  const v1 = { x: a.x - b.x, y: a.y - b.y }, v2 = { x: c.x - b.x, y: c.y - b.y };
  const cos = (v1.x * v2.x + v1.y * v2.y) / (Math.hypot(v1.x, v1.y) * Math.hypot(v2.x, v2.y));
  return (Math.acos(Math.max(-1, Math.min(1, cos))) * 180) / Math.PI;
}

function measure(raw, w, h) {
  const P = (i) => px(raw[i], w, h);
  const nose = P(LM.nose), cheekL = P(LM.cheekL), cheekR = P(LM.cheekR);
  const eyeL = P(LM.eyeL), eyeR = P(LM.eyeR);

  const yaw = dist(nose, cheekL) / dist(nose, cheekR);
  const roll = Math.abs((Math.atan2(eyeR.y - eyeL.y, eyeR.x - eyeL.x) * 180) / Math.PI);
  if (yaw < 0.8 || yaw > 1.25 || roll > 8) return null;

  const cheek = dist(cheekL, cheekR);
  const brow = P(LM.brow), chin = P(LM.chin);
  const length = 1.5 * dist(brow, chin);
  const jawAngle = (angleAt(P(LM.jawL), cheekL, chin) + angleAt(P(LM.jawR), cheekR, chin)) / 2;
  return {
    ratio: length / cheek,
    forehead: dist(P(LM.foreheadL), P(LM.foreheadR)) / cheek,
    jaw: dist(P(LM.jawL), P(LM.jawR)) / cheek,
    jawAngle,
  };
}

function average(samples) {
  const keys = ["ratio", "forehead", "jaw", "jawAngle"];
  const out = {};
  for (const k of keys) out[k] = samples.reduce((s, m) => s + m[k], 0) / samples.length;
  return out;
}

function draw(canvas, raw, ok) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  const P = (i) => px(raw[i], w, h);
  const color = ok ? "#d4a73a" : "#b0563b";

  ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
  FACE_OVAL.forEach((i, n) => { const p = P(i); n ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y); });
  ctx.closePath(); ctx.stroke();

  const brow = P(LM.brow), chin = P(LM.chin);
  const hairline = { x: brow.x + (brow.x - chin.x) * 0.5, y: brow.y + (brow.y - chin.y) * 0.5 };
  ctx.setLineDash([6, 5]); ctx.lineWidth = 1.5; ctx.strokeStyle = "#f3e7d3";
  const line = (a, b) => { ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); };
  line(hairline, chin);
  line(P(LM.foreheadL), P(LM.foreheadR));
  line(P(LM.cheekL), P(LM.cheekR));
  line(P(LM.jawL), P(LM.jawR));
  ctx.setLineDash([]);
  ctx.fillStyle = "#f3e7d3";
  ctx.beginPath(); ctx.arc(hairline.x, hairline.y, 5, 0, Math.PI * 2); ctx.fill();
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function playCameraIntro(dialog) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const intro = dialog.querySelector(".camera-intro");
  dialog.classList.remove("is-snap");
  dialog.classList.add("is-intro");
  setMood(intro, "camera");
  await sleep(1100);
  setMood(intro, "snap");
  dialog.classList.add("is-snap");
  await sleep(850);
  dialog.classList.remove("is-intro", "is-snap");
}

export function startFaceScan() {
  const dialog = document.getElementById("face-dialog");
  const video = document.getElementById("face-video");
  const canvas = document.getElementById("face-canvas");
  const status = document.getElementById("face-status");
  const metrics = document.getElementById("face-metrics");
  const useBtn = document.getElementById("face-use");
  const cancelBtn = document.getElementById("face-cancel");
  const rescanBtn = document.getElementById("face-rescan");

  return new Promise(async (resolve) => {
    let stream = null, rafId = null, done = false, current = null;
    let samples = [];

    const finish = (value) => {
      if (done) return;
      done = true;
      dialog.classList.remove("is-intro", "is-snap");
      cancelAnimationFrame(rafId);
      stream?.getTracks().forEach((t) => t.stop());
      video.srcObject = null;
      canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
      dialog.close();
      resolve(value);
    };
    const resetWindow = () => { samples = []; current = null; useBtn.disabled = true; };

    resetWindow();
    metrics.textContent = "";
    useBtn.onclick = () => finish(current);
    cancelBtn.onclick = () => finish(null);
    rescanBtn.onclick = resetWindow;
    dialog.oncancel = (e) => { e.preventDefault(); finish(null); };
    dialog.showModal();
    getLandmarker().catch(() => {});
    await playCameraIntro(dialog);
    if (done) return;

    try {
      status.textContent = "Meminta izin kamera…";
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: 1280, height: 720 } });
      video.srcObject = stream;
      await video.play();
      status.textContent = "Memuat model deteksi wajah…";
      const detector = await getLandmarker();
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      document.querySelector(".video-wrap").style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}`;

      let lastTime = -1;
      const loop = () => {
        if (done) return;
        if (video.currentTime !== lastTime) {
          lastTime = video.currentTime;
          const res = detector.detectForVideo(video, performance.now());
          const raw = res.faceLandmarks?.[0];
          if (!raw) {
            canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
            resetWindow();
            status.textContent = "Wajah belum terdeteksi. Hadap ke kamera ya.";
          } else {
            const m = measure(raw, video.videoWidth, video.videoHeight);
            draw(canvas, raw, Boolean(m));
            if (!m) {
              status.textContent = "Hadap lurus ke kamera, jangan miring atau menoleh.";
            } else {
              samples.push(m);
              if (samples.length > WINDOW) samples.shift();
              if (samples.length < WINDOW) {
                status.textContent = `Mengukur… ${Math.round((samples.length / WINDOW) * 100)}%`;
              } else {
                const avg = average(samples);
                const ranking = rankShapes(avg);
                current = ranking[0].shape;
                useBtn.disabled = false;
                const close = ranking[1].distance - ranking[0].distance < 0.5;
                status.innerHTML = `Perkiraan bentuk wajah: <strong>${FACE_LABELS[current]}</strong>` +
                  (close ? ` <span class="alt">(mirip juga: ${FACE_LABELS[ranking[1].shape]})</span>` : "") +
                  `<small>Update live. </small>`;
                metrics.textContent = `panjang/lebar ${avg.ratio.toFixed(2)} · dahi ${avg.forehead.toFixed(2)} · ` +
                  `rahang ${avg.jaw.toFixed(2)} · sudut rahang ${avg.jawAngle.toFixed(0)}°`;
              }
            }
          }
        }
        rafId = requestAnimationFrame(loop);
      };
      loop();
    } catch (err) {
      console.error(err);
      status.textContent = err.name === "NotAllowedError"
        ? "Izin kamera ditolak. Kamu tetap bisa memilih bentuk wajah secara manual."
        : `Kamera tidak bisa dipakai (${err.message}).`;
    }
  });
}
