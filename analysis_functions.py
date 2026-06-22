"""Helper functions for file parsing and baseline analysis.

The module is intentionally generic so it can support multiple use-cases
for Deviation and Change request workflows.
"""

from __future__ import annotations

import io
from collections import Counter
from typing import Any

import pandas as pd
from docx import Document
from pypdf import PdfReader
from streamlit.runtime.uploaded_file_manager import UploadedFile

SUPPORTED_FILE_TYPES = ["csv", "xlsx", "xls", "pdf", "docx"]


def parse_uploaded_file(uploaded_file: UploadedFile) -> dict[str, Any]:
	"""Parse uploaded file by extension and return standardized payload.

	Args:
		uploaded_file: Uploaded file object provided by Streamlit.

	Returns:
		A dictionary with normalized keys for table or text analysis.
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
