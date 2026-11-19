"""
Entry point for the Banking & Finance CV Analyzer Streamlit application.

Coordinates the local workflow:
1. PDF upload & validation
2. In-memory PyMuPDF extraction & layout analysis
3. Deterministic 9-category evaluation
4. Simplified 4-section CV evaluation results dashboard & PDF report export
"""

import streamlit as st

from config.settings import APP_NAME
from services.cv_extractor import ExtractedCVData, extract_cv_information
from services.evaluator import evaluate_cv
from services.pdf_processor import (
    PDFProcessingError,
    ProcessedPDFDocument,
    process_pdf_bytes,
)
from services.report_service import (
    CVEvaluationReport,
    build_evaluation_report,
    generate_pdf_report_bytes,
)
from ui.components import (
    render_analyze_controls,
    render_document_preview,
    render_header,
    render_results_dashboard,
    render_upload_section,
)
from ui.styles import inject_custom_css


def _initialize_session_state() -> None:
    """Ensure required session keys exist for tracking the active upload in memory."""
    defaults = {
        "uploader_nonce": 0,
        "active_file_signature": None,
        "processed_document": None,
        "extracted_cv": None,
        "evaluation_report": None,
        "pdf_report_bytes": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _reset_session_for_new_cv() -> None:
    """Clear active CV and evaluation state and rotate the uploader key."""
    st.session_state["uploader_nonce"] += 1
    st.session_state["active_file_signature"] = None
    st.session_state["processed_document"] = None
    st.session_state["extracted_cv"] = None
    st.session_state["evaluation_report"] = None
    st.session_state["pdf_report_bytes"] = None


def main() -> None:
    """Configure and render the Banking & Finance CV Analyzer application."""
    st.set_page_config(
        page_title=APP_NAME,
        page_icon="📊",
        layout="centered",
        initial_sidebar_state="collapsed",
    )

    inject_custom_css()
    _initialize_session_state()
    render_header()

    uploader_key = f"cv_pdf_uploader_{st.session_state['uploader_nonce']}"
    uploaded_file = render_upload_section(uploader_key=uploader_key)

    processed_doc: ProcessedPDFDocument | None = None
    extracted_cv: ExtractedCVData | None = None
    upload_error: str | None = None

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        file_signature = (uploaded_file.name, len(file_bytes))

        if st.session_state["active_file_signature"] != file_signature:
            st.session_state["active_file_signature"] = file_signature
            st.session_state["evaluation_report"] = None
            st.session_state["pdf_report_bytes"] = None
            st.session_state["processed_document"] = None
            st.session_state["extracted_cv"] = None

            with st.spinner("Validating PDF and extracting CV information..."):
                try:
                    processed_doc = process_pdf_bytes(
                        filename=uploaded_file.name,
                        file_bytes=file_bytes,
                        mime_type=getattr(uploaded_file, "type", None),
                    )
                    extracted_cv = extract_cv_information(processed_doc)
                    st.session_state["processed_document"] = processed_doc
                    st.session_state["extracted_cv"] = extracted_cv
                except PDFProcessingError as exc:
                    upload_error = str(exc)
                except Exception:
                    upload_error = (
                        "An unexpected error occurred while processing the uploaded PDF. "
                        "Please verify the file and try again."
                    )
        else:
            processed_doc = st.session_state["processed_document"]
            extracted_cv = st.session_state["extracted_cv"]

        if upload_error:
            st.error(upload_error)
        elif processed_doc is not None:
            st.success(f"PDF ready: {processed_doc.filename}")
            render_document_preview(processed_doc)
        else:
            try:
                process_pdf_bytes(
                    filename=uploaded_file.name,
                    file_bytes=file_bytes,
                    mime_type=getattr(uploaded_file, "type", None),
                )
            except PDFProcessingError as exc:
                st.error(str(exc))
    else:
        st.session_state["active_file_signature"] = None
        st.session_state["processed_document"] = None
        st.session_state["extracted_cv"] = None
        st.session_state["evaluation_report"] = None
        st.session_state["pdf_report_bytes"] = None

    current_doc: ProcessedPDFDocument | None = st.session_state.get("processed_document")
    current_extracted: ExtractedCVData | None = st.session_state.get("extracted_cv")
    active_report: CVEvaluationReport | None = st.session_state.get("evaluation_report")

    analyze_clicked, top_reset_clicked = render_analyze_controls(
        document=current_doc,
        has_report=(active_report is not None),
    )

    if top_reset_clicked:
        _reset_session_for_new_cv()
        st.rerun()

    if analyze_clicked and current_doc is not None and current_extracted is not None:
        with st.spinner("Evaluating CV across nine banking & finance categories..."):
            eval_result = evaluate_cv(current_doc, current_extracted)
            report_obj = build_evaluation_report(current_doc, current_extracted, eval_result)
            pdf_bytes = generate_pdf_report_bytes(report_obj)
            st.session_state["evaluation_report"] = report_obj
            st.session_state["pdf_report_bytes"] = pdf_bytes
        st.rerun()

    active_report = st.session_state.get("evaluation_report")
    active_pdf_bytes: bytes | None = st.session_state.get("pdf_report_bytes")
    if active_report is not None and active_pdf_bytes is not None:
        dashboard_reset = render_results_dashboard(active_report, active_pdf_bytes)
        if dashboard_reset:
            _reset_session_for_new_cv()
            st.rerun()


if __name__ == "__main__":
    main()
