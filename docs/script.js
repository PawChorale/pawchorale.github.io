const state = {
  songs: [],
  filtered: [],
  expanded: false,
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
    status.innerHTML = '<span aria-hidden="true"></span><p><strong>Release metadata is ready, pending the dataset rights notice.</strong> The public archive links will activate after the terms are approved.</p>';
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
