import streamlit as st
import requests

# --- 1. CONFIGURATION ---
# These must match your Meta Dashboard exactly
CLIENT_ID = "910661605032071"
CLIENT_SECRET = "a57ba995d5178d5ee80c3debba225138"
REDIRECT_URI = "http://localhost:8501"  # NO SLASH AT THE END

st.set_page_config(page_title="Scheddss Universal", page_icon="👟", layout="centered")

# --- 2. SESSION STATE & STYLING ---
if "access_token" not in st.session_state:
    st.session_state.access_token = None

st.title("👟 Scheddss: Universal Uploader")

# --- 3. AUTHENTICATION LOGIC ---
if st.session_state.access_token is None:
    # Build the Login URL
    # We include 'response_type=code' and the specific permissions for Carter page
    auth_url = (
        f"https://www.facebook.com/v21.0/dialog/oauth?"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&"
        f"response_type=code&"
        f"scope=pages_show_list,pages_manage_posts,pages_read_engagement,public_profile"
    )

    st.write("### Welcome to Scheddss")
    st.info("Please log in to manage your shoe pages.")

    # Custom Facebook Button
    st.markdown(f'''
        <a href="{auth_url}" target="_self" style="
            background-color: #1877F2; 
            color: white; 
            padding: 12px 24px; 
            text-decoration: none; 
            border-radius: 6px; 
            font-weight: bold;
            display: inline-block;
        ">🔓 Log in with Facebook</a>
    ''', unsafe_allow_html=True)

    # Check if we are returning from Facebook with a 'code' in the URL
    if "code" in st.query_params:
        code = st.query_params["code"]
        
        # Token Exchange
        token_url = "https://graph.facebook.com/v21.0/oauth/access_token"
        params = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,  # THIS MUST BE IDENTICAL TO THE ONE ABOVE
            "code": code
        }
        
        try:
            res = requests.get(token_url, params=params).json()
            if "access_token" in res:
                st.session_state.access_token = res["access_token"]
                st.query_params.clear()
                st.rerun()
            else:
                error_msg = res.get("error", {}).get("message", "Unknown error")
                st.error(f"Login Failed: {error_msg}")
                st.write("Check if the Redirect URI in Meta Dashboard matches `http://localhost:8501` exactly.")
        except Exception as e:
            st.error(f"Connection Error: {e}")

else:
    # --- 4. THE MAIN APP (Authenticated) ---
    user_token = st.session_state.access_token

    # Sidebar for logout
    if st.sidebar.button("🚪 Logout"):
        st.session_state.access_token = None
        st.rerun()

    st.success("✅ Connected to Facebook!")

    # Function to get pages
    def get_facebook_pages(token):
        url = f"https://graph.facebook.com/v21.0/me/accounts?access_token={token}"
        try:
            response = requests.get(url).json()
            return response.get('data', [])
        except:
            return []

    pages = get_facebook_pages(user_token)

    if pages:
        st.write("### Select your Page")
        # Creating a dictionary to map Page Name to (ID, Token)
        page_map = {p['name']: (p['id'], p['access_token']) for p in pages}
        selected_page_name = st.selectbox("Which page are we posting to?", options=list(page_map.keys()))
        
        target_id, target_token = page_map[selected_page_name]
        
        st.divider()
        
        # Uploading Section
        st.write(f"🎥 **Uploading to: {selected_page_name}**")
        video_file = st.file_uploader("Select Video (MP4/MOV)", type=['mp4', 'mov'])
        caption = st.text_area("Caption", "New drops available now! 👟🔥")

        if st.button("🚀 UPLOAD TO FACEBOOK"):
            if video_file:
                with st.spinner("Uploading... Please wait."):
                    upload_url = f"https://graph.facebook.com/v21.0/{target_id}/videos"
                    files = {'file': (video_file.name, video_file.getvalue(), 'video/mp4')}
                    data = {'description': caption, 'access_token': target_token}
                    
                    post_res = requests.post(upload_url, data=data, files=files)
                    
                    if post_res.status_code == 200:
                        st.balloons()
                        st.success(f"Video successfully posted to {selected_page_name}!")
                    else:
                        st.error(f"Error: {post_res.json().get('error', {}).get('message')}")
            else:
                st.warning("Please select a video file first.")
    else:
        st.warning("No pages found. Make sure you gave the app permission to 'Manage Pages' in the Facebook popup.")