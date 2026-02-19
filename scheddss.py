import streamlit as st
import requests
from datetime import datetime
import time

# --- 1. CONFIGURATION ---
CLIENT_ID = "910661605032071"
CLIENT_SECRET = "a57ba995d5178d5ee80c3debba225138"
REDIRECT_URI = "https://scheddss.streamlit.app/"

st.set_page_config(page_title="Scheddss Universal", page_icon="👟", layout="wide")

# --- 2. PERSISTENT LOGIN LOGIC ---
# We check URL params for a saved token first
if "token" in st.query_params:
    st.session_state.access_token = st.query_params["token"]

if "access_token" not in st.session_state:
    st.session_state.access_token = None

st.title("👟 Scheddss: Professional Uploader")

# --- 3. AUTHENTICATION ---
if st.session_state.access_token is None:
    auth_url = (
        f"https://www.facebook.com/v21.0/dialog/oauth?"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&"
        f"response_type=code&"
        f"scope=pages_show_list,pages_manage_posts,pages_read_engagement,public_profile"
    )
    st.info("Log in once to start. Your session will be saved in the URL.")
    st.link_button("🔓 Log in with Facebook", auth_url, type="primary")

    if "code" in st.query_params:
        code = st.query_params["code"]
        res = requests.get(f"https://graph.facebook.com/v21.0/oauth/access_token?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&client_secret={CLIENT_SECRET}&code={code}").json()
        if "access_token" in res:
            # Save token to URL for persistence
            st.query_params["token"] = res["access_token"]
            st.session_state.access_token = res["access_token"]
            st.rerun()
else:
    # --- 4. MAIN APP LOGIC ---
    user_token = st.session_state.access_token
    pages_res = requests.get(f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_token}").json()
    pages_data = pages_res.get('data', [])

    if not pages_data:
        st.error("No pages found. Ensure you checked all pages during login.")
        if st.button("Reset Login"):
            st.query_params.clear()
            st.session_state.access_token = None
            st.rerun()
        st.stop()

    page_map = {p['name']: (p['id'], p['access_token']) for p in pages_data}
    
    with st.sidebar:
        st.header("Settings")
        selected_page_name = st.selectbox("Target Page/Group", list(page_map.keys()))
        target_id, target_token = page_map[selected_page_name]
        if st.button("Logout"):
            st.query_params.clear()
            st.session_state.access_token = None
            st.rerun()

    tab1, tab2 = st.tabs(["🚀 New Post", "💬 Smart Commenter"])

    # --- TAB 1: NEW POST (MIXED MEDIA & SCHEDULING) ---
    with tab1:
        st.subheader("Create New Content")
        col1, col2 = st.columns(2)
        
        with col1:
            uploaded_files = st.file_uploader("Upload Media (Photos/Videos)", accept_multiple_files=True)
            caption = st.text_area("Post Caption")
            
            # Dynamic Comment Section for New Post
            st.write("### 📝 Scheduled Comments")
            if "new_comments" not in st.session_state: st.session_state.new_comments = [""]
            
            for i, val in enumerate(st.session_state.new_comments):
                st.session_state.new_comments[i] = st.text_input(f"Comment #{i+1}", value=val, key=f"new_comm_{i}")
            
            if st.button("➕ Add Another Comment", key="add_new"):
                st.session_state.new_comments.append("")
                st.rerun()

        with col2:
            timing = st.radio("When to post?", ["Immediately", "Schedule"])
            publish_time = datetime.now()
            if timing == "Schedule":
                d = st.date_input("Date")
                t = st.time_input("Time")
                publish_time = datetime.combine(d, t)
                st.warning(f"Will post at: {publish_time}")

        if st.button("🚀 EXECUTE POST", use_container_width=True):
            with st.spinner("Processing media..."):
                # Handle Mixed Media (This logic sends the first file; carousel needs batch API)
                if uploaded_files:
                    file = uploaded_files[0]
                    is_video = "video" in file.type
                    endpoint = f"https://graph-video.facebook.com/v21.0/{target_id}/videos" if is_video else f"https://graph.facebook.com/v21.0/{target_id}/photos"
                    
                    payload = {'access_token': target_token, 'caption' if not is_video else 'description': caption}
                    if timing == "Schedule":
                        payload.update({'published': 'false', 'scheduled_publish_time': int(publish_time.timestamp())})
                    
                    res = requests.post(endpoint, data=payload, files={'file': file.getvalue()})
                    if res.status_code == 200:
                        st.success("Post processed!")
                        # Post comments if Immediate
                        if timing == "Immediately":
                            post_id = res.json().get('id')
                            for c in st.session_state.new_comments:
                                if c.strip(): requests.post(f"https://graph.facebook.com/v21.0/{post_id}/comments", data={'message': c, 'access_token': target_token})
                    else:
                        st.error(res.json().get('error', {}).get('message'))

    # --- TAB 2: SMART COMMENTER (Visual & Clean) ---
    with tab2:
        st.subheader("Manage Existing Posts")
        
        # 1. Fetch Posts with Thumbnails
        posts_res = requests.get(f"https://graph.facebook.com/v21.0/{target_id}/published_posts?fields=id,message,full_picture&access_token={target_token}&limit=15").json()
        posts = posts_res.get('data', [])
        
        if posts:
            # Custom dropdown logic: show thumbnail + snippet
            post_options = {p['id']: f"{p.get('message', 'No caption')[:30]}... (ID: {p['id']})" for p in posts}
            selected_id = st.selectbox("Pick a post to comment on:", options=list(post_options.keys()), format_func=lambda x: post_options[x])
            
            # Show small preview
            selected_data = next(p for p in posts if p['id'] == selected_id)
            if selected_data.get('full_picture'):
                st.image(selected_data['full_picture'], width=150, caption="Preview")

            st.divider()
            
            # 2. Dynamic Comments
            if "smart_comments" not in st.session_state: st.session_state.smart_comments = [""]
            for j, val in enumerate(st.session_state.smart_comments):
                st.session_state.smart_comments[j] = st.text_input(f"Comment #{j+1}", value=val, key=f"smart_comm_{j}")
            
            if st.button("➕ Add Another Comment", key="add_smart"):
                st.session_state.smart_comments.append("")
                st.rerun()

            if st.button("💬 POST ALL COMMENTS NOW", use_container_width=True):
                for msg in st.session_state.smart_comments:
                    if msg.strip():
                        requests.post(f"https://graph.facebook.com/v21.0/{selected_id}/comments", data={'message': msg, 'access_token': target_token})
                st.success("Comments live!")
