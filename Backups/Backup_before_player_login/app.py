import streamlit as st
import sqlite3
import base64
import pandas as pd
import requests
from urllib.parse import urlparse, parse_qs
from datetime import datetime

st.title("Riftbound → OpenRift Collection Exporter")

conn = sqlite3.connect("riftbound_library.db")
c = conn.cursor()

# MASTER CARD DATABASE
c.execute("""
CREATE TABLE IF NOT EXISTS master_cards (
    code TEXT PRIMARY KEY,
    name TEXT,
    rarity TEXT,
    img TEXT,
    set_name TEXT,
    set_prefix TEXT
)
""")

# USER COLLECTION
c.execute("""
CREATE TABLE IF NOT EXISTS collection (
    code TEXT PRIMARY KEY,
    quantity INTEGER DEFAULT 0
)
""")

# IMPORTED BOOSTERS
c.execute("""
CREATE TABLE IF NOT EXISTS imported_boosters (
    seed TEXT PRIMARY KEY,
    import_date TEXT,
    set_prefix TEXT
)
""")

conn.commit()


def normalize_code(code):
    raw_code = str(code).strip().upper()
    parts = raw_code.split("-")

    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"

    return raw_code


def add_to_collection(code):
    code = normalize_code(code)

    c.execute("SELECT quantity FROM collection WHERE code = ?", (code,))
    existing = c.fetchone()

    if existing:
        c.execute(
            "UPDATE collection SET quantity = ? WHERE code = ?",
            (existing[0] + 1, code)
        )
    else:
        c.execute(
            "INSERT INTO collection (code, quantity) VALUES (?, ?)",
            (code, 1)
        )


def sync_master_database(set_id):
    set_id = set_id.lower().strip()
    page = 1
    total_synced = 0

    while True:
        url = f"https://api.riftcodex.com/cards?size=100&page={page}&set_id={set_id}&sort=collector_number"

        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        items = data.get("items", [])

        if not items:
            break

        for card in items:
            raw_code = (
                card.get("riftbound_id")
                or card.get("code")
                or card.get("card_id")
                or card.get("id")
                or ""
            )

            code = normalize_code(raw_code)

            name = card.get("name", "")

            classification = card.get("classification", {})
            rarity = ""

            if isinstance(classification, dict):
                rarity = classification.get("rarity", "")
            else:
                rarity = str(classification)

            media = card.get("media", {})
            img = ""

            if isinstance(media, dict):
                img = media.get("image_url", "") or media.get("image", "")

            set_data = card.get("set", {})
            set_name = "Unknown"
            set_prefix = set_id.upper()

            if isinstance(set_data, dict):
                set_name = set_data.get("label", "") or set_data.get("name", "Unknown")
                set_prefix = set_data.get("set_id", set_id).upper()

            if code:
                c.execute("""
                INSERT OR REPLACE INTO master_cards (
                    code,
                    name,
                    rarity,
                    img,
                    set_name,
                    set_prefix
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    code,
                    name,
                    rarity,
                    img,
                    set_name,
                    set_prefix
                ))

                total_synced += 1

        conn.commit()

        if len(items) < 100:
            break

        page += 1

    return total_synced


def get_collection_cards():
    return c.execute("""
    SELECT
        collection.code,
        COALESCE(master_cards.name, collection.code) as name,
        COALESCE(master_cards.rarity, 'Unknown') as rarity,
        COALESCE(master_cards.img, '') as img,
        COALESCE(master_cards.set_name, 'Unknown') as set_name,
        COALESCE(master_cards.set_prefix, SUBSTR(collection.code, 1, INSTR(collection.code, '-') - 1)) as set_prefix,
        collection.quantity
    FROM collection
    LEFT JOIN master_cards
    ON collection.code = master_cards.code
    ORDER BY collection.code
    """).fetchall()


# 1. SYNC MASTER CARDS
st.header("1. Sync Master Card Database")

set_id = st.text_input("Set ID to sync", value="UNL")

if st.button("Sync Master Cards"):
    try:
        count = sync_master_database(set_id)
        st.success(f"Synced {count} cards from set {set_id.upper()}!")
    except Exception as e:
        st.error(f"Sync failed: {e}")


# 2. IMPORT BOOSTER URL
st.header("2. Import Booster from Rifty URL")

booster_url = st.text_input("Paste Rifty booster URL")

if st.button("Import Booster URL"):
    try:
        parsed = urlparse(booster_url)
        params = parse_qs(parsed.query)

        seed = params.get("seed", [None])[0]
        edition = params.get("edition", ["UNKNOWN"])[0].upper()

        if not seed:
            st.error("No seed found in URL.")
        else:
            c.execute("SELECT seed FROM imported_boosters WHERE seed = ?", (seed,))
            existing_seed = c.fetchone()

            if existing_seed:
                st.warning("This booster has already been imported.")
            else:
                padded_seed = seed + "=" * (-len(seed) % 4)
                decoded = base64.b64decode(padded_seed).decode("utf-8")
                card_codes = [normalize_code(code) for code in decoded.split(",")]

                for code in card_codes:
                    add_to_collection(code)

                c.execute("""
                INSERT INTO imported_boosters (
                    seed,
                    import_date,
                    set_prefix
                )
                VALUES (?, ?, ?)
                """, (
                    seed,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    edition
                ))

                conn.commit()

                st.success(f"Imported {len(card_codes)} cards!")

    except Exception as e:
        st.error(f"Error importing URL: {e}")


cards = get_collection_cards()


# 3. EXPORT
st.header("3. Export for OpenRift")

export_data = []

for code, name, rarity, img, set_name, set_prefix, quantity in cards:
    export_data.append({
        "Variant Number": code,
        "Card Name": name,
        "Set": set_name,
        "Set Prefix": set_prefix,
        "Rarity": rarity,
        "Variant Type": "Normal",
        "Variant Label": "",
        "Quantity": quantity,
        "Language": "English",
        "Condition": "Near Mint"
    })

df = pd.DataFrame(export_data)
csv = df.to_csv(index=False).encode("utf-8")

st.download_button(
    label="Download OpenRift CSV",
    data=csv,
    file_name="openrift_import.csv",
    mime="text/csv"
)


# 4. COLLECTION VIEW
st.header("4. My Collection")

st.write(f"Unique cards: {len(cards)}")
st.write(f"Total cards: {sum(card[6] for card in cards)}")

search = st.text_input("Search collection")

# FILTERS
all_sets = sorted(list(set(card[5] for card in cards)))
selected_set = st.selectbox("Filter by Set", ["All"] + all_sets)

all_rarities = sorted(list(set(card[2] for card in cards)))
selected_rarity = st.selectbox("Filter by Rarity", ["All"] + all_rarities)

missing_only = st.checkbox("Show cards with missing info only")

# APPLY FILTERS
if search:
    cards = [
        card for card in cards
        if search.lower() in card[0].lower()
        or search.lower() in card[1].lower()
    ]

if selected_set != "All":
    cards = [
        card for card in cards
        if card[5] == selected_set
    ]

if selected_rarity != "All":
    cards = [
        card for card in cards
        if card[2] == selected_rarity
    ]

if missing_only:
    cards = [
        card for card in cards
        if card[1] == card[0]
        or card[2] == "Unknown"
    ]

columns_per_row = 4

for i in range(0, len(cards), columns_per_row):
    cols = st.columns(columns_per_row)

    for col, card in zip(cols, cards[i:i + columns_per_row]):
        code, name, rarity, img, set_name, set_prefix, quantity = card

        with col:
            if img:
                st.image(img, use_container_width=True)
            else:
                st.warning("No image")

            st.markdown(f"**{name}**")
            st.caption(f"{code}")
            st.caption(f"{rarity}")
            st.write(f"Qty: **{quantity}**")


# 5. MANUAL CARD FIXER
st.header("5. Manual Card Fixer")

st.write("Use this for missing token cards or incorrect card data.")

fix_code = st.text_input("Card ID", value="UNL-T07")
fix_name = st.text_input("Card Name")
fix_rarity = st.text_input("Rarity", value="Common")
fix_set = st.text_input("Set Name", value="Unleashed")
fix_prefix = st.text_input("Set Prefix", value="UNL")
fix_image = st.text_input(
    "Image URL",
    value="https://storage.googleapis.com/runebound-public/img/unl/UNL-T07.webp"
)

if st.button("Save Manual Card Fix"):
    code = normalize_code(fix_code)

    c.execute("""
    INSERT OR REPLACE INTO master_cards (
        code,
        name,
        rarity,
        img,
        set_name,
        set_prefix
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        code,
        fix_name,
        fix_rarity,
        fix_image,
        fix_set,
        fix_prefix
    ))

    conn.commit()

    st.success(f"Saved master card info for {code}")


# 6. PACK HISTORY
st.header("6. Imported Booster History")

history = c.execute("""
SELECT
    import_date,
    set_prefix,
    seed
FROM imported_boosters
ORDER BY import_date DESC
""").fetchall()

if history:
    history_df = pd.DataFrame(
        history,
        columns=["Import Date", "Set", "Seed"]
    )

    history_df.index = history_df.index + 1
    history_df.index.name = "Pack"

    history_df["Import Date"] = pd.to_datetime(
        history_df["Import Date"]
    ).dt.strftime("%Y-%m-%d %I:%M %p")

    st.dataframe(history_df, use_container_width=True)
else:
    st.info("No boosters imported yet.")


# 7. RESET
st.header("7. Reset Collection")

st.warning(
    "This clears your collection and booster history, "
    "but keeps synced master card data."
)

confirm_reset = st.checkbox(
    "I understand this will reset my collection only"
)

if st.button("Reset My Collection"):
    if confirm_reset:
        c.execute("DELETE FROM collection")
        c.execute("DELETE FROM imported_boosters")
        conn.commit()

        st.success("Collection reset successfully.")
    else:
        st.error("Check the confirmation box first.")