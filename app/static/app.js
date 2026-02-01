const state = {
  library: { files: [], folders: [] },
  albums: [],
  selected: new Map(),
  currentAlbumId: null,
  filter: "all",
  settings: {},
  nowPlaying: null,
  playerError: null,
  mediaRoots: {},
  storage: {},
};

const els = {
  status: document.getElementById("status-line"),
  playerPill: document.getElementById("player-pill"),
  uploadBtn: document.getElementById("upload-btn"),
  uploadStatus: document.getElementById("upload-status"),
  fileUpload: document.getElementById("file-upload"),
  folderUpload: document.getElementById("folder-upload"),
  libraryList: document.getElementById("library-list"),
  albumGrid: document.getElementById("album-grid"),
  albumName: document.getElementById("album-name"),
  createAlbum: document.getElementById("create-album"),
  albumSelect: document.getElementById("album-select"),
  addSelected: document.getElementById("add-selected"),
  replaceSelected: document.getElementById("replace-selected"),
  albumSources: document.getElementById("album-sources"),
  albumShuffle: document.getElementById("album-shuffle"),
  saveAlbumSettings: document.getElementById("save-album-settings"),
  playAlbum: document.getElementById("play-album"),
  stopPlayback: document.getElementById("stop-playback"),
  nextItem: document.getElementById("next-item"),
  prevItem: document.getElementById("prev-item"),
  toggleMute: document.getElementById("toggle-mute"),
  nowPlaying: document.getElementById("now-playing"),
  slideDuration: document.getElementById("slide-duration"),
  transition: document.getElementById("transition"),
  fadeDuration: document.getElementById("fade-duration"),
  fitMode: document.getElementById("fit-mode"),
  displayWidth: document.getElementById("display-width"),
  displayHeight: document.getElementById("display-height"),
  shuffle: document.getElementById("shuffle"),
  mute: document.getElementById("mute"),
  primaryRoot: document.getElementById("primary-root"),
  secondaryRoot: document.getElementById("secondary-root"),
  overflowThreshold: document.getElementById("overflow-threshold"),
  saveSettings: document.getElementById("save-settings"),
};

async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || response.statusText);
  }
  return response.json();
}

function setStatus(message) {
  els.status.textContent = message;
}

function updatePlayerPill() {
  const playing = state.nowPlaying?.playing;
  els.playerPill.textContent = playing ? "Playing" : "Player idle";
}

function renderLibrary() {
  const list = document.createElement("div");
  const items = [];
  if (state.filter === "all" || state.filter === "folder") {
    state.library.folders.forEach((folder) => {
      items.push({
        path: folder.path,
        name: folder.name,
        type: "folder",
        root: folder.root || "primary",
      });
    });
  }
  if (state.filter === "all" || state.filter === "image" || state.filter === "video") {
    state.library.files
      .filter((file) => state.filter === "all" || file.type === state.filter)
      .forEach((file) => items.push(file));
  }

  if (!items.length) {
    list.innerHTML = "<div class=\"library-item\"><span></span><span>No media yet.</span></div>";
  } else {
    items.forEach((item) => {
      const row = document.createElement("div");
      row.className = "library-item";
      const key = `${item.root}:${item.type}:${item.path}`;
      row.innerHTML = `
        <input type="checkbox" data-key="${key}" ${state.selected.has(key) ? "checked" : ""} />
        <div>
          <strong>${item.name}</strong><br />
        <small>${item.root || "primary"} · ${item.path}</small>
        </div>
        <small>${item.type}</small>
      `;
      row.querySelector("input").addEventListener("change", (event) => {
        if (event.target.checked) {
          state.selected.set(key, { path: item.path, type: item.type, root: item.root || "primary" });
        } else {
          state.selected.delete(key);
        }
      });
      list.appendChild(row);
    });
  }
  els.libraryList.innerHTML = "";
  els.libraryList.appendChild(list);
}

function renderAlbums() {
  els.albumGrid.innerHTML = "";
  state.albums.forEach((album) => {
    const card = document.createElement("div");
    card.className = "album-card";
    const count = album.sources?.length || 0;
    card.innerHTML = `
      <strong>${album.name}</strong>
      <small>${count} sources</small>
      <div class="row">
        <button class="btn ghost" data-play="${album.id}">Play</button>
        <button class="btn ghost" data-edit="${album.id}">Edit</button>
        <button class="btn ghost" data-delete="${album.id}">Delete</button>
      </div>
    `;
    card.querySelector("[data-play]").addEventListener("click", () => playAlbum(album.id));
    card.querySelector("[data-edit]").addEventListener("click", () => {
      els.albumSelect.value = album.id;
      state.currentAlbumId = album.id;
      renderAlbumSources();
    });
    card.querySelector("[data-delete]").addEventListener("click", () => deleteAlbum(album.id));
    els.albumGrid.appendChild(card);
  });

  els.albumSelect.innerHTML = "";
  state.albums.forEach((album) => {
    const opt = document.createElement("option");
    opt.value = album.id;
    opt.textContent = album.name;
    els.albumSelect.appendChild(opt);
  });
  const stillValid = state.albums.some((album) => album.id === state.currentAlbumId);
  if (!stillValid) {
    state.currentAlbumId = state.albums.length ? state.albums[0].id : null;
  }
  if (state.currentAlbumId) {
    els.albumSelect.value = state.currentAlbumId;
  }
  renderAlbumSources();
}

function renderAlbumSources() {
  const album = state.albums.find((item) => item.id === state.currentAlbumId);
  els.albumSources.innerHTML = "";
  if (!album) {
    els.albumSources.textContent = "Select an album.";
    return;
  }
  if (album.shuffle === true) {
    els.albumShuffle.value = "true";
  } else if (album.shuffle === false) {
    els.albumShuffle.value = "false";
  } else {
    els.albumShuffle.value = "default";
  }
  (album.sources || []).forEach((source, index) => {
    const row = document.createElement("div");
    row.className = "source-item";
    row.innerHTML = `
      <div>
        <strong>${source.type}</strong><br />
        <small>${source.root || "primary"} · ${source.path}</small>
      </div>
      <button class="btn ghost" data-remove="${index}">Remove</button>
    `;
    row.querySelector("button").addEventListener("click", () => {
      const nextSources = album.sources.filter((_, idx) => idx !== index);
      updateAlbum(album.id, { sources: nextSources });
    });
    els.albumSources.appendChild(row);
  });
}

function renderNowPlaying() {
  const now = state.nowPlaying;
  if (!now || !now.item) {
    els.nowPlaying.innerHTML = "<p class=\"subtle\">Nothing playing yet.</p>";
    return;
  }
  const item = now.item;
  const safePath = encodeURIComponent(item.path).replace(/%2F/g, "/");
  const safeRoot = encodeURIComponent(item.root || "primary");
  const src = `/media/${safeRoot}/${safePath}`;
  const header = `<div><strong>Now playing</strong><br /><small>${item.path}</small></div>`;
  if (item.type === "image") {
    els.nowPlaying.innerHTML = `${header}<img src="${src}" alt="" />`;
  } else {
    els.nowPlaying.innerHTML = `${header}<video src="${src}" muted playsinline controls preload="metadata"></video>`;
  }
}

function renderSettings() {
  els.slideDuration.value = state.settings.slide_duration ?? 12;
  els.transition.value = state.settings.transition ?? "fade";
  els.fadeDuration.value = state.settings.transition_duration ?? 0.6;
  els.fitMode.value = state.settings.fit_mode ?? "fit-blur";
  els.displayWidth.value = state.settings.display_width ?? 1024;
  els.displayHeight.value = state.settings.display_height ?? 600;
  els.shuffle.checked = !!state.settings.shuffle;
  els.mute.checked = !!state.settings.mute;
  els.primaryRoot.value = state.mediaRoots?.primary ?? "/srv/vframe-media";
  els.secondaryRoot.value = state.mediaRoots?.secondary ?? "/mnt/vframe-media";
  els.overflowThreshold.value = state.storage?.overflow_threshold_gb ?? 10;
}

async function refreshAll() {
  try {
    const data = await fetchJSON("/api/state");
    state.albums = data.albums || [];
    state.settings = data.settings || {};
    state.nowPlaying = data.now_playing || null;
    state.playerError = data.player_error;
    state.mediaRoots = data.media_roots || {};
    state.storage = data.storage || {};
    setStatus(state.playerError ? `Player issue: ${state.playerError}` : "Connected");
    updatePlayerPill();
    renderAlbums();
    renderSettings();
    renderNowPlaying();
  } catch (err) {
    setStatus("Disconnected");
  }
}

async function refreshLibrary() {
  try {
    state.library = await fetchJSON("/api/library");
    renderLibrary();
  } catch (err) {
    console.error(err);
  }
}

async function uploadFiles() {
  const files = Array.from(els.fileUpload.files || []);
  const folderFiles = Array.from(els.folderUpload.files || []);
  const allFiles = files.concat(folderFiles);
  if (!allFiles.length) {
    els.uploadStatus.textContent = "Pick files or a folder.";
    return;
  }
  const form = new FormData();
  const paths = [];
  allFiles.forEach((file) => {
    form.append("files", file);
    if (file.webkitRelativePath) {
      paths.push(file.webkitRelativePath);
    } else {
      paths.push(file.name);
    }
  });
  paths.forEach((path) => form.append("paths", path));
  els.uploadStatus.textContent = "Uploading...";
  try {
    await fetchJSON("/api/upload", { method: "POST", body: form });
    els.uploadStatus.textContent = "Uploaded!";
    els.fileUpload.value = "";
    els.folderUpload.value = "";
    await refreshLibrary();
  } catch (err) {
    els.uploadStatus.textContent = "Upload failed.";
  }
}

async function createAlbum() {
  const name = els.albumName.value.trim();
  if (!name) return;
  await fetchJSON("/api/albums", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  els.albumName.value = "";
  await refreshAll();
}

async function updateAlbum(albumId, payload) {
  await fetchJSON(`/api/albums/${albumId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await refreshAll();
}

async function deleteAlbum(albumId) {
  await fetchJSON(`/api/albums/${albumId}`, { method: "DELETE" });
  await refreshAll();
}

async function playAlbum(albumId) {
  await fetchJSON(`/api/play/${albumId}`, { method: "POST" });
  await refreshAll();
}

async function stopPlayback() {
  await fetchJSON(`/api/stop`, { method: "POST" });
  await refreshAll();
}

async function addSelectedToAlbum(replace) {
  const album = state.albums.find((item) => item.id === state.currentAlbumId);
  if (!album) return;
  const selected = Array.from(state.selected.values());
  if (!selected.length) return;
  const existing = replace ? [] : (album.sources || []);
  const merged = [...existing];
  selected.forEach((item) => {
    if (!merged.find((entry) => entry.path === item.path && entry.type === item.type && entry.root === item.root)) {
      merged.push({ path: item.path, type: item.type, root: item.root });
    }
  });
  await updateAlbum(album.id, { sources: merged });
}

async function saveAlbumSettings() {
  const album = state.albums.find((item) => item.id === state.currentAlbumId);
  if (!album) return;
  let shuffle = null;
  if (els.albumShuffle.value === "true") shuffle = true;
  if (els.albumShuffle.value === "false") shuffle = false;
  await updateAlbum(album.id, { shuffle });
}

async function saveSettings() {
  const payload = {
    slide_duration: parseFloat(els.slideDuration.value || "0"),
    transition: els.transition.value,
    transition_duration: parseFloat(els.fadeDuration.value || "0"),
    fit_mode: els.fitMode.value,
    display_width: parseInt(els.displayWidth.value || "1024", 10),
    display_height: parseInt(els.displayHeight.value || "600", 10),
    shuffle: els.shuffle.checked,
    mute: els.mute.checked,
  };
  await fetchJSON("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await fetchJSON("/api/storage", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      primary: els.primaryRoot.value.trim(),
      secondary: els.secondaryRoot.value.trim(),
      overflow_threshold_gb: parseFloat(els.overflowThreshold.value || "10"),
    }),
  });
  await refreshAll();
}

async function toggleMute() {
  els.mute.checked = !els.mute.checked;
  await saveSettings();
}

function bindEvents() {
  els.uploadBtn.addEventListener("click", uploadFiles);
  els.createAlbum.addEventListener("click", createAlbum);
  els.albumSelect.addEventListener("change", (event) => {
    state.currentAlbumId = event.target.value;
    renderAlbumSources();
  });
  els.addSelected.addEventListener("click", () => addSelectedToAlbum(false));
  els.replaceSelected.addEventListener("click", () => addSelectedToAlbum(true));
  els.saveAlbumSettings.addEventListener("click", saveAlbumSettings);
  els.playAlbum.addEventListener("click", () => {
    if (state.currentAlbumId) playAlbum(state.currentAlbumId);
  });
  els.stopPlayback.addEventListener("click", stopPlayback);
  els.nextItem.addEventListener("click", () => fetchJSON("/api/next", { method: "POST" }));
  els.prevItem.addEventListener("click", () => fetchJSON("/api/prev", { method: "POST" }));
  els.toggleMute.addEventListener("click", toggleMute);
  els.saveSettings.addEventListener("click", saveSettings);

  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", (event) => {
      document.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
      event.target.classList.add("active");
      state.filter = event.target.dataset.filter;
      renderLibrary();
    });
  });
}

bindEvents();
refreshAll();
refreshLibrary();
setInterval(refreshAll, 4000);
