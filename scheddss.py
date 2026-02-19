import streamlit as st
import requests
from datetime import datetime
import time

# --- 1. CONFIGURATION ---
CLIENT_ID = "910661605032071"
CLIENT_SECRET = "a57ba995d5178d5ee80c3debba225138"
REDIRECT_URI = "https://scheddss.streamlit.app/"

st.set_page_config(page_title="Scheddss Pro", page_icon="👟", layout="wide")

# Persistent storage for comments linked to scheduled posts
if "sched_comment_store" not in st.session_state:
    st.session_state.sched_comment_store = {}

# --- 2. PERSISTENT LOGIN ---
if "token" in st.query_params:
    st.session_state.access_token = st.query_params["token"]
elif "access_token" not in st.session_state:
    st.session_state.access_token = None

st.title("👟 Scheddss: Professional Suite")

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
        auth_url = f"https://www.facebook.com/v21.0/dialog/oauth?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=pages_show_list,pages_manage_posts,pages_read_engagement,public_profile"
        st.link_button("🔓 Log in with Facebook", auth_url, type="primary")
        st.stop()

# --- 4. DASHBOARD DATA ---
user_token = st.session_state.access_token
pages_res = requests.get(f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_token}").json()
pages_data = pages_res.get('data', [])

if not pages_data:
    st.error("No pages found.")
    st.stop()

page_map = {p['name']: (p['id'], p['access_token']) for p in pages_data}
with st.sidebar:
    selected_page_name = st.selectbox("Target Page", list(page_map.keys()))
    target_id, target_token = page_map[selected_page_name]

tab1, tab2, tab3 = st.tabs(["🚀 New Post", "💬 Smart Commenter", "📅 Scheduled Queue"])

# --- TAB 1: NEW POST (Captures Comments for Queue) ---
with tab1:
    st.subheader("Create Media Post")
    col1, col2 = st.columns(2)
    with col1:
        uploaded_files = st.file_uploader("Upload Files", accept_multiple_files=True)
        caption = st.text_area("Post Caption", height=150)
        
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
            file = uploaded_files[0]
            is_vid = "video" in file.type
            ep = f"https://graph-video.facebook.com/v21.0/{target_id}/videos" if is_vid else f"https://graph.facebook.com/v21.0/{target_id}/photos"
            payload = {'access_token': target_token, 'caption' if not is_vid else 'description': caption}
            
            if timing == "Schedule":
                payload.update({'published': 'false', 'scheduled_publish_time': int(pub_time.timestamp())})
            
            res = requests.post(ep, data=payload, files={'file': file.getvalue()}).json()
            if "id" in res:
                post_id = res['id']
                # Store comments in local queue if scheduled
                if timing == "Schedule":
                    st.session_state.sched_comment_store[post_id] = [c for c in st.session_state.new_comments if c.strip()]
                st.success(f"Post created! ID: {post_id}")
            else:
                st.error(str(res))

# --- TAB 3: SCHEDULED QUEUE (Posts AND Comments) ---
with tab3:
    st.subheader("Manage Upcoming Posts & Comments")
    q_res = requests.get(f"https://graph.facebook.com/v21.0/{target_id}/promotable_posts?is_published=false&fields=id,message,scheduled_publish_time,picture&access_token={target_token}").json()
    q_posts = q_res.get('data', [])

    if not q_posts:
        st.info("Nothing scheduled.")
    else:
        for p in q_posts:
            p_id = p['id']
            with st.container(border=True):
                c_main, c_side = st.columns([3, 1])
                with c_main:
                    st_time = datetime.fromtimestamp(p['scheduled_publish_time']).strftime('%Y-%m-%d %H:%M')
                    st.write(f"📅 **Live at:** `{st_time}`")
                    
                    # Edit Post Caption
                    new_msg = st.text_area("Edit Post Caption", value=p.get('message', ''), key=f"q_msg_{p_id}")
                    
                    # List & Edit Linked Comments
                    st.write("📌 **Linked Comments:**")
                    linked_comms = st.session_state.sched_comment_store.get(p_id, [])
                    for idx, c_text in enumerate(linked_comms):
                        linked_comms[idx] = st.text_input(f"Comment {idx+1}", value=c_text, key=f"q_comm_{p_id}_{idx}")
                    
                    st.session_state.sched_comment_store[p_id] = linked_comms

                    # Actions
                    b1, b2 = st.columns(2)
                    if b1.button("💾 Save All Changes", key=f"sv_{p_id}"):
                        requests.post(f"https://graph.facebook.com/v21.0/{p_id}", data={'message': new_msg, 'access_token': target_token})
                        st.success("Changes saved!")
                        st.rerun()
                    if b2.button("🗑️ Delete Everything", key=f"dl_{p_id}"):
                        requests.delete(f"https://graph.facebook.com/v21.0/{p_id}?access_token={target_token}")
                        if p_id in st.session_state.sched_comment_store:
                            del st.session_state.sched_comment_store[p_id]
                        st.rerun()
                with c_side:
                    if p.get('picture'): st.image(p['picture'], use_container_width=True)
