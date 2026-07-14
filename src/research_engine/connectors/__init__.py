"""Built-in Research Engine connectors."""

from .agent_reach import AgentReachBridgeConnector
from .base import Connector
from .external import ExternalJsonlConnector
from .finance import FinanceQuoteConnector
from .github_public import GitHubPublicSearchConnector
from .job_discovery import OfficialJobDiscoveryConnector
from .manual import ManualConnector
from .opencli import OpenCliBridgeConnector
from .web import WebPageConnector
from .xai_discovery import XaiDiscoveryConnector

__all__ = [
    "AgentReachBridgeConnector",
    "Connector",
    "ExternalJsonlConnector",
    "FinanceQuoteConnector",
    "GitHubPublicSearchConnector",
    "OfficialJobDiscoveryConnector",
    "ManualConnector",
    "OpenCliBridgeConnector",
    "WebPageConnector",
    "XaiDiscoveryConnector",
]
