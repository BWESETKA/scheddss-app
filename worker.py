import requests
import time
from supabase import create_client, Client

# --- CONFIG ---
SUPABASE_URL = "https://elpwqqvgrdovocvkzgyl.supabase.co"
SUPABASE_KEY = "your_anon_key_here"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def check_and_post():
    now_unix = int(time.time())
    
    # 1. Find comments that are 'pending' and whose time has passed
    res = supabase.table("comment_queue") \
        .select("*") \
        .eq("status", "pending") \
        .lte("scheduled_time", now_unix) \
        .execute()
    
    tasks = res.data
    
    for task in tasks:
        post_id = task['parent_post_id']
        token = task['page_access_token']
        msg = task['comment_text']
        
        # 2. Try to post to Facebook
        fb_res = requests.post(
            f"https://graph.facebook.com/v21.0/{post_id}/comments",
            data={'message': msg, 'access_token': token}
        ).json()
        
        if "id" in fb_res:
            print(f"✅ Success! Comment posted to {post_id}")
            # 3. Mark as 'sent' so we don't post it twice
            supabase.table("comment_queue").update({"status": "sent"}).eq("id", task['id']).execute()
        else:
            print(f"❌ Failed: {fb_res}")

if __name__ == "__main__":
    check_and_post()
