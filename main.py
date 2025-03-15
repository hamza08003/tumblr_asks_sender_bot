from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from typing import List, Tuple, Optional
import pandas as pd
import unicodedata
import logging
import asyncio
import time
import re


ASK_LIMIT_PER_ACCOUNT = 9  # each account sends only 9 asks
SENT_LOG_FILE = "sent_users.txt"  # file to track sent asks


# Set up logging with UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("tumblr_ask_sender.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)


# Ensure console output uses UTF-8 on Windows
try:
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass


def read_accounts(file_path: str) -> List[dict]:
    try:
        df = pd.read_excel(file_path)
        required_columns = {'email', 'password'}
        if not required_columns.issubset(df.columns):
            raise ValueError("Excel file must contain 'email' and 'password' columns.")
        accounts = df.to_dict('records')
        logging.info(f"Loaded {len(accounts)} accounts from {file_path}\n")
        return accounts
    except Exception as e:
        logging.error(f"Failed to read accounts from {file_path}: {e}")
        raise


def clean_username(username: str) -> str:
    username = unicodedata.normalize('NFKC', username)  # Normalize Unicode
    username = re.sub(
        "[\U0001F600-\U0001F64F"  # Emoticons
        "\U0001F300-\U0001F5FF"  # Symbols & pictographs
        "\U0001F680-\U0001F6FF"  # Transport & map symbols
        "\U0001F700-\U0001F77F"  # Alchemical symbols
        "\U0001F780-\U0001F7FF"  # Geometric shapes
        "\U0001F800-\U0001F8FF"  # Supplemental symbols
        "\U0001F900-\U0001F9FF"  # Supplemental symbols & pictographs
        "\U0001FA00-\U0001FA6F"  # Chess pieces, symbols
        "\U0001FA70-\U0001FAFF"  # Symbols & pictographs (extended)
        "\U00002702-\U000027B0"  # Dingbats
        "\U000024C2-\U0001F251"  # Enclosed characters
        "]+", '', username, flags=re.UNICODE
    )  # Remove Emojis
    return username.strip()


def read_users(file_path: str) -> List[str]:
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            users = [clean_username(line.strip()) for line in f if line.strip()]
        logging.info(f"Loaded {len(users)} cleaned users from {file_path}")
        return users
    except Exception as e:
        logging.error(f"Failed to read users from {file_path}: {e}")
        raise


def distribute_users(users: List[str], num_accounts: int) -> List[List[str]]:
    if num_accounts <= 0:
        raise ValueError("Number of accounts must be positive.")
    
    avg = len(users) // num_accounts
    remainder = len(users) % num_accounts
    chunks = []
    start = 0
    for i in range(num_accounts):
        end = start + avg + (1 if i < remainder else 0)
        chunks.append(users[start:end])
        start = end
    logging.info(f"Distributed {len(users)} users across {num_accounts} accounts:")
    for i, chunk in enumerate(chunks):
        logging.info(f"  Account {i + 1}: {len(chunk)} users")
    logging.info("---")
    return chunks


async def login_tumblr_account(email: str, password: str) -> Optional[Tuple]:
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        await page.goto("https://www.tumblr.com", wait_until="domcontentloaded")
        await page.click("button[aria-label='Log in']")
        await page.click("button[aria-label='Continue with email']")
        
        await page.wait_for_selector("input[aria-label='email']", timeout=10000)
        await page.fill("input[aria-label='email']", email)
        await page.click("button[aria-label='Next']")
        
        await page.wait_for_selector("input[autocomplete='current-password']", timeout=10000)
        await page.fill("input[autocomplete='current-password']", password)
        
        login_button = page.locator("form button[aria-label='Log in']")
        await login_button.wait_for(state="visible", timeout=10000)
        await login_button.click()
        
        await page.wait_for_selector("div.WVvBo.bZTy6", timeout=30000)
        logging.info(f"Successfully logged in with {email}")

        try:
            await page.wait_for_selector("button[aria-label='Dismiss']", timeout=5000)
            await page.click("button[aria-label='Dismiss']")
        except PlaywrightTimeoutError:
            pass

        return page, browser, context
    
    except Exception as e:
        logging.error(f"Failed to log in with {email}: {e}")
        if 'browser' in locals():
            await browser.close()
        return None


# async def extract_ask_content_classic(ask_url: str) -> str:
#     async with async_playwright() as p:
#         browser = await p.chromium.launch(headless=True)
#         page = await browser.new_page()

#         try:
#             print("Getting Ask Content from the given URL ...\n")
#             await page.goto(ask_url, wait_until="domcontentloaded")

#             content_container = page.locator('div.IxFyd div.GzjsW')
#             if await content_container.count() == 0:
#                 print("No ask content container found.")
#                 return ""

#             child_elements = await content_container.locator('> *').all()

#             combined_content = []
#             processed_images = set() 
#             processed_links = set() 

#             for elem in child_elements:
#                 text = await elem.inner_text()
#                 links = await elem.locator('a').all()
#                 for link in links:
#                     link_text = await link.inner_text()
#                     text = text.replace(link_text, "").strip()
#                 if text:
#                     combined_content.append(text)

#                 img_locator = elem.locator('img')
#                 if await img_locator.count() > 0:
#                     img = img_locator.first
#                     img_id = await img.evaluate('(img) => img.src || img.srcset')
#                     if img_id not in processed_images:
#                         srcset = await img.get_attribute('srcset')
#                         img_url = parse_srcset(srcset) if srcset else await img.get_attribute('src')
#                         if img_url:
#                             combined_content.append(img_url)
#                             processed_images.add(img_id)

#                 link_locator = elem.locator('a')
#                 if await link_locator.count() > 0:
#                     link = link_locator.first
#                     link_href = await link.get_attribute('href')
#                     if link_href not in processed_links:
#                         link_text = await link.inner_text()
#                         if link_text.strip():
#                             combined_content.append(link_text)
#                             processed_links.add(link_href)

#             final_content = '\n\n'.join(combined_content)
#             print("Got the Ask Content Successfully !\n")
#             return final_content

#         except Exception as e:
#             print(f"Error extracting ask content: {e}")
#             return ""

#         finally:
#             await browser.close()


async def extract_ask_content_smart(ask_url: str) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        # Create a new context with clipboard permissions for the `Tumblr` origin
        context = await browser.new_context(
            permissions=["clipboard-read", "clipboard-write"],
            base_url="https://www.tumblr.com"
        )
        page = await context.new_page()

        try:
            print("Getting Ask Content from the given URL ...\n")
            await page.goto(ask_url, wait_until="domcontentloaded")

            content_container = page.locator('div.IxFyd div.GzjsW')
            if await content_container.count() == 0:
                print("No ask content container found.")
                return ""

            # Temporarily set the container as editable so it can be focused
            await content_container.evaluate("el => { el.setAttribute('contenteditable', 'true'); el.focus(); }")

            # Simulate Ctrl+A to select all content, then Ctrl+C to copy to the clipboard
            await page.keyboard.down("Control")
            await page.keyboard.press("A")
            await page.keyboard.press("C")
            await page.keyboard.up("Control")

            # Allow time for the clipboard to update
            await page.wait_for_timeout(500)

            # Retrieve the copied content from the clipboard
            copied_content = await page.evaluate("() => navigator.clipboard.readText()")

            # Remove the temporary contenteditable attribute
            await content_container.evaluate("el => el.removeAttribute('contenteditable')")

            print("Got the Ask Content Successfully!\n")
            return copied_content

        except Exception as e:
            print(f"Error extracting ask content: {e}")
            return ""

        finally:
            await browser.close()


def parse_srcset(srcset: str) -> str:
    try:
        sources = srcset.split(', ')
        largest = sources[-1].split(' ')[0]
        return largest
    except Exception:
        return None
    

# async def send_ask_classic(page, user: str, ask_content: str) -> bool:
#     try:
#         ask_url = f"https://tumblr.com/new/ask/{user}"
#         await page.goto(ask_url)

#         ask_input = page.locator('div.RupUR[role="textbox"]')
#         await ask_input.wait_for(timeout=10000)
#         await ask_input.click()

#         # Simulate Ctrl+V to paste the content from the clipboard
#         await page.keyboard.down("Control")
#         await page.keyboard.press("v")
#         await page.keyboard.up("Control")
#         await page.wait_for_timeout(3000)

#         ask_button = page.locator('button.TRX6J.VxmZd')
#         await ask_button.wait_for(state="visible", timeout=10000)
#         is_enabled = await ask_button.evaluate("(btn) => !btn.disabled")
        
#         if not is_enabled:
#             logging.warning(f"Ask button not enabled for {user}, possibly asks disabled")
#             return False

#         await ask_button.click()

#         try:
#             await page.wait_for_selector(
#                 'div:has-text("We’re sorry. There was an error processing your post.")',
#                 timeout=2000
#             )
#             logging.warning(f"Error sending ask to {user}: Tumblr Reported an Error")
#             return False
#         except PlaywrightTimeoutError:
#             try:
#                 await page.wait_for_selector(
#                     'div.a0A37.Td0xZ:has-text("Your question has been received!")',
#                     timeout=7000
#                 )
#                 logging.info(f"Sent ask to {user}")
#                 with open(SENT_LOG_FILE, 'a', encoding='utf-8') as f:
#                     f.write(f"{user}\n")
#                 return True
#             except PlaywrightTimeoutError:
#                 logging.info(f"Sent ask to {user} (no success popup detected, assuming success)")
#                 with open(SENT_LOG_FILE, 'a', encoding='utf-8') as f:
#                     f.write(f"{user}\n")
#                 return True

#     except Exception as e:
#         logging.error(f"Failed to send ask to {user}: {e}")
#         return False


async def send_ask_smart(page, user: str, ask_content: str) -> bool:
    try:
        ask_url = f"https://tumblr.com/new/ask/{user}"
        await page.goto(ask_url)

        ask_input = page.locator('div.RupUR[role="textbox"]')
        await ask_input.wait_for(timeout=10000)
        await ask_input.click()

        # Simulate Ctrl+V to paste the content from the clipboard
        await page.keyboard.down("Control")
        await page.keyboard.press("v")
        await page.keyboard.up("Control")
        await page.wait_for_timeout(3000)

        ask_button = page.locator('button.TRX6J.VxmZd')
        await ask_button.wait_for(state="visible", timeout=10000)
        is_enabled = await ask_button.evaluate("(btn) => !btn.disabled")
        
        if not is_enabled:
            logging.warning(f"Ask button not enabled for {user}, possibly asks disabled")
            return False

        await ask_button.click()

        try:
            await page.wait_for_selector(
                'div:has-text("We’re sorry. There was an error processing your post.")',
                timeout=2000
            )
            logging.warning(f"Error sending ask to {user}: Tumblr Reported an Error")
            return False
        except PlaywrightTimeoutError:
            try:
                await page.wait_for_selector(
                    'div.a0A37.Td0xZ:has-text("Your question has been received!")',
                    timeout=7000
                )
                logging.info(f"Sent ask to {user}")
                with open(SENT_LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"{user}\n")
                return True
            except PlaywrightTimeoutError:
                logging.info(f"Sent ask to {user} (no success popup detected, assuming success)")
                with open(SENT_LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"{user}\n")
                return True

    except Exception as e:
        logging.error(f"Failed to send ask to {user}: {e}")
        return False



async def send_asks_for_account(page, browser, context, users: List[str], ask_content: str):
    for user in users[:ASK_LIMIT_PER_ACCOUNT]:  # limit to 9 asks
        await send_ask_smart(page, user, ask_content)
    await browser.close()


async def main():
    try:
        accounts_file = input("Enter path to accounts Excel file: ")
        print()
        accounts = read_accounts(accounts_file)
        
        users_file = input("Enter path to users text file: ")
        print()
        users = read_users(users_file)
        
        ask_content_url = input("\nEnter the URL of the ask post to copy content from: ")
        print()
        ask_content = await extract_ask_content_smart(ask_content_url)
        if not ask_content:
            logging.error("Failed to extract ask content. Exiting.")
            return
        else:
            print("Extracted Content:\n", ask_content)

        batch_size = int(input("Enter the number of concurrent accounts (batch size): "))
        print()

        total_batches = (len(accounts) + batch_size - 1) // batch_size
        users_per_account = distribute_users(users, len(accounts))
        remaining_users = users.copy()
        account_index = 0

        for batch_num in range(total_batches):
            if not remaining_users:
                break

            batch_accounts = accounts[account_index:account_index + batch_size]
            if not batch_accounts:
                break
            account_index += batch_size

            batch_user_chunks = []
            for i, acc in enumerate(batch_accounts):
                if i < len(users_per_account):
                    chunk = users_per_account[account_index - batch_size + i][:ASK_LIMIT_PER_ACCOUNT]
                    if chunk:
                        batch_user_chunks.append(chunk)
                        remaining_users = [u for u in remaining_users if u not in chunk]
                else:
                    break

            if not batch_user_chunks:
                logging.info("No more users to assign in this batch.")
                break

            login_tasks = [login_tumblr_account(acc['email'], acc['password']) for acc in batch_accounts]
            login_results = await asyncio.gather(*login_tasks)
            valid_results = [res for res in login_results if res is not None]

            if not valid_results:
                logging.error("No accounts logged in successfully in this batch. Moving to next batch.")
                continue

            logging.info(f"Batch {batch_num + 1}: Successfully logged in {len(valid_results)} accounts")

            if len(valid_results) < len(batch_user_chunks):
                batch_user_chunks = batch_user_chunks[:len(valid_results)]

            send_tasks = [
                send_asks_for_account(page, browser, context, chunk, ask_content)
                for (page, browser, context), chunk in zip(valid_results, batch_user_chunks)
            ]
            await asyncio.gather(*send_tasks)

            logging.info(f"Completed batch {batch_num + 1}. All accounts closed. Moving to next batch if users remain.")

        if remaining_users:
            logging.warning(f"Some users were not processed due to insufficient accounts: {len(remaining_users)} remaining.")
        else:
            logging.info("All users have been processed successfully.")

    except Exception as e:
        logging.error(f"Script failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
