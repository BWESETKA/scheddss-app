import streamlit as st
import requests
from datetime import datetime

# --- 1. CONFIGURATION ---
CLIENT_ID = "910661605032071"
CLIENT_SECRET = "a57ba995d5178d5ee80c3debba225138"
REDIRECT_URI = "https://scheddss.streamlit.app/"

st.set_page_config(page_title="Scheddss Pro", page_icon="👟", layout="wide")

# Initialize session state for the "Plus Button" comments
if "comment_list" not in st.session_state:
    st.session_state.comment_list = [""] # Starts with one empty comment box
if "access_token" not in st.session_state:
    st.session_state.access_token = None

st.title("👟 Scheddss: Advanced Scheduler")

# --- 2. AUTHENTICATION ---
if st.session_state.access_token is None:
    # Removed publish_video to fix the "Invalid Scopes" error
    auth_url = (
        f"https://www.facebook.com/v21.0/dialog/oauth?"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&"
        f"response_type=code&"
        f"scope=pages_show_list,pages_manage_posts,pages_read_engagement,public_profile"
    )
    st.link_button("🔓 Log in with Facebook", auth_url, type="primary")
    
    if "code" in st.query_params:
        code = st.query_params["code"]
        token_url = f"https://graph.facebook.com/v21.0/oauth/access_token?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&client_secret={CLIENT_SECRET}&code={code}"
        res = requests.get(token_url).json()
        if "access_token" in res:
            st.session_state.access_token = res["access_token"]
            st.rerun()
else:
    # --- 3. DYNAMIC PAGE PICKER ---
    user_token = st.session_state.access_token
    # This call fetches EVERY page you have permission for
    pages_res = requests.get(f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_token}").json()
    pages_data = pages_res.get('data', [])

    if not pages_data:
        st.warning("No pages found. Did you select them during Facebook Login?")
        if st.button("Reset Permissions"):
            st.session_state.access_token = None
            st.rerun()
        st.stop()

    # Create the mapping for the dropdown
    page_map = {p['name']: (p['id'], p['access_token']) for p in pages_data}
    
    with st.sidebar:
        st.header("Settings")
        selected_page_name = st.selectbox("Select Target Page", list(page_map.keys()))
        target_id, target_token = page_map[selected_page_name]
        st.divider()
        if st.button("Logout"):
            st.session_state.access_token = None
            st.rerun()

    tab1, tab2 = st.tabs(["🚀 New Media Post", "💬 Smart Commenter"])

    # --- TAB 1: UPLOADER ---
    with tab1:
        st.subheader(f"Posting to: {selected_page_name}")
        col1, col2 = st.columns(2)
        with col1:
            files = st.file_uploader("Upload Images/Videos", accept_multiple_files=True)
            caption = st.text_area("Post Caption")
        with col2:
            post_now = st.radio("Timing", ["Immediately", "Schedule"])
            if post_now == "Schedule":
                d = st.date_input("Date")
                t = st.time_input("Time")
                st.info(f"Unix Timestamp will be generated for: {d} {t}")

        if st.button("🚀 Publish Post"):
            st.write("Processing upload...")

    # --- TAB 2: SMART COMMENTER ---
    with tab2:
        st.subheader("Manage Comments")
        
        # 1. DYNAMIC POST PICKER
        with st.spinner("Loading recent posts..."):
            posts_url = f"https://graph.facebook.com/v21.0/{target_id}/published_posts?access_token={target_token}&limit=15"
            posts = requests.get(posts_url).json().get('data', [])
        
        if posts:
            post_options = {f"{p.get('message', 'No text content')[:50]}...": p['id'] for p in posts}
            target_post_id = st.selectbox("Pick a post to comment on:", list(post_options.keys()))
            actual_post_id = post_options[target_post_id]
        else:
            actual_post_id = st.text_input("No posts found. Enter Post ID manually:")

        st.divider()
        st.write("### 📝 Scheduled Comments")
        
        # 2. UNLIMITED COMMENT BOXES
        for i, comment_val in enumerate(st.session_state.comment_list):
            col_msg, col_del = st.columns([5, 1])
            st.session_state.comment_list[i] = col_msg.text_input(f"Comment #{i+1}", value=comment_val, key=f"input_{i}")
            if col_del.button("🗑️", key=f"del_{i}"):
                st.session_state.comment_list.pop(i)
                st.rerun()

        # THE PLUS BUTTON
        if st.button("➕ Add Another Comment"):
            st.session_state.comment_list.append("")
            st.rerun()

        if st.button("🔥 SEND ALL COMMENTS", use_container_width=True):
            for msg in st.session_state.comment_list:
                if msg.strip():
                    requests.post(f"https://graph.facebook.com/v21.0/{actual_post_id}/comments", 
                                  data={'message': msg, 'access_token': target_token})
            st.success("All comments sent!")

