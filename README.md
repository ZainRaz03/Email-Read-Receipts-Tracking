# 📡 Email Read Receipt Tracking System

**FastAPI + Gmail API + SQLite + Cloudflare Tunnel**

Accurate email open tracking with cache-resistant pixels, real-time analytics, and automatic Sent-folder sanitization.

---

## 🚀 Overview

This project is a from-scratch, privacy-aware, cache-aware email tracking system built using:

* **FastAPI** as the backend
* **Gmail API** for sending & managing emails
* **SQLite** for durable tracking
* **Cloudflare Tunnel** for public HTTPS exposure

It goes far beyond a simple “tracking pixel.”

The system is engineered to work around Gmail’s heavy caching & proxy behavior, ensuring:

✔ Each open event is **real**
✔ Your own Sent-folder opens **never count**
✔ Gmail image caching cannot merge events
✔ High-fidelity metadata for each open

---

## 🌟 Key Features

### 🔹 1. Tracked Email Sending

Send tracked emails with a pixel disguised as a tiny “Sent via Eunoia” logo.

**Endpoint:**
`POST /tracked_email/send`

Includes:

* Custom HTML
* Automatic Gmail OAuth
* Built-in tracking pixel
* Sanitization of Sent-folder copy

---

### 🔹 2. Accurate, Cache-Proof Read Tracking

Each email gets a unique uncacheable pixel URL:

```
t  = tracking token  
eid = internal email ID  
ts = timestamp  
nc = random nonce  
```

The tracking endpoint logs:

* IP
* User-Agent
* Timestamp
* Updates read stats

And returns the logo PNG with **aggressive no-cache headers**:

```
Cache-Control: no-store, no-cache, must-revalidate
Pragma: no-cache
Expires: 0
Vary: User-Agent, Accept
```

---

### 🔹 3. Sent-Folder Sanitization (Zero False Positives)

After sending:

1. Gmail stores the mail (with pixel)
2. We find that original message
3. Delete it
4. Insert a sanitized copy without the pixel

This ensures:

✔ You opening your own sent mail does **not** fire the pixel
✔ No inflated analytics

---

### 🔹 4. Status Dashboard

`GET /status`

Returns:

* Recent tracked emails
* Read status
* Read count
* First/last read timestamps
* Total open events

---

## 🧠 Why This Exists

Email read tracking is unreliable because of:

* Gmail proxy caching
* Pre-fetching
* Browser caching
* Sender opening the Sent folder
* Static pixel URLs

This system fixes all of that using:

✔ Unique URL per email
✔ No-cache responses
✔ Sent-folder sanitization
✔ Durable logging

---

## 🏗 Tech Stack

| Layer       | Technology        |
| ----------- | ----------------- |
| Backend     | FastAPI           |
| Email       | Gmail API (OAuth) |
| Database    | SQLite            |
| Exposure    | Cloudflare Tunnel |
| Environment | dotenv            |
| Runtime     | Uvicorn           |

---

## 📁 Directory Structure

```
Email-Read-Receipts-Tracking/
│
├── Email Assistant/
│   ├── tracked_email_system.py
│   ├── db.py
│
├── start_cloudflare.sh
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🔑 Prerequisites

* Python 3.10+
* Gmail account
* Google Cloud project
* cloudflared installed

---

## ⚙️ Installation

### 1. Clone the repo

```bash
git clone <your-repo-url> Email-Read-Receipts-Tracking
cd Email-Read-Receipts-Tracking
```

### 2. Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 🔐 Gmail API Setup

1. Create project
2. Enable Gmail API
3. Configure OAuth
4. Create Desktop OAuth Client
5. Download & rename to:

```
credentials.json
```

---

## 🧩 Environment Variables

`.env` example:

```
SENDER_EMAIL=youremail@gmail.com
GMAIL_CREDENTIALS_FILE=credentials.json
GMAIL_TOKEN_FILE=token_send.json
TRACKING_BASE_URL=https://your-subdomain.trycloudflare.com
```

---

## ▶️ Running the Server

```bash
uvicorn "tracked_email_system:app" \
  --app-dir "Email Assistant" \
  --host 0.0.0.0 \
  --port 8003 \
  --reload
```

---

## 🌐 Expose Public URL (Cloudflare Tunnel)

```bash
bash start_cloudflare.sh
```

---

## 🗄 Database Schema

### `tracked_emails`

Tracks each email.

| Field            | Description      |
| ---------------- | ---------------- |
| id               | PK               |
| tracking_id      | Unique per email |
| recipient        | Email            |
| subject          | Subject          |
| sent_at          | Timestamp        |
| gmail_message_id | Gmail ID         |
| is_read          | 0/1              |
| read_at          | First open       |
| last_read_at     | Latest           |
| read_count       | Total            |

### `email_opens`

| Field       | Description |
| ----------- | ----------- |
| id          | PK          |
| tracking_id | Ref         |
| opened_at   | Timestamp   |
| user_agent  | UA          |
| ip_address  | IP          |

---

## 📡 API Endpoints

### 🔸 Send Email

`POST /tracked_email/send`

```json
{
  "to": "someone@example.com",
  "subject": "Hello!",
  "html_body": "<p>Hello from Eunoia</p>"
}
```

### 🔸 Tracking Pixel

`GET /app/v1/bulkemail/email-read-receipt/?t=...`

### 🔸 Status Dashboard

`GET /status`

---

## 🔒 Security Notes

* Uses full Gmail mail scope
* Never commit `.env` or `credentials.json`
* Use test Gmail account
* Quick tunnels are not production-secure

---

