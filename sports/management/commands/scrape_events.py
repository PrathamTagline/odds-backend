import time
import random
import json
from django.core.management.base import BaseCommand
from django.db.models import Q
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from backend.services.crypt_service import decrypt_data
from sports.models import Event  # <-- replace with your actual Event model

# -------------------------
# Redis helper functions
# -------------------------
import redis
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

def set_ex_redis_data(key, value, ex_seconds=5):
    redis_client.set(key, json.dumps(value), ex=ex_seconds)

# -------------------------
# JS hook for capturing gamedataPrivate responses
# -------------------------
CAPTURE_JS = r"""
(function() {
  if (window.__gamedataHookInstalled) return;
  window.__gamedataHookInstalled = true;
  window.__capturedGamedata = [];

  const tryPush = (url, text) => {
    if (/gamedataPrivate/.test(url)) {
      window.__capturedGamedata.push({url, text, ts: Date.now()});
    }
  };

  const _fetch = window.fetch;
  if (_fetch) {
    window.fetch = function() {
      return _fetch.apply(this, arguments).then(async function(response) {
        try {
          const clone = response.clone();
          const ct = clone.headers.get('content-type') || '';
          if (ct.indexOf('application/json') !== -1) {
            const text = await clone.text();
            tryPush(clone.url, text);
          }
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
        driver = uc.Chrome(options=options)

        # Inject JS hook for capturing gamedataPrivate
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
                        btn.click()
                        self.stdout.write("Clicked 'Login with demo ID'")
                        break
            except Exception as e:
                self.stdout.write(f"Error clicking login button: {e}")

            # Wait for login to complete (adjust selector if needed)
            time.sleep(3)

            # 2️⃣ Query events with sport_type_id=4
            events = Event.objects.filter(sport__event_type_id=4)
            self.stdout.write(f"Found {events.count()} events in database")

            for element in events:
                event_id = element.event_id  # External ID expected by site
                sport_id = element.sport.oid  # Use the correct field for URL
                url = f"https://d247.com/game-details/{sport_id}/{event_id}/"

                driver.get(url)
                # time.sleep(3)  # wait for APIs to fire

                # 3️⃣ Get captured gamedata
                captured = driver.execute_script("return window.__capturedGamedata || []")
                if not captured:
                    self.stdout.write(f"No gamedata captured for event {event_id}")
                    continue

                for item in captured:
                    text = item.get("text")
                    if not text:
                        continue
                    try:
                        parsed = json.loads(text)
                        data_payload = parsed.get("data", text)
                        decrypted = decrypt_data(data_payload, "YOUR_PASSWORD_HERE")
                        set_ex_redis_data(f"events-odds/{event_id}", decrypted, ex_seconds=5)
                        self.stdout.write(f"Saved decrypted data for event {event_id}")
                    except Exception as e:
                        self.stdout.write(f"Error decrypting event {event_id}: {e}")

                # Clear captured array for next event
                driver.execute_script("window.__capturedGamedata = [];")

        finally:
            driver.quit()
            self.stdout.write("Scraping finished.")

