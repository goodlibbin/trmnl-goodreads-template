import re
import requests
from flask import Flask, jsonify, request
from bs4 import BeautifulSoup
import feedparser
import os
from datetime import datetime, timedelta
import hashlib
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import random

app = Flask(__name__)

# Configure caching to reduce server load and improve performance
cache = Cache(app, config={
    'CACHE_TYPE': 'simple',
    'CACHE_DEFAULT_TIMEOUT': 1800  # 30 minutes
})

# Configure rate limiting to prevent abuse
limiter = Limiter(
    app=app,
    key_func=lambda: hashlib.md5(
        request.args.get('rss_url', 'demo').encode()
    ).hexdigest()[:8],
    default_limits=["1000 per day", "100 per hour"],
    storage_uri="memory://"
)

# Sample books for demo mode
DEMO_BOOKS = [
    {
        "title": "The Midnight Library",
        "author": "Matt Haig",
        "pages": 288
    },
    {
        "title": "Project Hail Mary",
        "author": "Andy Weir",
        "pages": 476
    },
    {
        "title": "Klara and the Sun",
        "author": "Kazuo Ishiguro",
        "pages": 303
    },
    {
        "title": "The Seven Husbands of Evelyn Hugo",
        "author": "Taylor Jenkins Reid",
        "pages": 400
    },
    {
        "title": "Atomic Habits",
        "author": "James Clear",
        "pages": 320
    }
]

def generate_demo_data():
    """Generate sample data for demonstration purposes"""
    # Use date as seed for consistent daily data
    today = datetime.now().date()
    random.seed(str(today))
    
    # Select a book for today
    book = random.choice(DEMO_BOOKS)
    
    # Generate realistic progress
    base_progress = random.randint(15, 85)
    hour = datetime.now().hour
    progress = min(base_progress + (hour * 2), 95)
    
    # Generate dates
    days_ago = random.randint(3, 14)
    start_date = datetime.now() - timedelta(days=days_ago)
    update_date = datetime.now() - timedelta(hours=random.randint(1, 24))
    
    # Generate challenge data
    current_books = random.randint(15, 45)
    goal_books = random.randint(50, 100)
    
    return {
        "title": book["title"],
        "author": book["author"],
        "progress": progress,
        "start_date": start_date.strftime("%b %d, %Y"),
        "update_date": update_date.strftime("%b %d, %Y"),
        "challenge": f"{current_books} of {goal_books} books",
        "challenge_progress_percent": int((current_books / goal_books) * 100),
        "entries_count": random.randint(2, 5),
        "current_time": datetime.now().strftime('%m/%d %H:%M'),
        "is_demo": True
    }

def extract_author_from_entry(entry):
    """Extract author name from RSS entry"""
    try:
        # First, check for author links in description
        if hasattr(entry, 'description'):
            soup = BeautifulSoup(entry.description, 'html.parser')
            author_link = soup.find('a', href=re.compile(r'/author/'))
            if author_link:
                return author_link.get_text().strip()
            
            # Also check for "by Author Name" pattern in description
            desc_text = soup.get_text()
            by_match = re.search(r' by ([^<\n]+?)(?:\s*<|$)', desc_text)
            if by_match:
                author_name = by_match.group(1).strip()
                if author_name and len(author_name) > 1:
                    return author_name
    except:
        pass
    
    # Fallback: try to parse from title
    title = ' '.join(entry.title.split())  # Clean up multi-line titles
    if " by " in title:
        return title.split(" by ")[-1].split("(")[0].strip()
    
    return "Unknown Author"

def extract_progress_from_entry(entry):
    """Extract reading progress percentage from RSS entry"""
    # Clean up title - remove newlines and extra spaces
    title = ' '.join(entry.title.split())
    
    # Look for percentage
    match = re.search(r'(\d+)%', title)
    if match:
        return min(int(match.group(1)), 100)
    
    # Look for page numbers
    match = re.search(r'page (\d+) of (\d+)', title, re.IGNORECASE)
    if match:
        current = int(match.group(1))
        total = int(match.group(2))
        if total > 0:
            return min(int((current / total) * 100), 100)
    
    return 0

def extract_user_id_from_rss(rss_url):
    """Extract user ID from RSS URL"""
    match = re.search(r'/user/updates_rss/(\d+)', rss_url)
    if match:
        return match.group(1)
    return None

def fetch_challenge_stats(rss_url, user_id):
    """Fetch reading challenge statistics"""
    if not user_id:
        return None
    
    try:
        # Check Goodreads profile page for challenge data
        profile_url = f"https://www.goodreads.com/user/show/{user_id}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        
        response = requests.get(profile_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for reading challenge widget
            challenge_widget = soup.find('div', class_='challengePic')
            if challenge_widget:
                # Extract text from the challenge widget
                challenge_text = challenge_widget.get_text()
                
                # Try various patterns
                patterns = [
                    r'(\d+)\s+of\s+(\d+)',
                    r'(\d+)/(\d+)',
                    r'Read\s+(\d+)\s+of\s+(\d+)',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, challenge_text)
                    if match:
                        books_read = int(match.group(1))
                        books_goal = int(match.group(2))
                        return f"{books_read} of {books_goal} books"
            
            # Alternative: look for year challenge link
            current_year = datetime.now().year
            challenge_link = soup.find('a', href=re.compile(f'/user_challenges/{user_id}.*year={current_year}'))
            if challenge_link:
                challenge_text = challenge_link.get_text()
                match = re.search(r'(\d+)\s+of\s+(\d+)', challenge_text)
                if match:
                    return f"{match.group(1)} of {match.group(2)} books"
    
    except Exception as e:
        print(f"Error fetching challenge data: {e}")
    
    return None

@cache.memoize(timeout=1800)
def fetch_goodreads_data(rss_url):
    """Fetch and process Goodreads RSS feed data"""
    try:
        # Parse RSS feed
        feed = feedparser.parse(rss_url)
        if not feed.entries:
            return None
        
        # Extract user ID for challenge data
        user_id = extract_user_id_from_rss(rss_url)
        
        # Look for current book with progress
        current_book = None
        for entry in feed.entries[:20]:  # Check first 20 entries
            # Clean up title - remove newlines and extra spaces
            title = ' '.join(entry.title.split())
            title_lower = title.lower()
            
            # Check for reading progress indicators
            if any(phrase in title_lower for phrase in ["currently reading", "is on page", "% done", "progress", "done with"]):
                # Try single quotes first
                book_match = re.search(r"'([^']+)'", title)
                if not book_match:
                    # Pattern for "is X% done with BOOK TITLE"
                    book_match = re.search(r"done with (.+?)$", title)
                
                if book_match:
                    current_book = {
                        "title": book_match.group(1).strip(),
                        "author": extract_author_from_entry(entry),
                        "progress": extract_progress_from_entry(entry),
                        "entry": entry
                    }
                    break
        
        # If no current book with progress, find most recent "started reading"
        if not current_book:
            for entry in feed.entries[:10]:
                # Clean up title
                title = ' '.join(entry.title.split())
                if "started reading" in title.lower():
                    book_match = re.search(r"'([^']+)'", title)
                    if book_match:
                        current_book = {
                            "title": book_match.group(1),
                            "author": extract_author_from_entry(entry),
                            "progress": 0,
                            "entry": entry
                        }
                        break
        
        # If we have a current book but no author, try to find it from other entries
        if current_book and current_book["author"] == "Unknown Author":
            book_title_lower = current_book["title"].lower()
            for entry in feed.entries[:30]:
                title = ' '.join(entry.title.split())
                if book_title_lower in title.lower():
                    author = extract_author_from_entry(entry)
                    if author != "Unknown Author":
                        current_book["author"] = author
                        break
        
        if not current_book:
            return None
        
        # Extract dates
        start_date = current_book["entry"].published if hasattr(current_book["entry"], 'published') else None
        
        # Fetch reading challenge data
        challenge = fetch_challenge_stats(rss_url, user_id)
        
        return {
            "title": current_book["title"],
            "author": current_book["author"],
            "progress": current_book["progress"],
            "start_date": start_date,
            "challenge": challenge
        }
        
    except Exception as e:
        print(f"Error fetching RSS data: {e}")
        return None

def format_date(dt):
    """Format date for display"""
    if not dt:
        return "Unknown"
    try:
        if isinstance(dt, str):
            return datetime.strptime(dt, "%a, %d %b %Y %H:%M:%S %z").strftime("%b %d, %Y")
        return dt.strftime("%b %d, %Y")
    except:
        return "Unknown"

# Routes

@app.route("/")
def home():
    """Home page with demo and instructions"""
    demo_data = generate_demo_data()
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>TRMNL Goodreads Display</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body{{font-family:system-ui,-apple-system,sans-serif;max-width:800px;margin:0 auto;padding:20px;line-height:1.6;color:#333}}
            h1{{color:#2c3e50;border-bottom:2px solid #e1e4e8;padding-bottom:10px}}
            .demo{{background:#f6f8fa;border:1px solid #e1e4e8;padding:20px;border-radius:8px;margin:20px 0}}
            .book-display{{background:#fff;border:1px solid #e1e4e8;padding:20px;border-radius:6px;margin:10px 0}}
            .progress-bar{{width:100%;height:20px;background:#e1e4e8;border-radius:10px;overflow:hidden;margin:10px 0}}
            .progress-fill{{height:100%;background:#28a745;transition:width 0.3s}}
            code{{background:#f6f8fa;padding:2px 6px;border-radius:3px;font-family:monospace;font-size:14px}}
            .notice{{background:#fff5b1;border:1px solid #f0c36d;padding:15px;border-radius:6px;margin:20px 0}}
            .feature{{background:#f0f7ff;border-left:4px solid #0366d6;padding:10px 15px;margin:8px 0}}
            .button{{display:inline-block;padding:8px 16px;background:#0366d6;color:white;text-decoration:none;border-radius:6px;margin:5px 0}}
            .button:hover{{background:#0256c7}}
            footer{{margin-top:40px;padding-top:20px;border-top:1px solid #e1e4e8;text-align:center;color:#666}}
        </style>
    </head>
    <body>
        <h1>📚 TRMNL Goodreads Display</h1>
        
        <div class="demo">
            <h2>Live Demo</h2>
            <div class="book-display">
                <h3>{demo_data['title']}</h3>
                <p><strong>by {demo_data['author']}</strong></p>
                <div class="progress-bar">
                    <div class="progress-fill" style="width:{demo_data['progress']}%"></div>
                </div>
                <p><strong>{demo_data['progress']}%</strong> complete</p>
                <p>📅 Started: {demo_data['start_date']} | Updated: {demo_data['update_date']}</p>
                <p>🎯 <strong>2025 Reading Challenge:</strong> {demo_data['challenge']}</p>
            </div>
            <p><small>Demo data updates daily. <a href="/trmnl-data?demo=true">View JSON API</a></small></p>
        </div>
        
        <div class="notice">
            <h3>🎯 How to Use This Recipe</h3>
            <ol>
                <li>Install the "Goodreads Reading Progress" recipe in TRMNL</li>
                <li>Enter your Goodreads RSS URL when prompted</li>
                <li>Your reading progress will update automatically!</li>
            </ol>
            <p><strong>Find your RSS URL:</strong> Go to your Goodreads profile → Settings → RSS feed (must be public)</p>
        </div>
        
        <h3>✨ Features</h3>
        <div class="feature">📖 Displays your current book with real-time reading progress</div>
        <div class="feature">📊 Shows progress bars for both book and yearly reading challenge</div>
        <div class="feature">📅 Tracks when you started and last updated your book</div>
        <div class="feature">🔄 Updates automatically every time your TRMNL refreshes</div>
        
        <h3>🔧 Technical Details</h3>
        <p>This service provides a JSON API that TRMNL polls to get your reading data:</p>
        <code>/trmnl-data?rss_url=YOUR_GOODREADS_RSS_URL</code>
        
        <h3>🔒 Privacy & Performance</h3>
        <ul>
            <li>Your RSS URL is only used to fetch your reading data</li>
            <li>Data is cached for 30 minutes to reduce load</li>
            <li>No personal information is stored</li>
            <li>Rate limited to prevent abuse</li>
        </ul>
        
        <p style="text-align:center;margin-top:30px">
            <a href="/trmnl-data?demo=true" class="button">View Demo API Response</a>
        </p>
        
        <footer>
            <p>Built with ❤️ for the TRMNL community | <a href="https://github.com/goodlibbin/trmnl-goodreads-recipe">View on GitHub</a></p>
        </footer>
    </body>
    </html>
    """

@app.route("/trmnl-data")
@limiter.limit("20 per minute")
def serve_trmnl_data():
    """Main API endpoint for TRMNL to poll"""
    # Check if demo mode is requested
    if request.args.get('demo') == 'true':
        return jsonify(generate_demo_data())
    
    # Get RSS URL from query parameter
    rss_url = request.args.get('rss_url', '').strip()
    
    # Validate RSS URL
    if not rss_url or not rss_url.startswith('https://www.goodreads.com/user/updates_rss/'):
        # Return demo data if no valid URL provided
        return jsonify(generate_demo_data())
    
    # Fetch cached data
    book_data = fetch_goodreads_data(rss_url)
    
    if not book_data:
        # Return graceful fallback
        return jsonify({
            "title": "No current book found",
            "author": "Start reading on Goodreads",
            "progress": 0,
            "start_date": "Unknown",
            "update_date": "Unknown", 
            "challenge": None,
            "challenge_progress_percent": 0,
            "entries_count": 0,
            "current_time": datetime.now().strftime('%m/%d %H:%M')
        })
    
    # Calculate challenge progress percentage
    challenge_progress_percent = 0
    if book_data.get('challenge'):
        try:
            parts = book_data['challenge'].split(' of ')
            if len(parts) == 2:
                current = int(parts[0])
                total = int(parts[1].split(' ')[0])
                challenge_progress_percent = min(int((current / total) * 100), 100)
        except:
            pass
    
    # Format response for TRMNL
    response = {
        "title": book_data.get('title', 'Unknown Title'),
        "author": book_data.get('author', 'Unknown Author'),
        "progress": book_data.get('progress', 0),
        "start_date": format_date(book_data.get('start_date')),
        "update_date": format_date(book_data.get('start_date')),  # Using start_date as update for simplicity
        "challenge": book_data.get('challenge'),
        "challenge_progress_percent": challenge_progress_percent,
        "entries_count": 1,
        "current_time": datetime.now().strftime('%m/%d %H:%M')
    }
    
    return jsonify(response)

@app.route("/health")
def health():
    """Health check endpoint for monitoring"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route("/clear-cache")
def clear_cache():
    """Clear all cached data"""
    cache.clear()
    return jsonify({"status": "cache cleared", "timestamp": datetime.now().isoformat()})

@app.errorhandler(429)
def ratelimit_handler(e):
    """Handle rate limit exceeded errors"""
    return jsonify({
        "error": "Rate limit exceeded",
        "message": "Please try again in a few minutes"
    }), 429

if __name__ == "__main__":
    print("🚀 Starting TRMNL Goodreads Recipe Server")
    print("📚 Visit http://localhost:5001 to see the demo")
    
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
