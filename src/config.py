"""Runtime configuration -- loaded from .env. Replaces Luca's Step 0 stub."""
import os
from dotenv import load_dotenv

load_dotenv()

LIGHT_API_BASE_URL = os.environ.get("LIGHT_API_BASE_URL", "")
LIGHT_API_KEY = os.environ.get("LIGHT_API_KEY", "")

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

OUTPUT_FILE_PATH = os.environ.get("OUTPUT_FILE_PATH", "output/alert.txt")

AGING_THRESHOLDS = [
    int(x) for x in os.environ.get("AGING_THRESHOLDS", "7,14,30").split(",")
]
TIMEZONE = os.environ.get("TIMEZONE", "UTC")
