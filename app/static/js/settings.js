async function loadBotToken() {
  const res = await fetch("/api/settings/bot");
  const data = await res.json();
  if (data.bot_token) {
    document.getElementById("bot-token-input").value = data.bot_token;
    document.getElementById("bot-token-status").textContent = "Bot token is configured.";
  }
}

document.getElementById("save-bot-token-btn").addEventListener("click", async () => {
  const token = document.getElementById("bot-token-input").value.trim();
  if (!token) return;
  await fetch("/api/settings/bot", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bot_token: token }),
  });
  document.getElementById("bot-token-status").textContent = "Saved.";
});

function intervalLabel(minutes) {
  const map = {
    0: "Manual (post now)",
    15: "Every 15 min",
    30: "Every 30 min",
    60: "Every 1 hour",
    120: "Every 2 hours",
    360: "Every 6 hours",
    720: "Every 12 hours",
    1440: "Every 24 hours",
  };
  return map[minutes] || `Every ${minutes} min`;
}

function renderChannelRow(c) {
  return `
    <tr data-id="${c.id}">
      <td>${c.name}</td>
      <td>${c.channel_id}</td>
      <td>${intervalLabel(c.interval_minutes)}</td>
      <td>${c.post_quantity}</td>
      <td class="muted">${c.last_posted_at ? new Date(c.last_posted_at).toLocaleString() : "Never"}</td>
      <td>${c.active ? "Yes" : "No"}</td>
      <td>
        <button class="action-icon" data-action="post-now" title="Post now">▶</button>
        <button class="action-icon" data-action="verify" title="Verify bot is admin">✔</button>
        <button class="action-icon danger" data-action="delete" title="Delete">🗑</button>
      </td>
    </tr>
  `;
}

async function loadChannels() {
  const res = await fetch("/api/settings/channels");
  const data = await res.json();
  const tbody = document.getElementById("channels-tbody");
  if (!data.items.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted">No channels added yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = data.items.map(renderChannelRow).join("");
  tbody.querySelectorAll("[data-action]").forEach((btn) => {
    const id = btn.closest("tr").dataset.id;
    btn.addEventListener("click", () => handleChannelAction(btn.dataset.action, id));
  });
}

async function handleChannelAction(action, id) {
  if (action === "delete") {
    if (!confirm("Remove this channel?")) return;
    await fetch(`/api/settings/channels/${id}`, { method: "DELETE" });
    loadChannels();
  } else if (action === "post-now") {
    const res = await fetch(`/api/settings/channels/${id}/post-now`, { method: "POST" });
    const data = await res.json();
    alert(`Posted ${data.posted} video(s).`);
    loadChannels();
  } else if (action === "verify") {
    const res = await fetch(`/api/settings/channels/${id}/verify-admin`);
    const data = await res.json();
    const status = data.result && data.result.status;
    alert(status ? `Bot status in this channel: ${status}` : "Could not verify — check bot token/channel ID.");
  }
}

document.getElementById("add-channel-btn").addEventListener("click", async () => {
  const name = document.getElementById("channel-name-input").value.trim();
  const channel_id = document.getElementById("channel-id-input").value.trim();
  const interval_minutes = parseInt(document.getElementById("channel-interval-input").value, 10);
  const post_quantity = parseInt(document.getElementById("channel-quantity-input").value, 10) || 1;

  if (!name || !channel_id) {
    alert("Name and Channel ID are required.");
    return;
  }

  const res = await fetch("/api/settings/channels", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, channel_id, interval_minutes, post_quantity, active: true }),
  });

  if (!res.ok) {
    const err = await res.json();
    alert(err.detail || "Failed to add channel");
    return;
  }

  document.getElementById("channel-name-input").value = "";
  document.getElementById("channel-id-input").value = "";
  document.getElementById("channel-quantity-input").value = "1";
  loadChannels();
});

loadBotToken();
loadChannels();
