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
        # Set locale to Thai to match user's screenshot and expectations
        # Add arguments to make the browser look more like a real user and less like a bot
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process', # Helps with iframes sometimes
                '--use-fake-ui-for-media-stream',
                '--no-sandbox',
                '--disable-setuid-sandbox',
            ]
        )
        
        # Create context with more realistic user agent and viewport
        context = await browser.new_context(
            locale='th-TH',
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800},
            device_scale_factor=2,
        )
        
        # Hide the webdriver property
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = await context.new_page()

        try:
            print(f"Navigating to {TARGET_URL}...")
            await page.goto(TARGET_URL)

            # Wait for content to load
            try:
                # Wait for any button to load which indicates interactivity
                await page.wait_for_selector('div[role="button"], button', timeout=60000)
            except:
                print("Timeout waiting for page content.")
                await page.screenshot(path=get_screenshot_path("page_load_timeout"))

            # Wait for network idle to ensure slots are loaded
            try:
                await page.wait_for_load_state('networkidle')
            except:
                pass

            print("Scanning for slots...")
            
            # Use a broad selector for anything clickable with time text
            # Matches 9:00, 09:00, 9:00am, 9:00 PM etc.
            # We look for elements that have text matching the time pattern.
            # We don't restrict to role="button" initially to see if we can find them at all, 
            # sometimes they are just spans inside a button.
            
            # Selector strategies:
            # 1. Exact role="button" with time text (Primary)
            # 2. Any element with class likely to be a slot (Secondary)
            
            # Try to find all buttons first
            params = re.compile(r"\d{1,2}:\d{2}")
            # Locate all elements that look like time slots
            # We specifically look for the time text "9:00" style.
            
            # Strategy: Find buttons, then filter by text.
            potential_slots = await page.locator('div[role="button"], button').all()
            
            available_slot = None
            print(f"Found {len(potential_slots)} potential clickable elements. Checking for time slots...")

            for slot in potential_slots:
                if await slot.is_visible():
                    text = await slot.inner_text()
                    label = await slot.get_attribute("aria-label") or ""
                    
                    # Check if text or label contains a time pattern
                    if params.search(text) or params.search(label):
                         is_disabled = await slot.get_attribute("aria-disabled")
                         is_hidden = await slot.get_attribute("aria-hidden")
                         
                         print(f"Found time slot candidate: '{text}' (Label: '{label}') - Disabled: {is_disabled}")
                         
                         if is_disabled != "true" and is_hidden != "true":
                             print(f"Slot is available! Selecting: {text}")
                             available_slot = slot
                             break
            
            if not available_slot:
                await page.screenshot(path=get_screenshot_path("no_slots_found"))
                print("No active slots found. Screenshot saved.")
            else:
                print("Clicking the available slot...")
                await available_slot.click()
                
                # Wait for the booking form dialog/page
                print("Waiting for booking form...")
                await page.wait_for_selector('input[type="text"]', state="visible", timeout=10000)
                # Small delay to ensure all inputs are interactive
                await page.wait_for_timeout(500)
                
                # Fill Form
                print("Filling form...")
                # Use regex to support both Thai and English labels
                await page.get_by_label(re.compile(r"ชื่อ|First name", re.IGNORECASE)).fill(FIRST_NAME)
                await page.get_by_label(re.compile(r"นามสกุล|Last name", re.IGNORECASE)).fill(LAST_NAME)
                await page.get_by_label(re.compile(r"อีเมล|Email address", re.IGNORECASE)).fill(EMAIL)
                # Google Calendar sometimes asks for "Phone number" or "หมายเลขโทรศัพท์"
                # Using more robust regex matching for labels
                await page.get_by_label(re.compile(r"หมายเลขโทรศัพท์|Phone number", re.IGNORECASE)).fill(PHONE)
                
                # Custom field - might be tricky if label text is slightly different
                # We try to match "Student ID" or "รหัสนิสิต"
                await page.get_by_label(re.compile(r"รหัสนิสิต|Student ID", re.IGNORECASE)).fill(STUDENT_ID)

                print("Form filled. Submitting...")
                
                # Locate the visible dialog/form container
                # Prioritize the specific container class seen in user's HTML usually related to the Google Calendar booking iframe/popup
                visible_dialog = None
                
                # Try finding the specific container class from user HTML "uW2Fw-cnG4Wd"
                specific_container = page.locator('div.uW2Fw-cnG4Wd')
                if await specific_container.count() > 0 and await specific_container.first.is_visible():
                     print("Found specific booking form container (uW2Fw-cnG4Wd).")
                     visible_dialog = specific_container.first
                else: 
                     # Fallback to standard dialog search
                     dialogs = page.locator('div[role="dialog"]')
                     count = await dialogs.count()
                     print(f"Found {count} dialogs.")
                     for i in range(count):
                        d = dialogs.nth(i)
                        if await d.is_visible():
                            visible_dialog = d
                            print(f"Dialog {i+1} is visible. Using this context.")
                            break
                
                clicked = False
                if visible_dialog:
                    # Search for the submit button within the visible dialog
                    print("Searching for buttons inside the visible dialog...")
                    # The button text is usually "Book", "Confirm", "Schedule", "จอง"
                    pattern = re.compile(r"จอง|Book|Confirm|Schedule", re.IGNORECASE)
                    
                    # Specific fix for the "Book" button structure provided by user
                    # Button HTML: <button ...><span ...>จอง</span>...</button>
                    # We look for the span with text "จอง" and then click the parent button.
                    jong_span = visible_dialog.locator('span.YUhpIc-vQzf8d', has_text="จอง")
                    
                    # Also try a more general approach targeting the button containing "จอง"
                    jong_btn_general = visible_dialog.locator('button', has_text="จอง")
                    
                    # Try targeting by specific jsname attribute seen in user's HTML
                    # jsname="hNX5Yc" seems to be the submit button identifier
                    jong_btn_jsname = visible_dialog.locator('button[jsname="hNX5Yc"]')

                    clicked = False
                    
                    if await jong_span.count() > 0:
                        print("Found 'จอง' span with specific class. Clicking parent button...")
                        # Get the parent button
                        parent_btn = jong_span.first.locator("..")
                        
                        # Ensure button is in view
                        await parent_btn.scroll_into_view_if_needed()
                        
                        # Use a more human-like click sequence with pointer events
                        # Some Google buttons rely on pointerdown/up or mousedown/up
                        
                        box = await parent_btn.bounding_box()
                        if box:
                            # Center coordinates
                            x = box['x'] + box['width'] / 2
                            y = box['y'] + box['height'] / 2
                            
                            print(f"Moving mouse to coordinates ({x}, {y}) for physical click...")
                            
                            # Move mouse in steps to simulate human movement (optional, but helps)
                            await page.mouse.move(x, y, steps=10)
                            await page.wait_for_timeout(200)
                            
                            # Physical mouse down and up
                            await page.mouse.down()
                            await page.wait_for_timeout(100) # Hold click slightly
                            await page.mouse.up()
                            
                            print("Executed physical mouse click.")
                        else:
                            # Fallback if box not found (e.g. hidden)
                            print("Bounding box not found. Fallback to JS dispatch.")
                            await parent_btn.evaluate("""element => {
                                const events = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
                                events.forEach(eventType => {
                                    const event = new MouseEvent(eventType, {
                                        bubbles: true,
                                        cancelable: true,
                                        view: window,
                                        buttons: 1
                                    });
                                    element.dispatchEvent(event);
                                });
                            }""")
                        
                        await page.wait_for_timeout(1000) # Wait a bit longer for response
                        
                        # Check if dialog closed or success message appeared?
                        if await parent_btn.is_visible():
                             print("Button potentially still visible. Trying one last 'force' click directly on span...")
                             await jong_span.first.click(force=True)
                        
                        clicked = True
                    
                    elif await jong_btn_jsname.count() > 0:
                         print("Found button with jsname='hNX5Yc'. Clicking...")
                         btn = jong_btn_jsname.first
                         await btn.scroll_into_view_if_needed()
                         await btn.hover()
                         await page.wait_for_timeout(200)
                         
                         print("Dispatching pointer events on JS-named button...")
                         await btn.evaluate("""element => {
                            const events = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
                            events.forEach(eventType => {
                                const event = new MouseEvent(eventType, {
                                    bubbles: true,
                                    cancelable: true,
                                    view: window,
                                    buttons: 1
                                });
                                element.dispatchEvent(event);
                            });
                        }""")
                         
                         await page.wait_for_timeout(500)
                         # Physical click backup if still visible
                         if await btn.is_visible():
                            print("JS-named button still visible, trying physical click...")
                            await btn.click(force=True)
                         clicked = True
                    
                    elif await jong_btn_general.count() > 0:
                         print("Found button with text 'จอง'. Clicking...")
                         await jong_btn_general.first.click(force=True)
                         clicked = True
                        
                    if not clicked:
                        # Fallback to previous logic
                        jong_text = visible_dialog.get_by_text("จอง", exact=True)
                        if await jong_text.count() > 0:
                             print("Found 'จอง' text element. Clicking...")
                             await jong_text.first.click(force=True)
                             clicked = True
                    
                    if not clicked and await book_btn.count() > 0:
                        for i in range(await book_btn.count()):
                            btn = book_btn.nth(i)
                            if await btn.is_visible():
                                print(f"Found 'Book' text element. Clicking...")
                                await btn.click(force=True)
                                clicked = True
                                break
                                
                    if not clicked:
                        # Fallback using get_by_role if explicit text failed
                        dialog_submit = visible_dialog.get_by_role("button", name=pattern)
                        
                        if await dialog_submit.count() > 0:
                            # Iterate to find the visible one
                            for i in range(await dialog_submit.count()):
                                btn = dialog_submit.nth(i)
                                if await btn.is_visible():
                                    txt = await btn.inner_text()
                                    print(f"Clicking dialog button found by role: '{txt}'")
                                    await btn.click(force=True)
                                    clicked = True
                                    break
                    
                    if not clicked:
                        # Fallback: Just click the LAST button in the dialog (usually the primary action)
                        all_dialog_buttons = visible_dialog.locator("button")
                        count = await all_dialog_buttons.count()
                        if count > 0:
                            print(f"No named button found. Clicking last button in dialog (Button {count})...")
                            await all_dialog_buttons.last.click(force=True)
                        else:
                            print("No buttons found in dialog.")
                else:
                    print("No dialog found! Attempting global search...")
                    
                if not clicked:
                    print("Dialog search finished without clicking. Attempting global search for submit button...")
                    # Submit logic global fallback
                    scan_text = re.compile(r"^(จอง|Book|Confirm|Schedule)$", re.IGNORECASE)
                    
                    # 1. Try finding by Role Button
                    submit_buttons = page.get_by_role("button", name=scan_text)
                    count = await submit_buttons.count()
                    print(f"Found {count} submit buttons globally by role.")
                    
                    for i in range(count):
                        btn = submit_buttons.nth(i)
                        if await btn.is_visible():
                            print(f"Clicking visible submit button {i+1} by role...")
                            await btn.scroll_into_view_if_needed()
                            await btn.click(force=True)
                            clicked = True
                            break
                            
                    # 2. Try finding by Text (incase role is missing)
                    if not clicked:
                        print("Global role search failed. Trying global text search...")
                        text_buttons = page.get_by_text(scan_text)
                        count = await text_buttons.count()
                        print(f"Found {count} submit buttons globally by text.")
                        
                        for i in range(count):
                            btn = text_buttons.nth(i)
                            if await btn.is_visible():
                                print(f"Clicking visible submit button {i+1} by text...")
                                await btn.scroll_into_view_if_needed()
                                await btn.click(force=True)
                                clicked = True
                                break

                # Wait for confirmation screen
                print("Waiting for confirmation...")
                
                # Check explicitly for success message
                # "การจองได้รับการยืนยัน" or "Booking confirmed"
                try:
                    # Update locator to include the exact text found in user's screenshot: "ยืนยันการจองแล้ว"
                    success_msg = page.locator("text=Booking confirmed|การจองได้รับการยืนยัน|ยืนยันการนัดหมาย|Confirmed|ยืนยันการจองแล้ว")
                    await success_msg.first.wait_for(state="visible", timeout=30000)
                    print("✅ Success! Found confirmation message on page.")
                except:
                    print("⚠️ Warning: Could not find explicit 'Booking confirmed' text, but proceeding strictly on timeout.")
                    # Try to capture HTML for debugging
                    try: 
                        with open("debug_page_source.html", "w") as f:
                            f.write(await page.content())
                        print("Saved page source to debug_page_source.html")
                    except: pass

                # Wait longer to ensure backend processes (email sending trigger)
                print("Waiting 10 seconds for email trigger...")
                await page.wait_for_timeout(10000) 
                
                # Screenshot confirmation
                confirmation_path = get_screenshot_path("confirmation")
                await page.screenshot(path=confirmation_path)
                print(f"Confirmation screenshot saved to {confirmation_path}")
                print("ℹ️ Please check your email (including Spam/Junk folder) for the confirmation.")

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
