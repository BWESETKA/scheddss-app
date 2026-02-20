import streamlit as st
import requests
from datetime import datetime, timedelta
import time
import json
from supabase import create_client, Client

# --- 1. CONFIG & SESSION ---
CLIENT_ID = "910661605032071"
CLIENT_SECRET = "a57ba995d5178d5ee80c3debba225138"
REDIRECT_URI = "https://scheddss.streamlit.app/"

# --- SUPABASE CONFIG ---
SUPABASE_URL = "https://elpwqqvgrdovocvkzgyl.supabase.co"
SUPABASE_KEY = "sb_publishable_6FBWrUK1dLH-AUGF7DMjRA_8Wyl3dRE"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Scheddss Pro", page_icon="👟", layout="wide")

# SAFETY CHEETS
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

# --- AUTH LOGIC (FIXED) ---
if "access_token" not in st.session_state:
    # 1. Check if we are returning from FB with a code
    if "code" in st.query_params:
        auth_code = st.query_params["code"]
        
        # 2. Exchange code for token
        token_url = "https://graph.facebook.com/v21.0/oauth/access_token"
        token_params = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "code": auth_code,
        }
        
        token_res = requests.get(token_url, params=token_params).json()
        
        if "access_token" in token_res:
            st.session_state.access_token = token_res["access_token"]
            st.query_params.clear() # Clean URL
            st.rerun()
        else:
            st.error(f"Login Failed: {token_res.get('error', {}).get('message', 'Unknown error')}")
            st.stop()
    
    # 3. No token? Show Login Button
    else:
        st.title("👟 Scheddss: Login")
        auth_url = f"https://www.facebook.com/v21.0/dialog/oauth?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=pages_show_list,pages_manage_posts,pages_read_engagement,public_profile"
        st.link_button("🔓 Log in with Facebook", auth_url, type="primary")
        st.stop()

# --- IF LOGGED IN, PROCEED ---
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

# --- TAB 1: NEW POST (SUPABASE CONNECTED) ---
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
                    post_id = final['id']
                    valid_comments = [c for c in st.session_state.temp_comments if c.strip()]
                    
                    # --- CLOUD SYNC FOR COMMENTS ---
                    if valid_comments:
                        try:
                            for msg in valid_comments:
                                supabase.table("comment_queue").insert({
                                    "parent_post_id": post_id,
                                    "comment_text": msg,
                                    "scheduled_time": p_unix if timing == "Schedule" else int(time.time() + 30),
                                    "page_access_token": target_token,
                                    "status": "pending"
                                }).execute()
                        except Exception as e:
                            st.warning(f"Post created, but comments failed to cloud-sync: {e}")

                    st.success("Post & Comments Secured in Cloud!")
                    st.session_state.temp_comments = [""] 
                    st.session_state.reset_key += 1 
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(f"Post failed: {final}")

# --- TAB 2: SMART COMMENTER (COMPLETE) ---
with tab2:
    st.subheader("💬 Smart Commenter")
    st.markdown("---")

    # 1. FETCH PUBLISHED POSTS
    posts_url = f"https://graph.facebook.com/v21.0/{target_id}/published_posts?fields=id,message,full_picture,created_time&limit=10&access_token={target_token}"
    
    try:
        posts_data = requests.get(posts_url).json().get('data', [])
    except:
        posts_data = []

    if not posts_data:
        st.info("No published posts found.")
    else:
        # 2. SELECT POST TO COMMENT ON
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

        # 3. INPUT MULTIPLE COMMENTS
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

        # 4. TIMING LOGIC
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
            except: 
                st.error("Format HH:MM required.")

        # 5. EXECUTION (DATABASE SYNC)
        if st.button("🚀 EXECUTE SMART COMMENTS", use_container_width=True, type="primary"):
            valid_comments = [c.strip() for c in st.session_state.smart_comments if c.strip()]
            
            if not valid_comments:
                st.error("Please type a comment.")
            else:
                with st.spinner("Processing..."):
                    if sc_timing_mode == "Immediately":
                        for msg in valid_comments:
                            requests.post(f"https://graph.facebook.com/v21.0/{selected_post_id}/comments", 
                                          data={'message': msg, 'access_token': target_token})
                        st.success("Comments posted immediately!")
                    else:
                        # --- CLOUD SAVE LOGIC ---
                        try:
                            for msg in valid_comments:
                                supabase.table("comment_queue").insert({
                                    "parent_post_id": selected_post_id,
                                    "comment_text": msg,
                                    "scheduled_time": sc_unix,
                                    "page_access_token": target_token,
                                    "status": "pending"
                                }).execute()
                            st.success("Comments saved to Cloud Database!")
                        except Exception as e:
                            st.error(f"Cloud Save Failed: {e}")
                    
                    # Reset UI after success
                    st.session_state.smart_comments = [""]
                    st.session_state.sc_reset_key += 1 
                    time.sleep(2)
                    st.rerun()

# --- TAB 3: THE FULL MANAGEMENT QUEUE (COMPLETE) ---
with tab3:
    st.subheader("📅 Live Management Queue")
    
    # 1. FETCH LIVE DATA FROM FACEBOOK (FOR POSTS)
    q_url = f"https://graph.facebook.com/v21.0/{target_id}/scheduled_posts?fields=id,message,scheduled_publish_time,full_picture&access_token={target_token}"
    try:
        fb_posts = requests.get(q_url).json().get('data', [])
    except:
        fb_posts = []

    if not fb_posts:
        st.info("Your queue is currently empty.")
    else:
        st.write(f"Showing **{len(fb_posts)}** scheduled posts:")
        
        for p in fb_posts:
            pid = p['id']
            with st.container(border=True):
                col_img, col_main, col_btns = st.columns([1, 3, 2])
                
                # Convert Unix back to PH Time
                ts = p['scheduled_publish_time']
                lv = datetime.fromtimestamp(ts) + timedelta(hours=utc_offset)
                
                with col_img:
                    if p.get('full_picture'):
                        st.image(p['full_picture'], use_container_width=True)
                    else:
                        st.write("📁 Multi-Media")

                with col_main:
                    st.markdown(f"⏰ **Scheduled:** `{lv.strftime('%I:%M %p')} - {lv.strftime('%b %d')}`")
                    st.markdown(f"📝 **Caption:** {p.get('message', 'No caption')[:100]}...")

                with col_btns:
                    e_btn = st.button("📝 Edit Details", key=f"edit_ui_{pid}")
                    d_btn = st.button("🗑️ Delete Post", key=f"del_ui_{pid}", type="secondary")

                # --- DELETE LOGIC (POSTS) ---
                if d_btn:
                    with st.spinner("Deleting..."):
                        del_res = requests.delete(f"https://graph.facebook.com/v21.0/{pid}?access_token={target_token}").json()
                        if del_res.get("success"):
                            st.success("Post Deleted.")
                            time.sleep(1)
                            st.rerun()

                # --- EDIT LOGIC (POSTS) ---
                if e_btn or st.session_state.get(f"active_ed_{pid}"):
                    st.session_state[f"active_ed_{pid}"] = True
                    with st.expander("🛠️ FULL EDITOR MODE", expanded=True):
                        up_caption = st.text_area("Update Caption", value=p.get('message', ''), key=f"up_cap_{pid}")
                        up_files = st.file_uploader("Replace All Media (Optional)", accept_multiple_files=True, key=f"up_file_{pid}")
                        
                        st.write("**Change Schedule Time:**")
                        t1, t2 = st.columns(2)
                        up_time_str = t1.text_input("Time (HH:MM)", value=lv.strftime("%I:%M"), key=f"up_time_{pid}")
                        up_ampm = t2.selectbox("AM/PM", ["AM", "PM"], index=0 if lv.strftime("%p")=="AM" else 1, key=f"up_ap_{pid}")
                        
                        if st.button("💾 SAVE & RE-SYNC TO FACEBOOK", key=f"save_all_{pid}", type="primary"):
                            with st.spinner("Updating..."):
                                try:
                                    h, m = map(int, up_time_str.split(":"))
                                    if up_ampm == "PM" and h < 12: h += 12
                                    elif up_ampm == "AM" and h == 12: h = 0
                                    new_dt = datetime.combine(lv.date(), datetime.min.time()).replace(hour=h, minute=m)
                                    up_unix = int((new_dt - timedelta(hours=utc_offset)).timestamp())

                                    if up_files:
                                        # To change media, FB requires deleting and re-posting
                                        requests.delete(f"https://graph.facebook.com/v21.0/{pid}?access_token={target_token}")
                                        new_mids = []
                                        for f in up_files:
                                            is_vid = "video" in f.type
                                            ep = f"https://graph-video.facebook.com/v21.0/{target_id}/videos" if is_vid else f"https://graph.facebook.com/v21.0/{target_id}/photos"
                                            res = requests.post(ep, data={'access_token': target_token, 'published': 'false'}, files={'file': f.getvalue()}).json()
                                            if "id" in res: new_mids.append(res['id'])
                                        
                                        requests.post(f"https://graph.facebook.com/v21.0/{target_id}/feed", data={
                                            'message': up_caption,
                                            'access_token': target_token,
                                            'attached_media': json.dumps([{'media_fbid': i} for i in new_mids]),
                                            'published': 'false',
                                            'scheduled_publish_time': up_unix
                                        })
                                    else:
                                        # Just update caption/time on existing post
                                        requests.post(f"https://graph.facebook.com/v21.0/{pid}", data={
                                            'message': up_caption,
                                            'scheduled_publish_time': up_unix,
                                            'access_token': target_token
                                        })

                                    st.success("Changes Saved!")
                                    st.session_state[f"active_ed_{pid}"] = False
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Update failed: {e}")

                        if st.button("✖️ Cancel", key=f"can_ed_{pid}"):
                            st.session_state[f"active_ed_{pid}"] = False
                            st.rerun()

    # 2. INDEPENDENT SMART COMMENT QUEUE (POWERED BY SUPABASE)
    st.divider()
    st.write("### 💬 Independent Comment Queue (Cloud)")
    
    # FETCH PENDING COMMENTS FROM DATABASE
    try:
        res = supabase.table("comment_queue").select("*").eq("status", "pending").execute()
        cloud_comments = res.data
    except:
        cloud_comments = []

    if not cloud_comments:
        st.info("No scheduled comments found in the cloud.")
    else:
        for item in cloud_comments:
            cid = item['id']
            with st.container(border=True):
                c_col_info, c_col_btns = st.columns([4, 2])
                
                clv = datetime.fromtimestamp(item['scheduled_time']) + timedelta(hours=utc_offset)
                
                with c_col_info:
                    st.markdown(f"⏰ **Comment at:** `{clv.strftime('%I:%M %p - %b %d')}`")
                    st.caption(f"Parent Post ID: `{item['parent_post_id']}`")
                    st.markdown(f"📝 **Text:** {item['comment_text'][:50]}...")
                
                with c_col_btns:
                    sc_edit_btn = st.button("📝 Edit", key=f"sc_edit_btn_{cid}")
                    sc_del_btn = st.button("🗑️ Remove", key=f"sc_del_btn_{cid}", type="secondary")

                # --- DELETE COMMENT LOGIC ---
                if sc_del_btn:
                    supabase.table("comment_queue").delete().eq("id", cid).execute()
                    st.rerun()

                # --- EDIT COMMENT LOGIC ---
                if sc_edit_btn or st.session_state.get(f"active_sc_ed_{cid}"):
                    st.session_state[f"active_sc_ed_{cid}"] = True
                    with st.expander("📝 Edit Comment Content", expanded=True):
                        new_txt = st.text_area("Comment Text", value=item['comment_text'], key=f"q_ed_txt_{cid}")
                        
                        col_sc_save, col_sc_can = st.columns(2)
                        if col_sc_save.button("💾 Save Changes", key=f"sv_sc_{cid}", type="primary"):
                            supabase.table("comment_queue").update({"comment_text": new_txt}).eq("id", cid).execute()
                            st.success("Updated!")
                            st.session_state[f"active_sc_ed_{cid}"] = False
                            time.sleep(1)
                            st.rerun()
                            
                        if col_sc_can.button("✖️ Close", key=f"can_sc_{cid}"):
                            st.session_state[f"active_sc_ed_{cid}"] = False
                            st.rerun()

