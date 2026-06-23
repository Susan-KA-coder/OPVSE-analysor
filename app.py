"""Main Streamlit application.

This app provides two business tabs:
1. Deviation
2. Change request

Each tab allows users to upload a supported file and enter timeline/target data.

Code map:
1) Import and setup section
2) UI helper section
3) Tab workflow section (input -> parse -> filter -> result)
4) App entrypoint section
"""

from __future__ import annotations

# Standard library imports used for input validation and default dates.
import os
import re
import io
from datetime import date, timedelta

# Third-party UI framework.
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import streamlit as st

# Project-local analysis functions shared between tabs.
from analysis_functions import (
    SUPPORTED_FILE_TYPES,
    build_analysis_summary,
    evaluate_ppvr_impact_with_local_llm,
    evaluate_root_cause_with_local_llm,
    filter_by_classification,
    filter_by_deviation_progress,
    filter_by_target_line,
    filter_by_timeline,
    get_column_statistics,
    parse_uploaded_file,
)

import pandas as pd
# Project-local data dictionary used in the field guidance expander.
from data_dictionary import DATA_DICTIONARY


# ============================================================================
# UI HELPERS
# These helpers only render UI components and do not change filter logic.
# ============================================================================


def apply_custom_theme() -> None:
    """Apply a custom visual theme to improve readability and hierarchy."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Source+Sans+3:wght@400;600;700&display=swap');

        :root {
            --brand-ink: #0f172a;
            --brand-sea: #0f766e;
            --brand-amber: #d97706;
            --brand-slate: #334155;
            --brand-surface: #f8fafc;
            --brand-card: #ffffff;
            --brand-border: #cbd5e1;
            --brand-success: #0ea5a4;
        }

        .stApp {
            font-family: 'Source Sans 3', sans-serif;
            background:
                radial-gradient(circle at 15% 8%, rgba(20, 184, 166, 0.12), transparent 28%),
                radial-gradient(circle at 90% 0%, rgba(245, 158, 11, 0.14), transparent 30%),
                linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
        }

        h1, h2, h3, h4 {
            font-family: 'Space Grotesk', sans-serif !important;
            color: var(--brand-ink);
            letter-spacing: 0.01em;
        }

        .stCaption {
            color: var(--brand-slate) !important;
            font-size: 0.98rem !important;
        }

        .block-container {
            padding-top: 1.8rem !important;
            padding-bottom: 2.5rem !important;
        }

        div[data-testid="stMetric"] {
            background: var(--brand-card);
            border: 1px solid var(--brand-border);
            border-left: 0.35rem solid var(--brand-sea);
            border-radius: 0.8rem;
            padding: 0.65rem 0.8rem;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
            min-height: 108px;
        }

        div[data-testid="stMetricLabel"] {
            color: var(--brand-slate) !important;
            font-weight: 700 !important;
            font-size: 0.88rem !important;
        }

        div[data-testid="stMetricValue"] {
            color: var(--brand-ink) !important;
            font-family: 'Space Grotesk', sans-serif !important;
            font-size: 2rem !important;
            line-height: 1.1;
        }

        div[data-testid="stFileUploader"] {
            border: 2px dashed #94a3b8 !important;
            border-radius: 0.9rem !important;
            background: rgba(255, 255, 255, 0.66) !important;
            padding: 0.35rem;
        }

        .stButton > button, .stDownloadButton > button {
            border-radius: 0.7rem !important;
            border: 1px solid #0f766e !important;
            font-weight: 700 !important;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        .stDownloadButton > button {
            background: linear-gradient(135deg, #0f766e 0%, #0ea5a4 100%) !important;
            color: #ffffff !important;
            border: 0 !important;
        }

        .stButton > button:hover, .stDownloadButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 10px 22px rgba(15, 118, 110, 0.28);
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid var(--brand-border);
            border-radius: 0.8rem;
            overflow: hidden;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.07);
            background: #ffffff;
        }

        div[data-testid="stTable"] {
            border: 1px solid var(--brand-border);
            border-radius: 0.8rem;
            overflow: hidden;
            background: #ffffff;
        }

        [data-testid="stHorizontalBlock"] > div {
            animation: revealUp 0.35s ease-out;
        }

        @keyframes revealUp {
            from {
                opacity: 0;
                transform: translateY(8px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def section_card_start(title: str) -> None:
    """Render a styled section header card."""
    st.markdown(
        f"""
        <div style=\"background:#ffffff;border:1px solid #cbd5e1;border-radius:14px;padding:12px 16px;box-shadow:0 8px 22px rgba(15,23,42,0.08);margin:6px 0 14px 0;\">
            <h3 style=\"margin:0;color:#0f172a;\">{title}</h3>
            <p style=\"margin:4px 0 0 0;color:#334155;font-size:0.95rem;\">Review inputs and outputs with a cleaner visual layout.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_card_end() -> None:
    """No-op helper kept for readability in render flow."""


def render_data_dictionary() -> None:
    """Render business field guidance used by this app.

    The expander keeps the main screen clean while still giving users
    a quick reference for expected column meanings.
    """
    with st.expander("Field reference", expanded=False):
        st.table(
            [
                {"Field": field, "Description": description}
                for field, description in DATA_DICTIONARY.items()
            ]
        )


def render_table_analysis(dataframe) -> None:
    """Render optional table analytics with user-friendly widgets.

    Note:
        This helper is kept for the next analysis phase. The current workflow
        shows input-evaluation results after filtering.
    """
    summary = build_analysis_summary(dataframe)

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("Rows", summary["rows"])
    metric_col2.metric("Columns", summary["columns"])
    metric_col3.metric("Numeric columns", len(dataframe.select_dtypes(include="number").columns.tolist()))

    st.markdown("#### Data Preview")
    st.dataframe(dataframe.head(20), width="stretch")

    missing_table = [
        {"Column": column_name, "Missing values": missing_count}
        for column_name, missing_count in summary["missing_values_by_column"].items()
    ]
    st.markdown("#### Missing Values")
    st.table(missing_table)

    numeric_columns = dataframe.select_dtypes(include="number").columns.tolist()
    if numeric_columns:
        selected_column = st.selectbox(
            "Choose numeric column for detailed statistics",
            numeric_columns,
            key="stats_col_table",
        )
        stats = get_column_statistics(dataframe, selected_column)

        stat_col1, stat_col2, stat_col3 = st.columns(3)
        stat_col1.metric("Min", f"{stats['min']:.2f}")
        stat_col2.metric("Mean", f"{stats['mean']:.2f}")
        stat_col3.metric("Max", f"{stats['max']:.2f}")

        stat_col4, stat_col5, stat_col6 = st.columns(3)
        stat_col4.metric("Count", f"{stats['count']:.0f}")
        stat_col5.metric("Median", f"{stats['median']:.2f}")
        stat_col6.metric("Std Dev", f"{stats['std_dev']:.2f}")
    else:
        st.info("No numeric columns were detected for detailed statistics.")


def render_text_analysis(parsed: dict) -> None:
    """Render optional text analytics for PDF/Word uploads.

    Note:
        This helper is kept for the next analysis phase.
    """
    text_analysis = parsed["analysis"]

    metric_col1, metric_col2 = st.columns(2)
    metric_col1.metric("Characters", text_analysis["characters"])
    metric_col2.metric("Words", text_analysis["words"])

    st.markdown("#### Most Frequent Words")
    st.table(
        [
            {"Word": word, "Count": count}
            for word, count in text_analysis["top_10_words"]
        ]
    )

    st.markdown("#### Extracted Text Preview")
    st.text_area(
        label="Preview",
        value=parsed["preview"],
        height=220,
        key="preview_text",
        label_visibility="collapsed",
    )


def get_runtime_setting(name: str, default: str = "") -> str:
    """Read a setting from environment variables."""
    return os.getenv(name, default)


def _resolve_impact_text_columns(dataframe, text_columns: list[str]) -> list[str]:
    """Resolve text columns used to infer PPVR impact sheets."""
    if text_columns:
        return [col for col in text_columns if col in dataframe.columns]

    fallback_candidates = [
        "title",
        "description",
        "qa",
        "conclusion",
        "impact",
        "justification",
        "deviation",
        "root cause",
    ]
    resolved: list[str] = []
    for column_name in dataframe.columns:
        col_lower = str(column_name).lower()
        if any(token in col_lower for token in fallback_candidates):
            resolved.append(column_name)
    return resolved


def build_ppvr_impact_sheets(dataframe, text_columns: list[str]) -> dict[str, pd.DataFrame]:
    """Build record-level PPVR impact sheets by factor using keyword matching."""
    factor_keywords = {
        "Patient Safety": ["patient", "safety", "adverse", "harm", "injury", "risk"],
        "Product Quality": ["quality", "defect", "nonconform", "specification", "failure"],
        "Validation": ["validation", "validate", "verification", "verify", "qualification"],
        "Regulatory Documentation": ["regulatory", "documentation", "compliance", "submission", "gmp"],
    }

    columns_for_scan = _resolve_impact_text_columns(dataframe, text_columns)
    impact_sheets: dict[str, pd.DataFrame] = {}

    for factor_name, keywords in factor_keywords.items():
        matched_rows: list[dict[str, str]] = []

        for _, row in dataframe.iterrows():
            matched_fields: list[str] = []
            matched_keywords: list[str] = []

            for column_name in columns_for_scan:
                value_text = str(row.get(column_name, "") or "")
                value_lower = value_text.lower()
                hits = [keyword for keyword in keywords if keyword in value_lower]
                if hits:
                    matched_fields.append(str(column_name))
                    matched_keywords.extend(hits)

            if matched_fields:
                row_payload = {str(col): str(row.get(col, "") or "") for col in dataframe.columns}
                row_payload["Matched fields"] = ", ".join(sorted(set(matched_fields)))
                row_payload["Matched keywords"] = ", ".join(sorted(set(matched_keywords)))
                matched_rows.append(row_payload)

        if matched_rows:
            impact_sheets[factor_name] = pd.DataFrame(matched_rows)
        else:
            impact_sheets[factor_name] = pd.DataFrame(
                columns=["Matched fields", "Matched keywords"] + [str(col) for col in dataframe.columns]
            )

    return impact_sheets


def dataframe_to_excel_bytes(dataframe, impact_sheets: dict[str, pd.DataFrame] | None = None) -> bytes:
    """Return Excel bytes for a dataframe download, including impact sheets."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False, sheet_name="Filtered Records")
        if impact_sheets:
            for sheet_name, impact_df in impact_sheets.items():
                safe_sheet_name = sheet_name[:31]
                impact_df.to_excel(writer, index=False, sheet_name=safe_sheet_name)
    return buffer.getvalue()


def dataframe_to_pdf_bytes(dataframe) -> bytes:
    """Return simple PDF bytes for a dataframe download."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    left_margin = 36
    top_y = page_height - 40
    line_height = 14

    columns = [str(col) for col in dataframe.columns]
    rows = dataframe.fillna("").astype(str).values.tolist()

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left_margin, top_y, "Filtered Records")
    y = top_y - (line_height * 2)

    pdf.setFont("Helvetica", 8)
    header_text = " | ".join(columns)
    pdf.drawString(left_margin, y, header_text[:180])
    y -= line_height

    for row in rows:
        if y < 40:
            pdf.showPage()
            pdf.setFont("Helvetica", 8)
            y = page_height - 40
        line_text = " | ".join(row)
        pdf.drawString(left_margin, y, line_text[:180])
        y -= line_height

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


def render_tab(tab_name: str) -> None:
    """Render one business tab and run the two-stage input evaluation.

    Args:
        tab_name: Display name of the current tab.

    Evaluation steps:
        1) Keep records within selected timeline based on Date occurred.
        2) Keep records whose Title/Description contains target-line number.
    """
    # -------------------------------
    # SECTION A: INPUT COLLECTION
    # -------------------------------
    section_card_start(f"{tab_name} Input")

    # 1) Timeline input (date range)
    col1, col2 = st.columns(2)
    with col1:
        timeline_start = st.date_input(
            label="Timeline start date",
            value=date.today() - timedelta(days=365),
            key=f"timeline_start_{tab_name}",
            help="Select the start date of the analysis period.",
        )
    with col2:
        timeline_end = st.date_input(
            label="Timeline end date",
            value=date.today(),
            key=f"timeline_end_{tab_name}",
            help="Select the end date of the analysis period.",
        )

    if timeline_start > timeline_end:
        st.error("Start date must be before end date.")
        return

    timeline = f"{timeline_start.strftime('%d %b %Y')} to {timeline_end.strftime('%d %b %Y')}"

    # 2) Target line input and format validation
    target_line_raw = st.text_input(
        label="Target line (format: DF50.1)",
        key=f"target_{tab_name}",
        placeholder="Example: DF50.1",
        help="Enter target line in format DF followed by 2-3 digits, a dot, and 1-2 digits. Example: DF50.1",
    )

    target_line_raw = target_line_raw.strip().upper()
    TARGET_PATTERN = re.compile(r"^DF\d{2,3}\.\d{1,2}$")
    if target_line_raw and not TARGET_PATTERN.match(target_line_raw):
        st.warning("Target line must follow the format DF50.1 (for example DF50.1 or DF500.1).")
        target_line = ""
    else:
        target_line = target_line_raw

    # 3) Analysis options for next-stage business evaluation.
    st.markdown("### Analysis Options")
    st.caption("Select the options you want to use. For Summary and Impact on PPVR: selected means Yes, not selected means No.")

    ppvr_model = "llama3.2:1b"
    ppvr_base_url = "http://127.0.0.1:11434/v1"
    ppvr_configured = True  # Local LLM is always available, but depends on Ollama being reachable.

    option_definitions = {
        "Type of classification": ["Minor", "Major"],
        "Deviation Progress": ["Cancelled", "Close", "Ongoing"],
        "Root cause": ["Supplier", "Equipment", "Human cause", "Procedure"],
    }

    binary_options = ["Summary", "Impact on PPVR"]

    selected_analysis_options: list[dict[str, str]] = []

    for option_name in binary_options:
        option_token = option_name.lower().replace(" ", "_")
        is_ppvr_option = option_name == "Impact on PPVR"
        is_selected = st.checkbox(
            option_name,
            value=False,
            key=f"{option_token}_selected_{tab_name}",
            disabled=is_ppvr_option and not ppvr_configured,
        )
        selected_analysis_options.append(
            {
                "Option": option_name,
                "Status": "Selected" if is_selected else "Not selected",
                "Selection": "Yes" if is_selected else "No",
            }
        )

    if not ppvr_configured:
        st.info(
            "PPVR analysis is disabled until the local LLM server is reachable."
        )

    for option_name, values_for_option in option_definitions.items():
        option_token = option_name.lower().replace(" ", "_")

        is_selected = st.checkbox(
            f"Use {option_name}",
            value=False,
            key=f"use_{option_token}_{tab_name}",
        )

        selected_values: list[str] = []
        if is_selected:
            if option_name == "Type of classification":
                selected_values = st.multiselect(
                    f"{option_name} values",
                    options=values_for_option,
                    default=[],
                    key=f"{option_token}_values_{tab_name}",
                )
            else:
                selected_values = st.multiselect(
                    f"{option_name} values",
                    options=values_for_option,
                    default=[],
                    key=f"{option_token}_values_{tab_name}",
                )

        selected_analysis_options.append(
            {
                "Option": option_name,
                "Status": "Selected" if is_selected else "Not selected",
                "Selection": ", ".join(selected_values) if selected_values else "No value selected",
            }
        )

    # 4) File upload
    uploaded_file = st.file_uploader(
        "Upload file (CSV, Excel, PDF, Word)",
        type=SUPPORTED_FILE_TYPES,
        key=f"upload_{tab_name}",
    )
    section_card_end()

    if not uploaded_file:
        st.info("Upload a file to begin analysis.")
        return

    # -------------------------------
    # SECTION B: FILE PARSING
    # -------------------------------
    try:
        parsed = parse_uploaded_file(uploaded_file)
    except Exception:
        st.error("The uploaded file could not be processed. Please check the file format and try again.")
        return

    # Current input-evaluation logic works with tabular files.
    if parsed["kind"] != "table":
        st.warning("Only CSV and Excel files support the filtering analysis. Please upload a spreadsheet file.")
        return

    # -------------------------------
    # SECTION C: FILTER EXECUTION
    # -------------------------------
    raw_df = parsed["data"]
    total_rows = len(raw_df)

    # 4) Apply timeline filter first.
    df_after_timeline, removed_timeline, date_col = filter_by_timeline(
        raw_df, timeline_start, timeline_end
    )

    # 5) Apply target-line filter on the already timeline-filtered data.
    df_after_target, removed_target = filter_by_target_line(df_after_timeline, target_line)

    # 6) Extract classification values from selected options and apply filter.
    classification_values = []
    for option in selected_analysis_options:
        if option["Option"] == "Type of classification":
            selection_text = option["Selection"]
            if selection_text != "No value selected":
                classification_values = [val.strip() for val in selection_text.split(",")]
            break
    
    df_after_classification, removed_classification, classification_col, classification_counts = filter_by_classification(
        df_after_target, classification_values
    )

    # 7) Extract deviation progress values from selected options and apply filter.
    deviation_progress_values = []
    for option in selected_analysis_options:
        if option["Option"] == "Deviation Progress":
            selection_text = option["Selection"]
            if selection_text != "No value selected":
                deviation_progress_values = [val.strip() for val in selection_text.split(",")]
            break

    root_cause_values = []
    ppvr_analysis_selected = False
    for option in selected_analysis_options:
        if option["Option"] == "Root cause":
            selection_text = option["Selection"]
            if selection_text != "No value selected":
                root_cause_values = [val.strip() for val in selection_text.split(",")]
        if option["Option"] == "Impact on PPVR":
            ppvr_analysis_selected = option["Selection"] == "Yes"
    
    df_final, removed_deviation_progress, lifecycle_col, progress_counts = filter_by_deviation_progress(
        df_after_classification, deviation_progress_values
    )

    ppvr_impact_summary, ppvr_text_columns = ({}, [])
    ppvr_evaluation_error = ""
    if ppvr_analysis_selected and ppvr_configured:
        try:
            with st.spinner("Evaluating PPVR impact with Ollama..."):
                ppvr_impact_summary, ppvr_text_columns = evaluate_ppvr_impact_with_local_llm(
                    df_final,
                    model=ppvr_model,
                    base_url=ppvr_base_url,
                )
        except Exception as exc:
            ppvr_evaluation_error = str(exc)

    root_cause_summary, root_cause_text_columns = ({}, [])
    root_cause_error = ""
    if root_cause_values:
        try:
            with st.spinner("Evaluating root cause with Ollama..."):
                root_cause_summary, root_cause_text_columns = evaluate_root_cause_with_local_llm(
                    df_final,
                    model=ppvr_model,
                    base_url=ppvr_base_url,
                )
        except Exception as exc:
            root_cause_error = str(exc)

    # -------------------------------
    # SECTION D: RESULTS TO USER
    # -------------------------------
    # 6) Show evaluation results and filtered output.
    section_card_start("Result of Input Evaluation")

    if date_col is None:
        st.warning(
            "A 'Date occurred' column was not found in the file. "
            "Timeline filtering was skipped. "
            "Expected column name: 'Date occurred'."
        )
    if not target_line:
        st.warning("No target line was entered. Target line filtering was skipped.")

    summary_col1, summary_col2, summary_col3, summary_col4, summary_col5, summary_col6 = st.columns(6)
    # Six KPI cards summarize the filtering outcome.
    summary_col1.metric("Total records in file", total_rows)
    summary_col2.metric("Removed — outside timeline", removed_timeline)
    summary_col3.metric("Removed — no target line match", removed_target)
    summary_col4.metric("Removed — classification filter", removed_classification)
    summary_col5.metric("Removed — deviation progress filter", removed_deviation_progress)
    summary_col6.metric("Records kept for analysis", len(df_final))

    if len(df_final) == 0:
        st.error("No records remain after filtering. Check your timeline and target line settings.")
        section_card_end()
        return

    # Display classification breakdown if the classification column was found.
    if classification_col and classification_counts:
        st.markdown("#### Classification Summary")
        classification_summary = [
            {"Classification": key, "Count": value}
            for key, value in classification_counts.items()
        ]
        st.table(classification_summary)

    # Display selected classification results if user selected specific types.
    if classification_values and classification_col:
        st.markdown("#### Selected Classification Results")
        selected_classification_results = []
        for selected_type in classification_values:
            # Count records of this type in the final filtered dataframe
            count = (df_final[classification_col].astype(str).str.lower() == selected_type.lower()).sum()
            selected_classification_results.append(
                {"Classification Type": selected_type, "Records": int(count)}
            )
        st.table(selected_classification_results)

    # Display selected deviation progress results if user selected specific types.
    if deviation_progress_values and lifecycle_col:
        st.markdown("#### Selected Deviation Progress Results")
        selected_progress_results = []
        lifecycle_lower = df_final[lifecycle_col].astype(str).str.lower()
        for selected_progress in deviation_progress_values:
            display_progress = selected_progress
            if selected_progress.lower() == "ongoing":
                count = (~(
                    lifecycle_lower.str.contains("closed", na=False)
                    | lifecycle_lower.str.contains("cancelled", na=False)
                )).sum()
                display_progress = "Ongoing (not Closed / Cancelled)"
            else:
                count = lifecycle_lower.str.contains(
                    selected_progress.lower(),
                    na=False,
                    regex=False,
                ).sum()
            selected_progress_results.append(
                {"Deviation Progress": display_progress, "Fields": int(count)}
            )
        st.table(selected_progress_results)

    if ppvr_analysis_selected:
        st.markdown("#### PPVR Impact Evaluation")
        if ppvr_impact_summary:
            ppvr_results = [
                {"PPVR Assessment": label, "Fields": value}
                for label, value in ppvr_impact_summary.items()
            ]
            st.table(ppvr_results)
            st.caption(
                "LLM review based on text in: " + ", ".join(ppvr_text_columns)
            )
        elif ppvr_evaluation_error:
            st.warning(ppvr_evaluation_error)
        else:
            st.info(
                "PPVR impact could not be evaluated because no PPVR text columns were detected."
            )

    if root_cause_values:
        st.markdown("#### Selected Root Cause Results")
        if root_cause_summary:
            st.table(root_cause_summary)
            if root_cause_text_columns:
                st.caption("LLM review based on text in: " + ", ".join(root_cause_text_columns))
        else:
            st.warning(root_cause_error or "Root cause analysis could not return results.")

    # Use text from the first column in the uploaded sheet for DV scope display.
    first_column_name = df_final.columns[0]
    st.markdown("#### DV Numbers in Scope")
    st.dataframe(
        df_final[[first_column_name]].astype(str).rename(columns={first_column_name: "DV Number"}),
        width="stretch",
        hide_index=True,
    )

    st.markdown("#### Download Remaining Records")
    preferred_download_format = st.radio(
        "Choose your preferred download format",
        options=["Excel (.xlsx)", "PDF (.pdf)"],
        horizontal=True,
        key=f"download_format_{tab_name}",
    )
    impact_sheets = build_ppvr_impact_sheets(df_final, ppvr_text_columns)

    tab_slug = tab_name.lower().replace(" ", "_")
    if preferred_download_format == "Excel (.xlsx)":
        st.download_button(
            label="Download remaining records as Excel",
            data=dataframe_to_excel_bytes(df_final, impact_sheets=impact_sheets),
            file_name=f"{tab_slug}_remaining_records.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_excel_{tab_name}",
        )
    else:
        st.download_button(
            label="Download remaining records as PDF",
            data=dataframe_to_pdf_bytes(df_final),
            file_name=f"{tab_slug}_remaining_records.pdf",
            mime="application/pdf",
            key=f"download_pdf_{tab_name}",
        )

    st.markdown("#### Filtered Records")
    # Full records are still shown for traceability.
    st.dataframe(df_final, width="stretch", hide_index=True)
    section_card_end()


# ============================================================================
# APP ENTRYPOINT
# Builds page shell and mounts both business tabs.
# ============================================================================
def main() -> None:
    """Run the Streamlit application."""
    st.set_page_config(page_title="OPV/SE Analyzor", layout="wide")
    apply_custom_theme()
    st.title("OPV/SE Analyzor")
    st.caption("Upload a file in each tab and review baseline analysis.")

    deviation_tab, change_request_tab = st.tabs(["Deviation", "Change request"])

    with deviation_tab:
        render_tab("Deviation")

    with change_request_tab:
        render_tab("Change request")


if __name__ == "__main__":
    main()
