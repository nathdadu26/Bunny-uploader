function formatBytes(bytes) {
  if (!bytes) return "0 GB";
  const gb = bytes / (1024 ** 3);
  if (gb >= 1) return gb.toFixed(2) + " GB";
  const mb = bytes / (1024 ** 2);
  return mb.toFixed(1) + " MB";
}

async function loadOverview() {
  const res = await fetch("/api/overview");
  const data = await res.json();
  document.getElementById("stat-total-videos").textContent = data.total_videos;
  document.getElementById("stat-storage").textContent = formatBytes(data.total_storage_bytes);
  document.getElementById("stat-views").textContent = data.total_views;
  document.getElementById("stat-processing").textContent = data.processing_count;
  document.getElementById("stat-ready").textContent = data.ready_count;
  document.getElementById("stat-error").textContent = data.error_count;
}

loadOverview();
setInterval(loadOverview, 10000);

// ---------------- Live terminal ----------------

let lastLogTimestamp = null;
const terminalBody = document.getElementById("terminal-body");
const autoscrollCheckbox = document.getElementById("terminal-autoscroll");

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}

function appendLogLine(entry) {
  const line = document.createElement("div");
  line.className = `terminal-line level-${entry.level}`;
  const tag = entry.mapping ? `<span class="tag">[${entry.mapping}]</span>` : "";
  line.innerHTML = `<span class="ts">${formatTime(entry.created_at)}</span>${tag}${entry.message}`;
  terminalBody.appendChild(line);
}

async function pollLogs() {
  const params = new URLSearchParams();
  if (lastLogTimestamp) params.set("since", lastLogTimestamp);
  params.set("limit", "200");

  try {
    const res = await fetch(`/api/logs?${params.toString()}`);
    const data = await res.json();
    if (data.items.length) {
      if (!lastLogTimestamp) {
        terminalBody.innerHTML = ""; // clear the "Waiting for events…" placeholder on first load
      }
      data.items.forEach(appendLogLine);
      lastLogTimestamp = data.items[data.items.length - 1].created_at;

      // Cap rendered lines so the DOM doesn't grow forever on a long-running dashboard tab
      while (terminalBody.children.length > 500) {
        terminalBody.removeChild(terminalBody.firstChild);
      }

      if (autoscrollCheckbox.checked) {
        terminalBody.scrollTop = terminalBody.scrollHeight;
      }
    }
  } catch {
    // transient network hiccup — next poll will retry
  }
}

document.getElementById("terminal-clear-btn").addEventListener("click", () => {
  terminalBody.innerHTML = `<div class="terminal-line muted">Cleared — new events will keep streaming in.</div>`;
});

pollLogs();
setInterval(pollLogs, 2000);
