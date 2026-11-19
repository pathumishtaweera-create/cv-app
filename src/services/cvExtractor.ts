import type {
  ExperienceEntry,
  ExtractedCVData,
  ExtractedField,
  KeywordEvidenceValue,
  LanguageEntry,
  ProcessedPDFDocument,
  TextLineInfo,
} from '../types/cv';

const SECTION_ALIASES: Record<string, string[]> = {
  personal: ['personal details', 'personal information', 'contact', 'contact details', 'contact information'],
  summary: ['profile', 'personal profile', 'career objective', 'objective', 'summary', 'professional summary', 'about me'],
  education: [
    'education',
    'educational qualifications',
    'academic qualifications',
    'academic background',
    'education & qualifications',
    'qualifications',
    'school education',
  ],
  professional_qualifications: [
    'professional qualifications',
    'certifications',
    'professional certifications',
    'licenses & certifications',
    'banking & finance qualifications',
  ],
  experience: [
    'experience',
    'work experience',
    'professional experience',
    'employment history',
    'career history',
    'work history',
    'internships',
    'internship experience',
    'industrial training',
  ],
  skills: [
    'skills',
    'technical skills',
    'it skills',
    'computer skills',
    'core competencies',
    'competencies',
    'key skills',
    'software skills',
  ],
  languages: ['languages', 'language proficiency', 'communication & languages'],
  achievements: [
    'achievements',
    'awards',
    'honors & awards',
    'honours & awards',
    'extracurricular',
    'extracurricular activities',
    'extra-curricular activities',
    'co-curricular activities',
    'leadership',
    'leadership & activities',
    'volunteering',
    'volunteer experience',
    'sports & activities',
  ],
  referees: ['referees', 'references'],
};

const CORE_EXPECTED_SECTIONS = ['education', 'experience', 'skills', 'languages', 'achievements'];

const MONTH_MAP: Record<string, number> = {
  jan: 1, january: 1,
  feb: 2, february: 2,
  mar: 3, march: 3,
  apr: 4, april: 4,
  may: 5,
  jun: 6, june: 6,
  jul: 7, july: 7,
  aug: 8, august: 8,
  sep: 9, sept: 9, september: 9,
  oct: 10, october: 10,
  nov: 11, november: 11,
  dec: 12, december: 12,
};

const EMAIL_RE = /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/;
const PHONE_RE = /(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)\d{3,4}[\s.-]?\d{3,4}(?!\d)/;
const DATE_RANGE_RE =
  /((?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+\d{4})|(?:\d{1,2}\/\d{4})|(?:\d{4}-\d{2})|(?:\b(?:19|20)\d{2}\b))\s*(?:-|–|—|to)\s*((?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+\d{4})|(?:\d{1,2}\/\d{4})|(?:\d{4}-\d{2})|(?:\b(?:19|20)\d{2}\b)|(?:present|current|ongoing|till\s*date|to\s*date|now))/i;

const IGNORED_NAME_HEADERS = new Set([
  'curriculum vitae',
  'resume',
  'cv',
  'personal details',
  'personal profile',
  'contact details',
  'bio data',
  'biodata',
]);

const ROLE_TITLE_KEYWORDS = [
  'intern', 'trainee', 'analyst', 'associate', 'assistant', 'officer', 'executive',
  'clerk', 'teller', 'cashier', 'representative', 'specialist', 'coordinator',
  'auditor', 'accountant', 'bookkeeper', 'advisor', 'consultant', 'manager',
  'supervisor', 'apprentice', 'placement',
];

const COMPANY_HINT_KEYWORDS = [
  'bank', 'plc', 'ltd', 'limited', 'inc', 'llc', 'corp', 'group', 'holdings',
  'finance', 'financial', 'capital', 'securities', 'insurance', 'assurance',
  'credit', 'leasing', 'associates', 'partners', 'kpmg', 'pwc', 'ey', 'deloitte',
  'bdo', 'hsbc', 'commercial bank', 'sampath', 'hatton national', 'hnb', 'seylan',
  'ndb', 'dfcc', 'peoples bank', "people's bank", 'bank of ceylon', 'boc', 'nations trust',
];

function notFound<T>(fieldName: string, uncertainty?: string): ExtractedField<T> {
  return { fieldName, value: null, sourcePages: [], status: 'not_found', uncertainty };
}

function ocrBlocked<T>(fieldName: string): ExtractedField<T> {
  return {
    fieldName,
    value: null,
    sourcePages: [],
    status: 'not_extracted_ocr_required',
    uncertainty: 'Readable text could not be extracted because the PDF appears to be a scanned image.',
  };
}

function detectHeading(line: TextLineInfo): string | null {
  const clean = line.text.trim().replace(/[:|\-–—]+$/g, '').trim().toLowerCase();
  if (!clean || clean.length > 55) return null;
  for (const [canonical, aliases] of Object.entries(SECTION_ALIASES)) {
    if (aliases.includes(clean)) return canonical;
  }
  return null;
}

function segmentBySections(lines: TextLineInfo[]): {
  sections: Map<string, TextLineInfo[]>;
  detectedOrder: string[];
} {
  const sections = new Map<string, TextLineInfo[]>();
  const detectedOrder: string[] = [];
  let current = 'header';
  sections.set(current, []);

  for (const ln of lines) {
    const heading = detectHeading(ln);
    if (heading) {
      current = heading;
      if (!detectedOrder.includes(heading)) detectedOrder.push(heading);
      if (!sections.has(current)) sections.set(current, []);
      continue;
    }
    if (!sections.has(current)) sections.set(current, []);
    sections.get(current)!.push(ln);
  }
  return { sections, detectedOrder };
}

function parseMonthYearToken(token: string): { year: number; month: number; isMonthKnown: boolean; isCurrent: boolean } | null {
  const clean = token.trim().toLowerCase().replace(/\./g, '');
  if (/^(?:present|current|ongoing|till\s*date|to\s*date|now)$/.test(clean)) {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() + 1, isMonthKnown: true, isCurrent: true };
  }
  const myMatch = clean.match(/^([a-z]+)\s+(\d{4})$/);
  if (myMatch && MONTH_MAP[myMatch[1]]) {
    return { year: parseInt(myMatch[2], 10), month: MONTH_MAP[myMatch[1]], isMonthKnown: true, isCurrent: false };
  }
  const slashMatch = clean.match(/^(\d{1,2})\/(\d{4})$/);
  if (slashMatch) {
    const m = parseInt(slashMatch[1], 10);
    if (m >= 1 && m <= 12) return { year: parseInt(slashMatch[2], 10), month: m, isMonthKnown: true, isCurrent: false };
  }
  const isoMatch = clean.match(/^(\d{4})-(\d{2})$/);
  if (isoMatch) {
    const m = parseInt(isoMatch[2], 10);
    if (m >= 1 && m <= 12) return { year: parseInt(isoMatch[1], 10), month: m, isMonthKnown: true, isCurrent: false };
  }
  const yearMatch = clean.match(/^((?:19|20)\d{2})$/);
  if (yearMatch) {
    return { year: parseInt(yearMatch[1], 10), month: 1, isMonthKnown: false, isCurrent: false };
  }
  return null;
}

function calculateDuration(startTok: string, endTok: string): { months: number | null; display: string } {
  const s = parseMonthYearToken(startTok);
  const e = parseMonthYearToken(endTok);
  if (!s || !e) return { months: null, display: 'Duration could not be calculated' };
  if (!s.isMonthKnown || !e.isMonthKnown) {
    return { months: null, display: 'Cannot be calculated reliably (year-only dates)' };
  }
  const diff = (e.year - s.year) * 12 + (e.month - s.month) + 1;
  if (diff <= 0 || diff > 600) return { months: null, display: 'Invalid date range' };
  return { months: diff, display: `${diff} month(s)` };
}

function scanKeywordEvidence(
  lines: TextLineInfo[],
  fieldName: string,
  patterns: RegExp[],
  options?: { excludeExamLines?: boolean },
): ExtractedField<KeywordEvidenceValue> {
  const matchedTerms = new Set<string>();
  const evidenceLines: string[] = [];
  const pages = new Set<number>();

  for (const ln of lines) {
    if (options?.excludeExamLines && /\b(?:g\.?c\.?e\.?|o\/l|a\/l|ordinary\s+level|advanced\s+level)\b/i.test(ln.text)) {
      continue;
    }
    let hit = false;
    for (const pat of patterns) {
      const m = ln.text.match(pat);
      if (m) {
        matchedTerms.add(m[0]);
        hit = true;
      }
    }
    if (hit) {
      if (!evidenceLines.includes(ln.text)) evidenceLines.push(ln.text);
      pages.add(ln.pageNumber);
    }
  }

  if (evidenceLines.length === 0) return notFound<KeywordEvidenceValue>(fieldName);
  return {
    fieldName,
    value: {
      matchedTerms: Array.from(matchedTerms).slice(0, 6),
      evidenceLines: evidenceLines.slice(0, 4),
    },
    sourcePages: Array.from(pages).sort((a, b) => a - b),
    status: 'extracted',
  };
}

export function extractCvInformation(document: ProcessedPDFDocument): ExtractedCVData {
  if (document.isScannedPdf || !document.hasExtractableText) {
    return {
      personalAndContact: {
        candidateName: ocrBlocked('Candidate Name'),
        emailAddress: ocrBlocked('Email Address'),
        telephoneNumber: ocrBlocked('Telephone Number'),
        location: ocrBlocked('Location'),
      },
      educationalQualifications: {
        gceOlResults: ocrBlocked('G.C.E. O/L Results'),
        gceAlResults: ocrBlocked('G.C.E. A/L Results'),
        englishResults: ocrBlocked('English Results'),
        mathematicsResults: ocrBlocked('Mathematics Results'),
        degrees: ocrBlocked('Degrees'),
        diplomas: ocrBlocked('Diplomas'),
        professionalQualifications: ocrBlocked('Professional Qualifications'),
        bankingFinanceQualifications: ocrBlocked('Banking & Finance Qualifications'),
      },
      professionalExperience: {
        experienceEntries: ocrBlocked('Professional Experience'),
        internshipDetails: ocrBlocked('Internship Details'),
        totalCalculableDuration: ocrBlocked('Total Experience Duration'),
      },
      technicalSkills: {
        microsoftWord: ocrBlocked('Microsoft Word'),
        microsoftExcel: ocrBlocked('Microsoft Excel'),
        microsoftPowerPoint: ocrBlocked('Microsoft PowerPoint'),
        computerLiteracy: ocrBlocked('Computer Literacy'),
        accountingSoftware: ocrBlocked('Accounting Software'),
      },
      communicationAndLanguages: {
        languagesAndProficiency: ocrBlocked('Languages'),
        customerServiceExperience: ocrBlocked('Customer Service'),
      },
      bankingAndFinanceKnowledge: {
        bankingOperations: ocrBlocked('Banking Operations'),
        financialServices: ocrBlocked('Financial Services'),
        accounting: ocrBlocked('Accounting'),
        loansAndCredit: ocrBlocked('Loans & Credit'),
        depositsAndSavings: ocrBlocked('Deposits & Savings'),
        kycAndAml: ocrBlocked('KYC & AML'),
        financialCompliance: ocrBlocked('Financial Compliance'),
      },
      achievements: {
        academicAchievements: ocrBlocked('Academic Achievements'),
        awards: ocrBlocked('Awards'),
        leadershipActivities: ocrBlocked('Leadership Activities'),
        volunteering: ocrBlocked('Volunteering'),
        extracurricularActivities: ocrBlocked('Extracurricular Activities'),
        measurableAccomplishments: ocrBlocked('Measurable Accomplishments'),
      },
      detectedSections: [],
      missingSections: [...CORE_EXPECTED_SECTIONS],
    };
  }

  const lines = document.textLines;
  const { sections, detectedOrder } = segmentBySections(lines);

  // A. Personal & Contact
  let candidateName: ExtractedField<string> = notFound('Candidate Name');
  const p1TopLines = lines.filter((l) => l.pageNumber === 1).slice(0, 10);
  for (const ln of p1TopLines) {
    const raw = ln.text.trim();
    const lower = raw.toLowerCase();
    if (IGNORED_NAME_HEADERS.has(lower) || detectHeading(ln)) continue;
    if (EMAIL_RE.test(raw) || PHONE_RE.test(raw) || /https?:|www\.|linkedin/i.test(raw)) continue;
    if (/\d/.test(raw)) continue;
    const words = raw.split(/\s+/);
    if (words.length >= 2 && words.length <= 5 && /^[A-Za-z.'-\s]+$/.test(raw)) {
      candidateName = { fieldName: 'Candidate Name', value: raw, sourcePages: [1], status: 'extracted' };
      break;
    }
  }

  let emailField: ExtractedField<string> = notFound('Email Address');
  let phoneField: ExtractedField<string> = notFound('Telephone Number');
  let locationField: ExtractedField<string> = notFound('Location');

  for (const ln of lines) {
    if (emailField.status === 'not_found') {
      const m = ln.text.match(EMAIL_RE);
      if (m) emailField = { fieldName: 'Email Address', value: m[0], sourcePages: [ln.pageNumber], status: 'extracted' };
    }
    if (phoneField.status === 'not_found') {
      const m = ln.text.match(PHONE_RE);
      if (m && m[0].replace(/\D/g, '').length >= 9) {
        phoneField = { fieldName: 'Telephone Number', value: m[0].trim(), sourcePages: [ln.pageNumber], status: 'extracted' };
      }
    }
  }

  for (const ln of p1TopLines) {
    const locMatch = ln.text.match(
      /\b(?:Colombo|Kandy|Galle|Gampaha|Kurunegala|Matara|Negombo|Jaffna|Kalutara|Nugegoda|Dehiwala|Mount\s+Lavinia|Sri\s+Lanka|London|Singapore|Dubai)\b[^|•\n]*/i,
    );
    if (locMatch) {
      locationField = {
        fieldName: 'Location',
        value: locMatch[0].replace(/[|,]+$/, '').trim(),
        sourcePages: [1],
        status: 'extracted',
      };
      break;
    }
  }

  // B. Education
  const eduLines = [
    ...(sections.get('education') || []),
    ...(sections.get('professional_qualifications') || []),
  ];
  const eduSearchLines = eduLines.length > 0 ? eduLines : lines;

  const olLines: string[] = [];
  const olPages = new Set<number>();
  const alLines: string[] = [];
  const alPages = new Set<number>();
  const engLines: string[] = [];
  const engPages = new Set<number>();
  const mathLines: string[] = [];
  const mathPages = new Set<number>();
  const degreeLines: string[] = [];
  const degPages = new Set<number>();
  const diplomaLines: string[] = [];
  const dipPages = new Set<number>();
  const profQualLines: string[] = [];
  const profPages = new Set<number>();
  const bfQualLines: string[] = [];
  const bfPages = new Set<number>();

  for (const ln of eduSearchLines) {
    const t = ln.text;
    if (/\b(?:g\.?c\.?e\.?\s*)?o\/?l\b|ordinary\s+level/i.test(t)) {
      olLines.push(t);
      olPages.add(ln.pageNumber);
    }
    if (/\b(?:g\.?c\.?e\.?\s*)?a\/?l\b|advanced\s+level/i.test(t)) {
      alLines.push(t);
      alPages.add(ln.pageNumber);
    }
    const engGrade = t.match(/\b(?:general\s+)?english(?:\s+language)?\s*[:\-–—]?\s*([ABCSFW]|distinction|credit|pass)\b/i)
      || t.match(/\bIELTS\s*[:\-–—]?\s*(\d(?:\.\d)?)\b/i);
    if (engGrade) {
      engLines.push(engGrade[0]);
      engPages.add(ln.pageNumber);
    }
    const mathGrade = t.match(/\b(?:combined\s+)?math(?:ematic)?s\s*[:\-–—]?\s*([ABCSFW]|distinction|credit|pass)\b/i);
    if (mathGrade) {
      mathLines.push(mathGrade[0]);
      mathPages.add(ln.pageNumber);
    }
    if (/\b(?:b\.?sc\.?|b\.?ba\.?|b\.?com\.?|bachelor(?:'s)?|m\.?sc\.?|mba|master(?:'s)?|undergraduate\s+degree|hons)\b/i.test(t)
      && !/\bibsl\b|\bcbf\b|\bdabf\b/i.test(t)) {
      degreeLines.push(t);
      degPages.add(ln.pageNumber);
    } else if (/\bdiploma\b/i.test(t) && !/\bibsl\b|\bdabf\b|\bdbf\b/i.test(t)) {
      diplomaLines.push(t);
      dipPages.add(ln.pageNumber);
    }
    if (/\b(?:aat|cima|acca|ca\s+sri\s+lanka|chartered\s+accountant|cfa|acma|cgma)\b/i.test(t)) {
      profQualLines.push(t);
      profPages.add(ln.pageNumber);
    }
    if (/\b(?:ibsl|dabf|dbf|iabf|cbf|fmva|bloomberg\s+market\s+concepts|banking\s+and\s+finance)\b/i.test(t)) {
      bfQualLines.push(t);
      bfPages.add(ln.pageNumber);
    }
  }

  const olField: ExtractedField<string[]> = olLines.length
    ? {
        fieldName: 'G.C.E. O/L Results',
        value: olLines,
        sourcePages: Array.from(olPages),
        status: /\b(?:[ABCS]|pass|credit|distinction)\b/i.test(olLines.join(' ')) ? 'extracted' : 'partial',
      }
    : notFound('G.C.E. O/L Results');

  const alField: ExtractedField<string[]> = alLines.length
    ? {
        fieldName: 'G.C.E. A/L Results',
        value: alLines,
        sourcePages: Array.from(alPages),
        status: /[:\-–—]\s*[ABCS]\b|\b\d+\s*[ABC]'?s?\b|\bpass(?:es)?\b/i.test(alLines.join(' ')) ? 'extracted' : 'partial',
      }
    : notFound('G.C.E. A/L Results');

  // C. Professional Experience
  const expLines = sections.get('experience') || [];
  const entries: ExperienceEntry[] = [];
  let currentEntry: ExperienceEntry | null = null;

  for (const ln of expLines) {
    const raw = ln.text.trim();
    const isBullet = /^[•●▪▫◦\-*]\s+/.test(raw);
    const dateMatch = raw.match(DATE_RANGE_RE);

    if (!isBullet && (dateMatch || ROLE_TITLE_KEYWORDS.some((k) => new RegExp(`\\b${k}\\b`, 'i').test(raw)))) {
      if (currentEntry) entries.push(currentEntry);

      let headerText = raw;
      let empDates: string | null = null;
      let durMonths: number | null = null;
      let durDisplay = 'Dates not specified';
      if (dateMatch) {
        empDates = dateMatch[0].trim();
        const dur = calculateDuration(dateMatch[1], dateMatch[2]);
        durMonths = dur.months;
        durDisplay = dur.display;
        headerText = raw.replace(dateMatch[0], '').replace(/[|,\-–—]+$/g, '').trim();
      }

      const parts = headerText.split(/\s*(?:\||—|–| - | at )\s*/i).map((p) => p.trim()).filter(Boolean);
      let jobTitle: string | null = parts[0] || headerText || null;
      let companyName: string | null = parts.length >= 2 ? parts.slice(1).join(' - ') : null;

      if (companyName && !ROLE_TITLE_KEYWORDS.some((k) => new RegExp(`\\b${k}\\b`, 'i').test(jobTitle || ''))
        && COMPANY_HINT_KEYWORDS.some((k) => new RegExp(`\\b${k}\\b`, 'i').test(jobTitle || ''))) {
        const swap = jobTitle;
        jobTitle = companyName;
        companyName = swap;
      }

      currentEntry = {
        jobTitle,
        companyName,
        employmentDates: empDates,
        durationMonths: durMonths,
        durationDisplay: durDisplay,
        isInternship: /\b(?:intern|internship|trainee|industrial\s+training|placement)\b/i.test(`${jobTitle || ''} ${raw}`),
        responsibilities: [],
        sourcePages: [ln.pageNumber],
      };
    } else if (currentEntry) {
      const cleanedResp = raw.replace(/^[•●▪▫◦\-*]\s+/, '').trim();
      if (cleanedResp) {
        currentEntry.responsibilities.push(cleanedResp);
        if (!currentEntry.sourcePages.includes(ln.pageNumber)) {
          currentEntry.sourcePages.push(ln.pageNumber);
        }
      }
    }
  }
  if (currentEntry) entries.push(currentEntry);

  const internships = entries.filter((e) => e.isInternship);
  const calculableMonths = entries.filter((e) => typeof e.durationMonths === 'number').map((e) => e.durationMonths!);
  const totalMonths = calculableMonths.reduce((a, b) => a + b, 0);

  // E. Languages
  const langSectionLines = sections.get('languages') || lines;
  const langEntries: LanguageEntry[] = [];
  for (const ln of langSectionLines) {
    for (const langName of ['English', 'Sinhala', 'Tamil']) {
      const re = new RegExp(`\\b${langName}\\b(?:\\s*[:\\-–—\\(]\\s*([^|\\n\\)\\;]+)\\)?)?`, 'i');
      const m = ln.text.match(re);
      if (m && (sections.has('languages') || m[1])) {
        const prof = (m[1] || 'Not explicitly stated').trim();
        if (!langEntries.some((x) => x.language === langName && x.sourceLine === ln.text)) {
          langEntries.push({
            language: langName,
            proficiency: prof,
            sourceLine: ln.text,
            sourcePage: ln.pageNumber,
          });
        }
      }
    }
  }

  // F. Measurable accomplishments
  const measLines: string[] = [];
  const measPages = new Set<number>();
  for (const ln of lines) {
    if (/(?:\d+%|\b(?:lkr|rs\.?|usd|\$)\s*[\d,]+|\b\d+\+\s*(?:accounts?|clients?|customers?|reports?|presentations?))/i.test(ln.text)) {
      measLines.push(ln.text);
      measPages.add(ln.pageNumber);
    }
  }

  const missingSections = CORE_EXPECTED_SECTIONS.filter((sec) => !detectedOrder.includes(sec));

  return {
    personalAndContact: {
      candidateName,
      emailAddress: emailField,
      telephoneNumber: phoneField,
      location: locationField,
    },
    educationalQualifications: {
      gceOlResults: olField,
      gceAlResults: alField,
      englishResults: engLines.length
        ? { fieldName: 'English Results', value: engLines, sourcePages: Array.from(engPages), status: 'extracted' }
        : notFound('English Results'),
      mathematicsResults: mathLines.length
        ? { fieldName: 'Mathematics Results', value: mathLines, sourcePages: Array.from(mathPages), status: 'extracted' }
        : notFound('Mathematics Results'),
      degrees: degreeLines.length
        ? { fieldName: 'Degrees', value: degreeLines, sourcePages: Array.from(degPages), status: 'extracted' }
        : notFound('Degrees'),
      diplomas: diplomaLines.length
        ? { fieldName: 'Diplomas', value: diplomaLines, sourcePages: Array.from(dipPages), status: 'extracted' }
        : notFound('Diplomas'),
      professionalQualifications: profQualLines.length
        ? { fieldName: 'Professional Qualifications', value: profQualLines, sourcePages: Array.from(profPages), status: 'extracted' }
        : notFound('Professional Qualifications'),
      bankingFinanceQualifications: bfQualLines.length
        ? { fieldName: 'Banking & Finance Qualifications', value: bfQualLines, sourcePages: Array.from(bfPages), status: 'extracted' }
        : notFound('Banking & Finance Qualifications'),
    },
    professionalExperience: {
      experienceEntries: entries.length
        ? {
            fieldName: 'Experience Entries',
            value: entries,
            sourcePages: Array.from(new Set(entries.flatMap((e) => e.sourcePages))).sort((a, b) => a - b),
            status: 'extracted',
          }
        : notFound('Experience Entries'),
      internshipDetails: internships.length
        ? {
            fieldName: 'Internship Details',
            value: internships,
            sourcePages: Array.from(new Set(internships.flatMap((e) => e.sourcePages))).sort((a, b) => a - b),
            status: 'extracted',
          }
        : notFound('Internship Details'),
      totalCalculableDuration: calculableMonths.length
        ? {
            fieldName: 'Total Experience Duration',
            value: `${totalMonths} month(s)`,
            sourcePages: Array.from(new Set(entries.flatMap((e) => e.sourcePages))).sort((a, b) => a - b),
            status: 'extracted',
          }
        : entries.length
          ? {
              fieldName: 'Total Experience Duration',
              value: null,
              sourcePages: Array.from(new Set(entries.flatMap((e) => e.sourcePages))),
              status: 'partial',
              uncertainty: 'Employment dates lack month-level precision, so total duration cannot be calculated.',
            }
          : notFound('Total Experience Duration'),
    },
    technicalSkills: {
      microsoftWord: scanKeywordEvidence(lines, 'Microsoft Word', [/\b(?:microsoft\s+word|ms\s+word)\b/i]),
      microsoftExcel: scanKeywordEvidence(lines, 'Microsoft Excel', [/\b(?:microsoft\s+excel|ms\s+excel|excel)\b/i]),
      microsoftPowerPoint: scanKeywordEvidence(lines, 'Microsoft PowerPoint', [/\b(?:microsoft\s+powerpoint|ms\s+powerpoint|powerpoint)\b/i]),
      computerLiteracy: scanKeywordEvidence(lines, 'Computer Literacy', [/\b(?:computer\s+literacy|ms\s+office|microsoft\s+office|office\s+suite|it\s+literacy)\b/i]),
      accountingSoftware: scanKeywordEvidence(lines, 'Accounting Software', [/\b(?:quickbooks|sage|tally|xero|myob|peachtree|erp|sap)\b/i]),
    },
    communicationAndLanguages: {
      languagesAndProficiency: langEntries.length
        ? {
            fieldName: 'Languages',
            value: langEntries,
            sourcePages: Array.from(new Set(langEntries.map((l) => l.sourcePage))).sort((a, b) => a - b),
            status: 'extracted',
          }
        : notFound('Languages'),
      customerServiceExperience: scanKeywordEvidence(lines, 'Customer Service', [/\b(?:customer\s+service|client\s+service|customer\s+support|front\s+desk|onboarding|inquiries)\b/i]),
    },
    bankingAndFinanceKnowledge: {
      bankingOperations: scanKeywordEvidence(lines, 'Banking Operations', [/\b(?:banking\s+operations|branch\s+banking|cheque\s+clearing|teller|remittance|rtgs|swift|core\s+banking)\b/i]),
      financialServices: scanKeywordEvidence(lines, 'Financial Services', [/\b(?:financial\s+services|wealth\s+management|investment|treasury|capital\s+markets|leasing|microfinance)\b/i]),
      accounting: scanKeywordEvidence(
        lines,
        'Accounting',
        [/\b(?:financial\s+accounting|management\s+accounting|general\s+ledger|bookkeeping|trial\s+balance|balance\s+sheet|reconciliation|ifrs|accounting)\b/i],
        { excludeExamLines: true },
      ),
      loansAndCredit: scanKeywordEvidence(lines, 'Loans & Credit', [/\b(?:credit\s+analysis|loan\s+processing|sme\s+credit|underwriting|credit\s+risk|lending|facilities)\b/i]),
      depositsAndSavings: scanKeywordEvidence(lines, 'Deposits & Savings', [/\b(?:fixed\s+deposits?|savings\s+accounts?|term\s+deposits?|current\s+accounts?|account\s+opening)\b/i]),
      kycAndAml: scanKeywordEvidence(lines, 'KYC & AML', [/\b(?:kyc|know\s+your\s+customer|aml|anti[- ]money\s+laundering|cdd|customer\s+due\s+diligence)\b/i]),
      financialCompliance: scanKeywordEvidence(lines, 'Financial Compliance', [/\b(?:compliance|central\s+bank|cbsl|regulatory|basel|internal\s+control|audit\s+controls?)\b/i]),
    },
    achievements: {
      academicAchievements: scanKeywordEvidence(lines, 'Academic Achievements', [/\b(?:dean'?s\s+list|first\s+class|second\s+upper|scholarship|merit|top\s+of\s+class|valedictorian)\b/i]),
      awards: scanKeywordEvidence(lines, 'Awards', [/\b(?:award|prize|medal|champion|winner|runner[- ]up|trophy)\b/i]),
      leadershipActivities: scanKeywordEvidence(lines, 'Leadership Activities', [/\b(?:president|vice\s+president|captain|prefect|head\s+prefect|secretary|treasurer|committee\s+member|team\s+leader)\b/i]),
      volunteering: scanKeywordEvidence(lines, 'Volunteering', [/\b(?:volunteer|volunteered|volunteering|community\s+service|rotaract|leo\s+club|charity|literacy\s+workshops?)\b/i]),
      extracurricularActivities: scanKeywordEvidence(lines, 'Extracurricular Activities', [/\b(?:society|club|sports|athletics|cricket|badminton|debate|toastmasters|choir|chess)\b/i]),
      measurableAccomplishments: measLines.length
        ? {
            fieldName: 'Measurable Accomplishments',
            value: measLines.slice(0, 6),
            sourcePages: Array.from(measPages).sort((a, b) => a - b),
            status: 'extracted',
          }
        : notFound('Measurable Accomplishments'),
    },
    detectedSections: detectedOrder,
    missingSections,
  };
}
