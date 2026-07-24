const BLACK_PLACEHOLDER =
  "data:image/svg+xml;charset=UTF-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='64' height='36'%3E%3Crect width='64' height='36' fill='%23000'/%3E%3C/svg%3E";

let currentPage = 1;
let currentSearch = "";
let currentStatus = "";
let pollTimer = null;

function statusPill(status, errorReason) {
  const title = status === "ERROR" && errorReason ? ` title="${errorReason.replace(/"/g, "&quot;")}"` : "";
  return `<span class="status-pill status-${status}"${title}>${status}</span>`;
}

function renderRow(item) {
  const thumb = item.thumbnail
    ? `<img src="${item.thumbnail}" />`
    : `<img class="thumb-placeholder" src="${BLACK_PLACEHOLDER}" />`;

  return `
    <tr data-id="${item.id}">
      <td class="thumb-cell">${thumb}</td>
      <td>${item.title || "<span class='muted'>Untitled</span>"}</td>
      <td>${statusPill(item.status, item.error_reason)}</td>
      <td>${item.mapping}</td>
      <td>
        <button class="action-icon" title="Edit" data-action="edit">✎</button>
        <button class="action-icon" title="Play" data-action="play" ${item.status !== "READY" ? "disabled" : ""}>👁</button>
        <button class="action-icon danger" title="Delete" data-action="delete">🗑</button>
      </td>
    </tr>
  `;
}

function renderPagination(page, totalPages) {
  const el = document.getElementById("pagination");
  let html = "";
  for (let i = 1; i <= totalPages; i++) {
    html += `<button class="${i === page ? "active" : ""}" data-page="${i}">${i}</button>`;
  }
  el.innerHTML = html;
  el.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      currentPage = parseInt(btn.dataset.page, 10);
      loadFiles();
    });
  });
}

async function loadFiles() {
  const params = new URLSearchParams({ page: currentPage });
  if (currentSearch) params.set("search", currentSearch);
  if (currentStatus) params.set("status", currentStatus);

  const res = await fetch(`/api/files?${params.toString()}`);
  const data = await res.json();

  const tbody = document.getElementById("files-tbody");
  if (!data.items.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="muted">No videos yet — upload one above.</td></tr>`;
  } else {
    tbody.innerHTML = data.items.map(renderRow).join("");
  }
  renderPagination(data.page, data.total_pages);
  attachRowActions();

  const hasProcessing = data.items.some((i) => i.status === "PROCESSING");
  if (hasProcessing && !pollTimer) {
    pollTimer = setInterval(loadFiles, 8000);
  } else if (!hasProcessing && pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function attachRowActions() {
  document.querySelectorAll(".files-table tbody tr").forEach((row) => {
    const id = row.dataset.id;
    row.querySelectorAll("[data-action]").forEach((btn) => {
      btn.addEventListener("click", () => handleAction(btn.dataset.action, id));
    });
  });
}

async function handleAction(action, id) {
  if (action === "delete") {
    if (!confirm("Delete this video permanently? This removes it from Bunny, R2, and the database.")) return;
    await fetch(`/api/files/${id}`, { method: "DELETE" });
    loadFiles();
  } else if (action === "play") {
    const res = await fetch(`/api/files/${id}`);
    const data = await res.json();
    const master = data.master_playlist || Object.values(data.qualities || {})[0];
    const video = document.getElementById("player-video");
    video.src = master || "";
    document.getElementById("player-modal-backdrop").classList.add("open");
    fetch(`/api/files/${id}/view`, { method: "POST" });
  } else if (action === "edit") {
    const res = await fetch(`/api/files/${id}`);
    const data = await res.json();
    document.getElementById("edit-title-input").value = data.title || "";
    document.getElementById("edit-folder-input").value = data.folder || "";
    document.getElementById("edit-modal-backdrop").dataset.id = id;
    document.getElementById("edit-modal-backdrop").classList.add("open");
  }
}

document.getElementById("player-close").addEventListener("click", () => {
  document.getElementById("player-modal-backdrop").classList.remove("open");
  document.getElementById("player-video").pause();
  document.getElementById("player-video").src = "";
});

document.getElementById("edit-close").addEventListener("click", () => {
  document.getElementById("edit-modal-backdrop").classList.remove("open");
});

document.getElementById("edit-save-btn").addEventListener("click", async () => {
  const backdrop = document.getElementById("edit-modal-backdrop");
  const id = backdrop.dataset.id;
  const title = document.getElementById("edit-title-input").value;
  const folder = document.getElementById("edit-folder-input").value;
  await fetch(`/api/files/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, folder }),
  });
  backdrop.classList.remove("open");
  loadFiles();
});

document.getElementById("search-input").addEventListener("input", (e) => {
  currentSearch = e.target.value;
  currentPage = 1;
  loadFiles();
});

document.getElementById("status-filter").addEventListener("change", (e) => {
  currentStatus = e.target.value;
  currentPage = 1;
  loadFiles();
});

// ---------------- Upload ----------------

function uploadFiles(fileList, folderName) {
  const files = Array.from(fileList);
  if (!files.length) return;

  const container = document.getElementById("upload-progress-list");
  const item = document.createElement("div");
  item.className = "upload-progress-item";
  item.innerHTML = `
    <span>${files.length} file(s)${folderName ? " — folder: " + folderName : ""}</span>
    <div class="progress-bar-track"><div class="progress-bar-fill"></div></div>
  `;
  container.appendChild(item);
  const fill = item.querySelector(".progress-bar-fill");

  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));
  if (folderName) formData.append("folder", folderName);

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload");
  xhr.upload.addEventListener("progress", (e) => {
    if (e.lengthComputable) {
      fill.style.width = `${Math.round((e.loaded / e.total) * 100)}%`;
    }
  });
  xhr.onload = () => {
    fill.style.width = "100%";
    setTimeout(() => item.remove(), 1500);
    loadFiles();
  };
  xhr.onerror = () => {
    item.innerHTML += `<span class="error-text">Upload failed</span>`;
  };
  xhr.send(formData);
}

document.getElementById("file-input").addEventListener("change", (e) => {
  uploadFiles(e.target.files, null);
  e.target.value = "";
});

document.getElementById("folder-input").addEventListener("change", (e) => {
  const first = e.target.files[0];
  const folderName = first && first.webkitRelativePath ? first.webkitRelativePath.split("/")[0] : null;
  uploadFiles(e.target.files, folderName);
  e.target.value = "";
});

const dropZone = document.getElementById("drop-zone");
["dragenter", "dragover"].forEach((evt) =>
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((evt) =>
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
  })
);
dropZone.addEventListener("drop", (e) => {
  uploadFiles(e.dataTransfer.files, null);
});

loadFiles();
