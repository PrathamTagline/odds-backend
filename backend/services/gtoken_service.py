import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def get_cookie_token():
    # -----------------------------
    # Chrome options (headless)
    # -----------------------------
    options = Options()
    options.add_argument("--headless=new")  # headless mode (Chrome 109+)
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--enable-features=NetworkService,NetworkServiceInProcess")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    )

    # -----------------------------
    # ChromeDriver service (auto-download)
    # -----------------------------
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get("https://d247.com/")

        # -----------------------------
        # Wait for iframes and check login button
        # -----------------------------
        g_token = None

        try:
            iframes = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.TAG_NAME, "iframe"))
            )
            for iframe in iframes:
                driver.switch_to.frame(iframe)
                try:
                    login_button = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable(
                            (By.XPATH, "//button[contains(text(), 'Login with demo ID')]")
                        )
                    )
                    login_button.click()
                    break
                except:
                    driver.switch_to.default_content()
            else:
                # fallback: check main page
                driver.switch_to.default_content()
                login_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(text(), 'Login with demo ID')]")
                    )
                )
                login_button.click()
        except:
            # fallback if no iframe
            login_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(text(), 'Login with demo ID')]")
                )
            )
            login_button.click()

        # -----------------------------
        # Wait for cookies to be set
        # -----------------------------
        WebDriverWait(driver, 10).until(
            lambda d: any(c['name'] == 'g_token' for c in d.get_cookies())
        )

        # -----------------------------
        # Extract g_token cookie
        # -----------------------------
        for cookie in driver.get_cookies():
            if cookie["name"] == "g_token":
                g_token = f"{cookie['name']}={cookie['value']};"
                break

        return g_token

    finally:
        driver.quit()

