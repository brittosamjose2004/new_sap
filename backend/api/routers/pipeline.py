"""
routers/pipeline.py — Pipeline run and job status.
"""
from __future__ import annotations

import sys, subprocess, threading
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


def _run_pipeline_task(job_id: int, company_name: str, nse_symbol: str, year: int, all_years: bool):
    """Background task: run run_all.py for a company and update job status."""
    from backend.database.db import get_session
    db = get_session()
    job = db.query(PipelineJob).filter_by(id=job_id).first()
    if not job:
        db.close()
        return

    try:
        job.status = "FETCHING"
        db.commit()

        root = Path(__file__).parent.parent.parent.parent
        cmd = [
            sys.executable, str(root / "run_all.py"),
            "--batch",
            "--companies", company_name,
            "--year", str(year),
        ]
        if all_years:
            cmd.append("--all-years")

        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=600, cwd=str(root)
        )

        if result.returncode == 0:
            job.status = "PUBLISHED"
        else:
            job.status = "ERROR"
            job.error_msg = result.stderr[-500:] if result.stderr else "Unknown error"

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

    # Determine year
    year_str = body.financial_years[0] if body.financial_years else "FY2026"
    year = int(year_str.replace("FY", "").strip()) if year_str.startswith("FY") else 2026

    jobs: List[PipelineJobOut] = []
    for company in companies:
        # Create job record
        job = PipelineJob(
            company_id=company.id,
            company_name=company.name,
            year=year,
            status="QUEUED",
            data_sources=body.data_sources,
            triggered_by="api",
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        # Launch background task
        nse_symbol = company.ticker or company.name.upper().replace(" ", "")
        background_tasks.add_task(
            _run_pipeline_task,
            job.id, company.name, nse_symbol, year, body.all_years
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
