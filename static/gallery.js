const gallery = document.querySelector("#gallery");
const emptyState = document.querySelector("#emptyState");
const message = document.querySelector("#message");
const serverStatus = document.querySelector("#serverStatus");
const captureButton = document.querySelector("#captureButton");
const refreshButton = document.querySelector("#refreshButton");
const lanToggle = document.querySelector("#lanToggle");
const copyPreference = document.querySelector("#copyPreference");
const template = document.querySelector("#captureCardTemplate");

let settings = null;

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

function setMessage(text, isError = false) {
  message.textContent = text;
  message.classList.toggle("error", isError);
}

function formatBytes(value) {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

async function copyText(text) {
  await navigator.clipboard.writeText(text);
  setMessage("Copied");
}

function renderSettings() {
  lanToggle.checked = settings.sharing.lan_enabled;
  copyPreference.value = settings.sharing.copy_after_capture;
  const mode = settings.sharing.lan_enabled ? "LAN on" : "Local only";
  const host = settings.sharing.lan_enabled ? settings.lan_base_url : settings.local_base_url;
  serverStatus.textContent = `${mode} - ${host}`;

  if (settings.restart_required) {
    setMessage("Restart the app to apply the LAN server binding.");
  }
}

function renderCaptures(captures) {
  gallery.replaceChildren();
  emptyState.hidden = captures.length > 0;

  for (const capture of captures) {
    const card = template.content.firstElementChild.cloneNode(true);
    const link = card.querySelector(".capture-link");
    const image = card.querySelector(".capture-image");
    const title = card.querySelector(".capture-title");
    const details = card.querySelector(".capture-details");
    const copyLocalButton = card.querySelector(".copy-local-button");
    const shareButton = card.querySelector(".share-button");
    const copyLanButton = card.querySelector(".copy-lan-button");
    const deleteButton = card.querySelector(".delete-button");

    link.href = capture.local_url;
    image.src = capture.local_url;
    image.alt = capture.filename;
    title.textContent = capture.filename;
    details.textContent = `${formatDate(capture.created_at)} - ${capture.width} x ${capture.height} - ${formatBytes(capture.file_size)}`;

    copyLocalButton.addEventListener("click", () => copyText(capture.local_url).catch(showError));

    shareButton.textContent = capture.share_enabled ? "Unshare" : "Share";
    shareButton.addEventListener("click", async () => {
      await requestJson(`/api/captures/${capture.id}/share`, {
        method: "POST",
        body: JSON.stringify({ enabled: !capture.share_enabled }),
      });
      await loadAll();
      setMessage(capture.share_enabled ? "Sharing disabled" : "Sharing enabled");
    });

    copyLanButton.disabled = !capture.lan_url;
    copyLanButton.addEventListener("click", () => {
      if (capture.lan_url) {
        copyText(capture.lan_url).catch(showError);
      }
    });

    deleteButton.addEventListener("click", async () => {
      if (!window.confirm(`Delete ${capture.filename}?`)) {
        return;
      }
      await fetch(`/api/captures/${capture.id}`, { method: "DELETE" });
      await loadAll();
      setMessage("Deleted");
    });

    gallery.append(card);
  }
}

function showError(error) {
  setMessage(error.message || String(error), true);
}

async function loadSettings() {
  settings = await requestJson("/api/settings");
  renderSettings();
}

async function loadCaptures() {
  const data = await requestJson("/api/captures");
  renderCaptures(data.captures);
}

async function loadAll() {
  setMessage("");
  await loadSettings();
  await loadCaptures();
}

captureButton.addEventListener("click", async () => {
  try {
    await requestJson("/api/capture", { method: "POST" });
    setMessage("Capture started");
  } catch (error) {
    showError(error);
  }
});

refreshButton.addEventListener("click", () => loadAll().catch(showError));

lanToggle.addEventListener("change", async () => {
  try {
    settings = await requestJson("/api/settings", {
      method: "PATCH",
      body: JSON.stringify({ lan_enabled: lanToggle.checked }),
    });
    renderSettings();
    await loadCaptures();
  } catch (error) {
    showError(error);
  }
});

copyPreference.addEventListener("change", async () => {
  try {
    settings = await requestJson("/api/settings", {
      method: "PATCH",
      body: JSON.stringify({ copy_after_capture: copyPreference.value }),
    });
    renderSettings();
  } catch (error) {
    showError(error);
  }
});

loadAll().catch(showError);
