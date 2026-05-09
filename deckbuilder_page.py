import streamlit as st
import html


def render_deckbuilder_page(
    player_id,
    player_name,
    MAIN_DECK_LIMITS,
    get_setting,
    get_collection_cards,
    get_deck_cards,
    get_basic_runes,
    get_favorite_codes,
    toggle_favorite,
    add_to_deck,
    remove_from_deck,
    get_used_count,
    get_section_used_count,
    get_auto_section,
    build_decklist_text,
    section_count,
    section_label,
    render_preview_panel,
    render_card_image,
    set_preview,
    get_domain_label,
    clear_deck,
):
    st.header("Deckbuilder")
    render_preview_panel("deckbuilder")

    favorite_codes = get_favorite_codes(player_id)

    current_week = int(get_setting("current_week", "1"))
    main_limit = MAIN_DECK_LIMITS.get(current_week, 40)

    owned_cards = get_collection_cards(player_id)
    deck_cards = get_deck_cards(player_id)
    basic_runes = get_basic_runes()

    # Runes are handled in their own special pool.
    owned_cards = [
        card for card in owned_cards
        if card[7] != "Rune"
    ]

    left, right = st.columns([2, 1])

    with left:
        with st.expander("Basic Runes", expanded=False):
            if basic_runes:
                rune_cols = st.columns(6)

                for rune_col, rune in zip(rune_cols, basic_runes):
                    rune_code, rune_name, rune_img, rune_domain = rune

                    with rune_col:
                        render_card_image(rune_img, rune_name)
                        st.markdown(
                            f"<div class='small-card-name'>{html.escape(rune_name)}</div>",
                            unsafe_allow_html=True
                        )

                        rune_button_col1, rune_button_col2, rune_button_col3 = st.columns(3)

                        with rune_button_col1:
                            if st.button("+", key=f"rune_add_{rune_code}", help="Add rune"):
                                add_to_deck(player_id, rune_code, "Runes")
                                st.rerun()

                        with rune_button_col2:
                            if st.button("-", key=f"rune_remove_{rune_code}", help="Remove rune"):
                                remove_from_deck(player_id, rune_code, "Runes")
                                st.rerun()

                        with rune_button_col3:
                            if rune_img and st.button("🔍", key=f"preview_rune_{rune_code}", help="Preview rune"):
                                set_preview(rune_img, rune_name)
                                st.rerun()
            else:
                st.info("No basic runes found. Sync master card database first.")

        st.divider()

        st.subheader("Owned Cards")

        all_deck_types = sorted(list(set(card[7] for card in owned_cards if card[7])))
        all_deck_domains = sorted(list(set(
            domain.strip()
            for card in owned_cards
            for domain in str(card[9]).split(",")
            if domain.strip()
        )))

        if "selected_deck_domains" not in st.session_state:
            st.session_state["selected_deck_domains"] = []

        with st.expander("Deckbuilder Filters", expanded=False):
            deck_search = st.text_input("Search deckbuilder cards", key="deckbuilder_search")
            deck_type_filter = st.selectbox("Type", ["All"] + all_deck_types, key="deckbuilder_type_filter")
            deck_favorites_only = st.checkbox("Favorites only", key="deckbuilder_favorites_only")

            st.caption("Domain filters")
            ordered_domains = [
                d for d in ["Fury", "Calm", "Mind", "Body", "Chaos", "Order", "Colorless"]
                if d in all_deck_domains
            ]
            domain_cols = st.columns(max(1, len(ordered_domains)))
            for domain_col, domain in zip(domain_cols, ordered_domains):
                selected = domain in st.session_state["selected_deck_domains"]
                label = f"✓ {get_domain_label(domain)}" if selected else get_domain_label(domain)
                with domain_col:
                    if st.button(label, key=f"domain_filter_{domain}"):
                        if selected:
                            st.session_state["selected_deck_domains"].remove(domain)
                        else:
                            st.session_state["selected_deck_domains"].append(domain)
                        st.rerun()

        selected_deck_domains = st.session_state.get("selected_deck_domains", [])

        filtered_owned = owned_cards

        if deck_search:
            filtered_owned = [
                card for card in filtered_owned
                if deck_search.lower() in card[0].lower()
                or deck_search.lower() in card[1].lower()
            ]

        if deck_type_filter != "All":
            filtered_owned = [
                card for card in filtered_owned
                if card[7] == deck_type_filter
            ]

        if selected_deck_domains:
            filtered_owned = [
                card for card in filtered_owned
                if any(domain in str(card[9]).split(",") for domain in selected_deck_domains)
            ]

        if deck_favorites_only:
            filtered_owned = [card for card in filtered_owned if card[0] in favorite_codes]

        filtered_owned = sorted(
            filtered_owned,
            key=lambda card: (
                card[0] not in favorite_codes,
                len([d for d in str(card[9]).split(",") if d.strip()]) == 1,
                card[10] if card[10] is not None else 999,
                card[1]
            )
        )

        columns_per_row = 5

        for i in range(0, len(filtered_owned), columns_per_row):
            cols = st.columns(columns_per_row)

            for col, card in zip(cols, filtered_owned[i:i + columns_per_row]):
                (
                    code, name, rarity, img, set_name, set_prefix, owned_qty,
                    card_type, supertype, domain, energy, might, power, tags
                ) = card

                used_qty = get_used_count(deck_cards, code)
                side_used_qty = get_section_used_count(deck_cards, code, "Sideboard")
                auto_section = get_auto_section(card_type)
                fully_used = used_qty >= owned_qty
                is_favorite = code in favorite_codes

                with col:
                    render_card_image(img, name, fully_used=fully_used, favorite=is_favorite)

                    if not img:
                        st.markdown(
                        f"<div class='small-card-name'>{html.escape(name)}</div>",
                        unsafe_allow_html=True
                        )

                    if fully_used:
                        st.caption(f"✅ {used_qty}/{owned_qty}")
                    else:
                        st.caption(f"{used_qty}/{owned_qty}")

                    top_col1, top_col2 = st.columns(2)
                    with top_col1:
                        star_label = "★" if is_favorite else "☆"
                        if st.button(star_label, key=f"fav_deck_{code}_{i}", help="Toggle favorite"):
                            toggle_favorite(player_id, code)
                            st.rerun()
                    with top_col2:
                        if img and st.button("🔍", key=f"preview_deck_{code}_{i}", help="Preview card"):
                            set_preview(img, name)
                            st.rerun()

                    action_cols = st.columns([1, 1, 1, 1.3, 1.3])

                    with action_cols[0]:
                        if st.button(
                            "+",
                            key=f"deck_add_{code}_{i}",
                            help="Add to deck",
                            disabled=fully_used
                        ):
                            add_to_deck(player_id, code, auto_section)
                            st.rerun()

                    with action_cols[1]:
                        if st.button(
                            "-",
                            key=f"deck_remove_{code}_{i}",
                            help="Remove from deck"
                        ):
                            remove_from_deck(player_id, code, auto_section)
                            st.rerun()

                    with action_cols[2]:
                        if card_type == "Unit" and supertype == "Champion":
                            if st.button(
                                "⭐",
                                key=f"champion_{code}_{i}",
                                help="Set as chosen champion",
                                disabled=fully_used
                            ):
                                add_to_deck(player_id, code, "Champion")
                                st.rerun()

                    if card_type not in ["Rune", "Legend", "Battlefield"]:
                        with action_cols[3]:
                            if st.button(
                                "S+",
                                key=f"side_add_{code}_{i}",
                                help="Add to sideboard",
                                disabled=fully_used
                            ):
                                add_to_deck(player_id, code, "Sideboard")
                                st.rerun()

                        with action_cols[4]:
                            if st.button(
                                "S-",
                                key=f"side_remove_{code}_{i}",
                                help="Remove from sideboard",
                                disabled=(side_used_qty <= 0)
                            ):
                                remove_from_deck(player_id, code, "Sideboard")
                                st.rerun()

    with right:
        st.subheader("My Deck")

        legend_count = section_count(deck_cards, "Legend")
        champion_count = section_count(deck_cards, "Champion")
        main_count = section_count(deck_cards, "MainDeck")
        battlefield_count = section_count(deck_cards, "Battlefields")
        rune_count = section_count(deck_cards, "Runes")
        side_count = section_count(deck_cards, "Sideboard")

        st.markdown(section_label("Legend", legend_count, 1))
        st.markdown(section_label("Chosen Champion", champion_count, 1))
        st.markdown(section_label("MainDeck", main_count, main_limit))
        st.markdown(section_label("Battlefields", battlefield_count, 3))
        st.markdown(section_label("Runes", rune_count, 12))
        st.markdown(section_label("Sideboard", side_count, 8))

        st.divider()

        for section in ["Legend", "Champion", "MainDeck", "Battlefields", "Runes", "Sideboard"]:
            section_cards = [card for card in deck_cards if card[7] == section]

            with st.expander(section, expanded=(section != "Sideboard")):
                if not section_cards:
                    st.caption("No cards yet.")
                else:
                    for card in section_cards:
                        code, name, rarity, img, set_name, set_prefix, quantity, section_name = card[:8]

                        row1, row2, row3 = st.columns([3, 1, 1])

                        with row1:
                            st.write(f"{quantity} {name}")

                        with row2:
                            if img and st.button("🔍", key=f"right_preview_{section}_{code}"):
                                set_preview(img, name)
                                st.rerun()

                        with row3:
                            if st.button("−", key=f"right_remove_{section}_{code}"):
                                remove_from_deck(player_id, code, section)
                                st.rerun()

        st.divider()

        decklist_text = build_decklist_text(deck_cards)

        st.subheader("Decklist Export")
        st.text_area(
            "Decklist for TCG Arena — click inside, Ctrl+A, Ctrl+C",
            value=decklist_text,
            height=300
        )

        st.download_button(
            label="Download Decklist .txt",
            data=decklist_text.encode("utf-8"),
            file_name=f"{player_name.lower()}_decklist.txt",
            mime="text/plain"
        )

        st.divider()

        st.subheader("Clear Deck")

        confirm_clear = st.checkbox("I understand this will clear my saved deck")

        if st.button("Clear My Deck"):
            if confirm_clear:
                clear_deck(player_id)
                st.success("Deck cleared.")
                st.rerun()
            else:
                st.error("Check the confirmation box first.")
