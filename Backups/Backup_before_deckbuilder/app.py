import streamlit as st
import sqlite3
import base64
import json
import pandas as pd
import requests
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from collections import Counter

st.set_page_config(page_title="PackTrack", layout="wide")

st.title("PackTrack")
st.caption("Riftbound Sealed League Companion App")

conn = sqlite3.connect("riftbound_library.db")
c = conn.cursor()

PLAYERS = [
    (1, "Russ", "poro7", 1),
    (2, "Kayla", "jinx4", 0),
    (3, "Nick", "noxus2", 0),
    (4, "Steve", "zaun8", 0),
    (5, "Tyler", "yordle5", 0),
    (6, "Henry", "demacia9", 0),
]

PACK_SCHEDULE = {
    1: "6 Packs Unleashed",
    2: "3 Packs Origins",
    3: "3 Packs Spiritforged",
    4: "3 Packs Unleashed",
    5: "3 Packs Origins",
    6: "3 Packs Spiritforged",
}

# --------------------
# DATABASE SETUP
# --------------------

c.execute("""
CREATE TABLE IF NOT EXISTS players (
    player_id INTEGER PRIMARY KEY,
    player_name TEXT UNIQUE,
    passcode TEXT,
    is_admin INTEGER DEFAULT 0
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS master_cards (
    code TEXT PRIMARY KEY,
    name TEXT,
    rarity TEXT,
    img TEXT,
    set_name TEXT,
    set_prefix TEXT,
    card_type TEXT,
    supertype TEXT,
    domain TEXT,
    energy INTEGER,
    might INTEGER,
    power INTEGER,
    tags TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS collection (
    player_id INTEGER,
    code TEXT,
    quantity INTEGER DEFAULT 0,
    PRIMARY KEY (player_id, code)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS imported_boosters (
    player_id INTEGER,
    seed TEXT,
    import_date TEXT,
    set_prefix TEXT,
    total_cards INTEGER DEFAULT 0,
    new_unique_count INTEGER DEFAULT 0,
    source_url TEXT,
    PRIMARY KEY (player_id, seed)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS booster_cards (
    player_id INTEGER,
    seed TEXT,
    code TEXT,
    quantity INTEGER DEFAULT 1,
    PRIMARY KEY (player_id, seed, code)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS app_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT
)
""")

conn.commit()


def ensure_column(table, column, column_type):
    c.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in c.fetchall()]

    if column not in columns:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        conn.commit()


ensure_column("imported_boosters", "total_cards", "INTEGER DEFAULT 0")
ensure_column("imported_boosters", "new_unique_count", "INTEGER DEFAULT 0")
ensure_column("imported_boosters", "source_url", "TEXT")

ensure_column("master_cards", "card_type", "TEXT")
ensure_column("master_cards", "supertype", "TEXT")
ensure_column("master_cards", "domain", "TEXT")
ensure_column("master_cards", "energy", "INTEGER")
ensure_column("master_cards", "might", "INTEGER")
ensure_column("master_cards", "power", "INTEGER")
ensure_column("master_cards", "tags", "TEXT")

for player_id, player_name, passcode, is_admin in PLAYERS:
    c.execute("""
    INSERT OR REPLACE INTO players (
        player_id,
        player_name,
        passcode,
        is_admin
    )
    VALUES (?, ?, ?, ?)
    """, (player_id, player_name, passcode, is_admin))

conn.commit()


# --------------------
# HELPERS
# --------------------

def get_setting(key, default=""):
    c.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = ?",
        (key,)
    )
    result = c.fetchone()
    return result[0] if result else default


def set_setting(key, value):
    c.execute("""
    INSERT OR REPLACE INTO app_settings (
        setting_key,
        setting_value
    )
    VALUES (?, ?)
    """, (key, str(value)))
    conn.commit()


def normalize_code(code):
    raw_code = str(code).strip().upper()
    parts = raw_code.split("-")

    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"

    return raw_code


def get_current_player_id():
    return st.session_state.get("player_id")


def get_current_player_name():
    return st.session_state.get("player_name")


def is_admin():
    return st.session_state.get("is_admin", False)


def logout():
    st.session_state.pop("player_id", None)
    st.session_state.pop("player_name", None)
    st.session_state.pop("is_admin", None)


def add_to_collection(player_id, code):
    code = normalize_code(code)

    c.execute(
        "SELECT quantity FROM collection WHERE player_id = ? AND code = ?",
        (player_id, code)
    )
    existing = c.fetchone()

    if existing:
        c.execute(
            "UPDATE collection SET quantity = ? WHERE player_id = ? AND code = ?",
            (existing[0] + 1, player_id, code)
        )
    else:
        c.execute(
            "INSERT INTO collection (player_id, code, quantity) VALUES (?, ?, ?)",
            (player_id, code, 1)
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
            card_type = ""
            supertype = ""
            domain = ""

            if isinstance(classification, dict):
                rarity = classification.get("rarity", "")
                card_type = classification.get("type", "")
                supertype = classification.get("supertype", "") or ""

                domain_value = classification.get("domain", [])
                if isinstance(domain_value, list):
                    domain = ",".join(domain_value)
                else:
                    domain = str(domain_value)
            else:
                rarity = str(classification)

            attributes = card.get("attributes", {})
            energy = None
            might = None
            power = None

            if isinstance(attributes, dict):
                energy = attributes.get("energy")
                might = attributes.get("might")
                power = attributes.get("power")

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

            tags_value = card.get("tags", [])
            if isinstance(tags_value, list):
                tags = ",".join(tags_value)
            else:
                tags = str(tags_value)

            if code:
                c.execute("""
                INSERT OR REPLACE INTO master_cards (
                    code,
                    name,
                    rarity,
                    img,
                    set_name,
                    set_prefix,
                    card_type,
                    supertype,
                    domain,
                    energy,
                    might,
                    power,
                    tags
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    code,
                    name,
                    rarity,
                    img,
                    set_name,
                    set_prefix,
                    card_type,
                    supertype,
                    domain,
                    energy,
                    might,
                    power,
                    tags
                ))

                total_synced += 1

        conn.commit()

        if len(items) < 100:
            break

        page += 1

    return total_synced


def sync_all_sets():
    set_ids = ["UNL", "OGN", "SFD"]
    results = {}

    for set_id in set_ids:
        results[set_id] = sync_master_database(set_id)

    return results


def get_collection_cards(player_id):
    return c.execute("""
    SELECT
        collection.code,
        COALESCE(master_cards.name, collection.code) as name,
        COALESCE(master_cards.rarity, 'Unknown') as rarity,
        COALESCE(master_cards.img, '') as img,
        COALESCE(master_cards.set_name, 'Unknown') as set_name,
        COALESCE(master_cards.set_prefix, SUBSTR(collection.code, 1, INSTR(collection.code, '-') - 1)) as set_prefix,
        collection.quantity,
        COALESCE(master_cards.card_type, '') as card_type,
        COALESCE(master_cards.supertype, '') as supertype,
        COALESCE(master_cards.domain, '') as domain,
        master_cards.energy,
        master_cards.might,
        master_cards.power,
        COALESCE(master_cards.tags, '') as tags
    FROM collection
    LEFT JOIN master_cards
    ON collection.code = master_cards.code
    WHERE collection.player_id = ?
    ORDER BY collection.code
    """, (player_id,)).fetchall()


# --------------------
# LOGIN SCREEN
# --------------------

if "player_id" not in st.session_state:
    st.header("Login")

    player_names = [player[1] for player in PLAYERS]

    selected_name = st.selectbox("Select your name", player_names)
    entered_passcode = st.text_input("Enter your passcode", type="password")

    if st.button("Login"):
        c.execute("""
        SELECT player_id, player_name, is_admin
        FROM players
        WHERE player_name = ? AND passcode = ?
        """, (selected_name, entered_passcode))

        player = c.fetchone()

        if player:
            st.session_state["player_id"] = player[0]
            st.session_state["player_name"] = player[1]
            st.session_state["is_admin"] = bool(player[2])
            st.rerun()
        else:
            st.error("Incorrect name or passcode.")

    st.stop()


player_id = get_current_player_id()
player_name = get_current_player_name()

with st.sidebar:
    st.write(f"Logged in as **{player_name}**")

    if is_admin():
        st.success("Admin")

    if st.button("Logout"):
        logout()
        st.rerun()


# --------------------
# TABS
# --------------------

if is_admin():
    tabs = st.tabs([
        "Dashboard",
        "Import Packs",
        "My Collection",
        "Export CSV",
        "Pack History",
        "Admin Tools",
    ])
else:
    tabs = st.tabs([
        "Dashboard",
        "Import Packs",
        "My Collection",
        "Export CSV",
        "Pack History",
    ])


# --------------------
# DASHBOARD
# --------------------

with tabs[0]:
    announcement = get_setting("announcement", "").strip()
    current_week = int(get_setting("current_week", "1"))

    if announcement:
        col1, col2 = st.columns([1, 2])

        with col1:
            st.header(f"Welcome, {player_name}")

        with col2:
            st.info(announcement)
    else:
        st.header(f"Welcome, {player_name}")

    cards = get_collection_cards(player_id)

    total_cards = sum(card[6] for card in cards)
    unique_cards = len(cards)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Total Cards", total_cards)

    with col2:
        st.metric("Unique Cards", unique_cards)

    with col3:
        c.execute(
            "SELECT COUNT(*) FROM imported_boosters WHERE player_id = ?",
            (player_id,)
        )
        pack_count = c.fetchone()[0]
        st.metric("Packs Imported", pack_count)

    st.subheader("Current League Week")
    st.write(f"Week {current_week}: **{PACK_SCHEDULE.get(current_week, 'No schedule set')}**")

    with st.expander("Full Pack Schedule"):
        for week, schedule in PACK_SCHEDULE.items():
            st.write(f"Week {week}: {schedule}")


# --------------------
# IMPORT PACKS
# --------------------

with tabs[1]:
    st.header("Import Booster Packs")

    if "import_message" in st.session_state:
        st.success(st.session_state["import_message"])
        del st.session_state["import_message"]

    if "duplicate_message" in st.session_state:
        st.warning(st.session_state["duplicate_message"])
        del st.session_state["duplicate_message"]

    if "error_message" in st.session_state:
        st.error(st.session_state["error_message"])
        del st.session_state["error_message"]

    st.write("Paste one Rifty booster URL per line.")

    if "clear_booster_input" in st.session_state:
        st.session_state["booster_urls_input"] = ""
        del st.session_state["clear_booster_input"]

    booster_urls = st.text_area(
        "Booster URLs",
        height=180,
        key="booster_urls_input"
    )

    if st.button("Import Booster URLs"):
        urls = [
            url.strip()
            for url in booster_urls.splitlines()
            if url.strip()
        ]

        if not urls:
            st.error("Paste at least one booster URL.")
        else:
            imported_count = 0
            duplicate_count = 0
            error_count = 0
            total_cards_imported = 0
            total_new_unique = 0

            for booster_url in urls:
                try:
                    parsed = urlparse(booster_url)
                    params = parse_qs(parsed.query)

                    seed = params.get("seed", [None])[0]
                    edition = params.get("edition", ["UNKNOWN"])[0].upper()

                    if not seed:
                        error_count += 1
                        continue

                    c.execute(
                        "SELECT seed FROM imported_boosters WHERE player_id = ? AND seed = ?",
                        (player_id, seed)
                    )
                    existing_seed = c.fetchone()

                    if existing_seed:
                        duplicate_count += 1
                        continue

                    padded_seed = seed + "=" * (-len(seed) % 4)
                    decoded = base64.b64decode(padded_seed).decode("utf-8")
                    card_codes = [normalize_code(code) for code in decoded.split(",")]

                    unique_codes_in_pack = set(card_codes)
                    new_unique_count = 0

                    for code in unique_codes_in_pack:
                        c.execute(
                            "SELECT quantity FROM collection WHERE player_id = ? AND code = ?",
                            (player_id, code)
                        )
                        if c.fetchone() is None:
                            new_unique_count += 1

                    card_counter = Counter(card_codes)

                    for code in card_codes:
                        add_to_collection(player_id, code)

                    for code, qty in card_counter.items():
                        c.execute("""
                        INSERT OR REPLACE INTO booster_cards (
                            player_id,
                            seed,
                            code,
                            quantity
                        )
                        VALUES (?, ?, ?, ?)
                        """, (
                            player_id,
                            seed,
                            code,
                            qty
                        ))

                    c.execute("""
                    INSERT INTO imported_boosters (
                        player_id,
                        seed,
                        import_date,
                        set_prefix,
                        total_cards,
                        new_unique_count,
                        source_url
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        player_id,
                        seed,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        edition,
                        len(card_codes),
                        new_unique_count,
                        booster_url
                    ))

                    imported_count += 1
                    total_cards_imported += len(card_codes)
                    total_new_unique += new_unique_count

                except Exception:
                    error_count += 1

            conn.commit()

            if imported_count == 1:
                st.session_state["import_message"] = (
                    f"1 pack imported successfully. "
                    f"{total_cards_imported} cards • {total_new_unique} new cards."
                )
            elif imported_count > 1:
                st.session_state["import_message"] = (
                    f"{imported_count} packs imported successfully. "
                    f"{total_cards_imported} cards • {total_new_unique} new cards."
                )

            if duplicate_count > 0:
                st.session_state["duplicate_message"] = (
                    f"{duplicate_count} duplicate pack(s) skipped."
                )

            if error_count > 0:
                st.session_state["error_message"] = (
                    f"{error_count} URL(s) could not be imported."
                )

            st.session_state["clear_booster_input"] = True
            st.rerun()


# --------------------
# COLLECTION
# --------------------

with tabs[2]:
    st.header("My Collection")

    cards = get_collection_cards(player_id)

    st.write(f"Unique cards: {len(cards)}")
    st.write(f"Total cards: {sum(card[6] for card in cards)}")

    search = st.text_input("Search collection")

    all_sets = sorted(list(set(card[5] for card in cards)))
    selected_set = st.selectbox("Filter by Set", ["All"] + all_sets)

    all_rarities = sorted(list(set(card[2] for card in cards)))
    selected_rarity = st.selectbox("Filter by Rarity", ["All"] + all_rarities)

    all_types = sorted(list(set(card[7] for card in cards if card[7])))
    selected_type = st.selectbox("Filter by Type", ["All"] + all_types)

    all_domains = sorted(list(set(
        domain.strip()
        for card in cards
        for domain in str(card[9]).split(",")
        if domain.strip()
    )))
    selected_domain = st.selectbox("Filter by Domain", ["All"] + all_domains)

    missing_only = False
    if is_admin():
        missing_only = st.checkbox("Show cards with missing info only")

    filtered_cards = cards

    if search:
        filtered_cards = [
            card for card in filtered_cards
            if search.lower() in card[0].lower()
            or search.lower() in card[1].lower()
        ]

    if selected_set != "All":
        filtered_cards = [
            card for card in filtered_cards
            if card[5] == selected_set
        ]

    if selected_rarity != "All":
        filtered_cards = [
            card for card in filtered_cards
            if card[2] == selected_rarity
        ]

    if selected_type != "All":
        filtered_cards = [
            card for card in filtered_cards
            if card[7] == selected_type
        ]

    if selected_domain != "All":
        filtered_cards = [
            card for card in filtered_cards
            if selected_domain in str(card[9]).split(",")
        ]

    if missing_only:
        filtered_cards = [
            card for card in filtered_cards
            if card[1] == card[0]
            or card[2] == "Unknown"
        ]

    filtered_cards = sorted(
        filtered_cards,
        key=lambda card: (
            card[5],
            len(str(card[9]).split(",")) == 1,
            card[10] if card[10] is not None else 999,
            card[1]
        )
    )

    columns_per_row = 4

    for i in range(0, len(filtered_cards), columns_per_row):
        cols = st.columns(columns_per_row)

        for col, card in zip(cols, filtered_cards[i:i + columns_per_row]):
            (
                code, name, rarity, img, set_name, set_prefix, quantity,
                card_type, supertype, domain, energy, might, power, tags
            ) = card

            with col:
                if img:
                    st.image(img, use_container_width=True)

                st.markdown(f"**{name}**")
                st.caption(f"{code}")
                st.caption(f"{rarity} · {card_type}")
                if domain:
                    st.caption(f"Domain: {domain}")
                if energy is not None:
                    st.caption(f"Energy: {energy}")
                st.write(f"Qty: **{quantity}**")

    st.divider()

    st.subheader("Reset My Collection")

    st.warning(
        "This clears only your collection and booster history. "
        "Master card data stays saved."
    )

    confirm_reset = st.checkbox("I understand this will reset only my collection")

    if st.button("Reset My Collection"):
        if confirm_reset:
            c.execute("DELETE FROM collection WHERE player_id = ?", (player_id,))
            c.execute("DELETE FROM imported_boosters WHERE player_id = ?", (player_id,))
            c.execute("DELETE FROM booster_cards WHERE player_id = ?", (player_id,))
            conn.commit()
            st.success("Your collection was reset.")
            st.rerun()
        else:
            st.error("Check the confirmation box first.")


# --------------------
# EXPORT CSV
# --------------------

with tabs[3]:
    st.header("Export for OpenRift")

    cards = get_collection_cards(player_id)

    export_data = []

    for card in cards:
        code, name, rarity, img, set_name, set_prefix, quantity = card[:7]

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
        file_name=f"{player_name.lower()}_openrift_import.csv",
        mime="text/csv"
    )


# --------------------
# PACK HISTORY
# --------------------

with tabs[4]:
    st.header("Imported Booster History")

    history = c.execute("""
    SELECT
        import_date,
        set_prefix,
        seed,
        total_cards,
        new_unique_count
    FROM imported_boosters
    WHERE player_id = ?
    ORDER BY import_date DESC
    """, (player_id,)).fetchall()

    if history:
        total_packs = len(history)

        for index, (import_date, set_prefix, seed, total_cards, new_unique_count) in enumerate(history):
            pack_number = total_packs - index

            formatted_date = pd.to_datetime(import_date).strftime("%Y-%m-%d %I:%M %p")

            label = (
                f"Pack {pack_number} - {set_prefix} - "
                f"{formatted_date} - {total_cards} Cards - {new_unique_count} New"
            )

            with st.expander(label, expanded=(index == 0)):
                pack_cards = c.execute("""
                SELECT
                    booster_cards.code,
                    booster_cards.quantity,
                    COALESCE(master_cards.name, booster_cards.code) as name,
                    COALESCE(master_cards.rarity, 'Unknown') as rarity,
                    COALESCE(master_cards.img, '') as img,
                    COALESCE(master_cards.card_type, '') as card_type,
                    COALESCE(master_cards.domain, '') as domain,
                    master_cards.energy
                FROM booster_cards
                LEFT JOIN master_cards
                ON booster_cards.code = master_cards.code
                WHERE booster_cards.player_id = ?
                AND booster_cards.seed = ?
                ORDER BY
CASE COALESCE(master_cards.rarity, '')
    WHEN 'Epic' THEN 1
    WHEN 'Rare' THEN 2
    WHEN 'Uncommon' THEN 3
    WHEN 'Common' THEN 4
    ELSE 5
END,
master_cards.energy ASC,
master_cards.name ASC
                """, (player_id, seed)).fetchall()

                columns_per_row = 4

                for i in range(0, len(pack_cards), columns_per_row):
                    cols = st.columns(columns_per_row)

                    for col, pack_card in zip(cols, pack_cards[i:i + columns_per_row]):
                        code, qty, name, rarity, img, card_type, domain, energy = pack_card

                        with col:
                            if img:
                                st.image(img, use_container_width=True)

                            st.markdown(f"**{name}**")
                            st.caption(f"{code}")
                            st.caption(f"{rarity} · {card_type}")
                            if domain:
                                st.caption(f"Domain: {domain}")
                            if energy is not None:
                                st.caption(f"Energy: {energy}")

                            if qty > 1:
                                st.write(f"Qty in pack: **{qty}**")
    else:
        st.info("No boosters imported yet.")


# --------------------
# ADMIN TOOLS
# --------------------

if is_admin():
    with tabs[5]:
        st.header("Admin Tools")

        st.subheader("League Dashboard Settings")

        current_week = int(get_setting("current_week", "1"))

        selected_week = st.selectbox(
            "Current Week",
            [1, 2, 3, 4, 5, 6],
            index=current_week - 1
        )

        announcement_text = st.text_area(
            "Announcement",
            value=get_setting("announcement", ""),
            height=120
        )

        if st.button("Save Dashboard Settings"):
            set_setting("current_week", selected_week)
            set_setting("announcement", announcement_text.strip())
            st.success("Dashboard settings saved.")

        st.divider()

        st.subheader("Sync Master Card Database")

        set_id = st.text_input("Set ID to sync", value="UNL")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Sync One Set"):
                try:
                    count = sync_master_database(set_id)
                    st.success(f"Synced {count} cards from set {set_id.upper()}!")
                except Exception as e:
                    st.error(f"Sync failed: {e}")

        with col2:
            if st.button("Sync All Sets"):
                try:
                    results = sync_all_sets()
                    st.success(
                        "Synced all sets: "
                        + ", ".join([f"{set_id}: {count}" for set_id, count in results.items()])
                    )
                except Exception as e:
                    st.error(f"Sync all failed: {e}")

        st.divider()

        st.subheader("Master Card Data Debug")

        debug_code = st.text_input("Card ID to inspect", value="UNL-019")

        if st.button("Inspect Master Card"):
            normalized = normalize_code(debug_code)

            c.execute("""
            SELECT *
            FROM master_cards
            WHERE code = ?
            """, (normalized,))

            result = c.fetchone()

            if result:
                c.execute("PRAGMA table_info(master_cards)")
                columns = [row[1] for row in c.fetchall()]
                st.json(dict(zip(columns, result)))
            else:
                st.warning("Card not found in master_cards.")

        st.divider()

        st.subheader("Manual Card Fixer")

        st.write("Use this for missing token cards or incorrect card data.")

        fix_code = st.text_input("Card ID", value="UNL-T07")
        fix_name = st.text_input("Card Name")
        fix_rarity = st.text_input("Rarity", value="Common")
        fix_set = st.text_input("Set Name", value="Unleashed")
        fix_prefix = st.text_input("Set Prefix", value="UNL")
        fix_type = st.text_input("Card Type", value="Unit")
        fix_supertype = st.text_input("Supertype", value="")
        fix_domain = st.text_input("Domain", value="")
        fix_energy = st.number_input("Energy", min_value=0, value=0)
        fix_might = st.number_input("Might", min_value=0, value=0)
        fix_power = st.number_input("Power", min_value=0, value=0)
        fix_tags = st.text_input("Tags", value="")
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
                set_prefix,
                card_type,
                supertype,
                domain,
                energy,
                might,
                power,
                tags
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                code,
                fix_name,
                fix_rarity,
                fix_image,
                fix_set,
                fix_prefix,
                fix_type,
                fix_supertype,
                fix_domain,
                fix_energy,
                fix_might,
                fix_power,
                fix_tags
            ))

            conn.commit()

            st.success(f"Saved master card info for {code}")