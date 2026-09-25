from flask import Flask, render_template_string, request, redirect, url_for, session, flash, send_from_directory, jsonify
import sqlite3, os, uuid, re
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "campuscare-complete-secret-key"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "campuscare.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

CATEGORIES = ["Hostel","Classroom","Laboratory","Washroom","Electricity","Water","Wi-Fi","Food/Mess","Cleaning","Security","Other"]
PRIORITIES = ["Low","Medium","High","Emergency"]
STATUSES = ["Submitted","Assigned","In Progress","Resolved","Closed"]
ALLOWED_EXTENSIONS = {"png","jpg","jpeg","gif","webp"}

DEMO_WORKERS = [
    ("Ravi Kumar", "Electrical", "9876543210"),
    ("Suresh Reddy", "Plumbing", "9876543211"),
    ("Arjun Kumar", "Cleaning", "9876543212"),
    ("Naveen Kumar", "Maintenance", "9876543213"),
    ("Mahesh", "Wi-Fi & Network", "9876543214"),
    ("Prakash", "Security", "9876543215"),
]

CONTACTS = [
    ("Campus Admin", "Administration", "9876500001"),
    ("Hostel Warden", "Hostel Office", "9876500002"),
    ("Maintenance Desk", "Maintenance", "9876500003"),
    ("Security Desk", "Security", "9876500004"),
    ("Emergency Help", "Emergency", "112"),
]

def get_db():
    con = sqlite3.connect(DATABASE)
    con.row_factory = sqlite3.Row
    return con

def initialize_database():
    con = get_db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'student',
        room TEXT DEFAULT '',
        mobile TEXT DEFAULT '',
        student_id TEXT DEFAULT '',
        department TEXT DEFAULT '',
        year TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS workers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        department TEXT NOT NULL,
        mobile TEXT NOT NULL,
        active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS complaints(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id TEXT UNIQUE NOT NULL,
        user_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        location TEXT NOT NULL,
        priority TEXT NOT NULL,
        image TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'Submitted',
        assigned_to TEXT DEFAULT '',
        assigned_worker_id INTEGER DEFAULT NULL,
        admin_remark TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(assigned_worker_id) REFERENCES workers(id)
    );
    CREATE TABLE IF NOT EXISTS feedback(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id INTEGER NOT NULL,
        rating INTEGER NOT NULL,
        comment TEXT DEFAULT '',
        FOREIGN KEY(complaint_id) REFERENCES complaints(id)
    );
    """)
    # Upgrade older databases safely.
    existing = {r[1] for r in con.execute("PRAGMA table_info(users)").fetchall()}
    for col, typ in [("mobile","TEXT DEFAULT ''"),("student_id","TEXT DEFAULT ''"),("department","TEXT DEFAULT ''"),("year","TEXT DEFAULT ''"),("created_at","TIMESTAMP")]:
        if col not in existing:
            con.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
    existing_c = {r[1] for r in con.execute("PRAGMA table_info(complaints)").fetchall()}
    if "assigned_worker_id" not in existing_c:
        con.execute("ALTER TABLE complaints ADD COLUMN assigned_worker_id INTEGER DEFAULT NULL")
    if not con.execute("SELECT 1 FROM users WHERE email=?", ("admin@campuscare.com",)).fetchone():
        con.execute("INSERT INTO users(name,email,password,role,mobile,department) VALUES(?,?,?,?,?,?)", ("Dr. Anil Kumar","admin@campuscare.com",generate_password_hash("admin123"),"admin","9876500001","Campus Administration"))
    if not con.execute("SELECT 1 FROM users WHERE email=?", ("student@campuscare.com",)).fetchone():
        con.execute("INSERT INTO users(name,email,password,role,room,mobile,student_id,department,year) VALUES(?,?,?,?,?,?,?,?,?)", ("Demo Student","student@campuscare.com",generate_password_hash("student123"),"student","B-204","9876543200","CC2026001","CSE","1st Year"))
    for name, dept, mobile in DEMO_WORKERS:
        if not con.execute("SELECT 1 FROM workers WHERE name=? AND department=?", (name,dept)).fetchone():
            con.execute("INSERT INTO workers(name,department,mobile) VALUES(?,?,?)", (name,dept,mobile))
    # Give old users a student ID if missing.
    rows = con.execute("SELECT id FROM users WHERE role='student' AND (student_id IS NULL OR student_id='')").fetchall()
    for r in rows:
        con.execute("UPDATE users SET student_id=? WHERE id=?", (f"CC{2026000+r['id']}", r['id']))
    con.commit(); con.close()

def allowed_file(filename):
    return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXTENSIONS

def current_user():
    if not session.get("user_id"): return None
    con=get_db(); u=con.execute("SELECT * FROM users WHERE id=?",(session["user_id"],)).fetchone(); con.close(); return u

@app.context_processor
def globals_ctx():
    return {"categories":CATEGORIES,"priorities":PRIORITIES,"statuses":STATUSES,"current_user":current_user()}

# ---------------- UI ----------------
SHELL = r'''
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title or "Campus Care" }}</title>
<style>
:root{--ink:#12233f;--muted:#71809a;--paper:#f5f7fb;--white:#fff;--blue:#3568ff;--blue2:#6b7cff;--green:#18a873;--orange:#f29a3f;--red:#e95d6a;--line:#e6eaf2;--shadow:0 18px 45px rgba(24,42,75,.08);--radius:22px}*{box-sizing:border-box}body{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial;color:var(--ink);background:var(--paper)}a{text-decoration:none;color:inherit}button,input,select,textarea{font:inherit}button{cursor:pointer}.app{min-height:100vh;display:flex}.sidebar{position:fixed;left:0;top:0;bottom:0;width:260px;background:#101d35;color:#fff;padding:26px 18px;display:flex;flex-direction:column;z-index:20;overflow:auto}.brand{display:flex;align-items:center;gap:12px;padding:5px 10px 25px}.logo{width:43px;height:43px;border-radius:14px;background:linear-gradient(135deg,#5d7cff,#31c9ff);display:grid;place-items:center;font-weight:900;box-shadow:0 10px 25px rgba(59,120,255,.28)}.brand h2{font-size:19px;margin:0}.brand small{display:block;color:#8491a9;font-size:11px;margin-top:2px}.side-label{font-size:10px;letter-spacing:1.5px;color:#667590;font-weight:800;padding:0 12px;margin:8px 0 10px}.nav{display:grid;gap:6px}.nav a{display:flex;align-items:center;gap:12px;padding:12px 13px;border-radius:14px;color:#9da9bd;font-size:13px;font-weight:700}.nav a:hover,.nav a.active{background:rgba(255,255,255,.08);color:#fff}.nav-icon{width:20px;text-align:center;font-size:16px}.side-bottom{margin-top:auto;padding-top:20px}.user-mini{border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.045);border-radius:18px;padding:13px;display:flex;gap:10px;align-items:center}.avatar{width:38px;height:38px;border-radius:12px;background:linear-gradient(135deg,#dbe4ff,#a9c8ff);color:#173263;display:grid;place-items:center;font-weight:850}.user-mini strong{display:block;font-size:13px}.user-mini span{font-size:10px;color:#8290a8}.logout{display:block;text-align:center;color:#9ba7bb;font-size:12px;margin-top:13px}.main{margin-left:260px;min-height:100vh;width:calc(100% - 260px)}.topbar{height:82px;background:rgba(255,255,255,.9);backdrop-filter:blur(14px);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 42px;position:sticky;top:0;z-index:10}.eyebrow{font-size:10px;letter-spacing:2px;font-weight:850;color:#8290a7}.top-right{display:flex;gap:10px;align-items:center}.content{padding:38px 42px 60px;max-width:1450px;margin:auto}.flash{margin:0 42px 18px;padding:13px 16px;border-radius:13px;font-size:13px;font-weight:650}.flash.success{background:#e7f8f0;color:#08764c}.flash.error{background:#fff0f1;color:#b52e3e}.page-head{display:flex;justify-content:space-between;gap:25px;align-items:flex-end;margin-bottom:28px}.page-head h1{font-size:34px;line-height:1.05;margin:7px 0 8px;letter-spacing:-1.3px}.page-head p{margin:0;color:var(--muted);font-size:14px}.btn{border:0;border-radius:13px;padding:12px 17px;font-weight:800;display:inline-flex;align-items:center;gap:8px;transition:.2s}.btn:hover{transform:translateY(-1px)}.btn-primary{background:#152742;color:#fff;box-shadow:0 10px 25px rgba(20,40,70,.18)}.btn-blue{background:var(--blue);color:#fff}.btn-light{background:#fff;border:1px solid var(--line);color:var(--ink)}.hero{position:relative;overflow:hidden;min-height:265px;border-radius:28px;padding:34px;color:#fff;background:radial-gradient(circle at 85% 20%,rgba(92,125,255,.8),transparent 26%),linear-gradient(135deg,#13233e,#203f73 58%,#3568b6);box-shadow:var(--shadow);margin-bottom:31px}.hero:before{content:"";position:absolute;width:330px;height:330px;border:1px solid rgba(255,255,255,.13);border-radius:50%;right:-80px;top:-90px}.hero:after{content:"";position:absolute;width:210px;height:210px;border:1px dashed rgba(255,255,255,.18);border-radius:50%;right:15px;top:-20px}.hero-content{position:relative;z-index:2;max-width:610px}.hero-kicker{font-size:10px;letter-spacing:2px;font-weight:850;color:#a9d8ff}.hero h2{font-size:29px;letter-spacing:-1px;margin:9px 0}.hero p{color:#c8d5e8;max-width:560px;line-height:1.6;font-size:13px}.hero-link{display:inline-block;margin-top:13px;background:#fff;color:#162842;padding:11px 16px;border-radius:12px;font-weight:800;font-size:13px}.orbit{position:absolute;right:80px;top:75px;width:88px;height:88px;border-radius:50%;border:2px solid rgba(255,255,255,.35);z-index:2}.orbit:after{content:"✓";position:absolute;right:-8px;top:12px;width:35px;height:35px;border-radius:11px;background:#fff;color:#1e62da;display:grid;place-items:center;font-weight:900;box-shadow:0 10px 30px rgba(0,0,0,.18)}.section-title{display:flex;align-items:center;justify-content:space-between;margin:0 0 15px}.section-title h3{margin:0;font-size:17px}.section-title span{font-size:11px;color:var(--muted)}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:31px}.stat{background:#fff;border:1px solid var(--line);border-radius:18px;padding:19px;box-shadow:0 8px 28px rgba(24,42,75,.04)}.stat-top{display:flex;justify-content:space-between;align-items:center;color:var(--muted);font-size:12px;font-weight:700}.stat-icon{width:34px;height:34px;border-radius:11px;background:#eef3ff;display:grid;place-items:center}.stat strong{display:block;font-size:30px;margin-top:9px}.card{background:#fff;border:1px solid var(--line);border-radius:22px;box-shadow:var(--shadow);padding:25px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.full{grid-column:1/-1}label{display:block;font-size:11px;font-weight:850;color:#52617a;margin:0 0 8px}input,select,textarea{width:100%;border:1px solid #e1e6ef;background:#fbfcfe;color:var(--ink);border-radius:13px;padding:12px 13px;outline:none}input:focus,select:focus,textarea:focus{border-color:#7694ff;box-shadow:0 0 0 4px #edf1ff}textarea{min-height:125px;resize:vertical}.form-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:22px}.upload{border:1.5px dashed #cdd6e4;border-radius:15px;padding:18px;text-align:center;background:#fafcff;color:#728098;font-size:12px}.upload input{border:0;background:transparent;padding:0;margin-top:8px}.auth-wrap{min-height:100vh;display:grid;place-items:center;padding:30px;background:radial-gradient(circle at 10% 10%,#e5edff,transparent 32%),#f5f7fb}.auth-card{width:min(480px,100%);background:#fff;border:1px solid var(--line);border-radius:28px;padding:34px;box-shadow:var(--shadow)}.auth-brand{display:flex;align-items:center;gap:11px;margin-bottom:25px}.auth-brand h1{font-size:20px;margin:0}.auth-brand span{display:block;color:var(--muted);font-size:11px;margin-top:2px}.auth-card h2{font-size:29px;margin:0 0 7px}.auth-card>p{color:var(--muted);font-size:13px;margin:0 0 23px}.auth-card form{display:grid;gap:14px}.auth-link{text-align:center;font-size:12px;color:var(--muted);margin-top:18px}.auth-link a{color:var(--blue);font-weight:800}.demo{margin-top:22px;background:#f3f6fb;border-radius:15px;padding:13px;font-size:11px;color:#63718a;line-height:1.6}.demo b{color:var(--ink)}.complaints{display:grid;gap:10px}.complaint-row{background:#fff;border:1px solid var(--line);border-radius:18px;padding:16px 18px;display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center}.row-meta{font-size:10px;color:#8995a9;font-weight:750;margin-bottom:6px}.row-title{font-size:14px;font-weight:820}.row-sub{font-size:11px;color:var(--muted);margin-top:6px}.row-right{display:flex;align-items:center;gap:12px}.chip{display:inline-flex;align-items:center;gap:5px;padding:6px 9px;border-radius:99px;font-size:10px;font-weight:850;white-space:nowrap}.chip.submitted{background:#eef3ff;color:#4168cc}.chip.assigned{background:#f4edff;color:#8054bc}.chip.progress{background:#fff4df;color:#ad6b12}.chip.resolved{background:#e8f8f0;color:#08794e}.chip.closed{background:#edf0f3;color:#657184}.chip.emergency{background:#ffe7ea;color:#c53a49}.arrow{color:#99a5b8;font-size:19px}.detail-grid{display:grid;grid-template-columns:1.55fr .8fr;gap:20px}.detail-title{display:flex;justify-content:space-between;gap:15px;align-items:flex-start}.detail-title h1{margin:0;font-size:27px}.mini-meta{font-size:11px;color:var(--muted);margin-top:8px}.detail-block{margin-top:23px}.detail-block h4{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#8390a5;margin:0 0 9px}.detail-block p{font-size:13px;line-height:1.65;color:#516078;margin:0}.photo{width:100%;max-height:300px;object-fit:cover;border-radius:16px}.timeline{display:grid}.step{display:grid;grid-template-columns:28px 1fr;gap:11px;position:relative;min-height:58px}.step:not(:last-child):before{content:"";position:absolute;left:10px;top:21px;bottom:0;width:2px;background:#e5e9f1}.dot{width:22px;height:22px;border-radius:50%;background:#e8edf5;color:#8a96aa;display:grid;place-items:center;font-size:10px;font-weight:900;z-index:2}.step.done .dot{background:#e4f7ee;color:#0b8b5a}.step.current .dot{background:#e8eeff;color:#3867dd}.step b{font-size:12px}.step span{display:block;color:#8b97a9;font-size:10px;margin-top:3px}.info-list{display:grid;gap:13px}.info-item{display:flex;justify-content:space-between;gap:15px;font-size:12px}.info-item span{color:var(--muted)}.info-item strong{text-align:right}.feedback{margin-top:18px;background:#f8fafc;border:1px solid var(--line);border-radius:17px;padding:17px}.toolbar{background:#fff;border:1px solid var(--line);border-radius:18px;padding:12px;display:grid;grid-template-columns:1fr 190px auto;gap:10px;margin-bottom:18px}.admin-list{display:grid;gap:14px}.admin-card{background:#fff;border:1px solid var(--line);border-radius:20px;padding:19px;box-shadow:0 8px 28px rgba(24,42,75,.04)}.admin-top{display:flex;justify-content:space-between;gap:15px}.admin-title{font-weight:850;font-size:15px;margin:5px 0}.admin-meta{font-size:10px;color:#8490a4}.admin-desc{font-size:12px;color:#637089;line-height:1.55;margin:13px 0}.admin-tags{display:flex;gap:7px;flex-wrap:wrap}.admin-form{margin-top:15px;padding-top:15px;border-top:1px solid #edf0f5;display:grid;grid-template-columns:1fr 1fr 1.4fr auto;gap:8px;align-items:end}.table-wrap{overflow:auto;background:#fff;border:1px solid var(--line);border-radius:20px;box-shadow:var(--shadow)}table{width:100%;border-collapse:collapse;min-width:850px}th,td{text-align:left;padding:14px 15px;border-bottom:1px solid #edf0f5;font-size:12px}th{font-size:10px;text-transform:uppercase;letter-spacing:.8px;color:#8490a4;background:#fafbfd}td strong{font-size:12px}.searchbar{display:grid;grid-template-columns:1fr auto;gap:10px;margin-bottom:17px}.profile-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.contact-grid,.worker-grid,.help-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.contact-card,.worker-card,.help-card{background:#fff;border:1px solid var(--line);border-radius:20px;padding:20px;box-shadow:0 8px 28px rgba(24,42,75,.04)}.contact-card h3,.worker-card h3,.help-card h3{margin:0 0 6px;font-size:15px}.muted{color:var(--muted);font-size:12px;line-height:1.6}.phone{display:inline-block;margin-top:12px;font-weight:850;color:#315fda}.faq{display:grid;gap:10px}.faq details{background:#fff;border:1px solid var(--line);border-radius:16px;padding:15px}.faq summary{font-weight:800;font-size:13px;cursor:pointer}.faq p{color:var(--muted);font-size:12px;line-height:1.6}.ai-box{display:grid;grid-template-rows:1fr auto;height:520px;background:#fff;border:1px solid var(--line);border-radius:24px;overflow:hidden;box-shadow:var(--shadow)}.chat{padding:20px;overflow:auto;background:linear-gradient(#fbfcff,#f5f7fb)}.msg{max-width:78%;padding:12px 14px;border-radius:16px;margin-bottom:10px;font-size:12px;line-height:1.55}.msg.ai{background:#fff;border:1px solid var(--line)}.msg.user{background:#152742;color:#fff;margin-left:auto}.chat-form{display:flex;gap:8px;padding:13px;border-top:1px solid var(--line);background:#fff}.chat-form input{flex:1}.floating-ai{position:fixed;right:25px;bottom:24px;width:58px;height:58px;border-radius:50%;background:linear-gradient(135deg,#3568ff,#6b7cff);color:#fff;display:grid;place-items:center;font-size:23px;box-shadow:0 15px 35px rgba(53,104,255,.35);z-index:15}.empty{background:#fff;border:1px dashed #ccd5e3;border-radius:18px;padding:35px;text-align:center;color:#7c899d;font-size:13px}.mobile-menu{display:none}
@media(max-width:1050px){.sidebar{width:220px}.main{margin-left:220px;width:calc(100% - 220px)}.stats{grid-template-columns:repeat(2,1fr)}.detail-grid,.profile-grid{grid-template-columns:1fr}.contact-grid,.worker-grid,.help-grid{grid-template-columns:repeat(2,1fr)}.admin-form{grid-template-columns:1fr 1fr}.toolbar{grid-template-columns:1fr 180px}.orbit{right:35px}}
@media(max-width:760px){.sidebar{position:fixed;transform:translateX(-100%);transition:.25s;width:250px}.sidebar.open{transform:translateX(0)}.main{margin-left:0;width:100%}.topbar{padding:0 18px}.content{padding:25px 18px 45px}.flash{margin:0 18px 15px}.mobile-menu{display:block;border:0;background:#eef2f8;border-radius:10px;width:38px;height:38px}.page-head{align-items:flex-start;flex-direction:column}.page-head h1{font-size:28px}.hero{padding:25px}.orbit{opacity:.35}.stats{grid-template-columns:1fr 1fr}.complaint-row{grid-template-columns:1fr}.row-right{justify-content:space-between}.toolbar,.searchbar{grid-template-columns:1fr}.admin-form,.form-grid{grid-template-columns:1fr}.full{grid-column:auto}.contact-grid,.worker-grid,.help-grid{grid-template-columns:1fr}.ai-box{height:600px}.auth-card{padding:25px}}
</style></head><body>
{% if session.get('user_id') %}<div class="app"><aside class="sidebar" id="sidebar"><div class="brand"><div class="logo">CC</div><div><h2>Campus Care</h2><small>Campus support hub</small></div></div><div class="side-label">{{ 'ADMIN SPACE' if session.get('role')=='admin' else 'STUDENT SPACE' }}</div><nav class="nav">
{% if session.get('role')=='admin' %}<a href="{{url_for('admin_dashboard')}}" class="{{'active' if request.endpoint=='admin_dashboard' else ''}}"><span class="nav-icon">▦</span>Dashboard</a><a href="{{url_for('admin_students')}}" class="{{'active' if request.endpoint=='admin_students' else ''}}"><span class="nav-icon">👨‍🎓</span>Students</a><a href="{{url_for('admin_workers')}}" class="{{'active' if request.endpoint=='admin_workers' else ''}}"><span class="nav-icon">👷</span>Workers</a><a href="{{url_for('contacts')}}" class="{{'active' if request.endpoint=='contacts' else ''}}"><span class="nav-icon">☎</span>Contacts</a><a href="{{url_for('ai_assistant')}}" class="{{'active' if request.endpoint=='ai_assistant' else ''}}"><span class="nav-icon">🤖</span>AI Assistant</a><a href="{{url_for('help_support')}}" class="{{'active' if request.endpoint=='help_support' else ''}}"><span class="nav-icon">?</span>Help & Support</a><a href="{{url_for('admin_profile')}}" class="{{'active' if request.endpoint=='admin_profile' else ''}}"><span class="nav-icon">⚙</span>Admin Profile</a>
{% else %}<a href="{{url_for('student_dashboard')}}" class="{{'active' if request.endpoint=='student_dashboard' else ''}}"><span class="nav-icon">⌂</span>Dashboard</a><a href="{{url_for('new_complaint')}}" class="{{'active' if request.endpoint=='new_complaint' else ''}}"><span class="nav-icon">＋</span>New complaint</a><a href="{{url_for('contacts')}}" class="{{'active' if request.endpoint=='contacts' else ''}}"><span class="nav-icon">☎</span>Contacts</a><a href="{{url_for('ai_assistant')}}" class="{{'active' if request.endpoint=='ai_assistant' else ''}}"><span class="nav-icon">🤖</span>AI Assistant</a><a href="{{url_for('help_support')}}" class="{{'active' if request.endpoint=='help_support' else ''}}"><span class="nav-icon">?</span>Help & Support</a><a href="{{url_for('student_profile')}}" class="{{'active' if request.endpoint=='student_profile' else ''}}"><span class="nav-icon">◉</span>My Profile</a>{% endif %}</nav><div class="side-bottom"><div class="user-mini"><div class="avatar">{{(session.get('name') or 'U')[0]|upper}}</div><div><strong>{{session.get('name')}}</strong><span>{{session.get('role')|capitalize}}</span></div></div><a class="logout" href="{{url_for('logout')}}">Sign out →</a></div></aside><main class="main"><header class="topbar"><div style="display:flex;align-items:center;gap:10px"><button class="mobile-menu" onclick="document.getElementById('sidebar').classList.toggle('open')">☰</button><span class="eyebrow">{{eyebrow or 'CAMPUS CARE'}}</span></div><div class="top-right"><span class="chip" style="background:#edf2ff;color:#4869c8">● {{'Admin mode' if session.get('role')=='admin' else 'Student mode'}}</span></div></header>{% with messages=get_flashed_messages(with_categories=true) %}{% for category,message in messages %}<div class="flash {{category}}">{{message}}</div>{% endfor %}{% endwith %}<section class="content">{{body|safe}}</section></main></div>{% else %}<div class="auth-wrap">{% with messages=get_flashed_messages(with_categories=true) %}{% for category,message in messages %}<div class="flash {{category}}" style="position:fixed;top:20px;left:50%;transform:translateX(-50%);z-index:50;width:min(450px,90%)">{{message}}</div>{% endfor %}{% endwith %}{{body|safe}}</div>{% endif %}
</body></html>'''

def render_page(body,title="Campus Care",eyebrow="CAMPUS CARE"):
    return render_template_string(SHELL,body=body,title=title,eyebrow=eyebrow)

def require(role):
    return session.get("role")==role

def ai_reply(message):
    m=message.lower().strip()
    if not m: return "Hi! I’m Campus Care Assistant. Ask me about complaints, login, contacts, status, workers, or app problems."
    if any(x in m for x in ["not working","app problem","error","bug","broken","website"]):
        return "Try these steps: refresh the page, check your internet connection, sign out and sign in again, and try Chrome/Edge. If image upload fails, use JPG/PNG and a smaller file. If it still fails, open Help & Support and contact the admin with a screenshot."
    if "login" in m or "password" in m: return "For login problems, check your email and password, then try again. Demo student: student@campuscare.com / student123. Demo admin: admin@campuscare.com / admin123."
    if "complaint" in m and ("register" in m or "submit" in m or "new" in m): return "Open New complaint, enter the issue title, category, location, priority and description, optionally attach a photo, then submit. You will receive a complaint ID such as CC-XXXXXXXX."
    if "status" in m or "track" in m: return "Open your Dashboard and select a complaint. The status timeline shows Submitted, Assigned, In Progress, Resolved and Closed."
    if "contact" in m or "phone" in m or "number" in m: return "Open Contacts in the sidebar to see campus support numbers for administration, hostel, maintenance, security and emergency help."
    if "worker" in m or "staff" in m: return "The admin can assign a worker from the Workers list. The assigned worker name appears on the complaint status page."
    if "student" in m and "admin" in m: return "Admins can open Students to view registered student details, contact information and complaint counts."
    if "emergency" in m: return "For a campus emergency, use the Emergency Help number shown on the Contacts page. If there is immediate danger, contact local emergency services."
    return "I can help with Campus Care. Try asking: ‘How do I submit a complaint?’, ‘Why is my complaint still in progress?’, ‘The app is not working’, ‘Show contacts’, or ‘How can admin see students?’"

LOGIN = r'''<div class="auth-card"><div class="auth-brand"><div class="logo">CC</div><div><h1>Campus Care</h1><span>Hostel & campus support hub</span></div></div><h2>Welcome back.</h2><p>Report an issue, track progress and connect with campus support.</p><form method="POST"><div><label>Email</label><input type="email" name="email" placeholder="you@college.edu" required></div><div><label>Password</label><input type="password" name="password" placeholder="Enter your password" required></div><button class="btn btn-primary" style="justify-content:center" type="submit">Sign in →</button></form><div class="auth-link">New here? <a href="{{url_for('register')}}">Create a student account</a></div><div class="demo"><b>Demo student</b><br>student@campuscare.com · student123<br><br><b>Demo admin</b><br>admin@campuscare.com · admin123</div></div>'''

REGISTER = r'''<div class="auth-card"><div class="auth-brand"><div class="logo">CC</div><div><h1>Campus Care</h1><span>Create your student support account</span></div></div><h2>Join Campus Care.</h2><p>Your registration details will be visible to authorized admins for support management.</p><form method="POST"><div><label>Full name *</label><input name="name" required placeholder="Your full name"></div><div><label>Email *</label><input type="email" name="email" required placeholder="you@college.edu"></div><div><label>Mobile number *</label><input name="mobile" required pattern="[0-9]{10}" maxlength="10" placeholder="10-digit mobile number"></div><div class="form-grid"><div><label>Student ID</label><input name="student_id" placeholder="CC2026002"></div><div><label>Hostel / Room</label><input name="room" placeholder="B-204"></div><div><label>Department</label><input name="department" placeholder="CSE"></div><div><label>Year</label><select name="year"><option value="">Select year</option><option>1st Year</option><option>2nd Year</option><option>3rd Year</option><option>4th Year</option></select></div></div><div><label>Password *</label><input type="password" name="password" required placeholder="Create a password"></div><button class="btn btn-blue" style="justify-content:center" type="submit">Create account →</button></form><div class="auth-link">Already registered? <a href="{{url_for('login')}}">Sign in</a></div></div>'''

@app.route('/')
def home():
    if not session.get('user_id'): return redirect(url_for('login'))
    return redirect(url_for('admin_dashboard' if session.get('role')=='admin' else 'student_dashboard'))

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        con=get_db(); u=con.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone(); con.close()
        if u and check_password_hash(u['password'],password):
            session.clear(); session.update(user_id=u['id'],name=u['name'],role=u['role']); return redirect(url_for('home'))
        flash('Invalid email or password.','error')
    return render_page(render_template_string(LOGIN),'Login')

@app.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); mobile=re.sub(r'\D','',request.form.get('mobile','')); password=request.form.get('password',''); room=request.form.get('room','').strip(); sid=request.form.get('student_id','').strip(); dept=request.form.get('department','').strip(); year=request.form.get('year','').strip()
        if not name or not email or not password or len(mobile)!=10: flash('Enter all required details and a valid 10-digit mobile number.','error'); return redirect(url_for('register'))
        try:
            con=get_db(); con.execute('INSERT INTO users(name,email,password,role,room,mobile,student_id,department,year) VALUES(?,?,?,?,?,?,?,?,?)',(name,email,generate_password_hash(password),'student',room,mobile,sid,dept,year)); con.commit(); con.close(); flash('Account created. You can now sign in.','success'); return redirect(url_for('login'))
        except sqlite3.IntegrityError: flash('Email or Student ID is already registered.','error')
    return render_page(render_template_string(REGISTER),'Register')

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

@app.route('/student')
def student_dashboard():
    if not require('student'): return redirect(url_for('login'))
    con=get_db(); cs=con.execute('SELECT * FROM complaints WHERE user_id=? ORDER BY created_at DESC',(session['user_id'],)).fetchall(); con.close(); counts={s:sum(1 for c in cs if c['status']==s) for s in STATUSES}
    body=render_template_string(r'''<div class="page-head"><div><div class="eyebrow">STUDENT SPACE</div><h1>Good day, {{session.get('name','Student').split()[0]}} 👋</h1><p>Everything you report, in one calm place.</p></div><a class="btn btn-primary" href="{{url_for('new_complaint')}}">＋ Report an issue</a></div><div class="hero"><div class="hero-content"><div class="hero-kicker">CAMPUS CARE</div><h2>Make your campus better,<br>one report at a time.</h2><p>Report hostel and campus issues, attach evidence and follow every update without chasing anyone.</p><a class="hero-link" href="{{url_for('new_complaint')}}">Start a complaint →</a></div><div class="orbit"></div></div><div class="section-title"><h3>Your overview</h3><span>{{cs|length}} total reports</span></div><div class="stats"><div class="stat"><div class="stat-top"><span>Submitted</span><div class="stat-icon">↗</div></div><strong>{{counts['Submitted']}}</strong></div><div class="stat"><div class="stat-top"><span>Being handled</span><div class="stat-icon">◌</div></div><strong>{{counts['Assigned']+counts['In Progress']}}</strong></div><div class="stat"><div class="stat-top"><span>Resolved</span><div class="stat-icon">✓</div></div><strong>{{counts['Resolved']}}</strong></div><div class="stat"><div class="stat-top"><span>Closed</span><div class="stat-icon">▣</div></div><strong>{{counts['Closed']}}</strong></div></div><div class="section-title"><h3>Recent complaints</h3><span>Open a report for details</span></div><div class="complaints">{% for c in cs %}<a class="complaint-row" href="{{url_for('complaint_status',complaint_id=c['complaint_id'])}}"><div><div class="row-meta">{{c['category']|upper}} · {{c['location']}} · {{c['complaint_id']}}</div><div class="row-title">{{c['title']}}</div><div class="row-sub">{{c['created_at']}}</div></div><div class="row-right"><span class="chip {{ {'Submitted':'submitted','Assigned':'assigned','In Progress':'progress','Resolved':'resolved','Closed':'closed'}[c['status']] }}">{{c['status']}}</span><span class="arrow">›</span></div></a>{% else %}<div class="empty">No complaints yet. Your first report can start here.</div>{% endfor %}</div><a class="floating-ai" title="AI Assistant" href="{{url_for('ai_assistant')}}">🤖</a>''',cs=cs,counts=counts)
    return render_page(body,'Student Dashboard','STUDENT SPACE')

@app.route('/complaint/new',methods=['GET','POST'])
def new_complaint():
    if not require('student'): return redirect(url_for('login'))
    if request.method=='POST':
        title=request.form.get('title','').strip(); desc=request.form.get('description','').strip(); category=request.form.get('category',''); location=request.form.get('location','').strip(); priority=request.form.get('priority','Medium'); f=request.files.get('image'); image=''
        if not title or not desc or not category or not location: flash('Please complete all required fields.','error'); return redirect(url_for('new_complaint'))
        if f and f.filename:
            if not allowed_file(f.filename): flash('Please upload PNG, JPG, JPEG, GIF or WEBP.','error'); return redirect(url_for('new_complaint'))
            image=secure_filename(uuid.uuid4().hex[:10]+'_'+f.filename); f.save(os.path.join(UPLOAD_FOLDER,image))
        cid='CC-'+uuid.uuid4().hex[:8].upper(); con=get_db(); con.execute('INSERT INTO complaints(complaint_id,user_id,category,title,description,location,priority,image) VALUES(?,?,?,?,?,?,?,?)',(cid,session['user_id'],category,title,desc,location,priority,image)); con.commit(); con.close(); flash(f'Complaint {cid} submitted successfully.','success'); return redirect(url_for('complaint_status',complaint_id=cid))
    body=render_template_string(r'''<div class="page-head"><div><div class="eyebrow">NEW REPORT</div><h1>Tell us what needs attention</h1><p>A clear report helps the campus team solve it faster.</p></div></div><div class="card"><form method="POST" enctype="multipart/form-data"><div class="form-grid"><div class="full"><label>What is the issue? *</label><input name="title" required placeholder="Example: Water leaking near room B-204"></div><div><label>Category *</label><select name="category" required><option value="">Choose a category</option>{% for c in categories %}<option>{{c}}</option>{% endfor %}</select></div><div><label>Location *</label><input name="location" required placeholder="Block B, Room 204"></div><div><label>Priority</label><select name="priority">{% for p in priorities %}<option>{{p}}</option>{% endfor %}</select></div><div><label>Photo evidence</label><div class="upload">Attach an image if useful<input type="file" name="image" accept="image/*"></div></div><div class="full"><label>Description *</label><textarea name="description" required placeholder="Explain what happened, when you noticed it and anything that may help the staff."></textarea></div></div><div class="form-actions"><a class="btn btn-light" href="{{url_for('student_dashboard')}}">Cancel</a><button class="btn btn-primary" type="submit">Submit complaint →</button></div></form></div>''')
    return render_page(body,'New Complaint','NEW REPORT')

@app.route('/complaint/<complaint_id>')
def complaint_status(complaint_id):
    if not session.get('user_id'): return redirect(url_for('login'))
    con=get_db(); c=con.execute('''SELECT c.*,u.name,u.email,u.room,u.mobile,w.name worker_name,w.department worker_dept,w.mobile worker_mobile FROM complaints c JOIN users u ON u.id=c.user_id LEFT JOIN workers w ON w.id=c.assigned_worker_id WHERE c.complaint_id=?''',(complaint_id,)).fetchone(); feedback=con.execute('SELECT * FROM feedback WHERE complaint_id=? ORDER BY id DESC LIMIT 1',(c['id'],)).fetchone() if c else None; con.close()
    if not c: flash('Complaint not found.','error'); return redirect(url_for('home'))
    if session.get('role')=='student' and c['user_id']!=session['user_id']: flash('You cannot view that complaint.','error'); return redirect(url_for('student_dashboard'))
    idx=STATUSES.index(c['status']) if c['status'] in STATUSES else 0
    body=render_template_string(r'''<div class="page-head"><div><div class="eyebrow">COMPLAINT STATUS</div><h1>{{c['complaint_id']}}</h1><p>Track the report from submission to closure.</p></div><a class="btn btn-light" href="{{url_for('home')}}">← Back</a></div><div class="detail-grid"><div class="card"><div class="detail-title"><div><h1>{{c['title']}}</h1><div class="mini-meta">{{c['category']}} · {{c['location']}}</div></div><span class="chip {{ {'Submitted':'submitted','Assigned':'assigned','In Progress':'progress','Resolved':'resolved','Closed':'closed'}[c['status']] }}">{{c['status']}}</span></div><div class="detail-block"><h4>Progress</h4><div class="timeline">{% for s in statuses %}<div class="step {{'done' if loop.index0<idx else ('current' if loop.index0==idx else '')}}"><div class="dot">{{'✓' if loop.index0<idx else loop.index}}</div><div><b>{{s}}</b><span>{{'Completed' if loop.index0<idx else ('Current status' if loop.index0==idx else 'Waiting for next step')}}</span></div></div>{% endfor %}</div></div><div class="detail-block"><h4>Report details</h4><p>{{c['description']}}</p></div>{% if c['image'] %}<div class="detail-block"><h4>Photo evidence</h4><img class="photo" src="{{url_for('uploaded_file',filename=c['image'])}}"></div>{% endif %}{% if c['admin_remark'] %}<div class="detail-block"><h4>Admin remark</h4><p>{{c['admin_remark']}}</p></div>{% endif %}{% if c['status']=='Resolved' and session.get('role')=='student' and not feedback %}<div class="feedback"><h4>How did we do?</h4><form method="POST" action="{{url_for('submit_feedback',complaint_id=c['complaint_id'])}}"><div style="display:flex;gap:7px;font-size:25px"><label><input type="radio" name="rating" value="1" required>★</label><label><input type="radio" name="rating" value="2">★★</label><label><input type="radio" name="rating" value="3">★★★</label><label><input type="radio" name="rating" value="4">★★★★</label><label><input type="radio" name="rating" value="5">★★★★★</label></div><textarea name="comment" style="min-height:80px;margin-top:10px" placeholder="Optional comment"></textarea><button class="btn btn-primary" style="margin-top:10px" type="submit">Send feedback</button></form></div>{% elif feedback %}<div class="feedback"><h4>Feedback received</h4><div style="font-size:22px">{{'★'*feedback['rating']}}{{'☆'*(5-feedback['rating'])}}</div><p>{{feedback['comment']}}</p></div>{% endif %}</div><div style="display:grid;gap:18px;align-content:start"><div class="card"><h3 style="margin:0 0 17px">Assignment</h3><div class="info-list"><div class="info-item"><span>Priority</span><strong>{{c['priority']}}</strong></div><div class="info-item"><span>Assigned to</span><strong>{{c['worker_name'] or c['assigned_to'] or 'Not assigned yet'}}</strong></div>{% if c['worker_mobile'] %}<div class="info-item"><span>Worker mobile</span><strong>{{c['worker_mobile']}}</strong></div>{% endif %}<div class="info-item"><span>Student</span><strong>{{c['name']}}</strong></div><div class="info-item"><span>Room</span><strong>{{c['room'] or '—'}}</strong></div><div class="info-item"><span>Created</span><strong>{{c['created_at']}}</strong></div><div class="info-item"><span>Updated</span><strong>{{c['updated_at']}}</strong></div></div></div><div class="card"><h3 style="margin:0 0 8px">Need help?</h3><p class="muted">Keep <b>{{c['complaint_id']}}</b> when speaking with campus support.</p><a class="btn btn-light" href="{{url_for('ai_assistant')}}">Ask AI Assistant</a></div></div></div>''',c=c,idx=idx,statuses=STATUSES,feedback=feedback)
    return render_page(body,'Complaint Status','COMPLAINT STATUS')

@app.route('/complaint/<complaint_id>/feedback',methods=['POST'])
def submit_feedback(complaint_id):
    if not require('student'): return redirect(url_for('login'))
    try: rating=max(1,min(5,int(request.form.get('rating','5'))))
    except: rating=5
    con=get_db(); c=con.execute('SELECT * FROM complaints WHERE complaint_id=? AND user_id=?',(complaint_id,session['user_id'])).fetchone()
    if c: con.execute('INSERT INTO feedback(complaint_id,rating,comment) VALUES(?,?,?)',(c['id'],rating,request.form.get('comment','').strip())); con.execute("UPDATE complaints SET status='Closed',updated_at=CURRENT_TIMESTAMP WHERE id=?",(c['id'],)); con.commit()
    con.close(); flash('Thank you for your feedback. The complaint is now closed.','success'); return redirect(url_for('complaint_status',complaint_id=complaint_id))

@app.route('/admin')
def admin_dashboard():
    if not require('admin'): return redirect(url_for('login'))
    q=request.args.get('q','').strip(); selected=request.args.get('status','')
    con=get_db(); workers=con.execute('SELECT * FROM workers WHERE active=1 ORDER BY name').fetchall(); sql='''SELECT c.*,u.name,u.email,u.room,u.mobile,w.name worker_name FROM complaints c JOIN users u ON u.id=c.user_id LEFT JOIN workers w ON w.id=c.assigned_worker_id WHERE 1=1'''; params=[]
    if q: sql+=' AND (c.complaint_id LIKE ? OR c.title LIKE ? OR c.category LIKE ? OR c.location LIKE ? OR u.name LIKE ? OR u.mobile LIKE ?)'; params += [f'%{q}%']*6
    if selected: sql+=' AND c.status=?'; params.append(selected)
    sql+=' ORDER BY c.created_at DESC'; cs=con.execute(sql,params).fetchall(); stats={s:con.execute('SELECT COUNT(*) n FROM complaints WHERE status=?',(s,)).fetchone()['n'] for s in STATUSES}; students=con.execute("SELECT COUNT(*) n FROM users WHERE role='student'").fetchone()['n']; emergency=con.execute("SELECT COUNT(*) n FROM complaints WHERE priority='Emergency' AND status!='Closed'").fetchone()['n']
    body=render_template_string(r'''<div class="page-head"><div><div class="eyebrow">OPERATIONS CENTER</div><h1>Campus support overview</h1><p>Review, assign, support students and move complaints forward.</p></div><span class="chip" style="background:#152742;color:#fff;padding:9px 12px">ADMIN MODE</span></div><div class="stats"><div class="stat"><div class="stat-top"><span>Total reports</span><div class="stat-icon">▦</div></div><strong>{{cs|length}}</strong></div><div class="stat"><div class="stat-top"><span>In progress</span><div class="stat-icon">◌</div></div><strong>{{stats['Assigned']+stats['In Progress']}}</strong></div><div class="stat"><div class="stat-top"><span>Students</span><div class="stat-icon">👨‍🎓</div></div><strong>{{students}}</strong></div><div class="stat"><div class="stat-top"><span>Emergency</span><div class="stat-icon">!</div></div><strong>{{emergency}}</strong></div></div><form class="toolbar"><input name="q" value="{{q}}" placeholder="Search complaint, student, mobile, location…"><select name="status"><option value="">All statuses</option>{% for s in statuses %}<option value="{{s}}" {{'selected' if selected==s else ''}}>{{s}}</option>{% endfor %}</select><button class="btn btn-blue">Filter</button></form><div class="section-title"><h3>Complaint queue</h3><span>{{cs|length}} matching reports</span></div><div class="admin-list">{% for c in cs %}<div class="admin-card"><div class="admin-top"><div><div class="admin-meta">{{c['complaint_id']}} · {{c['category']}} · {{c['location']}}</div><div class="admin-title">{{c['title']}}</div><div class="admin-meta">{{c['name']}} · {{c['mobile']}} · Room {{c['room'] or '—'}}</div></div><div class="admin-tags"><span class="chip {{ {'Submitted':'submitted','Assigned':'assigned','In Progress':'progress','Resolved':'resolved','Closed':'closed'}[c['status']] }}">{{c['status']}}</span><span class="chip {{'emergency' if c['priority']=='Emergency' else 'assigned'}}">{{c['priority']}}</span></div></div><div class="admin-desc">{{c['description']}}</div><form class="admin-form" method="POST" action="{{url_for('update_complaint',id=c['id'])}}"><div><label>Status</label><select name="status">{% for s in statuses %}<option {{'selected' if c['status']==s else ''}}>{{s}}</option>{% endfor %}</select></div><div><label>Assign worker</label><select name="worker_id"><option value="">Unassigned</option>{% for w in workers %}<option value="{{w['id']}}" {{'selected' if c['assigned_worker_id']==w['id'] else ''}}>{{w['name']}} — {{w['department']}}</option>{% endfor %}</select></div><div><label>Admin remark</label><input name="remark" value="{{c['admin_remark']}}" placeholder="Add an update for the student"></div><button class="btn btn-primary" type="submit">Save</button></form><div style="display:flex;justify-content:flex-end;gap:15px;font-size:11px;margin-top:12px;color:#60708b">{% if c['image'] %}<a href="{{url_for('uploaded_file',filename=c['image'])}}" target="_blank">View photo ↗</a>{% endif %}<a href="{{url_for('complaint_status',complaint_id=c['complaint_id'])}}">Open details →</a></div></div>{% else %}<div class="empty">No complaints match your filters.</div>{% endfor %}</div>''',cs=cs,stats=stats,students=students,emergency=emergency,q=q,selected=selected,workers=workers)
    con.close()
    return render_page(body,'Admin Dashboard','OPERATIONS CENTER')

@app.route('/admin/complaint/<int:id>',methods=['POST'])
def update_complaint(id):
    if not require('admin'): return redirect(url_for('login'))
    status=request.form.get('status','Submitted'); status=status if status in STATUSES else 'Submitted'; wid=request.form.get('worker_id','').strip(); remark=request.form.get('remark','').strip(); con=get_db(); worker=con.execute('SELECT * FROM workers WHERE id=?',(wid,)).fetchone() if wid.isdigit() else None
    con.execute('UPDATE complaints SET status=?,assigned_worker_id=?,assigned_to=?,admin_remark=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(status,worker['id'] if worker else None,worker['name'] if worker else '',remark,id)); con.commit(); con.close(); flash('Complaint updated successfully.','success'); return redirect(url_for('admin_dashboard'))

@app.route('/admin/students')
def admin_students():
    if not require('admin'): return redirect(url_for('login'))
    q=request.args.get('q','').strip(); con=get_db(); sql="SELECT u.*,COUNT(c.id) complaints_count,SUM(CASE WHEN c.status='Resolved' THEN 1 ELSE 0 END) resolved_count FROM users u LEFT JOIN complaints c ON c.user_id=u.id WHERE u.role='student'"; params=[]
    if q: sql+=" AND (u.name LIKE ? OR u.email LIKE ? OR u.mobile LIKE ? OR u.student_id LIKE ? OR u.department LIKE ?)"; params += [f'%{q}%']*5
    sql+=' GROUP BY u.id ORDER BY u.created_at DESC'; students=con.execute(sql,params).fetchall(); con.close()
    body=render_template_string(r'''<div class="page-head"><div><div class="eyebrow">REGISTERED STUDENTS</div><h1>Student directory</h1><p>Every student who registers is visible here for authorized campus administration.</p></div></div><form class="searchbar"><input name="q" value="{{q}}" placeholder="Search name, student ID, email, mobile or department…"><button class="btn btn-blue">Search</button></form><div class="table-wrap"><table><thead><tr><th>Student</th><th>Student ID</th><th>Contact</th><th>Academic</th><th>Hostel</th><th>Complaints</th><th>Registered</th></tr></thead><tbody>{% for s in students %}<tr><td><strong>{{s['name']}}</strong><br><span class="muted">{{s['email']}}</span></td><td>{{s['student_id'] or '—'}}</td><td>{{s['mobile'] or '—'}}</td><td>{{s['department'] or '—'}}<br>{{s['year'] or ''}}</td><td>{{s['room'] or '—'}}</td><td>{{s['complaints_count'] or 0}} total<br>{{s['resolved_count'] or 0}} resolved</td><td>{{s['created_at'] or '—'}}</td></tr>{% else %}<tr><td colspan="7">No registered students found.</td></tr>{% endfor %}</tbody></table></div>''',students=students,q=q)
    return render_page(body,'Students','STUDENT DIRECTORY')

@app.route('/admin/workers',methods=['GET','POST'])
def admin_workers():
    if not require('admin'): return redirect(url_for('login'))
    con=get_db()
    if request.method=='POST':
        name=request.form.get('name','').strip(); dept=request.form.get('department','').strip(); mobile=re.sub(r'\D','',request.form.get('mobile',''))
        if name and dept and len(mobile)>=10: con.execute('INSERT INTO workers(name,department,mobile) VALUES(?,?,?)',(name,dept,mobile)); con.commit(); flash('Worker added successfully.','success')
        else: flash('Enter worker name, department and valid mobile number.','error')
    workers=con.execute('SELECT * FROM workers ORDER BY active DESC,name').fetchall(); con.close()
    body=render_template_string(r'''<div class="page-head"><div><div class="eyebrow">WORKFORCE</div><h1>Workers & staff</h1><p>Manage the people who can be assigned to campus complaints.</p></div></div><div class="card" style="margin-bottom:20px"><form class="form-grid" method="POST"><div><label>Worker name</label><input name="name" required placeholder="Worker name"></div><div><label>Department</label><input name="department" required placeholder="Electrical / Plumbing / Cleaning"></div><div><label>Mobile number</label><input name="mobile" required placeholder="10-digit number"></div><div style="display:flex;align-items:end"><button class="btn btn-blue" type="submit">＋ Add worker</button></div></form></div><div class="worker-grid">{% for w in workers %}<div class="worker-card"><div class="avatar" style="margin-bottom:12px">{{w['name'][0]|upper}}</div><h3>{{w['name']}}</h3><div class="muted">{{w['department']}}</div><a class="phone" href="tel:{{w['mobile']}}">☎ {{w['mobile']}}</a></div>{% endfor %}</div>''',workers=workers)
    return render_page(body,'Workers','WORKFORCE')

@app.route('/contacts')
def contacts():
    body=render_template_string(r'''<div class="page-head"><div><div class="eyebrow">CAMPUS CONTACTS</div><h1>Who can help?</h1><p>Keep important campus support numbers in one place.</p></div></div><div class="contact-grid">{% for name,dept,mobile in contacts %}<div class="contact-card"><div class="avatar">☎</div><h3 style="margin-top:14px">{{name}}</h3><div class="muted">{{dept}}</div><a class="phone" href="tel:{{mobile}}">{{mobile}}</a></div>{% endfor %}</div><div class="card" style="margin-top:20px"><h3 style="margin-top:0">Note</h3><p class="muted">These are demo contact numbers for the project. Replace them with your college's actual contacts before your final presentation.</p></div>''',contacts=CONTACTS)
    return render_page(body,'Contacts','CAMPUS CONTACTS')

@app.route('/help')
def help_support():
    body=render_template_string(r'''<div class="page-head"><div><div class="eyebrow">HELP & SUPPORT</div><h1>If Campus Care is not working</h1><p>Quick fixes for common problems during your demo or daily use.</p></div></div><div class="help-grid"><div class="help-card"><h3>🔐 Can't login?</h3><p class="muted">Check email and password. If needed, sign out and reopen the app. Confirm the Flask server is running.</p></div><div class="help-card"><h3>📤 Can't submit?</h3><p class="muted">Make sure title, category, location and description are filled. Refresh and try again.</p></div><div class="help-card"><h3>🖼️ Image upload fails?</h3><p class="muted">Use PNG, JPG, JPEG, GIF or WEBP. Try a smaller image and ensure the uploads folder can be created.</p></div><div class="help-card"><h3>📊 Status not updating?</h3><p class="muted">Ask an admin to save the complaint update again. Refresh the complaint page afterward.</p></div><div class="help-card"><h3>🧭 Page not opening?</h3><p class="muted">Restart the Python program and open http://127.0.0.1:5000 in your browser.</p></div><div class="help-card"><h3>🆘 Still stuck?</h3><p class="muted">Open AI Assistant or Contacts. For a project demo, show the issue and the troubleshooting workflow to your evaluator.</p></div></div><div class="faq" style="margin-top:22px"><details><summary>What should I do if the terminal shows a Python error?</summary><p>Read the last line of the traceback. It usually contains the file and line number. Fix the first error shown, restart Flask and refresh the browser.</p></details><details><summary>Where is complaint data stored?</summary><p>Campus Care stores data in the local SQLite file <b>campuscare.db</b> beside this Python file.</p></details><details><summary>Where are uploaded images stored?</summary><p>Images are saved in the <b>static/uploads</b> folder created automatically by the app.</p></details></div>''')
    return render_page(body,'Help & Support','HELP & SUPPORT')

@app.route('/ai',methods=['GET','POST'])
def ai_assistant():
    if not session.get('user_id'): return redirect(url_for('login'))
    answer=None; question=''
    if request.method=='POST': question=request.form.get('message','').strip(); answer=ai_reply(question)
    body=render_template_string(r'''<div class="page-head"><div><div class="eyebrow">SMART SUPPORT</div><h1>Campus Care AI Assistant 🤖</h1><p>Ask questions about complaints, contacts, workers, login or app troubleshooting.</p></div></div><div class="ai-box"><div class="chat">{% if question %}<div class="msg user">{{question}}</div><div class="msg ai"><b>Campus Care Assistant</b><br>{{answer}}</div>{% else %}<div class="msg ai"><b>Campus Care Assistant</b><br>Hi {{session.get('name','Student').split()[0]}}! How can I help you today?</div><div class="msg ai">Try: “How do I submit a complaint?”<br>“My app is not working.”<br>“How can I contact the warden?”<br>“How can admin see registered students?”</div>{% endif %}</div><form class="chat-form" method="POST"><input name="message" value="{{question}}" required placeholder="Ask Campus Care Assistant…"><button class="btn btn-blue">Send</button></form></div>''',question=question,answer=answer)
    return render_page(body,'AI Assistant','AI SUPPORT')

@app.route('/profile')
def student_profile():
    if not require('student'): return redirect(url_for('login'))
    con=get_db(); u=con.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone(); count=con.execute('SELECT COUNT(*) n FROM complaints WHERE user_id=?',(session['user_id'],)).fetchone()['n']; con.close()
    body=render_template_string(r'''<div class="page-head"><div><div class="eyebrow">MY PROFILE</div><h1>Student details</h1><p>Your registered information and support activity.</p></div></div><div class="profile-grid"><div class="card"><div class="avatar" style="width:60px;height:60px;font-size:22px">{{u['name'][0]|upper}}</div><h2>{{u['name']}}</h2><p class="muted">{{u['email']}}</p><div class="info-list"><div class="info-item"><span>Student ID</span><strong>{{u['student_id'] or '—'}}</strong></div><div class="info-item"><span>Mobile</span><strong>{{u['mobile'] or '—'}}</strong></div><div class="info-item"><span>Department</span><strong>{{u['department'] or '—'}}</strong></div><div class="info-item"><span>Year</span><strong>{{u['year'] or '—'}}</strong></div><div class="info-item"><span>Hostel / Room</span><strong>{{u['room'] or '—'}}</strong></div></div></div><div class="card"><h3>Support activity</h3><div class="stat"><div class="stat-top"><span>Total complaints</span><div class="stat-icon">▦</div></div><strong>{{count}}</strong></div><a class="btn btn-blue" href="{{url_for('student_dashboard')}}" style="margin-top:15px">View my complaints</a></div></div>''',u=u,count=count)
    return render_page(body,'My Profile','MY PROFILE')

@app.route('/admin/profile')
def admin_profile():
    if not require('admin'): return redirect(url_for('login'))
    con=get_db(); u=con.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone(); total=con.execute('SELECT COUNT(*) n FROM complaints').fetchone()['n']; resolved=con.execute("SELECT COUNT(*) n FROM complaints WHERE status IN ('Resolved','Closed')").fetchone()['n']; con.close()
    body=render_template_string(r'''<div class="page-head"><div><div class="eyebrow">ADMIN PROFILE</div><h1>{{u['name']}}</h1><p>Administrator account and campus support information.</p></div></div><div class="profile-grid"><div class="card"><div class="avatar" style="width:65px;height:65px;font-size:23px">{{u['name'][0]|upper}}</div><h2>{{u['name']}}</h2><p class="muted">{{u['department'] or 'Campus Administration'}}</p><div class="info-list"><div class="info-item"><span>Role</span><strong>Administrator / Warden</strong></div><div class="info-item"><span>Email</span><strong>{{u['email']}}</strong></div><div class="info-item"><span>Mobile</span><strong>{{u['mobile']}}</strong></div></div><a class="phone" href="tel:{{u['mobile']}}">☎ Call admin</a></div><div class="card"><h3>System overview</h3><div class="stats" style="grid-template-columns:1fr 1fr;margin:0"><div class="stat"><div class="stat-top"><span>Total reports</span></div><strong>{{total}}</strong></div><div class="stat"><div class="stat-top"><span>Resolved / closed</span></div><strong>{{resolved}}</strong></div></div></div></div>''',u=u,total=total,resolved=resolved)
    return render_page(body,'Admin Profile','ADMIN PROFILE')

@app.route('/uploads/<path:filename>')
def uploaded_file(filename): return send_from_directory(UPLOAD_FOLDER,filename)

initialize_database()
if __name__=='__main__': app.run(debug=True,host='127.0.0.1',port=5000)