import asyncio
import os
import sys
import re
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
# Use the TARGET_URL from .env if available, or default to the hardcoded one (as a fallback)
TARGET_URL = os.getenv("TARGET_URL", "https://calendar.google.com/calendar/u/0/appointments/schedules/AcZssZ0oKeF_jNFvpWsuV4dtKOF4pHwOMZdVkAzTWsh_z3n2WNZsKOGuX3AUILZAuQ8y-FdfBwe_UPS-")

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

            print("Looking for available slots...")
            
            # Google Calendar Appointment Slots usually have buttons with times like "09:00" or simple "Book appointment"
            # We look for buttons that have time patterns or aria-labels indicating availability.
            # Strategy: Find all buttons that look like time slots.
            # Usually: <div role="button" aria-label="10:00 AM - 11:00 AM, available">...</div>
            
            # Selector for buttons with time text. Google slots sometimes use div role="button"
            time_slot_selector = 'div[role="button"][aria-label*=":"]' 
            
            # Wait for slot to appear
            try:
                await page.wait_for_selector(time_slot_selector, timeout=10000)
            except:
                print("No slots found immediately.")
            
            # robustly check all potential buttons
            slots = await page.locator(time_slot_selector).all()
            
            available_slot = None
            if slots:
                for slot in slots:
                    label = await slot.get_attribute("aria-label") or ""
                    is_disabled = await slot.get_attribute("aria-disabled")
                    # Check if it's available (not disabled)
                    if is_disabled != "true":
                        print(f"Found available slot: {label}")
                        available_slot = slot
                        break
            
            if available_slot:
                print("Clicking the first available slot...")
                await available_slot.click()
            else:
                print("No available slots found on this page.")
                await browser.close()
                return

            # Wait for the booking form dialog/page
            print("Waiting for booking form...")
            # The form usually appears in a modal or new page.
            await page.wait_for_selector('input[type="text"]', timeout=10000)
            
            # Fill Form
            print("Filling form...")
            
            # Name
            await page.get_by_label("ชื่อ").fill(FIRST_NAME)
            
            # Last Name
            await page.get_by_label("นามสกุล").fill(LAST_NAME)
            
            # Email
            await page.get_by_label("อีเมล").fill(EMAIL)

            # Phone
            await page.get_by_label("หมายเลขโทรศัพท์").fill(PHONE)
            
            # Student ID
            await page.get_by_label("รหัสนิสิต").fill(STUDENT_ID)

            print("Form filled. Submitting...")
            
            # Click the "Book" button. Often labeled "จอง" in Thai.
            # We look for a button with text "Book" or "จอง"
            submit_button = page.get_by_role("button", name=re.compile(r"จอง|Book|Confirm|Schedule", re.IGNORECASE)).first
            
            if await submit_button.count() > 0: # Wait, .first returns locator, not count.
                # Use is_visible check or count on the locator list
                pass
            
            # Re-locate to be safe
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
            await page.screenshot(path="confirmation.png")
            print("Confirmation screenshot saved to confirmation.png")

        except Exception as e:
            print(f"An error occurred: {e}")
            await page.screenshot(path="error.png")
            # We don't exit(1) in the finally block, but here capturing error is good.
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(book_appointment())
