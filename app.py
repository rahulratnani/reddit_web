import flask
from flask import Flask, request, render_template, redirect, url_for, send_file
import praw
import mysql.connector
import openai
import pandas as pd
from io import BytesIO

app = Flask(__name__)

# Configure Reddit
reddit = praw.Reddit(
    client_id="4CPn1Knc9rqks_T-HTMAjA",
    client_secret="0fWZ01iC3lkjY1vEVAGOErVel5LGfw",
    user_agent="getPosts by u/Repulsive-Wolf70022"
)

# Configure OpenAI
openai.api_key = ""

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="mysql_rahul99",
            database="reddit_search_2",
            port=3306,
            auth_plugin='mysql_native_password',
            charset='utf8mb4'
        )
        return conn
    except mysql.connector.Error as err:
        print(f"Error connecting to database: {err}")
        return None

def initialize_db():
    conn = get_db_connection()
    if conn is None:
        return
    
    cursor = conn.cursor()
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS results_2 (
                id INT AUTO_INCREMENT PRIMARY KEY,
                keyword VARCHAR(255),
                title TEXT,
                description TEXT,
                url MEDIUMTEXT,
                comments_count INT,
                keyword_count_in_comments INT,
                UNIQUE KEY unique_result (url(255))
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INT AUTO_INCREMENT PRIMARY KEY,
                prompt TEXT,
                generated_text TEXT
            );
        ''')
        conn.commit()
        print("Tables created successfully.")
    except mysql.connector.Error as err:
        print(f"Error creating tables: {err}")
    finally:
        cursor.close()
        conn.close()

def fetch_reddit_posts(keyword, sort='new', time_filter='all', language='any', country='all'):
    try:
        posts = list(reddit.subreddit('all').search(keyword, sort=sort, time_filter=time_filter, limit=10))
        return posts
    except Exception as e:
        print(f"Error fetching Reddit posts: {e}")
        return []

def count_keyword_in_comments(post, keyword):
    count = 0
    post.comments.replace_more(limit=0)
    for comment in post.comments.list():
        count += comment.body.lower().count(keyword.lower())
    return count

def store_posts_in_database(keyword, posts):
    conn = get_db_connection()
    if conn is None:
        return
    
    cursor = conn.cursor()
    for post in posts:
        try:
            keyword_count = count_keyword_in_comments(post, keyword)
            cursor.execute('''
                INSERT IGNORE INTO results_2 
                (keyword, title, description, url, comments_count, keyword_count_in_comments)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (keyword, post.title, post.selftext[:500], post.url, post.num_comments, keyword_count))
        except mysql.connector.Error as err:
            print(f"Error inserting post: {err}")
    
    conn.commit()
    cursor.close()
    conn.close()

def store_report_in_database(prompt, generated_text):
    conn = get_db_connection()
    if conn is None:
        return
    
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO reports (prompt, generated_text) VALUES (%s, %s)', (prompt, generated_text))
        conn.commit()
    except mysql.connector.Error as err:
        print(f"Error inserting report: {err}")
    finally:
        cursor.close()
        conn.close()

def generate_openai_report(prompt, context):
    try:
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"{prompt}\n\nContext:\n{context}\n\nProvide a detailed and informative response based on the context."}
        ]
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Or the model you're using
            messages=messages,
            max_tokens=1000
        )
        
        generated_text = response.choices[0].message['content'].strip()
        
        formatted_text = generated_text.replace('\n', '<br>').replace('*', '<b>').replace('**', '</b>')
        
        return formatted_text
    except openai.error.OpenAIError as e:
        print(f"OpenAI Error: {e}")
        return f"Error generating response: {e}"

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        keyword = request.form['keyword']
        sort = request.form.get('sort', 'new')
        time_filter = request.form.get('time_filter', 'all')
        language = request.form.get('language', 'any')
        country = request.form.get('country', 'all')
        prompt = request.form.get('prompt', '')

        # Fetch and store Reddit posts
        posts = fetch_reddit_posts(keyword, sort, time_filter, language, country)
        store_posts_in_database(keyword, posts)
        
        # Prepare context for OpenAI
        if posts:
            context = "\n\n".join([f"Title: {p.title}\nDescription: {p.selftext}\nURL: {p.url}" for p in posts])
        else:
            context = "No relevant Reddit posts found."
        
        # Generate OpenAI report
        generated_text = generate_openai_report(prompt, context)
        
        # Store the generated report in the database
        store_report_in_database(prompt, generated_text)
        
        # Display only the OpenAI generated report
        return render_template('report.html', prompt=prompt, generated_text=generated_text)

    return render_template('index.html')

@app.route('/report', methods=['GET'])
def report():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM reports ORDER BY id DESC LIMIT 1')
    report_data = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if report_data:
        return render_template('report.html', prompt=report_data['prompt'], generated_text=report_data['generated_text'])
    else:
        return "No report available."

@app.route('/download_report/<filename>', methods=['GET'])
def download_report(filename):
    df = pd.DataFrame({
        'Prompt': [filename],
        'Generated Text': ['Sample text for the report.']
    })

    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Report', index=False)
    output.seek(0)
    
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/reset')
def reset_search():
    return redirect(url_for('home'))

if __name__ == '__main__':
    initialize_db()
    app.run(debug=True)

