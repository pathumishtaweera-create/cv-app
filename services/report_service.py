"""
User-friendly 4-section CV evaluation report builder and in-memory PDF exporter.

Translates PyMuPDF layout diagnostics, rule-based extraction, language checks,
and the 9-category evaluation engine into clear, everyday English:
1. Your CV Score
2. What You Did Well
3. What Needs Improvement (Mistakes to Fix vs. Areas You Can Improve)
4. How to Improve Your CV (3-step pattern: What is wrong? / How to fix it? / Why does this matter?)

Preserves all 9 evaluation categories, weights, and scoring logic unchanged.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import html
import io
import re
import pymupdf

from config.settings import APP_NAME
from services.cv_extractor import ExtractedCVData
from services.evaluator import (
    CVEvaluationResult,
    STATUS_EVALUATED,
    STATUS_NOT_MENTIONED,
)
from services.language_checker import (
    LanguageFinding,
    LanguageQualityReport,
    WEAK_PASSIVE_PHRASES,
    analyze_language_quality,
)
from services.pdf_processor import ProcessedPDFDocument


SCORE_QUALITY_DISCLAIMER = (
    "This score reflects how well your CV presents your background for entry-level "
    "banking and finance jobs. It does not guarantee a job interview or offer."
)

SCORE_BENCHMARK_PERCENTAGE = 60

SCORE_ABOVE_BENCHMARK_NOTE = (
    "Your CV is at a good starting level for applying for jobs. "
    "A score of 60% or higher means your CV has reached a basic standard that may be "
    "sufficient to help you get considered for an interview. However, an interview is "
    "never guaranteed. Your qualifications, experience, the job requirements, and the "
    "employer's decision also matter."
)

SCORE_BENCHMARK_CLARIFICATION = (
    "Please note: 60% is this app's suggested CV-quality benchmark, "
    "not an official banking-industry requirement."
)


_FRIENDLY_FACTOR_TITLES: dict[str, str] = {
    "O/L Results": "G.C.E. O/L exam results",
    "A/L Results": "G.C.E. A/L exam results",
    "English Results": "English exam grade",
    "Mathematics Results": "Mathematics exam grade",
    "Degrees and Diplomas": "Degree or diploma",
    "Banking and Finance Qualifications": "Banking and finance qualifications",
    "Professional Qualifications": "Professional finance or accounting qualifications",
    "Banking Experience": "Banking work experience",
    "Finance Company Experience": "Finance company experience",
    "Internships": "Internship experience",
    "Customer Service Experience": "Customer service experience",
    "Cash Handling Experience": "Cash handling experience",
    "Administrative Experience": "Office and administrative experience",
    "Sales Experience": "Sales experience",
    "Employment Duration": "Length of work experience",
    "Relevance of Responsibilities": "How relevant your work experience is",
    "Microsoft Excel": "Microsoft Excel skills",
    "Microsoft Word": "Microsoft Word skills",
    "Microsoft PowerPoint": "Microsoft PowerPoint skills",
    "Computer Literacy": "General computer skills",
    "Data Entry": "Data entry skills",
    "Spreadsheet Skills": "Spreadsheet skills",
    "Accounting Software": "Accounting software skills",
    "Digital Banking Knowledge": "Digital banking knowledge",
    "English Proficiency": "English language skills",
    "English Proficiency Evidence": "English language skills",
    "Sinhala Proficiency": "Sinhala language skills",
    "Sinhala Proficiency Evidence": "Sinhala language skills",
    "Tamil Proficiency": "Tamil language skills",
    "Tamil Proficiency Evidence": "Tamil language skills",
    "Written Communication": "Written communication",
    "Written Communication Evidence": "Written communication",
    "Customer Communication": "Customer communication",
    "Customer Communication Experience": "Customer communication",
    "Presentation Experience": "Presentation experience",
    "Interpersonal Communication": "Teamwork and communication",
    "Interpersonal Communication Evidence": "Teamwork and communication",
    "Banking Operations Knowledge": "Banking operations knowledge",
    "Financial Services Knowledge": "Financial services knowledge",
    "Accounting Knowledge": "Accounting knowledge",
    "Loans and Credit Knowledge": "Loans and credit knowledge",
    "Deposits and Savings Knowledge": "Deposits and savings knowledge",
    "Financial Calculations": "Financial calculations",
    "Customer Relationship Knowledge": "Customer relationship skills",
    "KYC and AML Awareness": "KYC and AML knowledge",
    "Financial Compliance": "Financial rules and compliance knowledge",
    "Academic Achievements": "Academic achievements",
    "Professional Achievements": "Work achievements",
    "Awards and Recognition": "Awards and honors",
    "Leadership Activities": "Leadership experience",
    "Volunteering": "Volunteer work",
    "Extracurricular Activities": "Activities outside study",
    "Projects and Research": "Projects and research",
    "Measurable Outcomes": "Results with numbers or figures",
    "Measurable Accomplishments": "Results with numbers or figures",
    "Logical Section Arrangement": "Clear order of CV sections",
    "Clear Section Headings": "Clear section headings",
    "Contact Information Placement": "Contact details at the top",
    "Education Organization": "Well-organized education section",
    "Work Experience Organization": "Well-organized work experience",
    "Chronological Consistency": "Clear order of dates",
    "Information Completeness": "Complete core CV sections",
    "Relevant Information": "Focused, job-relevant details",
    "Appropriate CV Length": "Good CV length",
    "Spelling": "Correct spelling",
    "Grammar": "Correct grammar",
    "Sentence Construction": "Clear sentence structure",
    "Punctuation": "Clean punctuation",
    "Capitalization": "Proper capital letters",
    "Professional Vocabulary": "Professional wording",
    "Sentence Clarity": "How clearly you write",
    "Repeated Words": "No repeated words",
    "Consistency of Writing Style": "Consistent bullet-point style",
    "Font Consistency": "Consistent font styles",
    "Font Readability": "Easy-to-read text size",
    "Font Size Consistency": "Consistent font sizes",
    "Paragraph Spacing": "Even line spacing",
    "Section Spacing": "Clear spacing between sections",
    "Text Alignment": "Neat text alignment",
    "Margin Consistency": "Balanced page margins",
    "Bullet-Point Formatting": "Clean bullet points",
    "Text Overlap": "No overlapping or cut-off text",
    "Overall Neatness": "Clean overall appearance",
    "Page Layout and Readability": "Clean page layout",
}


@dataclass(frozen=True)
class StrengthItem:
    """Section 2 item: plain-English CV strength backed by actual CV evidence."""

    title: str
    evidence: str
    why_it_helps: str
    source_pages: tuple[int, ...]


@dataclass(frozen=True)
class ImprovementAreaItem:
    """Section 3 item: plain-English mistake or improvement area with example and next step."""

    heading: str
    explanation: str
    cv_example: str
    next_step: str
    is_error: bool
    page_numbers: tuple[int, ...]


@dataclass(frozen=True)
class SpecificCorrectionItem:
    """Section 4 item following the 3-step structure."""

    category_label: str
    is_error: bool
    original_cv_example: str
    identified_problem: str
    recommended_improvement: str
    reason: str
    page_number: int | None


@dataclass(frozen=True)
class CVEvaluationReport:
    """Complete 4-section user-friendly evaluation report."""

    application_name: str
    candidate_name: str | None
    filename: str
    generated_at: str
    overall_score: float
    total_possible_score: int
    classification: str
    classification_band: str
    overall_explanation: str
    score_interpretation_title: str
    score_interpretation_note: str
    score_benchmark_clarification: str
    disclaimer: str
    evaluation: CVEvaluationResult
    whats_good: tuple[StrengthItem, ...]
    what_needs_improvement: tuple[ImprovementAreaItem, ...]
    specific_corrections: tuple[SpecificCorrectionItem, ...]
    assessment_limitations: tuple[str, ...]


def classify_cv_score(overall_score: float, is_assessable: bool) -> tuple[str, str]:
    """Map an overall score out of 100 to its CV quality classification and band key."""
    if not is_assessable:
        return "Not Assessable (Scanned PDF)", "unavailable"
    if overall_score >= 90.0:
        return "Outstanding CV", "outstanding"
    if overall_score >= 80.0:
        return "Very Good CV", "very_good"
    if overall_score >= 70.0:
        return "Good CV", "good"
    if overall_score >= 60.0:
        return "Average CV", "average"
    if overall_score >= 50.0:
        return "Below Average CV", "below_average"
    return "Needs Significant Improvement", "needs_improvement"


def _build_score_interpretation_note(
    overall_score: float,
    is_assessable: bool,
) -> tuple[str, str, str]:
    """Return (title, interpretation_note, benchmark_clarification) for the 60% CV benchmark."""
    if not is_assessable:
        return (
            "What Your Score Means",
            (
                "Your CV could not be compared with this app's suggested 60% starting standard "
                "because readable text was not found in the PDF. Please save your CV as a regular "
                "text PDF and upload it again. Even with a strong CV score, an interview is never "
                "guaranteed because your qualifications, experience, the job requirements, and the "
                "employer's decision also matter."
            ),
            SCORE_BENCHMARK_CLARIFICATION,
        )

    if overall_score >= float(SCORE_BENCHMARK_PERCENTAGE):
        return (
            "What Your Score Means (60% or Higher)",
            SCORE_ABOVE_BENCHMARK_NOTE,
            SCORE_BENCHMARK_CLARIFICATION,
        )

    return (
        "What Your Score Means (Below 60%)",
        (
            "Your CV needs further improvement before it reaches this app's suggested 60% "
            "starting standard for applying for jobs. Follow the simple steps below to fix mistakes "
            "and strengthen your details. Reaching 60% or higher can help your CV meet a basic "
            "standard for consideration, though an interview is never guaranteed because your "
            "qualifications, experience, the job requirements, and the employer's decision also matter."
        ),
        SCORE_BENCHMARK_CLARIFICATION,
    )


def _build_overall_explanation(
    evaluation: CVEvaluationResult,
    classification: str,
) -> str:
    """Build a friendly, plain-English summary of the score without technical jargon."""
    if not evaluation.is_assessable:
        return (
            "We could not read text from this PDF because it appears to be a scanned image. "
            "Please save your CV directly as a text PDF from Word or Google Docs and upload it again."
        )

    score = evaluation.overall_score
    unavail = [c.category.title for c in evaluation.categories if c.status == "Unavailable"]
    missing_note = ""
    if unavail:
        missing_note = (
            f" Some sections were not found in your CV ({', '.join(unavail)}), "
            "so adding any real experience or skills you have there can raise your score."
        )

    if score >= 80.0:
        summary = (
            f"Your CV scored {score:.0f} out of 100 ({classification}). "
            "You present strong qualifications, relevant skills, and a clean layout for entry-level banking and finance roles."
        )
    elif score >= 65.0:
        summary = (
            f"Your CV scored {score:.0f} out of 100 ({classification}). "
            "You have a solid foundation, and a few clear improvements will make your skills and experience stand out much more."
        )
    else:
        summary = (
            f"Your CV scored {score:.0f} out of 100 ({classification}). "
            "Fixing any mistakes and adding clearer details about your real skills, dates, and duties will make your CV much stronger."
        )
    return summary + missing_note


def _friendly_strength_evidence(
    category_key: str,
    factor_name: str,
    raw_evidence: tuple[str, ...],
    source_pages: tuple[int, ...],
) -> str:
    """Format evidence cleanly in everyday language without internal diagnostics."""
    page_note = f" (Page {', '.join(str(p) for p in source_pages)})" if source_pages else ""

    if factor_name == "Spelling":
        return "No spelling mistakes were found in your CV."
    if factor_name == "Grammar":
        return "No grammar mistakes were found in your sentences."
    if factor_name == "Punctuation":
        return "Commas, periods, and spacing around punctuation are used neatly."
    if factor_name == "Capitalization":
        return "Proper names and bullet points start with capital letters consistently."
    if factor_name == "Repeated Words":
        return "No accidental repeated words were found."
    if factor_name == "Sentence Construction":
        return "Your bullet points are concise and easy to read."
    if factor_name == "Sentence Clarity":
        return "Your bullet points stay short and clear for quick reading."
    if factor_name == "Consistency of Writing Style":
        return "Your bullet points follow a consistent ending style."
    if factor_name == "Professional Vocabulary":
        return "You use strong action words to describe what you did."
    if factor_name == "Font Consistency":
        return "Your CV sticks to a clean, consistent font style."
    if factor_name == "Font Readability":
        return "Your main text is a comfortable size for reading."
    if factor_name == "Font Size Consistency":
        return "Your headings stand out clearly from your normal text."
    if factor_name in ("Paragraph Spacing", "Section Spacing", "Page Layout and Readability", "Overall Neatness"):
        return "Your sections and lines have clean spacing and balance across the page."
    if factor_name == "Text Alignment":
        return "Your headings and text lines align neatly."
    if factor_name == "Margin Consistency":
        return "Your page margins leave comfortable space around the edges."
    if factor_name == "Bullet-Point Formatting":
        return "You use consistent bullet points to organize details."
    if factor_name == "Text Overlap":
        return "All text fits cleanly on the page without overlapping or getting cut off."
    if factor_name == "Clear Section Headings":
        return "Your CV uses clear headings so sections are easy to find."
    if factor_name == "Logical Section Arrangement":
        return "Your sections appear in a natural, easy-to-follow order."
    if factor_name == "Education Organization":
        return "Your qualifications are grouped neatly under an Education heading."
    if factor_name == "Work Experience Organization":
        return "Each role clearly lists your job title, company, dates, and duties."
    if factor_name == "Relevant Information":
        return "Your CV stays focused on job-relevant information without clutter."
    if factor_name == "Information Completeness":
        return "Your CV includes all core sections employers look for."
    if factor_name == "Appropriate CV Length":
        return f"Your CV has a practical length ({raw_evidence[0]})." if raw_evidence else "Your CV has a practical page length."

    return "; ".join(raw_evidence[:2]) + page_note


def _why_strength_helps(category_key: str, factor_name: str) -> str:
    """Return a plain-English, non-repetitive reason why each strength helps."""
    specific: dict[str, str] = {
        "Logical Section Arrangement": "Putting sections in a natural order lets recruiters review your qualifications and experience smoothly.",
        "Clear Section Headings": "Clear headings help busy employers find the exact section they want in seconds.",
        "Contact Information Placement": "Having your name, email, and phone at the top of Page 1 makes it easy to invite you for an interview.",
        "Education Organization": "Grouping your degrees and school grades neatly makes academic checks effortless.",
        "Work Experience Organization": "Listing job titles, companies, dates, and duties together gives a clear picture of your background.",
        "Chronological Consistency": "Consistent dates help employers verify your timeline without confusion.",
        "Relevant Information": "Keeping only job-relevant details helps employers stay focused on your qualifications.",
        "Appropriate CV Length": "A concise 1 to 2 page CV respects the recruiter's time while covering key facts.",
        "Spelling": "Correct spelling shows care, accuracy, and pride in your work.",
        "Grammar": "Clear grammar ensures employers understand your sentences easily on the first read.",
        "Punctuation": "Clean punctuation keeps your bullet points and sentences tidy.",
        "Capitalization": "Consistent capital letters give your CV a polished look.",
        "Repeated Words": "Avoiding repeated words shows careful proofreading.",
        "Font Consistency": "Using consistent fonts keeps the page clean and pleasant to read.",
        "Font Readability": "Comfortable text size makes your CV easy to read on screen or paper.",
        "Font Size Consistency": "Clear size differences between headings and body text guide the reader's eye.",
        "Text Overlap": "Clean spacing ensures no text gets hidden or cut off.",
    }
    if factor_name in specific:
        return specific[factor_name]

    lower = factor_name.lower()
    if category_key == "educational_qualifications":
        return "Banking employers check your school and degree results early when deciding who to shortlist."
    if "internship" in lower or "banking" in lower or "finance" in lower:
        return "Real banking or finance exposure shows employers you already understand workplace routines."
    if "excel" in lower or "spreadsheet" in lower or "accounting software" in lower:
        return "Finance teams use spreadsheets and accounting tools daily, so specific skills give employers confidence."
    if category_key == "communication_language_skills":
        return "Clear language and customer-facing skills are essential for helping clients and writing reports."
    if category_key == "achievements_extracurricular":
        return "Activities and measurable results show teamwork, initiative, and personal drive."
    if "vocabulary" in lower or "clarity" in lower or "construction" in lower or "consistency" in lower:
        return "Clear writing helps busy recruiters understand your duties and achievements quickly."
    return "Clear details help employers quickly see how your background fits the job."


def _build_whats_good(evaluation: CVEvaluationResult) -> tuple[StrengthItem, ...]:
    """Section 2: Build 'What You Did Well' strictly from evidenced factors scoring >= 4/5."""
    ranked: list[tuple[int, int, StrengthItem]] = []
    seen_titles: set[str] = set()

    for cat_eval in evaluation.categories:
        for f in cat_eval.factors:
            if f.status == STATUS_EVALUATED and f.score is not None and f.score >= 4 and f.evidence:
                friendly_title = _FRIENDLY_FACTOR_TITLES.get(f.factor_name, f.factor_name)
                if friendly_title in seen_titles:
                    continue
                seen_titles.add(friendly_title)
                ev_text = _friendly_strength_evidence(
                    cat_eval.category.key, f.factor_name, f.evidence, f.source_pages
                )
                ranked.append(
                    (
                        f.score,
                        cat_eval.max_weight,
                        StrengthItem(
                            title=friendly_title,
                            evidence=ev_text,
                            why_it_helps=_why_strength_helps(cat_eval.category.key, f.factor_name),
                            source_pages=f.source_pages,
                        ),
                    )
                )

    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return tuple(row[2] for row in ranked[:8])


def _apply_finding_to_sentence(sentence: str, finding: LanguageFinding) -> str:
    """Replace only the detected erroneous token/phrase inside the sentence, preserving facts."""
    inc = finding.incorrect
    corr = finding.correction
    if re.match(r"^[A-Za-z\s]+$", inc):
        pattern = re.compile(rf"(?<![A-Za-z]){re.escape(inc)}(?![A-Za-z])")
        updated, count = pattern.subn(corr, sentence, count=1)
        if count > 0:
            return updated
    if inc in sentence:
        return sentence.replace(inc, corr, 1)
    return sentence


def _rewrite_passive_line(line: str) -> str | None:
    """Produce a truthful active-word suggestion for weak passive sentence openings."""
    stripped = line.lstrip("•●▪▫◦-* ").strip()
    bullet_prefix = line[: len(line) - len(line.lstrip("•●▪▫◦-* "))].strip()
    prefix = f"{bullet_prefix} " if bullet_prefix else ""

    patterns = (
        (r"^Responsible\s+for\s+(?:daily\s+)?duties(?:\s+and\s+helped\s+with)?\s*", "Assisted with "),
        (r"^Responsible\s+for\s+", "Managed "),
        (r"^Duties\s+included\s+", "Handled "),
        (r"^Tasked\s+with\s+", "Completed "),
        (r"^Helped\s+with\s+", "Assisted with "),
        (r"^Was\s+involved\s+in\s+", "Supported "),
        (r"^Worked\s+on\s+", "Contributed to "),
    )
    for pat, repl in patterns:
        if re.match(pat, stripped, re.IGNORECASE):
            updated = re.sub(pat, repl, stripped, count=1, flags=re.IGNORECASE)
            return f"{prefix}{updated}"
    return None


def _collect_plain_formatting_notes(
    document: ProcessedPDFDocument,
    evaluation: CVEvaluationResult,
) -> tuple[list[str], list[str]]:
    """
    Translate formatting checks into plain-English issues and practical fixes
    without exposing raw bounding boxes, point measurements, or font-size lists.
    Returns (plain_problems, plain_fixes).
    """
    analysis = document.document_analysis
    pms = analysis.page_metrics
    cat9 = next(c for c in evaluation.categories if c.category.key == "visual_presentation_formatting")
    f9 = {f.factor_name: f for f in cat9.factors}

    problems: list[str] = []
    fixes: list[str] = []

    if f9.get("Font Consistency") and f9["Font Consistency"].weakness:
        problems.append("Your CV uses too many different font styles.")
        fixes.append("Stick to 1 or 2 clean, easy-to-read font styles across the whole document.")

    if f9.get("Font Readability") and f9["Font Readability"].weakness:
        problems.append("The main body text size is either too small or too large to read comfortably.")
        fixes.append("Set your main text to a standard comfortable reading size (around 10 to 11.5 pt).")

    if f9.get("Font Size Consistency") and f9["Font Size Consistency"].weakness:
        if len(analysis.font_sizes_pt) > 5:
            problems.append("Your CV uses too many different text sizes.")
            fixes.append("Use a consistent text size style: one size for normal text, one slightly larger size for headings, and one size for your name.")
        else:
            problems.append("Section headings do not stand out clearly enough from normal text.")
            fixes.append("Make your section headings slightly larger or bold so readers can spot each section quickly.")

    if f9.get("Paragraph Spacing") and f9["Paragraph Spacing"].weakness:
        problems.append("The spacing between lines looks either too tight or too spread out.")
        fixes.append("Use comfortable, even line spacing throughout your CV.")

    if f9.get("Section Spacing") and f9["Section Spacing"].weakness:
        problems.append("There is not enough clear space separating your main sections.")
        fixes.append("Add a consistent blank space before each section heading (Education, Experience, Skills).")

    if f9.get("Text Alignment") and f9["Text Alignment"].weakness:
        problems.append("Some text lines and headings are not lined up consistently.")
        fixes.append("Align your headings, bullet points, and dates cleanly along the left and right edges.")

    if f9.get("Margin Consistency") and f9["Margin Consistency"].weakness:
        problems.append("Your page margins look cramped near the edge or uneven across pages.")
        fixes.append("Use balanced, comfortable page margins on all sides.")

    if f9.get("Bullet-Point Formatting") and f9["Bullet-Point Formatting"].weakness:
        problems.append("Your bullet points use mixed symbols or uneven spacing.")
        fixes.append("Use the same simple bullet symbol and indentation for every list.")

    if any(len(pms) >= 2 and pm.text_distribution_pct < 12.0 for pm in pms) or any(
        pm.top_margin_pt is not None and pm.bottom_margin_pt is not None and (pm.top_margin_pt + pm.bottom_margin_pt) > 360.0 and pm.word_count < 60
        for pm in pms
    ):
        problems.append("Large empty spaces are left unused on the page.")
        fixes.append("Balance your content cleanly so the page looks full and well-arranged without big blank gaps.")

    return problems, fixes


def _build_what_needs_improvement(
    document: ProcessedPDFDocument,
    extracted_cv: ExtractedCVData,
    evaluation: CVEvaluationResult,
    lang_report: LanguageQualityReport,
) -> tuple[ImprovementAreaItem, ...]:
    """
    Section 3: Plain-English 'What Needs Improvement' with short headings,
    clear 1-2 sentence explanations, actual CV examples, and concrete next steps.
    Clearly separates Mistakes to Fix (is_error=True) from Areas You Can Improve (is_error=False).
    """
    if not evaluation.is_assessable:
        return ()

    mistakes: list[ImprovementAreaItem] = []
    improvements: list[ImprovementAreaItem] = []

    # --- A. MISTAKES TO FIX ---
    # 1. Language mistakes (spelling, grammar, punctuation, capitals, repeated words)
    all_lang = (
        list(lang_report.spelling_findings)
        + list(lang_report.grammar_findings)
        + list(lang_report.punctuation_findings)
        + list(lang_report.capitalization_findings)
        + list(lang_report.repeated_word_findings)
    )
    if all_lang:
        sample_fixes = []
        seen_inc = set()
        for f in all_lang:
            if f.incorrect not in seen_inc:
                seen_inc.add(f.incorrect)
                sample_fixes.append(f"'{f.incorrect}' should be '{f.correction}' (Page {f.page_number})")
            if len(sample_fixes) >= 3:
                break
        pages = tuple(sorted({f.page_number for f in all_lang}))
        mistakes.append(
            ImprovementAreaItem(
                heading="Your CV has spelling or grammar mistakes",
                explanation="We found wording or spelling errors in your CV. Fixing these small mistakes helps your CV look careful and professional.",
                cv_example="; ".join(sample_fixes) + ".",
                next_step="Review each highlighted sentence in Section 4 below and update it with the corrected wording.",
                is_error=True,
                page_numbers=pages,
            )
        )

    # 2. Overlapping or cut-off text
    analysis = document.document_analysis
    if analysis.total_overlapping_pairs > 0 or analysis.total_clipped_lines > 0:
        flagged_pages = tuple(
            sorted({pm.page_number for pm in analysis.page_metrics if pm.overlapping_line_pairs > 0 or pm.clipped_line_count > 0})
        )
        page_str = ", ".join(str(p) for p in flagged_pages) if flagged_pages else "1"
        mistakes.append(
            ImprovementAreaItem(
                heading="Some text overlaps or is cut off",
                explanation="Parts of your CV overlap other words or run past the edge of the page, making your document hard to read.",
                cv_example=f"Found on Page {page_str} of your uploaded CV.",
                next_step="Widen your page margins or resize text boxes so every line fits cleanly inside the page.",
                is_error=True,
                page_numbers=flagged_pages,
            )
        )

    # 3. Missing essential contact details
    p = extracted_cv.personal_and_contact
    missing_contact = [
        fld.field_name
        for fld in (p.candidate_name, p.email_address, p.telephone_number)
        if fld.status == "not_found"
    ]
    if missing_contact:
        present_parts = [
            f"{fld.field_name}: {fld.value}"
            for fld in (p.candidate_name, p.email_address, p.telephone_number)
            if fld.status != "not_found"
        ]
        mistakes.append(
            ImprovementAreaItem(
                heading=f"Missing {', '.join(missing_contact).lower()} at the top",
                explanation="Employers need your full contact details right at the top of Page 1 so they can contact you for an interview.",
                cv_example=(
                    f"Top of Page 1 currently shows: {', '.join(present_parts)}."
                    if present_parts
                    else "Contact details could not be found at the top of Page 1."
                ),
                next_step=f"Add your {', '.join(missing_contact).lower()} clearly at the top of Page 1.",
                is_error=True,
                page_numbers=(1,),
            )
        )

    # 4. Chronologically invalid experience dates
    exp_field = extracted_cv.professional_experience.experience_entries
    exp_entries = exp_field.value if isinstance(exp_field.value, list) else []
    exp_pages = exp_field.source_pages
    for entry in exp_entries:
        if "invalid" in str(entry.get("duration_display", "")).lower():
            mistakes.append(
                ImprovementAreaItem(
                    heading="Work experience dates do not match up",
                    explanation="One of your jobs lists an end date earlier than its start date, which looks like a typing mistake.",
                    cv_example=f"{entry.get('job_title') or 'Role'} at {entry.get('company_name') or 'Company'} ({entry.get('employment_dates')}).",
                    next_step="Double-check the start and end dates for this role and correct them.",
                    is_error=True,
                    page_numbers=exp_pages,
                )
            )
            break

    # --- B. AREAS YOU CAN IMPROVE ---
    # 1. Experience duties missing or limited relevance / year-only dates
    roles_without_duties = [e for e in exp_entries if not (e.get("responsibilities") or [])]
    year_only_roles = [
        e for e in exp_entries
        if e.get("duration_months") is None and e.get("employment_dates") and "invalid" not in str(e.get("duration_display", "")).lower()
    ]
    cat2 = next(c for c in evaluation.categories if c.category.key == "professional_experience")
    f2 = {f.factor_name: f for f in cat2.factors}

    if cat2.status == "Unavailable":
        improvements.append(
            ImprovementAreaItem(
                heading="No work experience or internships are listed",
                explanation="We did not find a work experience or internship section in your CV. Employers look for internships, part-time jobs, volunteering, or school projects.",
                cv_example="No Work Experience or Internship section found.",
                next_step="If you have done any internship, part-time work, or volunteer work, add it with your dates and main duties.",
                is_error=False,
                page_numbers=(),
            )
        )
    elif roles_without_duties:
        e0 = roles_without_duties[0]
        improvements.append(
            ImprovementAreaItem(
                heading="Your job or internship duties are not explained",
                explanation="You listed a role, but you haven't explained what work you actually did there. Employers need to see your real duties to understand your experience.",
                cv_example=f"{e0.get('job_title') or 'Role'} at {e0.get('company_name') or 'Company'} ({e0.get('employment_dates') or 'Dates not stated'}).",
                next_step="If accurate, add 2 to 4 bullet points under this role describing the real tasks you handled.",
                is_error=False,
                page_numbers=exp_pages,
            )
        )
    elif f2.get("Relevance of Responsibilities") and f2["Relevance of Responsibilities"].weakness:
        rel_ev = f2["Relevance of Responsibilities"].evidence
        improvements.append(
            ImprovementAreaItem(
                heading="Your work duties could connect better to banking and finance",
                explanation="The duties you mentioned do not clearly highlight numerical, customer service, or accuracy skills that banks look for.",
                cv_example="; ".join(rel_ev[:2]) if rel_ev else "Duties listed in your Work Experience section.",
                next_step="Where truthful, emphasize tasks involving numbers, customers, records, or accuracy.",
                is_error=False,
                page_numbers=exp_pages,
            )
        )

    if year_only_roles:
        e0 = year_only_roles[0]
        improvements.append(
            ImprovementAreaItem(
                heading="Your work dates do not show months",
                explanation="Your work dates only show years (without months), so employers cannot tell how long you actually worked in the role.",
                cv_example=f"{e0.get('job_title') or 'Role'} — {e0.get('employment_dates')}.",
                next_step="If you remember the months, write dates like 'Jan 2023 - Mar 2024' instead of just years.",
                is_error=False,
                page_numbers=exp_pages,
            )
        )

    # 2. Weak / passive wording
    passive_line = next(
        (ln for ln in document.text_lines if any(ph in ln.text.lower() for ph in WEAK_PASSIVE_PHRASES)),
        None,
    )
    if passive_line:
        improvements.append(
            ImprovementAreaItem(
                heading="Some sentences use weak or unclear wording",
                explanation="Starting bullet points with phrases like 'Responsible for' or 'Helped with' makes your work sound less clear and impactful.",
                cv_example=f'"{passive_line.text.strip()}" (Page {passive_line.page_number}).',
                next_step="Start each bullet point with a strong action word like 'Prepared', 'Assisted', 'Checked', or 'Managed'.",
                is_error=False,
                page_numbers=(passive_line.page_number,),
            )
        )

    # 3. Microsoft Excel clarity or absence
    excel_field = extracted_cv.technical_skills.microsoft_excel
    cat3 = next(c for c in evaluation.categories if c.category.key == "technical_computer_skills")
    excel_f = next((f for f in cat3.factors if f.factor_name == "Microsoft Excel"), None)
    if excel_f and excel_f.status == STATUS_NOT_MENTIONED:
        improvements.append(
            ImprovementAreaItem(
                heading="Microsoft Excel is not mentioned",
                explanation="Banking and finance jobs rely heavily on Excel for daily calculations and tables, but Excel was not found in your CV.",
                cv_example="No mention of Microsoft Excel in your Skills or Experience sections.",
                next_step="If you genuinely know how to use Microsoft Excel, add it to your Skills section along with what you can do.",
                is_error=False,
                page_numbers=(),
            )
        )
    elif excel_f and excel_f.score is not None and excel_f.score <= 3:
        ex_ev = excel_field.value.get("evidence_lines", []) if isinstance(excel_field.value, dict) else []
        improvements.append(
            ImprovementAreaItem(
                heading="Your Microsoft Excel skill level is not clear",
                explanation="You mentioned Excel by name, but did not explain what you can actually do with it.",
                cv_example=f'"{ex_ev[0]}"' if ex_ev else "Listed as 'Excel' without details.",
                next_step="If true, mention specific Excel tools you know, such as Pivot Tables, VLOOKUP, or formulas.",
                is_error=False,
                page_numbers=excel_field.source_pages,
            )
        )

    # 4. Unsupported banking keywords (exclude explicit G.C.E. A/L or O/L school exam lines)
    cat5 = next(c for c in evaluation.categories if c.category.key == "banking_finance_knowledge")
    bare_bf = [
        f for f in cat5.factors
        if f.status == STATUS_EVALUATED
        and f.score == 2
        and f.evidence
        and not re.search(r"\b(?:g\.?c\.?e\.?|o/l|a/l)\b", f.evidence[0], re.IGNORECASE)
    ]
    if bare_bf:
        names = ", ".join(_FRIENDLY_FACTOR_TITLES.get(f.factor_name, f.factor_name).replace(" knowledge", "").replace(" awareness", "") for f in bare_bf[:3])
        improvements.append(
            ImprovementAreaItem(
                heading="Banking terms are listed without examples or training",
                explanation=f"You listed {names} as keywords, but didn't show where you learned or used them.",
                cv_example=f'"{bare_bf[0].evidence[0]}"',
                next_step="If accurate, mention the course, certificate, or job duty where you practiced these skills.",
                is_error=False,
                page_numbers=bare_bf[0].source_pages,
            )
        )

    # 5. Missing English / Math exam grades
    edu = extracted_cv.educational_qualifications
    missing_grades = []
    if edu.english_results.status == STATUS_NOT_MENTIONED:
        missing_grades.append("English")
    if edu.mathematics_results.status == STATUS_NOT_MENTIONED:
        missing_grades.append("Mathematics")
    if missing_grades:
        improvements.append(
            ImprovementAreaItem(
                heading=f"{' and '.join(missing_grades)} exam grade(s) are not shown",
                explanation="Entry-level bank applications often check your school O/L or A/L grades in English and Mathematics.",
                cv_example="No explicit grade found in your Education section.",
                next_step=f"If you have completed O/L or A/L exams, add your exact {' and '.join(missing_grades)} grade(s) under Education.",
                is_error=False,
                page_numbers=(),
            )
        )

    # 6. Combined formatting issues under ONE heading: "Improve your CV formatting"
    fmt_problems, fmt_fixes = _collect_plain_formatting_notes(document, evaluation)
    if fmt_problems:
        improvements.append(
            ImprovementAreaItem(
                heading="Improve your CV formatting",
                explanation=" ".join(fmt_problems[:3]),
                cv_example="Visual layout check across your uploaded CV pages.",
                next_step=" ".join(fmt_fixes[:3]),
                is_error=False,
                page_numbers=tuple(pm.page_number for pm in analysis.page_metrics),
            )
        )

    # 7. Missing optional standard sections (not described as a mistake!)
    if extracted_cv.missing_sections:
        missing_pretty = ", ".join(s.title() for s in extracted_cv.missing_sections)
        improvements.append(
            ImprovementAreaItem(
                heading="Some common CV sections are not included",
                explanation=f"Your CV does not have separate sections for: {missing_pretty}. Adding them (if they apply to you) helps employers see a fuller picture.",
                cv_example=f"Sections currently found: {', '.join(s.title() for s in extracted_cv.detected_sections) or 'None'}.",
                next_step=f"If you have truthful details to share (for example, languages you speak or awards you earned), add a clear heading for {missing_pretty}.",
                is_error=False,
                page_numbers=(),
            )
        )

    return tuple(mistakes + improvements)


def _build_specific_corrections(
    document: ProcessedPDFDocument,
    extracted_cv: ExtractedCVData,
    evaluation: CVEvaluationResult,
    lang_report: LanguageQualityReport,
) -> tuple[SpecificCorrectionItem, ...]:
    """
    Section 4: 'How to Improve Your CV' following the 3-step structure:
    STEP 1 - What is wrong?
    STEP 2 - How to fix it?
    STEP 3 - Why does this matter?
    Lists Mistakes to Fix first, then Areas You Can Improve.
    """
    if not evaluation.is_assessable:
        return (
            SpecificCorrectionItem(
                category_label="Unreadable Scanned PDF",
                is_error=True,
                original_cv_example=f"Uploaded file '{document.filename}' appears to be a scanned image with no selectable text.",
                identified_problem="Our CV analyzer and employer CV-reading software cannot read words inside a scanned picture.",
                recommended_improvement="Save or export your CV directly as a standard text PDF from Microsoft Word or Google Docs and upload it again.",
                reason="A text-based PDF ensures CV-reading software and recruiters can read all your qualifications properly.",
                page_number=1,
            ),
        )

    corrections: list[SpecificCorrectionItem] = []

    # 1. Exact language, spelling, grammar, punctuation & repeated-word mistakes (Mistakes to Fix)
    all_lang_findings: list[LanguageFinding] = (
        list(lang_report.spelling_findings)
        + list(lang_report.grammar_findings)
        + list(lang_report.punctuation_findings)
        + list(lang_report.capitalization_findings)
        + list(lang_report.repeated_word_findings)
    )
    grouped_lang: dict[tuple[int, str], list[LanguageFinding]] = defaultdict(list)
    for f in all_lang_findings:
        grouped_lang[(f.page_number, f.context)].append(f)

    for (page_num, orig_line), findings in grouped_lang.items():
        corrected_line = orig_line
        problems: list[str] = []
        seen_pairs: set[tuple[str, str]] = set()
        for f in findings:
            corrected_line = _apply_finding_to_sentence(corrected_line, f)
            pair = (f.incorrect, f.correction)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                problems.append(f"'{f.incorrect}' should be '{f.correction}'")

        corrections.append(
            SpecificCorrectionItem(
                category_label="Spelling & Grammar",
                is_error=True,
                original_cv_example=f'"{orig_line}" (Page {page_num})',
                identified_problem=f"This line has wording or spelling mistake(s): {', '.join(problems)}.",
                recommended_improvement=f'"{corrected_line}"',
                reason="Clear, mistake-free English creates a stronger professional impression and avoids careless misunderstandings.",
                page_number=page_num,
            )
        )

    # 2. Overlapping or cut-off text (Mistake to Fix)
    analysis = document.document_analysis
    dim_by_page = {d.page_number: d for d in analysis.page_dimensions}
    pms = analysis.page_metrics

    if analysis.total_overlapping_pairs > 0 or analysis.total_clipped_lines > 0:
        clipped_examples = [
            ln for ln in document.text_lines
            if ln.page_number in dim_by_page and (
                ln.bbox[2] > dim_by_page[ln.page_number].width_pt + 1.0 or ln.bbox[0] < -1.0
            )
        ]
        flagged_pages = sorted(
            {pm.page_number for pm in pms if pm.overlapping_line_pairs > 0 or pm.clipped_line_count > 0}
        )
        first_p = flagged_pages[0] if flagged_pages else 1
        if clipped_examples:
            ex_ln = clipped_examples[0]
            orig_fmt = f'Page {ex_ln.page_number}: "{ex_ln.text.strip()}"'
            prob_fmt = "This line runs off the edge of the page, and some text on this page overlaps another line."
        else:
            orig_fmt = f"Page {', '.join(str(p) for p in flagged_pages)} layout"
            prob_fmt = "Some text appears to overlap on this page, making parts of your CV difficult to read."
        corrections.append(
            SpecificCorrectionItem(
                category_label="Overlapping or Cut-Off Text",
                is_error=True,
                original_cv_example=orig_fmt,
                identified_problem=prob_fmt,
                recommended_improvement="Adjust your text boxes, column widths, and page margins so every word sits inside the page with clear space around it.",
                reason="Clean spacing prevents text from disappearing on screen or getting misread by CV-reading software.",
                page_number=first_p,
            )
        )

    # 3. Missing essential contact information (Mistake to Fix)
    p = extracted_cv.personal_and_contact
    missing_contact = [
        fld.field_name
        for fld in (p.candidate_name, p.email_address, p.telephone_number)
        if fld.status == "not_found"
    ]
    if missing_contact:
        present_header = [
            f"{fld.field_name}: {fld.value}"
            for fld in (p.candidate_name, p.email_address, p.telephone_number, p.location)
            if fld.status != "not_found"
        ]
        corrections.append(
            SpecificCorrectionItem(
                category_label="Contact Details",
                is_error=True,
                original_cv_example=(
                    f"Top of Page 1: {', '.join(present_header)}."
                    if present_header
                    else "Top of Page 1: No contact details found."
                ),
                identified_problem=f"Your {', '.join(missing_contact).lower()} is missing from the top of your CV.",
                recommended_improvement=f"Add your {', '.join(missing_contact).lower()} clearly right under your name on Page 1.",
                reason="Employers need an easy way to call or email you without searching through the document.",
                page_number=1,
            )
        )

    # 4. Work experience & internship examples (Areas You Can Improve, or Mistake if invalid dates)
    exp_field = extracted_cv.professional_experience.experience_entries
    exp_pages = exp_field.source_pages
    exp_page_1 = exp_pages[0] if exp_pages else None
    exp_entries = exp_field.value if isinstance(exp_field.value, list) else []

    for entry in exp_entries:
        title = entry.get("job_title") or "Role title not stated"
        comp = entry.get("company_name") or "Company not stated"
        dates = entry.get("employment_dates") or "Dates not stated"
        dur_disp = str(entry.get("duration_display") or "")
        resps = entry.get("responsibilities") or []
        entry_quote = f'"{title} - {comp} | {dates}"' + (f" (Page {exp_page_1})" if exp_page_1 else "")

        if "invalid" in dur_disp.lower():
            corrections.append(
                SpecificCorrectionItem(
                    category_label="Work Dates",
                    is_error=True,
                    original_cv_example=entry_quote,
                    identified_problem="The end date is earlier than the start date.",
                    recommended_improvement="Fix the start and end month/year so the dates go in the right order.",
                    reason="Accurate dates prevent confusion when employers check your work history.",
                    page_number=exp_page_1,
                )
            )
        elif entry.get("duration_months") is None and entry.get("employment_dates"):
            corrections.append(
                SpecificCorrectionItem(
                    category_label="Work Dates",
                    is_error=False,
                    original_cv_example=entry_quote,
                    identified_problem="Only years are written here without months, so it is hard to tell how long you worked there.",
                    recommended_improvement="If you remember the months, write dates like 'Jan 2023 - Mar 2024' instead of just years.",
                    reason="Adding months helps recruiters see your exact experience length clearly.",
                    page_number=exp_page_1,
                )
            )

        if not resps:
            corrections.append(
                SpecificCorrectionItem(
                    category_label="Work Experience Duties",
                    is_error=False,
                    original_cv_example=entry_quote,
                    identified_problem="You mentioned this role, but did not explain what work you actually did.",
                    recommended_improvement=(
                        "If accurate, add 2 to 4 bullet points below this role showing your real duties "
                        "(such as helping customers, handling documents, or assisting with office records)."
                    ),
                    reason="Employers need to know what tasks you handled so they can see how your experience fits the job.",
                    page_number=exp_page_1,
                )
            )

    # 5. Weak / unclear wording (Areas You Can Improve)
    passive_added = 0
    for ln in document.text_lines:
        raw = ln.text.strip()
        lower_raw = raw.lower()
        if any(phrase in lower_raw for phrase in WEAK_PASSIVE_PHRASES):
            rewritten = _rewrite_passive_line(raw)
            if rewritten and rewritten != raw:
                corrections.append(
                    SpecificCorrectionItem(
                        category_label="Clearer Wording",
                        is_error=False,
                        original_cv_example=f'"{raw}" (Page {ln.page_number})',
                        identified_problem="Starts with weak wording ('Responsible for' / 'Helped with') instead of a direct action word.",
                        recommended_improvement=f'"{rewritten}" (adjust the opening word to match what you genuinely did).',
                        reason="Strong action words make your personal contribution sound clearer and more professional.",
                        page_number=ln.page_number,
                    )
                )
                passive_added += 1
                if passive_added >= 2:
                    break

    # 6. Technical skills / Microsoft Excel (Areas You Can Improve)
    excel_field = extracted_cv.technical_skills.microsoft_excel
    if excel_field.status != "not_found":
        ev_lines = excel_field.value.get("evidence_lines", [])
        cat3 = next(c for c in evaluation.categories if c.category.key == "technical_computer_skills")
        excel_factor = next((f for f in cat3.factors if f.factor_name == "Microsoft Excel"), None)
        if excel_factor and excel_factor.score is not None and excel_factor.score <= 3 and ev_lines:
            ex_page = excel_field.source_pages[0] if excel_field.source_pages else 1
            corrections.append(
                SpecificCorrectionItem(
                    category_label="Microsoft Excel Skills",
                    is_error=False,
                    original_cv_example=f'"{ev_lines[0]}" (Page {ex_page})',
                    identified_problem="Excel is mentioned, but it does not say what level you have or what tools you know.",
                    recommended_improvement=(
                        "If true, list the specific Excel features you can use "
                        "(for example: 'Microsoft Excel (Pivot Tables, VLOOKUP, formulas)')."
                    ),
                    reason="Specific details make your computer skills easier for banking employers to recognize and trust.",
                    page_number=ex_page,
                )
            )
    else:
        skills_sample = next(
            (ln for ln in document.text_lines if re.search(r"\b(?:skills|word|powerpoint|tally|quickbooks)\b", ln.text, re.IGNORECASE)),
            None,
        )
        orig_skills_ctx = (
            f'"{skills_sample.text.strip()}" (Page {skills_sample.page_number}) — Microsoft Excel is not listed.'
            if skills_sample
            else "Skills section: Microsoft Excel is not mentioned in your CV."
        )
        corrections.append(
            SpecificCorrectionItem(
                category_label="Microsoft Excel Skills",
                is_error=False,
                original_cv_example=orig_skills_ctx,
                identified_problem="Microsoft Excel is missing from your CV.",
                recommended_improvement="If you genuinely know how to use Microsoft Excel, add it under Skills along with what you can do.",
                reason="Almost all entry-level banking and finance roles expect basic or intermediate spreadsheet skills.",
                page_number=skills_sample.page_number if skills_sample else 1,
            )
        )

    # 7. Banking & finance keywords without supporting proof (exclude school G.C.E. A/L or O/L exam lines)
    cat5 = next(c for c in evaluation.categories if c.category.key == "banking_finance_knowledge")
    unsupported_terms: list[str] = []
    unsupported_evidence: list[str] = []
    unsupported_pages: list[int] = []
    for f in cat5.factors:
        if (
            f.status == STATUS_EVALUATED
            and f.score == 2
            and f.evidence
            and not re.search(r"\b(?:g\.?c\.?e\.?|o/l|a/l)\b", f.evidence[0], re.IGNORECASE)
        ):
            unsupported_terms.append(
                _FRIENDLY_FACTOR_TITLES.get(f.factor_name, f.factor_name).replace(" knowledge", "").replace(" awareness", "")
            )
            unsupported_evidence.extend(f.evidence[:1])
            unsupported_pages.extend(f.source_pages)
    if unsupported_terms:
        p_num = unsupported_pages[0] if unsupported_pages else 1
        quote = unsupported_evidence[0]
        corrections.append(
            SpecificCorrectionItem(
                category_label="Banking & Finance Skills",
                is_error=False,
                original_cv_example=f'"{quote}" (Page {p_num})',
                identified_problem=f"Lists {', '.join(unsupported_terms[:3])} as short words without showing where you learned or used them.",
                recommended_improvement="If accurate, add a short note showing the course, certificate, or job task where you practiced these skills.",
                reason="Employers value skills much more when they can see real classes or work tasks behind them.",
                page_number=p_num,
            )
        )

    # 8. Combined formatting improvements under ONE clear item (Areas You Can Improve)
    fmt_problems, fmt_fixes = _collect_plain_formatting_notes(document, evaluation)
    if fmt_problems:
        corrections.append(
            SpecificCorrectionItem(
                category_label="Improve Your CV Formatting",
                is_error=False,
                original_cv_example="Visual layout of your uploaded CV pages.",
                identified_problem=" ".join(fmt_problems),
                recommended_improvement=" ".join(fmt_fixes),
                reason="A neat, consistent layout improves readability and gives your CV a more professional appearance.",
                page_number=1,
            )
        )

    # 9. Missing optional CV sections (Areas You Can Improve)
    if extracted_cv.missing_sections:
        found_heads = ", ".join(s.title() for s in extracted_cv.detected_sections) or "None"
        missing_heads = ", ".join(s.title() for s in extracted_cv.missing_sections)
        corrections.append(
            SpecificCorrectionItem(
                category_label="Helpful CV Sections",
                is_error=False,
                original_cv_example=f"Headings currently in your CV: {found_heads}.",
                identified_problem=f"Your CV does not include separate section(s) for: {missing_heads}.",
                recommended_improvement=(
                    f"If you have truthful details to include, add clear headings for {missing_heads} "
                    "(only add sections that genuinely apply to you)."
                ),
                reason="Clear headings make it faster for recruiters to spot languages, skills, or achievements.",
                page_number=1,
            )
        )

    # Always show Mistakes to Fix first, then Areas You Can Improve
    corrections.sort(key=lambda item: (not item.is_error,))
    return tuple(corrections)


def build_evaluation_report(
    document: ProcessedPDFDocument,
    extracted_cv: ExtractedCVData,
    evaluation: CVEvaluationResult,
) -> CVEvaluationReport:
    """Assemble the user-friendly 4-section CVEvaluationReport."""
    classification, band_key = classify_cv_score(evaluation.overall_score, evaluation.is_assessable)
    lang_report = analyze_language_quality(document.text_lines)

    candidate_name = (
        extracted_cv.personal_and_contact.candidate_name.value
        if extracted_cv.personal_and_contact.candidate_name.status in ("extracted", "ambiguous")
        and isinstance(extracted_cv.personal_and_contact.candidate_name.value, str)
        else None
    )

    whats_good = _build_whats_good(evaluation) if evaluation.is_assessable else ()
    what_needs_improvement = _build_what_needs_improvement(
        document=document,
        extracted_cv=extracted_cv,
        evaluation=evaluation,
        lang_report=lang_report,
    )
    specific_corrections = _build_specific_corrections(
        document=document,
        extracted_cv=extracted_cv,
        evaluation=evaluation,
        lang_report=lang_report,
    )

    limitations: list[str] = [
        SCORE_QUALITY_DISCLAIMER,
        "This feedback is based only on the readable text inside your PDF file.",
        "If your CV is a scanned image, please re-save it as a regular text PDF from Word or Google Docs.",
        "Spoken English and interview communication cannot be checked from a written CV.",
    ]

    interp_title, interp_note, benchmark_note = _build_score_interpretation_note(
        evaluation.overall_score,
        evaluation.is_assessable,
    )

    return CVEvaluationReport(
        application_name=APP_NAME,
        candidate_name=candidate_name,
        filename=document.filename,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        overall_score=evaluation.overall_score,
        total_possible_score=evaluation.total_possible_score,
        classification=classification,
        classification_band=band_key,
        overall_explanation=_build_overall_explanation(evaluation, classification),
        score_interpretation_title=interp_title,
        score_interpretation_note=interp_note,
        score_benchmark_clarification=benchmark_note,
        disclaimer=SCORE_QUALITY_DISCLAIMER,
        evaluation=evaluation,
        whats_good=whats_good,
        what_needs_improvement=what_needs_improvement,
        specific_corrections=specific_corrections,
        assessment_limitations=tuple(dict.fromkeys(limitations)),
    )


def generate_pdf_report_bytes(report: CVEvaluationReport) -> bytes:
    """Render the user-friendly 4-section evaluation report as an A4 PDF in memory via PyMuPDF."""
    ev = report.evaluation
    candidate_display = html.escape(report.candidate_name or "Not specified in CV")

    cat_rows = "".join(
        f"<tr><td>{c.category.order}. {html.escape(c.category.title)}</td>"
        f"<td class='num'>{c.category_score:.1f} / {c.max_weight}</td>"
        f"<td class='num'>{(c.category_score / c.max_weight * 100.0) if c.max_weight else 0.0:.0f}%</td></tr>"
        for c in ev.categories
    )

    good_html = (
        "".join(
            f"<li><strong>{html.escape(s.title)}</strong><br/>"
            f"<span>In your CV: {html.escape(s.evidence)}</span><br/>"
            f"<span class='muted'>Why this helps: {html.escape(s.why_it_helps)}</span></li>"
            for s in report.whats_good
        )
        if report.whats_good
        else "<li>No strong examples were found in the readable text of this CV.</li>"
    )

    mistakes = [w for w in report.what_needs_improvement if w.is_error]
    optional_areas = [w for w in report.what_needs_improvement if not w.is_error]

    def _fmt_improve_list(items: list[ImprovementAreaItem], empty_msg: str) -> str:
        if not items:
            return f"<li>{html.escape(empty_msg)}</li>"
        return "".join(
            f"<li><strong>{html.escape(w.heading)}</strong><br/>"
            f"<span>{html.escape(w.explanation)}</span><br/>"
            f"<span class='muted'>In your CV: {html.escape(w.cv_example)} Next step: {html.escape(w.next_step)}</span></li>"
            for w in items
        )

    corrections_html = (
        "".join(
            f"""
            <div class="box">
                <p><strong>[{html.escape(c.category_label)} &mdash; {'Mistake to Fix' if c.is_error else 'Area You Can Improve'}]</strong></p>
                <table style="margin: 4px 0;">
                    <thead>
                        <tr>
                            <th style="width: 50%;">STEP 1 – What is wrong?</th>
                            <th style="width: 50%;">STEP 2 – How to fix it?</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>{html.escape(c.original_cv_example)}<br/><span class="muted">{html.escape(c.identified_problem)}</span></td>
                            <td>{html.escape(c.recommended_improvement)}</td>
                        </tr>
                    </tbody>
                </table>
                <p><strong>STEP 3 – Why does this matter?</strong> {html.escape(c.reason)}</p>
            </div>
            """
            for c in report.specific_corrections
        )
        if report.specific_corrections
        else "<p>No specific corrections were needed for your CV.</p>"
    )

    limitations_html = "".join(f"<li>{html.escape(lim)}</li>" for lim in report.assessment_limitations)

    report_html = f"""
    <html>
    <head>
    <style>
        body {{ font-family: sans-serif; font-size: 9.5pt; color: #0F172A; line-height: 1.42; }}
        h1 {{ font-size: 15pt; color: #0F2942; margin: 0 0 4px 0; }}
        h2 {{ font-size: 11.5pt; color: #0F2942; border-bottom: 1px solid #CBD5E1; padding-bottom: 3px; margin: 14px 0 6px 0; }}
        h3 {{ font-size: 10pt; color: #1E293B; margin: 8px 0 4px 0; }}
        .sub {{ font-size: 8.5pt; color: #475569; margin: 0 0 10px 0; }}
        .score-box {{ background: #F8FAFC; border: 1px solid #CBD5E1; padding: 10px 12px; margin-bottom: 8px; }}
        .interp-box {{ background: #F0FDF4; border: 1px solid #BBF7D0; border-left: 4px solid #16A34A; padding: 8px 11px; margin-bottom: 12px; }}
        .interp-box-below {{ background: #FFFBEB; border: 1px solid #FDE68A; border-left: 4px solid #D97706; padding: 8px 11px; margin-bottom: 12px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 6px 0 10px 0; font-size: 8.5pt; }}
        th {{ background: #0F2942; color: #FFFFFF; text-align: left; padding: 5px 6px; }}
        td {{ border-bottom: 1px solid #E2E8F0; padding: 4px 6px; vertical-align: top; }}
        .num {{ text-align: right; white-space: nowrap; }}
        .box {{ border: 1px solid #E2E8F0; background: #F8FAFC; padding: 6px 8px; margin-bottom: 6px; }}
        .box p {{ margin: 2px 0; font-size: 8.8pt; }}
        ul {{ margin: 4px 0 8px 16px; padding: 0; }}
        li {{ margin-bottom: 5px; }}
        .muted {{ color: #475569; font-size: 8.4pt; }}
    </style>
    </head>
    <body>
        <h1>{html.escape(report.application_name)} — CV Feedback Report</h1>
        <p class="sub">
            Candidate: <strong>{candidate_display}</strong> &middot;
            File: {html.escape(report.filename)} &middot;
            Generated: {html.escape(report.generated_at)}
        </p>

        <h2>1. Your CV Score</h2>
        <div class="score-box">
            <p style="font-size: 13pt; margin: 0 0 4px 0;">
                <strong>CV SCORE: {report.overall_score:.0f} / {report.total_possible_score}</strong>
                &mdash; <strong>{html.escape(report.classification)}</strong>
            </p>
            <p style="margin: 0 0 4px 0;">{html.escape(report.overall_explanation)}</p>
            <p class="muted" style="margin: 0;">{html.escape(report.disclaimer)}</p>
        </div>
        <div class="{'interp-box' if ev.is_assessable and report.overall_score >= 60.0 else 'interp-box-below'}">
            <p style="margin: 0 0 3px 0;"><strong>{html.escape(report.score_interpretation_title)}</strong></p>
            <p style="margin: 0 0 3px 0;">{html.escape(report.score_interpretation_note)}</p>
            <p class="muted" style="margin: 0;">{html.escape(report.score_benchmark_clarification)}</p>
        </div>

        <table>
            <thead><tr><th>Category</th><th class="num">Score</th><th class="num">%</th></tr></thead>
            <tbody>{cat_rows}</tbody>
        </table>

        <h2>2. What You Did Well</h2>
        <ul>{good_html}</ul>

        <h2>3. What Needs Improvement</h2>
        <h3>A. Mistakes to Fix</h3>
        <ul>{_fmt_improve_list(mistakes, "No spelling, grammar, contact, or text overlap mistakes were found.")}</ul>
        <h3>B. Areas You Can Improve</h3>
        <ul>{_fmt_improve_list(optional_areas, "No extra improvement areas were flagged.")}</ul>

        <h2>4. How to Improve Your CV</h2>
        {corrections_html}

        <h2>Good to Know</h2>
        <ul>{limitations_html}</ul>
    </body>
    </html>
    """

    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    story = pymupdf.Story(html=report_html)
    mediabox = pymupdf.Rect(0, 0, 595, 842)
    content_rect = pymupdf.Rect(42, 42, 553, 800)
    story.write(writer, lambda _rect_num, _filled: (mediabox, content_rect, None))
    writer.close()
    return buf.getvalue()
