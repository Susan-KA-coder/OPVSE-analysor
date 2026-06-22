# Deviation and Change Request Dashboard

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

## Run Locally

```powershell
cd c:\Users\RNUH\performance-board-python
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The app should open in your browser automatically.

## Notes

- This is the initial scaffold. Analysis logic is intentionally generic for now.
- You can now review the workflow, then we can add your detailed analysis rules in the next iteration.
- For a permanent team URL, follow [DEPLOYMENT.md](DEPLOYMENT.md).
