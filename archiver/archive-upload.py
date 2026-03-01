import os
import tarfile
import shutil
import logging
import time
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from b2sdk.v2 import InMemoryAccountInfo, B2Api

# -------- CONFIG --------
BASE = "/root/mbta-data"
LOG_FILE = "/root/mbta-data/archive-upload.log"

TIMEZONE = ZoneInfo("America/New_York")

B2_KEY_ID = os.environ["B2_KEY_ID"]
B2_APP_KEY = os.environ["B2_APP_KEY"]
B2_BUCKET_NAME = os.environ["B2_BUCKET_NAME"]

EMAIL_ALERT = os.environ["EMAIL_ALERT"]
EMAIL_FROM = os.environ["EMAIL_FROM"]
EMAIL_APP_PASSWORD = os.environ["EMAIL_APP_PASSWORD"]

# -------- LOGGING SETUP --------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)

# -------- GET PREVIOUS DAY --------
now_ny = datetime.now(TIMEZONE)
yesterday_ny = now_ny - timedelta(days=1)
DAY = yesterday_ny.strftime("%Y-%m-%d")

DAY_FOLDER = os.path.join(BASE, DAY)
OUTPUT_TAR = os.path.join(BASE, f"{DAY}.tar.gz")

start_time = time.monotonic()
logging.info("\n" + "=" * 60)
logging.info(f"Starting archive upload script for day {DAY}")

if not os.path.exists(DAY_FOLDER):
    logging.error(f"Folder {DAY_FOLDER} does not exist!")
    exit(1)

# -------- TAR PREVIOUS DAY --------
step_start = time.monotonic()
try:
    with tarfile.open(OUTPUT_TAR, "w:gz") as tar:
        tar.add(DAY_FOLDER, arcname=DAY)
    logging.info(f"Compressed {DAY_FOLDER} -> {OUTPUT_TAR}")
except Exception as e:
    logging.exception(f"Failed to compress folder {DAY_FOLDER}: {e}")
    exit(1)
logging.info(f"Compression took {time.monotonic() - step_start:.2f} seconds")

# -------- LOG SIZE --------
folder_size = sum(
    os.path.getsize(os.path.join(root, f))
    for root, _, files in os.walk(DAY_FOLDER)
    for f in files
)
tar_size = os.path.getsize(OUTPUT_TAR)
logging.info(f"Folder size: {folder_size}, tar size: {tar_size}")

# -------- UPLOAD TO BACKBLAZE --------
step_start = time.monotonic()
year = yesterday_ny.strftime("%Y")
month = yesterday_ny.strftime("%m")
file_name_in_b2 = f"{year}/{month}/{os.path.basename(OUTPUT_TAR)}"

info = InMemoryAccountInfo()
b2_api = B2Api(info)
b2_api.authorize_account("production", B2_KEY_ID, B2_APP_KEY)
bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)

uploaded_successfully = False
for attempt in range(1, 4):
    try:
        bucket.upload_local_file(local_file=OUTPUT_TAR, file_name=file_name_in_b2)
        logging.info(f"Uploaded {OUTPUT_TAR} to B2 as {file_name_in_b2}")
        uploaded_successfully = True
        break
    except Exception as e:
        logging.warning(f"Upload attempt {attempt} failed: {e}")
        time.sleep(5)

if not uploaded_successfully:
    logging.error(f"Failed to upload {OUTPUT_TAR} after 3 attempts")
    try:
        msg = EmailMessage()
        msg["Subject"] = f"MBTA archive upload FAILED for {DAY}"
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_ALERT
        msg.set_content(f"Failed to upload {OUTPUT_TAR} to B2 after 3 attempts.")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
            smtp.send_message(msg)
        logging.info(f"Sent failure email to {EMAIL_ALERT}")
    except Exception as e:
        logging.exception(f"Failed to send failure email: {e}")

logging.info(f"Upload step took {time.monotonic() - step_start:.2f} seconds")

# -------- CLEANUP LOCAL FILES --------
if uploaded_successfully:
    step_start = time.monotonic()
    try:
        shutil.rmtree(DAY_FOLDER)
        os.remove(OUTPUT_TAR)
        logging.info(f"Deleted folder {DAY_FOLDER} and tar {OUTPUT_TAR}")
    except Exception as e:
        logging.exception(f"Failed to cleanup local files: {e}")
    logging.info(f"Cleanup step took {time.monotonic() - step_start:.2f} seconds")
else:
    logging.info(f"Keeping {OUTPUT_TAR} locally for manual retry")


# -------- TOTAL RUNTIME --------
end_time = time.monotonic()
latency = end_time - start_time
logging.info(f"Completed archive upload for {DAY} in {latency:.2f} seconds")
