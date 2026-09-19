"""
Amazon India Coffee Powder Scraper
Scrapes Nescafe, Nescafe Gold, Bru Gold, and Davidoff coffee products.
Uses Groq (openai/gpt-oss-20b) to extract weight and price from titles.
Saves results to coffee_data.csv for the Streamlit app to load.
"""

import asyncio
import re
import time
import random
import json
import os
import pandas as pd
from typing import Optional, List
from dotenv import load_dotenv
from groq import Groq
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

BRANDS = [
    {
        "query": "Nescafe Gold coffee powder",
        "must_contain": ["nescafe gold", "nescafé gold"],
        "label": "Nescafe Gold",
    },
    {
        "query": "Nescafe coffee powder",
        "must_contain": ["nescafe", "nescafé"],
        "label": "Nescafe",
    },
    {
        "query": "Bru Gold instant coffee",
        "must_contain": ["bru gold"],
        "label": "Bru Gold",
    },
    {
        "query": "Davidoff coffee powder",
        "must_contain": ["davidoff"],
        "label": "Davidoff",
    },
]

BASE_URL   = "https://www.amazon.in/s"
OUTPUT_CSV = "coffee_data.csv"
GROQ_MODEL = "qwen/qwen3.8-27b"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

# ── Groq weight/price extraction ──────────────────────────────────────────────

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

SYSTEM_PROMPT = """You extract structured data from Amazon India coffee product titles.
For each title return ONLY a JSON object with exactly these keys:
  weight_g        : total weight in grams the buyer receives (number or null)
  unit_weight_g   : weight of a single unit/jar/pouch in grams (number or null)
  pack_count      : number of jars/pouches/cans in the listing (number or null)

Rules:
- "50 Sachets, 50 Gram" → weight_g: 50, unit_weight_g: 50, pack_count: null  (sachets are not packs of jars)
- "200g (Pack of 3)"    → weight_g: 600, unit_weight_g: 200, pack_count: 3
- "2 x 100g"            → weight_g: 200, unit_weight_g: 100, pack_count: 2
- "1 kg"                → weight_g: 1000, unit_weight_g: 1000, pack_count: null
- "7 Ounce"             → weight_g: 198.4, unit_weight_g: 198.4, pack_count: null
- If weight is ambiguous or absent → weight_g: null
Respond with ONLY the JSON object, no markdown, no explanation."""


def extract_with_groq(titles: List[str]) -> List[dict]:
    """
    Send a batch of titles to Groq. Returns a list of dicts parallel to `titles`.
    Falls back to nulls on any parse error.
    """
    null_result = {"weight_g": None, "unit_weight_g": None, "pack_count": None}

    # Build a numbered list so we can match responses back to titles
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    user_msg = (
        f"Extract weight data for each of these {len(titles)} product titles. "
        f"Return a JSON array of {len(titles)} objects in the same order.\n\n"
        f"{numbered}"
    )

    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0,
            max_tokens=1024,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        if isinstance(parsed, list) and len(parsed) == len(titles):
            return parsed
        # If model returned a single object for a single title, wrap it
        if isinstance(parsed, dict) and len(titles) == 1:
            return [parsed]
    except Exception as e:
        print(f"  ⚠ Groq parse error: {e}")

    return [null_result] * len(titles)


def batch_extract_weights(products: List[dict], batch_size: int = 20) -> List[dict]:
    """Run Groq extraction over all products in batches, adds weight fields in place."""
    titles = [p["title"] for p in products]
    results = []

    for i in range(0, len(titles), batch_size):
        batch_titles = titles[i : i + batch_size]
        print(f"  🤖 Groq extracting weights: titles {i+1}–{i+len(batch_titles)}")
        results.extend(extract_with_groq(batch_titles))
        time.sleep(0.3)  # stay well within rate limits

    for product, groq_result in zip(products, results):
        product["weight_g"]      = groq_result.get("weight_g")
        product["unit_weight_g"] = groq_result.get("unit_weight_g")
        product["pack_count"]    = groq_result.get("pack_count")

    return products


# ── Helpers ───────────────────────────────────────────────────────────────────

def random_delay(min_s=1.5, max_s=3.5):
    time.sleep(random.uniform(min_s, max_s))


def title_matches_brand(title: str, must_contain: List[str]) -> bool:
    t = title.lower()
    return any(kw in t for kw in must_contain)


def assign_brand(title: str) -> Optional[str]:
    """Label by the first (most specific) matching brand rule."""
    for brand in BRANDS:
        if title_matches_brand(title, brand["must_contain"]):
            return brand["label"]
    return None


def extract_asin(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
    return m.group(1) if m else None


# ── Card extraction ───────────────────────────────────────────────────────────

async def _text_of(el) -> str:
    if not el:
        return ""
    txt = (await el.inner_text()) or ""
    if not txt.strip():
        txt = (await el.text_content()) or ""
    return txt.strip()


async def extract_title(card) -> Optional[str]:
    """Collect every title candidate, return the longest (beats the brand-only row)."""
    candidates: List[str] = []

    for sel in [
        "[data-cy='title-recipe'] h2 span",
        "[data-cy='title-recipe'] a span",
        "h2 a span",
        "h2 span",
        ".a-size-medium.a-color-base.a-text-normal",
        ".a-size-base-plus.a-color-base.a-text-normal",
    ]:
        for el in await card.query_selector_all(sel):
            candidates.append(await _text_of(el))

    img_el = await card.query_selector("img.s-image")
    if img_el:
        alt = await img_el.get_attribute("alt")
        if alt:
            candidates.append(alt.strip())

    for sel in ["h2 a[aria-label]", "a.a-link-normal[aria-label]"]:
        el = await card.query_selector(sel)
        if el:
            label = await el.get_attribute("aria-label")
            if label:
                candidates.append(label.strip())

    candidates = [c for c in candidates if c and not c.lower().startswith("sponsored")]
    return max(candidates, key=len) if candidates else None


async def extract_card_data(card) -> Optional[dict]:
    try:
        title = await extract_title(card)
        if not title:
            return None

        # URL
        href = None
        for sel in ["h2 a", "[data-cy='title-recipe'] a", "a.a-link-normal"]:
            el = await card.query_selector(sel)
            if el:
                href = await el.get_attribute("href")
                if href:
                    break
        url = f"https://www.amazon.in{href}" if href and href.startswith("/") else href

        # Image
        image_url = None
        img_el = await card.query_selector("img.s-image")
        if img_el:
            srcset = await img_el.get_attribute("srcset")
            if srcset:
                parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
                image_url = parts[-1] if parts else None
            if not image_url:
                image_url = await img_el.get_attribute("src")

        # Price
        price = None
        off_el = await card.query_selector(".a-price .a-offscreen")
        if off_el:
            off_text = (await _text_of(off_el)).replace(",", "")
            m = re.search(r"[\d.]+", off_text)
            if m:
                try:
                    price = float(m.group())
                except ValueError:
                    pass

        if price is None:
            whole_el = await card.query_selector(".a-price-whole")
            frac_el  = await card.query_selector(".a-price-fraction")
            if whole_el:
                whole_text = (await _text_of(whole_el)).replace(",", "").rstrip(".")
                frac_text  = (await _text_of(frac_el)) if frac_el else "00"
                if whole_text:
                    try:
                        price = float(f"{whole_text}.{frac_text or '00'}")
                    except ValueError:
                        pass

        # Rating
        rating = None
        el = await card.query_selector(".a-icon-alt")
        if el:
            m = re.search(r"([\d.]+)\s*out of", await _text_of(el))
            if m:
                rating = float(m.group(1))
        if rating is None:
            el = await card.query_selector("[aria-label*='out of 5 stars']")
            if el:
                label = await el.get_attribute("aria-label") or ""
                m = re.search(r"([\d.]+)\s*out of", label)
                if m:
                    rating = float(m.group(1))

        # Review count
        review_count = None
        el = await card.query_selector("a[aria-label*='ratings'], a[aria-label*='rating']")
        if el:
            label = await el.get_attribute("aria-label") or ""
            digits = re.sub(r"[^\d]", "", label.split("rating")[0])
            if digits:
                review_count = int(digits)
        if review_count is None:
            card_text = await _text_of(card)
            m = re.search(r"out of 5 stars[^\(]{0,40}\(?([\d,]{1,9})\)?", card_text)
            if m:
                digits = m.group(1).replace(",", "")
                if digits.isdigit():
                    review_count = int(digits)

        return {
            "title":        title,
            "image_url":    image_url,
            "price_inr":    price,
            "rating":       rating,
            "review_count": review_count,
            "url":          url,
            "asin":         extract_asin(url),
        }

    except Exception as e:
        print(f"  ✗ Error parsing card: {e}")
        return None


# ── Search page scraper ───────────────────────────────────────────────────────

async def scrape_search_page(page, brand: dict, max_pages: int = 3) -> List[dict]:
    query        = brand["query"]
    must_contain = brand["must_contain"]
    label        = brand["label"]
    products     = []

    for page_num in range(1, max_pages + 1):
        url = f"{BASE_URL}?k={query.replace(' ', '+')}&page={page_num}"
        print(f"  → Fetching page {page_num}: {url}")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        except PlaywrightTimeout:
            print(f"  ✗ Timeout on page {page_num}, skipping.")
            break

        try:
            await page.wait_for_selector('[data-component-type="s-search-result"]', timeout=10_000)
        except PlaywrightTimeout:
            content = await page.content()
            if "captcha" in content.lower() or "robot" in content.lower():
                print("  ✗ CAPTCHA detected.")
            else:
                print(f"  ✗ No product cards found on page {page_num}.")
            break

        cards = await page.query_selector_all('[data-component-type="s-search-result"]')
        print(f"  ✓ Found {len(cards)} cards on page {page_num}")

        kept = 0
        for card in cards:
            product = await extract_card_data(card)
            if product and title_matches_brand(product["title"], must_contain):
                product["brand"] = assign_brand(product["title"]) or label
                products.append(product)
                kept += 1

        print(f"     ✓ Kept {kept} matching '{label}'")
        random_delay()

    return products


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    all_products = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 800},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={
                "Accept-Language": "en-IN,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        print("Warming up — visiting Amazon India homepage …")
        await page.goto("https://www.amazon.in", wait_until="domcontentloaded", timeout=30_000)
        random_delay(2, 4)

        for brand in BRANDS:
            print(f"\n{'─'*60}")
            print(f"Searching: {brand['query']}")
            print(f"{'─'*60}")
            products = await scrape_search_page(page, brand, max_pages=3)
            for p in products:
                p["search_query"] = brand["query"]
            all_products.extend(products)
            print(f"  Collected {len(products)} products for '{brand['label']}'")
            random_delay(2, 5)

        await browser.close()

    if not all_products:
        print("\n⚠  No products scraped.")
        return

    # ── Groq weight extraction ────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"Running Groq weight extraction on {len(all_products)} products …")
    print(f"{'─'*60}")
    all_products = batch_extract_weights(all_products, batch_size=20)

    df = pd.DataFrame(all_products)

    # Cost per gram
    df["cost_per_gram"] = df.apply(
        lambda r: round(r["price_inr"] / r["weight_g"], 2)
        if pd.notna(r["price_inr"]) and pd.notna(r["weight_g"]) and r["weight_g"] > 0
        else None,
        axis=1,
    )

    # Dedupe on ASIN where available
    has_asin = df["asin"].notna()
    df = pd.concat([
        df[has_asin].drop_duplicates(subset=["asin"]),
        df[~has_asin].drop_duplicates(subset=["title", "price_inr"]),
    ])
    df = df.sort_values(["brand", "cost_per_gram"], na_position="last").reset_index(drop=True)

    df.to_csv(OUTPUT_CSV, index=False)

    short_titles = (df["title"].str.len() < 30).sum()
    print(f"\n✓ Saved {len(df)} products to {OUTPUT_CSV}")
    print(f"  With images     : {df['image_url'].notna().sum()}")
    print(f"  With price      : {df['price_inr'].notna().sum()}")
    print(f"  With weight     : {df['weight_g'].notna().sum()}")
    print(f"  With cost/gram  : {df['cost_per_gram'].notna().sum()}")
    print(f"  With reviews    : {df['review_count'].notna().sum()}")
    if short_titles:
        print(f"  ⚠ {short_titles} suspiciously short titles — Amazon layout may have shifted.")


if __name__ == "__main__":
    asyncio.run(main())