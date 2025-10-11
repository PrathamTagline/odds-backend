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
from sports.models import Event

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
        self.stdout.write(self.style.SUCCESS("\n🚀 Starting scraping...\n"))

        # Setup undetected Chrome
        chrome_options = uc.ChromeOptions()
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--headless")
        driver = uc.Chrome(options=chrome_options)

        # Inject JS hook for all new documents
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": CAPTURE_JS})

        # Random viewport
        width = random.randint(300, 1920)
        height = random.randint(500, 1080)
        driver.set_window_size(width, height)
        self.stdout.write(f"📐 Viewport set to width: {width}, height: {height}")

        try:
            # 1️⃣ Open main page and login
            self.stdout.write("\n🔐 Attempting login...")
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
                        self.stdout.write(self.style.SUCCESS("✅ Clicked 'Login with demo ID'"))
                        break
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error clicking login button: {e}"))

            # Wait for login to complete
            time.sleep(10)

            # 2️⃣ Query events with sport_type_id=4 only
            events = Event.objects.filter(sport__oid=4)
            self.stdout.write(self.style.SUCCESS(f"\n📋 Found {events.count()} events in database\n"))

            for idx, element in enumerate(events, 1):
                event_id = element.event_id
                event_name = element.event_name
                sport_id = element.sport.oid
                
                self.stdout.write(f"\n{'='*70}")
                self.stdout.write(self.style.WARNING(f"🎯 [{idx}/{events.count()}] Processing: {event_name}"))
                self.stdout.write(f"   Event ID: {event_id} | Sport ID: {sport_id}")
                self.stdout.write(f"{'='*70}")
                
                url = f"https://d247.com/game-details/{sport_id}/{event_id}/"
                self.stdout.write(f"🌐 Visiting: {url}")

                # Inject JS hook for capturing gamedataPrivate
                driver.execute_script(CAPTURE_JS)
                driver.get(url)
                self.stdout.write("⏳ Waiting for APIs to load (10s)...")
                time.sleep(10)

                # 3️⃣ Get captured gamedata
                captured = driver.execute_script("return window.__capturedGamedata || []")
                self.stdout.write(f"📦 Captured {len(captured)} API responses")
                
                if not captured:
                    self.stdout.write(self.style.WARNING(f"⚠️  No gamedata captured for {event_name}"))
                    continue

                processed_count = 0
                for item_idx, item in enumerate(captured, 1):
                    text = item.get("text")
                    url_path = item.get("url", "")
                    
                    if not text:
                        continue
                    
                    self.stdout.write(f"\n  🔍 [{item_idx}/{len(captured)}] Checking: {url_path}")
                    
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            keys = list(parsed.keys())
                            self.stdout.write(f"     📋 Response keys: {keys}")
                            
                            if "data" in parsed:
                                data_payload = parsed["data"]
                                data_type = type(data_payload).__name__
                                self.stdout.write(f"     📦 Data payload type: {data_type}")
                                
                                # Case 1: Encrypted string data
                                if isinstance(data_payload, str):
                                    self.stdout.write(f"     🔐 Attempting to decrypt string data...")
                                    try:
                                        decrypted_data = decrypt_data(data_payload, get_decryption_key())
                                        
                                        # Check structure without printing full data
                                        has_nested_data = isinstance(decrypted_data, dict) and "data" in decrypted_data
                                        if has_nested_data:
                                            nested_data = decrypted_data["data"]
                                            has_t1_t2 = isinstance(nested_data, dict) and ("t1" in nested_data or "t2" in nested_data)
                                        else:
                                            has_t1_t2 = False
                                        
                                        self.stdout.write(f"     ✅ Decryption successful")
                                        self.stdout.write(f"     📊 Structure: has_nested_data={has_nested_data}, has_t1_t2={has_t1_t2}")
                                        
                                        if has_nested_data and has_t1_t2:
                                            # Count events in t1 and t2
                                            t1_data = nested_data.get("t1", [])
                                            t1_count = len(t1_data) if isinstance(t1_data, list) else 0
                                            t2_data = nested_data.get("t2", [])
                                            t2_count = len(t2_data) if isinstance(t2_data, list) else 0
                                            self.stdout.write(f"     📊 Events found - t1: {t1_count}, t2: {t2_count}")
                                            
                                            redis_key = f"sport/{event_id}/4/decrypted_data"
                                            redis_service.set_data(redis_key, decrypted_data, expire=500)
                                            self.stdout.write(self.style.SUCCESS(f"     ✅ Saved decrypted odds data to Redis: {redis_key}"))

                                            # Store market IDs from converted data
                                            self.stdout.write(f"     🔧 Extracting market IDs...")
                                            store_market_ids(element, decrypted_data)
                                            processed_count += 1
                                        else:
                                            decrypted_type = type(decrypted_data).__name__
                                            decrypted_keys = list(decrypted_data.keys()) if isinstance(decrypted_data, dict) else "N/A"
                                            self.stdout.write(f"     ⏭️  Skipped - not odds data (type: {decrypted_type}, keys: {decrypted_keys})")
                                            
                                    except ValueError as e:
                                        self.stdout.write(self.style.ERROR(f"     ❌ Decryption failed: {e}"))
                                        redis_service.set_data(f"sport/{event_id}/4/plain_data", parsed)
                                        self.stdout.write(f"     💾 Saved plain data as fallback")
                                        
                                # Case 2: Dict data with potential nested encryption
                                elif isinstance(data_payload, dict):
                                    payload_keys = list(data_payload.keys())
                                    self.stdout.write(f"     📋 Data payload keys: {payload_keys}")
                                    
                                    if "t1" in data_payload:
                                        self.stdout.write(f"     🔐 Found 't1' key, attempting decryption...")
                                        try:
                                            decrypted_data = decrypt_data(data_payload["t1"], get_decryption_key())
                                            
                                            # Check decrypted structure
                                            decrypted_type = type(decrypted_data).__name__
                                            self.stdout.write(f"     ✅ Decryption successful (type: {decrypted_type})")
                                            
                                            redis_key = f"sport/{event_id}/4/decrypted_data"
                                            redis_service.set_data(redis_key, decrypted_data, expire=5)
                                            self.stdout.write(self.style.SUCCESS(f"     ✅ Saved decrypted odds data to Redis: {redis_key}"))

                                            # Store market IDs
                                            self.stdout.write(f"     🔧 Extracting market IDs...")
                                            store_market_ids(element, decrypted_data)
                                            processed_count += 1
                                            
                                        except ValueError as e:
                                            self.stdout.write(self.style.ERROR(f"     ❌ Decryption failed: {e}"))
                                            redis_service.set_data(f"sport/{event_id}/4/plain_data", parsed)
                                            self.stdout.write(f"     💾 Saved plain data as fallback")
                                    else:
                                        self.stdout.write(f"     ⏭️  No 't1' key, storing plain JSON")
                                        redis_service.set_data(f"sport/{event_id}/4/plain_data", parsed)
                                        
                                else:
                                    self.stdout.write(f"     ⏭️  Data not str or dict, storing plain")
                                    redis_service.set_data(f"sport/{event_id}/4/plain_data", parsed)
                                    
                            else:
                                self.stdout.write(f"     ⏭️  No 'data' key, storing plain JSON")
                                redis_service.set_data(f"sport/{event_id}/4/plain_data", parsed)
                                
                        else:
                            self.stdout.write(f"     ⏭️  Skipping non-dict response (type: {type(parsed).__name__})")
                            continue
                            
                    except json.JSONDecodeError as e:
                        self.stdout.write(self.style.ERROR(f"     ❌ JSON decode error: {e}"))
                        continue
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"     ❌ Error processing: {e}"))
                        import traceback
                        self.stdout.write(f"     📜 Traceback: {traceback.format_exc()}")

                # Summary for this event
                if processed_count > 0:
                    self.stdout.write(self.style.SUCCESS(f"\n✅ Successfully processed {processed_count} response(s) for {event_name}"))
                else:
                    self.stdout.write(self.style.WARNING(f"\n⚠️  No valid odds data processed for {event_name}"))

                # Clear captured array for next event
                driver.execute_script("window.__capturedGamedata = [];")

        finally:
            driver.quit()
            self.stdout.write(self.style.SUCCESS("\n\n✅ Scraping finished.\n"))