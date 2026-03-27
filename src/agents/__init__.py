"""Agent definitions for the Event Analysis Team."""

from .base import BaseAgent
from .event_identifier import EventIdentifierAgent
from .macro_analyst import MacroAnalystAgent
from .geopolitical_analyst import GeopoliticalAnalystAgent
from .micro_analyst import MicroAnalystAgent
from .investment_analyst import InvestmentAnalystAgent
from .history_ethics_analyst import HistoryEthicsAnalystAgent
from .devils_advocate import DevilsAdvocateAgent
from .report_synthesizer import ReportSynthesizerAgent

__all__ = [
    "BaseAgent",
    "EventIdentifierAgent",
    "MacroAnalystAgent",
    "GeopoliticalAnalystAgent",
    "MicroAnalystAgent",
    "InvestmentAnalystAgent",
    "HistoryEthicsAnalystAgent",
    "DevilsAdvocateAgent",
    "ReportSynthesizerAgent",
]
