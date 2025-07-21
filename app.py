import re
import requests
from flask import Flask, jsonify, request
from bs4 import BeautifulSoup
import feedparser
import os
from datetime import datetime, timedelta
from functools import wraps
import hashlib

app = Flask(__name__)

# Simple in-memory caching system
cache_storage = {}

def cache_with_timeout(timeout_minutes):
    """
    A simple caching decorator that stores results in memory.
    Helps reduce API calls and improve response times.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create a unique cache key
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Check if we have a valid cached result
            if cache_key in cache_storage:
                result, timestamp = cache_storage[cache_key]
                if datetime.now() - timestamp < timedelta(minutes=timeout_minutes):
                    print(f"Cache hit for {func.__name__}")
                    return result
            
            # Call the function and cache the result
            print(f"Cache miss for {func.__name__}, fetching fresh data")
            result = func(*args, **kwargs)
            cache_storage[cache_key] = (result, datetime.now())
            return result
        return wrapper
    return decorator

def extract_author_from_entry(entry):
    """
    Extract author name from RSS entry using multiple strategies.
    Returns the most likely author name or 'Unknown Author' if not found.
    """
    try:
        # Strategy 1: Look for author links in the HTML description
        if hasattr(entry, 'description'):
            soup = BeautifulSoup(entry.description, 'html.parser')
            author_link = soup.find('a', href=re.compile(r'/author/'))
            if author_link:
                author_name = author_link.get_text().strip()
                if author_name and len(author_name) > 1:
                    return author_name
            
            # Strategy 2: Look for "by Author" pattern in description
            desc_text = soup.get_text()
            by_match = re.search(r' by ([^<\n]+?)(?:\s*<|$)', desc_text)
            if by_match:
                author_name = by_match.group(1).strip()
                if author_name and len(author_name) > 1:
                    return author_name
    except Exception as e:
        print(f"Author extraction error: {e}")
    
    # Strategy 3: Parse from title
    title = ' '.join(entry.title.split())
    if " by " in title:
        return title.split(" by ")[-1].split("(")[0].strip()
    
    return "Unknown Author"

def extract_progress_from_entry(entry):
    """
    Extract reading progress percentage from RSS entry.
    Handles various formats like "25%" or "page 50 of 200".
    """
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
    """Extract Goodreads user ID from RSS URL."""
    match = re.search(r'/user/updates_rss/(\d+)', rss_url)
    if match:
        return match.group(1)
    return None

def fetch_challenge_stats(user_id):
    """
    Fetch reading challenge statistics from Goodreads profile page.
    Returns formatted string like "15 of 25 books" or None if not found.
    """
    if not user_id:
        return None
    
    try:
        profile_url = f"https://www.goodreads.com/user/show/{user_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        
        response = requests.get(profile_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for the challenge progress link
            challenge_link = soup.find('a', class_='challengeBooksRead')
            if challenge_link:
                challenge_text = challenge_link.get_text()
                # Extract "X books of your goal of Y" pattern
                patterns = [
                    r'read (\d+) books? of your goal of (\d+)',
                    r'read (\d+) of (\d+) books',
                    r'(\d+) books? of (?:your goal of )?(\d+)'
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, challenge_text, re.IGNORECASE)
                    if match:
                        books_read = int(match.group(1))
                        books_goal = int(match.group(2))
                        return f"{books_read} of {books_goal} books"
            
            # Alternative: Look in the year challenge module
            current_year = datetime.now().year
            challenge_modules = soup.find_all('div', id=re.compile(r'user_challenge_\d+'))
            
            for module in challenge_modules:
                module_text = module.get_text()
                if str(current_year) in module_text:
                    # Try various patterns
                    patterns = [
                        r'read (\d+) books? of your goal of (\d+)',
                        r'(\d+) of (\d+) books',
                        r'(\d+) books? .*?goal.*?(\d+)'
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, module_text, re.IGNORECASE)
                        if match:
                            return f"{match.group(1)} of {match.group(2)} books"
            
            print(f"Challenge data not found on profile page for user {user_id}")
            
    except Exception as e:
        print(f"Error fetching challenge data: {e}")
    
    return None

@cache_with_timeout(30)
def fetch_goodreads_data(rss_url):
    """
    Fetch and process Goodreads RSS feed data.
    Returns book information and reading challenge progress.
    """
    try:
        # Parse RSS feed
        feed = feedparser.parse(rss_url)
        if not feed.entries:
            print("No entries found in RSS feed")
            return None
        
        # Extract user ID for challenge data
        user_id = extract_user_id_from_rss(rss_url)
        
        # Look for current book with progress
        current_book = None
        
        # Check first 20 entries for reading activity
        for entry in feed.entries[:20]:
            title = ' '.join(entry.title.split())
            title_lower = title.lower()
            
            # Check for reading progress indicators
            if any(phrase in title_lower for phrase in ["currently reading", "is on page", "% done", "progress", "done with"]):
                # Extract book title
                book_match = re.search(r"'([^']+)'", title)
                if not book_match:
                    # Try alternative pattern
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
        
        if not current_book:
            print("No current book found in RSS feed")
            return None
        
        # Extract dates
        start_date = current_book["entry"].published if hasattr(current_book["entry"], 'published') else None
        
        # Fetch reading challenge data
        challenge = fetch_challenge_stats(user_id)
        
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
    """Format date for display in a user-friendly way."""
    if not dt:
        return "Unknown"
    try:
        if isinstance(dt, str):
            parsed_date = datetime.strptime(dt, "%a, %d %b %Y %H:%M:%S %z")
            return parsed_date.strftime("%b %d, %Y")
        return dt.strftime("%b %d, %Y")
    except:
        return "Unknown"

def generate_demo_data():
    """Generate sample data for demonstration purposes."""
    import random
    
    demo_books = [
        {"title": "The Midnight Library", "author": "Matt Haig"},
        {"title": "Project Hail Mary", "author": "Andy Weir"},
        {"title": "Klara and the Sun", "author": "Kazuo Ishiguro"},
        {"title": "The Seven Husbands of Evelyn Hugo", "author": "Taylor Jenkins Reid"},
        {"title": "Atomic Habits", "author": "James Clear"}
    ]
    
    # Use current time as seed for consistent daily data
    today = datetime.now().date()
    random.seed(str(today))
    
    book = random.choice(demo_books)
    progress = random.randint(15, 85)
    
    # Generate dates
    days_ago = random.randint(3, 14)
    start_date = datetime.now() - timedelta(days=days_ago)
    
    # Generate challenge data
    current_books = random.randint(15, 45)
    goal_books = random.randint(50, 100)
    
    return {
        "title": book["title"],
        "author": book["author"],
        "progress": progress,
        "start_date": start_date.strftime("%b %d, %Y"),
        "update_date": start_date.strftime("%b %d, %Y"),
        "challenge": f"{current_books} of {goal_books} books",
        "challenge_progress_percent": int((current_books / goal_books) * 100),
        "current_time": datetime.now().strftime('%m/%d %H:%M'),
        "is_demo": True
    }

# Routes

@app.route("/")
def home():
    """Home page with information about the TRMNL Goodreads Recipe."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>TRMNL Goodreads Recipe</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: system-ui, -apple-system, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; }
            h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
            .demo { background: #f6f8fa; border: 1px solid #e1e4e8; padding: 20px; border-radius: 8px; margin: 20px 0; }
            .notice { background: #fff5b1; border: 1px solid #f0c36d; padding: 15px; border-radius: 6px; margin: 20px 0; }
            .feature { background: #f0f7ff; border-left: 4px solid #0366d6; padding: 10px 15px; margin: 8px 0; }
            code { background: #f6f8fa; padding: 2px 6px; border-radius: 3px; font-family: monospace; font-size: 14px; }
            .button { display: inline-block; padding: 8px 16px; background: #0366d6; color: white; text-decoration: none; border-radius: 6px; margin: 5px 0; }
            .button:hover { background: #0256c7; }
        </style>
    </head>
    <body>
        <h1>📚 TRMNL Goodreads Recipe</h1>
        
        <div class="notice">
            <h3>🎯 How to Use This Recipe</h3>
            <ol>
                <li>Install the "Goodreads Reading Progress" recipe in TRMNL</li>
                <li>Enter your Goodreads RSS URL when prompted</li>
                <li>Your reading progress will update automatically!</li>
            </ol>
            <p><strong>Find your RSS URL:</strong> Go to your Goodreads profile → Look for the RSS feed link</p>
        </div>
        
        <h3>✨ Features</h3>
        <div class="feature">📖 Displays your current book with real-time reading progress</div>
        <div class="feature">📊 Shows progress bars for both book and yearly reading challenge</div>
        <div class="feature">📅 Tracks when you started and last updated your book</div>
        <div class="feature">🔄 Updates automatically every time your TRMNL refreshes</div>
        
        <h3>🔧 API Endpoint</h3>
        <p>This service provides a JSON API that TRMNL polls to get your reading data:</p>
        <code>/trmnl-data?rss_url=YOUR_GOODREADS_RSS_URL</code>
        
        <p style="text-align:center; margin-top:30px">
            <a href="/trmnl-data?demo=true" class="button">View Demo API Response</a>
        </p>
        
        <footer style="margin-top:40px; padding-top:20px; border-top:1px solid #e1e4e8; text-align:center; color:#666;">
            Built with ❤️ for the TRMNL community
        </footer>
    </body>
    </html>
    """

@app.route("/trmnl-data")
def serve_trmnl_data():
    """
    Main API endpoint for TRMNL to poll.
    Returns JSON data with current book and reading challenge information.
    """
    # Check if demo mode is requested
    if request.args.get('demo') == 'true':
        return jsonify(generate_demo_data())
    
    # Get RSS URL from query parameter
    rss_url = request.args.get('rss_url', '').strip()
    
    # Validate RSS URL
    if not rss_url or not rss_url.startswith('https://www.goodreads.com/user/updates_rss/'):
        # Return demo data if no valid URL provided
        demo_data = generate_demo_data()
        demo_data["error"] = "Please provide a valid Goodreads RSS URL"
        return jsonify(demo_data)
    
    # Fetch book data (with caching)
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
        "update_date": format_date(book_data.get('start_date')),
        "challenge": book_data.get('challenge'),
        "challenge_progress_percent": challenge_progress_percent,
        "current_time": datetime.now().strftime('%m/%d %H:%M')
    }
    
    return jsonify(response)

@app.route("/health")
def health():
    """Health check endpoint for monitoring."""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "cache_size": len(cache_storage)
    })

@app.route("/clear-cache")
def clear_cache():
    """Clear all cached data - useful for forcing fresh data fetch."""
    cache_storage.clear()
    return jsonify({
        "status": "cache cleared",
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    print("🚀 Starting TRMNL Goodreads Recipe Server")
    print("📚 Visit http://localhost:5001 to see the home page")
    print("📊 API endpoint: /trmnl-data?rss_url=YOUR_GOODREADS_RSS_URL")
    print("🧪 Demo mode: /trmnl-data?demo=true")
    print("💓 Health check: /health")
    print("🗑️  Clear cache: /clear-cache")
    
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
