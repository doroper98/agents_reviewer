"""Agent definitions for the Event Analysis Team."""

from .base import BaseAgent
from .event_identifier import EventIdentifierAgent
from .macro_analyst import MacroAnalyst
from .geopolitical_analyst import GeopoliticalAnalyst
from .micro_analyst import MicroAnalyst
from .investment_analyst import InvestmentAnalyst
from .history_ethics_analyst import HistoryEthicsAnalyst
from .devils_advocate import DevilsAdvocateAgent
from .report_synthesizer import ReportSynthesizer

__all__ = [
    "BaseAgent",
    "EventIdentifierAgent",
    "MacroAnalyst",
    "GeopoliticalAnalyst",
    "MicroAnalyst",
    "InvestmentAnalyst",
    "HistoryEthicsAnalyst",
    "DevilsAdvocateAgent",
    "ReportSynthesizer",
]
