import streamlit as st
import requests
from datetime import datetime, timedelta
import time
import re

# --- 1. CONFIG & SESSION ---
CLIENT_ID = "910661605032071"
CLIENT_SECRET = "a57ba995d5178d5ee80c3debba225138"
REDIRECT_URI = "https://scheddss.streamlit.app/"

st.set_page_config(page_title="Scheddss Pro", page_icon="👟", layout="wide")

# Persistent Storage
if "master_queue" not in st.session_state:
    st.session_state.master_queue = {}  # Format: {id: {"type": "post", "comments": []}}
if "temp_comments" not in st.session_state:
    st.session_state.temp_comments = [""]
if "smart_comments" not in st.session_state:
    st.session_state.smart_comments = [""]

# --- 2. AUTHENTICATION ---
if "token" in st.query_params:
    st.session_state.access_token = st.query_params["token"]
elif "access_token" not in st.session_state:
    st.session_state.access_token = None

if st.session_state.access_token is None:
    st.title("👟 Scheddss: Login")
    auth_url = f"https://www.facebook.com/v21.0/dialog/oauth?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=pages_show_list,pages_manage_posts,pages_read_engagement,public_profile"
    st.link_button("🔓 Log in with Facebook", auth_url, type="primary")
    st.stop()

# --- 3. PAGE DATA ---
user_token = st.session_state.access_token
try:
    pages_res = requests.get(f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_token}").json()
    page_map = {p['name']: (p['id'], p['access_token']) for p in pages_res.get('data', [])}
except:
    st.error("Session expired. Please refresh or re-login.")
    st.stop()

with st.sidebar:
    st.header("⚙️ Settings")
    selected_page_name = st.selectbox("Target Page", list(page_map.keys()))
    target_id, target_token = page_map[selected_page_name]
    st.divider()
    utc_offset = st.number_input("UTC Offset (PH is 8)", value=8)

tab1, tab2, tab3 = st.tabs(["🚀 New Post", "💬 Smart Commenter", "📅 Scheduled Queue"])

# --- TAB 1: NEW POST ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        uploaded_files = st.file_uploader("Upload Media", accept_multiple_files=True)
        caption = st.text_area("Post Caption (Links & #Hashtags OK)", height=150)
        st.write("### 📝 Auto-Comments")
        for i in range(len(st.session_state.temp_comments)):
            st.session_state.temp_comments[i] = st.text_area(f"Comment #{i+1}", value=st.session_state.temp_comments[i], key=f"t1_c_{i}")
        if st.button("➕ Add Post Comment"):
            st.session_state.temp_comments.append("")
            st.rerun()

    with col2:
        timing = st.radio("Post Timing", ["Immediately", "Schedule"])
        p_unix = None
        if timing == "Schedule":
            p_d = st.date_input("Post Date", key="p_date")
            t_c, a_c = st.columns([2,1])
            p_t_str = t_c.text_input("Post Time (HH:MM)", value=datetime.now().strftime("%I:%M"), key="p_time")
            p_ampm = a_c.selectbox("AM/PM", ["AM", "PM"], key="p_ampm")
            try:
                h, m = map(int, p_t_str.split(":"))
                if p_ampm == "PM" and h < 12: h += 12
                if p_ampm == "AM" and h == 12: h = 0
                dt = datetime.combine(p_d, datetime.min.time()).replace(hour=h, minute=m)
                p_unix = int((dt - timedelta(hours=utc_offset)).timestamp())
                st.success(f"✅ Post set for {p_t_str} {p_ampm}")
            except: st.error("Use 09:30 format")

    if st.button("🚀 EXECUTE POST", use_container_width=True):
        if uploaded_files:
            file = uploaded_files[0]
            is_vid = "video" in file.type
            ep = f"https://graph-video.facebook.com/v21.0/{target_id}/videos" if is_vid else f"https://graph.facebook.com/v21.0/{target_id}/photos"
            payload = {'access_token': target_token, 'caption' if not is_vid else 'description': caption}
            if timing == "Schedule": payload.update({'published': 'false', 'scheduled_publish_time': p_unix})
            
            res = requests.post(ep, data=payload, files={'file': file.getvalue()}).json()
            if "id" in res:
                st.session_state.master_queue[res['id']] = {"type": "post", "comments": [c for c in st.session_state.temp_comments if c.strip()]}
                st.success(f"Success! ID: {res['id']}")
                st.session_state.temp_comments = [""]
            else: st.error(str(res))

# --- TAB 2: SMART COMMENTER (With AM/PM Scheduler) ---
with tab2:
    st.subheader("💬 Bulk/Scheduled Comments on Live Posts")
    posts_url = f"https://graph.facebook.com/v21.0/{target_id}/published_posts?fields=id,message,picture&limit=10&access_token={target_token}"
    posts_data = requests.get(posts_url).json().get('data', [])

    if not posts_data: st.info("No posts found.")
    else:
        post_options = {p['id']: f"{p.get('message', 'Media')[:50]}..." for p in posts_data}
        sel_id = st.selectbox("1. Select Live Post:", options=list(post_options.keys()), format_func=lambda x: post_options[x])
        
        st.write("### 2. Prepare Comments")
        for i in range(len(st.session_state.smart_comments)):
            st.session_state.smart_comments[i] = st.text_area(f"Comment #{i+1}", value=st.session_state.smart_comments[i], key=f"sc_{i}")
        if st.button("➕ Add Another Comment Line"):
            st.session_state.smart_comments.append("")
            st.rerun()

        st.divider()
        st.write("### 3. Set Time")
        c_timing = st.radio("Comment Timing", ["Immediately", "Schedule Comment"])
        c_unix = None
        if c_timing == "Schedule Comment":
            c_d = st.date_input("Comment Date")
            t_c2, a_c2 = st.columns([2,1])
            c_t_str = t_c2.text_input("Comment Time (HH:MM)", value=datetime.now().strftime("%I:%M"), key="c_time")
            c_ampm = a_c2.selectbox("AM/PM", ["AM", "PM"], key="c_ampm")
            try:
                h, m = map(int, c_t_str.split(":"))
                if c_ampm == "PM" and h < 12: h += 12
                if c_ampm == "AM" and h == 12: h = 0
                dt_c = datetime.combine(c_d, datetime.min.time()).replace(hour=h, minute=m)
                c_unix = int((dt_c - timedelta(hours=utc_offset)).timestamp())
                st.success(f"✅ Comment queued for {c_t_str} {c_ampm}")
            except: st.error("Use 09:30 format")

        if st.button("🚀 EXECUTE SMART COMMENT", use_container_width=True):
            valid_c = [c for c in st.session_state.smart_comments if c.strip()]
            if c_timing == "Immediately":
                for msg in valid_c:
                    requests.post(f"https://graph.facebook.com/v21.0/{sel_id}/comments", data={'message': msg, 'access_token': target_token})
                st.success("Posted now!")
            else:
                # We save this to the queue using a unique key
                queue_id = f"comment_{sel_id}_{int(time.time())}"
                st.session_state.master_queue[queue_id] = {
                    "type": "delayed_comment", 
                    "parent_post": sel_id, 
                    "scheduled_time": c_unix,
                    "comments": valid_c
                }
                st.success("Comment added to Scheduled Queue!")
            st.session_state.smart_comments = [""]

# --- TAB 3: SCHEDULED QUEUE (Lists Posts AND Scheduled Comments) ---
with tab3:
    st.subheader("📅 Unified Management Queue")
    # Fetch FB Posts
    q_url = f"https://graph.facebook.com/v21.0/{target_id}/promotable_posts?is_published=false&fields=id,message,scheduled_publish_time,picture&access_token={target_token}"
    fb_posts = requests.get(q_url).json().get('data', [])

    # Display FB Scheduled Posts
    st.write("### 🚀 Scheduled Posts")
    for p in fb_posts:
        pid = p['id']
        with st.container(border=True):
            lv = datetime.fromtimestamp(p['scheduled_publish_time']) + timedelta(hours=utc_offset)
            st.write(f"⏰ **Post Live at:** `{lv.strftime('%I:%M %p')}`")
            st.text_area("Caption", value=p.get('message', ''), key=f"q_p_{pid}")
            if pid in st.session_state.master_queue:
                st.write("💬 **Linked Comments:**")
                for i, txt in enumerate(st.session_state.master_queue[pid]['comments']):
                    st.session_state.master_queue[pid]['comments'][i] = st.text_input(f"C{i+1}", value=txt, key=f"q_pc_{pid}_{i}")
            if st.button("🗑️ Delete Post", key=f"del_p_{pid}"):
                requests.delete(f"https://graph.facebook.com/v21.0/{pid}?access_token={target_token}")
                st.rerun()

    # Display Scheduled Comments (from Tab 2)
    st.write("### 💬 Independently Scheduled Comments")
    for qid, data in list(st.session_state.master_queue.items()):
        if data['type'] == "delayed_comment":
            with st.container(border=True):
                clv = datetime.fromtimestamp(data['scheduled_time']) + timedelta(hours=utc_offset)
                st.write(f"⏰ **Comment Live at:** `{clv.strftime('%I:%M %p')}` | Post ID: `{data['parent_post']}`")
                for idx, c_txt in enumerate(data['comments']):
                    data['comments'][idx] = st.text_area(f"Comment {idx+1}", value=c_txt, key=f"q_dc_{qid}_{idx}")
                if st.button("🗑️ Remove from Queue", key=f"del_q_{qid}"):
                    del st.session_state.master_queue[qid]
                    st.rerun()
