import os
import sqlite3
from flask import Flask, render_template, request, redirect, session, send_from_directory, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "supersecretkey"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "mp4", "mkv", "mov"}

# Database
conn = sqlite3.connect("chat.db", check_same_thread=False)
c = conn.cursor()

# Tables
c.execute('''CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT NOT NULL
)''')

c.execute('''CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender TEXT,
    receiver TEXT,
    receiver_type TEXT DEFAULT 'user',
    type TEXT,
    content TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)''')

c.execute('''CREATE TABLE IF NOT EXISTS groups (
    groupname TEXT PRIMARY KEY
)''')

c.execute('''CREATE TABLE IF NOT EXISTS group_members (
    groupname TEXT,
    username TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS typing_status (
    sender TEXT,
    receiver TEXT,
    receiver_type TEXT DEFAULT 'user',
    is_typing INTEGER DEFAULT 0,
    PRIMARY KEY (sender, receiver, receiver_type)
)''')

conn.commit()

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def auth_user():
    return session.get("user")

@app.route("/")
def index():
    if "user" in session:
        return redirect("/chat")
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        if user:
            session["user"] = username
            return redirect("/chat")
        return "Invalid credentials. <a href='/login'>Try again</a>"
    return '''
        <h2>Login</h2>
        <form method="post">
            Username: <input name="username" required><br>
            Password: <input type="password" name="password" required><br>
            <button type="submit">Login</button>
        </form>
        <a href="/signup">New user? Sign up here</a>
    '''

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        if c.fetchone():
            return "Username already exists. <a href='/signup'>Try another</a>"
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
        return "Account created. <a href='/login'>Login</a>"
    return '''
        <h2>Signup</h2>
        <form method="post">
            Username: <input name="username" required><br>
            Password: <input type="password" name="password" required><br>
            <button type="submit">Sign up</button>
        </form>
        <a href="/login">Already have an account?</a>
    '''

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

@app.route("/chat")
def chat():
    if "user" not in session:
        return redirect("/login")
    return render_template("chat.html", username=session["user"])

@app.route("/group", methods=["GET", "POST"])
def group():
    if "user" not in session:
        return redirect("/login")
    if request.method == "POST":
        groupname = request.form["groupname"].strip()
        c.execute("SELECT * FROM groups WHERE groupname=?", (groupname,))
        if c.fetchone():
            return "Group already exists. <a href='/group'>Try another</a>"
        c.execute("INSERT INTO groups (groupname) VALUES (?)", (groupname,))
        c.execute("INSERT INTO group_members (groupname, username) VALUES (?, ?)", (groupname, session["user"]))
        conn.commit()
        return "Group created and joined! <a href='/chat'>Chat</a>"
    return '''
        <h2>Create Group</h2>
        <form method="post">
            Group Name: <input name="groupname" required><br>
            <button type="submit">Create & Join</button>
        </form>
        <a href="/chat">Back to Chat</a>
    '''

@app.route("/group/add", methods=["GET", "POST"])
def add_member():
    if "user" not in session:
        return redirect("/login")
    if request.method == "POST":
        groupname = request.form["groupname"].strip()
        member = request.form["username"].strip()
        c.execute("SELECT * FROM group_members WHERE groupname=? AND username=?", (groupname, session["user"]))
        if not c.fetchone():
            return "You're not in the group. <a href='/group/add'>Try again</a>"
        c.execute("SELECT * FROM users WHERE username=?", (member,))
        if not c.fetchone():
            return "User does not exist. <a href='/group/add'>Try again</a>"
        c.execute("SELECT * FROM group_members WHERE groupname=? AND username=?", (groupname, member))
        if c.fetchone():
            return "User already in group. <a href='/group/add'>Try again</a>"
        c.execute("INSERT INTO group_members (groupname, username) VALUES (?, ?)", (groupname, member))
        conn.commit()
        return f"Added {member} to '{groupname}'! <a href='/chat'>Chat</a>"
    return '''
        <h2>Add Member to Group</h2>
        <form method="post">
            Group Name: <input name="groupname" required><br>
            Username to Add: <input name="username" required><br>
            <button type="submit">Add Member</button>
        </form>
        <a href="/chat">Back to Chat</a>
    '''

@app.route("/api/send", methods=["POST"])
def api_send():
    data = request.get_json()
    sender = auth_user()
    receiver = data.get("receiver")
    content = data.get("content", "").strip()
    msg_type = data.get("type", "text")
    receiver_type = data.get("receiver_type", "user")

    if not sender or not receiver or not content:
        return jsonify({"error": "Missing data"}), 400

    c.execute("INSERT INTO messages (sender, receiver, receiver_type, type, content) VALUES (?, ?, ?, ?, ?)",
              (sender, receiver, receiver_type, msg_type, content))
    conn.commit()
    return jsonify({"success": True})

@app.route("/api/upload", methods=["POST"])
def api_upload():
    sender = auth_user()
    receiver = request.form.get("receiver")
    receiver_type = request.form.get("receiver_type", "user")
    file = request.files.get("file")

    if not sender or not receiver or not file:
        return jsonify({"error": "Missing data"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "File not allowed"}), 400

    filename = secure_filename(file.filename)
    file.save(os.path.join(UPLOAD_FOLDER, filename))

    c.execute("INSERT INTO messages (sender, receiver, receiver_type, type, content) VALUES (?, ?, ?, ?, ?)",
              (sender, receiver, receiver_type, "file", filename))
    conn.commit()
    return jsonify({"success": True})

@app.route("/media/<filename>")
def media(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/api/receive")
def api_receive():
    user = auth_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    c.execute("SELECT sender, receiver, receiver_type, type, content, timestamp FROM messages WHERE sender=? OR receiver=? OR receiver IN (SELECT groupname FROM group_members WHERE username=?) ORDER BY timestamp",
              (user, user, user))
    rows = c.fetchall()

    conversations = {}
    for r in rows:
        sender, receiver, receiver_type, msg_type, content, timestamp = r
        target = receiver if receiver_type == "group" else (receiver if sender == user else sender)
        if target not in conversations:
            conversations[target] = []
        conversations[target].append({
            "sender": sender,
            "receiver": receiver,
            "type": msg_type,
            "content": content,
            "timestamp": timestamp
        })

    return jsonify(conversations)

@app.route("/api/group-members/<groupname>")
def api_group_members(groupname):
    c.execute("SELECT username FROM group_members WHERE groupname=?", (groupname,))
    members = [row[0] for row in c.fetchall()]
    return jsonify(members)

@app.route("/api/typing", methods=["POST"])
def api_typing():
    data = request.get_json()
    sender = auth_user()
    receiver = data.get("receiver")
    receiver_type = data.get("receiver_type", "user")
    is_typing = int(data.get("is_typing", 0))

    if not sender or not receiver:
        return jsonify({"error": "Missing"}), 400

    c.execute("REPLACE INTO typing_status (sender, receiver, receiver_type, is_typing) VALUES (?, ?, ?, ?)",
              (sender, receiver, receiver_type, is_typing))
    conn.commit()
    return jsonify({"success": True})

@app.route("/api/typing/<target>")
def get_typing_status(target):
    user = auth_user()
    c.execute('''
        SELECT sender FROM typing_status 
        WHERE receiver=? AND receiver_type='user' AND is_typing=1 AND sender != ?
    ''', (user, user))
    users_typing = [row[0] for row in c.fetchall()]
    return jsonify(users_typing)

if __name__ == "__main__":
    app.run(debug=True)
