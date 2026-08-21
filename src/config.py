"""Runtime configuration -- loaded from .env. Replaces Luca's Step 0 stub."""
import os
from dotenv import load_dotenv

load_dotenv()

USE_MOCK_DATA = os.getenv("USE_MOCK_DATA", "true").lower() == "true"

LIGHT_API_KEY = os.getenv("LIGHT_API_KEY", "")
LIGHT_API_BASE_URL = os.getenv("LIGHT_API_BASE_URL", "https://api.light.inc")

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID", "")

OUTPUT_MODE = os.getenv("OUTPUT_MODE", "console")  # console | file | slack
OUTPUT_FILE_PATH = os.getenv("OUTPUT_FILE_PATH", "output/alert.txt")

TIMEZONE = os.getenv("TIMEZONE", "UTC")
AGING_THRESHOLDS = [int(x) for x in os.getenv("AGING_THRESHOLDS", "7,14,30").split(",")]

SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "09:00")  # daily digest, stretch goal only


def validate():
    if not USE_MOCK_DATA and not LIGHT_API_KEY:
        raise EnvironmentError("LIGHT_API_KEY is required when USE_MOCK_DATA=false")
    if OUTPUT_MODE == "slack" and not SLACK_WEBHOOK_URL:
        raise EnvironmentError("SLACK_WEBHOOK_URL required when OUTPUT_MODE=slack")
