import os
import json
import requests
import redis
from typing import Any, Dict, Optional
from backend.services.crypt_service import decrypt_data, encrypt_data
from backend.services.gtoken_service import get_cookie_token

# -----------------------------
# Redis client setup
# -----------------------------
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=int(os.getenv("REDIS_DB", 0)),
)
REDIS_KEY_G_TOKEN = "G_TOKEN"


# -----------------------------
# Public API Functions
# -----------------------------

def get_tree_record(password: str) -> Any:
    """
    Fetch tree data from d247.com and decrypt it.

    Args:
        password (str): Password for AES decryption.

    Returns:
        Any: Decrypted response data.

    Raises:
        Exception: If 'data' field is missing in response.
    """
    url = "https://d247.com/api/front/treedata"
    payload = {"data": {}}

    res_json = fetch_api(url, method="POST", payload=payload)

    encrypted_data = res_json.get("data")
    if not encrypted_data:
        raise Exception("No 'data' field in response")

    return decrypt_data(encrypted_data, password)


def get_odds(sport_id: int, event_id: int, password: str) -> Any:
    """
    Fetch game odds (private) from d247.com and decrypt.

    Args:
        sport_id (int): Sport/event type ID.
        event_id (int): Game match ID.
        password (str): Password for AES encryption/decryption.

    Returns:
        Any: Decrypted response data.
    """
    url = f"https://d247.com/api/front/gamedataPrivate?etId={sport_id}&gmid={event_id}"
    payload = {
        "data": encrypt_data({"etid": sport_id, "gmid": event_id}, password=password)
    }

    res_json = fetch_api(url, method="POST", payload=payload)
    encrypted_data = res_json.get("data")
    if not encrypted_data:
        raise Exception("No 'data' field in response")

    return decrypt_data(encrypted_data, password)


def get_highlight_home_private(etid: int, password: str) -> Any:
    """
    Fetch highlight home private data and decrypt.

    Args:
        etid (int): Event type ID.
        password (str): Password for encryption/decryption.

    Returns:
        Any: Decrypted response data.
    """
    base_url = os.getenv("BASE_URL", "https://d247.com")
    url = f"{base_url}/front/highlighthomePrivate?etid={etid}"
    payload = {
        "data": encrypt_data({"etid": etid, "type": "all"}, password)
    }

    res_json = fetch_api(url, method="POST", payload=payload, timeout=5)
    encrypted_data = res_json.get("data")
    if not encrypted_data:
        raise Exception("No 'data' field in response")

    return decrypt_data(encrypted_data, password)


# -----------------------------
# Helper Functions
# -----------------------------

def fetch_api(
    url: str,
    method: str = "GET",
    payload: Optional[Dict] = None,
    headers: Optional[Dict] = None,
    timeout: int = 3
) -> Dict:
    """
    Fetch API with automatic g_token retrieval from Redis or Selenium.

    Args:
        url (str): API endpoint URL.
        method (str): HTTP method ("GET" or "POST").
        payload (Optional[Dict]): JSON payload for POST.
        headers (Optional[Dict]): Additional headers.
        timeout (int): Request timeout in seconds.

    Returns:
        Dict: JSON response.

    Raises:
        requests.HTTPError: If the HTTP request fails.
    """
    cookie_value = redis_client.get(REDIS_KEY_G_TOKEN)
    if cookie_value:
        cookie_value = cookie_value.decode("utf-8")
        resp = make_request(cookie_value, headers, url, method, payload, timeout)
        if resp.status_code == 401:  # Token expired → refresh
            cookie_value = refresh_gtoken()
            resp = make_request(cookie_value, headers, url, method, payload, timeout)
    else:
        # No cookie → fetch a new one
        cookie_value = refresh_gtoken()
        resp = make_request(cookie_value, headers, url, method, payload, timeout)

    resp.raise_for_status()
    return resp.json()


def refresh_gtoken() -> str:
    """
    Get a new g_token using Selenium/Playwright and store in Redis.

    Returns:
        str: g_token value.
    """
    cookie_value = get_cookie_token()
    redis_client.setex(REDIS_KEY_G_TOKEN, 3600, cookie_value)
    return cookie_value


def make_request(
    cookie_value: str,
    headers: Optional[Dict] = None,
    url: Optional[str] = None,
    method: str = "GET",
    payload: Optional[Dict] = None,
    timeout: int = 3
):
    """
    Makes HTTP request with given cookie.

    Args:
        cookie_value (str): g_token cookie string.
        headers (Optional[Dict]): Additional headers.
        url (str): API endpoint.
        method (str): HTTP method.
        payload (Optional[Dict]): JSON payload.
        timeout (int): Request timeout.

    Returns:
        requests.Response: Response object.
    """
    final_headers = {
        **(headers or {}),
        "Cookie": f"{cookie_value}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if method.upper() == "POST":
        return requests.post(url, headers=final_headers, json=payload, timeout=timeout)
    return requests.get(url, headers=final_headers, timeout=timeout)
