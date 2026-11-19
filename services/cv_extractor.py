"""
Rule-based local CV information extraction service using PyMuPDF output.

Extracts structured candidate information strictly from text present in the PDF.
Never uses external AI APIs, never invents missing qualifications, and preserves
source page numbers, extraction status, and uncertainty notes for every field.
"""

from dataclasses import asdict, dataclass
from datetime import date
import re
from typing import Any

from services.pdf_processor import ProcessedPDFDocument, TextLineInfo


# Standard CV section headings mapped to canonical section identifiers
SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "personal": ("personal details", "personal information", "contact", "contact details", "contact information"),
    "summary": ("profile", "personal profile", "career objective", "objective", "summary", "professional summary", "about me"),
    "education": (
        "education",
        "educational qualifications",
        "academic qualifications",
        "academic background",
        "education & qualifications",
        "qualifications",
        "school education",
    ),
    "professional_qualifications": (
        "professional qualifications",
        "certifications",
        "professional certifications",
        "licenses & certifications",
        "banking & finance qualifications",
    ),
    "experience": (
        "experience",
        "work experience",
        "professional experience",
        "employment history",
        "career history",
        "work history",
        "internships",
        "internship experience",
        "industrial training",
    ),
    "skills": (
        "skills",
        "technical skills",
        "it skills",
        "computer skills",
        "core competencies",
        "competencies",
        "key skills",
        "software skills",
    ),
    "languages": ("languages", "language proficiency", "communication & languages"),
    "achievements": (
        "achievements",
        "awards",
        "honors & awards",
        "honours & awards",
        "extracurricular",
        "extracurricular activities",
        "extra-curricular activities",
        "co-curricular activities",
        "leadership",
        "leadership & activities",
        "volunteering",
        "volunteer experience",
        "sports & activities",
    ),
    "referees": ("referees", "references"),
}

CORE_EXPECTED_SECTIONS: tuple[str, ...] = (
    "education",
    "experience",
    "skills",
    "languages",
    "achievements",
)

MONTH_MAP: dict[str, int] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)\d{3,4}[\s.-]?\d{3,4}(?!\d)")
DATE_RANGE_RE = re.compile(
    r"("
    r"(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+\d{4})"
    r"|(?:\d{1,2}/\d{4})"
    r"|(?:\d{4}-\d{2})"
    r"|(?:\b(?:19|20)\d{2}\b)"
    r")"
    r"\s*(?:-|–|—|to)\s*"
    r"("
    r"(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+\d{4})"
    r"|(?:\d{1,2}/\d{4})"
    r"|(?:\d{4}-\d{2})"
    r"|(?:\b(?:19|20)\d{2}\b)"
    r"|(?:present|current|ongoing|till\s*date|to\s*date|now)"
    r")",
    re.IGNORECASE,
)

IGNORED_NAME_HEADERS = {
    "curriculum vitae",
    "resume",
    "cv",
    "personal details",
    "personal profile",
    "contact details",
    "bio data",
    "biodata",
}

ROLE_TITLE_KEYWORDS = (
    "intern",
    "trainee",
    "analyst",
    "associate",
    "assistant",
    "officer",
    "executive",
    "clerk",
    "teller",
    "cashier",
    "representative",
    "specialist",
    "coordinator",
    "auditor",
    "accountant",
    "bookkeeper",
    "advisor",
    "consultant",
    "manager",
    "supervisor",
    "apprentice",
    "placement",
)

COMPANY_HINT_KEYWORDS = (
    "bank",
    "plc",
    "ltd",
    "limited",
    "inc",
    "llc",
    "corp",
    "group",
    "holdings",
    "finance",
    "financial",
    "capital",
    "securities",
    "insurance",
    "assurance",
    "credit",
    "leasing",
    "associates",
    "partners",
    "kpmg",
    "pwc",
    "ey",
    "deloitte",
    "bdo",
    "hsbc",
    "commercial bank",
    "sampath",
    "hatton national",
    "hnb",
    "seylan",
    "ndb",
    "dfcc",
    "peoples bank",
    "people's bank",
    "bank of ceylon",
    "boc",
    "nations trust",
)


@dataclass(frozen=True)
class ExtractedField:
    """Structured field wrapper preserving provenance, status, and uncertainty."""

    field_name: str
    value: Any
    source_pages: tuple[int, ...]
    status: str  # extracted | partial | not_found | not_extracted_ocr_required | ambiguous
    uncertainty: str | None = None


@dataclass(frozen=True)
class PersonalContactInfo:
    """Section A: Personal and contact details."""

    candidate_name: ExtractedField
    email_address: ExtractedField
    telephone_number: ExtractedField
    location: ExtractedField


@dataclass(frozen=True)
class EducationalQualifications:
    """Section B: School examinations, degrees, diplomas, and professional credentials."""

    gce_ol_results: ExtractedField
    gce_al_results: ExtractedField
    english_results: ExtractedField
    mathematics_results: ExtractedField
    degrees: ExtractedField
    diplomas: ExtractedField
    professional_qualifications: ExtractedField
    banking_finance_qualifications: ExtractedField


@dataclass(frozen=True)
class ProfessionalExperienceInfo:
    """Section C: Structured work history, internships, dates, and duration."""

    experience_entries: ExtractedField
    internship_details: ExtractedField
    total_calculable_duration: ExtractedField


@dataclass(frozen=True)
class TechnicalSkillsInfo:
    """Section D: Office productivity, accounting software, and technical tools."""

    microsoft_word: ExtractedField
    microsoft_excel: ExtractedField
    microsoft_powerpoint: ExtractedField
    computer_literacy: ExtractedField
    accounting_software: ExtractedField
    other_technical_skills: ExtractedField


@dataclass(frozen=True)
class CommunicationLanguagesInfo:
    """Section E: Languages, proficiency, customer service, and communication evidence."""

    languages_and_proficiency: ExtractedField
    customer_service_experience: ExtractedField
    presentation_and_communication_evidence: ExtractedField


@dataclass(frozen=True)
class BankingFinanceKnowledgeInfo:
    """Section F: Banking, accounting, credit, deposits, KYC/AML, and compliance evidence."""

    accounting: ExtractedField
    financial_services: ExtractedField
    banking_operations: ExtractedField
    loans_and_credit: ExtractedField
    deposits_and_savings: ExtractedField
    kyc_and_aml: ExtractedField
    financial_compliance: ExtractedField


@dataclass(frozen=True)
class AchievementsInfo:
    """Section G: Awards, academic honors, leadership, volunteering, and metrics."""

    awards: ExtractedField
    academic_achievements: ExtractedField
    leadership_activities: ExtractedField
    volunteering: ExtractedField
    extracurricular_activities: ExtractedField
    measurable_accomplishments: ExtractedField


@dataclass(frozen=True)
class ExtractedCVData:
    """Complete structured representation of extracted CV information."""

    filename: str
    is_scanned_pdf: bool
    extraction_status_summary: str
    ocr_notice: str | None
    detected_sections: tuple[str, ...]
    missing_sections: tuple[str, ...]
    unusual_layout_notes: tuple[str, ...]
    personal_and_contact: PersonalContactInfo
    educational_qualifications: EducationalQualifications
    professional_experience: ProfessionalExperienceInfo
    technical_skills: TechnicalSkillsInfo
    communication_and_languages: CommunicationLanguagesInfo
    banking_and_finance_knowledge: BankingFinanceKnowledgeInfo
    achievements: AchievementsInfo

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete extracted CV payload to a JSON-compatible dictionary."""
        return asdict(self)


def _normalize_heading_text(text: str) -> str:
    """Normalize a line for section-heading comparison."""
    cleaned = re.sub(r"[:|\-–—•]+$", "", text.strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.lower()


def _match_section_heading(line: TextLineInfo) -> str | None:
    """Return canonical section name if the line behaves like a section heading."""
    raw = line.text.strip()
    if not raw or len(raw) > 55 or len(raw.split()) > 6:
        return None
    if "@" in raw or re.search(r"\d{4}", raw):
        return None

    normalized = _normalize_heading_text(raw)
    for section_key, aliases in SECTION_ALIASES.items():
        if normalized in aliases:
            return section_key
    return None


def _segment_lines_by_section(
    lines: tuple[TextLineInfo, ...],
) -> tuple[dict[str, list[TextLineInfo]], tuple[str, ...]]:
    """
    Group document lines into canonical sections while tracking order of appearance.

    Lines before the first recognized heading are placed under 'header'.
    """
    sections: dict[str, list[TextLineInfo]] = {"header": []}
    detected_order: list[str] = []
    current_section = "header"

    for line in lines:
        matched = _match_section_heading(line)
        if matched:
            current_section = matched
            if matched not in detected_order:
                detected_order.append(matched)
            sections.setdefault(matched, [])
            continue
        sections.setdefault(current_section, []).append(line)

    return sections, tuple(detected_order)


def _unique_pages(lines: list[TextLineInfo]) -> tuple[int, ...]:
    """Return sorted unique 1-indexed page numbers from a list of lines."""
    return tuple(sorted({ln.page_number for ln in lines}))


def _not_found(field_name: str, uncertainty: str | None = None) -> ExtractedField:
    """Helper for missing fields."""
    return ExtractedField(
        field_name=field_name,
        value=None,
        source_pages=(),
        status="not_found",
        uncertainty=uncertainty,
    )


def _ocr_blocked(field_name: str) -> ExtractedField:
    """Helper when a scanned PDF prevents text extraction."""
    return ExtractedField(
        field_name=field_name,
        value=None,
        source_pages=(),
        status="not_extracted_ocr_required",
        uncertainty="Scanned image PDF detected; OCR support is not currently implemented.",
    )


def _extract_personal_contact(
    lines: tuple[TextLineInfo, ...],
    sections: dict[str, list[TextLineInfo]],
) -> PersonalContactInfo:
    """Extract candidate name, email, telephone, and location from header/contact lines."""
    page1_top = [ln for ln in lines if ln.page_number == 1][:10]
    header_and_personal = sections.get("header", []) + sections.get("personal", [])
    contact_pool = list(dict.fromkeys(header_and_personal)) if header_and_personal else page1_top

    # 1. Candidate Name
    name_candidates: list[tuple[float, TextLineInfo]] = []
    for idx, ln in enumerate(contact_pool):
        txt = ln.text.strip()
        lower = txt.lower()
        if not txt or lower in IGNORED_NAME_HEADERS:
            continue
        if _match_section_heading(ln) is not None:
            continue
        if EMAIL_RE.search(txt) or PHONE_RE.search(txt) or "http" in lower or "linkedin.com" in lower:
            continue
        if any(lbl in lower for lbl in ("address:", "location:", "email:", "phone:", "tel:", "mobile:", "dob:", "nic:")):
            continue
        if re.search(r"\d", txt):
            continue

        # Handle explicit "Name: ..." label
        explicit_match = re.match(r"^(?:full\s+)?name\s*[:\-]\s*(.+)$", txt, re.IGNORECASE)
        if explicit_match:
            candidate_txt = explicit_match.group(1).strip()
            if 1 <= len(candidate_txt.split()) <= 5:
                name_field = ExtractedField(
                    field_name="Candidate Name",
                    value=candidate_txt,
                    source_pages=(ln.page_number,),
                    status="extracted",
                    uncertainty=None,
                )
                break
        words = txt.split()
        if 2 <= len(words) <= 5 and all(re.match(r"^[A-Za-z.'-]+$", w) for w in words):
            score = ln.max_font_size + (2.0 if ln.is_bold else 0.0) - (idx * 0.25)
            name_candidates.append((score, ln))
    else:
        if name_candidates:
            name_candidates.sort(key=lambda item: item[0], reverse=True)
            best_score, best_line = name_candidates[0]
            uncertainty = None
            status = "extracted"
            if len(name_candidates) > 1 and abs(best_score - name_candidates[1][0]) < 0.5:
                status = "ambiguous"
                uncertainty = (
                    f"Multiple top lines resembled a name ('{best_line.text}' vs '{name_candidates[1][1].text}'); "
                    "selected the highest-ranked top line."
                )
            name_field = ExtractedField(
                field_name="Candidate Name",
                value=best_line.text.strip(),
                source_pages=(best_line.page_number,),
                status=status,
                uncertainty=uncertainty,
            )
        else:
            name_field = _not_found(
                "Candidate Name",
                "No clear candidate name line was identified near the top of page 1.",
            )

    # 2. Email Address
    emails_found: list[str] = []
    email_pages: list[int] = []
    for ln in lines:
        for match in EMAIL_RE.findall(ln.text):
            if match not in emails_found:
                emails_found.append(match)
                email_pages.append(ln.page_number)

    if emails_found:
        email_uncertainty = (
            "Multiple email addresses found in CV." if len(emails_found) > 1 else None
        )
        email_field = ExtractedField(
            field_name="Email Address",
            value=emails_found[0] if len(emails_found) == 1 else emails_found,
            source_pages=tuple(sorted(set(email_pages))),
            status="extracted",
            uncertainty=email_uncertainty,
        )
    else:
        email_field = _not_found("Email Address")

    # 3. Telephone Number
    phones_found: list[str] = []
    phone_pages: list[int] = []
    for ln in contact_pool:
        cleaned_line = DATE_RANGE_RE.sub(" ", ln.text)
        for match in PHONE_RE.findall(cleaned_line):
            digits = re.sub(r"\D", "", match)
            if 7 <= len(digits) <= 15:
                normalized = re.sub(r"\s+", " ", match.strip())
                if normalized not in phones_found:
                    phones_found.append(normalized)
                    phone_pages.append(ln.page_number)

    if phones_found:
        phone_uncertainty = (
            "Multiple telephone numbers found." if len(phones_found) > 1 else None
        )
        phone_field = ExtractedField(
            field_name="Telephone Number",
            value=phones_found[0] if len(phones_found) == 1 else phones_found,
            source_pages=tuple(sorted(set(phone_pages))),
            status="extracted",
            uncertainty=phone_uncertainty,
        )
    else:
        phone_field = _not_found("Telephone Number")

    # 4. Location
    location_value: str | None = None
    location_pages: list[int] = []
    location_uncertainty: str | None = None

    for ln in contact_pool:
        loc_match = re.match(
            r"^(?:address|location|residence|city|based in)\s*[:\-]\s*(.+)$",
            ln.text.strip(),
            re.IGNORECASE,
        )
        if loc_match:
            location_value = loc_match.group(1).strip()
            location_pages.append(ln.page_number)
            break

    if not location_value:
        # Look for clean City, Country or City-style contact header segments
        for ln in contact_pool:
            if EMAIL_RE.search(ln.text) or "http" in ln.text.lower():
                parts = [p.strip() for p in re.split(r"[|•·]", ln.text) if p.strip()]
                for part in parts:
                    if "@" in part or PHONE_RE.search(part) or "linkedin" in part.lower():
                        continue
                    if "," in part and 2 <= len(part.split()) <= 6 and not re.search(r"\d{4}", part):
                        location_value = part
                        location_pages.append(ln.page_number)
                        break
                if location_value:
                    break
            elif (
                "," in ln.text
                and ln.text != (name_field.value if isinstance(name_field.value, str) else "")
                and not _match_section_heading(ln)
                and 2 <= len(ln.text.split()) <= 7
                and not re.search(r"\b(?:university|college|school|bank|ltd|plc|gpa|diploma|degree)\b", ln.text, re.IGNORECASE)
            ):
                location_value = ln.text.strip()
                location_pages.append(ln.page_number)
                location_uncertainty = "Inferred from header contact line rather than an explicit 'Location:' label."
                break

    if location_value:
        location_field = ExtractedField(
            field_name="Location",
            value=location_value,
            source_pages=tuple(sorted(set(location_pages))),
            status="partial" if location_uncertainty else "extracted",
            uncertainty=location_uncertainty,
        )
    else:
        location_field = _not_found(
            "Location",
            "No explicit address or location was detected in the contact header.",
        )

    return PersonalContactInfo(
        candidate_name=name_field,
        email_address=email_field,
        telephone_number=phone_field,
        location=location_field,
    )


def _extract_subject_grade(lines: list[TextLineInfo], subject_pattern: str) -> tuple[list[str], tuple[int, ...]]:
    """Find subject-grade mentions such as 'Mathematics - A' or 'O/L English: B'."""
    matches: list[str] = []
    pages: list[int] = []
    # Pattern 1: Subject followed by grade/score
    fwd_re = re.compile(
        rf"\b({subject_pattern})\b\s*(?:[:\-–—]|grade|result)?\s*([A-F][+\-]?|S|C|W|Pass|Credit|Distinction|\d(?:\.\d)?(?:/\d(?:\.\d)?)?)\b",
        re.IGNORECASE,
    )
    # Pattern 2: Grade followed by subject (rare, e.g., "'A' pass in Mathematics")
    rev_re = re.compile(
        rf"\b([A-F][+\-]?|Credit|Distinction)\s+(?:pass\s+)?in\s+({subject_pattern})\b",
        re.IGNORECASE,
    )
    for ln in lines:
        for m in fwd_re.finditer(ln.text):
            formatted = f"{m.group(1).strip()} - {m.group(2).strip()}"
            if formatted not in matches:
                matches.append(formatted)
                pages.append(ln.page_number)
        for m in rev_re.finditer(ln.text):
            formatted = f"{m.group(2).strip()} - {m.group(1).strip()}"
            if formatted not in matches:
                matches.append(formatted)
                pages.append(ln.page_number)
    return matches, tuple(sorted(set(pages)))


def _extract_education(
    lines: tuple[TextLineInfo, ...],
    sections: dict[str, list[TextLineInfo]],
) -> EducationalQualifications:
    """Extract O/L, A/L, English, Math, Degrees, Diplomas, and Professional/Finance qualifications."""
    edu_lines = sections.get("education", []) + sections.get("professional_qualifications", [])
    search_pool = edu_lines if edu_lines else list(lines)

    # Helper to gather contextual block lines around exam keywords
    def collect_exam_block(exam_re: re.Pattern[str]) -> tuple[list[str], list[TextLineInfo]]:
        captured_texts: list[str] = []
        captured_lines: list[TextLineInfo] = []
        idx = 0
        while idx < len(search_pool):
            ln = search_pool[idx]
            if exam_re.search(ln.text):
                block_parts = [ln.text]
                captured_lines.append(ln)
                # Look ahead up to 6 lines if they contain subjects/grades and not a new major heading/degree
                j = idx + 1
                while j < min(len(search_pool), idx + 7):
                    nxt = search_pool[j]
                    if re.search(
                        r"\b(?:g\.?c\.?e\.?\s*(?:o/l|a/l)|ordinary\s+level|advanced\s+level|b\.?sc|bba|b\.?com|m\.?sc|mba|diploma|cima|acca|cfa)\b",
                        nxt.text,
                        re.IGNORECASE,
                    ):
                        break
                    if re.search(
                        r"(?:[:\-–—]\s*[A-FSW]\b|\b\d+\s*[A-FS]\b|z-?score|mathematics|english|accounting|economics|commerce|business|science|sinhala|tamil|ict|index)",
                        nxt.text,
                        re.IGNORECASE,
                    ):
                        block_parts.append(nxt.text)
                        captured_lines.append(nxt)
                        j += 1
                    else:
                        break
                captured_texts.append(" | ".join(block_parts))
                idx = j
            else:
                idx += 1
        return captured_texts, captured_lines

    ol_re = re.compile(r"\b(?:g\.?c\.?e\.?\s*\(?o/l\)?|gce\s*o/l|o/l\b|ordinary\s+level)\b", re.IGNORECASE)
    al_re = re.compile(r"\b(?:g\.?c\.?e\.?\s*\(?a/l\)?|gce\s*a/l|a/l\b|advanced\s+level)\b", re.IGNORECASE)

    grade_evidence_re = re.compile(
        r"(?:\b\d+\s*[A-FS](?:'s|s)?\b"
        r"|[:\-–—]\s*[A-FS](?![/.])\b"
        r"|\b[A-FS]\s+(?:pass|grade)\b"
        r"|\b(?:z-?score|distinction|credit\s+pass|merit\s+pass)\b)",
        re.IGNORECASE,
    )

    ol_blocks, ol_lines = collect_exam_block(ol_re)
    if ol_blocks:
        has_grades = any(grade_evidence_re.search(b) for b in ol_blocks)
        ol_field = ExtractedField(
            field_name="G.C.E. O/L Results",
            value=ol_blocks,
            source_pages=_unique_pages(ol_lines),
            status="extracted" if has_grades else "partial",
            uncertainty=None if has_grades else "G.C.E. O/L was mentioned, but specific grades could not be confirmed.",
        )
    else:
        ol_field = _not_found("G.C.E. O/L Results")

    al_blocks, al_lines = collect_exam_block(al_re)
    if al_blocks:
        has_grades = any(grade_evidence_re.search(b) for b in al_blocks)
        al_field = ExtractedField(
            field_name="G.C.E. A/L Results",
            value=al_blocks,
            source_pages=_unique_pages(al_lines),
            status="extracted" if has_grades else "partial",
            uncertainty=None if has_grades else "G.C.E. A/L was mentioned, but subject grades were not clearly listed.",
        )
    else:
        al_field = _not_found("G.C.E. A/L Results")

    # English & Mathematics specific results (never assumed if absent)
    eng_matches, eng_pages = _extract_subject_grade(
        search_pool,
        r"(?:general\s+)?english(?:\s+language|\s+literature)?|ielts|toefl",
    )
    if eng_matches:
        english_field = ExtractedField(
            field_name="English Results",
            value=eng_matches,
            source_pages=eng_pages,
            status="extracted",
            uncertainty=None,
        )
    else:
        english_field = _not_found(
            "English Results",
            "No explicit English examination grade (e.g., O/L English, General English, or IELTS) was stated.",
        )

    math_matches, math_pages = _extract_subject_grade(
        search_pool,
        r"(?:combined\s+)?math(?:ematics|s)?|business\s+(?:mathematics|statistics)",
    )
    if math_matches:
        math_field = ExtractedField(
            field_name="Mathematics Results",
            value=math_matches,
            source_pages=math_pages,
            status="extracted",
            uncertainty=None,
        )
    else:
        math_field = _not_found(
            "Mathematics Results",
            "No explicit Mathematics examination grade was stated.",
        )

    # Degrees
    degree_re = re.compile(
        r"\b(?:b\.?sc\.?|bba|b\.?com\.?|b\.?a\.?|m\.?sc\.?|mba|m\.?com\.?|bachelor(?:'s)?|master(?:'s)?|undergraduate|reading\s+for\s+(?:a\s+)?(?:b\.?sc|bba|degree))\b",
        re.IGNORECASE,
    )
    degree_entries: list[str] = []
    degree_lines: list[TextLineInfo] = []
    for idx, ln in enumerate(search_pool):
        if degree_re.search(ln.text):
            entry = ln.text
            # Append immediate university/GPA continuation line if relevant
            if idx + 1 < len(search_pool):
                nxt = search_pool[idx + 1]
                if re.search(r"\b(?:university|institute|college|gpa|class|honours|honors|expected|20\d{2})\b", nxt.text, re.IGNORECASE) and not degree_re.search(nxt.text):
                    entry = f"{entry} — {nxt.text}"
            if entry not in degree_entries:
                degree_entries.append(entry)
                degree_lines.append(ln)

    if degree_entries:
        has_gpa_or_class = any(re.search(r"(?:gpa|class|honours|honors|\d\.\d{1,2})", d, re.IGNORECASE) for d in degree_entries)
        degree_field = ExtractedField(
            field_name="Degrees",
            value=degree_entries,
            source_pages=_unique_pages(degree_lines),
            status="extracted",
            uncertainty=None if has_gpa_or_class else "Degree mentioned without explicit GPA or class standing.",
        )
    else:
        degree_field = _not_found("Degrees")

    # Diplomas (exclude IBSL banking diplomas that get captured under banking_finance_qualifications, or include both cleanly)
    diploma_re = re.compile(
        r"\b(?:higher\s+national\s+diploma|hnd|advanced\s+diploma|postgraduate\s+diploma|diploma\s+in\b)\b",
        re.IGNORECASE,
    )
    diploma_entries = [ln.text for ln in search_pool if diploma_re.search(ln.text)]
    diploma_lines = [ln for ln in search_pool if diploma_re.search(ln.text)]
    if diploma_entries:
        diploma_field = ExtractedField(
            field_name="Diplomas",
            value=list(dict.fromkeys(diploma_entries)),
            source_pages=_unique_pages(diploma_lines),
            status="extracted",
        )
    else:
        diploma_field = _not_found("Diplomas")

    # Professional qualifications (CIMA, ACCA, CA, CFA, AAT, FRM, CMA, CPA)
    prof_re = re.compile(
        r"\b(?:cima|acca|ca\s*sri\s*lanka|icasl|chartered\s+accountant|cfa|frm|aat|cma|cpa|cipm|slim|acma|cgma)\b",
        re.IGNORECASE,
    )
    prof_lines = [ln for ln in lines if prof_re.search(ln.text)]
    if prof_lines:
        prof_vals = list(dict.fromkeys(ln.text for ln in prof_lines))
        prof_field = ExtractedField(
            field_name="Professional Qualifications",
            value=prof_vals,
            source_pages=_unique_pages(prof_lines),
            status="extracted",
        )
    else:
        prof_field = _not_found("Professional Qualifications")

    # Banking & Finance-related qualifications
    bf_qual_re = re.compile(
        r"\b(?:ibsl|institute\s+of\s+bankers|dabf|cbf|iabf|dbf|diploma\s+in\s+(?:applied\s+)?banking|"
        r"certificate\s+in\s+banking|bloomberg\s+market\s+concepts|\bbmc\b|fmva|corporate\s+finance\s+institute|"
        r"nism|treasury\s+(?:management\s+)?certificat|credit\s+management\s+(?:diploma|certificat))\b",
        re.IGNORECASE,
    )
    bf_lines = [ln for ln in lines if bf_qual_re.search(ln.text)]
    if bf_lines:
        bf_vals = list(dict.fromkeys(ln.text for ln in bf_lines))
        bf_field = ExtractedField(
            field_name="Banking & Finance Qualifications",
            value=bf_vals,
            source_pages=_unique_pages(bf_lines),
            status="extracted",
        )
    else:
        bf_field = _not_found("Banking & Finance Qualifications")

    return EducationalQualifications(
        gce_ol_results=ol_field,
        gce_al_results=al_field,
        english_results=english_field,
        mathematics_results=math_field,
        degrees=degree_field,
        diplomas=diploma_field,
        professional_qualifications=prof_field,
        banking_finance_qualifications=bf_field,
    )


def _parse_single_date(token: str) -> tuple[int, int, bool] | None:
    """
    Parse a date token into (year, month, is_year_only).
    Returns None if token is ongoing ('Present') or unparseable.
    """
    cleaned = token.strip().lower().replace(".", "")
    if re.match(r"^(?:present|current|ongoing|till\s*date|to\s*date|now)$", cleaned):
        return None

    m_word = re.match(r"^([a-z]+)\s+(\d{4})$", cleaned)
    if m_word:
        month = MONTH_MAP.get(m_word.group(1))
        year = int(m_word.group(2))
        if month:
            return (year, month, False)

    m_slash = re.match(r"^(\d{1,2})/(\d{4})$", cleaned)
    if m_slash:
        month = int(m_slash.group(1))
        year = int(m_slash.group(2))
        if 1 <= month <= 12:
            return (year, month, False)

    m_iso = re.match(r"^(\d{4})-(\d{2})$", cleaned)
    if m_iso:
        year = int(m_iso.group(1))
        month = int(m_iso.group(2))
        if 1 <= month <= 12:
            return (year, month, False)

    m_year = re.match(r"^(\d{4})$", cleaned)
    if m_year:
        return (int(m_year.group(1)), 1, True)

    return None


def _compute_duration_from_range(date_str: str) -> tuple[int | None, str, str | None]:
    """
    Calculate duration in months only when dates permit reliable calculation.
    Returns (months_or_None, display_str, uncertainty_note).
    """
    m = DATE_RANGE_RE.search(date_str)
    if not m:
        return None, "Not calculable", "No parseable start and end dates found."

    start_raw, end_raw = m.group(1), m.group(2)
    start_parsed = _parse_single_date(start_raw)
    if start_parsed is None:
        return None, "Not calculable", "Start date could not be parsed."

    end_is_present = bool(re.match(r"^(?:present|current|ongoing|till\s*date|to\s*date|now)$", end_raw.strip(), re.IGNORECASE))
    if end_is_present:
        today = date.today()
        end_year, end_month, end_year_only = today.year, today.month, start_parsed[2]
    else:
        end_parsed = _parse_single_date(end_raw)
        if end_parsed is None:
            return None, "Not calculable", "End date could not be parsed."
        end_year, end_month, end_year_only = end_parsed

    start_year, start_month, start_year_only = start_parsed

    if start_year_only or end_year_only:
        year_diff = end_year - start_year
        if year_diff < 0:
            return None, "Invalid date range", "End year appears earlier than start year."
        return (
            None,
            "Year-only dates (months not calculated)",
            f"Only years were provided ('{start_raw} – {end_raw}'); exact month duration cannot be determined without guessing.",
        )

    months = (end_year - start_year) * 12 + (end_month - start_month) + 1
    if months <= 0:
        return None, "Invalid date range", "End date appears earlier than start date."

    years_part, rem_months = divmod(months, 12)
    if years_part and rem_months:
        disp = f"{years_part} yr(s) {rem_months} mo(s) ({months} months)"
    elif years_part:
        disp = f"{years_part} yr(s) ({months} months)"
    else:
        disp = f"{months} mo(s)"

    uncertainty = (
        f"Ongoing role calculated through {date.today().strftime('%b %Y')}."
        if end_is_present
        else None
    )
    return months, disp, uncertainty


def _split_role_and_company(header_text: str) -> tuple[str | None, str | None]:
    """Heuristically separate job title and company name from an experience header line."""
    cleaned = DATE_RANGE_RE.sub("", header_text).strip(" |–—-,")
    if not cleaned:
        return None, None

    # Check common separators: "Title | Company", "Title - Company", "Title at Company", "Title, Company"
    if re.search(r"\s+at\s+", cleaned, re.IGNORECASE):
        parts = re.split(r"\s+at\s+", cleaned, maxsplit=1, flags=re.IGNORECASE)
        return parts[0].strip(), parts[1].strip()

    for sep in (" | ", " – ", " — ", " - ", ", "):
        if sep in cleaned:
            left, right = [p.strip() for p in cleaned.split(sep, 1)]
            left_has_company = any(k in left.lower() for k in COMPANY_HINT_KEYWORDS)
            right_has_role = any(k in right.lower() for k in ROLE_TITLE_KEYWORDS)
            if left_has_company and right_has_role:
                return right, left
            return left, right

    lower = cleaned.lower()
    if any(k in lower for k in COMPANY_HINT_KEYWORDS) and not any(k in lower for k in ROLE_TITLE_KEYWORDS):
        return None, cleaned
    return cleaned, None


def _extract_experience(
    sections: dict[str, list[TextLineInfo]],
) -> ProfessionalExperienceInfo:
    """Extract structured employment/internship entries, dates, responsibilities, and duration."""
    exp_lines = sections.get("experience", [])
    if not exp_lines:
        return ProfessionalExperienceInfo(
            experience_entries=_not_found(
                "Experience Entries",
                "No Work Experience or Internships section was found in the CV.",
            ),
            internship_details=_not_found("Internship Details"),
            total_calculable_duration=_not_found("Total Experience Duration"),
        )

    entries: list[dict[str, Any]] = []
    current_entry: dict[str, Any] | None = None

    for ln in exp_lines:
        txt = ln.text.strip()
        is_bullet = bool(re.match(r"^[•●▪▫◦\-\*]\s+", txt))
        date_match = DATE_RANGE_RE.search(txt)

        if date_match and not is_bullet:
            if current_entry is not None:
                entries.append(current_entry)

            date_str = date_match.group(0).strip()
            months, dur_disp, dur_uncertainty = _compute_duration_from_range(date_str)
            title, company = _split_role_and_company(txt)
            is_intern = bool(re.search(r"\b(?:intern(?:ship)?|trainee|apprentice|placement)\b", txt, re.IGNORECASE))

            current_entry = {
                "job_title": title,
                "company_name": company,
                "is_internship": is_intern,
                "employment_dates": date_str,
                "duration_months": months,
                "duration_display": dur_disp,
                "responsibilities": [],
                "source_page": ln.page_number,
                "uncertainty": dur_uncertainty,
            }
        elif current_entry is not None:
            if is_bullet:
                resp = re.sub(r"^[•●▪▫◦\-\*]\s+", "", txt).strip()
                if resp:
                    current_entry["responsibilities"].append(resp)
            elif not current_entry["company_name"] and len(txt.split()) <= 8 and not txt.endswith("."):
                current_entry["company_name"] = txt
            elif not current_entry["job_title"] and len(txt.split()) <= 8 and not txt.endswith("."):
                current_entry["job_title"] = txt
                if re.search(r"\b(?:intern(?:ship)?|trainee|apprentice|placement)\b", txt, re.IGNORECASE):
                    current_entry["is_internship"] = True
            else:
                current_entry["responsibilities"].append(txt)
        else:
            # Handle experience entries where date isn't on the very first line
            if not is_bullet and (any(k in txt.lower() for k in ROLE_TITLE_KEYWORDS + COMPANY_HINT_KEYWORDS) or ln.is_bold):
                title, company = _split_role_and_company(txt)
                is_intern = bool(re.search(r"\b(?:intern(?:ship)?|trainee|apprentice|placement)\b", txt, re.IGNORECASE))
                current_entry = {
                    "job_title": title,
                    "company_name": company,
                    "is_internship": is_intern,
                    "employment_dates": None,
                    "duration_months": None,
                    "duration_display": "Not calculable",
                    "responsibilities": [],
                    "source_page": ln.page_number,
                    "uncertainty": "Employment dates were not found alongside this role.",
                }

    if current_entry is not None:
        entries.append(current_entry)

    # Flag missing title or company per entry
    for entry in entries:
        notes: list[str] = []
        if entry.get("uncertainty"):
            notes.append(entry["uncertainty"])
        if not entry.get("job_title"):
            notes.append("Job title could not be isolated unambiguously.")
        if not entry.get("company_name"):
            notes.append("Company name could not be isolated unambiguously.")
        entry["uncertainty"] = " ".join(notes) if notes else None

    if not entries:
        raw_snippets = [ln.text for ln in exp_lines[:10]]
        return ProfessionalExperienceInfo(
            experience_entries=ExtractedField(
                field_name="Experience Entries",
                value=raw_snippets,
                source_pages=_unique_pages(exp_lines),
                status="ambiguous",
                uncertainty="Experience section found, but structured role/date boundaries could not be separated cleanly.",
            ),
            internship_details=_not_found("Internship Details"),
            total_calculable_duration=_not_found("Total Experience Duration"),
        )

    exp_pages = tuple(sorted({e["source_page"] for e in entries}))
    has_any_uncertainty = any(e.get("uncertainty") for e in entries)
    exp_field = ExtractedField(
        field_name="Experience Entries",
        value=entries,
        source_pages=exp_pages,
        status="partial" if has_any_uncertainty else "extracted",
        uncertainty=(
            "One or more entries had incomplete dates, year-only dates, or unclear title/company splits."
            if has_any_uncertainty
            else None
        ),
    )

    internships = [e for e in entries if e["is_internship"]]
    if internships:
        intern_field = ExtractedField(
            field_name="Internship Details",
            value=internships,
            source_pages=tuple(sorted({e["source_page"] for e in internships})),
            status="extracted",
        )
    else:
        intern_field = _not_found("Internship Details")

    calculable_months = [e["duration_months"] for e in entries if isinstance(e.get("duration_months"), int)]
    if calculable_months:
        total_m = sum(calculable_months)
        yrs, rem = divmod(total_m, 12)
        dur_text = f"{yrs} yr(s) {rem} mo(s) ({total_m} months total)" if yrs else f"{total_m} month(s) total"
        uncalculable_count = len(entries) - len(calculable_months)
        dur_unc = (
            f"Calculated across {len(calculable_months)} of {len(entries)} role(s); "
            f"{uncalculable_count} role(s) lacked month-level dates. Potential overlapping roles are summed directly."
            if uncalculable_count > 0 or len(calculable_months) > 1
            else None
        )
        duration_field = ExtractedField(
            field_name="Total Experience Duration",
            value=dur_text,
            source_pages=exp_pages,
            status="partial" if uncalculable_count > 0 else "extracted",
            uncertainty=dur_unc,
        )
    else:
        duration_field = _not_found(
            "Total Experience Duration",
            "Dates with month-level precision were not available to calculate experience duration.",
        )

    return ProfessionalExperienceInfo(
        experience_entries=exp_field,
        internship_details=intern_field,
        total_calculable_duration=duration_field,
    )


def _extract_keyword_evidence(
    field_name: str,
    lines: tuple[TextLineInfo, ...],
    patterns: tuple[tuple[str, str], ...],
    empty_uncertainty: str | None = None,
) -> ExtractedField:
    """
    Search document lines for explicit keyword/phrase evidence without guessing.
    Returns matched canonical labels and source page numbers.
    """
    matched_labels: list[str] = []
    matched_pages: list[int] = []
    evidence_lines: list[str] = []

    for ln in lines:
        for label, regex_pat in patterns:
            if re.search(regex_pat, ln.text, re.IGNORECASE):
                if label not in matched_labels:
                    matched_labels.append(label)
                if ln.page_number not in matched_pages:
                    matched_pages.append(ln.page_number)
                if ln.text not in evidence_lines and len(evidence_lines) < 6:
                    evidence_lines.append(ln.text)

    if not matched_labels:
        return _not_found(field_name, empty_uncertainty)

    return ExtractedField(
        field_name=field_name,
        value={"matched_terms": matched_labels, "evidence_lines": evidence_lines},
        source_pages=tuple(sorted(matched_pages)),
        status="extracted",
    )


def _extract_technical_skills(lines: tuple[TextLineInfo, ...]) -> TechnicalSkillsInfo:
    """Extract Microsoft Office tools, computer literacy, accounting software, and other skills."""
    ms_word = _extract_keyword_evidence(
        "Microsoft Word",
        lines,
        (
            ("Microsoft Word", r"\b(?:ms|microsoft)\s+word\b"),
            ("Word Processing", r"\bword\s+processing\b"),
            ("Word (Office context)", r"\bword\b(?=.*\b(?:excel|powerpoint|office)\b)|\b(?:excel|powerpoint|office)\b.*\bword\b"),
        ),
    )

    ms_excel = _extract_keyword_evidence(
        "Microsoft Excel",
        lines,
        (
            ("Microsoft Excel", r"\b(?:ms|microsoft)\s+excel\b|\bexcel\b"),
            ("Excel Functions (VLOOKUP/Pivot/Macros)", r"\b(?:vlookup|xlookup|pivot\s+tables?|excel\s+macros?|vba)\b"),
        ),
    )

    ms_ppt = _extract_keyword_evidence(
        "Microsoft PowerPoint",
        lines,
        (
            ("Microsoft PowerPoint", r"\b(?:ms|microsoft)?\s*power\s*point\b"),
        ),
    )

    comp_lit = _extract_keyword_evidence(
        "Computer Literacy",
        lines,
        (
            ("Microsoft Office / Office 365", r"\b(?:ms|microsoft)\s+office(?:\s+365|\s+suite)?\b"),
            ("Computer / IT Literacy", r"\b(?:computer\s+literacy|it\s+literacy|computer\s+skills|digital\s+literacy)\b"),
            ("Google Workspace", r"\bgoogle\s+(?:workspace|docs|sheets|slides)\b"),
        ),
    )

    acc_sw = _extract_keyword_evidence(
        "Accounting Software",
        lines,
        (
            ("QuickBooks", r"\bquickbooks\b"),
            ("Tally", r"\btally(?:\s+erp|\s+prime)?\b"),
            ("Sage", r"\bsage(?:\s+50|\s+pastel|\s+accounting)?\b"),
            ("Xero", r"\bxero\b"),
            ("SAP", r"\bsap(?:\s+fico|\s+erp)?\b"),
            ("Oracle Financials", r"\boracle\s+financials?\b"),
            ("MYOB", r"\bmyob\b"),
            ("Peachtree", r"\bpeachtree\b"),
            ("Zoho Books", r"\bzoho\s+books\b"),
        ),
    )

    other_tech = _extract_keyword_evidence(
        "Other Technical Skills",
        lines,
        (
            ("Python", r"\bpython\b"),
            ("SQL", r"\bsql\b|\bmysql\b|\bpostgresql\b"),
            ("Power BI", r"\bpower\s*bi\b"),
            ("Tableau", r"\btableau\b"),
            ("Bloomberg Terminal", r"\bbloomberg\b"),
            ("Reuters / Refinitiv", r"\b(?:reuters|refinitiv|eikon)\b"),
            ("SPSS / EViews / Stata / R", r"\b(?:spss|eviews|stata)\b"),
            ("Financial Modeling", r"\bfinancial\s+model(?:l)?ing\b"),
            ("Core Banking System", r"\b(?:finacle|temenos|t24|core\s+banking)\b"),
            ("ERP Systems", r"\berp\b"),
        ),
    )

    return TechnicalSkillsInfo(
        microsoft_word=ms_word,
        microsoft_excel=ms_excel,
        microsoft_powerpoint=ms_ppt,
        computer_literacy=comp_lit,
        accounting_software=acc_sw,
        other_technical_skills=other_tech,
    )


def _extract_communication_languages(
    lines: tuple[TextLineInfo, ...],
    sections: dict[str, list[TextLineInfo]],
) -> CommunicationLanguagesInfo:
    """Extract stated languages/proficiencies, customer service, and communication evidence."""
    lang_names = ("English", "Sinhala", "Tamil", "Hindi", "French", "German", "Mandarin", "Chinese", "Arabic", "Japanese", "Spanish")
    proficiency_re = re.compile(
        r"\b(native|mother\s+tongue|bilingual|fluent|proficient|professional\s+working|"
        r"full\s+professional|working\s+knowledge|intermediate|conversational|basic|elementary|"
        r"very\s+good|good|fair|oral\s*(?:&|and)\s*written|written\s*(?:&|and)\s*spoken|"
        r"c2|c1|b2|b1|a2|a1)\b",
        re.IGNORECASE,
    )

    lang_pool = sections.get("languages", [])
    # Fallback: scan lines explicitly mentioning language names near proficiency words or in bullet lists
    search_lines = lang_pool if lang_pool else [
        ln for ln in lines
        if any(re.search(rf"\b{lang}\b", ln.text, re.IGNORECASE) for lang in lang_names)
        and (
            proficiency_re.search(ln.text)
            or re.search(r"\b(?:languages?|fluent|speak|spoken|written)\b", ln.text, re.IGNORECASE)
        )
    ]

    extracted_langs: list[dict[str, Any]] = []
    lang_pages: list[int] = []
    seen_langs: set[str] = set()

    for ln in search_lines:
        for lang in lang_names:
            if re.search(rf"\b{lang}\b", ln.text, re.IGNORECASE):
                if lang in seen_langs:
                    continue
                seen_langs.add(lang)
                prof_matches = [m.group(0) for m in proficiency_re.finditer(ln.text)]
                proficiency_str = ", ".join(dict.fromkeys(prof_matches)) if prof_matches else "Not explicitly stated"
                extracted_langs.append(
                    {
                        "language": lang,
                        "proficiency": proficiency_str,
                        "source_line": ln.text,
                        "source_page": ln.page_number,
                    }
                )
                lang_pages.append(ln.page_number)

    if extracted_langs:
        missing_prof = any(item["proficiency"] == "Not explicitly stated" for item in extracted_langs)
        lang_field = ExtractedField(
            field_name="Languages & Proficiency",
            value=extracted_langs,
            source_pages=tuple(sorted(set(lang_pages))),
            status="partial" if missing_prof else "extracted",
            uncertainty=(
                "One or more languages were listed without an explicit proficiency level."
                if missing_prof
                else None
            ),
        )
    else:
        lang_field = _not_found(
            "Languages & Proficiency",
            "No explicit language proficiency section or language statements were found (document language is not assumed as stated proficiency).",
        )

    cust_service = _extract_keyword_evidence(
        "Customer Service Experience",
        lines,
        (
            ("Customer Service / Relations", r"\bcustomer\s+(?:service|relations|support|care|handling|inquiries|queries)\b"),
            ("Client Onboarding / Handling", r"\bclient\s+(?:service|relations|handling|onboarding|support|facing)\b"),
            ("Front Office / Teller", r"\b(?:front\s+office|front\s+desk|bank\s+teller|teller|cashier|call\s+cent(?:er|re))\b"),
        ),
    )

    comm_evidence = _extract_keyword_evidence(
        "Presentation & Communication Evidence",
        lines,
        (
            ("Presentations", r"\bpresentations?\b|\bpresented\b"),
            ("Public Speaking / Debating / Toastmasters", r"\b(?:public\s+speaking|toastmasters|debat(?:e|ing)|oratory)\b"),
            ("Report Writing / Briefings", r"\b(?:report\s+writing|stakeholder\s+communication|team\s+briefings?|written\s+communication|interpersonal)\b"),
        ),
    )

    return CommunicationLanguagesInfo(
        languages_and_proficiency=lang_field,
        customer_service_experience=cust_service,
        presentation_and_communication_evidence=comm_evidence,
    )


def _extract_banking_finance_knowledge(lines: tuple[TextLineInfo, ...]) -> BankingFinanceKnowledgeInfo:
    """Extract explicit domain evidence across the seven banking & finance knowledge areas."""
    return BankingFinanceKnowledgeInfo(
        accounting=_extract_keyword_evidence(
            "Accounting",
            lines,
            (
                ("Accounting / Bookkeeping", r"\b(?:accounting|bookkeeping|double[- ]entry|general\s+ledger)\b"),
                ("Financial Statements", r"\b(?:financial\s+statements?|balance\s+sheet|income\s+statement|profit\s+(?:&|and)\s+loss|cash\s+flow)\b"),
                ("Payables / Receivables / Reconciliation", r"\b(?:accounts?\s+payable|accounts?\s+receivable|bank\s+reconciliation|reconciliation)\b"),
                ("Auditing & Standards (IFRS/LKAS/GAAP)", r"\b(?:auditing|internal\s+audit|external\s+audit|ifrs|lkas|gaap)\b"),
            ),
        ),
        financial_services=_extract_keyword_evidence(
            "Financial Services",
            lines,
            (
                ("Financial Services", r"\bfinancial\s+services\b"),
                ("Retail / Corporate / Investment Banking", r"\b(?:retail\s+banking|corporate\s+banking|investment\s+banking|commercial\s+banking)\b"),
                ("Wealth / Asset Management / Capital Markets", r"\b(?:wealth\s+management|asset\s+management|capital\s+markets|equity\s+research|brokerage)\b"),
                ("Leasing / Microfinance / Insurance", r"\b(?:leasing|microfinance|insurance|hire\s+purchase)\b"),
            ),
        ),
        banking_operations=_extract_keyword_evidence(
            "Banking Operations",
            lines,
            (
                ("Banking / Branch Operations", r"\b(?:banking\s+operations|branch\s+operations|back\s+office|teller\s+operations)\b"),
                ("Account Opening / Remittances / Clearing", r"\b(?:account\s+opening|remittances?|cheque\s+clearing|clearing|fund\s+transfers?)\b"),
                ("Payment Rails (SWIFT/RTGS/CEFT)", r"\b(?:swift|rtgs|ceft|slips|treasury\s+operations)\b"),
            ),
        ),
        loans_and_credit=_extract_keyword_evidence(
            "Loans & Credit",
            lines,
            (
                ("Loans / Lending / Mortgages", r"\b(?:loans?|lending|mortgages?|housing\s+loan|personal\s+loan|sme\s+lending)\b"),
                ("Credit Analysis / Underwriting", r"\b(?:credit\s+analysis|credit\s+evaluation|credit\s+appraisal|underwriting|credit\s+risk)\b"),
                ("Recoveries / Collateral / NPL", r"\b(?:loan\s+recover(?:y|ies)|collateral|non[- ]performing|\bnpl\b)\b"),
            ),
        ),
        deposits_and_savings=_extract_keyword_evidence(
            "Deposits & Savings",
            lines,
            (
                ("Fixed / Term Deposits", r"\b(?:fixed\s+deposits?|term\s+deposits?|time\s+deposits?)\b"),
                ("Savings & Current Accounts (CASA)", r"\b(?:savings\s+accounts?|current\s+accounts?|casa|deposit\s+mobilization|deposits?)\b"),
            ),
        ),
        kyc_and_aml=_extract_keyword_evidence(
            "KYC & AML",
            lines,
            (
                ("KYC (Know Your Customer)", r"\b(?:kyc|know\s+your\s+customer)\b"),
                ("AML (Anti-Money Laundering)", r"\b(?:aml|anti[- ]money\s+laundering)\b"),
                ("CDD / EDD / Sanctions Screening", r"\b(?:customer\s+due\s+diligence|\bcdd\b|\bedd\b|sanctions\s+screening|suspicious\s+transaction)\b"),
            ),
        ),
        financial_compliance=_extract_keyword_evidence(
            "Financial Compliance",
            lines,
            (
                ("Regulatory Compliance", r"\b(?:financial\s+compliance|regulatory\s+compliance|compliance)\b"),
                ("Central Bank / Regulatory Frameworks", r"\b(?:central\s+bank|cbsl|basel|fatca|pci[- ]dss)\b"),
                ("Risk & Internal Controls", r"\b(?:risk\s+management|internal\s+controls?|corporate\s+governance)\b"),
            ),
        ),
    )


def _extract_achievements(
    lines: tuple[TextLineInfo, ...],
    sections: dict[str, list[TextLineInfo]],
) -> AchievementsInfo:
    """Extract awards, academic honors, leadership, volunteering, extracurriculars, and metrics."""
    awards = _extract_keyword_evidence(
        "Awards",
        lines,
        (
            ("Awards / Prizes / Scholarships", r"\b(?:award(?:ed)?|prize|scholarship|gold\s+medal|silver\s+medal|medal|winner|runner[- ]up|champion|best\s+performer|merit)\b"),
        ),
    )

    academic_ach = _extract_keyword_evidence(
        "Academic Achievements",
        lines,
        (
            ("Honors / Dean's List / Class Standing", r"\b(?:dean'?s\s+list|first\s+class|second\s+upper|distinction|valedictorian|academic\s+excellence|top\s+\d+%)\b"),
        ),
    )

    leadership = _extract_keyword_evidence(
        "Leadership Activities",
        lines,
        (
            ("Leadership Roles", r"\b(?:president|vice\s+president|captain|vice\s+captain|head\s+prefect|senior\s+prefect|prefect|secretary|treasurer|committee\s+chair|team\s+lead(?:er)?|project\s+lead)\b"),
        ),
    )

    volunteering = _extract_keyword_evidence(
        "Volunteering",
        lines,
        (
            ("Volunteering & Community Service", r"\b(?:volunteer(?:ing|ed)?|rotaract|leo\s+club|interact\s+club|aiesec|community\s+service|red\s+cross|charity|csr)\b"),
        ),
    )

    extracurricular = _extract_keyword_evidence(
        "Extracurricular Activities",
        lines,
        (
            ("Clubs, Societies & Competitions", r"\b(?:society|association|finance\s+club|investment\s+club|case\s+competition|hackathon|debating\s+team|choir|drama)\b"),
            ("Sports & Athletics", r"\b(?:athletics|cricket|rugby|football|basketball|netball|swimming|badminton|tennis|chess|sports\s+team)\b"),
        ),
    )

    # Measurable accomplishments: lines with concrete quantified outcomes (percentages, currency, counts with action context)
    quant_re = re.compile(
        r"(?:\b\d+(?:\.\d+)?%|\b(?:lkr|rs\.?|usd|\$|gbp|£|eur|€)\s?\d[\d,]*(?:\.\d+)?[kmb]?|\b\d{2,}\+?\s+(?:customers?|clients?|accounts?|reports?|transactions?|students?|members?|files?|invoices?))",
        re.IGNORECASE,
    )
    # Restrict to bullet points, experience, or achievement sections to avoid matching phone numbers/years/GPA
    ach_pool = sections.get("experience", []) + sections.get("achievements", [])
    if not ach_pool:
        ach_pool = list(lines)

    quant_matches: list[str] = []
    quant_pages: list[int] = []
    for ln in ach_pool:
        if PHONE_RE.search(ln.text) and not quant_re.search(ln.text):
            continue
        if quant_re.search(ln.text):
            cleaned = re.sub(r"^[•●▪▫◦\-\*]\s+", "", ln.text).strip()
            if cleaned not in quant_matches:
                quant_matches.append(cleaned)
                quant_pages.append(ln.page_number)

    if quant_matches:
        measurable_field = ExtractedField(
            field_name="Measurable Accomplishments",
            value=quant_matches,
            source_pages=tuple(sorted(set(quant_pages))),
            status="extracted",
        )
    else:
        measurable_field = _not_found(
            "Measurable Accomplishments",
            "No quantified achievements (percentages, financial figures, or volume metrics) were found.",
        )

    return AchievementsInfo(
        awards=awards,
        academic_achievements=academic_ach,
        leadership_activities=leadership,
        volunteering=volunteering,
        extracurricular_activities=extracurricular,
        measurable_accomplishments=measurable_field,
    )


def extract_cv_information(document: ProcessedPDFDocument) -> ExtractedCVData:
    """
    Extract structured candidate CV fields from a ProcessedPDFDocument.

    Handles scanned/image-only PDFs honestly without inventing data.
    """
    layout_notes = list(document.document_analysis.unusual_layout_indicators)

    # Handle scanned PDFs containing images instead of selectable text
    if document.is_scanned_pdf or not document.has_extractable_text:
        ocr_msg = (
            "This PDF appears to be a scanned or image-based document without selectable text. "
            "OCR support is not currently implemented, so candidate fields could not be extracted."
        )
        return ExtractedCVData(
            filename=document.filename,
            is_scanned_pdf=True,
            extraction_status_summary=ocr_msg,
            ocr_notice=ocr_msg,
            detected_sections=(),
            missing_sections=CORE_EXPECTED_SECTIONS,
            unusual_layout_notes=tuple(layout_notes),
            personal_and_contact=PersonalContactInfo(
                candidate_name=_ocr_blocked("Candidate Name"),
                email_address=_ocr_blocked("Email Address"),
                telephone_number=_ocr_blocked("Telephone Number"),
                location=_ocr_blocked("Location"),
            ),
            educational_qualifications=EducationalQualifications(
                gce_ol_results=_ocr_blocked("G.C.E. O/L Results"),
                gce_al_results=_ocr_blocked("G.C.E. A/L Results"),
                english_results=_ocr_blocked("English Results"),
                mathematics_results=_ocr_blocked("Mathematics Results"),
                degrees=_ocr_blocked("Degrees"),
                diplomas=_ocr_blocked("Diplomas"),
                professional_qualifications=_ocr_blocked("Professional Qualifications"),
                banking_finance_qualifications=_ocr_blocked("Banking & Finance Qualifications"),
            ),
            professional_experience=ProfessionalExperienceInfo(
                experience_entries=_ocr_blocked("Experience Entries"),
                internship_details=_ocr_blocked("Internship Details"),
                total_calculable_duration=_ocr_blocked("Total Experience Duration"),
            ),
            technical_skills=TechnicalSkillsInfo(
                microsoft_word=_ocr_blocked("Microsoft Word"),
                microsoft_excel=_ocr_blocked("Microsoft Excel"),
                microsoft_powerpoint=_ocr_blocked("Microsoft PowerPoint"),
                computer_literacy=_ocr_blocked("Computer Literacy"),
                accounting_software=_ocr_blocked("Accounting Software"),
                other_technical_skills=_ocr_blocked("Other Technical Skills"),
            ),
            communication_and_languages=CommunicationLanguagesInfo(
                languages_and_proficiency=_ocr_blocked("Languages & Proficiency"),
                customer_service_experience=_ocr_blocked("Customer Service Experience"),
                presentation_and_communication_evidence=_ocr_blocked("Presentation & Communication Evidence"),
            ),
            banking_and_finance_knowledge=BankingFinanceKnowledgeInfo(
                accounting=_ocr_blocked("Accounting"),
                financial_services=_ocr_blocked("Financial Services"),
                banking_operations=_ocr_blocked("Banking Operations"),
                loans_and_credit=_ocr_blocked("Loans & Credit"),
                deposits_and_savings=_ocr_blocked("Deposits & Savings"),
                kyc_and_aml=_ocr_blocked("KYC & AML"),
                financial_compliance=_ocr_blocked("Financial Compliance"),
            ),
            achievements=AchievementsInfo(
                awards=_ocr_blocked("Awards"),
                academic_achievements=_ocr_blocked("Academic Achievements"),
                leadership_activities=_ocr_blocked("Leadership Activities"),
                volunteering=_ocr_blocked("Volunteering"),
                extracurricular_activities=_ocr_blocked("Extracurricular Activities"),
                measurable_accomplishments=_ocr_blocked("Measurable Accomplishments"),
            ),
        )

    sections, detected_sections = _segment_lines_by_section(document.text_lines)
    missing_sections = tuple(s for s in CORE_EXPECTED_SECTIONS if s not in detected_sections)

    if not detected_sections:
        layout_notes.append(
            "No standard section headings (e.g., Education, Experience, Skills) were detected; "
            "extraction fell back to document-wide pattern matching."
        )

    personal = _extract_personal_contact(document.text_lines, sections)
    education = _extract_education(document.text_lines, sections)
    experience = _extract_experience(sections)
    tech_skills = _extract_technical_skills(document.text_lines)
    comm_langs = _extract_communication_languages(document.text_lines, sections)
    bf_knowledge = _extract_banking_finance_knowledge(document.text_lines)
    achievements = _extract_achievements(document.text_lines, sections)

    summary = (
        f"Structured extraction completed locally across {document.page_count} page(s). "
        f"Detected {len(detected_sections)} section heading group(s)."
    )
    if missing_sections:
        summary += f" Missing standard heading(s): {', '.join(missing_sections)}."

    return ExtractedCVData(
        filename=document.filename,
        is_scanned_pdf=False,
        extraction_status_summary=summary,
        ocr_notice=None,
        detected_sections=detected_sections,
        missing_sections=missing_sections,
        unusual_layout_notes=tuple(dict.fromkeys(layout_notes)),
        personal_and_contact=personal,
        educational_qualifications=education,
        professional_experience=experience,
        technical_skills=tech_skills,
        communication_and_languages=comm_langs,
        banking_and_finance_knowledge=bf_knowledge,
        achievements=achievements,
    )
