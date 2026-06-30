"""Analysis functions specific to the Deviation tab.

This module contains business logic filters and analysis functions that are
unique to the Deviation tab and not used by Change Request.
"""

from __future__ import annotations

import pandas as pd
from analysis_functions import find_column


def filter_by_classification(
	dataframe: pd.DataFrame,
	selected_values: list[str],
) -> tuple[pd.DataFrame, int, str | None, dict[str, int]]:
	"""Filter rows by classification column to match selected values (Minor/Major).

	This filter is Deviation-specific and is NOT applied to Change Request records,
	since change requests do not have a classification concept.

	Args:
		dataframe: Source dataset (already filtered by timeline and target line).
		selected_values: List of classification values to keep (e.g., ["Minor", "Major"]).

	Returns:
		Tuple of:
			- filtered_dataframe: DataFrame containing only rows that match the selected classifications
			- removed_row_count: Number of rows removed by this filter
			- matched_column_name_or_None: Name of the classification column (or None if not found)
			- classification_counts: Dictionary of classification value counts from the input
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
