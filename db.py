import sqlite3
import requests

DB_NAME = "riftbound_library.db"

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

MAIN_DECK_LIMITS = {
    1: 25,
    2: 30,
    3: 35,
    4: 40,
    5: 40,
    6: 40,
}


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    return conn, c


def ensure_column(c, conn, table, column, column_type):
    c.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in c.fetchall()]
    if column not in columns:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        conn.commit()


def initialize_database(conn, c):
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

    c.execute("""
    CREATE TABLE IF NOT EXISTS deck_cards (
        player_id INTEGER,
        code TEXT,
        section TEXT,
        quantity INTEGER DEFAULT 0,
        PRIMARY KEY (player_id, code, section)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS favorite_cards (
        player_id INTEGER,
        code TEXT,
        PRIMARY KEY (player_id, code)
    )
    """)

    conn.commit()

    ensure_column(c, conn, "imported_boosters", "total_cards", "INTEGER DEFAULT 0")
    ensure_column(c, conn, "imported_boosters", "new_unique_count", "INTEGER DEFAULT 0")
    ensure_column(c, conn, "imported_boosters", "source_url", "TEXT")

    ensure_column(c, conn, "master_cards", "card_type", "TEXT")
    ensure_column(c, conn, "master_cards", "supertype", "TEXT")
    ensure_column(c, conn, "master_cards", "domain", "TEXT")
    ensure_column(c, conn, "master_cards", "energy", "INTEGER")
    ensure_column(c, conn, "master_cards", "might", "INTEGER")
    ensure_column(c, conn, "master_cards", "power", "INTEGER")
    ensure_column(c, conn, "master_cards", "tags", "TEXT")

    for player_id, player_name, passcode, is_admin_value in PLAYERS:
        c.execute("""
        INSERT OR REPLACE INTO players (
            player_id,
            player_name,
            passcode,
            is_admin
        )
        VALUES (?, ?, ?, ?)
        """, (player_id, player_name, passcode, is_admin_value))

    conn.commit()


def get_setting(c, key, default=""):
    c.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = ?",
        (key,)
    )
    result = c.fetchone()
    return result[0] if result else default


def set_setting(conn, c, key, value):
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


def is_token_card(code):
    return "-T" in str(code).upper()

# --------------------
# COLLECTION HELPERS
# --------------------

def get_collection_cards(c, player_id):
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
    AND collection.code NOT LIKE '%-T%'
    ORDER BY collection.code
    """, (player_id,)).fetchall()


def add_to_collection(conn, c, player_id, code):
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


# --------------------
# FAVORITE HELPERS
# --------------------

def get_favorite_codes(c, player_id):
    rows = c.execute(
        "SELECT code FROM favorite_cards WHERE player_id = ?",
        (player_id,)
    ).fetchall()
    return set(row[0] for row in rows)


def toggle_favorite(conn, c, player_id, code):
    code = normalize_code(code)

    c.execute(
        "SELECT code FROM favorite_cards WHERE player_id = ? AND code = ?",
        (player_id, code)
    )
    existing = c.fetchone()

    if existing:
        c.execute(
            "DELETE FROM favorite_cards WHERE player_id = ? AND code = ?",
            (player_id, code)
        )
    else:
        c.execute(
            "INSERT INTO favorite_cards (player_id, code) VALUES (?, ?)",
            (player_id, code)
        )

    conn.commit()


# --------------------
# DECK HELPERS
# --------------------

def get_deck_cards(c, player_id):
    return c.execute("""
    SELECT
        deck_cards.code,
        COALESCE(master_cards.name, deck_cards.code) as name,
        COALESCE(master_cards.rarity, 'Unknown') as rarity,
        COALESCE(master_cards.img, '') as img,
        COALESCE(master_cards.set_name, 'Unknown') as set_name,
        COALESCE(master_cards.set_prefix, SUBSTR(deck_cards.code, 1, INSTR(deck_cards.code, '-') - 1)) as set_prefix,
        deck_cards.quantity,
        deck_cards.section,
        COALESCE(master_cards.card_type, '') as card_type,
        COALESCE(master_cards.supertype, '') as supertype,
        COALESCE(master_cards.domain, '') as domain,
        master_cards.energy,
        master_cards.might,
        master_cards.power,
        COALESCE(master_cards.tags, '') as tags
    FROM deck_cards
    LEFT JOIN master_cards
    ON deck_cards.code = master_cards.code
    WHERE deck_cards.player_id = ?
    ORDER BY
        CASE deck_cards.section
            WHEN 'Legend' THEN 1
            WHEN 'Champion' THEN 2
            WHEN 'MainDeck' THEN 3
            WHEN 'Battlefields' THEN 4
            WHEN 'Runes' THEN 5
            WHEN 'Sideboard' THEN 6
            ELSE 7
        END,
        master_cards.energy ASC,
        master_cards.name ASC
    """, (player_id,)).fetchall()


def get_basic_runes(c):
    rune_names = [
        "Body Rune",
        "Chaos Rune",
        "Calm Rune",
        "Fury Rune",
        "Mind Rune",
        "Order Rune",
    ]

    placeholders = ",".join(["?"] * len(rune_names))

    return c.execute(f"""
    SELECT
        code,
        name,
        img,
        domain
    FROM master_cards
    WHERE card_type = 'Rune'
    AND name IN ({placeholders})
    ORDER BY name
    """, rune_names).fetchall()


def get_auto_section(card_type):
    if card_type == "Legend":
        return "Legend"
    if card_type == "Battlefield":
        return "Battlefields"
    if card_type == "Rune":
        return "Runes"
    return "MainDeck"


def add_to_deck(conn, c, player_id, code, section):
    code = normalize_code(code)

    if section == "Champion":
        c.execute(
            "DELETE FROM deck_cards WHERE player_id = ? AND section = 'Champion'",
            (player_id,)
        )

    c.execute("""
    SELECT quantity
    FROM deck_cards
    WHERE player_id = ? AND code = ? AND section = ?
    """, (player_id, code, section))

    existing = c.fetchone()

    if existing:
        c.execute("""
        UPDATE deck_cards
        SET quantity = ?
        WHERE player_id = ? AND code = ? AND section = ?
        """, (existing[0] + 1, player_id, code, section))
    else:
        c.execute("""
        INSERT INTO deck_cards (
            player_id,
            code,
            section,
            quantity
        )
        VALUES (?, ?, ?, ?)
        """, (player_id, code, section, 1))

    conn.commit()


def remove_from_deck(conn, c, player_id, code, section):
    code = normalize_code(code)

    c.execute("""
    SELECT quantity
    FROM deck_cards
    WHERE player_id = ? AND code = ? AND section = ?
    """, (player_id, code, section))

    existing = c.fetchone()

    if not existing:
        return

    if existing[0] <= 1:
        c.execute("""
        DELETE FROM deck_cards
        WHERE player_id = ? AND code = ? AND section = ?
        """, (player_id, code, section))
    else:
        c.execute("""
        UPDATE deck_cards
        SET quantity = ?
        WHERE player_id = ? AND code = ? AND section = ?
        """, (existing[0] - 1, player_id, code, section))

    conn.commit()


def clear_deck(conn, c, player_id):
    c.execute("DELETE FROM deck_cards WHERE player_id = ?", (player_id,))
    conn.commit()


def get_used_count(deck_cards, code):
    code = normalize_code(code)
    return sum(card[6] for card in deck_cards if card[0] == code)


def get_section_used_count(deck_cards, code, section):
    code = normalize_code(code)
    return sum(card[6] for card in deck_cards if card[0] == code and card[7] == section)


def build_decklist_text(deck_cards):
    section_order = [
        "Legend",
        "Champion",
        "MainDeck",
        "Battlefields",
        "Runes",
        "Sideboard",
    ]

    lines = []

    for section in section_order:
        section_cards = [card for card in deck_cards if card[7] == section]

        if not section_cards:
            continue

        lines.append(f"{section}:")
        for card in section_cards:
            code, name, rarity, img, set_name, set_prefix, quantity = card[:7]
            lines.append(f"{quantity} {name}")

        lines.append("")

    return "\n".join(lines).strip()


def section_count(deck_cards, section):
    return sum(card[6] for card in deck_cards if card[7] == section)


def section_label(label, current, limit):
    if current > limit:
        return f":red[{label}: {current}/{limit}]"
    return f"{label}: {current}/{limit}"


# --------------------
# MASTER CARD SYNC HELPERS
# --------------------

def sync_master_database(conn, c, set_id):
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


def sync_all_sets(conn, c):
    set_ids = ["UNL", "OGN", "SFD"]
    results = {}
    for set_id in set_ids:
        results[set_id] = sync_master_database(conn, c, set_id)
    return results

