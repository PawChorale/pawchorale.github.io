const ZENODO_ARCHIVE_URL =
  "https://zenodo.org/api/records/21777039/files/PawChorale-1.0.0-full-200-works.zip/content";

const state = {
  songs: [],
  filtered: [],
  expanded: false,
};

const demoState = {
  catalog: [],
  zipIndex: {},
  data: null,
  audio: new Map(),
  objectUrls: new Set(),
  blobCache: new Map(),
  playing: false,
  frame: null,
  loadToken: 0,
  abortController: null,
};

const formatBytes = (bytes) => `${(bytes / 1024 ** 3).toFixed(2)} GiB`;

const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const formatTime = (seconds) => {
  const safe = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
  const minutes = Math.floor(safe / 60);
  const remainder = safe - minutes * 60;
  return `${String(minutes).padStart(2, "0")}:${remainder.toFixed(1).padStart(4, "0")}`;
};

const mimeForPath = (path) => {
  const extension = path.split(".").pop().toLowerCase();
  return {
    mp3: "audio/mpeg",
    mid: "audio/midi",
    midi: "audio/midi",
    xml: "application/xml",
    musicxml: "application/vnd.recordare.musicxml+xml",
    csv: "text/csv",
    json: "application/json",
  }[extension] || "application/octet-stream";
};

function renderDownloads(summary) {
  const grid = document.querySelector("#download-grid");
  const status = document.querySelector("#release-status");
  const enabled = Boolean(summary.downloads_enabled);

  grid.innerHTML = summary.archives
    .map((archive) => {
      const action = enabled
        ? `<a href="${escapeHtml(archive.download_url)}">Download ZIP ↓</a>`
        : '<span class="disabled-link" aria-disabled="true">Release pending</span>';
      return `
        <article class="download-card">
          <header>
            <span class="part-number">Part ${String(archive.part).padStart(2, "0")}</span>
            <span class="part-size">${formatBytes(archive.uncompressed_bytes)}</span>
          </header>
          <h3>Songs ${String(archive.first_song_id).padStart(3, "0")}–${String(archive.last_song_id).padStart(3, "0")}</h3>
          <p>${archive.song_count} curated works · MP3 + MIDI + MusicXML</p>
          ${action}
        </article>`;
    })
    .join("");

  if (enabled) {
    status.classList.add("ready");
    status.innerHTML = '<span aria-hidden="true"></span><p><strong>The complete Zenodo archive is available.</strong> Use the GitHub parts below only as alternative mirrors.</p>';
  } else {
    status.innerHTML = '<span aria-hidden="true"></span><p><strong>Full archives are not public yet.</strong> The catalog and example files remain available while the release assets are prepared.</p>';
  }
}

function renderDatasetStats(summary) {
  document.querySelector("#stat-works").textContent = summary.song_count.toLocaleString();
  document.querySelector("#stat-master-hours").textContent = `${summary.master_hours.toFixed(2)} h`;
  document.querySelector("#stat-stem-hours").textContent = `${summary.stem_hours.toFixed(2)} h`;
  document.querySelector("#stat-midi-notes").textContent = summary.midi_notes.toLocaleString();
  document.querySelector("#archive-total").textContent = `${summary.archives.length} parts · ${formatBytes(summary.total_bytes)} uncompressed`;
}

function renderCatalog() {
  const body = document.querySelector("#catalog-body");
  const count = document.querySelector("#catalog-count");
  const more = document.querySelector("#catalog-more");
  const visible = state.expanded ? state.filtered : state.filtered.slice(0, 12);

  body.innerHTML = visible.length
    ? visible
        .map(
          (song) => `<tr>
            <td>${String(song.id).padStart(3, "0")}</td>
            <td>${escapeHtml(song.title)}</td>
            <td>${song.stem_count}</td>
            <td>${song.midi_count}</td>
            <td>Part ${String(song.archive_part).padStart(2, "0")}</td>
          </tr>`,
        )
        .join("")
    : '<tr><td colspan="5">No matching works.</td></tr>';

  count.textContent = `${state.filtered.length} ${state.filtered.length === 1 ? "work" : "works"}`;
  more.hidden = state.filtered.length <= 12;
  more.textContent = state.expanded ? "Show fewer ↑" : "Show all works ↓";
}

function stopDemoPlayback() {
  demoState.playing = false;
  if (demoState.frame) cancelAnimationFrame(demoState.frame);
  demoState.frame = null;
  demoState.audio.forEach((audio) => audio.pause());
}

function disposeDemoMedia() {
  stopDemoPlayback();
  demoState.abortController?.abort();
  demoState.abortController = null;
  demoState.audio.clear();
  demoState.objectUrls.forEach((url) => URL.revokeObjectURL(url));
  demoState.objectUrls.clear();
  demoState.blobCache.clear();
  demoState.data = null;
  document.querySelector("#demo-audio-bank").replaceChildren();
  document.querySelector("#track-controls").replaceChildren();
}

async function fetchZipBlob(path, signal) {
  if (demoState.blobCache.has(path)) return demoState.blobCache.get(path);

  const request = (async () => {
    const entry = demoState.zipIndex[path];
    if (!entry) throw new Error(`${path} is not indexed in the release archive`);
    const [offset, compressedSize, fileSize, method] = entry;
    const response = await fetch(ZENODO_ARCHIVE_URL, {
      headers: { Range: `bytes=${offset}-${offset + compressedSize - 1}` },
      signal,
    });
    if (response.status !== 206) {
      response.body?.cancel();
      throw new Error("The archive server did not honor the requested byte range");
    }
    const compressed = await response.arrayBuffer();
    if (compressed.byteLength !== compressedSize) {
      throw new Error(`Incomplete archive entry for ${path}`);
    }

    let bytes;
    if (method === 0) {
      bytes = compressed;
    } else if (method === 8) {
      if (!("DecompressionStream" in window)) {
        throw new Error("This browser does not support on-demand ZIP decompression");
      }
      const stream = new Blob([compressed])
        .stream()
        .pipeThrough(new DecompressionStream("deflate-raw"));
      bytes = await new Response(stream).arrayBuffer();
    } else {
      throw new Error(`Unsupported ZIP compression method ${method}`);
    }
    if (bytes.byteLength !== fileSize) throw new Error(`Decompressed size mismatch for ${path}`);
    return new Blob([bytes], { type: mimeForPath(path) });
  })();

  demoState.blobCache.set(path, request);
  return request;
}

function renderPianoRoll(time = 0) {
  if (!demoState.data) return;
  const canvas = document.querySelector("#piano-roll");
  const context = canvas.getContext("2d");
  const cssWidth = Math.max(canvas.clientWidth, 720);
  const cssHeight = 360;
  const pixelRatio = window.devicePixelRatio || 1;
  canvas.width = Math.round(cssWidth * pixelRatio);
  canvas.height = Math.round(cssHeight * pixelRatio);
  context.scale(pixelRatio, pixelRatio);

  const width = cssWidth;
  const height = cssHeight;
  const labelWidth = 68;
  const rightPad = 18;
  const topPad = 25;
  const bottomPad = 24;
  const plotWidth = width - labelWidth - rightPad;
  const laneCount = Math.max(1, demoState.data.tracks.length);
  const laneHeight = (height - topPad - bottomPad) / laneCount;
  const duration = Math.max(0.001, demoState.data.duration_seconds);

  context.fillStyle = "#2c2421";
  context.fillRect(0, 0, width, height);
  context.font = "11px ui-monospace, SFMono-Regular, Menlo, monospace";
  context.textBaseline = "middle";

  const gridStep = duration > 300 ? 30 : duration > 120 ? 15 : 5;
  for (let second = 0; second <= duration; second += gridStep) {
    const x = labelWidth + (second / duration) * plotWidth;
    context.strokeStyle = "rgba(255,255,255,.1)";
    context.beginPath();
    context.moveTo(x, topPad - 10);
    context.lineTo(x, height - bottomPad);
    context.stroke();
    context.fillStyle = "rgba(255,255,255,.45)";
    context.fillText(`${second}s`, x + 4, 11);
  }

  demoState.data.tracks.forEach((track, index) => {
    const laneTop = topPad + index * laneHeight;
    context.fillStyle = index % 2 ? "rgba(255,255,255,.018)" : "rgba(255,255,255,.035)";
    context.fillRect(labelWidth, laneTop, plotWidth, laneHeight);
    context.strokeStyle = "rgba(255,255,255,.08)";
    context.beginPath();
    context.moveTo(labelWidth, laneTop + laneHeight);
    context.lineTo(width - rightPad, laneTop + laneHeight);
    context.stroke();
    context.fillStyle = track.color;
    context.font = "700 11px ui-sans-serif, sans-serif";
    const shortLabel = track.label
      .replace("Soprano", "S")
      .replace("Alto", "A")
      .replace("Tenor", "T")
      .replace("Bass", "B");
    context.fillText(shortLabel, 22, laneTop + laneHeight / 2);

    const pitchMin = track.pitch_min ?? 60;
    const pitchMax = track.pitch_max ?? pitchMin + 1;
    const pitchRange = Math.max(1, pitchMax - pitchMin);
    track.notes.forEach((note) => {
      const [pitch, start, end] = note;
      const x = labelWidth + (start / duration) * plotWidth;
      const noteWidth = Math.max(2, ((end - start) / duration) * plotWidth - 1);
      const relativePitch = (pitch - pitchMin) / pitchRange;
      const y = laneTop + laneHeight - 12 - relativePitch * Math.max(4, laneHeight - 24);
      context.fillStyle = track.color;
      context.globalAlpha = 0.9;
      context.fillRect(x, y, noteWidth, Math.min(5, Math.max(2, laneHeight / 8)));
    });
    context.globalAlpha = 1;
  });

  const playhead = labelWidth + (Math.min(time, duration) / duration) * plotWidth;
  context.strokeStyle = "#fffaf0";
  context.lineWidth = 2;
  context.beginPath();
  context.moveTo(playhead, topPad - 10);
  context.lineTo(playhead, height - bottomPad);
  context.stroke();
  context.fillStyle = "#fffaf0";
  context.beginPath();
  context.arc(playhead, topPad - 10, 4, 0, Math.PI * 2);
  context.fill();
}

function updateDemoFrame() {
  const master = demoState.audio.get("Master");
  if (!master) return;
  const current = master.currentTime;
  document.querySelector("#demo-progress").value = current;
  document.querySelector("#demo-current").textContent = formatTime(current);
  renderPianoRoll(current);

  if (demoState.playing) {
    demoState.audio.forEach((audio, name) => {
      if (name !== "Master" && Math.abs(audio.currentTime - current) > 0.08) {
        audio.currentTime = Math.min(current, audio.duration || current);
      }
    });
    demoState.frame = requestAnimationFrame(updateDemoFrame);
  }
}

function resetPlayButton() {
  const button = document.querySelector("#demo-play");
  button.innerHTML = '<span aria-hidden="true">▶</span><b>Play</b>';
  button.setAttribute("aria-label", "Play selected work");
}

async function toggleDemoPlayback() {
  const master = demoState.audio.get("Master");
  if (!master) return;
  const button = document.querySelector("#demo-play");
  if (demoState.playing) {
    stopDemoPlayback();
    resetPlayButton();
    return;
  }

  const position = master.ended ? 0 : master.currentTime;
  demoState.audio.forEach((audio) => {
    audio.currentTime = Math.min(position, audio.duration || position);
  });
  try {
    const results = await Promise.allSettled([...demoState.audio.values()].map((audio) => audio.play()));
    if (master.paused) throw new Error("Master audio was blocked by the browser");
    if (results.some((result) => result.status === "rejected")) {
      console.warn("One or more part recordings could not start; the master remains available.");
    }
    demoState.playing = true;
    button.innerHTML = '<span aria-hidden="true">Ⅱ</span><b>Pause</b>';
    button.setAttribute("aria-label", "Pause selected work");
    updateDemoFrame();
  } catch (error) {
    console.error("Demo playback could not start", error);
  }
}

function renderDemoMetadata(data) {
  const all = data.alignment.All;
  document.querySelector("#demo-work-kicker").textContent = `Selected · Work ${String(data.id).padStart(3, "0")}`;
  document.querySelector("#demo-work-title").textContent = data.title;
  document.querySelector("#demo-work-composer").textContent = data.composer || "Composer not listed";
  document.querySelector("#demo-stat-duration").textContent = formatTime(data.duration_seconds);
  document.querySelector("#demo-stat-voicing").textContent = data.voicing;
  document.querySelector("#demo-stat-notes").textContent = data.note_count.toLocaleString();
  document.querySelector("#demo-stat-matched").textContent = all ? `${all.matched_percent.toFixed(2)}%` : "—";

  document.querySelector("#demo-source-id").textContent = String(data.id).padStart(3, "0");
  document.querySelector("#demo-source-score").textContent = data.source.source_file || data.source.original_folder || "Not recorded";
  const edition = [data.source.cpdl_number ? `#${data.source.cpdl_number}` : "", data.source.editor]
    .filter(Boolean)
    .join(", ");
  document.querySelector("#demo-source-edition").textContent = edition || "Not recorded";
  document.querySelector("#demo-source-license").textContent = data.source.edition_license || "See rights manifest";
  const sourceLink = document.querySelector("#demo-source-link");
  sourceLink.href = data.source.cpdl_work_page || "https://www.cpdl.org/";
  sourceLink.hidden = !data.source.cpdl_work_page;

  const channelLabel = data.channels === 1 ? "mono" : data.channels === 2 ? "stereo" : `${data.channels} channels`;
  document.querySelector("#demo-render-audio").textContent = `MP3, ${channelLabel}, ${(data.sample_rate / 1000).toFixed(1)} kHz`;
  document.querySelector("#demo-render-layout").textContent = `Master + ${data.tracks.filter((track) => track.audio_path).length} isolated part${data.tracks.filter((track) => track.audio_path).length === 1 ? "" : "s"}`;

  document.querySelector("#demo-alignment-value").textContent = all ? `${all.onset_50ms_percent.toFixed(2)}%` : "—";
  document.querySelector("#demo-alignment-note").textContent = all
    ? `of matched notes begin within 50 ms · median onset error ${all.median_onset_error_ms.toFixed(1)} ms`
    : "No work-level alignment metric is available for this item.";
  document.querySelector("#demo-download-title").textContent = `Work ${String(data.id).padStart(3, "0")} files`;

  const legend = document.querySelector("#roll-legend");
  legend.innerHTML = data.tracks
    .map((track) => `<span style="--legend-color:${track.color}">${escapeHtml(track.label)}</span>`)
    .join("");
  legend.insertAdjacentHTML("beforeend", "<em>The playhead follows the master recording.</em>");
}

function addDownloadButton(container, path, kind) {
  if (!path) return;
  const button = document.createElement("button");
  const filename = path.split("/").pop();
  button.type = "button";
  button.innerHTML = `<span>${escapeHtml(filename)}</span><em>${escapeHtml(kind)} ↓</em>`;
  button.addEventListener("click", async () => {
    const original = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<span>${escapeHtml(filename)}</span><em>Loading…</em>`;
    try {
      const blob = await fetchZipBlob(path);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      button.innerHTML = `<span>${escapeHtml(filename)}</span><em>Downloaded ✓</em>`;
      setTimeout(() => { button.innerHTML = original; }, 1600);
    } catch (error) {
      console.error(error);
      button.innerHTML = `<span>${escapeHtml(filename)}</span><em>Try again</em>`;
    } finally {
      button.disabled = false;
    }
  });
  container.append(button);
}

function buildDemoDownloads(data) {
  const container = document.querySelector("#demo-download-list");
  container.replaceChildren();
  const seen = new Set();
  const add = (path, kind) => {
    if (!path || seen.has(path)) return;
    seen.add(path);
    addDownloadButton(container, path, kind);
  };

  add(data.master.path, "master");
  data.tracks.forEach((track) => {
    add(track.audio_path, track.label);
    track.midi_paths.forEach((path) => add(path, "MIDI"));
  });
  add(data.files.mixture_midi, "mixture MIDI");
  add(data.files.score_xml, "MusicXML");
  add(data.files.manifest_csv, "metadata");
  add(data.files.manifest_json, "metadata");
}

function createAudioControl(source, blob) {
  const bank = document.querySelector("#demo-audio-bank");
  const controls = document.querySelector("#track-controls");
  const url = URL.createObjectURL(blob);
  demoState.objectUrls.add(url);

  const audio = document.createElement("audio");
  audio.src = url;
  audio.preload = "auto";
  audio.muted = !source.enabled;
  bank.append(audio);
  demoState.audio.set(source.label, audio);

  const label = document.createElement("label");
  label.className = "track-toggle";
  label.style.setProperty("--track-color", source.color);
  label.innerHTML = `<input type="checkbox" ${source.enabled ? "checked" : ""} aria-label="Toggle ${escapeHtml(source.label)} audio"><span>${escapeHtml(source.label)}</span>`;
  label.querySelector("input").addEventListener("change", (event) => {
    audio.muted = !event.target.checked;
  });
  controls.append(label);

  return new Promise((resolve, reject) => {
    if (audio.readyState >= 1) {
      resolve();
      return;
    }
    audio.addEventListener("loadedmetadata", resolve, { once: true });
    audio.addEventListener("error", () => reject(new Error(`${source.path} could not load`)), { once: true });
  });
}

async function loadDemoSong(songId) {
  const token = ++demoState.loadToken;
  disposeDemoMedia();
  demoState.abortController = new AbortController();
  const { signal } = demoState.abortController;
  const playButton = document.querySelector("#demo-play");
  const loading = document.querySelector("#roll-loading");
  playButton.disabled = true;
  playButton.innerHTML = '<span aria-hidden="true">…</span><b>Loading</b>';
  playButton.setAttribute("aria-label", "Loading selected work");
  loading.hidden = false;
  loading.textContent = "Loading aligned MIDI…";
  document.querySelector("#demo-current").textContent = "00:00.0";
  document.querySelector("#demo-progress").value = 0;

  try {
    const response = await fetch(`demo/notes/${songId}.json`, { signal });
    if (!response.ok) throw new Error("Selected-work metadata is unavailable");
    const data = await response.json();
    if (token !== demoState.loadToken) return;
    demoState.data = data;
    renderDemoMetadata(data);
    buildDemoDownloads(data);
    renderPianoRoll(0);
    document.querySelector("#demo-progress").max = data.duration_seconds;
    document.querySelector("#demo-duration").textContent = formatTime(data.duration_seconds);

    const sources = [
      { label: "Master", path: data.master.path, color: "#271e1b", enabled: true },
      ...data.tracks
        .filter((track) => track.audio_path)
        .map((track) => ({ label: track.label, path: track.audio_path, color: track.color, enabled: false })),
    ];
    let loadedCount = 0;
    const fetched = await Promise.allSettled(
      sources.map(async (source) => {
        const blob = await fetchZipBlob(source.path, signal);
        loadedCount += 1;
        if (token === demoState.loadToken) loading.textContent = `Loading audio ${loadedCount}/${sources.length}…`;
        return { source, blob };
      }),
    );
    if (token !== demoState.loadToken) return;
    const available = fetched.filter((result) => result.status === "fulfilled").map((result) => result.value);
    if (!available.some(({ source }) => source.label === "Master")) {
      throw new Error("The master recording could not be loaded from the release archive");
    }
    const mediaReady = await Promise.allSettled(
      available.map(async ({ source, blob }) => {
        await createAudioControl(source, blob);
        return source.label;
      }),
    );
    if (token !== demoState.loadToken) return;
    const masterIndex = available.findIndex(({ source }) => source.label === "Master");
    if (masterIndex < 0 || mediaReady[masterIndex].status === "rejected") {
      throw new Error("The master recording could not be prepared for playback");
    }

    const master = demoState.audio.get("Master");
    master.addEventListener("ended", () => {
      stopDemoPlayback();
      resetPlayButton();
      updateDemoFrame();
    });
    playButton.disabled = false;
    resetPlayButton();
    loading.hidden = true;
  } catch (error) {
    if (error.name === "AbortError" || token !== demoState.loadToken) return;
    console.error(error);
    loading.hidden = false;
    loading.textContent = `This work could not be loaded: ${error.message}`;
    playButton.innerHTML = '<span aria-hidden="true">!</span><b>Unavailable</b>';
    playButton.setAttribute("aria-label", "Selected work is unavailable");
  }
}

async function initializeDemo() {
  const [catalogResponse, indexResponse] = await Promise.all([
    fetch("data/demo-catalog.json"),
    fetch("data/zenodo-zip-index.json"),
  ]);
  if (!catalogResponse.ok || !indexResponse.ok) throw new Error("Interactive demo catalog unavailable");
  [demoState.catalog, demoState.zipIndex] = await Promise.all([
    catalogResponse.json(),
    indexResponse.json(),
  ]);

  const selector = document.querySelector("#demo-song-select");
  selector.innerHTML = demoState.catalog
    .map((song) => `<option value="${song.id}">${String(song.id).padStart(3, "0")} — ${escapeHtml(song.full_title)}</option>`)
    .join("");
  selector.disabled = false;
  selector.addEventListener("change", () => loadDemoSong(Number(selector.value)));
  document.querySelector("#demo-play").addEventListener("click", toggleDemoPlayback);
  document.querySelector("#demo-progress").addEventListener("input", (event) => {
    const time = Number(event.target.value);
    demoState.audio.forEach((audio) => {
      audio.currentTime = Math.min(time, audio.duration || time);
    });
    updateDemoFrame();
  });
  window.addEventListener("resize", () => {
    const master = demoState.audio.get("Master");
    renderPianoRoll(master?.currentTime || 0);
  });

  const defaultSong = demoState.catalog.some((song) => song.id === 93) ? 93 : demoState.catalog[0].id;
  selector.value = String(defaultSong);
  await loadDemoSong(defaultSong);
}

async function initialize() {
  document.querySelector("#year").textContent = new Date().getFullYear();
  try {
    const [summaryResponse, songsResponse] = await Promise.all([
      fetch("data/release-summary.json"),
      fetch("data/songs.json"),
    ]);
    if (!summaryResponse.ok || !songsResponse.ok) throw new Error("Release metadata unavailable");
    const [summary, songs] = await Promise.all([summaryResponse.json(), songsResponse.json()]);
    state.songs = songs;
    state.filtered = songs;
    renderDatasetStats(summary);
    renderDownloads(summary);
    renderCatalog();
  } catch (error) {
    document.querySelector("#release-status").innerHTML = '<span aria-hidden="true"></span><p><strong>Release metadata could not be loaded.</strong> Please try again shortly.</p>';
    document.querySelector("#catalog-body").innerHTML = '<tr><td colspan="5">Catalog unavailable.</td></tr>';
    console.error(error);
  }

  try {
    await initializeDemo();
  } catch (error) {
    document.querySelector("#roll-loading").textContent = "The interactive catalog could not be loaded.";
    console.error(error);
  }
}

document.querySelector("#catalog-search").addEventListener("input", (event) => {
  const query = event.target.value.trim().toLocaleLowerCase();
  state.filtered = state.songs.filter(
    (song) => String(song.id).includes(query) || song.title.toLocaleLowerCase().includes(query),
  );
  state.expanded = Boolean(query);
  renderCatalog();
});

document.querySelector("#catalog-more").addEventListener("click", () => {
  state.expanded = !state.expanded;
  renderCatalog();
});

initialize();
