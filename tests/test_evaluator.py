"""
Comprehensive tests for the 9-category rule-based Banking & Finance CV Evaluation Engine.

Run with: python3 -m unittest discover -s tests -v
"""

import unittest
import pymupdf

from config.settings import EVALUATION_CATEGORIES
from services.evaluator import (
    STATUS_CANNOT_ASSESS,
    STATUS_EVALUATED,
    STATUS_NOT_MENTIONED,
    evaluate_cv,
)
from services.pdf_processor import process_pdf_bytes


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


class TestEvaluationEngine(unittest.TestCase):
    """Verify exact weights, scoring math, determinism, missing-data handling, and domain rules."""

    def test_exact_category_weights_sum_to_100(self) -> None:
        expected = [
            ("educational_qualifications", 20),
            ("professional_experience", 15),
            ("technical_computer_skills", 10),
            ("communication_language_skills", 10),
            ("banking_finance_knowledge", 10),
            ("achievements_extracurricular", 5),
            ("cv_structure_organization", 10),
            ("language_writing_quality", 10),
            ("visual_presentation_formatting", 10),
        ]
        self.assertEqual([(c.key, c.max_points) for c in EVALUATION_CATEGORIES], expected)
        self.assertEqual(sum(c.max_points for c in EVALUATION_CATEGORIES), 100)

    def test_strong_banking_cv_scores_consistently_and_within_bounds(self) -> None:
        page1 = [
            (50, 50, "Amaya Jayasinghe", 18, "hebo"),
            (50, 70, "Colombo, Sri Lanka | amaya.j@example.com | +94 77 111 2233", 10, "helv"),
            (50, 105, "EDUCATION", 12, "hebo"),
            (50, 125, "B.Sc. (Hons) Finance, University of Colombo (2020 - 2024)", 10, "helv"),
            (50, 140, "First Class Honours, GPA: 3.82 / 4.00", 10, "helv"),
            (50, 160, "G.C.E. A/L (2019) - Accounting - A, Economics - A, Business Studies - A, General English - A", 10, "helv"),
            (50, 178, "G.C.E. O/L (2016) - 9 A's including Mathematics - A, English - A", 10, "helv"),
            (50, 200, "IBSL Diploma in Applied Banking and Finance (DABF) & CIMA Managerial Level", 10, "helv"),
            (50, 230, "WORK EXPERIENCE", 12, "hebo"),
            (50, 250, "Banking Intern - Commercial Bank PLC | Jan 2024 - Dec 2024", 10, "hebo"),
            (60, 266, "• Performed KYC and AML customer due diligence checks for 30+ new savings accounts daily.", 10, "helv"),
            (60, 282, "• Assisted branch banking operations, fixed deposits, and SME credit analysis.", 10, "helv"),
            (60, 298, "• Reconciled daily teller cash balances and prepared Excel Pivot Tables reports.", 10, "helv"),
            (50, 328, "TECHNICAL SKILLS", 12, "hebo"),
            (50, 346, "Microsoft Excel (Pivot Tables, VLOOKUP, Financial Modeling), Microsoft Word, PowerPoint, QuickBooks, Finacle", 10, "helv"),
            (50, 376, "LANGUAGES", 12, "hebo"),
            (50, 394, "English - Fluent (Oral & Written), Sinhala - Native, Tamil - Conversational", 10, "helv"),
            (50, 424, "ACHIEVEMENTS", 12, "hebo"),
            (50, 442, "• Dean's List Award (2022, 2023); President of Finance Society; led 3 client presentations.", 10, "helv"),
            (50, 458, "• Reduced monthly reconciliation variance by 25% across LKR 2,000,000 portfolio.", 10, "helv"),
        ]
        pdf_bytes = _build_pdf([page1])
        doc = process_pdf_bytes("amaya_strong_cv.pdf", pdf_bytes, "application/pdf")

        res1 = evaluate_cv(doc)
        res2 = evaluate_cv(doc)

        # Determinism check: identical inputs -> identical outputs
        self.assertEqual(res1.to_dict(), res2.to_dict())

        self.assertTrue(res1.is_assessable)
        self.assertGreater(res1.overall_score, 70.0)
        self.assertLessEqual(res1.overall_score, 100.0)
        self.assertAlmostEqual(
            res1.overall_score,
            round(res1.candidate_capability_score + res1.document_presentation_score, 2),
            places=1,
        )

        for cat_eval in res1.categories:
            self.assertGreaterEqual(cat_eval.category_score, 0.0)
            self.assertLessEqual(cat_eval.category_score, float(cat_eval.max_weight))
            for f in cat_eval.factors:
                if f.status == STATUS_EVALUATED:
                    self.assertIsNotNone(f.score)
                    self.assertGreaterEqual(f.score, 0)
                    self.assertLessEqual(f.score, 5)
                else:
                    self.assertIsNone(f.score)

            # Verify weighted formula on evaluated categories
            if cat_eval.assessed_factor_count > 0 and cat_eval.average_factor_score is not None:
                expected_score = round((cat_eval.average_factor_score / 5.0) * cat_eval.max_weight, 2)
                self.assertAlmostEqual(cat_eval.category_score, expected_score, places=2)

    def test_missing_information_is_not_zeroed_and_weights_not_redistributed(self) -> None:
        # Sparse CV with NO Experience, NO Banking Knowledge, NO Achievements, NO Languages
        page1 = [
            (50, 50, "Nimal Bandara", 16, "helv"),
            (50, 70, "nimal@example.com", 10, "helv"),
            (50, 105, "EDUCATION", 12, "hebo"),
            (50, 125, "Diploma in Business Studies, NIBM", 10, "helv"),
            (50, 155, "TECHNICAL SKILLS", 12, "hebo"),
            (50, 175, "Microsoft Excel", 10, "helv"),
        ]
        pdf_bytes = _build_pdf([page1])
        doc = process_pdf_bytes("nimal_sparse.pdf", pdf_bytes, "application/pdf")
        res = evaluate_cv(doc)

        cat_by_key = {c.category.key: c for c in res.categories}

        # Category 2 (Experience), Category 4 (Communication), Category 5 (Banking), Category 6 (Achievements)
        # must be Unavailable (0 score, weight NOT redistributed) rather than penalized with 0-scored factors
        for unavail_key in ("professional_experience", "communication_language_skills", "banking_finance_knowledge", "achievements_extracurricular"):
            c = cat_by_key[unavail_key]
            self.assertEqual(c.status, "Unavailable")
            self.assertEqual(c.category_score, 0.0)
            self.assertIsNone(c.average_factor_score)
            for f in c.factors:
                self.assertEqual(f.status, STATUS_NOT_MENTIONED)

        # Low coverage warning must be disclosed
        self.assertIsNotNone(res.coverage_warning)
        self.assertLess(res.overall_coverage_pct, 50.0)

        # Education: Diploma only must NOT be penalized as 0, and must NOT be scored 5 like a First Class degree
        edu_factors = {f.factor_name: f for f in cat_by_key["educational_qualifications"].factors}
        self.assertEqual(edu_factors["Degrees and Diplomas"].status, STATUS_EVALUATED)
        self.assertEqual(edu_factors["Degrees and Diplomas"].score, 3)
        self.assertIn("diploma", edu_factors["Degrees and Diplomas"].explanation.lower())
        self.assertEqual(edu_factors["O/L Results"].status, STATUS_NOT_MENTIONED)

        # Technical skills: bare "Microsoft Excel" must NOT assume advanced skill (must score 3, not 5)
        tech_factors = {f.factor_name: f for f in cat_by_key["technical_computer_skills"].factors}
        self.assertEqual(tech_factors["Microsoft Excel"].score, 3)

    def test_language_quality_catches_actual_errors_and_preserves_uk_us_variants(self) -> None:
        page1 = [
            (50, 50, "Rohan Fernando", 16, "hebo"),
            (50, 70, "rohan@example.com", 10, "helv"),
            (50, 100, "EXPERIENCE", 12, "hebo"),
            (50, 120, "Audit Trainee - ABC Associates | Jan 2024 - Jun 2024", 10, "helv"),
            # Contains UK English variants ("honours", "analyse", "cheque", "organisation") which MUST NOT be flagged,
            # PLUS actual spelling/grammar/repeated-word errors which MUST be caught with corrections.
            (50, 138, "• Graduated with First Class honours and helped the organisation analyse cheque clearing.", 10, "helv"),
            (50, 156, "• Gained experiance as a intern handling the the finacial reconcilation.", 10, "helv"),
        ]
        pdf_bytes = _build_pdf([page1])
        doc = process_pdf_bytes("rohan_lang_test.pdf", pdf_bytes, "application/pdf")
        res = evaluate_cv(doc)

        cat8 = next(c for c in res.categories if c.category.key == "language_writing_quality")
        f8 = {f.factor_name: f for f in cat8.factors}

        # Actual errors caught with corrections
        spelling_ev = " ".join(f8["Spelling"].evidence)
        self.assertIn("'experiance' -> 'experience'", spelling_ev)
        self.assertIn("'finacial' -> 'financial'", spelling_ev)
        self.assertIn("'reconcilation' -> 'reconciliation'", spelling_ev)
        # Valid UK variants must NOT appear as misspellings
        for valid_uk in ("honours", "organisation", "analyse", "cheque"):
            self.assertNotIn(valid_uk, spelling_ev.lower())

        grammar_ev = " ".join(f8["Grammar"].evidence)
        self.assertIn("'a intern' -> 'an intern'", grammar_ev)

        rep_ev = " ".join(f8["Repeated Words"].evidence)
        self.assertIn("'the the' -> 'the'", rep_ev)

    def test_unsupported_banking_claim_vs_demonstrated_knowledge(self) -> None:
        # Bare buzzwords in Skills without experience or qualifications should score 2 ("unsupported claim")
        page1 = [
            (50, 50, "Sahan Perera", 16, "hebo"),
            (50, 70, "sahan@example.com", 10, "helv"),
            (50, 100, "SKILLS", 12, "hebo"),
            (50, 120, "KYC, AML, Credit Analysis, Banking Operations", 10, "helv"),
        ]
        pdf_bytes = _build_pdf([page1])
        doc = process_pdf_bytes("sahan_claims.pdf", pdf_bytes, "application/pdf")
        res = evaluate_cv(doc)

        cat5 = next(c for c in res.categories if c.category.key == "banking_finance_knowledge")
        f5 = {f.factor_name: f for f in cat5.factors}
        self.assertEqual(f5["KYC and AML Awareness"].score, 2)
        self.assertIn("without supporting", f5["KYC and AML Awareness"].explanation.lower())

    def test_visual_overlap_and_clipping_penalize_category_9(self) -> None:
        page1 = [
            (50, 50, "Dilani Silva", 16, "hebo"),
            (50, 70, "dilani@example.com", 10, "helv"),
            (50, 110, "Line one overlapping", 10, "helv"),
            (50, 111, "Line two overlapping", 10, "helv"),
            (540, 140, "Clipped text extending far outside the right page boundary", 10, "helv"),
        ]
        pdf_bytes = _build_pdf([page1])
        doc = process_pdf_bytes("dilani_overlap.pdf", pdf_bytes, "application/pdf")
        res = evaluate_cv(doc)

        cat9 = next(c for c in res.categories if c.category.key == "visual_presentation_formatting")
        f9 = {f.factor_name: f for f in cat9.factors}
        self.assertLessEqual(f9["Text Overlap"].score, 3)

    def test_year_only_experience_marks_duration_cannot_be_assessed(self) -> None:
        page1 = [
            (50, 50, "Ruwan Costa", 16, "hebo"),
            (50, 70, "ruwan@example.com", 10, "helv"),
            (50, 105, "EXPERIENCE", 12, "hebo"),
            (50, 125, "Accounts Clerk - Acme Ltd | 2022 - 2024", 10, "helv"),
            (60, 142, "• Maintained ledger entries and bank reconciliation.", 10, "helv"),
        ]
        pdf_bytes = _build_pdf([page1])
        doc = process_pdf_bytes("ruwan_year_only.pdf", pdf_bytes, "application/pdf")
        res = evaluate_cv(doc)

        cat2 = next(c for c in res.categories if c.category.key == "professional_experience")
        f2 = {f.factor_name: f for f in cat2.factors}
        self.assertEqual(f2["Employment Duration"].status, STATUS_CANNOT_ASSESS)
        self.assertIsNone(f2["Employment Duration"].score)


if __name__ == "__main__":
    unittest.main()
