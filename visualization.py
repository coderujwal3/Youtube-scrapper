import streamlit as st
import pandas as pd
import sqlite3
import os
from dotenv import load_dotenv
import plotly.express as px
from collections import Counter
import io
import time
from datetime import datetime
import requests
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer
import psycopg2
from psycopg2 import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

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

TABLE_NAMES = ["channels", "videos", "comments", "playlists", "video_analytics", "channel_analytics"]


def ensure_sqlite_database_path():
    db_path = os.path.abspath(DB_CONFIG["dbname"])
    db_directory = os.path.dirname(db_path)
    if db_directory:
        os.makedirs(db_directory, exist_ok=True)


def validate_postgres_config(config):
    required_fields = {
        "dbname": "DB_NAME",
        "user": "DB_USER",
        "password": "DB_PASSWORD",
        "host": "DB_HOST",
        "port": "DB_PORT",
    }
    missing_fields = [env_name for key, env_name in required_fields.items() if not config.get(key)]
    if missing_fields:
        raise ValueError(f"Missing PostgreSQL configuration: {', '.join(missing_fields)}")


def build_insert_query(table_name, columns, conflict_column=None):
    placeholders = ",".join("?" if IS_SQLITE else "%s" for _ in columns)
    column_sql = ", ".join(columns)
    base_query = f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders})"

    if IS_SQLITE:
        return base_query.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)

    if conflict_column:
        return f"{base_query} ON CONFLICT ({conflict_column}) DO NOTHING"

    return base_query


def fetch_json(url):
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"YouTube API request failed: {exc}") from exc

    payload = response.json()

    if "error" in payload:
        error_message = payload["error"].get("message", "Unknown API error")
        raise RuntimeError(error_message)

    return payload


@st.cache_resource
def get_sentiment_analyzer():
    try:
        nltk.data.find("sentiment/vader_lexicon.zip")
    except LookupError:
        nltk.download("vader_lexicon", quiet=True)

    try:
        return SentimentIntensityAnalyzer()
    except LookupError as exc:
        raise RuntimeError(
            "VADER lexicon is missing. Run `python -m nltk.downloader vader_lexicon` and try again."
        ) from exc


def empty_table_dict():
    return {table_name: pd.DataFrame() for table_name in TABLE_NAMES}


def get_sqlalchemy_connectable():
    if IS_SQLITE:
        ensure_sqlite_database_path()
        return sqlite3.connect(DB_CONFIG["dbname"])

    validate_postgres_config(DB_CONFIG)
    db_url = URL.create(
        "postgresql+psycopg2",
        username=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        host=DB_CONFIG["host"],
        port=int(DB_CONFIG["port"]),
        database=DB_CONFIG["dbname"],
    )
    return create_engine(db_url)

# ================= DATABASE FUNCTIONS =================
def create_database_if_not_exists():
    if IS_SQLITE:
        ensure_sqlite_database_path()
        sqlite3.connect(DB_CONFIG["dbname"]).close()
        return

    validate_postgres_config(DB_CONFIG)
    db_name = DB_CONFIG["dbname"]
    maintenance_config = DB_CONFIG.copy()
    maintenance_config["dbname"] = os.getenv("POSTGRES_MAINTENANCE_DB", "postgres")

    conn = psycopg2.connect(**maintenance_config)
    conn.autocommit = True
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        exists = cursor.fetchone()

        if not exists:
            st.info(f"[-] Creating database '{db_name}'...")
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
            st.success(f"[OK] Database '{db_name}' created")
        else:
            st.success(f"[OK] Database '{db_name}' exists")
    finally:
        cursor.close()
        conn.close()

def get_db_connection():
    if IS_SQLITE:
        ensure_sqlite_database_path()
        return sqlite3.connect(DB_CONFIG["dbname"])
    validate_postgres_config(DB_CONFIG)
    return psycopg2.connect(**DB_CONFIG)

def create_tables(conn):
    cursor = conn.cursor()
    analytics_id_type = "INTEGER PRIMARY KEY AUTOINCREMENT" if IS_SQLITE else "SERIAL PRIMARY KEY"
    boolean_type = "INTEGER" if IS_SQLITE else "BOOLEAN"

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
        f"""CREATE TABLE IF NOT EXISTS video_analytics (
            id {analytics_id_type},
            video_id VARCHAR(255),
            engagement_rate FLOAT,
            engagement_score INT,
            is_top_video {boolean_type},
            best_posting_time VARCHAR(50),
            sentiment_avg FLOAT,
            performance_category VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );""",
        f"""CREATE TABLE IF NOT EXISTS channel_analytics (
            id {analytics_id_type},
            channel_id VARCHAR(255),
            avg_views BIGINT,
            avg_engagement FLOAT,
            growth_rate FLOAT,
            best_posting_time VARCHAR(50),
            audience_quality_score FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );"""
    ]

    try:
        for query in queries:
            cursor.execute(query)
        conn.commit()
    finally:
        cursor.close()

def load_all_data():
    connectable = None
    dfs = empty_table_dict()

    try:
        create_database_if_not_exists()
        conn = get_db_connection()
        try:
            create_tables(conn)
        finally:
            conn.close()

        connectable = get_sqlalchemy_connectable()

        for table_name in TABLE_NAMES:
            try:
                dfs[table_name] = pd.read_sql_query(f"SELECT * FROM {table_name}", connectable)
            except Exception:
                dfs[table_name] = pd.DataFrame()
    except Exception:
        return dfs
    finally:
        if connectable is not None:
            if IS_SQLITE:
                connectable.close()
            else:
                connectable.dispose()

    return dfs

# ================= YOUTUBE API FUNCTIONS =================
def fetch_channel_id_by_name(channel_name, progress_container):
    with progress_container:
        st.info(f"[+] Searching for channel: {channel_name}")
    
    url = f"https://www.googleapis.com/youtube/v3/search?q={channel_name}&type=channel&part=snippet&maxResults=1&key={API_KEY}"
    res = fetch_json(url)

    if not res.get("items"):
        raise Exception(f"Channel '{channel_name}' not found")

    channel_id = res["items"][0]["id"]["channelId"]
    channel_title = res['items'][0]['snippet']['title']
    
    with progress_container:
        st.success(f"[OK] Found: {channel_title}")
    
    return channel_id

def fetch_channel_data(channel_id, progress_container):
    with progress_container:
        st.info("[+] Fetching channel data...")
    
    url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&id={channel_id}&key={API_KEY}"
    res = fetch_json(url)

    if not res.get("items"):
        raise Exception("Invalid Channel ID")

    item = res["items"][0]
    
    with progress_container:
        st.success("[OK] Channel data fetched")

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
    res = fetch_json(url)

    videos = []

    for item in res.get("items", []):
        if item["id"]["kind"] == "youtube#video":
            video_id = item["id"]["videoId"]
            stats_url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics,snippet&id={video_id}&key={API_KEY}"
            stats = fetch_json(stats_url)

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
        st.success(f"[OK] Fetched {len(videos)} videos")

    return videos

def fetch_playlists(channel_id, limit, progress_container):
    with progress_container:
        st.info(f"[+] Fetching up to {limit} playlists...")
    
    url = f"https://www.googleapis.com/youtube/v3/playlists?part=snippet,contentDetails&channelId={channel_id}&maxResults={limit}&key={API_KEY}"
    res = fetch_json(url)

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
        st.success(f"[OK] Fetched {len(playlists)} playlists")

    return playlists

def fetch_comments(video_id, limit=100):
    url = f"https://www.googleapis.com/youtube/v3/commentThreads?part=snippet&videoId={video_id}&maxResults={limit}&key={API_KEY}"
    try:
        res = fetch_json(url)
    except RuntimeError as exc:
        error_message = str(exc).lower()
        if "disabled comments" in error_message or "commentthreadsdisabled" in error_message:
            return []
        raise

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

    if videos.empty:
        empty_best_time = pd.Series(dtype="float64", name="engagement_rate")
        return videos.copy(), videos.copy(), empty_best_time

    videos = videos.copy()
    videos["views"] = pd.to_numeric(videos["views"], errors="coerce")
    videos["likes"] = pd.to_numeric(videos["likes"], errors="coerce").fillna(0)
    videos["comments"] = pd.to_numeric(videos["comments"], errors="coerce").fillna(0)
    safe_views = videos["views"].replace(0, pd.NA)

    videos["engagement_rate"] = ((videos["likes"] + videos["comments"]) / safe_views).fillna(0)
    videos["engagement_rate"] = videos["engagement_rate"].replace([float("inf"), float("-inf")], 0)

    top_videos = videos.sort_values(by="engagement_rate", ascending=False).head(7)

    videos["published_at"] = pd.to_datetime(videos["published_at"], errors="coerce")
    videos["hour"] = videos["published_at"].dt.hour
    videos["day"] = videos["published_at"].dt.day_name()

    time_ready_videos = videos.dropna(subset=["day", "hour"])
    if time_ready_videos.empty:
        best_time = pd.Series(dtype="float64", name="engagement_rate")
    else:
        best_time = (
            time_ready_videos.groupby(["day", "hour"])["engagement_rate"]
            .mean()
            .sort_values(ascending=False)
            .head(5)
        )

    return videos, top_videos, best_time

def sentiment_analysis(comments):
    if isinstance(comments, list):
        comments = pd.DataFrame(comments)

    if comments.empty or "text" not in comments.columns:
        return comments.copy()

    comments = comments.copy()
    sia = get_sentiment_analyzer()
    comments["sentiment_score"] = comments["text"].apply(lambda x: sia.polarity_scores(str(x))["compound"])
    comments["sentiment"] = comments["sentiment_score"].apply(
        lambda x: "Positive" if x > 0.05 else ("Negative" if x < -0.05 else "Neutral")
    )

    return comments

def extract_keywords(comments):
    if isinstance(comments, list):
        comments = pd.DataFrame(comments)

    if comments.empty or "text" not in comments.columns:
        return []

    all_text = " ".join(comments["text"].astype(str))
    words = [word for word in all_text.lower().split() if word.strip()]
    common_words = Counter(words).most_common(10)

    return common_words

# ================= DATABASE SAVE FUNCTIONS =================
def save_channel(conn, data):
    cursor = conn.cursor()
    try:
        cursor.execute(
            build_insert_query(
                "channels",
                ["channel_id", "title", "subscribers", "total_views", "video_count"],
                "channel_id",
            ),
            (data["channel_id"], data["title"], data["subscribers"], data["total_views"], data["video_count"]),
        )
        conn.commit()
    finally:
        cursor.close()

def save_videos(conn, videos):
    if not videos:
        return

    cursor = conn.cursor()
    try:
        insert_query = build_insert_query(
            "videos",
            ["video_id", "channel_id", "title", "views", "likes", "comments", "published_at"],
            "video_id",
        )
        for v in videos:
            cursor.execute(
                insert_query,
                (v["video_id"], v["channel_id"], v["title"], v["views"], v["likes"], v["comments"], v["published_at"]),
            )
        conn.commit()
    finally:
        cursor.close()

def save_comments(conn, comments):
    if not comments:
        return

    cursor = conn.cursor()
    try:
        insert_query = build_insert_query(
            "comments",
            ["comment_id", "video_id", "text", "like_count", "created_at"],
            "comment_id",
        )
        for c in comments:
            cursor.execute(
                insert_query,
                (c["comment_id"], c["video_id"], c["text"], c["like_count"], c["created_at"]),
            )
        conn.commit()
    finally:
        cursor.close()

def save_playlists(conn, playlists):
    if not playlists:
        return

    cursor = conn.cursor()
    try:
        insert_query = build_insert_query(
            "playlists",
            ["playlist_id", "channel_id", "title", "description", "item_count", "published_at"],
            "playlist_id",
        )
        for p in playlists:
            cursor.execute(
                insert_query,
                (p["playlist_id"], p["channel_id"], p["title"], p["description"], p["item_count"], p["published_at"]),
            )
        conn.commit()
    finally:
        cursor.close()

def save_video_analytics(conn, video_id, engagement_rate, engagement_score, is_top_video, best_posting_time, sentiment_avg, performance_category):
    cursor = conn.cursor()
    try:
        stored_is_top_video = int(bool(is_top_video)) if IS_SQLITE else bool(is_top_video)
        cursor.execute(
            build_insert_query(
                "video_analytics",
                [
                    "video_id",
                    "engagement_rate",
                    "engagement_score",
                    "is_top_video",
                    "best_posting_time",
                    "sentiment_avg",
                    "performance_category",
                ],
            ),
            (video_id, engagement_rate, engagement_score, stored_is_top_video, best_posting_time, sentiment_avg, performance_category),
        )
        conn.commit()
    finally:
        cursor.close()

def save_channel_analytics(conn, channel_id, avg_views, avg_engagement, growth_rate, best_posting_time, audience_quality_score):
    cursor = conn.cursor()
    try:
        cursor.execute(
            build_insert_query(
                "channel_analytics",
                [
                    "channel_id",
                    "avg_views",
                    "avg_engagement",
                    "growth_rate",
                    "best_posting_time",
                    "audience_quality_score",
                ],
            ),
            (channel_id, avg_views, avg_engagement, growth_rate, best_posting_time, audience_quality_score),
        )
        conn.commit()
    finally:
        cursor.close()

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

tab_fetch, tab_detailed, tab_visualize, tab_export = st.tabs(
    ["Fetch Data", "Detailed Analytics", "Visualize", "Export Data"]
)

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
            conn = None
            try:
                create_database_if_not_exists()
                conn = get_db_connection()
                create_tables(conn)
                
                progress_container = st.empty()
                st.markdown("---")
                st.subheader("Fetching Process Log")
                
                # Create a log area
                log_placeholder = st.empty()
                logs = []
                comments_df = pd.DataFrame()
                avg_views = 0
                avg_engagement = 0.0
                audience_quality_score = 0.0
                
                def add_log(msg):
                    logs.append(f"{datetime.now().strftime('%H:%M:%S')} - {msg}")
                    log_placeholder.text_area("Processing Logs:", value="\n".join(logs[-20:]), height=300, disabled=True)
                
                start_time = time.time()
                
                with st.spinner("Working..."):
                    # Step 1: Fetch Channel
                    add_log("[+] Searching for channel...")
                    channel_id = fetch_channel_id_by_name(channel_name, progress_container)
                    add_log(f"[OK] Channel found: {channel_name}")
                    
                    # Step 2: Fetch Channel Data
                    add_log("[+] Fetching channel statistics...")
                    channel_data = fetch_channel_data(channel_id, progress_container)
                    add_log(f"[OK] Channel data fetched - Subscribers: {channel_data['subscribers']:,}")
                    
                    # Step 3: Fetch Videos
                    add_log(f"[+] Fetching up to {videos_limit} videos...")
                    videos = fetch_videos(channel_id, videos_limit, progress_container)
                    add_log(f"[OK] Found {len(videos)} videos")
                    
                    # Step 4: Fetch Playlists
                    add_log(f"[+] Fetching up to {playlists_limit} playlists...")
                    playlists = fetch_playlists(channel_id, playlists_limit, progress_container)
                    add_log(f"[OK] Found {len(playlists)} playlists")
                    
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
                            add_log(f"[COMMENTS] [{idx+1}/{len(videos)}] Fetching comments - Elapsed: {int(elapsed)}s | Est. Total: {int(estimated_total)}s")
                            
                            comments_list = fetch_comments(v["video_id"])
                            all_comments.extend(comments_list)
                    
                    add_log(f"[OK] Fetched total {len(all_comments)} comments")
                    
                    # Step 6: Save to DB
                    add_log("[+] Saving channel data...")
                    save_channel(conn, channel_data)
                    add_log("[OK] Channel saved")
                    
                    add_log("[+] Saving videos...")
                    save_videos(conn, videos)
                    add_log(f"[OK] {len(videos)} videos saved")
                    
                    add_log("[+] Saving playlists...")
                    save_playlists(conn, playlists)
                    add_log(f"[OK] {len(playlists)} playlists saved")
                    
                    add_log("[+] Saving comments...")
                    save_comments(conn, all_comments)
                    add_log(f"[OK] {len(all_comments)} comments saved")
                    
                    # Step 7: Compute Analytics
                    add_log("[+] Computing engagement rate analytics...")
                    videos_df, top_videos, best_time = compute_analytics(videos)
                    add_log("[OK] Analytics computed")
                    
                    # Step 8: Sentiment Analysis
                    add_log("[+] Performing sentiment analysis...")
                    if all_comments:
                        comments_df = sentiment_analysis(all_comments)
                        sentiment_avg = float(comments_df["sentiment_score"].mean()) if "sentiment_score" in comments_df else 0.0
                        add_log(f"[OK] Sentiment analysis complete - Avg sentiment: {sentiment_avg:.3f}")
                    else:
                        sentiment_avg = 0.0
                        add_log("[X] No comments found for sentiment analysis")
                    
                    # Step 9: Save Analytics
                    add_log("[+] Saving video analytics...")
                    top_videos_list = top_videos["video_id"].tolist() if "video_id" in top_videos.columns else []
                    for _, video in videos_df.iterrows():
                        is_top = video["video_id"] in top_videos_list
                        engagement_score = int(video["engagement_rate"] * 100)
                        performance_category = (
                            "Excellent" if video["engagement_rate"] > 0.1
                            else "Good" if video["engagement_rate"] > 0.05
                            else "Average" if video["engagement_rate"] > 0.01
                            else "Poor"
                        )
                        posting_day = video.get("day")
                        posting_hour = video.get("hour")
                        best_posting_time = (
                            f"{posting_day} at {int(posting_hour)}:00"
                            if pd.notna(posting_day) and pd.notna(posting_hour)
                            else "Unknown"
                        )

                        save_video_analytics(
                            conn, video["video_id"], video["engagement_rate"],
                            engagement_score, is_top, best_posting_time,
                            sentiment_avg, performance_category
                        )
                    add_log(f"[OK] Video analytics saved for {len(videos_df)} videos")
                    
                    # Step 10: Save Channel Analytics
                    add_log("[+] Saving channel analytics...")
                    avg_views = int(videos_df["views"].fillna(0).mean()) if not videos_df.empty else 0
                    avg_engagement = float(videos_df["engagement_rate"].fillna(0).mean()) if not videos_df.empty else 0.0

                    if len(videos_df) > 1 and pd.notna(videos_df["views"].iloc[0]) and videos_df["views"].iloc[0] > 0:
                        first_views = float(videos_df["views"].iloc[0])
                        last_views = float(videos_df["views"].iloc[-1])
                        growth_rate = float(((last_views - first_views) / first_views) * 100)
                    else:
                        growth_rate = 0.0

                    if best_time.empty:
                        best_posting_time_str = "Not enough data"
                    else:
                        best_posting_day_hour = best_time.index[0]
                        best_posting_time_str = f"{best_posting_day_hour[0]} at {int(best_posting_day_hour[1])}:00"
                    
                    if all_comments:
                        positive_posts = (comments_df["sentiment"] == "Positive").sum()
                        audience_quality_score = float((positive_posts / len(comments_df) * 100) if len(comments_df) > 0 else 0)
                    else:
                        audience_quality_score = 0.0
                    
                    save_channel_analytics(
                        conn, channel_id, avg_views, avg_engagement,
                        growth_rate, best_posting_time_str, audience_quality_score
                    )
                    add_log("[OK] Channel analytics saved")
                    
                    total_time = time.time() - start_time
                    add_log(f"[OK] COMPLETE! Total time: {int(total_time)}s ({int(total_time)//60}m {int(total_time)%60}s)")
                
                st.markdown("---")
                st.subheader("Analytics Summary")
                
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Total Videos", len(videos))
                col2.metric("Total Comments", len(all_comments))
                col3.metric("Avg Views", f"{avg_views:,}")
                col4.metric("Avg Engagement", f"{avg_engagement:.4f}")
                col5.metric("Audience Score", f"{audience_quality_score:.1f}%")
                
                with st.expander("Top Videos"):
                    required_columns = ["title", "engagement_rate", "views", "likes", "comments"]
                    if not top_videos.empty and all(column in top_videos.columns for column in required_columns):
                        st.dataframe(top_videos[required_columns], width='stretch')
                    else:
                        st.info("No video analytics available yet.")
                
                with st.expander("Best Posting Time"):
                    if not best_time.empty:
                        st.dataframe(best_time.reset_index(), width='stretch')
                    else:
                        st.info("Not enough publishing data to calculate best posting time.")
                
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
                
                st.success("[OK] Data fetched successfully! Go to 'Visualize' tab.")
                
            except Exception as e:
                st.error(f"Error: {str(e)}")
            finally:
                if conn is not None:
                    conn.close()

# ================= TAB 2: DETAILED ANALYTICS =================
with tab_detailed:
    st.markdown("### Detailed Analytics")
    st.caption("Select a channel and video to inspect all available per-video analytics.")

    dfs_detailed = load_all_data()
    channels_detailed = dfs_detailed["channels"]
    videos_detailed = dfs_detailed["videos"]
    comments_detailed = dfs_detailed["comments"]
    video_analytics_detailed = dfs_detailed["video_analytics"]

    if channels_detailed.empty or videos_detailed.empty or video_analytics_detailed.empty:
        st.warning("[X] Detailed analytics needs channel, video, and video_analytics data. Fetch data first.")
    else:
        channel_col_detail = next(
            (c for c in ["channel_name", "name", "title", "channel"] if c in channels_detailed.columns),
            "title",
        )
        channel_id_col_detail = next(
            (c for c in ["channel_id", "id"] if c in channels_detailed.columns),
            "channel_id",
        )
        video_id_col_detail = next(
            (c for c in ["video_id", "id"] if c in videos_detailed.columns and c != channel_id_col_detail),
            "video_id",
        )
        video_title_col_detail = next(
            (c for c in ["title", "name"] if c in videos_detailed.columns),
            "title",
        )
        comment_video_id_col_detail = next(
            (c for c in ["video_id", "id"] if c in comments_detailed.columns),
            "video_id",
        )
        comment_text_col_detail = next(
            (c for c in ["text", "comment", "content"] if c in comments_detailed.columns),
            "text",
        )

        if channel_id_col_detail not in channels_detailed.columns or video_id_col_detail not in videos_detailed.columns:
            st.error("Detailed analytics cannot be shown because required ID columns are missing.")
        elif "video_id" not in video_analytics_detailed.columns:
            st.error("video_analytics table does not contain 'video_id'.")
        else:
            channels_map = (
                channels_detailed[[channel_id_col_detail, channel_col_detail]]
                .dropna()
                .drop_duplicates()
                .copy()
            )
            videos_map = videos_detailed.copy()
            videos_map[video_id_col_detail] = videos_map[video_id_col_detail].astype(str)
            videos_map[channel_id_col_detail] = videos_map[channel_id_col_detail].astype(str)

            channels_map[channel_id_col_detail] = channels_map[channel_id_col_detail].astype(str)
            analytics_video_ids = set(video_analytics_detailed["video_id"].dropna().astype(str))
            videos_map = videos_map[videos_map[video_id_col_detail].isin(analytics_video_ids)].copy()

            if channels_map.empty or videos_map.empty:
                st.warning("[X] No per-video analytics rows are available yet. Fetch data first.")
            else:
                channel_options = sorted(channels_map[channel_col_detail].dropna().astype(str).unique().tolist())
                selected_channel_name = st.selectbox("Select Channel", channel_options, key="detail_channel")

                selected_channel_ids = channels_map[
                    channels_map[channel_col_detail].astype(str) == selected_channel_name
                ][channel_id_col_detail].unique()

                channel_videos = videos_map[videos_map[channel_id_col_detail].isin(selected_channel_ids)].copy()

                if channel_videos.empty:
                    st.info("No videos with analytics found for this channel.")
                else:
                    channel_videos["video_label"] = channel_videos[video_title_col_detail].astype(str).str.slice(0, 85)
                    channel_videos["video_label"] = (
                        channel_videos["video_label"] + " (" + channel_videos[video_id_col_detail].str[:10] + "...)"
                    )
                    video_labels = channel_videos["video_label"].tolist()
                    selected_video_label = st.selectbox("Select Video", video_labels, key="detail_video")
                    selected_video_row = channel_videos[channel_videos["video_label"] == selected_video_label].iloc[0]
                    selected_video_id = str(selected_video_row[video_id_col_detail])

                    selected_video_analytics = video_analytics_detailed[
                        video_analytics_detailed["video_id"].astype(str) == selected_video_id
                    ].copy()

                    if selected_video_analytics.empty:
                        st.info("No analytics rows found for this video.")
                    else:
                        if "created_at" in selected_video_analytics.columns:
                            selected_video_analytics["created_at"] = pd.to_datetime(
                                selected_video_analytics["created_at"], errors="coerce"
                            )
                            selected_video_analytics = selected_video_analytics.sort_values(
                                by="created_at", ascending=False
                            )

                        latest_video_analytics = selected_video_analytics.iloc[0]

                        st.markdown("#### Video Info")
                        info_col1, info_col2, info_col3 = st.columns(3)
                        info_col1.metric("Video ID", selected_video_id)
                        info_col2.metric("Title", str(selected_video_row.get(video_title_col_detail, "N/A"))[:45])
                        if "published_at" in channel_videos.columns:
                            published_at_value = pd.to_datetime(
                                selected_video_row.get("published_at"), errors="coerce"
                            )
                            info_col3.metric(
                                "Published At",
                                published_at_value.strftime("%Y-%m-%d %H:%M") if pd.notna(published_at_value) else "N/A",
                            )
                        else:
                            info_col3.metric("Published At", "N/A")

                        st.markdown("#### Detailed Metrics")
                        views_value = pd.to_numeric(selected_video_row.get("views", 0), errors="coerce")
                        likes_value = pd.to_numeric(selected_video_row.get("likes", 0), errors="coerce")
                        comments_value = pd.to_numeric(selected_video_row.get("comments", 0), errors="coerce")

                        metric_col1, metric_col2, metric_col3 = st.columns(3)
                        metric_col1.metric("Views", f"{int(views_value):,}" if pd.notna(views_value) else "0")
                        metric_col2.metric("Likes", f"{int(likes_value):,}" if pd.notna(likes_value) else "0")
                        metric_col3.metric("Comments", f"{int(comments_value):,}" if pd.notna(comments_value) else "0")

                        engagement_rate_value = pd.to_numeric(
                            latest_video_analytics.get("engagement_rate", 0), errors="coerce"
                        )
                        engagement_score_value = pd.to_numeric(
                            latest_video_analytics.get("engagement_score", 0), errors="coerce"
                        )
                        sentiment_avg_value = pd.to_numeric(
                            latest_video_analytics.get("sentiment_avg", 0), errors="coerce"
                        )
                        is_top_video_value = latest_video_analytics.get("is_top_video", False)
                        performance_category_value = str(
                            latest_video_analytics.get("performance_category", "N/A")
                        )
                        best_posting_time_value = str(
                            latest_video_analytics.get("best_posting_time", "N/A")
                        )

                        metric_col4, metric_col5, metric_col6 = st.columns(3)
                        metric_col4.metric(
                            "Engagement Rate",
                            f"{float(engagement_rate_value) * 100:.2f}%" if pd.notna(engagement_rate_value) else "0%",
                        )
                        metric_col5.metric(
                            "Engagement Score",
                            str(int(engagement_score_value)) if pd.notna(engagement_score_value) else "0",
                        )
                        metric_col6.metric(
                            "Sentiment Avg",
                            f"{float(sentiment_avg_value):.3f}" if pd.notna(sentiment_avg_value) else "0.000",
                        )

                        metric_col7, metric_col8, metric_col9 = st.columns(3)
                        metric_col7.metric(
                            "Performance Category",
                            performance_category_value,
                        )
                        metric_col8.metric(
                            "Top Video",
                            "Yes" if bool(is_top_video_value) else "No",
                        )
                        metric_col9.metric(
                            "Best Posting Time",
                            best_posting_time_value,
                        )

                        st.markdown("#### Engagement Snapshot")
                        engagement_snapshot = pd.DataFrame(
                            {
                                "Metric": ["Views", "Likes", "Comments"],
                                "Value": [
                                    float(views_value) if pd.notna(views_value) else 0,
                                    float(likes_value) if pd.notna(likes_value) else 0,
                                    float(comments_value) if pd.notna(comments_value) else 0,
                                ],
                            }
                        )
                        engagement_fig = px.bar(
                            engagement_snapshot,
                            x="Metric",
                            y="Value",
                            title="Video Engagement Metrics",
                            color="Metric",
                        )
                        st.plotly_chart(engagement_fig, width='stretch', key=f"detail_engagement_{selected_video_id}")

                        if (
                            not comments_detailed.empty
                            and comment_video_id_col_detail in comments_detailed.columns
                            and comment_text_col_detail in comments_detailed.columns
                        ):
                            selected_video_comments = comments_detailed[
                                comments_detailed[comment_video_id_col_detail].astype(str) == selected_video_id
                            ].copy()
                            if not selected_video_comments.empty:
                                if comment_text_col_detail != "text":
                                    selected_video_comments = selected_video_comments.rename(
                                        columns={comment_text_col_detail: "text"}
                                    )
                                selected_video_comments = sentiment_analysis(selected_video_comments)

                                if "sentiment" in selected_video_comments.columns:
                                    sentiment_distribution = (
                                        selected_video_comments["sentiment"].value_counts().reset_index()
                                    )
                                    sentiment_distribution.columns = ["sentiment", "count"]
                                    sentiment_fig = px.pie(
                                        sentiment_distribution,
                                        names="sentiment",
                                        values="count",
                                        title="Sentiment Distribution for Selected Video",
                                    )
                                    st.plotly_chart(
                                        sentiment_fig,
                                        width='stretch',
                                        key=f"detail_sentiment_{selected_video_id}",
                                    )
                            else:
                                st.info("No comments available for this video.")

                        st.markdown("#### Analytics History")
                        st.dataframe(selected_video_analytics, width='stretch')

                        if len(selected_video_analytics) > 1:
                            trend_data = selected_video_analytics.copy()
                            trend_data = trend_data.iloc[::-1].reset_index(drop=True)
                            trend_data["snapshot"] = trend_data.index + 1
                            trend_columns = ["snapshot"]
                            if "engagement_rate" in trend_data.columns:
                                trend_columns.append("engagement_rate")
                            if "sentiment_avg" in trend_data.columns:
                                trend_columns.append("sentiment_avg")
                            if len(trend_columns) > 1:
                                trend_plot_data = trend_data[trend_columns].melt(
                                    id_vars=["snapshot"],
                                    var_name="metric",
                                    value_name="value",
                                )
                                trend_fig = px.line(
                                    trend_plot_data,
                                    x="snapshot",
                                    y="value",
                                    color="metric",
                                    markers=True,
                                    title="Analytics Trend Across Saved Snapshots",
                                )
                                st.plotly_chart(
                                    trend_fig,
                                    width='stretch',
                                    key=f"detail_trend_{selected_video_id}",
                                )

# ================= TAB 3: VISUALIZE =================
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
        videos = videos.copy()
        videos[likes_col] = pd.to_numeric(videos[likes_col], errors="coerce").fillna(0)
        videos[comments_count_col] = pd.to_numeric(videos[comments_count_col], errors="coerce").fillna(0)
        videos[views_col] = pd.to_numeric(videos[views_col], errors="coerce")
        safe_views = videos[views_col].replace(0, pd.NA)
        videos["engagement_rate"] = ((videos[likes_col] + videos[comments_count_col]) / safe_views).fillna(0)
        videos["engagement_rate"] = videos["engagement_rate"].fillna(0)
        
        if "published_at" in videos.columns:
            videos["published_at"] = pd.to_datetime(videos["published_at"], errors="coerce")
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

# ================= TAB 4: EXPORT DATA =================
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
                label="Download Complete Data",
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
