# OPV/SE Analyzor

This project is a Streamlit application with two main tabs:

- Deviation
- Change request

In each tab, users can:

- Upload CSV, Excel, PDF, or Word files
- Provide Timeline and Target line input
- View baseline analysis of uploaded data

## Project Structure

- app.py: Main Streamlit UI and tab layout
- analysis_functions.py: File parsing and analysis functions
- data_dictionary.py: Dictionary of common business fields

## Features Implemented

- Two tabs: Deviation and Change request
- File upload support:
	- CSV and Excel are parsed to data tables
	- PDF and Word are parsed to text
- Baseline analysis:
	- Row/column count for tables
	- Missing values per column
	- Numeric column statistics (min, max, mean, median, standard deviation)
	- Text metrics for PDF/Word (characters, words, top words)
- User prompts in each tab:
	- Timeline
	- Target line
- Data dictionary panel for consistent field naming

## Input Evaluation Flow

After uploading a CSV/Excel file, the app evaluates records in two steps:

1. Timeline filter
- Looks for `Date occurred` (case-insensitive variants are supported)
- Keeps only rows inside selected start/end dates
- Counts rows removed outside timeline

2. Target line filter
- Uses the numeric part of input (for example `DF50.1` -> `50.1`)
- Searches `Title` and `Description` columns for that numeric part
- 3-digit exception is supported (for example also matches `501`)
- Counts rows removed due to no target-line match

Then the app shows a `Result of Input Evaluation` section with:
- Total records in file
- Removed outside timeline
- Removed due to target-line mismatch
- Records kept for analysis
- DV numbers in scope (if `DV number` column exists)

## Expected Columns

For best results, include these columns in uploaded files:

- `Date occurred`
- `Title`
- `Description`
- `DV number`

The app also supports common naming variants, but the names above are recommended.

## Run Locally

```powershell
cd c:\Users\RNUH\performance-board-python
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The app should open in your browser automatically.

## PPVR Analysis Setup

PPVR analysis is optional and only works when an OpenAI-compatible API key is configured.

Set one of these in Streamlit secrets or environment variables:

- `PPVR_LLM_API_KEY` or `OPENAI_API_KEY`
- `PPVR_LLM_MODEL` or `OPENAI_MODEL` if you want to override the default model
- `PPVR_LLM_BASE_URL` or `OPENAI_BASE_URL` if you use a non-default API endpoint

For local development:

1. Copy [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example) to `.streamlit/secrets.toml`.
2. Replace the placeholder value with your real API key.
3. Restart Streamlit.

Example PowerShell session variable setup for the current terminal only:

```powershell
$env:PPVR_LLM_API_KEY = "your-api-key-here"
python -m streamlit run app.py
```

For Streamlit Community Cloud, add the same keys under App > Settings > Secrets.

## Notes

- This is the initial scaffold. Analysis logic is intentionally generic for now.
- You can now review the workflow, then we can add your detailed analysis rules in the next iteration.
- For a permanent team URL, follow [DEPLOYMENT.md](DEPLOYMENT.md).
