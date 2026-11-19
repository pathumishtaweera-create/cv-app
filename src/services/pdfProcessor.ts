import * as pdfjsLib from 'pdfjs-dist';
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB } from '../config/categories';
import type {
  PageDimensionInfo,
  PageLayoutMetrics,
  ProcessedPDFDocument,
  TextLineInfo,
} from '../types/cv';

function ensurePdfWorkerConfigured(): void {
  if (typeof pdfjsWorker === 'string' && pdfjsWorker.length > 0) {
    pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker;
  }
}

const MAX_RENDERED_PREVIEW_PAGES = 5;

export class PDFProcessingError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PDFProcessingError';
  }
}

export function formatFileSize(numBytes: number): string {
  if (numBytes < 1024) return `${numBytes} B`;
  if (numBytes < 1024 * 1024) return `${(numBytes / 1024).toFixed(1)} KB`;
  return `${(numBytes / (1024 * 1024)).toFixed(2)} MB`;
}

function classifyPaperSize(widthPt: number, heightPt: number): string {
  const tol = 8;
  if (Math.abs(widthPt - 595) <= tol && Math.abs(heightPt - 842) <= tol) return 'A4 Portrait';
  if (Math.abs(widthPt - 842) <= tol && Math.abs(heightPt - 595) <= tol) return 'A4 Landscape';
  if (Math.abs(widthPt - 612) <= tol && Math.abs(heightPt - 792) <= tol) return 'US Letter Portrait';
  if (Math.abs(widthPt - 792) <= tol && Math.abs(heightPt - 612) <= tol) return 'US Letter Landscape';
  return `Custom (${Math.round(widthPt)} x ${Math.round(heightPt)} pt)`;
}

function bboxIntersectionArea(
  a: [number, number, number, number],
  b: [number, number, number, number],
): number {
  const ix0 = Math.max(a[0], b[0]);
  const iy0 = Math.max(a[1], b[1]);
  const ix1 = Math.min(a[2], b[2]);
  const iy1 = Math.min(a[3], b[3]);
  if (ix1 <= ix0 || iy1 <= iy0) return 0;
  return (ix1 - ix0) * (iy1 - iy0);
}

function bboxArea(b: [number, number, number, number]): number {
  return Math.max(0, b[2] - b[0]) * Math.max(0, b[3] - b[1]);
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

interface RawTextChunk {
  str: string;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  fontSize: number;
  fontName: string;
  isBold: boolean;
}

export async function processUploadedPdf(file: File): Promise<ProcessedPDFDocument> {
  const safeName = (file.name || 'uploaded_cv.pdf').split(/[/\\]/).pop() || 'uploaded_cv.pdf';

  if (!safeName.toLowerCase().endsWith('.pdf')) {
    throw new PDFProcessingError(
      `Unsupported file format for '${safeName}'. Please upload a PDF (.pdf) file only.`,
    );
  }

  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);

  if (bytes.length === 0) {
    throw new PDFProcessingError(
      `The file '${safeName}' is empty (0 bytes). Please upload a valid PDF CV.`,
    );
  }

  if (bytes.length > MAX_FILE_SIZE_BYTES) {
    throw new PDFProcessingError(
      `The file '${safeName}' (${formatFileSize(bytes.length)}) exceeds the ${MAX_FILE_SIZE_MB} MB maximum upload limit. Please compress or export a smaller PDF.`,
    );
  }

  const headerSlice = new TextDecoder('latin1').decode(bytes.slice(0, Math.min(1024, bytes.length)));
  if (!headerSlice.includes('%PDF-')) {
    throw new PDFProcessingError(
      `The file '${safeName}' does not have a valid PDF signature. Please export your CV as a genuine PDF document and try again.`,
    );
  }

  ensurePdfWorkerConfigured();
  let pdfDoc: pdfjsLib.PDFDocumentProxy;
  const loadingTask = pdfjsLib.getDocument({ data: bytes });
  try {
    pdfDoc = await loadingTask.promise;
  } catch (err) {
    const errName = (err as { name?: string; message?: string })?.name || '';
    const errMsg = (err as { message?: string })?.message || '';
    if (errName === 'PasswordException' || /password/i.test(errMsg)) {
      throw new PDFProcessingError(
        `The PDF '${safeName}' is password-protected or encrypted. Please remove the password and upload an unlocked PDF.`,
      );
    }
    throw new PDFProcessingError(
      `The file '${safeName}' appears corrupted or cannot be parsed as a valid PDF.`,
    );
  }

  try {
    const pageCount = pdfDoc.numPages;
    if (pageCount === 0) {
      throw new PDFProcessingError(`The PDF '${safeName}' contains zero pages.`);
    }

    const pageDimensions: PageDimensionInfo[] = [];
    const pageTexts: string[] = [];
    const allLines: TextLineInfo[] = [];
    const pagePreviewUrls: string[] = [];
    const pageMetricsRaw: Array<{
      pageNumber: number;
      charCount: number;
      wordCount: number;
      lineCount: number;
      leftMarginPt: number | null;
      rightMarginPt: number | null;
      topMarginPt: number | null;
      bottomMarginPt: number | null;
      alignmentIndicators: string[];
      medianLineGapPt: number | null;
      sectionGapCount: number;
      overlappingLinePairs: number;
      clippedLineCount: number;
    }> = [];

    const fontSizeWeights = new Map<number, number>();
    const allFontNames = new Set<string>();
    let totalOverlapping = 0;
    let totalClipped = 0;

    for (let pageNum = 1; pageNum <= pageCount; pageNum++) {
      const page = await pdfDoc.getPage(pageNum);
      const viewport = page.getViewport({ scale: 1 });
      const pageWidth = viewport.width;
      const pageHeight = viewport.height;

      pageDimensions.push({
        pageNumber: pageNum,
        widthPt: round2(pageWidth),
        heightPt: round2(pageHeight),
        paperSizeLabel: classifyPaperSize(pageWidth, pageHeight),
      });

      const textContent = await page.getTextContent();
      const styles = (textContent.styles || {}) as Record<
        string,
        { fontFamily?: string }
      >;

      const chunks: RawTextChunk[] = [];
      for (const rawItem of textContent.items) {
        if (!('str' in rawItem)) continue;
        const textStr = rawItem.str;
        if (!textStr || !textStr.trim()) continue;

        const tx = rawItem.transform; // [a, b, c, d, e, f]
        const fontSize = Math.max(
          Math.hypot(tx[0], tx[1]),
          Math.hypot(tx[2], tx[3]),
          rawItem.height || 0,
        );
        const x0 = tx[4];
        // Convert PDF bottom-left origin to top-left coordinates matching PyMuPDF
        const baselineY = pageHeight - tx[5];
        const y0 = baselineY - fontSize * 0.85;
        const y1 = baselineY + fontSize * 0.2;
        const width = Math.max(rawItem.width || textStr.length * fontSize * 0.45, 2);
        const x1 = x0 + width;

        const styleInfo = styles[rawItem.fontName];
        const resolvedFont = styleInfo?.fontFamily || rawItem.fontName || 'sans-serif';
        const isBold = /bold|black|heavy|hebo/i.test(`${rawItem.fontName} ${resolvedFont}`);

        chunks.push({
          str: textStr,
          x0,
          y0,
          x1,
          y1,
          fontSize: Math.round(fontSize * 10) / 10,
          fontName: resolvedFont,
          isBold,
        });
      }

      // Group chunks into visual lines by baseline proximity (within 3pt) and horizontal continuity
      chunks.sort((a, b) => a.y0 - b.y0 || a.x0 - b.x0);
      const lineGroups: RawTextChunk[][] = [];
      for (const ch of chunks) {
        const lastGroup = lineGroups[lineGroups.length - 1];
        if (lastGroup) {
          const ref = lastGroup[0];
          const sameLineY = Math.abs(ch.y0 - ref.y0) <= Math.max(3.0, ref.fontSize * 0.35);
          // Avoid merging columns or intentionally separated overlapping text if far apart horizontally on different baselines
          if (sameLineY && Math.abs(ch.y0 - ref.y0) <= 2.5) {
            lastGroup.push(ch);
            continue;
          }
        }
        lineGroups.push([ch]);
      }

      const pageLines: TextLineInfo[] = [];
      for (const group of lineGroups) {
        group.sort((a, b) => a.x0 - b.x0);
        let merged = '';
        let prevX1: number | null = null;
        for (const ch of group) {
          if (prevX1 !== null && ch.x0 - prevX1 > Math.max(1.5, ch.fontSize * 0.15) && !merged.endsWith(' ')) {
            merged += ' ';
          }
          merged += ch.str;
          prevX1 = ch.x1;
        }
        const cleaned = merged.replace(/\s+/g, ' ').trim();
        if (!cleaned) continue;

        const x0 = Math.min(...group.map((g) => g.x0));
        const y0 = Math.min(...group.map((g) => g.y0));
        const x1 = Math.max(...group.map((g) => g.x1));
        const y1 = Math.max(...group.map((g) => g.y1));
        const maxFontSize = Math.max(...group.map((g) => g.fontSize));
        const fontNames = Array.from(new Set(group.map((g) => g.fontName)));
        const isBold = group.some((g) => g.isBold);

        for (const g of group) {
          if (g.fontSize > 0) {
            const roundedPt = Math.round(g.fontSize * 2) / 2;
            fontSizeWeights.set(roundedPt, (fontSizeWeights.get(roundedPt) || 0) + g.str.trim().length);
          }
          allFontNames.add(g.fontName);
        }

        const lineInfo: TextLineInfo = {
          pageNumber: pageNum,
          text: cleaned,
          bbox: [round2(x0), round2(y0), round2(x1), round2(y1)],
          fontNames,
          maxFontSize: round2(maxFontSize),
          isBold,
        };
        pageLines.push(lineInfo);
        allLines.push(lineInfo);
      }

      const pageText = pageLines.map((l) => l.text).join('\n');
      pageTexts.push(pageText);

      // Overlap and clipping checks
      let overlappingPairs = 0;
      for (let i = 0; i < pageLines.length; i++) {
        for (let j = i + 1; j < pageLines.length; j++) {
          const boxA = pageLines[i].bbox;
          const boxB = pageLines[j].bbox;
          if (boxB[1] >= boxA[3]) continue;
          const inter = bboxIntersectionArea(boxA, boxB);
          if (inter <= 0) continue;
          const minArea = Math.min(bboxArea(boxA), bboxArea(boxB));
          if (minArea > 0 && inter / minArea > 0.15) {
            overlappingPairs++;
          }
        }
      }

      let clippedLines = 0;
      for (const ln of pageLines) {
        if (ln.bbox[0] < -2 || ln.bbox[1] < -2 || ln.bbox[2] > pageWidth + 2 || ln.bbox[3] > pageHeight + 2) {
          clippedLines++;
        }
      }

      totalOverlapping += overlappingPairs;
      totalClipped += clippedLines;

      // Margins & alignment
      let leftMargin: number | null = null;
      let rightMargin: number | null = null;
      let topMargin: number | null = null;
      let bottomMargin: number | null = null;
      const alignmentIndicators: string[] = [];
      let medianGap: number | null = null;
      let sectionGapCount = 0;

      if (pageLines.length > 0) {
        leftMargin = round2(Math.max(0, Math.min(...pageLines.map((l) => l.bbox[0]))));
        rightMargin = round2(Math.max(0, pageWidth - Math.max(...pageLines.map((l) => l.bbox[2]))));
        topMargin = round2(Math.max(0, Math.min(...pageLines.map((l) => l.bbox[1]))));
        bottomMargin = round2(Math.max(0, pageHeight - Math.max(...pageLines.map((l) => l.bbox[3]))));

        const xBuckets = new Map<number, number>();
        for (const l of pageLines) {
          const bucket = Math.round(l.bbox[0] / 4) * 4;
          xBuckets.set(bucket, (xBuckets.get(bucket) || 0) + 1);
        }
        const dominantCount = Math.max(...xBuckets.values());
        if (dominantCount / pageLines.length >= 0.45) {
          alignmentIndicators.push('Consistent left-aligned margin anchors detected');
        } else {
          alignmentIndicators.push('Multiple horizontal text anchors detected');
        }

        const gaps: number[] = [];
        for (let i = 1; i < pageLines.length; i++) {
          const gap = pageLines[i].bbox[1] - pageLines[i - 1].bbox[3];
          if (gap >= -1 && gap <= 45) gaps.push(gap);
        }
        if (gaps.length > 0) {
          const med = median(gaps);
          medianGap = round2(med);
          sectionGapCount = gaps.filter((g) => g > Math.max(med * 1.8, med + 5)).length;
        }
      }

      const charCount = pageText.replace(/\s+/g, '').length;
      const words = pageText.trim() ? pageText.trim().split(/\s+/).length : 0;

      pageMetricsRaw.push({
        pageNumber: pageNum,
        charCount,
        wordCount: words,
        lineCount: pageLines.length,
        leftMarginPt: leftMargin,
        rightMarginPt: rightMargin,
        topMarginPt: topMargin,
        bottomMarginPt: bottomMargin,
        alignmentIndicators,
        medianLineGapPt: medianGap,
        sectionGapCount,
        overlappingLinePairs: overlappingPairs,
        clippedLineCount: clippedLines,
      });

      // Render page preview to canvas (up to MAX_RENDERED_PREVIEW_PAGES)
      if (pageNum <= MAX_RENDERED_PREVIEW_PAGES && typeof document !== 'undefined') {
        try {
          const previewViewport = page.getViewport({ scale: 1.35 });
          const canvas = document.createElement('canvas');
          canvas.width = Math.round(previewViewport.width);
          canvas.height = Math.round(previewViewport.height);
          const ctx = canvas.getContext('2d');
          if (ctx) {
            await page.render({ canvas, canvasContext: ctx, viewport: previewViewport }).promise;
            pagePreviewUrls.push(canvas.toDataURL('image/png'));
          }
        } catch {
          // Canvas preview is optional; ignore rendering issues in headless tests
        }
      }
    }

    const totalNonWsChars = pageMetricsRaw.reduce((acc, p) => acc + p.charCount, 0);
    const pageMetrics: PageLayoutMetrics[] = pageMetricsRaw.map((p) => ({
      pageNumber: p.pageNumber,
      characterCount: p.charCount,
      wordCount: p.wordCount,
      lineCount: p.lineCount,
      imageCount: 0,
      textDistributionPct: totalNonWsChars > 0 ? round2((p.charCount / totalNonWsChars) * 100) : 0,
      leftMarginPt: p.leftMarginPt,
      rightMarginPt: p.rightMarginPt,
      topMarginPt: p.topMarginPt,
      bottomMarginPt: p.bottomMarginPt,
      alignmentIndicators: p.alignmentIndicators,
      medianLineGapPt: p.medianLineGapPt,
      sectionGapCount: p.sectionGapCount,
      overlappingLinePairs: p.overlappingLinePairs,
      clippedLineCount: p.clippedLineCount,
    }));

    const extractedText = pageTexts.join('\n\n').trim();
    const totalWords = extractedText ? extractedText.split(/\s+/).length : 0;
    const totalChars = extractedText.length;
    const hasExtractableText = totalChars >= 25 && totalWords >= 5;

    const sortedSizes = Array.from(fontSizeWeights.keys()).sort((a, b) => a - b);
    let primaryBodySize: number | null = null;
    if (fontSizeWeights.size > 0) {
      let bestWeight = -1;
      for (const [sz, w] of fontSizeWeights.entries()) {
        if (w > bestWeight) {
          bestWeight = w;
          primaryBodySize = sz;
        }
      }
    }
    const largestHeadingSize = sortedSizes.length > 0 ? sortedSizes[sortedSizes.length - 1] : null;

    return {
      filename: safeName,
      fileSizeBytes: bytes.length,
      fileSizeDisplay: formatFileSize(bytes.length),
      pageCount,
      wordCount: totalWords,
      characterCount: totalChars,
      hasExtractableText,
      isScannedPdf: !hasExtractableText,
      extractedText,
      pageTexts,
      textLines: allLines,
      pagePreviewUrls,
      documentAnalysis: {
        pageCount,
        pageDimensions,
        fontNames: Array.from(allFontNames).sort(),
        fontSizesPt: sortedSizes,
        primaryBodyFontSizePt: primaryBodySize,
        largestHeadingFontSizePt: largestHeadingSize,
        pageMetrics,
        totalOverlappingPairs: totalOverlapping,
        totalClippedLines: totalClipped,
      },
    };
  } finally {
    await pdfDoc.cleanup();
    await loadingTask.destroy();
  }
}
