"""
Coffee Price Comparison - Streamlit App
Run: streamlit run app.py
Scrape first: python3 scraper.py
"""

import streamlit as st
import pandas as pd
import os

CSV_PATH = "coffee_data.csv"

st.set_page_config(
    page_title="☕ Coffee Price Comparison",
    page_icon="☕",
    layout="wide",
)

# ── Styles ────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .main { background-color: #1a0f00; }
    [data-testid="stAppViewContainer"] { background-color: #1a0f00; }
    [data-testid="stSidebar"] { background-color: #2d1a00; }

    .title-block {
        text-align: center;
        padding: 1.5rem 0 0.5rem;
    }
    .title-block h1 {
        color: #f5c842;
        font-size: 2.4rem;
        font-weight: 800;
        margin: 0;
    }
    .title-block p {
        color: #c49a4a;
        font-size: 1rem;
        margin: 0.3rem 0 0;
    }

    .card {
        background: #2d1a00;
        border: 1px solid #4a2e00;
        border-radius: 14px;
        padding: 1rem;
        margin-bottom: 1rem;
        transition: border-color 0.2s;
        height: 100%;
    }
    .card:hover { border-color: #f5c842; }

    .card img {
        width: 100%;
        height: 180px;
        object-fit: contain;
        border-radius: 8px;
        background: #fff;
        padding: 8px;
    }
    .card-title {
        color: #f0e0c0;
        font-size: 0.82rem;
        font-weight: 600;
        margin: 0.6rem 0 0.4rem;
        line-height: 1.3;
        display: -webkit-box;
        -webkit-line-clamp: 3;
        -webkit-box-orient: vertical;
        overflow: hidden;
        min-height: 3.2em;
    }
    .badge-brand {
        display: inline-block;
        background: #4a2e00;
        color: #f5c842;
        border-radius: 20px;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 2px 10px;
        margin-bottom: 0.5rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .stat-row {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        margin-top: 0.5rem;
        gap: 0.5rem;
    }
    .stat-price {
        color: #f5c842;
        font-size: 1.3rem;
        font-weight: 800;
    }
    .stat-weight {
        color: #a07840;
        font-size: 0.78rem;
    }
    .stat-cpg {
        color: #5cb85c;
        font-size: 0.85rem;
        font-weight: 700;
        text-align: right;
    }
    .stat-cpg span {
        display: block;
        color: #a07840;
        font-size: 0.68rem;
        font-weight: 400;
    }
    .no-cpg { color: #777; font-size: 0.78rem; }
    .rating-row {
        color: #c49a4a;
        font-size: 0.75rem;
        margin-top: 0.3rem;
    }
    .amazon-btn {
        display: block;
        text-align: center;
        background: #f5c842;
        color: #1a0f00 !important;
        border-radius: 8px;
        padding: 6px 0;
        font-size: 0.8rem;
        font-weight: 700;
        text-decoration: none !important;
        margin-top: 0.8rem;
    }
    .amazon-btn:hover { background: #ffd966; }

    .metric-card {
        background: #2d1a00;
        border: 1px solid #4a2e00;
        border-radius: 10px;
        padding: 0.8rem 1rem;
        text-align: center;
    }
    .metric-card .val {
        font-size: 1.6rem;
        font-weight: 800;
        color: #f5c842;
    }
    .metric-card .lbl {
        font-size: 0.75rem;
        color: #a07840;
        margin-top: 2px;
    }

    /* Sort/filter bar */
    label, .stSelectbox label, .stMultiSelect label, .stSlider label {
        color: #c49a4a !important;
        font-weight: 600;
    }
    .stSelectbox > div > div, .stMultiSelect > div > div {
        background: #2d1a00 !important;
        border-color: #4a2e00 !important;
        color: #f0e0c0 !important;
    }
    div[data-testid="stMetric"] label { color: #c49a4a !important; }
</style>
""", unsafe_allow_html=True)

# ── Load data ─────────────────────────────────────────────────────────────────

@st.cache_data
def load_data():
    if not os.path.exists(CSV_PATH):
        return pd.DataFrame()
    df = pd.read_csv(CSV_PATH)
    return df

df = load_data()

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="title-block">
    <h1>☕ Coffee Price Comparison</h1>
    <p>Nescafe · Nescafe Gold · Bru Gold · Davidoff — scraped from Amazon India</p>
</div>
""", unsafe_allow_html=True)

if df.empty:
    st.error("No data found. Run `python3 scraper.py` first to scrape Amazon.")
    st.stop()

# ── Sidebar filters ───────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🎛 Filters")

    brands = sorted(df["brand"].dropna().unique().tolist())
    selected_brands = st.multiselect("Brand", brands, default=brands)

    sort_by = st.selectbox("Sort by", [
        "Cost per gram (cheapest first)",
        "Price (low to high)",
        "Price (high to low)",
        "Rating (highest first)",
        "Weight (lightest first)",
        "Weight (heaviest first)",
    ])

    only_with_cpg = st.checkbox("Only show products with cost/gram data", value=False)
    only_with_price = st.checkbox("Only show products with price", value=False)

    st.markdown("---")
    st.markdown("### 💸 Price range (₹)")
    price_min = float(df["price_inr"].dropna().min()) if df["price_inr"].notna().any() else 0.0
    price_max = float(df["price_inr"].dropna().max()) if df["price_inr"].notna().any() else 5000.0
    price_range = st.slider("", min_value=price_min, max_value=price_max,
                            value=(price_min, price_max), step=10.0)

    st.markdown("---")
    if st.button("🔄 Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Filter + sort ─────────────────────────────────────────────────────────────

filtered = df[df["brand"].isin(selected_brands)].copy()

if only_with_cpg:
    filtered = filtered[filtered["cost_per_gram"].notna()]
if only_with_price:
    filtered = filtered[filtered["price_inr"].notna()]

# Price range filter
price_mask = (
    filtered["price_inr"].isna() |
    ((filtered["price_inr"] >= price_range[0]) & (filtered["price_inr"] <= price_range[1]))
)
filtered = filtered[price_mask]

sort_map = {
    "Cost per gram (cheapest first)": ("cost_per_gram", True),
    "Price (low to high)":            ("price_inr", True),
    "Price (high to low)":            ("price_inr", False),
    "Rating (highest first)":         ("rating", False),
    "Weight (lightest first)":        ("weight_g", True),
    "Weight (heaviest first)":        ("weight_g", False),
}
sort_col, sort_asc = sort_map[sort_by]
filtered = filtered.sort_values(sort_col, ascending=sort_asc, na_position="last").reset_index(drop=True)

# ── Summary metrics ───────────────────────────────────────────────────────────

st.markdown("<br>", unsafe_allow_html=True)
m1, m2, m3, m4 = st.columns(4)

with m1:
    st.markdown(f"""<div class="metric-card">
        <div class="val">{len(filtered)}</div>
        <div class="lbl">Products shown</div>
    </div>""", unsafe_allow_html=True)

with m2:
    n_price = filtered["price_inr"].notna().sum()
    st.markdown(f"""<div class="metric-card">
        <div class="val">{n_price}</div>
        <div class="lbl">With price data</div>
    </div>""", unsafe_allow_html=True)

with m3:
    n_cpg = filtered["cost_per_gram"].notna().sum()
    st.markdown(f"""<div class="metric-card">
        <div class="val">{n_cpg}</div>
        <div class="lbl">With cost/gram</div>
    </div>""", unsafe_allow_html=True)

with m4:
    best = filtered[filtered["cost_per_gram"].notna()]["cost_per_gram"].min()
    best_str = f"₹{best:.2f}/g" if pd.notna(best) else "—"
    st.markdown(f"""<div class="metric-card">
        <div class="val">{best_str}</div>
        <div class="lbl">Best value</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Product grid ──────────────────────────────────────────────────────────────

COLS = 4

if filtered.empty:
    st.warning("No products match your filters.")
else:
    rows = [filtered.iloc[i:i+COLS] for i in range(0, len(filtered), COLS)]
    for row_df in rows:
        cols = st.columns(COLS)
        for col, (_, row) in zip(cols, row_df.iterrows()):
            with col:
                # Image
                img_tag = ""
                if pd.notna(row.get("image_url")):
                    img_tag = f'<img src="{row["image_url"]}" alt="product image">'
                else:
                    img_tag = '<div style="height:180px;background:#3a2200;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#a07840;font-size:2rem;">☕</div>'

                # Price
                price_str = f"₹{row['price_inr']:,.0f}" if pd.notna(row.get("price_inr")) else "—"

                # Weight
                if pd.notna(row.get("weight_g")):
                    w = row["weight_g"]
                    weight_str = f"{w/1000:.1f} kg" if w >= 1000 else f"{w:.0f} g"
                else:
                    weight_str = "weight unknown"

                # Cost per gram
                if pd.notna(row.get("cost_per_gram")):
                    cpg_html = f'<div class="stat-cpg">₹{row["cost_per_gram"]:.2f}/g<span>per gram</span></div>'
                else:
                    cpg_html = '<div class="no-cpg">cost/gram N/A</div>'

                # Rating
                rating_html = ""
                if pd.notna(row.get("rating")):
                    stars = "★" * int(round(row["rating"])) + "☆" * (5 - int(round(row["rating"])))
                    reviews = f" ({int(row['review_count']):,})" if pd.notna(row.get("review_count")) else ""
                    rating_html = f'<div class="rating-row">{stars} {row["rating"]}{reviews}</div>'

                # Amazon link
                link_html = ""
                if pd.notna(row.get("url")):
                    link_html = f'<a class="amazon-btn" href="{row["url"]}" target="_blank">View on Amazon ↗</a>'

                st.markdown(f"""
                <div class="card">
                    {img_tag}
                    <div class="badge-brand">{row.get('brand', '')}</div>
                    <div class="card-title">{row.get('title', '')}</div>
                    <div class="stat-row">
                        <div>
                            <div class="stat-price">{price_str}</div>
                            <div class="stat-weight">{weight_str}</div>
                        </div>
                        {cpg_html}
                    </div>
                    {rating_html}
                    {link_html}
                </div>
                """, unsafe_allow_html=True)

# ── Raw data table ────────────────────────────────────────────────────────────

with st.expander("📊 View raw data table"):
    table_cols = ["brand", "title", "weight_g", "price_inr", "cost_per_gram", "rating", "review_count"]
    table_cols = [c for c in table_cols if c in filtered.columns]
    st.dataframe(
        filtered[table_cols].style.format({
            "price_inr": "₹{:.0f}",
            "cost_per_gram": "₹{:.2f}",
            "weight_g": "{:.0f}g",
            "rating": "{:.1f}",
        }, na_rep="—"),
        use_container_width=True,
        height=400,
    )

    st.download_button(
        "⬇ Download as CSV",
        data=filtered.to_csv(index=False),
        file_name="coffee_prices.csv",
        mime="text/csv",
    )

st.markdown(f"<p style='text-align:center;color:#4a2e00;font-size:0.75rem;margin-top:2rem;'>Last scraped: {os.path.getmtime(CSV_PATH) and pd.Timestamp.fromtimestamp(os.path.getmtime(CSV_PATH)).strftime('%d %b %Y, %I:%M %p')}</p>", unsafe_allow_html=True)