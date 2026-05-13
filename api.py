"""
FastAPI backend for the Text Matching Tool.
Heavy operations (KB setup, query processing) run as background jobs —
the browser can disconnect, screen can turn off, and work continues.
The frontend polls /api/job/{job_id} for status.
"""

import os
import sys

# Force UTF-8 for stdout/stderr — nohup redirects can default to ASCII
for stream_name in ('stdout', 'stderr'):
    stream = getattr(sys, stream_name, None)
    if stream and hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8', errors='replace')

import uuid
import json
import threading
import traceback
from typing import Optional, List, Literal
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.requests import Request
from pydantic import BaseModel

from matching_pipeline import MatchingPipeline
from processors import ExcelProcessor
from utils.export import ResultExporter
from qa.feedback_store import QAFeedbackStore
from qa.qa_learner import QALearner
from config import QA_SAMPLE_SIZE, MAX_TOP_N, DEFAULT_TOP_N, LLM_MODEL
from utils.llm_router import validate_keys_for_model
from utils.cost_estimate import count_queries_slice, build_cost_estimate
from utils.llm_pricing import QUERY_LLM_MODELS

os.makedirs("./data", exist_ok=True)
os.makedirs("./data/exports", exist_ok=True)

app = FastAPI(title="SMRAG – Text Matching API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"https://.*\.ngrok(-free)?\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# ── In-memory stores ───────────────────────────────────────────────────────
sessions: dict = {}
jobs: dict = {}  # job_id -> {status, result, error, progress}


def _get_session(session_id: str) -> dict:
    if session_id not in sessions:
        raise HTTPException(404, "Session not found. Create one first via /api/session.")
    return sessions[session_id]


def _run_job(job_id: str, fn, *args, **kwargs):
    """Run fn in a background thread; store result or error in jobs dict."""
    def worker():
        try:
            jobs[job_id]["status"] = "running"
            result = fn(*args, **kwargs)
            jobs[job_id]["result"] = result
            jobs[job_id]["status"] = "done"
        except Exception as e:
            jobs[job_id]["error"] = str(e)
            jobs[job_id]["status"] = "error"
            traceback.print_exc()

    jobs[job_id] = {"status": "pending", "result": None, "error": None, "progress": None}
    t = threading.Thread(target=worker, daemon=True)
    t.start()


# ── Pydantic models ────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    api_key: str
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None

class SetupPDFRequest(BaseModel):
    session_id: str
    file_path: str
    use_intelligent_chunking: bool = True
    user_context: Optional[str] = None

class SetupExcelRequest(BaseModel):
    session_id: str
    file_path: str
    key_column: str
    value_column: str
    additional_columns: Optional[List[str]] = None
    kb_context_prompt: Optional[str] = None

class ProcessQueriesRequest(BaseModel):
    session_id: str
    file_path: str
    query_column: str
    top_n: int = DEFAULT_TOP_N
    use_llm_reranking: bool = True
    use_query_expansion: bool = True
    query_offset: int = 0
    query_limit: Optional[int] = None
    matching_guidance: Optional[str] = None
    primary_key_column: Optional[str] = None
    llm_model: str = LLM_MODEL
    match_count_mode: Literal["fixed", "auto", "tag_driven"] = "fixed"
    min_llm_score: float = 0.70
    min_combined_score: float = 0.0
    relative_ratio: float = 0.75
    gap_stop_delta: float = 0.12
    tag_column: Optional[str] = None
    tag_separator: Optional[str] = None

class EstimateCostRequest(BaseModel):
    session_id: str
    file_path: str
    query_column: str
    primary_key_column: Optional[str] = None
    query_offset: int = 0
    query_limit: Optional[int] = None
    top_n: int = DEFAULT_TOP_N
    use_llm_reranking: bool = True
    use_query_expansion: bool = True
    matching_guidance: Optional[str] = None
    llm_model: str = LLM_MODEL

class QAFeedbackItem(BaseModel):
    session_id: str
    qa_session_id: str
    query_id: str
    query: str
    match_rank: int
    match_id: str
    match_text: str
    status: str
    notes: Optional[str] = None
    primary_key: Optional[str] = None
    tag_index: Optional[int] = None
    tag_value: Optional[str] = None

class ApplyLearningsRequest(BaseModel):
    session_id: str
    qa_session_id: str


# Match-count modes this backend build supports (frontend uses this to avoid 422 vs older servers).
MATCH_COUNT_MODES: List[str] = ["fixed", "auto", "tag_driven"]


# ── Config ─────────────────────────────────────────────────────────────────

@app.get("/api/config")
def get_config():
    return {
        "qa_sample_size": QA_SAMPLE_SIZE,
        "max_top_n": MAX_TOP_N,
        "default_top_n": DEFAULT_TOP_N,
        "query_llm_models": QUERY_LLM_MODELS,
        "default_query_llm": LLM_MODEL,
        "match_count_modes": MATCH_COUNT_MODES,
    }


# ── Job status polling ─────────────────────────────────────────────────────

@app.get("/api/job/{job_id}")
def get_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found.")
    job = jobs[job_id]
    return {
        "job_id": job_id,
        "status": job["status"],
        "result": job["result"],
        "error": job["error"],
        "progress": job.get("progress"),
    }


# ── Session management ─────────────────────────────────────────────────────

@app.post("/api/session")
def create_session(body: SessionCreate):
    sid = str(uuid.uuid4())
    anth = (body.anthropic_api_key or "").strip()
    ggl = (body.google_api_key or "").strip()
    sessions[sid] = {
        "openai_api_key": body.api_key.strip(),
        "anthropic_api_key": anth,
        "google_api_key": ggl,
        "pipeline": MatchingPipeline(
            body.api_key.strip(),
            anthropic_api_key=anth or None,
            google_api_key=ggl or None,
        ),
        "results": [],
        "qa_session_id": None,
        "use_case": None,
    }
    return {"session_id": sid}


@app.post("/api/estimate-cost")
def estimate_cost(body: EstimateCostRequest):
    sess = _get_session(body.session_id)
    try:
        validate_keys_for_model(
            body.llm_model,
            sess.get("openai_api_key"),
            sess.get("anthropic_api_key"),
            sess.get("google_api_key"),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    use_case = sess.get("use_case") or "excel_kb"
    n, texts = count_queries_slice(
        body.file_path,
        body.query_column,
        body.primary_key_column,
        body.query_offset,
        body.query_limit,
    )
    est = build_cost_estimate(
        num_queries=n,
        query_texts=texts,
        use_case=use_case,
        top_n=body.top_n,
        use_llm_reranking=body.use_llm_reranking,
        use_query_expansion=body.use_query_expansion,
        matching_guidance=body.matching_guidance or "",
        llm_model=body.llm_model,
    )
    return est


@app.get("/api/session-state/{session_id}")
def get_session_state(session_id: str):
    """Return the current state of a session so the frontend can reconnect."""
    if session_id not in sessions:
        raise HTTPException(404, "Session expired or not found.")
    sess = sessions[session_id]
    pipeline: MatchingPipeline = sess["pipeline"]

    kb_ready = getattr(pipeline, 'semantic_search', None) is not None
    results = sess.get("results", [])
    safe_results = []
    for r in results:
        sr = dict(r)
        sr.setdefault("matches", [])
        safe_results.append(sr)

    return {
        "alive": True,
        "kb_ready": kb_ready,
        "result_count": len(safe_results),
        "results": safe_results,
        "use_case": sess.get("use_case"),
        "qa_session_id": sess.get("qa_session_id"),
    }


# ── File upload ─────────────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    safe_name = file.filename.replace("/", "_")
    path = f"./data/{safe_name}"
    contents = await file.read()
    with open(path, "wb") as f:
        f.write(contents)
    return {"file_path": path, "file_name": safe_name}


# ── Excel preview ───────────────────────────────────────────────────────────

@app.post("/api/preview")
def preview_excel(file_path: str = Form(...)):
    proc = ExcelProcessor()
    proc.load_excel(file_path)
    preview = proc.preview_data(10)
    return {
        "columns": proc.get_columns(),
        "rows": json.loads(preview.to_json(orient="records")),
        "total_rows": len(proc.data),
    }


# ── KB setup (background jobs) ─────────────────────────────────────────────

def _do_setup_pdf(session_id, file_path, use_intelligent_chunking, user_context):
    sess = sessions[session_id]
    pipeline = sess["pipeline"]
    stats = pipeline.setup_pdf_knowledge_base(
        file_path,
        use_intelligent_chunking=use_intelligent_chunking,
        user_context=user_context,
        kb_context_prompt=user_context,
    )
    sess["use_case"] = "pdf_kb"
    serializable = {}
    for k, v in stats.items():
        if isinstance(v, dict):
            serializable[k] = {sk: str(sv) for sk, sv in v.items()}
        else:
            serializable[k] = v
    return {"stats": serializable}


def _do_setup_excel(session_id, file_path, key_column, value_column, additional_columns, kb_context_prompt):
    sess = sessions[session_id]
    pipeline = sess["pipeline"]
    stats = pipeline.setup_excel_knowledge_base(
        file_path, key_column, value_column,
        additional_columns,
        kb_context_prompt=kb_context_prompt,
    )
    sess["use_case"] = "excel_kb"
    return {"stats": stats}


@app.post("/api/setup/pdf")
def setup_pdf(body: SetupPDFRequest):
    _get_session(body.session_id)
    job_id = str(uuid.uuid4())
    _run_job(job_id, _do_setup_pdf,
             body.session_id, body.file_path,
             body.use_intelligent_chunking, body.user_context)
    return {"job_id": job_id}


@app.post("/api/setup/excel")
def setup_excel(body: SetupExcelRequest):
    _get_session(body.session_id)
    job_id = str(uuid.uuid4())
    _run_job(job_id, _do_setup_excel,
             body.session_id, body.file_path,
             body.key_column, body.value_column,
             body.additional_columns, body.kb_context_prompt)
    return {"job_id": job_id}


# ── Query processing (background job) ──────────────────────────────────────

def _do_process_queries(session_id, file_path, query_column, top_n,
                        use_llm_reranking, use_query_expansion,
                        query_offset, query_limit, matching_guidance,
                        primary_key_column, job_id, llm_model,
                        match_count_mode, min_llm_score, min_combined_score,
                        relative_ratio, gap_stop_delta,
                        tag_column, tag_separator):
    sess = sessions[session_id]
    pipeline = sess["pipeline"]

    def _progress(stage: str, done: int, total: int) -> None:
        j = jobs.get(job_id)
        if j is not None:
            j["progress"] = {"stage": stage, "done": done, "total": total}

    results = pipeline.process_queries(
        file_path, query_column,
        top_n=top_n,
        use_llm_reranking=use_llm_reranking,
        use_query_expansion=use_query_expansion,
        query_offset=query_offset,
        query_limit=query_limit,
        matching_guidance=matching_guidance,
        primary_key_column=primary_key_column,
        progress_callback=_progress,
        llm_model=llm_model,
        match_count_mode=match_count_mode,
        min_llm_score=min_llm_score,
        min_combined_score=min_combined_score,
        relative_ratio=relative_ratio,
        gap_stop_delta=gap_stop_delta,
        tag_column=tag_column,
        tag_separator=tag_separator,
    )
    if job_id in jobs:
        nr = len(results)
        jobs[job_id]["progress"] = {"stage": "done", "done": nr, "total": nr}
    sess["results"] = sess.get("results", []) + results
    return {"count": len(results), "results": results}


@app.post("/api/clear-results/{session_id}")
def clear_results(session_id: str):
    """Clear stored results so a full reprocess starts fresh."""
    sess = _get_session(session_id)
    sess["results"] = []
    return {"status": "ok"}


@app.post("/api/process-queries")
def process_queries(body: ProcessQueriesRequest):
    sess = _get_session(body.session_id)
    try:
        validate_keys_for_model(
            body.llm_model,
            sess.get("openai_api_key"),
            sess.get("anthropic_api_key"),
            sess.get("google_api_key"),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if body.match_count_mode == "tag_driven":
        if not (body.tag_column or "").strip():
            raise HTTPException(400, "Tag column is required for tag-driven mode.")
        if not (body.tag_separator or ""):
            raise HTTPException(400, "Tag separator is required for tag-driven mode.")
    job_id = str(uuid.uuid4())
    _run_job(job_id, _do_process_queries,
             body.session_id, body.file_path, body.query_column,
             body.top_n, body.use_llm_reranking, body.use_query_expansion,
             body.query_offset, body.query_limit, body.matching_guidance,
             body.primary_key_column, job_id, body.llm_model,
             body.match_count_mode, body.min_llm_score,
             body.min_combined_score, body.relative_ratio,
             body.gap_stop_delta,
             body.tag_column, body.tag_separator)
    return {"job_id": job_id}


# ── QA endpoints (lightweight — no background needed) ──────────────────────

@app.post("/api/qa/session")
def create_qa_session(session_id: str = Form(...), use_case: str = Form(...), total: int = Form(...)):
    qa_id = str(uuid.uuid4())
    store = QAFeedbackStore()
    store.create_session(qa_id, use_case, total)
    sess = _get_session(session_id)
    sess["qa_session_id"] = qa_id
    return {"qa_session_id": qa_id}


@app.post("/api/qa/feedback")
def save_feedback(body: QAFeedbackItem):
    store = QAFeedbackStore()
    store.add_feedback(
        body.qa_session_id, body.query_id, body.query,
        body.match_rank, body.match_id, body.match_text,
        body.status, notes=body.notes, primary_key_value=body.primary_key,
        tag_index=body.tag_index, tag_value=body.tag_value,
    )
    return {"status": "ok"}


@app.get("/api/qa/stats/{qa_session_id}")
def qa_stats(qa_session_id: str):
    store = QAFeedbackStore()
    stats = store.get_session_stats(qa_session_id)
    return stats


@app.get("/api/qa/analysis/{qa_session_id}")
def qa_analysis(qa_session_id: str):
    learner = QALearner()
    analysis = learner.analyze_qa_session(qa_session_id)
    return analysis


@app.post("/api/qa/apply-learnings")
def apply_learnings(body: ApplyLearningsRequest):
    sess = _get_session(body.session_id)
    pipeline: MatchingPipeline = sess["pipeline"]
    changes = pipeline.apply_qa_learnings(body.qa_session_id)
    return {"status": "ok", "changes": changes}


# ── KB keys ────────────────────────────────────────────────────────────────

@app.get("/api/kb-keys/{session_id}")
def get_kb_keys(session_id: str):
    sess = _get_session(session_id)
    pipeline: MatchingPipeline = sess["pipeline"]
    keys = sorted({
        entry.get("key", "").strip()
        for entry in pipeline.knowledge_base
        if entry.get("key", "").strip()
    })
    return {"keys": keys}


# ── Export ──────────────────────────────────────────────────────────────────

@app.post("/api/export/results")
def export_results(session_id: str = Form(...)):
    sess = _get_session(session_id)
    exporter = ResultExporter()
    use_case = sess.get("use_case", "excel_kb")
    filepath = exporter.export_results(sess["results"], use_case)
    return FileResponse(filepath, filename=os.path.basename(filepath),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/api/export/qa")
def export_qa(qa_session_id: str = Form(...)):
    store = QAFeedbackStore()
    feedback = store.get_session_feedback(qa_session_id)
    exporter = ResultExporter()
    filepath = exporter.export_qa_results(feedback)
    return FileResponse(filepath, filename=os.path.basename(filepath),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
