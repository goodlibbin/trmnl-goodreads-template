import re
import requests
from flask import Flask, jsonify, request
from bs4 import BeautifulSoup
import feedparser
import os
from datetime import datetime, timedelta

app = Flask(__name__)

# USER CONFIGURATION - UPDATE THESE VALUES WITH YOUR OWN
# =======================================================
# Your Goodreads RSS Feed URL
GOODREADS_RSS_URL = "https://www.goodreads.com/user/updates_rss/YOUR_USER_ID?key=YOUR_RSS_KEY"

# Your Goodreads User ID (just the number from your profile URL)
GOODREADS_USER_ID = "YOUR_USER_ID"
# =======================================================

# Enhanced caching system
cache = {
    'book_data': None,
    'challenge_data': None,
    'timestamp': None,
    'challenge_timestamp': None,
    'ttl_minutes': 5,
    'challenge_ttl_minutes': 30
}

def is_cache_valid():
    """Check if the book data cache is still valid"""
    if not cache['timestamp'] or not cache['book_data']:
        return False
    age = datetime.now() - cache['timestamp']
    return age < timedelta(minutes=cache['ttl_minutes'])

def is_challenge_cache_valid():
    """Check if the challenge data cache is still valid"""
    if not cache['challenge_timestamp']:
        return False
    age = datetime.now() - cache['challenge_timestamp']
    return age < timedelta(minutes=cache['challenge_ttl_minutes'])

def update_cache(book_data):
    """Update the book data cache with fresh information"""
    cache['book_data'] = book_data
    cache['timestamp'] = datetime.now()
    print(f"Book cache updated at {cache['timestamp'].strftime('%H:%M:%S')}")

def update_challenge_cache(challenge_data):
    """Update the challenge data cache with fresh information"""
    cache['challenge_data'] = challenge_data
    cache['challenge_timestamp'] = datetime.now()
    print(f"Challenge cache updated: {challenge_data}")

def extract_author_robust(entry):
    """Extract author name using multiple fallback strategies"""
    print(f"Extracting author from entry: {entry.title[:60]}...")
    
    # Strategy 1: Look for author links in the HTML description
    try:
        if hasattr(entry, 'description'):
            soup = BeautifulSoup(entry.description, 'html.parser')
            author_link = soup.find('a', href=re.compile(r'/author/'))
            if author_link:
                author_name = author_link.get_text().strip()
                if author_name and len(author_name) > 1 and author_name != "Unknown Author":
                    print(f"Found author via HTML link: {author_name}")
                    return author_name
    except Exception as e:
        print(f"Author strategy 1 failed: {e}")
    
    # Strategy 2: Parse title for "by Author" patterns
    try:
        title_clean = re.sub(r'(started reading|is currently reading|finished reading|is on page \d+ of \d+ of)', '', entry.title, flags=re.IGNORECASE)
        
        author_patterns = [
            r"'[^']+'\s+by\s+([^(]+?)(?:\s*\(|$)",
            r"by\s+([^(]+?)(?:\s*\(|$)",
            r"'[^']*'\s*(.+?)(?:\s*started|\s*is|\s*$)",
        ]
        
        for pattern in author_patterns:
            match = re.search(pattern, title_clean, re.IGNORECASE)
            if match:
                author_name = match.group(1).strip()
                author_name = re.sub(r'<[^>]+>', '', author_name)
                author_name = re.sub(r'\s+', ' ', author_name)
                
                if author_name and len(author_name) > 1 and len(author_name) < 100:
                    print(f"Found author via title parsing: {author_name}")
                    return author_name
    except Exception as e:
        print(f"Author strategy 2 failed: {e}")
    
    # Strategy 3: Check the author field directly
    try:
        if hasattr(entry, 'author'):
            author_text = re.sub(r"<[^>]+>", "", str(entry.author))
            author_text = re.sub(r'^.*?(started reading|is currently reading)', '', author_text, flags=re.IGNORECASE)
            
            if " by " in author_text:
                author_name = author_text.split(" by ")[-1].strip()
                if author_name and len(author_name) > 1 and len(author_name) < 100:
                    print(f"Found author via author field: {author_name}")
                    return author_name
    except Exception as e:
        print(f"Author strategy 3 failed: {e}")
    
    print("No reliable author found")
    return None

def extract_progress_from_entry(entry):
    """Extract reading progress percentage from RSS entry"""
    print(f"Extracting progress from: {entry.title}")
    
    # Look for progress patterns in the title
    title_patterns = [
        r'(\d+)%',
        r'is (\d+)% done',
        r'(\d+) percent',
        r'page (\d+) of (\d+)',
        r'is on page (\d+) of (\d+)',
    ]
    
    for pattern in title_patterns:
        match = re.search(pattern, entry.title, re.IGNORECASE)
        if match:
            if len(match.groups()) == 1:
                progress = min(int(match.group(1)), 100)
                print(f"Found progress in title: {progress}%")
                return progress
            elif len(match.groups()) == 2:
                current = int(match.group(1))
                total = int(match.group(2))
                if total > 0:
                    progress = min(int((current / total) * 100), 100)
                    print(f"Calculated progress: {current}/{total} = {progress}%")
                    return progress
    
    # Look for progress patterns in the description
    if hasattr(entry, "description"):
        soup = BeautifulSoup(entry.description, "html.parser")
        desc_text = soup.get_text()
        
        desc_patterns = [
            r'(\d+)%\s*(?:complete|done|finished|read)',
            r'(\d+)\s*percent',
            r'page\s+(\d+)\s+of\s+(\d+)',
            r'(\d+)\s*/\s*(\d+)\s*pages',
            r'progress:?\s*(\d+)%',
        ]
        
        for pattern in desc_patterns:
            match = re.search(pattern, desc_text, re.IGNORECASE)
            if match:
                if len(match.groups()) == 1:
                    progress = min(int(match.group(1)), 100)
                    print(f"Found progress in description: {progress}%")
                    return progress
                elif len(match.groups()) == 2:
                    current = int(match.group(1))
                    total = int(match.group(2))
                    if total > 0:
                        progress = min(int((current / total) * 100), 100)
                        print(f"Calculated progress from description: {current}/{total} = {progress}%")
                        return progress
    
    print(f"No progress found, defaulting to 0%")
    return 0

def normalize_book_title(title):
    """Normalize book titles for comparison across multiple entries"""
    if not title:
        return ""
    
    normalized = title.lower()
    # Remove subtitle after colon or dash
    normalized = re.sub(r'[:\-–—].*$', '', normalized)
    # Remove punctuation
    normalized = re.sub(r'[^\w\s]', '', normalized)
    # Normalize whitespace
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized

def find_all_book_entries():
    """Comprehensive search through RSS feed to find all book-related entries"""
    print("COMPREHENSIVE BOOK SEARCH")
    feed_url = GOODREADS_RSS_URL
    
    if feed_url == "https://www.goodreads.com/user/updates_rss/YOUR_USER_ID?key=YOUR_RSS_KEY":
        print("⚠️  WARNING: Please update GOODREADS_RSS_URL with your actual RSS feed URL")
        return {}
    
    try:
        feed = feedparser.parse(feed_url)
        if not feed.entries:
            print("No entries found in RSS feed")
            return {}
    except Exception as e:
        print(f"Failed to fetch RSS feed: {e}")
        return {}

    book_entries = {}
    print(f"Scanning {len(feed.entries)} RSS entries...")
    
    for i, entry in enumerate(feed.entries):
        title_lower = entry.title.lower()
        print(f"Entry {i+1}: {entry.title}")
        
        book_title = None
        progress = 0
        entry_type = "unknown"
        
        # Identify different types of reading activities
        if "started reading" in title_lower:
            match = re.search(r"'([^']+)'", entry.title)
            if match:
                book_title = match.group(1)
                progress = 0
                entry_type = "started"
                print(f"  -> Started reading: {book_title}")
        
        elif any(phrase in title_lower for phrase in ["is on page", "is currently reading", "updated her progress", "% done"]):
            title_patterns = [
                r"'([^']+)'",
                r"(?:is on page \d+ of \d+ of|is currently reading|updated (?:her|his) progress on|% done with)\s*(.+?)(?:\s*by|\s*$)",
            ]
            
            for pattern in title_patterns:
                match = re.search(pattern, entry.title, re.IGNORECASE)
                if match:
                    book_title = match.group(1).strip()
                    break
            
            if book_title:
                progress = extract_progress_from_entry(entry)
                entry_type = "progress_update"
                print(f"  -> Progress update: {book_title} - {progress}%")
        
        elif "currently reading" in title_lower:
            match = re.search(r"'([^']+)'", entry.title)
            if match:
                book_title = match.group(1)
                progress = extract_progress_from_entry(entry)
                entry_type = "currently_reading"
                print(f"  -> Currently reading: {book_title} - {progress}%")
        
        # Group entries by normalized title for data fusion
        if book_title:
            normalized_title = normalize_book_title(book_title)
            
            entry_data = {
                'entry': entry,
                'original_title': book_title,
                'progress': progress,
                'type': entry_type,
                'timestamp': entry.published if hasattr(entry, 'published') else None,
                'raw_rss_title': entry.title
            }
            
            if normalized_title not in book_entries:
                book_entries[normalized_title] = []
            
            book_entries[normalized_title].append(entry_data)
            print(f"  -> Added to collection: '{book_title}' ({progress}%, {entry_type})")
    
    return book_entries

def fetch_challenge_stats_enhanced():
    """Enhanced challenge stats extraction with multiple strategies"""
    if is_challenge_cache_valid():
        print("Using cached challenge data")
        return cache['challenge_data']
    
    print("ENHANCED CHALLENGE SEARCH")
    
    # Strategy 1: Search RSS feed for challenge updates
    try:
        rss_url = GOODREADS_RSS_URL
        if rss_url == "https://www.goodreads.com/user/updates_rss/YOUR_USER_ID?key=YOUR_RSS_KEY":
            print("⚠️  WARNING: RSS URL not configured")
            return None
            
        response = requests.get(rss_url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Cache-Control": "no-cache"
        }, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "lxml-xml")
            
            for item in soup.find_all("item"):
                if item.description:
                    desc_text = item.description.get_text()
                    
                    challenge_patterns = [
                        r"You have read (\d+) of (\d+) books",
                        r"has read (\d+) of (\d+) books",
                        r"read (\d+) of (\d+) books",
                        r"(\d+) of (\d+) books.*(?:challenge|goal|2025)",
                        r"(\d+)/(\d+) books",
                        r"has read (\d+) books? toward.*?goal of (\d+) books?",
                    ]
                    
                    for i, pattern in enumerate(challenge_patterns):
                        match = re.search(pattern, desc_text, re.IGNORECASE)
                        if match:
                            try:
                                books_read = int(match.group(1))
                                books_goal = int(match.group(2))
                                
                                if 0 <= books_read <= books_goal <= 500:
                                    result = f"{books_read} of {books_goal} books"
                                    print(f"Found challenge in RSS (pattern {i+1}): {result}")
                                    update_challenge_cache(result)
                                    return result
                            except (ValueError, IndexError):
                                continue
            
            print("No challenge data found in RSS descriptions")
    
    except Exception as e:
        print(f"RSS challenge search failed: {e}")
    
    # Strategy 2: Check Goodreads profile page
    try:
        if GOODREADS_USER_ID == "YOUR_USER_ID":
            print("⚠️  WARNING: User ID not configured")
            return None
            
        profile_url = f"https://www.goodreads.com/user/show/{GOODREADS_USER_ID}"
        print("Checking profile page...")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        
        response = requests.get(profile_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            full_text = soup.get_text()
            
            challenge_patterns = [
                r"You have read (\d+) of (\d+) books",
                r"(\d+) of (\d+) books.*?(?:ahead of schedule|behind|on track)",
                r"2025.*?(\d+) of (\d+)",
                r"(\d+) of (\d+) books",
                r"(\d+)/(\d+) books",
                r"read (\d+).*?of (\d+)",
            ]
            
            for pattern in challenge_patterns:
                match = re.search(pattern, full_text, re.IGNORECASE)
                if match:
                    books_read = int(match.group(1))
                    books_goal = int(match.group(2))
                    
                    if 0 <= books_read <= books_goal <= 500:
                        result = f"{books_read} of {books_goal} books"
                        print(f"Found challenge on profile: {result}")
                        update_challenge_cache(result)
                        return result
        
        print("No challenge data found on profile page")
        
    except Exception as e:
        print(f"Profile page search failed: {e}")
    
    print("All challenge search strategies failed")
    update_challenge_cache(None)
    return None

def build_enhanced_book_data(book_entries):
    """Intelligently fuse data from multiple entries for the same book"""
    if not book_entries:
        return None
    
    print(f"Building book data from {len(book_entries)} normalized titles")
    
    # Find the most recently active book
    most_recent_book = None
    most_recent_time = None
    
    for normalized_title, entries in book_entries.items():
        print(f"Checking normalized title: '{normalized_title}' with {len(entries)} entries")
        
        # Sort entries by timestamp to find the most recent activity
        sorted_entries = sorted(entries, key=lambda x: x['timestamp'] or '', reverse=True)
        
        if sorted_entries:
            latest_entry = sorted_entries[0]
            entry_time = latest_entry['timestamp']
            
            print(f"  Latest entry: {latest_entry['original_title']} ({latest_entry['progress']}%, {latest_entry['type']}, {entry_time})")
            
            if most_recent_time is None or (entry_time and entry_time > most_recent_time):
                most_recent_book = (normalized_title, sorted_entries)
                most_recent_time = entry_time
                print(f"  -> This is now the most recent book")
    
    if not most_recent_book:
        return None
    
    normalized_title, entries = most_recent_book
    
    # Perform intelligent data fusion across multiple entries
    best_progress = 0
    best_progress_entry = None
    best_metadata_entry = None
    best_cover_url = None
    all_authors = set()
    
    print(f"Performing data fusion for '{normalized_title}' ({len(entries)} entries)")
    
    # Find the entry with the highest progress that's not just "started reading"
    for entry_data in entries:
        print(f"  Checking: {entry_data['original_title']} - {entry_data['progress']}% ({entry_data['type']}) - {entry_data['timestamp']}")
        
        # Prioritize actual progress updates over initial "started reading" entries
        if entry_data['progress'] > best_progress or (entry_data['progress'] > 0 and best_progress == 0):
            best_progress = entry_data['progress']
            best_progress_entry = entry_data
            print(f"    -> New best progress: {best_progress}%")
        
        # Use "started reading" entries for metadata like start date
        if entry_data['type'] == 'started' and best_metadata_entry is None:
            best_metadata_entry = entry_data
            print(f"    -> Using as metadata source")
        
        # Collect all author mentions for validation
        author = extract_author_robust(entry_data['entry'])
        if author:
            all_authors.add(author)
        
        # Look for cover image URLs in entry descriptions
        if hasattr(entry_data['entry'], 'description'):
            cover_match = re.search(r'src="(https://[^"]+\.jpg)"', entry_data['entry'].description)
            if cover_match and not best_cover_url:
                best_cover_url = cover_match.group(1)
                print(f"    -> Found cover URL")
    
    if not best_metadata_entry:
        best_metadata_entry = entries[0]
    
    # Choose the best title (usually the longest/most complete version)
    best_title = best_progress_entry['original_title']
    for entry_data in entries:
        if len(entry_data['original_title']) > len(best_title):
            best_title = entry_data['original_title']
    
    # Choose the best author (most common or longest name found)
    best_author = "Unknown Author"
    if all_authors:
        best_author = max(all_authors, key=len)
    
    start_date = best_metadata_entry['timestamp']
    update_date = best_progress_entry['timestamp']
    
    # Fetch challenge data separately with its own caching
    challenge_data = fetch_challenge_stats_enhanced()
    
    print("Data fusion complete:")
    print(f"   Title: {best_title}")
    print(f"   Author: {best_author}")
    print(f"   Progress: {best_progress}% (from {best_progress_entry['type']} entry)")
    print(f"   Challenge: {challenge_data}")
    
    return {
        "title": best_title,
        "author": best_author,
        "progress": best_progress,
        "cover_url": best_cover_url,
        "start_date": start_date,
        "update_date": update_date,
        "challenge": challenge_data,
        "entry_types": [e['type'] for e in entries],
        "entries_count": len(entries),
        "selected_progress_entry": best_progress_entry['raw_rss_title']
    }

def fetch_book_data():
    """Main function to fetch and process current book data"""
    print("FETCHING BOOK DATA")
    
    # Check configuration first
    if GOODREADS_RSS_URL == "https://www.goodreads.com/user/updates_rss/YOUR_USER_ID?key=YOUR_RSS_KEY":
        print("⚠️  Configuration required: Please update your RSS URL in app.py")
        return {
            "title": "Configuration Required",
            "author": "Please update GOODREADS_RSS_URL in app.py",
            "progress": 0,
            "cover_url": None,
            "start_date": None,
            "update_date": None,
            "challenge": "Update your RSS URL to see challenge data",
            "entries_count": 0
        }
    
    # Check cache first to avoid unnecessary API calls
    if is_cache_valid():
        print("Using cached data")
        return cache['book_data']
    
    # Find all book entries in the RSS feed
    book_entries = find_all_book_entries()
    
    if book_entries:
        book_data = build_enhanced_book_data(book_entries)
        if book_data:
            update_cache(book_data)
            return book_data
    
    # Fallback if no current book is found
    print("No current book found")
    fallback_data = {
        "title": "No current book found",
        "author": "Check Goodreads activity",
        "progress": 0,
        "cover_url": None,
        "start_date": None,
        "update_date": None,
        "challenge": None,
        "entries_count": 0
    }
    
    update_cache(fallback_data)
    return fallback_data

def format_date_trmnl(dt):
    """Format date strings for display on TRMNL"""
    if not dt:
        return "Unknown"
    try:
        if isinstance(dt, str):
            return datetime.strptime(dt, "%a, %d %b %Y %H:%M:%S %z").strftime("%b %d, %Y")
        return dt.strftime("%b %d, %Y")
    except:
        return str(dt)[:10] if dt else "Unknown"

# Flask Routes

@app.route("/trmnl-data")
def serve_trmnl_data():
    """Main endpoint for TRMNL - returns JSON data for use in templates"""
    try:
        # Check if configuration is set up
        if GOODREADS_RSS_URL == "https://www.goodreads.com/user/updates_rss/YOUR_USER_ID?key=YOUR_RSS_KEY":
            return jsonify({
                "title": "Configuration Required",
                "author": "Please update your RSS URL in app.py",
                "progress": 0,
                "start_date": "Unknown",
                "update_date": "Unknown",
                "challenge": "Update GOODREADS_RSS_URL in app.py",
                "challenge_progress_percent": 0,
                "entries_count": 0,
                "current_time": datetime.now().strftime('%m/%d %H:%M')
            })
        
        book = fetch_book_data()
        
        # Calculate challenge progress percentage
        challenge_progress_percent = 0
        if book.get('challenge'):
            try:
                parts = book['challenge'].split(' of ')
                if len(parts) == 2:
                    current = int(parts[0])
                    total = int(parts[1].split(' ')[0])
                    challenge_progress_percent = min(int((current / total) * 100), 100)
            except:
                pass
        
        # Format dates
        start_date = format_date_trmnl(book.get('start_date'))
        update_date = format_date_trmnl(book.get('update_date'))
        current_time = datetime.now().strftime('%m/%d %H:%M')
        
        return jsonify({
            "title": book.get('title', 'Unknown Title'),
            "author": book.get('author', 'Unknown Author'),
            "progress": book.get('progress', 0),
            "cover_url": book.get('cover_url'),
            "start_date": start_date,
            "update_date": update_date,
            "challenge": book.get('challenge'),
            "challenge_progress_percent": challenge_progress_percent,
            "entries_count": book.get('entries_count', 0),
            "current_time": current_time
        })
        
    except Exception as e:
        print(f"Error in serve_trmnl_data: {e}")
        return jsonify({
            "title": "Error Loading Data",
            "author": "Please check configuration and connection",
            "progress": 0,
            "start_date": "Unknown",
            "update_date": "Unknown",
            "challenge": None,
            "challenge_progress_percent": 0,
            "entries_count": 0,
            "current_time": datetime.now().strftime('%m/%d %H:%M')
        }), 500

@app.route("/debug")
def debug_info():
    """Comprehensive debug endpoint"""
    try:
        book_entries = find_all_book_entries()
        book_data = build_enhanced_book_data(book_entries) if book_entries else None
        
        return jsonify({
            "book_data": book_data,
            "cache_status": {
                "book_cache_valid": is_cache_valid(),
                "challenge_cache_valid": is_challenge_cache_valid(),
                "book_timestamp": cache['timestamp'].isoformat() if cache['timestamp'] else None,
                "challenge_timestamp": cache['challenge_timestamp'].isoformat() if cache['challenge_timestamp'] else None,
                "cached_challenge": cache['challenge_data']
            },
            "raw_entries": {title: len(entries) for title, entries in book_entries.items()},
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e), "timestamp": datetime.now().isoformat()})

@app.route("/debug-entries")
def debug_entries():
    """Debug RSS entry parsing - shows detailed entry analysis"""
    try:
        book_entries = find_all_book_entries()
        
        entries_detail = {}
        for title, entries in book_entries.items():
            entries_detail[title] = []
            for entry in entries:
                entries_detail[title].append({
                    "title": entry['original_title'],
                    "progress": entry['progress'],
                    "type": entry['type'],
                    "rss_title": entry['raw_rss_title'],
                    "timestamp": entry['timestamp']
                })
        
        return jsonify({
            "message": "Detailed RSS entry analysis",
            "entries_found": entries_detail,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/test-challenge")
def test_challenge():
    """Test challenge data fetching with fresh lookup"""
    try:
        # Clear challenge cache to force fresh lookup
        cache['challenge_data'] = None
        cache['challenge_timestamp'] = None
        
        challenge_data = fetch_challenge_stats_enhanced()
        return jsonify({
            "challenge_data": challenge_data,
            "cache_valid": is_challenge_cache_valid(),
            "cache_timestamp": cache['challenge_timestamp'].isoformat() if cache['challenge_timestamp'] else None,
            "message": "Fresh challenge data lookup",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        })

@app.route("/clear-cache")
def clear_cache():
    """Clear all cached data"""
    cache['book_data'] = None
    cache['challenge_data'] = None
    cache['timestamp'] = None
    cache['challenge_timestamp'] = None
    return jsonify({
        "message": "All caches cleared", 
        "timestamp": datetime.now().isoformat()
    })

@app.route("/test-data")
def test_data():
    """Test endpoint with sample data for demonstration"""
    return jsonify({
        "title": "The Seven Husbands of Evelyn Hugo",
        "author": "Taylor Jenkins Reid",
        "progress": 68,
        "start_date": "Jun 15, 2025",
        "update_date": "Jun 26, 2025",
        "challenge": "15 of 25 books",
        "challenge_progress_percent": 60,
        "entries_count": 3,
        "current_time": datetime.now().strftime('%m/%d %H:%M')
    })

if __name__ == "__main__":
    print("🚀 Starting TRMNL Goodreads Data Server")
    print("=" * 60)
    print("📚 TRMNL Goodreads Reading Progress Data API")
    print("🔧 Configure your RSS URL in the USER CONFIGURATION section")
    print("📡 Main endpoint: /trmnl-data (JSON data for TRMNL templates)")
    print("🧪 Test endpoint: /test-data (sample data for testing)")
    print("🐛 Debug endpoints: /debug, /debug-entries, /test-challenge")
    print("💾 Clear cache: /clear-cache")
    print("=" * 60)
    
    if GOODREADS_RSS_URL == "https://www.goodreads.com/user/updates_rss/YOUR_USER_ID?key=YOUR_RSS_KEY":
        print("⚠️  WARNING: Please update GOODREADS_RSS_URL with your actual RSS feed URL")
        print("   Find your RSS URL at: https://www.goodreads.com/user/show/YOUR_ID")
        print("🧪 For testing, visit: /test-data to see sample output")
    else:
        print("✅ Configuration looks good! RSS URL is set.")
    
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=False)
