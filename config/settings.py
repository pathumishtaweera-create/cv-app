"""
Application-wide constants and configuration settings.

All constants here are local and require no external API keys.
"""

from dataclasses import dataclass

APP_NAME = "Banking & Finance CV Analyzer"
APP_SUBTITLE = (
    "Upload your CV in PDF format for a local, rule-based evaluation tailored "
    "to entry-level banking, corporate finance, and investment roles."
)

# Upload constraints
ALLOWED_EXTENSIONS = (".pdf",)
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
PDF_MAGIC_HEADER = b"%PDF-"

# Preview limits
DEFAULT_PREVIEW_CHAR_LIMIT = 2500


@dataclass(frozen=True)
class EvaluationCategory:
    """Represents one of the nine entry-level banking & finance CV evaluation categories."""

    order: int
    key: str
    title: str
    max_points: int
    group: str  # "candidate_capability" | "document_presentation"
    focus: str


# Nine predefined evaluation categories with exact weights totaling 100 points
EVALUATION_CATEGORIES: tuple[EvaluationCategory, ...] = (
    EvaluationCategory(
        order=1,
        key="educational_qualifications",
        title="Educational Qualifications",
        max_points=20,
        group="candidate_capability",
        focus="O/L & A/L results, English & Mathematics grades, degrees, diplomas, and banking/professional credentials (AAT, CIMA, ACCA, CA, IBSL).",
    ),
    EvaluationCategory(
        order=2,
        key="professional_experience",
        title="Professional Experience",
        max_points=15,
        group="candidate_capability",
        focus="Banking & finance exposure, internships, customer service, cash handling, administrative/sales experience, duration, and responsibility relevance.",
    ),
    EvaluationCategory(
        order=3,
        key="technical_computer_skills",
        title="Technical and Computer Skills",
        max_points=10,
        group="candidate_capability",
        focus="Microsoft Excel, Word, PowerPoint, computer literacy, data entry, spreadsheets, accounting software, and digital banking knowledge.",
    ),
    EvaluationCategory(
        order=4,
        key="communication_language_skills",
        title="Communication and Language Skills",
        max_points=10,
        group="candidate_capability",
        focus="English, Sinhala, and Tamil proficiency evidence, written & interpersonal communication, customer interaction, and presentation experience.",
    ),
    EvaluationCategory(
        order=5,
        key="banking_finance_knowledge",
        title="Banking and Finance Knowledge",
        max_points=10,
        group="candidate_capability",
        focus="Banking operations, financial services, accounting, loans & credit, deposits & savings, financial calculations, CRM, KYC/AML, and compliance.",
    ),
    EvaluationCategory(
        order=6,
        key="achievements_extracurricular",
        title="Achievements and Extracurricular Activities",
        max_points=5,
        group="candidate_capability",
        focus="Academic and professional achievements, awards, leadership, volunteering, sports/extracurriculars, projects, and measurable outcomes.",
    ),
    EvaluationCategory(
        order=7,
        key="cv_structure_organization",
        title="CV Structure and Organization",
        max_points=10,
        group="document_presentation",
        focus="Logical arrangement, clear headings, contact placement, education & experience structure, chronological consistency, completeness, and length.",
    ),
    EvaluationCategory(
        order=8,
        key="language_writing_quality",
        title="Language and Writing Quality",
        max_points=10,
        group="document_presentation",
        focus="Spelling, grammar, sentence construction, punctuation, capitalization, professional vocabulary, clarity, repetition, and style consistency.",
    ),
    EvaluationCategory(
        order=9,
        key="visual_presentation_formatting",
        title="Visual Presentation and Formatting",
        max_points=10,
        group="document_presentation",
        focus="Font consistency, readability, font sizes, paragraph & section spacing, alignment, margins, bullet formatting, overlap/clipping, and page layout.",
    ),
)
