"""
Minimal, lightweight CSS styles for the Banking & Finance CV Analyzer.

Uses a clean light canvas, system sans-serif typography, consistent spacing,
and restrained semantic indicators (green = strengths, amber/neutral = improvements,
red = genuine errors only). No animations or decorative clutter.
"""

import streamlit as st


def inject_custom_css() -> None:
    """Inject clean, lightweight CSS into the Streamlit application."""
    st.markdown(
        """
        <style>
        html, body, [class*="css"] {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: #0F172A;
        }

        .stApp {
            background-color: #F8FAFC;
        }

        .block-container {
            max-width: 960px;
            padding-top: 1.75rem;
            padding-bottom: 2.5rem;
        }

        /* Header */
        .bf-header {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 1.25rem 1.5rem;
            margin-bottom: 1.25rem;
        }

        .bf-title {
            font-size: 1.6rem;
            font-weight: 700;
            color: #0F2942;
            margin: 0 0 0.35rem 0;
            line-height: 1.25;
        }

        .bf-subtitle {
            font-size: 0.94rem;
            color: #475569;
            margin: 0;
            line-height: 1.5;
        }

        /* Section headings */
        .bf-section-title {
            font-size: 1.15rem;
            font-weight: 700;
            color: #0F2942;
            border-bottom: 1px solid #E2E8F0;
            padding-bottom: 0.35rem;
            margin: 1.35rem 0 0.75rem 0;
        }

        .bf-sub-caption {
            font-size: 0.86rem;
            color: #475569;
            margin: 0 0 0.75rem 0;
        }

        /* Document info summary */
        .bf-doc-summary {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.75rem;
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 0.85rem 1rem;
            margin: 0.75rem 0;
        }

        @media (max-width: 720px) {
            .bf-doc-summary {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }

        .bf-doc-label {
            font-size: 0.75rem;
            color: #64748B;
            margin-bottom: 0.1rem;
        }

        .bf-doc-val {
            font-size: 0.88rem;
            font-weight: 600;
            color: #0F172A;
            word-break: break-word;
        }

        /* Section 1: Overall Score Box */
        .bf-score-box {
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 8px;
            padding: 1.25rem 1.4rem;
            margin-bottom: 0.75rem;
        }

        .bf-score-headline {
            font-size: 1.55rem;
            font-weight: 700;
            color: #0F2942;
            margin: 0 0 0.2rem 0;
        }

        .bf-classification {
            font-size: 1.05rem;
            font-weight: 600;
            margin: 0 0 0.55rem 0;
        }

        .bf-class-outstanding, .bf-class-very_good { color: #166534; }
        .bf-class-good { color: #1D4ED8; }
        .bf-class-average { color: #B45309; }
        .bf-class-below_average, .bf-class-needs_improvement, .bf-class-unavailable { color: #B91C1C; }

        .bf-score-desc {
            font-size: 0.9rem;
            color: #1E293B;
            line-height: 1.5;
            margin: 0.5rem 0 0.35rem 0;
        }

        .bf-disclaimer {
            font-size: 0.8rem;
            color: #64748B;
            margin: 0;
        }

        /* Score Interpretation Note (60% suggested benchmark) */
        .bf-benchmark-note {
            border-radius: 8px;
            padding: 0.95rem 1.15rem;
            margin: 0.6rem 0 0.85rem 0;
        }

        .bf-benchmark-pass {
            background: #F0FDF4;
            border: 1px solid #BBF7D0;
            border-left: 4px solid #16A34A;
        }

        .bf-benchmark-below {
            background: #FFFBEB;
            border: 1px solid #FDE68A;
            border-left: 4px solid #D97706;
        }

        .bf-benchmark-unavailable {
            background: #F8FAFC;
            border: 1px solid #CBD5E1;
            border-left: 4px solid #64748B;
        }

        .bf-benchmark-title {
            font-size: 0.92rem;
            font-weight: 700;
            color: #0F2942;
            margin: 0 0 0.3rem 0;
        }

        .bf-benchmark-text {
            font-size: 0.9rem;
            color: #0F172A;
            line-height: 1.5;
            margin: 0 0 0.35rem 0;
        }

        .bf-benchmark-sub {
            font-size: 0.82rem;
            color: #475569;
            line-height: 1.45;
            margin: 0;
        }

        /* Semantic Item Blocks: Green (Strengths), Amber (Improvements), Red (Genuine Errors Only) */
        .bf-item {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 0.85rem 1rem;
            margin-bottom: 0.65rem;
        }

        .bf-item-good {
            border-left: 4px solid #16A34A;
            background: #F0FDF4;
        }

        .bf-item-improve {
            border-left: 4px solid #D97706;
            background: #FFFBEB;
        }

        .bf-item-error {
            border-left: 4px solid #DC2626;
            background: #FEF2F2;
        }

        .bf-item-head {
            font-size: 0.94rem;
            font-weight: 600;
            color: #0F172A;
            margin-bottom: 0.35rem;
        }

        .bf-badge-good { color: #166534; font-weight: 700; font-size: 0.82rem; }
        .bf-badge-improve { color: #B45309; font-weight: 700; font-size: 0.82rem; }
        .bf-badge-error { color: #B91C1C; font-weight: 700; font-size: 0.82rem; }

        .bf-line {
            font-size: 0.87rem;
            color: #1E293B;
            line-height: 1.48;
            margin: 0.2rem 0;
        }

        .bf-compare-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.75rem;
            margin: 0.45rem 0;
        }

        @media (max-width: 720px) {
            .bf-compare-grid {
                grid-template-columns: 1fr;
            }
        }

        .bf-step-box {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 5px;
            padding: 0.6rem 0.75rem;
        }

        .bf-step-box-fix {
            background: #FFFFFF;
            border: 1px solid #BBF7D0;
            border-radius: 5px;
            padding: 0.6rem 0.75rem;
        }

        .bf-step-label {
            font-size: 0.76rem;
            font-weight: 700;
            color: #475569;
            margin-bottom: 0.25rem;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }

        .bf-step-label-fix {
            color: #166534;
        }

        .bf-step-text {
            font-size: 0.86rem;
            color: #0F172A;
            line-height: 1.45;
        }

        .bf-step-note {
            font-size: 0.8rem;
            color: #475569;
            margin-top: 0.35rem;
            line-height: 1.4;
        }

        .bf-step-reason {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 5px;
            padding: 0.55rem 0.75rem;
            font-size: 0.86rem;
            color: #1E293B;
            line-height: 1.45;
            margin-top: 0.35rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
