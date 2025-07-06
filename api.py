from flask import Flask, request, jsonify, render_template, redirect, session, send_from_directory
from flask_cors import CORS
import sqlite3, os, datetime, werkzeug

app = Flask(__name__)
CORS(app)
app.secret_key = "super_secret_key"  # Required for session management

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- DB SETUP ---
conn = sqlite3.connect('chat.db', check_same_thread=False)
c = conn.cursor()

# Create users and messages table
c.execute('''CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender TEXT,
    receiver TEXT,
    type TEXT,
    content TEXT,
    timestamp TEXT
)''')

# --- In-memory tokens for desktop API login
tokens = {}

# --- ROUTES FOR BROWSER FRONTEND ---

@app.route('/')
def home():
    return render_template("login.html")

@app.route('/login', methods=['POST'])
def login_web():
    username = request.form.get("username")
    password = request.form.get("password")
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    if c.fetchone():
        session['user'] = username
        return redirect('/chat')
    return "❌ Invalid login. <a href='/'>Try again</a>"

@app.route('/register', methods=['POST'])
def register_web():
    username = request.form.get("username")
    password = request.form.get("password")
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    if c.fetchone():
        return "⚠️ Username exists. <a href='/'>Try again</a>"
    c.execute("INSERT INTO users VALUES (?, ?)", (username, password))
    conn.commit()
    session['user'] = username
    return redirect('/chat')

@app.route('/chat')
def chat_page():
    if 'user' not in session:
        return redirect('/')
    return render_template("chat.html", username=session['user'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# --- API ROUTES FOR GUI/JS CLIENTS ---

def auth_token():
    token = request.headers.get("Authorization")
    return tokens.get(token)

@app.route('/api/register', methods=['POST'])
@app.route('/api/receive')
def api_receive():
    user = auth_token() or session.get('user')
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    # Fetch all messages involving the user
    c.execute("SELECT sender, receiver, type, content, timestamp FROM messages WHERE sender=? OR receiver=? ORDER BY timestamp",
              (user, user))
    rows = c.fetchall()

    # Group messages by conversation partner
    conversations = {}
    for r in rows:
        sender, receiver, msg_type, content, timestamp = r

        # Identify the "other" person in this conversation
        if sender == user:
            other = receiver
        else:
            other = sender

        if other not in conversations:
            conversations[other] = []

        conversations[other].append({
            "sender": sender,
            "receiver": receiver,
            "type": msg_type,
            "content": content,
            "timestamp": timestamp
        })

    return jsonify(conversations)


@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    if not c.fetchone():
        return jsonify({"error": "Invalid credentials"}), 401
    token = os.urandom(12).hex()
    tokens[token] = username
    return jsonify({"token": token})

@app.route('/api/send', methods=['POST'])
def api_send():
    user = auth_token()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    receiver = data.get("receiver")
    msg_type = data.get("type", "text")
    content = data.get("content", "")
    timestamp = datetime.datetime.now().isoformat()
    c.execute("INSERT INTO messages (sender, receiver, type, content, timestamp) VALUES (?, ?, ?, ?, ?)",
              (user, receiver, msg_type, content, timestamp))
    conn.commit()
    return jsonify({"message": "Message sent"})

@app.route('/api/receive')
def api_receive():
    user = auth_token()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    c.execute("SELECT sender, receiver, type, content, timestamp FROM messages WHERE sender=? OR receiver=? ORDER BY timestamp",
              (user, user))
    rows = c.fetchall()
    return jsonify([
        {"sender": r[0], "receiver": r[1], "type": r[2], "content": r[3], "timestamp": r[4]}
        for r in rows
    ])

@app.route('/api/upload', methods=['POST'])
def api_upload():
    user = auth_token()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    file = request.files['file']
    receiver = request.form.get("receiver")
    filename = werkzeug.utils.secure_filename(file.filename)
    if file and len(file.read()) <= 60 * 1024 * 1024:
        file.seek(0)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        timestamp = datetime.datetime.now().isoformat()
        c.execute("INSERT INTO messages (sender, receiver, type, content, timestamp) VALUES (?, ?, ?, ?, ?)",
                  (user, receiver, "file", filename, timestamp))
        conn.commit()
        return jsonify({"message": "File uploaded"})
    return jsonify({"error": "File too large or missing"}), 400

@app.route('/media/<filename>')
def media(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# --- Start the Flask App ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
