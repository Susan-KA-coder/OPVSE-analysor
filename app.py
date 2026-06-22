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
    get_column_statistics,
    parse_uploaded_file,
)
from data_dictionary import DATA_DICTIONARY


def render_data_dictionary() -> None:
    """Render data dictionary in a user-friendly table."""
    with st.expander("Field reference", expanded=False):
        st.table(
            [
                {"Field": field, "Description": description}
                for field, description in DATA_DICTIONARY.items()
            ]
        )


def render_table_analysis(dataframe) -> None:
    """Render tabular analysis without showing raw program structures."""
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
    """Render text file analysis in readable layout."""
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
    """Render one business tab with upload and analysis controls.

    Args:
        tab_name: Display name of the current tab.
    """
    st.subheader(f"{tab_name} Input")

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

    target_line_raw = st.text_input(
        label="Target line (format: DF07.01)",
        key=f"target_{tab_name}",
        placeholder="Example: DF07.01",
        help="Enter target line in format DF followed by two digits, a dot, and two digits. Example: DF07.01",
    )

    TARGET_PATTERN = re.compile(r"^DF\d{2}\.\d{2}$")
    if target_line_raw and not TARGET_PATTERN.match(target_line_raw):
        st.warning("Target line must follow the format DF07.01 (e.g. DF12.03).")
        target_line = ""
    else:
        target_line = target_line_raw

    uploaded_file = st.file_uploader(
        "Upload file (CSV, Excel, PDF, Word)",
        type=SUPPORTED_FILE_TYPES,
        key=f"upload_{tab_name}",
    )

    if not uploaded_file:
        st.info("Upload a file to begin analysis.")
        return

    try:
        parse_uploaded_file(uploaded_file)
    except Exception:
        st.error("The uploaded file could not be processed. Please check the file format and try again.")
        return

    st.success(
        f"**{uploaded_file.name}** uploaded successfully. "
        f"Timeline: **{timeline}**. "
        f"Target line: **{target_line or 'Not provided yet.'}**"
    )
    st.info("Analysis will appear here once configured.")


def main() -> None:
    """Run the Streamlit application."""
    st.set_page_config(page_title="OPV/Se Analyzor", layout="wide")
    st.title("OPV/Se Analyzor")
    st.caption("Upload a file in each tab and review baseline analysis.")

    deviation_tab, change_request_tab = st.tabs(["Deviation", "Change request"])

    with deviation_tab:
        render_tab("Deviation")

    with change_request_tab:
        render_tab("Change request")


if __name__ == "__main__":
    main()
