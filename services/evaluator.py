"""
Rule-based Banking & Finance CV Evaluation Engine.

Evaluates a CV locally against the nine predefined categories (totaling 100 points)
using deterministic Python rules and evidence from PyMuPDF and structured CV extraction.
Never uses external AI APIs, never invents candidate qualifications, and never
automatically assigns 0 simply because an optional item is not mentioned.
"""

from collections import Counter
from dataclasses import asdict, dataclass
import re
from typing import Any

from config.settings import EVALUATION_CATEGORIES, EvaluationCategory
from services.cv_extractor import ExtractedCVData, ExtractedField, extract_cv_information
from services.language_checker import LanguageQualityReport, analyze_language_quality
from services.pdf_processor import ProcessedPDFDocument, TextLineInfo


# Allowed factor evaluation statuses
STATUS_EVALUATED = "Evaluated"
STATUS_NOT_MENTIONED = "Not mentioned in CV"
STATUS_CANNOT_ASSESS = "Cannot be assessed"
STATUS_NOT_APPLICABLE = "Not applicable"


@dataclass(frozen=True)
class FactorEvaluation:
    """Detailed 0-5 evaluation for a single factor within a category."""

    factor_name: str
    score: int | None  # 0..5 when status == "Evaluated", else None
    max_score: int
    status: str  # Evaluated | Not mentioned in CV | Cannot be assessed | Not applicable
    evidence: tuple[str, ...]
    explanation: str
    weakness: str | None = None
    source_pages: tuple[int, ...] = ()


@dataclass(frozen=True)
class CategoryEvaluation:
    """Weighted evaluation result for one of the nine predefined categories."""

    category: EvaluationCategory
    category_score: float
    max_weight: int
    average_factor_score: float | None
    assessed_factor_count: int
    applicable_factor_count: int
    coverage_pct: float
    status: str  # Evaluated | Partial Coverage | Unavailable
    coverage_note: str
    factors: tuple[FactorEvaluation, ...]


@dataclass(frozen=True)
class CVEvaluationResult:
    """Complete structured evaluation output across all 9 categories (out of 100)."""

    filename: str
    is_assessable: bool
    overall_score: float
    total_possible_score: int
    candidate_capability_score: float
    candidate_capability_max: int
    document_presentation_score: float
    document_presentation_max: int
    overall_assessed_factors: int
    overall_applicable_factors: int
    overall_coverage_pct: float
    coverage_warning: str | None
    summary_message: str
    categories: tuple[CategoryEvaluation, ...]
    identified_weaknesses: tuple[str, ...]
    missing_information: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize evaluation output to a JSON-compatible dictionary."""
        return asdict(self)


def _clamp_score(value: int) -> int:
    """Ensure every factor score stays strictly within 0..5."""
    return max(0, min(5, int(value)))


def _not_mentioned_factor(
    factor_name: str,
    reason: str | None = None,
) -> FactorEvaluation:
    """Create a standardized 'Not mentioned in CV' factor without assigning 0."""
    return FactorEvaluation(
        factor_name=factor_name,
        score=None,
        max_score=5,
        status=STATUS_NOT_MENTIONED,
        evidence=(),
        explanation=reason or f"{factor_name} is not mentioned in the uploaded CV.",
        weakness=None,
        source_pages=(),
    )


def _cannot_assess_factor(
    factor_name: str,
    reason: str,
    evidence: tuple[str, ...] = (),
    source_pages: tuple[int, ...] = (),
) -> FactorEvaluation:
    """Create a standardized 'Cannot be assessed' factor."""
    return FactorEvaluation(
        factor_name=factor_name,
        score=None,
        max_score=5,
        status=STATUS_CANNOT_ASSESS,
        evidence=evidence,
        explanation=reason,
        weakness=None,
        source_pages=source_pages,
    )


def _evaluated_factor(
    factor_name: str,
    score: int,
    evidence: tuple[str, ...],
    explanation: str,
    weakness: str | None = None,
    source_pages: tuple[int, ...] = (),
) -> FactorEvaluation:
    """Create a validated 'Evaluated' factor with score clamped to 0..5."""
    return FactorEvaluation(
        factor_name=factor_name,
        score=_clamp_score(score),
        max_score=5,
        status=STATUS_EVALUATED,
        evidence=evidence,
        explanation=explanation,
        weakness=weakness,
        source_pages=source_pages,
    )


def _score_single_grade_token(grade_text: str) -> tuple[int, str]:
    """Map an explicit exam grade (A/B/C/S/F or IELTS band) into a 0..5 score."""
    upper = grade_text.upper()
    ielts_m = re.search(r"IELTS\s*[:\-–—]?\s*(\d(?:\.\d)?)", upper)
    if ielts_m:
        band = float(ielts_m.group(1))
        if band >= 7.0:
            return 5, f"Strong IELTS band ({band})."
        if band >= 6.0:
            return 4, f"Good IELTS band ({band})."
        if band >= 5.5:
            return 3, f"Acceptable IELTS band ({band})."
        return 2, f"Below-target IELTS band ({band})."

    if re.search(r"(?:[:\-–—]\s*A[+*]?|\bDISTINCTION\b)", upper):
        return 5, "Distinction / 'A' grade recorded."
    if re.search(r"(?:[:\-–—]\s*B\b|\bCREDIT\b)", upper):
        return 4, "Credit / 'B' grade recorded."
    if re.search(r"(?:[:\-–—]\s*C\b|\bPASS\b)", upper):
        return 3, "Acceptable 'C' / Pass grade recorded."
    if re.search(r"[:\-–—]\s*S\b", upper):
        return 2, "Ordinary 'S' pass recorded."
    if re.search(r"[:\-–—]\s*[FW]\b", upper):
        return 1, "Weak / Fail grade recorded."
    return 3, "Examination result recorded."


def _evaluate_category_1_education(extracted_cv: ExtractedCVData) -> tuple[FactorEvaluation, ...]:
    """CATEGORY 1: EDUCATIONAL QUALIFICATIONS (Weight 20)."""
    edu = extracted_cv.educational_qualifications
    factors: list[FactorEvaluation] = []

    # 1. O/L Results
    ol = edu.gce_ol_results
    if ol.status == "not_found":
        factors.append(_not_mentioned_factor("O/L Results"))
    elif ol.status == "partial":
        vals = tuple(str(v) for v in (ol.value or []))
        factors.append(
            _evaluated_factor(
                "O/L Results",
                2,
                vals,
                "G.C.E. O/L is mentioned, but individual subject grades or pass summary are missing.",
                "Specify G.C.E. O/L subject grades (especially Mathematics and English).",
                ol.source_pages,
            )
        )
    else:
        joined = " ".join(str(v) for v in (ol.value or []))
        a_count_m = re.search(r"\b(\d+)\s*A(?:'s|s)?\b", joined, re.IGNORECASE)
        explicit_a = len(re.findall(r"[:\-–—]\s*A\b", joined))
        a_total = int(a_count_m.group(1)) if a_count_m else explicit_a
        if a_total >= 7:
            sc, exp, wk = 5, f"Strong G.C.E. O/L performance ({a_total} A grade(s) documented).", None
        elif a_total >= 4:
            sc, exp, wk = 4, f"Good G.C.E. O/L performance ({a_total} A grade(s) documented).", None
        elif re.search(r"\b(?:pass|credit|distinction|[BCS])\b", joined, re.IGNORECASE):
            sc, exp, wk = 3, "Acceptable G.C.E. O/L results documented.", None
        else:
            sc, exp, wk = 2, "G.C.E. O/L entry lacks clear grade strength.", "Clarify complete O/L pass counts and grades."
        factors.append(_evaluated_factor("O/L Results", sc, tuple(str(v) for v in ol.value), exp, wk, ol.source_pages))

    # 2. A/L Results
    al = edu.gce_al_results
    if al.status == "not_found":
        factors.append(_not_mentioned_factor("A/L Results"))
    elif al.status == "partial":
        vals = tuple(str(v) for v in (al.value or []))
        factors.append(
            _evaluated_factor(
                "A/L Results",
                2,
                vals,
                "G.C.E. A/L is mentioned, but subject grades were not clearly provided.",
                "Include A/L stream, subject grades, and Z-score if applicable.",
                al.source_pages,
            )
        )
    else:
        joined = " ".join(str(v) for v in (al.value or []))
        a_count_m = re.search(r"\b(\d+)\s*A(?:'s|s)?\b", joined, re.IGNORECASE)
        b_count_m = re.search(r"\b(\d+)\s*B(?:'s|s)?\b", joined, re.IGNORECASE)
        explicit_a = len(re.findall(r"[:\-–—]\s*A\b", joined))
        explicit_b = len(re.findall(r"[:\-–—]\s*B\b", joined))
        explicit_c = len(re.findall(r"[:\-–—]\s*C\b", joined))
        explicit_s = len(re.findall(r"[:\-–—]\s*S\b", joined))
        a_cnt = int(a_count_m.group(1)) if a_count_m else explicit_a
        b_cnt = int(b_count_m.group(1)) if b_count_m else explicit_b
        if a_cnt >= 3 or (a_cnt >= 2 and b_cnt >= 1):
            sc, exp, wk = 5, "Excellent G.C.E. A/L results with multiple distinction ('A') grades.", None
        elif a_cnt >= 1 or b_cnt >= 2:
            sc, exp, wk = 4, "Good G.C.E. A/L results documented.", None
        elif (explicit_c + explicit_s) >= 2 or re.search(r"\b(?:3\s*passes|commerce|mathematics)\b", joined, re.IGNORECASE):
            sc, exp, wk = 3, "Acceptable G.C.E. A/L results documented.", None
        else:
            sc, exp, wk = 2, "Below-average or incomplete A/L pass evidence.", "Provide full A/L subject grades."
        factors.append(_evaluated_factor("A/L Results", sc, tuple(str(v) for v in al.value), exp, wk, al.source_pages))

    # 3. English Results
    eng = edu.english_results
    if eng.status == "not_found":
        factors.append(_not_mentioned_factor("English Results"))
    else:
        vals = tuple(str(v) for v in (eng.value or []))
        best_sc = max(_score_single_grade_token(v)[0] for v in vals)
        best_exp = max((_score_single_grade_token(v) for v in vals), key=lambda x: x[0])[1]
        wk = "Strengthen English certification or clarify grade." if best_sc <= 2 else None
        factors.append(_evaluated_factor("English Results", best_sc, vals, best_exp, wk, eng.source_pages))

    # 4. Mathematics Results
    math = edu.mathematics_results
    if math.status == "not_found":
        factors.append(_not_mentioned_factor("Mathematics Results"))
    else:
        vals = tuple(str(v) for v in (math.value or []))
        best_sc = max(_score_single_grade_token(v)[0] for v in vals)
        best_exp = max((_score_single_grade_token(v) for v in vals), key=lambda x: x[0])[1]
        wk = "Mathematics grade is below typical banking entry benchmarks." if best_sc <= 2 else None
        factors.append(_evaluated_factor("Mathematics Results", best_sc, vals, best_exp, wk, math.source_pages))

    # 5. Degrees and Diplomas (never auto-penalize missing degree; never treat diploma as degree)
    deg = edu.degrees
    dip = edu.diplomas
    if deg.status == "not_found" and dip.status == "not_found":
        factors.append(_not_mentioned_factor("Degrees and Diplomas", "No university degree or academic diploma is mentioned in the CV."))
    elif deg.status != "not_found":
        deg_vals = tuple(str(v) for v in (deg.value or []))
        joined = " ".join(deg_vals)
        is_finance_rel = bool(re.search(r"\b(?:finance|banking|accounting|economics|commerce|business|management|financial|actuarial|statistics)\b", joined, re.IGNORECASE))
        is_ongoing = bool(re.search(r"\b(?:reading|undergraduate|pursuing|expected|ongoing)\b", joined, re.IGNORECASE))
        gpa_m = re.search(r"\b(\d\.\d{1,2})\s*(?:/\s*4(?:\.00?)?)?", joined)
        gpa_val = float(gpa_m.group(1)) if gpa_m and float(gpa_m.group(1)) <= 4.0 else None

        if is_finance_rel and (re.search(r"\bfirst\s+class\b", joined, re.IGNORECASE) or (gpa_val is not None and gpa_val >= 3.5)):
            sc = 5
            exp = "Relevant banking/finance/business degree with strong academic standing (First Class or GPA >= 3.5)."
            wk = None
        elif is_finance_rel and (re.search(r"\bsecond\s+upper\b", joined, re.IGNORECASE) or (gpa_val is not None and gpa_val >= 3.0)):
            sc = 4
            exp = "Relevant finance/business degree with good standing (Second Upper or GPA >= 3.0)."
            wk = None
        elif is_finance_rel and not is_ongoing:
            sc = 4
            exp = "Completed banking/finance/business degree documented."
            wk = "Include GPA or degree classification if available." if not gpa_val else None
        elif is_ongoing:
            sc = 3
            exp = "Undergraduate degree currently in progress."
            wk = "State expected graduation year and current GPA if available." if not gpa_val else None
        else:
            sc = 3
            exp = "University degree documented outside core finance/accounting subjects."
            wk = None
        factors.append(_evaluated_factor("Degrees and Diplomas", sc, deg_vals, exp, wk, deg.source_pages))
    else:
        # Diploma only — explicitly NOT treated as equivalent to a degree
        dip_vals = tuple(str(v) for v in (dip.value or []))
        joined = " ".join(dip_vals)
        is_finance_rel = bool(re.search(r"\b(?:finance|banking|accounting|business|commerce|management)\b", joined, re.IGNORECASE))
        sc = 3 if is_finance_rel else 2
        exp = (
            "Relevant business/finance diploma documented (evaluated distinctly as a diploma, not equivalent to a Bachelor's degree)."
            if is_finance_rel
            else "Non-finance diploma documented (evaluated as a diploma, not equivalent to a degree)."
        )
        factors.append(_evaluated_factor("Degrees and Diplomas", sc, dip_vals, exp, None, dip.source_pages))

    # 6. Banking and Finance Qualifications
    bfq = edu.banking_finance_qualifications
    if bfq.status == "not_found":
        factors.append(_not_mentioned_factor("Banking and Finance Qualifications"))
    else:
        vals = tuple(str(v) for v in (bfq.value or []))
        joined = " ".join(vals)
        if re.search(r"\b(?:dabf|dbf|iabf|diploma\s+in\s+(?:applied\s+)?banking|fmva)\b", joined, re.IGNORECASE):
            sc, exp = 5, "Recognized banking/finance diploma or specialist credential (e.g., DABF/IABF/FMVA) documented."
        elif re.search(r"\b(?:cbf|ibsl|bmc|bloomberg\s+market\s+concepts|certificate\s+in\s+banking)\b", joined, re.IGNORECASE):
            sc, exp = 4, "Relevant entry-level banking/finance qualification (e.g., IBSL/CBF/BMC) documented."
        else:
            sc, exp = 3, "Banking or finance-related qualification documented."
        factors.append(_evaluated_factor("Banking and Finance Qualifications", sc, vals, exp, None, bfq.source_pages))

    # 7. Professional Qualifications (AAT, CIMA, ACCA, CA, CFA, etc.)
    prof = edu.professional_qualifications
    if prof.status == "not_found":
        factors.append(_not_mentioned_factor("Professional Qualifications"))
    else:
        vals = tuple(str(v) for v in (prof.value or []))
        joined = " ".join(vals)
        if re.search(r"\b(?:finalist|affiliate|member|acma|cgma|aca|passed\s+final|cfa\s+level\s*(?:ii|iii|2|3))\b", joined, re.IGNORECASE):
            sc, exp, wk = 5, "Advanced professional accounting/finance standing documented.", None
        elif re.search(r"\b(?:strategic|managerial|management\s+level|applied\s+skills|cfa\s+level\s*(?:i|1)\s+passed|aat\s+(?:passed|final))\b", joined, re.IGNORECASE):
            sc, exp, wk = 4, "Mid-to-advanced professional qualification progress documented.", None
        elif re.search(r"\b(?:operational|foundation|knowledge|certificate|level\s*(?:1|i)|candidate|part|reading|following|passed)\b", joined, re.IGNORECASE):
            sc, exp, wk = 3, "Entry/operational stage professional qualification progress documented.", None
        else:
            sc, exp, wk = 2, "Professional body mentioned without clarifying completed stage or level.", "Specify exact level/papers completed (e.g., CIMA Operational Level, AAT Stage II)."
        factors.append(_evaluated_factor("Professional Qualifications", sc, vals, exp, wk, prof.source_pages))

    return tuple(factors)


def _evaluate_category_2_experience(
    extracted_cv: ExtractedCVData,
    lines: tuple[TextLineInfo, ...],
) -> tuple[FactorEvaluation, ...]:
    """CATEGORY 2: PROFESSIONAL EXPERIENCE (Weight 15)."""
    exp_info = extracted_cv.professional_experience
    entries = exp_info.experience_entries.value if isinstance(exp_info.experience_entries.value, list) else []

    if not entries and exp_info.experience_entries.status == "not_found":
        # Entire category is unmentioned — do not assign 0s
        factor_names = (
            "Banking Experience",
            "Finance Company Experience",
            "Internships",
            "Customer Service Experience",
            "Cash Handling Experience",
            "Administrative Experience",
            "Sales Experience",
            "Employment Duration",
            "Relevance of Responsibilities",
        )
        return tuple(
            _not_mentioned_factor(name, "No work experience or internship section was found in the CV.")
            for name in factor_names
        )

    # Aggregate role text strictly from documented experience entries
    def entry_text(e: dict[str, Any]) -> str:
        resps = " ".join(str(r) for r in e.get("responsibilities", []))
        return f"{e.get('job_title') or ''} {e.get('company_name') or ''} {resps}".strip()

    all_exp_blocks = [(e, entry_text(e)) for e in entries]
    exp_pages = exp_info.experience_entries.source_pages

    def match_exp_domain(pattern: str) -> list[tuple[dict[str, Any], str]]:
        rx = re.compile(pattern, re.IGNORECASE)
        return [(e, txt) for e, txt in all_exp_blocks if rx.search(txt)]

    factors: list[FactorEvaluation] = []

    # 1. Banking Experience
    bank_hits = match_exp_domain(r"\b(?:bank|banking\s+intern|teller|commercial\s+bank|sampath|hsbc|hnb|hatton\s+national|seylan|ndb|dfcc|boc|bank\s+of\s+ceylon|people'?s\s+bank|nations\s+trust)\b")
    if bank_hits:
        months = sum(e["duration_months"] for e, _ in bank_hits if isinstance(e.get("duration_months"), int))
        has_duties = any(len(e.get("responsibilities", [])) >= 1 for e, _ in bank_hits)
        sc = 5 if (months >= 6 and has_duties) else (4 if has_duties else 3)
        ev = tuple(f"{e.get('job_title') or 'Role'} at {e.get('company_name') or 'Bank'}" for e, _ in bank_hits)
        factors.append(_evaluated_factor("Banking Experience", sc, ev, "Direct banking sector experience documented.", None, exp_pages))
    else:
        factors.append(_not_mentioned_factor("Banking Experience"))

    # 2. Finance Company Experience
    fin_hits = match_exp_domain(r"\b(?:kpmg|pwc|ey|deloitte|bdo|audit|leasing|insurance|microfinance|capital|securities|brokerage|finance\s+(?:company|intern|trainee|executive)|accounts?\s+(?:trainee|assistant|executive))\b")
    if fin_hits:
        months = sum(e["duration_months"] for e, _ in fin_hits if isinstance(e.get("duration_months"), int))
        has_duties = any(len(e.get("responsibilities", [])) >= 1 for e, _ in fin_hits)
        sc = 5 if (months >= 6 and has_duties) else (4 if has_duties else 3)
        ev = tuple(f"{e.get('job_title') or 'Role'} at {e.get('company_name') or 'Organization'}" for e, _ in fin_hits)
        factors.append(_evaluated_factor("Finance Company Experience", sc, ev, "Financial services, audit, or accounting firm experience documented.", None, exp_pages))
    else:
        factors.append(_not_mentioned_factor("Finance Company Experience"))

    # 3. Internships
    interns = exp_info.internship_details.value if isinstance(exp_info.internship_details.value, list) else []
    if interns:
        banking_intern = any(re.search(r"\b(?:bank|finance|audit|credit|accounting|treasury)\b", entry_text(e), re.IGNORECASE) for e in interns)
        has_duties = any(len(e.get("responsibilities", [])) >= 1 for e in interns)
        sc = 5 if (banking_intern and has_duties) else (4 if has_duties else 3)
        ev = tuple(f"{e.get('job_title') or 'Intern'} at {e.get('company_name') or 'Organization'}" for e in interns)
        wk = "Add specific bulleted duties for the internship role." if not has_duties else None
        factors.append(_evaluated_factor("Internships", sc, ev, "Relevant entry-level internship or trainee experience documented.", wk, exp_info.internship_details.source_pages))
    else:
        factors.append(_not_mentioned_factor("Internships"))

    # 4. Customer Service Experience
    cust_hits = match_exp_domain(r"\b(?:customer|client|front\s+office|front\s+desk|call\s+cent(?:er|re)|inquiries|onboarding)\b")
    if cust_hits:
        quant_or_bank = any(re.search(r"(?:\d+|bank|onboarding|kyc|branch)", txt, re.IGNORECASE) for _, txt in cust_hits)
        sc = 4 if quant_or_bank else 3
        ev = tuple(r for e, _ in cust_hits for r in e.get("responsibilities", []) if re.search(r"customer|client|inquir|front", r, re.IGNORECASE))[:3] or tuple(entry_text(e)[:100] for e, _ in cust_hits[:2])
        factors.append(_evaluated_factor("Customer Service Experience", sc, ev, "Transferable customer-facing service experience documented.", None, exp_pages))
    else:
        factors.append(_not_mentioned_factor("Customer Service Experience"))

    # 5. Cash Handling Experience
    cash_hits = match_exp_domain(r"\b(?:cash|teller|cashier|petty\s+cash|till|vault|cheque|cash\s+reconciliation)\b")
    if cash_hits:
        reconcile = any(re.search(r"\b(?:reconcil|audit|teller|vault|control)\b", txt, re.IGNORECASE) for _, txt in cash_hits)
        sc = 4 if reconcile else 3
        ev = tuple(entry_text(e)[:120] for e, _ in cash_hits[:2])
        factors.append(_evaluated_factor("Cash Handling Experience", sc, ev, "Cash or payment-handling responsibilities documented.", None, exp_pages))
    else:
        factors.append(_not_mentioned_factor("Cash Handling Experience"))

    # 6. Administrative Experience
    admin_hits = match_exp_domain(r"\b(?:admin(?:istrative)?|filing|documentation|data\s+entry|clerical|clerk|record\s+keeping|scheduling|correspondence)\b")
    if admin_hits:
        sc = 4 if any(re.search(r"\b(?:documentation|compliance|loan|audit|record)\b", txt, re.IGNORECASE) for _, txt in admin_hits) else 3
        ev = tuple(entry_text(e)[:120] for e, _ in admin_hits[:2])
        factors.append(_evaluated_factor("Administrative Experience", sc, ev, "Administrative and office documentation experience documented.", None, exp_pages))
    else:
        factors.append(_not_mentioned_factor("Administrative Experience"))

    # 7. Sales Experience
    sales_hits = match_exp_domain(r"\b(?:sales|selling|cross[- ]sell|business\s+development|lead\s+generation|targets?|merchandising|account\s+acquisition)\b")
    if sales_hits:
        with_targets = any(re.search(r"\b(?:target|%|revenue|quota|exceeded)\b", txt, re.IGNORECASE) for _, txt in sales_hits)
        sc = 4 if with_targets else 3
        ev = tuple(entry_text(e)[:120] for e, _ in sales_hits[:2])
        factors.append(_evaluated_factor("Sales Experience", sc, ev, "Transferable sales or business development experience documented.", None, exp_pages))
    else:
        factors.append(_not_mentioned_factor("Sales Experience"))

    # 8. Employment Duration
    dur_field = exp_info.total_calculable_duration
    calculable_months = [e["duration_months"] for e in entries if isinstance(e.get("duration_months"), int)]
    if not calculable_months:
        factors.append(
            _cannot_assess_factor(
                "Employment Duration",
                dur_field.uncertainty or "Employment dates lack month-level precision, so duration cannot be calculated.",
                tuple(str(e.get("employment_dates") or "No dates") for e in entries),
                exp_pages,
            )
        )
    else:
        total_m = sum(calculable_months)
        if total_m >= 24:
            sc, wk = 5, None
        elif total_m >= 12:
            sc, wk = 4, None
        elif total_m >= 6:
            sc, wk = 3, None
        elif total_m >= 3:
            sc, wk = 2, "Total documented experience duration is relatively brief (under 6 months)."
        else:
            sc, wk = 1, "Very short documented employment duration (under 3 months)."
        factors.append(
            _evaluated_factor(
                "Employment Duration",
                sc,
                (str(dur_field.value),),
                f"Calculated {total_m} month(s) across roles with month-level dates.",
                wk,
                exp_pages,
            )
        )

    # 9. Relevance of Responsibilities (always assessed when experience entries exist)
    all_resps = [r for e in entries for r in e.get("responsibilities", [])]
    if not all_resps:
        factors.append(
            _evaluated_factor(
                "Relevance of Responsibilities",
                1,
                tuple(f"{e.get('job_title') or 'Role'} at {e.get('company_name') or 'Company'}" for e in entries),
                "Role titles are listed, but no specific responsibilities were documented.",
                "Add 3-5 bullet points per role describing concrete banking, finance, analytical, or client duties.",
                exp_pages,
            )
        )
    else:
        joined_resps = " ".join(all_resps)
        direct_bf = len(re.findall(r"\b(?:kyc|aml|credit|loan|deposit|account\s+opening|reconcil|financial\s+statement|audit|ifrs|teller|treasury|compliance)\b", joined_resps, re.IGNORECASE))
        transferable = len(re.findall(r"\b(?:customer|client|excel|report|data|sales|cash|administration|documentation)\b", joined_resps, re.IGNORECASE))
        if direct_bf >= 3:
            sc, exp, wk = 5, "Documented responsibilities align directly with entry-level banking and finance workflows.", None
        elif direct_bf >= 1:
            sc, exp, wk = 4, "Documented responsibilities include direct banking, finance, or audit duties.", None
        elif transferable >= 2:
            sc, exp, wk = 3, "Documented responsibilities demonstrate transferable client, analytical, or administrative skills.", "Highlight quantitative, financial, or client-impact details where truthful."
        else:
            sc, exp, wk = 2, "Documented responsibilities have limited direct relevance to banking and finance.", "Emphasize transferable accuracy, client handling, and numerical tasks."
        factors.append(_evaluated_factor("Relevance of Responsibilities", sc, tuple(all_resps[:3]), exp, wk, exp_pages))

    return tuple(factors)


def _evaluate_category_3_technical_skills(
    extracted_cv: ExtractedCVData,
    lines: tuple[TextLineInfo, ...],
) -> tuple[FactorEvaluation, ...]:
    """CATEGORY 3: TECHNICAL AND COMPUTER SKILLS (Weight 10)."""
    ts = extracted_cv.technical_skills
    factors: list[FactorEvaluation] = []

    # 1. Microsoft Excel (never assume advanced from bare word 'Excel')
    excel = ts.microsoft_excel
    if excel.status == "not_found":
        factors.append(_not_mentioned_factor("Microsoft Excel"))
    else:
        ev_lines = tuple(excel.value.get("evidence_lines", []))
        joined = " ".join(ev_lines)
        if re.search(r"\b(?:vba|macros?|power\s+query|financial\s+model|advanced\s+excel|automated\s+dashboard)\b", joined, re.IGNORECASE):
            sc, exp, wk = 5, "Advanced Microsoft Excel capabilities (e.g., macros/VBA/modeling) are explicitly supported.", None
        elif re.search(r"\b(?:pivot\s+tables?|vlookup|xlookup|hlookup|index|match|formulas?|intermediate)\b", joined, re.IGNORECASE):
            sc, exp, wk = 4, "Intermediate Microsoft Excel functions (e.g., Pivot Tables, VLOOKUP) are documented.", None
        elif re.search(r"\bbasic\b", joined, re.IGNORECASE):
            sc, exp, wk = 2, "Basic Microsoft Excel familiarity stated.", "Develop intermediate Excel skills (Pivot Tables, VLOOKUP) and document applied usage."
        else:
            sc, exp, wk = 3, "Microsoft Excel is mentioned without specifying proficiency level or functions (advanced skill is not assumed).", "Specify Excel proficiency or functions used (e.g., Pivot Tables, VLOOKUP, financial schedules)."
        factors.append(_evaluated_factor("Microsoft Excel", sc, ev_lines, exp, wk, excel.source_pages))

    # 2. Microsoft Word
    word = ts.microsoft_word
    if word.status == "not_found":
        factors.append(_not_mentioned_factor("Microsoft Word"))
    else:
        ev_lines = tuple(word.value.get("evidence_lines", []))
        joined = " ".join(ev_lines)
        sc = 4 if re.search(r"\b(?:advanced|proficient|reports?|formatting|mail\s+merge)\b", joined, re.IGNORECASE) else 3
        factors.append(_evaluated_factor("Microsoft Word", sc, ev_lines, "Microsoft Word proficiency documented.", None, word.source_pages))

    # 3. Microsoft PowerPoint
    ppt = ts.microsoft_powerpoint
    if ppt.status == "not_found":
        factors.append(_not_mentioned_factor("Microsoft PowerPoint"))
    else:
        ev_lines = tuple(ppt.value.get("evidence_lines", []))
        joined = " ".join(ev_lines)
        sc = 4 if re.search(r"\b(?:advanced|proficient|presentation|deck|slides)\b", joined, re.IGNORECASE) else 3
        factors.append(_evaluated_factor("Microsoft PowerPoint", sc, ev_lines, "Microsoft PowerPoint documented.", None, ppt.source_pages))

    # 4. Computer Literacy
    comp = ts.computer_literacy
    if comp.status == "not_found":
        # If individual Office apps exist, Computer Literacy can be assessed from them; otherwise not mentioned
        office_present = [f for f in (word, excel, ppt) if f.status != "not_found"]
        if office_present:
            ev = tuple(line for f in office_present for line in f.value.get("evidence_lines", []))[:2]
            pages = tuple(sorted({p for f in office_present for p in f.source_pages}))
            factors.append(_evaluated_factor("Computer Literacy", 3, ev, "General computer literacy supported by listed office applications.", None, pages))
        else:
            factors.append(_not_mentioned_factor("Computer Literacy"))
    else:
        ev_lines = tuple(comp.value.get("evidence_lines", []))
        sc = 4 if len(comp.value.get("matched_terms", [])) >= 2 else 3
        factors.append(_evaluated_factor("Computer Literacy", sc, ev_lines, "Computer literacy / office suite skills documented.", None, comp.source_pages))

    # 5. Data Entry
    de_lines = [ln for ln in lines if re.search(r"\b(?:data\s+entry|database\s+entry|record\s+entry|typing\s+speed|wpm)\b", ln.text, re.IGNORECASE)]
    if de_lines:
        ev = tuple(ln.text for ln in de_lines[:3])
        sc = 4 if any(re.search(r"\b(?:accuracy|\d+\s*wpm|verified|reconcil)\b", ln.text, re.IGNORECASE) for ln in de_lines) else 3
        factors.append(_evaluated_factor("Data Entry", sc, ev, "Data entry capability documented.", None, tuple(sorted({ln.page_number for ln in de_lines}))))
    else:
        factors.append(_not_mentioned_factor("Data Entry"))

    # 6. Spreadsheet Skills
    ss_lines = [ln for ln in lines if re.search(r"\b(?:spreadsheet|google\s+sheets|pivot\s+tables?|vlookup|xlookup|financial\s+schedules)\b", ln.text, re.IGNORECASE)]
    if ss_lines:
        ev = tuple(ln.text for ln in ss_lines[:3])
        sc = 4 if len(ss_lines) >= 2 else 3
        factors.append(_evaluated_factor("Spreadsheet Skills", sc, ev, "Spreadsheet usage or analytical functions documented.", None, tuple(sorted({ln.page_number for ln in ss_lines}))))
    else:
        factors.append(_not_mentioned_factor("Spreadsheet Skills"))

    # 7. Accounting Software
    acc_sw = ts.accounting_software
    if acc_sw.status == "not_found":
        factors.append(_not_mentioned_factor("Accounting Software"))
    else:
        terms = acc_sw.value.get("matched_terms", [])
        ev_lines = tuple(acc_sw.value.get("evidence_lines", []))
        sc = 5 if len(terms) >= 2 else 4
        factors.append(_evaluated_factor("Accounting Software", sc, ev_lines, f"Accounting software proficiency documented ({', '.join(terms)}).", None, acc_sw.source_pages))

    # 8. Digital Banking Knowledge
    db_lines = [ln for ln in lines if re.search(r"\b(?:digital\s+banking|online\s+banking|mobile\s+banking|e-?banking|fintech|payment\s+gateway|finacle|temenos|t24|core\s+banking|swift|rtgs|ceft)\b", ln.text, re.IGNORECASE)]
    if db_lines:
        ev = tuple(ln.text for ln in db_lines[:3])
        sc = 4 if len(db_lines) >= 2 else 3
        factors.append(_evaluated_factor("Digital Banking Knowledge", sc, ev, "Digital or core banking systems knowledge documented.", None, tuple(sorted({ln.page_number for ln in db_lines}))))
    else:
        factors.append(_not_mentioned_factor("Digital Banking Knowledge"))

    return tuple(factors)


def _score_stated_language(
    lang_name: str,
    extracted_cv: ExtractedCVData,
    exam_field: ExtractedField | None = None,
) -> FactorEvaluation:
    """Evaluate English, Sinhala, or Tamil strictly from stated proficiency and exam evidence."""
    langs = extracted_cv.communication_and_languages.languages_and_proficiency
    lang_entries = langs.value if isinstance(langs.value, list) else []
    matched = [item for item in lang_entries if item.get("language", "").lower() == lang_name.lower()]

    exam_vals = tuple(str(v) for v in (exam_field.value or [])) if exam_field and exam_field.status != "not_found" else ()

    if not matched and not exam_vals:
        return _not_mentioned_factor(
            f"{lang_name} Proficiency Evidence",
            f"No explicit {lang_name} language proficiency or {lang_name} examination grade was stated (speaking ability is not assumed).",
        )

    evidence: list[str] = []
    pages: list[int] = []
    prof_score = 0

    for item in matched:
        evidence.append(str(item.get("source_line", "")))
        pages.append(int(item.get("source_page", 1)))
        prof_str = str(item.get("proficiency", "")).lower()
        if any(k in prof_str for k in ("native", "mother tongue", "bilingual", "fluent", "c2", "c1")):
            prof_score = max(prof_score, 5)
        elif any(k in prof_str for k in ("proficient", "very good", "full professional", "professional working", "oral & written", "oral and written", "b2")):
            prof_score = max(prof_score, 4)
        elif any(k in prof_str for k in ("conversational", "intermediate", "good", "working knowledge", "b1")):
            prof_score = max(prof_score, 3)
        elif any(k in prof_str for k in ("basic", "elementary", "fair", "a1", "a2")):
            prof_score = max(prof_score, 2)
        else:
            prof_score = max(prof_score, 2)

    exam_score = 0
    if exam_vals and exam_field:
        evidence.extend(exam_vals)
        pages.extend(exam_field.source_pages)
        exam_score = max(_score_single_grade_token(v)[0] for v in exam_vals)

    # Combine stated proficiency and supporting exam results without claiming spoken testing
    if prof_score and exam_score:
        final_score = round((prof_score + exam_score) / 2)
        if prof_score >= 4 and exam_score >= 4:
            final_score = max(final_score, 4)
    else:
        final_score = prof_score or exam_score

    weakness = (
        f"Stated {lang_name} proficiency level is unspecified; clarify written and spoken level."
        if matched and all(m.get("proficiency") == "Not explicitly stated" for m in matched) and not exam_vals
        else None
    )
    return _evaluated_factor(
        f"{lang_name} Proficiency Evidence",
        final_score,
        tuple(dict.fromkeys(evidence)),
        f"Evaluated from documented {lang_name} proficiency/exam evidence in the CV (actual speaking ability has not been tested).",
        weakness,
        tuple(sorted(set(pages))),
    )


def _evaluate_category_4_communication(
    extracted_cv: ExtractedCVData,
    lines: tuple[TextLineInfo, ...],
) -> tuple[FactorEvaluation, ...]:
    """CATEGORY 4: COMMUNICATION AND LANGUAGE SKILLS (Weight 10)."""
    cl = extracted_cv.communication_and_languages
    edu = extracted_cv.educational_qualifications

    factors: list[FactorEvaluation] = [
        _score_stated_language("English", extracted_cv, edu.english_results),
        _score_stated_language("Sinhala", extracted_cv, None),
        _score_stated_language("Tamil", extracted_cv, None),
    ]

    # 4. Written Communication Evidence
    written_lines = [ln for ln in lines if re.search(r"\b(?:report\s+writing|written\s+communication|oral\s*(?:&|and)\s*written|memos?|correspondence|business\s+writing|minutes|drafted|prepared\s+reports?)\b", ln.text, re.IGNORECASE)]
    if written_lines:
        sc = 4 if len(written_lines) >= 2 else 3
        factors.append(
            _evaluated_factor(
                "Written Communication Evidence",
                sc,
                tuple(ln.text for ln in written_lines[:3]),
                "Written business or reporting communication evidence documented.",
                None,
                tuple(sorted({ln.page_number for ln in written_lines})),
            )
        )
    else:
        factors.append(_not_mentioned_factor("Written Communication Evidence"))

    # 5. Customer Communication Experience
    cust = cl.customer_service_experience
    if cust.status == "not_found":
        factors.append(_not_mentioned_factor("Customer Communication Experience"))
    else:
        ev = tuple(cust.value.get("evidence_lines", []))
        sc = 4 if any(re.search(r"(?:\d+|bank|client|inquiries|onboarding)", e, re.IGNORECASE) for e in ev) else 3
        factors.append(
            _evaluated_factor(
                "Customer Communication Experience",
                sc,
                ev,
                "Customer-facing communication responsibilities documented (spoken fluency is not independently tested).",
                None,
                cust.source_pages,
            )
        )

    # 6. Presentation Experience
    pres_lines = [ln for ln in lines if re.search(r"\b(?:presentation|presented|public\s+speaking|toastmasters|debat(?:e|ing)|oratory|pitched)\b", ln.text, re.IGNORECASE)]
    if pres_lines:
        sc = 4 if len(pres_lines) >= 2 or any(re.search(r"toastmasters|weekly|client|leadership|society", ln.text, re.IGNORECASE) for ln in pres_lines) else 3
        factors.append(
            _evaluated_factor(
                "Presentation Experience",
                sc,
                tuple(ln.text for ln in pres_lines[:3]),
                "Presentation or public speaking experience documented.",
                None,
                tuple(sorted({ln.page_number for ln in pres_lines})),
            )
        )
    else:
        factors.append(_not_mentioned_factor("Presentation Experience"))

    # 7. Interpersonal Communication Evidence
    interp_lines = [ln for ln in lines if re.search(r"\b(?:interpersonal|teamwork|stakeholder|liaised|collaborated|cross[- ]functional|relationship)\b", ln.text, re.IGNORECASE)]
    if interp_lines:
        sc = 4 if len(interp_lines) >= 2 else 3
        factors.append(
            _evaluated_factor(
                "Interpersonal Communication Evidence",
                sc,
                tuple(ln.text for ln in interp_lines[:3]),
                "Teamwork, stakeholder, or interpersonal communication evidence documented.",
                None,
                tuple(sorted({ln.page_number for ln in interp_lines})),
            )
        )
    else:
        factors.append(_not_mentioned_factor("Interpersonal Communication Evidence"))

    return tuple(factors)


def _evaluate_banking_knowledge_factor(
    factor_name: str,
    field: ExtractedField,
    extracted_cv: ExtractedCVData,
) -> FactorEvaluation:
    """
    Distinguish demonstrated banking/finance knowledge (backed by experience or
    relevant qualifications) from standalone skill claims.
    """
    if field.status == "not_found":
        return _not_mentioned_factor(factor_name)

    ev_lines = tuple(field.value.get("evidence_lines", [])) if isinstance(field.value, dict) else ()
    exp_entries = extracted_cv.professional_experience.experience_entries.value
    exp_corpus = " ".join(
        " ".join(str(r) for r in e.get("responsibilities", [])) + " " + str(e.get("job_title") or "")
        for e in (exp_entries if isinstance(exp_entries, list) else [])
    ).lower()

    has_rel_qual = (
        extracted_cv.educational_qualifications.banking_finance_qualifications.status != "not_found"
        or extracted_cv.educational_qualifications.professional_qualifications.status != "not_found"
    )
    in_experience = any(line.lower() in exp_corpus or any(r.lower() in line.lower() for r in [e_r for e in (exp_entries if isinstance(exp_entries, list) else []) for e_r in e.get("responsibilities", [])]) for line in ev_lines)
    looks_like_action_evidence = any(len(line.split()) >= 5 and re.search(r"\b(?:assisted|prepared|reconcil|verified|managed|supported|evaluated|handled|audited|analyzed|processed)\b", line, re.IGNORECASE) for line in ev_lines)

    if (in_experience or looks_like_action_evidence) and has_rel_qual:
        return _evaluated_factor(
            factor_name,
            5,
            ev_lines,
            f"Demonstrated {factor_name.lower()} supported by both practical duties and relevant qualifications.",
            None,
            field.source_pages,
        )
    if in_experience or looks_like_action_evidence:
        return _evaluated_factor(
            factor_name,
            4,
            ev_lines,
            f"Demonstrated {factor_name.lower()} inside documented responsibilities.",
            None,
            field.source_pages,
        )
    if has_rel_qual:
        return _evaluated_factor(
            factor_name,
            3,
            ev_lines,
            f"{factor_name} referenced alongside relevant finance/banking qualifications.",
            None,
            field.source_pages,
        )
    return _evaluated_factor(
        factor_name,
        2,
        ev_lines,
        f"{factor_name} appears only as a brief claim without supporting work or coursework context.",
        f"Substantiate {factor_name.lower()} with concrete coursework, certifications, or applied tasks.",
        field.source_pages,
    )


def _evaluate_category_5_banking_knowledge(
    extracted_cv: ExtractedCVData,
    lines: tuple[TextLineInfo, ...],
) -> tuple[FactorEvaluation, ...]:
    """CATEGORY 5: BANKING AND FINANCE KNOWLEDGE (Weight 10)."""
    bf = extracted_cv.banking_and_finance_knowledge

    # Helper to construct ad-hoc ExtractedField for Financial Calculations & CRM
    def scan_field(name: str, pat: str) -> ExtractedField:
        hits = [ln for ln in lines if re.search(pat, ln.text, re.IGNORECASE)]
        if not hits:
            return ExtractedField(name, None, (), "not_found")
        return ExtractedField(
            name,
            {"matched_terms": [name], "evidence_lines": [ln.text for ln in hits[:4]]},
            tuple(sorted({ln.page_number for ln in hits})),
            "extracted",
        )

    fin_calc_field = scan_field(
        "Financial Calculations",
        r"\b(?:ratio\s+analysis|dcf|npv|irr|valuation|amortization|interest\s+calculat|variance\s+analysis|financial\s+model|financial\s+calculat|reconcil(?:e|ed|iation))\b",
    )
    crm_field = scan_field(
        "Customer Relationship Management",
        r"\b(?:crm|customer\s+relationship|client\s+relationship|relationship\s+management|client\s+retention|portfolio\s+servicing)\b",
    )

    return (
        _evaluate_banking_knowledge_factor("Banking Operations", bf.banking_operations, extracted_cv),
        _evaluate_banking_knowledge_factor("Financial Services", bf.financial_services, extracted_cv),
        _evaluate_banking_knowledge_factor("Accounting Knowledge", bf.accounting, extracted_cv),
        _evaluate_banking_knowledge_factor("Loans and Credit", bf.loans_and_credit, extracted_cv),
        _evaluate_banking_knowledge_factor("Deposit and Savings Products", bf.deposits_and_savings, extracted_cv),
        _evaluate_banking_knowledge_factor("Financial Calculations", fin_calc_field, extracted_cv),
        _evaluate_banking_knowledge_factor("Customer Relationship Management", crm_field, extracted_cv),
        _evaluate_banking_knowledge_factor("KYC and AML Awareness", bf.kyc_and_aml, extracted_cv),
        _evaluate_banking_knowledge_factor("Financial Compliance", bf.financial_compliance, extracted_cv),
    )


def _evaluate_category_6_achievements(
    extracted_cv: ExtractedCVData,
    lines: tuple[TextLineInfo, ...],
) -> tuple[FactorEvaluation, ...]:
    """CATEGORY 6: ACHIEVEMENTS AND EXTRACURRICULAR ACTIVITIES (Weight 5)."""
    ach = extracted_cv.achievements
    factors: list[FactorEvaluation] = []

    def eval_kw_field(label: str, field: ExtractedField, desc: str) -> FactorEvaluation:
        if field.status == "not_found":
            return _not_mentioned_factor(label)
        ev = tuple(field.value.get("evidence_lines", [])) if isinstance(field.value, dict) else tuple(str(v) for v in (field.value or []))
        sc = 5 if len(ev) >= 2 else 4
        return _evaluated_factor(label, sc, ev, desc, None, field.source_pages)

    factors.append(eval_kw_field("Academic Achievements", ach.academic_achievements, "Academic honors or distinction documented."))

    # Professional achievements (awards/recognition inside experience section)
    exp_entries = extracted_cv.professional_experience.experience_entries.value
    prof_ach_hits = []
    if isinstance(exp_entries, list):
        for e in exp_entries:
            for r in e.get("responsibilities", []):
                if re.search(r"\b(?:award|recognized|top\s+performer|best\s+intern|promoted|commendation|exceeded\s+target)\b", r, re.IGNORECASE):
                    prof_ach_hits.append(r)
    if prof_ach_hits:
        factors.append(_evaluated_factor("Professional Achievements", 4, tuple(prof_ach_hits[:3]), "Work-related recognition or target achievement documented.", None))
    else:
        factors.append(_not_mentioned_factor("Professional Achievements"))

    factors.append(eval_kw_field("Awards", ach.awards, "Awards, scholarships, or competition honors documented."))
    factors.append(eval_kw_field("Leadership", ach.leadership_activities, "Leadership roles documented."))
    factors.append(eval_kw_field("Volunteering", ach.volunteering, "Volunteering and community involvement documented."))
    factors.append(eval_kw_field("Sports and Extracurricular Activities", ach.extracurricular_activities, "Extracurricular or sports participation documented."))

    # Projects
    proj_lines = [ln for ln in lines if re.search(r"\b(?:project|dissertation|thesis|capstone|case\s+study|research\s+paper)\b", ln.text, re.IGNORECASE)]
    if proj_lines:
        is_fin_proj = any(re.search(r"\b(?:finance|banking|credit|valuation|portfolio|stock|market|accounting|risk)\b", ln.text, re.IGNORECASE) for ln in proj_lines)
        sc = 4 if is_fin_proj else 3
        factors.append(_evaluated_factor("Projects", sc, tuple(ln.text for ln in proj_lines[:3]), "Academic or applied project work documented.", None, tuple(sorted({ln.page_number for ln in proj_lines}))))
    else:
        factors.append(_not_mentioned_factor("Projects"))

    # Measurable accomplishments
    meas = ach.measurable_accomplishments
    if meas.status == "not_found":
        factors.append(_not_mentioned_factor("Measurable Accomplishments"))
    else:
        vals = tuple(str(v) for v in (meas.value or []))
        sc = 5 if len(vals) >= 3 else (4 if len(vals) == 2 else 3)
        factors.append(_evaluated_factor("Measurable Accomplishments", sc, vals[:4], f"{len(vals)} quantified accomplishment(s) documented.", None, meas.source_pages))

    return tuple(factors)


def _evaluate_category_7_structure(
    document: ProcessedPDFDocument,
    extracted_cv: ExtractedCVData,
) -> tuple[FactorEvaluation, ...]:
    """CATEGORY 7: CV STRUCTURE AND ORGANIZATION (Weight 10)."""
    detected = list(extracted_cv.detected_sections)
    lines = document.text_lines
    factors: list[FactorEvaluation] = []

    # 1. Logical Section Arrangement
    if not detected:
        factors.append(_evaluated_factor("Logical Section Arrangement", 2, (), "No standard section headings were detected to establish logical navigation.", "Add clear section headings (Education, Experience, Technical Skills, Languages, Achievements)."))
    else:
        # Ideal entry-level order puts education/experience near top before skills/achievements/referees
        order_score = 5
        wk = None
        if "referees" in detected and detected.index("referees") < len(detected) - 1:
            order_score = 4
            wk = "Place Referees at the end of the CV."
        elif len(detected) < 3:
            order_score = 3
            wk = "Organize CV into more distinct standard sections."
        factors.append(_evaluated_factor("Logical Section Arrangement", order_score, (f"Section order: {' -> '.join(detected)}",), "Evaluated top-to-bottom section sequence.", wk))

    # 2. Clear Section Headings
    heading_count = len(detected)
    if heading_count >= 5:
        sc, wk = 5, None
    elif heading_count >= 4:
        sc, wk = 4, None
    elif heading_count >= 2:
        sc, wk = 3, "Add dedicated headings for missing standard CV sections."
    else:
        sc, wk = 1, "Standard CV section headings are largely absent."
    factors.append(_evaluated_factor("Clear Section Headings", sc, tuple(detected) or ("None detected",), f"{heading_count} standard section heading(s) identified.", wk))

    # 3. Contact Information Placement
    p = extracted_cv.personal_and_contact
    present_fields = [f for f in (p.candidate_name, p.email_address, p.telephone_number, p.location) if f.status != "not_found"]
    on_page1 = all(1 in f.source_pages for f in present_fields) if present_fields else False
    if len(present_fields) == 4 and on_page1:
        sc, wk = 5, None
    elif len(present_fields) >= 3 and on_page1:
        sc, wk = 4, "Include all core contact fields (name, email, phone, location) at the top of Page 1."
    elif len(present_fields) >= 2:
        sc, wk = 3, "Contact block is incomplete or not fully placed on Page 1."
    else:
        sc, wk = 1, "Essential contact information is missing from the CV header."
    factors.append(_evaluated_factor("Contact Information Placement", sc, tuple(f"{f.field_name}: {f.value}" for f in present_fields), f"{len(present_fields)} of 4 core contact fields detected on Page 1.", wk))

    # 4. Education Organization
    if "education" not in detected and extracted_cv.educational_qualifications.degrees.status == "not_found" and extracted_cv.educational_qualifications.gce_ol_results.status == "not_found":
        factors.append(_not_mentioned_factor("Education Organization", "No Education section was found in the CV."))
    else:
        edu = extracted_cv.educational_qualifications
        populated = sum(1 for f in (edu.degrees, edu.diplomas, edu.gce_al_results, edu.gce_ol_results) if f.status != "not_found")
        sc = 5 if ("education" in detected and populated >= 2) else (4 if populated >= 1 else 2)
        factors.append(_evaluated_factor("Education Organization", sc, (f"Education heading present: {'education' in detected}",), "Evaluated clarity and grouping of educational credentials.", None if sc >= 4 else "Group degrees, A/Ls, and O/Ls clearly under a dedicated Education heading."))

    # 5. Work Experience Organization
    exp_entries = extracted_cv.professional_experience.experience_entries.value
    if not isinstance(exp_entries, list) or not exp_entries:
        if "experience" in detected:
            factors.append(_evaluated_factor("Work Experience Organization", 2, (), "Experience heading is present, but structured role/date/bullet entries could not be separated.", "Format each role clearly as Title - Company | Start - End Date followed by bullet points."))
        else:
            factors.append(_not_mentioned_factor("Work Experience Organization", "No Work Experience section was found in the CV."))
    else:
        complete_entries = sum(1 for e in exp_entries if e.get("job_title") and e.get("company_name") and e.get("employment_dates") and e.get("responsibilities"))
        ratio = complete_entries / len(exp_entries)
        sc = 5 if ratio == 1.0 else (4 if ratio >= 0.5 else 3)
        wk = None if sc == 5 else "Ensure every role specifies job title, company name, month/year dates, and bulleted duties."
        factors.append(_evaluated_factor("Work Experience Organization", sc, (f"{complete_entries}/{len(exp_entries)} entries fully structured",), "Evaluated completeness of role, company, date, and duty structure.", wk))

    # 6. Chronological Consistency
    year_mentions = [int(y) for ln in lines for y in re.findall(r"\b((?:19|20)\d{2})\b", ln.text)]
    if isinstance(exp_entries, list) and len(exp_entries) >= 2:
        invalid_dates = any("invalid" in str(e.get("duration_display", "")).lower() for e in exp_entries)
        missing_dates = sum(1 for e in exp_entries if not e.get("employment_dates"))
        if invalid_dates:
            sc, exp, wk = 1, "One or more employment date ranges appear chronologically invalid.", "Correct start and end dates on employment entries."
        elif missing_dates > 0:
            sc, exp, wk = 3, f"{missing_dates} role(s) are missing dates, reducing chronological clarity.", "Add consistent Month Year - Month Year dates to every entry."
        else:
            sc, exp, wk = 5, "Experience dates are consistently formatted and chronologically coherent.", None
        factors.append(_evaluated_factor("Chronological Consistency", sc, tuple(str(e.get("employment_dates") or "Missing") for e in exp_entries), exp, wk))
    elif len(year_mentions) >= 2:
        factors.append(_evaluated_factor("Chronological Consistency", 4, (f"Years cited: {', '.join(str(y) for y in year_mentions[:6])}",), "Dates across sections are consistent.", None))
    else:
        factors.append(_cannot_assess_factor("Chronological Consistency", "Fewer than two dated entries exist to evaluate chronological ordering."))

    # 7. Information Completeness
    missing_cnt = len(extracted_cv.missing_sections)
    if missing_cnt == 0:
        sc, wk = 5, None
    elif missing_cnt == 1:
        sc, wk = 4, f"Missing standard section: {', '.join(extracted_cv.missing_sections)}."
    elif missing_cnt == 2:
        sc, wk = 3, f"Missing standard sections: {', '.join(extracted_cv.missing_sections)}."
    else:
        sc, wk = 2, f"Multiple core sections missing: {', '.join(extracted_cv.missing_sections)}."
    factors.append(_evaluated_factor("Information Completeness", sc, (f"Detected: {', '.join(detected) or 'None'}",), f"{len(detected)} section groups detected; {missing_cnt} core section(s) missing.", wk))

    # 8. Relevant Information & Conciseness (no repetition or irrelevant personal clutter)
    norm_lines = [ln.text.strip().lower() for ln in lines if len(ln.text.strip().split()) >= 4]
    dup_lines = [txt for txt, cnt in Counter(norm_lines).items() if cnt > 1]
    irrelevant_bio = [ln.text for ln in lines if re.search(r"\b(?:marital\s+status|religion|ethnicity|height|weight|passport\s+no|father'?s\s+name)\b", ln.text, re.IGNORECASE)]
    if dup_lines or len(irrelevant_bio) >= 2:
        sc = 3
        wk = "Remove duplicate lines or non-relevant personal details (e.g., marital status/religion)."
    elif irrelevant_bio:
        sc = 4
        wk = "Consider removing non-essential personal attributes (e.g., marital status/religion)."
    else:
        sc = 5
        wk = None
    factors.append(_evaluated_factor("Relevant Information", sc, tuple((dup_lines + irrelevant_bio)[:3]) or ("Focused professional content",), "Checked for duplicated lines and irrelevant personal attributes.", wk))

    # 9. Appropriate CV Length
    pages = document.page_count
    words = document.word_count
    if 1 <= pages <= 2 and 200 <= words <= 950:
        sc, exp, wk = 5, f"Appropriate entry-level length ({pages} page(s), {words} words).", None
    elif 1 <= pages <= 2 and 120 <= words < 200:
        sc, exp, wk = 3, f"Page count is concise ({pages} page(s)), though word count ({words}) is relatively sparse.", "Expand key education/project/experience bullet details."
    elif pages == 3 or words > 950:
        sc, exp, wk = 3, f"Slightly long for an entry-level CV ({pages} pages, {words} words).", "Aim for 1-2 tight, high-impact pages."
    else:
        sc, exp, wk = 2, f"Length is atypical ({pages} page(s), {words} words).", "Adjust CV length to 1-2 well-balanced pages."
    factors.append(_evaluated_factor("Appropriate CV Length", sc, (f"{pages} page(s), {words} words",), exp, wk))

    return tuple(factors)


def _evaluate_category_8_language(
    document: ProcessedPDFDocument,
) -> tuple[FactorEvaluation, ...]:
    """CATEGORY 8: LANGUAGE AND WRITING QUALITY (Weight 10)."""
    report: LanguageQualityReport = analyze_language_quality(document.text_lines)

    def format_findings(findings) -> tuple[str, ...]:
        return tuple(f"'{f.incorrect}' -> '{f.correction}' (p.{f.page_number})" for f in findings[:5])

    factors: list[FactorEvaluation] = []

    # 1. Spelling
    sp_cnt = len(report.spelling_findings)
    if sp_cnt == 0:
        factors.append(_evaluated_factor("Spelling", 5, ("No unambiguous misspellings detected (valid UK/US English variants preserved).",), "Clean spelling across extracted text.", None))
    else:
        sc = max(1, 5 - sp_cnt) if sp_cnt <= 3 else 1
        ev = format_findings(report.spelling_findings)
        factors.append(_evaluated_factor("Spelling", sc, ev, f"Detected {sp_cnt} spelling error(s).", f"Fix spelling errors: {'; '.join(ev)}.", tuple(sorted({f.page_number for f in report.spelling_findings}))))

    # 2. Grammar
    gr_cnt = len(report.grammar_findings)
    if gr_cnt == 0:
        factors.append(_evaluated_factor("Grammar", 5, ("No rule-based grammar errors detected.",), "Grammar rules checked cleanly.", None))
    else:
        sc = max(1, 5 - gr_cnt) if gr_cnt <= 3 else 1
        ev = format_findings(report.grammar_findings)
        factors.append(_evaluated_factor("Grammar", sc, ev, f"Detected {gr_cnt} grammar issue(s).", f"Correct grammar issues: {'; '.join(ev)}.", tuple(sorted({f.page_number for f in report.grammar_findings}))))

    # 3. Sentence Construction
    if report.bullet_count == 0 and document.word_count < 80:
        factors.append(_evaluated_factor("Sentence Construction", 3, (f"{document.word_count} total words",), "Limited prose/bullet sentences available to evaluate construction.", "Add structured bullet statements describing accomplishments."))
    elif report.long_bullet_count == 0 and report.fragmented_line_count <= 1:
        factors.append(_evaluated_factor("Sentence Construction", 5, (f"{report.bullet_count} bullet(s), avg {report.avg_bullet_words} words",), "Concise, well-constructed CV statements.", None))
    else:
        sc = 3 if (report.long_bullet_count + report.fragmented_line_count) <= 3 else 2
        factors.append(_evaluated_factor("Sentence Construction", sc, (f"{report.long_bullet_count} overly long bullet(s), {report.fragmented_line_count} very short fragment(s)",), "Some bullets are overly long (>35 words) or fragmented.", "Keep each bullet between 8 and 25 words with a clear verb + outcome."))

    # 4. Punctuation
    pu_cnt = len(report.punctuation_findings)
    if pu_cnt == 0:
        factors.append(_evaluated_factor("Punctuation", 5, ("Clean punctuation spacing and terminal marks.",), "No punctuation spacing errors detected.", None))
    else:
        sc = max(2, 5 - pu_cnt)
        ev = format_findings(report.punctuation_findings)
        factors.append(_evaluated_factor("Punctuation", sc, ev, f"Detected {pu_cnt} punctuation formatting issue(s).", f"Fix punctuation spacing: {'; '.join(ev)}."))

    # 5. Capitalization
    cap_cnt = len(report.capitalization_findings)
    if cap_cnt == 0:
        factors.append(_evaluated_factor("Capitalization", 5, ("Consistent capitalization of proper nouns and bullet starters.",), "No capitalization errors detected.", None))
    else:
        sc = max(2, 5 - cap_cnt)
        ev = format_findings(report.capitalization_findings)
        factors.append(_evaluated_factor("Capitalization", sc, ev, f"Detected {cap_cnt} capitalization issue(s).", f"Fix capitalization: {'; '.join(ev)}."))

    # 6. Professional Vocabulary
    if report.action_verb_hits >= 4 and report.weak_phrase_hits == 0:
        sc, wk = 5, None
    elif report.action_verb_hits >= 2:
        sc, wk = 4, ("Replace passive phrases like 'Responsible for' with strong action verbs." if report.weak_phrase_hits else None)
    elif report.action_verb_hits >= 1 or report.weak_phrase_hits >= 1:
        sc, wk = 3, "Use stronger banking/finance action verbs (e.g., Reconciled, Analyzed, Prepared, Audited)."
    else:
        sc, wk = 2, "Few professional action verbs detected; strengthen descriptions with action-oriented phrasing."
    factors.append(_evaluated_factor("Professional Vocabulary", sc, (f"{report.action_verb_hits} action-verb line(s), {report.weak_phrase_hits} weak passive phrase(s)",), "Evaluated presence of active professional verbs vs passive boilerplate.", wk))

    # 7. Sentence Clarity
    if report.bullet_count > 0:
        sc = 5 if 7.0 <= report.avg_bullet_words <= 22.0 else (4 if report.avg_bullet_words <= 28.0 else 3)
        wk = "Shorten dense bullets for rapid recruiter scanning." if sc < 4 else None
        factors.append(_evaluated_factor("Sentence Clarity", sc, (f"Average bullet length: {report.avg_bullet_words} words",), "Evaluated conciseness and scannability of bullet statements.", wk))
    else:
        factors.append(_evaluated_factor("Sentence Clarity", 3, ("No bulleted responsibility statements detected",), "Evaluated plain prose lines; bullet points would improve clarity.", "Use concise bullet points under experience and achievement entries."))

    # 8. Repeated Words
    rep_cnt = len(report.repeated_word_findings)
    opener_cnt = len(report.repeated_opener_phrases)
    if rep_cnt == 0 and opener_cnt == 0:
        factors.append(_evaluated_factor("Repeated Words", 5, ("No adjacent duplicate words or repetitive bullet openers detected.",), "Good lexical variety.", None))
    else:
        sc = max(1, 5 - (rep_cnt * 2) - opener_cnt)
        ev = format_findings(report.repeated_word_findings) + report.repeated_opener_phrases
        factors.append(_evaluated_factor("Repeated Words", sc, ev, "Detected repeated consecutive words or overused starting phrases.", f"Vary wording and remove duplicates: {'; '.join(ev)}."))

    # 9. Consistency of Writing Style
    if report.bullet_period_consistency_pct is None:
        factors.append(_cannot_assess_factor("Consistency of Writing Style", "Fewer than two bullet points were found to evaluate punctuation/style consistency."))
    else:
        pct = report.bullet_period_consistency_pct
        sc = 5 if pct >= 90.0 else (4 if pct >= 75.0 else 3)
        wk = None if pct >= 90.0 else f"Standardize bullet ending punctuation (currently {pct}% consistent)."
        factors.append(_evaluated_factor("Consistency of Writing Style", sc, (f"Bullet punctuation consistency: {pct}%",), "Checked uniform ending punctuation across bullet points.", wk))

    return tuple(factors)


def _evaluate_category_9_visual(document: ProcessedPDFDocument) -> tuple[FactorEvaluation, ...]:
    """CATEGORY 9: VISUAL PRESENTATION AND FORMATTING (Weight 10)."""
    analysis = document.document_analysis
    pms = analysis.page_metrics
    lines = document.text_lines
    factors: list[FactorEvaluation] = []

    # 1. Font Consistency (normalize Bold/Italic variants to base family)
    base_families = {
        re.sub(r"(?:^|\+)(?:[A-Z]{6}\+)?", "", fn).split("-")[0].split(",")[0].strip()
        for fn in analysis.font_names
        if fn
    }
    fam_count = len(base_families)
    if fam_count == 0:
        factors.append(_cannot_assess_factor("Font Consistency", "No embedded vector font metadata was detected."))
    else:
        sc = 5 if fam_count <= 2 else (4 if fam_count == 3 else (2 if fam_count == 4 else 1))
        wk = None if fam_count <= 2 else f"Standardize to 1-2 font families (currently {fam_count} families detected)."
        factors.append(_evaluated_factor("Font Consistency", sc, tuple(sorted(base_families)), f"{fam_count} base font family/families detected.", wk))

    # 2. Font Readability
    body_pt = analysis.primary_body_font_size_pt
    if body_pt is None:
        factors.append(_cannot_assess_factor("Font Readability", "Primary body font size could not be measured."))
    else:
        if 9.5 <= body_pt <= 12.0:
            sc, wk = 5, None
        elif 8.5 <= body_pt < 9.5 or 12.0 < body_pt <= 13.0:
            sc, wk = 4, None
        elif 7.5 <= body_pt < 8.5:
            sc, wk = 3, f"Primary body font ({body_pt} pt) is slightly small for comfortable reading; prefer 10-11.5 pt."
        else:
            sc, wk = 2, f"Primary body font ({body_pt} pt) falls outside standard readable range (9.5-12 pt)."
        factors.append(_evaluated_factor("Font Readability", sc, (f"Primary body font size: {body_pt} pt",), "Evaluated measurable body text point size.", wk))

    # 3. Font Size Consistency
    sizes = analysis.font_sizes_pt
    if not sizes:
        factors.append(_cannot_assess_factor("Font Size Consistency", "No font size measurements available."))
    else:
        has_hierarchy = (
            analysis.largest_heading_font_size_pt is not None
            and body_pt is not None
            and analysis.largest_heading_font_size_pt > body_pt
        )
        if 2 <= len(sizes) <= 4 and has_hierarchy:
            sc, wk = 5, None
        elif len(sizes) <= 5:
            sc, wk = 4, (None if has_hierarchy else "Use slightly larger heading font sizes to establish clear visual hierarchy.")
        else:
            sc, wk = 2, f"Too many distinct font sizes ({len(sizes)} sizes); standardize to 2-4 sizes."
        factors.append(_evaluated_factor("Font Size Consistency", sc, (f"Font sizes (pt): {', '.join(str(s) for s in sizes)}",), "Evaluated typographic size hierarchy and restraint.", wk))

    # 4. Paragraph Spacing
    med_gaps = [pm.median_line_gap_pt for pm in pms if pm.median_line_gap_pt is not None]
    if not med_gaps:
        factors.append(_cannot_assess_factor("Paragraph Spacing", "Insufficient multi-line spacing data to measure paragraph gaps."))
    else:
        avg_gap = round(sum(med_gaps) / len(med_gaps), 2)
        if 1.5 <= avg_gap <= 8.0:
            sc, wk = 5, None
        elif 0.8 <= avg_gap < 1.5 or 8.0 < avg_gap <= 12.0:
            sc, wk = 4, None
        else:
            sc, wk = 2, f"Line spacing ({avg_gap} pt median gap) is overly tight or excessively wide."
        factors.append(_evaluated_factor("Paragraph Spacing", sc, (f"Median line gap: {avg_gap} pt",), "Measured vertical line-to-line spacing across pages.", wk))

    # 5. Section Spacing
    total_sec_gaps = sum(pm.section_gap_count for pm in pms)
    if len(lines) < 5:
        factors.append(_cannot_assess_factor("Section Spacing", "Insufficient lines to measure section breaks."))
    else:
        sc = 5 if total_sec_gaps >= 3 else (4 if total_sec_gaps >= 1 else 2)
        wk = None if sc >= 4 else "Add clearer vertical whitespace breaks between CV sections."
        factors.append(_evaluated_factor("Section Spacing", sc, (f"Distinct section gaps detected: {total_sec_gaps}",), "Measured larger vertical breaks separating logical sections.", wk))

    # 6. Text Alignment
    align_notes = [note for pm in pms for note in pm.alignment_indicators]
    if not pms:
        factors.append(_cannot_assess_factor("Text Alignment", "No page alignment data available."))
    else:
        consistent_left = any("Consistent left-aligned" in a for a in align_notes)
        sc = 5 if consistent_left else 3
        wk = None if consistent_left else "Align section text along consistent left margin anchors."
        factors.append(_evaluated_factor("Text Alignment", sc, tuple(dict.fromkeys(align_notes)) or ("Irregular x-coordinates",), "Evaluated x-coordinate alignment consistency across text lines.", wk))

    # 7. Margin Consistency
    margins_present = [pm for pm in pms if pm.left_margin_pt is not None]
    if not margins_present:
        factors.append(_cannot_assess_factor("Margin Consistency", "No text bounding boxes available to measure margins."))
    else:
        min_margin = min(
            min(pm.left_margin_pt or 0, pm.right_margin_pt or 0, pm.top_margin_pt or 0, pm.bottom_margin_pt or 0)
            for pm in margins_present
        )
        if min_margin >= 28.0:
            sc, wk = 5, None
        elif min_margin >= 18.0:
            sc, wk = 4, None
        elif min_margin >= 10.0:
            sc, wk = 3, f"Margins are slightly narrow (minimum {min_margin} pt); aim for >= 28 pt (~10 mm)."
        else:
            sc, wk = 2, f"Cramped page margins detected (minimum {min_margin} pt)."
        ev = tuple(f"P{pm.page_number} L/R/T/B: {pm.left_margin_pt}/{pm.right_margin_pt}/{pm.top_margin_pt}/{pm.bottom_margin_pt} pt" for pm in margins_present)
        factors.append(_evaluated_factor("Margin Consistency", sc, ev, "Measured page margins from text bounding boxes.", wk))

    # 8. Bullet-Point Formatting
    bullet_chars = [ln.text.strip()[0] for ln in lines if re.match(r"^[•●▪▫◦\-\*]\s+", ln.text.strip())]
    if not bullet_chars:
        factors.append(_cannot_assess_factor("Bullet-Point Formatting", "No bulleted list symbols were detected to assess bullet uniformity."))
    else:
        unique_bullets = set(bullet_chars)
        sc = 5 if len(unique_bullets) == 1 else (3 if len(unique_bullets) == 2 else 2)
        wk = None if len(unique_bullets) == 1 else f"Mixed bullet symbols used ({', '.join(sorted(unique_bullets))}); standardize to a single bullet style."
        factors.append(_evaluated_factor("Bullet-Point Formatting", sc, (f"{len(bullet_chars)} bullet(s) using: {', '.join(sorted(unique_bullets))}",), "Evaluated bullet symbol uniformity.", wk))

    # 9. Text Overlap
    overlaps = analysis.total_overlapping_pairs
    clipped = analysis.total_clipped_lines
    if overlaps == 0 and clipped == 0:
        sc, wk = 5, None
    elif (overlaps + clipped) == 1:
        sc, wk = 3, "Detected 1 overlapping or clipped text bounding box; inspect layout alignment."
    elif (overlaps + clipped) <= 3:
        sc, wk = 2, f"Detected {overlaps} overlapping pair(s) and {clipped} clipped line(s)."
    else:
        sc, wk = 1, f"Severe text collision/clipping detected ({overlaps} overlaps, {clipped} clipped lines)."
    factors.append(_evaluated_factor("Text Overlap", sc, (f"Overlapping pairs: {overlaps}, Clipped lines: {clipped}",), "Checked PyMuPDF line bounding boxes for overlaps and out-of-bounds clipping.", wk))

    # 10. Overall Neatness
    dist_values = [pm.text_distribution_pct for pm in pms]
    has_trailing_sparse_page = len(dist_values) >= 2 and min(dist_values) < 10.0
    if overlaps == 0 and clipped == 0 and not has_trailing_sparse_page and fam_count <= 3:
        sc, wk = 5, None
    elif has_trailing_sparse_page:
        sc, wk = 3, f"Unbalanced page distribution ({', '.join(f'P{pm.page_number}: {pm.text_distribution_pct}%' for pm in pms)}); avoid a sparse trailing page."
    else:
        sc, wk = 4 if (overlaps + clipped) == 0 else 2, ("Resolve overlapping or clipped text to improve overall neatness." if (overlaps + clipped) > 0 else None)
    factors.append(_evaluated_factor("Overall Neatness", sc, tuple(f"Page {pm.page_number}: {pm.text_distribution_pct}% text" for pm in pms), "Evaluated cross-page text balance and visual cleanliness.", wk))

    # 11. Page Layout and Readability
    paper_labels = {dim.paper_size_label for dim in analysis.page_dimensions}
    standard_paper = all("A4" in lbl or "Letter" in lbl for lbl in paper_labels)
    if standard_paper and len(paper_labels) == 1:
        sc, wk = 5, None
    elif standard_paper:
        sc, wk = 4, "Mixed paper sizes across pages; standardize to uniform A4 or US Letter."
    else:
        sc, wk = 3, f"Non-standard page dimensions detected ({', '.join(paper_labels)})."
    factors.append(_evaluated_factor("Page Layout and Readability", sc, tuple(paper_labels), "Evaluated page size consistency and layout readability.", wk))

    return tuple(factors)


def _aggregate_category(
    category: EvaluationCategory,
    factors: tuple[FactorEvaluation, ...],
) -> CategoryEvaluation:
    """Apply the weighted scoring formula using assessable factors only."""
    applicable = [f for f in factors if f.status != STATUS_NOT_APPLICABLE]
    assessed = [f for f in applicable if f.status == STATUS_EVALUATED and f.score is not None]

    applicable_count = len(applicable)
    assessed_count = len(assessed)
    coverage_pct = round((assessed_count / applicable_count) * 100.0, 1) if applicable_count > 0 else 0.0

    if assessed_count == 0:
        return CategoryEvaluation(
            category=category,
            category_score=0.0,
            max_weight=category.max_points,
            average_factor_score=None,
            assessed_factor_count=0,
            applicable_factor_count=applicable_count,
            coverage_pct=0.0,
            status="Unavailable",
            coverage_note=(
                f"Category unavailable: 0 of {applicable_count} factors could be assessed. "
                f"Its {category.max_points}-point weight was NOT redistributed."
            ),
            factors=factors,
        )

    avg_score = round(sum(f.score for f in assessed if f.score is not None) / assessed_count, 2)
    raw_cat_score = (avg_score / 5.0) * category.max_points
    clamped_cat_score = round(max(0.0, min(float(category.max_points), raw_cat_score)), 2)

    if coverage_pct < 50.0:
        status = "Partial Coverage"
        note = (
            f"Partial assessment coverage ({assessed_count}/{applicable_count} factors, {coverage_pct}%). "
            "Score reflects assessed factors only; missing items were not penalized as zero."
        )
    else:
        status = "Evaluated"
        note = f"Assessed {assessed_count}/{applicable_count} factors ({coverage_pct}% coverage)."

    return CategoryEvaluation(
        category=category,
        category_score=clamped_cat_score,
        max_weight=category.max_points,
        average_factor_score=avg_score,
        assessed_factor_count=assessed_count,
        applicable_factor_count=applicable_count,
        coverage_pct=coverage_pct,
        status=status,
        coverage_note=note,
        factors=factors,
    )


def evaluate_cv(
    document: ProcessedPDFDocument,
    extracted_cv: ExtractedCVData | None = None,
) -> CVEvaluationResult:
    """
    Run the complete deterministic 9-category evaluation engine on a processed PDF CV.
    """
    if extracted_cv is None:
        extracted_cv = extract_cv_information(document)

    total_possible = sum(cat.max_points for cat in EVALUATION_CATEGORIES)
    cap_max = sum(cat.max_points for cat in EVALUATION_CATEGORIES if cat.group == "candidate_capability")
    pres_max = sum(cat.max_points for cat in EVALUATION_CATEGORIES if cat.group == "document_presentation")

    # Handle scanned / unreadable PDFs honestly without fabricating scores
    if document.is_scanned_pdf or not document.has_extractable_text:
        unavailable_cats: list[CategoryEvaluation] = []
        for cat in EVALUATION_CATEGORIES:
            unavailable_cats.append(
                CategoryEvaluation(
                    category=cat,
                    category_score=0.0,
                    max_weight=cat.max_points,
                    average_factor_score=None,
                    assessed_factor_count=0,
                    applicable_factor_count=1,
                    coverage_pct=0.0,
                    status="Unavailable",
                    coverage_note=(
                        "Unavailable: Scanned image PDF without selectable text (OCR not implemented). "
                        f"Weight ({cat.max_points} pts) was NOT redistributed."
                    ),
                    factors=(
                        _cannot_assess_factor(
                            cat.title,
                            "OCR support is not currently implemented; selectable text is required to evaluate this category.",
                        ),
                    ),
                )
            )
        return CVEvaluationResult(
            filename=document.filename,
            is_assessable=False,
            overall_score=0.0,
            total_possible_score=total_possible,
            candidate_capability_score=0.0,
            candidate_capability_max=cap_max,
            document_presentation_score=0.0,
            document_presentation_max=pres_max,
            overall_assessed_factors=0,
            overall_applicable_factors=len(EVALUATION_CATEGORIES),
            overall_coverage_pct=0.0,
            coverage_warning="OCR support is not currently implemented for scanned PDFs; 0% of evaluation factors could be assessed.",
            summary_message=f"'{document.filename}' could not be evaluated because it contains no selectable text (OCR not implemented).",
            categories=tuple(unavailable_cats),
            identified_weaknesses=(),
            missing_information=("All categories unavailable due to missing selectable text (OCR required).",),
        )

    lines = document.text_lines

    factor_map = {
        "educational_qualifications": _evaluate_category_1_education(extracted_cv),
        "professional_experience": _evaluate_category_2_experience(extracted_cv, lines),
        "technical_computer_skills": _evaluate_category_3_technical_skills(extracted_cv, lines),
        "communication_language_skills": _evaluate_category_4_communication(extracted_cv, lines),
        "banking_finance_knowledge": _evaluate_category_5_banking_knowledge(extracted_cv, lines),
        "achievements_extracurricular": _evaluate_category_6_achievements(extracted_cv, lines),
        "cv_structure_organization": _evaluate_category_7_structure(document, extracted_cv),
        "language_writing_quality": _evaluate_category_8_language(document),
        "visual_presentation_formatting": _evaluate_category_9_visual(document),
    }

    evaluated_categories = tuple(
        _aggregate_category(cat, factor_map[cat.key])
        for cat in EVALUATION_CATEGORIES
    )

    overall_score = round(
        min(float(total_possible), sum(c.category_score for c in evaluated_categories)),
        2,
    )
    cap_score = round(
        sum(c.category_score for c in evaluated_categories if c.category.group == "candidate_capability"),
        2,
    )
    pres_score = round(
        sum(c.category_score for c in evaluated_categories if c.category.group == "document_presentation"),
        2,
    )

    total_assessed = sum(c.assessed_factor_count for c in evaluated_categories)
    total_applicable = sum(c.applicable_factor_count for c in evaluated_categories)
    overall_cov = round((total_assessed / total_applicable) * 100.0, 1) if total_applicable > 0 else 0.0

    unavailable_names = [c.category.title for c in evaluated_categories if c.status == "Unavailable"]
    coverage_warning: str | None = None
    if overall_cov < 50.0 or unavailable_names:
        parts = [f"Assessment coverage is {overall_cov}% ({total_assessed} of {total_applicable} factors assessed)."]
        if unavailable_names:
            parts.append(f"Unavailable category/categories (weight not redistributed): {', '.join(unavailable_names)}.")
        parts.append("Low-coverage scores only reflect documented information and should not be treated as complete.")
        coverage_warning = " ".join(parts)

    weaknesses: list[str] = []
    missing_info: list[str] = []
    for cat_eval in evaluated_categories:
        for f in cat_eval.factors:
            if f.weakness:
                weaknesses.append(f"[{cat_eval.category.title} — {f.factor_name}] {f.weakness}")
            if f.status in (STATUS_NOT_MENTIONED, STATUS_CANNOT_ASSESS):
                missing_info.append(f"[{cat_eval.category.title}] {f.factor_name}: {f.status}")

    summary = (
        f"Evaluation complete for '{document.filename}': Overall Score {overall_score:.2f} / {total_possible} "
        f"(Candidate Capability: {cap_score:.2f}/{cap_max}, Document Presentation: {pres_score:.2f}/{pres_max}; "
        f"Assessment Coverage: {overall_cov}%)."
    )

    return CVEvaluationResult(
        filename=document.filename,
        is_assessable=True,
        overall_score=overall_score,
        total_possible_score=total_possible,
        candidate_capability_score=cap_score,
        candidate_capability_max=cap_max,
        document_presentation_score=pres_score,
        document_presentation_max=pres_max,
        overall_assessed_factors=total_assessed,
        overall_applicable_factors=total_applicable,
        overall_coverage_pct=overall_cov,
        coverage_warning=coverage_warning,
        summary_message=summary,
        categories=evaluated_categories,
        identified_weaknesses=tuple(weaknesses),
        missing_information=tuple(missing_info),
    )


# Backwards-compatible alias if earlier callers reference run_foundation_analysis
run_foundation_analysis = evaluate_cv
