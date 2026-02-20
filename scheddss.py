import streamlit as st
import requests
from datetime import datetime, timedelta
import re

# --- 1. CONFIG & SESSION ---
CLIENT_ID = "910661605032071"
CLIENT_SECRET = "a57ba995d5178d5ee80c3debba225138"
REDIRECT_URI = "https://scheddss.streamlit.app/"

st.set_page_config(page_title="Scheddss Pro", page_icon="👟", layout="wide")

# Persistent memory so data doesn't vanish when switching tabs
if "master_queue" not in st.session_state:
    st.session_state.master_queue = {}
if "temp_comments" not in st.session_state:
    st.session_state.temp_comments = [""]

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
        caption = st.text_area("Post Caption (#Hashtags & Links OK)", height=150)
        
        st.write("### 📝 Auto-Comments")
        for i in range(len(st.session_state.temp_comments)):
            st.session_state.temp_comments[i] = st.text_area(f"Comment #{i+1}", value=st.session_state.temp_comments[i], key=f"t1_c_{i}")
        
        if st.button("➕ Add Line"):
            st.session_state.temp_comments.append("")
            st.rerun()

    with col2:
        timing = st.radio("Timing", ["Immediately", "Schedule"])
        unix_time = None
        if timing == "Schedule":
            d = st.date_input("Date")
            t_col, ap_col = st.columns([2, 1])
            t_str = t_col.text_input("Time (HH:MM)", value=datetime.now().strftime("%I:%M"))
            ampm = ap_col.selectbox("AM/PM", ["AM", "PM"])
            
            try:
                h, m = map(int, t_str.split(":"))
                if ampm == "PM" and h < 12: h += 12
                if ampm == "AM" and h == 12: h = 0
                local_dt = datetime.combine(d, datetime.min.time()).replace(hour=h, minute=m)
                unix_time = int((local_dt - timedelta(hours=utc_offset)).timestamp())
                st.success(f"✅ Ready for {t_str} {ampm}")
            except: st.error("Use 09:30 format")

    if st.button("🚀 EXECUTE", use_container_width=True):
        if uploaded_files:
            file = uploaded_files[0]
            is_vid = "video" in file.type
            ep = f"https://graph-video.facebook.com/v21.0/{target_id}/videos" if is_vid else f"https://graph.facebook.com/v21.0/{target_id}/photos"
            payload = {'access_token': target_token, 'caption' if not is_vid else 'description': caption}
            if timing == "Schedule": payload.update({'published': 'false', 'scheduled_publish_time': unix_time})
            
            res = requests.post(ep, data=payload, files={'file': file.getvalue()}).json()
            if "id" in res:
                st.session_state.master_queue[res['id']] = [c for c in st.session_state.temp_comments if c.strip()]
                st.success("Post set!")
                st.session_state.temp_comments = [""]
            else: st.error(str(res))

# --- TAB 2: SMART COMMENTER (FIXED) ---
with tab2:
    st.subheader("Comment on Published Posts")
    # Fetch actual posts so the section isn't empty!
    posts_url = f"https://graph.facebook.com/v21.0/{target_id}/published_posts?fields=id,message,picture&limit=10&access_token={target_token}"
    posts_data = requests.get(posts_url).json().get('data', [])

    if not posts_data:
        st.info("No published posts found on this page.")
    else:
        post_options = {p['id']: f"{p.get('message', 'No text')[:50]}..." for p in posts_data}
        selected_post_id = st.selectbox("Select Post to Comment On:", options=list(post_options.keys()), format_func=lambda x: post_options[x])
        
        # Show image preview of selected post
        selected_post = next(p for p in posts_data if p['id'] == selected_post_id)
        if selected_post.get('picture'): st.image(selected_post['picture'], width=150)

        comment_text = st.text_area("Type your comment (Links & #Hashtags work!)", placeholder="Great deal! Check #Sneakers here: https://link.com")
        
        if st.button("💬 Post Comment Now"):
            res = requests.post(f"https://graph.facebook.com/v21.0/{selected_post_id}/comments", data={'message': comment_text, 'access_token': target_token})
            if res.status_code == 200: st.success("Comment posted!")
            else: st.error(res.text)

# --- TAB 3: SCHEDULED QUEUE ---
with tab3:
    st.subheader("Manage Upcoming Posts")
    q_url = f"https://graph.facebook.com/v21.0/{target_id}/promotable_posts?is_published=false&fields=id,message,scheduled_publish_time,picture&access_token={target_token}"
    q_data = requests.get(q_url).json().get('data', [])

    if not q_data:
        st.info("Queue is empty.")
    else:
        for p in q_data:
            pid = p['id']
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    local_view = datetime.fromtimestamp(p['scheduled_publish_time']) + timedelta(hours=utc_offset)
                    st.markdown(f"🗓️ **Live at:** `{local_view.strftime('%Y-%m-%d %I:%M %p')}`")
                    new_cap = st.text_area("Caption", value=p.get('message', ''), key=f"q_cap_{pid}")
                    
                    if pid in st.session_state.master_queue:
                        st.write("💬 **Comments:**")
                        for idx, txt in enumerate(st.session_state.master_queue[pid]):
                            st.session_state.master_queue[pid][idx] = st.text_area(f"C#{idx+1}", value=txt, key=f"q_c_{pid}_{idx}")
                    
                    if st.button("💾 Save All", key=f"sv_{pid}"):
                        requests.post(f"https://graph.facebook.com/v21.0/{pid}", data={'message': new_cap, 'access_token': target_token})
                        st.success("Saved!")
                    if st.button("🗑️ Delete", key=f"del_{pid}"):
                        requests.delete(f"https://graph.facebook.com/v21.0/{pid}?access_token={target_token}")
                        st.rerun()
                with c2:
                    if p.get('picture'): st.image(p['picture'])
