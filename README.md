# 🚀 Social Media Analytics & Engagement Intelligence

A data-driven system that analyzes YouTube channel performance and generates actionable insights to improve engagement and content strategy.

---

## 🎯 Project Objective

To build a **YouTube Analytics Intelligence System** that:

* Extracts public data using YouTube API
* Stores it in a database (PostgreSQL / SQLite)
* Performs analytics on engagement
* Generates meaningful insights for creators & brands

---

## ⚠️ Hackathon Constraint

> Only **public YouTube data** is used
> (No watch time, retention graph, demographics)

---

## 🧠 Core Features

### 📊 Analytics

* **Engagement Rate** - Measures interaction relative to views
* **Engagement Score** - Composite metric combining likes, comments, views
* **Top Performing Videos** - Auto-identified viral/trending content
* **Growth Trends** - Tracks channel subscriber and view growth
* **Content Performance** - Video categorization by engagement level

### ⏰ Time Intelligence

* Best Posting Time (Day + Hour analysis)
* Content frequency patterns
* Upload schedule optimization

### 💬 Comment Intelligence (🔥 Powerful)

* **Sentiment Analysis** (VADER - Valence Aware Dictionary and sEntiment Reasoner)
  - Positive/Negative/Neutral classification
  - Sentiment average per video
* **Top Keywords Extraction** - Most discussed topics in comments
* **Audience Feedback Insights** - Auto-categorized feedback patterns
* **Comment Engagement** - Like counts + reply patterns

### 📈 Creator Summary & Analytics Tables

* **Video Analytics**: Per-video metrics (engagement, sentiment, category)
* **Channel Analytics**: Aggregated channel-level insights
  - Average views per video
  - Average engagement rate
  - Growth rate calculation
  - Audience quality scoring
* **Average Views & Engagement** - Channel-wide metrics
* **Posting Frequency** - Content upload patterns

---

## 🚀 Bonus Features (Advanced)

* Audience Quality Score (proxy-based)
* Sponsorship Value Estimation
* Video Performance Clustering

---

## 🏗️ System Architecture

```
YouTube API
      ↓
Python Backend (Data Fetching)
      ↓
Database Layer (PostgreSQL / SQLite)
      ↓
Data Processing (Pandas)
      ↓
Analytics Engine
      ↓
Insight Engine
      ↓
Dashboard (Streamlit)
```

---

## 🗄️ Database Design

### 📊 Complete Schema Overview

The system uses 6 interconnected tables to store and analyze YouTube data:

#### 📺 **channels**
Stores YouTube channel metadata

| Field | Type | Description |
|-------|------|-------------|
| channel_id | VARCHAR(255) PK | Unique YouTube channel identifier |
| title | TEXT | Channel name |
| subscribers | BIGINT | Total subscriber count |
| total_views | BIGINT | Total lifetime views |
| video_count | INT | Total number of videos published |
| created_at | TIMESTAMP | Record creation timestamp |

#### 🎥 **videos**
Stores video-level data linked to channels

| Field | Type | Description |
|-------|------|-------------|
| video_id | VARCHAR(255) PK | Unique YouTube video identifier |
| channel_id | VARCHAR(255) FK | References channels table |
| title | TEXT | Video title |
| views | BIGINT | Video view count |
| likes | BIGINT | Video like count |
| comments | BIGINT | Video comment count |
| published_at | TIMESTAMP | Video publication timestamp |
| created_at | TIMESTAMP | Record creation timestamp |

#### 📋 **playlists**
Stores playlist information from channels

| Field | Type | Description |
|-------|------|-------------|
| playlist_id | VARCHAR(255) PK | Unique YouTube playlist identifier |
| channel_id | VARCHAR(255) FK | References channels table |
| title | TEXT | Playlist title |
| description | TEXT | Playlist description |
| item_count | INT | Number of videos in playlist |
| published_at | TIMESTAMP | Playlist creation timestamp |
| created_at | TIMESTAMP | Record creation timestamp |

#### 💬 **comments**
Stores individual video comments for sentiment analysis

| Field | Type | Description |
|-------|------|-------------|
| comment_id | VARCHAR(255) PK | Unique YouTube comment identifier |
| video_id | VARCHAR(255) FK | References videos table |
| text | TEXT | Comment text content |
| like_count | INT | Likes on the comment |
| created_at | TIMESTAMP | Comment creation timestamp |

#### 📈 **video_analytics**
Computed analytics for individual videos

| Field | Type | Description |
|-------|------|-------------|
| id | SERIAL PK | Auto-incrementing primary key |
| video_id | VARCHAR(255) FK | References videos table |
| engagement_rate | FLOAT | (likes + comments) / views * 100 |
| engagement_score | INT | Composite engagement metric |
| is_top_video | BOOLEAN | Flag for top-performing videos |
| best_posting_time | VARCHAR(50) | Optimal posting time format (e.g., "Tuesday 7:00 PM") |
| sentiment_avg | FLOAT | Average sentiment score from comments (VADER) |
| performance_category | VARCHAR(50) | Category (e.g., "viral", "trending", "standard") |
| created_at | TIMESTAMP | Record creation timestamp |

#### 🎯 **channel_analytics**
Aggregated analytics for channels

| Field | Type | Description |
|-------|------|-------------|
| id | SERIAL PK | Auto-incrementing primary key |
| channel_id | VARCHAR(255) FK | References channels table |
| avg_views | BIGINT | Average views per video |
| avg_engagement | FLOAT | Average engagement rate |
| growth_rate | FLOAT | Subscriber/view growth percentage |
| best_posting_time | VARCHAR(50) | Best posting time for channel content |
| audience_quality_score | FLOAT | Proxy-based audience quality metric (0-100) |
| created_at | TIMESTAMP | Record creation timestamp |

### 🔗 **Database Relationships**

```
channels (1) ──── (N) videos
       │               │
       │               └──── (N) video_analytics
       │
       └──── (N) playlists
       
videos (1) ──── (N) comments
```

## 📊 Available Queries & Insights

### 📈 Video-Level Analytics Queries

```sql
-- Get all videos with engagement metrics
SELECT v.title, v.views, v.likes, v.comments,
       va.engagement_rate, va.sentiment_avg, va.performance_category
FROM videos v
LEFT JOIN video_analytics va ON v.video_id = va.video_id
ORDER BY va.engagement_rate DESC;

-- Find top-performing videos
SELECT * FROM video_analytics 
WHERE is_top_video = TRUE 
ORDER BY engagement_score DESC;

-- Identify best posting times
SELECT best_posting_time, COUNT(*) as frequency
FROM video_analytics
GROUP BY best_posting_time
ORDER BY frequency DESC;
```

### 🎯 Channel-Level Analytics Queries

```sql
-- Get channel summary with all metrics
SELECT c.title, c.subscribers, c.total_views,
       ca.avg_views, ca.avg_engagement, ca.growth_rate,
       ca.audience_quality_score
FROM channels c
LEFT JOIN channel_analytics ca ON c.channel_id = ca.channel_id;

-- Compare channels by engagement
SELECT c.title, ca.avg_engagement, ca.audience_quality_score
FROM channels c
JOIN channel_analytics ca ON c.channel_id = ca.channel_id
ORDER BY ca.avg_engagement DESC;
```

### 💬 Comment & Sentiment Analysis

```sql
-- Sentiment insights from comments
SELECT v.title, va.sentiment_avg, 
       COUNT(c.comment_id) as total_comments
FROM videos v
LEFT JOIN comments c ON v.video_id = c.video_id
LEFT JOIN video_analytics va ON v.video_id = va.video_id
GROUP BY v.video_id, v.title, va.sentiment_avg
ORDER BY va.sentiment_avg DESC;
```

### 🔀 Complete Data Join (All Information)

```sql
-- Get comprehensive data: Channels → Videos → Comments → Analytics
SELECT 
    c.title as channel_name,
    c.subscribers,
    c.total_views as channel_total_views,
    ca.avg_views,
    ca.avg_engagement,
    ca.growth_rate,
    ca.audience_quality_score,
    v.title as video_title,
    v.views as video_views,
    v.likes,
    v.comments as comment_count,
    v.published_at,
    va.engagement_rate,
    va.engagement_score,
    va.sentiment_avg,
    va.performance_category,
    va.best_posting_time,
    COUNT(cm.comment_id) as total_comments_fetched
FROM channels c
LEFT JOIN channel_analytics ca ON c.channel_id = ca.channel_id
LEFT JOIN videos v ON c.channel_id = v.channel_id
LEFT JOIN video_analytics va ON v.video_id = va.video_id
LEFT JOIN comments cm ON v.video_id = cm.video_id
GROUP BY 
    c.channel_id, c.title, c.subscribers, c.total_views,
    ca.avg_views, ca.avg_engagement, ca.growth_rate, ca.audience_quality_score,
    v.video_id, v.title, v.views, v.likes, v.comments, v.published_at,
    va.engagement_rate, va.engagement_score, va.sentiment_avg, 
    va.performance_category, va.best_posting_time
ORDER BY c.title, v.published_at DESC;
```

---

## 🧪 Analytics Engine Metrics

### Engagement Rate Calculation
```
Engagement Rate = ((Likes + Comments) / Views) * 100
```

### Engagement Score (Composite)
```
Engagement Score = (Likes * 2) + Comments + (Views * 0.01)
```

### Audience Quality Score
```
Quality Score = (Engagement Rate * 0.4) + 
                (Sentiment Positivity * 0.3) + 
                (Comment Depth * 0.3)
```

### Performance Categories
- 🔥 **Viral**: Engagement Rate > 5%
- 📈 **Trending**: Engagement Rate 2-5%
- 📊 **Standard**: Engagement Rate < 2%

---

## ⚙️ Tech Stack

* **Python** 🐍 (3.8+)
* **YouTube Data API v3** - Data extraction
* **PostgreSQL** 🐘 - Production database
* **SQLite** ⚡ - Development/hackathon database
* **Pandas** 📊 - Data manipulation & analysis
* **Streamlit** 📈 - Dashboard framework
* **NLTK** - NLP processing (VADER sentiment)
* **psycopg2** - PostgreSQL driver
* **python-dotenv** - Environment config

---

## 📦 Dependencies (requirements.txt)

```
requests>=2.28.0
psycopg2-binary>=2.9
python-dotenv>=0.21
pandas>=1.5
nltk>=3.8
streamlit>=1.0
openpyxl>=3.8
```

---

## 🔄 Data Pipeline Flow

```
Input Channel Name
        ↓
Fetch Channel ID (YouTube API)
        ↓
Fetch Channel Data → Store in [channels] table
        ↓                    
Fetch Videos → Store in [videos] table
        ↓
Fetch Comments → Store in [comments] table
        ↓
Fetch Playlists → Store in [playlists] table
        ↓
[ANALYTICS ENGINE]
        ├─→ Sentiment Analysis (VADER) on comments
        ├─→ Calculate engagement rates
        ├─→ Identify top videos
        ├─→ Determine best posting times
        └─→ Store in [video_analytics] & [channel_analytics]
        ↓
Generate Backups
        ├─→ Save JSON Backup (backup.json)
        ├─→ Save CSV Backup (backup.csv)
        └─→ Create Excel export
        ↓
Ready for Dashboard/Insights
```

---

## 🧩 Database Flexibility (🔥 Important Upgrade)

### ✅ PostgreSQL Mode (Production)

Requires:

* PostgreSQL installed
* .env configuration

---

### ✅ SQLite Mode (Hackathon Friendly)

* No installation required
* Auto creates `.db` file
* Plug & Play

---

## 🔐 Environment Variables (.env)

```
YOUTUBE_API_KEY=your_api_key

# Choose DB Type
DB_TYPE=postgres   # or sqlite

# PostgreSQL Config
DB_NAME=social_analytics
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# SQLite Config (optional)
SQLITE_DB_NAME=social_analytics.db
```

---

## 🗂️ Accessing the Database

### PostgreSQL (Production)
```bash
# Connect via psql
psql -h localhost -U postgres -d social_analytics

# Useful queries
\dt                    # List all tables
SELECT * FROM channels;
SELECT * FROM video_analytics;
```

### SQLite (Local Development)
```bash
# Connect via sqlite3
sqlite3 social_analytics.db

# Useful queries
.tables                # List all tables
SELECT * FROM video_analytics LIMIT 10;
```

### Python Direct Query
```python
import sqlite3
# or: import psycopg2

conn = sqlite3.connect('social_analytics.db')
cursor = conn.cursor()

# Query video analytics
cursor.execute("""
    SELECT title, views, engagement_rate 
    FROM videos
    JOIN video_analytics ON videos.video_id = video_analytics.video_id
    ORDER BY engagement_rate DESC
""")

results = cursor.fetchall()
for row in results:
    print(row)
```

---

## ⚡ Auto Setup Features

✔ Database auto-creation
✔ Tables auto-created
✔ No manual SQL required
✔ JSON backup generated

---

## ▶️ How to Run

```bash
pip install -r requirements.txt
python social_analytics.py
```

Enter:

```
Channel ID (UCxxxx...)
```

---

## ⚠️ Important Notes & Limitations

### YouTube API Restrictions
* **Quota**: Single API key has daily quota limits
* **Public Data Only**: Cannot fetch private/deleted videos
* **Rate Limiting**: Implement delays between large requests
* **Channel Privacy**: Data depends on channel visibility settings

### Data Availability
* Comments are limited to recent videos (API restriction)
* Some channels may have disabled comments
* Closed caption data requires additional permissions
* Subscriber count may show as "hidden" for privacy

### Best Practices
* Cache API responses to reduce quota usage
* Run analytics during off-peak hours
* Batch process multiple channels
* Store data regularly for historical comparison

---

## 📁 Output & Generated Data

* **Database populated with:**
  * `channels` - Channel metadata and statistics
  * `videos` - Individual video data
  * `comments` - Comment text and engagement
  * `playlists` - Playlist information
  * `video_analytics` - Per-video engagement & sentiment metrics
  * `channel_analytics` - Aggregated channel insights

* **Backup files created:**
  * `backup.json` - Complete JSON export
  * `backup.csv` - CSV export for spreadsheet analysis
  * `backup.xlsx` - Excel workbook (if pandas-excel support enabled)

---

## 📊 Example Insights Generated

### Video Performance Insights
* "Videos posted at 7 PM perform best" (from `best_posting_time` analysis)
* "Tutorial videos get 45% higher engagement than vlogs"
* "Video titles with 5-7 words have optimal performance"
* "Audience sentiment is 68% positive on average"

### Channel Health Metrics
* "Channel growth rate: +2.3% this month"
* "Audience quality score: 78/100"
* "Average engagement rate: 3.2%"
* "Optimal posting frequency: 3-4 videos per week"

### Comparative Analytics
* "Top video 'XYZ' has 5x average engagement"
* "Comments on recent videos show positive sentiment shift"
* "Subscriber growth correlates with tutorial uploads"

---

## 🧠 ML Strategy

### Current Implementation:

* ✅ Rule-based analytics (engagement calculations)
* ✅ VADER sentiment analysis on comments
* ✅ Aggregations & time-series analysis
* ✅ Performance categorization (Viral/Trending/Standard)
* ✅ Audience quality scoring

### Optional Enhancements:

* Clustering (K-Means) - Group similar video types
* Regression (Prediction) - Predict video performance
* Topic Modeling (LDA) - Automatic content categorization
* Time Series Forecasting - Predict future trends
* Comment Toxicity Detection - Identify negative patterns

---

## 🚀 Development Roadmap

### ✅ Day 1: Data Fetching + Storage

* YouTube API integration
* Multi-database support (PostgreSQL/SQLite)
* Auto schema generation
* Data persistence

### ✅ Day 2: Analytics Engine

* Sentiment Analysis (VADER)
* Engagement calculations
* Performance categorization
* Time-based analysis
* Analytics table population

### 📋 Day 3: Dashboard & Insights

* Streamlit dashboard
* Real-time query interface
* Interactive visualizations
* Export capabilities
* Insight presentation

---

## 🧠 Key Learning

This project demonstrates:

* Data Engineering
* API Integration
* Database Design
* Analytics Thinking
* AI/ML Readiness

---

## 💡 Final Thought

> This is not just a dashboard
> This is a **Decision-Making Intelligence System**

---

### 😏 Ho gaya bhai... ab toh judge bhi impress ho jayenge (maybe)