import streamlit as st


ROUND_ROBIN_SCHEDULE = {
    1: [("Russ", "Kayla"), ("Nick", "Henry"), ("Steve", "Tyler")],
    2: [("Russ", "Nick"), ("Steve", "Kayla"), ("Tyler", "Henry")],
    3: [("Russ", "Steve"), ("Tyler", "Nick"), ("Henry", "Kayla")],
    4: [("Russ", "Tyler"), ("Henry", "Steve"), ("Kayla", "Nick")],
    5: [("Russ", "Henry"), ("Kayla", "Tyler"), ("Nick", "Steve")],
}


POSTSEASON_STRUCTURE = [
    "Seeds #1 and #2 receive first-round byes.",
    "Quarterfinal: #3 vs #6",
    "Quarterfinal: #4 vs #5",
    "Semifinal: #1 vs winner of #4/#5",
    "Semifinal: #2 vs winner of #3/#6",
    "Final: semifinal winners",
]


def get_player_name_map(c):
    players = c.execute("""
        SELECT player_id, player_name
        FROM players
        ORDER BY player_id
    """).fetchall()
    return {name: player_id for player_id, name in players}


def ensure_league_tables(conn, c):
    c.execute("""
    CREATE TABLE IF NOT EXISTS league_matches (
        match_id INTEGER PRIMARY KEY AUTOINCREMENT,
        week INTEGER,
        player1_id INTEGER,
        player2_id INTEGER,
        winner_id INTEGER,
        player1_score INTEGER DEFAULT 0,
        player2_score INTEGER DEFAULT 0,
        notes TEXT DEFAULT '',
        UNIQUE(week, player1_id, player2_id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS league_result_reports (
        report_id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER,
        submitted_by INTEGER,
        winner_id INTEGER,
        player1_score INTEGER DEFAULT 0,
        player2_score INTEGER DEFAULT 0,
        notes TEXT DEFAULT '',
        status TEXT DEFAULT 'pending',
        submitted_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()


def seed_round_robin_schedule(conn, c):
    name_to_id = get_player_name_map(c)

    for week, matchups in ROUND_ROBIN_SCHEDULE.items():
        for player1_name, player2_name in matchups:
            player1_id = name_to_id.get(player1_name)
            player2_id = name_to_id.get(player2_name)

            if player1_id and player2_id:
                c.execute("""
                INSERT OR IGNORE INTO league_matches (
                    week,
                    player1_id,
                    player2_id
                )
                VALUES (?, ?, ?)
                """, (week, player1_id, player2_id))

    conn.commit()


def get_matches(c):
    return c.execute("""
    SELECT
        league_matches.match_id,
        league_matches.week,
        p1.player_name as player1_name,
        p2.player_name as player2_name,
        league_matches.player1_id,
        league_matches.player2_id,
        league_matches.winner_id,
        league_matches.player1_score,
        league_matches.player2_score,
        league_matches.notes
    FROM league_matches
    JOIN players p1 ON league_matches.player1_id = p1.player_id
    JOIN players p2 ON league_matches.player2_id = p2.player_id
    ORDER BY league_matches.week, league_matches.match_id
    """).fetchall()


def get_head_to_head_winner(c, player_a_id, player_b_id):
    result = c.execute("""
        SELECT winner_id
        FROM league_matches
        WHERE winner_id IS NOT NULL
        AND (
            (player1_id = ? AND player2_id = ?)
            OR
            (player1_id = ? AND player2_id = ?)
        )
    """, (player_a_id, player_b_id, player_b_id, player_a_id)).fetchone()

    if result:
        return result[0]
    return None


def calculate_standings(c):
    players = c.execute("""
        SELECT player_id, player_name
        FROM players
        ORDER BY player_id
    """).fetchall()

    standings = {
        player_id: {
            "player_id": player_id,
            "name": player_name,
            "wins": 0,
            "losses": 0,
            "played": 0,
            "points": 0,
        }
        for player_id, player_name in players
    }

    completed_matches = c.execute("""
        SELECT player1_id, player2_id, winner_id
        FROM league_matches
        WHERE winner_id IS NOT NULL
    """).fetchall()

    for player1_id, player2_id, winner_id in completed_matches:
        if player1_id in standings:
            standings[player1_id]["played"] += 1
        if player2_id in standings:
            standings[player2_id]["played"] += 1

        if winner_id == player1_id:
            standings[player1_id]["wins"] += 1
            standings[player1_id]["points"] += 3
            standings[player2_id]["losses"] += 1
        elif winner_id == player2_id:
            standings[player2_id]["wins"] += 1
            standings[player2_id]["points"] += 3
            standings[player1_id]["losses"] += 1

    rows = list(standings.values())
    rows = sorted(rows, key=lambda row: (-row["wins"], row["losses"], row["name"]))

    # Simple behind-the-scenes head-to-head tiebreaker for 2-player ties.
    # Multi-player ties remain sorted by losses/name for now.
    i = 0
    final_rows = []
    while i < len(rows):
        tied_group = [rows[i]]
        j = i + 1

        while j < len(rows) and rows[j]["wins"] == rows[i]["wins"] and rows[j]["losses"] == rows[i]["losses"]:
            tied_group.append(rows[j])
            j += 1

        if len(tied_group) == 2:
            player_a = tied_group[0]
            player_b = tied_group[1]
            h2h_winner = get_head_to_head_winner(c, player_a["player_id"], player_b["player_id"])

            if h2h_winner == player_b["player_id"]:
                tied_group = [player_b, player_a]

        final_rows.extend(tied_group)
        i = j

    return final_rows


def get_match_status(match):
    winner_id = match[6]
    return "Completed" if winner_id else "Unreported"


def render_match_card(match, current_week):
    (
        match_id,
        week_number,
        player1_name,
        player2_name,
        player1_id,
        player2_id,
        winner_id,
        player1_score,
        player2_score,
        notes,
    ) = match

    status = get_match_status(match)
    is_current_week = week_number == current_week

    if winner_id == player1_id:
        result_line = f"Winner: **{player1_name}**"
    elif winner_id == player2_id:
        result_line = f"Winner: **{player2_name}**"
    else:
        result_line = "Result: _Not reported_"

    score_line = ""
    if winner_id:
        score_line = f"Score: {player1_name} {player1_score} - {player2_score} {player2_name}"

    if status == "Completed":
        st.success(f"✅ Week {week_number}: {player1_name} vs {player2_name}")
    elif is_current_week:
        st.info(f"🔥 Week {week_number}: {player1_name} vs {player2_name}")
    else:
        st.write(f"**Week {week_number}: {player1_name} vs {player2_name}**")

    st.caption(result_line)
    if score_line:
        st.caption(score_line)
    if notes:
        st.caption(f"Notes: {notes}")


def render_schedule(matches, current_week):
    st.subheader("League Schedule")
    st.caption("Current week is expanded automatically.")

    for week in range(1, 6):
        week_matches = [match for match in matches if match[1] == week]
        completed_count = sum(1 for match in week_matches if match[6])
        expanded = week == current_week

        label = f"Week {week} — {completed_count}/{len(week_matches)} reported"
        if week == current_week:
            label = f"🔥 {label}"

        with st.expander(label, expanded=expanded):
            for match in week_matches:
                render_match_card(match, current_week)
                st.divider()


def render_standings(c):
    st.subheader("Standings")

    standings = calculate_standings(c)

    if not standings:
        st.info("No standings yet.")
        return

    header_cols = st.columns([0.7, 2, 1, 1, 1, 1])
    header_cols[0].markdown("**Seed**")
    header_cols[1].markdown("**Player**")
    header_cols[2].markdown("**W**")
    header_cols[3].markdown("**L**")
    header_cols[4].markdown("**Played**")
    header_cols[5].markdown("**Pts**")

    for index, row in enumerate(standings, start=1):
        row_cols = st.columns([0.7, 2, 1, 1, 1, 1])
        row_cols[0].write(f"#{index}")
        row_cols[1].write(row["name"])
        row_cols[2].write(row["wins"])
        row_cols[3].write(row["losses"])
        row_cols[4].write(row["played"])
        row_cols[5].write(row["points"])

    st.caption("Tiebreakers are currently manual. Default sort is wins, then fewer losses, then name.")


def render_postseason_preview(c):
    st.subheader("Postseason Bracket Preview")

    standings = calculate_standings(c)

    if len(standings) < 6:
        st.info("Bracket preview will appear once all players are available.")
        return

    seeded = standings[:6]

    st.write("**Current Seeding**")
    for index, row in enumerate(seeded, start=1):
        bye_text = " — first-round bye" if index in [1, 2] else ""
        st.write(f"#{index}: {row['name']} ({row['wins']}-{row['losses']}){bye_text}")

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Quarterfinals**")
        st.write(f"#3 {seeded[2]['name']} vs #6 {seeded[5]['name']}")
        st.write(f"#4 {seeded[3]['name']} vs #5 {seeded[4]['name']}")

    with col2:
        st.write("**Semifinals**")
        st.write(f"#1 {seeded[0]['name']} vs winner of #4/#5")
        st.write(f"#2 {seeded[1]['name']} vs winner of #3/#6")

    st.write("**Finals**")
    st.write("Semifinal winners")


def render_player_result_submission(player_id, conn, c):
    st.subheader("Submit Match Result")

    matches = get_matches(c)
    player_matches = [
        match for match in matches
        if match[4] == player_id or match[5] == player_id
    ]

    if not player_matches:
        st.info("You do not have any scheduled matches.")
        return

    match_options = {}
    for match in player_matches:
        match_id = match[0]
        week = match[1]
        player1_name = match[2]
        player2_name = match[3]
        official_winner = match[6]

        if official_winner:
            status = "official result entered"
        else:
            pending = c.execute("""
                SELECT report_id
                FROM league_result_reports
                WHERE match_id = ?
                AND submitted_by = ?
                AND status = 'pending'
            """, (match_id, player_id)).fetchone()
            status = "pending report submitted" if pending else "unreported"

        label = f"Week {week}: {player1_name} vs {player2_name} ({status})"
        match_options[label] = match

    selected_label = st.selectbox(
        "Select your match",
        list(match_options.keys()),
        key="player_report_match_select"
    )

    selected_match = match_options[selected_label]
    (
        match_id,
        week,
        player1_name,
        player2_name,
        player1_id,
        player2_id,
        official_winner_id,
        player1_score,
        player2_score,
        notes,
    ) = selected_match

    if official_winner_id:
        st.info("This match already has an official result. Ask the admin if it needs to be changed.")
        return

    winner_options = {
        player1_name: player1_id,
        player2_name: player2_id,
    }

    selected_winner_label = st.selectbox(
        "Winner",
        list(winner_options.keys()),
        key="player_report_winner_select"
    )

    col1, col2 = st.columns(2)
    with col1:
        submitted_player1_score = st.number_input(
            f"{player1_name} score",
            min_value=0,
            value=0,
            key="player_report_player1_score"
        )
    with col2:
        submitted_player2_score = st.number_input(
            f"{player2_name} score",
            min_value=0,
            value=0,
            key="player_report_player2_score"
        )

    submitted_notes = st.text_area(
        "Notes / confirmation details",
        key="player_report_notes"
    )

    if st.button("Submit Result for Admin Review", key="player_submit_result_report"):
        c.execute("""
        INSERT INTO league_result_reports (
            match_id,
            submitted_by,
            winner_id,
            player1_score,
            player2_score,
            notes,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """, (
            match_id,
            player_id,
            winner_options[selected_winner_label],
            submitted_player1_score,
            submitted_player2_score,
            submitted_notes.strip(),
        ))
        conn.commit()
        st.success("Result submitted for admin review.")
        st.rerun()


def render_admin_result_approvals(conn, c):
    st.subheader("Admin Result Approvals")

    reports = c.execute("""
    SELECT
        league_result_reports.report_id,
        league_result_reports.match_id,
        league_result_reports.submitted_by,
        submitter.player_name as submitter_name,
        league_result_reports.winner_id,
        winner.player_name as winner_name,
        league_result_reports.player1_score,
        league_result_reports.player2_score,
        league_result_reports.notes,
        league_result_reports.submitted_at,
        league_matches.week,
        p1.player_name as player1_name,
        p2.player_name as player2_name
    FROM league_result_reports
    JOIN players submitter ON league_result_reports.submitted_by = submitter.player_id
    JOIN players winner ON league_result_reports.winner_id = winner.player_id
    JOIN league_matches ON league_result_reports.match_id = league_matches.match_id
    JOIN players p1 ON league_matches.player1_id = p1.player_id
    JOIN players p2 ON league_matches.player2_id = p2.player_id
    WHERE league_result_reports.status = 'pending'
    ORDER BY league_result_reports.submitted_at ASC
    """).fetchall()

    if not reports:
        st.info("No pending result reports.")
        return

    for report in reports:
        (
            report_id,
            match_id,
            submitted_by,
            submitter_name,
            winner_id,
            winner_name,
            player1_score,
            player2_score,
            notes,
            submitted_at,
            week,
            player1_name,
            player2_name,
        ) = report

        with st.expander(f"Week {week}: {player1_name} vs {player2_name} — submitted by {submitter_name}", expanded=True):
            st.write(f"**Submitted winner:** {winner_name}")
            st.write(f"**Score:** {player1_name} {player1_score} - {player2_score} {player2_name}")
            if notes:
                st.write(f"**Notes:** {notes}")
            st.caption(f"Submitted at: {submitted_at}")

            approve_col, reject_col = st.columns(2)

            with approve_col:
                if st.button("Approve Result", key=f"approve_report_{report_id}"):
                    c.execute("""
                    UPDATE league_matches
                    SET winner_id = ?,
                        player1_score = ?,
                        player2_score = ?,
                        notes = ?
                    WHERE match_id = ?
                    """, (
                        winner_id,
                        player1_score,
                        player2_score,
                        notes,
                        match_id,
                    ))

                    c.execute("""
                    UPDATE league_result_reports
                    SET status = 'approved'
                    WHERE report_id = ?
                    """, (report_id,))

                    conn.commit()
                    st.success("Result approved and standings updated.")
                    st.rerun()

            with reject_col:
                if st.button("Reject Report", key=f"reject_report_{report_id}"):
                    c.execute("""
                    UPDATE league_result_reports
                    SET status = 'rejected'
                    WHERE report_id = ?
                    """, (report_id,))
                    conn.commit()
                    st.success("Report rejected.")
                    st.rerun()


def render_admin_match_reporting(conn, c):
    st.subheader("Admin Match Reporting")

    matches = get_matches(c)

    show_only_unreported = st.checkbox(
        "Show only unreported matches",
        value=False,
        key="league_show_unreported_only"
    )

    if show_only_unreported:
        matches = [match for match in matches if not match[6]]

    match_options = {}
    for match in matches:
        match_id = match[0]
        week = match[1]
        player1_name = match[2]
        player2_name = match[3]
        winner_id = match[6]
        status = "reported" if winner_id else "unreported"
        label = f"Week {week}: {player1_name} vs {player2_name} ({status})"
        match_options[label] = match

    if not match_options:
        st.info("No matches available.")
        return

    selected_label = st.selectbox(
        "Select match",
        list(match_options.keys()),
        key="league_match_select"
    )

    selected_match = match_options[selected_label]
    (
        match_id,
        week,
        player1_name,
        player2_name,
        player1_id,
        player2_id,
        winner_id,
        player1_score,
        player2_score,
        notes,
    ) = selected_match

    st.write(f"**Selected:** Week {week} — {player1_name} vs {player2_name}")

    winner_options = {
        "Not reported": None,
        player1_name: player1_id,
        player2_name: player2_id,
    }

    current_winner_label = "Not reported"
    if winner_id == player1_id:
        current_winner_label = player1_name
    elif winner_id == player2_id:
        current_winner_label = player2_name

    selected_winner_label = st.selectbox(
        "Winner",
        list(winner_options.keys()),
        index=list(winner_options.keys()).index(current_winner_label),
        key="league_winner_select"
    )

    col1, col2 = st.columns(2)
    with col1:
        new_player1_score = st.number_input(
            f"{player1_name} score",
            min_value=0,
            value=int(player1_score or 0),
            key="league_player1_score"
        )
    with col2:
        new_player2_score = st.number_input(
            f"{player2_name} score",
            min_value=0,
            value=int(player2_score or 0),
            key="league_player2_score"
        )

    new_notes = st.text_area(
        "Notes",
        value=notes or "",
        key="league_match_notes"
    )

    save_col, clear_col = st.columns(2)

    with save_col:
        if st.button("Save Match Result", key="league_save_match_result"):
            c.execute("""
            UPDATE league_matches
            SET winner_id = ?,
                player1_score = ?,
                player2_score = ?,
                notes = ?
            WHERE match_id = ?
            """, (
                winner_options[selected_winner_label],
                new_player1_score,
                new_player2_score,
                new_notes.strip(),
                match_id,
            ))
            conn.commit()
            st.success("Match result saved.")
            st.rerun()

    with clear_col:
        if st.button("Clear Match Result", key="league_clear_match_result"):
            c.execute("""
            UPDATE league_matches
            SET winner_id = NULL,
                player1_score = 0,
                player2_score = 0,
                notes = ''
            WHERE match_id = ?
            """, (match_id,))
            conn.commit()
            st.success("Match result cleared.")
            st.rerun()


def render_league_page(
    player_id,
    is_admin,
    get_setting,
    conn,
    c,
):
    ensure_league_tables(conn, c)
    seed_round_robin_schedule(conn, c)

    st.header("League")

    current_week = int(get_setting("current_week", "1"))
    matches = get_matches(c)

    tab1, tab2, tab3 = st.tabs(["Schedule", "Standings", "Postseason"])

    with tab1:
        render_schedule(matches, current_week)

    with tab2:
        render_standings(c)

    with tab3:
        render_postseason_preview(c)

    st.divider()
    render_player_result_submission(player_id, conn, c)

    if is_admin:
        st.divider()
        render_admin_result_approvals(conn, c)
        st.divider()
        render_admin_match_reporting(conn, c)
