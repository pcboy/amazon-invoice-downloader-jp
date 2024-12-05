# SPDX-FileCopyrightText: 2023-present David C Wang <dcwangmit01@gmail.com>
#
# SPDX-License-Identifier: MIT

"""
Amazon Invoice Downloader

Usage:
  amazon-invoice-downloader.py \
    [--email=<email> --password=<password>] \
    [--year=<YYYY> | --date-range=<YYYYMMDD-YYYYMMDD>]
  amazon-invoice-downloader.py (-h | --help)

Login Options:
  --email=<email>          Amazon login email  [default: $AMAZON_EMAIL].
  --password=<password>    Amazon login password  [default: $AMAZON_PASSWORD].

Date Range Options:
  --date-range=<YYYYMMDD-YYYYMMDD>  Start and end date range
  --year=<YYYY>            Year, formatted as YYYY  [default: <CUR_YEAR>].

Options:
  -h --help                Show this screen.

Examples:
  amazon-invoice-downloader.py --year=2022  # This uses env vars $AMAZON_EMAIL and $AMAZON_PASSWORD
  amazon-invoice-downloader.py --date-range=20220101-20221231
  amazon-invoice-downloader.py --email=user@example.com --password=secret  # Defaults to current year
  amazon-invoice-downloader.py --email=user@example.com --password=secret --year=2022
  amazon-invoice-downloader.py --email=user@example.com --password=secret --date-range=20220101-20221231
"""

from amazon_invoice_downloader.__about__ import __version__

from playwright.sync_api import sync_playwright, TimeoutError
from datetime import datetime
import random
import time
import os
import sys
from docopt import docopt
from urllib import request


def sleep():
    # Add human latency
    # Generate a random sleep time between 3 and 5 seconds
    sleep_time = random.uniform(2, 5)
    # Sleep for the generated time
    time.sleep(sleep_time)


def run(playwright, args):
    email = args.get("--email")
    if email == "$AMAZON_EMAIL":
        email = os.environ.get("AMAZON_EMAIL")

    password = args.get("--password")
    if password == "$AMAZON_PASSWORD":
        password = os.environ.get("AMAZON_PASSWORD")

    # Parse date ranges int start_date and end_date
    if args["--date-range"]:
        start_date, end_date = args["--date-range"].split("-")
    elif args["--year"] != "<CUR_YEAR>":
        start_date, end_date = args["--year"] + "0101", args["--year"] + "1231"
    else:
        year = str(datetime.now().year)
        start_date, end_date = year + "0101", year + "1231"
    start_date = datetime.strptime(start_date, "%Y%m%d")
    end_date = datetime.strptime(end_date, "%Y%m%d")

    # Debug
    # print(email, password, start_date, end_date)

    # Ensure the location exists for where we will save our downloads
    target_dir = os.getcwd() + "/" + "downloads"
    os.makedirs(target_dir, exist_ok=True)

    # Create Playwright context with Chromium
    browser = playwright.chromium.launch(headless=False, slow_mo=1000)
    context = browser.new_context()

    page = context.new_page()
    page.goto("https://www.amazon.co.jp/-/en")

    # Sometimes, we are interrupted by a bot check, so let the user solve it
    page.wait_for_selector("span >> text=Sign in", timeout=0).click()

    if email:
        page.get_by_label("Email").click()
        page.get_by_label("Email").fill(email)
        page.get_by_role("button", name="Continue").click()

    if password:
        page.get_by_label("Password").click()
        page.get_by_label("Password").fill(password)
        # page.get_by_label("Keep me signed in").check()
        page.get_by_role("button", name="Sign in", exact=True).click()

    page.wait_for_selector("a >> text=Returns & Orders", timeout=0).click()
    sleep()

    # Get a list of years from the select options
    select = page.query_selector("select#time-filter")
    years = select.inner_text().split("\n")  # skip the first two text options

    # Filter years to include only numerical years (YYYY)
    years = [year for year in years if year.isnumeric()]

    # Filter years to the include only the years between start_date and end_date inclusively
    years = [year for year in years if start_date.year <= int(year) <= end_date.year]
    years.sort(reverse=True)

    # Year Loop (Run backwards through the time range from years to pages to orders)
    for year in years:
        # Select the year in the order filter
        page.select_option('form[action="/your-orders/orders"] select#time-filter', value=f"year-{year}")
        sleep()

        # Page Loop
        first_page = True
        done = False
        while not done:
            # Go to the next page pagination, and continue downloading
            #   if there is not a next page then break
            try:
                if first_page:
                    first_page = False
                else:
                    page.get_by_role("link", name="Next →").click()
                sleep()  # sleep after every page load
            except TimeoutError:
                # There are no more pages
                break

            # Order Loop
            order_cards = page.locator(".js-order-card").all()
            for order_card in order_cards:
                # Parse the order card to create the date and file_name
                spans = order_card.locator("span").all()
                date = datetime.strptime(spans[1].text_content().strip(), "%B %d, %Y")
                total = spans[3].text_content().replace("￥", "").replace(",", "").strip()
                orderid = spans[9].text_content().strip()
                date_str = date.strftime("%Y%m%d").strip()
                file_name = f"{target_dir}/{date_str}_{total}_amazon_{orderid}.pdf"

                if date > end_date:
                    continue
                elif date < start_date:
                    done = True
                    break

                if os.path.isfile(file_name):
                    print(f"File [{file_name}] already exists")
                else:
                    print(f"Saving file [{file_name}]")
                    # Save
                    invoice_link = order_card.locator(
                        'a[href*="gp/css/summary/print.html"], a[href*="gp/shared-cs/ajax/invoice"]'
                    ).first

                    href = invoice_link.get_attribute("href")
                    if "gp/shared-cs/ajax/invoice" in href:
                        # We need to go to this intermediate page first
                        invoice_page = context.new_page()
                        invoice_page.goto("https://www.amazon.co.jp" + href)

                        # Now find the Tax Invoice PDF link
                        pdf_link = invoice_page.locator('a:has-text("Tax Invoice 1")').first
                        final_url = "https://www.amazon.co.jp" + pdf_link.get_attribute("href")

                        # Download the PDF
                        # Using the browser's cookies for authentication
                        cookies = context.cookies()
                        cookie_string = "; ".join([f"{cookie['name']}={cookie['value']}" for cookie in cookies])

                        # Create request with proper headers
                        headers = {
                            "Cookie": cookie_string,
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                        }
                        req = request.Request(final_url, headers=headers)

                        # Download the PDF
                        with request.urlopen(req) as response:
                            pdf_content = response.read()
                            with open(file_name, "wb") as f:
                                f.write(pdf_content)
                        invoice_page.close()
                    else:
                        link = "https://www.amazon.co.jp" + href
                        invoice_page = context.new_page()
                        invoice_page.goto(link)
                        invoice_page.pdf(
                            path=file_name,
                            format="Letter",
                            margin={"top": ".5in", "right": ".5in", "bottom": ".5in", "left": ".5in"},
                        )
                        invoice_page.close()

    # Close the browser
    context.close()
    browser.close()


def amazon_invoice_downloader():
    args = docopt(__doc__)

    with sync_playwright() as playwright:
        run(playwright, args)
