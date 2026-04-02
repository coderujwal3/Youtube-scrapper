# Social Media Analytics & Engagement Intelligence

A Streamlit dashboard for collecting public YouTube channel data, storing it in a database, computing engagement and sentiment metrics, and exploring the results through interactive charts and exports.

## Overview

This project helps creators, analysts, and hackathon teams answer questions like:

- Which videos are driving the best engagement?
- When does a channel tend to perform best?
- What is the overall sentiment in audience comments?
- Which channels or videos should be studied more closely?

The app fetches public data from the YouTube Data API, stores it locally, computes analytics, and surfaces the results in a three-tab dashboard:

- `Fetch Data`
- `Visualize`
- `Export Data`

## What The App Does

- Search a YouTube channel by name
- Fetch channel metadata
- Fetch recent videos and playlists
- Fetch top-level comments for fetched videos
- Store collected data in database tables
- Calculate per-video engagement metrics
- Run VADER-based sentiment analysis on comments
- Generate channel-level summary metrics
- Visualize results with Plotly charts
- Export tables or the full dataset to Excel

## Current Project Structure

```text
.
|-- .env
|-- .gitignore
|-- README.md
|-- requirements.txt
`-- visualization.py
```

## Tech Stack

- Python
- Streamlit
- Plotly
- Pandas
- Requests
- NLTK VADER
- SQLAlchemy
- PostgreSQL
- SQLite
- OpenPyXL

## Dashboard Workflow

### 1. Fetch Data

From the `Fetch Data` tab, the app lets you:

- enter a channel name
- choose the number of videos to fetch
- choose the number of playlists to fetch
- watch a live progress log while data is collected

During the fetch flow, the app:

1. searches for the channel
2. pulls channel statistics
3. fetches videos
4. fetches playlists
5. fetches comments for each video
6. saves all records to the database
7. computes video and channel analytics

### 2. Visualize

The `Visualize` tab loads saved data and provides:

- channel selection from the sidebar
- KPI cards for videos, views, and engagement
- top-performing video charts
- best posting time heatmaps
- sentiment distribution charts
- top keyword charts from comments
- raw data tables for every stored entity

### 3. Export Data

The `Export Data` tab allows:

- downloading all tables in one Excel workbook
- downloading individual tables as Excel files
- previewing the current dataset before export

## Analytics Included

### Video-Level Metrics

- `engagement_rate = (likes + comments) / views`
- `engagement_score = int(engagement_rate * 100)`
- `is_top_video` flag for the highest-engagement videos
- `best_posting_time` derived from publish day and hour
- `performance_category` based on engagement rate thresholds:
  - `Excellent` if `engagement_rate > 0.10`
  - `Good` if `engagement_rate > 0.05`
  - `Average` if `engagement_rate > 0.01`
  - `Poor` otherwise

### Comment Intelligence

- VADER sentiment scoring
- Positive / Negative / Neutral classification
- top repeated keywords from comment text

### Channel-Level Metrics

- average views
- average engagement
- simple growth-rate estimate based on fetched videos
- best posting time summary
- audience quality score based on positive comment share

## Database Schema

The app works with six main tables:

| Table | Purpose |
|---|---|
| `channels` | Channel metadata and subscriber/view counts |
| `videos` | Video-level statistics and publish dates |
| `playlists` | Playlist data for the selected channel |
| `comments` | Top-level comment text and likes |
| `video_analytics` | Computed metrics for individual videos |
| `channel_analytics` | Aggregated metrics for the channel |

### Detailed Table Schemas

The following schemas match the current `create_tables()`

#### `channels`

| Column | Type | Constraints / Default | Description |
|---|---|---|---|
| `channel_id` | `VARCHAR(255)` | `PRIMARY KEY` | YouTube channel ID |
| `title` | `TEXT` |  | Channel title |
| `subscribers` | `BIGINT` |  | Subscriber count |
| `total_views` | `BIGINT` |  | Total channel views |
| `video_count` | `INT` |  | Total published videos reported by YouTube |
| `created_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Time the row was stored locally |

```sql
CREATE TABLE IF NOT EXISTS channels (
    channel_id VARCHAR(255) PRIMARY KEY,
    title TEXT,
    subscribers BIGINT,
    total_views BIGINT,
    video_count INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `videos`

| Column | Type | Constraints / Default | Description |
|---|---|---|---|
| `video_id` | `VARCHAR(255)` | `PRIMARY KEY` | YouTube video ID |
| `channel_id` | `VARCHAR(255)` |  | Parent channel ID |
| `title` | `TEXT` |  | Video title |
| `views` | `BIGINT` |  | View count |
| `likes` | `BIGINT` |  | Like count |
| `comments` | `BIGINT` |  | Total top-level comment count reported by YouTube |
| `published_at` | `TIMESTAMP` |  | Original YouTube publish timestamp |
| `created_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Time the row was stored locally |

```sql
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
```

#### `playlists`

| Column | Type | Constraints / Default | Description |
|---|---|---|---|
| `playlist_id` | `VARCHAR(255)` | `PRIMARY KEY` | YouTube playlist ID |
| `channel_id` | `VARCHAR(255)` |  | Parent channel ID |
| `title` | `TEXT` |  | Playlist title |
| `description` | `TEXT` |  | Playlist description |
| `item_count` | `INT` |  | Number of videos in the playlist |
| `published_at` | `TIMESTAMP` |  | Playlist publish timestamp |
| `created_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Time the row was stored locally |

```sql
CREATE TABLE IF NOT EXISTS playlists (
    playlist_id VARCHAR(255) PRIMARY KEY,
    channel_id VARCHAR(255),
    title TEXT,
    description TEXT,
    item_count INT,
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `comments`

| Column | Type | Constraints / Default | Description |
|---|---|---|---|
| `comment_id` | `VARCHAR(255)` | `PRIMARY KEY` | Top-level YouTube comment thread ID |
| `video_id` | `VARCHAR(255)` |  | Parent video ID |
| `text` | `TEXT` |  | Rendered comment text |
| `like_count` | `INT` |  | Comment likes |
| `created_at` | `TIMESTAMP` |  | Original comment publish timestamp |

```sql
CREATE TABLE IF NOT EXISTS comments (
    comment_id VARCHAR(255) PRIMARY KEY,
    video_id VARCHAR(255),
    text TEXT,
    like_count INT,
    created_at TIMESTAMP
);

### Relationship Summary

```text
channels (1) ---- (N) videos
channels (1) ---- (N) playlists
videos   (1) ---- (N) comments
videos   (1) ---- (N) video_analytics
channels (1) ---- (N) channel_analytics
```

## Setup

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
```

Windows PowerShell:

```bash
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Download the VADER lexicon

This project uses `SentimentIntensityAnalyzer`, so the VADER data package must be available locally:

```bash
python -m nltk.downloader vader_lexicon
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
YOUTUBE_API_KEY=your_youtube_api_key

# Database mode
DB_TYPE=postgresql

# PostgreSQL settings
DB_NAME=social_analytics
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# SQLite settings
SQLITE_DB_NAME=social_analytics.db
```

## Running The App

Start the Streamlit dashboard with:

```bash
streamlit run visualization.py
```

Then open the local Streamlit URL shown in the terminal, usually:

```text
http://localhost:8501
```

## How To Use

1. Open the `Fetch Data` tab.
2. Enter a channel name, such as `YouTube` or `MrBeast`.
3. Set your video and playlist limits.
4. Click `Fetch Data`.
5. Wait for the logs and summary metrics to finish.
6. Open `Visualize` to inspect charts and raw tables.
7. Open `Export Data` to download the results.

## Supported Databases

The code is structured for both PostgreSQL and SQLite through `DB_TYPE`.

- Use `DB_TYPE=postgresql` for a fuller local or production-style setup.
- Use `DB_TYPE=sqlite` for a lightweight local database file.

Note: the current codebase is primarily oriented around the PostgreSQL path, so PostgreSQL is the safer option if you want the most predictable setup.

## Requirements

Project dependencies are defined in [requirements.txt](/e:/Programming/syskriti/Project/requirements.txt).

Main packages:

- `streamlit`
- `plotly`
- `pandas`
- `numpy`
- `psycopg2-binary`
- `sqlalchemy`
- `requests`
- `python-dotenv`
- `openpyxl`
- `nltk`

## Important Notes

- Only public YouTube data is available through this workflow.
- API quota limits apply to the YouTube Data API.
- Comment fetching depends on comment availability and channel settings.
- The channel search step uses the first matching YouTube search result.
- Larger fetch sizes will take longer and consume more API quota.

## Practical Limitations

- Private analytics such as watch time, retention, and audience demographics are not available here.
- Keyword extraction currently uses a simple word-frequency approach.
- Growth calculations are based on fetched video data, not on full historical channel snapshots.
- Sentiment analysis is rule-based and may miss sarcasm, slang, or multilingual nuance.

## Future Improvements

- stronger keyword cleaning and stop-word filtering
- comparative multi-channel benchmarking
- historical trend snapshots over time
- better growth modeling
- richer export formats
- more robust SQLite compatibility

## Why This Project Matters

This project combines API integration, data storage, sentiment analysis, analytics, and dashboarding in one compact workflow. It is a practical portfolio piece for:

- data engineering
- analytics engineering
- dashboard development
- social media intelligence
- hackathon demos

## File Reference

Main app entry point: visualization.py
