"""
Centralized configuration for the procurement agent demo.
All environment-dependent values live here so the rest of the
codebase never hard-codes secrets or connection strings.
"""

import os
from dotenv import load_dotenv

load_dotenv()
# ---------------------------------------------------------------------------
# Azure OpenAI
# ---------------------------------------------------------------------------
AZURE_ENDPOINT = "https://gw-sb-aoai-01.openai.azure.com/"
AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_DEPLOYMENT = "gpt-5-mini"
AZURE_API_VERSION = "2024-12-01-preview"

# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://frank:@localhost:5432/procurement_agent",
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# Path to the teammate's scoring contract (relative to project root)
METRIC_CONTRACT_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "analytics",
    "metric_contract.yaml",
)
