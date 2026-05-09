import streamlit as st
import pandas as pd
import html


def render_collection_page(
    player_id,
    player_name,
    is_admin,
    get_collection_cards,
    get_favorite_codes,
    toggle_favorite,
    render_preview_panel,
    render_card_image,
):
    cards = get_collection_cards(player_id)
    favorite_codes = get_favorite_codes(player_id)

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

    collection_csv = pd.DataFrame(export_data).to_csv(index=False).encode("utf-8")

    title_col, download_col = st.columns([3, 1])
    with title_col:
        st.header("My Collection")
    with download_col:
        st.download_button(
            label="Download Collection",
            data=collection_csv,
            file_name=f"{player_name.lower()}_openrift_import.csv",
            mime="text/csv"
        )

    render_preview_panel("collection")

    st.write(f"Unique cards: {len(cards)}")
    st.write(f"Total cards: {sum(card[6] for card in cards)}")

    with st.expander("Filters", expanded=False):
        search = st.text_input("Search collection", key="collection_search")

        all_sets = sorted(list(set(card[5] for card in cards)))
        selected_set = st.selectbox("Set", ["All"] + all_sets, key="collection_set_filter")

        all_rarities = sorted(list(set(card[2] for card in cards)))
        selected_rarity = st.selectbox("Rarity", ["All"] + all_rarities, key="collection_rarity_filter")

        all_types = sorted(list(set(card[7] for card in cards if card[7])))
        selected_type = st.selectbox("Type", ["All"] + all_types, key="collection_type_filter")

        all_domains = sorted(list(set(
            domain.strip()
            for card in cards
            for domain in str(card[9]).split(",")
            if domain.strip()
        )))
        selected_domain = st.selectbox("Domain", ["All"] + all_domains, key="collection_domain_filter")

        favorites_only = st.checkbox("Favorites only", key="collection_favorites_only")

        missing_only = False
        if is_admin:
            missing_only = st.checkbox("Show cards with missing info only", key="collection_missing_only")

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

    if favorites_only:
        filtered_cards = [card for card in filtered_cards if card[0] in favorite_codes]

    if missing_only:
        filtered_cards = [
            card for card in filtered_cards
            if card[1] == card[0]
            or card[2] == "Unknown"
        ]

    filtered_cards = sorted(
        filtered_cards,
        key=lambda card: (
            card[0] not in favorite_codes,
            card[5],
            len([d for d in str(card[9]).split(",") if d.strip()]) == 1,
            card[10] if card[10] is not None else 999,
            card[1]
        )
    )

    cards_per_page = 50
    total_pages = max(1, (len(filtered_cards) + cards_per_page - 1) // cards_per_page)

    if "collection_page" not in st.session_state:
        st.session_state["collection_page"] = 1

    if st.session_state["collection_page"] > total_pages:
        st.session_state["collection_page"] = total_pages

    page_col1, page_col2, page_col3 = st.columns([1, 2, 1])

    with page_col1:
        if st.button("Previous Page", disabled=(st.session_state["collection_page"] <= 1), key="collection_prev_page"):
            st.session_state["collection_page"] -= 1
            st.rerun()

    with page_col2:
        selected_page = st.selectbox(
            "Collection Page",
            list(range(1, total_pages + 1)),
            index=st.session_state["collection_page"] - 1,
            key="collection_page_select"
        )
        if selected_page != st.session_state["collection_page"]:
            st.session_state["collection_page"] = selected_page
            st.rerun()

    with page_col3:
        if st.button("Next Page", disabled=(st.session_state["collection_page"] >= total_pages), key="collection_next_page"):
            st.session_state["collection_page"] += 1
            st.rerun()

    start_index = (st.session_state["collection_page"] - 1) * cards_per_page
    end_index = start_index + cards_per_page
    paged_cards = filtered_cards[start_index:end_index]

    st.caption(f"Showing {len(paged_cards)} of {len(filtered_cards)} matching cards")

    columns_per_row = 4

    for i in range(0, len(paged_cards), columns_per_row):
        cols = st.columns(columns_per_row)

        for col, card in zip(cols, paged_cards[i:i + columns_per_row]):
            (
                code, name, rarity, img, set_name, set_prefix, quantity,
                card_type, supertype, domain, energy, might, power, tags
            ) = card

            is_favorite = code in favorite_codes

            with col:
                render_card_image(img, name, favorite=is_favorite)

                star_label = "★" if is_favorite else "☆"
                star_col, spacer_col = st.columns(2)
                with star_col:
                    if st.button(star_label, key=f"fav_collection_{code}_{i}", help="Toggle favorite"):
                        toggle_favorite(player_id, code)
                        st.rerun()
                with spacer_col:
                    st.write("")

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
                if not img:
                    display_name = name if name and name != code else code
                    st.markdown(
                        f"<div class='small-card-name'>{html.escape(display_name)}</div>",
                        unsafe_allow_html=True
                    )

                st.write(f"Qty: **{quantity}**")
