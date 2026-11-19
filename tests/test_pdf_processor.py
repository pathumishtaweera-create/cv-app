"""
Unit tests for local PDF validation, PyMuPDF extraction, and evaluation foundation.

Run with: python3 -m unittest discover -s tests
"""

import unittest
import pymupdf

from config.settings import EVALUATION_CATEGORIES, MAX_FILE_SIZE_BYTES
from services.evaluator import run_foundation_analysis
from services.pdf_processor import (
    CorruptedPDFError,
    EmptyFileError,
    FileSizeExceededError,
    PasswordProtectedPDFError,
    UnsupportedFileTypeError,
    process_pdf_bytes,
)


def _create_sample_pdf_bytes(text: str = "Jane Doe\nInvestment Banking Analyst CV", password: str | None = None) -> bytes:
    """Create a valid PDF in memory for testing without touching disk."""
    doc = pymupdf.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 72), text)
    doc.set_metadata({"title": "Candidate CV", "author": "Jane Doe"})

    if password:
        pdf_bytes = doc.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw=password,
            owner_pw=password + "_owner",
            permissions=pymupdf.PDF_PERM_ACCESSIBILITY,
        )
    else:
        pdf_bytes = doc.tobytes()

    doc.close()
    return pdf_bytes


class TestPDFProcessor(unittest.TestCase):
    """Verify all required upload security, validation, and extraction rules."""

    def test_valid_pdf_extraction(self) -> None:
        pdf_bytes = _create_sample_pdf_bytes(
            "Alex Morgan\nBSc Finance & Economics\nSummer Investment Banking Intern"
        )
        result = process_pdf_bytes("alex_morgan_cv.pdf", pdf_bytes, "application/pdf")

        self.assertEqual(result.filename, "alex_morgan_cv.pdf")
        self.assertEqual(result.page_count, 1)
        self.assertTrue(result.has_extractable_text)
        self.assertGreater(result.word_count, 5)
        self.assertIn("Investment Banking", result.extracted_text)
        self.assertEqual(result.pdf_title, "Candidate CV")
        self.assertEqual(result.pdf_author, "Jane Doe")
        self.assertIsNotNone(result.first_page_preview_png)

        eval_result = run_foundation_analysis(result)
        self.assertTrue(eval_result.is_assessable)
        self.assertEqual(eval_result.total_possible_score, 100)
        self.assertEqual(len(eval_result.categories), 9)

    def test_reject_unsupported_extension(self) -> None:
        with self.assertRaises(UnsupportedFileTypeError):
            process_pdf_bytes("resume.docx", b"not a pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    def test_reject_empty_file(self) -> None:
        with self.assertRaises(EmptyFileError):
            process_pdf_bytes("empty.pdf", b"", "application/pdf")

    def test_reject_oversized_file(self) -> None:
        oversized = b"%PDF-1.4\n" + (b"0" * MAX_FILE_SIZE_BYTES)
        with self.assertRaises(FileSizeExceededError):
            process_pdf_bytes("large_cv.pdf", oversized, "application/pdf")

    def test_reject_renamed_non_pdf_file(self) -> None:
        with self.assertRaises(UnsupportedFileTypeError):
            process_pdf_bytes("fake_cv.pdf", b"Plain text disguised as a PDF", "application/pdf")

    def test_reject_corrupted_pdf(self) -> None:
        with self.assertRaises(CorruptedPDFError):
            process_pdf_bytes("broken.pdf", b"%PDF-1.4\n%%corrupted_binary_garbage", "application/pdf")

    def test_reject_password_protected_pdf(self) -> None:
        encrypted_bytes = _create_sample_pdf_bytes("Confidential CV", password="secret123")
        with self.assertRaises(PasswordProtectedPDFError):
            process_pdf_bytes("protected_cv.pdf", encrypted_bytes, "application/pdf")

    def test_blank_text_pdf_warns_gracefully(self) -> None:
        blank_pdf = _create_sample_pdf_bytes(text="")
        result = process_pdf_bytes("scanned_cv.pdf", blank_pdf, "application/pdf")
        self.assertFalse(result.has_extractable_text)
        self.assertEqual(result.word_count, 0)

        eval_result = run_foundation_analysis(result)
        self.assertFalse(eval_result.is_assessable)
        self.assertIsNotNone(eval_result.coverage_warning)

    def test_nine_categories_sum_to_100(self) -> None:
        self.assertEqual(len(EVALUATION_CATEGORIES), 9)
        self.assertEqual(sum(c.max_points for c in EVALUATION_CATEGORIES), 100)


if __name__ == "__main__":
    unittest.main()
