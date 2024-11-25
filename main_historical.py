import os
import re
import time
import base64
from datetime import datetime

import pytesseract
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

def extract_date_from_url(driver):
    url = driver.current_url
    # Extract the `data` parameter from the URL
    match = re.search(r"data=([^&]+)", url)
    if not match:
        print("No `data` parameter found in the URL.")
        return None

    # Extract the encoded data
    encoded_data = match.group(1)

    # Decode the base64-like data (if applicable)
    try:
        decoded_data = base64.b64decode(encoded_data + "===")  # Add padding for base64
        decoded_text = decoded_data.decode('utf-8', errors='ignore')
    except Exception as e:
        print("Failed to decode the data:", e)
        return None

    # Search for a date in the decoded text
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", decoded_text)
    if date_match:
        return date_match.group(1)
    else:
        print("No date found in the decoded data.")
        return None

def is_date_after(date_string, year):
    # Parse the date string into a datetime object
    date = datetime.strptime(date_string, "%Y-%m-%d")
    # Define the cutoff date (end of 2020)
    cutoff_date = datetime(int(year), 1, 1)
    # Check if the date is after the cutoff date
    return date > cutoff_date

def find_text(ocr_data, searching_text):
    results = []

    # Search for the text and collect its positions
    for i, text in enumerate(ocr_data['text']):
        if searching_text in text:
            x, y = ocr_data['left'][i], ocr_data['top'][i]
            results.append((x,y))

    return results


def find_symbols(ocr_data, showing_crop = False):
    results = {"<":[], ">":[]}

    # Search for the symbols and collect their positions
    for i, text in enumerate(ocr_data['text']):
        if text in ["<", ">"]:
            x = ocr_data['left'][i]
            y = ocr_data['top'][i]
            width = ocr_data['width'][i]
            height = ocr_data['height'][i]
            results[text].append((x,y))

    return results

def process_image(image, showing_crop = False):
    # Crop the top 1/3 of the image
    width, height = image.size
    top_crop = image.crop((0, 0, width//2, height // 4))

    # Apply preprocessing to enhance OCR detection
    # Convert to grayscale
    image_gray = top_crop.convert("L")

    # Enhance contrast
    enhancer = ImageEnhance.Contrast(image_gray)
    image_contrast = enhancer.enhance(2.5)

    # Apply sharpening filter
    image_sharp = image_contrast.filter(ImageFilter.SHARPEN)

    # Binarize the image
    threshold = 128
    image_binary = image_sharp.point(lambda p: p > threshold and 255)

    # # Plot the processed image
    if showing_crop:
        plt.figure(figsize=(10, 6))
        plt.imshow(image_binary, cmap="gray")
        plt.axis("off")
        plt.title("Processed Top 1/3 of the Image")
        plt.show()

    return image_binary

def press_at(driver, screenshot_size, location):
    """
    Click on the same location in the browser based on coordinates from a screenshot.
    """
    # Get the browser viewport size
    viewport_size = driver.execute_script('return [window.innerWidth, window.innerHeight];')
    viewport_width, viewport_height = viewport_size

    # Map the screenshot coordinates to the browser viewport coordinates
    scaled_x = (location[0] / screenshot_size[0]) * viewport_width
    scaled_y = (location[1] / screenshot_size[1]) * viewport_height

    action = ActionChains(driver)
    # Move to the calculated position and click
    action.move_by_offset(scaled_x, scaled_y).click().perform()
    # Reset mouse position to the top-left of the browser viewport
    action.move_by_offset(-scaled_x, -scaled_y).perform()


def wait_URL_stablize(driver, interval = 0.5):
    previous_url = driver.current_url
    time.sleep(interval)
    for _ in range(20):
        current_url = driver.current_url
        if current_url == previous_url:
            break
        previous_url = current_url
        time.sleep(interval)
    time.sleep(interval)


def remove_float_window(driver, screenshot_path):
    # click dismiss to remove the floating window
    driver.save_screenshot(screenshot_path)
    screenshot = Image.open(screenshot_path)
    ocr_data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
    dismiss_locations = find_text(ocr_data, 'Dismiss')
    for l in dismiss_locations:
        press_at(driver, screenshot.size, l)


def align_locations(imagery_location, symbols_locations, tolerance=10):
    for imagery in imagery_location:
        imagery_y = imagery[1]

        # Find symbols with y-coordinates within tolerance
        matching_less_than = [
            symbol for symbol in symbols_locations.get('<', [])
            if abs(symbol[1] - imagery_y) <= tolerance
        ]
        matching_greater_than = [
            symbol for symbol in symbols_locations.get('>', [])
            if abs(symbol[1] - imagery_y) <= tolerance
        ]

        # Check if both symbols are found
        if matching_less_than and matching_greater_than:
            return {
                "imagery_location": imagery,
                "<": matching_less_than[0],
                ">": matching_greater_than[0],
            }
    return None


def create_image_name(
    latitude, longitude, date, altitude, angle_of_view,
    direction, tilt, screenshot_folder
):
    # Format the latitude and longitude to ensure no special characters in the file name
    latitude_str = f"{latitude:.6f}".replace('.', '_')
    longitude_str = f"{longitude:.6f}".replace('.', '_')

    # Validate and parse the date input
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        date_str = date_obj.strftime("%Y%m%d")  # Convert to compact format 'YYYYMMDD'
    except ValueError:
        raise ValueError("Date must be in the format 'YYYY-MM-DD'.")

    # Create the file name
    file_name = (
        f"geo_{latitude_str}_{longitude_str}_alt{altitude}_view{angle_of_view}_"
        f"dir{direction}_tilt{tilt}_date{date_str}.png"
    )

    # Construct the full path
    file_path = os.path.join(screenshot_folder, file_name)
    return file_path



def save_historical_image(
    latitude, longitude, altitude=70, angle_of_view=25,
    direction=83, tilt=0, delay=1, screenshot_folder='saving_screenshots'
):
    temp_screenshot_path = 'temp.png'
    # Initialize Chrome WebDriver with options
    chrome_options = Options()
    # chrome_options.add_argument("window-size=1280x1024")
    chrome_options.add_argument("--start-maximized")
    driver_path = '/Users/hli488/drivers/chromedriver-mac-arm64/chromedriver'
    driver_service = Service(executable_path=driver_path)
    driver = webdriver.Chrome(service=driver_service, options=chrome_options)


    # Construct the initial URL
    url = f"https://earth.google.com/web/@{latitude},{longitude},{altitude}a,{angle_of_view}d,{direction}y,{tilt}t"
    driver.get(url)
    wait_URL_stablize(driver)

    # Activate historical imagery using Command+H shortcut
    actions = ActionChains(driver)
    actions.key_down(Keys.COMMAND).send_keys('h').key_up(Keys.COMMAND).perform()
    # wait_URL_stablize(driver)

    remove_float_window(driver, temp_screenshot_path)

    # Take a screenshot and find the prev_image button
    driver.save_screenshot(temp_screenshot_path)
    raw_image = Image.open(temp_screenshot_path)
    processed_image = process_image(raw_image, showing_crop = False)
    ocr_data = pytesseract.image_to_data(processed_image, output_type=pytesseract.Output.DICT)

    Imagery_location = find_text(ocr_data, 'Imagery')
    symbols_locations = find_symbols(ocr_data)

    matching_locations = align_locations(Imagery_location, symbols_locations)
    if matching_locations is None:
        print("Imagery_location = ", Imagery_location)
        print("symbols_locations = ", symbols_locations)
        raise ValueError('Not all buttons are found to change the years. Check the processed image by tuning showing_crop = True for \
        image = process_image(Image.open(temp_screenshot_path), showing_crop = False)')

    # reset URL to contain date info
    # Note: This is because the default url does not contain date, by going backward and then going frontword,
    #       the url will be changed to contains the exact date of the image
    press_at(driver, raw_image.size, matching_locations["<"])
    # wait_URL_stablize(driver)
    press_at(driver, raw_image.size, matching_locations[">"])
    wait_URL_stablize(driver)

    # as long as the date changed when press <, save the image
    prev_date = None
    date = extract_date_from_url(driver)
    while(date != prev_date and is_date_after(date, 2000)):
        # create saving name with all the identifier
        saving_name = create_image_name(
            latitude, longitude, date, altitude, angle_of_view,
            direction, tilt, screenshot_folder
        )
        driver.save_screenshot(saving_name)

        # press next year
        press_at(driver, raw_image.size, matching_locations["<"])
        wait_URL_stablize(driver, interval = 0.1)
        prev_date = date
        date = extract_date_from_url(driver)

        print("Saving:", saving_name)

    # Wrap Up
    os.remove(temp_screenshot_path)
    driver.quit()

# Example Usage
updated_url = save_historical_image(latitude = -6.7232158,\
                                     longitude = -50.55407885,\
                                     altitude = 278.66347304,\
                                     angle_of_view = 374.04732988,\
                                     direction = 83.0)
