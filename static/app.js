const state = {
  rangeName: document.body.dataset.defaultRange || "7d",
  startDate: "",
  endDate: "",
  logsPage: 1,
  logsTotalPages: 1,
};

function byId(id) {
  return document.getElementById(id);
}

function setMessage(id, text, isError = false) {
  const box = byId(id);
  box.textContent = text || "";
  box.classList.toggle("hidden", !text);
  box.style.background = isError ? "rgba(191, 61, 61, 0.12)" : "rgba(39, 93, 74, 0.08)";
  box.style.color = isError ? "#983131" : "#2d7558";
}

function formatNumber(value) {
  return new Intl.NumberFormat("zh-CN").format(value || 0);
}

function formatSpend(value) {
  return `¥/美元 ${Number(value || 0).toFixed(6)}`;
}

function formatTime(value) {
  if (!value) return "-";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString("zh-CN", { hour12: false });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    let message = `请求失败：${response.status}`;
    try {
      const detail = await response.json();
      message = detail?.detail?.error?.message || detail?.detail?.message || detail?.message || message;
    } catch (error) {
      // ignore
    }
    throw new Error(message);
  }
  return response.json();
}

function queryString(extra = {}) {
  const params = new URLSearchParams();
  if (state.startDate && state.endDate) {
    params.set("start_date", state.startDate);
    params.set("end_date", state.endDate);
  } else {
    params.set("range_name", state.rangeName);
  }
  Object.entries(extra).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, value);
    }
  });
  return params.toString();
}

function renderVerticalBars(containerId, items, limit = 24) {
  const container = byId(containerId);
  container.innerHTML = "";
  const rows = (items || []).slice(-limit);
  if (!rows.length) {
    container.innerHTML = '<div class="muted-pill">当前时间段没有数据</div>';
    return;
  }
  const maxValue = Math.max(...rows.map((item) => item.value), 1);
  rows.forEach((item) => {
    const node = document.createElement("div");
    node.className = "bar-column";
    const height = Math.max(4, Math.round((item.value / maxValue) * 180));
    node.innerHTML = `
      <span class="bar-value">${formatNumber(item.value)}</span>
      <div class="bar" style="height:${height}px" title="${item.label}: ${item.value}"></div>
      <span class="bar-label" title="${item.label}">${item.label}</span>
    `;
    container.appendChild(node);
  });
}

function renderHorizontalBars(containerId, items) {
  const container = byId(containerId);
  container.innerHTML = "";
  if (!items || !items.length) {
    container.innerHTML = '<div class="muted-pill">还没有虚拟密钥使用记录</div>';
    return;
  }
  const maxValue = Math.max(...items.map((item) => item.value), 1);
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = `
      <span class="row-label" title="${item.label}">${item.label}</span>
      <div class="row-track"><div class="row-fill" style="width:${Math.max(4, (item.value / maxValue) * 100)}%"></div></div>
      <span class="row-value">${formatNumber(item.value)}</span>
    `;
    container.appendChild(row);
  });
}

function renderModels(rows) {
  const tbody = byId("modelsTable");
  tbody.innerHTML = "";
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="5">暂无模型</td></tr>';
    return;
  }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    const deleteButton = row.can_delete
      ? `<button class="ghost-button delete-model" data-model-id="${row.id}">删除</button>`
      : `<span class="muted-pill">配置模型</span>`;
    tr.innerHTML = `
      <td><strong>${row.model_name}</strong><br><span class="section-copy">${row.description || ""}</span></td>
      <td>${row.upstream_model || "-"}</td>
      <td><code>${row.api_base || "-"}</code></td>
      <td>${row.status_text}</td>
      <td>${deleteButton}</td>
    `;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll(".delete-model").forEach((button) => {
    button.addEventListener("click", async () => {
      const modelId = button.dataset.modelId;
      if (!confirm("确认删除这个数据库模型吗？")) return;
      try {
        await api(`/api/models/${modelId}`, { method: "DELETE" });
        await loadModels();
        await loadDashboard();
      } catch (error) {
        alert(error.message);
      }
    });
  });
}

function renderKeys(rows) {
  const tbody = byId("keysTable");
  tbody.innerHTML = "";
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="4">暂无虚拟密钥</td></tr>';
    return;
  }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.key_alias}</td>
      <td>${formatSpend(row.spend)}</td>
      <td>${row.models.length ? row.models.join(", ") : "全部模型"}</td>
      <td>${row.expires ? formatTime(row.expires) : "不过期"}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderLogs(rows) {
  const tbody = byId("logsTable");
  tbody.innerHTML = "";
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="9">当前范围没有请求记录</td></tr>';
    return;
  }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${formatTime(row.time)}</td>
      <td>${row.model}</td>
      <td>${row.key_name}</td>
      <td>${row.status}</td>
      <td>${formatNumber(row.total_tokens)}</td>
      <td>${formatSpend(row.spend)}</td>
      <td>${formatNumber(row.duration_ms)}</td>
      <td><code>${row.request_id}</code></td>
      <td>${row.error_message || "-"}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function loadDashboard() {
  const data = await api(`/api/dashboard?${queryString()}`);
  byId("requestsCount").textContent = formatNumber(data.cards.requests);
  byId("tokensCount").textContent = formatNumber(data.cards.tokens);
  byId("spendCount").textContent = formatSpend(data.cards.spend);
  byId("failuresCount").textContent = formatNumber(data.cards.failures);
  byId("modelCount").textContent = formatNumber(data.system.model_count);
  byId("keyCount").textContent = formatNumber(data.system.key_count);
  byId("gatewayBadge").textContent = `网关已连接 · ${data.system.gateway_url}`;
  byId("hourlyRangeLabel").textContent = `${data.range.start_date} 到 ${data.range.end_date}`;

  renderVerticalBars("hourlyChart", data.hourly_requests, state.rangeName === "24h" ? 24 : 48);
  renderVerticalBars("dailyChart", data.daily_tokens, 30);
  renderHorizontalBars("keyChart", data.key_requests);
  renderLogs(data.recent_logs || []);

  const warning = byId("metaWarning");
  if (data.meta.truncated) {
    warning.textContent = `当前统计只加载了前 ${data.meta.loaded_pages} 页日志。若历史数据很多，建议缩小时间范围。`;
    warning.classList.remove("hidden");
  } else {
    warning.classList.add("hidden");
  }
}

async function loadLogs(page = 1) {
  const data = await api(`/api/logs?${queryString({ page, page_size: 20 })}`);
  state.logsPage = data.page;
  state.logsTotalPages = data.total_pages || 1;
  byId("logsPageText").textContent = `第 ${data.page} / ${state.logsTotalPages} 页`;
  renderLogs(data.data || []);
}

async function loadModels() {
  const data = await api("/api/models");
  renderModels(data.data || []);
}

async function loadKeys() {
  const data = await api("/api/keys");
  renderKeys(data.data || []);
}

function setActiveRange(rangeName) {
  state.rangeName = rangeName;
  state.startDate = "";
  state.endDate = "";
  document.querySelectorAll(".range-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.range === rangeName);
  });
}

async function refreshAll() {
  await Promise.all([loadDashboard(), loadModels(), loadKeys()]);
  await loadLogs(1);
}

async function bootstrap() {
  const init = await api("/api/bootstrap");
  byId("modelCount").textContent = formatNumber(init.system.model_count);
  byId("keyCount").textContent = formatNumber(init.system.key_count);
  byId("gatewayBadge").textContent = `网关已连接 · ${init.system.gateway_url}`;
  renderModels(init.models || []);
  renderKeys(init.keys || []);
  await loadDashboard();
  await loadLogs(1);
}

document.querySelectorAll(".range-button").forEach((button) => {
  button.addEventListener("click", async () => {
    setActiveRange(button.dataset.range);
    await loadDashboard();
    await loadLogs(1);
  });
});

byId("applyCustomRange").addEventListener("click", async () => {
  const start = byId("startDate").value;
  const end = byId("endDate").value;
  if (!start || !end) {
    alert("请选择开始和结束日期。");
    return;
  }
  state.startDate = start;
  state.endDate = end;
  document.querySelectorAll(".range-button").forEach((button) => button.classList.remove("active"));
  await loadDashboard();
  await loadLogs(1);
});

byId("modelForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(event.target);
  const payload = Object.fromEntries(formData.entries());
  payload.rpm = payload.rpm ? Number(payload.rpm) : 600;
  try {
    await api("/api/models", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    event.target.reset();
    setMessage("modelFormMessage", "模型已注册。");
    await loadModels();
    await loadDashboard();
  } catch (error) {
    setMessage("modelFormMessage", error.message, true);
  }
});

byId("keyForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(event.target);
  const models = String(formData.get("models") || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const payload = {
    key_alias: formData.get("key_alias"),
    duration: formData.get("duration"),
    models,
    max_budget: formData.get("max_budget") ? Number(formData.get("max_budget")) : null,
  };
  try {
    const response = await api("/api/keys", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const output = byId("newKeyOutput");
    output.classList.remove("hidden");
    output.value = JSON.stringify(response.data, null, 2);
    setMessage("keyFormMessage", "密钥已生成，请立即保存返回结果中的真实 key。");
    event.target.reset();
    await loadKeys();
    await loadDashboard();
  } catch (error) {
    setMessage("keyFormMessage", error.message, true);
  }
});

byId("refreshModels").addEventListener("click", async () => {
  await loadModels();
});

byId("refreshKeys").addEventListener("click", async () => {
  await loadKeys();
});

byId("prevLogsPage").addEventListener("click", async () => {
  if (state.logsPage > 1) {
    await loadLogs(state.logsPage - 1);
  }
});

byId("nextLogsPage").addEventListener("click", async () => {
  if (state.logsPage < state.logsTotalPages) {
    await loadLogs(state.logsPage + 1);
  }
});

bootstrap().catch((error) => {
  alert(`初始化失败：${error.message}`);
});
