import streamlit as st
import pandas as pd
import requests
from datetime import datetime
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
PERMANENT_TOKEN = "EAAM8Pe16gIcBQ0xi5pZAxKsZAONNzezJIuMmMqCrFjoE99rkyzHFeX3fGNAwiZBTUD6NZAL4pHcSutrUbZBgqHdojDjTLna9rlBP7xicZAWoBJaQaQ1NRBymQ9F7ggoSAOhFbgcZB9nHZCZBPW6HjGM2FwLOyCBm8TDAUTKPdTrfAR5fxn3b9xNiMLreoQqoU"

# --- SUPABASE CONFIG ---
SUPABASE_URL = "https://elpwqqvgrdovocvkzgyl.supabase.co"
SUPABASE_KEY = "sb_publishable_6FBWrUK1dLH-AUGF7DMjRA_8Wyl3dRE"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Scheddss Pro", page_icon="👟", layout="wide")

# Use the Permanent Token for all requests
PERMANENT_TOKEN = PERMANENT_TOKEN

# --- PERSISTENT CACHE TRICK ---
@st.cache_resource
def get_persistent_store():
    # This stays in server memory even if you refresh the browser
    return {"access_token": None}

token_store = get_persistent_store()

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

# --- AUTH LOGIC (LONG-LIVED & PERSISTENT) ---

# Check if we already have a token saved in the persistent cache
if token_store["access_token"] and "access_token" not in st.session_state:
    st.session_state.access_token = token_store["access_token"]

if "access_token" not in st.session_state:
    if "code" in st.query_params:
        auth_code = st.query_params["code"]
        
        # 1. Get Short-Lived Token
        token_url = "https://graph.facebook.com/v21.0/oauth/access_token"
        token_params = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "code": auth_code,
        }
        
        res = requests.get(token_url, params=token_params).json()
        
        if "access_token" in res:
            short_token = res["access_token"]
            
            # 2. Upgrade to LONG-LIVED Token (60 Days)
            long_url = "https://graph.facebook.com/v21.0/oauth/access_token"
            long_params = {
                "grant_type": "fb_exchange_token",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "fb_exchange_token": short_token
            }
            long_res = requests.get(long_url, params=long_params).json()
            final_token = long_res.get("access_token", short_token)
            
            # Store in both places
            st.session_state.access_token = final_token
            token_store["access_token"] = final_token
            
            st.query_params.clear() 
            st.rerun()
        else:
            st.query_params.clear()
            st.warning("Session expired or login failed. Please try again.")
            st.stop()
    else:
        st.title("👟 Scheddss: Login")
        # ADDED 'pages_manage_engagement' to the scope below
        scope_list = [
            "pages_show_list",
            "pages_manage_posts",
            "pages_read_engagement",
            "pages_manage_engagement",
            "public_profile"
        ]
        scope_str = ",".join(scope_list)
        
        auth_url = (
            f"https://www.facebook.com/v21.0/dialog/oauth?"
            f"client_id={CLIENT_ID}&"
            f"redirect_uri={REDIRECT_URI}&"
            f"response_type=code&"
            f"scope={scope_str}"
        )
        
        st.info("Please connect your Facebook account. Ensure you grant all permissions for comments to work.")
        st.link_button("🔓 Log in with Facebook", auth_url, type="primary")
        st.stop()
        
# --- APP START ---
user_token = st.session_state.access_token
pages_res = requests.get(f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_token}").json()

# Token Verification: If FB says the token is dead, clear the cache and force login
if "error" in pages_res:
    token_store["access_token"] = None
    del st.session_state.access_token
    st.rerun()

page_map = {p['name']: (p['id'], p['access_token']) for p in pages_res.get('data', [])}

with st.sidebar:
    st.header("⚙️ Settings")
    if page_map:
        selected_page_name = st.selectbox("Target Page", list(page_map.keys()))
        target_id, PERMANENT_TOKEN = page_map[selected_page_name]
    else:
        st.error("No pages found.")
        if st.button("🔄 Re-login"):
            token_store["access_token"] = None
            del st.session_state.access_token
            st.rerun()
        st.stop()
    utc_offset = st.number_input("UTC Offset (PH is 8)", value=8)

#TABS
tab1, tab2, tab3, tab4 = st.tabs(["🚀 New Post", "💬 Smart Commenter", "📅 Scheduled Queue", "📂 Bulk Scheduler"])
        
# --- TAB 1: NEW POST (DIRECT & CLOUD SYNC) ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        uploaded_files = st.file_uploader(
            "Upload Media (Photos/Videos)", 
            accept_multiple_files=True, 
            key=f"uploader_{st.session_state.reset_key}"
        )
        
        caption = st.text_area("Caption (# & Links OK)", height=150, key=f"cap_{st.session_state.reset_key}")
        
        st.write("---")
        st.subheader("💬 Comments")
        for i in range(len(st.session_state.temp_comments)):
            st.session_state.temp_comments[i] = st.text_area(
                f"Comment #{i+1}", 
                value=st.session_state.temp_comments[i], 
                key=f"t1_c_{i}_{st.session_state.reset_key}"
            )
        
        if st.button("➕ Add Another Comment", key=f"add_t1_{st.session_state.reset_key}"):
            st.session_state.temp_comments.append("")
            st.rerun()

    with col2:
        st.subheader("⏲️ Scheduling")
        timing = st.radio("When to post?", ["Immediately", "Schedule"], key=f"time_t1_{st.session_state.reset_key}")
        
        p_unix = None
        if timing == "Schedule":
            p_d = st.date_input("Select Date", key=f"date_t1_{st.session_state.reset_key}")
            t_col, ap_col = st.columns(2)
            p_t_str = t_col.text_input("Time (HH:MM)", value="12:00", key=f"t_str_t1_{st.session_state.reset_key}")
            p_ampm = ap_col.selectbox("AM/PM", ["AM", "PM"], key=f"ap_t1_{st.session_state.reset_key}")
            
            try:
                h, m = map(int, p_t_str.split(":"))
                if p_ampm == "PM" and h < 12: h += 12
                elif p_ampm == "AM" and h == 12: h = 0
                dt = datetime.combine(p_d, datetime.min.time()).replace(hour=h, minute=m)
                p_unix = int((dt - timedelta(hours=utc_offset)).timestamp())
                st.caption(f"Target Unix Time: {p_unix}")
            except:
                st.error("Invalid time format. Use HH:MM")

    st.write("---")
    if st.button("🚀 EXECUTE POST", use_container_width=True, type="primary"):
        if not uploaded_files:
            st.error("Please upload media first.")
        elif timing == "Schedule" and p_unix is None:
            st.error("Please fix the schedule time first.")
        else:
            with st.spinner("📤 Communicating with Facebook..."):
                try:
                    # 1. UPLOAD MEDIA
                    media_ids = []
                    for f in uploaded_files:
                        is_vid = "video" in f.type
                        ep = f"https://graph-video.facebook.com/v21.0/{target_id}/videos" if is_vid else f"https://graph.facebook.com/v21.0/{target_id}/photos"
                        
                        res = requests.post(
                            ep, 
                            data={'access_token': PERMANENT_TOKEN, 'published': 'false'}, 
                            files={'file': f.getvalue()}
                        ).json()
                        
                        if "id" in res:
                            media_ids.append(res['id'])
                        else:
                            st.error(f"Media Upload Failed: {res.get('error', {}).get('message')}")
                            st.stop()

                    # 2. CREATE THE FEED POST
                    post_payload = {
                        'message': caption,
                        'access_token': PERMANENT_TOKEN,
                        'attached_media': json.dumps([{'media_fbid': i} for i in media_ids])
                    }
                    
                    if timing == "Schedule":
                        post_payload.update({'published': 'false', 'scheduled_publish_time': p_unix})
                    
                    final_post = requests.post(
                        f"https://graph.facebook.com/v21.0/{target_id}/feed", 
                        data=post_payload
                    ).json()

                    if "id" in final_post:
                        post_id = final_post['id']
                        valid_comments = [c for c in st.session_state.temp_comments if c.strip()]
                        
                        # 3. HANDLE COMMENTS
                        if valid_comments:
                            if timing == "Immediately":
                                for msg in valid_comments:
                                    # Small delay to prevent FB spam trigger
                                    time.sleep(1) 
                                    c_res = requests.post(
                                        f"https://graph.facebook.com/v21.0/{post_id}/comments",
                                        data={'message': msg, 'access_token': PERMANENT_TOKEN}
                                    ).json()
                                    
                                    if "error" in c_res:
                                        st.error(f"Comment failed: {c_res['error']['message']}")
                                    else:
                                        st.toast(f"Comment Posted: {msg[:20]}...")
                                st.success("Post & Immediate comments processed!")
                            else:
                                # SCHEDULED: Send to Supabase
                                try:
                                    for msg in valid_comments:
                                        supabase.table("comment_queue").insert({
                                            "parent_post_id": post_id,
                                            "comment_text": msg,
                                            "scheduled_time": p_unix,
                                            "page_access_token": PERMANENT_TOKEN,
                                            "status": "pending"
                                        }).execute()
                                    st.success(f"Scheduled! Post & {len(valid_comments)} comments queued.")
                                except Exception as e:
                                    st.error(f"Supabase Error: {e}")
                        else:
                            st.success("Post LIVE (No comments).")

                        # Refresh UI
                        st.session_state.temp_comments = [""]
                        st.session_state.reset_key += 1
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error(f"FB Post Error: {final_post.get('error', {}).get('message')}")

                except Exception as e:
                    st.error(f"Critical System Error: {e}")

# ------ TAB 2-------
with tab2:
    st.subheader("💬 Smart Commenter")
    
    # CSS: Tall static cards, no internal scroll
    st.markdown("""
        <style>
        [data-testid="stVerticalBlock"] { gap: 0.5rem; }
        .stContainer > div > div { min-height: 350px !important; }
        </style>
        """, unsafe_allow_html=True)

    # 1. FETCH POSTS (FIXED: Added page-specific key)
    # We store posts in a dictionary keyed by the page ID
    if "sc_posts_cache" not in st.session_state:
        st.session_state.sc_posts_cache = {}

    if target_id not in st.session_state.sc_posts_cache:
        try:
            posts_url = f"https://graph.facebook.com/v21.0/{target_id}/published_posts?fields=id,message,full_picture,created_time&limit=50&access_token={PERMANENT_TOKEN}"
            response = requests.get(posts_url).json()
            # Store posts specifically for this page ID
            st.session_state.sc_posts_cache[target_id] = response.get('data', [])
        except:
            st.session_state.sc_posts_cache[target_id] = []

    # Use the specific page's data
    current_posts = st.session_state.sc_posts_cache[target_id]

    # 2. CSV UPLOADER
    st.write("---")
    st.markdown(f"### 📍 Current Page: <span style='color:red'>{selected_page_name}</span>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("📂 Upload Comment CSV (Template Library)", type="csv")
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        st.session_state.comment_templates = dict(zip(df['CATEGORY'], df['POST DESCRIPTION']))
    
    # 3. GRID RENDER
    if "selected_posts" not in st.session_state: st.session_state.selected_posts = {}
    
    for row in range(3):
        cols = st.columns(6, gap="small")
        for col_idx in range(6):
            idx = (row * 6) + col_idx
            # FIXED: Used current_posts instead of the missing st.session_state.sc_posts
            if idx < len(current_posts):
                post = current_posts[idx]
                with cols[col_idx]:
                    with st.container(border=True):
                        if post.get('full_picture'): st.image(post['full_picture'], use_container_width=True)
                        st.write(f"**{post.get('message', 'Media')[:15]}...**")
                        
                        raw_time = post.get('created_time', '')
                        if raw_time:
                            dt = datetime.strptime(raw_time, "%Y-%m-%dT%H:%M:%S+0000")
                            st.caption(dt.strftime("%Y-%m-%d: %I:%M %p"))
                        
                        is_checked = st.checkbox("Select", key=f"sel_{post['id']}", 
                                                 value=post['id'] in st.session_state.selected_posts)
                        if is_checked: st.session_state.selected_posts[post['id']] = post
                        elif post['id'] in st.session_state.selected_posts: del st.session_state.selected_posts[post['id']]

    st.markdown("---")
    
    # 4. COMMENT CONFIGURATION
    if st.session_state.selected_posts:
        st.write("### 📝 Configure Comments")
        if "results" not in st.session_state: st.session_state.results = []
        if "refresh_key" not in st.session_state: st.session_state.refresh_key = 0

        for post_id, post in st.session_state.selected_posts.items():
            raw_time = post.get('created_time', '')
            dt = datetime.strptime(raw_time, "%Y-%m-%dT%H:%M:%S+0000")
            display_time = dt.strftime("%Y-%m-%d: %I:%M %p")
            
            st.markdown(f"**Post:** `{post.get('message', 'Media Post')[:40]}` | *{display_time}*")
            
            if f"comm_{post_id}" not in st.session_state: st.session_state[f"comm_{post_id}"] = [""]
            
            def update_comment_callback(pid):
                selected_cat = st.session_state[f"temp_sel_{pid}"]
                if selected_cat != "-- Select Category --":
                    st.session_state[f"comm_{pid}"] = [st.session_state.comment_templates[selected_cat]]
                    st.session_state.refresh_key += 1
            
            if "comment_templates" in st.session_state:
                st.selectbox(f"Smart Fill (Category)", ["-- Select Category --"] + list(st.session_state.comment_templates.keys()), 
                             key=f"temp_sel_{post_id}", on_change=update_comment_callback, args=(post_id,))
            
            for i, val in enumerate(st.session_state[f"comm_{post_id}"]):
                st.session_state[f"comm_{post_id}"][i] = st.text_area(f"Line #{i+1}", value=val, key=f"area_{post_id}_{i}_{st.session_state.refresh_key}")
            
            if st.button("➕ Add Line", key=f"add_{post_id}"):
                st.session_state[f"comm_{post_id}"].append(""); st.rerun()

        # 5. EXECUTION & STATUS TRACKING
        if st.button("🚀 GO NOW", type="primary"):
            st.session_state.results = []
            for post_id in st.session_state.selected_posts:
                for msg in st.session_state.get(f"comm_{post_id}", []):
                    if msg.strip():
                        res = requests.post(f"https://graph.facebook.com/v21.0/{post_id}/comments", 
                                            data={'message': msg, 'access_token': PERMANENT_TOKEN})
                        status = "✅ Success" if res.status_code == 200 else f"❌ Failed ({res.status_code})"
                        st.session_state.results.append(f"Post {post_id[:5]}: {status}")
            st.rerun()

        for r in st.session_state.results:
            st.write(r)
            
# --- TAB 3: THE FULL MANAGEMENT QUEUE (COMPLETE) ---
with tab3:
    st.subheader("📅 Live Management Queue")
    
    # 1. FETCH LIVE DATA FROM FACEBOOK (FOR POSTS)
    q_url = f"https://graph.facebook.com/v21.0/{target_id}/scheduled_posts?fields=id,message,scheduled_publish_time,full_picture&access_token={PERMANENT_TOKEN}"
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
                        del_res = requests.delete(f"https://graph.facebook.com/v21.0/{pid}?access_token={PERMANENT_TOKEN}").json()
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
                                        requests.delete(f"https://graph.facebook.com/v21.0/{pid}?access_token={PERMANENT_TOKEN}")
                                        new_mids = []
                                        for f in up_files:
                                            is_vid = "video" in f.type
                                            ep = f"https://graph-video.facebook.com/v21.0/{target_id}/videos" if is_vid else f"https://graph.facebook.com/v21.0/{target_id}/photos"
                                            res = requests.post(ep, data={'access_token': PERMANENT_TOKEN, 'published': 'false'}, files={'file': f.getvalue()}).json()
                                            if "id" in res: new_mids.append(res['id'])
                                        
                                        requests.post(f"https://graph.facebook.com/v21.0/{target_id}/feed", data={
                                            'message': up_caption,
                                            'access_token': PERMANENT_TOKEN,
                                            'attached_media': json.dumps([{'media_fbid': i} for i in new_mids]),
                                            'published': 'false',
                                            'scheduled_publish_time': up_unix
                                        })
                                    else:
                                        # Just update caption/time on existing post
                                        requests.post(f"https://graph.facebook.com/v21.0/{pid}", data={
                                            'message': up_caption,
                                            'scheduled_publish_time': up_unix,
                                            'access_token': PERMANENT_TOKEN
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



# --- TAB 4: BULK CSV SCHEDULER (RESUMABLE UPLOAD FLOW) ---
with tab4:
    st.markdown(f"### 📍 Current Page: <span style='color:red'>{selected_page_name}</span>", unsafe_allow_html=True)
    st.subheader("📂 Bulk CSV Asset Manager")
    
    selected_type = st.selectbox("Select Post Type (Required):", ["Choose Content Type...", "Reel", "Standard Post"])
    is_ready = selected_type != "Choose Content Type..."
    
    uploaded_videos = st.file_uploader("Select your videos:", accept_multiple_files=True)

    if uploaded_videos:
        st.success(f"You have uploaded **{len(uploaded_videos)}** video file(s).")
        
    col_c, col_d = st.columns(2)
    map_csv = col_c.file_uploader("Upload: producedvidmapping.csv", type=['csv'])
    cap_csv = col_d.file_uploader("Upload: postcaption.csv", type=['csv'])

    if uploaded_videos and map_csv and cap_csv:
        df_map = pd.read_csv(map_csv)
        df_cap = pd.read_csv(cap_csv)
        master_df = pd.merge(df_map, df_cap, on='CATEGORY', how='left')
        
        # --- NEW: FILE MATCHING LOGIC ---
        # Check if the file name exists in the uploaded list
        uploaded_names = [f.name for f in uploaded_videos]
        master_df['Found'] = master_df['FILE NAME'].apply(lambda x: "✅ Found" if str(x).strip() in uploaded_names else "❌ Missing")
        
        # Reorder: Move 'Found' to the very first column
        cols = ['Found'] + [c for c in master_df.columns if c != 'Found']
        master_df = master_df[cols]
        
        # Add selection checkbox as the second column
        master_df.insert(1, 'Select', False)
        
        # Display table
        edited_df = st.data_editor(master_df, hide_index=True, use_container_width=True)

        if st.button("🚀 GO NOW: Queue Selected Files", type="primary", disabled=not is_ready):
            results = []
            selected_rows = edited_df[edited_df['Select'] == True]
            
            if selected_rows.empty:
                st.warning("Please select at least one row.")
            else:
                progress_bar = st.progress(0)
                asset_type = 'REEL' if selected_type == "Reel" else 'POST'
                
                for i, (_, row) in enumerate(selected_rows.iterrows()):
                    file_obj = next((f for f in uploaded_videos if f.name == str(row['FILE NAME']).strip()), None)
                    if not file_obj:
                        results.append({"File": row['FILE NAME'], "Status": "❌ Missing file"})
                        continue
                    
                    try:
                        # 1. INITIATE
                        init_res = requests.post(
                            f"https://graph-video.facebook.com/v21.0/{target_id}/videos",
                            data={'access_token': PERMANENT_TOKEN, 'upload_phase': 'start', 'file_size': file_obj.size}
                        ).json()
                        session_id = init_res['upload_session_id']
                        
                        # 2. TRANSFER
                        requests.post(
                            f"https://graph-video.facebook.com/v21.0/{target_id}/videos",
                            data={'access_token': PERMANENT_TOKEN, 'upload_phase': 'transfer', 'start_offset': 0, 'upload_session_id': session_id},
                            files={'video_file_chunk': file_obj.getvalue()}
                        )
                        
                        # 3. FINISH (POSITIONAL COLUMN PARSING - IGNORES HEADER NAME)
                        raw_date_val = str(row.iloc[2]) # Grabs 3rd column
                        raw_date_str = raw_date_val.replace("-", "/").replace(":", " ", 1).upper().strip()
                        local_dt = pd.to_datetime(raw_date_str, dayfirst=True)
                        utc_timestamp = int((local_dt - timedelta(hours=8)).timestamp())
                        
                        final_res = requests.post(
                            f"https://graph-video.facebook.com/v21.0/{target_id}/videos",
                            data={
                                'access_token': PERMANENT_TOKEN, 
                                'upload_phase': 'finish', 
                                'upload_session_id': session_id,
                                'description': row['POST DESCRIPTION'],
                                'scheduled_publish_time': utc_timestamp,
                                'published': False,
                                'video_asset_type': asset_type
                            }
                        ).json()
                        
                        results.append({"File": row['FILE NAME'], "Status": "✅ Success"})
                        time.sleep(3) # Anti-bot delay
                            
                    except Exception as e:
                        results.append({"File": row['FILE NAME'], "Status": f"❌ Error: {str(e)}"})
                    progress_bar.progress((i + 1) / len(selected_rows))
                st.table(pd.DataFrame(results))








































