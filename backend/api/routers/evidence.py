"""
routers/evidence.py — Evidence/source management per company.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.api.schemas import AddEvidenceRequest, EvidenceItemOut, SubmitSourceRequest, ApprovalRequestOut
from backend.database.models import EvidenceSource, ApprovalRequest, Company

router = APIRouter(prefix="/api/companies/{company_id}/evidence", tags=["evidence"])


# ── GET /api/companies/{id}/evidence ─────────────────────────────────────────

@router.get("", response_model=List[EvidenceItemOut])
def list_evidence(company_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(EvidenceSource)
        .filter_by(company_id=int(company_id))
        .order_by(EvidenceSource.created_at.desc())
        .all()
    )
    return [
        EvidenceItemOut(
            id=str(e.id), type=e.type, name=e.name,
            date=e.date or "", status=e.status, tags=e.tags or [],
        )
        for e in rows
    ]


# ── POST /api/companies/{id}/evidence ────────────────────────────────────────

@router.post("", response_model=EvidenceItemOut, status_code=status.HTTP_201_CREATED)
def add_evidence(company_id: str, body: AddEvidenceRequest, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=int(company_id)).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Create evidence with pending_review status + approval request
    ev = EvidenceSource(
        company_id=int(company_id),
        type=body.type,
        name=body.name,
        date=datetime.utcnow().strftime("%Y-%m-%d"),
        status="pending_review",
        tags=body.tags,
    )
    db.add(ev)

    # Create corresponding approval request
    req = ApprovalRequest(
        type="SOURCE",
        company_id=int(company_id),
        submitted_by=body.submitted_by or "Unknown",
        justification=body.justification or "",
        status="PENDING",
        source_type=body.type,
        source_name=body.name,
        source_tags=body.tags,
    )
    db.add(req)
    db.commit()
    db.refresh(ev)

    return EvidenceItemOut(
        id=str(ev.id), type=ev.type, name=ev.name,
        date=ev.date or "", status=ev.status, tags=ev.tags or [],
    )


# ── DELETE /api/companies/{id}/evidence/{ev_id} ───────────────────────────────

@router.delete("/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evidence(company_id: str, evidence_id: str, db: Session = Depends(get_db)):
    ev = db.query(EvidenceSource).filter_by(
        id=int(evidence_id), company_id=int(company_id)
    ).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evidence not found")
    db.delete(ev)
    db.commit()
