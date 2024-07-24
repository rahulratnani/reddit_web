from flask import Flask, request, render_template, redirect, url_for
import praw
import mysql.connector
from flask_caching import Cache

app = Flask(__name__, template_folder="templates")

# Flask-Caching configuration
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 300})

# Reddit API credentials
reddit_client_id = '4CPn1Knc9rqks_T-HTMAjA'
reddit_client_secret = '0fWZ01iC3lkjY1vEVAGOErVel5LGfw'
reddit_user_agent = 'getPosts by u/Repulsive-Wolf70022'

# MySQL database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'mysql_rahul99',
    'database': 'reddit_search_2',
    'port': 3306,  # Ensure this matches your MySQL port
    'auth_plugin': 'mysql_native_password',
    'charset': 'utf8mb4'
}

# Create a Reddit instance
reddit = praw.Reddit(client_id=reddit_client_id,
                     client_secret=reddit_client_secret,
                     user_agent=reddit_user_agent)

# Connect to MySQL database
def get_db_connection():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    return conn, cursor

# Create results table if not exists
conn, cursor = get_db_connection()
create_table_query = """
CREATE TABLE IF NOT EXISTS results_2 (
    id INT AUTO_INCREMENT PRIMARY KEY,
    keyword VARCHAR(255),
    title TEXT,
    description TEXT,
    url TEXT,
    comments_count INT,
    keyword_count_in_comments INT
);
"""
cursor.execute(create_table_query)
conn.commit()
cursor.close()
conn.close()

@app.route('/')
def index():
    previous_keyword = request.args.get('keyword', '')
    previous_filter_type = request.args.get('filterType', 'hot')
    previous_time_filter = request.args.get('timeFilter', 'all')
    return render_template('index.html', previous_keyword=previous_keyword, previous_filter_type=previous_filter_type, previous_time_filter=previous_time_filter)

@app.route('/search', methods=['GET'])
@cache.cached(timeout=300, query_string=True)
def search_reddit():
    keyword = request.args.get('keyword')
    filter_type = request.args.get('filterType', 'hot')
    time_filter = request.args.get('timeFilter', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    try:
        subreddit = reddit.subreddit('all')
        
        if time_filter == 'week':
            posts = subreddit.search(query=keyword, time_filter='week', sort=filter_type)
        elif time_filter == 'month':
            posts = subreddit.search(query=keyword, time_filter='month', sort=filter_type)
        elif time_filter == 'day':
            posts = subreddit.search(query=keyword, time_filter='day', sort=filter_type)
        elif time_filter == 'all':
            posts = subreddit.top(limit=100)
        else:
            posts = subreddit.search(query=keyword, sort=filter_type)

        results = []
        conn, cursor = get_db_connection()

        for post in posts:
            if keyword.lower() in post.title.lower() or keyword.lower() in post.selftext.lower():
                keyword_count_in_comments = sum(1 for comment in post.comments.list() if hasattr(comment, 'body') and keyword.lower() in comment.body.lower())

                insert_query = """
                INSERT INTO results_2 (keyword, title, description, url, comments_count, keyword_count_in_comments)
                VALUES (%s, %s, %s, %s, %s, %s)
                """
                cursor.execute(insert_query, (keyword, post.title, post.selftext, post.url, post.num_comments, keyword_count_in_comments))
                conn.commit()

                result = {
                    'title': post.title,
                    'description': post.selftext,
                    'url': post.url,
                    'comments_count': post.num_comments,
                    'keyword_count_in_comments': keyword_count_in_comments
                }
                results.append(result)

        total_results = len(results)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_results = results[start:end]
        total_pages = (total_results + per_page - 1) // per_page

        cursor.close()
        conn.close()

        return render_template('results.html', results=paginated_results, page=page, total_pages=total_pages, keyword=keyword, filterType=filter_type, timeFilter=time_filter)

    except Exception as e:
        print(f"Error: {e}")
        return render_template('error.html', error_message=f'An error occurred while searching: {str(e)}')

@app.route('/reset')
def reset_search():
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
