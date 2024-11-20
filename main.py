from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
import time
from PIL import Image
import pytesseract
import time
import re
import argparse

def google_earth_screenshot(latitude, longitude,
                                    altitude = 70,
                                    angle_of_view = 25,
                                    direction = 83,
                                    tilt = 0,
                                    delay = 1,
                                    path = 'page_screenshot.png'):
    # Configure Chrome Options
    chrome_options = Options()
    chrome_options.add_argument("window-size=10x10")

    # Set the path to ChromeDriver
    driver_path = '/Users/hli488/drivers/chromedriver-mac-arm64/chromedriver'

    # Initialize the driver service
    service = Service(executable_path=driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # Construct the URL with the specified parameters
    url = f"https://earth.google.com/web/@{latitude},{longitude},{altitude}a,{angle_of_view}d,{direction}y,{tilt}t"
    driver.get(url)

    # Retrieve the webpage
    previous_url = None
    time.sleep(delay)
    # Keep checking until URL is stabilized
    for _ in range(20):
        current_url = driver.current_url
        if current_url == previous_url:
            # URL has stabilized. -> Loading complete
            break
        previous_url = current_url
        time.sleep(1)  # Delay for half a second

    time.sleep(delay)

     # Take a screenshot of the entire page
    driver.save_screenshot(path)
    driver.quit()

def read_date_from_screenshot(path = 'page_screenshot.png'):
    # Open the screenshot and use OCR to extract text
    image = Image.open(path)
    text = pytesseract.image_to_string(image)

    # Search for the date using regex
    pattern = re.compile(r'Data attribution (\d{1,2}/\d{1,2}/\d{4}(?:-\w+)?)')
    match = pattern.search(text)

    if match:
        date_text = match.group(1)
        print("Date found:", date_text)
        return date_text
    else:
        print("Date not found. Check the screenshot to debug.")
        return None

# Main function we need to call, step 1: save the screenshot. step 2: extract the date info.
def read_date(latitude, longitude):
    google_earth_screenshot(latitude, longitude, delay = 1)
    read_date_from_screenshot()

# argparse
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Read data from Google Earth based on latitude and longitude.')
    parser.add_argument('latitude', type=float, help='Latitude of the location')
    parser.add_argument('longitude', type=float, help='Longitude of the location')
    args = parser.parse_args()

    result = read_date(args.latitude, args.longitude)
