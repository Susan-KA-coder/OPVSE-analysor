"""Main Streamlit application.

This app provides two business tabs:
1. Deviation
2. Change request

Each tab allows users to upload a supported file and enter timeline/target data.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import streamlit as st

from analysis_functions import (
    SUPPORTED_FILE_TYPES,
    build_analysis_summary,
    filter_by_target_line,
    filter_by_timeline,
    get_column_statistics,
    parse_uploaded_file,
)
from data_dictionary import DATA_DICTIONARY


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


def render_tab(tab_name: str) -> None:
    """Render one business tab and run the two-stage input evaluation.

    Args:
        tab_name: Display name of the current tab.

    Evaluation steps:
        1) Keep records within selected timeline based on Date occurred.
        2) Keep records whose Title/Description contains target-line number.
    """
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

    # 3) File upload
    uploaded_file = st.file_uploader(
        "Upload file (CSV, Excel, PDF, Word)",
        type=SUPPORTED_FILE_TYPES,
        key=f"upload_{tab_name}",
    )

    if not uploaded_file:
        st.info("Upload a file to begin analysis.")
        return

    try:
        parsed = parse_uploaded_file(uploaded_file)
    except Exception:
        st.error("The uploaded file could not be processed. Please check the file format and try again.")
        return

    # Current input-evaluation logic works with tabular files.
    if parsed["kind"] != "table":
        st.warning("Only CSV and Excel files support the filtering analysis. Please upload a spreadsheet file.")
        return

    raw_df = parsed["data"]
    total_rows = len(raw_df)

    # 4) Apply timeline filter first.
    df_after_timeline, removed_timeline, date_col = filter_by_timeline(
        raw_df, timeline_start, timeline_end
    )

    # 5) Apply target-line filter on the already timeline-filtered data.
    df_final, removed_target = filter_by_target_line(df_after_timeline, target_line)

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

    summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
    summary_col1.metric("Total records in file", total_rows)
    summary_col2.metric("Removed — outside timeline", removed_timeline)
    summary_col3.metric("Removed — no target line match", removed_target)
    summary_col4.metric("Records kept for analysis", len(df_final))

    if len(df_final) == 0:
        st.error("No records remain after filtering. Check your timeline and target line settings.")
        return

    if dv_col:
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
    st.dataframe(df_final, use_container_width=True, hide_index=True)


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
