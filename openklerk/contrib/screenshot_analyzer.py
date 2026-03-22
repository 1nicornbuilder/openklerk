"""
Screenshot analyzer -- LLM analyzes portal screenshots to generate draft filers.

Re-exports the analyzer from the intelligence module for convenience.
"""
from openklerk.intelligence.analyzer import analyze_screenshots

__all__ = ["analyze_screenshots"]
