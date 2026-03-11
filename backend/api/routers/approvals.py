"""
routers/approvals.py — Maker-Checker workflow (overrides + source requests).
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.deps import get_db, get_current_user
from backend.api.schemas import (
    SubmitOverrideRequest, SubmitSourceRequest,
    ApprovalRequestOut, ReviewDecision,
)
from backend.database.models import ApprovalRequest, Company, Answer, User

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def _approval_to_out(req: ApprovalRequest, company: Company) -> ApprovalRequestOut:
    return ApprovalRequestOut(
        id=str(req.id),
        type=req.type,
        company_id=str(req.company_id),
        company_name=company.name if company else "Unknown",
        company_ticker=company.ticker or "" if company else "",
        submitted_by=req.submitted_by or "Unknown",
        submitted_at=req.submitted_at.isoformat() if req.submitted_at else "",
        justification=req.justification or "",
        status=req.status,
        indicator_name=req.indicator_name,
        current_value=req.current_value,
        new_value=req.new_value,
        source_type=req.source_type,
        source_name=req.source_name,
        source_tags=req.source_tags or [],
    )


# ── GET /api/approvals ────────────────────────────────────────────────────────

@router.get("", response_model=List[ApprovalRequestOut])
def list_approvals(
    status_filter: str = "PENDING",
    db: Session = Depends(get_db),
):
    q = db.query(ApprovalRequest)
    if status_filter != "ALL":
        q = q.filter(ApprovalRequest.status == status_filter)
    requests = q.order_by(ApprovalRequest.submitted_at.desc()).all()
    result = []
    for req in requests:
        company = db.query(Company).filter_by(id=req.company_id).first()
        result.append(_approval_to_out(req, company))
    return result


# ── POST /api/approvals/override ──────────────────────────────────────────────

@router.post("/override", response_model=ApprovalRequestOut, status_code=status.HTTP_201_CREATED)
def submit_override(body: SubmitOverrideRequest, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=int(body.company_id)).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    req = ApprovalRequest(
        type="OVERRIDE",
        company_id=company.id,
        submitted_by=body.submitted_by or "Unknown",
        justification=body.justification,
        status="PENDING",
        indicator_id=body.indicator_id,
        indicator_name=body.indicator_name,
        current_value=str(body.current_value),
        new_value=str(body.new_value),
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return _approval_to_out(req, company)


# ── POST /api/approvals/source ────────────────────────────────────────────────

@router.post("/source", response_model=ApprovalRequestOut, status_code=status.HTTP_201_CREATED)
def submit_source_request(body: SubmitSourceRequest, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=int(body.company_id)).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    req = ApprovalRequest(
        type="SOURCE",
        company_id=company.id,
        submitted_by=body.submitted_by or "Unknown",
        justification=body.justification,
        status="PENDING",
        source_type=body.source_type,
        source_name=body.source_name,
        source_tags=body.source_tags,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return _approval_to_out(req, company)


# ── PUT /api/approvals/{id}/approve ──────────────────────────────────────────

@router.put("/{req_id}/approve", response_model=ApprovalRequestOut)
def approve_request(req_id: str, body: ReviewDecision, db: Session = Depends(get_db)):
    req = db.query(ApprovalRequest).filter_by(id=int(req_id)).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "PENDING":
        raise HTTPException(status_code=400, detail="Request already reviewed")

    req.status = "APPROVED"
    req.reviewed_by = body.reviewed_by
    req.reviewed_at = datetime.utcnow()

    # If it's an override, apply it to the answers table
    if req.type == "OVERRIDE" and req.indicator_id:
        answer = (
            db.query(Answer)
            .filter_by(company_id=req.company_id, indicator_id=req.indicator_id)
            .first()
        )
        if answer:
            answer.answer_value = str(req.new_value)
            answer.is_verified = True
            answer.notes = req.justification
            answer.updated_at = datetime.utcnow()

    db.commit()
    company = db.query(Company).filter_by(id=req.company_id).first()
    return _approval_to_out(req, company)


# ── PUT /api/approvals/{id}/reject ────────────────────────────────────────────

@router.put("/{req_id}/reject", response_model=ApprovalRequestOut)
def reject_request(req_id: str, body: ReviewDecision, db: Session = Depends(get_db)):
    req = db.query(ApprovalRequest).filter_by(id=int(req_id)).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "PENDING":
        raise HTTPException(status_code=400, detail="Request already reviewed")

    req.status = "REJECTED"
    req.reviewed_by = body.reviewed_by
    req.reviewed_at = datetime.utcnow()
    req.rejection_reason = body.reason

    db.commit()
    company = db.query(Company).filter_by(id=req.company_id).first()
    return _approval_to_out(req, company)
