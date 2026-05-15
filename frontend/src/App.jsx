import { useState, useEffect, useRef } from "react";
import * as api from "./api";
import "./App.css";

/** Labels for match_count_mode values returned by GET /api/config (match_count_modes). */
const MATCH_MODE_LABELS = {
  fixed: "Fixed (always top N)",
  auto: "Auto-detect (0..N by confidence)",
  tag_driven: "Tag-driven (1 best match per tag)",
};

/** If GET /api/config fails, still render the app so login is usable (matches backend defaults). */
const FALLBACK_CONFIG = {
  qa_sample_size: 50,
  max_top_n: 10,
  default_top_n: 3,
  query_llm_models: [
    "gemini-3-flash-preview",
    "claude-3-5-haiku-20241022",
    "claude-3-5-sonnet-20241022",
    "claude-3-7-sonnet-20250219",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-5.2",
  ],
  default_query_llm: "gpt-4.1-mini",
  match_count_modes: ["fixed", "auto", "tag_driven"],
};

/* ─── tiny helpers ───────────────────────────────────────────────── */

function StatusBadge({ text, type = "info" }) {
  return <span className={`badge badge-${type}`}>{text}</span>;
}

function Spinner({ text }) {
  return (
    <div className="spinner-wrap">
      <div className="spinner" />
      <span>{text}</span>
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <div className="metric-value">{value}</div>
      <div className="metric-label">{label}</div>
    </div>
  );
}

/* ─── File Upload ────────────────────────────────────────────────── */

function FileUpload({ accept, label, onUploaded, disabled, onError, sessionId }) {
  const [uploading, setUploading] = useState(false);
  const [fileName, setFileName] = useState(null);

  async function handleChange(e) {
    const file = e.target.files[0];
    if (!file) return;
    if (!sessionId) {
      if (onError) onError("Not connected", "Start a session before uploading files.");
      return;
    }
    setUploading(true);
    try {
      const res = await api.uploadFile(file, sessionId);
      setFileName(file.name);
      onUploaded(res.file_path, file.name);
    } catch (err) {
      if (onError) onError("Upload failed", err);
      else alert("Upload failed: " + err.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="file-upload">
      <label className="file-upload-label">
        <input type="file" accept={accept} onChange={handleChange} disabled={disabled || uploading || !sessionId} />
        <span className="file-upload-btn">{uploading ? "Uploading…" : label}</span>
      </label>
      {fileName && <span className="file-name">{fileName}</span>}
    </div>
  );
}

/* ─── Data Preview Table ─────────────────────────────────────────── */

function DataPreview({ rows, columns }) {
  if (!rows || rows.length === 0) return null;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>{columns.map((c) => <td key={c}>{row[c] != null ? String(row[c]) : ""}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ─── Match Card ─────────────────────────────────────────────────── */

function MatchCard({ match, useCase, children }) {
  const [showReasoning, setShowReasoning] = useState(false);
  return (
    <div className="match-card">
      <div className="match-header">
        <StatusBadge text={`Rank ${match.rank}`} type="primary" />
        <span className="score">Score: {(match.combined_score || 0).toFixed(3)}</span>
        {match.llm_relevance_score != null && (
          <span className="score">LLM: {match.llm_relevance_score.toFixed(3)}</span>
        )}
      </div>
      {match.tag_value != null && match.tag_value !== "" && (
        <div className="match-meta"><strong>Tag {match.tag_index || "?"}:</strong> {match.tag_value}</div>
      )}
      {useCase === "pdf_kb" ? (
        <>
          <div className="match-meta">Page {match.page_number}</div>
          <p className="match-text">{match.text}</p>
        </>
      ) : (
        <>
          <div className="match-meta">
            <strong>{match.key}</strong> — Row {match.row_number}
          </div>
          <p className="match-text">{match.definition}</p>
        </>
      )}
      {match.llm_reasoning && (
        <button className="link-btn" onClick={() => setShowReasoning(!showReasoning)}>
          {showReasoning ? "Hide" : "Show"} LLM reasoning
        </button>
      )}
      {showReasoning && <p className="reasoning">{match.llm_reasoning}</p>}
      {children}
        </div>
  );
}

/* ─── Results Browser ────────────────────────────────────────────── */

function ResultsBrowser({ results, useCase, onStartQA, onExport, onReset, onReprocessAll, matchingStage, processing, learningsApplied, totalQueries, queryJobProgress }) {
  const [expanded, setExpanded] = useState(null);

  const isFinal = matchingStage === "final_done";
  const isLearningsDone = matchingStage === "remaining_done" && learningsApplied;

  return (
    <section className="panel">
      <h2>Results ({results.length} queries{totalQueries > 0 && results.length < totalQueries ? ` of ${totalQueries}` : ""})</h2>

      {processing && (
        <Spinner
          text={
            formatQueryJobProgress(queryJobProgress)
            || "Processing all queries… This runs in the background even if your screen turns off."
          }
        />
      )}

      {isLearningsDone && !processing && (
        <div className="info-box" style={{ marginBottom: 16 }}>
          <h4>All {results.length} Queries Processed with Learned Settings</h4>
          <p className="muted">
            Review a few results below to check quality. If satisfied, export directly.
            Or click <strong>"Reprocess All"</strong> to re-run with current settings, or <strong>"Re-QA"</strong> to verify a sample first.
          </p>
          <div className="btn-row" style={{ marginTop: 10 }}>
            <button className="btn btn-primary" onClick={onExport}>
              Export All {results.length} Results to Excel
            </button>
            <button className="btn btn-secondary" onClick={onReprocessAll}>
              Reprocess All {results.length} Queries
            </button>
            <button className="btn btn-outline" onClick={onStartQA}>Re-QA a Sample</button>
          </div>
        </div>
      )}

      {isFinal && !processing && (
        <div className="info-box" style={{ marginBottom: 16 }}>
          <StatusBadge text={`All ${results.length} queries processed — ready to export`} type="success" />
        </div>
      )}

      <div className="btn-row">
        <button className="btn btn-primary" onClick={onExport} disabled={processing}>
          Export All {results.length} Results to Excel
        </button>
        {!isFinal && !isLearningsDone && !processing && (
          <button className="btn btn-secondary" onClick={onStartQA}>Start QA Review</button>
        )}
        <button className="btn btn-ghost" onClick={onReset}>Reset</button>
      </div>
      <div className="results-list">
        {results.map((r, i) => (
          <div key={r.query_id} className="result-item">
            <button className="result-toggle" onClick={() => setExpanded(expanded === i ? null : i)}>
              <span className="result-num">Q{i + 1}</span>
              <span className="result-query">
                {r.primary_key != null && r.primary_key !== "" && (
                  <span className="result-pk muted" style={{ marginRight: 8 }}>[{r.primary_key}]</span>
                )}
                {r.query}
              </span>
              <span className="result-count">{r.num_matches} matches</span>
              <span className="chevron">{expanded === i ? "▲" : "▼"}</span>
            </button>
            {expanded === i && (
              <div className="result-detail">
                {r.warning && <div className="info-box" style={{ marginBottom: 10 }}>{r.warning}</div>}
                {r.error && <div className="error-msg">{r.error}</div>}
                {r.matches.map((m) => (
                  <MatchCard key={m.rank} match={m} useCase={useCase} />
                ))}
                {r.matches.length === 0 && !r.error && <p className="muted">No matches found.</p>}
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

/* ─── QA Review Interface ────────────────────────────────────────── */

function QAReview({
  results,
  useCase,
  sessionId,
  qaSessionId,
  kbKeys,
  qaSampleSize,
  totalQueries,
  remainingOffset,
  onBackToResults,
  onSkipLearningsProcessAll,
  onOpenRemainingCostModal,
  onRescoreAfterLearnings,
  onExportQAReviewed,
  onError,
}) {
  const qaResults = results.slice(0, Math.min(qaSampleSize, results.length));
  const [idx, setIdx] = useState(0);
  const [labels, setLabels] = useState({});
  const [suggestedKey, setSuggestedKey] = useState("");
  const [suggestedText, setSuggestedText] = useState("");
  const [analystNote, setAnalystNote] = useState("");
  const [saving, setSaving] = useState(false);

  const [showSummary, setShowSummary] = useState(false);

  if (idx >= qaResults.length || showSummary) {
    return (
      <QASummary
        sessionId={sessionId}
        qaSessionId={qaSessionId}
        totalQueries={totalQueries}
        remainingOffset={remainingOffset}
        onError={onError}
        onBackToQAReview={() => {
          setShowSummary(false);
          setIdx(Math.max(0, qaResults.length - 1));
        }}
        onSkipLearningsProcessAll={onSkipLearningsProcessAll}
        onRescoreAfterLearnings={onRescoreAfterLearnings}
        onOpenRemainingCost={onOpenRemainingCostModal}
        onBackToResults={onBackToResults}
        onExportQAReviewed={onExportQAReviewed}
      />
    );
  }

  const current = qaResults[idx];

  async function handleSaveNext() {
    setSaving(true);
    const statusMap = { Relevant: "accepted", "Not Relevant": "rejected", Unsure: "skipped" };
    try {
      for (const match of current.matches) {
        const label = labels[match.rank] || "Unsure";
        const status = statusMap[label];
        await api.saveQAFeedback({
          session_id: sessionId,
          qa_session_id: qaSessionId,
          query_id: current.query_id,
          query: current.query,
          primary_key: current.primary_key || null,
          match_rank: match.rank,
          match_id: match.chunk_id || match.key || "",
          match_text: match.text || match.definition || "",
          tag_index: match.tag_index ?? null,
          tag_value: match.tag_value ?? null,
          status,
          notes: JSON.stringify({
            review_label: label,
            suggested_key: status === "rejected" ? suggestedKey : "",
            suggested_text: status === "rejected" ? suggestedText : "",
            analyst_note: status === "rejected" ? analystNote : "",
          }),
        });
      }
      try {
        await api.markQAQueryReviewed(qaSessionId, current.query_id);
      } catch (e) {
        if (onError) onError("Could not record QA review", e);
      }
      setLabels({});
      setSuggestedKey("");
      setSuggestedText("");
      setAnalystNote("");
      setIdx(idx + 1);
    } catch (err) {
      if (onError) onError("Error saving feedback", err);
      else alert("Error saving feedback: " + err.message);
    } finally {
      setSaving(false);
    }
  }

  const progress = ((idx + 1) / qaResults.length) * 100;

  return (
    <section className="panel">
      <h2>QA Review — Query {idx + 1} of {qaResults.length}</h2>
      <div className="progress-bar"><div className="progress-fill" style={{ width: `${progress}%` }} /></div>

      <div className="qa-query-box">
        <label>Query</label>
        <p>{current.query}</p>
        {current.primary_key != null && current.primary_key !== "" && (
          <p className="muted" style={{ marginTop: 6 }}><strong>Primary key:</strong> {current.primary_key}</p>
        )}
      </div>

      {current.matches.map((match) => (
        <MatchCard key={match.rank} match={match} useCase={useCase}>
          <select
            className="qa-select"
            value={labels[match.rank] || "Unsure"}
            onChange={(e) => setLabels({ ...labels, [match.rank]: e.target.value })}
          >
            <option>Unsure</option>
            <option>Relevant</option>
            <option>Not Relevant</option>
          </select>
        </MatchCard>
      ))}

      <div className="qa-corrections">
        <h4>Suggest a better match (optional)</h4>
        {useCase === "excel_kb" && kbKeys.length > 0 && (
          <select className="input" value={suggestedKey} onChange={(e) => setSuggestedKey(e.target.value)}>
            <option value="">-- Select KB key --</option>
            {kbKeys.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        )}
        <textarea className="input" placeholder="Better match text…" rows={2} value={suggestedText} onChange={(e) => setSuggestedText(e.target.value)} />
        <input className="input" placeholder="Analyst note…" value={analystNote} onChange={(e) => setAnalystNote(e.target.value)} />
      </div>

      <div className="btn-row">
        <button className="btn btn-ghost" disabled={idx === 0} onClick={() => setIdx(idx - 1)}>← Previous</button>
        <button className="btn btn-ghost" onClick={() => { setIdx(idx + 1); }}>Skip →</button>
        <button className="btn btn-primary" onClick={handleSaveNext} disabled={saving}>
          {saving ? "Saving…" : "Save & Next →"}
        </button>
        <button className="btn btn-outline" onClick={() => setShowSummary(true)}>Finish QA Early →</button>
      </div>
      <div className="btn-row" style={{ marginTop: 8 }}>
        <button type="button" className="btn btn-secondary" onClick={onExportQAReviewed}>
          Export QA-reviewed subset
        </button>
        <button className="btn btn-ghost" onClick={onBackToResults}>← Back to Results</button>
      </div>
      </section>
  );
}

/* ─── QA Summary ─────────────────────────────────────────────────── */

function QASummary({
  sessionId,
  qaSessionId,
  totalQueries,
  remainingOffset,
  onError,
  onBackToQAReview,
  onSkipLearningsProcessAll,
  onRescoreAfterLearnings,
  onOpenRemainingCost,
  onBackToResults,
  onExportQAReviewed,
}) {
  const [analysis, setAnalysis] = useState(null);
  const [applying, setApplying] = useState(false);
  const [applyResult, setApplyResult] = useState(null);

  const hasRemaining = totalQueries <= 0 || remainingOffset < totalQueries;

  useEffect(() => {
    api.getQAAnalysis(qaSessionId).then(setAnalysis).catch(() => { /* ignored — spinner stays */ });
  }, [qaSessionId]);

  async function handleApply() {
    setApplying(true);
    try {
      const res = await api.applyLearnings(sessionId, qaSessionId);
      setApplyResult(res.changes);
    } catch (err) {
      if (onError) onError("Error applying learnings", err);
      else alert("Error: " + err.message);
    } finally {
      setApplying(false);
    }
  }

  if (!analysis) return <Spinner text="Loading QA analysis…" />;

  return (
    <section className="panel">
      <h2>QA Review Complete</h2>
      <div className="metrics-row">
        <Metric label="Total Reviews" value={analysis.total_reviews} />
        <Metric label="Accepted" value={analysis.accepted} />
        <Metric label="Rejected" value={analysis.rejected} />
        <Metric label="Acceptance Rate" value={`${(analysis.acceptance_rate * 100).toFixed(0)}%`} />
        <Metric label="Confidence" value={`${(analysis.confidence * 100).toFixed(0)}%`} />
      </div>

      <div className="btn-row" style={{ marginTop: 12 }}>
        <button type="button" className="btn btn-secondary" onClick={onExportQAReviewed}>
          Export QA-reviewed subset
        </button>
      </div>
      <p className="muted" style={{ marginTop: 6 }}>
        Rows saved with Save &amp; Next (and marked reviewed) are merged into Excel with model columns, QA status, and suggestions.
      </p>

      {analysis.suggested_weights && (
        <div className="suggestion-box">
          <h4>Suggested Weight Adjustment</h4>
          <p>Semantic: {(analysis.suggested_weights.semantic_weight * 100).toFixed(0)}% — Keyword: {(analysis.suggested_weights.keyword_weight * 100).toFixed(0)}%</p>
          <p className="muted">{analysis.suggested_weights.reasoning}</p>
        </div>
      )}

      {!applyResult ? (
        <div className="btn-row">
          <button className="btn btn-primary" onClick={handleApply} disabled={applying || analysis.total_reviews < 3}>
            {applying ? "Applying…" : "Apply Learnings"}
          </button>
          <button className="btn btn-secondary" onClick={onSkipLearningsProcessAll}>
            Skip Learnings &amp; Process All
          </button>
          <button className="btn btn-outline" onClick={onBackToQAReview}>← Go Back to QA Review</button>
        </div>
      ) : (
        <div>
          {applyResult.weights_adjusted && <StatusBadge text="Weights adjusted" type="success" />}
          {applyResult.few_shot_enabled && <StatusBadge text={`Few-shot enabled (${applyResult.num_examples} examples)`} type="success" />}
          <p className="muted" style={{ marginTop: 12 }}>
            Choose how to continue: re-run the QA sample with updated settings, process the rest of the file (cost estimate), or return to the results list.
          </p>
          <div className="btn-row" style={{ marginTop: 12 }}>
            <button type="button" className="btn btn-primary" onClick={onRescoreAfterLearnings}>
              Re-score sample &amp; QA again
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onOpenRemainingCost}
              disabled={!hasRemaining}
            >
              Process remaining (estimate cost)
            </button>
            <button type="button" className="btn btn-outline" onClick={onBackToResults}>
              Back to results
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

/* ─── sessionStorage helpers ─────────────────────────────────────── */

const STORAGE_KEY = "smrag_session";

function saveSession(data) {
  try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data)); } catch { /* storage unavailable */ }
}
function loadSession() {
  try { return JSON.parse(sessionStorage.getItem(STORAGE_KEY)); } catch { return null; }
}
function clearSession() {
  try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* storage unavailable */ }
}

const TAG_SEPARATOR_OPTIONS = [
  { label: "Comma (,)", value: "," },
  { label: "Semicolon (;)", value: ";" },
  { label: "Pipe (|)", value: "|" },
  { label: "Slash (/)", value: "/" },
  { label: "Backslash (\\)", value: "\\" },
  { label: "Asterisk (*)", value: "*" },
  { label: "Hash (#)", value: "#" },
];

function splitTagPreview(rawValue, sep) {
  if (rawValue == null) return [];
  const text = String(rawValue).trim();
  if (!text) return [];
  return text.split(sep).map((t) => t.trim()).filter(Boolean);
}

/** Backend job progress: { stage, done, total } */
function formatQueryJobProgress(p) {
  if (!p || p.total == null || p.total <= 0) return null;
  const { stage, done, total } = p;
  if (stage === "retrieval") return `Retrieving queries: ${done} / ${total}`;
  if (stage === "rerank") return `Ranking matches: ${done} / ${total}`;
  if (stage === "done") return `Complete: ${done} / ${total}`;
  return `Processing: ${done} / ${total}`;
}

/* ─── Full-process cost confirmation (all queries vs remaining slice) ─── */

function ProcessAllCostModal({ estimate, title, proceedPrompt, onClose, onProceed }) {
  const n = estimate?.num_queries ?? 0;
  const total = estimate?.total_usd ?? 0;
  const avg = estimate?.avg_usd_per_query ?? 0;
  const model = estimate?.llm_model ?? "—";
  const lo = estimate?.total_usd_range?.[0];
  const hi = estimate?.total_usd_range?.[1];
  const modalTitle = title || "Process queries";
  const prompt = proceedPrompt || "Do you want to proceed and run matching for these queries?";
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal-panel cost-confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cost-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="cost-modal-title" className="cost-modal-title">{modalTitle}</h3>
        <div className="cost-modal-section">
          <div className="cost-modal-section-head">## QUERIES ##</div>
          <pre className="cost-modal-pre">
            {`Queries in this run: ${n}`}
          </pre>
        </div>
        <div className="cost-modal-section">
          <div className="cost-modal-section-head">## COSTS (approx.) ##</div>
          <pre className="cost-modal-pre">
            {`LLM model: ${model}
Avg. est. cost per query: $${avg.toFixed(6)}
Estimated total: $${total.toFixed(4)}${lo != null && hi != null ? `\nTypical range: $${lo.toFixed(4)} – $${hi.toFixed(4)}` : ""}`}
          </pre>
          <p className="muted cost-modal-disclaimer">{estimate?.disclaimer}</p>
        </div>
        <p className="cost-modal-prompt">{prompt}</p>
        <div className="cost-modal-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-primary" onClick={onProceed}>OK</button>
        </div>
      </div>
    </div>
  );
}

function ErrorModal({ title, message, onClose, onCopy }) {
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal-panel cost-confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="error-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="error-modal-title" className="cost-modal-title">{title || "Error"}</h3>
        <div className="cost-modal-section">
          <div className="cost-modal-section-head">## DETAILS ##</div>
          <pre className="cost-modal-pre">{message || "Unknown error"}</pre>
        </div>
        <div className="cost-modal-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>Close</button>
          <button type="button" className="btn btn-primary" onClick={onCopy}>Copy full error</button>
        </div>
      </div>
    </div>
  );
}

/* ─── Main App ───────────────────────────────────────────────────── */

export default function App() {
  // config
  const [cfg, setCfg] = useState(null);

  // sidebar
  const [apiKey, setApiKey] = useState("");
  const [anthropicKey, setAnthropicKey] = useState("");
  const [googleKey, setGoogleKey] = useState("");
  const [useCase, setUseCase] = useState("excel");
  const [topN, setTopN] = useState(3);
  const [matchCountMode, setMatchCountMode] = useState("fixed");
  const [useLLM, setUseLLM] = useState(true);
  const [useExpansion, setUseExpansion] = useState(true);
  const [guidance, setGuidance] = useState("");

  // session
  const [sessionId, setSessionId] = useState(null);
  const [connecting, setConnecting] = useState(false);

  // KB step
  const [kbFilePath, setKbFilePath] = useState(null);
  const [kbPreview, setKbPreview] = useState(null);
  const [kbColumns, setKbColumns] = useState([]);
  const [keyCol, setKeyCol] = useState("");
  const [valCol, setValCol] = useState("");
  const [addlCols, setAddlCols] = useState([]);
  const [kbContext, setKbContext] = useState("");
  const [kbProcessed, setKbProcessed] = useState(false);
  const [kbStats, setKbStats] = useState(null);
  const [kbLoading, setKbLoading] = useState(false);

  // PDF-specific
  const [useIntelligent, setUseIntelligent] = useState(true);
  const [pdfContext, setPdfContext] = useState("");

  // query step
  const [queryFilePath, setQueryFilePath] = useState(null);
  const [queryPreview, setQueryPreview] = useState(null);
  const [queryColumns, setQueryColumns] = useState([]);
  const [queryCol, setQueryCol] = useState("");
  const [queryPkCol, setQueryPkCol] = useState("");
  const [queryTagCol, setQueryTagCol] = useState("");
  const [queryTagSep, setQueryTagSep] = useState(",");
  const [queryLlmModel, setQueryLlmModel] = useState("");

  const fullProcessOptsRef = useRef(null);
  const [fullProcessEstimate, setFullProcessEstimate] = useState(null);
  const [fullProcessModalMeta, setFullProcessModalMeta] = useState(null);
  const [errorModal, setErrorModal] = useState(null);

  // processing
  const [processing, setProcessing] = useState(false);
  const [queryJobProgress, setQueryJobProgress] = useState(null);
  const [results, setResults] = useState(null);
  const [totalQueries, setTotalQueries] = useState(0);
  const [remainingOffset, setRemainingOffset] = useState(0);
  const [matchingStage, setMatchingStage] = useState("idle");
  const [restoring, setRestoring] = useState(true);

  // QA
  const [qaMode, setQaMode] = useState(false);
  const [qaSessionId, setQaSessionId] = useState(null);
  const [kbKeys, setKbKeys] = useState([]);
  const [learningsApplied, setLearningsApplied] = useState(false);

  // ── Persist state to sessionStorage on every meaningful change ──
  useEffect(() => {
    if (!sessionId) return;
    saveSession({
      sessionId,
      apiKey,
      anthropicKey,
      googleKey,
      useCase,
      topN,
      matchCountMode,
      useLLM,
      useExpansion,
      guidance,
      kbFilePath,
      kbProcessed,
      kbStats,
      queryFilePath,
      queryCol,
      queryPkCol,
      queryTagCol,
      queryTagSep,
      queryLlmModel,
      matchingStage,
      totalQueries,
      remainingOffset,
      qaSessionId,
      learningsApplied,
    });
  }, [sessionId, apiKey, anthropicKey, googleKey, useCase, topN, matchCountMode, useLLM, useExpansion, guidance,
      kbFilePath, kbProcessed, kbStats, queryFilePath, queryCol, queryPkCol, queryTagCol, queryTagSep, queryLlmModel,
      matchingStage, totalQueries, remainingOffset, qaSessionId, learningsApplied]);

  // ── On mount: try restoring session from backend ──
  useEffect(() => {
    async function restore() {
      const saved = loadSession();
      if (!saved?.sessionId) {
        setRestoring(false);
        return;
      }
      try {
        const state = await api.getSessionState(saved.sessionId);
        if (!state.alive) throw new Error("dead");

        setApiKey(saved.apiKey || "");
        setAnthropicKey(saved.anthropicKey || "");
        setGoogleKey(saved.googleKey || "");
        setUseCase(saved.useCase || "excel");
        setTopN(saved.topN ?? 3);
        setMatchCountMode(saved.matchCountMode || "fixed");
        setUseLLM(saved.useLLM ?? true);
        setUseExpansion(saved.useExpansion ?? true);
        setGuidance(saved.guidance || "");
        setSessionId(saved.sessionId);
        setKbFilePath(saved.kbFilePath || null);
        setKbProcessed(state.kb_ready);
        setKbStats(saved.kbStats || null);
        setQueryFilePath(saved.queryFilePath || null);
        setQueryCol(saved.queryCol || "");
        setQueryPkCol(saved.queryPkCol || "");
        setQueryTagCol(saved.queryTagCol || "");
        setQueryTagSep(saved.queryTagSep || ",");
        setQueryLlmModel(saved.queryLlmModel || "");
        setMatchingStage(saved.matchingStage || "idle");
        setTotalQueries(saved.totalQueries || 0);
        setRemainingOffset(saved.remainingOffset || 0);
        setQaSessionId(state.qa_session_id || saved.qaSessionId || null);
        setLearningsApplied(saved.learningsApplied || false);

        if (state.results?.length > 0) {
          setResults(state.results);
        }
        if (state.kb_ready && saved.useCase !== "pdf") {
          api.getKBKeys(saved.sessionId).then((r) => setKbKeys(r.keys)).catch(() => {});
        }
      } catch { /* session expired or backend restarted */
        clearSession();
      } finally {
        setRestoring(false);
      }
    }
    restore();
  }, []);

  // load config (fallback keeps UI usable if backend is down)
  useEffect(() => {
    api.getConfig().then(setCfg).catch((err) => {
      setErrorModal({
        title: "Cannot reach backend",
        message: typeof err?.message === "string" ? err.message : "Is it running? Run ./start.sh from the project root.",
      });
      setCfg(FALLBACK_CONFIG);
    });
  }, []);

  useEffect(() => {
    if (!cfg?.default_query_llm) return;
    setQueryLlmModel((prev) => {
      if (prev && cfg.query_llm_models?.includes(prev)) return prev;
      return cfg.default_query_llm;
    });
  }, [cfg]);

  const supportedMatchModes =
    cfg?.match_count_modes?.length > 0 ? cfg.match_count_modes : ["fixed", "auto"];
  /** Synced to state but clamped to what this API build supports (avoids 422 before useEffect runs). */
  const effectiveMatchCountMode = supportedMatchModes.includes(matchCountMode)
    ? matchCountMode
    : (supportedMatchModes[0] || "fixed");

  useEffect(() => {
    if (!cfg || restoring) return;
    const modes =
      cfg.match_count_modes?.length > 0 ? cfg.match_count_modes : ["fixed", "auto"];
    setMatchCountMode((prev) => (modes.includes(prev) ? prev : modes[0] || "fixed"));
  }, [cfg, restoring]);

  // connect
  async function handleConnect() {
    if (!apiKey.trim()) return;
    setConnecting(true);
    try {
      const res = await api.createSession({
        api_key: apiKey.trim(),
        anthropic_api_key: anthropicKey.trim() || null,
        google_api_key: googleKey.trim() || null,
      });
      setSessionId(res.session_id);
    } catch (err) {
      showError("Connection failed", err);
    } finally {
      setConnecting(false);
    }
  }

  // KB file uploaded → preview
  async function handleKBUploaded(path) {
    setKbFilePath(path);
    if (useCase === "excel") {
      const prev = await api.previewExcel(sessionId, path);
      setKbPreview(prev);
      setKbColumns(prev.columns);
      if (prev.columns.length > 0) setKeyCol(prev.columns[0]);
      if (prev.columns.length > 1) setValCol(prev.columns[1]);
    }
  }

  // Process KB (runs as background job — survives browser disconnect)
  async function handleProcessKB() {
    if (useCase === "excel" && (!keyCol || !valCol)) {
      showError("Missing columns", "Please select both a Key Column and a Definition Column.");
      return;
    }
    setKbLoading(true);
    try {
      let res;
      if (useCase === "pdf") {
        res = await api.setupPDF({
          session_id: sessionId,
          file_path: kbFilePath,
          use_intelligent_chunking: useIntelligent,
          user_context: pdfContext || null,
        });
      } else {
        res = await api.setupExcel({
          session_id: sessionId,
          file_path: kbFilePath,
          key_column: keyCol,
          value_column: valCol,
          additional_columns: addlCols.length > 0 ? addlCols : null,
          kb_context_prompt: kbContext || null,
        });
      }
      setKbStats(res.stats);
      setKbProcessed(true);
      if (useCase === "excel") {
        api.getKBKeys(sessionId).then((r) => setKbKeys(r.keys)).catch(() => {});
      }
    } catch (err) {
      showError("KB processing failed", err);
    } finally {
      setKbLoading(false);
    }
  }

  // Query file uploaded → preview
  async function handleQueryUploaded(path) {
    setQueryFilePath(path);
    setQueryPkCol("");
    setQueryTagCol("");
    setQueryTagSep(",");
    const prev = await api.previewExcel(sessionId, path);
    setQueryPreview(prev);
    setQueryColumns(prev.columns);
    if (prev.columns.length > 0) setQueryCol(prev.columns[0]);
  }

  const buildFullProcessEstimateBody = (query_offset = 0, query_limit = null) => ({
    session_id: sessionId,
    file_path: queryFilePath,
    query_column: queryCol,
    primary_key_column: queryPkCol.trim() ? queryPkCol.trim() : null,
    query_offset,
    query_limit,
    top_n: topN,
    use_llm_reranking: useLLM,
    use_query_expansion: useExpansion,
    matching_guidance: guidance || null,
    llm_model: queryLlmModel || cfg?.default_query_llm || "gpt-4.1-mini",
  });

  function closeFullProcessModal() {
    fullProcessOptsRef.current = null;
    setFullProcessEstimate(null);
    setFullProcessModalMeta(null);
  }

  function showError(title, errOrMessage) {
    const message = typeof errOrMessage === "string"
      ? errOrMessage
      : (errOrMessage?.message || String(errOrMessage));
    setErrorModal({ title, message });
  }

  function closeErrorModal() {
    setErrorModal(null);
  }

  async function copyErrorModalText() {
    if (!errorModal?.message) return;
    try {
      await navigator.clipboard.writeText(errorModal.message);
    } catch {
      // Clipboard may be unavailable in some environments; keep modal open.
    }
  }

  // Process queries (runs as background job — survives browser disconnect)
  async function handleProcessQueries(offset = 0, limit = null, append = false) {
    setProcessing(true);
    setQueryJobProgress(null);
    try {
      const res = await api.processQueries(
        {
          session_id: sessionId,
          file_path: queryFilePath,
          query_column: queryCol,
          primary_key_column: queryPkCol.trim() ? queryPkCol.trim() : null,
          top_n: topN,
          match_count_mode: effectiveMatchCountMode,
          min_llm_score: 0.70,
          min_combined_score: 0.0,
          relative_ratio: 0.75,
          gap_stop_delta: 0.12,
          tag_column: effectiveMatchCountMode === "tag_driven" ? (queryTagCol.trim() || null) : null,
          tag_separator: effectiveMatchCountMode === "tag_driven" ? queryTagSep : null,
          use_llm_reranking: useLLM,
          use_query_expansion: useExpansion,
          query_offset: offset,
          query_limit: limit,
          matching_guidance: guidance || null,
          llm_model: queryLlmModel || cfg?.default_query_llm || "gpt-4.1-mini",
        },
        (job) => {
          if (job.progress) setQueryJobProgress(job.progress);
        },
      );
      if (append) {
        setResults((prev) => [...(prev || []), ...res.results]);
      } else {
        setResults(res.results);
      }
      return res;
    } catch (err) {
      showError("Processing failed", err);
    } finally {
      setQueryJobProgress(null);
      setProcessing(false);
    }
  }

  async function handleProceedFullProcess() {
    const opt = fullProcessOptsRef.current;
    setFullProcessEstimate(null);
    setFullProcessModalMeta(null);
    fullProcessOptsRef.current = null;
    if (!opt) return;
    try {
      if (opt.processKind === "full_all") {
        await api.clearResults(sessionId);
        setResults(null);
        const res = await handleProcessQueries(0, null, false);
        if (res) {
          setTotalQueries(res.count);
          setRemainingOffset(res.count);
          setMatchingStage("final_done");
          setLearningsApplied(false);
        }
      } else if (opt.processKind === "remaining") {
        const res = await handleProcessQueries(remainingOffset, null, true);
        if (res) {
          setMatchingStage("remaining_done");
          setLearningsApplied(true);
          setRemainingOffset(remainingOffset + res.count);
        }
      }
      setQaMode(false);
    } catch (err) {
      showError("Processing failed", err);
    }
  }

  // Start first N + QA
  async function handleStartQA() {
    const prev = await api.previewExcel(sessionId, queryFilePath);
    setTotalQueries(prev.total_rows);

    const sampleSize = cfg?.qa_sample_size || 50;
    await api.clearResults(sessionId);
    const res = await handleProcessQueries(0, sampleSize, false);
    if (!res) return;

    setRemainingOffset(res.results.length);
    setMatchingStage("sample_done");

    const qa = await api.createQASession(sessionId, useCase === "pdf" ? "pdf_kb" : "excel_kb", res.results.length);
    setQaSessionId(qa.qa_session_id);
    setQaMode(true);
  }

  async function openFullFileCostModal(meta) {
    try {
      const est = await api.estimateCost(buildFullProcessEstimateBody(0, null));
      fullProcessOptsRef.current = { processKind: "full_all" };
      setFullProcessModalMeta(meta || {
        title: "Process all queries",
        prompt: "Proceed with matching for every row in the query file?",
      });
      setFullProcessEstimate(est);
    } catch (err) {
      showError("Could not estimate cost", err);
    }
  }

  async function handleReprocessAll() {
    await openFullFileCostModal({
      title: "Reprocess all queries",
      prompt: "This replaces current results and re-runs matching for every row. Proceed?",
    });
  }

  async function handleOpenRemainingCostModal() {
    if (totalQueries > 0 && remainingOffset >= totalQueries) {
      showError("Nothing left to process", "All query rows have already been matched.");
      return;
    }
    try {
      const est = await api.estimateCost(buildFullProcessEstimateBody(remainingOffset, null));
      fullProcessOptsRef.current = { processKind: "remaining" };
      const nRemain = totalQueries > 0 ? totalQueries - remainingOffset : est.num_queries;
      setFullProcessModalMeta({
        title: "Process remaining queries",
        prompt: `Run matching for the next ${nRemain} row(s) (everything after your QA sample) and append to current results?`,
      });
      setFullProcessEstimate(est);
    } catch (err) {
      showError("Could not estimate cost", err);
    }
  }

  async function handleRescoreAfterLearnings() {
    const sampleSize = cfg?.qa_sample_size || 50;
    setQaMode(false);
    try {
      await api.clearResults(sessionId);
      const res = await handleProcessQueries(0, sampleSize, false);
      if (!res) return;
      setRemainingOffset(res.results.length);
      setMatchingStage("sample_done");
      const qa = await api.createQASession(sessionId, useCase === "pdf" ? "pdf_kb" : "excel_kb", res.results.length);
      setQaSessionId(qa.qa_session_id);
      setQaMode(true);
    } catch (err) {
      showError("Could not re-run QA sample", err);
    }
  }

  async function handleExportQAReviewed() {
    try {
      const blob = await api.exportQAReviewed(sessionId, qaSessionId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `qa_reviewed_${qaSessionId?.slice(0, 8) || "export"}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      showError("QA export failed", err);
    }
  }

  // Export
  async function handleExport() {
    try {
      const blob = await api.exportResults(sessionId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `matching_results_${Date.now()}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      showError("Export failed", err);
    }
  }

  // Reset
  function handleReset() {
    clearSession();
    setKbFilePath(null); setKbPreview(null); setKbProcessed(false); setKbStats(null);
    setQueryFilePath(null); setQueryPreview(null); setQueryPkCol(""); setQueryTagCol(""); setQueryTagSep(","); setResults(null);
    setMatchingStage("idle"); setQaMode(false); setQaSessionId(null);
    setSessionId(null); setRemainingOffset(0); setTotalQueries(0);
    setMatchCountMode("fixed");
    setLearningsApplied(false);
    setQueryJobProgress(null);
    setAnthropicKey("");
    setGoogleKey("");
    setQueryLlmModel(cfg?.default_query_llm || "");
    closeFullProcessModal();
  }

  // Toggle additional columns
  function toggleAddlCol(col) {
    setAddlCols((prev) => prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col]);
  }

  if (!cfg || restoring) {
    const loadingText = !cfg ? "Connecting to backend…" : "Restoring session…";
    return <div className="app-loading"><Spinner text={loadingText} /></div>;
  }

  /* ─── Not connected yet ──────────────────────────────────── */
  if (!sessionId) {
    return (
      <div className="login-page">
        <div className="login-card">
          <h1>SMRAG</h1>
          <p className="subtitle">AI-Powered Text Matching Tool</p>
          <input
            type="password"
            className="input"
            placeholder="OpenAI API key (required — embeddings + GPT models)"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleConnect()}
          />
          <input
            type="password"
            className="input"
            style={{ marginTop: 10 }}
            placeholder="Anthropic API key (optional — for Claude)"
            value={anthropicKey}
            onChange={(e) => setAnthropicKey(e.target.value)}
          />
          <input
            type="password"
            className="input"
            style={{ marginTop: 10 }}
            placeholder="Google AI API key (optional — for Gemini)"
            value={googleKey}
            onChange={(e) => setGoogleKey(e.target.value)}
          />
          <div className="use-case-toggle">
            <button className={`toggle-btn ${useCase === "excel" ? "active" : ""}`} onClick={() => setUseCase("excel")}>
              Excel KB → Excel Queries
            </button>
            <button className={`toggle-btn ${useCase === "pdf" ? "active" : ""}`} onClick={() => setUseCase("pdf")}>
              PDF KB → Excel Queries
            </button>
          </div>
          <button className="btn btn-primary full-w" onClick={handleConnect} disabled={connecting || !apiKey.trim()}>
            {connecting ? "Connecting…" : "Start Session"}
          </button>
        </div>
      </div>
    );
  }

  /* ─── Main layout ────────────────────────────────────────── */
  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h2>SMRAG</h2>
          <span className="sidebar-sub">Text Matching Tool</span>
        </div>

        <div className="sidebar-section">
          <label>Use Case</label>
          <div className="use-case-toggle compact">
            <button className={`toggle-btn ${useCase === "excel" ? "active" : ""}`} onClick={() => { setUseCase("excel"); handleReset(); }}>Excel KB</button>
            <button className={`toggle-btn ${useCase === "pdf" ? "active" : ""}`} onClick={() => { setUseCase("pdf"); handleReset(); }}>PDF KB</button>
          </div>
        </div>

        <div className="sidebar-section">
          <label>{effectiveMatchCountMode === "auto" ? "Max matches per query" : "Matches per query"}</label>
          <input type="range" min={1} max={cfg.max_top_n} value={topN} onChange={(e) => setTopN(+e.target.value)} />
          <span className="range-value">{topN}</span>
        </div>

        <div className="sidebar-section">
          <label>Match count mode</label>
          <select className="input" value={effectiveMatchCountMode} onChange={(e) => setMatchCountMode(e.target.value)}>
            {supportedMatchModes.map((mode) => (
              <option key={mode} value={mode}>
                {MATCH_MODE_LABELS[mode] || mode}
              </option>
            ))}
          </select>
          <span className="sidebar-hint">
            Thresholds are applied only in auto mode. Tag-driven returns one best match for each tag.
            {!supportedMatchModes.includes("tag_driven") && (
              <> Tag-driven is unavailable until the API you are using is updated (it must list <code>tag_driven</code> in <code>/api/config</code>).</>
            )}
          </span>
        </div>

        <div className="sidebar-section">
          <label className="checkbox-label">
            <input type="checkbox" checked={useLLM} onChange={(e) => setUseLLM(e.target.checked)} />
            LLM Re-ranking
          </label>
        </div>

        <div className="sidebar-section">
          <label className="checkbox-label">
            <input type="checkbox" checked={useExpansion} onChange={(e) => setUseExpansion(e.target.checked)} />
            Query Expansion
          </label>
          <span className="sidebar-hint">Generates synonym reformulations for all queries to improve keyword recall</span>
        </div>

        <div className="sidebar-section">
          <label>Matching Guidance</label>
          <textarea className="input" rows={3} placeholder="e.g., Prefer exact ATA chapter alignment…" value={guidance} onChange={(e) => setGuidance(e.target.value)} />
        </div>

        <div className="sidebar-section">
          <label>LLM for queries (expansion + rerank)</label>
          <select className="input" value={queryLlmModel} onChange={(e) => setQueryLlmModel(e.target.value)}>
            {(cfg.query_llm_models || []).map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <span className="sidebar-hint">Add Anthropic / Google keys on login if you pick Claude or Gemini.</span>
        </div>

        <div className="sidebar-footer">
          <button className="btn btn-ghost full-w" onClick={handleReset}>Reset Session</button>
        </div>
      </aside>

      {/* Main content */}
      <main className="main-content">
        {/* ── QA Mode ────────────────────────── */}
        {qaMode && results ? (
          <QAReview
            results={results}
            useCase={useCase === "pdf" ? "pdf_kb" : "excel_kb"}
            sessionId={sessionId}
            qaSessionId={qaSessionId}
            kbKeys={kbKeys}
            qaSampleSize={cfg.qa_sample_size}
            totalQueries={totalQueries}
            remainingOffset={remainingOffset}
            onBackToResults={() => setQaMode(false)}
            onSkipLearningsProcessAll={() => openFullFileCostModal({
              title: "Process all queries",
              prompt: "Skip learnings and run matching for every row in the query file?",
            })}
            onOpenRemainingCostModal={handleOpenRemainingCostModal}
            onRescoreAfterLearnings={handleRescoreAfterLearnings}
            onExportQAReviewed={handleExportQAReviewed}
            onError={showError}
          />
        ) : results ? (
          /* ── Results ────────────────────────── */
          <ResultsBrowser
            results={results}
            useCase={useCase === "pdf" ? "pdf_kb" : "excel_kb"}
            onStartQA={() => setQaMode(true)}
            onExport={handleExport}
            onReset={handleReset}
            onReprocessAll={handleReprocessAll}
            matchingStage={matchingStage}
            processing={processing}
            learningsApplied={learningsApplied}
            totalQueries={totalQueries}
            queryJobProgress={queryJobProgress}
          />
        ) : (
          /* ── Setup + Query steps ────────────── */
          <>
            {/* Step 1: KB Upload */}
            <section className="panel">
              <h2>Step 1 — Upload Knowledge Base {useCase === "pdf" ? "(PDF)" : "(Excel)"}</h2>

              <FileUpload
                accept={useCase === "pdf" ? ".pdf" : ".xlsx,.xls,.csv"}
                label={useCase === "pdf" ? "Choose PDF file" : "Choose Excel / CSV file"}
                sessionId={sessionId}
                onUploaded={handleKBUploaded}
                onError={showError}
                disabled={kbProcessed}
              />

              {/* PDF options */}
              {useCase === "pdf" && kbFilePath && !kbProcessed && (
                <div className="options-block">
                  <label className="checkbox-label">
                    <input type="checkbox" checked={useIntelligent} onChange={(e) => setUseIntelligent(e.target.checked)} />
                    Intelligent Chunking (Recommended)
                  </label>
                  {useIntelligent && (
                    <textarea className="input" rows={2} placeholder="Describe the document domain (optional)…" value={pdfContext} onChange={(e) => setPdfContext(e.target.value)} />
                  )}
                </div>
              )}

              {/* Excel KB options */}
              {useCase === "excel" && kbPreview && !kbProcessed && (
                <>
                  <DataPreview rows={kbPreview.rows} columns={kbPreview.columns} />
                  <div className="column-selectors">
                    <div>
                      <label>Key Column</label>
                      <select className="input" value={keyCol} onChange={(e) => setKeyCol(e.target.value)}>
                        {kbColumns.map((c) => <option key={c}>{c}</option>)}
                      </select>
                    </div>
                    <div>
                      <label>Definition Column</label>
                      <select className="input" value={valCol} onChange={(e) => setValCol(e.target.value)}>
                        {kbColumns.map((c) => <option key={c}>{c}</option>)}
                      </select>
                    </div>
                  </div>
                  <div className="options-block">
                    <label>Additional Columns</label>
                    <div className="chip-group">
                      {kbColumns.filter((c) => c !== keyCol && c !== valCol).map((c) => (
                        <button key={c} className={`chip ${addlCols.includes(c) ? "active" : ""}`} onClick={() => toggleAddlCol(c)}>{c}</button>
                      ))}
                    </div>
                    <textarea className="input" rows={2} placeholder="KB context prompt (optional)…" value={kbContext} onChange={(e) => setKbContext(e.target.value)} />
                  </div>
                </>
              )}

              {kbFilePath && !kbProcessed && (
                <button
                  className="btn btn-primary"
                  onClick={handleProcessKB}
                  disabled={kbLoading || (useCase === "excel" && (!keyCol || !valCol))}
                >
                  {kbLoading ? <Spinner text="Processing KB…" /> : "Process Knowledge Base"}
                </button>
              )}

              {kbProcessed && kbStats && (
                <div className="metrics-row">
                  <Metric label="Entries" value={kbStats.entries_processed || kbStats.total_chunks || "—"} />
                  <Metric label="Embeddings" value={kbStats.embeddings_created || "—"} />
                  {kbStats.embeddings_failed > 0 && <Metric label="Failed" value={kbStats.embeddings_failed} />}
                  <StatusBadge text="KB Ready" type="success" />
        </div>
              )}
      </section>

            {/* Step 2: Query Upload */}
            {kbProcessed && (
              <section className="panel">
                <h2>Step 2 — Upload Queries (Excel)</h2>

                <FileUpload
                  accept=".xlsx,.xls,.csv"
                  label="Choose query file"
                  sessionId={sessionId}
                  onUploaded={handleQueryUploaded}
                  onError={showError}
                  disabled={processing}
                />

                {queryPreview && (
                  <>
                    <DataPreview rows={queryPreview.rows} columns={queryPreview.columns} />
                    {effectiveMatchCountMode === "tag_driven" && queryTagCol && (
                      <div className="info-box" style={{ marginBottom: 12 }}>
                        {(() => {
                          const row = (queryPreview.rows || []).find((r) => {
                            const v = r?.[queryTagCol];
                            return v != null && String(v).trim() !== "";
                          });
                          const raw = row?.[queryTagCol] ?? "";
                          const parts = splitTagPreview(raw, queryTagSep);
                          return (
                            <>
                              <strong>Tag split preview</strong>
                              <p className="muted" style={{ marginTop: 6 }}>
                                Sample value: {raw ? String(raw) : "—"}
                              </p>
                              <p className="muted" style={{ marginTop: 4 }}>
                                Parsed tags ({parts.length}): {parts.length ? parts.join(" | ") : "none"}
                              </p>
                            </>
                          );
                        })()}
                      </div>
                    )}
                    <div className="column-selectors">
                      <div>
                        <label>Query Column</label>
                        <select className="input" value={queryCol} onChange={(e) => setQueryCol(e.target.value)}>
                          {queryColumns.map((c) => <option key={c}>{c}</option>)}
                        </select>
                      </div>
                      <div>
                        <label>Primary key column (optional)</label>
                        <select className="input" value={queryPkCol} onChange={(e) => setQueryPkCol(e.target.value)}>
                          <option value="">— None —</option>
                          {queryColumns.map((c) => (
                            <option key={c} value={c}>{c}</option>
                          ))}
                        </select>
                      </div>
                      {effectiveMatchCountMode === "tag_driven" && (
                        <div>
                          <label>Tag column</label>
                          <select className="input" value={queryTagCol} onChange={(e) => setQueryTagCol(e.target.value)}>
                            <option value="">— Select tag column —</option>
                            {queryColumns.map((c) => (
                              <option key={c} value={c}>{c}</option>
                            ))}
                          </select>
                        </div>
                      )}
                      {effectiveMatchCountMode === "tag_driven" && (
                        <div>
                          <label>Tag separator</label>
                          <select className="input" value={queryTagSep} onChange={(e) => setQueryTagSep(e.target.value)}>
                            {TAG_SEPARATOR_OPTIONS.map((opt) => (
                              <option key={opt.value} value={opt.value}>{opt.label}</option>
                            ))}
                          </select>
                        </div>
                      )}
                    </div>
                    <button
                      className="btn btn-primary"
                      onClick={handleStartQA}
                      disabled={processing || !queryCol || (effectiveMatchCountMode === "tag_driven" && !queryTagCol)}
                    >
                      {processing ? (
                        <Spinner text={formatQueryJobProgress(queryJobProgress) || "Processing…"} />
                      ) : (
                        `Process First ${cfg.qa_sample_size} & Start QA`
                      )}
                    </button>
                  </>
                )}
              </section>
            )}
          </>
        )}
      </main>

      {fullProcessEstimate && (
        <ProcessAllCostModal
          estimate={fullProcessEstimate}
          title={fullProcessModalMeta?.title}
          proceedPrompt={fullProcessModalMeta?.prompt}
          onClose={closeFullProcessModal}
          onProceed={handleProceedFullProcess}
        />
      )}
      {errorModal && (
        <ErrorModal
          title={errorModal.title}
          message={errorModal.message}
          onClose={closeErrorModal}
          onCopy={copyErrorModalText}
        />
      )}
    </div>
  );
}
