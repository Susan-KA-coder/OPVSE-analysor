"""Main Streamlit application.

This app provides two business tabs:
1. Deviation
2. Change request

Each tab allows users to upload a supported file and enter timeline/target data.
"""

from __future__ import annotations

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

    timeline = st.text_input(
        label="Timeline",
        key=f"timeline_{tab_name}",
        placeholder="Example: Week 28, 2026",
        help="Enter timeline information for this record.",
    )
    target_line = st.text_input(
        label="Target line",
        key=f"target_{tab_name}",
        placeholder="Example: Production Line 4",
        help="Enter the target line for this analysis.",
    )

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
