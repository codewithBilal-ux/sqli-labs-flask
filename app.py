import sqlite3
import os
from flask import Flask, request, render_template, g

app = Flask(__name__)
DATABASE = 'sqli_labs.db'

# ─── DB helpers ───────────────────────────────────────────────────────────────

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    """Execute a query and return results."""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def raw_query(query):
    """Execute a RAW unsanitized query — intentionally vulnerable."""
    try:
        db = get_db()
        cur = db.execute(query)
        rv = cur.fetchall()
        cur.close()
        return rv, None
    except Exception as e:
        return [], str(e)

# ─── Database seeding ─────────────────────────────────────────────────────────

def init_db():
    if os.path.exists(DATABASE):
        return
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    # products
    cur.execute("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            price REAL,
            released INTEGER DEFAULT 0
        )
    """)
    cur.executemany("INSERT INTO products VALUES (?,?,?,?,?,?)", [
        (1,  'Laptop Pro',        'High-end laptop',         'Electronics', 1299.99, 1),
        (2,  'Wireless Mouse',    'Ergonomic wireless mouse','Electronics',   29.99, 1),
        (3,  'USB-C Hub',         '7-port USB-C hub',        'Electronics',   49.99, 1),
        (4,  'Standing Desk',     'Adjustable standing desk','Furniture',    399.99, 1),
        (5,  'Ergonomic Chair',   'Lumbar support chair',    'Furniture',    299.99, 1),
        (6,  'SECRET PROTOTYPE',  'Unreleased product!',     'Electronics',    0.00, 0),
        (7,  'HIDDEN ITEM',       'Top secret item',         'Furniture',      0.00, 0),
        (8,  'Mechanical Keyboard','RGB mechanical keyboard','Electronics',   89.99, 1),
        (9,  'Monitor 4K',        '27-inch 4K display',      'Electronics',  499.99, 1),
        (10, 'Desk Lamp',         'LED adjustable lamp',     'Furniture',     39.99, 1),
    ])

    # users
    cur.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT,
            role TEXT DEFAULT 'user'
        )
    """)
    cur.executemany("INSERT INTO users VALUES (?,?,?,?,?)", [
        (1, 'alice',     'password123',   'alice@example.com',   'user'),
        (2, 'bob',       'securepass',    'bob@example.com',     'user'),
        (3, 'charlie',   'charlie2024',   'charlie@example.com', 'user'),
        (4, 'admin',     'super_secret',  'admin@example.com',   'admin'),
        (5, 'moderator', 'mod_pass_2024', 'mod@example.com',     'moderator'),
    ])

    # secret_users (for UNION-based exfil labs)
    cur.execute("""
        CREATE TABLE secret_users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            secret_key TEXT,
            clearance_level INTEGER
        )
    """)
    cur.executemany("INSERT INTO secret_users VALUES (?,?,?,?)", [
        (1, 'agent_x',   'KEY-ALPHA-9921', 5),
        (2, 'shadow',    'KEY-BRAVO-4477', 4),
        (3, 'handler',   'KEY-CHARLIE-001',3),
    ])

    # comments (for lab6 — second-order)
    cur.execute("""
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            comment TEXT
        )
    """)

    db.commit()
    db.close()

# ─── Home ─────────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    labs = [
        dict(n=1, title='WHERE Clause Filter Bypass',       desc='Bypass released=1 filter with OR 1=1',         method='GET',  param='?category=Electronics'),
        dict(n=2, title='Login Bypass',                     desc='Log in as admin without knowing the password',  method='POST', param='/lab2'),
        dict(n=3, title='UNION — Column Count',             desc='Find number of columns with ORDER BY / UNION',  method='GET',  param='?category=Electronics'),
        dict(n=4, title='UNION — Data Exfiltration',        desc='Dump usernames & passwords via UNION SELECT',   method='GET',  param='?category=Electronics'),
        dict(n=5, title='UNION — Cross-Table Exfiltration', desc='Steal data from secret_users table',            method='GET',  param='?category=Electronics'),
        dict(n=6, title='Blind Boolean-Based SQLi',         desc='Extract data one bit at a time with true/false',method='GET',  param='?username=admin'),
        dict(n=7, title='Second-Order SQLi',                desc='Stored payload fires on a different request',   method='POST', param='/lab7'),
        dict(n=8, title='Error-Based SQLi',                 desc='Force DB errors to leak schema information',    method='GET',  param='?id=1'),
    ]
    return render_template('home.html', labs=labs)

# ─── Lab 1 — WHERE clause bypass ──────────────────────────────────────────────

@app.route('/lab1')
def lab1():
    category  = request.args.get('category', '')
    results, error = [], None
    raw_sql = ''
    if category:
        raw_sql = f"SELECT * FROM products WHERE category = '{category}' AND released = 1"
        results, error = raw_query(raw_sql)
    lab = dict(
        number=1, title='WHERE Clause Filter Bypass',
        description='The app filters products by category and only shows released=1 items. Can you make it show ALL products, including secret unreleased ones?',
        goal='See the SECRET PROTOTYPE and HIDDEN ITEM rows.',
        payload="' OR 1=1--",
        hint="The injected ' closes the string, OR 1=1 makes the condition always true, and -- comments out the AND released=1 filter.",
        safe_version="SELECT * FROM products WHERE category = ? AND released = 1",
        param='category', method='GET',
    )
    return render_template('lab.html', lab=lab, results=results, raw_sql=raw_sql, error=error, input_val=category)

# ─── Lab 2 — Login bypass ─────────────────────────────────────────────────────

@app.route('/lab2', methods=['GET', 'POST'])
def lab2():
    result, raw_sql, error, success = None, '', None, False
    username = password = ''
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        raw_sql  = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
        rows, error = raw_query(raw_sql)
        if rows:
            result  = dict(rows[0])
            success = True
    lab = dict(
        number=2, title='Login Bypass',
        description='Log into the admin account without knowing the password.',
        goal='Get a successful login response for the admin user.',
        payload="admin'--  (username), anything (password)",
        hint="Injecting ' -- in the username closes the string and comments out the password check entirely.",
        safe_version="SELECT * FROM users WHERE username = ? AND password = ?",
        param='username / password', method='POST',
    )
    return render_template('lab_login.html', lab=lab, result=result, raw_sql=raw_sql,
                           error=error, success=success, username=username, password=password)

# ─── Lab 3 — UNION column count ───────────────────────────────────────────────

@app.route('/lab3')
def lab3():
    category  = request.args.get('category', '')
    results, error = [], None
    raw_sql = ''
    if category:
        raw_sql = f"SELECT id, name, description, category, price FROM products WHERE category = '{category}' AND released = 1"
        results, error = raw_query(raw_sql)
    lab = dict(
        number=3, title='UNION — Column Count Discovery',
        description='Before UNION injection you must know how many columns the query selects. Use ORDER BY or NULL probing.',
        goal='Determine the exact number of columns (5) so a UNION payload works.',
        payload="' ORDER BY 5--   then   ' UNION SELECT NULL,NULL,NULL,NULL,NULL--",
        hint="Increment ORDER BY until you get an error. Then match NULLs in UNION SELECT to that count.",
        safe_version="SELECT id,name,description,category,price FROM products WHERE category = ? AND released = 1",
        param='category', method='GET',
    )
    return render_template('lab.html', lab=lab, results=results, raw_sql=raw_sql, error=error, input_val=category)

# ─── Lab 4 — UNION data exfiltration ─────────────────────────────────────────

@app.route('/lab4')
def lab4():
    category  = request.args.get('category', '')
    results, error = [], None
    raw_sql = ''
    if category:
        raw_sql = f"SELECT id, name, description, category, price FROM products WHERE category = '{category}' AND released = 1"
        results, error = raw_query(raw_sql)
    lab = dict(
        number=4, title='UNION — Dump Users Table',
        description='Use a UNION SELECT to append rows from the users table onto the products result set.',
        goal='See all usernames and passwords from the users table.',
        payload="' UNION SELECT id,username,password,role,NULL FROM users--",
        hint="The UNION appends rows from a second query. Column types must be compatible — map text fields to text columns.",
        safe_version="Use parameterized queries; UNION injection is impossible with bound parameters.",
        param='category', method='GET',
    )
    return render_template('lab.html', lab=lab, results=results, raw_sql=raw_sql, error=error, input_val=category)

# ─── Lab 5 — Cross-table exfiltration ────────────────────────────────────────

@app.route('/lab5')
def lab5():
    category  = request.args.get('category', '')
    results, error = [], None
    raw_sql = ''
    if category:
        raw_sql = f"SELECT id, name, description, category, price FROM products WHERE category = '{category}' AND released = 1"
        results, error = raw_query(raw_sql)
    lab = dict(
        number=5, title='UNION — Cross-Table: secret_users',
        description='The secret_users table exists but is never queried by the app. UNION it in to steal its data.',
        goal='Reveal all rows from secret_users (username, secret_key, clearance_level).',
        payload="' UNION SELECT id,username,secret_key,CAST(clearance_level AS TEXT),NULL FROM secret_users--",
        hint="You need to know the table name. In a real attack you'd enumerate sqlite_master first.",
        safe_version="Parameterized queries prevent UNION injection entirely.",
        param='category', method='GET',
    )
    return render_template('lab.html', lab=lab, results=results, raw_sql=raw_sql, error=error, input_val=category)

# ─── Lab 6 — Blind boolean-based ─────────────────────────────────────────────

@app.route('/lab6')
def lab6():
    username = request.args.get('username', '')
    exists   = None
    raw_sql  = ''
    if username:
        raw_sql = f"SELECT id FROM users WHERE username = '{username}'"
        rows, _ = raw_query(raw_sql)
        exists  = len(rows) > 0
    lab = dict(
        number=6, title='Blind Boolean-Based SQLi',
        description='The app returns only true/false (user found / not found). Use conditional payloads to extract data one character at a time.',
        goal="Determine the admin's password length, then extract each character.",
        payload="admin' AND LENGTH(password)>5--   →   admin' AND SUBSTR(password,1,1)='s'--",
        hint="When the response is 'User found', your condition is TRUE. Binary-search each character position.",
        safe_version="SELECT id FROM users WHERE username = ?",
        param='username', method='GET',
    )
    return render_template('lab_blind.html', lab=lab, exists=exists, raw_sql=raw_sql, username=username)

# ─── Lab 7 — Second-order SQLi ────────────────────────────────────────────────

@app.route('/lab7', methods=['GET', 'POST'])
def lab7():
    stored_comments, trigger_result, raw_sql_store, raw_sql_trigger = [], None, '', ''
    store_msg = trigger_msg = ''

    db = get_db()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'store':
            # Step 1 — safely INSERT the comment (parameterized — looks safe!)
            uname   = request.form.get('username', '')
            comment = request.form.get('comment', '')
            raw_sql_store = f"INSERT INTO comments (username, comment) VALUES (?, ?)"
            db.execute(raw_sql_store, (uname, comment))
            db.commit()
            store_msg = f"Comment by '{uname}' stored."

        elif action == 'trigger':
            # Step 2 — fetch username from DB, then use it UNSAFELY in a new query
            comment_id   = request.form.get('comment_id', '1')
            row = query_db("SELECT username FROM comments WHERE id = ?", [comment_id], one=True)
            if row:
                stored_username  = row['username']   # ← contains the malicious payload!
                raw_sql_trigger  = f"SELECT * FROM users WHERE username = '{stored_username}'"
                trigger_result, _ = raw_query(raw_sql_trigger)
                trigger_msg = f"Triggered query with stored username: {stored_username}"

    stored_comments = query_db("SELECT id, username, comment FROM comments")

    lab = dict(
        number=7, title='Second-Order SQLi',
        description='The payload is stored safely (parameterized INSERT) but later retrieved and used unsafely in a second query. Classic second-order injection.',
        goal="Store a malicious username that causes the trigger step to dump all users.",
        payload="username = admin'--  (store it), then trigger comment id 1",
        hint="The INSERT is safe. The vulnerability is in step 2 when the stored value is interpolated into a new raw query.",
        safe_version="Use parameterized queries in BOTH the store AND the trigger steps.",
        param='username / comment', method='POST',
    )
    return render_template('lab_secondorder.html', lab=lab,
                           stored_comments=stored_comments,
                           trigger_result=trigger_result,
                           raw_sql_store=raw_sql_store,
                           raw_sql_trigger=raw_sql_trigger,
                           store_msg=store_msg, trigger_msg=trigger_msg)

# ─── Lab 8 — Error-based SQLi ─────────────────────────────────────────────────

@app.route('/lab8')
def lab8():
    product_id = request.args.get('id', '')
    results, error = [], None
    raw_sql = ''
    if product_id:
        raw_sql = f"SELECT id, name, description, category, price FROM products WHERE id = {product_id}"
        results, error = raw_query(raw_sql)
    lab = dict(
        number=8, title='Error-Based SQLi',
        description='Integer parameter injected directly. SQLite error messages can reveal table and column names.',
        goal='Trigger a descriptive error that leaks schema info, then pivot to extracting data.',
        payload="1 AND 1=CAST((SELECT name FROM sqlite_master WHERE type='table' LIMIT 1) AS INTEGER)",
        hint="The CAST forces a type error whose message contains the table name. Iterate with OFFSET to enumerate all tables.",
        safe_version="SELECT ... FROM products WHERE id = ?",
        param='id', method='GET',
    )
    return render_template('lab_error.html', lab=lab, results=results, raw_sql=raw_sql,
                           error=error, input_val=product_id)

# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
