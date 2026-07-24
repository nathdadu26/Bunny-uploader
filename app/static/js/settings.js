async function loadBotToken() {
  const res = await fetch("/api/settings/bot");
  const data = await res.json();
  if (data.bot_token) {
    document.getElementById("bot-token-input").value = data.bot_token;
    document.getElementById("bot-token-status").textContent = data.webhook_configured
      ? "Bot token is configured and the webhook is active."
      : "Bot token is configured, but the webhook isn't set up yet (needs PUBLIC_URL in the environment).";
  }
  document.getElementById("stat-bot-name").textContent = data.bot_name
    ? `${data.bot_name}${data.bot_username ? " (@" + data.bot_username + ")" : ""}`
    : "—";
}

async function loadBotStats() {
  const res = await fetch("/api/settings/bot/stats");
  const data = await res.json();
  document.getElementById("stat-total-channels").textContent = data.total_channels;
  document.getElementById("stat-total-posts").textContent = data.total_posts;
  document.getElementById("stat-total-failed").textContent = data.total_failed_posts;
}

document.getElementById("save-bot-token-btn").addEventListener("click", async () => {
  const token = document.getElementById("bot-token-input").value.trim();
  if (!token) return;
  const status = document.getElementById("bot-token-status");
  status.textContent = "Saving…";
  const res = await fetch("/api/settings/bot", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bot_token: token }),
  });
  if (!res.ok) {
    const err = await res.json();
    status.textContent = err.detail || "Failed to save token.";
    return;
  }
  status.textContent = "Saved.";
  loadBotToken();
  loadBotStats();
});

const INTERVAL_OPTIONS = [
  [0, "Manual (post now)"],
  [15, "Every 15 min"],
  [30, "Every 30 min"],
  [60, "Every 1 hour"],
  [120, "Every 2 hours"],
  [360, "Every 6 hours"],
  [720, "Every 12 hours"],
  [1440, "Every 24 hours"],
];

function intervalSelectHtml(current) {
  return INTERVAL_OPTIONS.map(
    ([val, label]) => `<option value="${val}" ${val === current ? "selected" : ""}>${label}</option>`
  ).join("");
}

function renderChannelRow(c) {
  return `
    <tr data-id="${c.id}">
      <td>${c.name}</td>
      <td>${c.channel_id}</td>
      <td><select class="channel-interval-select">${intervalSelectHtml(c.interval_minutes)}</select></td>
      <td><input type="number" min="1" class="channel-qty-input" value="${c.post_quantity}" style="width:64px;" /></td>
      <td>${c.posted_count} / ${c.failed_count}</td>
      <td class="muted">${c.last_posted_at ? new Date(c.last_posted_at).toLocaleString() : "Never"}</td>
      <td><input type="checkbox" class="channel-active-checkbox" ${c.active ? "checked" : ""} /></td>
      <td>
        <button class="action-icon danger" data-action="remove" title="Remove channel">🗑</button>
      </td>
    </tr>
  `;
}

async function loadChannels() {
  const res = await fetch("/api/settings/channels");
  const data = await res.json();
  const tbody = document.getElementById("channels-tbody");
  if (!data.items.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="muted">No channels yet — forward a message from a channel to the bot to add one.</td></tr>`;
    return;
  }
  tbody.innerHTML = data.items.map(renderChannelRow).join("");
  attachChannelRowHandlers();
}

function attachChannelRowHandlers() {
  document.querySelectorAll("#channels-tbody tr").forEach((row) => {
    const id = row.dataset.id;
    if (!id) return;

    row.querySelector(".channel-interval-select").addEventListener("change", (e) => {
      patchChannel(id, { interval_minutes: parseInt(e.target.value, 10) });
    });

    row.querySelector(".channel-qty-input").addEventListener("change", (e) => {
      const qty = parseInt(e.target.value, 10) || 1;
      patchChannel(id, { post_quantity: qty });
    });

    row.querySelector(".channel-active-checkbox").addEventListener("change", (e) => {
      patchChannel(id, { active: e.target.checked });
    });

    row.querySelector('[data-action="remove"]').addEventListener("click", async () => {
      if (!confirm("Remove this channel? It will stop receiving auto-posts.")) return;
      await fetch(`/api/settings/channels/${id}`, { method: "DELETE" });
      loadChannels();
      loadBotStats();
    });
  });
}

async function patchChannel(id, updates) {
  await fetch(`/api/settings/channels/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
}

loadBotToken();
loadBotStats();
loadChannels();
setInterval(loadChannels, 15000);
setInterval(loadBotStats, 15000);
