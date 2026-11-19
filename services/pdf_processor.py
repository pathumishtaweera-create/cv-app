"""
Local PDF validation, text extraction, and document layout analysis using PyMuPDF.

All uploaded files are validated and processed strictly in memory.
No files are executed or permanently written to disk.
"""

from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from statistics import median
from typing import Any
import pymupdf

from config.settings import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_MB,
    PDF_MAGIC_HEADER,
)

# Maximum pages to render into PNG preview images in memory to keep memory bounded
MAX_RENDERED_PREVIEW_PAGES = 5


class PDFProcessingError(Exception):
    """Base exception for PDF validation and extraction failures."""


class UnsupportedFileTypeError(PDFProcessingError):
    """Raised when the uploaded file is not a valid PDF."""


class EmptyFileError(PDFProcessingError):
    """Raised when the uploaded file is empty (0 bytes) or has no pages."""


class FileSizeExceededError(PDFProcessingError):
    """Raised when the uploaded file exceeds the configured maximum size."""


class PasswordProtectedPDFError(PDFProcessingError):
    """Raised when the uploaded PDF is encrypted and requires a password."""


class CorruptedPDFError(PDFProcessingError):
    """Raised when the uploaded PDF cannot be parsed or appears corrupted."""


@dataclass(frozen=True)
class TextLineInfo:
    """Represents a single extracted text line with PyMuPDF layout coordinates and font metadata."""

    page_number: int
    text: str
    bbox: tuple[float, float, float, float]
    font_names: tuple[str, ...]
    max_font_size: float
    is_bold: bool


@dataclass(frozen=True)
class PageDimensionInfo:
    """Page size metadata in points and millimeters."""

    page_number: int
    width_pt: float
    height_pt: float
    width_mm: float
    height_mm: float
    paper_size_label: str


@dataclass(frozen=True)
class PageLayoutMetrics:
    """Document-quality and layout geometry metrics collected for a single PDF page."""

    page_number: int
    character_count: int
    word_count: int
    line_count: int
    image_count: int
    text_distribution_pct: float
    left_margin_pt: float | None
    right_margin_pt: float | None
    top_margin_pt: float | None
    bottom_margin_pt: float | None
    alignment_indicators: tuple[str, ...]
    median_line_gap_pt: float | None
    section_gap_count: int
    multi_column_suspected: bool
    overlapping_line_pairs: int
    clipped_line_count: int


@dataclass(frozen=True)
class PDFDocumentAnalysis:
    """Technical document-quality metrics collected for later evaluation."""

    page_count: int
    page_dimensions: tuple[PageDimensionInfo, ...]
    font_names: tuple[str, ...]
    font_sizes_pt: tuple[float, ...]
    primary_body_font_size_pt: float | None
    largest_heading_font_size_pt: float | None
    total_image_count: int
    page_metrics: tuple[PageLayoutMetrics, ...]
    total_overlapping_pairs: int
    total_clipped_lines: int
    unusual_layout_indicators: tuple[str, ...]
    measurement_limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Convert analysis metrics into a JSON-serializable dictionary."""
        return asdict(self)


@dataclass(frozen=True)
class ProcessedPDFDocument:
    """In-memory representation of a validated and parsed PDF CV."""

    filename: str
    file_size_bytes: int
    file_size_display: str
    page_count: int
    word_count: int
    character_count: int
    has_extractable_text: bool
    is_scanned_pdf: bool
    extracted_text: str
    page_texts: tuple[str, ...]
    text_lines: tuple[TextLineInfo, ...]
    pdf_title: str
    pdf_author: str
    first_page_preview_png: bytes | None
    page_preview_images: tuple[bytes | None, ...]
    document_analysis: PDFDocumentAnalysis


def format_file_size(num_bytes: int) -> str:
    """Return a human-readable file size string (e.g., '412.5 KB' or '1.84 MB')."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"


def _sanitize_filename(raw_filename: str) -> str:
    """Strip directory components so only a safe base filename is displayed."""
    return Path(raw_filename or "uploaded_cv.pdf").name


def _classify_paper_size(width_pt: float, height_pt: float) -> str:
    """Identify standard paper dimensions (A4, US Letter) within a small tolerance."""
    tol = 8.0
    if abs(width_pt - 595.0) <= tol and abs(height_pt - 842.0) <= tol:
        return "A4 Portrait"
    if abs(width_pt - 842.0) <= tol and abs(height_pt - 595.0) <= tol:
        return "A4 Landscape"
    if abs(width_pt - 612.0) <= tol and abs(height_pt - 792.0) <= tol:
        return "US Letter Portrait"
    if abs(width_pt - 792.0) <= tol and abs(height_pt - 612.0) <= tol:
        return "US Letter Landscape"
    return f"Custom ({round(width_pt)} x {round(height_pt)} pt)"


def _bbox_intersection_area(
    box_a: tuple[float, float, float, float],
    box_b: tuple[float, float, float, float],
) -> float:
    """Compute intersection area between two (x0, y0, x1, y1) bounding boxes."""
    ix0 = max(box_a[0], box_b[0])
    iy0 = max(box_a[1], box_b[1])
    ix1 = min(box_a[2], box_b[2])
    iy1 = min(box_a[3], box_b[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def _bbox_area(box: tuple[float, float, float, float]) -> float:
    """Compute area of a bounding box."""
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def validate_upload_inputs(
    filename: str,
    file_bytes: bytes,
    mime_type: str | None = None,
) -> str:
    """
    Validate file extension, size, emptiness, MIME hint, and PDF signature.

    Returns the sanitized filename if valid, or raises a specific PDFProcessingError.
    """
    safe_name = _sanitize_filename(filename)

    if Path(safe_name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported file format for '{safe_name}'. Please upload a PDF (.pdf) file only."
        )

    if not file_bytes or len(file_bytes) == 0:
        raise EmptyFileError(
            f"The file '{safe_name}' is empty (0 bytes). Please upload a valid PDF CV."
        )

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        actual_size = format_file_size(len(file_bytes))
        raise FileSizeExceededError(
            f"The file '{safe_name}' ({actual_size}) exceeds the {MAX_FILE_SIZE_MB} MB "
            "maximum upload limit. Please compress or export a smaller PDF."
        )

    if mime_type:
        normalized_mime = mime_type.lower().strip()
        allowed_mimes = {"application/pdf", "application/x-pdf", "application/octet-stream"}
        if normalized_mime not in allowed_mimes:
            raise UnsupportedFileTypeError(
                f"Unsupported file content type ('{mime_type}'). Only PDF documents are accepted."
            )

    if PDF_MAGIC_HEADER not in file_bytes[:1024]:
        raise UnsupportedFileTypeError(
            f"The file '{safe_name}' does not have a valid PDF signature. "
            "Please export your CV as a genuine PDF document and try again."
        )

    return safe_name


def _extract_page_lines_and_metrics(
    page: pymupdf.Page,
    page_number: int,
) -> tuple[list[TextLineInfo], dict[str, Any], Counter[float], set[str]]:
    """
    Inspect a PyMuPDF page dictionary to collect ordered text lines, font usage,
    alignment/spacing geometry, overlaps, and clipping indicators.
    """
    page_dict = page.get_text("dict", clip=pymupdf.INFINITE_RECT())
    rect = page.rect
    page_width = float(rect.width)
    page_height = float(rect.height)
    image_count = len(page.get_images(full=True))

    lines: list[TextLineInfo] = []
    font_size_char_weights: Counter[float] = Counter()
    page_fonts: set[str] = set()

    for block in page_dict.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue

            span_texts: list[str] = []
            line_fonts: list[str] = []
            max_size = 0.0
            is_bold = False

            for span in spans:
                txt = span.get("text", "")
                if not txt:
                    continue
                span_texts.append(txt)
                font_name = (span.get("font") or "").strip()
                if font_name:
                    line_fonts.append(font_name)
                    page_fonts.add(font_name)
                    if any(tok in font_name.lower() for tok in ("bold", "black", "heavy", "semibold", "demi")):
                        is_bold = True

                size_val = round(float(span.get("size", 0.0)) * 2.0) / 2.0
                if size_val > 0:
                    max_size = max(max_size, size_val)
                    non_ws_len = len(txt.strip())
                    if non_ws_len > 0:
                        font_size_char_weights[size_val] += non_ws_len

                flags = int(span.get("flags", 0))
                if flags & 16:  # PyMuPDF bold flag bit
                    is_bold = True

            combined_text = " ".join("".join(span_texts).split()).strip()
            if not combined_text:
                continue

            bbox_raw = line.get("bbox", (0.0, 0.0, 0.0, 0.0))
            bbox = (
                round(float(bbox_raw[0]), 2),
                round(float(bbox_raw[1]), 2),
                round(float(bbox_raw[2]), 2),
                round(float(bbox_raw[3]), 2),
            )
            lines.append(
                TextLineInfo(
                    page_number=page_number,
                    text=combined_text,
                    bbox=bbox,
                    font_names=tuple(dict.fromkeys(line_fonts)),
                    max_font_size=max_size,
                    is_bold=is_bold,
                )
            )

    # Sort top-to-bottom, left-to-right for raw geometry checks
    lines_sorted = sorted(lines, key=lambda item: (round(item.bbox[1], 1), item.bbox[0]))

    # Detect multi-column layout by checking if significant text starts near or right of page midpoint
    midpoint_x = page_width * 0.48
    left_column_lines = [ln for ln in lines_sorted if ln.bbox[0] < midpoint_x and ln.bbox[2] <= page_width * 0.58]
    right_column_lines = [ln for ln in lines_sorted if ln.bbox[0] >= midpoint_x]
    multi_column_suspected = len(left_column_lines) >= 5 and len(right_column_lines) >= 5

    # If two-column layout is suspected, reorder reading stream: full-width header lines,
    # then left column top-to-bottom, then right column top-to-bottom
    if multi_column_suspected:
        full_width_top: list[TextLineInfo] = []
        left_col: list[TextLineInfo] = []
        right_col: list[TextLineInfo] = []
        col_split_y = min(ln.bbox[1] for ln in right_column_lines)
        for ln in lines_sorted:
            if ln.bbox[1] < col_split_y - 4 and ln.bbox[2] > midpoint_x:
                full_width_top.append(ln)
            elif ln.bbox[0] >= midpoint_x:
                right_col.append(ln)
            else:
                left_col.append(ln)
        ordered_lines = (
            sorted(full_width_top, key=lambda l: (l.bbox[1], l.bbox[0]))
            + sorted(left_col, key=lambda l: (l.bbox[1], l.bbox[0]))
            + sorted(right_col, key=lambda l: (l.bbox[1], l.bbox[0]))
        )
    else:
        ordered_lines = lines_sorted

    # Geometry & spacing metrics
    if lines_sorted:
        min_x0 = min(ln.bbox[0] for ln in lines_sorted)
        max_x1 = max(ln.bbox[2] for ln in lines_sorted)
        min_y0 = min(ln.bbox[1] for ln in lines_sorted)
        max_y1 = max(ln.bbox[3] for ln in lines_sorted)
        left_margin = round(max(0.0, min_x0), 1)
        right_margin = round(max(0.0, page_width - max_x1), 1)
        top_margin = round(max(0.0, min_y0), 1)
        bottom_margin = round(max(0.0, page_height - max_y1), 1)
    else:
        left_margin = right_margin = top_margin = bottom_margin = None

    # Alignment indicators from line x-coordinates
    alignment_indicators: list[str] = []
    if lines_sorted:
        left_x_clusters = Counter(round(ln.bbox[0] / 4.0) * 4 for ln in lines_sorted)
        dominant_left_count = left_x_clusters.most_common(1)[0][1]
        if dominant_left_count >= max(3, int(len(lines_sorted) * 0.3)):
            alignment_indicators.append("Consistent left-aligned block structure")

        centered_lines = [
            ln
            for ln in lines_sorted
            if abs(((ln.bbox[0] + ln.bbox[2]) / 2.0) - (page_width / 2.0)) <= 18.0
            and (ln.bbox[2] - ln.bbox[0]) < page_width * 0.7
        ]
        if centered_lines:
            alignment_indicators.append(f"Centered elements detected ({len(centered_lines)} line(s))")

        right_aligned_lines = [
            ln
            for ln in lines_sorted
            if ln.bbox[0] > page_width * 0.55 and abs((page_width - ln.bbox[2]) - (left_margin or 36.0)) <= 24.0
        ]
        if right_aligned_lines:
            alignment_indicators.append(f"Right-aligned metadata/dates detected ({len(right_aligned_lines)} line(s))")

        if multi_column_suspected:
            alignment_indicators.append("Multi-column layout detected")

    # Vertical line spacing & section gap indicators (computed along vertical reading order)
    vertical_gaps: list[float] = []
    for idx in range(1, len(ordered_lines)):
        prev_ln = ordered_lines[idx - 1]
        curr_ln = ordered_lines[idx]
        gap = curr_ln.bbox[1] - prev_ln.bbox[3]
        # Ignore negative column-jump gaps
        if -1.0 <= gap <= 80.0:
            vertical_gaps.append(round(max(0.0, gap), 2))

    positive_gaps = [g for g in vertical_gaps if g > 0.5]
    med_gap = round(median(positive_gaps), 2) if positive_gaps else None
    section_gap_count = 0
    if med_gap is not None and med_gap > 0:
        section_gap_count = sum(1 for g in vertical_gaps if g >= max(med_gap * 1.8, 10.0))
    else:
        section_gap_count = sum(1 for g in vertical_gaps if g >= 12.0)

    # Potentially overlapping text lines (pairwise check within y-proximity)
    overlapping_pairs = 0
    for i in range(len(lines_sorted)):
        box_a = lines_sorted[i].bbox
        area_a = _bbox_area(box_a)
        if area_a <= 0:
            continue
        for j in range(i + 1, len(lines_sorted)):
            box_b = lines_sorted[j].bbox
            if box_b[1] > box_a[3]:
                break
            inter = _bbox_intersection_area(box_a, box_b)
            if inter > 0:
                area_b = _bbox_area(box_b)
                min_area = min(area_a, area_b)
                if min_area > 0 and (inter / min_area) >= 0.2:
                    overlapping_pairs += 1

    # Clipped or out-of-page-bounds text lines
    clipped_lines = sum(
        1
        for ln in lines_sorted
        if ln.bbox[0] < -2.0
        or ln.bbox[1] < -2.0
        or ln.bbox[2] > page_width + 2.0
        or ln.bbox[3] > page_height + 2.0
    )

    page_text = "\n".join(ln.text for ln in ordered_lines).strip()

    raw_metrics = {
        "page_number": page_number,
        "character_count": len(page_text),
        "word_count": len(page_text.split()) if page_text else 0,
        "line_count": len(ordered_lines),
        "image_count": image_count,
        "left_margin_pt": left_margin,
        "right_margin_pt": right_margin,
        "top_margin_pt": top_margin,
        "bottom_margin_pt": bottom_margin,
        "alignment_indicators": tuple(alignment_indicators),
        "median_line_gap_pt": med_gap,
        "section_gap_count": section_gap_count,
        "multi_column_suspected": multi_column_suspected,
        "overlapping_line_pairs": overlapping_pairs,
        "clipped_line_count": clipped_lines,
        "page_text": page_text,
    }
    return ordered_lines, raw_metrics, font_size_char_weights, page_fonts


def process_pdf_bytes(
    filename: str,
    file_bytes: bytes,
    mime_type: str | None = None,
) -> ProcessedPDFDocument:
    """
    Validate and extract text, metadata, rendered page previews, and layout metrics
    from an in-memory PDF byte buffer using PyMuPDF.
    """
    safe_name = validate_upload_inputs(filename=filename, file_bytes=file_bytes, mime_type=mime_type)

    doc: pymupdf.Document | None = None
    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise CorruptedPDFError(
            f"Unable to open '{safe_name}'. The PDF appears to be corrupted or malformed."
        ) from exc
    except Exception as exc:
        raise CorruptedPDFError(
            f"An unexpected error occurred while reading '{safe_name}'. Please re-export the PDF."
        ) from exc

    try:
        if getattr(doc, "needs_pass", False):
            raise PasswordProtectedPDFError(
                f"'{safe_name}' is password-protected. Please remove the password "
                "protection from the PDF before uploading."
            )

        page_count = doc.page_count
        if page_count <= 0:
            raise EmptyFileError(
                f"'{safe_name}' contains 0 pages and cannot be analyzed."
            )

        all_lines: list[TextLineInfo] = []
        page_texts: list[str] = []
        page_dimensions: list[PageDimensionInfo] = []
        raw_page_metrics: list[dict[str, Any]] = []
        total_font_size_weights: Counter[float] = Counter()
        all_fonts: set[str] = set()
        page_preview_images: list[bytes | None] = []
        unusual_layout_indicators: list[str] = []

        for page_index in range(page_count):
            page_num = page_index + 1
            page = doc.load_page(page_index)
            rect = page.rect
            width_pt = round(float(rect.width), 1)
            height_pt = round(float(rect.height), 1)
            page_dimensions.append(
                PageDimensionInfo(
                    page_number=page_num,
                    width_pt=width_pt,
                    height_pt=height_pt,
                    width_mm=round(width_pt * 25.4 / 72.0, 1),
                    height_mm=round(height_pt * 25.4 / 72.0, 1),
                    paper_size_label=_classify_paper_size(width_pt, height_pt),
                )
            )

            ordered_lines, raw_metrics, size_weights, page_fonts = _extract_page_lines_and_metrics(
                page=page,
                page_number=page_num,
            )
            all_lines.extend(ordered_lines)
            page_texts.append(raw_metrics["page_text"])
            raw_page_metrics.append(raw_metrics)
            total_font_size_weights.update(size_weights)
            all_fonts.update(page_fonts)

            if raw_metrics["multi_column_suspected"]:
                unusual_layout_indicators.append(
                    f"Page {page_num} uses a multi-column layout; reading order was reconstructed from column coordinates."
                )
            if raw_metrics["overlapping_line_pairs"] > 0:
                unusual_layout_indicators.append(
                    f"Page {page_num} has {raw_metrics['overlapping_line_pairs']} overlapping text bounding box pair(s)."
                )
            if raw_metrics["clipped_line_count"] > 0:
                unusual_layout_indicators.append(
                    f"Page {page_num} has {raw_metrics['clipped_line_count']} text line(s) extending outside page bounds."
                )

            if page_index < MAX_RENDERED_PREVIEW_PAGES:
                try:
                    pixmap = page.get_pixmap(dpi=130, alpha=False)
                    page_preview_images.append(pixmap.tobytes("png"))
                except Exception:
                    page_preview_images.append(None)

        extracted_text = "\n\n".join(txt for txt in page_texts if txt).strip()
        character_count = len(extracted_text)
        word_count = len(extracted_text.split()) if extracted_text else 0
        has_extractable_text = character_count > 0

        total_image_count = sum(m["image_count"] for m in raw_page_metrics)
        is_scanned_pdf = (not has_extractable_text) or (character_count < 25 and total_image_count > 0)

        if is_scanned_pdf and total_image_count > 0:
            unusual_layout_indicators.append(
                "Document contains embedded page image(s) with little or no selectable text (likely scanned)."
            )

        # Compute per-page text distribution percentages
        total_chars_for_dist = sum(m["character_count"] for m in raw_page_metrics)
        page_metrics_objs: list[PageLayoutMetrics] = []
        for m in raw_page_metrics:
            dist_pct = (
                round((m["character_count"] / total_chars_for_dist) * 100.0, 1)
                if total_chars_for_dist > 0
                else 0.0
            )
            page_metrics_objs.append(
                PageLayoutMetrics(
                    page_number=m["page_number"],
                    character_count=m["character_count"],
                    word_count=m["word_count"],
                    line_count=m["line_count"],
                    image_count=m["image_count"],
                    text_distribution_pct=dist_pct,
                    left_margin_pt=m["left_margin_pt"],
                    right_margin_pt=m["right_margin_pt"],
                    top_margin_pt=m["top_margin_pt"],
                    bottom_margin_pt=m["bottom_margin_pt"],
                    alignment_indicators=m["alignment_indicators"],
                    median_line_gap_pt=m["median_line_gap_pt"],
                    section_gap_count=m["section_gap_count"],
                    multi_column_suspected=m["multi_column_suspected"],
                    overlapping_line_pairs=m["overlapping_line_pairs"],
                    clipped_line_count=m["clipped_line_count"],
                )
            )

        sorted_font_sizes = tuple(sorted(total_font_size_weights.keys()))
        primary_body_size = (
            total_font_size_weights.most_common(1)[0][0]
            if total_font_size_weights
            else None
        )
        largest_heading_size = max(sorted_font_sizes) if sorted_font_sizes else None

        measurement_limitations = (
            "Text positions, margins, and font metadata reflect embedded PDF vector text objects only.",
            "Text rendered inside raster images or scanned pages cannot be inspected without OCR (not implemented).",
            "Visual aesthetics (color harmony, whitespace balance, and table borders) are not scored automatically in this module.",
        )

        doc_analysis = PDFDocumentAnalysis(
            page_count=page_count,
            page_dimensions=tuple(page_dimensions),
            font_names=tuple(sorted(all_fonts)),
            font_sizes_pt=sorted_font_sizes,
            primary_body_font_size_pt=primary_body_size,
            largest_heading_font_size_pt=largest_heading_size,
            total_image_count=total_image_count,
            page_metrics=tuple(page_metrics_objs),
            total_overlapping_pairs=sum(m["overlapping_line_pairs"] for m in raw_page_metrics),
            total_clipped_lines=sum(m["clipped_line_count"] for m in raw_page_metrics),
            unusual_layout_indicators=tuple(unusual_layout_indicators),
            measurement_limitations=measurement_limitations,
        )

        metadata = doc.metadata or {}
        pdf_title = (metadata.get("title") or "").strip() or "Not specified"
        pdf_author = (metadata.get("author") or "").strip() or "Not specified"

        first_preview = page_preview_images[0] if page_preview_images else None

        return ProcessedPDFDocument(
            filename=safe_name,
            file_size_bytes=len(file_bytes),
            file_size_display=format_file_size(len(file_bytes)),
            page_count=page_count,
            word_count=word_count,
            character_count=character_count,
            has_extractable_text=has_extractable_text,
            is_scanned_pdf=is_scanned_pdf,
            extracted_text=extracted_text,
            page_texts=tuple(page_texts),
            text_lines=tuple(all_lines),
            pdf_title=pdf_title,
            pdf_author=pdf_author,
            first_page_preview_png=first_preview,
            page_preview_images=tuple(page_preview_images),
            document_analysis=doc_analysis,
        )
    except PDFProcessingError:
        raise
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise CorruptedPDFError(
            f"'{safe_name}' could not be read cleanly and may be damaged."
        ) from exc
    finally:
        if doc is not None:
            doc.close()
