const state = {
  rangeName: document.body.dataset.defaultRange || "24h",
  startDate: "",
  endDate: "",
  logRangeName: "30d",
  logStartDate: "",
  logEndDate: "",
  logsPage: 1,
  logsTotalPages: 1,
  logsTotal: 0,
  logsPageSize: 20,
  activeSection: "usageSection",
};

const seriesConfig = [
  { key: "spend", label: "成本", color: "#ff4d67", dashed: true, money: true },
  { key: "input", label: "输入", color: "#377dff" },
  { key: "output", label: "输出", color: "#10b981" },
  { key: "cached", label: "缓存命中", color: "#9a4cff", area: true },
  { key: "cache_create", label: "缓存创建", color: "#f59e0b" },
];

function byId(id) {
  return document.getElementById(id);
}

function showToast(text, isError = false) {
  const toast = byId("toast");
  toast.textContent = text;
  toast.style.background = isError ? "#be123c" : "#111827";
  toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), 4200);
}

function setMessage(id, text, isError = false) {
  const box = byId(id);
  box.textContent = text || "";
  box.classList.toggle("hidden", !text);
  box.style.background = isError ? "#fff1f2" : "#e8fbf4";
  box.style.color = isError ? "#be123c" : "#047857";
}

function formatNumber(value) {
  return new Intl.NumberFormat("zh-CN").format(Math.round(Number(value || 0)));
}

function formatCompact(value) {
  const number = Number(value || 0);
  if (number >= 100000000) return `${(number / 100000000).toFixed(2)} 亿`;
  if (number >= 10000) return `${(number / 10000).toFixed(1)} 万`;
  return formatNumber(number);
}

function formatSpend(value) {
  return `¥ ${Number(value || 0).toFixed(6)}`;
}

function formatMs(value) {
  const number = Number(value || 0);
  if (number >= 1000) return `${(number / 1000).toFixed(2)}s`;
  return `${Math.round(number)}ms`;
}

function formatTime(value) {
  if (!value) return "-";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString("zh-CN", { hour12: false });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
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
      message =
        detail?.detail?.error?.message ||
        detail?.detail?.message ||
        detail?.detail ||
        detail?.message ||
        message;
    } catch (error) {
      // Keep the default message when the response is not JSON.
    }
    throw new Error(String(message));
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

function logsQueryString(extra = {}) {
  const params = new URLSearchParams();
  if (state.logStartDate && state.logEndDate) {
    params.set("start_date", state.logStartDate);
    params.set("end_date", state.logEndDate);
  } else {
    params.set("range_name", state.logRangeName);
  }
  Object.entries(extra).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, value);
    }
  });
  return params.toString();
}

function chartPoint(index, value, rows, maxValue, width, height, pad) {
  const usableWidth = width - pad.left - pad.right;
  const usableHeight = height - pad.top - pad.bottom;
  const x = pad.left + (rows.length === 1 ? usableWidth / 2 : (index / (rows.length - 1)) * usableWidth);
  const y = pad.top + usableHeight - (Number(value || 0) / maxValue) * usableHeight;
  return [x, y];
}

function pathFromPoints(points) {
  return points.map((point, index) => `${index === 0 ? "M" : "L"}${point[0].toFixed(2)},${point[1].toFixed(2)}`).join(" ");
}

function renderUsageChart(rows) {
  const container = byId("usageChart");
  const data = (rows || []).slice(-48);
  if (!data.length) {
    container.innerHTML = '<div class="muted-pill">当前时间段没有统计数据</div>';
    return;
  }

  const width = 1180;
  const height = 360;
  const pad = { top: 22, right: 64, bottom: 46, left: 58 };
  const tokenMax = Math.max(...data.flatMap((row) => [row.input, row.output, row.cached, row.cache_create]), 1);
  const spendMax = Math.max(...data.map((row) => row.spend), 1);
  const tokenGrid = [0, 0.25, 0.5, 0.75, 1];
  const xLabels = data.filter((_, index) => index % Math.max(1, Math.ceil(data.length / 8)) === 0);

  const lines = seriesConfig.map((series) => {
    const max = series.money ? spendMax : tokenMax;
    const points = data.map((row, index) => chartPoint(index, row[series.key], data, max, width, height, pad));
    const path = pathFromPoints(points);
    const areaPath = `${path} L${points[points.length - 1][0].toFixed(2)},${height - pad.bottom} L${points[0][0].toFixed(2)},${height - pad.bottom} Z`;
    return `
      ${series.area ? `<path d="${areaPath}" fill="${series.color}" opacity="0.12"></path>` : ""}
      <path d="${path}" fill="none" stroke="${series.color}" stroke-width="${series.money ? 2.4 : 2}" ${series.dashed ? 'stroke-dasharray="7 6"' : ""}></path>
    `;
  }).join("");

  const grid = tokenGrid.map((tick) => {
    const y = pad.top + (1 - tick) * (height - pad.top - pad.bottom);
    return `
      <line x1="${pad.left}" x2="${width - pad.right}" y1="${y}" y2="${y}" stroke="#edf0f6"></line>
      <text x="${pad.left - 10}" y="${y + 4}" text-anchor="end" fill="#6b7280" font-size="12">${formatCompact(tokenMax * tick)}</text>
      <text x="${width - pad.right + 10}" y="${y + 4}" fill="#6b7280" font-size="12">${formatSpend(spendMax * tick)}</text>
    `;
  }).join("");

  const labels = xLabels.map((row) => {
    const index = data.indexOf(row);
    const [x] = chartPoint(index, 0, data, tokenMax, width, height, pad);
    return `<text x="${x}" y="${height - 16}" text-anchor="middle" fill="#6b7280" font-size="12">${escapeHtml(row.label)}</text>`;
  }).join("");

  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="分时消耗趋势图">
      <rect x="0" y="0" width="${width}" height="${height}" rx="8" fill="#fff"></rect>
      ${grid}
      ${lines}
      ${labels}
    </svg>
  `;
}

function renderRank(containerId, rows) {
  const container = byId(containerId);
  container.innerHTML = "";
  if (!rows || !rows.length) {
    container.innerHTML = '<div class="muted-pill">当前范围暂无数据</div>';
    return;
  }
  const maxTokens = Math.max(...rows.map((row) => row.tokens), 1);
  rows.forEach((row) => {
    const node = document.createElement("div");
    node.className = "rank-row";
    node.innerHTML = `
      <span class="rank-label" title="${escapeHtml(row.label)}">${escapeHtml(row.label)}</span>
      <div class="rank-track"><div class="rank-fill" style="width:${Math.max(3, (row.tokens / maxTokens) * 100)}%"></div></div>
      <span class="rank-meta">${formatCompact(row.tokens)} · ${formatSpend(row.spend)}</span>
    `;
    container.appendChild(node);
  });
}

function renderModels(rows) {
  const tbody = byId("modelsTable");
  tbody.innerHTML = "";
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="6">暂无模型</td></tr>';
    return;
  }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    const price = row.input_price || row.output_price
      ? `入 ¥${row.input_price ?? "-"} / 出 ¥${row.output_price ?? "-"}`
      : "-";
    const deleteButton = row.can_delete
      ? `<button class="ghost-button delete-model" data-model-id="${escapeHtml(row.id)}" type="button">删除</button>`
      : `<span class="muted-pill">配置模型</span>`;
    tr.innerHTML = `
      <td><span class="cell-main">${escapeHtml(row.model_name)}</span><span class="cell-sub">${escapeHtml(row.description || "")}</span></td>
      <td>${escapeHtml(row.upstream_model || "-")}</td>
      <td>${escapeHtml(row.context_window || "-")}</td>
      <td>${escapeHtml(price)}</td>
      <td><code>${escapeHtml(row.api_base || "-")}</code></td>
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
        showToast("模型已删除");
      } catch (error) {
        showToast(error.message, true);
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
      <td><span class="cell-main">${escapeHtml(row.key_alias)}</span><span class="cell-sub">${escapeHtml(row.user_id || "")}</span></td>
      <td>${formatSpend(row.spend)}</td>
      <td>${row.models.length ? escapeHtml(row.models.join(", ")) : "全部模型"}</td>
      <td>${row.expires ? formatTime(row.expires) : "不过期"}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderLogs(rows) {
  const tbody = byId("logsTable");
  tbody.innerHTML = "";
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="11">当前范围没有请求记录</td></tr>';
    return;
  }
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    const statusClass = row.status === "失败" ? "status-fail" : "status-ok";
    tr.innerHTML = `
      <td>${formatTime(row.time)}</td>
      <td>${escapeHtml(row.model)}</td>
      <td>${escapeHtml(row.key_name)}</td>
      <td><span class="${statusClass}">${escapeHtml(row.status_code || row.status)}</span></td>
      <td><span class="cell-main">${formatNumber(row.input_tokens)}</span><span class="cell-sub">总 ${formatNumber(row.total_tokens)}</span></td>
      <td><span class="cell-main">${formatNumber(row.output_tokens)}</span><span class="cell-sub">推理 ${formatNumber(row.reasoning_tokens)}</span></td>
      <td><span class="cell-main">${formatNumber(row.cached_tokens)}</span><span class="cell-sub">${row.cache_hit ? "命中" : "未命中"}</span></td>
      <td>${formatNumber(row.cache_creation_tokens)}</td>
      <td>${formatSpend(row.spend)}</td>
      <td>${formatMs(row.duration_ms)}</td>
      <td><code title="${escapeHtml(row.error_message || "")}">${escapeHtml(row.request_id || "-")}</code></td>
    `;
    tbody.appendChild(tr);
  });
}

function updateCards(data) {
  const cards = data.cards || {};
  byId("requestsCount").textContent = formatNumber(cards.requests);
  byId("tokensCount").textContent = formatNumber(cards.total_tokens);
  byId("spendCount").textContent = formatSpend(cards.spend);
  byId("successRate").textContent = `${Number(cards.success_rate || 0).toFixed(1)}%`;
  byId("inputTokens").textContent = formatCompact(cards.input_tokens);
  byId("outputTokens").textContent = formatCompact(cards.output_tokens);
  byId("cachedTokens").textContent = formatCompact(cards.cached_tokens);
  byId("cacheCreateTokens").textContent = formatCompact(cards.cache_creation_tokens);
  byId("reasoningTokens").textContent = formatCompact(cards.reasoning_tokens);
  byId("avgLatency").textContent = formatMs(cards.avg_latency_ms);
  byId("cacheHitRate").textContent = `${Number(cards.cache_hit_rate || 0).toFixed(1)}%`;
  byId("cacheHitBar").style.width = `${Math.min(100, Number(cards.cache_hit_rate || 0))}%`;
  byId("rangeText").textContent = `${data.range.start_date} 至 ${data.range.end_date}`;
  byId("gatewayBadge").textContent = `网关已连接 · ${data.system.gateway_url}`;
}

async function loadDashboard() {
  const data = await api(`/api/dashboard?${queryString()}`);
  updateCards(data);
  renderUsageChart(data.hourly_usage || []);
  renderRank("keyUsage", data.key_usage || []);
  renderRank("modelUsage", data.model_usage || []);
  const warning = byId("metaWarning");
  if (data.warnings?.length) {
    warning.textContent = `网关部分接口不可用：${data.warnings.join("；")}`;
    warning.classList.remove("hidden");
  } else if (data.meta?.truncated) {
    warning.textContent = `当前统计只加载了前 ${data.meta.loaded_pages} 页日志。历史数据较多时建议缩小时间范围。`;
    warning.classList.remove("hidden");
  } else {
    warning.classList.add("hidden");
  }
}

async function loadLogs(page = 1) {
  const nextPage = Math.max(1, Number(page || 1));
  const data = await api(`/api/logs?${logsQueryString({ page: nextPage, page_size: state.logsPageSize })}`);
  state.logsPage = data.page;
  state.logsTotalPages = data.total_pages || 1;
  state.logsTotal = data.total || 0;
  byId("logsPageText").textContent = `第 ${data.page} / ${state.logsTotalPages} 页`;
  byId("logsTotalText").textContent = `共 ${formatNumber(state.logsTotal)} 条记录`;
  byId("logsPageInput").value = data.page;
  byId("logsPageInput").max = state.logsTotalPages;
  renderLogs(data.data || []);
  if (data.warning) showToast(`请求日志暂不可用：${data.warning}`, true);
}

async function loadModels() {
  const data = await api("/api/models");
  renderModels(data.data || []);
  if (data.warning) showToast(`模型列表暂不可用：${data.warning}`, true);
}

async function loadKeys() {
  const data = await api("/api/keys");
  renderKeys(data.data || []);
  if (data.warning) showToast(`密钥列表暂不可用：${data.warning}`, true);
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
  try {
    await Promise.all([loadDashboard(), loadModels(), loadKeys()]);
    if (state.activeSection === "logsSection") await loadLogs(1);
  } catch (error) {
    showToast(`初始化失败：${error.message}`, true);
  }
}

async function bootstrap() {
  const init = await api("/api/bootstrap");
  byId("gatewayBadge").textContent = `网关已连接 · ${init.system.gateway_url}`;
  renderModels(init.models || []);
  renderKeys(init.keys || []);
  if (init.warnings?.length) showToast(`网关部分接口不可用：${init.warnings.join("；")}`, true);
  await loadDashboard();
}

document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", async () => {
    document.querySelectorAll(".tab-button").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".view-section").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    byId(button.dataset.target).classList.add("active");
    state.activeSection = button.dataset.target;
    if (state.activeSection === "logsSection") {
      await loadLogs(state.logsPage || 1);
    }
  });
});

document.querySelectorAll(".range-button").forEach((button) => {
  button.addEventListener("click", async () => {
    setActiveRange(button.dataset.range);
    state.logsPage = 1;
    await loadDashboard();
    if (state.activeSection === "logsSection") await loadLogs(1);
  });
});

document.querySelectorAll(".log-range-button").forEach((button) => {
  button.addEventListener("click", async () => {
    state.logRangeName = button.dataset.logRange;
    state.logStartDate = "";
    state.logEndDate = "";
    state.logsPage = 1;
    document.querySelectorAll(".log-range-button").forEach((item) => {
      item.classList.toggle("active", item === button);
    });
    await loadLogs(1);
  });
});

byId("applyLogsRange").addEventListener("click", async () => {
  const start = byId("logsStartDate").value;
  const end = byId("logsEndDate").value;
  if (!start || !end) {
    showToast("请选择日志开始和结束日期。", true);
    return;
  }
  state.logStartDate = start;
  state.logEndDate = end;
  state.logsPage = 1;
  document.querySelectorAll(".log-range-button").forEach((button) => button.classList.remove("active"));
  await loadLogs(1);
});

byId("applyCustomRange").addEventListener("click", async () => {
  const start = byId("startDate").value;
  const end = byId("endDate").value;
  if (!start || !end) {
    showToast("请选择开始和结束日期。", true);
    return;
  }
  state.startDate = start;
  state.endDate = end;
  state.logsPage = 1;
  document.querySelectorAll(".range-button").forEach((button) => button.classList.remove("active"));
  await loadDashboard();
  if (state.activeSection === "logsSection") await loadLogs(1);
});

byId("modelForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(event.target);
  const payload = Object.fromEntries(formData.entries());
  payload.rpm = payload.rpm ? Number(payload.rpm) : 600;
  try {
    await api("/api/models", { method: "POST", body: JSON.stringify(payload) });
    event.target.reset();
    setMessage("modelFormMessage", "模型已注册。");
    await loadModels();
    await loadDashboard();
    if (state.activeSection === "logsSection") await loadLogs(1);
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
    const response = await api("/api/keys", { method: "POST", body: JSON.stringify(payload) });
    const output = byId("newKeyOutput");
    output.classList.remove("hidden");
    output.value = JSON.stringify(response.data, null, 2);
    setMessage("keyFormMessage", "密钥已生成，请立即保存返回结果中的真实 key。");
    event.target.reset();
    await loadKeys();
    await loadDashboard();
    if (state.activeSection === "logsSection") await loadLogs(1);
  } catch (error) {
    setMessage("keyFormMessage", error.message, true);
  }
});

byId("refreshModels").addEventListener("click", loadModels);
byId("refreshKeys").addEventListener("click", loadKeys);
byId("refreshAll").addEventListener("click", refreshAll);

byId("prevLogsPage").addEventListener("click", async () => {
  if (state.logsPage > 1) await loadLogs(state.logsPage - 1);
});

byId("nextLogsPage").addEventListener("click", async () => {
  if (state.logsPage < state.logsTotalPages) await loadLogs(state.logsPage + 1);
});

byId("jumpLogsPage").addEventListener("click", async () => {
  const requested = Number(byId("logsPageInput").value || 1);
  const page = Math.min(Math.max(1, requested), state.logsTotalPages || 1);
  await loadLogs(page);
});

byId("logsPageInput").addEventListener("keydown", async (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    byId("jumpLogsPage").click();
  }
});

byId("logsPageSize").addEventListener("change", async (event) => {
  state.logsPageSize = Number(event.target.value || 20);
  state.logsPage = 1;
  await loadLogs(1);
});

bootstrap().catch((error) => {
  showToast(`初始化失败：${error.message}`, true);
});
