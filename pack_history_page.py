import streamlit as st
import pandas as pd
import html


def render_pack_history_page(
    player_id,
    c,
    render_card_image,
):
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
                            render_card_image(img, name)
                            st.markdown(
                                f"<div class='small-card-name'>{html.escape(name)}</div>",
                                unsafe_allow_html=True
                            )
                            if not img:
                                display_name = name if name and name != code else code
                                st.markdown(
                                    f"<div class='small-card-name'>{html.escape(display_name)}</div>",
                                    unsafe_allow_html=True
                                )

                            if qty > 1:
                                st.write(f"Qty in pack: **{qty}**")
    else:
        st.info("No boosters imported yet.")
