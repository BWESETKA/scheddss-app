import streamlit as st
import requests
from datetime import datetime
import time

# --- 1. INITIALIZATION & CONFIG ---
CLIENT_ID = "910661605032071"
CLIENT_SECRET = "a57ba995d5178d5ee80c3debba225138"
REDIRECT_URI = "https://scheddss.streamlit.app/"

st.set_page_config(page_title="Scheddss Pro", page_icon="👟", layout="wide")

# Initialize safety variables to prevent NameError
target_id = None
target_token = None

# --- 2. PERSISTENT DATA LOGIC (URL SYNC) ---
# Check URL for saved token to prevent repeat login
if "token" in st.query_params:
    st.session_state.access_token = st.query_params["token"]
elif "access_token" not in st.session_state:
    st.session_state.access_token = None

st.title("👟 Scheddss: Professional Suite")

# --- 3. AUTHENTICATION ---
if st.session_state.access_token is None:
    auth_url = (
        f"https://www.facebook.com/v21.0/dialog/oauth?"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&"
        f"response_type=code&"
        f"scope=pages_show_list,pages_manage_posts,pages_read_engagement,public_profile"
    )
    st.info("👋 Welcome! Log in once to save your session in the URL.")
    st.link_button("🔓 Log in with Facebook", auth_url, type="primary")

    if "code" in st.query_params:
        code = st.query_params["code"]
        res = requests.get(f"https://graph.facebook.com/v21.0/oauth/access_token?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&client_secret={CLIENT_SECRET}&code={code}").json()
        if "access_token" in res:
            st.query_params["token"] = res["access_token"]
            st.session_state.access_token = res["access_token"]
            st.rerun()
else:
    # --- 4. DATA FETCHING ---
    user_token = st.session_state.access_token
    try:
        pages_res = requests.get(f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_token}").json()
        pages_data = pages_res.get('data', [])
    except:
        pages_data = []

    if not pages_data:
        st.error("Session expired or no pages found.")
        if st.button("Re-authenticate"):
            st.query_params.clear()
            st.session_state.access_token = None
            st.rerun()
        st.stop()

    page_map = {p['name']: (p['id'], p['access_token']) for p in pages_data}
    
    with st.sidebar:
        st.header("Settings")
        selected_page_name = st.selectbox("Select Target Page", list(page_map.keys()))
        target_id, target_token = page_map[selected_page_name]
        st.divider()
        if st.button("Clear App & Logout"):
            st.query_params.clear()
            st.session_state.access_token = None
            st.rerun()

    tab1, tab2 = st.tabs(["🚀 New Post Creator", "💬 Smart Commenter"])

    # --- TAB 1: NEW POST ---
    with tab1:
        st.subheader("Post & Sched Comment Queue")
        col1, col2 = st.columns(2)
        
        with col1:
            uploaded_files = st.file_uploader("Upload Media", accept_multiple_files=True)
            # URL persistence for caption
            saved_cap = st.query_params.get("cap", "")
            caption = st.text_area("Post Caption", value=saved_cap)
            if caption != saved_cap: st.query_params["cap"] = caption

            st.write("### 📝 Attached Comments")
            if "new_comments" not in st.session_state: st.session_state.new_comments = [""]
            
            for i, val in enumerate(st.session_state.new_comments):
                st.session_state.new_comments[i] = st.text_input(f"Comment #{i+1}", value=val, key=f"nc_{i}")
            
            if st.button("➕ Add Comment Line"):
                st.session_state.new_comments.append("")
                st.rerun()

        with col2:
            timing = st.radio("Timing", ["Immediately", "Schedule"])
            pub_time = datetime.now()
            if timing == "Schedule":
                d = st.date_input("Date")
                t = st.time_input("Time")
                pub_time = datetime.combine(d, t)

        if st.button("🚀 EXECUTE POSTING", use_container_width=True):
            with st.spinner("Uploading..."):
                if uploaded_files:
                    file = uploaded_files[0]
                    is_vid = "video" in file.type
                    endpoint = f"https://graph-video.facebook.com/v21.0/{target_id}/videos" if is_vid else f"https://graph.facebook.com/v21.0/{target_id}/photos"
                    payload = {'access_token': target_token, 'caption' if not is_vid else 'description': caption}
                    if timing == "Schedule":
                        payload.update({'published': 'false', 'scheduled_publish_time': int(pub_time.timestamp())})
                    
                    res = requests.post(endpoint, data=payload, files={'file': file.getvalue()})
                    if res.status_code == 200:
                        st.success("Post set!")
                        if timing == "Immediately":
                            pid = res.json().get('id')
                            for c in st.session_state.new_comments:
                                if c.strip(): requests.post(f"https://graph.facebook.com/v21.0/{pid}/comments", data={'message': c, 'access_token': target_token})
                    else:
                        st.error(res.text)

    # --- TAB 2: SMART COMMENTER ---
    with tab2:
        st.subheader("Visual Post Selector")
        # Ensure we have target info before calling API
        if target_id and target_token:
            posts_res = requests.get(f"https://graph.facebook.com/v21.0/{target_id}/published_posts?fields=id,message,picture&access_token={target_token}&limit=15").json()
            posts = posts_res.get('data', [])
            
            if posts:
                post_opts = {p['id']: f"{p.get('message', 'No caption')[:40]}..." for p in posts}
                sel_id = st.selectbox("Pick a post:", options=list(post_opts.keys()), format_func=lambda x: post_opts[x])
                
                # Tiny Thumbnail Preview
                sel_post = next(p for p in posts if p['id'] == sel_id)
                if sel_post.get('picture'):
                    st.image(sel_post['picture'], width=100)

                st.divider()
                if "smart_comments" not in st.session_state:
                    st.session_state.smart_comments = [{"text": "", "date": datetime.now(), "time": datetime.now().time()}]

                for j, comm in enumerate(st.session_state.smart_comments):
                    with st.container(border=True):
                        c1, c2, c3, c4 = st.columns([3, 1, 1, 0.5])
                        st.session_state.smart_comments[j]["text"] = c1.text_input("Comment", value=comm["text"], key=f"sct_{j}")
                        st.session_state.smart_comments[j]["date"] = c2.date_input("Date", value=comm["date"], key=f"scd_{j}")
                        st.session_state.smart_comments[j]["time"] = c3.time_input("Time", value=comm["time"], key=f"sctime_{j}")
                        if c4.button("🗑️", key=f"scdel_{j}"):
                            st.session_state.smart_comments.pop(j)
                            st.rerun()
                
                if st.button("➕ Add Another Comment Line"):
                    st.session_state.smart_comments.append({"text": "", "date": datetime.now(), "time": datetime.now().time()})
                    st.rerun()

                if st.button("💬 BLAST COMMENTS", use_container_width=True):
                    for c in st.session_state.smart_comments:
                        if c["text"].strip():
                            requests.post(f"https://graph.facebook.com/v21.0/{sel_id}/comments", data={'message': c["text"], 'access_token': target_token})
                    st.success("All comments sent!")
