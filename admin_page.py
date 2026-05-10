import streamlit as st
import os
import shutil
from datetime import datetime


def render_admin_page(
    get_setting,
    set_setting,
    sync_master_database,
    sync_all_sets,
    normalize_code,
    conn,
    c,
):
    st.header("Admin Tools")

    st.subheader("Database Backup / Restore")

    db_path = "riftbound_library.db"

    if os.path.exists(db_path):
        with open(db_path, "rb") as db_file:
            st.download_button(
                label="Download Database Backup",
                data=db_file,
                file_name=f"packtrack_backup_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.db",
                mime="application/octet-stream",
                key="admin_download_db_backup",
            )
    else:
        st.warning("Database file not found.")

    uploaded_backup = st.file_uploader(
        "Upload Database Backup",
        type=["db"],
        key="admin_upload_db_backup",
    )

    confirm_restore = st.checkbox(
        "I understand this will replace the current live database",
        key="admin_confirm_restore_db",
    )

    if st.button("Restore Database Backup", key="admin_restore_db_backup"):
        if not uploaded_backup:
            st.error("Upload a .db backup file first.")
        elif not confirm_restore:
            st.error("Check the confirmation box first.")
        else:
            safety_copy = f"riftbound_library_before_restore_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.db"

            if os.path.exists(db_path):
                shutil.copy(db_path, safety_copy)

            with open(db_path, "wb") as f:
                f.write(uploaded_backup.getbuffer())

            st.success("Database restored. Restart or refresh the app if needed.")
            st.rerun()

    st.divider()

    st.subheader("Admin Reset Player Data")

    players = c.execute("""
        SELECT player_id, player_name
        FROM players
        ORDER BY player_id
    """).fetchall()

    player_options = {
        f"{player_name} (ID {player_id})": player_id
        for player_id, player_name in players
    }

    selected_player_label = st.selectbox(
        "Select player to reset",
        list(player_options.keys()),
        key="admin_reset_player_select"
    )

    selected_player_id = player_options[selected_player_label]

    reset_collection = st.checkbox(
        "Reset collection",
        key="admin_reset_collection"
    )

    reset_imports = st.checkbox(
        "Reset imported pack history",
        key="admin_reset_imports"
    )

    reset_deck = st.checkbox(
        "Reset saved deck",
        key="admin_reset_deck"
    )

    confirm_player_reset = st.checkbox(
        "I understand this will permanently delete the selected player data",
        key="admin_confirm_player_reset"
    )

    if st.button("Reset Selected Player Data", key="admin_reset_player_data"):
        if not confirm_player_reset:
            st.error("Check the confirmation box first.")
        elif not reset_collection and not reset_imports and not reset_deck:
            st.error("Choose at least one reset option.")
        else:
            if reset_collection:
                c.execute(
                    "DELETE FROM collection WHERE player_id = ?",
                    (selected_player_id,)
                )

            if reset_imports:
                c.execute(
                    "DELETE FROM imported_boosters WHERE player_id = ?",
                    (selected_player_id,)
                )
                c.execute(
                    "DELETE FROM booster_cards WHERE player_id = ?",
                    (selected_player_id,)
                )

            if reset_deck:
                c.execute(
                    "DELETE FROM deck_cards WHERE player_id = ?",
                    (selected_player_id,)
                )

            conn.commit()
            st.success(f"Reset selected data for {selected_player_label}.")
            st.rerun()

    st.divider()


    st.subheader("League Dashboard Settings")

    current_week = int(get_setting("current_week", "1"))

    selected_week = st.selectbox(
        "Current Week",
        [1, 2, 3, 4, 5, 6],
        index=current_week - 1,
        key="admin_current_week",
    )

    announcement_text = st.text_area(
        "Announcement",
        value=get_setting("announcement", ""),
        height=120,
        key="admin_announcement",
    )

    if st.button("Save Dashboard Settings", key="admin_save_dashboard_settings"):
        set_setting("current_week", selected_week)
        set_setting("announcement", announcement_text.strip())
        st.success("Dashboard settings saved.")

    st.divider()

    st.subheader("Sync Master Card Database")

    set_id = st.text_input("Set ID to sync", value="UNL", key="admin_set_id")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Sync One Set", key="admin_sync_one_set"):
            try:
                count = sync_master_database(set_id)
                st.success(f"Synced {count} cards from set {set_id.upper()}!")
            except Exception as e:
                st.error(f"Sync failed: {e}")

    with col2:
        if st.button("Sync All Sets", key="admin_sync_all_sets"):
            try:
                results = sync_all_sets()
                st.success(
                    "Synced all sets: "
                    + ", ".join(
                        [f"{set_id}: {count}" for set_id, count in results.items()]
                    )
                )
            except Exception as e:
                st.error(f"Sync all failed: {e}")

    st.divider()

    st.subheader("Master Card Data Debug")

    debug_code = st.text_input(
        "Card ID to inspect",
        value="UNL-019",
        key="admin_debug_code",
    )

    if st.button("Inspect Master Card", key="admin_inspect_master_card"):
        normalized = normalize_code(debug_code)

        c.execute(
            """
            SELECT *
            FROM master_cards
            WHERE code = ?
            """,
            (normalized,),
        )

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

    fix_code = st.text_input("Card ID", value="UNL-003", key="admin_fix_code")
    fix_name = st.text_input(
        "Card Name",
        value="Mischievous Marai",
        key="admin_fix_name",
    )
    fix_rarity = st.text_input("Rarity", value="Common", key="admin_fix_rarity")
    fix_set = st.text_input("Set Name", value="Unleashed", key="admin_fix_set")
    fix_prefix = st.text_input("Set Prefix", value="UNL", key="admin_fix_prefix")
    fix_type = st.text_input("Card Type", value="Unit", key="admin_fix_type")
    fix_supertype = st.text_input("Supertype", value="", key="admin_fix_supertype")
    fix_domain = st.text_input("Domain", value="Body", key="admin_fix_domain")
    fix_energy = st.number_input("Energy", min_value=0, value=1, key="admin_fix_energy")
    fix_might = st.number_input("Might", min_value=0, value=1, key="admin_fix_might")
    fix_power = st.number_input("Power", min_value=0, value=0, key="admin_fix_power")
    fix_tags = st.text_input("Tags", value="", key="admin_fix_tags")
    fix_image = st.text_input(
        "Image URL",
        value="https://cmsassets.rgpub.io/sanity/images/dsfx7636/game_data_live/",
        key="admin_fix_image",
    )

    if st.button("Save Manual Card Fix", key="admin_save_manual_fix"):
        code = normalize_code(fix_code)

        c.execute(
            """
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
            """,
            (
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
                fix_tags,
            ),
        )

        conn.commit()

        st.success(f"Saved master card info for {code}")