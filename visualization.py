import streamlit as st
import pandas as pd
import sqlite3
import os
from dotenv import load_dotenv
import plotly.express as px
from collections import Counter
import io
import json
import time
from datetime import datetime, timedelta
from sqlalchemy import create_engine
import requests
from nltk.sentiment import SentimentIntensityAnalyzer
import psycopg2
from psycopg2 import sql

load_dotenv()

st.set_page_config(page_title="YouTube Analytics Dashboard", layout="wide")

# ================= CONFIGURATION =================
API_KEY = os.getenv("YOUTUBE_API_KEY")
DB_TYPE = (os.getenv("DB_TYPE") or "sqlite").strip().lower()
IS_SQLITE = DB_TYPE in {"sqlite", "sqlite3"}

if IS_SQLITE:
    DB_CONFIG = {"dbname": os.getenv("SQLITE_DB_NAME", "social_analytics.db")}
else:
    DB_CONFIG = {
        "dbname": os.getenv("DB_NAME", "social_analytics"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT"),
    }

# ================= DATABASE FUNCTIONS =================
def create_database_if_not_exists():
    if IS_SQLITE:
        sqlite3.connect(DB_CONFIG["dbname"]).close()
        return

    db_name = DB_CONFIG["dbname"]
    maintenance_config = DB_CONFIG.copy()
    maintenance_config["dbname"] = os.getenv("POSTGRES_MAINTENANCE_DB", "postgres")

    conn = psycopg2.connect(**maintenance_config)
    conn.autocommit = True
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
    exists = cursor.fetchone()

    if not exists:
        st.info(f"[-] Creating database '{db_name}'...")
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
        st.success(f"[✓] Database '{db_name}' created")
    else:
        st.success(f"[✓] Database '{db_name}' exists")

    cursor.close()
    conn.close()

def get_db_connection():
    if IS_SQLITE:
        return sqlite3.connect(DB_CONFIG["dbname"])
    return psycopg2.connect(**DB_CONFIG)

def create_tables(conn):
    cursor = conn.cursor()
    
    queries = [
        """CREATE TABLE IF NOT EXISTS channels (
            channel_id VARCHAR(255) PRIMARY KEY,
            title TEXT,
            subscribers BIGINT,
            total_views BIGINT,
            video_count INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );""",
        """CREATE TABLE IF NOT EXISTS videos (
            video_id VARCHAR(255) PRIMARY KEY,
            channel_id VARCHAR(255),
            title TEXT,
            views BIGINT,
            likes BIGINT,
            comments BIGINT,
            published_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );""",
        """CREATE TABLE IF NOT EXISTS playlists (
            playlist_id VARCHAR(255) PRIMARY KEY,
            channel_id VARCHAR(255),
            title TEXT,
            description TEXT,
            item_count INT,
            published_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );""",
        """CREATE TABLE IF NOT EXISTS comments (
            comment_id VARCHAR(255) PRIMARY KEY,
            video_id VARCHAR(255),
            text TEXT,
            like_count INT,
            created_at TIMESTAMP
        );""",
        """CREATE TABLE IF NOT EXISTS video_analytics (
            id SERIAL PRIMARY KEY,
            video_id VARCHAR(255),
            engagement_rate FLOAT,
            engagement_score INT,
            is_top_video BOOLEAN,
            best_posting_time VARCHAR(50),
            sentiment_avg FLOAT,
            performance_category VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );""",
        """CREATE TABLE IF NOT EXISTS channel_analytics (
            id SERIAL PRIMARY KEY,
            channel_id VARCHAR(255),
            avg_views BIGINT,
            avg_engagement FLOAT,
            growth_rate FLOAT,
            best_posting_time VARCHAR(50),
            audience_quality_score FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );"""
    ]
    
    for query in queries:
        cursor.execute(query)
    conn.commit()

def load_all_data():
    engine = create_engine(f"sqlite:///{DB_CONFIG['dbname']}" if IS_SQLITE else 
        f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
    
    dfs = {}
    tables = ["channels", "videos", "comments", "playlists", "video_analytics", "channel_analytics"]
    
    for table in tables:
        try:
            dfs[table] = pd.read_sql(f"SELECT * FROM {table}", engine)
        except:
            dfs[table] = pd.DataFrame()
    
    return dfs

# ================= YOUTUBE API FUNCTIONS =================
def fetch_channel_id_by_name(channel_name, progress_container):
    with progress_container:
        st.info(f"[+] Searching for channel: {channel_name}")
    
    url = f"https://www.googleapis.com/youtube/v3/search?q={channel_name}&type=channel&part=snippet&maxResults=1&key={API_KEY}"
    res = requests.get(url).json()

    if not res.get("items"):
        raise Exception(f"Channel '{channel_name}' not found")

    channel_id = res["items"][0]["id"]["channelId"]
    channel_title = res['items'][0]['snippet']['title']
    
    with progress_container:
        st.success(f"[✓] Found: {channel_title}")
    
    return channel_id

def fetch_channel_data(channel_id, progress_container):
    with progress_container:
        st.info("[+] Fetching channel data...")
    
    url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&id={channel_id}&key={API_KEY}"
    res = requests.get(url).json()

    if not res.get("items"):
        raise Exception("Invalid Channel ID")

    item = res["items"][0]
    
    with progress_container:
        st.success("[✓] Channel data fetched")

    return {
        "channel_id": channel_id,
        "title": item["snippet"]["title"],
        "subscribers": int(item["statistics"].get("subscriberCount", 0)),
        "total_views": int(item["statistics"].get("viewCount", 0)),
        "video_count": int(item["statistics"].get("videoCount", 0)),
    }

def fetch_videos(channel_id, limit, progress_container):
    with progress_container:
        st.info(f"[+] Fetching up to {limit} videos...")
    
    url = f"https://www.googleapis.com/youtube/v3/search?key={API_KEY}&channelId={channel_id}&part=snippet,id&order=date&maxResults={limit}"
    res = requests.get(url).json()

    videos = []

    for item in res.get("items", []):
        if item["id"]["kind"] == "youtube#video":
            video_id = item["id"]["videoId"]
            stats_url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics,snippet&id={video_id}&key={API_KEY}"
            stats = requests.get(stats_url).json()

            if not stats.get("items"):
                continue

            s = stats["items"][0]
            videos.append({
                "video_id": video_id,
                "channel_id": channel_id,
                "title": s["snippet"]["title"],
                "views": int(s["statistics"].get("viewCount", 0)),
                "likes": int(s["statistics"].get("likeCount", 0)),
                "comments": int(s["statistics"].get("commentCount", 0)),
                "published_at": s["snippet"]["publishedAt"],
            })

    with progress_container:
        st.success(f"[✓] Fetched {len(videos)} videos")

    return videos

def fetch_playlists(channel_id, limit, progress_container):
    with progress_container:
        st.info(f"[+] Fetching up to {limit} playlists...")
    
    url = f"https://www.googleapis.com/youtube/v3/playlists?part=snippet,contentDetails&channelId={channel_id}&maxResults={limit}&key={API_KEY}"
    res = requests.get(url).json()

    playlists = []
    for item in res.get("items", []):
        playlists.append({
            "playlist_id": item["id"],
            "channel_id": channel_id,
            "title": item["snippet"]["title"],
            "description": item["snippet"].get("description", ""),
            "item_count": int(item["contentDetails"].get("itemCount", 0)),
            "published_at": item["snippet"]["publishedAt"],
        })

    with progress_container:
        st.success(f"[✓] Fetched {len(playlists)} playlists")

    return playlists

def fetch_comments(video_id, limit=100):
    url = f"https://www.googleapis.com/youtube/v3/commentThreads?part=snippet&videoId={video_id}&maxResults={limit}&key={API_KEY}"
    res = requests.get(url).json()

    comments = []
    for item in res.get("items", []):
        c = item["snippet"]["topLevelComment"]["snippet"]
        comments.append({
            "comment_id": item["id"],
            "video_id": video_id,
            "text": c["textDisplay"],
            "like_count": c["likeCount"],
            "created_at": c["publishedAt"],
        })

    return comments

# ================= ANALYTICS FUNCTIONS =================
def compute_analytics(videos):
    if isinstance(videos, list):
        videos = pd.DataFrame(videos)
    
    videos["engagement_rate"] = (videos["likes"] + videos["comments"]) / videos["views"]
    videos["engagement_rate"] = videos["engagement_rate"].fillna(0)

    top_videos = videos.sort_values(by="engagement_rate", ascending=False).head(7)

    videos["published_at"] = pd.to_datetime(videos["published_at"])
    videos["hour"] = videos["published_at"].dt.hour
    videos["day"] = videos["published_at"].dt.day_name()

    best_time = videos.groupby(["day", "hour"])["engagement_rate"].mean().sort_values(ascending=False).head(5)

    return videos, top_videos, best_time

def sentiment_analysis(comments):
    sia = SentimentIntensityAnalyzer()

    if isinstance(comments, list):
        comments = pd.DataFrame(comments)

    comments["sentiment_score"] = comments["text"].apply(lambda x: sia.polarity_scores(str(x))["compound"])
    comments["sentiment"] = comments["sentiment_score"].apply(
        lambda x: "Positive" if x > 0.05 else ("Negative" if x < -0.05 else "Neutral")
    )

    return comments

def extract_keywords(comments):
    if isinstance(comments, list):
        comments = pd.DataFrame(comments)

    all_text = " ".join(comments["text"].astype(str))
    words = all_text.lower().split()
    common_words = Counter(words).most_common(10)

    return common_words

# ================= DATABASE SAVE FUNCTIONS =================
def save_channel(conn, data):
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO channels (channel_id, title, subscribers, total_views, video_count) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (channel_id) DO NOTHING;",
        (data["channel_id"], data["title"], data["subscribers"], data["total_views"], data["video_count"]),
    )
    conn.commit()

def save_videos(conn, videos):
    cursor = conn.cursor()
    for v in videos:
        cursor.execute(
            "INSERT INTO videos (video_id, channel_id, title, views, likes, comments, published_at) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (video_id) DO NOTHING;",
            (v["video_id"], v["channel_id"], v["title"], v["views"], v["likes"], v["comments"], v["published_at"]),
        )
    conn.commit()

def save_comments(conn, comments):
    cursor = conn.cursor()
    for c in comments:
        cursor.execute(
            "INSERT INTO comments (comment_id, video_id, text, like_count, created_at) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (comment_id) DO NOTHING;",
            (c["comment_id"], c["video_id"], c["text"], c["like_count"], c["created_at"]),
        )
    conn.commit()

def save_playlists(conn, playlists):
    cursor = conn.cursor()
    for p in playlists:
        cursor.execute(
            "INSERT INTO playlists (playlist_id, channel_id, title, description, item_count, published_at) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (playlist_id) DO NOTHING;",
            (p["playlist_id"], p["channel_id"], p["title"], p["description"], p["item_count"], p["published_at"]),
        )
    conn.commit()

def save_video_analytics(conn, video_id, engagement_rate, engagement_score, is_top_video, best_posting_time, sentiment_avg, performance_category):
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO video_analytics (video_id, engagement_rate, engagement_score, is_top_video, best_posting_time, sentiment_avg, performance_category) VALUES (%s,%s,%s,%s,%s,%s,%s);",
        (video_id, engagement_rate, engagement_score, is_top_video, best_posting_time, sentiment_avg, performance_category),
    )
    conn.commit()

def save_channel_analytics(conn, channel_id, avg_views, avg_engagement, growth_rate, best_posting_time, audience_quality_score):
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO channel_analytics (channel_id, avg_views, avg_engagement, growth_rate, best_posting_time, audience_quality_score) VALUES (%s,%s,%s,%s,%s,%s);",
        (channel_id, avg_views, avg_engagement, growth_rate, best_posting_time, audience_quality_score),
    )
    conn.commit()

# ================= EXPORT FUNCTIONS =================
def export_to_excel(dataframes_dict):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, df in dataframes_dict.items():
            if not df.empty:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output.getvalue()

def export_single_table(df, table_name):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=table_name, index=False)
    output.seek(0)
    return output.getvalue()

# ================= UI =================
st.title("YouTube Analytics Dashboard")
st.markdown("### Social Media Analytics & Engagement Intelligence")

tab_fetch, tab_visualize, tab_export = st.tabs(["Fetch Data", "Visualize", "Export Data"])

# ================= TAB 1: FETCH DATA =================
with tab_fetch:
    st.markdown("### Fetch YouTube Data")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        channel_name = st.text_input("Channel Name", placeholder="e.g., YouTube")
    with col2:
        videos_limit = st.number_input("Videos Limit", min_value=1, max_value=50, value=50)
    with col3:
        playlists_limit = st.number_input("Playlists Limit", min_value=1, max_value=50, value=50)
    
    if st.button("Fetch Data", width='stretch', type="primary"):
        if not channel_name:
            st.error("[X] Please enter a channel name")
        elif not API_KEY:
            st.error("[X] YouTube API Key not found in .env file")
        else:
            try:
                create_database_if_not_exists()
                conn = get_db_connection()
                create_tables(conn)
                
                progress_container = st.empty()
                log_container = st.container()
                st.markdown("---")
                st.subheader("📊 Fetching Process Log")
                
                # Create a log area
                log_placeholder = st.empty()
                logs = []
                
                def add_log(msg):
                    logs.append(f"⏱️ {datetime.now().strftime('%H:%M:%S')} - {msg}")
                    log_placeholder.text_area("Processing Logs:", value="\n".join(logs[-20:]), height=300, disabled=True)
                
                start_time = time.time()
                
                with st.spinner("Working..."):
                    # Step 1: Fetch Channel
                    add_log("[+] Searching for channel...")
                    channel_id = fetch_channel_id_by_name(channel_name, progress_container)
                    add_log(f"✓ Channel found: {channel_name}")
                    
                    # Step 2: Fetch Channel Data
                    add_log("[+] Fetching channel statistics...")
                    channel_data = fetch_channel_data(channel_id, progress_container)
                    add_log(f"✓ Channel data fetched - Subscribers: {channel_data['subscribers']:,}")
                    
                    # Step 3: Fetch Videos
                    add_log(f"[+] Fetching up to {videos_limit} videos...")
                    videos = fetch_videos(channel_id, videos_limit, progress_container)
                    add_log(f"✓ Found {len(videos)} videos")
                    
                    # Step 4: Fetch Playlists
                    add_log(f"[+] Fetching up to {playlists_limit} playlists...")
                    playlists = fetch_playlists(channel_id, playlists_limit, progress_container)
                    add_log(f"✓ Found {len(playlists)} playlists")
                    
                    # Step 5: Fetch Comments
                    add_log(f"[+] Starting to fetch comments from {len(videos)} videos...")
                    all_comments = []
                    
                    # Calculate time per video for estimation
                    if len(videos) > 0:
                        progress_bar = st.progress(0)
                        
                        for idx, v in enumerate(videos):
                            elapsed = time.time() - start_time
                            avg_time_per_video = elapsed / (idx + 1)
                            remaining_videos = len(videos) - idx - 1
                            estimated_remaining = avg_time_per_video * remaining_videos
                            
                            progress_percent = (idx + 1) / len(videos)
                            progress_bar.progress(progress_percent)
                            
                            estimated_total = elapsed + estimated_remaining
                            add_log(f"💬 [{idx+1}/{len(videos)}] Fetching comments - Elapsed: {int(elapsed)}s | Est. Total: {int(estimated_total)}s")
                            
                            comments_list = fetch_comments(v["video_id"])
                            all_comments.extend(comments_list)
                    
                    add_log(f"✓ Fetched total {len(all_comments)} comments")
                    
                    # Step 6: Save to DB
                    add_log("[+] Saving channel data...")
                    save_channel(conn, channel_data)
                    add_log("✓ Channel saved")
                    
                    add_log("[+] Saving videos...")
                    save_videos(conn, videos)
                    add_log(f"✓ {len(videos)} videos saved")
                    
                    add_log("[+] Saving playlists...")
                    save_playlists(conn, playlists)
                    add_log(f"✓ {len(playlists)} playlists saved")
                    
                    add_log("[+] Saving comments...")
                    save_comments(conn, all_comments)
                    add_log(f"✓ {len(all_comments)} comments saved")
                    
                    # Step 7: Compute Analytics
                    add_log("[+] Computing engagement rate analytics...")
                    videos_df, top_videos, best_time = compute_analytics(videos)
                    add_log("✓ Analytics computed")
                    
                    # Step 8: Sentiment Analysis
                    add_log("[+] Performing sentiment analysis...")
                    if all_comments:
                        comments_df = sentiment_analysis(all_comments)
                        sentiment_avg = float(comments_df["sentiment_score"].mean())
                        add_log(f"✓ Sentiment analysis complete - Avg sentiment: {sentiment_avg:.3f}")
                    else:
                        sentiment_avg = 0.0
                        add_log("[X] No comments found for sentiment analysis")
                    
                    # Step 9: Save Analytics
                    add_log("[+] Saving video analytics...")
                    top_videos_list = top_videos["video_id"].tolist()
                    for idx, video in videos_df.iterrows():
                        is_top = video["video_id"] in top_videos_list
                        engagement_score = int(video["engagement_rate"] * 100)
                        performance_category = (
                            "Excellent" if video["engagement_rate"] > 0.1
                            else "Good" if video["engagement_rate"] > 0.05
                            else "Average" if video["engagement_rate"] > 0.01
                            else "Poor"
                        )
                        best_posting_time = f"{video['day']} at {video['hour']}:00"
                        
                        save_video_analytics(
                            conn, video["video_id"], video["engagement_rate"],
                            engagement_score, is_top, best_posting_time,
                            sentiment_avg, performance_category
                        )
                    add_log(f"✓ Video analytics saved for {len(videos_df)} videos")
                    
                    # Step 10: Save Channel Analytics
                    add_log("[+] Saving channel analytics...")
                    avg_views = int(videos_df["views"].mean())
                    avg_engagement = float(videos_df["engagement_rate"].mean())
                    growth_rate = float((videos_df["views"].iloc[-1] - videos_df["views"].iloc[0]) / videos_df["views"].iloc[0] * 100) if len(videos_df) > 1 else 0.0
                    
                    best_posting_day_hour = best_time.idxmax()
                    best_posting_time_str = f"{best_posting_day_hour[0]} at {best_posting_day_hour[1]}:00"
                    
                    if all_comments:
                        positive_posts = (comments_df["sentiment"] == "Positive").sum()
                        audience_quality_score = float((positive_posts / len(comments_df) * 100) if len(comments_df) > 0 else 0)
                    else:
                        audience_quality_score = 0.0
                    
                    save_channel_analytics(
                        conn, channel_id, avg_views, avg_engagement,
                        growth_rate, best_posting_time_str, audience_quality_score
                    )
                    add_log("✓ Channel analytics saved")
                    
                    conn.close()
                    
                    total_time = time.time() - start_time
                    add_log(f"[✓] COMPLETE! Total time: {int(total_time)}s ({int(total_time)//60}m {int(total_time)%60}s)")
                
                st.markdown("---")
                st.subheader("Analytics Summary")
                
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Total Videos", len(videos))
                col2.metric("Total Comments", len(all_comments))
                col3.metric("Avg Views", f"{avg_views:,}")
                col4.metric("Avg Engagement", f"{avg_engagement:.4f}")
                col5.metric("Audience Score", f"{audience_quality_score:.1f}%")
                
                with st.expander("Top Videos"):
                    st.dataframe(top_videos[["title", "engagement_rate", "views", "likes", "comments"]], width='stretch')
                
                with st.expander("Best Posting Time"):
                    st.dataframe(best_time.reset_index(), width='stretch')
                
                if all_comments and len(comments_df) > 0:
                    with st.expander("Sentiment Analysis"):
                        col1, col2 = st.columns(2)
                        with col1:
                            sentiment_counts = comments_df["sentiment"].value_counts()
                            fig = px.pie(names=sentiment_counts.index, values=sentiment_counts.values, 
                                       title="Sentiment Distribution")
                            st.plotly_chart(fig, width='stretch')
                        
                        with col2:
                            keywords = extract_keywords(comments_df)
                            df_keywords = pd.DataFrame(keywords, columns=["word", "count"])
                            fig = px.bar(df_keywords, x="word", y="count", title="Top Keywords")
                            st.plotly_chart(fig, width='stretch')
                
                st.success("[✓] Data fetched successfully! Go to 'Visualize' tab.")
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")

# ================= TAB 2: VISUALIZE =================
with tab_visualize:
    st.markdown("### Visualize Channel Analytics")
    
    dfs = load_all_data()
    channels = dfs["channels"]
    videos = dfs["videos"]
    comments = dfs["comments"]
    playlists = dfs["playlists"]
    video_analytics = dfs["video_analytics"]
    channel_analytics = dfs["channel_analytics"]
    
    if channels.empty:
        st.warning("[X] No data available. Please fetch data using the 'Fetch Data' tab first.")
        st.stop()
    
    # Detect columns
    channel_col = next((c for c in ["channel_name", "name", "title", "channel"] if c in channels.columns), "title")
    channel_id_col = next((c for c in ["channel_id", "id"] if c in channels.columns), "channel_id")
    video_id_col = next((c for c in ["video_id", "id"] if c in videos.columns and c != channel_id_col), "video_id")
    comment_video_id_col = next((c for c in ["video_id", "id"] if c in comments.columns), "video_id")
    comment_text_col = next((c for c in ["text", "comment", "content"] if c in comments.columns), "text")
    video_title_col = next((c for c in ["title", "name"] if c in videos.columns), "title")
    likes_col = "likes" if "likes" in videos.columns else None
    comments_count_col = "comments" if "comments" in videos.columns else None
    views_col = "views" if "views" in videos.columns else None
    
    # Compute engagement rate
    if not videos.empty and likes_col and comments_count_col and views_col:
        videos["engagement_rate"] = (videos[likes_col] + videos[comments_count_col]) / videos[views_col]
        videos["engagement_rate"] = videos["engagement_rate"].fillna(0)
        
        if "published_at" in videos.columns:
            videos["published_at"] = pd.to_datetime(videos["published_at"])
            videos["hour"] = videos["published_at"].dt.hour
            videos["day"] = videos["published_at"].dt.day_name()
    
    # Channel selection in sidebar
    st.sidebar.markdown("### 📺 Channel Selection")
    channel_names = channels[channel_col].unique().tolist()
    selected_channels = st.sidebar.multiselect(
        "Select Channels:",
        channel_names,
        default=channel_names[:1] if channel_names else []
    )
    
    if not selected_channels:
        st.warning("[-] Select at least one channel")
        st.stop()
    
    # Filter data
    videos_filtered = videos[videos[channel_id_col].isin(
        channels[channels[channel_col].isin(selected_channels)][channel_id_col].values
    )].copy() if not videos.empty else pd.DataFrame()
    
    comments_filtered = comments[comments[comment_video_id_col].isin(
        videos_filtered[video_id_col].values
    )].copy() if not comments.empty and not videos_filtered.empty else pd.DataFrame()
    
    # KPI Section
    st.markdown("---")
    st.subheader("Overview")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Videos", len(videos_filtered))
    col2.metric("Avg Views", int(videos_filtered[views_col].mean()) if not videos_filtered.empty and views_col else 0)
    col3.metric("Avg Engagement", round(videos_filtered["engagement_rate"].mean(), 3) if not videos_filtered.empty else 0)
    
    # Download Section
    st.subheader("Download Data")
    
    col1, col2, col3 = st.columns(3)
    channels_filtered = channels[channels[channel_col].isin(selected_channels)]
    
    with col1:
        if not channels_filtered.empty:
            st.download_button(
                "Channels",
                export_single_table(channels_filtered, "channels"),
                f"channels_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_ch"
            )
    
    with col2:
        if not videos_filtered.empty:
            st.download_button(
                "Videos",
                export_single_table(videos_filtered, "videos"),
                f"videos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_vid"
            )
    
    with col3:
        if not comments_filtered.empty:
            st.download_button(
                "Comments",
                export_single_table(comments_filtered, "comments"),
                f"comments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_com"
            )
    
    # Visualizations
    st.subheader("Top Performing Videos")
    
    if not videos_filtered.empty:
        for channel_name in selected_channels:
            channel_videos = videos_filtered[
                videos_filtered[channel_id_col].isin(
                    channels[channels[channel_col] == channel_name][channel_id_col].values
                )
            ].copy()
            
            if not channel_videos.empty:
                st.markdown(f"#### {channel_name}")
                top_videos = channel_videos.sort_values(by="engagement_rate", ascending=False).head(10)
                
                fig = px.bar(
                    top_videos,
                    x="engagement_rate",
                    y=video_title_col,
                    orientation="h",
                    title=f"Top Videos by Engagement"
                )
                st.plotly_chart(fig, width='stretch', key=f"top_videos_{channel_name}")
    
    # Best Posting Time
    st.subheader("Best Posting Time")
    
    if not videos_filtered.empty and "hour" in videos_filtered.columns:
        for channel_name in selected_channels:
            channel_videos = videos_filtered[
                videos_filtered[channel_id_col].isin(
                    channels[channels[channel_col] == channel_name][channel_id_col].values
                )
            ].copy()
            
            if not channel_videos.empty:
                st.markdown(f"#### {channel_name}")
                heatmap_data = channel_videos.groupby(["day", "hour"])["engagement_rate"].mean().reset_index()
                
                if not heatmap_data.empty:
                    fig = px.density_heatmap(
                        heatmap_data, x="hour", y="day", z="engagement_rate",
                        title="Best Posting Time Heatmap"
                    )
                    st.plotly_chart(fig, width='stretch', key=f"best_time_{channel_name}")
    
    # Sentiment Analysis
    st.subheader("Sentiment Analysis")
    
    if not comments_filtered.empty:
        sia = SentimentIntensityAnalyzer()
        
        for channel_name in selected_channels:
            channel_videos = videos_filtered[
                videos_filtered[channel_id_col].isin(
                    channels[channels[channel_col] == channel_name][channel_id_col].values
                )
            ].copy()
            
            channel_comments = comments_filtered[
                comments_filtered[comment_video_id_col].isin(channel_videos[video_id_col].values)
            ].copy()
            
            if not channel_comments.empty:
                st.markdown(f"#### {channel_name}")
                
                channel_comments["sentiment"] = channel_comments[comment_text_col].apply(
                    lambda x: "Positive" if sia.polarity_scores(str(x))["compound"] > 0.05
                    else ("Negative" if sia.polarity_scores(str(x))["compound"] < -0.05 else "Neutral")
                )
                
                sentiment_counts = channel_comments["sentiment"].value_counts()
                
                fig = px.pie(
                    names=sentiment_counts.index,
                    values=sentiment_counts.values,
                    title="Audience Sentiment"
                )
                st.plotly_chart(fig, width='stretch', key=f"sentiment_{channel_name}")
    
    # Keywords
    st.subheader("Top Keywords")
    
    if not comments_filtered.empty:
        for channel_name in selected_channels:
            channel_videos = videos_filtered[
                videos_filtered[channel_id_col].isin(
                    channels[channels[channel_col] == channel_name][channel_id_col].values
                )
            ].copy()
            
            channel_comments = comments_filtered[
                comments_filtered[comment_video_id_col].isin(channel_videos[video_id_col].values)
            ].copy()
            
            if not channel_comments.empty:
                st.markdown(f"#### {channel_name}")
                
                text = " ".join(channel_comments[comment_text_col].astype(str))
                words = text.lower().split()
                common_words = Counter(words).most_common(10)
                
                if common_words:
                    df_words = pd.DataFrame(common_words, columns=["word", "count"])
                    fig = px.bar(df_words, x="word", y="count", title="Top Keywords")
                    st.plotly_chart(fig, width='stretch', key=f"keywords_{channel_name}")
    
    # Raw Data
    with st.expander("View Raw Data"):
        raw_tab1, raw_tab2, raw_tab3, raw_tab4, raw_tab5, raw_tab6 = st.tabs(["Channels", "Videos", "Comments", "Playlists", "Video Analytics", "Channel Analytics"])
        
        with raw_tab1:
            st.dataframe(channels_filtered, width='stretch')
        
        with raw_tab2:
            st.dataframe(videos_filtered, width='stretch')
        
        with raw_tab3:
            st.dataframe(comments_filtered, width='stretch')
        
        with raw_tab4:
            playlists_filtered = playlists[playlists[channel_id_col].isin(
                channels[channels[channel_col].isin(selected_channels)][channel_id_col].values
            )].copy() if not playlists.empty else pd.DataFrame()
            st.dataframe(playlists_filtered, width='stretch')
        
        with raw_tab5:
            if not video_analytics.empty:
                video_analytics_filtered = video_analytics[video_analytics["video_id"].isin(
                    videos_filtered[video_id_col].values
                )].copy()
                st.dataframe(video_analytics_filtered, width='stretch')
            else:
                st.info("No video analytics data available")
        
        with raw_tab6:
            if not channel_analytics.empty:
                channel_analytics_filtered = channel_analytics[channel_analytics["channel_id"].isin(
                    channels[channels[channel_col].isin(selected_channels)][channel_id_col].values
                )].copy()
                st.dataframe(channel_analytics_filtered, width='stretch')
            else:
                st.info("No channel analytics data available")

# ================= TAB 3: EXPORT DATA =================
with tab_export:
    st.markdown("### Export Complete Data")
    st.info("\tDownload all collected data in a single Excel file with multiple sheets.")
    
    dfs_export = load_all_data()
    
    if all(df.empty for df in dfs_export.values()):
        st.warning("[X] No data available. Please fetch data using the 'Fetch Data' tab first.")
        st.stop()
    
    st.subheader("Available Data Summary")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Channels", len(dfs_export["channels"]))
    col2.metric("Videos", len(dfs_export["videos"]))
    col3.metric("Comments", len(dfs_export["comments"]))
    
    col4, col5, col6 = st.columns(3)
    col4.metric("Playlists", len(dfs_export["playlists"]))
    col5.metric("Video Analytics", len(dfs_export["video_analytics"]))
    col6.metric("Channel Analytics", len(dfs_export["channel_analytics"]))
    
    st.markdown("---")
    
    st.subheader("⬇ Download Options")
    
    # Option 1: Download All Data
    if st.button("Download All Data", width='stretch', type="primary"):
        with st.spinner("Preparing complete dataset..."):
            all_data_excel = export_to_excel(dfs_export)
            st.download_button(
                label="✓ Click to Download Complete Data",
                data=all_data_excel,
                file_name=f"youtube_analytics_complete_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_complete_export"
            )
    
    st.markdown("---")
    st.subheader("Download Individual Tables")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if not dfs_export["channels"].empty:
            st.download_button(
                "Channels",
                export_single_table(dfs_export["channels"], "channels"),
                f"channels_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_ch_export"
            )
    
    with col2:
        if not dfs_export["videos"].empty:
            st.download_button(
                "Videos",
                export_single_table(dfs_export["videos"], "videos"),
                f"videos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_vid_export"
            )
    
    with col3:
        if not dfs_export["comments"].empty:
            st.download_button(
                "Comments",
                export_single_table(dfs_export["comments"], "comments"),
                f"comments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_com_export"
            )
    
    col4, col5, col6 = st.columns(3)
    
    with col4:
        if not dfs_export["playlists"].empty:
            st.download_button(
                "Playlists",
                export_single_table(dfs_export["playlists"], "playlists"),
                f"playlists_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_pl_export"
            )
    
    with col5:
        if not dfs_export["video_analytics"].empty:
            st.download_button(
                "Video Analytics",
                export_single_table(dfs_export["video_analytics"], "video_analytics"),
                f"video_analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_va_export"
            )
    
    with col6:
        if not dfs_export["channel_analytics"].empty:
            st.download_button(
                "Channel Analytics",
                export_single_table(dfs_export["channel_analytics"], "channel_analytics"),
                f"channel_analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_ca_export"
            )
    
    st.markdown("---")
    st.subheader("Preview Data Tables")
    
    preview_tab1, preview_tab2, preview_tab3, preview_tab4, preview_tab5, preview_tab6 = st.tabs(
        ["Channels", "Videos", "Comments", "Playlists", "Video Analytics", "Channel Analytics"]
    )
    
    with preview_tab1:
        if not dfs_export["channels"].empty:
            st.dataframe(dfs_export["channels"], width='stretch')
        else:
            st.info("No channels data available")
    
    with preview_tab2:
        if not dfs_export["videos"].empty:
            st.dataframe(dfs_export["videos"], width='stretch')
        else:
            st.info("No videos data available")
    
    with preview_tab3:
        if not dfs_export["comments"].empty:
            st.dataframe(dfs_export["comments"], width='stretch')
        else:
            st.info("No comments data available")
    
    with preview_tab4:
        if not dfs_export["playlists"].empty:
            st.dataframe(dfs_export["playlists"], width='stretch')
        else:
            st.info("No playlists data available")
    
    with preview_tab5:
        if not dfs_export["video_analytics"].empty:
            st.dataframe(dfs_export["video_analytics"], width='stretch')
        else:
            st.info("No video analytics data available")
    
    with preview_tab6:
        if not dfs_export["channel_analytics"].empty:
            st.dataframe(dfs_export["channel_analytics"], width='stretch')
        else:
            st.info("No channel analytics data available")
