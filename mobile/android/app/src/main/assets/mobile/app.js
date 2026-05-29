const $ = (id) => document.getElementById(id);

const state = {
  serverUrl: "",
  apiToken: "",
  statsTimer: null,
  callsTimer: null,
  activeCall: null,
  selectedImage: "",
  companion: {
    connected: false,
    stream: null,
    frameTimer: null,
    locationWatch: null,
    audioRecorder: null,
  },
};

function nativeAvailable() {
  return typeof window.JarvisAndroid !== "undefined";
}

function nativeGet(key) {
  try {
    return nativeAvailable() ? window.JarvisAndroid.getSetting(key) : "";
  } catch {
    return "";
  }
}

function nativeSet(key, value) {
  try {
    if (nativeAvailable()) window.JarvisAndroid.setSetting(key, value || "");
  } catch {}
}

function nativeJson(methodName) {
  try {
    if (!nativeAvailable() || typeof window.JarvisAndroid[methodName] !== "function") return null;
    const raw = window.JarvisAndroid[methodName]();
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function normalizeUrl(value) {
  let url = String(value || "").trim();
  if (!url) return "";
  if (!/^https?:\/\//i.test(url)) url = `http://${url}`;
  return url.replace(/\/+$/, "");
}

function loadSettings() {
  state.serverUrl = normalizeUrl(nativeGet("server_url") || localStorage.getItem("server_url") || "");
  state.apiToken = nativeGet("api_token") || localStorage.getItem("api_token") || "";
  $("serverUrl").value = state.serverUrl;
  $("apiToken").value = state.apiToken;
  $("settingsServerUrl").value = state.serverUrl;
  $("settingsApiToken").value = state.apiToken;
}

function saveSettings() {
  state.serverUrl = normalizeUrl($("serverUrl").value || $("settingsServerUrl").value);
  state.apiToken = $("apiToken").value || $("settingsApiToken").value || "";
  localStorage.setItem("server_url", state.serverUrl);
  localStorage.setItem("api_token", state.apiToken);
  nativeSet("server_url", state.serverUrl);
  nativeSet("api_token", state.apiToken);
  $("serverUrl").value = state.serverUrl;
  $("settingsServerUrl").value = state.serverUrl;
  $("apiToken").value = state.apiToken;
  $("settingsApiToken").value = state.apiToken;
  setSetupMessage("Settings saved.");
}

function setSetupMessage(text, isError = false) {
  $("setupMessage").textContent = text || "";
  $("setupMessage").style.color = isError ? "var(--red)" : "var(--muted)";
}

function setConnection(ok, label) {
  const pill = $("connectionPill");
  pill.textContent = label || (ok ? "Online" : "Offline");
  pill.classList.toggle("ok", !!ok);
  pill.classList.toggle("warn", !ok);
}

function requireServer() {
  if (!state.serverUrl) {
    throw new Error("Server URL missing. Add your HTTPS Ngrok URL or PC LAN URL in settings.");
  }
}

function isLocalUrl(url) {
  return /^http:\/\/(localhost|127\.0\.0\.1|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/i.test(url || "");
}

function requireCompanionUrl() {
  requireServer();
  if (!/^https:\/\//i.test(state.serverUrl) && !isLocalUrl(state.serverUrl)) {
    throw new Error("Use HTTPS Ngrok URL for remote access. Local Wi-Fi HTTP is allowed only on private LAN.");
  }
}

async function api(path, options = {}) {
  requireServer();
  const headers = {
    ...(options.headers || {}),
    "X-Jarvis-Token": state.apiToken || "jarvis",
  };
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const res = await fetch(`${state.serverUrl}${path}`, { ...options, headers });
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { ok: false, error: text };
  }
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `HTTP ${res.status}`);
  }
  return data;
}

async function companionApi(path, body) {
  requireCompanionUrl();
  return api(path, {
    method: "POST",
    body: JSON.stringify(body || {}),
  });
}

function setCompanionMessage(text, isError = false) {
  $("companionMessage").textContent = text || "";
  $("companionMessage").style.color = isError ? "var(--red)" : "var(--muted)";
}

function setCompanionStatus(connected, label) {
  state.companion.connected = !!connected;
  const status = $("companionStatus");
  status.textContent = label || (connected ? "Connected" : "Disconnected");
  status.classList.toggle("ok", !!connected);
}

function renderPermissionStatus(status) {
  const data = status || {};
  $("permCamera").textContent = `Camera: ${data.camera ? "granted" : "needed"}`;
  $("permMic").textContent = `Mic: ${data.microphone ? "granted" : "needed"}`;
  $("permLocation").textContent = `Location: ${(data.fine_location || data.coarse_location) ? "granted" : "needed"}`;
  $("permStorage").textContent = `Notify/storage: ${(data.notifications && data.storage) ? "granted" : "needed"}`;
}

function refreshCompanionPermissions() {
  const status = nativeJson("companionPermissionStatus");
  if (status) renderPermissionStatus(status);
}

function requestCompanionPermissions() {
  if (nativeAvailable() && window.JarvisAndroid.requestCompanionPermissions) {
    window.JarvisAndroid.requestCompanionPermissions();
    setCompanionMessage("Android permission dialogs opening. Grant only what you want to share.");
    return;
  }
  setCompanionMessage("Use the browser permission dialogs when Connect live is tapped.");
}

window.onCompanionPermissionsUpdated = (rawStatus) => {
  try {
    renderPermissionStatus(JSON.parse(rawStatus || "{}"));
  } catch {
    refreshCompanionPermissions();
  }
};

window.onNativeCompanionTest = (ok, message) => {
  setCompanionStatus(false, ok ? "Server reachable" : "Disconnected");
  setCompanionMessage(message || (ok ? "Server reachable." : "Server test failed."), !ok);
};

function testCompanionLink() {
  saveSettings();
  try {
    requireCompanionUrl();
  } catch (err) {
    setCompanionMessage(err.message, true);
    return;
  }
  if (nativeAvailable() && window.JarvisAndroid.testCompanionConnection) {
    window.JarvisAndroid.testCompanionConnection(state.serverUrl, state.apiToken || "");
    setCompanionMessage("Testing connection with native Retrofit...");
    return;
  }
  testConnection();
}

function dataUrlFromBlob(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

function startFrameLoop(video) {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  state.companion.frameTimer = setInterval(async () => {
    if (!state.companion.connected || !ctx || video.readyState < 2) return;
    const w = Math.min(640, video.videoWidth || 640);
    const h = Math.max(1, Math.round(w * ((video.videoHeight || 480) / (video.videoWidth || 640))));
    canvas.width = w;
    canvas.height = h;
    ctx.drawImage(video, 0, 0, w, h);
    try {
      await companionApi("/api/mobile/frame", {
        image: canvas.toDataURL("image/jpeg", 0.58),
        width: w,
        height: h,
        captured_at: new Date().toISOString(),
      });
    } catch (err) {
      setCompanionMessage(`Frame send failed: ${err.message}`, true);
    }
  }, 1500);
}

function startAudioLoop(stream) {
  if (!("MediaRecorder" in window)) {
    setCompanionMessage("Camera/location active. Audio recorder is unavailable on this WebView.", true);
    return;
  }
  const audioTracks = stream.getAudioTracks();
  if (!audioTracks.length) return;
  const audioStream = new MediaStream(audioTracks);
  const recorder = new MediaRecorder(audioStream);
  state.companion.audioRecorder = recorder;
  recorder.ondataavailable = async (event) => {
    if (!state.companion.connected || !event.data || !event.data.size) return;
    try {
      await companionApi("/api/mobile/audio", {
        audio: await dataUrlFromBlob(event.data),
        mime_type: event.data.type || "audio/webm",
        captured_at: new Date().toISOString(),
      });
    } catch (err) {
      setCompanionMessage(`Audio send failed: ${err.message}`, true);
    }
  };
  recorder.start(2500);
}

function startLocationLoop() {
  if (!navigator.geolocation) {
    setCompanionMessage("Camera/audio active. Location is unavailable on this device.", true);
    return;
  }
  state.companion.locationWatch = navigator.geolocation.watchPosition(
    async (pos) => {
      if (!state.companion.connected) return;
      try {
        await companionApi("/api/mobile/location", {
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy_m: pos.coords.accuracy,
          altitude_m: pos.coords.altitude,
          speed_mps: pos.coords.speed,
          heading_deg: pos.coords.heading,
          captured_at: new Date(pos.timestamp).toISOString(),
        });
      } catch (err) {
        setCompanionMessage(`Location send failed: ${err.message}`, true);
      }
    },
    (err) => setCompanionMessage(`Location permission/error: ${err.message}`, true),
    { enableHighAccuracy: true, maximumAge: 3000, timeout: 12000 }
  );
}

async function connectCompanion() {
  saveSettings();
  try {
    requireCompanionUrl();
    await api("/api/health");
    if (nativeAvailable() && window.JarvisAndroid.startCompanionService) {
      const raw = window.JarvisAndroid.startCompanionService(state.serverUrl, state.apiToken || "");
      const result = raw ? JSON.parse(raw) : { ok: false, message: "No native service result." };
      if (!result.ok) throw new Error(result.message || "Foreground service failed.");
      setCompanionStatus(true, "Foreground live");
      setConnection(true, "Online");
      setCompanionMessage("Foreground sharing is ON. A permanent notification is visible; Disconnect stops it.");
      return;
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 640 }, height: { ideal: 480 } },
      audio: true,
    });
    state.companion.stream = stream;
    const preview = $("companionPreview");
    preview.srcObject = stream;
    preview.classList.remove("hidden");
    setCompanionStatus(true, "Connected");
    setConnection(true, "Online");
    setCompanionMessage("Live sharing is ON. Disconnect anytime to stop camera, mic, and location.");
    await companionApi("/api/mobile/session", { status: "connected", connected_at: new Date().toISOString() });
    startFrameLoop(preview);
    startAudioLoop(stream);
    startLocationLoop();
  } catch (err) {
    disconnectCompanion(false);
    setCompanionMessage(err.message, true);
  }
}

async function disconnectCompanion(notify = true) {
  if (nativeAvailable() && window.JarvisAndroid.stopCompanionService) {
    try {
      window.JarvisAndroid.stopCompanionService();
    } catch {}
  }
  if (state.companion.frameTimer) clearInterval(state.companion.frameTimer);
  state.companion.frameTimer = null;
  if (state.companion.locationWatch !== null && navigator.geolocation) {
    navigator.geolocation.clearWatch(state.companion.locationWatch);
  }
  state.companion.locationWatch = null;
  try {
    if (state.companion.audioRecorder && state.companion.audioRecorder.state !== "inactive") {
      state.companion.audioRecorder.stop();
    }
  } catch {}
  state.companion.audioRecorder = null;
  if (state.companion.stream) {
    state.companion.stream.getTracks().forEach((track) => track.stop());
  }
  state.companion.stream = null;
  const preview = $("companionPreview");
  preview.srcObject = null;
  preview.classList.add("hidden");
  setCompanionStatus(false, "Disconnected");
  if (notify && state.serverUrl) {
    try {
      await companionApi("/api/mobile/session", { status: "disconnected", disconnected_at: new Date().toISOString() });
    } catch {}
  }
  setCompanionMessage("Live sharing is OFF.");
}

function addBubble(text, who = "jarvis") {
  const log = $("chatLog");
  const bubble = document.createElement("div");
  bubble.className = `bubble ${who}`;
  bubble.textContent = text;
  log.appendChild(bubble);
  log.scrollTop = log.scrollHeight;
}

function speak(text) {
  const clean = String(text || "").slice(0, 650);
  if (!clean) return;
  try {
    if (nativeAvailable()) {
      window.JarvisAndroid.speak(clean);
      return;
    }
  } catch {}
  if ("speechSynthesis" in window) {
    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.lang = "hi-IN";
    utterance.rate = 1.02;
    speechSynthesis.cancel();
    speechSynthesis.speak(utterance);
  }
}

async function testConnection() {
  try {
    saveSettings();
    const data = await api("/api/health");
    setConnection(true, "Online");
    setSetupMessage(`Connected: ${data.name || "JARVIS"}`);
    $("setupCard").classList.add("hidden");
    addBubble("Mobile connected to JARVIS.", "jarvis");
    refreshStats();
    startCallPolling();
  } catch (err) {
    setConnection(false, "Offline");
    setSetupMessage(err.message, true);
  }
}

async function sendCommand(command) {
  const text = String(command || $("commandInput").value || "").trim();
  if (!text) return;
  addBubble(text, "user");
  $("commandInput").value = "";
  if (tryMobileCommand(text)) return;
  try {
    const data = await api("/api/command", {
      method: "POST",
      body: JSON.stringify({ command: text, speak: false, allow_interactive: false }),
    });
    const reply = data.reply || "Done.";
    addBubble(reply, "jarvis");
    speak(reply);
  } catch (err) {
    addBubble(err.message, "error");
    speak("Connection issue hai bhai.");
  }
}

function executeMobileCommand(command) {
  if (!nativeAvailable() || !window.JarvisAndroid.executeMobileCommand) {
    return null;
  }
  try {
    const raw = window.JarvisAndroid.executeMobileCommand(command);
    return raw ? JSON.parse(raw) : null;
  } catch (err) {
    return { handled: true, ok: false, message: err.message || "Mobile command failed." };
  }
}

function tryMobileCommand(command) {
  const result = executeMobileCommand(command);
  if (!result || !result.handled) return false;
  const msg = result.message || (result.ok ? "Mobile command done." : "Mobile command failed.");
  addBubble(msg, result.ok ? "jarvis" : "error");
  speak(msg);
  return true;
}

function refreshPhoneControl() {
  const status = nativeJson("mobileControlStatus");
  if (!status) {
    $("phoneControlStatus").textContent = "Open this inside JARVIS Android APK to use phone control.";
    return;
  }
  $("phoneControlStatus").textContent = [
    `Accessibility: ${status.accessibility_enabled ? "enabled" : "needed for tap/type/scroll"}`,
    status.message || "",
    "Try: instagram open karo, back, home, scroll down, click Search, type hello"
  ].filter(Boolean).join("\n");
}

function setupPhoneControl() {
  if (!nativeAvailable() || !window.JarvisAndroid.openAccessibilitySettings) {
    $("phoneControlStatus").textContent = "Phone control setup works only inside the Android APK.";
    return;
  }
  window.JarvisAndroid.openAccessibilitySettings();
  $("phoneControlStatus").textContent = "Android Accessibility settings opened. Enable JARVIS Phone Control.";
}

async function whatsappStatus() {
  try {
    const data = await api("/api/whatsapp/status");
    const wa = data.whatsapp || {};
    const node = wa.node || {};
    const msg = `WhatsApp bridge: ${wa.enabled ? "enabled" : "disabled"}\nMode: ${wa.mode || "unknown"}\nNode ready: ${node.ready ? "yes" : "no"}`;
    addBubble(msg, "jarvis");
    speak(msg);
  } catch (err) {
    addBubble(err.message, "error");
  }
}

function setCallMessage(text, isError = false) {
  $("callMessage").textContent = text || "";
  $("callMessage").style.color = isError ? "var(--red)" : "var(--muted)";
}

function showCall(call) {
  state.activeCall = call;
  $("callTitle").textContent = call.sender || "Unknown caller";
  $("callMeta").textContent = `WhatsApp ${call.call_type || "voice"} call • ${call.received_at || "now"}`;
  $("callType").textContent = call.is_video ? "Video" : "Voice";
  $("callReplyText").placeholder = `Reply to ${call.sender || "caller"}`;
  $("callCard").classList.remove("hidden");
}

function hideCall() {
  state.activeCall = null;
  $("callCard").classList.add("hidden");
  $("callReplyText").value = "";
  setCallMessage("");
}

async function refreshCalls() {
  if (!state.serverUrl) return;
  try {
    const data = await api("/api/whatsapp/calls");
    const calls = Array.isArray(data.calls) ? data.calls : [];
    if (calls.length) {
      const nextCall = calls[0];
      const oldId = state.activeCall?.call_id || "";
      showCall(nextCall);
      if (nextCall.call_id && nextCall.call_id !== oldId) {
        const text = `${nextCall.sender || "Kisi"} ka WhatsApp ${nextCall.call_type || "voice"} call aa raha hai.`;
        addBubble(text, "jarvis");
        speak(`${text} Reply karna hai to call card use karo.`);
      }
    } else {
      hideCall();
    }
  } catch (_err) {
    // Keep the normal chat/status UI calm if WhatsApp bridge is offline.
  }
}

function startCallPolling() {
  stopCallPolling();
  refreshCalls();
  state.callsTimer = setInterval(refreshCalls, 2000);
}

function stopCallPolling() {
  if (state.callsTimer) clearInterval(state.callsTimer);
  state.callsTimer = null;
}

async function handleCallAction(action) {
  const call = state.activeCall;
  if (!call?.call_id) {
    setCallMessage("No active call found.", true);
    return;
  }
  const text = $("callReplyText").value.trim();
  if (action === "reply_text" && !text) {
    setCallMessage("Custom reply likho pehle.", true);
    return;
  }
  setCallMessage("Working...");
  try {
    const data = await api("/api/whatsapp/calls/action", {
      method: "POST",
      body: JSON.stringify({ call_id: call.call_id, action, text }),
    });
    const sender = data.sender || call.sender || "caller";
    let msg = `${sender}: ${action.replace("_", " ")} done.`;
    if (data.sent && data.reply) msg = `${sender} ko reply bhej diya: ${data.reply}`;
    else if (data.rejected) msg = `${sender} ka call decline kar diya.`;
    else if (action === "ignore") msg = `${sender} ka call ignore kar diya.`;
    if (data.reject_error && data.sent) msg += `\nCall reject nahi hua, par message send ho gaya.`;
    addBubble(msg, "jarvis");
    speak(msg);
    hideCall();
    setTimeout(refreshCalls, 500);
  } catch (err) {
    setCallMessage(err.message, true);
    addBubble(err.message, "error");
    speak("Call action fail ho gaya bhai.");
  }
}

function setBar(id, value) {
  $(id).style.width = `${Math.max(0, Math.min(100, Number(value || 0)))}%`;
}

async function refreshStats() {
  try {
    const data = await api("/api/system-stats");
    setConnection(true, "Online");
    $("cpuText").textContent = `${Math.round(data.cpu_percent || 0)}%`;
    $("ramText").textContent = `${data.ram_used_gb || 0}/${data.ram_total_gb || 0} GB`;
    $("diskText").textContent = `${data.disk_used_gb || 0}/${data.disk_total_gb || 0} GB`;
    $("netText").textContent = `Up ${data.net_upload_mbps || 0} / Down ${data.net_download_mbps || 0}`;
    $("batteryText").textContent = `Battery ${data.battery_percent ?? "--"}% ${data.battery_plugged ? "plugged" : ""}`;
    setBar("cpuBar", data.cpu_percent);
    setBar("ramBar", data.ram_percent);
    setBar("diskBar", data.disk_percent);

    const list = $("processList");
    list.innerHTML = "";
    (data.top_processes || []).slice(0, 5).forEach((proc) => {
      const row = document.createElement("div");
      row.className = "process-row";
      row.innerHTML = `<span>${escapeHtml(proc.name || "Process")}</span><b>${Number(proc.cpu || 0).toFixed(1)}% / ${Math.round(proc.ram_mb || 0)} MB</b>`;
      list.appendChild(row);
    });
  } catch (err) {
    setConnection(false, "Offline");
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function startStatsPolling() {
  stopStatsPolling();
  refreshStats();
  state.statsTimer = setInterval(refreshStats, 2000);
}

function stopStatsPolling() {
  if (state.statsTimer) clearInterval(state.statsTimer);
  state.statsTimer = null;
}

function switchTab(tab) {
  document.querySelectorAll(".screen").forEach((screen) => {
    screen.classList.toggle("active", screen.id === tab);
  });
  document.querySelectorAll(".bottom-nav button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tab);
  });
  if (tab === "dashboard") startStatsPolling();
  else stopStatsPolling();
}

function startSpeech() {
  if (nativeAvailable()) {
    window.JarvisAndroid.startSpeech();
    return;
  }
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    addBubble("Speech recognition unavailable on this device.", "error");
    return;
  }
  const recognition = new SpeechRecognition();
  recognition.lang = "hi-IN";
  recognition.interimResults = false;
  recognition.onresult = (event) => {
    const text = event.results?.[0]?.[0]?.transcript || "";
    $("commandInput").value = text;
    sendCommand(text);
  };
  recognition.onerror = () => addBubble("Mic could not capture speech.", "error");
  recognition.start();
}

window.onNativeSpeechResult = (text) => {
  $("commandInput").value = text || "";
  if (text) sendCommand(text);
};

window.onNativeSpeechError = (message) => {
  addBubble(message || "Speech capture failed.", "error");
};

window.onNormalCallSecretaryUpdated = (message) => {
  refreshNormalCallSecretary();
  if (message) addBubble(message, "jarvis");
};

function saveNormalCallReply() {
  if (!nativeAvailable() || !window.JarvisAndroid.setNormalCallSecretaryReply) {
    $("normalCallStatus").textContent = "Normal call secretary works only inside the Android APK.";
    return false;
  }
  const reply = $("normalCallReply").value.trim();
  window.JarvisAndroid.setNormalCallSecretaryReply(reply);
  return true;
}

function refreshNormalCallSecretary() {
  const status = nativeJson("normalCallSecretaryStatus");
  if (!status) {
    $("normalCallStatus").textContent = "Open this inside JARVIS Android APK to use normal call secretary.";
    return;
  }
  $("normalCallReply").value = status.reply || $("normalCallReply").value;
  const lines = [
    `Enabled: ${status.enabled ? "yes" : "no"}`,
    `Call Screening role: ${status.role_held ? "granted" : "needed"}`,
    `Phone permission: ${status.read_phone_state ? "yes" : "no"}`,
    `Call log permission: ${status.read_call_log ? "yes" : "no"}`,
    `SMS permission: ${status.send_sms ? "yes" : "no"}`,
  ];
  if (status.last_status) {
    const when = status.last_time ? new Date(status.last_time).toLocaleString() : "";
    lines.push(`Last: ${status.last_status}${when ? ` • ${when}` : ""}`);
  }
  $("normalCallStatus").textContent = lines.join("\n");
}

function setupNormalCallSecretary() {
  if (!saveNormalCallReply()) return;
  try {
    window.JarvisAndroid.requestNormalCallSecretarySetup();
    $("normalCallStatus").textContent = "Android permissions/Call Screening setup opening...";
  } catch {
    $("normalCallStatus").textContent = "Could not open Android call setup.";
  }
}

function setNormalCallEnabled(enabled) {
  if (!saveNormalCallReply()) return;
  try {
    window.JarvisAndroid.setNormalCallSecretaryEnabled(Boolean(enabled));
    refreshNormalCallSecretary();
    addBubble(`Normal call secretary ${enabled ? "enabled" : "disabled"}.`, "jarvis");
  } catch {
    $("normalCallStatus").textContent = "Could not update normal call secretary.";
  }
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function handleImagePicked(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  state.selectedImage = await readFileAsDataUrl(file);
  $("preview").src = state.selectedImage;
  $("preview").classList.remove("hidden");
  $("cameraResult").textContent = "Image ready. Tap Analyze image.";
}

async function analyzeImage() {
  if (!state.selectedImage) {
    $("cameraResult").textContent = "Select or capture an image first.";
    return;
  }
  $("cameraResult").textContent = "Analyzing...";
  try {
    const data = await api("/api/camera_process", {
      method: "POST",
      body: JSON.stringify({ image: state.selectedImage, face_tracking: true }),
    });
    const faces = data.faces || [];
    if (!faces.length) {
      $("cameraResult").textContent = `No face target found.\nFace engine: ${data.face_lib_available ? "available" : "unavailable"}`;
      return;
    }
    $("cameraResult").textContent = faces.map((face, index) => {
      return `Face ${index + 1}: ${face.name || "UNKNOWN"}\nRecognized: ${face.recognized ? "yes" : "no"}\nDistance: ${face.distance}m\nLevel: ${face.threat}`;
    }).join("\n\n");
  } catch (err) {
    $("cameraResult").textContent = err.message;
  }
}

function bindEvents() {
  $("saveSettings").addEventListener("click", saveSettings);
  $("saveSettings2").addEventListener("click", () => {
    $("serverUrl").value = $("settingsServerUrl").value;
    $("apiToken").value = $("settingsApiToken").value;
    saveSettings();
  });
  $("testConnection").addEventListener("click", testConnection);
  $("sendCommand").addEventListener("click", () => sendCommand());
  $("micBtn").addEventListener("click", startSpeech);
  $("clearChat").addEventListener("click", () => { $("chatLog").innerHTML = ""; });
  $("refreshStats").addEventListener("click", refreshStats);
  $("imagePicker").addEventListener("change", handleImagePicked);
  $("analyzeImage").addEventListener("click", analyzeImage);
  $("whatsappStatus").addEventListener("click", whatsappStatus);
  $("ignoreCall").addEventListener("click", () => handleCallAction("ignore"));
  $("declineCall").addEventListener("click", () => handleCallAction("decline"));
  $("busyCall").addEventListener("click", () => handleCallAction("busy"));
  $("replyCall").addEventListener("click", () => handleCallAction("reply_text"));
  $("setupNormalCall").addEventListener("click", setupNormalCallSecretary);
  $("refreshNormalCall").addEventListener("click", refreshNormalCallSecretary);
  $("enableNormalCall").addEventListener("click", () => setNormalCallEnabled(true));
  $("disableNormalCall").addEventListener("click", () => setNormalCallEnabled(false));
  $("setupPhoneControl").addEventListener("click", setupPhoneControl);
  $("refreshPhoneControl").addEventListener("click", refreshPhoneControl);
  $("grantCompanionPermissions").addEventListener("click", requestCompanionPermissions);
  $("testCompanionLink").addEventListener("click", testCompanionLink);
  $("connectCompanion").addEventListener("click", connectCompanion);
  $("disconnectCompanion").addEventListener("click", () => disconnectCompanion(true));

  document.querySelectorAll(".bottom-nav button").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  });
  document.querySelectorAll(".action[data-command]").forEach((button) => {
    button.addEventListener("click", () => sendCommand(button.dataset.command));
  });
  document.querySelectorAll(".action[data-mobile-command]").forEach((button) => {
    button.addEventListener("click", () => {
      const command = button.dataset.mobileCommand || "";
      addBubble(command, "user");
      tryMobileCommand(command);
    });
  });
}

function finishSplash() {
  $("splash").classList.add("hidden");
  $("app").classList.remove("hidden");
  $("bottomNav").classList.remove("hidden");
  loadSettings();
  if (state.serverUrl) testConnection();
}

function setupSplash() {
  const video = $("introVideo");
  const fallback = $("introFallback");
  const skip = $("skipIntro");
  let done = false;
  let fallbackTimer = null;
  let durationTimer = null;
  let playStarted = false;

  const clearTimers = () => {
    if (fallbackTimer) clearTimeout(fallbackTimer);
    if (durationTimer) clearTimeout(durationTimer);
    fallbackTimer = null;
    durationTimer = null;
  };

  const finishOnce = () => {
    if (done) return;
    done = true;
    clearTimers();
    try {
      video.pause();
    } catch {}
    finishSplash();
  };

  const armDurationTimer = () => {
    if (!Number.isFinite(video.duration) || video.duration <= 0) return;
    if (durationTimer) clearTimeout(durationTimer);
    durationTimer = setTimeout(finishOnce, Math.ceil((video.duration + 1.5) * 1000));
  };

  const tryPlayIntro = () => {
    if (done || playStarted) return;
    playStarted = true;
    fallback.classList.add("hidden");
    armDurationTimer();
    video.play().catch(() => {
      fallback.classList.remove("hidden");
      fallbackTimer = setTimeout(finishOnce, 3500);
    });
  };

  skip.addEventListener("click", finishOnce);
  video.addEventListener("ended", finishOnce);
  video.addEventListener("loadedmetadata", armDurationTimer);
  video.addEventListener("timeupdate", () => {
    if (Number.isFinite(video.duration) && video.duration > 0 && video.currentTime >= video.duration - 0.15) {
      finishOnce();
    }
  });
  video.addEventListener("canplay", tryPlayIntro);
  video.addEventListener("canplaythrough", tryPlayIntro);
  video.addEventListener("error", () => {
    fallback.classList.remove("hidden");
    fallbackTimer = setTimeout(finishOnce, 3500);
  });
  fallbackTimer = setTimeout(() => {
    if (!playStarted) finishOnce();
  }, 15000);
  try {
    video.load();
  } catch {}
  setTimeout(tryPlayIntro, 250);
}

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  setupSplash();
  addBubble("Ready bhai. Connect your PC JARVIS and send a command.", "jarvis");
  setTimeout(refreshNormalCallSecretary, 800);
  setTimeout(refreshPhoneControl, 900);
  setTimeout(refreshCompanionPermissions, 1000);
});
