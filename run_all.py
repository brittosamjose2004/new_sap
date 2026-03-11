#!/usr/bin/env python3
"""
run_all.py
----------
Smart interactive runner for the Impactree backend.

Modes:
  1. INTERACTIVE (default) — enter a company name, choose current year OR all years,
     then the full pipeline runs automatically. Type 'done' when finished.
  2. BATCH — process the built-in COMPANIES list (or a subset) in one go.

Usage:
    python run_all.py                             # interactive: prompted for company + years
    python run_all.py --all-years                 # interactive: always fill all years
    python run_all.py --batch                     # batch: run all built-in companies
    python run_all.py --batch --all-years         # batch: every company, every year
    python run_all.py --batch --companies TCS     # batch: specific company
    python run_all.py --year 2026                 # override latest fiscal year
    python run_all.py --num-years 5               # how many past years to fill (default 5)
    python run_all.py --skip-download             # reuse PDFs already in /tmp/

Examples:
    python run_all.py                             # interactive, prompts all options
    python run_all.py --all-years                 # interactive, fills all 5 years per company
    python run_all.py --batch --all-years         # batch all companies x all years
    python run_all.py --batch --companies "Reliance Industries" --all-years
"""

import sys
import os
import argparse
import datetime
import requests
import sqlite3
from pathlib import Path

# ── make backend importable ────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── Built-in company list (used in --batch mode) ───────────────────────────────
# "nse_symbol" is the NSE ticker used to look up the annual report PDF.
# "name"       is the name passed to the CLI scraper.

COMPANIES = [
    {"name": "Tata Consultancy Services",  "nse_symbol": "TCS"},
    {"name": "HCL Technologies",           "nse_symbol": "HCLTECH"},
    {"name": "Infosys",                    "nse_symbol": "INFY"},
    {"name": "Wipro",                      "nse_symbol": "WIPRO"},
    {"name": "Reliance Industries",        "nse_symbol": "RELIANCE"},
]

# Auto-detect fiscal year:
#   Indian FY runs April→March, so after April 1 the new FY begins.
#   e.g. running in Jan-Mar 2026 → FY 2026  |  Apr-Dec 2026 → FY 2027
_today = datetime.date.today()
FISCAL_YEAR = _today.year if _today.month >= 4 else _today.year
# Override here if you always want a specific year:
# FISCAL_YEAR = 2026

PDF_DIR = Path("/tmp")  # where downloaded PDFs are stored

# ── NSE PDF download ───────────────────────────────────────────────────────────

NSE_BASE    = "https://www.nseindia.com/api/annual-reports"
NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":   "application/json",
    "Referer":  "https://www.nseindia.com/",
}


def _download_pdf(nse_symbol: str, dest: Path) -> bool:
    """Download the most-recent annual report PDF from NSE. Returns True on success."""
    print(f"  [NSE] Fetching annual report list for {nse_symbol} …")
    try:
        resp = requests.get(
            NSE_BASE,
            params={"index": "equities", "symbol": nse_symbol},
            headers=NSE_HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  [ERROR] NSE API call failed: {exc}")
        return False

    entries = data.get("data") or []
    if not entries:
        print(f"  [ERROR] No annual report entries found for {nse_symbol}")
        return False

    pdf_url = entries[0].get("fileName") or entries[0].get("fileUrl")
    year_label = entries[0].get("toYr", "?")
    if not pdf_url:
        print(f"  [ERROR] Could not find PDF URL in NSE response for {nse_symbol}")
        return False

    print(f"  [NSE] Downloading FY{year_label} report: {pdf_url}")
    dl_headers = {**NSE_HEADERS, "Accept": "application/pdf,*/*", "Accept-Encoding": "identity"}
    try:
        r = requests.get(pdf_url, headers=dl_headers, timeout=300, stream=True)
        r.raise_for_status()
        expected = int(r.headers.get("Content-Length", 0))
        total = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
        if expected and total < expected * 0.95:
            print(f"  [WARN] Downloaded {total:,} bytes but Content-Length is {expected:,} — may be truncated")
        else:
            print(f"  [OK]   Saved {total:,} bytes → {dest}")
        return True
    except Exception as exc:
        print(f"  [ERROR] Download failed: {exc}")
        return False


# ── per-company pipeline (split into scrape + questionnaire) ──────────────────

def _scrape_company(name: str, nse_symbol: str, latest_year: int,
                    skip_download: bool) -> dict:
    """
    Step 1-3: Download PDF, verify, scrape all data into DB.
    Returns dict with keys: company_name, official_name, ticker,
                            brsr_fields, history_years, error
    """
    safe_name = nse_symbol.upper()
    pdf_path  = PDF_DIR / f"{safe_name}_annual.pdf"
    result    = {"company_name": name, "official_name": name,
                 "brsr_fields": 0, "history_years": [], "error": None}

    # ── 1. Download PDF ──────────────────────────────────────────────────────
    if skip_download and pdf_path.exists():
        print(f"  [SKIP]  Using cached PDF: {pdf_path}")
    else:
        ok = _download_pdf(nse_symbol, pdf_path)
        if not ok:
            result["error"] = "PDF download failed"
            return result

    # ── 2. Verify PDF ────────────────────────────────────────────────────────
    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        print(f"  [PDF]   {len(reader.pages)} pages verified OK")
    except Exception as exc:
        result["error"] = f"PDF unreadable: {exc}"
        print(f"  [ERROR] PDF could not be read: {exc}")
        return result

    # ── 3. Scrape ────────────────────────────────────────────────────────────
    print(f"  [SCRAPE] Starting (may take 60-120 s for large PDFs) …")
    from backend.database.db import init_db, get_session
    from backend.database.models import Company, ScrapedData
    from backend.scraper.company_scraper import CompanyScraper
    from backend.scraper.financial_scraper import FinancialScraper
    from backend.scraper.brsr_scraper import BRSRScraper

    init_db()
    db = get_session()

    scraper       = CompanyScraper(name)
    info          = scraper.get_company_info() or {}
    official_name = info.get("official_name") or name
    ticker_val    = info.get("ticker") or ""
    result["official_name"] = official_name
    result["ticker"]        = ticker_val

    company = (
        db.query(Company).filter(Company.name == official_name).first()
        or db.query(Company).filter(Company.ticker == ticker_val, ticker_val != "").first()
        or db.query(Company).filter(Company.name.ilike(f"%{name}%")).first()
    )
    if not company:
        company = Company(
            name=official_name,
            sector=info.get("sector"),
            industry=info.get("industry"),
            exchange=info.get("exchange"),
            ticker=info.get("ticker"),
            website=info.get("website"),
            headquarters=info.get("headquarters"),
            description=(info.get("description") or "")[:500],
        )
        db.add(company)
    else:
        company.name         = official_name
        company.sector       = info.get("sector")       or company.sector
        company.industry     = info.get("industry")     or company.industry
        company.exchange     = info.get("exchange")     or company.exchange
        company.ticker       = info.get("ticker")       or company.ticker
        company.website      = info.get("website")      or company.website
        company.headquarters = info.get("headquarters") or company.headquarters
    db.commit()

    def _upsert(key, value, source="yahoo", yr=latest_year):
        if value is None:
            return
        ex = db.query(ScrapedData).filter_by(
            company_id=company.id, year=yr, source=source, data_key=key).first()
        if ex:
            ex.data_value = str(value)
        else:
            db.add(ScrapedData(company_id=company.id, year=yr,
                               source=source, data_key=key, data_value=str(value)))

    for k, v in info.items():
        if v is not None:
            _upsert(k, str(v), source="yahoo")
    db.commit()

    # Historical financials (covers past 5 years automatically)
    ticker = info.get("ticker")
    history_years = []
    if ticker:
        fin     = FinancialScraper(ticker, name)
        history = fin.get_historical_financials(years=5)
        if history:
            for fy, metrics in history.items():
                for mk, mv in metrics.items():
                    if mv is not None:
                        _upsert(mk, str(mv), source="yahoo_historical", yr=fy)
            db.commit()
            history_years = sorted(history.keys())
            print(f"  [FIN]   Historical data saved for years: {history_years}")

        esg = fin.get_esg_scores()
        if esg:
            for k, v in esg.items():
                _upsert(k, v, source="yahoo_esg")
            db.commit()

    # BRSR PDF → tagged to latest_year
    brsr      = BRSRScraper(name, ticker=ticker)
    brsr_data = brsr.parse_local_pdf(str(pdf_path))
    if brsr_data:
        for k, v in brsr_data.items():
            _upsert(k, v, source="brsr_pdf", yr=latest_year)
        db.commit()
        result["brsr_fields"] = len(brsr_data)
        print(f"  [BRSR]  {len(brsr_data)} fields extracted from PDF → year {latest_year}")
    else:
        print(f"  [BRSR]  No BRSR fields extracted")

    result["history_years"] = history_years
    return result


def _fill_questionnaire(company_name: str, year: int) -> dict:
    """
    Step 4-5: Auto-fill questionnaire for one year and return answer counts.
    """
    print(f"  [QUEST] Year {year} — auto-filling 151 questions …")
    from backend.questionnaire.engine import QuestionnaireEngine
    engine = QuestionnaireEngine(company_name, year, standard="ALL")
    engine.run_auto(module_filter=None)

    conn = sqlite3.connect(str(ROOT / "data" / "impactree.db"))
    cur  = conn.cursor()
    cur.execute("""
        SELECT ans.source, COUNT(*)
        FROM answers ans
        JOIN questionnaire_sessions qs ON ans.session_id = qs.id
        JOIN companies co ON qs.company_id = co.id
        WHERE qs.year = ? AND co.name = ?
        GROUP BY ans.source
    """, (year, company_name))
    counts = dict(cur.fetchall())
    conn.close()

    total    = sum(counts.values())
    defaults = counts.get("smart_default", 0)
    real     = counts.get("scraped", 0) + counts.get("historical", 0)
    status   = "✓" if defaults == 0 else "⚠"
    src_str  = "  |  ".join(f"{s}: {n}" for s, n in sorted(counts.items()))
    print(f"  {status} Year {year}: {total} answers  ({src_str})")

    return {"year": year, "answered": total, "real": real,
            "smart_defaults": defaults, "counts": counts}


def run_company(name: str, nse_symbol: str, year: int, skip_download: bool) -> dict:
    """Full pipeline for one company, one year."""
    print()
    print("=" * 65)
    print(f"  COMPANY : {name}  ({nse_symbol})  |  Year: {year}")
    print("=" * 65)

    scrape = _scrape_company(name, nse_symbol, year, skip_download)
    if scrape["error"]:
        return {"name": name, "year": year, "error": scrape["error"],
                "answered": 0, "smart_defaults": 0, "scraped": 0}

    q = _fill_questionnaire(scrape["official_name"], year)
    return {"name": name, "year": year, "error": None,
            "answered": q["answered"], "smart_defaults": q["smart_defaults"],
            "scraped_count": q["real"], "scraped": scrape["brsr_fields"]}


def run_company_all_years(name: str, nse_symbol: str, latest_year: int,
                          num_years: int, skip_download: bool) -> list:
    """
    Scrape the company ONCE, then auto-fill the questionnaire for EACH year
    from (latest_year - num_years + 1) up to latest_year.
    Returns a list of per-year result dicts.
    """
    print()
    print("=" * 65)
    print(f"  COMPANY : {name}  ({nse_symbol})")
    print(f"  YEARS   : {latest_year - num_years + 1} → {latest_year}  ({num_years} years)")
    print("=" * 65)

    scrape = _scrape_company(name, nse_symbol, latest_year, skip_download)
    if scrape["error"]:
        return [{"name": name, "year": yr, "error": scrape["error"],
                 "answered": 0, "smart_defaults": 0, "scraped": 0}
                for yr in range(latest_year - num_years + 1, latest_year + 1)]

    official_name = scrape["official_name"]
    years_to_fill = list(range(latest_year - num_years + 1, latest_year + 1))

    print()
    print(f"  Filling questionnaire year by year: {years_to_fill}")
    print()

    results = []
    for yr in years_to_fill:
        q = _fill_questionnaire(official_name, yr)
        results.append({
            "name":           name,
            "year":           yr,
            "error":          None,
            "answered":       q["answered"],
            "smart_defaults": q["smart_defaults"],
            "scraped_count":  q["real"],
            # BRSR fields only available for latest_year
            "scraped":        scrape["brsr_fields"] if yr == latest_year else 0,
        })

    return results


# ── summary table ──────────────────────────────────────────────────────────────

def print_summary(results: list, multi_year: bool = False):
    """
    results: flat list of dicts, each with keys:
             name, year, answered, real/scraped_count, smart_defaults, scraped, error
    """
    years = sorted({r["year"] for r in results})
    title = (f"ALL YEARS  ({min(years)} → {max(years)})"
             if multi_year and len(years) > 1
             else f"Fiscal Year {years[0]}")
    print()
    print("=" * 72)
    print(f"  FINAL SUMMARY  —  {title}")
    print("=" * 72)
    if multi_year and len(years) > 1:
        hdr = f"  {'Company':<30} {'Year':>6} {'Answered':>8}  {'Real':>6}  {'Default':>7}  {'BRSR':>5}"
    else:
        hdr = f"  {'Company':<35} {'Answered':>8}  {'Real':>6}  {'Default':>7}  {'BRSR':>5}"
    print(hdr)
    print("  " + "-" * 68)
    for r in results:
        if r.get("error"):
            if multi_year and len(years) > 1:
                print(f"  ✗ {r['name']:<29} {r['year']:>6}  ERROR: {r['error']}")
            else:
                print(f"  ✗ {r['name']:<34}  ERROR: {r['error']}")
        else:
            status = "✓" if r["smart_defaults"] == 0 else "⚠"
            if multi_year and len(years) > 1:
                print(
                    f"  {status} {r['name']:<29}"
                    f" {r['year']:>6}"
                    f" {r['answered']:>8}"
                    f"  {r.get('scraped_count', 0):>6}"
                    f"  {r['smart_defaults']:>7}"
                    f"  {r['scraped']:>5}"
                )
            else:
                print(
                    f"  {status} {r['name']:<34}"
                    f" {r['answered']:>8}"
                    f"  {r.get('scraped_count', 0):>6}"
                    f"  {r['smart_defaults']:>7}"
                    f"  {r['scraped']:>5}"
                )
    print("=" * 72)


# ── NSE symbol lookup helper ───────────────────────────────────────────────────

def _guess_nse_symbol(name: str) -> str:
    """
    Try to derive an NSE symbol from a company name by checking the NSE API.
    Returns the guessed symbol, or the uppercased first word as a fallback.
    """
    # Common known mappings to help users
    KNOWN = {
        "tcs": "TCS", "tata consultancy": "TCS",
        "hcl": "HCLTECH", "hcl tech": "HCLTECH",
        "infosys": "INFY",
        "wipro": "WIPRO",
        "reliance": "RELIANCE", "reliance industries": "RELIANCE",
        "hdfc bank": "HDFCBANK", "hdfc": "HDFCBANK",
        "icici": "ICICIBANK", "icici bank": "ICICIBANK",
        "sbi": "SBIN", "state bank": "SBIN",
        "ongc": "ONGC",
        "itc": "ITC",
        "bajaj": "BAJFINANCE",
        "maruti": "MARUTI",
        "tata motors": "TATAMOTORS",
        "tata steel": "TATASTEEL",
        "sun pharma": "SUNPHARMA",
        "asian paints": "ASIANPAINT",
        "kotak": "KOTAKBANK",
        "larsen": "LT", "l&t": "LT",
        "ultratech": "ULTRACEMCO",
        "titan": "TITAN",
        "nestlé": "NESTLEIND", "nestle": "NESTLEIND",
        "power grid": "POWERGRID",
        "ntpc": "NTPC",
        "tech mahindra": "TECHM",
        "m&m": "M&M", "mahindra": "M&M",
        "axis bank": "AXISBANK",
        "bharti airtel": "BHARTIARTL", "airtel": "BHARTIARTL",
        "adani": "ADANIENT",
        "jio": "JIOFIN",
    }
    key = name.strip().lower()
    for k, v in KNOWN.items():
        if k in key:
            return v
    # Fallback: first word of name uppercased
    return name.strip().split()[0].upper()


# ── interactive mode ───────────────────────────────────────────────────────────

def run_interactive(latest_year: int, num_years: int,
                    force_all_years: bool, skip_download: bool):
    """Prompt the user to enter companies one by one, process each immediately."""
    from backend.database.db import init_db
    init_db()

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║       IMPACTREE  —  Smart Interactive Runner                 ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  Enter a company name to process it automatically.           ║")
    print("║  Type  'list'  to see built-in companies.                    ║")
    print("║  Type  'done'  (or Ctrl+C) to finish and see summary.        ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    years_range = f"{latest_year - num_years + 1}–{latest_year}"
    print(f"  Latest year : {latest_year}  |  Years to fill: {years_range}  |  PDF dir: {PDF_DIR}")
    print()

    all_results   = []   # flat list of per-year dicts
    multi_year    = False

    while True:
        try:
            raw = input("  Enter company name (or 'done'/'list'): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue
        if raw.lower() == "done":
            break
        if raw.lower() == "list":
            print()
            print("  Built-in companies:")
            for i, c in enumerate(COMPANIES, 1):
                print(f"    {i}. {c['name']}  ({c['nse_symbol']})")
            print()
            continue

        # Pick from built-in list by number
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(COMPANIES):
                comp       = COMPANIES[idx]
                name       = comp["name"]
                nse_symbol = comp["nse_symbol"]
                print(f"  → Selected: {name}  ({nse_symbol})")
            else:
                print(f"  [ERROR] Number out of range. Type 'list' to see options.")
                continue
        else:
            name      = raw
            suggested = _guess_nse_symbol(name)
            try:
                sym_raw = input(f"  NSE symbol for '{name}' [{suggested}]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            nse_symbol = sym_raw.upper() if sym_raw else suggested

        # Ask: current year only OR all years?
        do_all_years = force_all_years
        if not force_all_years:
            try:
                ay = input(
                    f"  Fill all years ({years_range})? [Y/n]: "
                ).strip().lower()
                do_all_years = ay not in ("n", "no")
            except (EOFError, KeyboardInterrupt):
                print()
                break

        # Confirm
        yr_display = years_range if do_all_years else str(latest_year)
        print(f"  ┌─────────────────────────────────────────────────┐")
        print(f"  │  Company   : {name:<36}│")
        print(f"  │  NSE Symbol: {nse_symbol:<36}│")
        print(f"  │  Years     : {yr_display:<36}│")
        print(f"  └─────────────────────────────────────────────────┘")
        try:
            confirm = input("  Proceed? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if confirm in ("n", "no"):
            print("  Skipped.")
            continue

        if do_all_years:
            multi_year = True
            rs = run_company_all_years(
                name=name, nse_symbol=nse_symbol,
                latest_year=latest_year, num_years=num_years,
                skip_download=skip_download,
            )
            all_results.extend(rs)
        else:
            r = run_company(name=name, nse_symbol=nse_symbol,
                            year=latest_year, skip_download=skip_download)
            all_results.append(r)

        print()
        print(f"  ✓ '{name}' processed. Add another company or type 'done'.")
        print()

    if all_results:
        print_summary(all_results, multi_year=multi_year)
    else:
        print("  No companies were processed.")


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Impactree Smart Runner.\n"
            "Default: interactive — enter a company name, choose years, pipeline runs automatically.\n"
            "Use --batch to process the built-in COMPANIES list non-interactively."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--batch", action="store_true",
        help="Batch mode: process all built-in companies (non-interactive)"
    )
    parser.add_argument(
        "--all-years", action="store_true",
        help="Fill questionnaire for every available year, not just the latest"
    )
    parser.add_argument(
        "--num-years", type=int, default=5,
        help="How many past years to fill when --all-years is used (default: 5)"
    )
    parser.add_argument(
        "--companies", nargs="*", metavar="NAME",
        help="(Batch mode) Names or NSE symbols to process. "
             'E.g. --companies TCS Wipro "Reliance Industries"'
    )
    parser.add_argument(
        "--year", type=int, default=FISCAL_YEAR,
        help=f"Latest fiscal year (default: {FISCAL_YEAR})"
    )
    parser.add_argument(
        "--skip-download", action="store_true",
        help="Skip PDF download if PDF already exists in /tmp/"
    )
    args = parser.parse_args()

    # ── INTERACTIVE MODE (default) ─────────────────────────────────────────
    if not args.batch:
        run_interactive(
            latest_year=args.year,
            num_years=args.num_years,
            force_all_years=args.all_years,
            skip_download=args.skip_download,
        )
        return

    # ── BATCH MODE ─────────────────────────────────────────────────────────
    companies_to_run = COMPANIES
    if args.companies:
        filters = [c.upper() for c in args.companies]
        companies_to_run = [
            c for c in COMPANIES
            if c["nse_symbol"].upper() in filters
            or any(f in c["name"].upper() for f in filters)
        ]
        if not companies_to_run:
            print(f"[ERROR] No matching companies found for: {args.companies}")
            print(f"Available: {[c['name'] for c in COMPANIES]}")
            sys.exit(1)

    years_range = f"{args.year - args.num_years + 1}–{args.year}"
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║          IMPACTREE  —  Batch Pipeline Runner                 ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  Companies : {len(companies_to_run)}")
    print(f"  Years     : {years_range if args.all_years else str(args.year)}")
    print(f"  PDF dir   : {PDF_DIR}")
    print(f"  DB        : {ROOT / 'data' / 'impactree.db'}")

    from backend.database.db import init_db
    init_db()

    all_results = []
    for comp in companies_to_run:
        if args.all_years:
            rs = run_company_all_years(
                name=comp["name"],
                nse_symbol=comp["nse_symbol"],
                latest_year=args.year,
                num_years=args.num_years,
                skip_download=args.skip_download,
            )
            all_results.extend(rs)
        else:
            r = run_company(
                name=comp["name"],
                nse_symbol=comp["nse_symbol"],
                year=args.year,
                skip_download=args.skip_download,
            )
            all_results.append(r)

    print_summary(all_results, multi_year=args.all_years)


if __name__ == "__main__":
    main()
