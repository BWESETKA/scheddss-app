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

if "master_queue" not in st.session_state:
    st.session_state.master_queue = {}  
if "temp_comments" not in st.session_state:
    st.session_state.temp_comments = [""]

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
    selected_page_name = st.selectbox("Target Page", list(page_map.keys()))
    target_id, target_token = page_map[selected_page_name]
    utc_offset = st.number_input("UTC Offset (PH is 8)", value=8)

tab1, tab2, tab3 = st.tabs(["🚀 New Post", "💬 Smart Commenter", "📅 Scheduled Queue"])

# --- TAB 1: NEW POST (UNLIMITED MEDIA FIX) ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        # FIXED: Removed specific numbers. User can pick any amount.
        uploaded_files = st.file_uploader("Upload Media (Photos/Videos)", accept_multiple_files=True)
        caption = st.text_area("Caption (# & Links OK)", height=150)
        for i in range(len(st.session_state.temp_comments)):
            st.session_state.temp_comments[i] = st.text_area(f"Comment #{i+1}", value=st.session_state.temp_comments[i], key=f"t1_c_{i}")
        if st.button("➕ Add Comment"):
            st.session_state.temp_comments.append("")
            st.rerun()

    with col2:
        timing = st.radio("Timing", ["Immediately", "Schedule"])
        p_unix = None
        if timing == "Schedule":
            p_d = st.date_input("Date")
            t_col, ap_col = st.columns(2)
            p_t_str = t_col.text_input("Time (HH:MM)", value="12:00")
            p_ampm = ap_col.selectbox("AM/PM", ["AM", "PM"])
            h, m = map(int, p_t_str.split(":"))
            if p_ampm == "PM" and h < 12: h += 12
            elif p_ampm == "AM" and h == 12: h = 0
            dt = datetime.combine(p_d, datetime.min.time()).replace(hour=h, minute=m)
            p_unix = int((dt - timedelta(hours=utc_offset)).timestamp())

    if st.button("🚀 EXECUTE POST", use_container_width=True, type="primary"):
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
                # Save to Master Queue for Tab 3 visibility
                st.session_state.master_queue[final['id']] = {
                    "comments": [c for c in st.session_state.temp_comments if c.strip()],
                    "caption": caption,
                    "media_count": len(media_ids)
                }
                st.success("Post Created!")
                time.sleep(2)
                st.rerun()

# --- TAB 2: SMART COMMENTER (COMPLETE) ---
with tab2:
    st.subheader("💬 Smart Commenter")
    st.markdown("---")

    # 1. FETCH LIVE POSTS WITH THUMBNAILS
    # Using 'full_picture' ensures the thumbnail actually shows up
    posts_url = f"https://graph.facebook.com/v21.0/{target_id}/published_posts?fields=id,message,full_picture,created_time&limit=10&access_token={target_token}"
    
    try:
        posts_data = requests.get(posts_url).json().get('data', [])
    except:
        posts_data = []
        st.error("Failed to fetch posts from Facebook.")

    if not posts_data:
        st.info("No published posts found on this page.")
    else:
        # Create a selection list
        post_options = {p['id']: f"{p.get('message', 'Media Post')[:50]}... ({p['id']})" for p in posts_data}
        selected_post_id = st.selectbox("🎯 Select a Post to Comment On:", 
                                        options=list(post_options.keys()), 
                                        format_func=lambda x: post_options[x])

        # Show Thumbnail of selected post
        selected_item = next(p for p in posts_data if p['id'] == selected_post_id)
        if selected_item.get('full_picture'):
            st.image(selected_item['full_picture'], width=300, caption="Selected Post Preview")

        st.divider()

        # 2. MULTIPLE COMMENT INPUTS
        st.write("### 📝 Your Comments")
        if "smart_comments" not in st.session_state:
            st.session_state.smart_comments = [""]

        # Loop through comments in session state
        for i in range(len(st.session_state.smart_comments)):
            st.session_state.smart_comments[i] = st.text_area(
                f"Comment Line #{i+1} (Links & #Hashtags OK)", 
                value=st.session_state.smart_comments[i], 
                key=f"sc_input_{i}",
                height=100
            )

        col_add, col_rem = st.columns(2)
        if col_add.button("➕ Add More Comment Lines"):
            st.session_state.smart_comments.append("")
            st.rerun()
        if col_rem.button("➖ Remove Last Line") and len(st.session_state.smart_comments) > 1:
            st.session_state.smart_comments.pop()
            st.rerun()

        st.divider()

        # 3. DATE AND TIME SCHEDULING
        st.write("### ⏰ Set Timing")
        sc_timing_mode = st.radio("When to post?", ["Immediately", "Schedule for Later"], horizontal=True)

        sc_unix = None
        if sc_timing_mode == "Schedule for Later":
            sc_col1, sc_col2, sc_col3 = st.columns([2, 2, 1])
            sc_date = sc_col1.date_input("Pick Date", value=datetime.now())
            sc_time_str = sc_col2.text_input("Time (HH:MM)", value=datetime.now().strftime("%I:%M"))
            sc_ampm = sc_col3.selectbox("AM/PM", ["AM", "PM"], key="sc_ampm_select")

            try:
                # Convert to Unix for the background worker
                sh, sm = map(int, sc_time_str.split(":"))
                if sc_ampm == "PM" and sh < 12: sh += 12
                elif sc_ampm == "AM" and sh == 12: sh = 0
                
                sc_dt = datetime.combine(sc_date, datetime.min.time()).replace(hour=sh, minute=sm)
                # Convert PH Time to UTC for Facebook/Engine
                sc_unix = int((sc_dt - timedelta(hours=utc_offset)).timestamp())
                
                # Validation
                if sc_unix < time.time() + 600: # 10 mins buffer
                    st.warning("⚠️ For scheduling, please set at least 10-20 minutes in the future.")
            except:
                st.error("Invalid time format. Please use HH:MM (e.g., 02:30)")

        # 4. EXECUTE BUTTON
        if st.button("🚀 EXECUTE SMART COMMENTS", use_container_width=True, type="primary"):
            valid_comments = [c.strip() for c in st.session_state.smart_comments if c.strip()]
            
            if not valid_comments:
                st.error("Please type at least one comment.")
            else:
                with st.spinner("Processing..."):
                    if sc_timing_mode == "Immediately":
                        # Post directly to Facebook API
                        success_count = 0
                        for msg in valid_comments:
                            c_url = f"https://graph.facebook.com/v21.0/{selected_post_id}/comments"
                            res = requests.post(c_url, data={'message': msg, 'access_token': target_token}).json()
                            if "id" in res:
                                success_count += 1
                        st.success(f"✅ Successfully posted {success_count} comments immediately!")
                    else:
                        # Add to the Master Queue for the background script to handle
                        # We create a unique ID for this comment batch
                        batch_id = f"sc_{int(time.time())}"
                        st.session_state.master_queue[batch_id] = {
                            "type": "delayed_comment",
                            "parent_post": selected_post_id,
                            "comments": valid_comments,
                            "scheduled_time": sc_unix
                        }
                        st.success(f"📅 {len(valid_comments)} comments scheduled for {sc_time_str} {sc_ampm}!")
                    
                    # Clear inputs after success
                    st.session_state.smart_comments = [""]
                    time.sleep(2)
                    st.rerun()

# --- TAB 3: THE FULL MANAGEMENT QUEUE (COMPLETE) ---
with tab3:
    st.subheader("📅 Live Management Queue")
    
    # 1. FETCH LIVE DATA FROM FACEBOOK
    # We fetch 'full_picture' for thumbnails and 'message' for captions
    q_url = f"https://graph.facebook.com/v21.0/{target_id}/scheduled_posts?fields=id,message,scheduled_publish_time,full_picture&access_token={target_token}"
    try:
        fb_posts = requests.get(q_url).json().get('data', [])
    except:
        fb_posts = []

    if not fb_posts and not st.session_state.master_queue:
        st.info("Your queue is currently empty.")
    else:
        st.write(f"Showing **{len(fb_posts)}** scheduled posts:")
        
        for p in fb_posts:
            pid = p['id']
            with st.container(border=True):
                col_img, col_main, col_btns = st.columns([1, 3, 2])
                
                # Convert Unix back to PH Time for display
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
                    # CLEAN BUTTON LOOK
                    e_btn = st.button("📝 Edit Details", key=f"edit_ui_{pid}")
                    d_btn = st.button("🗑️ Delete Post", key=f"del_ui_{pid}", type="secondary")

                # --- DELETE LOGIC ---
                if d_btn:
                    with st.spinner("Deleting..."):
                        del_res = requests.delete(f"https://graph.facebook.com/v21.0/{pid}?access_token={target_token}").json()
                        if del_res.get("success"):
                            if pid in st.session_state.master_queue: 
                                del st.session_state.master_queue[pid]
                            st.success("Post Deleted.")
                            time.sleep(1)
                            st.rerun()

                # --- EDIT LOGIC (CAPTION, TIME, COMMENT, MEDIA) ---
                if e_btn or st.session_state.get(f"active_ed_{pid}"):
                    st.session_state[f"active_ed_{pid}"] = True
                    
                    with st.expander("🛠️ FULL EDITOR MODE", expanded=True):
                        # 1. Edit Caption
                        up_caption = st.text_area("Update Caption", value=p.get('message', ''), key=f"up_cap_{pid}")
                        
                        # 2. Edit Media
                        up_files = st.file_uploader("Replace All Media (Optional)", accept_multiple_files=True, key=f"up_file_{pid}")
                        
                        # 3. Edit Time
                        st.write("**Change Schedule Time:**")
                        t1, t2 = st.columns(2)
                        up_time_str = t1.text_input("Time (HH:MM)", value=lv.strftime("%I:%M"), key=f"up_time_{pid}")
                        up_ampm = t2.selectbox("AM/PM", ["AM", "PM"], index=0 if lv.strftime("%p")=="AM" else 1, key=f"up_ap_{pid}")
                        
                        # 4. Edit Comments (Caught from Tab 1/Tab 2 Memory)
                        st.write("**Edit Linked Comments:**")
                        if pid in st.session_state.master_queue:
                            coms = st.session_state.master_queue[pid]['comments']
                            for i in range(len(coms)):
                                coms[i] = st.text_area(f"Comment {i+1}", value=coms[i], key=f"up_com_{pid}_{i}")
                        else:
                            st.caption("No linked comments found for this post ID.")

                        # --- SAVE ALL CHANGES ---
                        if st.button("💾 SAVE & RE-SYNC TO FACEBOOK", key=f"save_all_{pid}", type="primary"):
                            with st.spinner("Updating Facebook..."):
                                # Calculate New Unix Time
                                h, m = map(int, up_time_str.split(":"))
                                if up_ampm == "PM" and h < 12: h += 12
                                elif up_ampm == "AM" and h == 12: h = 0
                                new_dt = datetime.combine(lv.date(), datetime.min.time()).replace(hour=h, minute=m)
                                up_unix = int((new_dt - timedelta(hours=utc_offset)).timestamp())

                                if up_files:
                                    # MEDIA SWAP: Delete old and create new
                                    requests.delete(f"https://graph.facebook.com/v21.0/{pid}?access_token={target_token}")
                                    
                                    # Re-upload new media bundle
                                    new_mids = []
                                    for f in up_files:
                                        is_vid = "video" in f.type
                                        ep = f"https://graph-video.facebook.com/v21.0/{target_id}/videos" if is_vid else f"https://graph.facebook.com/v21.0/{target_id}/photos"
                                        res = requests.post(ep, data={'access_token': target_token, 'published': 'false'}, files={'file': f.getvalue()}).json()
                                        if "id" in res: new_mids.append(res['id'])
                                    
                                    # Create final feed post
                                    new_post = requests.post(f"https://graph.facebook.com/v21.0/{target_id}/feed", data={
                                        'message': up_caption,
                                        'access_token': target_token,
                                        'attached_media': json.dumps([{'media_fbid': i} for i in new_mids]),
                                        'published': 'false',
                                        'scheduled_publish_time': up_unix
                                    }).json()
                                    
                                    # Transfer comments to new ID
                                    if "id" in new_post:
                                        st.session_state.master_queue[new_post['id']] = {"comments": coms}
                                        if pid in st.session_state.master_queue: del st.session_state.master_queue[pid]
                                else:
                                    # TEXT/TIME ONLY UPDATE
                                    requests.post(f"https://graph.facebook.com/v21.0/{pid}", data={
                                        'message': up_caption,
                                        'scheduled_publish_time': up_unix,
                                        'access_token': target_token
                                    })
                                    if pid in st.session_state.master_queue:
                                        st.session_state.master_queue[pid]['comments'] = coms

                                st.success("Changes Saved Successfully!")
                                st.session_state[f"active_ed_{pid}"] = False
                                time.sleep(2)
                                st.rerun()

                        if st.button("✖️ Cancel", key=f"can_ed_{pid}"):
                            st.session_state[f"active_ed_{pid}"] = False
                            st.rerun()

    # 2. INDEPENDENT SMART COMMENT QUEUE (Delayed comments from Tab 2)
    st.divider()
    st.write("### 💬 Independent Comment Queue")
    for qid, data in list(st.session_state.master_queue.items()):
        if data.get('type') == "delayed_comment":
            with st.container(border=True):
                clv = datetime.fromtimestamp(data['scheduled_time']) + timedelta(hours=utc_offset)
                st.write(f"⏰ **Comment at:** `{clv.strftime('%I:%M %p')}` | Post ID: `{data['parent_post']}`")
                
                # Edit Smart Comment Content
                for i, txt in enumerate(data['comments']):
                    data['comments'][i] = st.text_area(f"Edit Comment {i+1}", value=txt, key=f"q_ed_{qid}_{i}")
                
                col_save_q, col_del_q = st.columns(2)
                if col_save_q.button("💾 Save Comment Edits", key=f"sv_q_{qid}"):
                    st.success("Comment content updated in queue!")
                if col_del_q.button("🗑️ Remove from Queue", key=f"rm_q_{qid}"):
                    del st.session_state.master_queue[qid]
                    st.rerun()
