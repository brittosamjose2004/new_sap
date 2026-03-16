"""
routers/pipeline.py — Pipeline run and job status.
"""
from __future__ import annotations

import sys, subprocess, threading
import json, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

from backend.api.deps import get_db, get_current_user
from backend.api.schemas import RunPipelineRequest, PipelineJobOut
from backend.database.models import Company, PipelineJob, User

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

# Built-in NSE symbols — used to skip auto-discovery for known companies
_BUILTIN_NSE_SYMBOLS = [
    {"nse_symbol": "TCS"},
    {"nse_symbol": "HCLTECH"},
    {"nse_symbol": "INFY"},
    {"nse_symbol": "WIPRO"},
    {"nse_symbol": "RELIANCE"},
]


def _direct_questionnaire_fill(company_name: str, company_id: int, year: int) -> int:
    """
    Directly invoke QuestionnaireEngine to fill smart-default answers for
    (company, year).  Returns the number of answers saved.
    """
    from backend.questionnaire.engine import QuestionnaireEngine
    from backend.database.db import get_session
    from backend.database.models import Company as _Company
    engine = QuestionnaireEngine(company_name, year, standard="ALL")
    engine.setup()
    # Pin to the exact DB record so ilike won't match the wrong company.
    if engine.company and engine.company.id != company_id:
        _db = get_session()
        exact = _db.query(_Company).filter_by(id=company_id).first()
        if exact:
            engine.company = exact
        _db.close()
    return engine.run_auto(module_filter=None)


def _company_slug(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", (name or "company").strip())
    slug = slug.strip("_")
    return slug or "company"


def _export_company_data_snapshot(company_id: int, company_name: str) -> None:
    """Write a company-wise JSON snapshot of collected data to disk."""
    from backend.database.db import get_session
    from backend.database.models import Company as _Company, ScrapedData, QuestionnaireSession, Answer, PipelineJob as _PipelineJob

    root = Path(__file__).parent.parent.parent.parent
    company_dir = root / "data" / "company_data" / _company_slug(company_name)
    company_dir.mkdir(parents=True, exist_ok=True)

    db = get_session()
    try:
        company = db.query(_Company).filter(_Company.id == company_id).first()
        scraped_rows = db.query(ScrapedData).filter(ScrapedData.company_id == company_id).all()
        sessions = db.query(QuestionnaireSession).filter(QuestionnaireSession.company_id == company_id).all()
        answers = db.query(Answer).filter(Answer.company_id == company_id).all()
        jobs = db.query(_PipelineJob).filter(_PipelineJob.company_id == company_id).order_by(_PipelineJob.started_at.desc()).limit(100).all()

        payload = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "company": {
                "id": company.id if company else company_id,
                "name": (company.name if company else company_name),
                "ticker": (company.ticker if company else "") or "",
                "cin": (company.cin if company else "") or "",
                "sector": (company.sector if company else "") or "",
                "exchange": (company.exchange if company else "") or "",
                "website": (company.website if company else "") or "",
                "headquarters": (company.headquarters if company else "") or "",
            },
            "years": sorted({s.year for s in sessions}),
            "counts": {
                "scraped_data": len(scraped_rows),
                "sessions": len(sessions),
                "answers": len(answers),
                "jobs": len(jobs),
            },
            "scraped_data": [
                {
                    "year": r.year,
                    "source": r.source,
                    "key": r.data_key,
                    "value": r.data_value,
                    "scraped_at": r.scraped_at.isoformat() if r.scraped_at else None,
                }
                for r in scraped_rows
            ],
            "sessions": [
                {
                    "id": s.id,
                    "year": s.year,
                    "standard": s.standard,
                    "status": s.status,
                    "total_questions": s.total_questions,
                    "answered_questions": s.answered_questions,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                }
                for s in sessions
            ],
            "answers": [
                {
                    "session_id": a.session_id,
                    "year": a.year,
                    "indicator_id": a.indicator_id,
                    "module": a.module,
                    "indicator_name": a.indicator_name,
                    "answer_value": a.answer_value,
                    "answer_unit": a.answer_unit,
                    "source": a.source,
                    "confidence": a.confidence,
                    "is_verified": a.is_verified,
                    "updated_at": a.updated_at.isoformat() if a.updated_at else None,
                }
                for a in answers
            ],
            "jobs": [
                {
                    "id": j.id,
                    "year": j.year,
                    "status": j.status,
                    "error_msg": j.error_msg,
                    "started_at": j.started_at.isoformat() if j.started_at else None,
                    "finished_at": j.finished_at.isoformat() if j.finished_at else None,
                }
                for j in jobs
            ],
        }

        latest_path = company_dir / "latest_snapshot.json"
        latest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        history_path = company_dir / f"snapshot_{stamp}.json"
        history_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    finally:
        db.close()


def _run_pipeline_task(
    job_id: int,
    company_name: str,
    nse_symbol: str,
    financial_years: list,   # list[int] — the exact years the user selected
    all_years: bool,
):
    """Background task — run scrape + questionnaire fill for every requested year.

    Flow:
      1. Call run_all.py with the EXACT selected years from the frontend.
      2. For EVERY requested year, ensure a QuestionnaireSession exists.
         If any are missing, fill via QuestionnaireEngine so UI can always
         visualize analytics for each selected year.
    """
    from backend.database.db import get_session
    from backend.database.models import QuestionnaireSession
    db = get_session()
    job = db.query(PipelineJob).filter_by(id=job_id).first()
    if not job:
        db.close()
        return

    company_id = job.company_id

    try:
        job.status = "FETCHING"
        db.commit()

        root = Path(__file__).parent.parent.parent.parent
        selected_years = sorted(set(financial_years or [2026]))
        latest_year = max(selected_years)

        # Attempt PDF scrape via run_all.py (works only for built-in NSE companies).
        # Non-matching companies cause run_all.py to exit 0 with a log message.
        cmd = [
            sys.executable, str(root / "run_all.py"),
            "--batch",
            "--companies", company_name,
            "--year", str(latest_year),
            "--years", *[str(y) for y in selected_years],
        ]
        # Resolve symbol: if company.ticker looks like a fallback (e.g. "HCLTECHNOLOGIESFRANCE")
        # try auto-discovering the real ticker from Yahoo Finance (works for ANY global exchange).
        resolved_symbol = nse_symbol
        is_builtin = any(comp["nse_symbol"] == nse_symbol for comp in _BUILTIN_NSE_SYMBOLS)
        # Also skip auto-discovery if ticker looks like a real symbol (short, no spaces)
        looks_real = nse_symbol and len(nse_symbol) <= 15 and " " not in nse_symbol
        if not is_builtin and not looks_real:
            try:
                import requests as _req
                _yf_resp = _req.get(
                    "https://query2.finance.yahoo.com/v1/finance/search",
                    params={"q": company_name, "quotesCount": 10, "newsCount": 0},
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=10,
                )
                if _yf_resp.ok:
                    for _q in _yf_resp.json().get("quotes", []):
                        _sym = _q.get("symbol", "")
                        if _q.get("quoteType") not in ("EQUITY", None):
                            continue
                        if ".NS" in _sym:
                            resolved_symbol = _sym.replace(".NS", "")
                            break
                        elif ".BO" in _sym and resolved_symbol == nse_symbol:
                            resolved_symbol = _sym.replace(".BO", "")
                        elif resolved_symbol == nse_symbol and _sym:
                            # Global ticker (e.g. AAPL, SHEL, BHP)
                            resolved_symbol = _sym
            except Exception:
                pass  # keep original nse_symbol

        # Pass the resolved ticker. For NSE/BSE companies this triggers a real
        # PDF download + scrape. For global companies Yahoo Finance data is used.
        # If no valid ticker found, run_all.py falls back to smart defaults.
        cmd += ["--nse-symbol", resolved_symbol]

        subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=str(root))

        # ── Ensure every requested year has data for THIS company ─────────────
        # run_all.py may have saved data for a different company_id (name match
        # on a built-in entry like "HCL Technologies" instead of "HCL FRANCE"),
        # or it may have done nothing (no built-in match). Either way, fill any
        # missing sessions for the exact years the user selected.
        db.expire_all()
        for yr in selected_years:
            has = db.query(QuestionnaireSession).filter(
                QuestionnaireSession.company_id == company_id,
                QuestionnaireSession.year == yr,
            ).first()
            if not has:
                try:
                    _direct_questionnaire_fill(company_name, company_id, yr)
                except Exception:
                    pass  # best-effort; continue to next year

        job.status = "PUBLISHED"

    except subprocess.TimeoutExpired:
        job.status = "ERROR"
        job.error_msg = "Pipeline timed out after 10 minutes"
    except Exception as exc:
        job.status = "ERROR"
        job.error_msg = str(exc)[:500]
    finally:
        job.finished_at = datetime.utcnow()
        db.commit()
        db.close()
        try:
            _export_company_data_snapshot(company_id=company_id, company_name=company_name)
        except Exception:
            pass


# ── POST /api/pipeline/run ────────────────────────────────────────────────────

@router.post("/run", response_model=List[PipelineJobOut])
def run_pipeline(
    body: RunPipelineRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    # Resolve companies
    if body.company_ids:
        companies = db.query(Company).filter(Company.id.in_([int(i) for i in body.company_ids])).all()
    else:
        companies = db.query(Company).all()

    if not companies:
        raise HTTPException(status_code=400, detail="No companies found")

    # Parse every selected financial year into integers.
    # e.g. ["FY2022", "FY2024", "FY2025"] → [2022, 2024, 2025]
    financial_years_int: list = sorted(set(
        int(fy.replace("FY", "").strip())
        for fy in (body.financial_years or ["FY2026"])
        if fy.upper().startswith("FY") and fy[2:].strip().isdigit()
    ))
    if not financial_years_int:
        financial_years_int = [2026]
    # When all_years toggle is on, expand to the 5 years up to the latest
    if body.all_years:
        latest = max(financial_years_int)
        financial_years_int = sorted(set(financial_years_int) | set(range(latest - 4, latest + 1)))
    primary_year = max(financial_years_int)  # shown in the job row

    jobs: List[PipelineJobOut] = []
    for company in companies:
        # Create one job record per company (covers all selected years)
        job = PipelineJob(
            company_id=company.id,
            company_name=company.name,
            year=primary_year,
            status="QUEUED",
            data_sources=body.data_sources,
            triggered_by="api",
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        # Launch background task with the full years list
        nse_symbol = company.ticker or company.name.upper().replace(" ", "")
        background_tasks.add_task(
            _run_pipeline_task,
            job.id, company.name, nse_symbol, financial_years_int, body.all_years
        )

        jobs.append(PipelineJobOut(
            id=str(job.id),
            company_id=str(job.company_id),
            company_name=job.company_name or "",
            year=job.year,
            status=job.status,
            error_msg=job.error_msg,
            started_at=job.started_at.isoformat(),
            finished_at=job.finished_at.isoformat() if job.finished_at else None,
        ))

    return jobs


# ── GET /api/pipeline/status/{job_id} ────────────────────────────────────────

@router.get("/status/{job_id}", response_model=PipelineJobOut)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(PipelineJob).filter_by(id=int(job_id)).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return PipelineJobOut(
        id=str(job.id),
        company_id=str(job.company_id),
        company_name=job.company_name or "",
        year=job.year,
        status=job.status,
        error_msg=job.error_msg,
        started_at=job.started_at.isoformat(),
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
    )


# ── GET /api/pipeline/jobs ────────────────────────────────────────────────────

@router.get("/jobs", response_model=List[PipelineJobOut])
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(PipelineJob).order_by(PipelineJob.started_at.desc()).limit(50).all()
    return [
        PipelineJobOut(
            id=str(j.id),
            company_id=str(j.company_id),
            company_name=j.company_name or "",
            year=j.year,
            status=j.status,
            error_msg=j.error_msg,
            started_at=j.started_at.isoformat(),
            finished_at=j.finished_at.isoformat() if j.finished_at else None,
        )
        for j in jobs
    ]
