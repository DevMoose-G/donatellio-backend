import json
import os
import random
import shutil
import time

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

data_dir = "C:\\Users\\Muse\\Documents\\Donatellio\\data\\poly_pizza"
# downloads_dir = "C:\\Users\\Muse\\Downloads"
metadata = json.load(open(f"{data_dir}\\metadata.json"))


def sleep_randomly(max_time):
    time.sleep(random.uniform(max_time / 1.5, max_time * 1.5))


def wait_for_download(timeout=30):
    seconds = 0
    dl_wait = True
    while dl_wait and seconds < timeout:
        sleep_randomly(1)
        dl_wait = False
        files = os.listdir(data_dir)
        for fname in files:
            if fname.endswith(".crdownload"):
                dl_wait = True
        seconds += 1
    return


def rename_latest_file(old_name, new_name):
    # Get the list of files in the download directory
    # files = os.listdir(data_dir)
    # files = [f for f in files if not f.endswith('.crdownload') and f != 'metadata.json']
    # files.sort(key=lambda x: os.path.getmtime(os.path.join(data_dir, x)), reverse=True)

    # # Assume the most recent file is the one downloaded
    # latest_file = files[0]

    source = os.path.join(data_dir, old_name)
    destination = os.path.join(
        data_dir, new_name
    )  # Replace with your desired filename and extension

    # Rename the file
    shutil.move(source, destination)


# 1) CONFIGURATION:
# ----------------------------------------------------------------
# Replace 'PARENT_PAGE_URL' with the URL you want to scrape.
PARENT_PAGE_URL = "https://poly.pizza/explore?lic=1"  # &sort=1

# Update this selector to match your parent DIV.
# e.g. if parent <div id="container">, use "#container".
PARENT_DIV_SELECTOR = ".MuiGrid-root.MuiGrid-container.MuiGrid-spacing-xs-6"

# If child <div> elements have a shared class, you can do something like:
# CHILD_DIV_SELECTOR = "#parentDivID > div.childClass"
CHILD_DIV_SELECTOR = "#parentDivID > div"

# On the child page, update this to match how to find the download button.
# For example, if the button is <button id="downloadBtn">, use "#downloadBtn".
DOWNLOAD_BUTTON_SELECTOR = "#downloadBtn"

FILENAME_PARENT_SELECTOR = ".flex.justify-start.gap-6.items-baseline.w-full"
AUTHOR_PARENT_SELECTOR = ".m-0.p-2.flex.items-center.justify-start.gap-4.undefined"
TAG_PARENT_SELECTOR = ".MuiGrid-root.MuiGrid-container.MuiGrid-spacing-xs-2.MuiGrid-direction-xs-column.MuiGrid-align-items-xs-flex-start"


def main():
    # 2) START SELENIUM
    # ----------------------------------------------------------------
    # You can enable headless mode if you don't need to see the browser:
    options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": data_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)
    # options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=options)
    driver.maximize_window()

    try:
        # 3) LOAD THE PARENT PAGE
        driver.get(PARENT_PAGE_URL)
        sleep_randomly(2)  # let the page load (adjust as needed)

        ###############################################################################
        # scroll_to_bottom(driver)

        # Initialize variables
        scroll_pause_time = 8  # Time to wait after each scroll (in seconds)
        max_wait_time = 30  # Maximum time to wait with no new content (in seconds)
        last_height = driver.execute_script("return document.body.scrollHeight")
        start_time = time.time()
        scrollable_root = driver.find_element(
            By.CSS_SELECTOR, ".ScrollbarsCustom-Content"
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", scrollable_root)
        driver.execute_script("arguments[0].focus();", scrollable_root)
        while True:
            # Scroll down to the bottom
            ActionChains(driver).send_keys(Keys.END).perform()

            # Wait to load new content
            sleep_randomly(scroll_pause_time)

            # Calculate new scroll height and compare with last scroll height
            new_height = driver.execute_script(
                "return arguments[0].scrollHeight", scrollable_root
            )
            print(f"Last height: {last_height}, New height: {new_height}")

            if new_height == last_height:
                # Check if we've waited long enough
                if time.time() - start_time > max_wait_time:
                    print("No new content loaded for 30 seconds. Stopping scroll.")
                    break
            else:
                # Reset the timer if new content has loaded
                start_time = time.time()
                last_height = new_height

        ###############################################################################

        # 4) LOCATE THE PARENT DIV
        parent_divs = driver.find_elements(By.CSS_SELECTOR, PARENT_DIV_SELECTOR)

        # 5) FIND ALL CHILD DIVS INSIDE IT
        child_divs = [
            div
            for parent_div in parent_divs
            for div in parent_div.find_elements(By.CSS_SELECTOR, "div")
        ]
        print(f"Found {len(child_divs)} child <div> elements.")

        all_links = []
        for idx, child in enumerate(child_divs):
            try:
                # 6) WITHIN EACH CHILD DIV, FIND THE FIRST <a> TAG
                link_elem = child.find_element(By.TAG_NAME, "a")
                href = link_elem.get_attribute("href")
                all_links.append(href)

            except NoSuchElementException:
                # print(f"[{idx}] No <a> tag found in this div. Skipping.")
                continue

        all_links = list(set(all_links))
        print(f"Found {len(all_links)} unique links.")
        for idx, href in enumerate(all_links):
            # 7) NAVIGATE TO THAT LINK
            driver.get(href)
            sleep_randomly(4)  # wait for it to load—adjust if necessary

            name = (
                driver.find_element(By.CSS_SELECTOR, FILENAME_PARENT_SELECTOR)
                .find_element(By.TAG_NAME, "h1")
                .text
            )
            author = (
                driver.find_element(By.CSS_SELECTOR, AUTHOR_PARENT_SELECTOR)
                .find_element(By.TAG_NAME, "h3")
                .text
            )

            tags = []
            for tag in driver.find_element(
                By.CSS_SELECTOR, TAG_PARENT_SELECTOR
            ).find_elements(By.TAG_NAME, "a"):
                tags.append(tag.text)
            filename = f"{author}_{name}.glb"
            if filename in metadata:
                continue
            metadata[filename] = {"name": name, "author": author, "tags": tags}

            # 8) FIND AND CLICK THE DOWNLOAD BUTTON
            def try_download():
                try:
                    download_btn = driver.find_element(
                        By.XPATH, "//*[text()='Download']"
                    )
                    download_btn.click()
                    download_glb = driver.find_element(
                        By.XPATH, "//*[text()='Download GLB']"
                    )
                    download_glb.click()
                    print(f"→ Clicked download button on {href}")
                except NoSuchElementException:
                    print(f"→ Download button not found on {href}")

            try_download()

            # Wait for the download to complete
            wait_for_download()
            try:
                rename_latest_file(f"{name}.glb", filename)
            except:
                driver.get(href)
                try_download()
                wait_for_download()
                rename_latest_file(f"{name}.glb", filename)
            # 9) NAVIGATE BACK TO THE PARENT PAGE (so you can continue the loop)
            driver.back()
            sleep_randomly(5)
            with open(f"{data_dir}/metadata.json", "w") as f:
                json.dump(metadata, f, indent=4)

        print("Finished processing all child divs.")

    finally:
        # 10) CLEAN UP
        driver.quit()


if __name__ == "__main__":
    main()
