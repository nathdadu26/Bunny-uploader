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
