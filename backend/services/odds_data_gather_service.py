import json
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

class SimpleAPIScraper:
    def __init__(self, url):
        self.url = url
        self.driver = None
        
    def setup_driver(self):
        """Setup Chrome driver with network logging enabled"""
        chrome_options = Options()
        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.maximize_window()
        
    def get_api_payloads(self):
        """Get API payloads from browser logs"""
        logs = self.driver.get_log('performance')
        payloads = []
        
        for log in logs:
            try:
                message = json.loads(log['message'])['message']
                
                if message['method'] == 'Network.responseReceived':
                    response = message['params']['response']
                    url = response['url']
                    
                    # Filter for gamedataPrivate API
                    if 'gamedataPrivate' in url or 'gamedata' in url.lower():
                        request_id = message['params']['requestId']
                        
                        try:
                            response_body = self.driver.execute_cdp_cmd(
                                'Network.getResponseBody',
                                {'requestId': request_id}
                            )
                            
                            # Parse and return only the payload
                            try:
                                payload = json.loads(response_body.get('body', '{}'))
                                payloads.append({
                                    'url': url,
                                    'payload': payload,
                                    'timestamp': datetime.now().isoformat()
                                })
                            except:
                                payloads.append({
                                    'url': url,
                                    'payload': response_body.get('body', ''),
                                    'timestamp': datetime.now().isoformat()
                                })
                        except:
                            pass
            except:
                continue
        print(payload)
        return payloads
    
    def run(self):
        """Run the scraper"""
        print(f"Opening: {self.url}")
        
        try:
            # Load the page
            self.driver.get(self.url)
            print("Page loaded. Looking for demo login button...")
            
            # Click demo login button
            try:
                wait = WebDriverWait(self.driver, 15)
                demo_button = wait.until(
                    EC.element_to_be_clickable((By.XPATH, '//*[@id="root"]/div[2]/div/div/div[2]/form/div[3]/button[2]'))
                )
                print("Clicking demo login...")
                demo_button.click()
                time.sleep(5)
            except Exception as e:
                print(f"Error clicking demo button: {e}")
                return None
            
            # Navigate to game details page
            print(f"Navigating to: {self.url}")
            self.driver.get(self.url)
            time.sleep(5)
            
            # Get API payloads
            print("\nFetching API payloads...")
            payloads = self.get_api_payloads()
            
            if payloads:
                print(f"\n✓ Found {len(payloads)} API payloads:")
                for p in payloads:
                    print(f"\nURL: {p['url']}")
                    print(f"Payload: {json.dumps(p['payload'], indent=2)}")
                return payloads
            else:
                print("No API payloads found")
                return None
                
        except Exception as e:
            print(f"Error: {e}")
            return None
        finally:
            if self.driver:
                self.driver.quit()

def main():
    TARGET_URL = "https://d247.com/game-details/4/559593926"
    
    scraper = SimpleAPIScraper(TARGET_URL)
    scraper.setup_driver()
    
    # Get the payloads
    payloads = scraper.run()
    
    # Print results
    if payloads:
        print(f"\n{'='*50}")
        print(f"Total API payloads captured: {len(payloads)}")
        print(f"{'='*50}")

if __name__ == "__main__":
    main()