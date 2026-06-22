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

    parsed = parse_uploaded_file(uploaded_file)

    st.markdown("### Input Details")
    st.write(
        {
            "tab": tab_name,
            "timeline": timeline,
            "timeline_start": str(timeline_start),
            "timeline_end": str(timeline_end),
            "target_line": target_line,
            "file_name": uploaded_file.name,
            "file_type": parsed["file_type"],
        }
    )

    st.markdown("### Data Dictionary")
    st.json(DATA_DICTIONARY)

    st.markdown("### Analysis")
    if parsed["kind"] == "table":
        dataframe = parsed["data"]
        st.dataframe(dataframe.head(20), use_container_width=True)
        st.write(build_analysis_summary(dataframe))

        numeric_columns = dataframe.select_dtypes(include="number").columns.tolist()
        if numeric_columns:
            selected_column = st.selectbox(
                "Choose numeric column for detailed statistics",
                numeric_columns,
                key=f"stats_col_{tab_name}",
            )
            st.write(get_column_statistics(dataframe, selected_column))
        else:
            st.warning("No numeric columns were detected for detailed statistics.")
    else:
        st.text_area(
            label="Extracted text preview",
            value=parsed["preview"],
            height=220,
            key=f"preview_{tab_name}",
        )
        st.write(parsed["analysis"])


def main() -> None:
    """Run the Streamlit application."""
    st.set_page_config(page_title="Deviation and Change Request", layout="wide")
    st.title("Deviation and Change Request Dashboard")
    st.caption("Upload a file in each tab and review baseline analysis.")

    deviation_tab, change_request_tab = st.tabs(["Deviation", "Change request"])

    with deviation_tab:
        render_tab("Deviation")

    with change_request_tab:
        render_tab("Change request")


if __name__ == "__main__":
    main()
