import type { EvaluationCategory } from '../types/cv';

export const APP_NAME = 'Banking & Finance CV Analyzer';
export const APP_SUBTITLE =
  'Upload your CV in PDF format for a local, rule-based evaluation tailored to entry-level banking, corporate finance, and investment roles.';

export const MAX_FILE_SIZE_MB = 10;
export const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;
export const DEFAULT_PREVIEW_CHAR_LIMIT = 2500;

export const SCORE_QUALITY_DISCLAIMER =
  'This score reflects how well your CV presents your background for entry-level banking and finance jobs. It does not guarantee a job interview or offer.';

export const SCORE_BENCHMARK_PERCENTAGE = 60;

export const SCORE_ABOVE_BENCHMARK_NOTE =
  "Your CV is at a good starting level for applying for jobs. A score of 60% or higher means your CV has reached a basic standard that may be sufficient to help you get considered for an interview. However, an interview is never guaranteed. Your qualifications, experience, the job requirements, and the employer's decision also matter.";

export const SCORE_BENCHMARK_CLARIFICATION =
  "Please note: 60% is this app's suggested CV-quality benchmark, not an official banking-industry requirement.";

export const EVALUATION_CATEGORIES: EvaluationCategory[] = [
  {
    order: 1,
    key: 'educational_qualifications',
    title: 'Educational Qualifications',
    maxPoints: 20,
    group: 'candidate_capability',
    focus:
      'O/L & A/L results, English & Mathematics grades, degrees, diplomas, and banking/professional credentials (AAT, CIMA, ACCA, CA, IBSL).',
  },
  {
    order: 2,
    key: 'professional_experience',
    title: 'Professional Experience',
    maxPoints: 15,
    group: 'candidate_capability',
    focus:
      'Banking & finance exposure, internships, customer service, cash handling, administrative/sales experience, duration, and responsibility relevance.',
  },
  {
    order: 3,
    key: 'technical_computer_skills',
    title: 'Technical and Computer Skills',
    maxPoints: 10,
    group: 'candidate_capability',
    focus:
      'Microsoft Excel, Word, PowerPoint, computer literacy, data entry, spreadsheets, accounting software, and digital banking knowledge.',
  },
  {
    order: 4,
    key: 'communication_language_skills',
    title: 'Communication and Language Skills',
    maxPoints: 10,
    group: 'candidate_capability',
    focus:
      'English, Sinhala, and Tamil proficiency evidence, written & interpersonal communication, customer interaction, and presentation experience.',
  },
  {
    order: 5,
    key: 'banking_finance_knowledge',
    title: 'Banking and Finance Knowledge',
    maxPoints: 10,
    group: 'candidate_capability',
    focus:
      'Banking operations, financial services, accounting, loans & credit, deposits & savings, financial calculations, CRM, KYC/AML, and compliance.',
  },
  {
    order: 6,
    key: 'achievements_extracurricular',
    title: 'Achievements and Extracurricular Activities',
    maxPoints: 5,
    group: 'candidate_capability',
    focus:
      'Academic and professional achievements, awards, leadership, volunteering, sports/extracurriculars, projects, and measurable outcomes.',
  },
  {
    order: 7,
    key: 'cv_structure_organization',
    title: 'CV Structure and Organization',
    maxPoints: 10,
    group: 'document_presentation',
    focus:
      'Logical arrangement, clear headings, contact placement, education & experience structure, chronological consistency, completeness, and length.',
  },
  {
    order: 8,
    key: 'language_writing_quality',
    title: 'Language and Writing Quality',
    maxPoints: 10,
    group: 'document_presentation',
    focus:
      'Spelling, grammar, sentence construction, punctuation, capitalization, professional vocabulary, clarity, repetition, and style consistency.',
  },
  {
    order: 9,
    key: 'visual_presentation_formatting',
    title: 'Visual Presentation and Formatting',
    maxPoints: 10,
    group: 'document_presentation',
    focus:
      'Font consistency, readability, font sizes, paragraph & section spacing, alignment, margins, bullet formatting, overlap/clipping, and page layout.',
  },
];
