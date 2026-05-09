import streamlit as st
import html


def inject_global_styles():
    st.markdown("""
    <style>
    .pack-card-img {
        width: 100%;
        border-radius: 10px;
        transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease, filter 0.15s ease;
    }
    .pack-card-img:hover {
        transform: translateY(-2px) scale(1.015);
        box-shadow: 0 8px 20px rgba(0,0,0,0.22);
    }
    .pack-card-img.used-up {
        opacity: 0.38;
        filter: grayscale(70%);
    }
    .pack-card-img.favorite-card {
        border: 3px solid #d4af37;
        box-shadow: 0 0 10px rgba(212,175,55,0.65);
    }
    .pack-card-img.new-card {
        border: 3px solid #24c869;
        box-shadow: 0 0 10px rgba(36,200,105,0.65);
    }
    .small-card-name {
        font-size: 0.9rem;
        font-weight: 650;
        line-height: 1.15;
        margin-top: 0.25rem;
        margin-bottom: 0.1rem;
    }
    .used-text {
        font-size: 0.8rem;
        opacity: 0.78;
    }
    </style>
    """, unsafe_allow_html=True)


def set_preview(img, name):
    if img:
        st.session_state["preview_img"] = img
        st.session_state["preview_name"] = name


def render_preview_panel(location_key):
    if "preview_img" in st.session_state:
        preview_col, close_col = st.columns([4, 1])
        with preview_col:
            st.markdown(f"**Preview:** {st.session_state.get('preview_name', '')}")
            st.image(
                st.session_state["preview_img"],
                width=300
            )
        with close_col:
            if st.button("Close", key=f"close_preview_{location_key}"):
                st.session_state.pop("preview_img", None)
                st.session_state.pop("preview_name", None)
                st.rerun()
        st.divider()


def render_card_image(img, name, fully_used=False, favorite=False, new_card=False):
    if not img:
        st.info("No image")
        return

    css_classes = ["pack-card-img"]
    if fully_used:
        css_classes.append("used-up")
    if favorite:
        css_classes.append("favorite-card")
    if new_card:
        css_classes.append("new-card")

    safe_img = html.escape(img, quote=True)
    safe_name = html.escape(name, quote=True)
    st.markdown(
        f'<img src="{safe_img}" alt="{safe_name}" class="{" ".join(css_classes)}">',
        unsafe_allow_html=True
    )


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
