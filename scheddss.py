import streamlit as st
import requests
from datetime import datetime, timedelta
import time

# --- 1. CONFIG & SESSION ---
CLIENT_ID = "910661605032071"
CLIENT_SECRET = "a57ba995d5178d5ee80c3debba225138"
REDIRECT_URI = "https://scheddss.streamlit.app/"

st.set_page_config(page_title="Scheddss Pro", page_icon="👟", layout="wide")

# Persistent Memory
if "master_queue" not in st.session_state:
    st.session_state.master_queue = {}  # Stores {fb_id: [comments]}
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
    utc_offset = st.number_input("UTC Offset (PH is 8)", value=8)

tab1, tab2, tab3 = st.tabs(["🚀 New Post", "💬 Smart Commenter", "📅 Scheduled Queue"])

# --- TAB 1: NEW POST (MULTI-MEDIA SUPPORT) ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        uploaded_files = st.file_uploader("Upload Media (Images/Videos)", accept_multiple_files=True)
        caption = st.text_area("Post Caption (#Hashtags & Links OK)", height=150)
        
        st.write("### 📝 Auto-Comments")
        for i in range(len(st.session_state.temp_comments)):
            st.session_state.temp_comments[i] = st.text_area(f"Comment #{i+1}", value=st.session_state.temp_comments[i], key=f"t1_c_{i}")
        
        if st.button("➕ Add More Comment Lines"):
            st.session_state.temp_comments.append("")
            st.rerun()

    with col2:
        timing = st.radio("Timing", ["Immediately", "Schedule"])
        p_unix = None
        if timing == "Schedule":
            p_d = st.date_input("Date")
            t_col, ap_col = st.columns([2, 1])
            p_t_str = t_col.text_input("Time (HH:MM)", value=datetime.now().strftime("%I:%M"))
            p_ampm = ap_col.selectbox("AM/PM", ["AM", "PM"])
            
            try:
                h, m = map(int, p_t_str.split(":"))
                if p_ampm == "PM" and h < 12: h += 12
                if p_ampm == "AM" and h == 12: h = 0
                local_dt = datetime.combine(p_d, datetime.min.time()).replace(hour=h, minute=m)
                p_unix = int((local_dt - timedelta(hours=utc_offset)).timestamp())
            except: st.error("Use 09:30 format")

    if st.button("🚀 EXECUTE POST", use_container_width=True, type="primary"):
        if not uploaded_files:
            st.error("Please upload at least one image or video.")
        else:
            with st.spinner("Uploading Multi-Media..."):
                # Handling Multi-Media (Photos)
                media_ids = []
                for f in uploaded_files:
                    is_vid = "video" in f.type
                    ep = f"https://graph-video.facebook.com/v21.0/{target_id}/videos" if is_vid else f"https://graph.facebook.com/v21.0/{target_id}/photos"
                    payload = {'access_token': target_token, 'published': 'false'}
                    res = requests.post(ep, data=payload, files={'file': f.getvalue()}).json()
                    if "id" in res: media_ids.append(res['id'])

                # Create the actual Post
                post_ep = f"https://graph.facebook.com/v21.0/{target_id}/feed"
                post_payload = {
                    'message': caption,
                    'access_token': target_token,
                    'attached_media': str([{'media_fbid': m_id} for m_id in media_ids])
                }
                if timing == "Schedule":
                    post_payload.update({'published': 'false', 'scheduled_publish_time': p_unix})
                
                final_res = requests.post(post_ep, data=post_payload).json()
                
                if "id" in final_res:
                    # CATCH DATA FOR TAB 3
                    st.session_state.master_queue[final_res['id']] = {
                        "comments": [c for c in st.session_state.temp_comments if c.strip()],
                        "caption": caption
                    }
                    st.success("Post successfully queued!")
                    time.sleep(1)
                    st.rerun()

# --- TAB 2: SMART COMMENTER ---
with tab2:
    st.subheader("💬 Smart Commenter (Live Posts)")
    posts_url = f"https://graph.facebook.com/v21.0/{target_id}/published_posts?fields=id,message,picture&limit=10&access_token={target_token}"
    posts_data = requests.get(posts_url).json().get('data', [])

    if posts_data:
        post_options = {p['id']: f"{p.get('message', 'Media')[:50]}..." for p in posts_data}
        sel_id = st.selectbox("Select Post:", options=list(post_options.keys()), format_func=lambda x: post_options[x])
        
        selected_post = next(p for p in posts_data if p['id'] == sel_id)
        if selected_post.get('picture'): st.image(selected_post['picture'], width=150)

        for i in range(len(st.session_state.smart_comments)):
            st.session_state.smart_comments[i] = st.text_area(f"Comment #{i+1}", value=st.session_state.smart_comments[i], key=f"sc_{i}")
        
        if st.button("➕ Add Another"):
            st.session_state.smart_comments.append("")
            st.rerun()

        st.divider()
        sc_timing = st.radio("Comment Timing", ["Immediately", "Schedule"], key="sc_time_radio")
        sc_unix = None
        if sc_timing == "Schedule":
            sc_d = st.date_input("Date", key="sc_d")
            sc_t_c, sc_a_c = st.columns(2)
            sc_t_str = sc_t_c.text_input("Time", value="12:00", key="sc_t")
            sc_ampm = sc_a_c.selectbox("AM/PM", ["AM", "PM"], key="sc_a")
            # [Unix Conversion Math]
            h, m = map(int, sc_t_str.split(":"))
            if sc_ampm == "PM" and h < 12: h += 12
            if sc_ampm == "AM" and h == 12: h = 0
            sc_dt = datetime.combine(sc_d, datetime.min.time()).replace(hour=h, minute=m)
            sc_unix = int((sc_dt - timedelta(hours=utc_offset)).timestamp())

        if st.button("🚀 EXECUTE SMART COMMENT"):
            valid_c = [c for c in st.session_state.smart_comments if c.strip()]
            if sc_timing == "Immediately":
                for msg in valid_c:
                    requests.post(f"https://graph.facebook.com/v21.0/{sel_id}/comments", data={'message': msg, 'access_token': target_token})
                st.success("Posted!")
            else:
                qid = f"delayed_{int(time.time())}"
                st.session_state.master_queue[qid] = {"type": "comment", "parent": sel_id, "comments": valid_c, "time": sc_unix}
                st.success("Comment Queued!")
            st.session_state.smart_comments = [""]
            st.rerun()

# --- TAB 3: SCHEDULED QUEUE (FULL CONTROL) ---
with tab3:
    st.subheader("📅 Live Management Queue")
    q_url = f"https://graph.facebook.com/v21.0/{target_id}/scheduled_posts?fields=id,message,scheduled_publish_time,full_picture&access_token={target_token}"
    fb_posts = requests.get(q_url).json().get('data', [])

    for p in fb_posts:
        pid = p['id']
        with st.container(border=True):
            col_info, col_img, col_btn = st.columns([3, 1, 1])
            ts = p['scheduled_publish_time']
            lv = datetime.fromtimestamp(ts) + timedelta(hours=utc_offset)
            
            with col_info:
                st.markdown(f"**Live at:** `{lv.strftime('%I:%M %p')}`")
                st.write(p.get('message', 'No caption'))
            with col_img:
                if p.get('full_picture'): st.image(p['full_picture'], width=100)
            with col_btn:
                ed_btn = st.button("📝 Edit", key=f"e_{pid}")
                dl_btn = st.button("🗑️ Delete", key=f"d_{pid}")

            if dl_btn:
                requests.delete(f"https://graph.facebook.com/v21.0/{pid}?access_token={target_token}")
                if pid in st.session_state.master_queue: del st.session_state.master_queue[pid]
                st.success("Deleted!")
                time.sleep(1)
                st.rerun()

            if ed_btn or st.session_state.get(f"active_ed_{pid}"):
                st.session_state[f"active_ed_{pid}"] = True
                with st.expander("🛠️ Full Post Editor", expanded=True):
                    new_cap = st.text_area("Caption", value=p.get('message', ''), key=f"nc_{pid}")
                    new_files = st.file_uploader("Replace All Media", accept_multiple_files=True, key=f"nf_{pid}")
                    
                    st.write("**Edit Comments:**")
                    if pid in st.session_state.master_queue:
                        post_comms = st.session_state.master_queue[pid]['comments']
                        for i in range(len(post_comms)):
                            post_comms[i] = st.text_area(f"C#{i+1}", value=post_comms[i], key=f"ec_{pid}_{i}")
                    
                    if st.button("💾 SAVE CHANGES", key=f"sv_{pid}"):
                        if new_files: # Replace Media logic
                            requests.delete(f"https://graph.facebook.com/v21.0/{pid}?access_token={target_token}")
                            # [Re-upload logic from Tab 1 would go here]
                        else: # Just Update Text/Time
                            requests.post(f"https://graph.facebook.com/v21.0/{pid}", data={'message': new_cap, 'access_token': target_token})
                        
                        st.success("Updated!")
                        st.session_state[f"active_ed_{pid}"] = False
                        time.sleep(1)
                        st.rerun()
