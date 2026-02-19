import streamlit as st
import requests
from datetime import datetime
import time

# --- 1. CONFIGURATION ---
CLIENT_ID = "910661605032071"
CLIENT_SECRET = "a57ba995d5178d5ee80c3debba225138"
REDIRECT_URI = "https://scheddss.streamlit.app/"

st.set_page_config(page_title="Scheddss Pro", page_icon="👟", layout="wide")

# Initialize global variables to prevent NameErrors
target_id = None
target_token = None

# --- 2. PERSISTENT LOGIN LOGIC (URL SYNC) ---
# This part looks at the address bar. If ?token= exists, it skips the login screen.
if "token" in st.query_params:
    st.session_state.access_token = st.query_params["token"]
elif "access_token" not in st.session_state:
    st.session_state.access_token = None

st.title("👟 Scheddss: Universal Suite")

# --- 3. AUTHENTICATION FLOW ---
if st.session_state.access_token is None:
    # Check if we are returning from FB with a code
    if "code" in st.query_params:
        code = st.query_params["code"]
        res = requests.get(f"https://graph.facebook.com/v21.0/oauth/access_token?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&client_secret={CLIENT_SECRET}&code={code}").json()
        if "access_token" in res:
            # Set the token in URL and State
            st.query_params["token"] = res["access_token"]
            st.session_state.access_token = res["access_token"]
            st.rerun()
    else:
        # Show Login Button ONLY if no token is found in URL or Session
        auth_url = (
            f"https://www.facebook.com/v21.0/dialog/oauth?"
            f"client_id={CLIENT_ID}&"
            f"redirect_uri={REDIRECT_URI}&"
            f"response_type=code&"
            f"scope=pages_show_list,pages_manage_posts,pages_read_engagement,public_profile"
        )
        st.info("👋 Access restricted. Please log in to unlock your dashboard.")
        st.link_button("🔓 Log in with Facebook", auth_url, type="primary")
        st.stop() # Stops the rest of the app from loading until login is done

# --- 4. DASHBOARD (Reached only if token exists) ---
user_token = st.session_state.access_token
try:
    pages_res = requests.get(f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_token}").json()
    pages_data = pages_res.get('data', [])
except:
    pages_data = []

if not pages_data:
    st.error("Invalid session or no pages found.")
    if st.sidebar.button("Reset & Re-login"):
        st.query_params.clear()
        st.session_state.access_token = None
        st.rerun()
    st.stop()

page_map = {p['name']: (p['id'], p['access_token']) for p in pages_data}

with st.sidebar:
    st.header("Settings")
    selected_page_name = st.selectbox("Target Page", list(page_map.keys()))
    target_id, target_token = page_map[selected_page_name]
    st.divider()
    if st.button("Logout"):
        st.query_params.clear()
        st.session_state.access_token = None
        st.rerun()

tab1, tab2, tab3 = st.tabs(["🚀 New Post", "💬 Smart Commenter", "📅 Scheduled Queue"])

# --- TAB 1: NEW POST (With Wrap-Text Area) ---
with tab1:
    st.subheader("Create Media Post")
    col1, col2 = st.columns(2)
    with col1:
        uploaded_files = st.file_uploader("Upload Files", accept_multiple_files=True)
        caption = st.text_area("Post Caption", value=st.query_params.get("cap", ""), height=150)
        if caption: st.query_params["cap"] = caption
        
        st.write("### 📝 Auto-Comments")
        if "new_comments" not in st.session_state: st.session_state.new_comments = [""]
        for i, val in enumerate(st.session_state.new_comments):
            st.session_state.new_comments[i] = st.text_area(f"Comment #{i+1}", value=val, key=f"nc_{i}", height=80)
        
        if st.button("➕ Add Comment"):
            st.session_state.new_comments.append("")
            st.rerun()

    with col2:
        timing = st.radio("Post Timing", ["Immediately", "Schedule"])
        pub_time = datetime.now()
        if timing == "Schedule":
            d = st.date_input("Date")
            t = st.time_input("Time")
            pub_time = datetime.combine(d, t)

    if st.button("🚀 EXECUTE", use_container_width=True):
        if uploaded_files:
            with st.spinner("Uploading..."):
                file = uploaded_files[0]
                is_vid = "video" in file.type
                ep = f"https://graph-video.facebook.com/v21.0/{target_id}/videos" if is_vid else f"https://graph.facebook.com/v21.0/{target_id}/photos"
                payload = {'access_token': target_token, 'caption' if not is_vid else 'description': caption}
                if timing == "Schedule":
                    payload.update({'published': 'false', 'scheduled_publish_time': int(pub_time.timestamp())})
                
                res = requests.post(ep, data=payload, files={'file': file.getvalue()})
                if res.status_code == 200:
                    st.success("Post set successfully!")
                    if timing == "Immediately":
                        pid = res.json().get('id')
                        for c in st.session_state.new_comments:
                            if c.strip(): requests.post(f"https://graph.facebook.com/v21.0/{pid}/comments", data={'message': c, 'access_token': target_token})
                else: st.error(res.text)

# --- TAB 2: SMART COMMENTER (Standard FB Wrap Style) ---
with tab2:
    st.subheader("Comment on Existing Posts")
    posts_res = requests.get(f"https://graph.facebook.com/v21.0/{target_id}/published_posts?fields=id,message,picture&access_token={target_token}&limit=15").json()
    posts_list = posts_res.get('data', [])
    
    if posts_list:
        post_opts = {p['id']: f"{p.get('message', 'No caption')[:40]}..." for p in posts_list}
        sel_id = st.selectbox("Pick Post:", options=list(post_opts.keys()), format_func=lambda x: post_opts[x])
        
        sel_data = next(p for p in posts_list if p['id'] == sel_id)
        if sel_data.get('picture'): st.image(sel_data['picture'], width=80)

        st.divider()
        if "smart_comments" not in st.session_state:
            st.session_state.smart_comments = [{"text": "", "date": datetime.now(), "time": datetime.now().time()}]

        for j, comm in enumerate(st.session_state.smart_comments):
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([4, 1.2, 1.2, 0.6])
                st.session_state.smart_comments[j]["text"] = c1.text_area("Comment Text", value=comm["text"], key=f"sct_{j}", height=100)
                st.session_state.smart_comments[j]["date"] = c2.date_input("Date", value=comm["date"], key=f"scd_{j}")
                st.session_state.smart_comments[j]["time"] = c3.time_input("Time", value=comm["time"], key=f"sctm_{j}")
                if c4.button("🗑️", key=f"scdel_{j}"):
                    st.session_state.smart_comments.pop(j)
                    st.rerun()
        
        if st.button("➕ Add Another Line"):
            st.session_state.smart_comments.append({"text": "", "date": datetime.now(), "time": datetime.now().time()})
            st.rerun()

        if st.button("💬 BLAST COMMENTS", use_container_width=True):
            for c in st.session_state.smart_comments:
                if c["text"].strip():
                    requests.post(f"https://graph.facebook.com/v21.0/{sel_id}/comments", data={'message': c["text"], 'access_token': target_token})
            st.success("All comments posted!")
    else: st.info("No posts found.")

# --- TAB 3: SCHEDULED QUEUE ---
with tab3:
    st.subheader("Upcoming Posts")
    q_res = requests.get(f"https://graph.facebook.com/v21.0/{target_id}/promotable_posts?is_published=false&fields=id,message,scheduled_publish_time,picture&access_token={target_token}").json()
    q_posts = q_res.get('data', [])

    if not q_posts: st.info("Nothing scheduled yet.")
    else:
        for p in q_posts:
            with st.container(border=True):
                col_p, col_i = st.columns([4, 1])
                with col_p:
                    st_time = datetime.fromtimestamp(p['scheduled_publish_time']).strftime('%Y-%m-%d %H:%M')
                    st.write(f"📅 **Live at:** `{st_time}`")
                    new_msg = st.text_area("Caption", value=p.get('message', ''), key=f"q_edit_{p['id']}", height=100)
                    
                    sub_c1, sub_c2 = st.columns(2)
                    if sub_c1.button("💾 Save Changes", key=f"q_sv_{p['id']}"):
                        requests.post(f"https://graph.facebook.com/v21.0/{p['id']}", data={'message': new_msg, 'access_token': target_token})
                        st.rerun()
                    if sub_c2.button("🗑️ Delete Post", key=f"q_dl_{p['id']}"):
                        requests.delete(f"https://graph.facebook.com/v21.0/{p['id']}?access_token={target_token}")
                        st.rerun()
                with col_i:
                    if p.get('picture'): st.image(p['picture'], width=100)
