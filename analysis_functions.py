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
import re
from collections import Counter
from typing import Any

import pandas as pd
from docx import Document
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
