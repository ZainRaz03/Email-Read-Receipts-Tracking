import base64
import datetime
import logging
import os
import sqlite3
import time
import uuid
from email.message import EmailMessage
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
import requests
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pydantic import BaseModel, EmailStr

DB_FILE = "email_assistant.db"


load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Tracked Email System")

print("\n" + "="*80)
print("🚀 TRACKED EMAIL SYSTEM STARTING")
print("="*80)
tracking_url = os.getenv("TRACKING_BASE_URL", "")
if not tracking_url:
    print("⚠️  WARNING: TRACKING_BASE_URL is NOT set - pixels will NOT be embedded!")
else:
    print(f"✅ TRACKING_BASE_URL: {tracking_url}")
print(f"✅ DB path: {os.path.abspath(DB_FILE)}")
print(f"✅ SENDER_EMAIL: {os.getenv('SENDER_EMAIL', 'NOT SET')}")
print("="*80 + "\n")

DEFAULT_LOGO_URL = (
    "https://media.licdn.com/dms/image/v2/D4D0BAQGpJ-n5KsNMEQ/company-logo_100_100/"
    "company-logo_100_100/0/1730288525595/eunoia_app_logo"
    "?e=1765411200&v=beta&t=OSEILLfhBQsaI2Px4YnNkxcAdDQV_W4rR_OJWC5rLpk"
)


SCOPES = ["https://mail.google.com/"]


def _load_gmail_credentials() -> Credentials:
    """
    Load or create OAuth2 credentials for the Gmail API.
    Uses GMAIL_CREDENTIALS_FILE and GMAIL_TOKEN_FILE from env or defaults.
    """
    creds: Optional[Credentials] = None
    credentials_file = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
    token_file = os.getenv("GMAIL_TOKEN_FILE", "token_send.json")

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=8080, access_type="offline", prompt="consent")

        with open(token_file, "w") as token:
            token.write(creds.to_json())

    return creds


def get_gmail_service():
    creds = _load_gmail_credentials()
    service = build("gmail", "v1", credentials=creds)
    return service


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(os.path.abspath(DB_FILE))


def init_tracking_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tracked_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_id TEXT UNIQUE,
            recipient TEXT,
            subject TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            gmail_message_id TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS email_opens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_id TEXT,
            opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_agent TEXT,
            ip_address TEXT
        )
        """
    )

    cursor.execute("PRAGMA table_info(tracked_emails)")
    columns = [row[1] for row in cursor.fetchall()]
    if "is_read" not in columns:
        cursor.execute("ALTER TABLE tracked_emails ADD COLUMN is_read INTEGER DEFAULT 0")
    if "read_at" not in columns:
        cursor.execute("ALTER TABLE tracked_emails ADD COLUMN read_at TIMESTAMP")
    if "last_read_at" not in columns:
        cursor.execute("ALTER TABLE tracked_emails ADD COLUMN last_read_at TIMESTAMP")
    if "read_count" not in columns:
        cursor.execute("ALTER TABLE tracked_emails ADD COLUMN read_count INTEGER DEFAULT 0")

    conn.commit()
    conn.close()


init_tracking_db()


class SendTrackedEmailRequest(BaseModel):
    to: EmailStr
    subject: str
    html_body: str 


def _build_email_html(tracking_id: str, email_db_id: int, req: SendTrackedEmailRequest) -> tuple[str, str]:
    """
    Build two HTML variants:
    - with tracking logo (for the recipient) - the logo itself tracks opens
    - sanitized (static logo) for the Sent copy

    The visible logo is loaded through our tracking endpoint, which:
    1. Records the open event
    2. Returns the actual logo image (proxied or hosted)
    """
    base_html = req.html_body.strip()
    tracking_base = os.getenv("TRACKING_BASE_URL", "").rstrip("/")
    static_logo_url = os.getenv("TRACKING_LOGO_URL", DEFAULT_LOGO_URL)

    if not tracking_base:
        logger.warning("TRACKING_BASE_URL is empty; sending email WITHOUT tracking")
        logo_block = (
            f'<div style="margin-top:20px;text-align:center;">'
            f'<img src="{static_logo_url}" alt="Zain" '
            f'style="display:block;width:60px;height:auto;margin:0 auto;border-radius:8px;" />'
            f'<p style="margin:8px 0 0 0;font-size:12px;color:#666;font-family:Arial,sans-serif;">'
            f"Sent via Zain</p>"
            f"</div>"
        )
        full_html = base_html + "\n" + logo_block
        return full_html, full_html

    ts = int(datetime.datetime.utcnow().timestamp() * 1000)
    nonce = uuid.uuid4().hex
    tracking_logo_url = (
        f"{tracking_base}/app/v1/bulkemail/email-read-receipt/"
        f"?t={tracking_id}&eid={email_db_id}&ts={ts}&nc={nonce}"
    )

    logo_block_tracked = (
        f'<div style="margin-top:20px;text-align:center;">'
        f'<img src="{tracking_logo_url}" alt="Zain" '
        f'style="display:block;width:60px;height:auto;margin:0 auto;border-radius:8px;" />'
        f'<p style="margin:8px 0 0 0;font-size:12px;color:#666;font-family:Arial,sans-serif;">'
        f"Sent via Zain</p>"
        f"</div>"
    )

    logo_block_static = (
        f'<div style="margin-top:20px;text-align:center;">'
        f'<img src="{static_logo_url}" alt="Zain" '
        f'style="display:block;width:60px;height:auto;margin:0 auto;border-radius:8px;" />'
        f'<p style="margin:8px 0 0 0;font-size:12px;color:#666;font-family:Arial,sans-serif;">'
        f"Sent via Zain</p>"
        f"</div>"
    )

    html_with_tracking = base_html + "\n" + logo_block_tracked
    html_sanitized = base_html + "\n" + logo_block_static

    return html_with_tracking, html_sanitized


def _build_raw_message(from_addr: str, to_addr: str, subject: str, html_body: str) -> str:
    msg = EmailMessage()
    msg["To"] = to_addr
    msg["From"] = from_addr
    msg["Subject"] = subject
    msg.set_content("This email requires an HTML-capable client.")
    msg.add_alternative(html_body, subtype="html")

    raw_bytes = msg.as_bytes()
    raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")
    return raw_b64


@app.post("/tracked_email/send")
def send_tracked_email(req: SendTrackedEmailRequest):
    """
    Send an email via Gmail API with:
    - Zain logo appended at the bottom
    - Tracking pixel that hits /track/open/{tracking_id}.png

    After sending:
    - Delete the original Sent copy
    - Insert a sanitized Sent copy without the tracking pixel
    """
    sender_email = os.getenv("SENDER_EMAIL")
    if not sender_email:
        raise HTTPException(status_code=500, detail="SENDER_EMAIL not configured in .env")

    tracking_id = uuid.uuid4().hex

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tracked_emails (tracking_id, recipient, subject)
        VALUES (?, ?, ?)
        """,
        (tracking_id, str(req.to), req.subject),
    )
    email_db_id = cursor.lastrowid
    conn.commit()
    conn.close()

    html_with_pixel, html_sanitized = _build_email_html(tracking_id, email_db_id, req)

    service = get_gmail_service()

    raw_with_pixel = _build_raw_message(
        from_addr=sender_email,
        to_addr=req.to,
        subject=req.subject,
        html_body=html_with_pixel,
    )

    try:
        sent_msg = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw_with_pixel})
            .execute()
        )
    except Exception as e:
        logger.error(f"Error sending tracked email via Gmail API: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Gmail send failed")

    gmail_message_id = sent_msg.get("id")

    if gmail_message_id:
        time.sleep(0.5)
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"   🗑️  Attempting to delete original sent message (attempt {attempt + 1}/{max_retries})...")
                service.users().messages().delete(userId="me", id=gmail_message_id).execute()
                print(f"   ✅ Original sent message deleted successfully")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"   ⚠️  Delete failed (attempt {attempt + 1}): {e}")
                    print(f"   🔄 Retrying in {1 + attempt} seconds...")
                    time.sleep(1 + attempt)  # Exponential backoff: 1s, 2s
                else:
                    print(f"   ❌ Could not delete original sent message after {max_retries} attempts: {e}")
                    logger.warning(f"Could not delete original sent message after {max_retries} attempts: {e}")

    raw_sanitized = _build_raw_message(
        from_addr=sender_email,
        to_addr=req.to,
        subject=req.subject,
        html_body=html_sanitized,
    )
    try:
        service.users().messages().insert(
            userId="me",
            body={"raw": raw_sanitized, "labelIds": ["SENT"]},
        ).execute()
    except Exception as e:
        logger.warning(f"Could not insert sanitized Sent copy: {e}")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tracked_emails SET gmail_message_id = ? WHERE tracking_id = ?",
        (gmail_message_id, tracking_id),
    )
    conn.commit()
    conn.close()

    return {"tracking_id": tracking_id, "gmail_message_id": gmail_message_id}


def _record_open(tracking_id: str, ua: str, client_ip: str):
    """
    Record an open event in email_opens and update aggregated stats in tracked_emails.
    """
    print(f"\n{'='*80}")
    print(f"📧 EMAIL OPENED!")
    print(f"   tracking_id: {tracking_id}")
    print(f"   User-Agent: {ua[:100]}")
    print(f"   IP: {client_ip}")
    print(f"{'='*80}\n")
    
    now = datetime.datetime.utcnow().isoformat(sep=" ")
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO email_opens (tracking_id, opened_at, user_agent, ip_address)
        VALUES (?, ?, ?, ?)
        """,
        (tracking_id, now, ua, client_ip),
    )
    print(f"✅ Recorded open event in email_opens table")

    # Update aggregate stats
    cursor.execute(
        """
        SELECT is_read, read_at, last_read_at, read_count
        FROM tracked_emails
        WHERE tracking_id = ?
        """,
        (tracking_id,),
    )
    row = cursor.fetchone()
    if row is not None:
        is_read, read_at, last_read_at, read_count = row
        read_count = (read_count or 0) + 1
        if not is_read:
            read_at = now
            is_read = 1
            print(f"✅ FIRST READ - Marking as read!")
        else:
            print(f"✅ Additional read (count now: {read_count})")
        last_read_at = now
        cursor.execute(
            """
            UPDATE tracked_emails
            SET is_read = ?, read_at = ?, last_read_at = ?, read_count = ?
            WHERE tracking_id = ?
            """,
            (is_read, read_at, last_read_at, read_count, tracking_id),
        )
        print(f"✅ Updated tracked_emails: is_read={is_read}, read_count={read_count}")
    else:
        print(f"⚠️  WARNING: No tracked_emails row found for tracking_id={tracking_id}")

    conn.commit()
    conn.close()
    print(f"{'='*80}\n")


def _proxy_logo_response() -> Response:
    """
    Return the actual logo image with aggressive no-cache headers.
    This is what gets loaded when the email is opened - a visible logo that tracks.
    
    Cache-busting strategy:
    - Each email has unique query params (timestamp in ms + nonce)
    - Strong no-cache headers prevent Gmail proxy from caching
    - Vary header forces fresh request for different query params
    """
    logo_url = os.getenv("TRACKING_LOGO_URL", DEFAULT_LOGO_URL)
    
    try:
        print(f"   📥 Fetching logo from: {logo_url[:80]}...")
        r = requests.get(logo_url, timeout=5)
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "image/png")
        print(f"   ✅ Logo fetched successfully ({len(r.content)} bytes, {content_type})")
        
        return Response(
            content=r.content,
            media_type=content_type,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
                "Content-Disposition": "inline",
                "Vary": "User-Agent, Accept",  
                "X-Robots-Tag": "noindex, nofollow",  
            },
        )
    except Exception as e:
        print(f"   ⚠️  Error fetching logo: {e}")
        print(f"   📤 Returning fallback 1x1 transparent GIF")
        transparent_gif = base64.b64decode(
            "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
        )
        return Response(
            content=transparent_gif,
            media_type="image/gif",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
                "Content-Disposition": "inline",
                "Vary": "User-Agent, Accept",
                "X-Robots-Tag": "noindex, nofollow",
            },
        )


@app.get("/app/v1/bulkemail/email-read-receipt/")
async def email_read_receipt(request: Request):
    """
    Read receipt endpoint, modeled after the office Django view:
    ?t=<tracking_token>&eid=<email_id>&ts=<timestamp>&nc=<nonce>
    """
    params = request.query_params
    tracking_id = params.get("t")
    eid = params.get("eid")

    ua = request.headers.get("User-Agent", "")
    client_ip = request.client.host if request.client else ""
    
    print(f"\n🔔 READ RECEIPT HIT: eid={eid}, t={tracking_id[:16] if tracking_id else None}..., IP={client_ip}")
    print(f"   User-Agent: {ua[:100]}")

    if eid and eid.isdigit():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tracking_id FROM tracked_emails WHERE id = ?",
            (int(eid),),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            tracking_id = row[0]
            print(f"   ✅ Found tracking_id from eid={eid}: {tracking_id}")

    if tracking_id:
        _record_open(tracking_id, ua, client_ip)
    else:
        print(f"   ⚠️  No tracking_id found - skipping record")

    return _proxy_logo_response()


@app.get("/track/open/{tracking_id}.png")
async def track_open(tracking_id: str, request: Request):
    """
    Legacy tracking pixel endpoint.
    Logs an open event and returns the logo (or transparent PNG fallback).
    """
    ua = request.headers.get("User-Agent", "")
    client_ip = request.client.host if request.client else ""
    _record_open(tracking_id, ua, client_ip)
    return _proxy_logo_response()


@app.get("/status")
def status():
    """Quick status check showing recent tracked emails and their read status."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, tracking_id, recipient, subject, is_read, read_count, 
               sent_at, read_at, last_read_at
        FROM tracked_emails
        ORDER BY id DESC
        LIMIT 10
        """
    )
    rows = cursor.fetchall()
    emails = []
    for row in rows:
        emails.append({
            "id": row[0],
            "tracking_id": row[1],
            "recipient": row[2],
            "subject": row[3],
            "is_read": bool(row[4]),
            "read_count": row[5] or 0,
            "sent_at": row[6],
            "read_at": row[7],
            "last_read_at": row[8],
        })
    
    cursor.execute("SELECT COUNT(*) FROM email_opens")
    total_opens = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "status": "running",
        "tracking_base_url": os.getenv("TRACKING_BASE_URL", "NOT SET"),
        "db_path": os.path.abspath(DB_FILE),
        "total_opens": total_opens,
        "recent_emails": emails,
    }


