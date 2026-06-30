"""Change Request tab analysis and rendering.

This module handles the complete Change Request tab workflow, separated from
the Deviation tab to keep each analysis path clear and maintainable.
"""

from datetime import date, timedelta
import re

import streamlit as st
import pandas as pd

from analysis_functions import (
    SUPPORTED_FILE_TYPES,
    evaluate_root_cause_with_local_llm,
    filter_by_deviation_progress,
    filter_by_target_line,
    filter_by_timeline,
    parse_uploaded_file,
)
from analysis_functions_CR import evaluate_ppvr_impact_with_local_llm_cr


def render_change_request_tab() -> None:
    """Render the Change Request tab with analysis specific to change control.

    Unlike the Deviation tab, Change Request does NOT include:
    - Type of classification (Minor/Major) filter
    - Classification filter in the data pipeline
    - Most date columns in exports (except Change QA Approval Date)

    The Change Request workflow is:
    1. Collect timeline range, target line, file upload, and analysis options
    2. Parse and validate the uploaded file (CSV/Excel only)
    3. Filter by timeline (records within selected date range)
    4. Filter by target line (records matching DF###.# pattern)
    5. Skip classification filter (no classification concept in change requests)
    6. Filter by CR progress (Cancelled/Closed/Ongoing lifecycle state)
    7. Optional: evaluate PPVR impact and root cause with local LLM
    8. Display filtered results and export with date columns removed
    """
    # Lazy import breaks circular dependency with app.py while reusing shared UI/export helpers.
    from app import (
        build_ppvr_impact_sheets,
        dataframe_to_excel_bytes,
        dataframe_to_pdf_bytes,
        render_data_dictionary,
        render_ppvr_conclusion_banner,
        section_card_end,
        section_card_start,
    )

    tab_name = "Change request"

    # =========================================================================
    # SECTION A: INPUT COLLECTION
    # =========================================================================
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

    # 3) Analysis options
    st.markdown("### Analysis Options")
    st.caption("Select the options you want to use. For Summary and Impact on PPVR: selected means Yes, not selected means No.")

    ppvr_model = "llama3.2:1b"
    ppvr_base_url = "http://127.0.0.1:11434/v1"
    ppvr_configured = True

    # Change Request does NOT have the "Type of classification" option.
    option_definitions = {
        "CR Progress": ["Closed", "Cancelled", "Ongoing"],
        "Root cause": ["Supplier", "Equipment", "Human cause", "Procedure"],
    }

    binary_options = ["Summary", "Impact on PPVR"]
    selected_analysis_options: list[dict[str, str]] = []

    # Binary checkboxes (Summary, Impact on PPVR)
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
        st.info("PPVR analysis is disabled until the local LLM server is reachable.")

    # Multi-select options (CR Progress, Root cause)
    for option_name, values_for_option in option_definitions.items():
        option_token = option_name.lower().replace(" ", "_")

        is_selected = st.checkbox(
            f"Use {option_name}",
            value=False,
            key=f"use_{option_token}_{tab_name}",
        )

        selected_values: list[str] = []
        if is_selected:
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

    # 4) File upload (CSV, Excel only - no PDF/Word for this workflow)
    uploaded_file = st.file_uploader(
        "Upload file (CSV, Excel)",
        type=SUPPORTED_FILE_TYPES,
        key=f"upload_{tab_name}",
    )
    section_card_end()

    if not uploaded_file:
        st.info("Upload a file to begin analysis.")
        return

    # =========================================================================
    # SECTION B: FILE PARSING
    # =========================================================================
    try:
        parsed = parse_uploaded_file(uploaded_file)
    except Exception:
        st.error("The uploaded file could not be processed. Please check the file format and try again.")
        return

    if parsed["kind"] != "table":
        st.warning("Only CSV and Excel files support the filtering analysis. Please upload a spreadsheet file.")
        return

    # =========================================================================
    # SECTION C: FILTER EXECUTION (Change Request specific pipeline)
    # =========================================================================
    raw_df = parsed["data"]
    total_rows = len(raw_df)

    # Step 1: Apply timeline filter (Date occurred must fall within selected range)
    df_after_timeline, removed_timeline, date_col = filter_by_timeline(
        raw_df, timeline_start, timeline_end
    )

    # Step 2: Apply target-line filter (Title/Description must contain target line number)
    df_after_target, removed_target = filter_by_target_line(df_after_timeline, target_line)

    # Step 3: Skip classification filter (not applicable to Change Requests)
    df_after_classification = df_after_target
    removed_classification = 0

    # Step 4: Extract CR progress values and apply lifecycle-state filter
    cr_progress_values = []
    for option in selected_analysis_options:
        if option["Option"] == "CR Progress":
            selection_text = option["Selection"]
            if selection_text != "No value selected":
                cr_progress_values = [val.strip() for val in selection_text.split(",")]
            break

    df_final, removed_cr_progress, lifecycle_col, progress_counts = filter_by_deviation_progress(
        df_after_classification, cr_progress_values
    )

    # Step 5: Optional PPVR impact evaluation
    ppvr_impact_summary, ppvr_text_columns = ({}, [])
    ppvr_evaluation_error = ""
    ppvr_analysis_selected = False
    for option in selected_analysis_options:
        if option["Option"] == "Impact on PPVR":
            ppvr_analysis_selected = option["Selection"] == "Yes"
            break

    if ppvr_analysis_selected and ppvr_configured:
        try:
            with st.spinner("Evaluating PPVR impact with Ollama..."):
                ppvr_impact_summary, ppvr_text_columns = evaluate_ppvr_impact_with_local_llm_cr(
                    df_final,
                    model=ppvr_model,
                    base_url=ppvr_base_url,
                )
        except Exception as exc:
            ppvr_evaluation_error = str(exc)

    # Step 6: Optional root cause evaluation
    root_cause_summary, root_cause_text_columns = ({}, [])
    root_cause_error = ""
    root_cause_values = []
    for option in selected_analysis_options:
        if option["Option"] == "Root cause":
            selection_text = option["Selection"]
            if selection_text != "No value selected":
                root_cause_values = [val.strip() for val in selection_text.split(",")]
            break

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

    # =========================================================================
    # SECTION D: RESULTS TO USER
    # =========================================================================
    section_card_start("Result of Input Evaluation")

    if date_col is None:
        st.warning(
            "A 'Date occurred' column was not found in the file. "
            "Timeline filtering was skipped. "
            "Expected column name: 'Date occurred'."
        )
    if not target_line:
        st.warning("No target line was entered. Target line filtering was skipped.")

    # KPI Summary (Change Request: 5 metrics, no classification metric)
    summary_col1, summary_col2, summary_col3, summary_col4, summary_col5 = st.columns(5)
    summary_col1.metric("Total records in file", total_rows)
    summary_col2.metric("Removed — outside timeline", removed_timeline)
    summary_col3.metric("Removed — no target line match", removed_target)
    summary_col4.metric("Removed - CR progress filter", removed_cr_progress)
    summary_col5.metric("Records kept for analysis", len(df_final))

    if len(df_final) == 0:
        st.error("No records remain after filtering. Check your timeline and target line settings.")
        section_card_end()
        return

    # Display CR progress breakdown based on Lifecycle State
    if cr_progress_values and lifecycle_col:
        st.markdown("#### Selected CR Progress Results")
        selected_progress_results = []
        lifecycle_lower = df_final[lifecycle_col].astype(str).str.lower()
        for selected_progress in cr_progress_values:
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
                {"CR Progress": display_progress, "Fields": int(count)}
            )
        st.table(selected_progress_results)

    # Display PPVR impact evaluation results
    if ppvr_analysis_selected:
        st.markdown("#### PPVR Impact Evaluation")
        if ppvr_impact_summary:
            render_ppvr_conclusion_banner(ppvr_impact_summary)
            ppvr_results = [
                {"PPVR Assessment": label, "Fields": value}
                for label, value in ppvr_impact_summary.items()
            ]
            st.table(ppvr_results)
            st.caption("LLM review based on text in: " + ", ".join(ppvr_text_columns))
        elif ppvr_evaluation_error:
            st.warning(ppvr_evaluation_error)
        else:
            st.info("PPVR impact could not be evaluated because no PPVR text columns were detected.")

    # Display root cause evaluation results
    if root_cause_values:
        st.markdown("#### Selected Root Cause Results")
        if root_cause_summary:
            st.table(root_cause_summary)
            if root_cause_text_columns:
                st.caption("LLM review based on text in: " + ", ".join(root_cause_text_columns))
        else:
            st.warning(root_cause_error or "Root cause analysis could not return results.")

    # Display DV Numbers in Scope
    first_column_name = df_final.columns[0]
    st.markdown("#### DV Numbers in Scope")
    st.dataframe(
        df_final[[first_column_name]].astype(str).rename(columns={first_column_name: "DV Number"}),
        width="stretch",
        hide_index=True,
    )

    # Download section with date column removal for Change Request
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
            data=dataframe_to_excel_bytes(df_final, impact_sheets=impact_sheets, tab_name=tab_name),
            file_name=f"{tab_slug}_remaining_records.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_excel_{tab_name}",
        )
    else:
        st.download_button(
            label="Download remaining records as PDF",
            data=dataframe_to_pdf_bytes(df_final, tab_name=tab_name),
            file_name=f"{tab_slug}_remaining_records.pdf",
            mime="application/pdf",
            key=f"download_pdf_{tab_name}",
        )

    # Display full records (on-screen, not exported)
    st.markdown("#### Filtered Records")
    st.dataframe(df_final, width="stretch", hide_index=True)
    section_card_end()

    # Render field reference guide
    render_data_dictionary()
