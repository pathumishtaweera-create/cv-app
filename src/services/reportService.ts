import { jsPDF } from 'jspdf';
import {
  APP_NAME,
  SCORE_ABOVE_BENCHMARK_NOTE,
  SCORE_BENCHMARK_CLARIFICATION,
  SCORE_BENCHMARK_PERCENTAGE,
  SCORE_QUALITY_DISCLAIMER,
} from '../config/categories';
import type {
  CVEvaluationReport,
  CVEvaluationResult,
  ExtractedCVData,
  ImprovementAreaItem,
  LanguageFinding,
  ProcessedPDFDocument,
  SpecificCorrectionItem,
  StrengthItem,
} from '../types/cv';
import { analyzeLanguageQuality, WEAK_PASSIVE_PHRASES } from './languageChecker';

const FRIENDLY_TITLES: Record<string, string> = {
  'O/L Results': 'G.C.E. O/L exam results',
  'A/L Results': 'G.C.E. A/L exam results',
  'English Results': 'English exam grade',
  'Mathematics Results': 'Mathematics exam grade',
  'Degrees and Diplomas': 'Degree or diploma',
  'Banking and Finance Qualifications': 'Banking and finance qualifications',
  'Professional Qualifications': 'Professional finance or accounting qualifications',
  'Banking Experience': 'Banking work experience',
  'Finance Company Experience': 'Finance company experience',
  Internships: 'Internship experience',
  'Customer Service Experience': 'Customer service experience',
  'Cash Handling Experience': 'Cash handling experience',
  'Administrative Experience': 'Office and administrative experience',
  'Sales Experience': 'Sales experience',
  'Employment Duration': 'Length of work experience',
  'Relevance of Responsibilities': 'How relevant your work experience is',
  'Microsoft Excel': 'Microsoft Excel skills',
  'Microsoft Word': 'Microsoft Word skills',
  'Microsoft PowerPoint': 'Microsoft PowerPoint skills',
  'Computer Literacy': 'General computer skills',
  'Data Entry': 'Data entry skills',
  'Spreadsheet Skills': 'Spreadsheet skills',
  'Accounting Software': 'Accounting software skills',
  'Digital Banking Knowledge': 'Digital banking knowledge',
  'English Proficiency Evidence': 'English language skills',
  'Sinhala Proficiency Evidence': 'Sinhala language skills',
  'Tamil Proficiency Evidence': 'Tamil language skills',
  'Written Communication Evidence': 'Written communication',
  'Customer Communication Experience': 'Customer communication',
  'Presentation Experience': 'Presentation experience',
  'Interpersonal Communication Evidence': 'Teamwork and communication',
  'Banking Operations': 'Banking operations knowledge',
  'Financial Services': 'Financial services knowledge',
  'Accounting Knowledge': 'Accounting knowledge',
  'Loans and Credit': 'Loans and credit knowledge',
  'Deposit and Savings Products': 'Deposits and savings knowledge',
  'Financial Calculations': 'Financial calculations',
  'Customer Relationship Management': 'Customer relationship skills',
  'KYC and AML Awareness': 'KYC and AML knowledge',
  'Financial Compliance': 'Financial rules and compliance knowledge',
  'Academic Achievements': 'Academic achievements',
  'Professional Achievements': 'Work achievements',
  Awards: 'Awards and honors',
  Leadership: 'Leadership experience',
  Volunteering: 'Volunteer work',
  'Sports and Extracurricular Activities': 'Activities outside study',
  Projects: 'Projects and research',
  'Measurable Accomplishments': 'Results with numbers or figures',
  'Logical Section Arrangement': 'Clear order of CV sections',
  'Clear Section Headings': 'Clear section headings',
  'Contact Information Placement': 'Contact details at the top',
  'Education Organization': 'Well-organized education section',
  'Work Experience Organization': 'Well-organized work experience',
  'Chronological Consistency': 'Clear order of dates',
  'Information Completeness': 'Complete core CV sections',
  'Relevant Information': 'Focused, job-relevant details',
  'Appropriate CV Length': 'Good CV length',
  Spelling: 'Correct spelling',
  Grammar: 'Correct grammar',
  'Sentence Construction': 'Clear sentence structure',
  Punctuation: 'Clean punctuation',
  Capitalization: 'Proper capital letters',
  'Professional Vocabulary': 'Professional wording',
  'Sentence Clarity': 'How clearly you write',
  'Repeated Words': 'No repeated words',
  'Consistency of Writing Style': 'Consistent bullet-point style',
  'Font Consistency': 'Consistent font styles',
  'Font Readability': 'Easy-to-read text size',
  'Font Size Consistency': 'Consistent font sizes',
  'Paragraph Spacing': 'Even line spacing',
  'Section Spacing': 'Clear spacing between sections',
  'Text Alignment': 'Neat text alignment',
  'Margin Consistency': 'Balanced page margins',
  'Bullet-Point Formatting': 'Clean bullet points',
  'Text Overlap': 'No overlapping or cut-off text',
  'Overall Neatness': 'Clean overall appearance',
  'Page Layout and Readability': 'Clean page layout',
};

function friendlyName(raw: string): string {
  return FRIENDLY_TITLES[raw] || raw;
}

export function classifyCvScore(
  overallScore: number,
  isAssessable: boolean,
): { classification: string; band: CVEvaluationReport['classificationBand'] } {
  if (!isAssessable) return { classification: 'Not Assessable (Scanned PDF)', band: 'unavailable' };
  if (overallScore >= 90) return { classification: 'Outstanding CV', band: 'outstanding' };
  if (overallScore >= 80) return { classification: 'Very Good CV', band: 'very_good' };
  if (overallScore >= 70) return { classification: 'Good CV', band: 'good' };
  if (overallScore >= 60) return { classification: 'Average CV', band: 'average' };
  if (overallScore >= 50) return { classification: 'Below Average CV', band: 'below_average' };
  return { classification: 'Needs Significant Improvement', band: 'needs_improvement' };
}

function buildScoreInterpretationNote(
  overallScore: number,
  isAssessable: boolean,
): { title: string; note: string; clarification: string } {
  if (!isAssessable) {
    return {
      title: 'What Your Score Means',
      note:
        "Your CV could not be compared with this app's suggested 60% starting standard because readable text was not found in the PDF. Please save your CV as a regular text PDF and upload it again. Even with a strong CV score, an interview is never guaranteed because your qualifications, experience, the job requirements, and the employer's decision also matter.",
      clarification: SCORE_BENCHMARK_CLARIFICATION,
    };
  }
  if (overallScore >= SCORE_BENCHMARK_PERCENTAGE) {
    return {
      title: 'What Your Score Means (60% or Higher)',
      note: SCORE_ABOVE_BENCHMARK_NOTE,
      clarification: SCORE_BENCHMARK_CLARIFICATION,
    };
  }
  return {
    title: 'What Your Score Means (Below 60%)',
    note:
      "Your CV needs further improvement before it reaches this app's suggested 60% starting standard for applying for jobs. Follow the simple steps below to fix mistakes and strengthen your details. Reaching 60% or higher can help your CV meet a basic standard for consideration, though an interview is never guaranteed because your qualifications, experience, the job requirements, and the employer's decision also matter.",
    clarification: SCORE_BENCHMARK_CLARIFICATION,
  };
}

function buildOverallExplanation(ev: CVEvaluationResult): string {
  if (!ev.isAssessable) {
    return 'We could not read text from this PDF because it appears to be a scanned image. Please save your CV directly as a text PDF from Word or Google Docs and upload it again.';
  }
  const unavail = ev.categories.filter((c) => c.status === 'Unavailable').map((c) => c.category.title);
  const missingNote = unavail.length
    ? ` Some sections were not found in your CV (${unavail.slice(0, 3).join(', ')}), so those parts did not earn points.`
    : '';
  if (ev.overallScore >= 85) {
    return `Your CV is strong and well-prepared for entry-level banking and finance roles.${missingNote} Fixing the small points below can make it even stronger.`;
  }
  if (ev.overallScore >= 70) {
    return `Your CV has a good foundation for entry-level banking and finance jobs.${missingNote} Addressing the improvements below will help your CV stand out more clearly.`;
  }
  if (ev.overallScore >= 55) {
    return `Your CV covers some useful basics, but important details or fixes are still needed.${missingNote} Use the step-by-step suggestions below to make your CV clearer and stronger.`;
  }
  return `Your CV currently needs major updates before sending it to banks or finance employers.${missingNote} Start with the mistakes and missing details listed below.`;
}

function applyFindingsToLine(line: string, findings: LanguageFinding[]): string {
  let updated = line;
  for (const f of findings) {
    if (f.category === 'Spelling' || f.category === 'Grammar' || f.category === 'Repeated Words') {
      const escaped = f.incorrect.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      updated = updated.replace(new RegExp(`\\b${escaped}\\b`), f.correction);
    } else if (f.category === 'Punctuation') {
      updated = updated.replace(/\s+([,.;:])/g, '$1');
    } else if (f.category === 'Capitalization') {
      updated = updated.replace(/^([•●▪▫◦\-*]\s+)([a-z])/, (_, prefix, ch) => prefix + ch.toUpperCase());
    }
  }
  return updated;
}

export function buildEvaluationReport(
  doc: ProcessedPDFDocument,
  extractedCv: ExtractedCVData,
  evaluation: CVEvaluationResult,
): CVEvaluationReport {
  const { classification, band } = classifyCvScore(evaluation.overallScore, evaluation.isAssessable);
  const interp = buildScoreInterpretationNote(evaluation.overallScore, evaluation.isAssessable);
  const langReport = analyzeLanguageQuality(doc.textLines);

  const candidateName =
    extractedCv.personalAndContact.candidateName.status === 'extracted' &&
    extractedCv.personalAndContact.candidateName.value
      ? extractedCv.personalAndContact.candidateName.value
      : null;

  // Section 2: What You Did Well
  const whatsGood: StrengthItem[] = [];
  if (evaluation.isAssessable) {
    const candidates: Array<{ score: number; order: number; item: StrengthItem }> = [];
    for (const cat of evaluation.categories) {
      for (const f of cat.factors) {
        if (f.status === 'Evaluated' && (f.score || 0) >= 4 && !f.weakness) {
          const ev = f.evidence[0] || f.explanation;
          candidates.push({
            score: f.score || 4,
            order: cat.category.order,
            item: {
              title: friendlyName(f.factorName),
              evidence: ev.length > 140 ? `${ev.slice(0, 137)}...` : ev,
              whyItHelps: f.explanation,
              sourcePages: f.sourcePages,
            },
          });
        }
      }
    }
    candidates.sort((a, b) => b.score - a.score || a.order - b.order);
    const seen = new Set<string>();
    for (const c of candidates) {
      if (!seen.has(c.item.title)) {
        seen.add(c.item.title);
        whatsGood.push(c.item);
      }
      if (whatsGood.length >= 6) break;
    }
  }

  // Section 3 & 4: Mistakes to Fix + Areas You Can Improve
  const improvements: ImprovementAreaItem[] = [];
  const corrections: SpecificCorrectionItem[] = [];

  if (!evaluation.isAssessable) {
    corrections.push({
      categoryLabel: 'Readable PDF File',
      isError: true,
      originalCvExample: `Uploaded file: '${doc.filename}' (appears to be a scanned picture PDF with no readable text).`,
      identifiedProblem: 'The text inside your PDF could not be read automatically.',
      recommendedImprovement: 'Save or export your CV directly as a text PDF from Microsoft Word or Google Docs.',
      reason: 'Banks and CV-reading software need real selectable text to read your qualifications and contact details.',
      pageNumber: 1,
    });
  } else {
    // 1. Language Mistakes (Spelling, Grammar, Repeated Words, Punctuation, Capitalization)
    const allLangFindings = [
      ...langReport.spellingFindings,
      ...langReport.grammarFindings,
      ...langReport.repeatedWordFindings,
      ...langReport.punctuationFindings,
      ...langReport.capitalizationFindings,
    ];

    if (allLangFindings.length > 0) {
      const sample = allLangFindings.slice(0, 3).map((f) => `'${f.incorrect}' -> '${f.correction}'`).join('; ');
      improvements.push({
        heading: 'Spelling, grammar, and writing mistakes',
        explanation: 'There are spelling, grammar, or repeated-word mistakes in your CV text.',
        cv_example: allLangFindings[0].context,
        cvExample: allLangFindings[0].context,
        nextStep: `Fix these mistakes before sending your CV: ${sample}.`,
        isError: true,
        pageNumbers: Array.from(new Set(allLangFindings.map((f) => f.pageNumber))),
      } as ImprovementAreaItem);

      const groupedByLine = new Map<string, LanguageFinding[]>();
      for (const f of allLangFindings) {
        const list = groupedByLine.get(f.context) || [];
        list.push(f);
        groupedByLine.set(f.context, list);
      }

      for (const [origLine, findings] of Array.from(groupedByLine.entries()).slice(0, 4)) {
        const fixedLine = applyFindingsToLine(origLine, findings);
        const fixNotes = findings.map((f) => `'${f.incorrect}' should be '${f.correction}'`).join('; ');
        corrections.push({
          categoryLabel: 'Language & Spelling',
          isError: true,
          originalCvExample: origLine,
          identifiedProblem: `Found ${findings.length} writing mistake(s): ${fixNotes}.`,
          recommendedImprovement: fixedLine,
          reason: 'Clean spelling and grammar create a strong first impression and show attention to detail for banking roles.',
          pageNumber: findings[0].pageNumber,
        });
      }
    }

    // 2. Contact mistakes
    const p = extractedCv.personalAndContact;
    const missingContact: string[] = [];
    if (p.emailAddress.status === 'not_found') missingContact.push('email address');
    if (p.telephoneNumber.status === 'not_found') missingContact.push('phone number');
    if (p.location.status === 'not_found') missingContact.push('city/location');

    if (missingContact.length > 0) {
      improvements.push({
        heading: 'Missing contact details at the top',
        explanation: `Your CV header is missing your ${missingContact.join(', ')}.`,
        cvExample: p.candidateName.value ? `Top of CV: ${p.candidateName.value}` : 'Top contact section',
        nextStep: `Add your ${missingContact.join(', ')} clearly near your name on Page 1.`,
        isError: true,
        pageNumbers: [1],
      });
      corrections.push({
        categoryLabel: 'Contact Details',
        isError: true,
        originalCvExample: `${p.candidateName.value || 'Candidate Name'} | ${p.emailAddress.value || 'No email shown'}`,
        identifiedProblem: `Missing ${missingContact.join(', ')} in the header.`,
        recommendedImprovement: `${p.candidateName.value || 'Your Full Name'} | ${p.location.value || 'City, Country'} | ${p.emailAddress.value || 'your.name@email.com'} | ${p.telephoneNumber.value || '+94 7X XXX XXXX'}`,
        reason: 'Recruiters need complete contact details right at the top so they can easily invite you for an interview.',
        pageNumber: 1,
      });
    }

    // 3. Layout / Formatting mistakes (overlaps / clipping)
    const ov = doc.documentAnalysis.totalOverlappingPairs;
    const cl = doc.documentAnalysis.totalClippedLines;
    if (ov > 0 || cl > 0) {
      const clippedLine = doc.textLines.find((l) => l.bbox[2] > (doc.documentAnalysis.pageDimensions[l.pageNumber - 1]?.widthPt || 595) + 2);
      const exampleTxt = clippedLine ? clippedLine.text : 'Some lines overlap or extend close to the edge of the page.';
      improvements.push({
        heading: 'Improve your CV formatting',
        explanation: 'Some text in your PDF is overlapping or extends past the page edge, making it harder to read.',
        cvExample: exampleTxt,
        nextStep: 'Widen your page margins slightly and check the spacing between headings and lines in Word or Google Docs.',
        isError: true,
        pageNumbers: [1],
      });
      corrections.push({
        categoryLabel: 'Page Layout & Formatting',
        isError: true,
        originalCvExample: exampleTxt,
        identifiedProblem: `${ov > 0 ? `${ov} overlapping text area(s)` : ''}${ov > 0 && cl > 0 ? ' and ' : ''}${cl > 0 ? `${cl} line(s) cut off at the page margin` : ''}.`,
        recommendedImprovement: 'Keep comfortable margins (at least 0.5 inches / 13 mm on all sides) and give each heading its own separate line.',
        reason: 'Clean, uncrowded pages ensure recruiters and CV-reading software can read every detail clearly.',
        pageNumber: clippedLine?.pageNumber || 1,
      });
    }

    // 4. Areas You Can Improve (Non-error suggestions)
    const expEntries = extractedCv.professionalExperience.experienceEntries.value || [];
    for (const entry of expEntries) {
      if (entry.responsibilities.length === 0) {
        const titleStr = `${entry.jobTitle || 'Role'} - ${entry.companyName || 'Company'}${entry.employmentDates ? ` | ${entry.employmentDates}` : ''}`;
        improvements.push({
          heading: 'Add duties under your work experience',
          explanation: 'Listing a job title alone does not show recruiters what tasks or skills you practiced.',
          cvExample: titleStr,
          nextStep: 'Add 2-4 short bullet points explaining what you handled, prepared, or reconciled.',
          isError: false,
          pageNumbers: entry.sourcePages,
        });
        corrections.push({
          categoryLabel: 'Work Experience Details',
          isError: false,
          originalCvExample: titleStr,
          identifiedProblem: 'No bullet points describing your daily duties were found under this role.',
          recommendedImprovement: `${titleStr}\n• Assisted customers politely with daily inquiries and accurate record keeping.\n• Prepared daily summaries and reconciled figures using Microsoft Excel.`,
          reason: 'Clear duties help employers quickly see how relevant your work experience is to banking.',
          pageNumber: entry.sourcePages[0] || 1,
        });
        break;
      }
    }

    // Weak passive phrases
    const passiveLine = doc.textLines.find((l) =>
      WEAK_PASSIVE_PHRASES.some((p) => new RegExp(`\\b${p}\\b`, 'i').test(l.text)),
    );
    if (passiveLine) {
      improvements.push({
        heading: 'Use stronger action words in your duties',
        explanation: 'Starting bullets with phrases like "Responsible for" or "Helped with" sounds less direct.',
        cvExample: passiveLine.text,
        nextStep: 'Start your bullet points with clear action words like "Prepared", "Reconciled", "Assisted", or "Handled".',
        isError: false,
        pageNumbers: [passiveLine.pageNumber],
      });
      corrections.push({
        categoryLabel: 'Stronger Wording',
        isError: false,
        originalCvExample: passiveLine.text,
        identifiedProblem: 'Uses passive wording instead of a direct action verb.',
        recommendedImprovement: passiveLine.text
          .replace(/\bresponsible for\b/gi, 'Managed')
          .replace(/\bhelped with\b/gi, 'Assisted with')
          .replace(/\bworked on\b/gi, 'Completed'),
        reason: 'Strong action words highlight what you personally accomplished.',
        pageNumber: passiveLine.pageNumber,
      });
    }

    // Missing Excel detail or Excel missing
    const excelField = extractedCv.technicalSkills.microsoftExcel;
    if (excelField.status === 'not_found') {
      improvements.push({
        heading: 'Add Microsoft Excel if you know how to use it',
        explanation: 'Microsoft Excel is not mentioned in your CV yet, and most entry-level banking jobs use spreadsheets daily.',
        cvExample: 'Skills section',
        nextStep: 'If you have used Microsoft Excel, list it along with any features you know (such as tables, formulas, or charts).',
        isError: false,
        pageNumbers: [1],
      });
    } else if (!/\b(?:pivot|vlookup|xlookup|formula|vba|macro|intermediate|advanced)\b/i.test((excelField.value?.evidenceLines || []).join(' '))) {
      const exLine = excelField.value?.evidenceLines[0] || 'Excel';
      improvements.push({
        heading: 'Explain your Microsoft Excel skills clearly',
        explanation: 'You mentioned Excel, but stating which tasks or tools you know makes it much stronger.',
        cvExample: exLine,
        nextStep: 'Mention specific Excel tasks you genuinely know, such as formulas, Pivot Tables, VLOOKUP, or financial schedules.',
        isError: false,
        pageNumbers: excelField.sourcePages,
      });
      corrections.push({
        categoryLabel: 'Technical Skills',
        isError: false,
        originalCvExample: exLine,
        identifiedProblem: 'Lists Excel without showing what level or tools you can use.',
        recommendedImprovement: `${exLine} (formulas, Pivot Tables, VLOOKUP, and daily reporting)`,
        reason: 'Recruiters look for specific spreadsheet familiarity for banking operations and finance trainee roles.',
        pageNumber: excelField.sourcePages[0] || 1,
      });
    }

    // Standalone banking/finance claim without context
    const bfCat = evaluation.categories.find((c) => c.category.key === 'banking_finance_knowledge');
    const claimFactor = bfCat?.factors.find((f) => f.status === 'Evaluated' && (f.score || 5) <= 2);
    if (claimFactor && claimFactor.evidence.length) {
      improvements.push({
        heading: `Explain your ${friendlyName(claimFactor.factorName)}`,
        explanation: 'You listed a banking or finance keyword on its own without explaining where you learned or practiced it.',
        cvExample: claimFactor.evidence[0],
        nextStep: 'Add a short note showing whether you practiced it at work, in an internship, or in a course.',
        isError: false,
        pageNumbers: claimFactor.sourcePages,
      });
    }

    // Missing standard sections
    if (extractedCv.missingSections.length > 0) {
      improvements.push({
        heading: 'Add missing information or standard sections',
        explanation: `Your CV is missing standard section headings (${extractedCv.missingSections.join(', ')}), if those apply to you.`,
        cvExample: `Sections found: ${extractedCv.detectedSections.join(', ') || 'None'}`,
        nextStep: 'Add clear headings for any genuine experience, skills, languages, or achievements you have.',
        isError: false,
        pageNumbers: [1],
      });
    }
  }

  // Always show Mistakes to Fix first
  improvements.sort((a, b) => Number(b.isError) - Number(a.isError));
  corrections.sort((a, b) => Number(b.isError) - Number(a.isError));

  return {
    applicationName: APP_NAME,
    candidateName,
    filename: doc.filename,
    generatedAt: new Date().toLocaleString(),
    overallScore: evaluation.overallScore,
    totalPossibleScore: evaluation.totalPossibleScore,
    classification,
    classificationBand: band,
    overallExplanation: buildOverallExplanation(evaluation),
    scoreInterpretationTitle: interp.title,
    scoreInterpretationNote: interp.note,
    scoreBenchmarkClarification: interp.clarification,
    disclaimer: SCORE_QUALITY_DISCLAIMER,
    evaluation,
    whatsGood,
    whatNeedsImprovement: improvements,
    specificCorrections: corrections,
    assessmentLimitations: [
      SCORE_QUALITY_DISCLAIMER,
      'This feedback is based only on the readable text inside your PDF file.',
      'If your CV is a scanned image, please re-save it as a regular text PDF from Word or Google Docs.',
      'Spoken English and interview communication cannot be checked from a written CV.',
    ],
  };
}

export function generatePdfReportBlob(report: CVEvaluationReport): Blob {
  const pdf = new jsPDF({ unit: 'pt', format: 'a4' });
  const pageW = pdf.internal.pageSize.getWidth();
  const pageH = pdf.internal.pageSize.getHeight();
  const margin = 42;
  const maxW = pageW - margin * 2;
  let y = 46;

  const ensureSpace = (needed: number) => {
    if (y + needed > pageH - 42) {
      pdf.addPage();
      y = 46;
    }
  };

  const writeWrapped = (text: string, size: number, bold = false, color: [number, number, number] = [15, 23, 42]) => {
    pdf.setFont('helvetica', bold ? 'bold' : 'normal');
    pdf.setFontSize(size);
    pdf.setTextColor(color[0], color[1], color[2]);
    const wrapped = pdf.splitTextToSize(text, maxW) as string[];
    const lineH = size * 1.38;
    for (const ln of wrapped) {
      ensureSpace(lineH);
      pdf.text(ln, margin, y);
      y += lineH;
    }
  };

  writeWrapped(`${report.applicationName} - CV Feedback Report`, 15, true, [15, 41, 66]);
  y += 2;
  writeWrapped(
    `Candidate: ${report.candidateName || 'Not specified in CV'} | File: ${report.filename} | Generated: ${report.generatedAt}`,
    9,
    false,
    [71, 85, 105],
  );
  y += 10;

  writeWrapped('1. Your CV Score', 12, true, [15, 41, 66]);
  y += 2;
  writeWrapped(`CV SCORE: ${Math.round(report.overallScore)} / ${report.totalPossibleScore} - ${report.classification}`, 11, true);
  writeWrapped(report.overallExplanation, 9.5);
  writeWrapped(report.disclaimer, 8.5, false, [71, 85, 105]);
  y += 4;
  writeWrapped(report.scoreInterpretationTitle, 10, true, [15, 41, 66]);
  writeWrapped(report.scoreInterpretationNote, 9.5);
  writeWrapped(report.scoreBenchmarkClarification, 8.5, false, [71, 85, 105]);
  y += 8;

  writeWrapped('Category Score Breakdown (9 Areas)', 10.5, true, [15, 41, 66]);
  for (const cat of report.evaluation.categories) {
    const pct = cat.maxWeight ? Math.round((cat.categoryScore / cat.maxWeight) * 100) : 0;
    writeWrapped(`${cat.category.order}. ${cat.category.title}: ${cat.categoryScore.toFixed(1)} / ${cat.maxWeight} (${pct}%)`, 9);
  }
  y += 8;

  writeWrapped('2. What You Did Well', 12, true, [15, 41, 66]);
  if (report.whatsGood.length === 0) {
    writeWrapped('No strong examples were found in the readable text of this CV.', 9.5);
  } else {
    for (const s of report.whatsGood) {
      writeWrapped(`• ${s.title}`, 9.5, true);
      writeWrapped(`  In your CV: ${s.evidence}`, 9);
      writeWrapped(`  Why this helps: ${s.whyItHelps}`, 8.5, false, [71, 85, 105]);
    }
  }
  y += 8;

  writeWrapped('3. What Needs Improvement', 12, true, [15, 41, 66]);
  const mistakes = report.whatNeedsImprovement.filter((w) => w.isError);
  const optional = report.whatNeedsImprovement.filter((w) => !w.isError);
  writeWrapped('A. Mistakes to Fix', 10, true);
  if (!mistakes.length) writeWrapped('No spelling, grammar, contact, or text overlap mistakes were found.', 9);
  for (const w of mistakes) {
    writeWrapped(`• ${w.heading}: ${w.explanation}`, 9, true);
    writeWrapped(`  Example: ${w.cvExample} | Next step: ${w.nextStep}`, 8.5, false, [71, 85, 105]);
  }
  writeWrapped('B. Areas You Can Improve', 10, true);
  if (!optional.length) writeWrapped('No extra improvement areas were flagged.', 9);
  for (const w of optional) {
    writeWrapped(`• ${w.heading}: ${w.explanation}`, 9, true);
    writeWrapped(`  In your CV: ${w.cvExample} | Next step: ${w.nextStep}`, 8.5, false, [71, 85, 105]);
  }
  y += 8;

  writeWrapped('4. How to Improve Your CV', 12, true, [15, 41, 66]);
  if (!report.specificCorrections.length) {
    writeWrapped('No specific corrections were needed for your CV.', 9.5);
  } else {
    report.specificCorrections.forEach((c, idx) => {
      writeWrapped(`${idx + 1}. ${c.categoryLabel} (${c.isError ? 'Mistake to Fix' : 'Area You Can Improve'})`, 9.5, true);
      writeWrapped(`  STEP 1 - What is wrong? ${c.originalCvExample} (${c.identifiedProblem})`, 9);
      writeWrapped(`  STEP 2 - How to fix it? ${c.recommendedImprovement}`, 9);
      writeWrapped(`  STEP 3 - Why does this matter? ${c.reason}`, 8.5, false, [71, 85, 105]);
      y += 3;
    });
  }

  return pdf.output('blob');
}
