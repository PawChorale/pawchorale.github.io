const state = {
  songs: [],
  filtered: [],
  expanded: false,
};

const demoState = {
  data: null,
  audio: new Map(),
  playing: false,
  frame: null,
};

const formatBytes = (bytes) => {
  const gib = bytes / 1024 ** 3;
  return `${gib.toFixed(2)} GiB`;
};

const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

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
          <p>${archive.song_count} curated works · MP3 + MIDI + manifests</p>
          ${action}
        </article>`;
    })
    .join("");

  if (enabled) {
    status.classList.add("ready");
    status.innerHTML = '<span aria-hidden="true"></span><p><strong>Version 1.0.0 is available.</strong> Download all four parts for the complete release.</p>';
  } else {
    status.innerHTML = '<span aria-hidden="true"></span><p><strong>Full archives are not public yet.</strong> The 205-work package is prepared and awaiting four source permissions; the catalog and example files are available above.</p>';
  }
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

const formatTime = (seconds) => {
  const safe = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
  const minutes = Math.floor(safe / 60);
  const remainder = safe - minutes * 60;
  return `${String(minutes).padStart(2, "0")}:${remainder.toFixed(1).padStart(4, "0")}`;
};

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
  const laneHeight = (height - topPad - bottomPad) / demoState.data.tracks.length;
  const duration = demoState.data.duration_seconds;

  context.fillStyle = "#2c2421";
  context.fillRect(0, 0, width, height);
  context.font = "11px ui-monospace, SFMono-Regular, Menlo, monospace";
  context.textBaseline = "middle";

  for (let second = 0; second <= duration; second += 5) {
    const x = labelWidth + (second / duration) * plotWidth;
    context.strokeStyle = second % 10 === 0 ? "rgba(255,255,255,.14)" : "rgba(255,255,255,.07)";
    context.beginPath();
    context.moveTo(x, topPad - 10);
    context.lineTo(x, height - bottomPad);
    context.stroke();
    if (second % 10 === 0) {
      context.fillStyle = "rgba(255,255,255,.45)";
      context.fillText(`${second}s`, x + 4, 11);
    }
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
    context.fillText(track.part.slice(0, 1), 26, laneTop + laneHeight / 2);

    const pitchRange = Math.max(1, track.pitch_max - track.pitch_min);
    track.notes.forEach((note) => {
      const x = labelWidth + (note.start / duration) * plotWidth;
      const noteWidth = Math.max(2, ((note.end - note.start) / duration) * plotWidth - 1);
      const relativePitch = (note.pitch - track.pitch_min) / pitchRange;
      const y = laneTop + laneHeight - 12 - relativePitch * (laneHeight - 24);
      context.fillStyle = track.color;
      context.globalAlpha = 0.9;
      context.fillRect(x, y, noteWidth, 5);
    });
    context.globalAlpha = 1;
  });

  const playhead = labelWidth + (time / duration) * plotWidth;
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
        audio.currentTime = current;
      }
    });
    demoState.frame = requestAnimationFrame(updateDemoFrame);
  }
}

async function toggleDemoPlayback() {
  const master = demoState.audio.get("Master");
  if (!master) return;
  const button = document.querySelector("#demo-play");
  if (demoState.playing) {
    demoState.audio.forEach((audio) => audio.pause());
    demoState.playing = false;
    cancelAnimationFrame(demoState.frame);
    button.innerHTML = '<span aria-hidden="true">▶</span><b>Play</b>';
    button.setAttribute("aria-label", "Play demo");
    return;
  }

  const position = master.ended ? 0 : master.currentTime;
  demoState.audio.forEach((audio) => { audio.currentTime = position; });
  try {
    const results = await Promise.allSettled(
      [...demoState.audio.values()].map((audio) => audio.play()),
    );
    if (master.paused) throw new Error("Master audio was blocked by the browser");
    if (results.some((result) => result.status === "rejected")) {
      console.warn("One or more muted demo stems could not start; the master remains available.");
    }
    demoState.playing = true;
    button.innerHTML = '<span aria-hidden="true">Ⅱ</span><b>Pause</b>';
    button.setAttribute("aria-label", "Pause demo");
    updateDemoFrame();
  } catch (error) {
    console.error("Demo playback could not start", error);
  }
}

function buildDemoDownloads(data) {
  const files = [
    [data.master_file, "master"],
    ...data.tracks.flatMap((track) => [[track.audio_file, track.part], [track.midi_file, "MIDI"]]),
    [data.source.manifest_file, "metadata"],
    ["RIGHTS_NOTICE.md", "rights"],
  ];
  document.querySelector("#demo-download-list").innerHTML = files
    .map(([filename, kind]) => `<a href="demo/93/${escapeHtml(filename)}" download><span>${escapeHtml(filename)}</span><em>${escapeHtml(kind)} ↓</em></a>`)
    .join("");
}

async function initializeDemo() {
  const response = await fetch("demo/93/notes.json");
  if (!response.ok) throw new Error("Demo metadata unavailable");
  demoState.data = await response.json();

  const sources = [
    { part: "Master", audio_file: demoState.data.master_file, color: "#271e1b", enabled: true },
    ...demoState.data.tracks.map((track) => ({ ...track, enabled: false })),
  ];
  const bank = document.querySelector("#demo-audio-bank");
  const controls = document.querySelector("#track-controls");
  const mediaReady = [];
  sources.forEach((source) => {
    const audio = document.createElement("audio");
    audio.src = `demo/93/${source.audio_file}`;
    audio.preload = "metadata";
    audio.muted = !source.enabled;
    bank.append(audio);
    demoState.audio.set(source.part, audio);
    mediaReady.push(new Promise((resolve, reject) => {
      if (audio.readyState >= 1) {
        resolve();
        return;
      }
      audio.addEventListener("loadedmetadata", resolve, { once: true });
      audio.addEventListener(
        "error",
        () => reject(new Error(`${source.audio_file} could not load`)),
        { once: true },
      );
    }));

    const label = document.createElement("label");
    label.className = "track-toggle";
    label.style.setProperty("--track-color", source.color);
    label.innerHTML = `<input type="checkbox" ${source.enabled ? "checked" : ""} aria-label="Toggle ${escapeHtml(source.part)} audio"><span>${escapeHtml(source.part)}</span>`;
    label.querySelector("input").addEventListener("change", (event) => {
      audio.muted = !event.target.checked;
    });
    controls.append(label);
  });

  const master = demoState.audio.get("Master");
  master.addEventListener("ended", () => {
    demoState.playing = false;
    demoState.audio.forEach((audio) => audio.pause());
    document.querySelector("#demo-play").innerHTML = '<span aria-hidden="true">▶</span><b>Play</b>';
    updateDemoFrame();
  });
  document.querySelector("#demo-progress").max = demoState.data.duration_seconds;
  document.querySelector("#demo-duration").textContent = formatTime(demoState.data.duration_seconds);
  const playButton = document.querySelector("#demo-play");
  playButton.addEventListener("click", toggleDemoPlayback);
  document.querySelector("#demo-progress").addEventListener("input", (event) => {
    const time = Number(event.target.value);
    demoState.audio.forEach((audio) => { audio.currentTime = time; });
    updateDemoFrame();
  });
  window.addEventListener("resize", () => renderPianoRoll(master.currentTime));
  await Promise.all(mediaReady);
  playButton.disabled = false;
  playButton.setAttribute("aria-label", "Play demo");
  playButton.innerHTML = '<span aria-hidden="true">▶</span><b>Play</b>';
  document.querySelector("#roll-loading").hidden = true;
  buildDemoDownloads(demoState.data);
  renderPianoRoll(0);
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
    renderDownloads(summary);
    renderCatalog();
    await initializeDemo();
  } catch (error) {
    document.querySelector("#release-status").innerHTML = '<span aria-hidden="true"></span><p><strong>Release metadata could not be loaded.</strong> Please try again shortly.</p>';
    document.querySelector("#catalog-body").innerHTML = '<tr><td colspan="5">Catalog unavailable.</td></tr>';
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
