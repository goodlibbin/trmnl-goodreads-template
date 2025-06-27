# 📚 TRMNL Goodreads Display Template

A Flask data backend for displaying your current Goodreads reading progress on TRMNL e-ink devices. Provides clean JSON data that works with TRMNL's template system to show book title, author, progress bars, and reading challenge tracking.

![TRMNL Goodreads Display MockUp](https://github.com/goodlibbin/trmnl-goodreads-template/blob/main/mock.jpg)

## ✨ Features

- **📖 Current Reading Progress**: Tracks your active book with percentage complete
- **🔄 Smart Data Fusion**: Combines multiple Goodreads RSS entries for accurate information  
- **🎯 Reading Challenge Tracking**: Extracts your annual reading goal with progress percentage
- **📅 Reading Timeline**: Shows when you started and last updated your book
- **⚡ Optimized for TRMNL**: Clean JSON data API designed for TRMNL's template system
- **🧠 Intelligent Caching**: Reduces API calls (5min book data, 30min challenge data)
- **📱 Multiple Layouts**: Works with Full, Half-Horizontal, Half-Vertical, and Quadrant layouts

## 🚀 Quick Deploy

### Deploy to Railway (Recommended)
[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/evQIi3?referralCode=9288Uc)

### Deploy to Heroku
[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/goodlibbin/trmnl-goodreads-template)

### Deploy to Render
1. Fork this repository
2. Connect to [Render](https://render.com)
3. Create new Web Service from your fork
4. Use `python app.py` as the start command

## ⚙️ Configuration

### Step 1: Find Your Goodreads Information

#### Get Your RSS URL:
1. Go to your Goodreads profile
2. Make sure your profile and updates are set to **public**
3. Look for your RSS feed URL in your profile settings
4. Format: `https://www.goodreads.com/user/updates_rss/[USER_ID]?key=[YOUR_KEY]`

#### Get Your User ID:
- It's the number in your Goodreads profile URL
- Example: `https://www.goodreads.com/user/show/12345678` → User ID is `12345678`

### Step 2: Update Your Configuration

1. Open `app.py` in your deployed repository
2. Find the "USER CONFIGURATION" section at the top
3. Replace the placeholder values:

```python
# USER CONFIGURATION - UPDATE THESE VALUES WITH YOUR OWN
# =======================================================
# Your Goodreads RSS Feed URL
GOODREADS_RSS_URL = "https://www.goodreads.com/user/updates_rss/12345678?key=abcdef123456"

# Your Goodreads User ID (just the number from your profile URL)
GOODREADS_USER_ID = "12345678"
# =======================================================
```

4. Save and redeploy your app

### Step 3: Test Your Backend

1. Visit your deployed URL: `https://your-app.railway.app/trmnl-data`
2. You should see JSON data with your book information
3. If you see "Configuration Required", update your RSS URL in `app.py`

## 📱 TRMNL Setup

### Using the Recipe (Recommended)
1. Install the "Goodreads Reading Progress" recipe from TRMNL
2. Enter your backend URL: `https://your-app.railway.app`
3. Choose your layout preference
4. Save and enjoy!

### Manual Setup
1. Create a Private Plugin in TRMNL
2. Set strategy to "Polling"
3. Set polling URL to: `https://your-app.railway.app/trmnl-data`
4. Copy your preferred template markup from our examples
5. Paste into markup editor and save

## 🎨 Template Examples

This backend provides clean JSON data that works with TRMNL's template system. Here are example templates for different layout sizes:

### Full Layout Template
```html
<div class="layout">
  <div class="columns">
    <div class="column">
      <!-- Centered Title with Border -->
      <div class="richtext richtext--center mb--3">
        <div class="content content--large clamp--3 text--center p--2" data-pixel-perfect="true" style="font-weight: bold; border: 2px solid black;">{{ title }}</div>
      </div>
      
      <!-- Data Table -->
      <table class="table">
        <tbody>
          <tr>
            <td class="w--32"><span class="title title--medium">Author</span></td>
            <td><span class="label clamp--1">{{ author }}</span></td>
          </tr>
          <tr>
            <td><span class="title title--medium">Progress</span></td>
            <td>
              <span class="label">{{ progress }}%</span>
              <div style="width: 100%; height: 10px; border: 1px solid black; position: relative; margin-top: 5px;">
                <div style="position: absolute; background: black; height: 100%; width: {{ progress }}%;"></div>
              </div>
            </td>
          </tr>
          <tr>
            <td><span class="title title--medium">Started</span></td>
            <td><span class="label clamp--1">{{ start_date }}</span></td>
          </tr>
          {% if update_date != start_date and update_date != "Unknown" %}
          <tr>
            <td><span class="title title--medium">Updated</span></td>
            <td><span class="label clamp--1">{{ update_date }}</span></td>
          </tr>
          {% endif %}
          {% if challenge %}
          <tr>
            <td><span class="title title--medium">2025 Goal</span></td>
            <td>
              <span class="label clamp--1">{{ challenge }}</span>
              <div style="width: 100%; height: 8px; border: 1px solid black; background: white; position: relative; margin-top: 3px;">
                <div style="position: absolute; background: black; height: 100%; width: {{ challenge_progress_percent }}%;"></div>
              </div>
            </td>
          </tr>
          {% endif %}
        </tbody>
      </table>
    </div>
  </div>
</div>
<div class="title_bar">
  <img class="image" src="https://usetrmnl.com/images/plugins/trmnl--render.svg">
  <span class="title">Goodreads</span>
  <span class="instance">{{ current_time }}</span>
</div>
```

### Half-Vertical Layout Template  
```html
<div class="layout layout--col layout--top gap--small">
  <div class="w-full">
    <!-- Centered Title -->
    <div class="richtext richtext--center mb--2">
      <div class="content content--large clamp--3 text--center p--2" data-pixel-perfect="true" style="font-weight: bold; border: 2px solid black;">{{ title }}</div>
    </div>
    
    <!-- Data Table -->
    <table class="table">
      <tbody>
        <tr>
          <td class="w--32"><span class="title title--medium">Author</span></td>
          <td><span class="label clamp--1">{{ author }}</span></td>
        </tr>
        <tr>
          <td><span class="title title--medium">Progress</span></td>
          <td>
            <span class="label">{{ progress }}%</span>
            <div style="width: 100%; height: 8px; border: 1px solid black; position: relative; margin-top: 3px;">
              <div style="position: absolute; background: black; height: 100%; width: {{ progress }}%;"></div>
            </div>
          </td>
        </tr>
        <tr>
          <td><span class="title title--medium">Started</span></td>
          <td><span class="label clamp--1">{{ start_date }}</span></td>
        </tr>
        {% if challenge %}
        <tr>
          <td><span class="title title--medium">Goal</span></td>
          <td>
            <span class="label clamp--1">{{ challenge }}</span>
            <div style="width: 100%; height: 6px; border: 1px solid black; background: white; position: relative; margin-top: 3px;">
              <div style="position: absolute; background: black; height: 100%; width: {{ challenge_progress_percent }}%;"></div>
            </div>
          </td>
        </tr>
        {% endif %}
      </tbody>
    </table>
  </div>
</div>
<div class="title_bar">
  <img class="image" src="https://usetrmnl.com/images/plugins/trmnl--render.svg">
  <span class="title">Goodreads</span>
  <span class="instance">{{ current_time }}</span>
</div>
```

## 📊 JSON Data Structure

The `/trmnl-data` endpoint returns data in this format:

```json
{
  "title": "The Empusium: A Health Resort Horror Story",
  "author": "Olga Tokarczuk", 
  "progress": 41,
  "start_date": "Jun 16, 2025",
  "update_date": "Jun 25, 2025",
  "challenge": "26 of 30 books",
  "challenge_progress_percent": 87,
  "entries_count": 3,
  "current_time": "06/26 17:42"
}
```

## 🔧 API Endpoints

- `/trmnl-data` - Main JSON data endpoint for TRMNL templates
- `/debug` - System diagnostics and cache status
- `/debug-entries` - RSS feed parsing details
- `/test-challenge` - Challenge data testing
- `/clear-cache` - Force fresh data fetch

## 🛠️ Troubleshooting

### "Configuration Required" Message
- Ensure you've updated `GOODREADS_RSS_URL` in `app.py`
- Verify your Goodreads profile is public
- Check that your RSS URL format is correct

### "No current book found"
- Make sure you have recent reading activity on Goodreads
- Verify your RSS feed contains book entries
- Test the `/debug-entries` endpoint to see what data is being found

### Challenge data not appearing
- Ensure your reading challenge is public on Goodreads
- Test the `/test-challenge` endpoint
- Some profiles may not expose challenge data publicly

### Templates not displaying correctly
- Verify your polling URL points to `/trmnl-data`
- Check the JSON response format matches expected template variables
- Test different layout templates to find what works best

## 🔄 Updating

To update your deployment with the latest features:

1. Check this repository for updates
2. Compare with your deployed version
3. Update your `app.py` with new features (keep your personal configuration)
4. Redeploy your app

## 📊 How It Works

![TRMNL Goodreads Display Example](https://github.com/goodlibbin/trmnl-goodreads-template/blob/main/example.jpg)

1. **RSS Parsing**: Fetches your Goodreads RSS feed every 5 minutes
2. **Data Fusion**: Intelligently combines multiple entries for the same book
3. **Progress Extraction**: Uses multiple strategies to find reading progress
4. **Challenge Tracking**: Scrapes challenge data from RSS and profile page
5. **JSON API**: Provides clean data for TRMNL's template system
6. **Smart Caching**: Caches book data (5min) and challenge data (30min)

## 🤝 Contributing

This is an open-source project! Feel free to:
- Report issues
- Suggest improvements  
- Submit pull requests
- Share your layout customizations

## 📄 License

MIT License - feel free to modify for your own use!

## 🙏 Acknowledgments

- Built for the [TRMNL](https://usetrmnl.com) e-ink display community
- Inspired by the need for beautiful, automated reading progress tracking
- Thanks to Goodreads for providing RSS feeds

---

**Enjoy tracking your reading progress!** 📚✨

For more TRMNL templates and projects, visit the [TRMNL community](https://usetrmnl.com).
