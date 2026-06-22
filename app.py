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
from datetime import date, timedelta

# Third-party UI framework.
import streamlit as st

# Project-local analysis functions shared between tabs.
from analysis_functions import (
    SUPPORTED_FILE_TYPES,
    build_analysis_summary,
    evaluate_ppvr_impact_with_llm,
    filter_by_classification,
    filter_by_deviation_progress,
    filter_by_target_line,
    filter_by_timeline,
    get_column_statistics,
    parse_uploaded_file,
    summarize_selected_root_causes,
)

# Project-local data dictionary used in the field guidance expander.
from data_dictionary import DATA_DICTIONARY


# ============================================================================
# UI HELPERS
# These helpers only render UI components and do not change filter logic.
# ============================================================================


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
    """Read a setting from Streamlit secrets first, then environment variables."""
    if name in st.secrets:
        return str(st.secrets[name])
    return os.getenv(name, default)


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
    st.subheader(f"{tab_name} Input")

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

    option_definitions = {
        "Type of classification": ["Minor", "Major"],
        "Deviation Progress": ["Cancelled", "Close", "Ongoing"],
        "Root cause": ["Supplier", "Equipment", "Human cause", "Procedure"],
    }

    binary_options = ["Summary", "Impact on PPVR"]

    selected_analysis_options: list[dict[str, str]] = []

    for option_name in binary_options:
        option_token = option_name.lower().replace(" ", "_")
        is_selected = st.checkbox(
            option_name,
            value=False,
            key=f"{option_token}_selected_{tab_name}",
        )
        selected_analysis_options.append(
            {
                "Option": option_name,
                "Status": "Selected" if is_selected else "Not selected",
                "Selection": "Yes" if is_selected else "No",
            }
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
    if ppvr_analysis_selected:
        llm_api_key = get_runtime_setting("PPVR_LLM_API_KEY") or get_runtime_setting("OPENAI_API_KEY")
        llm_model = get_runtime_setting("PPVR_LLM_MODEL", "gpt-4.1-mini")
        llm_base_url = get_runtime_setting("PPVR_LLM_BASE_URL") or get_runtime_setting("OPENAI_BASE_URL")

        if llm_api_key:
            try:
                with st.spinner("Evaluating PPVR impact with the LLM..."):
                    ppvr_impact_summary, ppvr_text_columns = evaluate_ppvr_impact_with_llm(
                        df_final,
                        api_key=llm_api_key,
                        model=llm_model,
                        base_url=llm_base_url or None,
                    )
            except Exception as exc:
                ppvr_evaluation_error = str(exc)
        else:
            ppvr_evaluation_error = (
                "PPVR LLM settings are not configured. Add PPVR_LLM_API_KEY and optionally "
                "PPVR_LLM_MODEL / PPVR_LLM_BASE_URL in Streamlit secrets or environment variables."
            )

    root_cause_summary, root_cause_col = summarize_selected_root_causes(
        df_final, root_cause_values
    )

    # -------------------------------
    # SECTION D: RESULTS TO USER
    # -------------------------------
    # 6) Show evaluation results and filtered output.
    st.markdown("---")
    st.markdown("### Result of Input Evaluation")

    if date_col is None:
        st.warning(
            "A 'Date occurred' column was not found in the file. "
            "Timeline filtering was skipped. "
            "Expected column name: 'Date occurred'."
        )
    if not target_line:
        st.warning("No target line was entered. Target line filtering was skipped.")

    # Try common DV column name variants for display.
    dv_col_candidates = ["dv number", "dv_number", "dvnumber", "dv no", "dv"]
    dv_col = next(
        (col for col in df_final.columns if col.lower().strip() in dv_col_candidates),
        None,
    )

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
                "PPVR impact could not be evaluated because Description, QA conclusion, "
                "Conclusion, and Justification of Impact columns were not found."
            )

    if root_cause_values:
        st.markdown("#### Selected Root Cause Results")
        if root_cause_summary and root_cause_col:
            st.table(root_cause_summary)
            st.caption(f"Counts are based on the '{root_cause_col}' column.")
        else:
            st.info("A root cause column was not found in the filtered records.")

    if dv_col:
        # Show only DV identifiers as a compact quick-check list.
        st.markdown("#### DV Numbers in Scope")
        st.dataframe(
            df_final[[dv_col]].rename(columns={dv_col: "DV Number"}),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            "A 'DV number' column was not found in the file. "
            f"{len(df_final)} records passed all filters."
        )

    st.markdown("#### Filtered Records")
    # Full records are still shown for traceability.
    st.dataframe(df_final, use_container_width=True, hide_index=True)


# ============================================================================
# APP ENTRYPOINT
# Builds page shell and mounts both business tabs.
# ============================================================================
def main() -> None:
    """Run the Streamlit application."""
    st.set_page_config(page_title="OPV/SE Analyzor", layout="wide")
    st.title("OPV/SE Analyzor")
    st.caption("Upload a file in each tab and review baseline analysis.")

    deviation_tab, change_request_tab = st.tabs(["Deviation", "Change request"])

    with deviation_tab:
        render_tab("Deviation")

    with change_request_tab:
        render_tab("Change request")


if __name__ == "__main__":
    main()
