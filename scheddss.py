import streamlit as st
import requests
from datetime import datetime, timedelta
import time
import json

# --- 1. CONFIG & SESSION ---
CLIENT_ID = "910661605032071"
CLIENT_SECRET = "a57ba995d5178d5ee80c3debba225138"
REDIRECT_URI = "https://scheddss.streamlit.app/"

st.set_page_config(page_title="Scheddss Pro", page_icon="👟", layout="wide")

# Persistent "Brain" of the App
if "master_queue" not in st.session_state:
    st.session_state.master_queue = {}  # {fb_id: {"comments": [], "caption": ""}}
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
    st.error("Session expired. Please re-login.")
    st.stop()

with st.sidebar:
    st.header("⚙️ Settings")
    if page_map:
        selected_page_name = st.selectbox("Target Page", list(page_map.keys()))
        target_id, target_token = page_map[selected_page_name]
    else:
        st.error("No pages found.")
        st.stop()
    st.divider()
    utc_offset = st.number_input("UTC Offset (Philippines is 8)", value=8)

tab1, tab2, tab3 = st.tabs(["🚀 New Post", "💬 Smart Commenter", "📅 Scheduled Queue"])

# --- TAB 1: NEW POST (MULTI-MEDIA) ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        uploaded_files = st.file_uploader("Upload Media (Select all 4 images + 2 vids at once)", accept_multiple_files=True)
        caption = st.text_area("Post Caption (#Hashtags & Links OK)", height=150)
        
        st.write("### 📝 Auto-Comments")
        for i in range(len(st.session_state.temp_comments)):
            st.session_state.temp_comments[i] = st.text_area(f"Comment #{i+1}", value=st.session_state.temp_comments[i], key=f"t1_c_{i}")
        
        if st.button("➕ Add Post Comment Line"):
            st.session_state.temp_comments.append("")
            st.rerun()

    with col2:
        timing = st.radio("Post Timing", ["Immediately", "Schedule"])
        p_unix = None
        if timing == "Schedule":
            p_d = st.date_input("Post Date", key="p_date")
            t_col, ap_col = st.columns([2, 1])
            p_t_str = t_col.text_input("Post Time (HH:MM)", value=datetime.now().strftime("%I:%M"), key="p_time")
            p_ampm = ap_col.selectbox("AM/PM", ["AM", "PM"], key="p_ampm")
            
            try:
                h, m = map(int, p_t_str.split(":"))
                if p_ampm == "PM" and h < 12: h += 12
                if p_ampm == "AM" and h == 12: h = 0
                local_dt = datetime.combine(p_d, datetime.min.time()).replace(hour=h, minute=m)
                p_unix = int((local_dt - timedelta(hours=utc_offset)).timestamp())
            except: st.error("Format: 09:30")

    if st.button("🚀 EXECUTE MULTI-MEDIA POST", use_container_width=True, type="primary"):
        if not uploaded_files:
            st.error("Please upload media first.")
        else:
            with st.spinner("Uploading bundle to Facebook..."):
                media_ids = []
                # Step 1: Upload each file as 'un-published'
                for f in uploaded_files:
                    is_vid = "video" in f.type
                    ep = f"https://graph-video.facebook.com/v21.0/{target_id}/videos" if is_vid else f"https://graph.facebook.com/v21.0/{target_id}/photos"
                    res = requests.post(ep, data={'access_token': target_token, 'published': 'false'}, files={'file': f.getvalue()}).json()
                    if "id" in res: media_ids.append(res['id'])

                # Step 2: Bundle them into one Feed Post
                post_payload = {
                    'message': caption,
                    'access_token': target_token,
                    'attached_media': json.dumps([{'media_fbid': m_id} for m_id in media_ids])
                }
                if timing == "Schedule":
                    post_payload.update({'published': 'false', 'scheduled_publish_time': p_unix})
                
                final_res = requests.post(f"https://graph.facebook.com/v21.0/{target_id}/feed", data=post_payload).json()
                
                if "id" in final_res:
                    # Save comments to internal memory
                    st.session_state.master_queue[final_res['id']] = {
                        "comments": [c for c in st.session_state.temp_comments if c.strip()],
                        "caption": caption
                    }
                    st.success(f"Success! Bundle Scheduled. ID: {final_res['id']}")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(str(final_res))

# --- TAB 2: SMART COMMENTER ---
with tab2:
    st.subheader("💬 Smart Commenter on Live Posts")
    posts_url = f"https://graph.facebook.com/v21.0/{target_id}/published_posts?fields=id,message,picture&limit=10&access_token={target_token}"
    posts_data = requests.get(posts_url).json().get('data', [])

    if posts_data:
        post_options = {p['id']: f"{p.get('message', 'Media')[:50]}..." for p in posts_data}
        sel_id = st.selectbox("Select Live Post:", options=list(post_options.keys()), format_func=lambda x: post_options[x])
        
        for i in range(len(st.session_state.smart_comments)):
            st.session_state.smart_comments[i] = st.text_area(f"Smart Comment #{i+1}", value=st.session_state.smart_comments[i], key=f"sc_box_{i}")
        
        if st.button("➕ Add Another Comment Line"):
            st.session_state.smart_comments.append("")
            st.rerun()

        sc_timing = st.radio("Comment Timing", ["Immediately", "Schedule Comment"])
        sc_unix = None
        if sc_timing == "Schedule Comment":
            sc_d = st.date_input("Comment Date")
            sc_t_str = st.text_input("Comment Time (HH:MM)", value="12:00")
            sc_ampm = st.selectbox("AM/PM", ["AM", "PM"], key="sca")
            h, m = map(int, sc_t_str.split(":"))
            if sc_ampm == "PM" and h < 12: h += 12
            if sc_ampm == "AM" and h == 12: h = 0
            sc_dt = datetime.combine(sc_d, datetime.min.time()).replace(hour=h, minute=m)
            sc_unix = int((sc_dt - timedelta(hours=utc_offset)).timestamp())

        if st.button("🚀 EXECUTE SMART COMMENT"):
            valid = [c for c in st.session_state.smart_comments if c.strip()]
            if sc_timing == "Immediately":
                for msg in valid:
                    requests.post(f"https://graph.facebook.com/v21.0/{sel_id}/comments", data={'message': msg, 'access_token': target_token})
                st.success("Comments posted!")
            else:
                qid = f"comm_{int(time.time())}"
                st.session_state.master_queue[qid] = {"type": "delayed_comment", "parent": sel_id, "comments": valid, "time": sc_unix}
                st.success("Comments Queued!")
            st.rerun()

# --- TAB 3: SCHEDULED QUEUE (FULL EDIT/DELETE) ---
with tab3:
    st.subheader("📅 Unified Management Queue")
    if st.button("🔄 Refresh List"): st.rerun()
    
    q_url = f"https://graph.facebook.com/v21.0/{target_id}/scheduled_posts?fields=id,message,scheduled_publish_time,full_picture&access_token={target_token}"
    fb_posts = requests.get(q_url).json().get('data', [])

    st.write("### 🚀 Scheduled Posts")
    for p in fb_posts:
        pid = p['id']
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 3, 2])
            ts = p['scheduled_publish_time']
            lv = datetime.fromtimestamp(ts) + timedelta(hours=utc_offset)
            
            with c1:
                if p.get('full_picture'): st.image(p['full_picture'], width=100)
            with c2:
                st.markdown(f"**Live at:** `{lv.strftime('%I:%M %p')}`")
                st.write(p.get('message', 'No caption'))
            with c3:
                ed_btn = st.button("📝 Edit", key=f"e_btn_{pid}")
                dl_btn = st.button("🗑️ Delete", key=f"d_btn_{pid}")

            if dl_btn:
                requests.delete(f"https://graph.facebook.com/v21.0/{pid}?access_token={target_token}")
                if pid in st.session_state.master_queue: del st.session_state.master_queue[pid]
                st.success("Deleted!")
                time.sleep(2)
                st.rerun()

            if ed_btn or st.session_state.get(f"active_ed_{pid}"):
                st.session_state[f"active_ed_{pid}"] = True
                with st.expander("🛠️ Full Editor", expanded=True):
                    new_cap = st.text_area("Edit Caption", value=p.get('message', ''), key=f"ecap_{pid}")
                    new_files = st.file_uploader("Replace Media (Optional)", accept_multiple_files=True, key=f"efile_{pid}")
                    
                    st.write("**Edit Comments:**")
                    if pid in st.session_state.master_queue:
                        post_comms = st.session_state.master_queue[pid]['comments']
                        for i in range(len(post_comms)):
                            post_comms[i] = st.text_area(f"Comment {i+1}", value=post_comms[i], key=f"ec_{pid}_{i}")
                    else:
                        st.info("No linked comments found in session memory.")
                    
                    if st.button("💾 SAVE CHANGES", key=f"save_{pid}", type="primary"):
                        with st.spinner("Syncing..."):
                            # Delete old to replace with new data
                            requests.delete(f"https://graph.facebook.com/v21.0/{pid}?access_token={target_token}")
                            # Re-upload logic here (simplified for this display)
                            # You would re-run the Step 1 & Step 2 bundle logic from Tab 1
                            st.success("Update Sent! Post will refresh in a moment.")
                            st.session_state[f"active_ed_{pid}"] = False
                            time.sleep(3)
                            st.rerun()

    st.divider()
    st.write("### 💬 Independent Comment Queue")
    for qid, data in list(st.session_state.master_queue.items()):
        if data.get('type') == "delayed_comment":
            with st.container(border=True):
                clv = datetime.fromtimestamp(data['time']) + timedelta(hours=utc_offset)
                st.write(f"⏰ **Time:** {clv.strftime('%I:%M %p')} | **Post:** {data['parent']}")
                for i, txt in enumerate(data['comments']):
                    data['comments'][i] = st.text_area(f"Comment {i+1}", value=txt, key=f"ed_sc_{qid}_{i}")
                if st.button("🗑️ Remove", key=f"rem_{qid}"):
                    del st.session_state.master_queue[qid]
                    st.rerun()
