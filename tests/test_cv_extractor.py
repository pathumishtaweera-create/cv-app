"""
Multi-CV test suite for structured CV extraction and PDF document layout analysis.

Tests multiple synthetic in-memory PDF CVs:
1. Complete 2-page entry-level banking & finance graduate CV
2. Minimal / incomplete CV (missing sections, year-only dates, no assumed grades)
3. Two-column layout CV with overlapping/clipped text geometry
4. Scanned image-only PDF (verifies honest OCR-not-implemented notice)

Run with: python3 -m unittest discover -s tests -v
"""

import unittest
import pymupdf

from services.cv_extractor import extract_cv_information
from services.evaluator import run_foundation_analysis
from services.pdf_processor import process_pdf_bytes


def _build_multiline_pdf(pages_content: list[list[tuple[float, float, str, float, str]]]) -> bytes:
    """
    Create an in-memory multi-page PDF with explicit coordinates, font sizes, and fonts.
    Each item in pages_content[i] is (x, y, text, fontsize, fontname).
    """
    doc = pymupdf.open()
    for items in pages_content:
        page = doc.new_page(width=595, height=842)  # A4 Portrait
        for x, y, text, fontsize, fontname in items:
            page.insert_text((x, y), text, fontsize=fontsize, fontname=fontname)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _build_scanned_image_pdf() -> bytes:
    """Create a 1-page PDF containing only an embedded raster image and zero vector text."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200), False)
    pix.set_rect(pix.irect, (230, 235, 240))
    page.insert_image(pymupdf.Rect(50, 50, 500, 750), pixmap=pix)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestCVExtractionMultiSample(unittest.TestCase):
    """Validate structured CV extraction and PDF quality metrics across multiple CV styles."""

    def test_sample_1_complete_banking_graduate_cv(self) -> None:
        page1 = [
            (50, 50, "Nadeesha Perera", 18, "helv"),
            (50, 70, "Colombo, Sri Lanka | nadeesha.perera@example.com | +94 77 456 7890", 10, "helv"),
            (50, 105, "EDUCATION", 12, "hebo"),
            (50, 125, "B.Sc. (Hons) in Finance, University of Colombo (2020 - 2024)", 10, "helv"),
            (50, 140, "GPA: 3.68 / 4.00 - Second Class Upper Division", 10, "helv"),
            (50, 160, "G.C.E. A/L (2019) - Commerce Stream (Z-Score: 1.7240)", 10, "helv"),
            (60, 175, "Accounting - A, Economics - A, Business Studies - B, General English - B", 10, "helv"),
            (50, 195, "G.C.E. O/L (2016) - 8 A's, 1 B", 10, "helv"),
            (60, 210, "Mathematics - A, English - A", 10, "helv"),
            (50, 235, "PROFESSIONAL QUALIFICATIONS", 12, "hebo"),
            (50, 255, "CIMA Operational Level (Passed 3 subjects)", 10, "helv"),
            (50, 270, "IBSL Certificate in Banking and Finance (CBF)", 10, "helv"),
            (50, 300, "WORK EXPERIENCE", 12, "hebo"),
            (50, 320, "Banking Intern - Commercial Bank PLC | Jan 2024 - Jun 2024", 10, "hebo"),
            (60, 336, "• Assisted with KYC and AML customer due diligence checks for 25+ new accounts daily.", 10, "helv"),
            (60, 352, "• Supported retail banking operations, fixed deposits, and savings account onboarding.", 10, "helv"),
            (60, 368, "• Handled customer inquiries and prepared branch loan documentation.", 10, "helv"),
            (50, 392, "Audit Trainee - KPMG | Jul 2023 - Dec 2023", 10, "hebo"),
            (60, 408, "• Reconciled bank statements and verified financial statements using IFRS.", 10, "helv"),
            (60, 424, "• Built Excel Pivot Tables and VLOOKUP models, cutting reconciliation time by 20%.", 10, "helv"),
        ]
        page2 = [
            (50, 60, "TECHNICAL SKILLS", 12, "hebo"),
            (50, 80, "Microsoft Word, Microsoft Excel (VLOOKUP, Pivot Tables), Microsoft PowerPoint", 10, "helv"),
            (50, 96, "Accounting Software: QuickBooks, Sage 50 | Analytics: Power BI, SQL", 10, "helv"),
            (50, 126, "LANGUAGES", 12, "hebo"),
            (50, 146, "English - Fluent (Oral & Written), Sinhala - Native, Tamil - Conversational", 10, "helv"),
            (50, 176, "ACHIEVEMENTS & EXTRACURRICULAR ACTIVITIES", 12, "hebo"),
            (50, 196, "• Dean's List Award (2022 & 2023) for academic excellence.", 10, "helv"),
            (50, 212, "• President, University Finance & Investment Society; delivered weekly presentations.", 10, "helv"),
            (50, 228, "• Volunteer Treasurer, Rotaract Club; managed LKR 350,000 community budget.", 10, "helv"),
        ]
        pdf_bytes = _build_multiline_pdf([page1, page2])
        doc = process_pdf_bytes("nadeesha_perera_cv.pdf", pdf_bytes, "application/pdf")
        extracted = extract_cv_information(doc)

        # Document analysis assertions
        self.assertEqual(doc.page_count, 2)
        self.assertEqual(doc.document_analysis.page_dimensions[0].paper_size_label, "A4 Portrait")
        self.assertEqual(doc.document_analysis.primary_body_font_size_pt, 10.0)
        self.assertEqual(doc.document_analysis.largest_heading_font_size_pt, 18.0)

        # Personal & Contact
        self.assertEqual(extracted.personal_and_contact.candidate_name.value, "Nadeesha Perera")
        self.assertEqual(extracted.personal_and_contact.email_address.value, "nadeesha.perera@example.com")
        self.assertEqual(extracted.personal_and_contact.telephone_number.value, "+94 77 456 7890")
        self.assertEqual(extracted.personal_and_contact.location.value, "Colombo, Sri Lanka")

        # Education
        edu = extracted.educational_qualifications
        self.assertEqual(edu.gce_ol_results.status, "extracted")
        self.assertEqual(edu.gce_al_results.status, "extracted")
        self.assertIn("English - A", " ".join(edu.english_results.value))
        self.assertIn("Mathematics - A", " ".join(edu.mathematics_results.value))
        self.assertEqual(edu.degrees.status, "extracted")
        self.assertEqual(edu.professional_qualifications.status, "extracted")
        self.assertEqual(edu.banking_finance_qualifications.status, "extracted")

        # Experience
        exp = extracted.professional_experience
        self.assertEqual(len(exp.experience_entries.value), 2)
        self.assertEqual(len(exp.internship_details.value), 2)
        self.assertIn("12 months", exp.total_calculable_duration.value)

        # Technical skills (page 2)
        ts = extracted.technical_skills
        self.assertEqual(ts.microsoft_word.source_pages, (2,))
        self.assertIn(1, ts.microsoft_excel.source_pages)
        self.assertIn(2, ts.microsoft_excel.source_pages)
        self.assertEqual(ts.microsoft_powerpoint.status, "extracted")
        self.assertIn("QuickBooks", ts.accounting_software.value["matched_terms"])
        self.assertIn("Power BI", ts.other_technical_skills.value["matched_terms"])

        # Communication & languages
        cl = extracted.communication_and_languages
        self.assertEqual(cl.languages_and_proficiency.status, "extracted")
        self.assertEqual(len(cl.languages_and_proficiency.value), 3)
        self.assertEqual(cl.customer_service_experience.status, "extracted")
        self.assertEqual(cl.presentation_and_communication_evidence.status, "extracted")

        # Banking & finance knowledge
        bf = extracted.banking_and_finance_knowledge
        self.assertEqual(bf.accounting.status, "extracted")
        self.assertEqual(bf.banking_operations.status, "extracted")
        self.assertEqual(bf.loans_and_credit.status, "extracted")
        self.assertEqual(bf.deposits_and_savings.status, "extracted")
        self.assertEqual(bf.kyc_and_aml.status, "extracted")

        # Achievements
        ach = extracted.achievements
        self.assertEqual(ach.awards.status, "extracted")
        self.assertEqual(ach.academic_achievements.status, "extracted")
        self.assertEqual(ach.leadership_activities.status, "extracted")
        self.assertEqual(ach.volunteering.status, "extracted")
        self.assertEqual(ach.measurable_accomplishments.status, "extracted")

        # Serialization check
        serialized = extracted.to_dict()
        self.assertIn("personal_and_contact", serialized)
        self.assertFalse(serialized["is_scanned_pdf"])

    def test_sample_2_minimal_incomplete_cv_no_hallucination(self) -> None:
        page1 = [
            (50, 50, "Kasun Silva", 16, "helv"),
            (50, 70, "kasun.silva@mail.com", 10, "helv"),
            (50, 100, "EDUCATION", 12, "hebo"),
            (50, 120, "Diploma in Business Management, NIBM", 10, "helv"),
            (50, 140, "G.C.E. A/L Completed", 10, "helv"),
            (50, 170, "EXPERIENCE", 12, "hebo"),
            (50, 190, "Junior Clerk - ABC Holdings | 2023 - 2024", 10, "helv"),
            (60, 206, "• Handled filing and general office tasks.", 10, "helv"),
        ]
        pdf_bytes = _build_multiline_pdf([page1])
        doc = process_pdf_bytes("kasun_minimal.pdf", pdf_bytes, "application/pdf")
        extracted = extract_cv_information(doc)

        # Must not invent English/Math grades or O/L results or telephone/location
        self.assertEqual(extracted.personal_and_contact.telephone_number.status, "not_found")
        self.assertEqual(extracted.personal_and_contact.location.status, "not_found")
        self.assertEqual(extracted.educational_qualifications.gce_ol_results.status, "not_found")
        self.assertEqual(extracted.educational_qualifications.english_results.status, "not_found")
        self.assertEqual(extracted.educational_qualifications.mathematics_results.status, "not_found")
        self.assertEqual(extracted.educational_qualifications.diplomas.status, "extracted")
        # A/L mentioned without grades -> partial with uncertainty
        self.assertEqual(extracted.educational_qualifications.gce_al_results.status, "partial")
        self.assertIsNotNone(extracted.educational_qualifications.gce_al_results.uncertainty)

        # Year-only dates must not fabricate exact months
        self.assertEqual(extracted.professional_experience.total_calculable_duration.status, "not_found")
        self.assertIsNotNone(extracted.professional_experience.total_calculable_duration.uncertainty)

        # Missing sections detected
        self.assertIn("skills", extracted.missing_sections)
        self.assertIn("languages", extracted.missing_sections)

        # Must not assume English proficiency just because CV is written in English
        self.assertEqual(extracted.communication_and_languages.languages_and_proficiency.status, "not_found")

    def test_sample_3_two_column_and_overlapping_clipped_layout(self) -> None:
        # Left column x=40..250, Right column x=310..560, plus an overlapping line and clipped line
        page1 = [
            (40, 50, "Dilani Fernando", 17, "hebo"),
            (40, 70, "Kandy, Sri Lanka | dilani.f@example.com | 071 222 3344", 10, "helv"),
            # Left column
            (40, 110, "SKILLS", 12, "hebo"),
            (40, 128, "Microsoft Excel", 10, "helv"),
            (40, 144, "Computer Literacy", 10, "helv"),
            (40, 160, "Tally ERP", 10, "helv"),
            (40, 176, "Financial Compliance", 10, "helv"),
            (40, 192, "Regulatory Risk", 10, "helv"),
            # Right column
            (310, 110, "EXPERIENCE", 12, "hebo"),
            (310, 128, "Credit Analyst Intern - Sampath Bank | Feb 2024 - May 2024", 10, "helv"),
            (310, 144, "• Evaluated SME loans and credit risk.", 10, "helv"),
            (310, 160, "• Prepared credit appraisal memos.", 10, "helv"),
            (310, 176, "• Monitored collateral documentation.", 10, "helv"),
            (310, 192, "• Verified KYC compliance records.", 10, "helv"),
            # Deliberate overlapping line and clipped text beyond x=595
            (40, 193, "Overlapping test line", 10, "helv"),
            (540, 240, "Clipped text extending far beyond page right edge", 10, "helv"),
        ]
        pdf_bytes = _build_multiline_pdf([page1])
        doc = process_pdf_bytes("dilani_two_col.pdf", pdf_bytes, "application/pdf")
        extracted = extract_cv_information(doc)

        analysis = doc.document_analysis
        self.assertTrue(analysis.page_metrics[0].multi_column_suspected)
        self.assertGreater(analysis.total_overlapping_pairs, 0)
        self.assertGreater(analysis.total_clipped_lines, 0)
        self.assertTrue(len(extracted.unusual_layout_notes) > 0)

        self.assertEqual(extracted.personal_and_contact.candidate_name.value, "Dilani Fernando")
        self.assertEqual(extracted.banking_and_finance_knowledge.loans_and_credit.status, "extracted")
        self.assertEqual(extracted.banking_and_finance_knowledge.financial_compliance.status, "extracted")
        self.assertEqual(extracted.technical_skills.accounting_software.status, "extracted")

    def test_sample_4_scanned_image_pdf_reports_ocr_limitation(self) -> None:
        scanned_bytes = _build_scanned_image_pdf()
        doc = process_pdf_bytes("scanned_cv.pdf", scanned_bytes, "application/pdf")
        extracted = extract_cv_information(doc)
        eval_foundation = run_foundation_analysis(doc, extracted)

        self.assertTrue(doc.is_scanned_pdf)
        self.assertTrue(extracted.is_scanned_pdf)
        self.assertIsNotNone(extracted.ocr_notice)
        self.assertIn("OCR support is not currently implemented", extracted.ocr_notice)
        self.assertEqual(extracted.personal_and_contact.candidate_name.status, "not_extracted_ocr_required")
        self.assertIsNone(extracted.personal_and_contact.candidate_name.value)
        self.assertFalse(eval_foundation.is_assessable)


if __name__ == "__main__":
    unittest.main()
