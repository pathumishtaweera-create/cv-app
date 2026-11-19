"""
Local deterministic language, spelling, grammar, and writing-style analyzer.

Used by Category 8 (Language and Writing Quality) of the evaluation engine.
Uses explicit rule sets and an unambiguous misspelling map so valid British/American
English variations, proper nouns, and Sri Lankan/banking terms are never falsely flagged.
"""

from collections import Counter
from dataclasses import dataclass
import re

from services.pdf_processor import TextLineInfo


# Unambiguous common CV misspellings mapped to their exact corrections.
# Valid British/American English variants (e.g. analyse/analyze, honours/honors,
# organisation/organization, cheque/check, programme/program) are intentionally excluded.
COMMON_MISSPELLINGS: dict[str, str] = {
    "recieved": "received",
    "recieve": "receive",
    "acheivement": "achievement",
    "achievment": "achievement",
    "acheivements": "achievements",
    "achievments": "achievements",
    "experiance": "experience",
    "experince": "experience",
    "managment": "management",
    "mangement": "management",
    "fianance": "finance",
    "finacial": "financial",
    "finanacial": "financial",
    "accouting": "accounting",
    "accountng": "accounting",
    "bussiness": "business",
    "buisness": "business",
    "responsibilites": "responsibilities",
    "responsiblities": "responsibilities",
    "responsiblity": "responsibility",
    "communiction": "communication",
    "communcation": "communication",
    "proficiant": "proficient",
    "proficency": "proficiency",
    "proficeincy": "proficiency",
    "excelent": "excellent",
    "excellant": "excellent",
    "knowledgable": "knowledgeable",
    "seperate": "separate",
    "occured": "occurred",
    "untill": "until",
    "wich": "which",
    "teh": "the",
    "adn": "and",
    "succesful": "successful",
    "sucessful": "successful",
    "collegue": "colleague",
    "refree": "referee",
    "refrees": "referees",
    "curriculam": "curriculum",
    "curiculum": "curriculum",
    "diplamo": "diploma",
    "certifcate": "certificate",
    "certficate": "certificate",
    "analysys": "analysis",
    "evalution": "evaluation",
    "custmer": "customer",
    "custommer": "customer",
    "documetation": "documentation",
    "documentaion": "documentation",
    "reconcilation": "reconciliation",
    "reconcilliation": "reconciliation",
    "complaince": "compliance",
    "complince": "compliance",
    "transacion": "transaction",
    "transcation": "transaction",
    "calender": "calendar",
    "independant": "independent",
    "maintenence": "maintenance",
    "supervison": "supervision",
    "microsft": "Microsoft",
    "powerpiont": "PowerPoint",
    "excell": "Excel",
    "languge": "language",
    "langauge": "language",
    "activites": "activities",
    "extraccuricular": "extracurricular",
    "voluntering": "volunteering",
    "graduted": "graduated",
    "univeristy": "university",
    "universtiy": "university",
    "instituton": "institution",
    "enviroment": "environment",
    "improvment": "improvement",
    "developement": "development",
    "organisaton": "organisation",
    "organizaton": "organization",
    "knowlege": "knowledge",
    "assitant": "assistant",
    "assistnt": "assistant",
    "managar": "manager",
    "execuitve": "executive",
    "internhsip": "internship",
    "intership": "internship",
    "treasuer": "treasurer",
    "secratary": "secretary",
    "presantations": "presentations",
    "presentaion": "presentation",
    "strenghts": "strengths",
    "strenght": "strength",
    "summery": "summary",
    "qualificaton": "qualification",
    "qualificatons": "qualifications",
    "refernces": "references",
    "accurancy": "accuracy",
    "acuracy": "accuracy",
    "efficent": "efficient",
    "effecient": "efficient",
}

PROFESSIONAL_ACTION_VERBS: tuple[str, ...] = (
    "analyzed", "analysed", "assisted", "audited", "balanced", "built", "calculated",
    "collaborated", "compiled", "conducted", "coordinated", "created", "delivered",
    "developed", "documented", "evaluated", "executed", "facilitated", "generated",
    "handled", "implemented", "improved", "led", "maintained", "managed", "monitored",
    "organized", "organised", "performed", "prepared", "processed", "reconciled",
    "reduced", "reported", "resolved", "reviewed", "streamlined", "supported",
    "verified", "wrote",
)

WEAK_PASSIVE_PHRASES: tuple[str, ...] = (
    "responsible for",
    "duties included",
    "tasked with",
    "worked on",
    "helped with",
    "was involved in",
)

EMAIL_OR_URL_RE = re.compile(r"\S+@\S+|https?://\S+|www\.\S+", re.IGNORECASE)
BULLET_PREFIX_RE = re.compile(r"^([•●▪▫◦\-\*])\s+(.+)$")


@dataclass(frozen=True)
class LanguageFinding:
    """Represents a concrete spelling, grammar, punctuation, or capitalization finding."""

    category: str
    incorrect: str
    correction: str
    page_number: int
    context: str


@dataclass(frozen=True)
class LanguageQualityReport:
    """Aggregated deterministic diagnostics for Category 8."""

    spelling_findings: tuple[LanguageFinding, ...]
    grammar_findings: tuple[LanguageFinding, ...]
    punctuation_findings: tuple[LanguageFinding, ...]
    capitalization_findings: tuple[LanguageFinding, ...]
    repeated_word_findings: tuple[LanguageFinding, ...]
    bullet_count: int
    avg_bullet_words: float
    long_bullet_count: int
    fragmented_line_count: int
    action_verb_hits: int
    weak_phrase_hits: int
    repeated_opener_phrases: tuple[str, ...]
    bullet_period_consistency_pct: float | None


def _preserve_case_replacement(original: str, correction: str) -> str:
    """Match leading capitalization when suggesting a spelling correction."""
    if original.isupper():
        return correction.upper()
    if original[0].isupper() and not correction[0].isupper():
        return correction[0].upper() + correction[1:]
    return correction


def analyze_language_quality(lines: tuple[TextLineInfo, ...]) -> LanguageQualityReport:
    """Run deterministic spelling, grammar, punctuation, capitalization, and style checks."""
    spelling_findings: list[LanguageFinding] = []
    grammar_findings: list[LanguageFinding] = []
    punctuation_findings: list[LanguageFinding] = []
    capitalization_findings: list[LanguageFinding] = []
    repeated_word_findings: list[LanguageFinding] = []

    bullet_texts: list[str] = []
    bullet_word_counts: list[int] = []
    bullet_with_period = 0
    bullet_without_period = 0
    bullet_openers: Counter[str] = Counter()
    long_bullets = 0
    fragmented_lines = 0
    action_hits = 0
    weak_hits = 0

    for ln in lines:
        raw = ln.text.strip()
        if not raw:
            continue

        # Strip URLs/emails before checking spelling/punctuation
        sanitized = EMAIL_OR_URL_RE.sub(" ", raw)

        # 1. Spelling check via unambiguous dictionary
        for word_match in re.finditer(r"\b([A-Za-z]+)\b", sanitized):
            token = word_match.group(1)
            lower_tok = token.lower()
            if lower_tok in COMMON_MISSPELLINGS:
                corr = _preserve_case_replacement(token, COMMON_MISSPELLINGS[lower_tok])
                spelling_findings.append(
                    LanguageFinding(
                        category="Spelling",
                        incorrect=token,
                        correction=corr,
                        page_number=ln.page_number,
                        context=raw,
                    )
                )

        # 2. Grammar checks with exact incorrect -> correction pairs
        grammar_rules = (
            (re.compile(r"\bi\b"), "i", "I", "Lowercase personal pronoun 'i'"),
            (re.compile(r"\ba\s+(intern|internship|accountant|audit|auditor|analyst|assistant|associate|executive|officer|university\s+undergraduate\s+of\s+arts|mba|acca|aat)\b", re.IGNORECASE), None, None, "Indefinite article mismatch"),
            (re.compile(r"\ban\s+(university|bachelor|bank|business|diploma|degree|certificate)\b", re.IGNORECASE), None, None, "Indefinite article mismatch"),
            (re.compile(r"\bresponsibilities\s+includes\b", re.IGNORECASE), "responsibilities includes", "responsibilities include", "Subject-verb agreement"),
            (re.compile(r"\bexperiences\s+was\b", re.IGNORECASE), "experiences was", "experiences were", "Subject-verb agreement"),
            (re.compile(r"\b(?:was|were)\s+work(?:ed)?\s+(?:as|at|in)\b", re.IGNORECASE), None, None, "Incorrect passive auxiliary before 'work'"),
            (re.compile(r"\bI\s+has\b"), "I has", "I have", "Subject-verb agreement"),
        )

        # Evaluate explicit article & agreement patterns cleanly
        for m in re.finditer(r"\b(a)\s+(intern|internship|accountant|auditor|analyst|assistant|associate|executive|officer|mba)\b", sanitized, re.IGNORECASE):
            inc = m.group(0)
            corr = f"{'An' if m.group(1)[0].isupper() else 'an'} {m.group(2)}"
            grammar_findings.append(
                LanguageFinding("Grammar", inc, corr, ln.page_number, raw)
            )

        for m in re.finditer(r"\b(an)\s+(university|bachelor|bank|business|diploma|degree|certificate)\b", sanitized, re.IGNORECASE):
            inc = m.group(0)
            corr = f"{'A' if m.group(1)[0].isupper() else 'a'} {m.group(2)}"
            grammar_findings.append(
                LanguageFinding("Grammar", inc, corr, ln.page_number, raw)
            )

        for m in re.finditer(r"(?<![A-Za-z])i(?![A-Za-z0-9/.\-])", sanitized):
            # Ignore Roman numeral I inside headings like "Level I" or "Phase I" or "Part I"
            start_idx = max(0, m.start() - 12)
            prefix = sanitized[start_idx:m.start()].lower()
            if not re.search(r"\b(?:level|part|phase|stage|tier)\s+$", prefix):
                if m.group(0) == "i":
                    grammar_findings.append(
                        LanguageFinding("Grammar", "i", "I", ln.page_number, raw)
                    )

        for pat, inc_lbl, corr_lbl, _ in grammar_rules[3:]:
            m = pat.search(sanitized)
            if m:
                inc_val = inc_lbl or m.group(0)
                corr_val = corr_lbl or re.sub(r"\b(?:was|were)\s+work(?:ed)?\b", "worked", m.group(0), flags=re.IGNORECASE)
                grammar_findings.append(
                    LanguageFinding("Grammar", inc_val, corr_val, ln.page_number, raw)
                )

        # 3. Repeated consecutive words ("the the", "and and")
        for m in re.finditer(r"\b([A-Za-z]{2,})\s+\1\b", sanitized, re.IGNORECASE):
            repeated_word_findings.append(
                LanguageFinding(
                    category="Repeated Words",
                    incorrect=m.group(0),
                    correction=m.group(1),
                    page_number=ln.page_number,
                    context=raw,
                )
            )

        # 4. Punctuation spacing errors (missing space after comma or doubled comma/period excluding decimals/ellipses/abbreviations)
        for m in re.finditer(r"([A-Za-z]{2,}),([A-Za-z]{2,})", sanitized):
            punctuation_findings.append(
                LanguageFinding(
                    category="Punctuation",
                    incorrect=m.group(0),
                    correction=f"{m.group(1)}, {m.group(2)}",
                    page_number=ln.page_number,
                    context=raw,
                )
            )

        for m in re.finditer(r"([A-Za-z]{2,})\.\.(?!\.)", sanitized):
            punctuation_findings.append(
                LanguageFinding(
                    category="Punctuation",
                    incorrect=m.group(0),
                    correction=f"{m.group(1)}.",
                    page_number=ln.page_number,
                    context=raw,
                )
            )

        if re.search(r"\s+[,;:]", sanitized):
            m = re.search(r"(\S+)\s+([,;:])", sanitized)
            if m:
                punctuation_findings.append(
                    LanguageFinding(
                        category="Punctuation",
                        incorrect=m.group(0),
                        correction=f"{m.group(1)}{m.group(2)}",
                        page_number=ln.page_number,
                        context=raw,
                    )
                )

        # 5. Capitalization checks (proper brand/language nouns & lowercase bullet starts)
        proper_noun_map = (
            (re.compile(r"\bmicrosoft\b"), "microsoft", "Microsoft"),
            (re.compile(r"\bexcel\b"), "excel", "Excel"),
            (re.compile(r"\bpowerpoint\b"), "powerpoint", "PowerPoint"),
            (re.compile(r"\benglish\b"), "english", "English"),
            (re.compile(r"\bsinhala\b"), "sinhala", "Sinhala"),
            (re.compile(r"\btamil\b"), "tamil", "Tamil"),
            (re.compile(r"\bsri lanka\b"), "sri lanka", "Sri Lanka"),
        )
        for pat, inc_tok, corr_tok in proper_noun_map:
            if pat.search(sanitized):
                capitalization_findings.append(
                    LanguageFinding("Capitalization", inc_tok, corr_tok, ln.page_number, raw)
                )

        # Bullet analysis for sentence construction, clarity, vocabulary, and style consistency
        bm = BULLET_PREFIX_RE.match(raw)
        if bm:
            body = bm.group(2).strip()
            bullet_texts.append(body)
            words = body.split()
            bullet_word_counts.append(len(words))

            if words and body[0].islower():
                capitalization_findings.append(
                    LanguageFinding(
                        category="Capitalization",
                        incorrect=words[0],
                        correction=words[0].capitalize(),
                        page_number=ln.page_number,
                        context=raw,
                    )
                )

            if len(words) > 35:
                long_bullets += 1
            if len(words) <= 2 and not re.search(r"\b(?:excel|word|sql|python|cima|acca|cfa)\b", body, re.IGNORECASE):
                fragmented_lines += 1

            if body.endswith("."):
                bullet_with_period += 1
            else:
                bullet_without_period += 1

            if len(words) >= 2:
                opener = " ".join(words[:2]).lower()
                bullet_openers[opener] += 1

        # Action verbs vs weak passive phrases
        lower_raw = sanitized.lower()
        for verb in PROFESSIONAL_ACTION_VERBS:
            if re.search(rf"\b{verb}\b", lower_raw):
                action_hits += 1
                break
        for phrase in WEAK_PASSIVE_PHRASES:
            if phrase in lower_raw:
                weak_hits += 1

    total_bullets = len(bullet_texts)
    avg_bullet_words = round(sum(bullet_word_counts) / total_bullets, 1) if total_bullets else 0.0

    period_consistency_pct: float | None = None
    if total_bullets >= 2:
        dominant = max(bullet_with_period, bullet_without_period)
        period_consistency_pct = round((dominant / total_bullets) * 100.0, 1)

    repeated_openers = tuple(
        f"'{phrase}' ({count} times)"
        for phrase, count in bullet_openers.items()
        if count >= 3
    )

    return LanguageQualityReport(
        spelling_findings=tuple(spelling_findings),
        grammar_findings=tuple(grammar_findings),
        punctuation_findings=tuple(punctuation_findings),
        capitalization_findings=tuple(capitalization_findings),
        repeated_word_findings=tuple(repeated_word_findings),
        bullet_count=total_bullets,
        avg_bullet_words=avg_bullet_words,
        long_bullet_count=long_bullets,
        fragmented_line_count=fragmented_lines,
        action_verb_hits=action_hits,
        weak_phrase_hits=weak_hits,
        repeated_opener_phrases=repeated_openers,
        bullet_period_consistency_pct=period_consistency_pct,
    )
