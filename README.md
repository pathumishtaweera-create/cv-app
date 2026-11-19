# Banking & Finance CV Analyzer

A local, privacy-first Python and Streamlit web application for evaluating PDF CVs for entry-level banking and finance roles — without any external AI APIs, cloud services, or API keys.

## Features

- **In-Memory PDF Validation**: Accepts `.pdf` files up to 10 MB, checks `%PDF-` headers, and rejects unsupported formats, empty files, corrupted files, and password-protected documents without saving uploads to disk.
- **PyMuPDF Extraction & Layout Analysis**: Extracts personal/contact details, O/L, A/L, degrees/diplomas, professional qualifications, work/internship experience, technical skills, languages, banking/finance knowledge, achievements, and PDF formatting metrics.
- **Deterministic 9-Category Evaluation Engine (100 Points)**: Scores Educational Qualifications (20), Professional Experience (15), Technical & Computer Skills (10), Communication & Language Skills (10), Banking & Finance Knowledge (10), Achievements & Extracurriculars (5), CV Structure & Organization (10), Language & Writing Quality (10), and Visual Presentation & Formatting (10).
- **Clean 4-Section Results Dashboard**:
  1. **Overall CV Score** — Score out of 100, visual progress indicator, classification, short explanation, and collapsible 9-category breakdown.
  2. **What's Good** — Evidence-backed strengths from the uploaded CV.
  3. **What Needs Improvement** — Identified weaknesses and genuine errors backed by CV evidence.
  4. **Specific Corrections and Recommendations** — Direct A/B/C/D feedback (*Original CV Example*, *Identified Problem*, *Recommended Improvement*, *Reason*) anchored in actual text and layout findings, plus downloadable PDF report export.

## Installation & Startup

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Running Tests

```bash
python3 -m unittest discover -s tests -v
```
