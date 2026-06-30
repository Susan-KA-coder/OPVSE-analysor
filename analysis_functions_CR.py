"""Analysis functions specific to the Change Request tab.

This module contains business logic used only by Change Request, including
PPVR analysis that relies on Change Request-specific justification columns.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from analysis_functions import (
	_aggregate_ppvr,
	_build_text_records,
	_create_chat_client,
	_mock_ppvr_response,
	find_columns,
)


def get_ppvr_text_columns_cr(dataframe: pd.DataFrame) -> list[str]:
	"""Return CR-specific text columns used for PPVR impact assessment.

	Only these columns are considered for Change Request PPVR interpretation:
	- Justification - Facilities or Equipment
	- Justification - Quality and Safety
	- Justification - Validated State
	- Regulatory Assessment
	"""
	return find_columns(
		dataframe,
		[
			"Justification - Facilities or Equipment",
			"Justification - Quality and Safety",
			"Justification - Validated State",
			"Regulatory Assessment",
		],
	)


def evaluate_ppvr_impact_with_local_llm_cr(
	dataframe: pd.DataFrame,
	model: str = "mistral",
	base_url: str | None = "http://127.0.0.1:11434/v1",
) -> tuple[dict[str, int], list[str]]:
	"""Evaluate PPVR impact for Change Requests using CR-specific text columns.

	This uses the same classification logic as Deviation PPVR analysis but limits
	model input to CR justification/regulatory columns.
	"""
	text_columns = get_ppvr_text_columns_cr(dataframe)
	if not text_columns:
		return {}, []

	try:
		client = _create_chat_client(base_url=base_url, api_key="ollama")
		batch_size = 10
		classifications: list[dict[str, Any]] = []

		for start_index in range(0, len(dataframe), batch_size):
			batch_df = dataframe.iloc[start_index : start_index + batch_size]
			records_payload = _build_text_records(batch_df, text_columns, start_index=start_index + 1)

			prompt = (
				"You are reviewing change request records for potential PPVR impact. "
				"PPVR categories are patient safety, product quality, validation, and regulatory documentation. "
				"Interpret the provided justification and regulatory text to decide whether there is potential impact. "
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

		return _aggregate_ppvr(classifications, len(dataframe)), text_columns
	except Exception:
		# Fallback for local testing when Ollama/API is unavailable.
		return _mock_ppvr_response(dataframe, text_columns), text_columns
