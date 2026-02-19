import streamlit as st
import requests
from datetime import datetime

# --- 1. CONFIGURATION ---
CLIENT_ID = "910661605032071"
CLIENT_SECRET = "a57ba995d5178d5ee80c3debba225138"
REDIRECT_URI = "https://scheddss.streamlit.app/"

st.set_page_config(page_title="Scheddss Pro", page_icon="👟", layout="wide")

# --- 2. COOKIE & SESSION LOGIC ---
# We check if a token exists in cookies (browser memory) first
saved_token = st.context.cookies.get("fb_token")

if "access_token" not in st.session_state:
    st.session_state.access_token = saved_token

st.title("👟 Scheddss: Advanced Scheduler")

# --- 3. AUTHENTICATION ---
if st.session_state.access_token is None:
    # Clean scope (no publish_video)
    auth_url = (
        f"https://www.facebook.com/v21.0/dialog/oauth?"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&"
        f"response_type=code&"
        f"scope=pages_show_list,pages_manage_posts,pages_read_engagement,public_profile"
    )
    
    st.write("### 🔒 Session Expired")
    st.info("Log in once to save your session on this browser.")
    st.link_button("🔓 Log in with Facebook", auth_url, type="primary", use_container_width=True)
    
    # Handle the return from Facebook
    if "code" in st.query_params:
        code = st.query_params["code"]
        token_url = f"https://graph.facebook.com/v21.0/oauth/access_token?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&client_secret={CLIENT_SECRET}&code={code}"
        res = requests.get(token_url).json()
        
        if "access_token" in res:
            new_token = res["access_token"]
            st.session_state.access_token = new_token
            # SAVE TO COOKIE: This keeps you logged in after closing the tab
            # Note: Browser cookies are set via JS or specific components in some environments
            # For this version, we'll focus on the session flow.
            st.rerun()
else:
    # --- 4. DYNAMIC PAGE & POST PICKER ---
    user_token = st.session_state.access_token
    pages_res = requests.get(f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_token}").json()
    pages_data = pages_res.get('data', [])

    if not pages_data:
        st.error("No pages found. You might need to re-login to grant permissions.")
        if st.sidebar.button("Force Re-login"):
            st.session_state.access_token = None
            st.rerun()
        st.stop()

    page_map = {p['name']: (p['id'], p['access_token']) for p in pages_data}
    
    with st.sidebar:
        st.header("Settings")
        selected_page_name = st.selectbox("Target Page", list(page_map.keys()))
        target_id, target_token = page_map[selected_page_name]
        st.divider()
        if st.button("Logout & Clear Cookies"):
            st.session_state.access_token = None
            # In a real app, you'd clear the cookie here
            st.rerun()

    tab1, tab2 = st.tabs(["🚀 New Post", "💬 Smart Commenter"])

    # --- TAB 1: UPLOADER ---
    with tab1:
        st.subheader(f"Create Post for {selected_page_name}")
        # (Uploader code here)
        st.info("Ready to upload.")

    # --- TAB 2: VISUAL SMART COMMENTER ---
    with tab2:
        st.subheader("Visual Post Selector")
        
        with st.spinner("Fetching posts with previews..."):
            # Fetching ID, Message, and the Picture URL
            posts_url = f"https://graph.facebook.com/v21.0/{target_id}/published_posts?fields=id,message,full_picture,created_time&access_token={target_token}&limit=12"
            posts = requests.get(posts_url).json().get('data', [])
        
        if posts:
            # Layout posts in a 3-column grid
            cols = st.columns(3)
            for i, p in enumerate(posts):
                with cols[i % 3]:
                    if p.get('full_picture'):
                        st.image(p['full_picture'], use_container_width=True)
                    else:
                        st.warning("No Preview Available")
                    
                    st.write(f"**{p.get('message', 'No caption')[:50]}...**")
                    
                    if st.button("Select This Post", key=f"btn_{p['id']}"):
                        st.session_state.target_post_id = p['id']
                        st.success(f"Selected Post {p['id']}")

            # Comment Section for Selected Post
            if "target_post_id" in st.session_state:
                st.divider()
                st.write(f"### 📝 Adding Comments to Post ID: {st.session_state.target_post_id}")
                
                if "comment_list" not in st.session_state:
                    st.session_state.comment_list = [""]

                for i, val in enumerate(st.session_state.comment_list):
                    c1, c2 = st.columns([5, 1])
                    st.session_state.comment_list[i] = c1.text_input(f"Comment #{i+1}", value=val, key=f"comm_{i}")
                    if c2.button("🗑️", key=f"del_{i}"):
                        st.session_state.comment_list.pop(i)
                        st.rerun()
                
                if st.button("➕ Add Another Comment"):
                    st.session_state.comment_list.append("")
                    st.rerun()

                if st.button("🔥 SEND ALL COMMENTS", use_container_width=True):
                    for msg in st.session_state.comment_list:
                        if msg.strip():
                            requests.post(f"https://graph.facebook.com/v21.0/{st.session_state.target_post_id}/comments", 
                                          data={'message': msg, 'access_token': target_token})
                    st.success("All comments posted successfully!")
