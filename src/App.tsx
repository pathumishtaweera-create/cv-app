import React, { useRef, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Download,
  FileText,
  RotateCcw,
  Upload,
} from 'lucide-react';
import {
  APP_NAME,
  APP_SUBTITLE,
  DEFAULT_PREVIEW_CHAR_LIMIT,
  MAX_FILE_SIZE_MB,
} from './config/categories';
import { extractCvInformation } from './services/cvExtractor';
import { evaluateCv } from './services/evaluator';
import { PDFProcessingError, processUploadedPdf } from './services/pdfProcessor';
import { buildEvaluationReport, generatePdfReportBlob } from './services/reportService';
import type { CVEvaluationReport, ProcessedPDFDocument } from './types/cv';

function friendlyCategoryStatus(status: string): string {
  if (status === 'Evaluated') return 'Checked';
  if (status === 'Partial Coverage') return 'Some details missing';
  if (status === 'Unavailable') return 'Not found in CV';
  return status;
}

function classificationColor(band: CVEvaluationReport['classificationBand']): string {
  if (band === 'outstanding' || band === 'very_good') return 'text-green-800';
  if (band === 'good') return 'text-blue-700';
  if (band === 'average') return 'text-amber-700';
  return 'text-red-700';
}

export default function App() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isProcessingPdf, setIsProcessingPdf] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [document, setDocument] = useState<ProcessedPDFDocument | null>(null);
  const [report, setReport] = useState<CVEvaluationReport | null>(null);

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewTab, setPreviewTab] = useState<'text' | 'page'>('text');
  const [selectedPreviewPage, setSelectedPreviewPage] = useState(1);
  const [breakdownOpen, setBreakdownOpen] = useState(false);

  const handleFileSelected = async (file: File | null | undefined) => {
    if (!file) return;
    setUploadError(null);
    setReport(null);
    setDocument(null);
    setPreviewOpen(false);
    setSelectedPreviewPage(1);
    setIsProcessingPdf(true);

    try {
      const processed = await processUploadedPdf(file);
      setDocument(processed);
    } catch (err) {
      if (err instanceof PDFProcessingError) {
        setUploadError(err.message);
      } else {
        setUploadError(
          'An unexpected error occurred while reading the PDF file. Please verify the file and try again.',
        );
      }
    } finally {
      setIsProcessingPdf(false);
    }
  };

  const handleReset = () => {
    setDocument(null);
    setReport(null);
    setUploadError(null);
    setPreviewOpen(false);
    setBreakdownOpen(false);
    setSelectedPreviewPage(1);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleAnalyze = () => {
    if (!document) return;
    setIsAnalyzing(true);
    try {
      const extracted = extractCvInformation(document);
      const evaluation = evaluateCv(document, extracted);
      const builtReport = buildEvaluationReport(document, extracted, evaluation);
      setReport(builtReport);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleDownloadPdf = () => {
    if (!report) return;
    const blob = generatePdfReportBlob(report);
    const url = URL.createObjectURL(blob);
    const stem =
      report.filename
        .replace(/\.[^.]+$/, '')
        .replace(/[^A-Za-z0-9_-]+/g, '_')
        .replace(/^_+|_+$/g, '') || 'cv';
    const anchor = window.document.createElement('a');
    anchor.href = url;
    anchor.download = `${stem}_cv_feedback_report.pdf`;
    window.document.body.appendChild(anchor);
    anchor.click();
    window.document.body.removeChild(anchor);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const mistakes = report ? report.whatNeedsImprovement.filter((w) => w.isError) : [];
  const optionalAreas = report ? report.whatNeedsImprovement.filter((w) => !w.isError) : [];

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A] antialiased">
      <main className="mx-auto max-w-[960px] px-4 py-7 sm:px-6">
        {/* Header */}
        <header className="mb-5 rounded-lg border border-slate-200 bg-white px-6 py-5">
          <h1 className="text-[1.6rem] font-bold leading-tight text-[#0F2942]">{APP_NAME}</h1>
          <p className="mt-1.5 text-[0.94rem] leading-relaxed text-slate-600">{APP_SUBTITLE}</p>
        </header>

        {/* Upload Section */}
        <section className="mb-4">
          <h2 className="mb-2 border-b border-slate-200 pb-1.5 text-[1.15rem] font-bold text-[#0F2942]">
            Upload Your CV
          </h2>
          <p className="mb-3 text-[0.86rem] text-slate-600">
            Upload your CV as a PDF file (up to {MAX_FILE_SIZE_MB} MB). Everything runs privately inside your browser — no external AI APIs or uploads to third-party servers.
          </p>

          <div
            role="button"
            tabIndex={0}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setIsDragging(false);
              const file = e.dataTransfer.files?.[0];
              void handleFileSelected(file);
            }}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-7 text-center transition-colors ${
              isDragging
                ? 'border-[#0F2942] bg-slate-100'
                : 'border-slate-300 bg-white hover:border-slate-400 hover:bg-slate-50'
            }`}
          >
            <Upload className="mb-2 h-7 w-7 text-[#0F2942]" />
            <div className="text-sm font-semibold text-[#0F2942]">
              {isProcessingPdf ? 'Reading PDF file...' : 'Drag and drop your PDF CV here, or click to browse'}
            </div>
            <div className="mt-1 text-xs text-slate-500">
              Accepted format: .pdf only (max {MAX_FILE_SIZE_MB} MB)
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                void handleFileSelected(file);
              }}
            />
          </div>

          {uploadError && (
            <div className="mt-3 flex items-start gap-2.5 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{uploadError}</span>
            </div>
          )}
        </section>

        {/* Uploaded Document Summary & Preview */}
        {document && (
          <section className="mb-4">
            <div className="mb-3 flex items-center gap-2 rounded-md border border-green-200 bg-green-50 px-4 py-2.5 text-sm font-medium text-green-800">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>PDF ready: {document.filename}</span>
            </div>

            <div className="grid grid-cols-2 gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3.5 sm:grid-cols-4">
              <div>
                <div className="text-xs text-slate-500">File Name</div>
                <div className="break-words text-sm font-semibold text-slate-900">{document.filename}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500">File Size</div>
                <div className="text-sm font-semibold text-slate-900">{document.fileSizeDisplay}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500">Pages</div>
                <div className="text-sm font-semibold text-slate-900">{document.pageCount}</div>
              </div>
              <div>
                <div className="text-xs text-slate-500">Words Read</div>
                <div className="text-sm font-semibold text-slate-900">{document.wordCount.toLocaleString()}</div>
              </div>
            </div>

            {document.isScannedPdf && (
              <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                This PDF looks like a scanned picture, so words cannot be read automatically. Please save your CV as a normal text PDF from Word or Google Docs and try again.
              </div>
            )}

            <div className="mt-3 rounded-lg border border-slate-200 bg-white">
              <button
                type="button"
                onClick={() => setPreviewOpen((v) => !v)}
                className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm font-semibold text-[#0F2942] hover:bg-slate-50"
              >
                <span className="flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  Preview Your Uploaded CV
                </span>
                {previewOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </button>

              {previewOpen && (
                <div className="border-t border-slate-200 px-4 py-3">
                  <div className="mb-3 flex gap-2 border-b border-slate-200 pb-2">
                    <button
                      type="button"
                      onClick={() => setPreviewTab('text')}
                      className={`rounded px-3 py-1 text-xs font-semibold ${
                        previewTab === 'text'
                          ? 'bg-[#0F2942] text-white'
                          : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                      }`}
                    >
                      Readable Text
                    </button>
                    <button
                      type="button"
                      onClick={() => setPreviewTab('page')}
                      className={`rounded px-3 py-1 text-xs font-semibold ${
                        previewTab === 'page'
                          ? 'bg-[#0F2942] text-white'
                          : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                      }`}
                    >
                      Page View
                    </button>
                  </div>

                  {previewTab === 'text' ? (
                    document.hasExtractableText ? (
                      <textarea
                        readOnly
                        rows={10}
                        value={
                          document.extractedText.length > DEFAULT_PREVIEW_CHAR_LIMIT
                            ? `${document.extractedText.slice(0, DEFAULT_PREVIEW_CHAR_LIMIT)}\n\n[Preview shortened — your full CV is loaded for checking.]`
                            : document.extractedText
                        }
                        className="w-full rounded border border-slate-200 bg-slate-50 p-3 font-mono text-xs text-slate-800 focus:outline-none"
                      />
                    ) : (
                      <p className="text-sm text-slate-600">No readable text was found in this PDF.</p>
                    )
                  ) : document.pagePreviewUrls.length > 0 ? (
                    <div>
                      {document.pagePreviewUrls.length > 1 && (
                        <div className="mb-2 flex items-center gap-2">
                          <label htmlFor="preview-page-select" className="text-xs font-medium text-slate-600">
                            Page:
                          </label>
                          <select
                            id="preview-page-select"
                            value={selectedPreviewPage}
                            onChange={(e) => setSelectedPreviewPage(Number(e.target.value))}
                            className="rounded border border-slate-300 bg-white px-2 py-1 text-xs"
                          >
                            {document.pagePreviewUrls.map((_, i) => (
                              <option key={i + 1} value={i + 1}>
                                Page {i + 1} of {document.pageCount}
                              </option>
                            ))}
                          </select>
                        </div>
                      )}
                      <img
                        src={document.pagePreviewUrls[selectedPreviewPage - 1]}
                        alt={`Page ${selectedPreviewPage} preview`}
                        className="mx-auto max-h-[540px] rounded border border-slate-200 object-contain"
                      />
                    </div>
                  ) : (
                    <p className="text-sm text-slate-600">Page preview is unavailable for this document.</p>
                  )}
                </div>
              )}
            </div>
          </section>
        )}

        {/* Action Buttons */}
        <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <button
            type="button"
            disabled={!document || isProcessingPdf || isAnalyzing}
            onClick={handleAnalyze}
            className="sm:col-span-2 rounded-md bg-[#0F2942] px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#173B5E] disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {isAnalyzing ? 'Analyzing CV...' : 'Analyze CV'}
          </button>
          <button
            type="button"
            disabled={!document && !report && !uploadError}
            onClick={handleReset}
            className="flex items-center justify-center gap-2 rounded-md border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RotateCcw className="h-4 w-4" />
            Upload Another CV
          </button>
        </div>

        {/* 4-Section Evaluation Dashboard */}
        {report && (
          <div className="space-y-6">
            {/* 1. YOUR CV SCORE */}
            <section>
              <h2 className="mb-3 border-b border-slate-200 pb-1.5 text-[1.15rem] font-bold text-[#0F2942]">
                1. Your CV Score
              </h2>

              <div className="rounded-lg border border-slate-300 bg-white px-5 py-5">
                <div className="mb-1 text-xs text-slate-500">
                  Candidate: <strong>{report.candidateName || 'Not shown in CV'}</strong> &middot; File:{' '}
                  {report.filename}
                </div>
                <div className="text-[1.55rem] font-bold text-[#0F2942]">
                  CV SCORE: {Math.round(report.overallScore)}/{report.totalPossibleScore}
                </div>
                <div className={`mb-2 text-[1.05rem] font-semibold ${classificationColor(report.classificationBand)}`}>
                  {report.classification}
                </div>
                <p className="mb-1.5 text-[0.9rem] leading-relaxed text-slate-800">{report.overallExplanation}</p>
                <p className="text-xs text-slate-500">{report.disclaimer}</p>
              </div>

              {/* Visual Progress Indicator */}
              <div className="mt-2.5 h-2.5 w-full overflow-hidden rounded-full bg-slate-200">
                <div
                  className="h-full rounded-full bg-[#0F2942] transition-all"
                  style={{ width: `${Math.max(0, Math.min(100, report.overallScore))}%` }}
                />
              </div>

              {/* CV Score Interpretation Note (60%+ Suggested Benchmark) */}
              <div
                className={`mt-3 rounded-lg border border-l-4 px-4 py-3.5 ${
                  !report.evaluation.isAssessable
                    ? 'border-slate-300 border-l-slate-500 bg-slate-50'
                    : report.overallScore >= 60
                      ? 'border-green-200 border-l-green-600 bg-green-50'
                      : 'border-amber-200 border-l-amber-600 bg-amber-50'
                }`}
              >
                <div className="mb-1 text-sm font-bold text-[#0F2942]">{report.scoreInterpretationTitle}</div>
                <p className="mb-1.5 text-[0.9rem] leading-relaxed text-slate-900">{report.scoreInterpretationNote}</p>
                <p className="text-xs leading-relaxed text-slate-600">{report.scoreBenchmarkClarification}</p>
              </div>

              {/* Collapsible 9-Category Breakdown */}
              <div className="mt-3 rounded-lg border border-slate-200 bg-white">
                <button
                  type="button"
                  onClick={() => setBreakdownOpen((v) => !v)}
                  className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm font-semibold text-[#0F2942] hover:bg-slate-50"
                >
                  <span>See score breakdown by category (9 areas)</span>
                  {breakdownOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </button>
                {breakdownOpen && (
                  <div className="overflow-x-auto border-t border-slate-200">
                    <table className="w-full border-collapse text-left text-sm">
                      <thead className="bg-slate-50 text-xs uppercase text-slate-600">
                        <tr>
                          <th className="px-4 py-2.5">Category</th>
                          <th className="px-4 py-2.5 text-right">Score</th>
                          <th className="px-4 py-2.5 text-right">%</th>
                          <th className="px-4 py-2.5">Details Found</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200">
                        {report.evaluation.categories.map((cat) => {
                          const pct = cat.maxWeight ? Math.round((cat.categoryScore / cat.maxWeight) * 100) : 0;
                          return (
                            <tr key={cat.category.key}>
                              <td className="px-4 py-2 font-medium text-slate-900">
                                {cat.category.order}. {cat.category.title}
                              </td>
                              <td className="whitespace-nowrap px-4 py-2 text-right">
                                {cat.categoryScore.toFixed(1)} / {cat.maxWeight}
                              </td>
                              <td className="whitespace-nowrap px-4 py-2 text-right">{pct}%</td>
                              <td className="px-4 py-2 text-slate-600">{friendlyCategoryStatus(cat.status)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Download PDF & Check Another CV */}
              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
                <button
                  type="button"
                  onClick={handleDownloadPdf}
                  className="sm:col-span-2 flex items-center justify-center gap-2 rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-[#0F2942] hover:bg-slate-50"
                >
                  <Download className="h-4 w-4" />
                  Download PDF Feedback Report
                </button>
                <button
                  type="button"
                  onClick={handleReset}
                  className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Check Another CV
                </button>
              </div>
            </section>

            {/* 2. WHAT YOU DID WELL */}
            <section>
              <h2 className="mb-3 border-b border-slate-200 pb-1.5 text-[1.15rem] font-bold text-[#0F2942]">
                2. What You Did Well
              </h2>
              {report.whatsGood.length > 0 ? (
                <div className="space-y-2.5">
                  {report.whatsGood.map((item, idx) => (
                    <div
                      key={`${item.title}-${idx}`}
                      className="rounded-md border border-green-200 border-l-4 border-l-green-600 bg-green-50 px-4 py-3"
                    >
                      <div className="mb-1 text-sm font-semibold text-slate-900">
                        <span className="text-xs font-bold text-green-800">[Good]</span> {item.title}
                      </div>
                      <div className="text-sm text-slate-800">
                        <strong>In your CV:</strong> {item.evidence}
                      </div>
                      <div className="mt-0.5 text-sm text-slate-700">
                        <strong>Why this helps:</strong> {item.whyItHelps}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                  No strong examples were found in the readable text of this CV.
                </div>
              )}
            </section>

            {/* 3. WHAT NEEDS IMPROVEMENT */}
            <section>
              <h2 className="mb-3 border-b border-slate-200 pb-1.5 text-[1.15rem] font-bold text-[#0F2942]">
                3. What Needs Improvement
              </h2>

              {report.whatNeedsImprovement.length === 0 ? (
                <div className="rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
                  {report.evaluation.isAssessable
                    ? 'Your CV looks solid with no major mistakes or missing basics.'
                    : 'We could not check this CV because no readable text was found inside the PDF.'}
                </div>
              ) : (
                <div className="space-y-4">
                  {mistakes.length > 0 && (
                    <div className="space-y-2.5">
                      <h3 className="text-sm font-bold text-slate-900">A. Mistakes to Fix</h3>
                      {mistakes.map((item, idx) => (
                        <div
                          key={`err-${idx}`}
                          className="rounded-md border border-red-200 border-l-4 border-l-red-600 bg-red-50 px-4 py-3"
                        >
                          <div className="mb-1 text-sm font-semibold text-slate-900">
                            <span className="text-xs font-bold text-red-700">[Mistake to Fix]</span> {item.heading}
                          </div>
                          <div className="text-sm text-slate-800">{item.explanation}</div>
                          <div className="mt-1 text-sm text-slate-800">
                            <strong>Example in your CV:</strong> {item.cvExample}
                          </div>
                          <div className="mt-0.5 text-sm text-slate-800">
                            <strong>What to do next:</strong> {item.nextStep}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {optionalAreas.length > 0 && (
                    <div className="space-y-2.5">
                      <h3 className="text-sm font-bold text-slate-900">B. Areas You Can Improve</h3>
                      {optionalAreas.map((item, idx) => (
                        <div
                          key={`imp-${idx}`}
                          className="rounded-md border border-amber-200 border-l-4 border-l-amber-600 bg-amber-50 px-4 py-3"
                        >
                          <div className="mb-1 text-sm font-semibold text-slate-900">
                            <span className="text-xs font-bold text-amber-800">[Area to Improve]</span> {item.heading}
                          </div>
                          <div className="text-sm text-slate-800">{item.explanation}</div>
                          <div className="mt-1 text-sm text-slate-800">
                            <strong>In your CV:</strong> {item.cvExample}
                          </div>
                          <div className="mt-0.5 text-sm text-slate-800">
                            <strong>What to do next:</strong> {item.nextStep}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </section>

            {/* 4. HOW TO IMPROVE YOUR CV (3-STEP PATTERN) */}
            <section>
              <h2 className="mb-1 border-b border-slate-200 pb-1.5 text-[1.15rem] font-bold text-[#0F2942]">
                4. How to Improve Your CV
              </h2>
              <p className="mb-3 text-xs text-slate-500">
                Mistakes to fix are shown first, followed by areas you can improve. Only add extra details if they are true for you.
              </p>

              {report.specificCorrections.length > 0 ? (
                <div className="space-y-3">
                  {report.specificCorrections.map((corr, idx) => (
                    <div
                      key={`corr-${idx}`}
                      className={`rounded-md border border-l-4 px-4 py-3.5 ${
                        corr.isError
                          ? 'border-red-200 border-l-red-600 bg-red-50'
                          : 'border-amber-200 border-l-amber-600 bg-amber-50'
                      }`}
                    >
                      <div className="mb-2 text-sm font-semibold text-slate-900">
                        {idx + 1}. {corr.categoryLabel} &mdash;{' '}
                        <span className={corr.isError ? 'text-xs font-bold text-red-700' : 'text-xs font-bold text-amber-800'}>
                          {corr.isError ? 'Mistake to Fix' : 'Area You Can Improve'}
                        </span>
                      </div>

                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <div className="rounded border border-slate-200 bg-white p-3">
                          <div className="mb-1 text-[0.72rem] font-bold uppercase tracking-wide text-slate-600">
                            STEP 1 &ndash; What is wrong?
                          </div>
                          <div className="whitespace-pre-line text-sm text-slate-900">{corr.originalCvExample}</div>
                          <div className="mt-1.5 text-xs text-slate-600">{corr.identifiedProblem}</div>
                        </div>

                        <div className="rounded border border-green-200 bg-white p-3">
                          <div className="mb-1 text-[0.72rem] font-bold uppercase tracking-wide text-green-800">
                            STEP 2 &ndash; How to fix it?
                          </div>
                          <div className="whitespace-pre-line text-sm text-slate-900">{corr.recommendedImprovement}</div>
                        </div>
                      </div>

                      <div className="mt-2 rounded border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800">
                        <strong>STEP 3 &ndash; Why does this matter?</strong> {corr.reason}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
                  No specific corrections are needed right now.
                </div>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
