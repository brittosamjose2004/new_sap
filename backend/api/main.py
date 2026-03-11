"""
main.py — FastAPI application entrypoint for Rubicr Caetis API.

Run:
    uvicorn backend.api.main:app --reload --port 8000
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import httpx

from backend.database.db import init_db
from backend.api.routers import auth, companies, pipeline, approvals, evidence, config
from backend.api.seed import seed_default_users

app = FastAPI(
    title="Rubicr Caetis API",
    description="Super Admin Console — Risk Intelligence Platform",
    version="1.0.0",
)

# ── CORS (allow Vite dev server + production) ─────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(pipeline.router)
app.include_router(approvals.router)
app.include_router(evidence.router)
app.include_router(config.router)


@app.on_event("startup")
async def on_startup():
    """Initialize DB tables and seed default users on first start."""
    init_db()
    seed_default_users()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Rubicr Caetis API v1.0"}


@app.get("/api/search/companies")
async def search_companies(q: str = Query(..., min_length=1), per_page: int = 20):
    """Search companies using GLEIF LEI API (free, no key required)."""
    results = []

    async with httpx.AsyncClient(timeout=15) as client:
        # Step 1: fuzzycompletions → returns up to 10 name-matched suggestions with LEI IDs
        fuzzy_task = client.get(
            "https://api.gleif.org/api/v1/fuzzycompletions",
            params={"field": "entity.legalName", "q": q},
            headers={"Accept": "application/vnd.api+json"},
        )
        # Step 2: direct lei-records search by exact/partial name (up to per_page results)
        direct_task = client.get(
            "https://api.gleif.org/api/v1/lei-records",
            params={"filter[entity.legalName]": q.upper(), "page[size]": per_page},
            headers={"Accept": "application/vnd.api+json"},
        )
        fuzzy_resp, direct_resp = await asyncio.gather(fuzzy_task, direct_task)

        seen_leis: set = set()

        # Collect LEI IDs from fuzzycompletions
        lei_ids = []
        if fuzzy_resp.status_code == 200:
            for c in fuzzy_resp.json().get("data", []):
                lei_id = c.get("relationships", {}).get("lei-records", {}).get("data", {}).get("id", "")
                if lei_id and lei_id not in lei_ids:
                    lei_ids.append(lei_id)

        # Batch-fetch all fuzzy LEI IDs in one request
        if lei_ids:
            batch_resp = await client.get(
                "https://api.gleif.org/api/v1/lei-records",
                params={"filter[lei]": ",".join(lei_ids), "page[size]": len(lei_ids)},
                headers={"Accept": "application/vnd.api+json"},
            )
            if batch_resp.status_code == 200:
                for rec in batch_resp.json().get("data", []):
                    _append_record(rec, results, seen_leis)

        # Add direct name-match results (deduped)
        if direct_resp.status_code == 200:
            for rec in direct_resp.json().get("data", []):
                _append_record(rec, results, seen_leis)

    return {"results": {"companies": results, "total_count": len(results)}}


def _append_record(rec: dict, results: list, seen_leis: set) -> None:
    """Extract fields from a GLEIF lei-record and append to results if not seen."""
    attrs = rec.get("attributes", {})
    lei = attrs.get("lei", "")
    if not lei or lei in seen_leis:
        return
    seen_leis.add(lei)
    entity = attrs.get("entity", {})
    addr = entity.get("legalAddress", {})
    results.append({
        "name": entity.get("legalName", {}).get("name", lei),
        "lei": lei,
        "address": ", ".join(filter(None, [
            ", ".join(addr.get("addressLines", [])),
            addr.get("city", ""),
            addr.get("country", ""),
        ])),
        "ticker": "",
        "region": _country_to_region(addr.get("country", "")),
        "sector": entity.get("category", "Unknown"),
        "jurisdiction": addr.get("country", ""),
        "incorporation_date": entity.get("creationDate", ""),
        "company_number": lei,
        "status": entity.get("status", ""),
    })


def _country_to_region(country: str) -> str:
    country = country.upper()
    if country in {"US", "CA", "MX"}: return "NA"
    if country in {"GB", "DE", "FR", "NL", "ES", "IT", "SE", "CH", "BE", "NO", "DK", "FI", "PL", "PT", "AT", "IE"}: return "EU"
    if country in {"IN", "CN", "JP", "AU", "SG", "HK", "KR", "MY", "TH", "ID", "NZ", "PH"}: return "APAC"
    if country in {"BR", "AR", "CL", "CO", "PE", "MX"}: return "LATAM"
    return "EMEA"
