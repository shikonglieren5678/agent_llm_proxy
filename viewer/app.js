const state = {
  allRecords: [],
  filteredRecords: [],
  currentFile: "",
};

const els = {
  file: document.getElementById("log-file"),
  loadButton: document.getElementById("load-button"),
  search: document.getElementById("search-input"),
  dateFromFilter: document.getElementById("date-from-filter"),
  dateToFilter: document.getElementById("date-to-filter"),
  hostFilter: document.getElementById("host-filter"),
  statusFilter: document.getElementById("status-filter"),
  stats: document.getElementById("stats"),
  title: document.getElementById("title"),
  summaryMeta: document.getElementById("summary-meta"),
  resultCount: document.getElementById("result-count"),
  records: document.getElementById("records"),
  template: document.getElementById("record-template"),
  modal: document.getElementById("parsed-modal"),
  modalClose: document.getElementById("modal-close"),
  parsedThink: document.getElementById("parsed-think"),
  parsedResult: document.getElementById("parsed-result"),
  copyThink: document.getElementById("copy-think"),
  copyResult: document.getElementById("copy-result"),
};

const modalState = {
  think: "",
  result: "",
};

function safeJson(value) {
  return JSON.stringify(value, null, 2);
}

function toChinaDateParts(value) {
  if (!value) {
    return { date: "", datetime: "-" };
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return { date: "", datetime: value };
  }

  const formatter = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });

  const parts = Object.fromEntries(formatter.formatToParts(date).map((item) => [item.type, item.value]));
  const yyyyMmDd = `${parts.year}-${parts.month}-${parts.day}`;
  const full = `${yyyyMmDd} ${parts.hour}:${parts.minute}:${parts.second}`;
  return { date: yyyyMmDd, datetime: full };
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

function decodeBase64Utf8(base64) {
  if (!base64) {
    return "";
  }
  const binary = window.atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new TextDecoder("utf-8").decode(bytes);
}

function parseJsonChunksFromText(text) {
  const chunks = [];
  const normalized = text.replace(/\r/g, "");
  const sseMatches = normalized.matchAll(/(?:^|\n)data:(.*?)(?=\n(?:id:|event:|data:|\n|$))/gs);
  for (const match of sseMatches) {
    const payload = match[1].trim();
    if (!payload || payload === "[DONE]") {
      continue;
    }
    try {
      chunks.push(JSON.parse(payload));
    } catch {
      // ignore non-json lines
    }
  }

  if (chunks.length > 0) {
    return chunks;
  }

  const lines = normalized
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  for (const line of lines) {
    const payload = line.startsWith("data:") ? line.slice(5).trim() : line;
    if (!payload || payload === "[DONE]") {
      continue;
    }
    try {
      chunks.push(JSON.parse(payload));
    } catch {
      // ignore non-json lines
    }
  }

  return chunks;
}

function collectParsedDeltaContent(value, collector) {
  if (!value) {
    return;
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      collectParsedDeltaContent(item, collector);
    }
    return;
  }

  if (typeof value !== "object") {
    return;
  }

  const delta = value.delta;
  if (delta && typeof delta === "object") {
    if (delta.type === "thinking_delta" && typeof delta.thinking === "string") {
      collector.think.push(delta.thinking);
    }
    if (delta.type === "text_delta" && typeof delta.text === "string") {
      collector.result.push(delta.text);
    }
  }

  for (const nested of Object.values(value)) {
    if (nested && typeof nested === "object") {
      collectParsedDeltaContent(nested, collector);
    }
  }
}

function parseResponseDeltaContent(record) {
  const bodyText = record.response?.body_text;
  const bodyBase64 = record.response?.body_base64;
  const decodedText = bodyText || decodeBase64Utf8(bodyBase64);
  const chunks = parseJsonChunksFromText(decodedText);
  const collector = { think: [], result: [] };

  for (const chunk of chunks) {
    collectParsedDeltaContent(chunk, collector);
  }

  return {
    raw: decodedText,
    think: collector.think.join(""),
    result: collector.result.join(""),
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
  const dateFrom = els.dateFromFilter.value;
  const dateTo = els.dateToFilter.value;
  const host = els.hostFilter.value;
  const status = els.statusFilter.value;

  state.filteredRecords = state.allRecords.filter((record) => {
    const chinaDate = toChinaDateParts(record.captured_at).date;
    const textMatch = !search || normalizeText(record).includes(search);
    const dateFromMatch = !dateFrom || (chinaDate && chinaDate >= dateFrom);
    const dateToMatch = !dateTo || (chinaDate && chinaDate <= dateTo);
    const hostMatch = !host || record.request?.host === host;
    const statusMatch = !status || String(record.response?.status_code || "") === status;
    return textMatch && dateFromMatch && dateToMatch && hostMatch && statusMatch;
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
    const requestCopy = node.querySelector(".request-copy");
    const responseCopy = node.querySelector(".response-copy");
    const parsedResponseCopy = node.querySelector(".parsed-response-copy");

    const statusCode = record.response?.status_code || 0;
    const chinaTime = toChinaDateParts(record.captured_at);
    method.textContent = record.request?.method || "UNKNOWN";
    url.textContent = record.request?.pretty_url || record.raw_line || record.id;
    status.textContent = statusCode ? String(statusCode) : (record.error ? "ERROR" : "-");
    status.classList.add(getStatusTone(statusCode));
    time.textContent = chinaTime.datetime;

    const requestPayload = safeJson({
      request_line: `${record.request?.method || ""} ${record.request?.path || ""}`.trim(),
      headers: record.request?.headers || {},
      query: record.request?.query || [],
      body: parseBody(record.request),
    });
    requestView.textContent = requestPayload;

    const responsePayload = safeJson({
      status_code: record.response?.status_code,
      reason: record.response?.reason,
      headers: record.response?.headers || {},
      body: parseBody(record.response),
      error: record.error || null,
    });
    responseView.textContent = responsePayload;

    button.addEventListener("click", () => {
      node.classList.toggle("open");
    });
    requestCopy.addEventListener("click", (event) => {
      event.stopPropagation();
      copyText(requestPayload, requestCopy, "复制请求");
    });
    responseCopy.addEventListener("click", (event) => {
      event.stopPropagation();
      copyText(responsePayload, responseCopy, "复制响应");
    });
    parsedResponseCopy.addEventListener("click", async (event) => {
      event.stopPropagation();
      const parsed = parseResponseDeltaContent(record);
      openParsedModal(parsed);
      const combined = buildParsedCopyText(parsed);
      await copyText(combined, parsedResponseCopy, "复制解析响应内容");
    });

    els.records.appendChild(node);
  }
}

function buildParsedCopyText(parsed) {
  return [`<think>\n${parsed.think || ""}\n</think>`, `<result>\n${parsed.result || ""}\n</result>`].join("\n\n");
}

function openParsedModal(parsed) {
  modalState.think = parsed.think || "";
  modalState.result = parsed.result || "";
  els.parsedThink.textContent = modalState.think || "(未解析到 thinking 内容)";
  els.parsedResult.textContent = modalState.result || "(未解析到 text 内容)";
  els.modal.classList.remove("hidden");
}

function closeParsedModal() {
  els.modal.classList.add("hidden");
}

async function copyText(text, button, defaultLabel) {
  try {
    await navigator.clipboard.writeText(text);
    const previous = button.textContent;
    button.textContent = "已复制";
    button.classList.add("copied");
    window.setTimeout(() => {
      button.textContent = defaultLabel || previous;
      button.classList.remove("copied");
    }, 1200);
  } catch (error) {
    button.textContent = "复制失败";
    window.setTimeout(() => {
      button.textContent = defaultLabel;
    }, 1200);
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
  els.dateFromFilter.addEventListener("change", applyFilters);
  els.dateToFilter.addEventListener("change", applyFilters);
  els.hostFilter.addEventListener("change", applyFilters);
  els.statusFilter.addEventListener("change", applyFilters);
  els.modalClose.addEventListener("click", closeParsedModal);
  els.modal.addEventListener("click", (event) => {
    if (event.target?.dataset?.closeModal === "true") {
      closeParsedModal();
    }
  });
  els.copyThink.addEventListener("click", () => {
    copyText(modalState.think || "", els.copyThink, "复制 think");
  });
  els.copyResult.addEventListener("click", () => {
    copyText(modalState.result || "", els.copyResult, "复制 result");
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !els.modal.classList.contains("hidden")) {
      closeParsedModal();
    }
  });
}

bindEvents();
loadLogs().catch((error) => {
  els.title.textContent = "等待加载日志";
  els.summaryMeta.textContent = error.message;
});
