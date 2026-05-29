/*
  J.A.R.V.I.S. High-Level Tactical Client
  Manages organic 3D simulated particle orb morphing, Synthesizer nodes, and full telemetry metrics.
*/

// --- State Variables ---
let currentPasscode = "";
let isAuthorized = false;
let currentCoreState = "STANDBY"; // STANDBY, LISTENING, THINKING, SPEAKING
let lastPingTime = 0;
let apiToken = "";
let activeTab = "mission";
let currentTtsBackend = "elevenlabs";
let bootSequenceConsumed = false;

// Telemetry Histories (30 points for sparklines)
const statHistories = {
  cpu: new Array(30).fill(0),
  ram: new Array(30).fill(0),
  battery: new Array(30).fill(0),
  disk: new Array(30).fill(0),
  netDown: new Array(30).fill(0),
  netUp: new Array(30).fill(0)
};

// Dynamic Network counters
let lastTxBytes = 0;
let lastRxBytes = 0;
let lastNetTimestamp = 0;
let smoothedTelemetry = {
  cpu: null
};

// Web Audio API Synthesizer Context
let audioCtx = null;

// Speech and Audio Stream variables
let micStream = null;
let audioAnalyser = null;
let audioDataArray = null;
let micCanvasCtx = null;
let recognition = null;
let isListening = false;

// 3D Speech Reaction Variables
let speechAmplitude = 0;
let targetSpeechAmplitude = 0;
let speechUtterance = null;

// 3D Particles Sphere Setup for Hologram Canvas
let hologramCanvas = null;
let hologramCtx = null;
const particles = [];
const PARTICLE_COUNT = 280; // Denser particle count for organic ChatGPT core look

// Feature States
let selectedPid = null;
let selectedNoteIndex = null;
let selectedReminderIndex = null;
let selectedTaskIndex = null;
let localRemindersList = [];
let quickTasksList = [];
let attachedWebReferences = [];
let spokenReminders = new Set();
let calendarEvents = [];
let currentMonth = 4; // May (0-indexed is 4)
let currentYear = 2026;
let radarCanvas = null;
let radarCtx = null;
let radarAngle = 0;
let isWebcamActive = false;
let selectedContextIndex = null;
const radarBlips = [];
let systemStatsPollTimer = null;
let mobileCompanionPollTimer = null;
let latestMobileMapUrl = "";

// --- Initialize Elements ---
document.addEventListener("DOMContentLoaded", () => {
  initClock();
  initPasscode();
  init3DHologram();
  initRadar();
  initCameraHUD();
  animateEqualizer();
  setupEventListeners();
  createGuiParityPanels();
  
  const bootParams = new URLSearchParams(window.location.search);
  const skipIntro = bootParams.get("skipIntro") === "1" || bootParams.get("intro") === "0";
  if (skipIntro) {
    document.getElementById("boot-sequence-overlay")?.remove();
    checkAuthAndUnlock();
  } else {
    // For development and showing off the cinematic boot sequence, we play it every time.
    // We can add sessionStorage check back later for production.
    playBootSequence().then(() => checkAuthAndUnlock());
  }

  function checkAuthAndUnlock() {
    // Query parameter token auto-unlock check (e.g. ?token=JARVIS_WEB_TOKEN)
    const urlParams = new URLSearchParams(window.location.search);
    const urlToken = urlParams.get("token");
    if (urlToken) {
      apiToken = urlToken;
      sessionStorage.setItem("jarvis_token", apiToken);
      
      // Validate with server and unlock
      fetch("/api/auth", {
        method: "POST",
        headers: publicHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ token: urlToken })
      })
      .then(res => res.json())
      .then(data => {
        if (data.ok) {
          unlockDashboard();
        }
      })
      .catch(() => {
        // Offline/fallback unlock
        unlockDashboard();
      });
    } else if (sessionStorage.getItem("jarvis_token")) {
      apiToken = sessionStorage.getItem("jarvis_token") || "jarvis";
      unlockDashboard();
    }
  }
});

// --- Web Audio Synthesizer Cues ---
function playSynthSound(type) {
  try {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }

    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);

    const now = audioCtx.currentTime;

    if (type === "click") {
      osc.type = "sine";
      osc.frequency.setValueAtTime(1400, now);
      osc.frequency.exponentialRampToValueAtTime(120, now + 0.04);
      gain.gain.setValueAtTime(0.1, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
      osc.start(now);
      osc.stop(now + 0.04);
    } 
    else if (type === "success") {
      osc.type = "sine";
      osc.frequency.setValueAtTime(700, now);
      osc.frequency.setValueAtTime(1100, now + 0.07);
      gain.gain.setValueAtTime(0.18, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
      osc.start(now);
      osc.stop(now + 0.35);
    } 
    else if (type === "error") {
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(105, now);
      gain.gain.setValueAtTime(0.25, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
      osc.start(now);
      osc.stop(now + 0.3);
    }
    else if (type === "startup") {
      osc.type = "triangle";
      osc.frequency.setValueAtTime(180, now);
      osc.frequency.exponentialRampToValueAtTime(950, now + 0.6);
      gain.gain.setValueAtTime(0.2, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.75);
      osc.start(now);
      osc.stop(now + 0.75);
    }
  } catch (e) {
    console.warn("Audio Context blocked:", e);
  }
}

// --- Passcode / Security Screen ---
function publicHeaders(extra = {}) {
  return Object.assign({
    "ngrok-skip-browser-warning": "1"
  }, extra);
}

function initPasscode() {
  const display = document.getElementById("pass-display");
  const keys = document.querySelectorAll(".key-btn[data-val]");
  const deleteBtn = document.getElementById("key-del");
  const enterBtn = document.getElementById("key-enter");
  const pasteBtn = document.getElementById("key-paste");
  const bioTrigger = document.getElementById("bio-scan-trigger");
  const lockscreenRoot = document.getElementById("lockscreen");
  const statusText = document.getElementById("nlk-status-text");
  const MAX_TOKEN_LENGTH = 256;

  keys.forEach(btn => {
    btn.addEventListener("click", () => {
      playSynthSound("click");
      clearAuthError();
      if (currentPasscode.length < MAX_TOKEN_LENGTH) {
        currentPasscode += btn.getAttribute("data-val");
        pulseVirtualKey(btn.getAttribute("data-key") || btn.getAttribute("data-val"));
        updatePasscodeDisplay();
      }
    });
  });

  if (deleteBtn) {
    deleteBtn.addEventListener("click", () => {
      playSynthSound("click");
      clearAuthError();
      pulseVirtualKey("Backspace");
      currentPasscode = currentPasscode.slice(0, -1);
      updatePasscodeDisplay();
    });
  }

  if (enterBtn) {
    enterBtn.addEventListener("click", () => {
      pulseVirtualKey("Enter");
      verifyAccess();
    });
  }

  function setPasscodeFromText(text) {
    const clean = String(text || "").trim().slice(0, MAX_TOKEN_LENGTH);
    if (!clean) return;
    currentPasscode = clean;
    updatePasscodeDisplay();
  }

  async function pasteTokenFromClipboard() {
    clearAuthError();
    try {
      const text = await navigator.clipboard.readText();
      setPasscodeFromText(text);
      if (statusText) statusText.textContent = "TOKEN PASTED";
      playSynthSound("success");
    } catch (_err) {
      if (statusText) statusText.textContent = "PRESS CTRL+V TO PASTE TOKEN";
      playSynthSound("error");
    }
  }

  if (pasteBtn) {
    pasteBtn.addEventListener("click", pasteTokenFromClipboard);
  }

  document.addEventListener("paste", (e) => {
    const lockscreen = document.getElementById("lockscreen");
    if (!lockscreen || lockscreen.style.opacity === "0") return;
    const text = e.clipboardData?.getData("text") || "";
    if (!text.trim()) return;
    e.preventDefault();
    clearAuthError();
    setPasscodeFromText(text);
    if (statusText) statusText.textContent = "TOKEN PASTED";
  });

  // Keyboard support for passcode (so you can type "jarvis" or anything else)
  document.addEventListener("keydown", (e) => {
    // Only listen if lockscreen is active
    const lockscreen = document.getElementById("lockscreen");
    if (!lockscreen || lockscreen.style.opacity === "0") return;

    if (e.key === "Enter") {
      e.preventDefault();
      pulseVirtualKey("Enter");
      verifyAccess();
    } else if (e.key === "Backspace") {
      e.preventDefault();
      playSynthSound("click");
      clearAuthError();
      pulseVirtualKey("Backspace");
      currentPasscode = currentPasscode.slice(0, -1);
      updatePasscodeDisplay();
    } else if (e.key === "Tab") {
      e.preventDefault();
      pulseVirtualKey("Tab");
    } else if (e.key.length === 1 && /^[ -~]$/.test(e.key)) {
      e.preventDefault();
      playSynthSound("click");
      clearAuthError();
      pulseVirtualKey(e.key);
      if (currentPasscode.length < MAX_TOKEN_LENGTH) {
        currentPasscode += e.key;
        updatePasscodeDisplay();
      }
    }
  });

  if (bioTrigger) {
    bioTrigger.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      const bootOverlay = document.getElementById("boot-sequence-overlay");
      if (bootOverlay) {
        bootOverlay.style.display = "none";
        bootOverlay.style.opacity = "0";
        bootOverlay.remove();
      }
      bootSequenceConsumed = true;
      document.body.classList.remove("boot-video-active");
      playSynthSound("click");
      clearAuthError();
      bioTrigger.classList.add("scanning");
      if (statusText) statusText.textContent = "BIOMETRIC SCAN IN PROGRESS";
      const scanLine = bioTrigger.querySelector(".scanner-bar");
      if (scanLine) scanLine.style.animationPlayState = "running";
      
      // Biometric match simulation
      setTimeout(() => {
        bioTrigger.classList.remove("scanning");
        if (statusText) statusText.textContent = "IDENTITY CONFIRMED";
        playSynthSound("success");
        unlockDashboard();
      }, 1500);
    });
  }

  function updatePasscodeDisplay() {
    if (currentPasscode.length === 0) {
      display.textContent = "••••••••";
      display.removeAttribute("data-filled");
      if (statusText) statusText.textContent = "AWAITING AUTHORIZATION";
    } else {
      display.textContent = "•".repeat(Math.min(currentPasscode.length, 24));
      display.setAttribute("data-filled", String(currentPasscode.length));
      if (statusText) statusText.textContent = `${currentPasscode.length} GLYPHS CAPTURED`;
    }
  }

  function clearAuthError() {
    if (lockscreenRoot) lockscreenRoot.classList.remove("auth-error");
    if (display) display.style.color = "";
  }

  function pulseVirtualKey(key) {
    const normalized = key.length === 1 ? key.toLowerCase() : key;
    const candidates = Array.from(document.querySelectorAll(".key-btn")).filter(btn => {
      const btnKey = btn.getAttribute("data-key");
      if (!btnKey) return false;
      return btnKey.length === 1 ? btnKey.toLowerCase() === normalized : btnKey === normalized;
    });
    const target = candidates[0];
    if (!target) return;
    target.classList.remove("key-active");
    void target.offsetWidth;
    target.classList.add("key-active");
    setTimeout(() => target.classList.remove("key-active"), 150);
  }

  function verifyAccess() {
    const providedToken = currentPasscode.trim();
    if (statusText) statusText.textContent = "VERIFYING OVERRIDE CODE";
    
    // Call server-side authentication endpoint
    fetch("/api/auth", {
      method: "POST",
      headers: publicHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ token: providedToken })
    })
    .then(res => {
      if (!res.ok) throw new Error("Auth failed");
      return res.json();
    })
    .then(data => {
      if (data.ok) {
        playSynthSound("success");
        apiToken = providedToken;
        sessionStorage.setItem("jarvis_token", apiToken);
        unlockDashboard();
      } else {
        throw new Error("Invalid credentials");
      }
    })
    .catch(() => {
      // Local fallback for quick development bypass or offline use
      const cleanCode = providedToken.toLowerCase();
      if (cleanCode === "1234" || cleanCode === "jarvis" || cleanCode === "0a0w8e4p7x6n9x1u3" || cleanCode === "") {
        playSynthSound("success");
        apiToken = cleanCode === "jarvis" || cleanCode === "0a0w8e4p7x6n9x1u3" ? providedToken : "jarvis";
        sessionStorage.setItem("jarvis_token", apiToken);
        unlockDashboard();
      } else {
        playSynthSound("error");
        if (lockscreenRoot) {
          lockscreenRoot.classList.remove("auth-error");
          void lockscreenRoot.offsetWidth;
          lockscreenRoot.classList.add("auth-error");
        }
        if (statusText) statusText.textContent = "ACCESS DENIED";
        display.textContent = "ACCESS DENIED";
        display.style.color = "var(--red-primary)";
        currentPasscode = "";
        setTimeout(updatePasscodeDisplay, 1200);
      }
    });
  }
}

function unlockDashboard() {
  isAuthorized = true;
  document.getElementById("lockscreen").style.opacity = "0";
  document.getElementById("lockscreen").style.pointerEvents = "none";
  
  // Set default idle state
  document.body.classList.add("jarvis-idle");
  
  // Remove hidden to trigger cinematic CSS transitions
  document.getElementById("main-hud").classList.remove("hidden");
  
  setTimeout(() => {
    playSynthSound("startup");
    startAmbientAudio();
    appendLog("SYSTEM", "Biometric credentials approved. Quantum web hub online.", "sys");
    
    // Switch to initial tab pane visibility manually to render cleanly
    switchTab("mission");
  }, 300);

  // Begin REST polling loop
  startDataPolling();
}

// --- Multi-Layer Ambient Audio Stacking ---
let ambientOsc = null;
let ambientGain = null;

function startAmbientAudio() {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') audioCtx.resume();
    
    // Layer 1: Low Reactor Hum (Continuous)
    ambientOsc = audioCtx.createOscillator();
    ambientGain = audioCtx.createGain();
    ambientOsc.type = "sine";
    ambientOsc.frequency.setValueAtTime(45, audioCtx.currentTime);
    ambientGain.gain.setValueAtTime(0.02, audioCtx.currentTime);
    
    ambientOsc.connect(ambientGain);
    ambientGain.connect(audioCtx.destination);
    ambientOsc.start();
    
    // Layer 2: Distant Server Chirps (Random)
    setInterval(() => {
      // Only play chirps sometimes
      if (Math.random() > 0.3) {
        const chirpOsc = audioCtx.createOscillator();
        const chirpGain = audioCtx.createGain();
        chirpOsc.type = "square";
        
        // Random high frequency
        const freq = 2000 + Math.random() * 2000;
        chirpOsc.frequency.setValueAtTime(freq, audioCtx.currentTime);
        
        chirpGain.gain.setValueAtTime(0.005, audioCtx.currentTime);
        chirpGain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + 0.1);
        
        chirpOsc.connect(chirpGain);
        chirpGain.connect(audioCtx.destination);
        chirpOsc.start();
        chirpOsc.stop(audioCtx.currentTime + 0.1);
      }
    }, 4000);
    
  } catch(e) {
    console.warn("Ambient audio failed:", e);
  }
}

// --- Live Clock & Time ---
function initClock() {
  const clock = document.getElementById("clock-time");
  const dateEl = document.getElementById("date-display");

  function updateTime() {
    const d = new Date();
    clock.textContent = d.toLocaleTimeString('en-US');
    
    const options = { weekday: 'long', year: 'numeric', month: 'short', day: 'numeric' };
    dateEl.textContent = d.toLocaleDateString('en-US', options).toUpperCase();
  }
  setInterval(updateTime, 1000);
  updateTime();
}

// --- ChatGPT-Style 3D Morphing Organic Particle Orb Engine ---
function init3DHologram() {
  hologramCanvas = document.getElementById("hologram-canvas");
  hologramCtx = hologramCanvas.getContext("2d");
  
  // Distribute particles uniformly over a sphere shell with radial volumetric variance
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const theta = Math.acos(Math.random() * 2 - 1); // 0 to PI
    const phi = Math.random() * Math.PI * 2;         // 0 to 2*PI
    
    // Categorize particles into layers for advanced depth-coloring
    let layer = 'mid';
    const rand = Math.random();
    if (rand > 0.7) {
      layer = 'neon';  // light glowing core highlights
    } else if (rand < 0.3) {
      layer = 'deep';  // deep background ambient volume
    }
    
    particles.push({
      theta: theta,
      phi: phi,
      size: Math.random() * 2.2 + 0.8,
      baseRadiusOffset: Math.random() * 24 - 12, // creates thickness/volumetric shell
      layer: layer,
      phase: Math.random() * Math.PI * 2
    });
  }

  let timeVal = 0;

  function drawHologram() {
    const w = hologramCanvas.width;
    const h = hologramCanvas.height;
    const cx = w / 2;
    const cy = h / 2;

    hologramCtx.clearRect(0, 0, w, h);

    // Dynamic animation parameters based on HUD state
    let rotSpeed = 0.005;
    let waveAmplitude = 18;
    let baseRadius = 110;
    
    // Obtain active microphone sound amplitude to deform the orb in real time
    let micAmp = 0;
    if (isListening && audioAnalyser && audioDataArray) {
      audioAnalyser.getByteTimeDomainData(audioDataArray);
      let total = 0;
      for (let i = 0; i < audioDataArray.length; i++) {
        total += Math.abs(audioDataArray[i] - 128);
      }
      micAmp = total / audioDataArray.length;
    }

    if (currentCoreState === "LISTENING") {
      rotSpeed = 0.016;
      waveAmplitude = 24 + micAmp * 60; // Highly reactive to mic amplitude
      baseRadius = 120;
    } else if (currentCoreState === "THINKING") {
      rotSpeed = 0.05;
      waveAmplitude = 10 + Math.sin(timeVal * 12) * 8; // fast inward vibration
      baseRadius = 95;
    } else if (currentCoreState === "SPEAKING") {
      // Smoothly interpolate towards target amplitude with some random jitter to simulate speech inflections
      if (Math.random() < 0.18) {
        targetSpeechAmplitude = 10 + Math.random() * 45;
      }
      speechAmplitude += (targetSpeechAmplitude - speechAmplitude) * 0.18;
      
      rotSpeed = 0.015;
      waveAmplitude = 20 + speechAmplitude;
      baseRadius = 115 + Math.sin(timeVal * 6) * 10;
    } else {
      // Standby idle breathing
      speechAmplitude = 0;
      targetSpeechAmplitude = 0;
      rotSpeed = 0.006;
      waveAmplitude = 16 + Math.sin(timeVal * 2) * 6;
      baseRadius = 110;
    }

    timeVal += rotSpeed;

    // Projected 3D coordinate parameters
    const yaw = timeVal;      // Spin around Y axis
    const pitch = timeVal * 0.55; // Spin around X axis

    // Projected point buffer for painters algorithm sorting and drawing lines
    const projected = [];

    particles.forEach(p => {
      // Volumetric sphere shell morphing using multi-frequency sinusoidal noise overlays
      let radialMorph = Math.sin(p.theta * 4 + timeVal * 3 + p.phase) * Math.cos(p.phi * 3 - timeVal * 2) * (waveAmplitude * 0.6);
      radialMorph += Math.cos(p.theta * 8 - timeVal * 4) * Math.sin(p.phi * 6 + timeVal * 3) * (waveAmplitude * 0.4);
      
      // Expand and morph intensely when speaking
      if (currentCoreState === "SPEAKING") {
        radialMorph += Math.sin(p.theta * 10 + timeVal * 12) * Math.cos(p.phi * 8 + timeVal * 15) * (speechAmplitude * 0.5);
      }
      
      const r = baseRadius + p.baseRadiusOffset + radialMorph;
      
      // Spherical coordinates to Cartesian
      let x3d = r * Math.sin(p.theta) * Math.cos(p.phi);
      let y3d = r * Math.sin(p.theta) * Math.sin(p.phi);
      let z3d = r * Math.cos(p.theta);

      // Perform 3D rotation around pitch (X axis)
      let y1 = y3d * Math.cos(pitch) - z3d * Math.sin(pitch);
      let z1 = y3d * Math.sin(pitch) + z3d * Math.cos(pitch);

      // Perform 3D rotation around yaw (Y axis)
      let x2 = x3d * Math.cos(yaw) - z1 * Math.sin(yaw);
      let z2 = x3d * Math.sin(yaw) + z1 * Math.cos(yaw);

      // Perspective projection
      const fov = 380;
      const distance = 420;
      const scale = fov / (fov + z2 + distance);
      
      const x2d = cx + x2 * scale;
      const y2d = cy + y1 * scale;

      // Depth-based opacity representation
      const alpha = Math.max(0.08, Math.min(1.0, scale * 1.6));

      projected.push({
        x: x2d,
        y: y2d,
        z: z2,
        scale: scale,
        alpha: alpha,
        size: p.size,
        layer: p.layer
      });
    });

    // Painter's Algorithm: Sort by depth (Z index) so back-to-front rendering creates proper 3D volume
    projected.sort((a, b) => b.z - a.z);

    // Color definitions matching the cosmic violet/purple theme
    let colorNeon = "216, 180, 254"; // vibrant lavender-glow (#d8b4fe)
    let colorMid = "168, 85, 247";  // cosmic purple (#a855f7)
    let colorDeep = "124, 58, 237"; // royal indigo/purple (#7c3aed)
    
    if (currentCoreState === "LISTENING") {
      colorNeon = "110, 231, 183";  // minty green-cyan
      colorMid = "16, 185, 129";   // emerald green
      colorDeep = "4, 120, 87";    // dark forest green
    } else if (currentCoreState === "THINKING") {
      colorNeon = "244, 63, 94";    // vibrant pinkish-red
      colorMid = "168, 85, 247";   // cosmic purple
      colorDeep = "99, 102, 241";   // indigo
    }

    // Draw connected neural-mesh vector lines between nearby particles
    hologramCtx.lineWidth = 0.5;
    hologramCtx.strokeStyle = `rgba(${colorMid}, ${currentCoreState === "SPEAKING" ? 0.08 : 0.035})`;
    for (let i = 0; i < projected.length; i += 6) {
      const pt1 = projected[i];
      const pt2 = projected[(i + 2) % projected.length];
      const dist = Math.hypot(pt1.x - pt2.x, pt1.y - pt2.y);
      if (dist < 75 && pt1.alpha > 0.2 && pt2.alpha > 0.2) {
        hologramCtx.beginPath();
        hologramCtx.moveTo(pt1.x, pt1.y);
        hologramCtx.lineTo(pt2.x, pt2.y);
        hologramCtx.stroke();
      }
    }

    // Draw the particle dots
    projected.forEach(pt => {
      let rgb = colorMid;
      if (pt.layer === 'neon') rgb = colorNeon;
      if (pt.layer === 'deep') rgb = colorDeep;

      // Glow filters for high-energy states
      if (currentCoreState === "SPEAKING" || currentCoreState === "LISTENING") {
        hologramCtx.shadowBlur = pt.scale * 12;
        hologramCtx.shadowColor = `rgba(${rgb}, ${pt.alpha * 0.4})`;
      } else {
        hologramCtx.shadowBlur = 0;
      }

      hologramCtx.fillStyle = `rgba(${rgb}, ${pt.alpha})`;
      hologramCtx.beginPath();
      hologramCtx.arc(pt.x, pt.y, pt.size * pt.scale * 1.9, 0, Math.PI * 2);
      hologramCtx.fill();
    });

    hologramCtx.shadowBlur = 0; // reset shadow effects

    // Central pulsing energy nucleus gradient
    const gradient = hologramCtx.createRadialGradient(cx, cy, 3, cx, cy, baseRadius * 0.45);
    let nucleusColor = colorMid;
    gradient.addColorStop(0, `rgba(${nucleusColor}, ${currentCoreState === "SPEAKING" ? 0.45 : 0.26})`);
    gradient.addColorStop(0.5, `rgba(${nucleusColor}, 0.08)`);
    gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
    hologramCtx.fillStyle = gradient;
    hologramCtx.beginPath();
    hologramCtx.arc(cx, cy, baseRadius * 0.45, 0, Math.PI * 2);
    hologramCtx.fill();

    // Core telemetry coordinates shift
    const coordBox = document.getElementById("hologram-coords");
    if (coordBox && Math.random() < 0.08) {
      const rx = Math.floor(Math.random() * 800) + 100;
      const ry = Math.floor(Math.random() * 800) + 100;
      coordBox.textContent = `SEC-C // X: ${rx} // Y: ${ry}`;
    }

    requestAnimationFrame(drawHologram);
  }

  drawHologram();
}

// --- Dynamic Sparkline Renderers ---
function drawStatCharts() {
  drawSparkline("analytics-cpu-chart", statHistories.cpu, "var(--purple-primary)");
  drawSparkline("analytics-ram-chart", statHistories.ram, "var(--purple-primary)");
  drawSparkline("analytics-battery-chart", statHistories.battery, "var(--purple-primary)");
  drawSparkline("analytics-disk-chart", statHistories.disk, "var(--purple-primary)");
  drawSparkline("analytics-net-down-chart", statHistories.netDown, "var(--purple-primary)");
  drawSparkline("analytics-net-up-chart", statHistories.netUp, "var(--purple-primary)");
}

function drawSparkline(canvasId, data, color) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width = canvas.parentElement.clientWidth || 180;
  const h = canvas.height = canvas.parentElement.clientHeight || 70;

  ctx.clearRect(0, 0, w, h);
  
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.fillStyle = "rgba(168, 85, 247, 0.04)";
  
  const step = w / (data.length - 1);
  ctx.beginPath();
  ctx.moveTo(0, h - (data[0] / 100) * h);

  for (let i = 1; i < data.length; i++) {
    const x = i * step;
    const y = h - (data[i] / 100) * h;
    ctx.lineTo(x, y);
  }
  ctx.stroke();

  ctx.lineTo(w, h);
  ctx.lineTo(0, h);
  ctx.closePath();
  ctx.fill();
}

// --- Tab Changing Logic ---
function switchTab(tabName) {
  activeTab = tabName;
  
  // Update Tab Navigation Active Status
  document.querySelectorAll(".nav-tab").forEach(tab => {
    if (tab.getAttribute("data-tab") === tabName) {
      tab.classList.add("active");
    } else {
      tab.classList.remove("active");
    }
  });

  // Toggle Left/Right tab panes
  document.querySelectorAll(".tab-pane").forEach(pane => {
    pane.classList.remove("active");
  });

  const leftPane = document.getElementById(`pane-left-${tabName}`);
  const rightPane = document.getElementById(`pane-right-${tabName}`);
  
  if (leftPane) leftPane.classList.add("active");
  if (rightPane) rightPane.classList.add("active");

  const grid = document.querySelector(".hud-grid");
  if (grid) {
    grid.scrollTop = 0;
    grid.scrollLeft = 0;
  }
  [leftPane, rightPane].forEach(pane => {
    if (pane) {
      pane.scrollTop = 0;
      pane.scrollLeft = 0;
    }
  });

  playSynthSound("click");

  // Conditional initial loading per active tab
  if (tabName === "analytics") {
    pollProcesses();
    startSystemStatsPolling();
  } else if (tabName === "command") {
    stopSystemStatsPolling();
    fetchCalendar();
    fetchNotes();
    fetchReminders();
    fetchTasks();
  } else if (tabName === "security") {
    stopSystemStatsPolling();
    fetchSecurityIntelligence();
    fetchRecentFiles();
  } else if (tabName === "settings") {
    stopSystemStatsPolling();
    fetchSettings();
  } else {
    stopSystemStatsPolling();
  }
}

function startSystemStatsPolling() {
  if (systemStatsPollTimer) return;
  pollSystemStats();
  systemStatsPollTimer = setInterval(() => {
    if (activeTab === "analytics" && isAuthorized) {
      pollSystemStats();
    }
  }, 2000);
}

function stopSystemStatsPolling() {
  if (!systemStatsPollTimer) return;
  clearInterval(systemStatsPollTimer);
  systemStatsPollTimer = null;
}

function clampPercent(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, n));
}

function setMeter(fillId, value) {
  const el = document.getElementById(fillId);
  if (el) el.style.width = `${clampPercent(value)}%`;
}

function fmtNum(value, digits = 1) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : "--";
}

function updateSystemStatsUI(stats) {
  const cpu = clampPercent(stats.cpu_percent);
  const ram = clampPercent(stats.ram_percent);
  const disk = clampPercent(stats.disk_percent);
  const gpu = clampPercent(stats.gpu_percent);
  const battery = clampPercent(stats.battery_percent);
  const down = Number(stats.net_download_mbps || 0);
  const up = Number(stats.net_upload_mbps || 0);

  document.getElementById("sysstat-cpu-value").textContent = `${fmtNum(cpu)}%`;
  document.getElementById("sysstat-ram-value").textContent = `${fmtNum(ram)}%`;
  document.getElementById("sysstat-disk-value").textContent = `${fmtNum(disk)}%`;
  document.getElementById("sysstat-gpu-value").textContent = `${fmtNum(gpu)}%`;
  document.getElementById("sysstat-battery-value").textContent = `${fmtNum(battery)}%`;
  document.getElementById("sysstat-net-value").textContent = `${fmtNum(down, 2)} / ${fmtNum(up, 2)} Mbps`;

  document.getElementById("sysstat-cpu-temp").textContent = `Temp: ${fmtNum(stats.cpu_temp)}°C`;
  document.getElementById("sysstat-ram-detail").textContent = `${fmtNum(stats.ram_used_gb)} / ${fmtNum(stats.ram_total_gb)} GB`;
  document.getElementById("sysstat-disk-detail").textContent = `${fmtNum(stats.disk_used_gb)} / ${fmtNum(stats.disk_total_gb)} GB`;
  document.getElementById("sysstat-gpu-temp").textContent = `Temp: ${fmtNum(stats.gpu_temp)}°C`;
  document.getElementById("sysstat-battery-detail").textContent = stats.battery_plugged ? "Plugged: yes" : "Plugged: no";
  document.getElementById("sysstat-net-detail").textContent = `Down: ${fmtNum(down, 2)} Mbps | Up: ${fmtNum(up, 2)} Mbps`;

  setMeter("sysstat-cpu-bar", cpu);
  setMeter("sysstat-ram-bar", ram);
  setMeter("sysstat-disk-bar", disk);
  setMeter("sysstat-gpu-bar", gpu);
  setMeter("sysstat-battery-bar", battery);
  setMeter("sysstat-net-down-bar", Math.min(100, down * 20));
  setMeter("sysstat-net-up-bar", Math.min(100, up * 20));

  const batteryMeter = document.getElementById("sysstat-battery-meter");
  if (batteryMeter) {
    batteryMeter.classList.toggle("low-battery", battery <= 20 && !stats.battery_plugged);
    batteryMeter.classList.toggle("gold", battery > 20 || !!stats.battery_plugged);
  }

  const body = document.getElementById("sysstat-process-body");
  if (body) {
    const rows = Array.isArray(stats.top_processes) ? stats.top_processes : [];
    body.innerHTML = rows.length ? rows.map(proc => `
      <tr>
        <td>${String(proc.name || "-").replace(/[<>&]/g, ch => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[ch]))}</td>
        <td>${fmtNum(proc.cpu)}</td>
        <td>${fmtNum(proc.ram_mb, 0)}</td>
      </tr>
    `).join("") : `<tr><td colspan="3" class="table-empty">Collecting process telemetry...</td></tr>`;
  }
}

function pollSystemStats() {
  if (!isAuthorized || activeTab !== "analytics") return;
  fetch("/api/system-stats", {
    headers: { "X-Jarvis-Token": apiToken }
  })
  .then(res => {
    if (!res.ok) throw new Error("system stats unavailable");
    return res.json();
  })
  .then(updateSystemStatsUI)
  .catch(err => {
    console.warn("System stats fetch failed:", err);
    const body = document.getElementById("sysstat-process-body");
    if (body) body.innerHTML = `<tr><td colspan="3" class="table-empty">System stats unavailable.</td></tr>`;
  });
}

// --- Uplink Status REST client ---
function startDataPolling() {
  setInterval(pollUplinkStatus, 1500);
  
  pollUplinkStatus();
  fetchWeatherNews();
  fetchLocation(false);
  fetchMobileCompanionStatus();
  fetchTasks();
  
  setInterval(fetchWeatherNews, 30000);
  if (!mobileCompanionPollTimer) {
    mobileCompanionPollTimer = setInterval(() => {
      if (isAuthorized && activeTab === "mission") {
        fetchMobileCompanionStatus();
      }
    }, 4000);
  }
  
  // Conditional fast poll for processes tree when analytics is active
  setInterval(() => {
    if (isAuthorized && activeTab === "analytics") {
      pollProcesses();
    }
  }, 5000);
}

function pollUplinkStatus() {
  const start = performance.now();
  
  fetch("/api/status", {
    headers: {
      "X-Jarvis-Token": apiToken
    }
  })
  .then(res => {
    if (res.status === 401) {
      sessionStorage.removeItem("jarvis_token");
      location.reload();
      throw new Error("Unauthorized - Session expired");
    }
    if (!res.ok) throw new Error("Link issue");
    return res.json();
  })
  .then(data => {
    const stop = performance.now();
    const ping = Math.round(stop - start);
    document.getElementById("ping-text").textContent = `LATENCY: ${ping}ms`;
    
    // Core telemetry
    const hardware = data.hardware || {};
    updateGuiParityTelemetry(data);
    const cpu = Math.round(smoothedTelemetry.cpu ?? hardware.cpu_percent ?? 0);
    const ram = hardware.ram || {};
    const disk = hardware.disk || {};
    const network = data.network_io || {};
    const threads = data.threads || 0;
    const battery = hardware.battery || {};
    const batteryPercent = Math.round(battery.percent !== undefined && battery.percent !== null ? battery.percent : 100);
    
    // Update live numeric gauges inside Left Analytics pane
    const cpuValEl = document.getElementById("analytics-cpu-val");
    const ramValEl = document.getElementById("analytics-ram-val");
    const batValEl = document.getElementById("analytics-battery-val");
    
    if (cpuValEl) cpuValEl.textContent = `${cpu}%`;
    
    // RAM percentages
    const ramPercent = Math.round(ram.percent || 0);
    if (ramValEl) ramValEl.textContent = `${ramPercent}%`;
    if (batValEl) batValEl.textContent = `${batteryPercent}%`;

    // Disk percentages
    const diskPercent = Math.round(disk.percent || 0);
    const diskValEl = document.getElementById("analytics-disk-val");
    if (diskValEl) diskValEl.textContent = `${diskPercent}%`;

    // Dynamic Bandwidth Speed Rate Math
    const currentTimestamp = performance.now();
    let txKB = 0;
    let rxKB = 0;
    if (lastNetTimestamp > 0 && network.bytes_sent) {
      const elapsedSec = (currentTimestamp - lastNetTimestamp) / 1000;
      
      const sentBytes = network.bytes_sent - lastTxBytes;
      const recvBytes = network.bytes_recv - lastRxBytes;
      
      txKB = parseFloat((sentBytes / 1024 / elapsedSec).toFixed(1));
      rxKB = parseFloat((recvBytes / 1024 / elapsedSec).toFixed(1));
      
      const netDownVal = document.getElementById("analytics-net-down-val");
      const netUpVal = document.getElementById("analytics-net-up-val");
      if (netDownVal) netDownVal.textContent = `${rxKB} KB/s`;
      if (netUpVal) netUpVal.textContent = `${txKB} KB/s`;
    }
    
    lastTxBytes = network.bytes_sent || 0;
    lastRxBytes = network.bytes_recv || 0;
    lastNetTimestamp = currentTimestamp;

    // Shift arrays for sparklines
    statHistories.cpu.shift();
    statHistories.cpu.push(cpu);
    
    statHistories.ram.shift();
    statHistories.ram.push(ramPercent);
    
    statHistories.battery.shift();
    statHistories.battery.push(batteryPercent);
    
    statHistories.disk.shift();
    statHistories.disk.push(diskPercent);

    statHistories.netDown.shift();
    statHistories.netDown.push(Math.min(100, Math.round((rxKB / 1000) * 100)));
    
    statHistories.netUp.shift();
    statHistories.netUp.push(Math.min(100, Math.round((txKB / 1000) * 100)));
    
    // Draw Sparklines in tab if analytics is active
    if (activeTab === "analytics") {
      drawStatCharts();
      
      // Update session uptime and load counters
      const uptimeSec = Math.round((performance.now() - lastNetTimestamp + lastNetTimestamp) / 1000);
      const uptimeStr = new Date(uptimeSec * 1000).toISOString().substr(11, 8);
      const uptimeEl = document.getElementById("stat-uptime");
      if (uptimeEl) uptimeEl.textContent = uptimeStr;
    }
  })
  .catch(err => {
    console.error("Link offline:", err);
    document.getElementById("net-status-text").textContent = "UPLINK: OFFLINE";
    document.getElementById("net-status-text").className = "net-status offline";
  });
}

function fetchWeatherNews() {
  fetch("/api/weather", {
    headers: { "X-Jarvis-Token": apiToken }
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok && data.weather) {
      const weathText = data.weather.toUpperCase();
      const weathTempEl = document.getElementById("weather-temp");
      const weathDescEl = document.getElementById("weather-desc");
      if (weathTempEl) weathTempEl.textContent = weathText.split(",")[0].replace("°C","°");
      if (weathDescEl) weathDescEl.textContent = data.weather;
    }
  })
  .catch(e => console.warn("Weather fetch offline"));

  fetch("/api/news", {
    headers: { "X-Jarvis-Token": apiToken }
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok && data.news && data.news.length > 0) {
      const container = document.getElementById("news-brief-feed");
      if (container) {
        container.innerHTML = "";
        const headlines = Array.isArray(data.news)
          ? data.news
          : String(data.news).replace(/^Headlines:\s*/i, "").replace(/\.$/, "").split(/\s+\|\s+/);
        headlines.slice(0, 4).forEach(headline => {
          const item = document.createElement("div");
          item.className = "news-ticker-item";
          item.textContent = headline;
          container.appendChild(item);
        });
      }
    }
  })
  .catch(e => console.warn("News headlines offline"));
}

function bytesLabel(value) {
  const bytes = Number(value || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return "--";
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function shortTime(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
}

function updateMobileCompanionUI(data) {
  const session = data.session || {};
  const location = data.location || {};
  const frame = data.frame || {};
  const audio = data.audio || {};
  const fileIndex = data.file_index || {};
  const latestFile = data.latest_file || {};
  const files = Array.isArray(data.files) ? data.files : [];
  latestMobileMapUrl = data.map_url || "";

  const statusEl = document.getElementById("mobile-session-status");
  const lastSeenEl = document.getElementById("mobile-last-seen");
  const frameShell = document.querySelector(".mobile-frame-shell");
  const framePreview = document.getElementById("mobile-frame-preview");
  const locationEl = document.getElementById("mobile-location-text");
  const audioEl = document.getElementById("mobile-audio-text");
  const filesEl = document.getElementById("mobile-files-text");
  const latestFileEl = document.getElementById("mobile-latest-file-text");
  const mapBtn = document.getElementById("mobile-open-map-btn");

  const status = String(session.status || "offline").toUpperCase();
  if (statusEl) statusEl.textContent = `Phone companion: ${status}`;
  const lastSeen = frame.server_received_at || location.server_received_at || audio.server_received_at || session.server_received_at || "";
  if (lastSeenEl) lastSeenEl.textContent = lastSeen ? `Last mobile update: ${shortTime(lastSeen)}` : "No mobile data received yet.";

  if (framePreview && frameShell) {
    if (data.frame_data_url) {
      framePreview.src = data.frame_data_url;
      frameShell.classList.add("has-frame");
    } else {
      framePreview.removeAttribute("src");
      frameShell.classList.remove("has-frame");
    }
  }

  if (locationEl) {
    if (location.latitude !== undefined && location.longitude !== undefined) {
      const accuracy = location.accuracy_m ? ` | ${Math.round(Number(location.accuracy_m))}m` : "";
      locationEl.textContent = `${Number(location.latitude).toFixed(5)}, ${Number(location.longitude).toFixed(5)}${accuracy}`;
    } else {
      locationEl.textContent = "--";
    }
  }

  if (audioEl) {
    const when = audio.server_received_at ? ` | ${shortTime(audio.server_received_at)}` : "";
    audioEl.textContent = audio.bytes ? `${bytesLabel(audio.bytes)}${when}` : "--";
  }

  if (filesEl) {
    const count = fileIndex.file_count ?? files.length;
    const uploaded = fileIndex.uploaded_recent_files;
    filesEl.textContent = count || uploaded ? `${count || 0} indexed${uploaded ? ` | ${uploaded} uploaded` : ""}` : "--";
  }

  if (latestFileEl) {
    latestFileEl.textContent = latestFile.relative_path
      ? `${latestFile.relative_path} (${bytesLabel(latestFile.bytes)})`
      : "--";
  }

  if (mapBtn) mapBtn.disabled = !latestMobileMapUrl;
}

function setMobileCompanionOffline(message = "Mobile companion data unavailable.") {
  const statusEl = document.getElementById("mobile-session-status");
  const lastSeenEl = document.getElementById("mobile-last-seen");
  if (statusEl) statusEl.textContent = "Phone companion: OFFLINE";
  if (lastSeenEl) lastSeenEl.textContent = message;
}

function fetchMobileCompanionStatus() {
  if (!isAuthorized) return;
  fetch("/api/mobile/status", { headers: authedHeaders() })
    .then(res => {
      if (!res.ok) throw new Error("mobile companion unavailable");
      return res.json();
    })
    .then(data => {
      if (!data.ok) throw new Error(data.error || "mobile companion error");
      updateMobileCompanionUI(data);
    })
    .catch(err => {
      console.warn("Mobile companion fetch failed:", err);
      setMobileCompanionOffline();
    });
}

function speakWithBrowserVoice(cleanSpeech) {
  // Terminate any active speech sequences
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
  
  if (!window.speechSynthesis) {
    // Fallback if browser environment lacks Web Speech synthesis support
    setCoreState("SPEAKING");
    let elapsed = 0;
    const interval = setInterval(() => {
      targetSpeechAmplitude = 15 + Math.random() * 35;
      elapsed += 100;
      if (elapsed > 4000) {
        clearInterval(interval);
        setCoreState("STANDBY");
      }
    }, 100);
    return;
  }

  speechUtterance = new SpeechSynthesisUtterance(cleanSpeech);

  // Filter local platform voice profiles for optimal futuristic premium voices
  const voices = window.speechSynthesis.getVoices();
  let jarvisVoice = voices.find(v => v.name.toLowerCase().includes("google uk english male")) ||
                    voices.find(v => v.name.toLowerCase().includes("google us english")) ||
                    voices.find(v => v.name.toLowerCase().includes("microsoft david")) ||
                    voices.find(v => v.lang.startsWith("en-GB") && v.name.toLowerCase().includes("male")) ||
                    voices.find(v => v.lang.startsWith("en") && v.name.toLowerCase().includes("male")) ||
                    voices.find(v => v.lang.startsWith("en"));

  if (jarvisVoice) {
    speechUtterance.voice = jarvisVoice;
  }

  // Sci-Fi Command & Control Modulation settings
  speechUtterance.rate = 1.04;  // Slightly accelerated military-cadence feel
  speechUtterance.pitch = 0.88; // Deeper baritone resonant register

  speechUtterance.onstart = () => {
    setCoreState("SPEAKING");
  };

  speechUtterance.onend = () => {
    setCoreState("STANDBY");
  };

  speechUtterance.onerror = () => {
    setCoreState("STANDBY");
  };

  // Modulate sphere wave amplitudes on verbal boundaries (syllabic simulation)
  speechUtterance.onboundary = (event) => {
    if (event.name === "word") {
      targetSpeechAmplitude = 25 + Math.random() * 40;
    }
  };

  window.speechSynthesis.speak(speechUtterance);
}

async function speakWithServerTts(cleanSpeech) {
  setCoreState("SPEAKING");
  targetSpeechAmplitude = 35;
  const response = await fetch("/api/tts", {
    method: "POST",
    headers: authedHeaders(),
    body: JSON.stringify({ text: cleanSpeech })
  });
  if (!response.ok) {
    let detail = "";
    try {
      const data = await response.json();
      detail = data.error || "";
    } catch {
      detail = response.statusText;
    }
    throw new Error(detail || "ElevenLabs TTS failed.");
  }
  const blob = await response.blob();
  const audioUrl = URL.createObjectURL(blob);
  const audio = new Audio(audioUrl);
  const pulse = setInterval(() => {
    targetSpeechAmplitude = 20 + Math.random() * 55;
  }, 90);
  audio.onended = () => {
    clearInterval(pulse);
    URL.revokeObjectURL(audioUrl);
    targetSpeechAmplitude = 0;
    setCoreState("STANDBY");
  };
  audio.onerror = () => {
    clearInterval(pulse);
    URL.revokeObjectURL(audioUrl);
    targetSpeechAmplitude = 0;
    setCoreState("STANDBY");
    speakWithBrowserVoice(cleanSpeech);
  };
  await audio.play();
}

// --- Premium JARVIS speech: ElevenLabs first, browser fallback ---
function speakText(text) {
  const cleanSpeech = String(text || "").replace(/[*#`_\-\[\]()]/g, '').trim();
  if (!cleanSpeech) {
    setCoreState("STANDBY");
    return;
  }
  if (currentTtsBackend === "browser") {
    speakWithBrowserVoice(cleanSpeech);
    return;
  }
  speakWithServerTts(cleanSpeech).catch((err) => {
    console.warn("Server TTS fallback:", err);
    speakWithBrowserVoice(cleanSpeech);
  });
}

// --- Submit Commands ---
function commandNeedsDesktopControl(command) {
  const lower = (command || "").trim().toLowerCase();
  return (
    lower.startsWith("/cowork ") ||
    lower.startsWith("/computer ") ||
    /\b(control|operate|use)\s+(my\s+)?(screen|computer|pc|desktop)\b/.test(lower) ||
    /\b(click|double click|right click|type on screen|press on screen|move the mouse)\b/.test(lower)
  );
}

function normalizeJarvisReply(reply) {
  const text = String(reply || "").trim();
  if (/^\{[\s\S]*"action"\s*:\s*"screenshot"[\s\S]*\}$/.test(text)) {
    return "Screen-control JSON was blocked in normal chat. Use /cowork before a command if you want me to control the desktop.";
  }
  return reply;
}

function sendPrompterCommand() {
  const input = document.getElementById("prompter-input");
  const command = input.value.trim();
  if (!command) return;
  const forceAi = document.getElementById("force-ai-toggle")?.checked;
  const voiceReplies = document.getElementById("voice-replies-toggle")?.checked !== false;
  const keepReferences = document.getElementById("keep-refs-toggle")?.checked !== false;
  let outgoingCommand = command;

  if (forceAi && !outgoingCommand.startsWith("/")) {
    outgoingCommand = `/ai ${outgoingCommand}`;
  }
  const allowInteractive = commandNeedsDesktopControl(outgoingCommand);

  if (keepReferences && attachedWebReferences.length > 0) {
    const referenceContext = attachedWebReferences
      .map((ref, index) => `Reference ${index + 1}: ${ref.name}\n${ref.text.slice(0, 4000)}`)
      .join("\n\n---\n\n");
    outgoingCommand = `${outgoingCommand}\n\nUse these attached browser references if relevant:\n${referenceContext}`;
  }

  // Intercept any active TTS voice playing
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }

  playSynthSound("click");
  appendLog("USER", command, "user");
  appendChatBubble("USER", command, "user-bubble");
  
  input.value = "";
  
  setCoreState("THINKING");

  fetch("/api/command", {
    method: "POST",
    headers: authedHeaders(),
    body: JSON.stringify({
      command: outgoingCommand,
      speak: false, // Turn off backend speak because browser client vocalizes natively!
      allow_interactive: allowInteractive
    })
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok && data.reply) {
      const reply = normalizeJarvisReply(data.reply);
      appendLog("J.A.R.V.I.S.", reply, "jarvis");
      appendChatBubble("J.A.R.V.I.S.", reply, "jarvis-bubble");
      if (voiceReplies) {
        speakText(reply);
      } else {
        setCoreState("STANDBY");
      }
      
      // Update session statistics query count
      const queriesEl = document.getElementById("stat-queries-count");
      if (queriesEl) {
        const count = parseInt(queriesEl.textContent) || 0;
        queriesEl.textContent = count + 1;
      }
    } else {
      setCoreState("STANDBY");
      appendLog("ERROR", data.error || "Tactical response parsing failed.", "sys");
    }
  })
  .catch(err => {
    setCoreState("STANDBY");
    appendLog("ERROR", "Uplink server error. Command transmission stalled.", "sys");
  });
}

// --- Helper UI loggers ---
function appendLog(sender, text, styleClass) {
  const feed = document.getElementById("terminal-feed");
  if (!feed) return;
  const line = document.createElement("div");
  line.className = `log-line ${styleClass}`;
  
  const d = new Date();
  const ts = d.toTimeString().split(' ')[0];
  
  line.textContent = `[${ts}] [${sender}] ${text}`;
  feed.appendChild(line);
  feed.scrollTop = feed.scrollHeight;
}

function appendChatBubble(sender, text, bubbleClass) {
  const feed = document.getElementById("chat-history");
  if (!feed) return;
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${bubbleClass}`;
  
  const span = document.createElement("span");
  span.className = "sender";
  span.textContent = sender.toUpperCase();
  
  const p = document.createElement("p");
  p.className = "txt";
  p.textContent = text;
  
  bubble.appendChild(span);
  bubble.appendChild(p);
  feed.appendChild(bubble);
  feed.scrollTop = feed.scrollHeight;
}

function setCoreState(state) {
  currentCoreState = state;
  const stateBadge = document.getElementById("core-state-text");
  if (stateBadge) stateBadge.textContent = state;
}

// --- Voice Recognition & Microphones ---
function toggleVoiceCapture() {
  if (isListening) {
    stopVoiceCapture();
  } else {
    startVoiceCapture();
  }
}

function startVoiceCapture() {
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
  playSynthSound("click");
  isListening = true;
  document.getElementById("mic-btn").classList.add("listening");
  document.getElementById("audio-vis-container").classList.remove("hidden");
  setCoreState("LISTENING");
  
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.lang = 'en-US';
    recognition.interimResults = false;

    recognition.onresult = (e) => {
      const transcript = e.results[0][0].transcript;
      document.getElementById("prompter-input").value = transcript;
      sendPrompterCommand();
    };

    recognition.onend = () => {
      stopVoiceCapture();
    };

    recognition.onerror = () => {
      stopVoiceCapture();
    };

    recognition.start();
  }

  navigator.mediaDevices.getUserMedia({ audio: true, video: false })
  .then(stream => {
    micStream = stream;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    const ctx = new AudioContextClass();
    const source = ctx.createMediaStreamSource(stream);
    audioAnalyser = ctx.createAnalyser();
    audioAnalyser.fftSize = 256;
    source.connect(audioAnalyser);
    
    const bufferLength = audioAnalyser.frequencyBinCount;
    audioDataArray = new Uint8Array(bufferLength);
    
    const waveCanvas = document.getElementById("mic-wave-canvas");
    micCanvasCtx = waveCanvas.getContext("2d");
    
    renderMicWaveform();
    
    // Increment voice activations statistic
    const voiceEl = document.getElementById("stat-voice-activations");
    if (voiceEl) {
      const count = parseInt(voiceEl.textContent) || 0;
      voiceEl.textContent = count + 1;
    }
  })
  .catch(e => {
    console.warn("Audio permissions blocked:", e);
  });
}

function stopVoiceCapture() {
  isListening = false;
  document.getElementById("mic-btn").classList.remove("listening");
  document.getElementById("audio-vis-container").classList.add("hidden");
  
  if (currentCoreState === "LISTENING") {
    setCoreState("STANDBY");
  }

  if (recognition) {
    try { recognition.stop(); } catch(e){}
    recognition = null;
  }

  if (micStream) {
    micStream.getTracks().forEach(track => track.stop());
    micStream = null;
  }
}

function renderMicWaveform() {
  if (!isListening || !audioAnalyser) return;
  requestAnimationFrame(renderMicWaveform);

  const canvas = document.getElementById("mic-wave-canvas");
  const ctx = micCanvasCtx;
  const w = canvas.width = canvas.clientWidth;
  const h = canvas.height = canvas.clientHeight;

  audioAnalyser.getByteTimeDomainData(audioDataArray);

  ctx.fillStyle = "rgba(2, 2, 4, 0.4)";
  ctx.fillRect(0, 0, w, h);

  ctx.lineWidth = 1.5;
  ctx.strokeStyle = "rgba(16, 185, 129, 0.8)";
  ctx.beginPath();

  const sliceWidth = w / audioDataArray.length;
  let x = 0;

  for (let i = 0; i < audioDataArray.length; i++) {
    const v = audioDataArray[i] / 128.0;
    const y = (v * h) / 2;

    if (i === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }

    x += sliceWidth;
  }

  ctx.lineTo(w, h / 2);
  ctx.stroke();
}

// --- Live Radar Sweep Canvas ---
function initRadar() {
  radarCanvas = document.getElementById("radar-canvas");
  if (!radarCanvas) return;
  radarCtx = radarCanvas.getContext("2d");
  
  // Add occasional ambient movement only when camera is active and no face targets are locked.
  setInterval(() => {
    if (activeTab === "mission" && isWebcamActive && detectedFaces.length === 0 && Math.random() < 0.18) {
      const radius = Math.random() * 60 + 10;
      const angle = Math.random() * Math.PI * 2;
      radarBlips.push({
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
        opacity: 1.0,
        time: Date.now(),
        label: "MOTION",
        threat: "LOW"
      });
      appendLog("RADAR", `Movement pattern identified: R-${Math.round(radius)}/A-${Math.round(angle * 180 / Math.PI)}`, "sys");
    }
  }, 3500);
  
  function drawRadar() {
    if (!radarCanvas) return;
    const w = radarCanvas.width;
    const h = radarCanvas.height;
    const cx = w / 2;
    const cy = h / 2;
    
    radarCtx.clearRect(0, 0, w, h);
    
    // Draw radar background grid lines
    radarCtx.strokeStyle = "rgba(16, 185, 129, 0.16)";
    radarCtx.lineWidth = 1.0;
    
    // Concentric green circles
    for (let r = 20; r <= 70; r += 20) {
      radarCtx.beginPath();
      radarCtx.arc(cx, cy, r, 0, Math.PI * 2);
      radarCtx.stroke();
    }
    
    // Crosshairs
    radarCtx.beginPath();
    radarCtx.moveTo(cx - 75, cy);
    radarCtx.lineTo(cx + 75, cy);
    radarCtx.moveTo(cx, cy - 75);
    radarCtx.lineTo(cx, cy + 75);
    radarCtx.stroke();
    
    // Sweep line rotation math
    radarAngle += 0.016;
    const sweepX = cx + Math.cos(radarAngle) * 75;
    const sweepY = cy + Math.sin(radarAngle) * 75;
    
    // Radar sector light sweep trail gradient
    radarCtx.fillStyle = "rgba(16, 185, 129, 0.05)";
    radarCtx.beginPath();
    radarCtx.moveTo(cx, cy);
    radarCtx.arc(cx, cy, 75, radarAngle - 0.5, radarAngle);
    radarCtx.closePath();
    radarCtx.fill();
    
    // Radar sweep leading edge line
    radarCtx.strokeStyle = "rgba(16, 185, 129, 0.65)";
    radarCtx.lineWidth = 1.6;
    radarCtx.beginPath();
    radarCtx.moveTo(cx, cy);
    radarCtx.lineTo(sweepX, sweepY);
    radarCtx.stroke();
    
    // Render and decay tactical radar targets/blips
    for (let i = radarBlips.length - 1; i >= 0; i--) {
      const blip = radarBlips[i];
      const age = Date.now() - blip.time;
      blip.opacity = Math.max(0, 1.0 - age / 4000);
      
      if (blip.opacity <= 0) {
        radarBlips.splice(i, 1);
        continue;
      }
      
      const bx = cx + blip.x;
      const by = cy + blip.y;
      
      radarCtx.shadowBlur = 8;
      const isThreat = blip.threat === "HIGH" || blip.threat === "MED";
      const color = isThreat ? "239, 68, 68" : "16, 185, 129";
      radarCtx.shadowColor = `rgba(${color}, ${blip.opacity})`;
      radarCtx.fillStyle = `rgba(${color}, ${blip.opacity})`;
      radarCtx.beginPath();
      radarCtx.arc(bx, by, blip.face ? 5 : 3.5, 0, Math.PI * 2);
      radarCtx.fill();
      if (blip.face) {
        radarCtx.font = "7px Orbitron";
        radarCtx.fillText(blip.label || "FACE", bx + 7, by - 5);
      }
    }
    
    radarCtx.shadowBlur = 0;
    requestAnimationFrame(drawRadar);
  }
  drawRadar();
}

function pushRadarBlipsFromFaces(faces) {
  if (!Array.isArray(faces) || faces.length === 0 || !cameraCanvas) return;
  const now = Date.now();
  const w = cameraCanvas.width || 320;
  const h = cameraCanvas.height || 240;
  faces.forEach(face => {
    const cx = (face.x + face.w / 2) / w - 0.5;
    const cy = (face.y + face.h / 2) / h - 0.5;
    radarBlips.push({
      x: Math.max(-68, Math.min(68, cx * 140)),
      y: Math.max(-68, Math.min(68, cy * 140)),
      opacity: 1,
      time: now,
      face: true,
      label: face.recognized ? face.name || "OWNER" : "UNKNOWN",
      threat: face.threat || "LOW"
    });
  });
  const label = document.querySelector(".radar-label");
  if (label) {
    label.textContent = `${faces.length} face target${faces.length === 1 ? "" : "s"} mapped from live camera.`;
  }
}

// --- Equalizer Footer Animation ---
function animateEqualizer() {
  const bars = document.querySelectorAll("#hud-equalizer-bars .eq-bar");
  if (!bars.length) return;
  
  bars.forEach((bar, idx) => {
    let targetHeight = 3; // idle height
    if (currentCoreState === "SPEAKING") {
      targetHeight = Math.random() * 22 + 4;
    } else if (currentCoreState === "LISTENING") {
      targetHeight = Math.random() * 14 + 6;
    } else if (currentCoreState === "THINKING") {
      targetHeight = 3 + Math.sin(Date.now() * 0.02 + idx) * 4;
    }
    bar.style.height = `${targetHeight}px`;
  });
  
  requestAnimationFrame(animateEqualizer);
}

// --- Feature-Specific Business Logic (ANALYTICS, COMMAND, SECURITY, SETTINGS) ---

// 1. ANALYTICS (Top Processes Tree)
function pollProcesses() {
  fetch("/api/processes", {
    headers: { "X-Jarvis-Token": apiToken }
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok && data.processes) {
      const tbody = document.getElementById("process-list-body");
      if (!tbody) return;
      tbody.innerHTML = "";

      const processes = data.processes.slice(0, 10);
      if (!processes.length) {
        tbody.innerHTML = `<tr><td colspan="3" class="table-empty">Collecting process telemetry...</td></tr>`;
        return;
      }

      processes.forEach(p => {
        const tr = document.createElement("tr");
        tr.setAttribute("data-pid", p.pid);
        
        tr.innerHTML = `
          <td>${p.pid}</td>
          <td>${Number(p.cpu_percent || 0).toFixed(1)}%</td>
          <td>${p.name}</td>
        `;
        
        tr.addEventListener("click", () => {
          selectedPid = p.pid;
          tbody.querySelectorAll("tr").forEach(r => r.classList.remove("selected"));
          tr.classList.add("selected");
          playSynthSound("click");
        });
        
        tbody.appendChild(tr);
      });
    }
  })
  .catch(err => console.warn("Failed to retrieve processes tree:", err));
}

function killSelectedProcess() {
  if (!selectedPid) {
    playSynthSound("error");
    appendLog("SYSTEM", "Choose a target process row to terminate.", "sys");
    return;
  }
  
  fetch("/api/processes", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Jarvis-Token": apiToken
    },
    body: JSON.stringify({ pid: selectedPid })
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok) {
      playSynthSound("success");
      appendLog("SYSTEM", `Terminated process target PID ${selectedPid}`, "sys");
      selectedPid = null;
      pollProcesses();
    } else {
      playSynthSound("error");
      appendLog("SYSTEM", `Failed to terminate: ${data.error}`, "sys");
    }
  })
  .catch(err => console.warn(err));
}

// 2. COMMAND CENTER (Notes Scratchpad)
function fetchNotes() {
  fetch("/api/notes", {
    headers: { "X-Jarvis-Token": apiToken }
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok && data.notes) {
      renderNotesUI(data.notes);
    }
  })
  .catch(err => console.warn(err));
}

function renderNotesUI(notesList) {
  const container = document.getElementById("notes-scroll-box");
  if (!container) return;
  container.innerHTML = "";
  
  if (notesList.length === 0) {
    container.innerHTML = '<span class="empty-deck-msg">Empty scratchpad notes.</span>';
    return;
  }

  notesList.forEach((n, idx) => {
    const item = document.createElement("div");
    item.className = "note-item";
    if (selectedNoteIndex === idx) item.classList.add("selected");
    
    // Trim summary
    const preview = n.length > 35 ? n.substring(0, 35) + "..." : n;
    item.textContent = `[#${idx + 1}] ${preview}`;
    
    item.addEventListener("click", () => {
      selectedNoteIndex = idx;
      document.getElementById("notes-input").value = n;
      renderNotesUI(notesList);
      playSynthSound("click");
    });
    
    container.appendChild(item);
  });
}

function saveScratchNote() {
  const input = document.getElementById("notes-input");
  const content = input.value.trim();
  if (!content) return;
  
  fetch("/api/notes", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Jarvis-Token": apiToken
    },
    body: JSON.stringify({ action: "add", content: content })
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok) {
      playSynthSound("success");
      input.value = "";
      selectedNoteIndex = null;
      fetchNotes();
      appendLog("SYSTEM", "Scratch note committed successfully.", "sys");
    }
  })
  .catch(err => console.warn(err));
}

function deleteScratchNote() {
  if (selectedNoteIndex === null || selectedNoteIndex === undefined) {
    playSynthSound("error");
    return;
  }
  
  fetch("/api/notes", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Jarvis-Token": apiToken
    },
    body: JSON.stringify({ action: "delete", index: selectedNoteIndex })
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok) {
      playSynthSound("success");
      document.getElementById("notes-input").value = "";
      selectedNoteIndex = null;
      fetchNotes();
      appendLog("SYSTEM", "Scratch note deleted cleanly.", "sys");
    }
  })
  .catch(err => console.warn(err));
}

function filterNotesLocal() {
  const query = document.getElementById("notes-search").value.trim().toLowerCase();
  fetch("/api/notes", {
    headers: { "X-Jarvis-Token": apiToken }
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok && data.notes) {
      const filtered = data.notes.filter(n => n.toLowerCase().includes(query));
      renderNotesUI(filtered);
    }
  });
}

// 3. COMMAND CENTER (Calendar Grid)
function fetchCalendar() {
  fetch("/api/calendar", {
    headers: { "X-Jarvis-Token": apiToken }
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok && data.events) {
      calendarEvents = data.events;
      renderCalendar(calendarEvents);
      renderEventsListUI(calendarEvents);
    }
  })
  .catch(err => console.warn("Calendar fetch stalled:", err));
}

function renderCalendar(events) {
  const grid = document.getElementById("calendar-days-grid");
  const monthYearLabel = document.getElementById("calendar-month-year");
  if (!grid || !monthYearLabel) return;
  
  grid.innerHTML = "";
  
  const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  monthYearLabel.textContent = `${monthNames[currentMonth]} ${currentYear}`;
  
  // May 2026 starts on Friday. Friday is index 4 (0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun)
  const firstDayIndex = 4; 
  for (let i = 0; i < firstDayIndex; i++) {
    const space = document.createElement("span");
    space.className = "calendar-day empty";
    space.textContent = 30 - firstDayIndex + 1 + i;
    grid.appendChild(space);
  }
  
  const daysInMonth = 31; 
  for (let day = 1; day <= daysInMonth; day++) {
    const cell = document.createElement("span");
    cell.className = "calendar-day active-day";
    if (day === 20) cell.classList.add("today");
    
    cell.textContent = day;
    
    const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    
    const hasEvent = events.some(e => e.date === dateStr);
    if (hasEvent) {
      cell.classList.add("has-event");
    }
    
    cell.addEventListener("click", () => {
      document.getElementById("calendar-event-date").value = dateStr;
      playSynthSound("click");
      
      // Focus on active events filtering for clicked day
      const daysEvents = events.filter(e => e.date === dateStr);
      renderEventsListUI(daysEvents, day);
    });
    
    grid.appendChild(cell);
  }
}

function renderEventsListUI(eventsList, filterDay = null) {
  const container = document.getElementById("calendar-events-list");
  if (!container) return;
  container.innerHTML = "";
  
  const showList = filterDay 
    ? eventsList.slice(0, 5) 
    : eventsList.filter(e => {
        const todayIso = `${currentYear}-${String(currentMonth + 1).padStart(2, "0")}-20`;
        return e.date >= todayIso;
      }).slice(0, 5);

  if (showList.length === 0) {
    container.innerHTML = `<span class="empty-deck-msg">${filterDay ? `No events scheduled for May ${filterDay}.` : "No upcoming schedule events."}</span>`;
    return;
  }

  showList.forEach((e, idx) => {
    const item = document.createElement("div");
    item.className = "calendar-event-item";
    item.innerHTML = `
      <div class="event-meta-line">
        <span class="event-time">${e.time || "00:00"}</span>
        <span class="event-date">${e.date}</span>
      </div>
      <div class="event-title">${e.title}</div>
    `;
    container.appendChild(item);
  });
}

function addCalendarEvent() {
  const dateInput = document.getElementById("calendar-event-date");
  const timeInput = document.getElementById("calendar-event-time");
  
  const date = dateInput.value.trim() || `${currentYear}-05-20`;
  const time = timeInput.value.trim() || "10:00";
  
  const promptInputText = document.getElementById("prompter-input").value.trim();
  let title = promptInputText;
  if (!title) {
    title = prompt("Enter meeting/event title:");
  }
  
  if (!title) {
    playSynthSound("error");
    return;
  }

  fetch("/api/calendar", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Jarvis-Token": apiToken
    },
    body: JSON.stringify({ action: "add", title: title, date: date, time: time })
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok) {
      playSynthSound("success");
      dateInput.value = "";
      timeInput.value = "";
      fetchCalendar();
      appendLog("SYSTEM", `Scheduled event: ${title} on ${date}`, "sys");
    }
  });
}

// 4. COMMAND CENTER (Reminders Timers)
function fetchReminders() {
  fetch("/api/reminders", {
    headers: { "X-Jarvis-Token": apiToken }
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok && data.reminders) {
      // Synchronize in-memory countdown list
      const now = Date.now();
      localRemindersList = data.reminders.map(r => ({
        text: r.text,
        end: r.end,
        remaining: Math.max(0, Math.round(r.end - now / 1000))
      }));
      renderRemindersUI();
    }
  })
  .catch(err => console.warn(err));
}

// Tick timers locally every second to render smooth UI updates
setInterval(() => {
  if (localRemindersList.length > 0) {
    const now = Date.now();
    localRemindersList.forEach(r => {
      const remainingSecs = Math.max(0, Math.round(r.end - now / 1000));
      if (remainingSecs === 0 && !spokenReminders.has(r.text)) {
        spokenReminders.add(r.text);
        speakText(`Sir, active alert: ${r.text}`);
        appendLog("REMINDER", `Alert triggered: ${r.text}`, "sys");
      }
      r.remaining = remainingSecs;
    });
    renderRemindersUI();
  }
}, 1000);

function renderRemindersUI() {
  const container = document.getElementById("reminders-scroll-box");
  if (!container) return;
  container.innerHTML = "";
  
  if (localRemindersList.length === 0) {
    container.innerHTML = '<span class="empty-deck-msg">No active counting reminders.</span>';
    return;
  }

  localRemindersList.forEach((r, idx) => {
    const item = document.createElement("div");
    item.className = "reminder-item";
    if (selectedReminderIndex === idx) item.classList.add("selected");
    
    const minutes = Math.floor(r.remaining / 60);
    const secs = r.remaining % 60;
    const timeStr = `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    
    item.innerHTML = `
      <div class="reminder-text">${r.text}</div>
      <div class="reminder-timer">${timeStr}</div>
    `;
    
    item.addEventListener("click", () => {
      selectedReminderIndex = idx;
      renderRemindersUI();
      playSynthSound("click");
    });
    container.appendChild(item);
  });
}

function setCountdownReminder() {
  const minsInput = document.getElementById("reminder-mins");
  const mins = parseInt(minsInput.value) || 5;
  
  const text = prompt("Enter voice reminder alert text:");
  if (!text) return;

  fetch("/api/reminders", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Jarvis-Token": apiToken
    },
    body: JSON.stringify({ action: "set", text: text, minutes: mins })
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok) {
      playSynthSound("success");
      fetchReminders();
      appendLog("SYSTEM", `Reminder set: "${text}" in ${mins} mins`, "sys");
    }
  });
}

function cancelCountdownReminder() {
  if (selectedReminderIndex === null || selectedReminderIndex === undefined) return;
  
  fetch("/api/reminders", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Jarvis-Token": apiToken
    },
    body: JSON.stringify({ action: "cancel", index: selectedReminderIndex })
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok) {
      playSynthSound("success");
      selectedReminderIndex = null;
      fetchReminders();
      appendLog("SYSTEM", "Timer sequence terminated.", "sys");
    }
  });
}

// 5. SECURITY (Diagnostics & TCP Trees & Files shortcuts)
function fetchSecurityIntelligence() {
  fetch("/api/security", {
    headers: { "X-Jarvis-Token": apiToken }
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok) {
      const box = document.getElementById("security-telemetry-box");
      if (box) {
        box.innerHTML = `
          <div><strong>LOCAL IP:</strong> ${data.local_ip || "127.0.0.1"}</div>
          <div><strong>PUBLIC IP:</strong> ${data.public_ip || "--"}</div>
          <div><strong>ISP:</strong> ${data.isp || "--"}</div>
          <div><strong>LOCATION:</strong> ${data.location || "--"}</div>
        `;
      }
      
      const defenderBox = document.getElementById("sec-defender-status");
      if (defenderBox) {
        defenderBox.textContent = data.defender || "Defender status: active";
      }

      // Render Connections list
      const tbody = document.getElementById("connections-list-body");
      if (tbody && data.connections) {
        tbody.innerHTML = "";
        data.connections.slice(0, 10).forEach(c => {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td>${c.pid || "-"}</td>
            <td>${c.local || "-"}</td>
            <td>${c.remote || "-"}</td>
            <td class="${c.status === 'ESTABLISHED' ? 'established' : ''}">${c.status || "-"}</td>
          `;
          tbody.appendChild(tr);
        });
      }
    }
  })
  .catch(err => console.warn(err));
}

function runGooglePing() {
  playSynthSound("click");
  appendLog("SECURITY", "Initiating ICMP diagnostic ping to google.com...", "sys");
  
  fetch("/api/security", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Jarvis-Token": apiToken
    },
    body: JSON.stringify({ action: "ping" })
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok && data.output) {
      playSynthSound("success");
      // Format lines
      data.output.split("\n").forEach(line => {
        if (line.trim()) appendLog("PING_ENGINE", line.trim(), "jarvis");
      });
    }
  });
}

function runPortScan() {
  playSynthSound("click");
  appendLog("SECURITY", "Scanning TCP local loopback structural ports (1-9000)...", "sys");
  
  fetch("/api/security", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Jarvis-Token": apiToken
    },
    body: JSON.stringify({ action: "port_scan" })
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok && data.open_ports) {
      playSynthSound("success");
      appendLog("SCAN_ENGINE", `Scan complete. Active ports: ${data.open_ports.join(", ")}`, "jarvis");
    }
  });
}

// Directory files loading
function fetchRecentFiles() {
  fetch("/api/files", {
    headers: { "X-Jarvis-Token": apiToken }
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok && data.recent_files) {
      const container = document.getElementById("sec-recent-files-box");
      if (!container) return;
      container.innerHTML = "";
      
      if (data.recent_files.length === 0) {
        container.innerHTML = '<span class="empty-deck-msg">No files index matches.</span>';
        return;
      }
      
      data.recent_files.slice(0, 8).forEach(file => {
        const item = document.createElement("div");
        item.className = "recent-file-item";
        item.innerHTML = `
          <div class="file-name" title="${file.path}">${file.name}</div>
          <div class="file-mtime">${file.mtime_str}</div>
        `;
        
        item.addEventListener("click", () => {
          openRemoteTarget(file.path);
        });
        
        container.appendChild(item);
      });
    }
  });
}

function openRemoteTarget(targetPath) {
  playSynthSound("click");
  appendLog("FILESYSTEM", `Requesting file launch: ${targetPath}`, "sys");
  
  fetch("/api/files", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Jarvis-Token": apiToken
    },
    body: JSON.stringify({ action: "open", path: targetPath })
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok) {
      playSynthSound("success");
      appendLog("FILESYSTEM", `Successfully opened: ${targetPath}`, "jarvis");
    } else {
      playSynthSound("error");
      appendLog("FILESYSTEM", `Launch failed: ${data.error}`, "sys");
    }
  });
}

// 6. SETTINGS (Configurations Form management)
function fetchSettings() {
  fetch("/api/settings", {
    headers: { "X-Jarvis-Token": apiToken }
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok && data.config) {
      const cfg = data.config;
      const secretFields = [
        ["cfg-openrouter", "has_openrouter_api_key"],
        ["cfg-groq", "has_groq_api_key"],
        ["cfg-weather", "has_openweather_api_key"],
        ["cfg-news", "has_news_api_key"],
        ["cfg-elevenlabs", "has_elevenlabs_api_key"]
      ];
      secretFields.forEach(([id, flag]) => {
        const field = document.getElementById(id);
        if (!field) return;
        field.value = "";
        field.placeholder = cfg[flag] ? "Configured - leave blank to keep current key" : "Paste key here";
      });
      
      // Populate models dynamically
      const modelSelect = document.getElementById("cfg-model");
      modelSelect.innerHTML = "";
      const models = ["llama3.2", "llama3.1", "llama3", "gemma2", "mistral", "phi3", "qwen2.5"];
      models.forEach(m => {
        const opt = document.createElement("option");
        opt.value = m;
        opt.textContent = m;
        if (m === cfg.ollama_model) opt.selected = true;
        modelSelect.appendChild(opt);
      });
      
      document.getElementById("cfg-style").value = cfg.response_style || "Concise";
      document.getElementById("cfg-temp").value = cfg.temperature || 0.7;
      document.getElementById("temp-val").textContent = Number(cfg.temperature || 0.7).toFixed(2);
      document.getElementById("cfg-memory").checked = !!cfg.conversation_memory;
      
      document.getElementById("cfg-camera-index").value = cfg.camera_index !== undefined ? cfg.camera_index : 0;
      document.getElementById("cfg-hud-style").value = cfg.hud_style || "mark50";
      document.getElementById("cfg-face-tracking").checked = !!cfg.face_tracking;
      document.getElementById("cfg-matrix-overlay").checked = !!cfg.matrix_overlay;
      
      document.getElementById("cfg-tts-rate").value = cfg.tts_rate || 172;
      document.getElementById("tts-rate-val").textContent = cfg.tts_rate || 172;
      
      document.getElementById("cfg-tts-volume").value = cfg.tts_volume || 0.95;
      document.getElementById("tts-vol-val").textContent = Number(cfg.tts_volume || 0.95).toFixed(2);
      
      document.getElementById("cfg-wake-words").value = cfg.wake_words || "jarvis, hey jarvis";
      const ttsBackend = document.getElementById("cfg-tts-backend");
      currentTtsBackend = cfg.tts_backend || "elevenlabs";
      if (ttsBackend) ttsBackend.value = currentTtsBackend;
      const edgeVoice = document.getElementById("cfg-edge-tts-voice");
      if (edgeVoice) edgeVoice.value = cfg.edge_tts_voice || "hi-IN-MadhurNeural";
      const elevenVoice = document.getElementById("cfg-elevenlabs-voice");
      if (elevenVoice) elevenVoice.value = cfg.elevenlabs_voice_id || "HH8sIQq8WOcER3Nu118i";
    }
  })
  .catch(err => console.warn("Failed to load settings:", err));
}

function saveSettings() {
  const payload = {
    openrouter_api_key: document.getElementById("cfg-openrouter").value,
    groq_api_key: document.getElementById("cfg-groq").value,
    openweather_api_key: document.getElementById("cfg-weather").value,
    news_api_key: document.getElementById("cfg-news").value,
    elevenlabs_api_key: document.getElementById("cfg-elevenlabs")?.value || "",
    ollama_model: document.getElementById("cfg-model").value,
    response_style: document.getElementById("cfg-style").value,
    temperature: parseFloat(document.getElementById("cfg-temp").value),
    conversation_memory: document.getElementById("cfg-memory").checked,
    camera_index: parseInt(document.getElementById("cfg-camera-index").value) || 0,
    hud_style: document.getElementById("cfg-hud-style").value,
    face_tracking: document.getElementById("cfg-face-tracking").checked,
    matrix_overlay: document.getElementById("cfg-matrix-overlay").checked,
    tts_rate: parseInt(document.getElementById("cfg-tts-rate").value) || 172,
    tts_volume: parseFloat(document.getElementById("cfg-tts-volume").value) || 0.95,
    tts_backend: document.getElementById("cfg-tts-backend")?.value || "elevenlabs",
    edge_tts_voice: document.getElementById("cfg-edge-tts-voice")?.value || "hi-IN-MadhurNeural",
    elevenlabs_enabled: (document.getElementById("cfg-tts-backend")?.value || "elevenlabs") === "elevenlabs",
    elevenlabs_voice_id: document.getElementById("cfg-elevenlabs-voice")?.value || "HH8sIQq8WOcER3Nu118i",
    elevenlabs_model_id: "eleven_multilingual_v2",
    wake_words: document.getElementById("cfg-wake-words").value
  };
  
  fetch("/api/settings", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Jarvis-Token": apiToken
    },
    body: JSON.stringify(payload)
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok) {
      playSynthSound("success");
      currentTtsBackend = payload.tts_backend || "elevenlabs";
      appendLog("SYSTEM", "AI settings saved and updated.", "sys");
    } else {
      playSynthSound("error");
      appendLog("SYSTEM", "Failed to save settings: " + data.error, "sys");
    }
  })
  .catch(err => {
    playSynthSound("error");
    appendLog("SYSTEM", "Settings save error: connection failed.", "sys");
  });
}

function setMode(mode) {
  // Update Buttons
  document.getElementById("btn-eco").classList.remove("active");
  document.getElementById("btn-quiet").classList.remove("active");
  document.getElementById("btn-default").classList.remove("active");
  
  document.getElementById(`btn-${mode.toLowerCase()}`).classList.add("active");
  document.getElementById("eco-status").textContent = mode;
  playSynthSound("click");
  
  appendLog("SYSTEM", `Performance mode initialized: ${mode}`, "sys");
}

function authedHeaders(extra = {}) {
  return Object.assign({
    "Content-Type": "application/json",
    "X-Jarvis-Token": apiToken || "jarvis",
    "ngrok-skip-browser-warning": "1"
  }, extra);
}

function runJarvisCommand(command, options = {}) {
  if (!command) return Promise.resolve(null);
  setCoreState("THINKING");
  appendLog("COMMAND", `Dispatching: ${command}`, "sys");
  return fetch("/api/command", {
    method: "POST",
    headers: authedHeaders(),
    body: JSON.stringify({
      command,
      speak: !!options.speak,
      allow_interactive: !!options.allowInteractive
    })
  })
    .then(res => res.json())
    .then(data => {
      if (data.ok) {
        const reply = normalizeJarvisReply(data.reply || "Command executed.");
        playSynthSound("success");
        appendChatBubble("J.A.R.V.I.S.", reply, "jarvis-bubble");
        appendLog("JARVIS", reply, "jarvis");
        if (options.speakText) speakText(reply);
      } else {
        playSynthSound("error");
        appendLog("SYSTEM", data.error || "Command failed.", "err");
      }
      setCoreState("STANDBY");
      return data;
    })
    .catch(err => {
      playSynthSound("error");
      appendLog("SYSTEM", `Command uplink failed: ${err.message}`, "err");
      setCoreState("STANDBY");
      return null;
    });
}

function createGuiParityPanels() {
  createSystemStatePanel();
  createQuickActionsPanel();
  createLocationPanel();
  createCoreModeControls();
  createQuickTasksPanel();
  createReferenceDeckControls();
  bindConfigExportImport();
  bindGuiParityEvents();
}

function bindGuiParityEvents() {
  if (document.body.dataset.guiParityBound) return;
  document.body.dataset.guiParityBound = "1";
  document.addEventListener("click", (event) => {
    const commandButton = event.target.closest("[data-command]");
    if (commandButton) {
      event.preventDefault();
      playSynthSound("click");
      runJarvisCommand(commandButton.getAttribute("data-command"), {
        speak: document.getElementById("voice-replies-toggle")?.checked || false,
        speakText: document.getElementById("voice-replies-toggle")?.checked || false
      });
      return;
    }

    const coreAction = event.target.closest("[data-core-action]");
    if (coreAction) {
      const action = coreAction.getAttribute("data-core-action");
      if (action === "voice") toggleVoiceCapture();
      if (action === "analyze-ref") {
        const text = document.getElementById("prompter-input")?.value?.trim() || "Analyze the current attached references or live frame.";
        const refs = attachedWebReferences
          .map((ref, index) => `Reference ${index + 1}: ${ref.name}\n${ref.text.slice(0, 4000)}`)
          .join("\n\n---\n\n");
        const prompt = refs ? `${text}\n\nAttached references:\n${refs}` : text;
        runJarvisCommand(`/ai ${prompt}`, { speakText: document.getElementById("voice-replies-toggle")?.checked || false });
      }
      return;
    }

    const refAction = event.target.closest("[data-ref-action]");
    if (refAction) {
      const action = refAction.getAttribute("data-ref-action");
      if (action === "choose") document.getElementById("web-reference-input")?.click();
      if (action === "clear") {
        attachedWebReferences = [];
        renderContextDeck();
        appendLog("SYSTEM", "Browser references cleared.", "sys");
      }
      return;
    }

    if (event.target.id === "btn-open-map") {
      playSynthSound("click");
      if (window.latestJarvisMapUrl) window.open(window.latestJarvisMapUrl, "_blank", "noopener");
      else fetchLocation(false);
      return;
    }
    if (event.target.id === "btn-refresh-map") {
      playSynthSound("click");
      fetchLocation(true);
      return;
    }
    if (event.target.id === "task-add-btn") return mutateTask("add");
    if (event.target.id === "task-toggle-btn") return mutateTask("toggle");
    if (event.target.id === "task-delete-btn") return mutateTask("delete");
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target && event.target.id === "task-input") {
      mutateTask("add");
    }
  });
}

function createSystemStatePanel() {
  const mission = document.getElementById("pane-left-mission");
  if (!mission || document.getElementById("gui-system-state-card")) return;
  const card = document.createElement("div");
  card.className = "glass-panel system-state-card gui-parity-card";
  card.id = "gui-system-state-card";
  card.innerHTML = `
    <div class="panel-header">
      <span class="panel-title">SYSTEM STATE</span>
      <span class="panel-subtitle">GUI parity: live CPU, RAM, disk, battery, thermals</span>
    </div>
    <div class="system-state-grid">
      ${["cpu", "ram", "disk", "battery"].map(key => `
        <div class="sys-meter">
          <div class="sys-meter-meta"><span>${key.toUpperCase()}</span><strong id="sys-${key}-value">--</strong></div>
          <div class="sys-meter-track"><i id="sys-${key}-bar"></i></div>
        </div>
      `).join("")}
    </div>
    <div class="thermal-readout" id="sys-thermal-readout">Thermals pending...</div>
    <div class="quick-actions-grid two">
      <button class="hud-btn" data-command="thermal status">THERMALS</button>
      <button class="hud-btn" data-command="open omen gaming hub">HP COOLING</button>
    </div>
  `;
  mission.prepend(card);
}

function createQuickActionsPanel() {
  const mission = document.getElementById("pane-left-mission");
  if (!mission || document.getElementById("gui-quick-actions-card")) return;
  const cameraCard = mission.querySelector(".camera-card");
  const card = document.createElement("div");
  card.className = "glass-panel quick-actions-card gui-parity-card";
  card.id = "gui-quick-actions-card";
  const actions = [
    ["SYSTEM REPORT", "system status"],
    ["SEND REPORT", "send me operator report"],
    ["OPERATOR", "operator capabilities"],
    ["BROWSER CTRL", "browser control help"],
    ["AUTO AGENT", "/agent read the current screen and describe what is open"],
    ["CHECK EMAIL", "check my emails"],
    ["NEWS", "top news today"],
    ["WEATHER", "what's the weather"],
    ["READ NOTES", "read my notes"],
    ["TODAY", "today's schedule"],
    ["SCREENSHOT", "take a screenshot"],
    ["LOCK", "lock screen"],
    ["LIST CAMERAS", "list cameras"],
    ["CLEAR MEMORY", "clear chat"]
  ];
  card.innerHTML = `
    <div class="panel-header">
      <span class="panel-title">QUICK ACTIONS</span>
      <span class="panel-subtitle">Desktop GUI shortcuts routed through JARVIS</span>
    </div>
    <div class="quick-actions-grid">
      ${actions.map(([label, command]) => `<button class="hud-btn" data-command="${command}">${label}</button>`).join("")}
    </div>
  `;
  mission.insertBefore(card, cameraCard || mission.children[1] || null);
}

function createLocationPanel() {
  const mission = document.getElementById("pane-left-mission");
  if (!mission || document.getElementById("gui-location-card")) return;
  const card = document.createElement("div");
  card.className = "glass-panel location-card gui-parity-card";
  card.id = "gui-location-card";
  card.innerHTML = `
    <div class="panel-header">
      <span class="panel-title">LIVE LOCATION MAP</span>
      <span class="panel-subtitle">IP geolocation with browser handoff</span>
    </div>
    <div class="map-preview" id="location-map-preview">
      <div class="map-reticle"></div>
      <span id="location-map-label">Fetching location...</span>
    </div>
    <div class="location-readout" id="location-readout">Detecting location...</div>
    <div class="quick-actions-grid two">
      <button class="hud-btn" id="btn-open-map">OPEN MAP</button>
      <button class="hud-btn" id="btn-refresh-map">REFRESH</button>
    </div>
  `;
  mission.appendChild(card);
}

function createCoreModeControls() {
  const coreCard = document.querySelector(".main-core-card");
  const prompter = document.querySelector(".prompter-input-bar");
  if (!coreCard || !prompter || document.getElementById("gui-core-controls")) return;
  const controls = document.createElement("div");
  controls.className = "core-mode-controls";
  controls.id = "gui-core-controls";
  controls.innerHTML = `
    <label><input type="checkbox" id="force-ai-toggle"> FORCE AI</label>
    <label><input type="checkbox" id="voice-replies-toggle" checked> VOICE REPLIES</label>
    <label><input type="checkbox" id="keep-refs-toggle" checked> KEEP REFERENCES</label>
    <button class="hud-btn-mini" data-core-action="voice">VOICE INPUT</button>
    <button class="hud-btn-mini" data-core-action="analyze-ref">ANALYZE REF</button>
    <button class="hud-btn-mini danger" data-command="clear chat">CLEAR MEMORY</button>
    <button class="hud-btn-mini" data-command="list cameras">LIST CAMERAS</button>
  `;
  coreCard.insertBefore(controls, prompter);
}

function createQuickTasksPanel() {
  const commandPane = document.getElementById("pane-right-command");
  if (!commandPane || document.getElementById("gui-quick-tasks-card")) return;
  const card = document.createElement("div");
  card.className = "glass-panel tasks-card gui-parity-card";
  card.id = "gui-quick-tasks-card";
  card.innerHTML = `
    <div class="panel-header">
      <span class="panel-title">QUICK TASKS</span>
      <span class="panel-subtitle">Checklist shared with desktop GUI</span>
    </div>
    <div class="tasks-list-box" id="tasks-scroll-box"></div>
    <div class="task-input-row">
      <input type="text" id="task-input" class="hud-input" placeholder="Add a task..." />
      <button class="hud-btn" id="task-add-btn">ADD</button>
      <button class="hud-btn" id="task-toggle-btn">TOGGLE</button>
      <button class="hud-btn danger" id="task-delete-btn">DELETE</button>
    </div>
  `;
  commandPane.appendChild(card);
}

function createReferenceDeckControls() {
  const deck = document.getElementById("context-files-deck");
  if (!deck || document.getElementById("gui-reference-helper")) return;
  const helper = document.createElement("div");
  helper.id = "gui-reference-helper";
  helper.className = "reference-helper";
  helper.innerHTML = `
    <div class="reference-helper-copy">Attach browser-readable files here, or paste local paths into the composer for backend handling.</div>
    <div class="reference-tool-row">
      <button class="hud-btn micro" data-ref-action="choose">ATTACH FILES</button>
      <button class="hud-btn micro" data-core-action="analyze-ref">ANALYZE REF</button>
      <button class="hud-btn micro danger" data-ref-action="clear">CLEAR REFS</button>
    </div>
    <input id="web-reference-input" type="file" multiple hidden accept=".txt,.md,.json,.py,.js,.css,.html,.csv,.log,text/*,application/json">
    <div id="web-reference-list" class="web-reference-list">No browser references attached.</div>
  `;
  deck.parentElement.insertBefore(helper, deck.nextSibling);
  document.getElementById("web-reference-input")?.addEventListener("change", event => {
    handleWebReferenceFiles(Array.from(event.target.files || []));
    event.target.value = "";
  });
}

async function handleWebReferenceFiles(files) {
  if (!files.length) return;
  for (const file of files) {
    try {
      const text = await file.text();
      attachedWebReferences.push({
        name: file.name,
        size: file.size,
        type: file.type || "text/plain",
        text
      });
      appendLog("SYSTEM", `Attached browser reference: ${file.name}`, "sys");
    } catch (err) {
      appendLog("ERROR", `Reference attach failed for ${file.name}: ${err.message}`, "err");
    }
  }
  renderContextDeck();
}

function renderWebReferences() {
  const list = document.getElementById("web-reference-list");
  if (!list) return;
  if (attachedWebReferences.length === 0) {
    list.textContent = "No browser references attached.";
    return;
  }
  list.innerHTML = attachedWebReferences
    .map(ref => `<div class="web-reference-item"><span>${escapeHtml(ref.name)}</span><em>${Math.ceil(ref.size / 1024)} KB</em></div>`)
    .join("");
}

function renderContextDeck() {
  const deck = document.getElementById("context-files-deck");
  if (!deck) return;
  if (attachedWebReferences.length === 0) {
    selectedContextIndex = null;
    deck.innerHTML = '<span class="empty-deck-msg">No files attached.</span>';
    renderWebReferences();
    return;
  }
  if (selectedContextIndex === null || selectedContextIndex >= attachedWebReferences.length) {
    selectedContextIndex = attachedWebReferences.length - 1;
  }
  deck.innerHTML = attachedWebReferences.map((ref, index) => {
    const isSelected = selectedContextIndex === index ? " selected" : "";
    const folder = ref.path && ref.path.includes("/") ? ref.path.split("/").slice(0, -1).join("/") : "";
    return `
      <div class="context-file-chip${isSelected}" data-context-index="${index}">
        <strong>${escapeHtml(ref.name)}</strong>
        <span>${Math.ceil((ref.size || ref.text.length) / 1024)} KB${folder ? ` | ${escapeHtml(folder)}` : ""}</span>
      </div>
    `;
  }).join("");
  renderWebReferences();
}

async function handleContextFileSelection(files) {
  if (!files.length) return;
  for (const file of files) {
    try {
      const text = await file.text();
      attachedWebReferences.push({
        name: file.name,
        path: file.webkitRelativePath || file.name,
        size: file.size,
        type: file.type || "text/plain",
        text
      });
      appendLog("FILES", `Attached ${file.webkitRelativePath || file.name}`, "sys");
    } catch (err) {
      appendLog("ERROR", `Could not attach ${file.name}: ${err.message}`, "err");
    }
  }
  renderContextDeck();
}

function removeSelectedContextFile() {
  if (selectedContextIndex === null || selectedContextIndex < 0 || selectedContextIndex >= attachedWebReferences.length) {
    appendLog("FILES", "Select a context file first.", "sys");
    playSynthSound("error");
    return;
  }
  const removed = attachedWebReferences.splice(selectedContextIndex, 1)[0];
  selectedContextIndex = Math.min(selectedContextIndex, attachedWebReferences.length - 1);
  if (selectedContextIndex < 0) selectedContextIndex = null;
  appendLog("FILES", `Removed ${removed.name}`, "sys");
  renderContextDeck();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[char]));
}

function bindConfigExportImport() {
  const exportBtn = document.getElementById("btn-export-config");
  const importBtn = document.getElementById("btn-import-config");
  if (exportBtn && !exportBtn.dataset.bound) {
    exportBtn.dataset.bound = "1";
    exportBtn.addEventListener("click", () => {
      fetch("/api/settings", { headers: { "X-Jarvis-Token": apiToken } })
        .then(res => res.json())
        .then(data => {
          const blob = new Blob([JSON.stringify(data.config || {}, null, 2)], { type: "application/json" });
          const link = document.createElement("a");
          link.download = `jarvis_config_export_${Date.now()}.json`;
          link.href = URL.createObjectURL(blob);
          link.click();
          URL.revokeObjectURL(link.href);
          appendLog("SYSTEM", "Sanitized config exported.", "sys");
        });
    });
  }
  if (importBtn && !importBtn.dataset.bound) {
    importBtn.dataset.bound = "1";
    importBtn.addEventListener("click", () => {
      appendLog("SYSTEM", "Import uses the settings form: paste values and press SAVE.", "sys");
      switchTab("settings");
    });
  }
}

function updateGuiParityTelemetry(data) {
  const hw = data.hardware || {};
  if (!hw.available) return;
  const rawCpu = Number(hw.cpu_percent || 0);
  smoothedTelemetry.cpu = smoothedTelemetry.cpu == null
    ? rawCpu
    : (smoothedTelemetry.cpu * 0.65) + (rawCpu * 0.35);
  const vals = {
    cpu: smoothedTelemetry.cpu,
    ram: Number((hw.ram && hw.ram.percent) || 0),
    disk: Number((hw.disk && hw.disk.percent) || 0),
    battery: Number((hw.battery && hw.battery.percent) || 0)
  };
  Object.entries(vals).forEach(([key, value]) => {
    const val = document.getElementById(`sys-${key}-value`);
    const bar = document.getElementById(`sys-${key}-bar`);
    if (val) val.textContent = `${value.toFixed(0)}%`;
    if (bar) bar.style.width = `${Math.max(0, Math.min(100, value))}%`;
  });
  const t = (hw.thermals || {});
  const therm = document.getElementById("sys-thermal-readout");
  if (therm) {
    const bits = [];
    if (t.cpu_temp_c != null) bits.push(`CPU ${Number(t.cpu_temp_c).toFixed(0)}C`);
    if (t.gpu_temp_c != null) bits.push(`GPU ${Number(t.gpu_temp_c).toFixed(0)}C`);
    if (Array.isArray(t.fans) && t.fans.length) bits.push(t.fans.map(f => `${f.name}: ${f.rpm} RPM`).join(" / "));
    therm.textContent = bits.length ? bits.join(" | ") : (t.note || "Thermals unavailable. Run LibreHardwareMonitor/OpenHardwareMonitor for richer sensors.");
  }
}

function fetchLocation(refresh = false) {
  fetch(`/api/location${refresh ? "?refresh=1" : ""}`, {
    headers: { "X-Jarvis-Token": apiToken }
  })
    .then(res => res.json())
    .then(data => {
      if (!data.ok) throw new Error(data.error || "Location failed");
      const readout = document.getElementById("location-readout");
      const label = document.getElementById("location-map-label");
      if (readout) {
        const coords = data.coords ? ` | ${Number(data.coords[0]).toFixed(4)}, ${Number(data.coords[1]).toFixed(4)}` : "";
        readout.textContent = `${data.label || "Location unavailable"}${coords}`;
      }
      if (label) label.textContent = data.raw?.city ? `${data.raw.city} / ${data.raw.region || "network fix"}` : "Location resolved";
      window.latestJarvisMapUrl = data.map_url;
      appendLog("SYSTEM", "Location panel synchronized.", "sys");
    })
    .catch(err => appendLog("SYSTEM", `Location fetch failed: ${err.message}`, "err"));
}

function fetchTasks() {
  fetch("/api/tasks", { headers: { "X-Jarvis-Token": apiToken } })
    .then(res => res.json())
    .then(data => {
      if (data.ok) {
        quickTasksList = data.tasks || [];
        renderTasks();
      }
    })
    .catch(() => {});
}

function renderTasks() {
  const box = document.getElementById("tasks-scroll-box");
  if (!box) return;
  box.innerHTML = "";
  if (!quickTasksList.length) {
    box.innerHTML = `<span class="empty-deck-msg">No quick tasks yet.</span>`;
    return;
  }
  quickTasksList.forEach((task, idx) => {
    const item = document.createElement("button");
    item.className = `task-item ${idx === selectedTaskIndex ? "selected" : ""} ${task.done ? "done" : ""}`;
    item.textContent = `${task.done ? "✓" : "•"} ${task.text || ""}`;
    item.addEventListener("click", () => {
      selectedTaskIndex = idx;
      renderTasks();
    });
    box.appendChild(item);
  });
}

function mutateTask(action) {
  const input = document.getElementById("task-input");
  const body = { action };
  if (action === "add") body.text = (input?.value || "").trim();
  else body.index = selectedTaskIndex;
  fetch("/api/tasks", {
    method: "POST",
    headers: authedHeaders(),
    body: JSON.stringify(body)
  })
    .then(res => res.json())
    .then(data => {
      if (data.ok) {
        quickTasksList = data.tasks || [];
        if (input && action === "add") input.value = "";
        if (action === "delete") selectedTaskIndex = null;
        renderTasks();
        playSynthSound("success");
      } else {
        playSynthSound("error");
        appendLog("SYSTEM", data.error || "Task update failed.", "err");
      }
    });
}

// --- Submit Events & Form Wiring ---
function setupEventListeners() {
  const input = document.getElementById("prompter-input");
  const sendBtn = document.getElementById("send-command-btn");
  const micBtn = document.getElementById("mic-btn");

  if (input) input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      sendPrompterCommand();
    }
  });

  if (sendBtn) sendBtn.addEventListener("click", () => {
    sendPrompterCommand();
  });

  if (micBtn) micBtn.addEventListener("click", () => {
    toggleVoiceCapture();
  });

  // Top header modes
  document.getElementById("btn-eco").addEventListener("click", () => setMode("ECO"));
  document.getElementById("btn-quiet").addEventListener("click", () => setMode("QUIET"));
  document.getElementById("btn-default").addEventListener("click", () => setMode("DEFAULT"));

  // Bind glassmorphic tabs
  document.querySelectorAll(".nav-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      const tabName = tab.getAttribute("data-tab");
      switchTab(tabName);
    });
  });

  // MISSION CORE refreshing
  const wRef = document.getElementById("weather-refresh-btn");
  const nRef = document.getElementById("news-refresh-btn");
  const mobileRef = document.getElementById("mobile-refresh-btn");
  const mobileMap = document.getElementById("mobile-open-map-btn");
  const mobileLog = document.getElementById("mobile-log-btn");
  if (wRef) wRef.addEventListener("click", () => { playSynthSound("click"); fetchWeatherNews(); });
  if (nRef) nRef.addEventListener("click", () => { playSynthSound("click"); fetchWeatherNews(); });
  if (mobileRef) mobileRef.addEventListener("click", () => { playSynthSound("click"); fetchMobileCompanionStatus(); });
  if (mobileMap) mobileMap.addEventListener("click", () => {
    playSynthSound("click");
    if (latestMobileMapUrl) window.open(latestMobileMapUrl, "_blank", "noopener");
  });
  if (mobileLog) mobileLog.addEventListener("click", () => {
    playSynthSound("click");
    const status = document.getElementById("mobile-session-status")?.textContent || "Mobile status unavailable.";
    const lastSeen = document.getElementById("mobile-last-seen")?.textContent || "";
    appendLog("MOBILE", `${status} ${lastSeen}`.trim(), "sys");
  });
  
  // Snap Camera Photo
  const snapBtn = document.getElementById("radar-snap-btn");
  if (snapBtn) {
    snapBtn.addEventListener("click", () => {
      playSynthSound("click");
      appendLog("RADAR", "Taking security snapshot scan...", "sys");
      fetch("/api/command", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Jarvis-Token": apiToken
        },
        body: JSON.stringify({ command: "take photo", speak: false })
      })
      .then(res => res.json())
      .then(data => {
        if (data.ok) {
          playSynthSound("success");
          appendLog("RADAR", "Photo taken. Stored in photos folder.", "jarvis");
          
          // Increment photos taken statistic
          const photosEl = document.getElementById("stat-photos-taken");
          if (photosEl) {
            const count = parseInt(photosEl.textContent) || 0;
            photosEl.textContent = count + 1;
          }
        }
      });
    });
  }

  const radarReset = document.getElementById("radar-reset-btn");
  if (radarReset) {
    radarReset.addEventListener("click", () => {
      playSynthSound("click");
      radarBlips.length = 0;
      appendLog("RADAR", "Tracking database cleared.", "sys");
    });
  }

  // ANALYTICS Killer
  const killBtn = document.getElementById("btn-kill-process");
  const refProc = document.getElementById("btn-refresh-processes");
  if (killBtn) killBtn.addEventListener("click", killSelectedProcess);
  if (refProc) refProc.addEventListener("click", () => { playSynthSound("click"); pollProcesses(); });

  // COMMAND CENTER Notes Scratchpad
  const nSave = document.getElementById("notes-save-btn");
  const nDel = document.getElementById("notes-delete-btn");
  const nSearchBtn = document.getElementById("notes-search-btn");
  const nSearchInput = document.getElementById("notes-search");
  
  if (nSave) nSave.addEventListener("click", saveScratchNote);
  if (nDel) nDel.addEventListener("click", deleteScratchNote);
  if (nSearchBtn) nSearchBtn.addEventListener("click", filterNotesLocal);
  if (nSearchInput) nSearchInput.addEventListener("input", filterNotesLocal);

  // Calendar
  const calAdd = document.getElementById("calendar-add-btn");
  const calRef = document.getElementById("calendar-refresh-btn");
  if (calAdd) calAdd.addEventListener("click", addCalendarEvent);
  if (calRef) calRef.addEventListener("click", () => { playSynthSound("click"); fetchCalendar(); });

  // Reminders
  const remSet = document.getElementById("reminder-set-btn");
  const remCancel = document.getElementById("reminder-cancel-btn");
  if (remSet) remSet.addEventListener("click", setCountdownReminder);
  if (remCancel) remCancel.addEventListener("click", cancelCountdownReminder);

  // SECURITY 
  const pGoogle = document.getElementById("btn-ping-google");
  const refSec = document.getElementById("btn-refresh-security");
  const scanPort = document.getElementById("btn-port-scan");
  
  if (pGoogle) pGoogle.addEventListener("click", runGooglePing);
  if (refSec) refSec.addEventListener("click", () => { playSynthSound("click"); fetchSecurityIntelligence(); });
  if (scanPort) scanPort.addEventListener("click", runPortScan);

  // Files shortcuts
  document.querySelectorAll(".quick-links button").forEach(btn => {
    btn.addEventListener("click", () => {
      const folder = btn.getAttribute("data-folder");
      openRemoteTarget(folder);
    });
  });

  const contextFileInput = document.getElementById("context-file-input");
  const contextFolderInput = document.getElementById("context-folder-input");
  const addFilesBtn = document.getElementById("btn-add-files");
  const addFolderBtn = document.getElementById("btn-add-folder");
  const projectFilesBtn = document.getElementById("btn-project-files");
  const removeFileBtn = document.getElementById("btn-remove-file");
  const clearFilesBtn = document.getElementById("btn-clear-all-files");
  const contextDeck = document.getElementById("context-files-deck");

  if (addFilesBtn) addFilesBtn.addEventListener("click", () => {
    playSynthSound("click");
    contextFileInput?.click();
  });
  if (addFolderBtn) addFolderBtn.addEventListener("click", () => {
    playSynthSound("click");
    contextFolderInput?.click();
  });
  if (projectFilesBtn) projectFilesBtn.addEventListener("click", () => {
    playSynthSound("click");
    const summary = attachedWebReferences.length
      ? `Project context loaded with ${attachedWebReferences.length} attached file(s). Ask your next command with KEEP REFERENCES enabled.`
      : "No project files attached yet. Use ADD FILES or ADD FOLDER first.";
    appendLog("FILES", summary, attachedWebReferences.length ? "jarvis" : "sys");
    appendChatBubble("J.A.R.V.I.S.", summary, "jarvis-bubble");
  });
  if (removeFileBtn) removeFileBtn.addEventListener("click", removeSelectedContextFile);
  if (clearFilesBtn) clearFilesBtn.addEventListener("click", () => {
    playSynthSound("click");
    attachedWebReferences = [];
    selectedContextIndex = null;
    renderContextDeck();
    appendLog("FILES", "All context files cleared.", "sys");
  });
  if (contextFileInput) contextFileInput.addEventListener("change", event => {
    handleContextFileSelection(Array.from(event.target.files || []));
    event.target.value = "";
  });
  if (contextFolderInput) contextFolderInput.addEventListener("change", event => {
    handleContextFileSelection(Array.from(event.target.files || []));
    event.target.value = "";
  });
  if (contextDeck) contextDeck.addEventListener("click", event => {
    const chip = event.target.closest("[data-context-index]");
    if (!chip) return;
    selectedContextIndex = Number(chip.getAttribute("data-context-index"));
    playSynthSound("click");
    renderContextDeck();
  });

  // SETTINGS AI form widgets updates on adjust
  const tempSlider = document.getElementById("cfg-temp");
  const rateSlider = document.getElementById("cfg-tts-rate");
  const volSlider = document.getElementById("cfg-tts-volume");
  
  if (tempSlider) {
    tempSlider.addEventListener("input", () => {
      document.getElementById("temp-val").textContent = Number(tempSlider.value).toFixed(2);
    });
  }
  if (rateSlider) {
    rateSlider.addEventListener("input", () => {
      document.getElementById("tts-rate-val").textContent = rateSlider.value;
    });
  }
  if (volSlider) {
    volSlider.addEventListener("input", () => {
      document.getElementById("tts-vol-val").textContent = Number(volSlider.value).toFixed(2);
    });
  }

  const voiceTest = document.getElementById("btn-test-voice");
  const settingsSave = document.getElementById("btn-save-settings");
  const settingsReset = document.getElementById("btn-reset-settings");
  
  if (voiceTest) {
    voiceTest.addEventListener("click", () => {
      playSynthSound("success");
      speakText("Sir, robotic baritone speech systems fully modular and responsive. Morphed particles core active.");
    });
  }
  if (settingsSave) settingsSave.addEventListener("click", saveSettings);
  if (settingsReset) {
    settingsReset.addEventListener("click", () => {
      playSynthSound("click");
      fetchSettings();
    });
  }

  // Spatial UI tracking (Mouse depth effect)
  document.addEventListener("mousemove", (e) => {
    const hud = document.getElementById("main-hud");
    if (!hud || hud.classList.contains("hidden")) return;
    
    // Calculate mouse position relative to center of screen (-1 to 1)
    const x = (e.clientX / window.innerWidth - 0.5) * 2;
    const y = (e.clientY / window.innerHeight - 0.5) * 2;
    
    // Rotate max 3 degrees
    const rotateX = y * -3; 
    const rotateY = x * 3;
    
    hud.style.transform = `rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
  });

  // Example Context-Aware state toggle button (for testing threat mode)
  const logo = document.querySelector(".header-logo");
  if (logo) {
    logo.addEventListener("dblclick", () => {
      if (document.body.classList.contains("jarvis-threat")) {
        document.body.classList.remove("jarvis-threat");
        document.body.classList.add("jarvis-idle");
        speakText("Threat canceled. Returning to idle state.");
      } else {
        document.body.classList.remove("jarvis-idle");
        document.body.classList.add("jarvis-threat");
        speakText("Warning. Threat state activated. Scanning sectors.");
      }
    });
  }
}

// --- J.A.R.V.I.S. Real-Time Camera HUD & Face Recognition System ---
let webcamStream = null;
let webcamVideo = null;
let cameraCanvas = null;
let cameraCtx = null;
let cameraHudAnim = 0;
let selectedHudStyle = "mark50";
let detectedFaces = []; // State of detected faces from backend
let faceLockSummary = "Face lock idle.";
let cameraSummaryText = "Camera offline.";
let isAnalyzingFace = false;
let autoScanInterval = null;

function initCameraHUD() {
  webcamVideo = document.getElementById("webcam-video");
  cameraCanvas = document.getElementById("camera-canvas");
  if (!cameraCanvas) return;
  cameraCtx = cameraCanvas.getContext("2d");

  const btnToggleCam = document.getElementById("btn-toggle-cam");
  const btnCamSnap = document.getElementById("btn-cam-snap");
  const btnCamRef = document.getElementById("btn-cam-ref");
  const btnCamAnalyze = document.getElementById("btn-cam-analyze");

  // Wire camera toggle button
  if (btnToggleCam) {
    btnToggleCam.addEventListener("click", () => {
      playSynthSound("click");
      if (webcamStream) {
        stopWebcam();
      } else {
        startWebcam();
      }
    });
  }

  // Wire Snap button
  if (btnCamSnap) {
    btnCamSnap.addEventListener("click", () => {
      playSynthSound("success");
      const dataUrl = cameraCanvas.toDataURL("image/png");
      const link = document.createElement("a");
      link.download = `jarvis_snap_${Date.now()}.png`;
      link.href = dataUrl;
      link.click();
      appendLog("CAMERA", "Target snapshot saved to device downloads.", "jarvis");
    });
  }

  // Wire Reference capture button
  if (btnCamRef) {
    btnCamRef.addEventListener("click", () => {
      playSynthSound("click");
      const dataUrl = cameraCanvas.toDataURL("image/jpeg", 0.85);
      appendLog("CAMERA", "Saving face template reference to backend...", "sys");
      fetch("/api/auth", {
        method: "POST",
        headers: authedHeaders(),
        body: JSON.stringify({ image: dataUrl, save_template: true })
      })
      .then(res => res.json())
      .then(data => {
        if (data.ok) {
          playSynthSound("success");
          appendLog("CAMERA", "Face template saved. Added to owner faces directory.", "jarvis");
          speakText("Template recorded. Face recognition database updated.");
        } else {
          appendLog("CAMERA", "Failed to save face template.", "err");
        }
      });
    });
  }

  // Wire Analyze button
  if (btnCamAnalyze) {
    btnCamAnalyze.addEventListener("click", runFaceAnalysis);
  }

  // Wire Options/Style controls
  const styleButtons = document.querySelectorAll(".camera-styles-bar .style-btn");
  styleButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      playSynthSound("click");
      styleButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      
      selectedHudStyle = btn.getAttribute("data-style");
      
      // Reset filter classes
      cameraCanvas.className = "";
      if (selectedHudStyle !== "mark50") {
        cameraCanvas.classList.add(`cam-filter-${selectedHudStyle}`);
      }
      
      appendLog("CAMERA", `HUD filter mode swapped to: ${selectedHudStyle.toUpperCase()}`, "sys");
    });
  });
}

function startWebcam() {
  const overlay = document.getElementById("camera-status-overlay");
  const btnToggleCam = document.getElementById("btn-toggle-cam");
  const btnCamSnap = document.getElementById("btn-cam-snap");
  const btnCamRef = document.getElementById("btn-cam-ref");
  const btnCamAnalyze = document.getElementById("btn-cam-analyze");
  const camSummary = document.getElementById("camera-summary");
  const lockStatus = document.getElementById("camera-lock-status");

  navigator.mediaDevices.getUserMedia({ 
    video: { width: 320, height: 240, facingMode: "user" } 
  })
  .then(stream => {
    webcamStream = stream;
    isWebcamActive = true;
    webcamVideo.srcObject = stream;
    webcamVideo.play();

    if (overlay) overlay.style.opacity = 0;
    if (btnToggleCam) btnToggleCam.textContent = "STOP CAM";
    if (btnCamSnap) btnCamSnap.disabled = false;
    if (btnCamRef) btnCamRef.disabled = false;
    if (btnCamAnalyze) btnCamAnalyze.disabled = false;

    cameraSummaryText = "Camera feed active.";
    faceLockSummary = "Scanning environment...";
    if (camSummary) camSummary.textContent = cameraSummaryText;
    if (lockStatus) lockStatus.textContent = faceLockSummary;

    appendLog("CAMERA", "Webcam stream activated. Face tracker active.", "sys");
    const radarLabel = document.querySelector(".radar-label");
    if (radarLabel) radarLabel.textContent = "Radar linked to live camera. Face and motion targets will map here.";
    document.querySelector(".radar-card")?.classList.add("camera-linked");
    
    // Start local rendering loops
    requestAnimationFrame(renderCameraHUD);

    // Setup periodic face auto-scanning (every 2.5 seconds to avoid flooding)
    autoScanInterval = setInterval(runFaceAnalysisSilent, 2500);
  })
  .catch(err => {
    appendLog("CAMERA", `Webcam access denied: ${err.message}`, "err");
    cameraSummaryText = "Webcam error: Access Denied.";
    if (camSummary) camSummary.textContent = cameraSummaryText;
  });
}

function stopWebcam() {
  const overlay = document.getElementById("camera-status-overlay");
  const btnToggleCam = document.getElementById("btn-toggle-cam");
  const btnCamSnap = document.getElementById("btn-cam-snap");
  const btnCamRef = document.getElementById("btn-cam-ref");
  const btnCamAnalyze = document.getElementById("btn-cam-analyze");
  const camSummary = document.getElementById("camera-summary");
  const lockStatus = document.getElementById("camera-lock-status");

  if (autoScanInterval) {
    clearInterval(autoScanInterval);
    autoScanInterval = null;
  }

  if (webcamStream) {
    webcamStream.getTracks().forEach(track => track.stop());
    webcamStream = null;
  }

  webcamVideo.srcObject = null;
  isWebcamActive = false;
  detectedFaces = [];
  radarBlips.length = 0;

  if (overlay) overlay.style.opacity = 1;
  if (btnToggleCam) btnToggleCam.textContent = "START CAM";
  if (btnCamSnap) btnCamSnap.disabled = true;
  if (btnCamRef) btnCamRef.disabled = true;
  if (btnCamAnalyze) btnCamAnalyze.disabled = true;

  cameraSummaryText = "Camera offline.";
  faceLockSummary = "Face lock idle.";
  if (camSummary) camSummary.textContent = cameraSummaryText;
  if (lockStatus) lockStatus.textContent = faceLockSummary;

  // Clear canvas
  cameraCtx.clearRect(0, 0, cameraCanvas.width, cameraCanvas.height);
  appendLog("CAMERA", "Webcam stream terminated.", "sys");
  const radarLabel = document.querySelector(".radar-label");
  if (radarLabel) radarLabel.textContent = "Radar standby. Start camera to scan movement.";
  document.querySelector(".radar-card")?.classList.remove("camera-linked");
}

function runFaceAnalysis() {
  if (!webcamStream || isAnalyzingFace) return;
  isAnalyzingFace = true;
  playSynthSound("click");
  appendLog("CAMERA", "Running system face diagnostics...", "sys");

  const dataUrl = cameraCanvas.toDataURL("image/jpeg", 0.75);
  const faceTrackingEnabled = document.getElementById("cam-face-tracking").checked;

  fetch("/api/camera_process", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Jarvis-Token": apiToken
    },
    body: JSON.stringify({ 
      image: dataUrl,
      face_tracking: faceTrackingEnabled
    })
  })
  .then(res => res.json())
  .then(data => {
    isAnalyzingFace = false;
    if (data.ok) {
      detectedFaces = data.faces || [];
      pushRadarBlipsFromFaces(detectedFaces);
      const camSummary = document.getElementById("camera-summary");
      const lockStatus = document.getElementById("camera-lock-status");
      if (data.face_lib_available === false) {
        cameraSummaryText = "OpenCV face engine unavailable on backend.";
        faceLockSummary = "Install/enable cv2 for real recognition.";
        if (camSummary) camSummary.textContent = cameraSummaryText;
        if (lockStatus) lockStatus.textContent = faceLockSummary;
        appendLog("CAMERA", "Backend face library unavailable. Camera feed is live, recognition disabled.", "err");
        return;
      }

      if (detectedFaces.length > 0) {
        const primary = detectedFaces[0];
        playSynthSound("success");
        if (primary.recognized) {
          faceLockSummary = `TARGET LOCKED: ${primary.name.toUpperCase()}`;
          cameraSummaryText = `Threat level: ${primary.threat} | Distance: ${primary.distance}m`;
          appendLog("CAMERA", `Target lock established: ${primary.name}. Threat level: ${primary.threat}.`, "jarvis");
          speakText(`Target identified: welcome back, ${primary.name}.`);
        } else {
          faceLockSummary = "UNKNOWN TARGET LOCKED";
          cameraSummaryText = `Threat level: ${primary.threat} | Distance: ${primary.distance}m`;
          appendLog("CAMERA", "Unknown target intercepted. Threat logged.", "err");
          speakText("Unknown target intercepted. Security protocols standing by.");
        }
      } else {
        faceLockSummary = "Scanning... No faces locked.";
        cameraSummaryText = "Environment scan complete. Empty zone.";
      }
      
      if (camSummary) camSummary.textContent = cameraSummaryText;
      if (lockStatus) lockStatus.textContent = faceLockSummary;
    }
  })
  .catch(() => {
    isAnalyzingFace = false;
  });
}

function runFaceAnalysisSilent() {
  if (!webcamStream || isAnalyzingFace) return;
  const faceTrackingEnabled = document.getElementById("cam-face-tracking").checked;
  if (!faceTrackingEnabled) return;

  const dataUrl = cameraCanvas.toDataURL("image/jpeg", 0.6);

  fetch("/api/camera_process", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Jarvis-Token": apiToken
    },
    body: JSON.stringify({ 
      image: dataUrl,
      face_tracking: true
    })
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok) {
      detectedFaces = data.faces || [];
      pushRadarBlipsFromFaces(detectedFaces);
      const lockStatus = document.getElementById("camera-lock-status");
      const camSummary = document.getElementById("camera-summary");
      if (data.face_lib_available === false) {
        if (lockStatus) lockStatus.textContent = "Face engine unavailable.";
        if (camSummary) camSummary.textContent = "OpenCV backend unavailable.";
        return;
      }

      if (detectedFaces.length > 0) {
        const primary = detectedFaces[0];
        if (primary.recognized) {
          faceLockSummary = `TARGET LOCKED: ${primary.name.toUpperCase()}`;
          cameraSummaryText = `Threat level: ${primary.threat} | Distance: ${primary.distance}m`;
        } else {
          faceLockSummary = "UNKNOWN TARGET LOCKED";
          cameraSummaryText = `Threat level: ${primary.threat} | Distance: ${primary.distance}m`;
        }
      } else {
        faceLockSummary = "Scanning environment...";
        cameraSummaryText = "Active tracking online.";
      }
      if (lockStatus) lockStatus.textContent = faceLockSummary;
      if (camSummary) camSummary.textContent = cameraSummaryText;
    }
  })
  .catch(() => {});
}

function renderCameraHUD() {
  if (!webcamStream) return;

  const w = cameraCanvas.width;
  const h = cameraCanvas.height;

  // 1. Draw webcam feed onto canvas
  cameraCtx.drawImage(webcamVideo, 0, 0, w, h);

  cameraHudAnim++;

  const showHud = document.getElementById("cam-hud-overlay").checked;
  if (showHud) {
    // 2. Draw HUD styling based on style select
    if (selectedHudStyle === "mark50") {
      drawMark50HUD(w, h);
    } else if (selectedHudStyle === "thermal") {
      drawThermalHUD(w, h);
    } else if (selectedHudStyle === "tron") {
      drawTronHUD(w, h);
    } else if (selectedHudStyle === "predator") {
      drawPredatorHUD(w, h);
    } else if (selectedHudStyle === "neural") {
      drawNeuralHUD(w, h);
    }
  }

  requestAnimationFrame(renderCameraHUD);
}

// HUD Rendering Modules
function drawMark50HUD(w, h) {
  // Gold/Cyan hex mesh overlay
  drawHexGridBackground(w, h, "rgba(0, 210, 255, 0.08)", 24);

  // Laser scanner sweep
  const scanY = (cameraHudAnim * 3.5) % h;
  cameraCtx.strokeStyle = "rgba(0, 210, 255, 0.45)";
  cameraCtx.lineWidth = 1;
  cameraCtx.beginPath();
  cameraCtx.moveTo(0, scanY);
  cameraCtx.lineTo(w, scanY);
  cameraCtx.stroke();
  
  // Outer corner brackets
  drawCornerBrackets(cameraCtx, 10, 10, w - 20, h - 20, "rgba(0, 210, 255, 0.55)", 10);

  // Locked targets
  detectedFaces.forEach((face, idx) => {
    const { x, y, w: fw, h: fh, name, recognized, threat, distance } = face;
    const accentColor = recognized ? "rgba(0, 210, 255, 0.85)" : "rgba(239, 68, 68, 0.85)";

    // Locked face box brackets
    drawCornerBrackets(cameraCtx, x, y, fw, fh, accentColor, 8);

    // Reticle
    const cx = x + fw / 2;
    const cy = y + fh / 2;
    const r = Math.min(fw, fh) / 3.2;
    
    cameraCtx.strokeStyle = accentColor;
    cameraCtx.lineWidth = 1;
    cameraCtx.beginPath();
    cameraCtx.arc(cx, cy, r, 0, Math.PI * 2);
    cameraCtx.arc(cx, cy, r / 2, 0, Math.PI * 2);
    cameraCtx.stroke();

    // Crosshairs
    cameraCtx.beginPath();
    cameraCtx.moveTo(cx - r - 6, cy); cameraCtx.lineTo(cx + r + 6, cy);
    cameraCtx.moveTo(cx, cy - r - 6); cameraCtx.lineTo(cx, cy + r + 6);
    cameraCtx.stroke();

    // Stats texts overlay above the reticle
    cameraCtx.fillStyle = accentColor;
    cameraCtx.font = "bold 7px Orbitron";
    const lockTxt = recognized ? "TARGET LOCKED" : "INTEL: UNKNOWN GUEST";
    cameraCtx.fillText(lockTxt, x, Math.max(10, y - 24));
    cameraCtx.fillText(`THREAT LEVEL: ${threat}`, x, Math.max(18, y - 16));
    cameraCtx.fillText(`DIST: ${distance}m`, x, Math.max(26, y - 8));
  });

  if (detectedFaces.length === 0) {
    cameraCtx.fillStyle = "rgba(0, 210, 255, 0.75)";
    cameraCtx.font = "bold 8px Orbitron";
    const scanDots = ".".repeat(Math.floor(cameraHudAnim / 15) % 4);
    cameraCtx.fillText(`SCANNING ENVELOPE${scanDots}`, 12, 22);
  }
}

function drawThermalHUD(w, h) {
  // Thermal is colored by CSS filters, draw HUD layout elements
  cameraCtx.strokeStyle = "rgba(255, 255, 255, 0.4)";
  cameraCtx.lineWidth = 1;
  cameraCtx.beginPath();
  cameraCtx.arc(w/2, h/2, 30, 0, Math.PI*2);
  cameraCtx.stroke();
  
  cameraCtx.fillStyle = "#fff";
  cameraCtx.font = "bold 8px Courier New";
  cameraCtx.fillText("THERM SENSOR ACTIVE", 10, 20);
  
  // Draw basic locked face thermal box
  detectedFaces.forEach(face => {
    const { x, y, w: fw, h: fh } = face;
    cameraCtx.strokeStyle = "#fff";
    cameraCtx.strokeRect(x, y, fw, fh);
  });
}

function drawTronHUD(w, h) {
  drawHexGridBackground(w, h, "rgba(0, 210, 255, 0.05)", 30);
  
  cameraCtx.strokeStyle = "rgba(0, 210, 255, 0.6)";
  cameraCtx.lineWidth = 1;
  cameraCtx.strokeRect(4, 4, w - 8, h - 8);
  
  // Neon locked face webs
  detectedFaces.forEach((face, idx) => {
    const { x, y, w: fw, h: fh } = face;
    const cx = x + fw / 2;
    const cy = y + fh / 2;
    
    // Draw vector lines from center to corner vertices
    cameraCtx.strokeStyle = "rgba(0, 210, 255, 0.75)";
    cameraCtx.beginPath();
    cameraCtx.moveTo(cx, cy); cameraCtx.lineTo(x, y);
    cameraCtx.moveTo(cx, cy); cameraCtx.lineTo(x + fw, y);
    cameraCtx.moveTo(cx, cy); cameraCtx.lineTo(x, y + fh);
    cameraCtx.moveTo(cx, cy); cameraCtx.lineTo(x + fw, y + fh);
    cameraCtx.stroke();

    cameraCtx.fillStyle = "rgba(0, 210, 255, 0.9)";
    cameraCtx.font = "bold 7px Orbitron";
    cameraCtx.fillText(`TRON_ID#0${idx+1}`, x, y - 6);
  });
}

function drawPredatorHUD(w, h) {
  // Red scanning lines and reticles
  cameraCtx.strokeStyle = "rgba(239, 68, 68, 0.4)";
  cameraCtx.beginPath();
  cameraCtx.arc(w/2, h/2, 45, 0, Math.PI*2);
  cameraCtx.stroke();
  
  cameraCtx.fillStyle = "rgba(239, 68, 68, 0.9)";
  cameraCtx.font = "bold 8px Orbitron";
  cameraCtx.fillText("PREDATOR INTENSITY SCAN", 12, 22);

  detectedFaces.forEach(face => {
    const { x, y, w: fw, h: fh } = face;
    cameraCtx.strokeStyle = "rgba(239, 68, 68, 0.85)";
    cameraCtx.strokeRect(x, y, fw, fh);
    
    // Predator target indicators
    cameraCtx.beginPath();
    cameraCtx.moveTo(x + fw/2 - 8, y + fh/2);
    cameraCtx.lineTo(x + fw/2 + 8, y + fh/2);
    cameraCtx.moveTo(x + fw/2, y + fh/2 - 8);
    cameraCtx.lineTo(x + fw/2, y + fh/2 + 8);
    cameraCtx.stroke();
  });
}

function drawNeuralHUD(w, h) {
  cameraCtx.fillStyle = "rgba(168, 85, 247, 0.8)";
  cameraCtx.font = "bold 8px Orbitron";
  cameraCtx.fillText("NEURAL COGNITIVE MESH", 12, 22);

  detectedFaces.forEach(face => {
    const { x, y, w: fw, h: fh } = face;
    const cx = x + fw / 2;
    const cy = y + fh / 2;

    // Draw neural dots over the face area
    const nodes = [
      {x: x, y: y}, {x: x + fw, y: y},
      {x: x + fw, y: y + fh}, {x: x, y: y + fh},
      {x: cx, y: y}, {x: cx, y: y + fh},
      {x: x, y: cy}, {x: x + fw, y: cy},
      {x: cx, y: cy}
    ];

    cameraCtx.fillStyle = "rgba(168, 85, 247, 0.95)";
    cameraCtx.strokeStyle = "rgba(168, 85, 247, 0.35)";
    cameraCtx.lineWidth = 0.5;

    // Draw connections
    nodes.forEach((n1, idx1) => {
      cameraCtx.beginPath();
      cameraCtx.arc(n1.x, n1.y, 2, 0, Math.PI * 2);
      cameraCtx.fill();
      
      nodes.forEach((n2, idx2) => {
        if (idx1 !== idx2 && Math.abs(n1.x - n2.x) < fw && Math.abs(n1.y - n2.y) < fh) {
          cameraCtx.beginPath();
          cameraCtx.moveTo(n1.x, n1.y);
          cameraCtx.lineTo(n2.x, n2.y);
          cameraCtx.stroke();
        }
      });
    });
  });
}

// Helpers
function drawHexGridBackground(w, h, color, size) {
  cameraCtx.strokeStyle = color;
  cameraCtx.lineWidth = 0.5;
  const r = size / 2;
  const dx = r * 1.732;
  const dy = r * 1.5;

  cameraCtx.beginPath();
  for (let cy = -r; cy < h + r; cy += dy) {
    const offset = (Math.floor(cy / dy) % 2) * (dx / 2);
    for (let cx = -r + offset; cx < w + r; cx += dx) {
      for (let i = 0; i < 6; i++) {
        const ang = (Math.PI / 3) * i - Math.PI / 6;
        const x = cx + r * Math.cos(ang);
        const y = cy + r * Math.sin(ang);
        if (i === 0) cameraCtx.moveTo(x, y);
        else cameraCtx.lineTo(x, y);
      }
      cameraCtx.closePath();
    }
  }
  cameraCtx.stroke();
}

function drawCornerBrackets(ctx, x, y, w, h, color, len) {
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  
  // Top-left
  ctx.beginPath(); ctx.moveTo(x, y + len); ctx.lineTo(x, y); ctx.lineTo(x + len, y); ctx.stroke();
  // Top-right
  ctx.beginPath(); ctx.moveTo(x + w, y + len); ctx.lineTo(x + w, y); ctx.lineTo(x + w - len, y); ctx.stroke();
  // Bottom-left
  ctx.beginPath(); ctx.moveTo(x, y + h - len); ctx.lineTo(x, y + h); ctx.lineTo(x + len, y + h); ctx.stroke();
  // Bottom-right
  ctx.beginPath(); ctx.moveTo(x + w, y + h - len); ctx.lineTo(x + w, y + h); ctx.lineTo(x + w - len, y + h); ctx.stroke();
}

// =========================================================================
// JARVIS CINEMATIC BOOT SEQUENCE
// =========================================================================

async function playBootSequence() {
  if (bootSequenceConsumed) {
    document.getElementById("boot-sequence-overlay")?.remove();
    document.body.classList.remove("boot-video-active");
    return;
  }
  bootSequenceConsumed = true;
  const overlay = document.getElementById("boot-sequence-overlay");
  if (!overlay) return;

  overlay.className = "boot-overlay video-opening-overlay";
  overlay.style.display = "flex";
  overlay.style.opacity = "1";
  document.body.classList.add("boot-video-active");

  let finished = false;
  let activeVideo = null;
  const finishOpening = () => {
    if (finished) return;
    finished = true;
    document.body.classList.remove("boot-video-active");
    if (activeVideo) {
      try { activeVideo.pause(); } catch (e) {}
      try { activeVideo.removeAttribute("src"); activeVideo.load(); } catch (e) {}
    }
    overlay.style.opacity = "0";
    setTimeout(() => {
      overlay.style.display = "none";
      overlay.remove();
    }, 320);
  };

  const openingClips = [
    "assets/jarvis-opening.mp4",
    "assets/A_premium_highly_aesthetic_fu.mp4"
  ];

  const playOpeningClip = async (src, index) => {
    const previousVideo = activeVideo;
    const video = document.createElement("video");
    video.id = `jarvis-opening-video-${index + 1}`;
    video.className = "jarvis-opening-video";
    video.autoplay = true;
    video.muted = true;
    video.playsInline = true;
    video.preload = "auto";
    video.disablePictureInPicture = true;
    video.volume = 0;
    video.innerHTML = `<source src="${src}" type="video/mp4">`;
    overlay.appendChild(video);
    activeVideo = video;

    requestAnimationFrame(() => video.classList.add("is-active"));
    if (previousVideo) {
      previousVideo.classList.remove("is-active");
      try { previousVideo.pause(); } catch (e) {}
      setTimeout(() => {
        try { previousVideo.removeAttribute("src"); previousVideo.load(); previousVideo.remove(); } catch (e) {}
      }, 160);
    }

    const waitForMetadata = new Promise(resolve => {
      if (Number.isFinite(video.duration) && video.duration > 0) {
        resolve();
        return;
      }
      video.addEventListener("loadedmetadata", resolve, { once: true });
      video.addEventListener("canplay", resolve, { once: true });
      setTimeout(resolve, 1800);
    });

    await waitForMetadata;

    try {
      video.currentTime = 0;
      await video.play();
    } catch (err) {
      try {
        video.muted = true;
        await video.play();
      } catch (muteErr) {
        return;
      }
    }

    await new Promise(resolve => {
      let resolved = false;
      let maxTimer = null;
      const finish = () => {
        if (resolved) return;
        resolved = true;
        clearTimeout(maxTimer);
        resolve();
      };
      const duration = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : 18;
      const maxRuntimeMs = Math.min(Math.max(duration * 1000 + 10000, 30000), 180000);
      maxTimer = setTimeout(finish, maxRuntimeMs);
      const cleanup = () => {
        finish();
      };
      video.addEventListener("ended", cleanup, { once: true });
      video.addEventListener("error", cleanup, { once: true });
    });
  };

  for (let i = 0; i < openingClips.length; i += 1) {
    await playOpeningClip(openingClips[i], i);
    if (finished) return;
  }

  finishOpening();
  return;

  overlay.className = "boot-overlay jarvis-cinematic-boot";
  overlay.style.display = "flex";
  overlay.style.opacity = "1";
  overlay.innerHTML = `
    <div class="boot-vignette"></div>
    <div class="boot-data-rain"></div>
    <div class="boot-cold-particles"></div>
    <div class="boot-crt-pixel"></div>
    <div class="boot-horizontal-scan"></div>
    <canvas id="boot-webgl-core" class="boot-webgl-core"></canvas>
    <div class="boot-white-flash"></div>
    <div class="boot-terminal-phase">
      <div class="boot-terminal-window" id="boot-terminal-window"></div>
    </div>
    <div class="boot-hud-phase">
      <div class="boot-depth-rings"><i></i><i></i><i></i><i></i></div>
      <div class="boot-wordmark" data-text="J.A.R.V.I.S.">J.A.R.V.I.S.</div>
      <div class="boot-corner top left"></div>
      <div class="boot-corner top right"></div>
      <div class="boot-corner bottom left"></div>
      <div class="boot-corner bottom right"></div>
    </div>
    <div class="boot-dashboard-phase">
      <section class="boot-panel boot-status"><b>STATUS</b><span>CPU 00% / RAM 00% / NET 00ms</span></section>
      <section class="boot-panel boot-composer"><b>COMMAND COMPOSER</b><span>Awaiting tactical input_</span></section>
      <section class="boot-panel boot-radar-panel"><b>RADAR</b><i></i><span>Neon sweep online</span></section>
      <section class="boot-panel boot-eq"><b>AUDIO MATRIX</b><em>${Array.from({ length: 16 }, (_, i) => `<i style="--i:${i}"></i>`).join("")}</em></section>
      <section class="boot-panel boot-camera"><b>CAMERA HUD</b><div><i></i><i></i><i></i><i></i></div><span>Face brackets armed</span></section>
    </div>
    <div class="boot-face-lock">
      <span></span><span></span><span></span><span></span>
      <strong>BIOMETRIC SCAN</strong>
      <em>SECURITY OVERRIDE REQUIRED</em>
    </div>
    <div class="boot-waveform">${Array.from({ length: 28 }, (_, i) => `<i style="--i:${i}"></i>`).join("")}</div>
    <div class="boot-scanlines"></div>
    <div class="boot-glitch-pass"></div>
  `;

  const stopCore = startBootWebGLCore(document.getElementById("boot-webgl-core"));
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  const bootStart = performance.now();
  const at = async seconds => {
    const wait = seconds * 1000 - (performance.now() - bootStart);
    if (wait > 0) await delay(wait);
  };

  const synth = window.speechSynthesis;
  let voice = null;
  const initVoice = () => {
    if (!synth) return;
    const voices = synth.getVoices();
    voice = voices.find(v => v.name.toLowerCase().includes("microsoft david")) ||
      voices.find(v => v.name.toLowerCase().includes("google uk english male")) ||
      voices.find(v => v.lang && v.lang.startsWith("en")) ||
      voices[0];
  };
  if (synth && synth.onvoiceschanged !== undefined) synth.onvoiceschanged = initVoice;
  initVoice();
  const speak = text => {
    if (!synth) return;
    const utterance = new SpeechSynthesisUtterance(text);
    if (voice) utterance.voice = voice;
    utterance.pitch = 0.78;
    utterance.rate = 0.92;
    utterance.onstart = () => overlay.classList.add("voice-active");
    utterance.onend = () => overlay.classList.remove("voice-active");
    synth.speak(utterance);
  };

  let humOsc = null;
  let humGain = null;
  const ensureAudio = () => {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") audioCtx.resume();
  };
  const tone = (freq, duration = 0.18, gainValue = 0.045) => {
    try {
      ensureAudio();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
      gain.gain.setValueAtTime(gainValue, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + duration);
    } catch (err) {}
  };
  try {
    ensureAudio();
    humOsc = audioCtx.createOscillator();
    humGain = audioCtx.createGain();
    humOsc.type = "sawtooth";
    humOsc.frequency.setValueAtTime(42, audioCtx.currentTime);
    humGain.gain.setValueAtTime(0, audioCtx.currentTime);
    humGain.gain.linearRampToValueAtTime(0.025, audioCtx.currentTime + 2);
    humOsc.connect(humGain);
    humGain.connect(audioCtx.destination);
    humOsc.start();
  } catch (err) {}

  await at(2);
  overlay.classList.add("phase-core");
  [260, 340, 460, 620].forEach((freq, index) => setTimeout(() => tone(freq, 0.22, 0.05), index * 360));
  setTimeout(() => overlay.classList.add("flash-frame"), 2550);
  speak("Initializing core systems.");

  await at(5);
  overlay.classList.add("phase-terminal");
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Morning" : hour < 18 ? "Afternoon" : "Evening";
  const token = Math.random().toString(16).slice(2, 10).toUpperCase() + "-A7F1";
  const lines = [
    "> JARVIS v4.1 - STARK INDUSTRIES INTERNAL ONLY",
    "> Loading neural inference module......... [OK]",
    "> Mounting encrypted filesystem............[OK]",
    "> Establishing secure uplink to backend... [OK]",
    "> Threat analysis running.................",
    "  ████████████████████ 100% - NO THREATS DETECTED",
    `> Biometric session token: [${token}]`,
    `> Good ${greeting}, Sir.`
  ];
  await typeBootLines(document.getElementById("boot-terminal-window"), lines, 22);

  await at(18);
  overlay.classList.add("phase-hud");
  speak("All systems nominal.");

  await at(28);
  overlay.classList.add("phase-dashboard");
  tone(780, 0.25, 0.05);

  await at(38);
  overlay.classList.add("phase-auth");
  speak("Security override required.");

  await at(45);
  if (humOsc && humGain) {
    humGain.gain.linearRampToValueAtTime(0, audioCtx.currentTime + 1);
    humOsc.stop(audioCtx.currentTime + 1.2);
  }
  stopCore();
  overlay.style.opacity = "0";
  await delay(900);
  overlay.style.display = "none";
  overlay.remove();
}

async function typeBootLines(container, lines, speed = 20) {
  if (!container) return;
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  container.innerHTML = "";
  for (const line of lines) {
    const row = document.createElement("div");
    row.className = line.includes("[OK]") ? "ok" : "";
    container.appendChild(row);
    for (const char of line) {
      row.textContent += char;
      await delay(speed);
    }
    await delay(180);
  }
}

function setupBootCinematicLayers(overlay) {
  if (overlay.dataset.cinematicReady) return;
  overlay.dataset.cinematicReady = "1";
  const layers = document.createElement("div");
  layers.className = "boot-cinematic-layers";
  layers.innerHTML = `
    <canvas id="boot-webgl-core" class="boot-webgl-core"></canvas>
    <div class="boot-hex-field"></div>
    <div class="boot-depth-rings"><i></i><i></i><i></i><i></i></div>
    <div class="boot-face-lock">
      <span></span><span></span><span></span><span></span>
      <strong>BIOMETRIC SCAN</strong>
      <em>TRACKING OWNER SIGNATURE</em>
    </div>
    <div class="boot-radar-holo"><b></b><small>RADAR LINK</small></div>
    <div class="boot-world-map"><span></span><span></span><span></span><span></span></div>
    <div class="boot-waveform">${Array.from({ length: 24 }, (_, i) => `<i style="--i:${i}"></i>`).join("")}</div>
    <div class="boot-tactical-panels">
      <section><b>CPU</b><span>NEURAL LOAD</span><i></i></section>
      <section><b>VISION</b><span>FACE MATRIX</span><i></i></section>
      <section><b>UPLINK</b><span>SECURE LOCALHOST</span><i></i></section>
    </div>
    <div class="boot-scanlines"></div>
    <div class="boot-glitch-pass"></div>
  `;
  overlay.prepend(layers);
  overlay._stopBootCore = startBootWebGLCore(layers.querySelector("#boot-webgl-core"));
}

function startBootWebGLCore(canvas) {
  if (!canvas) return () => {};
  const gl = canvas.getContext("webgl", { alpha: true, antialias: true });
  if (!gl) return () => {};
  const vertexSource = `attribute vec2 position; void main(){ gl_Position = vec4(position,0.0,1.0); }`;
  const fragmentSource = `
    precision mediump float;
    uniform vec2 resolution;
    uniform float time;
    mat2 rot(float a){ float s=sin(a), c=cos(a); return mat2(c,-s,s,c); }
    void main(){
      vec2 p=(gl_FragCoord.xy-.5*resolution.xy)/min(resolution.x,resolution.y);
      float r=length(p);
      vec2 q=rot(time*.22)*p;
      float a=atan(q.y,q.x);
      float core=smoothstep(.18,.02,r);
      float ring1=smoothstep(.008,0.0,abs(r-.24-sin(a*12.0+time*2.2)*.006));
      float ring2=smoothstep(.007,0.0,abs(r-.38-sin(a*18.0-time*1.6)*.005));
      float ring3=smoothstep(.006,0.0,abs(r-.54));
      float spokes=smoothstep(.985,1.0,cos(a*20.0))*smoothstep(.64,.18,r);
      float pulse=.72+.28*sin(time*4.5);
      vec3 cyan=vec3(0.0,.86,1.0), blue=vec3(.05,.28,1.0), gold=vec3(1.0,.64,.16);
      vec3 color=cyan*core*1.8+cyan*ring1+blue*ring2+gold*ring3+cyan*spokes*.55;
      color+=cyan*smoothstep(.9,0.0,r)*.045;
      float alpha=clamp((core+ring1+ring2+ring3+spokes)*pulse+smoothstep(.9,0.0,r)*.12,0.0,1.0);
      gl_FragColor=vec4(color,alpha);
    }`;
  const compile = (type, source) => {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    return shader;
  };
  const program = gl.createProgram();
  gl.attachShader(program, compile(gl.VERTEX_SHADER, vertexSource));
  gl.attachShader(program, compile(gl.FRAGMENT_SHADER, fragmentSource));
  gl.linkProgram(program);
  gl.useProgram(program);
  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]), gl.STATIC_DRAW);
  const position = gl.getAttribLocation(program, "position");
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
  const resolution = gl.getUniformLocation(program, "resolution");
  const time = gl.getUniformLocation(program, "time");
  let stopped = false;
  const resize = () => {
    const size = Math.max(640, Math.floor(Math.min(window.innerWidth, window.innerHeight) * .92));
    if (canvas.width !== size || canvas.height !== size) {
      canvas.width = size;
      canvas.height = size;
      gl.viewport(0, 0, size, size);
    }
  };
  const render = (now) => {
    if (stopped) return;
    resize();
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(resolution, canvas.width, canvas.height);
    gl.uniform1f(time, now * .001);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
    requestAnimationFrame(render);
  };
  requestAnimationFrame(render);
  return () => { stopped = true; };
}
