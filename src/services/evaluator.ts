import { EVALUATION_CATEGORIES } from '../config/categories';
import type {
  CVEvaluationResult,
  CategoryEvaluation,
  EvaluationCategory,
  ExperienceEntry,
  ExtractedCVData,
  ExtractedField,
  FactorEvaluation,
  KeywordEvidenceValue,
  ProcessedPDFDocument,
} from '../types/cv';
import { analyzeLanguageQuality } from './languageChecker';

function clampScore(value: number): number {
  return Math.max(0, Math.min(5, Math.round(value)));
}

function notMentioned(factorName: string, reason?: string): FactorEvaluation {
  return {
    factorName,
    score: null,
    maxScore: 5,
    status: 'Not mentioned in CV',
    evidence: [],
    explanation: reason || `${factorName} is not mentioned in the uploaded CV.`,
    weakness: null,
    sourcePages: [],
  };
}

function cannotAssess(
  factorName: string,
  reason: string,
  evidence: string[] = [],
  sourcePages: number[] = [],
): FactorEvaluation {
  return {
    factorName,
    score: null,
    maxScore: 5,
    status: 'Cannot be assessed',
    evidence,
    explanation: reason,
    weakness: null,
    sourcePages,
  };
}

function evaluated(
  factorName: string,
  score: number,
  evidence: string[],
  explanation: string,
  weakness: string | null = null,
  sourcePages: number[] = [],
): FactorEvaluation {
  return {
    factorName,
    score: clampScore(score),
    maxScore: 5,
    status: 'Evaluated',
    evidence,
    explanation,
    weakness,
    sourcePages,
  };
}

function scoreSingleGradeToken(gradeText: string): { score: number; explanation: string } {
  const upper = gradeText.toUpperCase();
  const ielts = upper.match(/IELTS\s*[:\-–—]?\s*(\d(?:\.\d)?)/);
  if (ielts) {
    const band = parseFloat(ielts[1]);
    if (band >= 7.0) return { score: 5, explanation: `Strong IELTS band (${band}).` };
    if (band >= 6.0) return { score: 4, explanation: `Good IELTS band (${band}).` };
    if (band >= 5.5) return { score: 3, explanation: `Acceptable IELTS band (${band}).` };
    return { score: 2, explanation: `Below-target IELTS band (${band}).` };
  }
  if (/(?:[:\-–—]\s*A[+*]?|\bDISTINCTION\b)/.test(upper)) return { score: 5, explanation: "Distinction / 'A' grade recorded." };
  if (/(?:[:\-–—]\s*B\b|\bCREDIT\b)/.test(upper)) return { score: 4, explanation: "Credit / 'B' grade recorded." };
  if (/(?:[:\-–—]\s*C\b|\bPASS\b)/.test(upper)) return { score: 3, explanation: "Acceptable 'C' / Pass grade recorded." };
  if (/[:\-–—]\s*S\b/.test(upper)) return { score: 2, explanation: "Ordinary 'S' pass recorded." };
  if (/[:\-–—]\s*[FW]\b/.test(upper)) return { score: 1, explanation: 'Weak / Fail grade recorded.' };
  return { score: 3, explanation: 'Examination result recorded.' };
}

function evaluateCategory1Education(cv: ExtractedCVData): FactorEvaluation[] {
  const edu = cv.educationalQualifications;
  const factors: FactorEvaluation[] = [];

  // 1. O/L Results
  if (edu.gceOlResults.status === 'not_found') {
    factors.push(notMentioned('O/L Results'));
  } else if (edu.gceOlResults.status === 'partial') {
    factors.push(
      evaluated(
        'O/L Results',
        2,
        edu.gceOlResults.value || [],
        'G.C.E. O/L is mentioned, but individual subject grades or pass summary are missing.',
        'Specify G.C.E. O/L subject grades (especially Mathematics and English).',
        edu.gceOlResults.sourcePages,
      ),
    );
  } else {
    const vals = edu.gceOlResults.value || [];
    const joined = vals.join(' ');
    const aCountM = joined.match(/\b(\d+)\s*A(?:'s|s)?\b/i);
    const explicitA = (joined.match(/[:\-–—]\s*A\b/g) || []).length;
    const aTotal = aCountM ? parseInt(aCountM[1], 10) : explicitA;
    if (aTotal >= 7) factors.push(evaluated('O/L Results', 5, vals, `Strong G.C.E. O/L performance (${aTotal} A grade(s) documented).`, null, edu.gceOlResults.sourcePages));
    else if (aTotal >= 4) factors.push(evaluated('O/L Results', 4, vals, `Good G.C.E. O/L performance (${aTotal} A grade(s) documented).`, null, edu.gceOlResults.sourcePages));
    else if (/\b(?:pass|credit|distinction|[BCS])\b/i.test(joined)) factors.push(evaluated('O/L Results', 3, vals, 'Acceptable G.C.E. O/L results documented.', null, edu.gceOlResults.sourcePages));
    else factors.push(evaluated('O/L Results', 2, vals, 'G.C.E. O/L entry lacks clear grade strength.', 'Clarify complete O/L pass counts and grades.', edu.gceOlResults.sourcePages));
  }

  // 2. A/L Results
  if (edu.gceAlResults.status === 'not_found') {
    factors.push(notMentioned('A/L Results'));
  } else if (edu.gceAlResults.status === 'partial') {
    factors.push(
      evaluated(
        'A/L Results',
        2,
        edu.gceAlResults.value || [],
        'G.C.E. A/L is mentioned, but subject grades were not clearly provided.',
        'Include A/L stream, subject grades, and Z-score if applicable.',
        edu.gceAlResults.sourcePages,
      ),
    );
  } else {
    const vals = edu.gceAlResults.value || [];
    const joined = vals.join(' ');
    const aM = joined.match(/\b(\d+)\s*A(?:'s|s)?\b/i);
    const bM = joined.match(/\b(\d+)\s*B(?:'s|s)?\b/i);
    const aCnt = aM ? parseInt(aM[1], 10) : (joined.match(/[:\-–—]\s*A\b/g) || []).length;
    const bCnt = bM ? parseInt(bM[1], 10) : (joined.match(/[:\-–—]\s*B\b/g) || []).length;
    const cCnt = (joined.match(/[:\-–—]\s*C\b/g) || []).length;
    const sCnt = (joined.match(/[:\-–—]\s*S\b/g) || []).length;
    if (aCnt >= 3 || (aCnt >= 2 && bCnt >= 1)) factors.push(evaluated('A/L Results', 5, vals, "Excellent G.C.E. A/L results with multiple distinction ('A') grades.", null, edu.gceAlResults.sourcePages));
    else if (aCnt >= 1 || bCnt >= 2) factors.push(evaluated('A/L Results', 4, vals, 'Good G.C.E. A/L results documented.', null, edu.gceAlResults.sourcePages));
    else if (cCnt + sCnt >= 2 || /\b(?:3\s*passes|commerce|mathematics)\b/i.test(joined)) factors.push(evaluated('A/L Results', 3, vals, 'Acceptable G.C.E. A/L results documented.', null, edu.gceAlResults.sourcePages));
    else factors.push(evaluated('A/L Results', 2, vals, 'Below-average or incomplete A/L pass evidence.', 'Provide full A/L subject grades.', edu.gceAlResults.sourcePages));
  }

  // 3. English Results
  if (edu.englishResults.status === 'not_found') {
    factors.push(notMentioned('English Results'));
  } else {
    const vals = edu.englishResults.value || [];
    const scored = vals.map(scoreSingleGradeToken);
    const best = scored.reduce((a, b) => (b.score > a.score ? b : a));
    factors.push(evaluated('English Results', best.score, vals, best.explanation, best.score <= 2 ? 'Strengthen English certification or clarify grade.' : null, edu.englishResults.sourcePages));
  }

  // 4. Mathematics Results
  if (edu.mathematicsResults.status === 'not_found') {
    factors.push(notMentioned('Mathematics Results'));
  } else {
    const vals = edu.mathematicsResults.value || [];
    const scored = vals.map(scoreSingleGradeToken);
    const best = scored.reduce((a, b) => (b.score > a.score ? b : a));
    factors.push(evaluated('Mathematics Results', best.score, vals, best.explanation, best.score <= 2 ? 'Mathematics grade is below typical banking entry benchmarks.' : null, edu.mathematicsResults.sourcePages));
  }

  // 5. Degrees and Diplomas
  if (edu.degrees.status === 'not_found' && edu.diplomas.status === 'not_found') {
    factors.push(notMentioned('Degrees and Diplomas', 'No university degree or academic diploma is mentioned in the CV.'));
  } else if (edu.degrees.status !== 'not_found') {
    const vals = edu.degrees.value || [];
    const joined = vals.join(' ');
    const isFin = /\b(?:finance|banking|accounting|economics|commerce|business|management|financial|actuarial|statistics)\b/i.test(joined);
    const isOngoing = /\b(?:reading|undergraduate|pursuing|expected|ongoing)\b/i.test(joined);
    const gpaM = joined.match(/\b(\d\.\d{1,2})\s*(?:\/\s*4(?:\.00?)?)?/);
    const gpa = gpaM && parseFloat(gpaM[1]) <= 4.0 ? parseFloat(gpaM[1]) : null;
    if (isFin && (/\bfirst\s+class\b/i.test(joined) || (gpa !== null && gpa >= 3.5))) {
      factors.push(evaluated('Degrees and Diplomas', 5, vals, 'Relevant banking/finance/business degree with strong academic standing (First Class or GPA >= 3.5).', null, edu.degrees.sourcePages));
    } else if (isFin && (/\bsecond\s+upper\b/i.test(joined) || (gpa !== null && gpa >= 3.0))) {
      factors.push(evaluated('Degrees and Diplomas', 4, vals, 'Relevant finance/business degree with good standing (Second Upper or GPA >= 3.0).', null, edu.degrees.sourcePages));
    } else if (isFin && !isOngoing) {
      factors.push(evaluated('Degrees and Diplomas', 4, vals, 'Completed banking/finance/business degree documented.', gpa ? null : 'Include GPA or degree classification if available.', edu.degrees.sourcePages));
    } else if (isOngoing) {
      factors.push(evaluated('Degrees and Diplomas', 3, vals, 'Undergraduate degree currently in progress.', gpa ? null : 'State expected graduation year and current GPA if available.', edu.degrees.sourcePages));
    } else {
      factors.push(evaluated('Degrees and Diplomas', 3, vals, 'University degree documented outside core finance/accounting subjects.', null, edu.degrees.sourcePages));
    }
  } else {
    const vals = edu.diplomas.value || [];
    const isFin = /\b(?:finance|banking|accounting|business|commerce|management)\b/i.test(vals.join(' '));
    factors.push(evaluated('Degrees and Diplomas', isFin ? 3 : 2, vals, isFin ? 'Relevant business/finance diploma documented.' : 'Non-finance diploma documented.', null, edu.diplomas.sourcePages));
  }

  // 6. Banking & Finance Qualifications
  if (edu.bankingFinanceQualifications.status === 'not_found') {
    factors.push(notMentioned('Banking and Finance Qualifications'));
  } else {
    const vals = edu.bankingFinanceQualifications.value || [];
    const joined = vals.join(' ');
    const sc = /\b(?:dabf|dbf|iabf|diploma\s+in\s+(?:applied\s+)?banking|fmva)\b/i.test(joined)
      ? 5
      : /\b(?:cbf|ibsl|bmc|bloomberg\s+market\s+concepts|certificate\s+in\s+banking)\b/i.test(joined)
        ? 4
        : 3;
    factors.push(evaluated('Banking and Finance Qualifications', sc, vals, 'Banking or finance-related qualification documented.', null, edu.bankingFinanceQualifications.sourcePages));
  }

  // 7. Professional Qualifications
  if (edu.professionalQualifications.status === 'not_found') {
    factors.push(notMentioned('Professional Qualifications'));
  } else {
    const vals = edu.professionalQualifications.value || [];
    const joined = vals.join(' ');
    let sc = 2;
    let wk: string | null = 'Specify exact level/papers completed (e.g., CIMA Operational Level, AAT Stage II).';
    if (/\b(?:finalist|affiliate|member|acma|cgma|aca|passed\s+final|cfa\s+level\s*(?:ii|iii|2|3))\b/i.test(joined)) {
      sc = 5;
      wk = null;
    } else if (/\b(?:strategic|managerial|management\s+level|applied\s+skills|cfa\s+level\s*(?:i|1)\s+passed|aat\s+(?:passed|final))\b/i.test(joined)) {
      sc = 4;
      wk = null;
    } else if (/\b(?:operational|foundation|knowledge|certificate|level\s*(?:1|i)|candidate|part|reading|following|passed)\b/i.test(joined)) {
      sc = 3;
      wk = null;
    }
    factors.push(evaluated('Professional Qualifications', sc, vals, 'Professional accounting/finance progress documented.', wk, edu.professionalQualifications.sourcePages));
  }

  return factors;
}

function evaluateCategory2Experience(cv: ExtractedCVData): FactorEvaluation[] {
  const entries = cv.professionalExperience.experienceEntries.value || [];
  if (entries.length === 0) {
    return [
      'Banking Experience',
      'Finance Company Experience',
      'Internships',
      'Customer Service Experience',
      'Cash Handling Experience',
      'Administrative Experience',
      'Sales Experience',
      'Employment Duration',
      'Relevance of Responsibilities',
    ].map((name) => notMentioned(name, 'No work experience or internship section was found in the CV.'));
  }

  const entryText = (e: ExperienceEntry) =>
    `${e.jobTitle || ''} ${e.companyName || ''} ${e.responsibilities.join(' ')}`.trim();
  const blocks = entries.map((e) => ({ entry: e, text: entryText(e) }));
  const expPages = cv.professionalExperience.experienceEntries.sourcePages;
  const factors: FactorEvaluation[] = [];

  const matchDomain = (rx: RegExp) => blocks.filter((b) => rx.test(b.text));

  const bankHits = matchDomain(/\b(?:bank|banking\s+intern|teller|commercial\s+bank|sampath|hsbc|hnb|hatton\s+national|seylan|ndb|dfcc|boc|bank\s+of\s+ceylon|people'?s\s+bank|nations\s+trust)\b/i);
  if (bankHits.length) {
    const months = bankHits.reduce((a, b) => a + (b.entry.durationMonths || 0), 0);
    const hasDuties = bankHits.some((b) => b.entry.responsibilities.length >= 1);
    const sc = months >= 6 && hasDuties ? 5 : hasDuties ? 4 : 3;
    factors.push(evaluated('Banking Experience', sc, bankHits.map((b) => `${b.entry.jobTitle || 'Role'} at ${b.entry.companyName || 'Bank'}`), 'Direct banking sector experience documented.', null, expPages));
  } else {
    factors.push(notMentioned('Banking Experience'));
  }

  const finHits = matchDomain(/\b(?:kpmg|pwc|ey|deloitte|bdo|audit|leasing|insurance|microfinance|capital|securities|brokerage|finance\s+(?:company|intern|trainee|executive)|accounts?\s+(?:trainee|assistant|executive))\b/i);
  if (finHits.length) {
    const months = finHits.reduce((a, b) => a + (b.entry.durationMonths || 0), 0);
    const hasDuties = finHits.some((b) => b.entry.responsibilities.length >= 1);
    const sc = months >= 6 && hasDuties ? 5 : hasDuties ? 4 : 3;
    factors.push(evaluated('Finance Company Experience', sc, finHits.map((b) => `${b.entry.jobTitle || 'Role'} at ${b.entry.companyName || 'Organization'}`), 'Financial services, audit, or accounting firm experience documented.', null, expPages));
  } else {
    factors.push(notMentioned('Finance Company Experience'));
  }

  const interns = cv.professionalExperience.internshipDetails.value || [];
  if (interns.length) {
    const bankingIntern = interns.some((e) => /\b(?:bank|finance|audit|credit|accounting|treasury)\b/i.test(entryText(e)));
    const hasDuties = interns.some((e) => e.responsibilities.length >= 1);
    const sc = bankingIntern && hasDuties ? 5 : hasDuties ? 4 : 3;
    factors.push(evaluated('Internships', sc, interns.map((e) => `${e.jobTitle || 'Intern'} at ${e.companyName || 'Organization'}`), 'Relevant entry-level internship or trainee experience documented.', hasDuties ? null : 'Add specific bulleted duties for the internship role.', cv.professionalExperience.internshipDetails.sourcePages));
  } else {
    factors.push(notMentioned('Internships'));
  }

  const custHits = matchDomain(/\b(?:customer|client|front\s+office|front\s+desk|call\s+cent(?:er|re)|inquiries|onboarding)\b/i);
  factors.push(
    custHits.length
      ? evaluated('Customer Service Experience', custHits.some((b) => /(?:\d+|bank|onboarding|kyc|branch)/i.test(b.text)) ? 4 : 3, custHits.map((b) => b.text.slice(0, 100)), 'Transferable customer-facing service experience documented.', null, expPages)
      : notMentioned('Customer Service Experience'),
  );

  const cashHits = matchDomain(/\b(?:cash|teller|cashier|petty\s+cash|till|vault|cheque|cash\s+reconciliation)\b/i);
  factors.push(
    cashHits.length
      ? evaluated('Cash Handling Experience', cashHits.some((b) => /\b(?:reconcil|audit|teller|vault|control)\b/i.test(b.text)) ? 4 : 3, cashHits.map((b) => b.text.slice(0, 120)), 'Cash or payment-handling responsibilities documented.', null, expPages)
      : notMentioned('Cash Handling Experience'),
  );

  const adminHits = matchDomain(/\b(?:admin(?:istrative)?|filing|documentation|data\s+entry|clerical|clerk|record\s+keeping|scheduling|correspondence)\b/i);
  factors.push(
    adminHits.length
      ? evaluated('Administrative Experience', adminHits.some((b) => /\b(?:documentation|compliance|loan|audit|record)\b/i.test(b.text)) ? 4 : 3, adminHits.map((b) => b.text.slice(0, 120)), 'Administrative and office documentation experience documented.', null, expPages)
      : notMentioned('Administrative Experience'),
  );

  const salesHits = matchDomain(/\b(?:sales|selling|cross[- ]sell|business\s+development|lead\s+generation|targets?|merchandising|account\s+acquisition)\b/i);
  factors.push(
    salesHits.length
      ? evaluated('Sales Experience', salesHits.some((b) => /\b(?:target|%|revenue|quota|exceeded)\b/i.test(b.text)) ? 4 : 3, salesHits.map((b) => b.text.slice(0, 120)), 'Transferable sales or business development experience documented.', null, expPages)
      : notMentioned('Sales Experience'),
  );

  const calcMonths = entries.filter((e) => typeof e.durationMonths === 'number').map((e) => e.durationMonths!);
  if (calcMonths.length === 0) {
    factors.push(
      cannotAssess(
        'Employment Duration',
        cv.professionalExperience.totalCalculableDuration.uncertainty || 'Employment dates lack month-level precision, so duration cannot be calculated.',
        entries.map((e) => e.employmentDates || 'No dates'),
        expPages,
      ),
    );
  } else {
    const totalM = calcMonths.reduce((a, b) => a + b, 0);
    const sc = totalM >= 24 ? 5 : totalM >= 12 ? 4 : totalM >= 6 ? 3 : totalM >= 3 ? 2 : 1;
    const wk = totalM < 6 ? 'Total documented experience duration is relatively brief (under 6 months).' : null;
    factors.push(evaluated('Employment Duration', sc, [String(cv.professionalExperience.totalCalculableDuration.value)], `Calculated ${totalM} month(s) across roles with month-level dates.`, wk, expPages));
  }

  const allResps = entries.flatMap((e) => e.responsibilities);
  if (allResps.length === 0) {
    factors.push(evaluated('Relevance of Responsibilities', 1, entries.map((e) => `${e.jobTitle || 'Role'} at ${e.companyName || 'Company'}`), 'Role titles are listed, but no specific responsibilities were documented.', 'Add 3-5 bullet points per role describing concrete banking, finance, analytical, or client duties.', expPages));
  } else {
    const joined = allResps.join(' ');
    const directBf = (joined.match(/\b(?:kyc|aml|credit|loan|deposit|account\s+opening|reconcil|financial\s+statement|audit|ifrs|teller|treasury|compliance)\b/gi) || []).length;
    const transferable = (joined.match(/\b(?:customer|client|excel|report|data|sales|cash|administration|documentation)\b/gi) || []).length;
    if (directBf >= 3) factors.push(evaluated('Relevance of Responsibilities', 5, allResps.slice(0, 3), 'Documented responsibilities align directly with entry-level banking and finance workflows.', null, expPages));
    else if (directBf >= 1) factors.push(evaluated('Relevance of Responsibilities', 4, allResps.slice(0, 3), 'Documented responsibilities include direct banking, finance, or audit duties.', null, expPages));
    else if (transferable >= 2) factors.push(evaluated('Relevance of Responsibilities', 3, allResps.slice(0, 3), 'Documented responsibilities demonstrate transferable client, analytical, or administrative skills.', 'Highlight quantitative, financial, or client-impact details where truthful.', expPages));
    else factors.push(evaluated('Relevance of Responsibilities', 2, allResps.slice(0, 3), 'Documented responsibilities have limited direct relevance to banking and finance.', 'Emphasize transferable accuracy, client handling, and numerical tasks.', expPages));
  }

  return factors;
}

function evaluateCategory3Technical(cv: ExtractedCVData, doc: ProcessedPDFDocument): FactorEvaluation[] {
  const ts = cv.technicalSkills;
  const lines = doc.textLines;
  const factors: FactorEvaluation[] = [];

  if (ts.microsoftExcel.status === 'not_found') {
    factors.push(notMentioned('Microsoft Excel'));
  } else {
    const ev = ts.microsoftExcel.value?.evidenceLines || [];
    const joined = ev.join(' ');
    if (/\b(?:vba|macros?|power\s+query|financial\s+model|advanced\s+excel|automated\s+dashboard)\b/i.test(joined)) {
      factors.push(evaluated('Microsoft Excel', 5, ev, 'Advanced Microsoft Excel capabilities are explicitly supported.', null, ts.microsoftExcel.sourcePages));
    } else if (/\b(?:pivot\s+tables?|vlookup|xlookup|hlookup|index|match|formulas?|intermediate)\b/i.test(joined)) {
      factors.push(evaluated('Microsoft Excel', 4, ev, 'Intermediate Microsoft Excel functions (e.g., Pivot Tables, VLOOKUP) are documented.', null, ts.microsoftExcel.sourcePages));
    } else if (/\bbasic\b/i.test(joined)) {
      factors.push(evaluated('Microsoft Excel', 2, ev, 'Basic Microsoft Excel familiarity stated.', 'Develop intermediate Excel skills (Pivot Tables, VLOOKUP) and document applied usage.', ts.microsoftExcel.sourcePages));
    } else {
      factors.push(evaluated('Microsoft Excel', 3, ev, 'Microsoft Excel is mentioned without specifying proficiency level or functions.', 'Specify Excel proficiency or functions used (e.g., Pivot Tables, VLOOKUP, financial schedules).', ts.microsoftExcel.sourcePages));
    }
  }

  factors.push(
    ts.microsoftWord.status === 'not_found'
      ? notMentioned('Microsoft Word')
      : evaluated('Microsoft Word', /\b(?:advanced|proficient|reports?|formatting|mail\s+merge)\b/i.test((ts.microsoftWord.value?.evidenceLines || []).join(' ')) ? 4 : 3, ts.microsoftWord.value?.evidenceLines || [], 'Microsoft Word proficiency documented.', null, ts.microsoftWord.sourcePages),
  );

  factors.push(
    ts.microsoftPowerPoint.status === 'not_found'
      ? notMentioned('Microsoft PowerPoint')
      : evaluated('Microsoft PowerPoint', /\b(?:advanced|proficient|presentation|deck|slides)\b/i.test((ts.microsoftPowerPoint.value?.evidenceLines || []).join(' ')) ? 4 : 3, ts.microsoftPowerPoint.value?.evidenceLines || [], 'Microsoft PowerPoint documented.', null, ts.microsoftPowerPoint.sourcePages),
  );

  if (ts.computerLiteracy.status === 'not_found') {
    const officePresent = [ts.microsoftWord, ts.microsoftExcel, ts.microsoftPowerPoint].filter((f) => f.status !== 'not_found');
    if (officePresent.length > 0) {
      factors.push(evaluated('Computer Literacy', 3, officePresent.flatMap((f) => f.value?.evidenceLines || []).slice(0, 2), 'General computer literacy supported by listed office applications.', null));
    } else {
      factors.push(notMentioned('Computer Literacy'));
    }
  } else {
    factors.push(evaluated('Computer Literacy', (ts.computerLiteracy.value?.matchedTerms.length || 0) >= 2 ? 4 : 3, ts.computerLiteracy.value?.evidenceLines || [], 'Computer literacy / office suite skills documented.', null, ts.computerLiteracy.sourcePages));
  }

  const deLines = lines.filter((l) => /\b(?:data\s+entry|database\s+entry|record\s+entry|typing\s+speed|wpm)\b/i.test(l.text));
  factors.push(
    deLines.length
      ? evaluated('Data Entry', deLines.some((l) => /\b(?:accuracy|\d+\s*wpm|verified|reconcil)\b/i.test(l.text)) ? 4 : 3, deLines.slice(0, 3).map((l) => l.text), 'Data entry capability documented.', null)
      : notMentioned('Data Entry'),
  );

  const ssLines = lines.filter((l) => /\b(?:spreadsheet|google\s+sheets|pivot\s+tables?|vlookup|xlookup|financial\s+schedules)\b/i.test(l.text));
  factors.push(
    ssLines.length
      ? evaluated('Spreadsheet Skills', ssLines.length >= 2 ? 4 : 3, ssLines.slice(0, 3).map((l) => l.text), 'Spreadsheet usage or analytical functions documented.', null)
      : notMentioned('Spreadsheet Skills'),
  );

  factors.push(
    ts.accountingSoftware.status === 'not_found'
      ? notMentioned('Accounting Software')
      : evaluated('Accounting Software', (ts.accountingSoftware.value?.matchedTerms.length || 0) >= 2 ? 5 : 4, ts.accountingSoftware.value?.evidenceLines || [], 'Accounting software proficiency documented.', null, ts.accountingSoftware.sourcePages),
  );

  const dbLines = lines.filter((l) => /\b(?:digital\s+banking|online\s+banking|mobile\s+banking|e-?banking|fintech|payment\s+gateway|finacle|temenos|t24|core\s+banking|swift|rtgs|ceft)\b/i.test(l.text));
  factors.push(
    dbLines.length
      ? evaluated('Digital Banking Knowledge', dbLines.length >= 2 ? 4 : 3, dbLines.slice(0, 3).map((l) => l.text), 'Digital or core banking systems knowledge documented.', null)
      : notMentioned('Digital Banking Knowledge'),
  );

  return factors;
}

function scoreLanguage(langName: string, cv: ExtractedCVData, examField?: ExtractedField<string[]>): FactorEvaluation {
  const entries = (cv.communicationAndLanguages.languagesAndProficiency.value || []).filter((l) => l.language.toLowerCase() === langName.toLowerCase());
  const examVals = examField && examField.status !== 'not_found' ? examField.value || [] : [];
  if (entries.length === 0 && examVals.length === 0) {
    return notMentioned(`${langName} Proficiency Evidence`, `No explicit ${langName} language proficiency or ${langName} examination grade was stated.`);
  }
  const ev: string[] = [];
  let profScore = 0;
  for (const item of entries) {
    ev.push(item.sourceLine);
    const p = item.proficiency.toLowerCase();
    if (/native|mother tongue|bilingual|fluent|c2|c1/.test(p)) profScore = Math.max(profScore, 5);
    else if (/proficient|very good|full professional|professional working|oral & written|oral and written|b2/.test(p)) profScore = Math.max(profScore, 4);
    else if (/conversational|intermediate|good|working knowledge|b1/.test(p)) profScore = Math.max(profScore, 3);
    else profScore = Math.max(profScore, 2);
  }
  let examScore = 0;
  if (examVals.length) {
    ev.push(...examVals);
    examScore = Math.max(...examVals.map((v) => scoreSingleGradeToken(v).score));
  }
  let finalScore = profScore && examScore ? Math.round((profScore + examScore) / 2) : profScore || examScore;
  if (profScore >= 4 && examScore >= 4) finalScore = Math.max(finalScore, 4);
  const wk = entries.length && entries.every((m) => m.proficiency === 'Not explicitly stated') && !examVals.length
    ? `Stated ${langName} proficiency level is unspecified; clarify written and spoken level.`
    : null;
  return evaluated(`${langName} Proficiency Evidence`, finalScore, Array.from(new Set(ev)), `Evaluated from documented ${langName} proficiency/exam evidence in the CV.`, wk);
}

function evaluateCategory4Communication(cv: ExtractedCVData, doc: ProcessedPDFDocument): FactorEvaluation[] {
  const lines = doc.textLines;
  const factors: FactorEvaluation[] = [
    scoreLanguage('English', cv, cv.educationalQualifications.englishResults),
    scoreLanguage('Sinhala', cv),
    scoreLanguage('Tamil', cv),
  ];

  const written = lines.filter((l) => /\b(?:report\s+writing|written\s+communication|oral\s*(?:&|and)\s*written|memos?|correspondence|business\s+writing|minutes|drafted|prepared\s+reports?)\b/i.test(l.text));
  factors.push(written.length ? evaluated('Written Communication Evidence', written.length >= 2 ? 4 : 3, written.slice(0, 3).map((l) => l.text), 'Written business or reporting communication evidence documented.', null) : notMentioned('Written Communication Evidence'));

  const cust = cv.communicationAndLanguages.customerServiceExperience;
  factors.push(cust.status === 'not_found' ? notMentioned('Customer Communication Experience') : evaluated('Customer Communication Experience', (cust.value?.evidenceLines || []).some((e) => /(?:\d+|bank|client|inquiries|onboarding)/i.test(e)) ? 4 : 3, cust.value?.evidenceLines || [], 'Customer-facing communication responsibilities documented.', null, cust.sourcePages));

  const pres = lines.filter((l) => /\b(?:presentation|presented|public\s+speaking|toastmasters|debat(?:e|ing)|oratory|pitched)\b/i.test(l.text));
  factors.push(pres.length ? evaluated('Presentation Experience', pres.length >= 2 || pres.some((l) => /toastmasters|weekly|client|leadership|society/i.test(l.text)) ? 4 : 3, pres.slice(0, 3).map((l) => l.text), 'Presentation or public speaking experience documented.', null) : notMentioned('Presentation Experience'));

  const interp = lines.filter((l) => /\b(?:interpersonal|teamwork|stakeholder|liaised|collaborated|cross[- ]functional|relationship)\b/i.test(l.text));
  factors.push(interp.length ? evaluated('Interpersonal Communication Evidence', interp.length >= 2 ? 4 : 3, interp.slice(0, 3).map((l) => l.text), 'Teamwork, stakeholder, or interpersonal communication evidence documented.', null) : notMentioned('Interpersonal Communication Evidence'));

  return factors;
}

function evalBankingFactor(name: string, field: ExtractedField<KeywordEvidenceValue>, cv: ExtractedCVData): FactorEvaluation {
  if (field.status === 'not_found') return notMentioned(name);
  const evLines = field.value?.evidenceLines || [];
  const entries = cv.professionalExperience.experienceEntries.value || [];
  const expCorpus = entries.map((e) => `${e.jobTitle || ''} ${e.responsibilities.join(' ')}`).join(' ').toLowerCase();
  const hasRelQual =
    cv.educationalQualifications.bankingFinanceQualifications.status !== 'not_found' ||
    cv.educationalQualifications.professionalQualifications.status !== 'not_found';
  const inExp = evLines.some((line) => expCorpus.includes(line.toLowerCase()));
  const actionLike = evLines.some((line) => line.split(/\s+/).length >= 5 && /\b(?:assisted|prepared|reconcil|verified|managed|supported|evaluated|handled|audited|analyzed|processed)\b/i.test(line));
  if ((inExp || actionLike) && hasRelQual) return evaluated(name, 5, evLines, `Demonstrated ${name.toLowerCase()} supported by practical duties and relevant qualifications.`, null, field.sourcePages);
  if (inExp || actionLike) return evaluated(name, 4, evLines, `Demonstrated ${name.toLowerCase()} inside documented responsibilities.`, null, field.sourcePages);
  if (hasRelQual) return evaluated(name, 3, evLines, `${name} referenced alongside relevant finance/banking qualifications.`, null, field.sourcePages);
  return evaluated(name, 2, evLines, `${name} appears only as a brief claim without supporting work or coursework context.`, `Substantiate ${name.toLowerCase()} with concrete coursework, certifications, or applied tasks.`, field.sourcePages);
}

function evaluateCategory5Banking(cv: ExtractedCVData, doc: ProcessedPDFDocument): FactorEvaluation[] {
  const bf = cv.bankingAndFinanceKnowledge;
  const lines = doc.textLines;
  const scanAdHoc = (name: string, rx: RegExp): ExtractedField<KeywordEvidenceValue> => {
    const hits = lines.filter((l) => rx.test(l.text));
    if (!hits.length) return { fieldName: name, value: null, sourcePages: [], status: 'not_found' };
    return {
      fieldName: name,
      value: { matchedTerms: [name], evidenceLines: hits.slice(0, 4).map((h) => h.text) },
      sourcePages: Array.from(new Set(hits.map((h) => h.pageNumber))),
      status: 'extracted',
    };
  };
  return [
    evalBankingFactor('Banking Operations', bf.bankingOperations, cv),
    evalBankingFactor('Financial Services', bf.financialServices, cv),
    evalBankingFactor('Accounting Knowledge', bf.accounting, cv),
    evalBankingFactor('Loans and Credit', bf.loansAndCredit, cv),
    evalBankingFactor('Deposit and Savings Products', bf.depositsAndSavings, cv),
    evalBankingFactor('Financial Calculations', scanAdHoc('Financial Calculations', /\b(?:ratio\s+analysis|dcf|npv|irr|valuation|amortization|interest\s+calculat|variance\s+analysis|financial\s+model|financial\s+calculat|reconcil(?:e|ed|iation))\b/i), cv),
    evalBankingFactor('Customer Relationship Management', scanAdHoc('Customer Relationship Management', /\b(?:crm|customer\s+relationship|client\s+relationship|relationship\s+management|client\s+retention|portfolio\s+servicing)\b/i), cv),
    evalBankingFactor('KYC and AML Awareness', bf.kycAndAml, cv),
    evalBankingFactor('Financial Compliance', bf.financialCompliance, cv),
  ];
}

function evaluateCategory6Achievements(cv: ExtractedCVData, doc: ProcessedPDFDocument): FactorEvaluation[] {
  const ach = cv.achievements;
  const evalKw = (label: string, f: ExtractedField<KeywordEvidenceValue>, desc: string) =>
    f.status === 'not_found' ? notMentioned(label) : evaluated(label, (f.value?.evidenceLines.length || 0) >= 2 ? 5 : 4, f.value?.evidenceLines || [], desc, null, f.sourcePages);

  const entries = cv.professionalExperience.experienceEntries.value || [];
  const profHits = entries.flatMap((e) => e.responsibilities).filter((r) => /\b(?:award|recognized|top\s+performer|best\s+intern|promoted|commendation|exceeded\s+target)\b/i.test(r));
  const projLines = doc.textLines.filter((l) => /\b(?:project|dissertation|thesis|capstone|case\s+study|research\s+paper)\b/i.test(l.text));
  const measVals = ach.measurableAccomplishments.value || [];

  return [
    evalKw('Academic Achievements', ach.academicAchievements, 'Academic honors or distinction documented.'),
    profHits.length ? evaluated('Professional Achievements', 4, profHits.slice(0, 3), 'Work-related recognition or target achievement documented.', null) : notMentioned('Professional Achievements'),
    evalKw('Awards', ach.awards, 'Awards, scholarships, or competition honors documented.'),
    evalKw('Leadership', ach.leadershipActivities, 'Leadership roles documented.'),
    evalKw('Volunteering', ach.volunteering, 'Volunteering and community involvement documented.'),
    evalKw('Sports and Extracurricular Activities', ach.extracurricularActivities, 'Extracurricular or sports participation documented.'),
    projLines.length ? evaluated('Projects', projLines.some((l) => /\b(?:finance|banking|credit|valuation|portfolio|stock|market|accounting|risk)\b/i.test(l.text)) ? 4 : 3, projLines.slice(0, 3).map((l) => l.text), 'Academic or applied project work documented.', null) : notMentioned('Projects'),
    ach.measurableAccomplishments.status === 'not_found' ? notMentioned('Measurable Accomplishments') : evaluated('Measurable Accomplishments', measVals.length >= 3 ? 5 : measVals.length === 2 ? 4 : 3, measVals.slice(0, 4), `${measVals.length} quantified accomplishment(s) documented.`, null, ach.measurableAccomplishments.sourcePages),
  ];
}

function evaluateCategory7Structure(doc: ProcessedPDFDocument, cv: ExtractedCVData): FactorEvaluation[] {
  const detected = cv.detectedSections;
  const lines = doc.textLines;
  const factors: FactorEvaluation[] = [];

  if (!detected.length) {
    factors.push(evaluated('Logical Section Arrangement', 2, [], 'No standard section headings were detected.', 'Add clear section headings (Education, Experience, Technical Skills, Languages, Achievements).'));
  } else {
    let sc = 5;
    let wk: string | null = null;
    if (detected.includes('referees') && detected.indexOf('referees') < detected.length - 1) {
      sc = 4;
      wk = 'Place Referees at the end of the CV.';
    } else if (detected.length < 3) {
      sc = 3;
      wk = 'Organize CV into more distinct standard sections.';
    }
    factors.push(evaluated('Logical Section Arrangement', sc, [`Section order: ${detected.join(' -> ')}`], 'Evaluated top-to-bottom section sequence.', wk));
  }

  const hc = detected.length;
  factors.push(
    evaluated(
      'Clear Section Headings',
      hc >= 5 ? 5 : hc >= 4 ? 4 : hc >= 2 ? 3 : 1,
      hc ? detected : ['None detected'],
      `${hc} standard section heading(s) identified.`,
      hc >= 4 ? null : hc >= 2 ? 'Add dedicated headings for missing standard CV sections.' : 'Standard CV section headings are largely absent.',
    ),
  );

  const p = cv.personalAndContact;
  const present = [p.candidateName, p.emailAddress, p.telephoneNumber, p.location].filter((f) => f.status !== 'not_found');
  const onP1 = present.length > 0 && present.every((f) => f.sourcePages.includes(1));
  const cSc = present.length === 4 && onP1 ? 5 : present.length >= 3 && onP1 ? 4 : present.length >= 2 ? 3 : 1;
  const cWk =
    cSc === 5 ? null : cSc === 4 ? 'Include all core contact fields (name, email, phone, location) at the top of Page 1.' : cSc === 3 ? 'Contact block is incomplete or not fully placed on Page 1.' : 'Essential contact information is missing from the CV header.';
  factors.push(evaluated('Contact Information Placement', cSc, present.map((f) => `${f.fieldName}: ${f.value}`), `${present.length} of 4 core contact fields detected on Page 1.`, cWk));

  const edu = cv.educationalQualifications;
  if (!detected.includes('education') && edu.degrees.status === 'not_found' && edu.gceOlResults.status === 'not_found') {
    factors.push(notMentioned('Education Organization', 'No Education section was found in the CV.'));
  } else {
    const pop = [edu.degrees, edu.diplomas, edu.gceAlResults, edu.gceOlResults].filter((f) => f.status !== 'not_found').length;
    const eSc = detected.includes('education') && pop >= 2 ? 5 : pop >= 1 ? 4 : 2;
    factors.push(evaluated('Education Organization', eSc, [`Education heading present: ${detected.includes('education')}`], 'Evaluated clarity and grouping of educational credentials.', eSc >= 4 ? null : 'Group degrees, A/Ls, and O/Ls clearly under a dedicated Education heading.'));
  }

  const expEntries = cv.professionalExperience.experienceEntries.value || [];
  if (!expEntries.length) {
    factors.push(
      detected.includes('experience')
        ? evaluated('Work Experience Organization', 2, [], 'Experience heading is present, but structured role/date/bullet entries could not be separated.', 'Format each role clearly as Title - Company | Start - End Date followed by bullet points.')
        : notMentioned('Work Experience Organization', 'No Work Experience section was found in the CV.'),
    );
  } else {
    const complete = expEntries.filter((e) => e.jobTitle && e.companyName && e.employmentDates && e.responsibilities.length).length;
    const ratio = complete / expEntries.length;
    const wSc = ratio === 1 ? 5 : ratio >= 0.5 ? 4 : 3;
    factors.push(evaluated('Work Experience Organization', wSc, [`${complete}/${expEntries.length} entries fully structured`], 'Evaluated completeness of role, company, date, and duty structure.', wSc === 5 ? null : 'Ensure every role specifies job title, company name, month/year dates, and bulleted duties.'));
  }

  const years = lines.flatMap((l) => l.text.match(/\b(?:19|20)\d{2}\b/g) || []);
  if (expEntries.length >= 2) {
    const invalid = expEntries.some((e) => e.durationDisplay.toLowerCase().includes('invalid'));
    const missingDates = expEntries.filter((e) => !e.employmentDates).length;
    if (invalid) factors.push(evaluated('Chronological Consistency', 1, expEntries.map((e) => e.employmentDates || 'Missing'), 'One or more employment date ranges appear chronologically invalid.', 'Correct start and end dates on employment entries.'));
    else if (missingDates > 0) factors.push(evaluated('Chronological Consistency', 3, expEntries.map((e) => e.employmentDates || 'Missing'), `${missingDates} role(s) are missing dates.`, 'Add consistent Month Year - Month Year dates to every entry.'));
    else factors.push(evaluated('Chronological Consistency', 5, expEntries.map((e) => e.employmentDates || ''), 'Experience dates are consistently formatted and chronologically coherent.', null));
  } else if (years.length >= 2) {
    factors.push(evaluated('Chronological Consistency', 4, [`Years cited: ${years.slice(0, 6).join(', ')}`], 'Dates across sections are consistent.', null));
  } else {
    factors.push(cannotAssess('Chronological Consistency', 'Fewer than two dated entries exist to evaluate chronological ordering.'));
  }

  const mCnt = cv.missingSections.length;
  factors.push(
    evaluated(
      'Information Completeness',
      mCnt === 0 ? 5 : mCnt === 1 ? 4 : mCnt === 2 ? 3 : 2,
      [`Detected: ${detected.join(', ') || 'None'}`],
      `${detected.length} section groups detected; ${mCnt} core section(s) missing.`,
      mCnt === 0 ? null : `Missing standard sections: ${cv.missingSections.join(', ')}.`,
    ),
  );

  const normLines = lines.map((l) => l.text.trim().toLowerCase()).filter((t) => t.split(/\s+/).length >= 4);
  const lineCounts = new Map<string, number>();
  normLines.forEach((t) => lineCounts.set(t, (lineCounts.get(t) || 0) + 1));
  const dupLines = Array.from(lineCounts.entries()).filter(([, c]) => c > 1).map(([t]) => t);
  const irrelevantBio = lines.filter((l) => /\b(?:marital\s+status|religion|ethnicity|height|weight|passport\s+no|father'?s\s+name)\b/i.test(l.text)).map((l) => l.text);
  const relSc = dupLines.length || irrelevantBio.length >= 2 ? 3 : irrelevantBio.length ? 4 : 5;
  const relWk = relSc === 3 ? 'Remove duplicate lines or non-relevant personal details.' : relSc === 4 ? 'Consider removing non-essential personal attributes.' : null;
  factors.push(evaluated('Relevant Information', relSc, [...dupLines, ...irrelevantBio].slice(0, 3).length ? [...dupLines, ...irrelevantBio].slice(0, 3) : ['Focused professional content'], 'Checked for duplicated lines and irrelevant personal attributes.', relWk));

  const pages = doc.pageCount;
  const words = doc.wordCount;
  if (pages >= 1 && pages <= 2 && words >= 200 && words <= 950) factors.push(evaluated('Appropriate CV Length', 5, [`${pages} page(s), ${words} words`], `Appropriate entry-level length (${pages} page(s), ${words} words).`, null));
  else if (pages >= 1 && pages <= 2 && words >= 120 && words < 200) factors.push(evaluated('Appropriate CV Length', 3, [`${pages} page(s), ${words} words`], `Page count is concise (${pages} page(s)), though word count (${words}) is sparse.`, 'Expand key education/project/experience bullet details.'));
  else if (pages === 3 || words > 950) factors.push(evaluated('Appropriate CV Length', 3, [`${pages} page(s), ${words} words`], `Slightly long for an entry-level CV (${pages} pages, ${words} words).`, 'Aim for 1-2 tight, high-impact pages.'));
  else factors.push(evaluated('Appropriate CV Length', 2, [`${pages} page(s), ${words} words`], `Length is atypical (${pages} page(s), ${words} words).`, 'Adjust CV length to 1-2 well-balanced pages.'));

  return factors;
}

function evaluateCategory8Language(doc: ProcessedPDFDocument): FactorEvaluation[] {
  const r = analyzeLanguageQuality(doc.textLines);
  const fmt = (arr: { incorrect: string; correction: string; pageNumber: number }[]) =>
    arr.slice(0, 5).map((f) => `'${f.incorrect}' -> '${f.correction}' (p.${f.pageNumber})`);

  return [
    r.spellingFindings.length === 0
      ? evaluated('Spelling', 5, ['No unambiguous misspellings detected.'], 'Clean spelling across extracted text.', null)
      : evaluated('Spelling', r.spellingFindings.length <= 3 ? Math.max(1, 5 - r.spellingFindings.length) : 1, fmt(r.spellingFindings), `Detected ${r.spellingFindings.length} spelling error(s).`, `Fix spelling errors: ${fmt(r.spellingFindings).join('; ')}.`),
    r.grammarFindings.length === 0
      ? evaluated('Grammar', 5, ['No rule-based grammar errors detected.'], 'Grammar rules checked cleanly.', null)
      : evaluated('Grammar', r.grammarFindings.length <= 3 ? Math.max(1, 5 - r.grammarFindings.length) : 1, fmt(r.grammarFindings), `Detected ${r.grammarFindings.length} grammar issue(s).`, `Correct grammar issues: ${fmt(r.grammarFindings).join('; ')}.`),
    r.bulletCount === 0 && doc.wordCount < 80
      ? evaluated('Sentence Construction', 3, [`${doc.wordCount} total words`], 'Limited bullet statements available.', 'Add structured bullet statements describing accomplishments.')
      : r.longBulletCount === 0 && r.fragmentedLineCount <= 1
        ? evaluated('Sentence Construction', 5, [`${r.bulletCount} bullet(s), avg ${r.avgBulletWords} words`], 'Concise, well-constructed CV statements.', null)
        : evaluated('Sentence Construction', r.longBulletCount + r.fragmentedLineCount <= 3 ? 3 : 2, [`${r.longBulletCount} long bullet(s), ${r.fragmentedLineCount} fragment(s)`], 'Some bullets are overly long or fragmented.', 'Keep each bullet between 8 and 25 words with a clear verb + outcome.'),
    r.punctuationFindings.length === 0
      ? evaluated('Punctuation', 5, ['Clean punctuation spacing.'], 'No punctuation spacing errors detected.', null)
      : evaluated('Punctuation', Math.max(2, 5 - r.punctuationFindings.length), fmt(r.punctuationFindings), `Detected ${r.punctuationFindings.length} punctuation issue(s).`, `Fix punctuation spacing: ${fmt(r.punctuationFindings).join('; ')}.`),
    r.capitalizationFindings.length === 0
      ? evaluated('Capitalization', 5, ['Consistent capitalization of proper nouns and bullet starters.'], 'No capitalization errors detected.', null)
      : evaluated('Capitalization', Math.max(2, 5 - r.capitalizationFindings.length), fmt(r.capitalizationFindings), `Detected ${r.capitalizationFindings.length} capitalization issue(s).`, `Fix capitalization: ${fmt(r.capitalizationFindings).join('; ')}.`),
    evaluated(
      'Professional Vocabulary',
      r.actionVerbHits >= 4 && r.weakPhraseHits === 0 ? 5 : r.actionVerbHits >= 2 ? 4 : r.actionVerbHits >= 1 || r.weakPhraseHits >= 1 ? 3 : 2,
      [`${r.actionVerbHits} action-verb line(s), ${r.weakPhraseHits} weak passive phrase(s)`],
      'Evaluated presence of active professional verbs vs passive phrases.',
      r.actionVerbHits >= 4 && r.weakPhraseHits === 0 ? null : r.weakPhraseHits ? "Replace passive phrases like 'Responsible for' with strong action verbs." : 'Use stronger banking/finance action verbs.',
    ),
    r.bulletCount > 0
      ? evaluated('Sentence Clarity', r.avgBulletWords >= 7 && r.avgBulletWords <= 22 ? 5 : r.avgBulletWords <= 28 ? 4 : 3, [`Average bullet length: ${r.avgBulletWords} words`], 'Evaluated conciseness of bullet statements.', r.avgBulletWords > 28 ? 'Shorten dense bullets for rapid scanning.' : null)
      : evaluated('Sentence Clarity', 3, ['No bulleted responsibility statements detected'], 'Bullet points would improve clarity.', 'Use concise bullet points under experience entries.'),
    r.repeatedWordFindings.length === 0 && r.repeatedOpenerPhrases.length === 0
      ? evaluated('Repeated Words', 5, ['No adjacent duplicate words or repetitive bullet openers detected.'], 'Good lexical variety.', null)
      : evaluated('Repeated Words', Math.max(1, 5 - r.repeatedWordFindings.length * 2 - r.repeatedOpenerPhrases.length), [...fmt(r.repeatedWordFindings), ...r.repeatedOpenerPhrases], 'Detected repeated consecutive words or overused starting phrases.', 'Vary wording and remove duplicate words.'),
    r.bulletPeriodConsistencyPct === null
      ? cannotAssess('Consistency of Writing Style', 'Fewer than two bullet points were found to evaluate consistency.')
      : evaluated('Consistency of Writing Style', r.bulletPeriodConsistencyPct >= 90 ? 5 : r.bulletPeriodConsistencyPct >= 75 ? 4 : 3, [`Bullet punctuation consistency: ${r.bulletPeriodConsistencyPct}%`], 'Checked uniform ending punctuation across bullet points.', r.bulletPeriodConsistencyPct >= 90 ? null : `Standardize bullet ending punctuation (currently ${r.bulletPeriodConsistencyPct}% consistent).`),
  ];
}

function evaluateCategory9Visual(doc: ProcessedPDFDocument): FactorEvaluation[] {
  const analysis = doc.documentAnalysis;
  const pms = analysis.pageMetrics;
  const lines = doc.textLines;
  const factors: FactorEvaluation[] = [];

  const baseFamilies = new Set(
    analysis.fontNames.map((fn) => fn.replace(/^(?:[A-Z]{6}\+)?/, '').split('-')[0].split(',')[0].trim()).filter(Boolean),
  );
  const famCount = baseFamilies.size;
  factors.push(
    famCount === 0
      ? cannotAssess('Font Consistency', 'No embedded font metadata was detected.')
      : evaluated('Font Consistency', famCount <= 2 ? 5 : famCount === 3 ? 4 : famCount === 4 ? 2 : 1, Array.from(baseFamilies).sort(), `${famCount} base font family/families detected.`, famCount <= 2 ? null : `Standardize to 1-2 font families (currently ${famCount} detected).`),
  );

  const bodyPt = analysis.primaryBodyFontSizePt;
  if (bodyPt === null) {
    factors.push(cannotAssess('Font Readability', 'Primary body font size could not be measured.'));
  } else {
    const sc = bodyPt >= 9.5 && bodyPt <= 12 ? 5 : (bodyPt >= 8.5 && bodyPt < 9.5) || (bodyPt > 12 && bodyPt <= 13) ? 4 : bodyPt >= 7.5 && bodyPt < 8.5 ? 3 : 2;
    const wk = sc <= 3 ? `Primary body font (${bodyPt} pt) is outside optimal range (9.5-12 pt).` : null;
    factors.push(evaluated('Font Readability', sc, [`Primary body font size: ${bodyPt} pt`], 'Evaluated measurable body text point size.', wk));
  }

  const sizes = analysis.fontSizesPt;
  if (!sizes.length) {
    factors.push(cannotAssess('Font Size Consistency', 'No font size measurements available.'));
  } else {
    const hasHier = analysis.largestHeadingFontSizePt !== null && bodyPt !== null && analysis.largestHeadingFontSizePt > bodyPt;
    const sc = sizes.length >= 2 && sizes.length <= 4 && hasHier ? 5 : sizes.length <= 5 ? 4 : 2;
    const wk = sc === 2 ? `Too many distinct font sizes (${sizes.length} sizes); standardize to 2-4 sizes.` : sc === 4 && !hasHier ? 'Use slightly larger heading font sizes to establish clear visual hierarchy.' : null;
    factors.push(evaluated('Font Size Consistency', sc, [`Font sizes (pt): ${sizes.join(', ')}`], 'Evaluated typographic size hierarchy and restraint.', wk));
  }

  const medGaps = pms.map((p) => p.medianLineGapPt).filter((g): g is number => g !== null);
  if (!medGaps.length) {
    factors.push(cannotAssess('Paragraph Spacing', 'Insufficient multi-line spacing data.'));
  } else {
    const avgGap = Math.round((medGaps.reduce((a, b) => a + b, 0) / medGaps.length) * 100) / 100;
    const sc = avgGap >= 1.5 && avgGap <= 8 ? 5 : (avgGap >= 0.8 && avgGap < 1.5) || (avgGap > 8 && avgGap <= 12) ? 4 : 2;
    factors.push(evaluated('Paragraph Spacing', sc, [`Median line gap: ${avgGap} pt`], 'Measured vertical line-to-line spacing across pages.', sc === 2 ? `Line spacing (${avgGap} pt median gap) is overly tight or excessively wide.` : null));
  }

  const totalSecGaps = pms.reduce((a, p) => a + p.sectionGapCount, 0);
  factors.push(
    lines.length < 5
      ? cannotAssess('Section Spacing', 'Insufficient lines to measure section breaks.')
      : evaluated('Section Spacing', totalSecGaps >= 3 ? 5 : totalSecGaps >= 1 ? 4 : 2, [`Distinct section gaps detected: ${totalSecGaps}`], 'Measured vertical breaks separating sections.', totalSecGaps >= 1 ? null : 'Add clearer vertical whitespace breaks between CV sections.'),
  );

  const alignNotes = pms.flatMap((p) => p.alignmentIndicators);
  const consistentLeft = alignNotes.some((n) => n.includes('Consistent left-aligned'));
  factors.push(evaluated('Text Alignment', consistentLeft ? 5 : 3, Array.from(new Set(alignNotes)), 'Evaluated x-coordinate alignment consistency across text lines.', consistentLeft ? null : 'Align section text along consistent left margin anchors.'));

  const marginsPresent = pms.filter((p) => p.leftMarginPt !== null);
  if (!marginsPresent.length) {
    factors.push(cannotAssess('Margin Consistency', 'No text bounding boxes available to measure margins.'));
  } else {
    const minMargin = Math.min(...marginsPresent.map((p) => Math.min(p.leftMarginPt || 0, p.rightMarginPt || 0, p.topMarginPt || 0, p.bottomMarginPt || 0)));
    const sc = minMargin >= 28 ? 5 : minMargin >= 18 ? 4 : minMargin >= 10 ? 3 : 2;
    const wk = sc <= 3 ? `Margins are narrow (minimum ${minMargin} pt); aim for >= 28 pt.` : null;
    factors.push(evaluated('Margin Consistency', sc, marginsPresent.map((p) => `P${p.pageNumber}: min ${minMargin} pt`), 'Measured page margins from text bounding boxes.', wk));
  }

  const bulletChars = lines.map((l) => l.text.trim()).filter((t) => /^[•●▪▫◦\-*]\s+/.test(t)).map((t) => t[0]);
  if (!bulletChars.length) {
    factors.push(cannotAssess('Bullet-Point Formatting', 'No bulleted list symbols were detected.'));
  } else {
    const uniq = Array.from(new Set(bulletChars));
    factors.push(evaluated('Bullet-Point Formatting', uniq.length === 1 ? 5 : uniq.length === 2 ? 3 : 2, [`${bulletChars.length} bullet(s) using: ${uniq.join(', ')}`], 'Evaluated bullet symbol uniformity.', uniq.length === 1 ? null : `Mixed bullet symbols used (${uniq.join(', ')}); standardize to a single style.`));
  }

  const overlaps = analysis.totalOverlappingPairs;
  const clipped = analysis.totalClippedLines;
  const ovSc = overlaps === 0 && clipped === 0 ? 5 : overlaps + clipped === 1 ? 3 : overlaps + clipped <= 3 ? 2 : 1;
  factors.push(evaluated('Text Overlap', ovSc, [`Overlaps: ${overlaps}, Clipped: ${clipped}`], 'Checked line positions for overlapping or cut-off text.', ovSc === 5 ? null : `Detected ${overlaps} overlap(s) and ${clipped} cut-off line(s).`));

  const dists = pms.map((p) => p.textDistributionPct);
  const sparseTrail = dists.length >= 2 && Math.min(...dists) < 10;
  const neatSc = overlaps === 0 && clipped === 0 && !sparseTrail && famCount <= 3 ? 5 : sparseTrail ? 3 : overlaps + clipped === 0 ? 4 : 2;
  factors.push(evaluated('Overall Neatness', neatSc, pms.map((p) => `Page ${p.pageNumber}: ${p.textDistributionPct}% text`), 'Evaluated cross-page text balance and visual cleanliness.', neatSc <= 3 ? 'Improve page balance and resolve any layout collisions.' : null));

  const paperLabels = Array.from(new Set(analysis.pageDimensions.map((d) => d.paperSizeLabel)));
  const stdPaper = paperLabels.every((l) => l.includes('A4') || l.includes('Letter'));
  factors.push(evaluated('Page Layout and Readability', stdPaper && paperLabels.length === 1 ? 5 : stdPaper ? 4 : 3, paperLabels, 'Evaluated page size consistency and layout readability.', stdPaper && paperLabels.length === 1 ? null : 'Standardize all pages to uniform A4 or US Letter size.'));

  return factors;
}

function aggregateCategory(category: EvaluationCategory, factors: FactorEvaluation[]): CategoryEvaluation {
  const applicable = factors.filter((f) => f.status !== 'Not applicable');
  const assessed = applicable.filter((f) => f.status === 'Evaluated' && f.score !== null);
  const coveragePct = applicable.length > 0 ? Math.round((assessed.length / applicable.length) * 1000) / 10 : 0;

  if (assessed.length === 0) {
    return {
      category,
      categoryScore: 0,
      maxWeight: category.maxPoints,
      averageFactorScore: null,
      assessedFactorCount: 0,
      applicableFactorCount: applicable.length,
      coveragePct: 0,
      status: 'Unavailable',
      coverageNote: `Category unavailable: 0 of ${applicable.length} factors could be assessed.`,
      factors,
    };
  }

  const avg = Math.round((assessed.reduce((a, f) => a + (f.score || 0), 0) / assessed.length) * 100) / 100;
  const rawScore = (avg / 5) * category.maxPoints;
  const clamped = Math.round(Math.max(0, Math.min(category.maxPoints, rawScore)) * 100) / 100;

  return {
    category,
    categoryScore: clamped,
    maxWeight: category.maxPoints,
    averageFactorScore: avg,
    assessedFactorCount: assessed.length,
    applicableFactorCount: applicable.length,
    coveragePct,
    status: coveragePct < 50 ? 'Partial Coverage' : 'Evaluated',
    coverageNote: `Assessed ${assessed.length}/${applicable.length} factors (${coveragePct}% coverage).`,
    factors,
  };
}

export function evaluateCv(document: ProcessedPDFDocument, extractedCv: ExtractedCVData): CVEvaluationResult {
  const totalPossible = EVALUATION_CATEGORIES.reduce((a, c) => a + c.maxPoints, 0);
  const capMax = EVALUATION_CATEGORIES.filter((c) => c.group === 'candidate_capability').reduce((a, c) => a + c.maxPoints, 0);
  const presMax = EVALUATION_CATEGORIES.filter((c) => c.group === 'document_presentation').reduce((a, c) => a + c.maxPoints, 0);

  if (document.isScannedPdf || !document.hasExtractableText) {
    const unavailableCats: CategoryEvaluation[] = EVALUATION_CATEGORIES.map((category) => ({
      category,
      categoryScore: 0,
      maxWeight: category.maxPoints,
      averageFactorScore: null,
      assessedFactorCount: 0,
      applicableFactorCount: 1,
      coveragePct: 0,
      status: 'Unavailable',
      coverageNote: 'Unavailable: Scanned image PDF without selectable text.',
      factors: [cannotAssess(category.title, 'Selectable text is required to evaluate this category.')],
    }));

    return {
      filename: document.filename,
      isAssessable: false,
      overallScore: 0,
      totalPossibleScore: totalPossible,
      candidateCapabilityScore: 0,
      candidateCapabilityMax: capMax,
      documentPresentationScore: 0,
      documentPresentationMax: presMax,
      overallAssessedFactors: 0,
      overallApplicableFactors: EVALUATION_CATEGORIES.length,
      overallCoveragePct: 0,
      categories: unavailableCats,
    };
  }

  const factorMap: Record<EvaluationCategory['key'], FactorEvaluation[]> = {
    educational_qualifications: evaluateCategory1Education(extractedCv),
    professional_experience: evaluateCategory2Experience(extractedCv),
    technical_computer_skills: evaluateCategory3Technical(extractedCv, document),
    communication_language_skills: evaluateCategory4Communication(extractedCv, document),
    banking_finance_knowledge: evaluateCategory5Banking(extractedCv, document),
    achievements_extracurricular: evaluateCategory6Achievements(extractedCv, document),
    cv_structure_organization: evaluateCategory7Structure(document, extractedCv),
    language_writing_quality: evaluateCategory8Language(document),
    visual_presentation_formatting: evaluateCategory9Visual(document),
  };

  const categories = EVALUATION_CATEGORIES.map((cat) => aggregateCategory(cat, factorMap[cat.key]));
  const overallScore = Math.round(Math.min(totalPossible, categories.reduce((a, c) => a + c.categoryScore, 0)) * 100) / 100;
  const capScore = Math.round(categories.filter((c) => c.category.group === 'candidate_capability').reduce((a, c) => a + c.categoryScore, 0) * 100) / 100;
  const presScore = Math.round(categories.filter((c) => c.category.group === 'document_presentation').reduce((a, c) => a + c.categoryScore, 0) * 100) / 100;
  const totalAssessed = categories.reduce((a, c) => a + c.assessedFactorCount, 0);
  const totalApplicable = categories.reduce((a, c) => a + c.applicableFactorCount, 0);

  return {
    filename: document.filename,
    isAssessable: true,
    overallScore,
    totalPossibleScore: totalPossible,
    candidateCapabilityScore: capScore,
    candidateCapabilityMax: capMax,
    documentPresentationScore: presScore,
    documentPresentationMax: presMax,
    overallAssessedFactors: totalAssessed,
    overallApplicableFactors: totalApplicable,
    overallCoveragePct: totalApplicable > 0 ? Math.round((totalAssessed / totalApplicable) * 1000) / 10 : 0,
    categories,
  };
}
