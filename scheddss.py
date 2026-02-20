import streamlit as st
import requests
from datetime import datetime, timedelta
import time
import json

# --- 1. CONFIG & SESSION (STAYING WORKING) ---
CLIENT_ID = "910661605032071"
CLIENT_SECRET = "a57ba995d5178d5ee80c3debba225138"
REDIRECT_URI = "https://scheddss.streamlit.app/"

st.set_page_config(page_title="Scheddss Pro", page_icon="👟", layout="wide")

# SAFETY CHEETS: Prevents the AttributeError you saw
if "master_queue" not in st.session_state:
    st.session_state.master_queue = {}  
if "temp_comments" not in st.session_state:
    st.session_state.temp_comments = [""]
if "smart_comments" not in st.session_state:
    st.session_state.smart_comments = [""]
if "reset_key" not in st.session_state:
    st.session_state.reset_key = 0
if "sc_reset_key" not in st.session_state:
    st.session_state.sc_reset_key = 0

# --- AUTH LOGIC ---
if "access_token" not in st.session_state:
    if "token" in st.query_params:
        st.session_state.access_token = st.query_params["token"]
    else:
        st.title("👟 Scheddss: Login")
        auth_url = f"https://www.facebook.com/v21.0/dialog/oauth?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=pages_show_list,pages_manage_posts,pages_read_engagement,public_profile"
        st.link_button("🔓 Log in with Facebook", auth_url, type="primary")
        st.stop()

user_token = st.session_state.access_token
pages_res = requests.get(f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_token}").json()
page_map = {p['name']: (p['id'], p['access_token']) for p in pages_res.get('data', [])}

with st.sidebar:
    st.header("⚙️ Settings")
    if page_map:
        selected_page_name = st.selectbox("Target Page", list(page_map.keys()))
        target_id, target_token = page_map[selected_page_name]
    else:
        st.error("No pages found.")
        st.stop()
    utc_offset = st.number_input("UTC Offset (PH is 8)", value=8)

tab1, tab2, tab3 = st.tabs(["🚀 New Post", "💬 Smart Commenter", "📅 Scheduled Queue"])

# --- TAB 1: NEW POST ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        uploaded_files = st.file_uploader(
            "Upload Media (Photos/Videos)", 
            accept_multiple_files=True, 
            key=f"uploader_{st.session_state.reset_key}"
        )
        
        caption = st.text_area("Caption (# & Links OK)", height=150, key=f"cap_{st.session_state.reset_key}")
        
        for i in range(len(st.session_state.temp_comments)):
            st.session_state.temp_comments[i] = st.text_area(f"Comment #{i+1}", value=st.session_state.temp_comments[i], key=f"t1_c_{i}_{st.session_state.reset_key}")
        
        if st.button("➕ Add Comment", key=f"add_t1_{st.session_state.reset_key}"):
            st.session_state.temp_comments.append("")
            st.rerun()

    with col2:
        timing = st.radio("Timing", ["Immediately", "Schedule"], key=f"time_t1_{st.session_state.reset_key}")
        p_unix = None
        if timing == "Schedule":
            p_d = st.date_input("Date", key=f"date_t1_{st.session_state.reset_key}")
            t_col, ap_col = st.columns(2)
            p_t_str = t_col.text_input("Time (HH:MM)", value="12:00", key=f"t_str_t1_{st.session_state.reset_key}")
            p_ampm = ap_col.selectbox("AM/PM", ["AM", "PM"], key=f"ap_t1_{st.session_state.reset_key}")
            
            try:
                h, m = map(int, p_t_str.split(":"))
                if p_ampm == "PM" and h < 12: h += 12
                elif p_ampm == "AM" and h == 12: h = 0
                dt = datetime.combine(p_d, datetime.min.time()).replace(hour=h, minute=m)
                p_unix = int((dt - timedelta(hours=utc_offset)).timestamp())
            except: st.error("Time format error.")

    if st.button("🚀 EXECUTE POST", use_container_width=True, type="primary"):
        if not uploaded_files:
            st.error("Please select media first.")
        else:
            with st.spinner("Processing Media..."):
                media_ids = []
                for f in uploaded_files:
                    is_vid = "video" in f.type
                    ep = f"https://graph-video.facebook.com/v21.0/{target_id}/videos" if is_vid else f"https://graph.facebook.com/v21.0/{target_id}/photos"
                    res = requests.post(ep, data={'access_token': target_token, 'published': 'false'}, files={'file': f.getvalue()}).json()
                    if "id" in res: media_ids.append(res['id'])
                
                post_payload = {
                    'message': caption,
                    'access_token': target_token,
                    'attached_media': json.dumps([{'media_fbid': i} for i in media_ids])
                }
                if timing == "Schedule":
                    post_payload.update({'published': 'false', 'scheduled_publish_time': p_unix})
                
                final = requests.post(f"https://graph.facebook.com/v21.0/{target_id}/feed", data=post_payload).json()
                
                if "id" in final:
                    st.session_state.master_queue[final['id']] = {
                        "comments": [c for c in st.session_state.temp_comments if c.strip()],
                        "caption": caption
                    }
                    st.success("Post Successfully Created!")
                    st.session_state.temp_comments = [""] 
                    st.session_state.reset_key += 1 # Reset Tab 1 UI
                    time.sleep(2)
                    st.rerun()

# --- TAB 2: SMART COMMENTER ---
with tab2:
    st.subheader("💬 Smart Commenter")
    st.markdown("---")

    posts_url = f"https://graph.facebook.com/v21.0/{target_id}/published_posts?fields=id,message,full_picture,created_time&limit=10&access_token={target_token}"
    
    try:
        posts_data = requests.get(posts_url).json().get('data', [])
    except:
        posts_data = []

    if not posts_data:
        st.info("No published posts found.")
    else:
        post_options = {p['id']: f"{p.get('message', 'Media Post')[:50]}..." for p in posts_data}
        selected_post_id = st.selectbox(
            "🎯 Select a Post:", 
            options=list(post_options.keys()), 
            format_func=lambda x: post_options[x],
            key=f"sc_sel_{st.session_state.sc_reset_key}"
        )

        selected_item = next(p for p in posts_data if p['id'] == selected_post_id)
        if selected_item.get('full_picture'):
            st.image(selected_item['full_picture'], width=300)

        st.divider()

        st.write("### 📝 Your Comments")
        for i in range(len(st.session_state.smart_comments)):
            st.session_state.smart_comments[i] = st.text_area(
                f"Comment Line #{i+1}", 
                value=st.session_state.smart_comments[i], 
                key=f"sc_input_{i}_{st.session_state.sc_reset_key}",
                height=100
            )

        col_add, col_rem = st.columns(2)
        if col_add.button("➕ Add More Lines", key=f"add_sc_{st.session_state.sc_reset_key}"):
            st.session_state.smart_comments.append("")
            st.rerun()
        if col_rem.button("➖ Remove Last Line", key=f"rem_sc_{st.session_state.sc_reset_key}"):
            if len(st.session_state.smart_comments) > 1:
                st.session_state.smart_comments.pop()
                st.rerun()

        st.divider()

        st.write("### ⏰ Set Timing")
        sc_timing_mode = st.radio("When to post?", ["Immediately", "Schedule for Later"], horizontal=True, key=f"sc_mode_{st.session_state.sc_reset_key}")

        sc_unix = None
        if sc_timing_mode == "Schedule for Later":
            sc_col1, sc_col2, sc_col3 = st.columns([2, 2, 1])
            sc_date = sc_col1.date_input("Pick Date", value=datetime.now(), key=f"sc_date_{st.session_state.sc_reset_key}")
            sc_time_str = sc_col2.text_input("Time (HH:MM)", value="12:00", key=f"sc_time_{st.session_state.sc_reset_key}")
            sc_ampm = sc_col3.selectbox("AM/PM", ["AM", "PM"], key=f"sc_ap_{st.session_state.sc_reset_key}")

            try:
                sh, sm = map(int, sc_time_str.split(":"))
                if sc_ampm == "PM" and sh < 12: sh += 12
                elif sc_ampm == "AM" and sh == 12: sh = 0
                sc_dt = datetime.combine(sc_date, datetime.min.time()).replace(hour=sh, minute=sm)
                sc_unix = int((sc_dt - timedelta(hours=utc_offset)).timestamp())
            except: st.error("Format HH:MM required.")

        if st.button("🚀 EXECUTE SMART COMMENTS", use_container_width=True, type="primary"):
            valid_comments = [c.strip() for c in st.session_state.smart_comments if c.strip()]
            if not valid_comments:
                st.error("Please type a comment.")
            else:
                with st.spinner("Processing..."):
                    if sc_timing_mode == "Immediately":
                        for msg in valid_comments:
                            requests.post(f"https://graph.facebook.com/v21.0/{selected_post_id}/comments", data={'message': msg, 'access_token': target_token})
                        st.success("Comments posted immediately!")
                    else:
                        batch_id = f"sc_{int(time.time())}"
                        st.session_state.master_queue[batch_id] = {
                            "type": "delayed_comment",
                            "parent_post": selected_post_id,
                            "comments": valid_comments,
                            "scheduled_time": sc_unix
                        }
                        st.success("Comments scheduled!")
                    
                    st.session_state.smart_comments = [""]
                    st.session_state.sc_reset_key += 1 # Reset Tab 2 UI
                    time.sleep(2)
                    st.rerun()

# --- TAB 3: SCHEDULED QUEUE ---
with tab3:
    st.subheader("📅 Live Management Queue")
    q_url = f"https://graph.facebook.com/v21.0/{target_id}/scheduled_posts?fields=id,message,scheduled_publish_time,full_picture&access_token={target_token}"
    try:
        fb_posts = requests.get(q_url).json().get('data', [])
    except: fb_posts = []

    if not fb_posts and not st.session_state.master_queue:
        st.info("Queue is empty.")
    else:
        for p in fb_posts:
            pid = p['id']
            with st.container(border=True):
                col_img, col_main, col_btns = st.columns([1, 3, 2])
                ts = p['scheduled_publish_time']
                lv = datetime.fromtimestamp(ts) + timedelta(hours=utc_offset)
                
                with col_img:
                    if p.get('full_picture'): st.image(p['full_picture'], use_container_width=True)
                with col_main:
                    st.markdown(f"⏰ **Scheduled:** `{lv.strftime('%I:%M %p')}`")
                    st.markdown(f"📝 **Caption:** {p.get('message', '')[:50]}...")
                with col_btns:
                    if st.button("🗑️ Delete", key=f"del_{pid}"):
                        requests.delete(f"https://graph.facebook.com/v21.0/{pid}?access_token={target_token}")
                        if pid in st.session_state.master_queue: del st.session_state.master_queue[pid]
                        st.rerun()
                    e_btn = st.button("📝 Edit", key=f"ed_{pid}")

                if e_btn or st.session_state.get(f"act_{pid}"):
                    st.session_state[f"act_{pid}"] = True
                    with st.expander("Edit Post", expanded=True):
                        new_cap = st.text_area("Caption", value=p.get('message', ''), key=f"upc_{pid}")
                        if st.button("Save Changes", key=f"sav_{pid}"):
                            requests.post(f"https://graph.facebook.com/v21.0/{pid}", data={'message': new_cap, 'access_token': target_token})
                            st.session_state[f"act_{pid}"] = False
                            st.rerun()

    st.divider()
    st.write("### 💬 Independent Comment Queue")
    for qid, data in list(st.session_state.master_queue.items()):
        if data.get('type') == "delayed_comment":
            with st.container(border=True):
                st.write(f"Post ID: {data['parent_post']}")
                if st.button("🗑️ Remove", key=f"rm_scq_{qid}"):
                    del st.session_state.master_queue[qid]
                    st.rerun()
