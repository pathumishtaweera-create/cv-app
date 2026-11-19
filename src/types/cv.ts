export type ExtractionStatus =
  | 'extracted'
  | 'partial'
  | 'not_found'
  | 'not_extracted_ocr_required'
  | 'ambiguous';

export interface TextLineInfo {
  pageNumber: number;
  text: string;
  bbox: [number, number, number, number]; // [x0, y0, x1, y1]
  fontNames: string[];
  maxFontSize: number;
  isBold: boolean;
}

export interface PageDimensionInfo {
  pageNumber: number;
  widthPt: number;
  heightPt: number;
  paperSizeLabel: string;
}

export interface PageLayoutMetrics {
  pageNumber: number;
  characterCount: number;
  wordCount: number;
  lineCount: number;
  imageCount: number;
  textDistributionPct: number;
  leftMarginPt: number | null;
  rightMarginPt: number | null;
  topMarginPt: number | null;
  bottomMarginPt: number | null;
  alignmentIndicators: string[];
  medianLineGapPt: number | null;
  sectionGapCount: number;
  overlappingLinePairs: number;
  clippedLineCount: number;
}

export interface PDFDocumentAnalysis {
  pageCount: number;
  pageDimensions: PageDimensionInfo[];
  fontNames: string[];
  fontSizesPt: number[];
  primaryBodyFontSizePt: number | null;
  largestHeadingFontSizePt: number | null;
  pageMetrics: PageLayoutMetrics[];
  totalOverlappingPairs: number;
  totalClippedLines: number;
}

export interface ProcessedPDFDocument {
  filename: string;
  fileSizeBytes: number;
  fileSizeDisplay: string;
  pageCount: number;
  wordCount: number;
  characterCount: number;
  hasExtractableText: boolean;
  isScannedPdf: boolean;
  extractedText: string;
  pageTexts: string[];
  textLines: TextLineInfo[];
  pagePreviewUrls: string[];
  documentAnalysis: PDFDocumentAnalysis;
}

export interface ExtractedField<T = unknown> {
  fieldName: string;
  value: T | null;
  sourcePages: number[];
  status: ExtractionStatus;
  uncertainty?: string;
}

export interface ExperienceEntry {
  jobTitle: string | null;
  companyName: string | null;
  employmentDates: string | null;
  durationMonths: number | null;
  durationDisplay: string;
  isInternship: boolean;
  responsibilities: string[];
  sourcePages: number[];
}

export interface LanguageEntry {
  language: string;
  proficiency: string;
  sourceLine: string;
  sourcePage: number;
}

export interface KeywordEvidenceValue {
  matchedTerms: string[];
  evidenceLines: string[];
}

export interface ExtractedCVData {
  personalAndContact: {
    candidateName: ExtractedField<string>;
    emailAddress: ExtractedField<string>;
    telephoneNumber: ExtractedField<string>;
    location: ExtractedField<string>;
  };
  educationalQualifications: {
    gceOlResults: ExtractedField<string[]>;
    gceAlResults: ExtractedField<string[]>;
    englishResults: ExtractedField<string[]>;
    mathematicsResults: ExtractedField<string[]>;
    degrees: ExtractedField<string[]>;
    diplomas: ExtractedField<string[]>;
    professionalQualifications: ExtractedField<string[]>;
    bankingFinanceQualifications: ExtractedField<string[]>;
  };
  professionalExperience: {
    experienceEntries: ExtractedField<ExperienceEntry[]>;
    internshipDetails: ExtractedField<ExperienceEntry[]>;
    totalCalculableDuration: ExtractedField<string>;
  };
  technicalSkills: {
    microsoftWord: ExtractedField<KeywordEvidenceValue>;
    microsoftExcel: ExtractedField<KeywordEvidenceValue>;
    microsoftPowerPoint: ExtractedField<KeywordEvidenceValue>;
    computerLiteracy: ExtractedField<KeywordEvidenceValue>;
    accountingSoftware: ExtractedField<KeywordEvidenceValue>;
  };
  communicationAndLanguages: {
    languagesAndProficiency: ExtractedField<LanguageEntry[]>;
    customerServiceExperience: ExtractedField<KeywordEvidenceValue>;
  };
  bankingAndFinanceKnowledge: {
    bankingOperations: ExtractedField<KeywordEvidenceValue>;
    financialServices: ExtractedField<KeywordEvidenceValue>;
    accounting: ExtractedField<KeywordEvidenceValue>;
    loansAndCredit: ExtractedField<KeywordEvidenceValue>;
    depositsAndSavings: ExtractedField<KeywordEvidenceValue>;
    kycAndAml: ExtractedField<KeywordEvidenceValue>;
    financialCompliance: ExtractedField<KeywordEvidenceValue>;
  };
  achievements: {
    academicAchievements: ExtractedField<KeywordEvidenceValue>;
    awards: ExtractedField<KeywordEvidenceValue>;
    leadershipActivities: ExtractedField<KeywordEvidenceValue>;
    volunteering: ExtractedField<KeywordEvidenceValue>;
    extracurricularActivities: ExtractedField<KeywordEvidenceValue>;
    measurableAccomplishments: ExtractedField<string[]>;
  };
  detectedSections: string[];
  missingSections: string[];
}

export interface EvaluationCategory {
  order: number;
  key:
    | 'educational_qualifications'
    | 'professional_experience'
    | 'technical_computer_skills'
    | 'communication_language_skills'
    | 'banking_finance_knowledge'
    | 'achievements_extracurricular'
    | 'cv_structure_organization'
    | 'language_writing_quality'
    | 'visual_presentation_formatting';
  title: string;
  maxPoints: number;
  group: 'candidate_capability' | 'document_presentation';
  focus: string;
}

export type FactorStatus =
  | 'Evaluated'
  | 'Not mentioned in CV'
  | 'Cannot be assessed'
  | 'Not applicable';

export interface FactorEvaluation {
  factorName: string;
  score: number | null;
  maxScore: number;
  status: FactorStatus;
  evidence: string[];
  explanation: string;
  weakness: string | null;
  sourcePages: number[];
}

export interface CategoryEvaluation {
  category: EvaluationCategory;
  categoryScore: number;
  maxWeight: number;
  averageFactorScore: number | null;
  assessedFactorCount: number;
  applicableFactorCount: number;
  coveragePct: number;
  status: 'Evaluated' | 'Partial Coverage' | 'Unavailable';
  coverageNote: string;
  factors: FactorEvaluation[];
}

export interface CVEvaluationResult {
  filename: string;
  isAssessable: boolean;
  overallScore: number;
  totalPossibleScore: number;
  candidateCapabilityScore: number;
  candidateCapabilityMax: number;
  documentPresentationScore: number;
  documentPresentationMax: number;
  overallAssessedFactors: number;
  overallApplicableFactors: number;
  overallCoveragePct: number;
  categories: CategoryEvaluation[];
}

export interface LanguageFinding {
  category: 'Spelling' | 'Grammar' | 'Punctuation' | 'Capitalization' | 'Repeated Words';
  incorrect: string;
  correction: string;
  pageNumber: number;
  context: string;
}

export interface LanguageQualityReport {
  spellingFindings: LanguageFinding[];
  grammarFindings: LanguageFinding[];
  punctuationFindings: LanguageFinding[];
  capitalizationFindings: LanguageFinding[];
  repeatedWordFindings: LanguageFinding[];
  bulletCount: number;
  avgBulletWords: number;
  longBulletCount: number;
  fragmentedLineCount: number;
  actionVerbHits: number;
  weakPhraseHits: number;
  repeatedOpenerPhrases: string[];
  bulletPeriodConsistencyPct: number | null;
}

export interface StrengthItem {
  title: string;
  evidence: string;
  whyItHelps: string;
  sourcePages: number[];
}

export interface ImprovementAreaItem {
  heading: string;
  explanation: string;
  cvExample: string;
  nextStep: string;
  isError: boolean;
  pageNumbers: number[];
}

export interface SpecificCorrectionItem {
  categoryLabel: string;
  isError: boolean;
  originalCvExample: string;
  identifiedProblem: string;
  recommendedImprovement: string;
  reason: string;
  pageNumber: number | null;
}

export interface CVEvaluationReport {
  applicationName: string;
  candidateName: string | null;
  filename: string;
  generatedAt: string;
  overallScore: number;
  totalPossibleScore: number;
  classification: string;
  classificationBand:
    | 'outstanding'
    | 'very_good'
    | 'good'
    | 'average'
    | 'below_average'
    | 'needs_improvement'
    | 'unavailable';
  overallExplanation: string;
  scoreInterpretationTitle: string;
  scoreInterpretationNote: string;
  scoreBenchmarkClarification: string;
  disclaimer: string;
  evaluation: CVEvaluationResult;
  whatsGood: StrengthItem[];
  whatNeedsImprovement: ImprovementAreaItem[];
  specificCorrections: SpecificCorrectionItem[];
  assessmentLimitations: string[];
}
