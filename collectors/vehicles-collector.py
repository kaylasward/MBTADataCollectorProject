import os
import json
import time
import requests
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

# -------- CONFIG --------
BASE = "/root/mbta-data"
TIMEZONE = ZoneInfo("America/New_York")
URL = "https://api-v3.mbta.com/vehicles"
API_KEY = os.getenv("MBTA_API_KEY")


# -------- HELPERS --------
def log_line(path, run_id, timestamp, http_status, **fields):
    parts = [
        f'run_id="{run_id}"',
        f'timestamp="{timestamp}"',
        f'http_status="{http_status}"',
    ]
    for k, v in fields.items():
        parts.append(f'{k}="{v}"')
    with open(path, "a", encoding="utf-8") as f:
        f.write(" | ".join(parts) + "\n")


def get_paths(now):
    """Return JSONL file path and daily log path."""
    date_folder = now.strftime("%Y-%m-%d")
    file_folder_path = os.path.join(BASE, date_folder, "vehicles")
    os.makedirs(file_folder_path, exist_ok=True)
    filename = now.strftime("vehicles_%Y-%m-%d_%H.jsonl")
    file_path = os.path.join(file_folder_path, filename)

    log_folder = os.path.join(BASE, date_folder)
    os.makedirs(log_folder, exist_ok=True)
    log_path = os.path.join(log_folder, f"vehicles-{date_folder}.log")

    return file_path, log_path, filename


# -------- COLLECT --------
def collect_vehicles():
    now = datetime.now(TIMEZONE)
    run_id = str(uuid.uuid4())
    file_path, log_path, filename = get_paths(now)

    start = time.monotonic()
    try:
        headers = {}
        if API_KEY:
            headers["x-api-key"] = API_KEY
        r = requests.get(URL, headers=headers, timeout=5)
        r.raise_for_status()
        data = r.json()
        http_status = r.status_code
        vehicles = data.get("data", [])
        latency = time.monotonic() - start

        line = {
            "run_id": run_id,
            "timestamp": now.isoformat(),
            "num_vehicles": len(vehicles),
            "data": vehicles,
        }

        log_line(
            log_path,
            run_id,
            now.isoformat(),
            http_status,
            latency=f"{latency:.2f}s",
            vehicles=len(vehicles),
            file=filename,
        )

    except requests.exceptions.RequestException as e:
        latency = time.monotonic() - start

        http_status = None
        if hasattr(e, "response") and e.response is not None:
            http_status = e.response.status_code

        line = {
            "run_id": run_id,
            "timestamp": now.isoformat(),
            "http_status": http_status,
            "latency": round(latency, 2),
            "error_type": type(e).__name__,
            "error": str(e),
            "data": None,
        }

        log_line(
            log_path,
            run_id,
            now.isoformat(),
            http_status,
            latency=f"{latency:.2f}s",
            error_type=type(e).__name__,
            error=str(e),
        )

    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


if __name__ == "__main__":
    collect_vehicles()
