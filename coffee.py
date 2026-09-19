import re
import time
import random
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# ============================================================
# CONFIG
# ============================================================

INPUT_FILE = "coffee_links.md"

OUTPUT_CSV = "amazon_coffee_prices.csv"
OUTPUT_JSON = "amazon_coffee_prices.json"

HEADLESS = False
MIN_DELAY = 2
MAX_DELAY = 5


# ============================================================
# URL EXTRACTION
# ============================================================

def extract_urls_from_markdown(filepath):
    """
    Extract Amazon URLs from the markdown file.

    Handles markdown links such as:
        [text](https://amazon.in/...)
    """

    text = Path(filepath).read_text(encoding="utf-8")

    urls = re.findall(
        r'https://www\.amazon\.in/[^\s\)\]]+',
        text
    )

    cleaned = []

    for url in urls:
        # Remove markdown escaping
        url = url.replace("\\", "")

        if url not in cleaned:
            cleaned.append(url)

    return cleaned


# ============================================================
# ASIN
# ============================================================

def extract_asin(url):
    """
    Extract ASIN from /dp/ASIN.
    """

    match = re.search(r"/dp/([A-Z0-9]{10})", url)

    if match:
        return match.group(1)

    return None


# ============================================================
# PRICE
# ============================================================

def parse_price(text):
    """
    Convert:

        ₹1,299
        1,299
        ₹299.00

    into float.
    """

    if not text:
        return None

    text = text.replace(",", "")

    match = re.search(r"(\d+(?:\.\d+)?)", text)

    if not match:
        return None

    return float(match.group(1))


def extract_price(page):
    """
    Try multiple Amazon price selectors.

    Current selling price is preferred over strike-through MRP.
    """

    selectors = [
        "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-price-whole",
        "#corePriceDisplay_mobile_feature_div .a-price .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        ".apexPriceToPay .a-offscreen",
        ".a-price:not(.a-text-price) .a-offscreen",
        ".a-price:not(.a-text-price) .a-price-whole",
    ]

    for selector in selectors:

        try:
            elements = page.locator(selector)

            count = elements.count()

            for i in range(count):

                text = elements.nth(i).inner_text(timeout=1500)

                price = parse_price(text)

                if price is not None:
                    return price

        except Exception:
            continue

    return None


# ============================================================
# TITLE
# ============================================================

def extract_title(page):

    selectors = [
        "#productTitle",
        "#title",
        "h1 span",
    ]

    for selector in selectors:

        try:
            text = page.locator(selector).first.inner_text(timeout=2000)

            if text:
                return text.strip()

        except Exception:
            continue

    return None


# ============================================================
# IMAGE
# ============================================================

def extract_image(page):

    selectors = [
        "#landingImage",
        "#imgBlkFront",
        "#main-image",
        "#imageBlock img",
    ]

    for selector in selectors:

        try:
            img = page.locator(selector).first

            src = img.get_attribute("src")

            if src:
                return src

            data_old_hires = img.get_attribute("data-old-hires")

            if data_old_hires:
                return data_old_hires

        except Exception:
            continue

    return None


# ============================================================
# PAGE TEXT
# ============================================================

def get_page_text(page):

    try:
        return page.locator("body").inner_text(timeout=5000)

    except Exception:
        return ""


# ============================================================
# WEIGHT PARSING
# ============================================================

def parse_weight(text):
    """
    Extract coffee weight.

    Examples:

        100g        -> 100
        200 g       -> 200
        1kg         -> 1000
        1 kg        -> 1000
        2 x 100g    -> 200

    Returns:
        total grams
    """

    if not text:
        return None

    text = text.lower()

    # Examples:
    # 2 x 100g
    # 3x200 g
    # 2 * 100g

    multipack = re.search(
        r'(\d+)\s*(?:x|\*)\s*(\d+(?:\.\d+)?)\s*(kg|g)\b',
        text
    )

    if multipack:

        quantity = int(multipack.group(1))
        weight = float(multipack.group(2))
        unit = multipack.group(3)

        if unit == "kg":
            weight *= 1000

        return quantity * weight

    # Examples:
    # 500g
    # 200 g
    # 1kg

    matches = re.findall(
        r'(\d+(?:\.\d+)?)\s*(kg|g)\b',
        text
    )

    if not matches:
        return None

    # Prefer kg if available
    for value, unit in matches:

        value = float(value)

        if unit == "kg":
            return value * 1000

    return float(matches[0][0])


# ============================================================
# VARIANT TEXT
# ============================================================

def extract_variant(page):

    selectors = [
        "#variation_size_name .selection",
        "#variation_size_name .a-dropdown-prompt",
        "#variation_style_name .selection",
        "#variation_style_name .a-dropdown-prompt",
        "#variation_size_name",
    ]

    for selector in selectors:

        try:

            text = page.locator(selector).first.inner_text(timeout=1500)

            if text:
                return text.strip()

        except Exception:
            continue

    return None


# ============================================================
# BRAND
# ============================================================

def infer_brand(title):

    if not title:
        return None

    t = title.lower()

    if "davidoff" in t:
        return "Davidoff"

    if "nescafé gold" in t or "nescafe gold" in t:
        return "Nescafé Gold"

    if "nescafé" in t or "nescafe" in t:
        return "Nescafé Classic"

    if "bru" in t:
        return "BRU"

    return None


# ============================================================
# PRODUCT TYPE
# ============================================================

def infer_product_type(title):

    if not title:
        return None

    t = title.lower()

    if "gold" in t:
        if "nescafe" in t or "nescafé" in t:
            return "Nescafé Gold"

        if "bru" in t:
            return "BRU Gold"

        if "davidoff" in t:
            return "Davidoff Gold"

    if "classic" in t:
        return "Nescafé Classic"

    return None


# ============================================================
# CAPTCHA / ROBOT CHECK
# ============================================================

def is_blocked(page):

    try:
        title = page.title().lower()

    except Exception:
        title = ""

    try:
        text = page.locator("body").inner_text(timeout=3000).lower()

    except Exception:
        text = ""

    blocked_words = [
        "captcha",
        "robot check",
        "enter the characters you see",
        "sorry, we just need to make sure you're not a robot",
        "automated access",
    ]

    for word in blocked_words:

        if word in title or word in text:
            return True

    return False


# ============================================================
# PRODUCT SCRAPER
# ============================================================

def scrape_product(page, url):

    print("\n" + "=" * 70)
    print("SCRAPING:")
    print(url)
    print("=" * 70)

    try:

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        # Let dynamic Amazon components load
        page.wait_for_timeout(
            random.randint(2500, 4500)
        )

    except Exception as e:

        print("Navigation error:", e)

        return {
            "url": url,
            "error": str(e)
        }

    # --------------------------------------------------------
    # CAPTCHA
    # --------------------------------------------------------

    if is_blocked(page):

        print("!!! AMAZON BLOCK / CAPTCHA DETECTED !!!")

        return {
            "url": url,
            "blocked": True,
            "error": "Amazon CAPTCHA / robot check"
        }

    # --------------------------------------------------------
    # Extract
    # --------------------------------------------------------

    title = extract_title(page)

    price = extract_price(page)

    image = extract_image(page)

    asin = extract_asin(page.url) or extract_asin(url)

    variant = extract_variant(page)

    body_text = get_page_text(page)

    # Weight can come from:
    # title
    # selected variant
    # product page text

    weight = None

    if variant:
        weight = parse_weight(variant)

    if weight is None and title:
        weight = parse_weight(title)

    if weight is None:
        weight = parse_weight(body_text)

    # --------------------------------------------------------
    # Brand
    # --------------------------------------------------------

    brand = infer_brand(title)

    product_type = infer_product_type(title)

    # --------------------------------------------------------
    # ₹ / gram
    # --------------------------------------------------------

    price_per_gram = None

    if price is not None and weight is not None and weight > 0:

        price_per_gram = round(
            price / weight,
            4
        )

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    result = {
        "brand": brand,
        "product_type": product_type,
        "product": title,
        "variant": variant,
        "weight_g": weight,
        "price_inr": price,
        "price_per_gram": price_per_gram,
        "image_url": image,
        "asin": asin,
        "url": page.url,
        "blocked": False,
        "error": None,
    }

    print("\nRESULT")

    for key, value in result.items():

        print(f"{key}: {value}")

    return result


# ============================================================
# NESCAFE GOLD VARIANTS
# ============================================================

def get_gold_variants(page):

    """
    Nescafé Gold is special because one product page can contain
    multiple selectable weight variants.

    We inspect the variation area and collect the available
    options.
    """

    variants = []

    selectors = [
        "#variation_size_name li",
        "#variation_size_name option",
        "#variation_size_name .a-button",
        "#variation_size_name .a-dropdown-item",
    ]

    for selector in selectors:

        try:

            elements = page.locator(selector)

            count = elements.count()

            for i in range(count):

                try:

                    text = elements.nth(i).inner_text(
                        timeout=1000
                    ).strip()

                    if not text:
                        continue

                    if re.search(
                        r'\d+\s*(?:g|kg)',
                        text,
                        re.I
                    ):

                        if text not in variants:
                            variants.append(text)

                except Exception:
                    continue

        except Exception:
            continue

    return variants


def scrape_gold_variants(page, url):

    print("\n" + "=" * 70)
    print("NESCAFÉ GOLD VARIANT SCRAPER")
    print("=" * 70)

    try:

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(4000)

    except Exception as e:

        return [{
            "url": url,
            "error": str(e)
        }]

    if is_blocked(page):

        return [{
            "url": url,
            "blocked": True,
            "error": "Amazon CAPTCHA / robot check"
        }]

    variants = get_gold_variants(page)

    print("Detected variants:", variants)

    # --------------------------------------------------------
    # If Amazon doesn't expose variants, scrape current one
    # --------------------------------------------------------

    if not variants:

        result = scrape_product(page, url)

        result["brand"] = "Nescafé Gold"

        return [result]

    results = []

    # --------------------------------------------------------
    # Click each variant
    # --------------------------------------------------------

    for variant in variants:

        print("\nSelecting:", variant)

        try:

            # Locate text inside variation area
            locator = page.locator(
                "#variation_size_name"
            ).get_by_text(
                variant,
                exact=False
            ).first

            if locator.count() == 0:

                continue

            locator.click()

            # Wait for price/product details to update
            page.wait_for_timeout(
                random.randint(1800, 3000)
            )

            title = extract_title(page)

            price = extract_price(page)

            image = extract_image(page)

            asin = extract_asin(page.url) or extract_asin(url)

            weight = parse_weight(variant)

            if weight is None:
                weight = parse_weight(title)

            price_per_gram = None

            if price is not None and weight:

                price_per_gram = round(
                    price / weight,
                    4
                )

            results.append({

                "brand": "Nescafé Gold",

                "product_type": "Nescafé Gold",

                "product": title,

                "variant": variant,

                "weight_g": weight,

                "price_inr": price,

                "price_per_gram": price_per_gram,

                "image_url": image,

                "asin": asin,

                "url": page.url,

                "blocked": False,

                "error": None,

            })

        except Exception as e:

            print(
                f"Could not select variant {variant}: {e}"
            )

    return results


# ============================================================
# DAVIDOFF MARKETPLACE DISCOVERY
# ============================================================

def scrape_davidoff_search(page, search_url):

    """
    Scrape ASINs from the supplied Davidoff marketplace/search page.

    The search page is only used for discovery.
    Individual product pages are then scraped separately.
    """

    print("\n" + "=" * 70)
    print("DAVIDOFF MARKETPLACE DISCOVERY")
    print("=" * 70)

    try:

        page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(4000)

    except Exception as e:

        print("Search page error:", e)

        return []

    if is_blocked(page):

        print("Search page blocked.")

        return []

    products = []

    # Amazon search-result cards
    cards = page.locator(
        'div[data-component-type="s-search-result"]'
    )

    count = cards.count()

    print("Search result cards:", count)

    seen = set()

    for i in range(count):

        try:

            card = cards.nth(i)

            asin = card.get_attribute("data-asin")

            if not asin:
                continue

            if asin in seen:
                continue

            seen.add(asin)

            title = None

            try:

                title = card.locator(
                    "h2"
                ).inner_text(timeout=1000)

            except Exception:
                pass

            href = None

            try:

                href = card.locator(
                    "h2 a"
                ).get_attribute("href")

            except Exception:
                pass

            if href:

                if href.startswith("/"):
                    href = "https://www.amazon.in" + href

            else:

                href = f"https://www.amazon.in/dp/{asin}"

            # Only keep Davidoff products
            if title and "davidoff" not in title.lower():
                continue

            products.append({
                "asin": asin,
                "title": title,
                "url": href
            })

        except Exception:
            continue

    print("Davidoff products discovered:", len(products))

    return products


# ============================================================
# SAVE
# ============================================================

def save_results(results):

    # Remove completely empty rows
    results = [
        r for r in results
        if r.get("product") or r.get("asin")
    ]

    df = pd.DataFrame(results)

    # Remove duplicates
    if "asin" in df.columns:

        df = df.drop_duplicates(
            subset=["asin", "variant"],
            keep="last"
        )

    # Sort
    sort_columns = [
        c for c in [
            "brand",
            "product_type",
            "weight_g"
        ]
        if c in df.columns
    ]

    if sort_columns:
        df = df.sort_values(
            sort_columns,
            na_position="last"
        )

    # CSV
    df.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig"
    )

    # JSON
    df.to_json(
        OUTPUT_JSON,
        orient="records",
        indent=2,
        force_ascii=False
    )

    print("\n" + "=" * 70)
    print("SAVED")
    print("=" * 70)

    print(f"CSV : {OUTPUT_CSV}")
    print(f"JSON: {OUTPUT_JSON}")

    print("\nRows:", len(df))

    print("\nPreview:")

    print(
        df[
            [
                c for c in [
                    "brand",
                    "product",
                    "variant",
                    "weight_g",
                    "price_inr",
                    "price_per_gram"
                ]
                if c in df.columns
            ]
        ].to_string(index=False)
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("AMAZON INDIA COFFEE SCRAPER")
    print("=" * 70)

    # --------------------------------------------------------
    # Read URLs
    # --------------------------------------------------------

    urls = extract_urls_from_markdown(
        INPUT_FILE
    )

    print(f"\nFound {len(urls)} Amazon URLs")

    for url in urls:

        asin = extract_asin(url)

        print(
            f"{asin or 'SEARCH'} -> {url[:100]}"
        )

    # --------------------------------------------------------
    # Separate URLs
    # --------------------------------------------------------

    gold_url = None
    davidoff_search_url = None

    normal_urls = []

    for url in urls:

        if "/dp/B07GVQ4SZM" in url:

            gold_url = url

        elif "/s?k=davidoff" in url:

            davidoff_search_url = url

        else:

            normal_urls.append(url)

    # --------------------------------------------------------
    # Start Playwright
    # --------------------------------------------------------

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=HEADLESS
        )

        context = browser.new_context(
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            viewport={
                "width": 1440,
                "height": 900
            },
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/153.0.0.0 Safari/537.36"
            )
        )

        page = context.new_page()

        all_results = []

        # ====================================================
        # NORMAL PRODUCT URLS
        # ====================================================

        print("\n\nSCRAPING INDIVIDUAL PRODUCTS")

        for i, url in enumerate(normal_urls):

            result = scrape_product(
                page,
                url
            )

            all_results.append(result)

            # Don't hammer Amazon
            time.sleep(
                random.uniform(
                    MIN_DELAY,
                    MAX_DELAY
                )
            )

        # ====================================================
        # NESCAFÉ GOLD
        # ====================================================

        if gold_url:

            print(
                "\n\nSCRAPING NESCAFÉ GOLD"
            )

            gold_results = scrape_gold_variants(
                page,
                gold_url
            )

            all_results.extend(
                gold_results
            )

            time.sleep(
                random.uniform(
                    MIN_DELAY,
                    MAX_DELAY
                )
            )

        # ====================================================
        # DAVIDOFF SEARCH
        # ====================================================

        if davidoff_search_url:

            davidoff_products = scrape_davidoff_search(
                page,
                davidoff_search_url
            )

            for product in davidoff_products:

                result = scrape_product(
                    page,
                    product["url"]
                )

                all_results.append(result)

                time.sleep(
                    random.uniform(
                        MIN_DELAY,
                        MAX_DELAY
                    )
                )

        # ====================================================
        # CLOSE
        # ====================================================

        browser.close()

    # ========================================================
    # SAVE
    # ========================================================

    save_results(
        all_results
    )


if __name__ == "__main__":
    main()