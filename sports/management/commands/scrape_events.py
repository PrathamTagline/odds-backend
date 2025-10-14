import time
import random
import json
import os
from django.core.management.base import BaseCommand
from django.db.models import Q
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from backend.services.crypt_service import decrypt_data
from backend.services.tasks import expire_redis_key
from backend.services.store_market_ids import store_market_ids
from backend.services.redis_service import redis_service
from sports.models import Event  # <-- replace with your actual Event model

def get_decryption_key():
    """Fetch DECRYPTION_KEY from environment with default."""
    return os.getenv("DECRYPTION_KEY", "cae7b808-8b1e-4f47-87a5-1a4b6a08030e")

# -------------------------
# Redis helper functions (using RedisService)
# -------------------------
def set_ex_redis_data(key, value, ex_seconds=1500):
    # Set the key with value using RedisService
    redis_service.set_data(key, value, expire=ex_seconds)
    # Schedule task to expire key after ex_seconds (set to empty)
    expire_redis_key.apply_async(args=[key], countdown=ex_seconds)

# -------------------------
# JS hook for capturing gamedataPrivate responses
# -------------------------
CAPTURE_JS = r"""
(function() {
  if (window.__gamedataHookInstalled) return;
  window.__gamedataHookInstalled = true;
  window.__capturedGamedata = [];

  const tryPush = (url, text) => {
    window.__capturedGamedata.push({url, text, ts: Date.now()});
  };

  const _fetch = window.fetch;
  if (_fetch) {
    window.fetch = function() {
      return _fetch.apply(this, arguments).then(async function(response) {
        try {
          const clone = response.clone();
          const text = await clone.text();
          tryPush(clone.url, text);
        } catch(e){}
        return response;
      });
    };
  }

  const _open = XMLHttpRequest.prototype.open;
  const _send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url) {
    this.__requestedUrl = url;
    return _open.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function(body) {
    this.addEventListener && this.addEventListener('readystatechange', function() {
      if(this.readyState === 4 && this.responseText){
        tryPush(this.__requestedUrl, this.responseText);
      }
    });
    return _send.apply(this, arguments);
  };

  const _WebSocket = window.WebSocket;
  window.WebSocket = function(...args) {
    const ws = new _WebSocket(...args);
    ws.addEventListener('message', function(event) {
      tryPush(args[0], event.data);
    });
    return ws;
  };
})();
"""

# -------------------------
# Django Management Command
# -------------------------
class Command(BaseCommand):
    help = "Login first, then scrape events for sport_type_id=4 and store in Redis"

    def handle(self, *args, **options):
        self.stdout.write("Starting scraping...")

        # Setup undetected Chrome
        options = uc.ChromeOptions()
        options.add_argument("--disable-notifications")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-features=VizDisplayCompositor")
        options.add_argument("--headless=new") 
        driver = uc.Chrome(options=options)

        # Inject JS hook for all new documents
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": CAPTURE_JS})

        # Random viewport
        width = random.randint(300, 1920)
        height = random.randint(500, 1080)
        driver.set_window_size(width, height)
        self.stdout.write(f"Viewport set to width: {width}, height: {height}")

        try:
            # 1️⃣ Open main page and login
            driver.get("https://d247.com/")
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )

            # Find and click "Login with demo ID" button
            try:
                buttons = driver.find_elements(By.TAG_NAME, "button")
                for btn in buttons:
                    if "Login with demo ID" in btn.text:
                        driver.execute_script("arguments[0].click();", btn)
                        self.stdout.write("Clicked 'Login with demo ID'")
                        break
            except Exception as e:
                self.stdout.write(f"Error clicking login button: {e}")

            # Wait for login to complete (adjust selector if needed)
            time.sleep(10)

            # 2️⃣ Query events with sport_type_id=4
            events = Event.objects.filter(sport__oid=4)
            self.stdout.write(f"Found {events.count()} events in database")

            for element in events:
                event_id = element.event_id  # External ID expected by site
                sport_id = element.sport.oid  # Use the correct field for URL
                self.stdout.write(f"Processing event {event_id}, sport_id {sport_id}")
                url = f"https://d247.com/game-details/{sport_id}/{event_id}/"
                self.stdout.write(f"Visiting {url}")

                # Inject JS hook for capturing gamedataPrivate
                driver.execute_script(CAPTURE_JS)
                driver.get(url)
                time.sleep(10)  # wait for APIs to fire
                

                # 3️⃣ Get captured gamedata
                captured = driver.execute_script("return window.__capturedGamedata || []")
                self.stdout.write(f"Captured {len(captured)} items for event {event_id}")
                if not captured:
                    self.stdout.write(f"No gamedata captured for event {event_id}")
                    continue

                for item in captured:
                    text = item.get("text")
                    if not text:
                        continue
                    self.stdout.write(f"Captured from {item.get('url')}: {text[:200]}...")
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            self.stdout.write(f"Captured keys for event {event_id}: {list(parsed.keys())}")
                            if "data" in parsed:
                                data_payload = parsed["data"]
                                if isinstance(data_payload, str):
                                    try:
                                        decrypted_data = decrypt_data(data_payload, get_decryption_key())
                                        # Check if this is the odds data (has t1 or t2 in data)
                                        if isinstance(decrypted_data, dict) and "data" in decrypted_data and isinstance(decrypted_data["data"], dict) and ("t1" in decrypted_data["data"] or "t2" in decrypted_data["data"]):
                                            redis_service.set_data(f"sport/{event_id}/4/decrypted_data", decrypted_data, expire=500)
                                            self.stdout.write(f"Saved decrypted odds data for event {event_id}")

                                            # Store market IDs from converted data
                                            store_market_ids(element, decrypted_data)
                                        else:
                                            self.stdout.write(f"Skipped non-odds data for event {event_id}: {decrypted_data}")
                                    except ValueError as e:
                                        self.stdout.write(f"Decryption failed for event {event_id}: {e}")
                                        # Store plain data as fallback
                                        redis_service.set_data(f"sport/{event_id}/4/plain_data", parsed)
                                        self.stdout.write(f"Saved plain data for event {event_id} due to decryption failure")
                                elif isinstance(data_payload, dict):
                                    if "t1" in data_payload:
                                        try:
                                            decrypted_data = decrypt_data(data_payload["t1"], get_decryption_key())
                                            redis_service.set_data(f"sport/{event_id}/4/decrypted_data", decrypted_data, expire=500)
                                            self.stdout.write(f"Saved decrypted odds data for event {event_id}")

                                            # Store market IDs from converted data
                                            store_market_ids(element, decrypted_data)
                                        except ValueError as e:
                                            self.stdout.write(f"Decryption failed for event {event_id}: {e}")
                                            # Store plain data as fallback
                                            redis_service.set_data(f"sport/{event_id}/4/plain_data", parsed)
                                            self.stdout.write(f"Saved plain data for event {event_id} due to decryption failure")
                                    else:
                                        # No 't1', store plain JSON
                                        redis_service.set_data(f"sport/{event_id}/4/plain_data", parsed)
                                        self.stdout.write(f"Saved plain data for event {event_id} (no 't1' in data)")
                                else:
                                    # data not str or dict, store plain
                                    redis_service.set_data(f"sport/{event_id}/4/plain_data", parsed)
                                    self.stdout.write(f"Saved plain data for event {event_id} (data not str or dict)")
                            else:
                                # No 'data' key, store plain JSON
                                redis_service.set_data(f"sport/{event_id}/4/plain_data", parsed)
                                self.stdout.write(f"Saved plain data for event {event_id} (no 'data' key)")
                        else:
                            self.stdout.write(f"Skipping non-dict response for event {event_id}: {type(parsed)} - {parsed}")
                            continue
                    except json.JSONDecodeError as e:
                        self.stdout.write(f"JSON decode error for event {event_id}: {e}")
                        continue
                    except Exception as e:
                        self.stdout.write(f"Other error processing event {event_id}: {e}")

                # Clear captured array for next event
                driver.execute_script("window.__capturedGamedata = [];")

        finally:
            driver.quit()
            self.stdout.write("Scraping finished.")