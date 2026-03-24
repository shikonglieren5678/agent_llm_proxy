const state = {
  allRecords: [],
  filteredRecords: [],
  currentFile: "",
};

const els = {
  file: document.getElementById("log-file"),
  loadButton: document.getElementById("load-button"),
  search: document.getElementById("search-input"),
  hostFilter: document.getElementById("host-filter"),
  statusFilter: document.getElementById("status-filter"),
  stats: document.getElementById("stats"),
  title: document.getElementById("title"),
  summaryMeta: document.getElementById("summary-meta"),
  resultCount: document.getElementById("result-count"),
  records: document.getElementById("records"),
  template: document.getElementById("record-template"),
};

function safeJson(value) {
  return JSON.stringify(value, null, 2);
}

function normalizeText(record) {
  return [
    record.request?.host,
    record.request?.path,
    record.request?.pretty_url,
    record.request?.body_text,
    record.response?.body_text,
    safeJson(record.request?.headers || {}),
    safeJson(record.response?.headers || {}),
    record.error,
  ]
    .filter(Boolean)
    .join("\n")
    .toLowerCase();
}

function parseBody(recordPart) {
  if (!recordPart) {
    return null;
  }
  if (recordPart.body_text) {
    try {
      return JSON.parse(recordPart.body_text);
    } catch {
      return recordPart.body_text;
    }
  }
  return {
    body_base64: recordPart.body_base64,
    body_size: recordPart.body_size,
    body_truncated: recordPart.body_truncated,
  };
}

function getStatusTone(statusCode) {
  if (statusCode >= 500) return "bad";
  if (statusCode >= 400) return "warn";
  return "ok";
}

function renderStats(records) {
  const total = records.length;
  const errors = records.filter((item) => item.error || (item.response?.status_code || 0) >= 400).length;
  const hosts = new Set(records.map((item) => item.request?.host).filter(Boolean)).size;
  const methods = new Set(records.map((item) => item.request?.method).filter(Boolean)).size;

  els.stats.innerHTML = [
    statCard("总记录", total),
    statCard("异常记录", errors),
    statCard("Host 数量", hosts),
    statCard("Method 数量", methods),
  ].join("");
}

function statCard(label, value) {
  return `<div class="stat"><div class="label">${label}</div><div class="value">${value}</div></div>`;
}

function renderFilters(records) {
  const hosts = [...new Set(records.map((item) => item.request?.host).filter(Boolean))].sort();
  const statuses = [...new Set(records.map((item) => item.response?.status_code).filter(Boolean))].sort((a, b) => a - b);

  els.hostFilter.innerHTML = `<option value="">全部</option>${hosts
    .map((host) => `<option value="${host}">${host}</option>`)
    .join("")}`;
  els.statusFilter.innerHTML = `<option value="">全部</option>${statuses
    .map((status) => `<option value="${status}">${status}</option>`)
    .join("")}`;
}

function applyFilters() {
  const search = els.search.value.trim().toLowerCase();
  const host = els.hostFilter.value;
  const status = els.statusFilter.value;

  state.filteredRecords = state.allRecords.filter((record) => {
    const textMatch = !search || normalizeText(record).includes(search);
    const hostMatch = !host || record.request?.host === host;
    const statusMatch = !status || String(record.response?.status_code || "") === status;
    return textMatch && hostMatch && statusMatch;
  });

  renderList(state.filteredRecords);
}

function renderList(records) {
  els.resultCount.textContent = `${records.length} 条`;
  els.records.innerHTML = "";

  for (const record of records) {
    const node = els.template.content.firstElementChild.cloneNode(true);
    const button = node.querySelector(".record-head");
    const method = node.querySelector(".method");
    const url = node.querySelector(".url");
    const status = node.querySelector(".status");
    const time = node.querySelector(".time");
    const requestView = node.querySelector(".request-view");
    const responseView = node.querySelector(".response-view");

    const statusCode = record.response?.status_code || 0;
    method.textContent = record.request?.method || "UNKNOWN";
    url.textContent = record.request?.pretty_url || record.raw_line || record.id;
    status.textContent = statusCode ? String(statusCode) : (record.error ? "ERROR" : "-");
    status.classList.add(getStatusTone(statusCode));
    time.textContent = record.captured_at || "-";

    requestView.textContent = safeJson({
      request_line: `${record.request?.method || ""} ${record.request?.path || ""}`.trim(),
      headers: record.request?.headers || {},
      query: record.request?.query || [],
      body: parseBody(record.request),
    });

    responseView.textContent = safeJson({
      status_code: record.response?.status_code,
      reason: record.response?.reason,
      headers: record.response?.headers || {},
      body: parseBody(record.response),
      error: record.error || null,
    });

    button.addEventListener("click", () => {
      node.classList.toggle("open");
    });

    els.records.appendChild(node);
  }
}

async function loadLogs() {
  const file = els.file.value.trim() || "logs/records.jsonl";
  const response = await fetch(`/api/logs?file=${encodeURIComponent(file)}`);
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.error || "读取日志失败");
  }

  state.currentFile = payload.file;
  state.allRecords = (payload.records || []).sort((a, b) => {
    return String(b.captured_at || "").localeCompare(String(a.captured_at || ""));
  });

  els.title.textContent = "日志读取完成";
  els.summaryMeta.textContent = payload.file;

  renderStats(state.allRecords);
  renderFilters(state.allRecords);
  applyFilters();
}

function bindEvents() {
  els.loadButton.addEventListener("click", () => {
    loadLogs().catch((error) => {
      els.title.textContent = "读取失败";
      els.summaryMeta.textContent = error.message;
    });
  });

  els.search.addEventListener("input", applyFilters);
  els.hostFilter.addEventListener("change", applyFilters);
  els.statusFilter.addEventListener("change", applyFilters);
}

bindEvents();
loadLogs().catch((error) => {
  els.title.textContent = "等待加载日志";
  els.summaryMeta.textContent = error.message;
});
