import streamlit as st
import sqlite3
import base64
import html
import pandas as pd
import requests
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from collections import Counter
from deckbuilder_page import render_deckbuilder_page
from collection_page import render_collection_page
from import_page import render_import_page
from pack_history_page import render_pack_history_page
from admin_page import render_admin_page
from ui_helpers import (
    inject_global_styles,
    set_preview,
    render_preview_panel,
    render_card_image,
    get_domain_label,
)
st.set_page_config(page_title="PackTrack", layout="wide")
from league_page import (
    render_league_page,
    ensure_league_tables,
    seed_round_robin_schedule,
    get_matches,
    calculate_standings,
)
from db import (
    PLAYERS,
    PACK_SCHEDULE,
    MAIN_DECK_LIMITS,
    get_connection,
    initialize_database,
    get_setting as db_get_setting,
    set_setting as db_set_setting,
    normalize_code,
    is_token_card,
    get_collection_cards as db_get_collection_cards,
    add_to_collection as db_add_to_collection,
    get_favorite_codes as db_get_favorite_codes,
    toggle_favorite as db_toggle_favorite,
    get_deck_cards as db_get_deck_cards,
    get_basic_runes as db_get_basic_runes,
    get_auto_section,
    add_to_deck as db_add_to_deck,
    remove_from_deck as db_remove_from_deck,
    clear_deck as db_clear_deck,
    get_used_count,
    get_section_used_count,
    build_decklist_text,
    section_count,
    section_label,
    sync_master_database as db_sync_master_database,
    sync_all_sets as db_sync_all_sets,
)

inject_global_styles()

st.title("PackTrack")
st.caption("Riftbound Sealed League Companion App")

conn, c = get_connection()
initialize_database(conn, c)

# --------------------
# HELPERS
# --------------------

def get_setting(key, default=""):
    return db_get_setting(c, key, default)


def set_setting(key, value):
    db_set_setting(conn, c, key, value)


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



def get_auto_section(card_type):
    if card_type == "Legend":
        return "Legend"
    if card_type == "Battlefield":
        return "Battlefields"
    if card_type == "Rune":
        return "Runes"
    return "MainDeck"


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


def get_domain_label(domain):
    domain = str(domain).strip()
    icons = {
        "Fury": "🔴 Fury",
        "Calm": "🟢 Calm",
        "Mind": "🔵 Mind",
        "Body": "🟠 Body",
        "Chaos": "🟣 Chaos",
        "Order": "🟡 Order",
        "Colorless": "⚫ Colorless",
    }
    return icons.get(domain, domain)

def get_collection_cards(player_id):
    return db_get_collection_cards(c, player_id)


def add_to_collection(player_id, code):
    db_add_to_collection(conn, c, player_id, code)


def get_favorite_codes(player_id):
    return db_get_favorite_codes(c, player_id)


def toggle_favorite(player_id, code):
    db_toggle_favorite(conn, c, player_id, code)


def get_deck_cards(player_id):
    return db_get_deck_cards(c, player_id)


def get_basic_runes():
    return db_get_basic_runes(c)


def add_to_deck(player_id, code, section):
    db_add_to_deck(conn, c, player_id, code, section)


def remove_from_deck(player_id, code, section):
    db_remove_from_deck(conn, c, player_id, code, section)


def clear_deck(player_id):
    db_clear_deck(conn, c, player_id)


def sync_master_database(set_id):
    return db_sync_master_database(conn, c, set_id)


def sync_all_sets():
    return db_sync_all_sets(conn, c)

def render_dashboard_league_summary():
    ensure_league_tables(conn, c)
    seed_round_robin_schedule(conn, c)

    current_week = int(get_setting("current_week", "1"))
    matches = get_matches(c)
    standings = calculate_standings(c)

    current_week_matches = [
        match for match in matches
        if match[1] == current_week
    ]

    completed_matches = [
        match for match in matches
        if match[6] is not None
    ]

    st.subheader("League Summary")
    st.write(f"**Current Week:** Week {current_week}")

    st.write("**This Week’s Matchups:**")
    for match in current_week_matches:
        player1_name = match[2]
        player2_name = match[3]
        winner_id = match[6]
        player1_id = match[4]
        player2_id = match[5]

        if winner_id == player1_id:
            st.write(f"✅ {player1_name} defeated {player2_name}")
        elif winner_id == player2_id:
            st.write(f"✅ {player2_name} defeated {player1_name}")
        else:
            st.write(f"• {player1_name} vs {player2_name}")

    if standings:
        leader = standings[0]
        st.write(
            f"**Current Leader:** {leader['name']} "
            f"({leader['wins']}-{leader['losses']})"
        )

    st.caption(f"Reported matches: {len(completed_matches)}/{len(matches)}")

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
favorite_codes = get_favorite_codes(player_id)

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
        "Deckbuilder",
        "League",
        "Pack History",
        "Admin Tools",
    ])
else:
    tabs = st.tabs([
        "Dashboard",
        "Import Packs",
        "My Collection",
        "Deckbuilder",
        "League",
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

st.divider()
render_dashboard_league_summary()

# --------------------
# IMPORT PACKS
# --------------------

with tabs[1]:
    render_import_page(
        player_id=player_id,
        add_to_collection=add_to_collection,
        normalize_code=normalize_code,
        conn=conn,
        c=c,
    )

# --------------------
# COLLECTION
# --------------------

with tabs[2]:
    render_collection_page(
        player_id=player_id,
        player_name=player_name,
        is_admin=is_admin(),
        get_collection_cards=get_collection_cards,
        get_favorite_codes=get_favorite_codes,
        toggle_favorite=toggle_favorite,
        render_preview_panel=render_preview_panel,
        render_card_image=render_card_image,
    )

# --------------------
# DECKBUILDER
# --------------------

with tabs[3]:
    render_deckbuilder_page(
        player_id=player_id,
        player_name=player_name,
        MAIN_DECK_LIMITS=MAIN_DECK_LIMITS,
        get_setting=get_setting,
        get_collection_cards=get_collection_cards,
        get_deck_cards=get_deck_cards,
        get_basic_runes=get_basic_runes,
        get_favorite_codes=get_favorite_codes,
        toggle_favorite=toggle_favorite,
        add_to_deck=add_to_deck,
        remove_from_deck=remove_from_deck,
        get_used_count=get_used_count,
        get_section_used_count=get_section_used_count,
        get_auto_section=get_auto_section,
        build_decklist_text=build_decklist_text,
        section_count=section_count,
        section_label=section_label,
        render_preview_panel=render_preview_panel,
        render_card_image=render_card_image,
        set_preview=set_preview,
        get_domain_label=get_domain_label,
        clear_deck=clear_deck,
    )

# --------------------
# LEAGUE
# --------------------

with tabs[4]:
    render_league_page(
        player_id=player_id,
        is_admin=is_admin(),
        get_setting=get_setting,
        conn=conn,
        c=c,
    )

# --------------------
# PACK HISTORY
# --------------------

with tabs[5]:
    render_pack_history_page(
        player_id=player_id,
        c=c,
        render_card_image=render_card_image,
    )

# --------------------
# ADMIN TOOLS
# --------------------

if is_admin():
    with tabs[6]:
        render_admin_page(
            get_setting=get_setting,
            set_setting=set_setting,
            sync_master_database=sync_master_database,
            sync_all_sets=sync_all_sets,
            normalize_code=normalize_code,
            conn=conn,
            c=c,
        )
