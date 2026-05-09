import streamlit as st
import base64
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from collections import Counter


def render_import_page(
    player_id,
    add_to_collection,
    normalize_code,
    conn,
    c,
):
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

    if st.button("Import Booster URLs", key="import_booster_urls_button"):
        urls = [
            url.strip()
            for url in booster_urls.splitlines()
            if url.strip()
        ]

        if not urls:
            st.error("Paste at least one booster URL.")
            return

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
