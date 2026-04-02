import json     # at last storing the data in json backup file, so imported json module
import os       # for environment variable handling
import sqlite3  # for sqlite database
import psycopg2     # for postgreSQL database
import requests     # for making HTTP requests
from dotenv import load_dotenv      # for loading environment variables from .env file
from psycopg2 import sql        # for safely constructing SQL queries (especially for database creation)
import pandas as pd     # for creating excel backup file

# importing packages for NLP
from nltk.sentiment import SentimentIntensityAnalyzer
from collections import Counter

# Load environment variables from .env file
load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")      # Replace with your API key

DB_TYPE = (os.getenv("DB_TYPE") or "postgres").strip().lower()      # "postgres" or "sqlite"
IS_SQLITE = DB_TYPE in {"sqlite", "sqlite3"}

if IS_SQLITE:
    DB_CONFIG = {
        "dbname": os.getenv("SQLITE_DB_NAME", "social_analytics.db"),
    }
else:   # else connect with postgreSQL
    DB_CONFIG = {
        "dbname": os.getenv("DB_NAME", "social_analytics"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT"),
    }

# If Database doesn't exist, create it (only for PostgreSQL)
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
        print(f"[-] Database '{db_name}' does not exist. [+] Creating...")
        cursor.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name))
        )
        print(f"[OK] Database '{db_name}' created")
    else:
        print(f"[OK] Database '{db_name}' already exists")

    cursor.close()
    conn.close()


# ------------------ DB CONNECTION ------------------
def get_db_connection():
    if IS_SQLITE:
        return sqlite3.connect(DB_CONFIG["dbname"])
    return psycopg2.connect(**DB_CONFIG)


# ------------------ CREATE TABLES ------------------
def create_tables(conn):
    cursor = conn.cursor()

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS channels (
        channel_id VARCHAR(255) PRIMARY KEY,
        title TEXT,
        subscribers BIGINT,
        total_views BIGINT,
        video_count INT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS videos (
        video_id VARCHAR(255) PRIMARY KEY,
        channel_id VARCHAR(255),
        title TEXT,
        views BIGINT,
        likes BIGINT,
        comments BIGINT,
        published_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS playlists (
        playlist_id VARCHAR(255) PRIMARY KEY,
        channel_id VARCHAR(255),
        title TEXT,
        description TEXT,
        item_count INT,
        published_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS comments (
        comment_id VARCHAR(255) PRIMARY KEY,
        video_id VARCHAR(255),
        text TEXT,
        like_count INT,
        created_at TIMESTAMP
    );
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS video_analytics (
        id SERIAL PRIMARY KEY,
        video_id VARCHAR(255),
        engagement_rate FLOAT,
        engagement_score INT,
        is_top_video BOOLEAN,
        best_posting_time VARCHAR(50),
        sentiment_avg FLOAT,
        performance_category VARCHAR(50),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS channel_analytics (
        id SERIAL PRIMARY KEY,
        channel_id VARCHAR(255),
        avg_views BIGINT,
        avg_engagement FLOAT,
        growth_rate FLOAT,
        best_posting_time VARCHAR(50),
        audience_quality_score FLOAT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    )

    conn.commit()


# ------------------ FETCH CHANNEL ID BY NAME ------------------
def fetch_channel_id_by_name(channel_name):
    url = (
        "https://www.googleapis.com/youtube/v3/search"
        f"?q={channel_name}&type=channel&part=snippet&maxResults=1&key={API_KEY}"
    )
    res = requests.get(url).json()

    if not res.get("items"):
        raise Exception(f"Channel '{channel_name}' not found")

    channel_id = res["items"][0]["id"]["channelId"]
    print(f"[OK] Found channel: {res['items'][0]['snippet']['title']}")
    return channel_id


# ------------------ FETCH CHANNEL ------------------
def fetch_channel_data(channel_id):
    url = (
        "https://www.googleapis.com/youtube/v3/channels"
        f"?part=snippet,statistics&id={channel_id}&key={API_KEY}"
    )
    res = requests.get(url).json()

    if not res.get("items"):
        raise Exception("Invalid Channel ID")

    item = res["items"][0]

    return {
        "channel_id": channel_id,
        "title": item["snippet"]["title"],
        "subscribers": int(item["statistics"].get("subscriberCount", 0)),
        "total_views": int(item["statistics"].get("viewCount", 0)),
        "video_count": int(item["statistics"].get("videoCount", 0)),
    }


# ------------------ FETCH VIDEOS ------------------
def fetch_videos(channel_id):
    limit = int(input("Enter number of max videos to fetch: "))
    url = (
        "https://www.googleapis.com/youtube/v3/search"
        f"?key={API_KEY}&channelId={channel_id}&part=snippet,id&order=date&maxResults={limit}"
    )
    res = requests.get(url).json()

    videos = []

    for item in res.get("items", []):
        print("[↓] Fetching video: " + item["snippet"]["title"] + "...")
        if item["id"]["kind"] == "youtube#video":
            video_id = item["id"]["videoId"]

            stats_url = (
                "https://www.googleapis.com/youtube/v3/videos"
                f"?part=statistics,snippet&id={video_id}&key={API_KEY}"
            )
            stats = requests.get(stats_url).json()

            if not stats.get("items"):
                continue

            s = stats["items"][0]

            videos.append(
                {
                    "video_id": video_id,
                    "channel_id": channel_id,
                    "title": s["snippet"]["title"],
                    "views": int(s["statistics"].get("viewCount", 0)),
                    "likes": int(s["statistics"].get("likeCount", 0)),
                    "comments": int(s["statistics"].get("commentCount", 0)),
                    "published_at": s["snippet"]["publishedAt"],
                }
            )

    return videos


# ------------------ FETCH PLAYLISTS ------------------
def fetch_playlists(channel_id):
    limit = int(input("Enter number of max playlists to fetch: "))
    url = (
        "https://www.googleapis.com/youtube/v3/playlists"
        f"?part=snippet,contentDetails&channelId={channel_id}&maxResults={limit}&key={API_KEY}"
    )
    res = requests.get(url).json()

    playlists = []

    for item in res.get("items", []):
        print("[↓] Fetching playlist: " + item["snippet"]["title"] + "...")
        playlists.append(
            {
                "playlist_id": item["id"],
                "channel_id": channel_id,
                "title": item["snippet"]["title"],
                "description": item["snippet"].get("description", ""),
                "item_count": int(item["contentDetails"].get("itemCount", 0)),
                "published_at": item["snippet"]["publishedAt"],
            }
        )

    return playlists


# ------------------ FETCH COMMENTS ------------------
def fetch_comments(video_id, limit=100):
    url = (
        "https://www.googleapis.com/youtube/v3/commentThreads"
        f"?part=snippet&videoId={video_id}&maxResults={limit}&key={API_KEY}"
    )
    res = requests.get(url).json()

    comments = []

    for item in res.get("items", []):
        c = item["snippet"]["topLevelComment"]["snippet"]

        comments.append(
            {
                "comment_id": item["id"],
                "video_id": video_id,
                "text": c["textDisplay"],
                "like_count": c["likeCount"],
                "created_at": c["publishedAt"],
            }
        )

    return comments


# ------------------ COMPUTING ANALYTICS (engagement rate, top videos, best time) ------------------
def compute_analytics(videos):
    # Convert list of dicts to DataFrame if needed
    if isinstance(videos, list):
        videos = pd.DataFrame(videos)
    
    # Engagement Rate
    videos["engagement_rate"] = (videos["likes"] + videos["comments"]) / videos["views"]

    # Handle division by zero
    videos["engagement_rate"] = videos["engagement_rate"].fillna(0)

    # Top videos
    top_videos = videos.sort_values(by="engagement_rate", ascending=False).head(5)

    # Best Posting Time
    videos["published_at"] = pd.to_datetime(videos["published_at"])
    videos["hour"] = videos["published_at"].dt.hour
    videos["day"] = videos["published_at"].dt.day_name()

    best_time = (
        videos.groupby(["day", "hour"])["engagement_rate"]
        .mean()
        .sort_values(ascending=False)
        .head(5)
    )

    return videos, top_videos, best_time



# ------------------ NLP ENGINE ------------------
def sentiment_analysis(comments):
    sia = SentimentIntensityAnalyzer()

    if isinstance(comments, list):
        comments = pd.DataFrame(comments)

    comments["sentiment_score"] = comments["text"].apply(
        lambda x: sia.polarity_scores(str(x))["compound"]
    )

    # Label sentiment
    comments["sentiment"] = comments["sentiment_score"].apply(
        lambda x: "Positive" if x > 0.05 else ("Negative" if x < -0.05 else "Neutral")
    )

    return comments



# ------------------ KEYWORD EXTRACTION ------------------
def extract_keywords(comments):
    if isinstance(comments, list):
        comments = pd.DataFrame(comments)

    all_text = " ".join(comments["text"].astype(str))
    words = all_text.lower().split()

    common_words = Counter(words).most_common(10)

    return common_words



# ------------------ SAVE VIDEO ANALYTICS ------------------
def save_video_analytics(conn, video_id, engagement_rate, engagement_score, is_top_video, best_posting_time, sentiment_avg, performance_category):
    cursor = conn.cursor()
    cursor.execute(
        """
    INSERT INTO video_analytics (
        video_id,
        engagement_rate,
        engagement_score,
        is_top_video,
        best_posting_time,
        sentiment_avg,
        performance_category
    ) VALUES (%s,%s,%s,%s,%s,%s,%s);
    """,
        (
            video_id,
            engagement_rate,
            engagement_score,
            is_top_video,
            best_posting_time,
            sentiment_avg,
            performance_category,
        ),
    )
    conn.commit()


# ------------------ SAVE CHANNEL ANALYTICS ------------------
def save_channel_analytics(conn, channel_id, avg_views, avg_engagement, growth_rate, best_posting_time, audience_quality_score):
    cursor = conn.cursor()
    cursor.execute(
        """
    INSERT INTO channel_analytics (
        channel_id,
        avg_views,
        avg_engagement,
        growth_rate,
        best_posting_time,
        audience_quality_score
    ) VALUES (%s,%s,%s,%s,%s,%s);
    """,
        (
            channel_id,
            avg_views,
            avg_engagement,
            growth_rate,
            best_posting_time,
            audience_quality_score,
        ),
    )
    conn.commit()


# ------------------ SAVE FUNCTIONS ------------------
def save_channel(conn, data):
    cursor = conn.cursor()
    cursor.execute(
        """
    INSERT INTO channels (
        channel_id,
        title,
        subscribers,
        total_views,
        video_count
    ) VALUES (%s,%s,%s,%s,%s)
    ON CONFLICT (channel_id) DO NOTHING;
    """,
        (
            data["channel_id"],
            data["title"],
            data["subscribers"],
            data["total_views"],
            data["video_count"],
        ),
    )
    conn.commit()


def save_videos(conn, videos):
    cursor = conn.cursor()
    for v in videos:
        cursor.execute(
            """
        INSERT INTO videos (
            video_id,
            channel_id,
            title,
            views,
            likes,
            comments,
            published_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (video_id) DO NOTHING;
        """,
            (
                v["video_id"],
                v["channel_id"],
                v["title"],
                v["views"],
                v["likes"],
                v["comments"],
                v["published_at"],
            ),
        )
    conn.commit()


def save_comments(conn, comments):
    cursor = conn.cursor()
    for c in comments:
        cursor.execute(
            """
        INSERT INTO comments (
            comment_id,
            video_id,
            text,
            like_count,
            created_at
        ) VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (comment_id) DO NOTHING;
        """,
            (
                c["comment_id"],
                c["video_id"],
                c["text"],
                c["like_count"],
                c["created_at"],
            ),
        )
    conn.commit()


def save_playlists(conn, playlists):
    cursor = conn.cursor()
    for p in playlists:
        cursor.execute(
            """
        INSERT INTO playlists (
            playlist_id,
            channel_id,
            title,
            description,
            item_count,
            published_at
        ) VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (playlist_id) DO NOTHING;
        """,
            (
                p["playlist_id"],
                p["channel_id"],
                p["title"],
                p["description"],
                p["item_count"],
                p["published_at"],
            ),
        )
    conn.commit()


# ------------------ JSON BACKUP ------------------
def save_json_backup(data):
    with open("backup.json", "w") as f:
        json.dump(data, f, indent=4)


# ------------------ EXCEL BACKUP ------------------
def save_excel_backup(channel, videos, playlists, comments):
    with pd.ExcelWriter("backup.xlsx", engine="openpyxl") as writer:
        pd.DataFrame([channel]).to_excel(writer, sheet_name="Channel", index=False)
        pd.DataFrame(videos).to_excel(writer, sheet_name="Videos", index=False)
        pd.DataFrame(playlists).to_excel(writer, sheet_name="Playlists", index=False)
        pd.DataFrame(comments).to_excel(writer, sheet_name="Comments", index=False)
    print("[OK] Excel backup saved as 'backup.xlsx'")


# ------------------ MAIN ------------------
def main():
    channel_name = input("Enter Channel Name: ")

    create_database_if_not_exists()

    conn = get_db_connection()
    create_tables(conn)

    print("Searching for channel...")
    channel_id = fetch_channel_id_by_name(channel_name)

    print("Fetching channel...")
    channel = fetch_channel_data(channel_id)

    print("Fetching videos...")
    videos = fetch_videos(channel_id)

    print("Fetching playlists...")
    playlists = fetch_playlists(channel_id)

    print("Fetching comments...")
    all_comments = []

    for v in videos:
        print(f"[↓] Fetching comments for {v['video_id']}...")
        comments = fetch_comments(v["video_id"])
        all_comments.extend(comments)

    print("Saving to DB...")
    save_channel(conn, channel)
    save_videos(conn, videos)
    save_playlists(conn, playlists)
    save_comments(conn, all_comments)

    print("Saving JSON backup...")
    save_json_backup(
        {
            "channel": channel,
            "videos": videos,
            "playlists": playlists,
            "comments": all_comments,
        }
    )

    print("Saving Excel backup...")
    save_excel_backup(channel, videos, playlists, all_comments)

    print("DONE - Data Pipeline Ready!", end="\n\n")

    print("================================== Computing Analytics... ==================================")
    videos, top_videos, best_time = compute_analytics(videos)

    print("\n[+] Top Videos:")
    print(top_videos[["title", "engagement_rate"]])

    print("\n[+] Best Posting Time:\n")
    print(best_time)

    print("\n================================== Running NLP... ==================================")
    comments_df = sentiment_analysis(comments)

    sentiment_counts = comments_df["sentiment"].value_counts()

    print("\n[+] Sentiment Distribution:")
    print(sentiment_counts)

    print("\n[+] Top Keywords:")
    print(extract_keywords(comments_df))

    # Save Analytics to Database
    print("\n================================== Saving Analytics to DB... ==================================")
    
    # Get sentiment average for all videos (convert to Python float to avoid numpy serialization issues)
    sentiment_avg = float(comments_df["sentiment_score"].mean())
    
    # Save VIDEO ANALYTICS for each video
    top_videos_list = top_videos["video_id"].tolist()
    for idx, video in videos.iterrows():
        is_top = video["video_id"] in top_videos_list
        engagement_score = int(video["engagement_rate"] * 100)
        
        # Determine performance category
        if video["engagement_rate"] > 0.1:
            performance_category = "Excellent"
        elif video["engagement_rate"] > 0.05:
            performance_category = "Good"
        elif video["engagement_rate"] > 0.01:
            performance_category = "Average"
        else:
            performance_category = "Poor"
        
        best_posting_time = f"{video['day']} at {video['hour']}:00"
        
        save_video_analytics(
            conn,
            video["video_id"],
            video["engagement_rate"],
            engagement_score,
            is_top,
            best_posting_time,
            sentiment_avg,
            performance_category
        )
    
    # Save CHANNEL ANALYTICS
    avg_views = int(videos["views"].mean())
    avg_engagement = float(videos["engagement_rate"].mean())
    
    # Calculate growth rate (views trend)
    if len(videos) > 1:
        growth_rate = float((videos["views"].iloc[-1] - videos["views"].iloc[0]) / videos["views"].iloc[0] * 100)
    else:
        growth_rate = 0.0
    
    # Best posting time for channel
    best_posting_day_hour = best_time.idxmax()
    best_posting_time_str = f"{best_posting_day_hour[0]} at {best_posting_day_hour[1]}:00"
    
    # Audience quality score based on sentiment
    positive_posts = (comments_df["sentiment"] == "Positive").sum()
    total_comments = len(comments_df)
    audience_quality_score = float((positive_posts / total_comments * 100) if total_comments > 0 else 0)
    
    save_channel_analytics(
        conn,
        channel_id,
        avg_views,
        avg_engagement,
        growth_rate,
        best_posting_time_str,
        audience_quality_score
    )
    
    print("[OK] Analytics saved to database!")


if __name__ == "__main__":
    main()
