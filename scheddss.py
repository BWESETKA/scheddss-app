import streamlit as st
import requests

# --- 1. CONFIGURATION ---
CLIENT_ID = "910661605032071"
CLIENT_SECRET = "a57ba995d5178d5ee80c3debba225138"
# This MUST match your Meta Dashboard exactly (including the /)
REDIRECT_URI = "https://scheddss.streamlit.app/"

st.set_page_config(page_title="Scheddss Universal", page_icon="👟", layout="centered")

# --- 2. SESSION STATE ---
if "access_token" not in st.session_state:
    st.session_state.access_token = None

st.title("👟 Scheddss: Universal Uploader")

# --- 3. AUTHENTICATION LOGIC ---
if st.session_state.access_token is None:
    # Build the Facebook Login URL
    auth_url = (
        f"https://www.facebook.com/v21.0/dialog/oauth?"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&"
        f"response_type=code&"
        f"scope=pages_show_list,pages_manage_posts,pages_read_engagement,public_profile"
    )

    st.write("### Welcome to Scheddss")
    st.info("Your app is now live! Connect your Facebook account to start uploading.")

    # THE FIX: target="_top" breaks out of the Streamlit frame to avoid "Refused to connect"
    st.markdown(f'''
        <a href="{auth_url}" target="_top" style="
            background-color: #1877F2; 
            color: white; 
            padding: 12px 24px; 
            text-decoration: none; 
            border-radius: 6px; 
            font-weight: bold;
            display: inline-block;
            text-align: center;
        ">🔓 Log in with Facebook</a>
    ''', unsafe_allow_html=True)

    # Check if we just returned from Facebook with a 'code'
    query_params = st.query_params
    if "code" in query_params:
        code = query_params["code"]
        
        # Swap the Code for a real Access Token
        token_url = "https://graph.facebook.com/v21.0/oauth/access_token"
        params = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "code": code
        }
        
        try:
            res = requests.get(token_url, params=params).json()
            if "access_token" in res:
                st.session_state.access_token = res["access_token"]
                # Clean up the URL and refresh the app
                st.query_params.clear()
                st.rerun()
            else:
                st.error(f"Login Error: {res.get('error', {}).get('message', 'Unknown error')}")
        except Exception as e:
            st.error(f"Connection Error: {e}")

else:
    # --- 4. THE MAIN APP (When Logged In) ---
    user_token = st.session_state.access_token

    if st.sidebar.button("🚪 Logout"):
        st.session_state.access_token = None
        st.rerun()

    st.success("✅ Connected to Facebook!")

    # Function to fetch user's pages
    def get_facebook_pages(token):
        url = f"https://graph.facebook.com/v21.0/me/accounts?access_token={token}"
        try:
            response = requests.get(url).json()
            return response.get('data', [])
        except:
            return []

    pages = get_facebook_pages(user_token)

    if pages:
        st.write("### Choose a Page to Post To")
        page_map = {p['name']: (p['id'], p['access_token']) for p in pages}
        selected_page_name = st.selectbox("Select Page:", options=list(page_map.keys()))
        
        target_id, target_token = page_map[selected_page_name]
        
        st.divider()
        
        # Uploading Interface
        st.write(f"🎥 **Target Page:** {selected_page_name}")
        video_file = st.file_uploader("Upload Video (MP4/MOV)", type=['mp4', 'mov'])
        caption = st.text_area("Video Caption", "New sneakers in stock! 👟🔥")

        if st.button("🚀 PUBLISH VIDEO"):
            if video_file:
                with st.spinner("Uploading to Facebook..."):
                    # Facebook Video API Endpoint
                    upload_url = f"https://graph-video.facebook.com/v21.0/{target_id}/videos"
                    files = {'file': (video_file.name, video_file.getvalue(), 'video/mp4')}
                    data = {'description': caption, 'access_token': target_token}
                    
                    post_res = requests.post(upload_url, data=data, files=files)
                    
                    if post_res.status_code == 200:
                        st.balloons()
                        st.success(f"Successfully posted to {selected_page_name}!")
                    else:
                        st.error(f"Upload Failed: {post_res.json().get('error', {}).get('message')}")
            else:
                st.warning("Please upload a video file first.")
    else:
        st.warning("No pages found. Make sure you granted 'Manage Pages' permissions during login.")
