const BASE = "";

async function request(path, opts = {}) {
  let res;
  try {
    res = await fetch(`${BASE}${path}`, opts);
  } catch (err) {
    throw new Error("Cannot reach backend. Is it running?");
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = body.detail || JSON.stringify(body);
    } catch {
      msg = await res.text().catch(() => msg);
    }
    throw new Error(msg);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res.blob();
}

export function getConfig() {
  return request("/api/config");
}

export function createSession(apiKey) {
  return request("/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export async function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/api/upload", { method: "POST", body: form });
}

export function previewExcel(filePath) {
  const form = new FormData();
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
    if (job.status === "error") throw new Error(job.error);
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

export function getKBKeys(sessionId) {
  return request(`/api/kb-keys/${sessionId}`);
}

export function getSessionState(sessionId) {
  return request(`/api/session-state/${sessionId}`);
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
