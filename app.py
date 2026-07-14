#!/usr/bin/env python3
"""Thyhe - Intentionally Vulnerable Corporate Intranet Portal"""

import os
import re
import json
import time
import sqlite3
import hashlib
import base64
import subprocess
import random
import string
import urllib.request
from functools import wraps
from datetime import datetime, timedelta

import jwt
import requests
from lxml import etree
from flask import (
    Flask, render_template, render_template_string, request, redirect,
    url_for, session, flash, jsonify, send_from_directory, make_response,
    abort, g
)
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'thyhe-secret-key-2024'
app.permanent_session_lifetime = timedelta(days=365)
JWT_SECRET = 'secret'
DATABASE = os.path.join(os.path.dirname(__file__), 'thyhe.db')
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
DOCUMENTS_FOLDER = os.path.join(os.path.dirname(__file__), 'documents', 'files')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOCUMENTS_FOLDER, exist_ok=True)


# ============================================================
# DATABASE HELPERS
# ============================================================

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    c = db.cursor()

    c.execute("DROP TABLE IF EXISTS users")
    c.execute("DROP TABLE IF EXISTS products")
    c.execute("DROP TABLE IF EXISTS reviews")
    c.execute("DROP TABLE IF EXISTS support_tickets")
    c.execute("DROP TABLE IF EXISTS ticket_replies")
    c.execute("DROP TABLE IF EXISTS employees")
    c.execute("DROP TABLE IF EXISTS documents")
    c.execute("DROP TABLE IF EXISTS news_comments")
    c.execute("DROP TABLE IF EXISTS password_resets")
    c.execute("DROP TABLE IF EXISTS mfa_codes")
    c.execute("DROP TABLE IF EXISTS api_keys")
    c.execute("DROP TABLE IF EXISTS messages")

    c.execute("""CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        email TEXT,
        role TEXT DEFAULT 'employee',
        bio TEXT DEFAULT '',
        avatar TEXT DEFAULT 'default.png',
        department TEXT DEFAULT 'General',
        mfa_enabled INTEGER DEFAULT 0,
        mfa_code TEXT DEFAULT '',
        locked INTEGER DEFAULT 0,
        failed_logins INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE employees (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        first_name TEXT,
        last_name TEXT,
        position TEXT,
        salary REAL,
        ssn TEXT,
        phone TEXT,
        address TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    c.execute("""CREATE TABLE products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        price REAL,
        category TEXT,
        stock INTEGER,
        image TEXT DEFAULT 'product.png'
    )""")

    c.execute("""CREATE TABLE reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        user_id INTEGER,
        username TEXT,
        content TEXT,
        rating INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(product_id) REFERENCES products(id)
    )""")

    c.execute("""CREATE TABLE support_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        content TEXT,
        status TEXT DEFAULT 'open',
        priority TEXT DEFAULT 'medium',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    c.execute("""CREATE TABLE ticket_replies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id INTEGER,
        user_id INTEGER,
        username TEXT,
        content TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(ticket_id) REFERENCES support_tickets(id)
    )""")

    c.execute("""CREATE TABLE documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        filename TEXT,
        original_name TEXT,
        upload_date TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    c.execute("""CREATE TABLE news_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER,
        username TEXT,
        comment TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        token TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    c.execute("""CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user INTEGER,
        to_user INTEGER,
        subject TEXT,
        body TEXT,
        read INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    users = [
        ('admin', 'admin123', 'admin@thyhe.com', 'admin', 'System Administrator', 1, ''),
        ('jsmith', 'password123', 'jsmith@thyhe.com', 'manager', 'IT Manager', 1, ''),
        ('agarcia', 'Welcome1!', 'agarcia@thyhe.com', 'employee', 'Software Developer', 0, ''),
        ('bwilson', 'letmein', 'bwilson@thyhe.com', 'employee', 'HR Specialist', 0, ''),
        ('cjones', 'qwerty', 'cjones@thyhe.com', 'employee', 'Sales Representative', 0, ''),
        ('dlee', 'dragon', 'dlee@thyhe.com', 'employee', 'DevOps Engineer', 0, ''),
        ('emartinez', 'baseball', 'emartinez@thyhe.com', 'employee', 'Marketing Analyst', 0, ''),
        ('fthomas', 'iloveyou', 'fthomas@thyhe.com', 'employee', 'Finance Clerk', 0, ''),
        ('ghall', 'monkey', 'ghall@thyhe.com', 'hr', 'HR Director', 0, ''),
        ('hkim', 'master', 'hkim@thyhe.com', 'employee', 'QA Tester', 0, ''),
    ]

    for u in users:
        c.execute("INSERT INTO users (username, password, email, role, department, mfa_enabled, bio) VALUES (?,?,?,?,?,?,?)",
                  (u[0], u[1], u[2], u[3], u[4], u[5], u[6]))

    employees = [
        (1001, 1, 'System', 'Admin', 'CTO', 250000, '123-45-6789', '555-0100', '1 Corporate Blvd'),
        (1002, 2, 'John', 'Smith', 'IT Manager', 120000, '234-56-7890', '555-0101', '42 Tech Lane'),
        (1003, 3, 'Ana', 'Garcia', 'Software Developer', 95000, '345-67-8901', '555-0102', '15 Code Street'),
        (1004, 4, 'Brian', 'Wilson', 'HR Specialist', 75000, '456-78-9012', '555-0103', '88 People Ave'),
        (1005, 5, 'Carol', 'Jones', 'Sales Rep', 65000, '567-89-0123', '555-0104', '33 Commerce Dr'),
        (1006, 6, 'David', 'Lee', 'DevOps Engineer', 110000, '678-90-1234', '555-0105', '7 Cloud Way'),
        (1007, 7, 'Elena', 'Martinez', 'Marketing Analyst', 70000, '789-01-2345', '555-0106', '21 Brand Blvd'),
        (1008, 8, 'Frank', 'Thomas', 'Finance Clerk', 55000, '890-12-3456', '555-0107', '99 Money St'),
        (1009, 9, 'Grace', 'Hall', 'HR Director', 130000, '901-23-4567', '555-0108', '50 HR Plaza'),
        (1010, 10, 'Henry', 'Kim', 'QA Tester', 80000, '012-34-5678', '555-0109', '12 Test Lane'),
    ]

    for e in employees:
        c.execute("INSERT INTO employees VALUES (?,?,?,?,?,?,?,?,?)", e)

    products = [
        ('Thyhe Firewall Pro', 'Enterprise-grade firewall appliance with advanced threat detection', 4999.99, 'Security', 50, 'firewall.png'),
        ('SecureVPN Gateway', 'High-performance VPN solution for remote workers', 2499.99, 'Networking', 100, 'vpn.png'),
        ('DataShield Backup', 'Automated cloud backup with military-grade encryption', 999.99, 'Storage', 200, 'backup.png'),
        ('NetMonitor Suite', 'Real-time network monitoring and alerting platform', 3499.99, 'Monitoring', 75, 'monitor.png'),
        ('CloudStack Platform', 'Multi-cloud orchestration and management tool', 7999.99, 'Cloud', 30, 'cloud.png'),
        ('EndPoint Armor', 'Next-gen endpoint detection and response', 1999.99, 'Security', 150, 'endpoint.png'),
        ('CodeAudit Pro', 'Static and dynamic code analysis toolkit', 5999.99, 'DevSecOps', 40, 'audit.png'),
        ('IdentityForge', 'Identity and access management platform', 3999.99, 'IAM', 60, 'identity.png'),
    ]

    for p in products:
        c.execute("INSERT INTO products (name, description, price, category, stock, image) VALUES (?,?,?,?,?,?)", p)

    reviews = [
        (1, 2, 'jsmith', 'Great firewall, easy to configure!', 5),
        (1, 3, 'agarcia', 'Works well but documentation could be better', 4),
        (2, 4, 'bwilson', 'VPN speeds are excellent', 5),
        (3, 5, 'cjones', 'Backup solution saved our data twice already', 5),
        (4, 6, 'dlee', 'Good monitoring but needs more integrations', 3),
    ]

    for r in reviews:
        c.execute("INSERT INTO reviews (product_id, user_id, username, content, rating) VALUES (?,?,?,?,?)", r)

    tickets = [
        (2, 'VPN Not Connecting', 'I cannot connect to the VPN from home. Getting timeout errors.', 'open', 'high'),
        (3, 'Need IDE License', 'Please provision a new IDE license for the dev team project.', 'open', 'medium'),
        (4, 'Payroll Question', 'My last paycheck seems incorrect. Can someone review?', 'closed', 'medium'),
        (5, 'Sales Portal Down', 'The sales portal has been showing 503 errors since morning.', 'open', 'critical'),
    ]

    for t in tickets:
        c.execute("INSERT INTO support_tickets (user_id, title, content, status, priority) VALUES (?,?,?,?,?)", t)

    c.execute("INSERT INTO mfa_codes (user_id, code) VALUES (1, '123456')",) if False else None
    c.execute("""CREATE TABLE IF NOT EXISTS mfa_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        code TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("INSERT INTO mfa_codes (user_id, code) VALUES (1, '123456')")
    c.execute("INSERT INTO mfa_codes (user_id, code) VALUES (2, '654321')")

    for fname in ['employee_handbook.txt', 'network_diagram.txt', 'vpn_config.txt']:
        fpath = os.path.join(DOCUMENTS_FOLDER, fname)
        if not os.path.exists(fpath):
            with open(fpath, 'w') as f:
                if 'handbook' in fname:
                    f.write("Thyhe Employee Handbook v3.2\n\nWelcome to Thyhe!\n\nInternal WiFi Password: VulnC0rp_Internal_2024\nVPN Gateway: vpn.thyhe.internal\nAdmin Portal: http://admin.thyhe.internal:8443\n\nDB Credentials (DEV): devuser / D3v$ecret!\n")
                elif 'network' in fname:
                    f.write("Internal Network Diagram\n\n10.10.10.0/24 - Corporate LAN\n10.10.20.0/24 - Server VLAN\n10.10.30.0/24 - DMZ\n\nDomain Controller: 10.10.20.5\nFile Server: 10.10.20.10\nDB Server: 10.10.20.15 (MySQL root:r00tP@ss)\n")
                else:
                    f.write("VPN Configuration\n\nServer: vpn.thyhe.com\nPort: 1194\nProtocol: UDP\nPre-shared key: VulnC0rp_VPN_K3y!\n")

    secret_path = os.path.join(os.path.dirname(__file__), 'documents')
    with open(os.path.join(secret_path, 'admin_credentials.txt'), 'w') as f:
        f.write("=== ADMIN CREDENTIALS ===\nPortal Admin: admin / admin123\nDB Admin: root / r00tP@ss\nSSH Root: root / Vu1nC0rp_R00t!\nAWS Key: AKIAIOSFODNN7EXAMPLE\nAWS Secret: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n")

    messages = [
        (1, 3, 'Server Maintenance', 'Hi Ana, the staging server will be down tonight for patching. Please push your changes before 6pm.'),
        (1, 2, 'Q3 Budget Review', 'John, please review the Q3 budget spreadsheet I uploaded to the shared drive. Password for the file is: Budget2024!'),
        (2, 4, 'New Hire Onboarding', 'Brian, the new developer starts Monday. Can you set up their AD account? Temp password should be Welcome1! as usual.'),
        (3, 1, 'Deploy Request', 'Admin, the hotfix for ticket #247 is ready for production deploy. Branch: hotfix/auth-bypass'),
        (1, 5, 'Client Demo Prep', 'Carol, the client demo is Thursday. Here are the demo credentials: demo_admin / DemoP@ss123'),
        (2, 1, 'VPN Access Issue', 'Admin, I cannot connect to the VPN from home. Can you reset my VPN certificate? My employee ID is 1002.'),
        (6, 1, 'AWS Keys Rotation', 'Admin, reminder that the AWS access keys have not been rotated in 90 days. Current key ID: AKIAIOSFODNN7EXAMPLE'),
        (1, 6, 'RE: AWS Keys Rotation', 'David, thanks for the reminder. I will rotate them this week. The current secret is in the admin_credentials.txt file.'),
    ]
    for m in messages:
        c.execute("INSERT INTO messages (from_user, to_user, subject, body) VALUES (?,?,?,?)", m)

    db.commit()
    db.close()


# ============================================================
# AUTH HELPERS
# ============================================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    if 'user_id' in session:
        db = get_db()
        return db.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    return None


# ============================================================
# MAIN ROUTES
# ============================================================

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/init')
def init_database():
    init_db()
    flash('Database initialized successfully!', 'success')
    return redirect(url_for('login'))


# ============================================================
# AUTHENTICATION ATTACKS
# ============================================================

# --- VULN: SQL Injection login bypass (Auth #1, SQLi #1) ---
# --- VULN: Username enumeration (Auth #2) ---
# --- VULN: No rate limiting / brute force (Auth #3) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        db = get_db()

        # VULN: SQL Injection - string concatenation
        query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
        try:
            user = db.execute(query).fetchone()
        except Exception as e:
            error = f"Database error: {e}"
            return render_template('login.html', error=error)

        if user:
            if user['locked']:
                error = "Account is locked due to too many failed attempts."
                return render_template('login.html', error=error)

            if user['mfa_enabled']:
                session['mfa_user_id'] = user['id']
                session['mfa_username'] = user['username']
                return redirect(url_for('mfa_verify'))

            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']

            next_url = request.args.get('next', '')
            if next_url:
                # VULN: Open redirect #1 - unvalidated next parameter
                return redirect(next_url)
            return redirect(url_for('dashboard'))
        else:
            # VULN: Username enumeration - different messages
            check_user = db.execute(f"SELECT * FROM users WHERE username = '{username}'").fetchone()
            if check_user:
                # VULN: Reveals that username exists
                error = "Invalid password for this account."
                db.execute("UPDATE users SET failed_logins = failed_logins + 1 WHERE username = ?", (username,))
                if check_user['failed_logins'] >= 4:
                    db.execute("UPDATE users SET locked = 1 WHERE username = ?", (username,))
                db.commit()
            else:
                error = "User not found in our system."

    return render_template('login.html', error=error)


# --- VULN: Username enumeration via registration (Auth #4) ---
# --- VULN: Second-order SQLi (stored payload) (SQLi #2) ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        email = request.form.get('email', '')

        db = get_db()
        existing = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            # VULN: Username enumeration - confirms existing usernames
            error = f"Username '{username}' is already taken. Please choose another."
            return render_template('register.html', error=error)

        # VULN: Second-order SQLi - username stored as-is, triggered later
        db.execute("INSERT INTO users (username, password, email, role, department) VALUES (?, ?, ?, 'employee', 'General')",
                   (username, password, email))
        db.commit()

        new_user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        emp_id = 1100 + new_user['id']
        db.execute("INSERT INTO employees (id, user_id, first_name, last_name, position, salary, ssn, phone, address) VALUES (?,?,?,?,?,?,?,?,?)",
                   (emp_id, new_user['id'], username, 'New', 'New Employee', 50000, '000-00-0000', '555-0000', 'TBD'))
        db.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', error=error)


# --- VULN: MFA bypass - code not bound to user session (Auth #5) ---
# --- VULN: MFA brute force - short numeric code (Auth #6) ---
# --- VULN: MFA code reuse (Auth #7) ---
@app.route('/mfa', methods=['GET', 'POST'])
def mfa_verify():
    if 'mfa_user_id' not in session:
        return redirect(url_for('login'))

    error = None
    if request.method == 'POST':
        code = request.form.get('mfa_code', '')
        # VULN: submitted username can differ from authenticated user
        submitted_username = request.form.get('username', session.get('mfa_username', ''))

        db = get_db()

        # VULN: MFA code accepted for ANY user - not bound to session user
        mfa_record = db.execute("SELECT * FROM mfa_codes WHERE code = ?", (code,)).fetchone()

        if mfa_record:
            # VULN: Username from form, not from session - MFA bypass via username swap
            target_user = db.execute("SELECT * FROM users WHERE username = ?", (submitted_username,)).fetchone()
            if target_user:
                session.permanent = True
                session['user_id'] = target_user['id']
                session['username'] = target_user['username']
                session['role'] = target_user['role']
                session.pop('mfa_user_id', None)
                session.pop('mfa_username', None)
                return redirect(url_for('dashboard'))

        error = "Invalid MFA code."

    return render_template('mfa.html', error=error, username=session.get('mfa_username', ''))


# --- VULN: Predictable password reset token (Auth #8) ---
# --- VULN: Username enumeration via reset (Auth #9) ---
@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    message = None
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '')
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            # VULN: Predictable reset token (sequential + timestamp)
            token = hashlib.md5(f"{user['id']}{int(time.time())}".encode()).hexdigest()
            db.execute("INSERT INTO password_resets (user_id, token) VALUES (?, ?)",
                       (user['id'], token))
            db.commit()
            message = f"If an account exists with that email, a password reset link has been sent."
        else:
            # VULN: Username enumeration
            error = "No account found with that email address."

    return render_template('reset_password.html', message=message, error=error)


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password_confirm(token):
    db = get_db()
    reset = db.execute("SELECT * FROM password_resets WHERE token = ?", (token,)).fetchone()
    if not reset:
        flash('Invalid or expired reset token.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_password = request.form.get('password', '')
        db.execute("UPDATE users SET password = ? WHERE id = ?", (new_password, reset['user_id']))
        db.execute("DELETE FROM password_resets WHERE token = ?", (token,))
        db.commit()
        flash('Password updated successfully!', 'success')
        return redirect(url_for('login'))

    return render_template('reset_confirm.html', token=token)


@app.route('/logout')
def logout():
    session.clear()
    # VULN: Open redirect #2 - unvalidated return URL
    return_url = request.args.get('return', url_for('login'))
    return redirect(return_url)


# ============================================================
# DASHBOARD
# ============================================================

@app.route('/dashboard')
@login_required
def dashboard():
    user = get_current_user()
    db = get_db()
    tickets = db.execute("SELECT * FROM support_tickets WHERE user_id = ? ORDER BY created_at DESC LIMIT 5",
                         (session['user_id'],)).fetchall()
    return render_template('dashboard.html', user=user, tickets=tickets)


# ============================================================
# EMPLOYEE DIRECTORY - IDOR / ACCESS CONTROL
# ============================================================

# --- VULN: IDOR #1 - enumerate employee records by ID ---
@app.route('/employees')
@login_required
def employees():
    db = get_db()
    emps = db.execute("SELECT e.*, u.username, u.email, u.role FROM employees e JOIN users u ON e.user_id = u.id").fetchall()
    return render_template('employees.html', employees=emps)


# --- VULN: IDOR #2 - access any employee by changing ID ---
# --- VULN: Horizontal access control bypass ---
@app.route('/employees/<int:emp_id>')
@login_required
def employee_detail(emp_id):
    db = get_db()
    # VULN: No check that current user is authorized to view this employee
    emp = db.execute("SELECT e.*, u.username, u.email, u.role, u.bio FROM employees e JOIN users u ON e.user_id = u.id WHERE e.id = ?",
                     (emp_id,)).fetchone()
    if not emp:
        abort(404)
    return render_template('employee_detail.html', emp=emp)


# --- VULN: SQL Injection #3 - employee search ---
@app.route('/employees/search')
@login_required
def employee_search():
    q = request.args.get('q', '')
    db = get_db()
    results = []
    if q:
        # VULN: SQL Injection in search
        query = f"SELECT e.*, u.username, u.email FROM employees e JOIN users u ON e.user_id = u.id WHERE e.first_name LIKE '%{q}%' OR e.last_name LIKE '%{q}%' OR u.username LIKE '%{q}%'"
        try:
            results = db.execute(query).fetchall()
        except Exception as e:
            flash(f'Search error: {e}', 'error')
    return render_template('employees.html', employees=results, search=q)


# ============================================================
# PROFILE - XSS / CSRF / IDOR
# ============================================================

# --- VULN: IDOR #3 - view any user's profile ---
@app.route('/profile')
@app.route('/profile/<int:user_id>')
@login_required
def profile(user_id=None):
    if user_id is None:
        user_id = session['user_id']
    db = get_db()
    # VULN: No authorization check - any user can view any profile
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        abort(404)

    # VULN: Second-order SQLi triggered here - bio rendered from DB
    # The username is used in a raw query for "recent activity"
    activity_query = f"SELECT * FROM support_tickets WHERE user_id = (SELECT id FROM users WHERE username = '{user['username']}')"
    try:
        activities = db.execute(activity_query).fetchall()
    except:
        activities = []

    return render_template('profile.html', profile_user=user, activities=activities)


# --- VULN: Stored XSS #1 - bio field not sanitized ---
# --- VULN: CSRF #1 - no CSRF token on profile update ---
# --- VULN: Horizontal access control #2 - can update any user's profile ---
@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def profile_edit():
    db = get_db()

    if request.method == 'POST':
        # VULN: user_id from form, not session - can edit anyone's profile
        user_id = request.form.get('user_id', session['user_id'])
        bio = request.form.get('bio', '')
        email = request.form.get('email', '')
        department = request.form.get('department', '')

        # VULN: No sanitization on bio - stored XSS
        db.execute("UPDATE users SET bio = ?, email = ?, department = ? WHERE id = ?",
                   (bio, email, department, user_id))
        db.commit()
        flash('Profile updated!', 'success')
        return redirect(url_for('profile', user_id=user_id))

    user = get_current_user()
    return render_template('profile_edit.html', user=user)


# --- VULN: SSTI #1 - custom greeting with user input ---
@app.route('/profile/greeting', methods=['GET', 'POST'])
@login_required
def profile_greeting():
    result = None
    if request.method == 'POST':
        template_str = request.form.get('greeting', '')
        # VULN: SSTI - user input passed directly to render_template_string
        try:
            result = render_template_string(template_str)
        except Exception as e:
            result = f"Template error: {e}"
    return render_template('greeting.html', result=result)


# ============================================================
# PRODUCTS - SQLi / XSS
# ============================================================

@app.route('/products')
@login_required
def products():
    db = get_db()
    prods = db.execute("SELECT * FROM products").fetchall()
    return render_template('products.html', products=prods)


# --- VULN: UNION-based SQL Injection #4 ---
# --- VULN: Reflected XSS #1 - search term reflected ---
@app.route('/products/search')
@login_required
def product_search():
    q = request.args.get('q', '')
    db = get_db()
    results = []
    if q:
        # VULN: SQL Injection - UNION-based
        query = f"SELECT id, name, description, price, category FROM products WHERE name LIKE '%{q}%' OR description LIKE '%{q}%'"
        try:
            results = db.execute(query).fetchall()
        except Exception as e:
            flash(f'Error: {e}', 'error')

    # VULN: Reflected XSS - q reflected without escaping in template
    return render_template('product_search.html', products=results, query=q)


# --- VULN: Blind SQL Injection #5 ---
@app.route('/products/filter')
@login_required
def product_filter():
    category = request.args.get('category', '')
    db = get_db()
    # VULN: Blind SQL Injection - boolean-based
    query = f"SELECT * FROM products WHERE category = '{category}'"
    try:
        results = db.execute(query).fetchall()
        return render_template('products.html', products=results, filter_cat=category)
    except:
        return render_template('products.html', products=[], filter_cat=category)


# --- VULN: Stored XSS #2 - review content not sanitized ---
@app.route('/products/<int:product_id>')
@login_required
def product_detail(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        abort(404)
    reviews = db.execute("SELECT * FROM reviews WHERE product_id = ? ORDER BY created_at DESC", (product_id,)).fetchall()
    return render_template('product_detail.html', product=product, reviews=reviews)


@app.route('/products/<int:product_id>/review', methods=['POST'])
@login_required
def product_review(product_id):
    content = request.form.get('content', '')
    rating = request.form.get('rating', 5)
    db = get_db()
    # VULN: Stored XSS - review content stored without sanitization
    db.execute("INSERT INTO reviews (product_id, user_id, username, content, rating) VALUES (?,?,?,?,?)",
               (product_id, session['user_id'], session['username'], content, rating))
    db.commit()
    return redirect(url_for('product_detail', product_id=product_id))


# ============================================================
# SUPPORT TICKETS - IDOR / XSS / CSRF
# ============================================================

@app.route('/support')
@login_required
def support():
    db = get_db()
    if session.get('role') in ('admin', 'manager', 'hr'):
        tickets = db.execute("SELECT t.*, u.username FROM support_tickets t JOIN users u ON t.user_id = u.id ORDER BY t.created_at DESC").fetchall()
    else:
        tickets = db.execute("SELECT t.*, u.username FROM support_tickets t JOIN users u ON t.user_id = u.id WHERE t.user_id = ? ORDER BY t.created_at DESC",
                             (session['user_id'],)).fetchall()
    return render_template('support.html', tickets=tickets)


# --- VULN: IDOR #4 - view any ticket by changing ID ---
@app.route('/support/ticket/<int:ticket_id>')
@login_required
def support_ticket(ticket_id):
    db = get_db()
    # VULN: No authorization check - any user can view any ticket
    ticket = db.execute("SELECT t.*, u.username FROM support_tickets t JOIN users u ON t.user_id = u.id WHERE t.id = ?",
                        (ticket_id,)).fetchone()
    if not ticket:
        abort(404)
    replies = db.execute("SELECT * FROM ticket_replies WHERE ticket_id = ? ORDER BY created_at", (ticket_id,)).fetchall()
    return render_template('support_ticket.html', ticket=ticket, replies=replies)


# --- VULN: Stored XSS #3 - ticket content not sanitized ---
# --- VULN: CSRF #2 - no CSRF token ---
@app.route('/support/create', methods=['GET', 'POST'])
@login_required
def support_create():
    if request.method == 'POST':
        title = request.form.get('title', '')
        content = request.form.get('content', '')
        priority = request.form.get('priority', 'medium')
        db = get_db()
        # VULN: Stored XSS - title and content stored without sanitization
        db.execute("INSERT INTO support_tickets (user_id, title, content, priority) VALUES (?,?,?,?)",
                   (session['user_id'], title, content, priority))
        db.commit()
        flash('Ticket created!', 'success')
        return redirect(url_for('support'))
    return render_template('support_create.html')


# --- VULN: SQL Injection #6 - ticket search ---
@app.route('/support/search')
@login_required
def support_search():
    q = request.args.get('q', '')
    db = get_db()
    results = []
    if q:
        # VULN: SQL Injection in ticket search
        query = f"SELECT t.*, u.username FROM support_tickets t JOIN users u ON t.user_id = u.id WHERE t.title LIKE '%{q}%' OR t.content LIKE '%{q}%'"
        try:
            results = db.execute(query).fetchall()
        except Exception as e:
            flash(f'Search error: {e}', 'error')
    return render_template('support.html', tickets=results, search=q)


# --- VULN: IDOR #5 - reply to any ticket ---
@app.route('/support/ticket/<int:ticket_id>/reply', methods=['POST'])
@login_required
def ticket_reply(ticket_id):
    content = request.form.get('content', '')
    db = get_db()
    # VULN: No check that user owns this ticket
    db.execute("INSERT INTO ticket_replies (ticket_id, user_id, username, content) VALUES (?,?,?,?)",
               (ticket_id, session['user_id'], session['username'], content))
    db.commit()
    return redirect(url_for('support_ticket', ticket_id=ticket_id))


# ============================================================
# INTERNAL TOOLS - COMMAND INJECTION / SSRF
# ============================================================

@app.route('/tools')
@login_required
def tools():
    return render_template('tools.html')


# --- VULN: Command Injection #1 - basic ---
@app.route('/tools/ping', methods=['GET', 'POST'])
@login_required
def tools_ping():
    result = None
    if request.method == 'POST':
        host = request.form.get('host', '')
        # VULN: Command injection - direct shell execution
        try:
            result = subprocess.check_output(
                f"ping -c 2 {host}", shell=True, stderr=subprocess.STDOUT, timeout=10
            ).decode()
        except subprocess.TimeoutExpired:
            result = "Command timed out"
        except subprocess.CalledProcessError as e:
            result = e.output.decode()
        except Exception as e:
            result = str(e)
    return render_template('tool_ping.html', result=result)


# --- VULN: Command Injection #2 - with weak filter (semicolon removed) ---
@app.route('/tools/dns', methods=['GET', 'POST'])
@login_required
def tools_dns():
    result = None
    if request.method == 'POST':
        domain = request.form.get('domain', '')
        # VULN: Weak filter - only removes semicolons
        domain = domain.replace(';', '')
        try:
            result = subprocess.check_output(
                f"nslookup {domain}", shell=True, stderr=subprocess.STDOUT, timeout=10
            ).decode()
        except subprocess.TimeoutExpired:
            result = "Command timed out"
        except subprocess.CalledProcessError as e:
            result = e.output.decode()
        except Exception as e:
            result = str(e)
    return render_template('tool_dns.html', result=result)


# --- VULN: Blind Command Injection #3 - no output displayed ---
@app.route('/tools/traceroute', methods=['GET', 'POST'])
@login_required
def tools_traceroute():
    message = None
    if request.method == 'POST':
        host = request.form.get('host', '')
        # VULN: Blind command injection - output not shown
        try:
            subprocess.Popen(
                f"traceroute {host} > /dev/null 2>&1", shell=True
            )
            message = f"Traceroute to {host} started in background. Results will be emailed."
        except Exception as e:
            message = f"Error: {e}"
    return render_template('tool_traceroute.html', message=message)


# --- VULN: SSRF #1 - server fetches user-supplied URL ---
@app.route('/tools/urlcheck', methods=['GET', 'POST'])
@login_required
def tools_urlcheck():
    result = None
    status = None
    if request.method == 'POST':
        url = request.form.get('url', '')
        # VULN: SSRF - server fetches arbitrary URL
        try:
            resp = requests.get(url, timeout=5, allow_redirects=True)
            status = resp.status_code
            result = resp.text[:5000]
        except Exception as e:
            result = f"Error: {e}"
    return render_template('tool_urlcheck.html', result=result, status=status)


# --- VULN: Blind SSRF #2 - webhook tester ---
@app.route('/tools/webhook', methods=['GET', 'POST'])
@login_required
def tools_webhook():
    message = None
    if request.method == 'POST':
        url = request.form.get('webhook_url', '')
        payload = request.form.get('payload', '{"test": true}')
        # VULN: Blind SSRF - server makes request, only shows success/fail
        try:
            requests.post(url, data=payload, timeout=5,
                         headers={'Content-Type': 'application/json'})
            message = "Webhook sent successfully!"
        except Exception as e:
            message = f"Webhook delivery failed: connection error"
    return render_template('tool_webhook.html', message=message)


# --- VULN: SSRF #3 - price comparison fetches vendor URLs ---
@app.route('/tools/compare', methods=['GET', 'POST'])
@login_required
def tools_compare():
    result = None
    if request.method == 'POST':
        vendor_url = request.form.get('vendor_url', '')
        # VULN: SSRF - fetches vendor price from user-supplied URL
        try:
            resp = requests.get(vendor_url, timeout=5)
            result = resp.text[:3000]
        except Exception as e:
            result = f"Could not reach vendor: {e}"
    return render_template('tool_compare.html', result=result)


# ============================================================
# DOCUMENTS - FILE UPLOAD / LFI / RFI
# ============================================================

@app.route('/documents')
@login_required
def documents():
    db = get_db()
    docs = db.execute("SELECT * FROM documents WHERE user_id = ?", (session['user_id'],)).fetchall()
    files = os.listdir(DOCUMENTS_FOLDER) if os.path.isdir(DOCUMENTS_FOLDER) else []
    return render_template('documents.html', docs=docs, files=files)


# --- VULN: File Upload #1 - no server-side validation (client-side JS only) ---
@app.route('/documents/upload', methods=['POST'])
@login_required
def document_upload():
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('documents'))

    f = request.files['file']
    if f.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('documents'))

    # VULN: No server-side file type validation
    filename = f.filename
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    f.save(filepath)

    db = get_db()
    db.execute("INSERT INTO documents (user_id, filename, original_name) VALUES (?,?,?)",
               (session['user_id'], filename, f.filename))
    db.commit()
    flash('File uploaded successfully!', 'success')
    return redirect(url_for('documents'))


# --- VULN: File Upload #2 - MIME type check only (bypassable) ---
@app.route('/profile/avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'avatar' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('profile_edit'))

    f = request.files['avatar']
    # VULN: Only checks Content-Type header, not actual file content
    allowed_mimes = ['image/jpeg', 'image/png', 'image/gif']
    if f.content_type not in allowed_mimes:
        flash('Only image files (JPG, PNG, GIF) are allowed!', 'error')
        return redirect(url_for('profile_edit'))

    filename = f"{session['user_id']}_{f.filename}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    f.save(filepath)

    db = get_db()
    db.execute("UPDATE users SET avatar = ? WHERE id = ?", (filename, session['user_id']))
    db.commit()
    flash('Avatar updated!', 'success')
    return redirect(url_for('profile'))


# --- VULN: File Upload #3 - extension blocklist (bypassable) ---
@app.route('/support/attach', methods=['POST'])
@login_required
def support_attach():
    if 'attachment' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('support'))

    f = request.files['attachment']
    # VULN: Blocklist - only blocks these specific extensions
    blocked = ['.php', '.exe', '.sh', '.bat', '.cmd']
    ext = os.path.splitext(f.filename)[1].lower()
    if ext in blocked:
        flash('File type not allowed!', 'error')
        return redirect(url_for('support'))

    # VULN: .phtml, .php5, .phar, etc. bypass the blocklist
    filename = f.filename
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    f.save(filepath)
    flash('Attachment uploaded!', 'success')
    return redirect(url_for('support'))


# --- VULN: LFI #1 - basic directory traversal ---
@app.route('/documents/view')
@login_required
def document_view():
    filename = request.args.get('file', '')
    if not filename:
        return redirect(url_for('documents'))

    # VULN: LFI - no path traversal protection
    filepath = os.path.join(DOCUMENTS_FOLDER, filename)
    try:
        with open(filepath, 'r') as f:
            content = f.read()
    except Exception as e:
        content = f"Error reading file: {e}"

    return render_template('document_view.html', filename=filename, content=content)


# --- VULN: LFI #2 - with weak filter (single ../ removal, non-recursive) ---
@app.route('/pages')
@login_required
def pages():
    page = request.args.get('page', 'welcome')
    # VULN: Non-recursive filter - ..././ becomes ../
    page = page.replace('../', '')
    filepath = os.path.join(DOCUMENTS_FOLDER, page)
    try:
        with open(filepath, 'r') as f:
            content = f.read()
    except:
        content = "Page not found."
    return render_template('page_view.html', content=content, page=page)


# --- VULN: LFI #3 / RFI - page parameter accepts URLs ---
@app.route('/resources')
@login_required
def resources():
    resource = request.args.get('src', '')
    content = ''
    if resource:
        if resource.startswith('http://') or resource.startswith('https://'):
            # VULN: RFI - fetches and displays remote content
            try:
                resp = requests.get(resource, timeout=5)
                content = resp.text[:5000]
            except:
                content = "Could not fetch resource."
        else:
            # VULN: LFI fallback
            filepath = os.path.join(DOCUMENTS_FOLDER, resource)
            try:
                with open(filepath, 'r') as f:
                    content = f.read()
            except:
                content = "Resource not found."
    return render_template('page_view.html', content=content, page=resource)


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(filepath):
        return "Not found", 404
    # VULN: Script execution - .py and .sh files are executed, mirroring PHP execution behaviour
    if filename.endswith('.py'):
        try:
            result = subprocess.check_output(
                ['python3', filepath], stderr=subprocess.STDOUT, timeout=10
            ).decode()
        except subprocess.CalledProcessError as e:
            result = e.output.decode()
        except Exception as e:
            result = str(e)
        return result, 200, {'Content-Type': 'text/plain'}
    if filename.endswith('.sh'):
        try:
            result = subprocess.check_output(
                ['bash', filepath], stderr=subprocess.STDOUT, timeout=10
            ).decode()
        except subprocess.CalledProcessError as e:
            result = e.output.decode()
        except Exception as e:
            result = str(e)
        return result, 200, {'Content-Type': 'text/plain'}
    return send_from_directory(UPLOAD_FOLDER, filename)


# ============================================================
# REPORTS - XXE / SSTI
# ============================================================

@app.route('/reports')
@login_required
def reports():
    return render_template('reports.html')


# --- VULN: XXE #1 - XML report import ---
@app.route('/reports/import', methods=['GET', 'POST'])
@login_required
def report_import():
    result = None
    if request.method == 'POST':
        xml_data = request.form.get('xml_data', '')
        if xml_data:
            # VULN: XXE - external entity loading enabled
            try:
                parser = etree.XMLParser(resolve_entities=True, load_dtd=True, no_network=False)
                doc = etree.fromstring(xml_data.encode(), parser)
                result = etree.tostring(doc, pretty_print=True).decode()
            except Exception as e:
                result = f"XML Parse Error: {e}"
    return render_template('report_import.html', result=result)


# --- VULN: XXE #2 - XML file upload and parse ---
@app.route('/reports/upload-xml', methods=['POST'])
@login_required
def report_upload_xml():
    if 'xmlfile' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('reports'))

    f = request.files['xmlfile']
    xml_data = f.read()
    # VULN: XXE - parsing uploaded XML with entities enabled
    try:
        parser = etree.XMLParser(resolve_entities=True, load_dtd=True, no_network=False)
        doc = etree.fromstring(xml_data, parser)
        result = etree.tostring(doc, pretty_print=True).decode()
    except Exception as e:
        result = f"XML Parse Error: {e}"
    return render_template('report_import.html', result=result)


# --- VULN: XXE #3 - API XML endpoint ---
@app.route('/api/v1/data/import', methods=['POST'])
def api_data_import():
    xml_data = request.data
    if xml_data:
        try:
            parser = etree.XMLParser(resolve_entities=True, load_dtd=True, no_network=False)
            doc = etree.fromstring(xml_data, parser)
            result = etree.tostring(doc, pretty_print=True).decode()
            return jsonify({'status': 'success', 'data': result})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 400
    return jsonify({'status': 'error', 'message': 'No XML data provided'}), 400


# --- VULN: SSTI #2 - report template generation ---
@app.route('/reports/generate', methods=['GET', 'POST'])
@login_required
def report_generate():
    result = None
    if request.method == 'POST':
        template = request.form.get('template', '')
        # VULN: SSTI - user-controlled template string
        try:
            result = render_template_string(template)
        except Exception as e:
            result = f"Template error: {e}"
    return render_template('report_generate.html', result=result)


# --- VULN: SSTI #3 - email preview ---
@app.route('/reports/email-preview', methods=['GET', 'POST'])
@login_required
def email_preview():
    result = None
    if request.method == 'POST':
        subject = request.form.get('subject', '')
        body = request.form.get('body', '')
        # VULN: SSTI - body rendered as template
        template_str = f"<h3>{subject}</h3><div>{body}</div>"
        try:
            result = render_template_string(template_str)
        except Exception as e:
            result = f"Render error: {e}"
    return render_template('email_preview.html', result=result)


# ============================================================
# NEWS - XSS (Reflected, DOM-based)
# ============================================================

# --- VULN: DOM-based XSS #1 - URL hash processed client-side ---
# --- VULN: Reflected XSS #2 - tag parameter ---
@app.route('/news')
@login_required
def news():
    tag = request.args.get('tag', '')
    articles = [
        {'id': 1, 'title': 'Thyhe Q3 Results Exceed Expectations', 'date': '2024-10-15', 'summary': 'Revenue up 23% year-over-year...'},
        {'id': 2, 'title': 'New Security Product Launch', 'date': '2024-10-10', 'summary': 'Introducing EndPoint Armor v2...'},
        {'id': 3, 'title': 'Employee Appreciation Week', 'date': '2024-10-05', 'summary': 'Join us for special events...'},
    ]
    db = get_db()
    for a in articles:
        a['comments'] = db.execute("SELECT * FROM news_comments WHERE article_id = ? ORDER BY created_at DESC", (a['id'],)).fetchall()
    # VULN: tag reflected without escaping
    return render_template('news.html', articles=articles, tag=tag)


# --- VULN: Reflected XSS #3 - error message reflected ---
@app.route('/error')
def error_page():
    msg = request.args.get('msg', 'An unknown error occurred.')
    # VULN: Error message reflected without sanitization
    return render_template('error.html', message=msg)


# --- VULN: Stored XSS #4 - news comments ---
@app.route('/news/<int:article_id>/comment', methods=['POST'])
@login_required
def news_comment(article_id):
    comment = request.form.get('comment', '')
    db = get_db()
    # VULN: Stored XSS - comment stored without sanitization
    db.execute("INSERT INTO news_comments (article_id, username, comment) VALUES (?,?,?)",
               (article_id, session['username'], comment))
    db.commit()
    return redirect(url_for('news'))


# --- VULN: DOM-based XSS #2 - welcome page with name from URL ---
@app.route('/welcome')
def welcome():
    return render_template('welcome.html')


# ============================================================
# SETTINGS - CSRF
# ============================================================

# --- VULN: CSRF #3 - weak token validation (checks existence only) ---
@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    db = get_db()
    user = get_current_user()

    if request.method == 'POST':
        csrf_token = request.form.get('csrf_token', '')
        # VULN: Only checks that csrf_token field EXISTS, not its value
        if csrf_token:
            email = request.form.get('email', '')
            password = request.form.get('password', '')
            if email:
                db.execute("UPDATE users SET email = ? WHERE id = ?", (email, session['user_id']))
            if password:
                db.execute("UPDATE users SET password = ? WHERE id = ?", (password, session['user_id']))
            db.commit()
            flash('Settings updated!', 'success')
        else:
            flash('Missing security token!', 'error')

    return render_template('settings.html', user=user)


# ============================================================
# MESSAGING - Stored XSS / IDOR
# ============================================================

@app.route('/messages')
@login_required
def messages():
    db = get_db()
    msgs = db.execute("""
        SELECT m.*, u.username as from_username
        FROM messages m JOIN users u ON m.from_user = u.id
        WHERE m.to_user = ? ORDER BY m.created_at DESC
    """, (session['user_id'],)).fetchall()
    return render_template('messages.html', messages=msgs)


# --- VULN: IDOR #6 - view any message by ID ---
@app.route('/messages/<int:msg_id>')
@login_required
def message_detail(msg_id):
    db = get_db()
    # VULN: No check that message belongs to current user
    msg = db.execute("""
        SELECT m.*, u.username as from_username
        FROM messages m JOIN users u ON m.from_user = u.id
        WHERE m.id = ?
    """, (msg_id,)).fetchone()
    if not msg:
        abort(404)
    return render_template('message_detail.html', message=msg)


# --- VULN: Stored XSS #5 - message body ---
@app.route('/messages/send', methods=['GET', 'POST'])
@login_required
def message_send():
    if request.method == 'POST':
        to_user = request.form.get('to_user', '')
        subject = request.form.get('subject', '')
        body = request.form.get('body', '')
        db = get_db()
        target = db.execute("SELECT id FROM users WHERE username = ?", (to_user,)).fetchone()
        if target:
            db.execute("INSERT INTO messages (from_user, to_user, subject, body) VALUES (?,?,?,?)",
                       (session['user_id'], target['id'], subject, body))
            db.commit()
            flash('Message sent!', 'success')
        else:
            flash('User not found.', 'error')
        return redirect(url_for('messages'))

    db = get_db()
    users = db.execute("SELECT username FROM users").fetchall()
    return render_template('message_send.html', users=users)


# ============================================================
# ADMIN PANEL - VERTICAL ACCESS CONTROL
# ============================================================

# --- VULN: Vertical access control #1 - no role check ---
@app.route('/admin')
@login_required
def admin_panel():
    # VULN: No role verification - any authenticated user can access
    db = get_db()
    users = db.execute("SELECT * FROM users").fetchall()
    stats = {
        'total_users': len(users),
        'total_tickets': db.execute("SELECT COUNT(*) FROM support_tickets").fetchone()[0],
        'total_products': db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
    }
    return render_template('admin.html', users=users, stats=stats)


# --- VULN: Vertical access control #2 - delete user without admin check ---
@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    # VULN: No role check
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    flash('User deleted.', 'success')
    return redirect(url_for('admin_panel'))


# --- VULN: Vertical access control #3 - update user roles ---
@app.route('/admin/update-role', methods=['POST'])
@login_required
def admin_update_role():
    # VULN: No role check - any user can promote themselves
    user_id = request.form.get('user_id', '')
    new_role = request.form.get('role', '')
    db = get_db()
    db.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
    db.commit()
    flash('Role updated.', 'success')
    return redirect(url_for('admin_panel'))


# ============================================================
# API ENDPOINTS - JWT / IDOR / BOLA
# ============================================================

def verify_jwt(token):
    try:
        # VULN: JWT algorithm "none" accepted
        header = jwt.get_unverified_header(token)
        if header.get('alg') == 'none':
            return jwt.decode(token, options={"verify_signature": False}, algorithms=["none"])
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except:
        return None


def jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token required'}), 401
        payload = verify_jwt(token)
        if not payload:
            return jsonify({'error': 'Invalid token'}), 401
        g.jwt_user = payload
        return f(*args, **kwargs)
    return decorated


# --- VULN: JWT with weak secret / algorithm none (Auth #10, #11) ---
@app.route('/api/v1/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    username = data.get('username', '')
    password = data.get('password', '')

    db = get_db()
    # VULN: SQL Injection in API login too
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    try:
        user = db.execute(query).fetchone()
    except:
        return jsonify({'error': 'Database error'}), 500

    if user:
        # VULN: JWT with weak secret 'secret'
        token = jwt.encode({
            'user_id': user['id'],
            'username': user['username'],
            'role': user['role'],
            'exp': datetime.utcnow() + timedelta(hours=24)
        }, JWT_SECRET, algorithm='HS256')
        return jsonify({'token': token, 'role': user['role']})

    return jsonify({'error': 'Invalid credentials'}), 401


# --- VULN: BOLA/IDOR #7 - API get any user ---
@app.route('/api/v1/users/<int:user_id>')
@jwt_required
def api_get_user(user_id):
    db = get_db()
    # VULN: No check that JWT user matches requested user_id
    user = db.execute("SELECT id, username, email, role, bio, department FROM users WHERE id = ?",
                      (user_id,)).fetchone()
    if user:
        return jsonify(dict(user))
    return jsonify({'error': 'User not found'}), 404


# --- VULN: Broken function-level auth #4 - update any user via API ---
@app.route('/api/v1/users/<int:user_id>/update', methods=['PUT'])
@jwt_required
def api_update_user(user_id):
    data = request.get_json() or {}
    db = get_db()
    # VULN: Any authenticated user can update any other user's data
    updates = []
    params = []
    for field in ['bio', 'email', 'department', 'role']:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field])
    if updates:
        params.append(user_id)
        db.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        db.commit()
    return jsonify({'status': 'updated'})


# --- VULN: Vertical access - admin API accessible to any JWT holder ---
@app.route('/api/v1/admin/users')
@jwt_required
def api_admin_users():
    # VULN: No role check in JWT payload
    db = get_db()
    users = db.execute("SELECT id, username, email, role, department FROM users").fetchall()
    return jsonify([dict(u) for u in users])


# --- VULN: Blind SQL Injection via API ---
@app.route('/api/v1/users/check')
def api_check_user():
    username = request.args.get('username', '')
    db = get_db()
    # VULN: Blind SQLi - different responses for true/false
    query = f"SELECT * FROM users WHERE username = '{username}'"
    try:
        user = db.execute(query).fetchone()
        if user:
            return jsonify({'exists': True})
        return jsonify({'exists': False})
    except:
        return jsonify({'exists': False})


# ============================================================
# OPEN REDIRECT
# ============================================================

# --- VULN: Open Redirect #3 - dedicated redirect handler ---
@app.route('/redirect')
def open_redirect():
    url = request.args.get('url', '/')
    # VULN: No validation on redirect target
    return redirect(url)


# ============================================================
# SOLUTIONS PAGE
# ============================================================

@app.route('/solutions')
def solutions():
    return redirect(url_for('walkthrough'))


@app.route('/walkthrough')
def walkthrough():
    return render_template('walkthrough.html')


# ============================================================
# INTERNAL ADMIN PAGE (for SSRF targets)
# ============================================================

@app.route('/internal/admin')
def internal_admin():
    if request.remote_addr not in ('127.0.0.1', '::1'):
        abort(403)
    return "<h1>Internal Admin Panel</h1><p>DB Password: r00tP@ss</p><p>AWS Key: AKIAIOSFODNN7EXAMPLE</p><p>Flag: VULNCORP{ssrf_internal_access}</p>"


@app.route('/internal/status')
def internal_status():
    if request.remote_addr not in ('127.0.0.1', '::1'):
        abort(403)
    return jsonify({
        'status': 'running',
        'db': 'connected',
        'secret_flag': 'VULNCORP{blind_ssrf_confirmed}',
        'internal_services': ['mysql:3306', 'redis:6379', 'elasticsearch:9200']
    })


# Hidden pages - no links anywhere, only discoverable via directory brute-force
@app.route('/backup')
@login_required
def backup_page():
    return """<html><body><h1>Database Backups</h1>
    <ul><li><a href="/backup/thyhe_2026-01-15.sql.gz">thyhe_2026-01-15.sql.gz</a> (42MB)</li>
    <li><a href="/backup/thyhe_2025-12-01.sql.gz">thyhe_2025-12-01.sql.gz</a> (38MB)</li></ul>
    <p>Backup credentials: <code>backup_user:Bkp#2026!Secure</code></p></body></html>"""

@app.route('/debug.html')
@login_required
def debug_page():
    return """<html><body><h1>Debug Info</h1>
    <pre>APP_SECRET_KEY=%s\nDATABASE=%s\nDEBUG=True\nFLASK_ENV=development</pre>
    <p>Stack trace endpoint: <a href="/debug/trace">/debug/trace</a></p></body></html>""" % (app.secret_key, DATABASE)

@app.route('/config.json')
def config_json():
    return jsonify({
        'app': 'Thyhe', 'version': '2.3.1',
        'database': {'host': 'localhost', 'port': 3306, 'user': 'thyhe_app', 'password': 'V@ulnC0rp_db!'},
        'smtp': {'host': 'mail.thyhe.internal', 'user': 'noreply@thyhe.com', 'password': 'SmtpP@ss123'},
        'api_keys': {'stripe': 'sk_live_FAKEFAKEFAKE', 'sendgrid': 'SG.FAKEFAKEFAKE'}
    })


# ============================================================
# RUN
# ============================================================

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        print("[*] Initializing database...")
        init_db()
        print("[*] Database ready!")
    app.run(host='0.0.0.0', port=5000, debug=True)
