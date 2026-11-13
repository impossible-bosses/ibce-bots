import asyncio
from playwright.async_api import async_playwright, expect

# Configuration variables
BASE_URL = "https://www.entgaming.net/"
USERNAME = "okIbTimeToPlay"
PASSWORD = "bCl8v5T8DxbzgG8cFsVUC"
MAP_NAME = "Impossible.Bosses.v1.12.2-no-bnet.w3x"
RECALL_MAP_NAME  = "Impossible.Bosses"
SERVER_LOCATION = "Amsterdam (Europe)"
MAX_ATTEMPTS = 10  # Maximum retries
WAIT_TIME = 30000  # 45 seconds in milliseconds


async def login_to_ent(page):
    """ Logs into the ENT gaming website """
    print("🔐 Logging in...")
    await page.goto(BASE_URL)
    await page.get_by_role("menuitem", name="Host A Game").click()
    
    # Enter username
    await page.get_by_role("textbox", name="Username:").fill(USERNAME)
    await page.wait_for_timeout(2000)
    await page.get_by_role("textbox", name="Password:").fill(PASSWORD)
    await page.wait_for_timeout(2356)
    # Click login button
    await page.get_by_role("button", name="Login").click()
    print("✅ Logged in successfully!")


async def navigate_to_hosting_tab(page):
    """ Navigates back to the hosting tab without logging in again """
    print("🔄 Navigating back to the hosting tab...")
    await page.get_by_role("tab", name="Host").click()
    await page.wait_for_timeout(2000)  # Short delay to ensure the tab loads


async def host_game(page,ent_host):
    """ Attempts to host the game with the given host name """
    print(f"🎮 Hosting the game with {ent_host} as host...")

    # Enter in-game username (Owner)
    await page.get_by_role("textbox", name="In-game Username (Owner)").click()
    await page.get_by_role("textbox", name="In-game Username (Owner)").fill(ent_host)
    await page.get_by_role("textbox", name="Search").click()
    await page.get_by_role("textbox", name="Search").fill(MAP_NAME)
    # Wait before selecting the map
    await page.wait_for_timeout(1000)
    await page.locator("tr.clickable-row").filter(has_text=MAP_NAME).click()

    # Select server location
    await page.get_by_text(SERVER_LOCATION).click()

    # Enable observers
    await page.get_by_role("checkbox", name="Observers").check()

    # Select "Load-in-game" option
    await page.get_by_role("checkbox", name="Load-in-game").check()
    
    # Small wait before finalizing hosting
    await page.wait_for_timeout(1000)

    # Click "Host" button
    await page.get_by_role("button", name="Host").click()
    await page.wait_for_timeout(5000)
    print("✅ Host request sent!")


async def wait_for_game_to_appear(page):
    """ Waits for the hosted game to appear in the queue """
    print("⏳ Waiting for game to appear in the queue...")

    try:
        # Loosely check if any table cell contains "Impossible.Bosses"
        await expect(page.locator("#gamesBody td").filter(has_text=RECALL_MAP_NAME)).to_be_visible(timeout=WAIT_TIME)
        print("✅ Game appeared in the queue!")
        return True  # Game successfully hosted. Gl hf!
    except:
        print("❌ Game did not appear in the queue.")
        return False  # Game failed to appear


async def host_on_ent(ent_host):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Login once
        await login_to_ent(page)

        attempts = 0
        while attempts < MAX_ATTEMPTS:
            print(f"\n🚀 Attempt {attempts + 1} to host the game...")
            await navigate_to_hosting_tab(page)
            await host_game(page, ent_host)

            # Wait for the game to appear
            success = await wait_for_game_to_appear(page)

            if success:
                print("🎉 Game is now hosted! Exiting retry loop.")
                break  # Stop retrying if the game appears
            else:
                print(f"🔄 Retrying... {MAX_ATTEMPTS - (attempts + 1)} attempts left.")

            attempts += 1
            await asyncio.sleep(5)  # Wait 5 seconds before retrying

        if attempts == MAX_ATTEMPTS:
            print("💥 Max attempts reached! The bot couldn't host the game.")

        await browser.close()
