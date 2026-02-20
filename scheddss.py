import streamlit as st
import requests
from datetime import datetime, timedelta, timezone
import time
import re

# --- 1. CONFIG ---
CLIENT_ID = "910661605032071"
CLIENT_SECRET = "a57ba995d5178d5ee80c3debba225138"
REDIRECT_URI = "https://scheddss.streamlit.app/"

st.set_page_config(page_title="Scheddss Pro", page_icon="👟", layout="wide")

if "master_queue" not in st.session_state:
    st.session_state.master_queue = {}

# --- 2. PERSISTENT LOGIN ---
if "token" in st.query_params:
    st.session_state.access_token = st.query_params["token"]
elif "access_token" not in st.session_state:
    st.session_state.access_token = None

# --- 3. AUTHENTICATION ---
if st.session_state.access_token is None:
    if "code" in st.query_params:
        code = st.query_params["code"]
        res = requests.get(f"https://graph.facebook.com/v21.0/oauth/access_token?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&client_secret={CLIENT_SECRET}&code={code}").json()
        if "access_token" in res:
            st.query_params["token"] = res["access_token"]
            st.session_state.access_token = res["access_token"]
            st.rerun()
    else:
        st.title("👟 Scheddss: Login")
        auth_url = f"https://www.facebook.com/v21.0/dialog/oauth?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=pages_show_list,pages_manage_posts,pages_read_engagement,public_profile"
        st.link_button("🔓 Log in with Facebook", auth_url, type="primary")
        st.stop()

# --- 4. DATA FETCHING ---
user_token = st.session_state.access_token
try:
    pages_res = requests.get(f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_token}").json()
    page_map = {p['name']: (p['id'], p['access_token']) for p in pages_res.get('data', [])}
except:
    st.error("Session expired. Please log in again.")
    st.stop()

with st.sidebar:
    st.header("⚙️ Settings")
    selected_page_name = st.selectbox("Target Page", list(page_map.keys()))
    target_id, target_token = page_map[selected_page_name]
    
    st.divider()
    st.write("🌍 **Timezone Config**")
    # Set to 8 for Philippines
    utc_offset = st.number_input("UTC Offset (Hours)", value=8)

tab1, tab2, tab3 = st.tabs(["🚀 New Post", "💬 Smart Commenter", "📅 Scheduled Queue"])

# --- TAB 1: NEW POST ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        uploaded_files = st.file_uploader("Upload Media", accept_multiple_files=True)
        caption = st.text_area("Post Caption", height=150)
        
        st.write("### 📝 Auto-Comments")
        if "new_comments" not in st.session_state: st.session_state.new_comments = [""]
        for i, val in enumerate(st.session_state.new_comments):
            st.session_state.new_comments[i] = st.text_area(f"Comment #{i+1}", value=val, key=f"nc_{i}", height=80)
        if st.button("➕ Add Another Comment"):
            st.session_state.new_comments.append("")
            st.rerun()

    with col2:
        timing = st.radio("Timing", ["Immediately", "Schedule"])
        unix_time = None
        if timing == "Schedule":
            d = st.date_input("Select Date")
            # TYPING TYPE TIME PICKER
            t_input = st.text_input("Type Time (24h format HH:MM)", value=datetime.now().strftime("%H:%M"))
            
            if re.match(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", t_input):
                h, m = map(int, t_input.split(":"))
                local_dt = datetime.combine(d, datetime.min.time()).replace(hour=h, minute=m)
                # Correct UTC math for Facebook
                utc_dt = local_dt - timedelta(hours=utc_offset)
                unix_time = int(utc_dt.timestamp())
                st.success(f"✅ Ready: {t_input} (UTC{utc_offset:+} )")
            else:
                st.error("Invalid format. Use HH:MM")

    if st.button("🚀 EXECUTE", use_container_width=True):
        if uploaded_files:
            file = uploaded_files[0]
            is_vid = "video" in file.type
            ep = f"https://graph-video.facebook.com/v21.0/{target_id}/videos" if is_vid else f"https://graph.facebook.com/v21.0/{target_id}/photos"
            payload = {'access_token': target_token, 'caption' if not is_vid else 'description': caption}
            
            if timing == "Schedule" and unix_time:
                payload.update({'published': 'false', 'scheduled_publish_time': unix_time})
            
            res = requests.post(ep, data=payload, files={'file': file.getvalue()}).json()
            if "id" in res:
                pid = res['id']
                # Link comments to ID in memory
                st.session_state.master_queue[pid] = [c for c in st.session_state.new_comments if c.strip()]
                st.success(f"Success! Post ID: {pid}")
            else:
                st.error(str(res))

# --- TAB 3: SCHEDULED QUEUE ---
with tab3:
    st.subheader("Manage Upcoming Posts & Comments")
    q_url = f"https://graph.facebook.com/v21.0/{target_id}/promotable_posts?is_published=false&fields=id,message,scheduled_publish_time,picture&access_token={target_token}"
    q_res = requests.get(q_url).json()
    q_data = q_res.get('data', [])

    if not q_data:
        st.info("Queue is empty.")
    else:
        for p in q_data:
            pid = p['id']
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    local_view = datetime.fromtimestamp(p['scheduled_publish_time']) + timedelta(hours=utc_offset)
                    st.markdown(f"🗓️ **Scheduled for:** `{local_view.strftime('%Y-%m-%d %I:%M %p')}`")
                    
                    new_cap = st.text_area("Caption", value=p.get('message', ''), key=f"q_cap_{pid}", height=100)
                    
                    # Manage queue comments
                    q_comms = st.session_state.master_queue.get(pid, [])
                    if q_comms:
                        st.write("💬 **Scheduled Comments:**")
                        for idx, txt in enumerate(q_comms):
                            q_comms[idx] = st.text_area(f"C#{idx+1}", value=txt, key=f"q_c_{pid}_{idx}", height=70)
                    
                    b_sv, b_del = st.columns(2)
                    if b_sv.button("💾 Save Changes", key=f"sv_{pid}"):
                        requests.post(f"https://graph.facebook.com/v21.0/{pid}", data={'message': new_cap, 'access_token': target_token})
                        st.session_state.master_queue[pid] = q_comms
                        st.rerun()
                    
                    if b_del.button("🗑️ Delete Everything", key=f"del_{pid}"):
                        requests.delete(f"https://graph.facebook.com/v21.0/{pid}?access_token={target_token}")
                        if pid in st.session_state.master_queue: del st.session_state.master_queue[pid]
                        st.rerun()

                with c2:
                    if p.get('picture'): st.image(p['picture'])
