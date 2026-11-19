"""
End-to-end tests for the user-friendly 4-section CV report:
1. Your CV Score
2. What You Did Well
3. What Needs Improvement (Mistakes to Fix vs. Areas You Can Improve)
4. How to Improve Your CV (STEP 1 / STEP 2 / STEP 3)

Tests Weak, Average, and Strong sample CVs plus a scanned PDF, and verifies that
technical jargon and internal measurements are translated into simple everyday English.
Run with: python3 -m unittest discover -s tests -v
"""

import unicodedata
import unittest
import pymupdf

from config.settings import APP_NAME
from services.cv_extractor import extract_cv_information
from services.evaluator import evaluate_cv
from services.pdf_processor import process_pdf_bytes
from services.report_service import (
    SCORE_ABOVE_BENCHMARK_NOTE,
    SCORE_BENCHMARK_CLARIFICATION,
    build_evaluation_report,
    classify_cv_score,
    generate_pdf_report_bytes,
)


def _build_pdf(pages_content: list[list[tuple[float, float, str, float, str]]]) -> bytes:
    """Create an in-memory PDF with explicit coordinates and fonts."""
    doc = pymupdf.open()
    for items in pages_content:
        page = doc.new_page(width=595, height=842)
        for x, y, text, fontsize, fontname in items:
            page.insert_text((x, y), text, fontsize=fontsize, fontname=fontname)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _build_scanned_pdf() -> bytes:
    """Create a PDF containing only a raster image and no selectable vector text."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 120, 120), False)
    pix.set_rect(pix.irect, (230, 230, 230))
    page.insert_image(pymupdf.Rect(50, 50, 500, 700), pixmap=pix)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _sample_weak_cv_bytes() -> bytes:
    page1 = [
        (50, 50, "Kasun Perera", 12, "helv"),
        (50, 68, "kasun@example.com", 10, "helv"),
        (50, 100, "EDUCATION", 11, "helv"),
        (50, 118, "Completed school education in 2021.", 10, "helv"),
        (50, 145, "SKILLS", 11, "helv"),
        (50, 163, "KYC, AML, Excel", 10, "helv"),
        (50, 190, "EXPERIENCE", 11, "helv"),
        (50, 191, "Overlapping header note", 10, "helv"),
        (50, 212, "Trainee - Local Shop | 2023 - 2024", 10, "helv"),
        (50, 230, "• Responsible for daily duties and helped with the the finacial reconcilation as a intern.", 10, "helv"),
        (540, 250, "Clipped note extending past the right page edge", 10, "helv"),
    ]
    return _build_pdf([page1])


def _sample_average_cv_bytes() -> bytes:
    page1 = [
        (50, 50, "Nadeesha Silva", 16, "hebo"),
        (50, 70, "Kandy, Sri Lanka | nadeesha.silva@example.com | +94 71 222 3344", 10, "helv"),
        (50, 105, "EDUCATION", 12, "hebo"),
        (50, 125, "Bachelor of Business Administration, University of Peradeniya (2020 - 2024)", 10, "helv"),
        (50, 142, "G.C.E. A/L (2019) - Economics - B, Accounting - B, Business Studies - C, General English - B", 10, "helv"),
        (50, 159, "G.C.E. O/L (2016) - Mathematics - B, English - B", 10, "helv"),
        (50, 189, "EXPERIENCE", 12, "hebo"),
        (50, 209, "Customer Service Assistant - Metro Retail | Jan 2024 - Jun 2024", 10, "hebo"),
        (60, 226, "• Assisted customers with billing inquiries, cash register balancing, and daily sales logs.", 10, "helv"),
        (60, 243, "• Prepared weekly inventory summaries using Microsoft Excel and Microsoft Word.", 10, "helv"),
        (50, 273, "TECHNICAL SKILLS", 12, "hebo"),
        (50, 291, "Microsoft Excel, Microsoft Word, PowerPoint, Data Entry", 10, "helv"),
        (50, 321, "LANGUAGES", 12, "hebo"),
        (50, 339, "English - Good, Sinhala - Native", 10, "helv"),
    ]
    return _build_pdf([page1])


def _sample_strong_cv_bytes() -> bytes:
    page1 = [
        (50, 50, "Amaya Jayasinghe", 18, "hebo"),
        (50, 70, "Colombo, Sri Lanka | amaya.j@example.com | +94 77 111 2233", 10, "helv"),
        (50, 102, "PROFILE", 12, "hebo"),
        (50, 120, "First Class Finance graduate with 12 months of commercial banking internship experience in KYC, AML, and credit operations.", 10, "helv"),
        (50, 150, "EDUCATION", 12, "hebo"),
        (50, 168, "B.Sc. (Hons) Finance, University of Colombo (2020 - 2024)", 10, "helv"),
        (50, 184, "First Class Honours, GPA: 3.85 / 4.00", 10, "helv"),
        (50, 200, "G.C.E. A/L (2019) - Accounting - A, Economics - A, Business Studies - A, General English - A", 10, "helv"),
        (50, 216, "G.C.E. O/L (2016) - 9 A's including Mathematics - A, English - A", 10, "helv"),
        (50, 232, "IBSL Diploma in Applied Banking and Finance (DABF) & CIMA Managerial Level", 10, "helv"),
        (50, 262, "WORK EXPERIENCE", 12, "hebo"),
        (50, 280, "Banking Intern - Commercial Bank PLC | Jan 2024 - Dec 2024", 10, "hebo"),
        (60, 297, "• Performed KYC and AML customer due diligence checks for 35+ new savings accounts daily.", 10, "helv"),
        (60, 314, "• Assisted branch banking operations, fixed deposits, cheque clearing, and SME credit analysis.", 10, "helv"),
        (60, 331, "• Reconciled daily teller cash balances and prepared Excel Pivot Tables and VLOOKUP reports.", 10, "helv"),
        (50, 361, "TECHNICAL SKILLS", 12, "hebo"),
        (50, 379, "Microsoft Excel (Pivot Tables, VLOOKUP, Financial Modeling), Microsoft Word, PowerPoint, QuickBooks, Finacle", 10, "helv"),
        (50, 409, "LANGUAGES", 12, "hebo"),
        (50, 427, "English - Fluent (Oral & Written), Sinhala - Native, Tamil - Conversational", 10, "helv"),
        (50, 457, "ACHIEVEMENTS", 12, "hebo"),
        (50, 475, "• Dean's List Award (2022, 2023); President of Finance Society; led 4 client presentations.", 10, "helv"),
        (50, 492, "• Reduced monthly reconciliation variance by 25% across LKR 2,000,000 portfolio and volunteered in financial literacy workshops.", 10, "helv"),
    ]
    return _build_pdf([page1])


class TestUserFriendlyReport(unittest.TestCase):
    """Verify plain-English report wording, grouping, 3-step format, and PDF export."""

    def test_score_classification_bands(self) -> None:
        self.assertEqual(classify_cv_score(92.0, True)[0], "Outstanding CV")
        self.assertEqual(classify_cv_score(84.5, True)[0], "Very Good CV")
        self.assertEqual(classify_cv_score(73.0, True)[0], "Good CV")
        self.assertEqual(classify_cv_score(64.0, True)[0], "Average CV")
        self.assertEqual(classify_cv_score(55.0, True)[0], "Below Average CV")
        self.assertEqual(classify_cv_score(42.0, True)[0], "Needs Significant Improvement")
        self.assertEqual(classify_cv_score(0.0, False)[0], "Not Assessable (Scanned PDF)")

    def test_weak_average_strong_cvs_plain_english_report(self) -> None:
        reports = {}
        for tier, filename, raw_bytes in (
            ("weak", "kasun_weak.pdf", _sample_weak_cv_bytes()),
            ("average", "nadeesha_average.pdf", _sample_average_cv_bytes()),
            ("strong", "amaya_strong.pdf", _sample_strong_cv_bytes()),
        ):
            doc = process_pdf_bytes(filename, raw_bytes, "application/pdf")
            ext = extract_cv_information(doc)
            ev = evaluate_cv(doc, ext)
            rep = build_evaluation_report(doc, ext, ev)
            pdf_out = generate_pdf_report_bytes(rep)
            reports[tier] = (rep, ev, pdf_out)

        weak_rep, weak_ev, weak_pdf = reports["weak"]
        avg_rep, avg_ev, _ = reports["average"]
        strong_rep, strong_ev, strong_pdf = reports["strong"]

        # Underlying 9-category scores unchanged and ordered Weak < Average < Strong
        self.assertEqual(weak_rep.overall_score, weak_ev.overall_score)
        self.assertEqual(avg_rep.overall_score, avg_ev.overall_score)
        self.assertEqual(strong_rep.overall_score, strong_ev.overall_score)
        self.assertLess(weak_rep.overall_score, avg_rep.overall_score)
        self.assertLess(avg_rep.overall_score, strong_rep.overall_score)

        # Verify zero technical jargon leaks into any user-facing text
        forbidden_jargon = (
            "bounding box",
            "bounding-box",
            "ats parser",
            "boilerplate",
            "assessable factors",
            "overlapping pairs:",
            "clipped lines:",
            "l/r/t/b",
            "median line gap",
            "typographic size hierarchy",
            "action-verb line",
        )
        for rep in (weak_rep, avg_rep, strong_rep):
            combined_text = " ".join(
                [
                    rep.overall_explanation,
                    rep.score_interpretation_title,
                    rep.score_interpretation_note,
                    rep.score_benchmark_clarification,
                    rep.disclaimer,
                ]
                + [f"{s.title} {s.evidence} {s.why_it_helps}" for s in rep.whats_good]
                + [f"{w.heading} {w.explanation} {w.cv_example} {w.next_step}" for w in rep.what_needs_improvement]
                + [
                    f"{c.category_label} {c.original_cv_example} {c.identified_problem} {c.recommended_improvement} {c.reason}"
                    for c in rep.specific_corrections
                ]
            ).lower()
            for term in forbidden_jargon:
                self.assertNotIn(term, combined_text)

        # Verify 60%+ benchmark note and <60% improvement note
        self.assertLess(weak_rep.overall_score, 60.0)
        self.assertGreaterEqual(avg_rep.overall_score, 60.0)
        self.assertGreaterEqual(strong_rep.overall_score, 60.0)

        self.assertEqual(avg_rep.score_interpretation_note, SCORE_ABOVE_BENCHMARK_NOTE)
        self.assertEqual(strong_rep.score_interpretation_note, SCORE_ABOVE_BENCHMARK_NOTE)
        self.assertEqual(avg_rep.score_benchmark_clarification, SCORE_BENCHMARK_CLARIFICATION)
        self.assertEqual(strong_rep.score_benchmark_clarification, SCORE_BENCHMARK_CLARIFICATION)

        self.assertIn("needs further improvement", weak_rep.score_interpretation_note.lower())
        self.assertIn("never guaranteed", weak_rep.score_interpretation_note.lower())
        self.assertIn("suggested cv-quality benchmark", weak_rep.score_benchmark_clarification.lower())
        self.assertIn("not an official banking-industry requirement", weak_rep.score_benchmark_clarification.lower())

        # Section 3 combines formatting improvements under one heading and separates Mistakes vs Areas to Improve
        weak_headings = [w.heading for w in weak_rep.what_needs_improvement]
        self.assertEqual(weak_headings.count("Improve your CV formatting"), 1)
        # Missing Excel is an Area to Improve, NOT a mistake
        excel_items = [w for w in weak_rep.what_needs_improvement if "excel" in w.heading.lower()]
        self.assertTrue(excel_items and not excel_items[0].is_error)
        # Spelling/grammar and overlapping text ARE Mistakes to Fix
        lang_items = [w for w in weak_rep.what_needs_improvement if "spelling" in w.heading.lower()]
        self.assertTrue(lang_items and lang_items[0].is_error)

        # Section 4 lists Mistakes first, quotes actual CV lines, and keeps UK English intact
        error_flags = [c.is_error for c in weak_rep.specific_corrections]
        self.assertTrue(error_flags[0])
        if False in error_flags:
            self.assertNotIn(True, error_flags[error_flags.index(False):])

        weak_orig_all = " ".join(c.original_cv_example for c in weak_rep.specific_corrections)
        weak_fix_all = " ".join(c.recommended_improvement for c in weak_rep.specific_corrections)
        self.assertIn("finacial reconcilation", weak_orig_all)
        self.assertIn("financial reconciliation", weak_fix_all)
        self.assertIn("an intern", weak_fix_all)
        self.assertIn("Trainee - Local Shop | 2023 - 2024", weak_orig_all)
        self.assertIn("Clipped note extending past", weak_orig_all)

        strong_orig_all = " ".join(c.original_cv_example for c in strong_rep.specific_corrections).lower()
        self.assertNotIn("honours", strong_orig_all)
        self.assertNotIn("cheque", strong_orig_all)

        # Exported PDF contains all 4 plain-English headings and STEP 1/2/3 structure
        for rep, _, pdf_bytes in ((weak_rep, weak_ev, weak_pdf), (strong_rep, strong_ev, strong_pdf)):
            self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
            parsed = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            try:
                self.assertGreaterEqual(parsed.page_count, 1)
                full_text = unicodedata.normalize("NFKC", "\n".join(p.get_text("text") for p in parsed))
            finally:
                parsed.close()

            self.assertIn(APP_NAME, full_text)
            self.assertIn("1. Your CV Score", full_text)
            self.assertIn("2. What You Did Well", full_text)
            self.assertIn("3. What Needs Improvement", full_text)
            self.assertIn("4. How to Improve Your CV", full_text)
            self.assertIn("suggested CV-quality benchmark", full_text)
            if rep.overall_score >= 60.0:
                self.assertIn("good starting level for applying for jobs", full_text)
            else:
                self.assertIn("needs further improvement", full_text)
            if rep.specific_corrections:
                self.assertIn("STEP 1", full_text)
                self.assertIn("STEP 2", full_text)
                self.assertIn("STEP 3", full_text)

    def test_scanned_pdf_handled_in_simple_english(self) -> None:
        raw_bytes = _build_scanned_pdf()
        doc = process_pdf_bytes("scanned_cv.pdf", raw_bytes, "application/pdf")
        ext = extract_cv_information(doc)
        ev = evaluate_cv(doc, ext)
        rep = build_evaluation_report(doc, ext, ev)
        pdf_bytes = generate_pdf_report_bytes(rep)

        self.assertEqual(rep.overall_score, 0.0)
        self.assertEqual(rep.classification, "Not Assessable (Scanned PDF)")
        self.assertEqual(len(rep.whats_good), 0)
        self.assertEqual(len(rep.specific_corrections), 1)
        self.assertIn("scanned", rep.overall_explanation.lower())
        self.assertIn("never guaranteed", rep.score_interpretation_note.lower())
        self.assertEqual(rep.score_benchmark_clarification, SCORE_BENCHMARK_CLARIFICATION)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
