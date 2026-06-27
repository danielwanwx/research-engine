"""Built-in Research Engine connectors."""

from .agent_reach import AgentReachBridgeConnector
from .base import Connector
from .external import ExternalJsonlConnector
from .finance import FinanceQuoteConnector
from .github_public import GitHubPublicSearchConnector
from .manual import ManualConnector
from .opencli import OpenCliBridgeConnector
from .web import WebPageConnector

__all__ = [
    "AgentReachBridgeConnector",
    "Connector",
    "ExternalJsonlConnector",
    "FinanceQuoteConnector",
    "GitHubPublicSearchConnector",
    "ManualConnector",
    "OpenCliBridgeConnector",
    "WebPageConnector",
]
