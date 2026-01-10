# Claude Code Rules for MFViewer

## Context Management
- Reread this file after every conversation compression to refresh these rules

## Git Operations
- Do NOT add, commit, or push to GitHub unless explicitly asked by the user

## Error Handling
- Do NOT substitute stub or placeholder values - report errors instead
- If data is missing or unavailable, raise an error rather than guessing

## Scientific/Engineering Standards
- This is a scientific/engineering program that requires accuracy
- Results must be correct or the program should error out
- Never silently fail or produce approximate results without clear indication

## Units and Sample Rates
- Be extremely careful with units (e.g., RPM, Hz, seconds, milliseconds)
- Pay close attention to sample rates and ensure proper unit conversions
- Always verify unit consistency in calculations
- Document units clearly in code and comments when relevant
