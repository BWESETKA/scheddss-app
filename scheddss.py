import streamlit as st
import requests

# --- 1. CONFIGURATION ---
CLIENT_ID = "910661605032071"
CLIENT_SECRET = "a57ba995d5178d5ee80c3debba225138"
REDIRECT_URI = "https://scheddss.streamlit.app/"

st.set_page_config(page_title="Scheddss Universal", page_icon="👟", layout="wide")

# --- 2. SESSION STATE ---
if "access_token" not in st.session_state:
    st.session_state.access_token = None

st.title("👟 Scheddss: Universal Uploader")

# --- 3. THE TOKEN UPGRADER (The "Secret Sauce") ---
def get_long_lived_token(short_token):
    """Swaps a 2-hour token for a 60-day token"""
    url = "https://graph.facebook.com/v21.0/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "fb_exchange_token": short_token
    }
    try:
        response = requests.get(url, params=params).json()
        return response.get("access_token")
    except:
        return None

# --- 4. AUTHENTICATION LOGIC ---
if st.session_state.access_token is None:
    auth_url = (
        f"https://www.facebook.com/v21.0/dialog/oauth?"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&"
        f"response_type=code&"
        f"scope=pages_show_list,pages_manage_posts,pages_read_engagement,public_profile"
    )

    st.write("### 🔒 System Locked")
    st.info("Please connect your Facebook account to manage your shoe pages.")
    
    # Official Link Button (Guaranteed Clickable)
    st.link_button("🔓 Log in with Facebook", auth_url, type="primary", use_container_width=True)

    # Handle the return from Facebook
    if "code" in st.query_params:
        code = st.query_params["code"]
        
        # Step A: Get the Initial Token
        token_url = "https://graph.facebook.com/v21.0/oauth/access_token"
        params = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "code": code
        }
        
        res = requests.get(token_url, params=params).json()
        short_token = res.get("access_token")

        if short_token:
            # Step B: AUTO-UPGRADE to 60-day token
            long_token = get_long_lived_token(short_token)
            st.session_state.access_token = long_token if long_token else short_token
            st.query_params.clear()
            st.rerun()
        else:
            st.error(f"Login Error: {res.get('error', {}).get('message', 'Unknown error')}")

else:
    # --- 5. THE MAIN APP (Logged In) ---
    user_token = st.session_state.access_token

    with st.sidebar:
        st.write("👤 **Logged In**")
        if st.button("🚪 Logout"):
            st.session_state.access_token = None
            st.rerun()

    # Get Pages and their individual tokens
    pages_url = f"https://graph.facebook.com/v21.0/me/accounts?access_token={user_token}"
    pages_data = requests.get(pages_url).json().get('data', [])

    if pages_data:
        st.success("✅ Connected to Facebook Pages!")
        
        page_names = [p['name'] for p in pages_data]
        selected_page = st.selectbox("Select Page to Post To:", page_names)
        
        # Find the specific token for the selected page
        target_page = next(p for p in pages_data if p['name'] == selected_page)
        target_id = target_page['id']
        target_token = target_page['access_token'] # This is the key for posting

        st.divider()
        
        col1, col2 = st.columns(2)
        with col1:
            video_file = st.file_uploader("🎥 Select Video", type=['mp4', 'mov'])
        with col2:
            caption = st.text_area("✍️ Caption", "Fresh drops! 👟🔥\nAvailable now.")

        if st.button("🚀 PUBLISH NOW"):
            if video_file:
                with st.spinner(f"Uploading to {selected_page}..."):
                    upload_url = f"https://graph-video.facebook.com/v21.0/{target_id}/videos"
                    files = {'file': (video_file.name, video_file.getvalue(), 'video/mp4')}
                    data = {'description': caption, 'access_token': target_token}
                    
                    post_res = requests.post(upload_url, data=data, files=files)
                    
                    if post_res.status_code == 200:
                        st.balloons()
                        st.success("Post successful! Check your page.")
                    else:
                        st.error(f"Upload Failed: {post_res.json().get('error', {}).get('message')}")
            else:
                st.warning("Please upload a video file.")
    else:
        st.warning("No pages found. Ensure you granted permissions to your pages during login.")
