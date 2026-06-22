"""Data dictionary definitions used by the dashboard."""

from __future__ import annotations

DATA_DICTIONARY = {
    "DV number": "Unique deviation identifier (e.g. DV-2025-001).",
    "Date occurred": "Date the deviation or change request occurred. Used for timeline filtering.",
    "Title": "Short title of the record. Used for target line filtering.",
    "Description": "Detailed description of the record. Used for target line filtering.",
    "owner": "Responsible person or team.",
    "department": "Business unit or functional group.",
    "status": "Current state such as open, in progress, or closed.",
    "priority": "Urgency level for processing the record.",
    "target_line": "User-provided target line code (format: DF07.01).",
}
