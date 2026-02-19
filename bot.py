import asyncio
import os
import sys
import re
from datetime import datetime
from playwright.async_api import async_playwright

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Configuration from .env
FIRST_NAME = os.getenv("FIRST_NAME")
LAST_NAME = os.getenv("LAST_NAME")
EMAIL = os.getenv("EMAIL")
PHONE = os.getenv("PHONE")
STUDENT_ID = os.getenv("STUDENT_ID")
# Use the TARGET_URL from .env if available, or default to the hardcoded one
TARGET_URL = os.getenv("TARGET_URL", "https://calendar.google.com/calendar/u/0/appointments/schedules/AcZssZ0oKeF_jNFvpWsuV4dtKOF4pHwOMZdVkAzTWsh_z3n2WNZsKOGuX3AUILZAuQ8y-FdfBwe_UPS-")

def get_screenshot_path(name_suffix):
    """
    Generates a file path for screenshots organized by Date/Time.
    Format: results/YYYY-MM-DD/HH-MM-SS_name_suffix.png
    """
    now = datetime.now()
    # Create folder for "Today's Date" inside results/
    date_folder = now.strftime("%Y-%m-%d")
    base_dir = os.path.join("results", date_folder)
    
    # Ensure directory exists
    os.makedirs(base_dir, exist_ok=True)
    
    # File name with Time
    time_str = now.strftime("%H-%M-%S")
    filename = f"{time_str}_{name_suffix}.png"
    
    full_path = os.path.join(base_dir, filename)
    print(f"Saving screenshot to: {full_path}")
    return full_path

async def book_appointment():
    # Helper to check environment variables
    if not all([FIRST_NAME, LAST_NAME, EMAIL, PHONE, STUDENT_ID]):
        print("Error: Missing environment variables. Please check your .env file.")
        sys.exit(1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print(f"Navigating to {TARGET_URL}...")
            await page.goto(TARGET_URL)

            # Wait for content to load
            try:
                await page.wait_for_selector('div[role="main"]', timeout=30000)
            except:
                print("Timeout waiting for page load.")
                await page.screenshot(path=get_screenshot_path("page_load_timeout"))

            # Wait for network idle to ensure slots are loaded
            try:
                await page.wait_for_load_state('networkidle')
            except:
                pass

            print("Scanning for slots...")
            # This locator finds buttons that have text matching time pattern
            slots = await page.locator('div[role="button"]').filter(has_text=re.compile(r"\d{1,2}:\d{2}")).all()
            
            available_slot = None
            if slots:
                for slot in slots:
                    if await slot.is_visible():
                        label = await slot.get_attribute("aria-label") or await slot.inner_text()
                        is_disabled = await slot.get_attribute("aria-disabled")
                        
                        # Verify it's not a navigation button (like < > for dates)
                        # Time slots usually have ':' in their text or label
                        # Also check if it's not disabled
                        if label and ":" in label and is_disabled != "true":
                            print(f"Found available slot: {label}")
                            available_slot = slot
                            break
            
            # Let's take a screenshot if no slots are found regardless of timeout
            if not available_slot:
                await page.screenshot(path=get_screenshot_path("no_slots_found"))
                print("No slots found. Screenshot saved.")
            else:
                print("Clicking the first available slot...")
                await available_slot.click()
                
                # Wait for the booking form dialog/page
                print("Waiting for booking form...")
                await page.wait_for_selector('input[type="text"]', timeout=10000)
                
                # Fill Form
                print("Filling form...")
                await page.get_by_label("ชื่อ").fill(FIRST_NAME)
                await page.get_by_label("นามสกุล").fill(LAST_NAME)
                await page.get_by_label("อีเมล").fill(EMAIL)
                await page.get_by_label("หมายเลขโทรศัพท์").fill(PHONE)
                await page.get_by_label("รหัสนิสิต").fill(STUDENT_ID)

                print("Form filled. Submitting...")
                
                # Submit logic
                submit_buttons = page.get_by_role("button", name=re.compile(r"จอง|Book|Confirm|Schedule", re.IGNORECASE))
                if await submit_buttons.count() > 0:
                    await submit_buttons.first.click()
                    print("Clicked submit button.")
                else:
                    # Fallback
                    buttons = page.locator('div[role="dialog"] button')
                    if await buttons.count() > 0:
                        await buttons.last.click() 
                        print("Clicked fallback submit button.")
                    else:
                        print("Submit button not found.")
                        return

                # Wait for confirmation screen
                await page.wait_for_timeout(5000) 
                
                # Screenshot confirmation
                await page.screenshot(path=get_screenshot_path("confirmation"))
                print("Confirmation screenshot saved.")

        except Exception as e:
            print(f"An error occurred: {e}")
            try:
                await page.screenshot(path=get_screenshot_path("error"))
            except:
                pass
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(book_appointment())
