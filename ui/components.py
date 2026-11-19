"""
Clean, user-friendly Streamlit UI components for the Banking & Finance CV Analyzer.
"""

import html
import re
import streamlit as st

from config.settings import APP_NAME, APP_SUBTITLE, DEFAULT_PREVIEW_CHAR_LIMIT, MAX_FILE_SIZE_MB
from services.pdf_processor import ProcessedPDFDocument
from services.report_service import CVEvaluationReport


def render_header() -> None:
    """Render the application title and short description."""
    st.markdown(
        f"""
        <div class="bf-header">
            <h1 class="bf-title">{html.escape(APP_NAME)}</h1>
            <p class="bf-subtitle">{html.escape(APP_SUBTITLE)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_upload_section(uploader_key: str = "cv_pdf_uploader"):
    """Render the drag-and-drop PDF upload widget."""
    st.markdown('<div class="bf-section-title">Upload Your CV</div>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="bf-sub-caption">Upload your CV as a PDF file (up to {MAX_FILE_SIZE_MB} MB). Everything runs privately on this computer.</p>',
        unsafe_allow_html=True,
    )
    return st.file_uploader(
        label=f"Upload CV (PDF only, max {MAX_FILE_SIZE_MB} MB)",
        type=["pdf"],
        accept_multiple_files=False,
        key=uploader_key,
        help=f"Accepted format: .pdf up to {MAX_FILE_SIZE_MB} MB.",
        label_visibility="collapsed",
    )


def render_document_preview(document: ProcessedPDFDocument) -> None:
    """Render basic document metadata and an optional expandable preview."""
    st.markdown(
        f"""
        <div class="bf-doc-summary">
            <div>
                <div class="bf-doc-label">File Name</div>
                <div class="bf-doc-val">{html.escape(document.filename)}</div>
            </div>
            <div>
                <div class="bf-doc-label">File Size</div>
                <div class="bf-doc-val">{html.escape(document.file_size_display)}</div>
            </div>
            <div>
                <div class="bf-doc-label">Pages</div>
                <div class="bf-doc-val">{document.page_count}</div>
            </div>
            <div>
                <div class="bf-doc-label">Words Read</div>
                <div class="bf-doc-val">{document.word_count:,}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if document.is_scanned_pdf:
        st.warning(
            "This PDF looks like a scanned picture, so words cannot be read automatically. "
            "Please save your CV as a normal text PDF from Word or Google Docs and try again."
        )

    with st.expander("Preview Your Uploaded CV", expanded=False):
        tab_text, tab_visual = st.tabs(["Readable Text", "Page View"])
        with tab_text:
            if document.has_extractable_text:
                snippet = document.extracted_text[:DEFAULT_PREVIEW_CHAR_LIMIT]
                if len(document.extracted_text) > DEFAULT_PREVIEW_CHAR_LIMIT:
                    snippet += "\n\n[Preview shortened — your full CV is loaded for checking.]"
                st.text_area(
                    label="CV Text",
                    value=snippet,
                    height=220,
                    disabled=True,
                    label_visibility="collapsed",
                )
            else:
                st.info("No readable text was found in this PDF.")

        with tab_visual:
            available_pages = [
                (idx + 1, img)
                for idx, img in enumerate(document.page_preview_images)
                if img is not None
            ]
            if available_pages:
                if len(available_pages) > 1:
                    selected_page = st.selectbox(
                        "Page",
                        options=[p for p, _ in available_pages],
                        format_func=lambda p: f"Page {p} of {document.page_count}",
                        key="visual_preview_page_selector",
                    )
                    chosen_img = dict(available_pages)[selected_page]
                else:
                    selected_page, chosen_img = available_pages[0]

                st.image(
                    chosen_img,
                    caption=f"Page {selected_page} of {document.page_count}",
                    width="stretch",
                )
            else:
                st.info("Page preview is unavailable for this document.")


def render_analyze_controls(
    document: ProcessedPDFDocument | None,
    has_report: bool,
) -> tuple[bool, bool]:
    """Render primary Analyze CV and reset controls. Returns (analyze_clicked, reset_clicked)."""
    col1, col2 = st.columns([2, 1])
    with col1:
        analyze_clicked = st.button(
            label="Analyze CV",
            type="primary",
            width="stretch",
            disabled=(document is None),
        )
    with col2:
        reset_clicked = st.button(
            label="Upload Another CV",
            type="secondary",
            width="stretch",
            disabled=(document is None and not has_report),
        )
    return analyze_clicked, reset_clicked


def _friendly_category_status(status: str) -> str:
    """Translate internal category status labels into simple words."""
    if status == "Evaluated":
        return "Checked"
    if status == "Partial Coverage":
        return "Some details missing"
    if status == "Unavailable":
        return "Not found in CV"
    return status


def render_results_dashboard(
    report: CVEvaluationReport,
    pdf_report_bytes: bytes,
) -> bool:
    """
    Render the user-friendly 4-section CV report:
    1. Your CV Score
    2. What You Did Well
    3. What Needs Improvement (Mistakes to Fix vs. Areas You Can Improve)
    4. How to Improve Your CV (STEP 1 / STEP 2 / STEP 3)

    Returns True if the user clicks 'Check Another CV'.
    """
    ev = report.evaluation
    score_val = max(0.0, min(100.0, report.overall_score))
    safe_candidate = html.escape(report.candidate_name or "Not shown in CV")

    # ------------------------------------------------------------------
    # 1. YOUR CV SCORE
    # ------------------------------------------------------------------
    st.markdown('<div class="bf-section-title">1. Your CV Score</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="bf-score-box">
            <div style="font-size: 0.82rem; color: #64748B; margin-bottom: 0.25rem;">
                Candidate: <strong>{safe_candidate}</strong> &middot; File: {html.escape(report.filename)}
            </div>
            <div class="bf-score-headline">CV SCORE: {report.overall_score:.0f}/{report.total_possible_score}</div>
            <div class="bf-classification bf-class-{html.escape(report.classification_band)}">
                {html.escape(report.classification)}
            </div>
            <p class="bf-score-desc">{html.escape(report.overall_explanation)}</p>
            <p class="bf-disclaimer">{html.escape(report.disclaimer)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(score_val / 100.0)

    if not ev.is_assessable:
        benchmark_variant = "bf-benchmark-unavailable"
    elif report.overall_score >= 60.0:
        benchmark_variant = "bf-benchmark-pass"
    else:
        benchmark_variant = "bf-benchmark-below"

    st.markdown(
        f"""
        <div class="bf-benchmark-note {benchmark_variant}">
            <div class="bf-benchmark-title">{html.escape(report.score_interpretation_title)}</div>
            <p class="bf-benchmark-text">{html.escape(report.score_interpretation_note)}</p>
            <p class="bf-benchmark-sub">{html.escape(report.score_benchmark_clarification)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("See score breakdown by category (9 areas)", expanded=False):
        cat_rows = [
            {
                "Category": f"{c.category.order}. {c.category.title}",
                "Score": f"{c.category_score:.1f} / {c.max_weight}",
                "Percentage": f"{(c.category_score / c.max_weight * 100.0) if c.max_weight else 0.0:.0f}%",
                "Details Found": _friendly_category_status(c.status),
            }
            for c in ev.categories
        ]
        st.dataframe(cat_rows, width="stretch", hide_index=True)

    dl_col, reset_col = st.columns([2, 1])
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", report.filename.rsplit(".", 1)[0]).strip("_") or "cv"
    with dl_col:
        st.download_button(
            label="Download PDF Feedback Report",
            data=pdf_report_bytes,
            file_name=f"{stem}_cv_feedback_report.pdf",
            mime="application/pdf",
            type="secondary",
            width="stretch",
        )
    with reset_col:
        dashboard_reset = st.button(
            label="Check Another CV",
            type="secondary",
            width="stretch",
            key="dashboard_evaluate_another_btn",
        )

    # ------------------------------------------------------------------
    # 2. WHAT YOU DID WELL
    # ------------------------------------------------------------------
    st.markdown('<div class="bf-section-title">2. What You Did Well</div>', unsafe_allow_html=True)
    if report.whats_good:
        for item in report.whats_good:
            st.markdown(
                f"""
                <div class="bf-item bf-item-good">
                    <div class="bf-item-head">
                        <span class="bf-badge-good">[Good]</span> {html.escape(item.title)}
                    </div>
                    <div class="bf-line"><strong>In your CV:</strong> {html.escape(item.evidence)}</div>
                    <div class="bf-line"><strong>Why this helps:</strong> {html.escape(item.why_it_helps)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("No strong examples were found in the readable text of this CV.")

    # ------------------------------------------------------------------
    # 3. WHAT NEEDS IMPROVEMENT
    # ------------------------------------------------------------------
    st.markdown('<div class="bf-section-title">3. What Needs Improvement</div>', unsafe_allow_html=True)
    mistakes = [w for w in report.what_needs_improvement if w.is_error]
    optional_areas = [w for w in report.what_needs_improvement if not w.is_error]

    if not report.what_needs_improvement:
        if not ev.is_assessable:
            st.warning("We could not check this CV because no readable text was found inside the PDF.")
        else:
            st.success("Your CV looks solid with no major mistakes or missing basics.")
    else:
        if mistakes:
            st.markdown("**A. Mistakes to Fix**")
            for item in mistakes:
                st.markdown(
                    f"""
                    <div class="bf-item bf-item-error">
                        <div class="bf-item-head">
                            <span class="bf-badge-error">[Mistake to Fix]</span> {html.escape(item.heading)}
                        </div>
                        <div class="bf-line">{html.escape(item.explanation)}</div>
                        <div class="bf-line"><strong>Example in your CV:</strong> {html.escape(item.cv_example)}</div>
                        <div class="bf-line"><strong>What to do next:</strong> {html.escape(item.next_step)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        if optional_areas:
            st.markdown("**B. Areas You Can Improve**")
            for item in optional_areas:
                st.markdown(
                    f"""
                    <div class="bf-item bf-item-improve">
                        <div class="bf-item-head">
                            <span class="bf-badge-improve">[Area to Improve]</span> {html.escape(item.heading)}
                        </div>
                        <div class="bf-line">{html.escape(item.explanation)}</div>
                        <div class="bf-line"><strong>In your CV:</strong> {html.escape(item.cv_example)}</div>
                        <div class="bf-line"><strong>What to do next:</strong> {html.escape(item.next_step)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    # ------------------------------------------------------------------
    # 4. HOW TO IMPROVE YOUR CV (3-STEP PATTERN)
    # ------------------------------------------------------------------
    st.markdown('<div class="bf-section-title">4. How to Improve Your CV</div>', unsafe_allow_html=True)
    st.caption(
        "Mistakes to fix are shown first, followed by areas you can improve. "
        "Only add extra details if they are true for you."
    )

    if report.specific_corrections:
        for idx, corr in enumerate(report.specific_corrections, start=1):
            cls = "bf-item-error" if corr.is_error else "bf-item-improve"
            badge_cls = "bf-badge-error" if corr.is_error else "bf-badge-improve"
            badge_txt = "Mistake to Fix" if corr.is_error else "Area You Can Improve"
            st.markdown(
                f"""
                <div class="bf-item {cls}">
                    <div class="bf-item-head">
                        {idx}. {html.escape(corr.category_label)} &mdash;
                        <span class="{badge_cls}">{badge_txt}</span>
                    </div>
                    <div class="bf-compare-grid">
                        <div class="bf-step-box">
                            <div class="bf-step-label">STEP 1 &ndash; What is wrong?</div>
                            <div class="bf-step-text">{html.escape(corr.original_cv_example)}</div>
                            <div class="bf-step-note">{html.escape(corr.identified_problem)}</div>
                        </div>
                        <div class="bf-step-box-fix">
                            <div class="bf-step-label bf-step-label-fix">STEP 2 &ndash; How to fix it?</div>
                            <div class="bf-step-text">{html.escape(corr.recommended_improvement)}</div>
                        </div>
                    </div>
                    <div class="bf-step-reason">
                        <strong>STEP 3 &ndash; Why does this matter?</strong> {html.escape(corr.reason)}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.success("Great work — no specific wording mistakes or layout issues were found.")

    with st.expander("Good to Know", expanded=False):
        for lim in report.assessment_limitations:
            st.write(f"- {lim}")

    return dashboard_reset
