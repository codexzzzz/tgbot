import requests
import base64
import os
from datetime import datetime, timedelta

IMGBB_API_KEY = os.environ.get("IMGBB_API_KEY", "")

PERMANENT_EXPIRATION = None
TEMP_EXPIRATION_DAYS = 14
TEMP_EXPIRATION_SECONDS = TEMP_EXPIRATION_DAYS * 24 * 3600


def upload_image(image_bytes: bytes, is_premium: bool) -> dict:
    """Upload image to imgBB. Returns dict with url, delete_url, expires_at."""
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    params = {"key": IMGBB_API_KEY}
    data = {"image": b64}

    if not is_premium:
        data["expiration"] = str(TEMP_EXPIRATION_SECONDS)

    response = requests.post("https://api.imgbb.com/1/upload", params=params, data=data, timeout=30)
    response.raise_for_status()
    result = response.json()

    if not result.get("success"):
        raise Exception(f"imgBB error: {result}")

    img_data = result["data"]
    url = img_data["url"]
    delete_url = img_data.get("delete_url", "")

    if is_premium:
        expires_at = None
    else:
        expires_at = (datetime.utcnow() + timedelta(days=TEMP_EXPIRATION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "url": url,
        "delete_url": delete_url,
        "expires_at": expires_at,
    }
