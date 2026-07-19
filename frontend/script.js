const BASE_URL = "http://localhost:8000"; // change to your FastAPI host

const chatLog     = document.getElementById("chatLog");
const chatForm    = document.getElementById("chatForm");
const chatInput   = document.getElementById("chatInput");
const sendBtn     = document.getElementById("sendBtn");
const typingRow   = document.getElementById("typingRow");
const statusDot   = document.getElementById("statusDot");
const statusText  = document.getElementById("statusText");

// Full running history sent to the backend on every turn.
let history = [];

/* ---------------- Backend health check ---------------- */

async function checkHealth() {
  try {
    const res = await fetch(`${BASE_URL}/health`, { method: "GET" });
    if (!res.ok) throw new Error("bad status");
    statusDot.classList.add("online");
    statusDot.classList.remove("offline");
    statusText.textContent = "backend connected";
  } catch (err) {
    statusDot.classList.add("offline");
    statusDot.classList.remove("online");
    statusText.textContent = "backend unreachable — start your FastAPI server";
  }
}

checkHealth();

/* ---------------- Module detection (for the little colored tag) ---------------- */
// Purely cosmetic: guesses which SAP module a message relates to,
// so the UI can show a matching accent. Backend can also send
// an authoritative "module" field which takes priority.

function detectModule(text) {
  const t = text.toLowerCase();
  if (/\bs\/?4\s?hana\b|\bfiori\b|\bmigration cockpit\b/.test(t)) return "S4";
  if (/\bmm\b|material management|\bmigo\b|\bme21n\b|\bme51n\b|purchase order|\bmara\b|\bmb1a\b|inventory/.test(t)) return "MM";
  if (/\bsd\b|sales.*distribution|\bva01\b|\bvbak\b|sales order|\bdelivery\b|\bbilling\b/.test(t)) return "SD";
  return "";
}

function setActiveChip(moduleKey) {
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.classList.toggle("active", chip.dataset.module === moduleKey);
  });
}

/* ---------------- Rendering ---------------- */

function scrollToBottom() {
  chatLog.scrollTop = chatLog.scrollHeight;
}

function appendMessage({ role, text, module = "", sources = [], isError = false }) {
  const row = document.createElement("div");
  row.className = `msg msg-${role}${isError ? " msg-error" : ""}`;
  if (module) row.dataset.module = module;

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.textContent = role === "user" ? "YOU" : "AI";

  const body = document.createElement("div");
  body.className = "msg-body";

  const meta = document.createElement("div");
  meta.className = "msg-meta";
  const roleLabel = document.createElement("span");
  roleLabel.className = "msg-role";
  roleLabel.textContent = role === "user" ? "You" : "Assistant";
  meta.appendChild(roleLabel);

  if (module) {
    const tag = document.createElement("span");
    tag.className = "msg-module-tag";
    tag.textContent = module === "S4" ? "S/4HANA" : module;
    meta.appendChild(tag);
  }

  const textEl = document.createElement("div");
  textEl.className = "msg-text";
  textEl.textContent = text;

  body.appendChild(meta);
  body.appendChild(textEl);

  if (sources && sources.length) {
    const srcWrap = document.createElement("div");
    srcWrap.className = "msg-sources";
    sources.forEach((s) => {
      const tag = document.createElement("span");
      tag.className = "source-tag";
      tag.textContent = s;
      srcWrap.appendChild(tag);
    });
    body.appendChild(srcWrap);
  }

  row.appendChild(avatar);
  row.appendChild(body);
  chatLog.appendChild(row);
  scrollToBottom();
}

function showTyping(show) {
  typingRow.hidden = !show;
  if (show) scrollToBottom();
}

/* ---------------- Sending messages ---------------- */

async function sendMessage(message) {
  const module = detectModule(message);
  setActiveChip(module);

  appendMessage({ role: "user", text: message, module });
  history.push({ role: "user", content: message });

  sendBtn.disabled = true;
  showTyping(true);

  try {
    const res = await fetch(`${BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
    });

    if (!res.ok) throw new Error(`Server responded ${res.status}`);

    const data = await res.json();
    const replyModule = data.module || module;

    appendMessage({
      role: "assistant",
      text: data.reply ?? "No response received.",
      module: replyModule,
      sources: data.sources ?? [],
    });

    history.push({ role: "assistant", content: data.reply ?? "" });
  } catch (err) {
    appendMessage({
      role: "assistant",
      text: `Couldn't reach the backend (${err.message}). Confirm your FastAPI server is running at ${BASE_URL}.`,
      isError: true,
    });
  } finally {
    showTyping(false);
    sendBtn.disabled = false;
    chatInput.focus();
  }
}

/* ---------------- Form + input handling ---------------- */

chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;
  chatInput.value = "";
  autoResize();
  sendMessage(message);
});

chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    chatForm.requestSubmit();
  }
});

function autoResize() {
  chatInput.style.height = "auto";
  chatInput.style.height = Math.min(chatInput.scrollHeight, 140) + "px";
}
chatInput.addEventListener("input", autoResize);

chatInput.focus();