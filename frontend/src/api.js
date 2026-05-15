const BASE = "";

/** Skip ngrok’s browser interstitial for API fetches (free tier). */
function ngrokHeaders() {
  if (typeof window === "undefined") return {};
  const h = window.location.hostname || "";
  if (/ngrok/i.test(h)) {
    return { "ngrok-skip-browser-warning": "true" };
  }
  return {};
}

/** Merge hooks / skip headers without clobbering FormData POSTs incorrectly. */
function mergeHeaders(existing, extra = {}) {
  const out = new Headers(existing || {});
  for (const [k, v] of Object.entries({ ...ngrokHeaders(), ...extra })) {
    out.set(k, v);
  }
  return out;
}

function looksLikeNgrokHtml(text) {
  if (!text || typeof text !== "string") return false;
  const t = text.slice(0, 500).toLowerCase();
  return t.includes("ngrok") && (t.includes("<!doctype html") || t.includes("<html"));
}

function formatErrorDetail(detail) {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const path = Array.isArray(item.loc) ? item.loc.join(".") : "";
          const msg = item.msg || JSON.stringify(item);
          return path ? `${path}: ${msg}` : msg;
        }
        return String(item);
      })
      .join("; ");
  }
  if (typeof detail === "object") return JSON.stringify(detail);
  return String(detail);
}

/** Guidance when status is non-2xx but body has no usable JSON/text (common with proxies / HTTP/2). */
function emptyErrorBodyHint(requestPath = "") {
  const pathLine = requestPath ? ` (${requestPath})` : "";
  return [
    "The server returned an error with no usable body text, so no extra detail is available here.",
    `• DevTools → Network → select the failed request${pathLine} → Response (and Headers).`,
    "• If you use ngrok or a tunnel: check body size limits, tunnel dashboard errors, same-origin vs split frontend/API URLs, and CORS.",
    "• If logs/backend.log has no line for this request, the failure may be from the tunnel or a reverse proxy, not Uvicorn.",
  ].join("\n");
}

/** Never throw an Error with an empty .message (shows as "Error" in the UI). */
function buildHttpErrorMessage(res, detailText, rawBodySnippet, requestPath = "") {
  const code = res.status || 0;
  const st = (res.statusText || "").trim();
  const line1 = [code || "?", st].filter(Boolean).join(" ");
  const parts = [`HTTP ${line1 || code}`];
  if (detailText && detailText.trim()) parts.push(detailText.trim());
  else if (rawBodySnippet && rawBodySnippet.trim()) {
    const snip = rawBodySnippet.trim().slice(0, 800);
    parts.push(looksLikeNgrokHtml(snip)
      ? "Received an HTML page instead of JSON (often ngrok’s warning or a proxy). Open this URL in a tab once, or ensure ngrok-skip-browser-warning is sent."
      : snip);
  } else {
    parts.push(emptyErrorBodyHint(requestPath));
  }
  return parts.join("\n\n");
}

async function request(path, opts = {}) {
  const { timeoutMs, ...fetchOpts } = opts;
  const controller = new AbortController();
  const timer =
    timeoutMs != null && timeoutMs > 0
      ? setTimeout(() => controller.abort(), timeoutMs)
      : null;

  const init = { ...fetchOpts, signal: controller.signal };
  const method = (init.method || "GET").toUpperCase();
  const isForm = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (isForm) {
    init.headers = mergeHeaders(init.headers, {});
  } else {
    const extra = {};
    if (method !== "GET" && method !== "HEAD" && init.body != null && !init.headers?.["Content-Type"]) {
      extra["Content-Type"] = "application/json";
    }
    init.headers = mergeHeaders(init.headers, extra);
  }

  let res;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch (err) {
    if (timer) clearTimeout(timer);
    if (err?.name === "AbortError") {
      throw new Error("Request timed out. Is the backend running?");
    }
    const net = (err && err.message) ? err.message : "Network error";
    throw new Error(`Cannot reach backend (${net}). If you use ngrok, confirm the API URL / proxy and CORS.`);
  }
  if (timer) clearTimeout(timer);

  const ct = res.headers.get("content-type") || "";

  if (!res.ok) {
    let raw = "";
    let detailText = "";
    try {
      const body = await res.clone().json();
      detailText = formatErrorDetail(body?.detail) || (body && typeof body === "object" ? JSON.stringify(body) : "");
    } catch {
      try {
        raw = await res.text();
      } catch {
        raw = "";
      }
      if (looksLikeNgrokHtml(raw)) {
        detailText =
          "ngrok returned an HTML interstitial or error page instead of JSON. Visit the site once in this browser, or expose the app with the ngrok skip header / paid tier.";
      }
    }
    throw new Error(buildHttpErrorMessage(res, detailText, raw, path));
  }

  if (ct.includes("application/json")) {
    const data = await res.json();
    return data;
  }

  if (path.startsWith("/api/export")) {
    return res.blob();
  }

  const text = await res.text();
  if (looksLikeNgrokHtml(text)) {
    throw new Error(
      "Expected JSON but received HTML (often ngrok’s browser-warning page). Open this tunnel URL once in the browser or use ngrok authentication / paid tier.",
    );
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`Expected JSON but could not parse body (first 300 chars):\n${text.slice(0, 300)}`);
  }
}

export function getConfig() {
  return request("/api/config", { timeoutMs: 15000 });
}

export function createSession(body) {
  return request("/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function estimateCost(body) {
  return request("/api/estimate-cost", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function uploadFile(file, sessionId) {
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("file", file);
  const raw = await request("/api/upload", { method: "POST", body: form });
  if (!raw || typeof raw !== "object" || typeof raw.file_path !== "string") {
    throw new Error(
      "Upload response was not valid JSON (missing file_path). Often caused by ngrok or a proxy returning HTML instead of the API."
    );
  }
  return raw;
}

export function previewExcel(sessionId, filePath) {
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("file_path", filePath);
  return request("/api/preview", { method: "POST", body: form });
}

export function getJobStatus(jobId) {
  return request(`/api/job/${jobId}`);
}

/**
 * Submit a job and poll until it finishes.
 * onProgress is called on each poll so the UI can show status.
 * Returns the job result on success, throws on error.
 */
export async function submitAndPoll(path, body, onProgress, intervalMs = 2000) {
  const { job_id } = await request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  while (true) {
    await new Promise((r) => setTimeout(r, intervalMs));
    const job = await getJobStatus(job_id);
    if (onProgress) onProgress(job);

    if (job.status === "done") return job.result;
    if (job.status === "error") throw new Error(job.error || "Background job failed with no message.");
  }
}

export function setupPDF(body, onProgress) {
  return submitAndPoll("/api/setup/pdf", body, onProgress);
}

export function setupExcel(body, onProgress) {
  return submitAndPoll("/api/setup/excel", body, onProgress);
}

export function processQueries(body, onProgress) {
  return submitAndPoll("/api/process-queries", body, onProgress);
}

export function createQASession(sessionId, useCase, total) {
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("use_case", useCase);
  form.append("total", total);
  return request("/api/qa/session", { method: "POST", body: form });
}

export function saveQAFeedback(body) {
  return request("/api/qa/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function getQAStats(qaSessionId) {
  return request(`/api/qa/stats/${qaSessionId}`);
}

export function getQAAnalysis(qaSessionId) {
  return request(`/api/qa/analysis/${qaSessionId}`);
}

export function applyLearnings(sessionId, qaSessionId) {
  return request("/api/qa/apply-learnings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, qa_session_id: qaSessionId }),
  });
}

export function markQAQueryReviewed(qaSessionId, queryId) {
  return request("/api/qa/mark-reviewed", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ qa_session_id: qaSessionId, query_id: queryId }),
  });
}

export function getKBKeys(sessionId) {
  return request(`/api/kb-keys/${sessionId}`);
}

export function getSessionState(sessionId) {
  return request(`/api/session-state/${sessionId}`, { timeoutMs: 15000 });
}

export function clearResults(sessionId) {
  return request(`/api/clear-results/${sessionId}`, { method: "POST" });
}

export function exportResults(sessionId) {
  const form = new FormData();
  form.append("session_id", sessionId);
  return request("/api/export/results", { method: "POST", body: form });
}

export function exportQA(qaSessionId) {
  const form = new FormData();
  form.append("qa_session_id", qaSessionId);
  return request("/api/export/qa", { method: "POST", body: form });
}

export function exportQAReviewed(sessionId, qaSessionId) {
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("qa_session_id", qaSessionId);
  return request("/api/export/qa-reviewed", { method: "POST", body: form });
}
