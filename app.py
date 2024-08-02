from flask import Flask, request, render_template, redirect, url_for, send_file
import praw
import mysql.connector
from mysql.connector import Error
from flask_caching import Cache
from io import BytesIO
import pandas as pd
import os

app = Flask(__name__, template_folder="templates")

# Flask-Caching configuration
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 300})

# Reddit API credentials
reddit_client_id = os.getenv('REDDIT_CLIENT_ID', '4CPn1Knc9rqks_T-HTMAjA')
reddit_client_secret = os.getenv('REDDIT_CLIENT_SECRET', '0fWZ01iC3lkjY1vEVAGOErVel5LGfw')
reddit_user_agent = os.getenv('REDDIT_USER_AGENT', 'getPosts by u/Repulsive-Wolf70022')

# MySQL database configuration
db_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'mysql_rahul99'),
    'database': os.getenv('DB_NAME', 'reddit_search_2'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'auth_plugin': 'mysql_native_password',
    'charset': 'utf8mb4'
}

# Create a Reddit instance
reddit = praw.Reddit(client_id=reddit_client_id,
                     client_secret=reddit_client_secret,
                     user_agent=reddit_user_agent)

# Connect to MySQL database
def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        return conn, cursor
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None, None

# Create results table if not exists
def initialize_database():
    conn, cursor = get_db_connection()
    if conn and cursor:
        try:
            create_table_query = """
            CREATE TABLE IF NOT EXISTS results_2 (
                id INT AUTO_INCREMENT PRIMARY KEY,
                keyword VARCHAR(255),
                title TEXT,
                description TEXT,
                url MEDIUMTEXT,
                comments_count INT,
                keyword_count_in_comments INT,
                UNIQUE KEY unique_result (url)
            );
            """
            cursor.execute(create_table_query)
            conn.commit()
        except Error as e:
            print(f"Error initializing database: {e}")
        finally:
            cursor.close()
            conn.close()

initialize_database()

@app.route('/')
def index():
    previous_keyword = request.args.get('keyword', '')
    previous_filter_type = request.args.get('filterType', 'hot')
    previous_time_filter = request.args.get('timeFilter', 'week')
    return render_template(
        'index.html',
        previous_keyword=previous_keyword,
        previous_filter_type=previous_filter_type,
        previous_time_filter=previous_time_filter
    )

@app.route('/search', methods=['GET'])
@cache.cached(timeout=300, query_string=True)
def search_reddit():
    keyword = request.args.get('keyword', '').strip()
    filter_type = request.args.get('filterType', 'hot')
    time_filter = request.args.get('timeFilter', 'week')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    if not keyword:
        return render_template('error.html', error_message='Search keyword cannot be empty.')

    try:
        subreddit = reddit.subreddit('all')
        posts = subreddit.search(query=keyword, sort=filter_type, time_filter=time_filter)

        results = []
        conn, cursor = get_db_connection()
        if conn and cursor:
            try:
                for post in posts:
                    if keyword.lower() in post.title.lower() or keyword.lower() in post.selftext.lower():
                        cursor.execute("SELECT id FROM results_2 WHERE url = %s", (post.url,))
                        if cursor.fetchone():
                            continue

                        keyword_count_in_comments = 0
                        post.comments.replace_more(limit=0)
                        for comment in post.comments.list():
                            if keyword.lower() in comment.body.lower():
                                keyword_count_in_comments += 1

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
                if total_results == 0:
                    return render_template('error.html', error_message='No results found for the given keyword.')

                start = (page - 1) * per_page
                end = start + per_page
                paginated_results = results[start:end]
                total_pages = (total_results + per_page - 1) // per_page

                pagination = {
                    'prev': page - 1 if page > 1 else None,
                    'next': page + 1 if page < total_pages else None,
                    'pages': list(range(1, total_pages + 1)),
                    'current': page
                }

            except Error as e:
                print(f"Database error: {e}")
                return render_template('error.html', error_message='An error occurred while interacting with the database.')
            finally:
                cursor.close()
                conn.close()
        else:
            return render_template('error.html', error_message='Unable to connect to the database.')

        return render_template(
            'results.html',
            posts=paginated_results,
            pagination=pagination,
            keyword=keyword,
            filterType=filter_type,
            timeFilter=time_filter
        )

    except Exception as e:
        print(f"Error: {e}")
        return render_template('error.html', error_message=f'An error occurred while searching: {str(e)}')

@app.route('/reset')
def reset_search():
    return redirect(url_for('index'))

@app.route('/save_report', methods=['GET'])
def save_report():
    keyword = request.args.get('keyword', '')

    conn, cursor = get_db_connection()
    if conn and cursor:
        try:
            query = """
            SELECT title, description, url, comments_count, keyword_count_in_comments
            FROM results_2
            WHERE keyword = %s
            """
            cursor.execute(query, (keyword,))
            results = cursor.fetchall()

            if results:
                df = pd.DataFrame(results, columns=['Title', 'Description', 'URL', 'Comments Count', 'Keyword Count in Comments'])
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Results')
                output.seek(0)

                return send_file(
                    output,
                    as_attachment=True,
                    download_name=f"report_{keyword}.xlsx",
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                return render_template('error.html', error_message='No results to save.')

        except Error as e:
            print(f"Database error: {e}")
            return render_template('error.html', error_message='An error occurred while fetching the results.')
        finally:
            cursor.close()
            conn.close()
    else:
        return render_template('error.html', error_message='Unable to connect to the database.')

if __name__ == '__main__':
    app.run(debug=True)















































































=======
@app.route('/reset')
def reset_search():
    return redirect(url_for('index'))

if __name__ == '__main__':
    application.run()
>>>>>>> origin/master
