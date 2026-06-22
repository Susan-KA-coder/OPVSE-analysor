"""Helper functions for file parsing and input-evaluation analysis.

This module contains:
1) File parsing helpers for CSV/Excel/PDF/Word.
2) Generic summary/statistics utilities.
3) Business filters used by the app:
	- timeline filter via Date occurred
	- target line filter via Title/Description
"""

from __future__ import annotations

import io
import json
import re
from collections import Counter
from typing import Any

import pandas as pd
from docx import Document
from openai import OpenAI
from pypdf import PdfReader
from streamlit.runtime.uploaded_file_manager import UploadedFile

SUPPORTED_FILE_TYPES = ["csv", "xlsx", "xls", "pdf", "docx"]


def parse_uploaded_file(uploaded_file: UploadedFile) -> dict[str, Any]:
	"""Parse uploaded file by extension and return a normalized payload.

	Args:
		uploaded_file: Uploaded file object provided by Streamlit.

	Returns:
		A dictionary with the following keys:
			kind: "table" or "text"
			file_type: csv/excel/pdf/word
			data: pandas DataFrame (for tables)
			preview/analysis: text preview + metrics (for documents)
	"""
	file_name = uploaded_file.name.lower()

	if file_name.endswith(".csv"):
		dataframe = pd.read_csv(uploaded_file)
		return {
			"kind": "table",
			"file_type": "csv",
			"data": dataframe,
		}

	if file_name.endswith((".xlsx", ".xls")):
		dataframe = pd.read_excel(uploaded_file)
		return {
			"kind": "table",
			"file_type": "excel",
			"data": dataframe,
		}

	if file_name.endswith(".pdf"):
		raw_bytes = io.BytesIO(uploaded_file.getvalue())
		reader = PdfReader(raw_bytes)
		text = "\n".join((page.extract_text() or "") for page in reader.pages)
		return {
			"kind": "text",
			"file_type": "pdf",
			"preview": text[:4000],
			"analysis": build_text_analysis(text),
		}

	if file_name.endswith(".docx"):
		raw_bytes = io.BytesIO(uploaded_file.getvalue())
		document = Document(raw_bytes)
		text = "\n".join(paragraph.text for paragraph in document.paragraphs)
		return {
			"kind": "text",
			"file_type": "word",
			"preview": text[:4000],
			"analysis": build_text_analysis(text),
		}

	raise ValueError("Unsupported file format. Please upload CSV, Excel, PDF, or DOCX.")


def build_analysis_summary(dataframe: pd.DataFrame) -> dict[str, Any]:
	"""Build high-level, table-oriented analysis output.

	Args:
		dataframe: Uploaded tabular data.

	Returns:
		Summary dictionary with row/column counts and missing data.
	"""
	missing_counts = dataframe.isna().sum().to_dict()
	missing_counts = {key: int(value) for key, value in missing_counts.items()}

	return {
		"rows": int(dataframe.shape[0]),
		"columns": int(dataframe.shape[1]),
		"column_names": dataframe.columns.tolist(),
		"missing_values_by_column": missing_counts,
	}


def get_column_statistics(dataframe: pd.DataFrame, column_name: str) -> dict[str, float]:
	"""Return descriptive statistics for one numeric column.

	Args:
		dataframe: Source dataset.
		column_name: Selected numeric column.

	Returns:
		Basic descriptive statistics.
	"""
	series = dataframe[column_name].dropna()
	if series.empty:
		return {
			"count": 0.0,
			"min": 0.0,
			"max": 0.0,
			"mean": 0.0,
			"median": 0.0,
			"std_dev": 0.0,
		}

	return {
		"count": float(series.count()),
		"min": float(series.min()),
		"max": float(series.max()),
		"mean": float(series.mean()),
		"median": float(series.median()),
		"std_dev": float(series.std() if series.count() > 1 else 0.0),
	}


def find_column(dataframe: pd.DataFrame, candidates: list[str]) -> str | None:
	"""Find the first matching column name from a list of candidates (case-insensitive).

	Args:
		dataframe: Source dataframe.
		candidates: List of possible column name variants to search for.

	Returns:
		Matched column name as it appears in the dataframe, or None.
	"""
	# Build a case-insensitive lookup but preserve original column names.
	lower_map = {col.lower().strip(): col for col in dataframe.columns}
	for candidate in candidates:
		match = lower_map.get(candidate.lower().strip())
		if match is not None:
			return match
	return None


def find_columns(dataframe: pd.DataFrame, candidates: list[str]) -> list[str]:
	"""Find all matching column names from a list of candidates (case-insensitive)."""
	lower_map = {col.lower().strip(): col for col in dataframe.columns}
	matched_columns: list[str] = []
	for candidate in candidates:
		match = lower_map.get(candidate.lower().strip())
		if match is not None and match not in matched_columns:
			matched_columns.append(match)
	return matched_columns


def filter_by_timeline(
	dataframe: pd.DataFrame,
	start_date,
	end_date,
) -> tuple[pd.DataFrame, int, str | None]:
	"""Filter rows by the 'Date occurred' column within the given date range.

	Args:
		dataframe: Source dataset.
		start_date: Inclusive start date.
		end_date: Inclusive end date.

	Returns:
		Tuple of (filtered_dataframe, removed_row_count, matched_column_name_or_None).
	"""
	date_col = find_column(
		dataframe,
		["date occurred", "date_occurred", "dateoccurred", "date", "occurred date"],
	)
	if date_col is None:
		return dataframe, 0, None

	# Non-parseable dates become NaT and are excluded from the kept range.
	parsed_dates = pd.to_datetime(dataframe[date_col], errors="coerce")
	start = pd.Timestamp(start_date)
	end = pd.Timestamp(end_date)

	mask = (parsed_dates >= start) & (parsed_dates <= end)
	removed = int((~mask).sum())
	return dataframe[mask].reset_index(drop=True), removed, date_col


def filter_by_target_line(
	dataframe: pd.DataFrame,
	target_line: str,
) -> tuple[pd.DataFrame, int]:
	"""Filter rows by checking Title/Description for numeric target-line content.

	Args:
		dataframe: Source dataset (already timeline-filtered).
			target_line: Target line code to search for (e.g. DF50.1).

	Returns:
		Tuple of (filtered_dataframe, removed_row_count).
	"""
	if not target_line:
		return dataframe, 0

	title_col = find_column(dataframe, ["title", "name", "subject"])
	desc_col = find_column(dataframe, ["description", "desc", "details", "detail"])

	match = re.search(r"(\d{2,3}\.\d{1,2})", target_line)
	if match is None:
		return dataframe, 0

	# Use only the numeric portion, for example DF50.1 -> 50.1
	numeric_part = match.group(1).lower()
	search_terms = {numeric_part}

	# Exception: also match compact 3-digit representation such as 50.1 -> 501.
	compact_numeric = re.sub(r"\D", "", numeric_part)
	if len(compact_numeric) == 3:
		search_terms.add(compact_numeric)

	mask = pd.Series([False] * len(dataframe), index=dataframe.index)
	if title_col:
		title_series = dataframe[title_col].astype(str).str.lower()
		for term in search_terms:
			mask |= title_series.str.contains(term, na=False, regex=False)
	if desc_col:
		desc_series = dataframe[desc_col].astype(str).str.lower()
		for term in search_terms:
			mask |= desc_series.str.contains(term, na=False, regex=False)

	# If neither text column exists, do not remove anything in this step.
	if title_col is None and desc_col is None:
		return dataframe, 0

	removed = int((~mask).sum())
	return dataframe[mask].reset_index(drop=True), removed


def filter_by_classification(
	dataframe: pd.DataFrame,
	selected_values: list[str],
) -> tuple[pd.DataFrame, int, str | None, dict[str, int]]:
	"""Filter rows by classification column to match selected values (Minor/Major).

	Args:
		dataframe: Source dataset (already filtered by timeline and target line).
		selected_values: List of classification values to keep (e.g., ["Minor", "Major"]).

	Returns:
		Tuple of (filtered_dataframe, removed_row_count, matched_column_name_or_None, classification_counts).
	"""
	if not selected_values:
		return dataframe, 0, None, {}

	classification_col = find_column(
		dataframe,
		["classification", "type of classification", "type_of_classification", "class", "type"],
	)
	if classification_col is None:
		return dataframe, 0, None, {}

	# Get counts before filtering
	classification_counts = dataframe[classification_col].value_counts().to_dict()

	# Create mask for rows matching selected values (case-insensitive)
	mask = dataframe[classification_col].astype(str).str.lower().isin([val.lower() for val in selected_values])
	removed = int((~mask).sum())
	
	return dataframe[mask].reset_index(drop=True), removed, classification_col, classification_counts


def filter_by_deviation_progress(
	dataframe: pd.DataFrame,
	selected_values: list[str],
) -> tuple[pd.DataFrame, int, str | None, dict[str, int]]:
	"""Filter rows by lifecycle state column to match selected deviation progress values.

	Args:
		dataframe: Source dataset (already filtered by timeline, target line, and classification).
		selected_values: List of deviation progress values to keep (e.g., ["Closed", "Cancelled", "Ongoing"]).
		
		Matching: Uses partial/substring matching (case-insensitive).
		Special handling: If "Ongoing" is selected, it includes records that do NOT contain "Closed" and do NOT contain "Cancelled".

	Returns:
		Tuple of (filtered_dataframe, removed_row_count, matched_column_name_or_None, progress_counts).
	"""
	if not selected_values:
		return dataframe, 0, None, {}

	lifecycle_col = find_column(
		dataframe,
		["lifecycle state", "lifecycle_state", "lifecyclestate", "state", "status", "deviation progress"],
	)
	if lifecycle_col is None:
		return dataframe, 0, None, {}

	# Get counts before filtering
	progress_counts = dataframe[lifecycle_col].value_counts().to_dict()

	# Create mask for rows matching selected values (case-insensitive, partial matching)
	mask = pd.Series([False] * len(dataframe), index=dataframe.index)
	lifecycle_lower = dataframe[lifecycle_col].astype(str).str.lower()
	
	# Check if "Ongoing" is in selected values
	has_ongoing = any(val.lower() == "ongoing" for val in selected_values)
	other_values = [val for val in selected_values if val.lower() != "ongoing"]
	
	# If "Ongoing" is selected, include records that do NOT contain "Closed" or "Cancelled"
	if has_ongoing:
		ongoing_mask = ~(lifecycle_lower.str.contains("closed", na=False) | lifecycle_lower.str.contains("cancelled", na=False))
		mask |= ongoing_mask
	
	# For other selected values, use substring matching
	if other_values:
		for val in other_values:
			mask |= lifecycle_lower.str.contains(val.lower(), na=False, regex=False)
	
	removed = int((~mask).sum())
	
	return dataframe[mask].reset_index(drop=True), removed, lifecycle_col, progress_counts


def evaluate_ppvr_impact_with_llm(
	dataframe: pd.DataFrame,
	api_key: str,
	model: str,
	base_url: str | None = None,
) -> tuple[dict[str, int], list[str]]:
	"""Evaluate potential PPVR impact with an LLM across the filtered records."""
	text_columns = find_columns(
		dataframe,
		[
			"description",
			"desc",
			"details",
			"detail",
			"qa conclusion",
			"qa_conclusion",
			"qaconclusion",
			"conclusion",
			"justification of impact",
			"justification_of_impact",
			"impact justification",
		],
	)
	if not text_columns:
		return {}, []

	client = OpenAI(api_key=api_key, base_url=base_url)
	batch_size = 10
	classifications: list[dict[str, Any]] = []

	for start_index in range(0, len(dataframe), batch_size):
		batch_df = dataframe.iloc[start_index : start_index + batch_size]
		records_payload: list[dict[str, str | int]] = []
		for row_index, (_, row) in enumerate(batch_df.iterrows(), start=start_index + 1):
			record_text_parts = []
			for column_name in text_columns:
				cell_value = str(row.get(column_name, "") or "").strip()
				if cell_value:
					record_text_parts.append(f"{column_name}: {cell_value}")
			records_payload.append(
				{
					"record_id": row_index,
					"text": "\n".join(record_text_parts) if record_text_parts else "No relevant text provided.",
				}
			)

		prompt = (
			"You are reviewing deviation records for potential PPVR impact. "
			"PPVR categories are patient safety, product quality, validation, and regulatory documentation. "
			"Interpret the record text and decide whether there is potential impact. "
			"Return strict JSON only with the schema: "
			"{\"records\":[{\"record_id\":1,\"potential_ppvr_impact\":true,\"no_identified_impact\":false,\"unclear\":false,\"patient_safety\":false,\"product_quality\":true,\"validation\":false,\"regulatory_documentation\":false,\"rationale\":\"short rationale\"}]}. "
			"Mark no_identified_impact true only when the text clearly supports no impact. "
			"Mark unclear true when the text is insufficient or ambiguous. "
			"A record may affect more than one category."
		)

		response = client.chat.completions.create(
			model=model,
			messages=[
				{"role": "system", "content": prompt},
				{"role": "user", "content": json.dumps(records_payload, ensure_ascii=True)},
			],
			response_format={"type": "json_object"},
			temperature=0,
		)

		content = response.choices[0].message.content or "{\"records\": []}"
		parsed = json.loads(content)
		classifications.extend(parsed.get("records", []))

	impact_summary = {
		"Records reviewed": int(len(dataframe)),
		"Potential PPVR impact": 0,
		"No identified impact": 0,
		"Unclear / manual review": 0,
		"Patient safety": 0,
		"Product quality": 0,
		"Validation": 0,
		"Regulatory documentation": 0,
	}

	for classification in classifications:
		if classification.get("potential_ppvr_impact"):
			impact_summary["Potential PPVR impact"] += 1
		if classification.get("no_identified_impact"):
			impact_summary["No identified impact"] += 1
		if classification.get("unclear"):
			impact_summary["Unclear / manual review"] += 1
		if classification.get("patient_safety"):
			impact_summary["Patient safety"] += 1
		if classification.get("product_quality"):
			impact_summary["Product quality"] += 1
		if classification.get("validation"):
			impact_summary["Validation"] += 1
		if classification.get("regulatory_documentation"):
			impact_summary["Regulatory documentation"] += 1

	return impact_summary, text_columns


def summarize_selected_root_causes(
	dataframe: pd.DataFrame,
	selected_values: list[str],
) -> tuple[list[dict[str, int | str]], str | None]:
	"""Count filtered records by the selected root cause values."""
	if not selected_values:
		return [], None

	root_cause_col = find_column(
		dataframe,
		["root cause", "root_cause", "rootcause", "cause", "cause category", "cause_category"],
	)
	if root_cause_col is None:
		return [], None

	root_cause_lower = dataframe[root_cause_col].astype(str).str.lower()
	root_cause_summary: list[dict[str, int | str]] = []
	for selected_value in selected_values:
		count = root_cause_lower.str.contains(selected_value.lower(), na=False, regex=False).sum()
		root_cause_summary.append({"Root Cause": selected_value, "Fields": int(count)})

	return root_cause_summary, root_cause_col


def build_text_analysis(text: str) -> dict[str, Any]:
	"""Generate simple text analysis for PDF and Word uploads.

	Args:
		text: Extracted text from file.

	Returns:
		Dictionary with character count, word count, and common words.
	"""
	words = [word.strip(".,;:!?()[]{}\"'").lower() for word in text.split()]
	words = [word for word in words if word]

	common_words = Counter(words).most_common(10)
	return {
		"characters": len(text),
		"words": len(words),
		"top_10_words": common_words,
	}
