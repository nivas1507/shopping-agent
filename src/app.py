import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

from agent import build_agent, ask
from setup_db import DB_PATH, create_database

st.set_page_config(page_title="Fresh Cart", page_icon=":material/shopping_basket:", layout="wide")

if not os.path.exists(DB_PATH):
    create_database()


@st.cache_resource
def get_agent():
    return build_agent()


SAMPLES = [
    (":material/emoji_nature:", "Find me organic honey under $20 with 4.5+ rating"),
    (":material/emoji_food_beverage:", "What are the best rated teas?"),
    (":material/eco:", "Show organic snacks under $10"),
    (":material/coffee:", "Find coffee with 4.5+ rating"),
    (":material/shopping_cart_checkout:", "Order the Organic Acacia Honey"),
]

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending" not in st.session_state:
    st.session_state.pending = None

with st.sidebar:
    st.header(":material/shopping_basket: Fresh Cart")
    st.caption("Your AI grocery assistant")
    if st.button("New chat", icon=":material/add_circle:", type="primary", width="stretch"):
        st.session_state.messages = []
        st.session_state.pending = None
        st.rerun()
    st.divider()
    st.subheader("Try asking")
    for icon, q in SAMPLES:
        if st.button(q, icon=icon, width="stretch", key=q):
            st.session_state.pending = q

with st.container(border=True):
    st.title(":green[Fresh] :orange[Cart] :material/shopping_basket:")
    st.markdown("Search groceries, filter by price and rating, and place orders just by chatting.")
    st.badge("Organic", icon=":material/eco:", color="green")
    st.badge("Top rated", icon=":material/star:", color="yellow")
    st.badge("Fast ordering", icon=":material/bolt:", color="orange")

if not st.session_state.messages:
    st.info("Pick a sample from the sidebar or type below to get started.", icon=":material/lightbulb:")

AVATARS = {"user": ":material/person:", "assistant": ":material/storefront:"}

for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar=AVATARS[m["role"]]):
        st.markdown(m["content"])

prompt = st.chat_input("Ask me to find or order a product...") or st.session_state.pending
st.session_state.pending = None

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=AVATARS["user"]):
        st.markdown(prompt)
    with st.chat_message("assistant", avatar=AVATARS["assistant"]):
        with st.spinner("Browsing the shelves..."):
            try:
                reply = ask(get_agent(), st.session_state.messages)
            except Exception as e:
                reply = f"Sorry, something went wrong: `{e}`"
        st.markdown(reply)
    st.session_state.messages.append({"role": "assistant", "content": reply})
