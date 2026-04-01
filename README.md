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

* Engagement Rate
* Top Performing Videos
* Growth Trends
* Content Performance

### ⏰ Time Intelligence

* Best Posting Time (Day + Hour analysis)

### 💬 Comment Intelligence (🔥 Powerful)

* Sentiment Analysis (VADER ready)
* Top Keywords Extraction
* Audience Feedback Insights

### 📈 Creator Summary

* Average Views
* Average Engagement
* Posting Frequency

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

### Tables:

#### 📺 channels

* channel_id (PK)
* title
* subscribers
* total_views
* video_count

#### 🎥 videos

* video_id (PK)
* channel_id (FK)
* title
* views
* likes
* comments
* published_at

#### 💬 comments

* comment_id (PK)
* video_id (FK)
* text
* like_count
* created_at

---

## ⚙️ Tech Stack

* Python 🐍
* YouTube Data API v3
* PostgreSQL 🐘 / SQLite ⚡
* Pandas 📊
* Streamlit 📈
* NLP (VADER / TextBlob)

---

## 🔄 Data Pipeline Flow

```
Input Channel Name
        ↓
Fetch Channel ID
        ↓
Fetch Channel Data
        ↓
Fetch Videos
        ↓
Fetch Comments
        ↓
Store in Database
        ↓
Save JSON Backup
        ↓
Save CSV Backup
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

## 📁 Output

* Database populated with:

  * Channels
  * Videos
  * Comments

* `backup.json` file created

---

## 📊 Example Insights (Next Phase)

* “Videos posted at 7 PM perform best”
* “Audience sentiment is mostly positive”
* “Tutorial content gets higher engagement”

---

## 🧠 ML Strategy

### Current:

* Rule-based analytics
* Aggregations

### Optional:

* Clustering (K-Means)
* Regression (Prediction)

---

## 🚀 Development Roadmap

### Day 1:

* Data Fetching + Storage ✅

### Day 2:

* Analytics Engine
* Sentiment Analysis

### Day 3:

* Dashboard (Streamlit)
* Insights + Presentation

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