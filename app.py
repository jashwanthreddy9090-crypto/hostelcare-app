from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import sqlite3, os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hostelcare-demo-secret")
DB = "hostelcare.db"

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'student'
    );
    CREATE TABLE IF NOT EXISTS complaints(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        hostel TEXT NOT NULL,
        room TEXT NOT NULL,
        priority TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Submitted',
        assigned_to TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        resolved_at TEXT,
        rating INTEGER,
        feedback TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    # Demo admin account: admin@hostelcare.com / admin123
    admin = c.execute("SELECT id FROM users WHERE email=?", ("admin@hostelcare.com",)).fetchone()
    if not admin:
        c.execute("INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
                  ("Hostel Warden","admin@hostelcare.com",generate_password_hash("admin123"),"admin"))
    c.commit()
    c.close()

def login_required():
    return "user_id" in session

def admin_required():
    return session.get("role") == "admin"

@app.route("/")
def home():
    return redirect(url_for("dashboard" if login_required() else "login"))

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name=request.form["name"].strip()
        email=request.form["email"].strip().lower()
        password=request.form["password"]
        if len(password)<6:
            flash("Password must contain at least 6 characters.","danger")
            return redirect(url_for("register"))
        c=db()
        try:
            c.execute("INSERT INTO users(name,email,password) VALUES(?,?,?)",
                      (name,email,generate_password_hash(password)))
            c.commit()
            flash("Account created. Please log in.","success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email already registered.","danger")
        finally:
            c.close()
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form["email"].strip().lower()
        password=request.form["password"]
        c=db()
        u=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
        c.close()
        if u and check_password_hash(u["password"],password):
            session["user_id"]=u["id"]; session["name"]=u["name"]; session["role"]=u["role"]
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.","danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if not login_required(): return redirect(url_for("login"))
    c=db()
    if admin_required():
        total=c.execute("SELECT COUNT(*) n FROM complaints").fetchone()["n"]
        pending=c.execute("SELECT COUNT(*) n FROM complaints WHERE status IN ('Submitted','Assigned')").fetchone()["n"]
        progress=c.execute("SELECT COUNT(*) n FROM complaints WHERE status='In Progress'").fetchone()["n"]
        resolved=c.execute("SELECT COUNT(*) n FROM complaints WHERE status='Resolved'").fetchone()["n"]
        recent=c.execute("""SELECT complaints.*, users.name student FROM complaints
                           JOIN users ON users.id=complaints.user_id
                           ORDER BY complaints.id DESC LIMIT 8""").fetchall()
        cats=c.execute("SELECT category,COUNT(*) n FROM complaints GROUP BY category ORDER BY n DESC").fetchall()
        c.close()
        return render_template("admin_dashboard.html",total=total,pending=pending,progress=progress,resolved=resolved,recent=recent,cats=cats)
    rows=c.execute("""SELECT * FROM complaints WHERE user_id=? ORDER BY id DESC""",(session["user_id"],)).fetchall()
    c.close()
    return render_template("student_dashboard.html",rows=rows)

@app.route("/complaint/new", methods=["GET","POST"])
def new_complaint():
    if not login_required() or admin_required(): return redirect(url_for("login"))
    if request.method=="POST":
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c=db()
        cur=c.execute("""INSERT INTO complaints
        (user_id,title,category,hostel,room,priority,description,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?)""",(
            session["user_id"],request.form["title"].strip(),request.form["category"],
            request.form["hostel"],request.form["room"].strip(),request.form["priority"],
            request.form["description"].strip(),now,now))
        c.commit(); cid=cur.lastrowid; c.close()
        flash(f"Complaint #{cid} submitted successfully.","success")
        return redirect(url_for("dashboard"))
    return render_template("new_complaint.html")

@app.route("/complaint/<int:cid>")
def complaint(cid):
    if not login_required(): return redirect(url_for("login"))
    c=db()
    row=c.execute("""SELECT complaints.*,users.name student,users.email
                     FROM complaints JOIN users ON users.id=complaints.user_id
                     WHERE complaints.id=?""",(cid,)).fetchone()
    c.close()
    if not row: return render_template("404.html"),404
    if not admin_required() and row["user_id"]!=session["user_id"]: return "Unauthorized",403
    return render_template("complaint_detail.html",r=row)

@app.route("/admin/complaints")
def admin_complaints():
    if not admin_required(): return redirect(url_for("login"))
    q=request.args.get("q","").strip()
    status=request.args.get("status","")
    c=db()
    sql="""SELECT complaints.*,users.name student FROM complaints
           JOIN users ON users.id=complaints.user_id WHERE 1=1"""
    params=[]
    if q:
        sql+=" AND (complaints.title LIKE ? OR complaints.room LIKE ? OR complaints.category LIKE ?)"
        params += [f"%{q}%"]*3
    if status:
        sql+=" AND complaints.status=?"; params.append(status)
    sql+=" ORDER BY complaints.id DESC"
    rows=c.execute(sql,params).fetchall(); c.close()
    return render_template("admin_complaints.html",rows=rows,q=q,status=status)

@app.route("/admin/complaint/<int:cid>/update", methods=["POST"])
def update_complaint(cid):
    if not admin_required(): return redirect(url_for("login"))
    status=request.form["status"]
    assigned=request.form.get("assigned_to","").strip()
    now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    resolved=now if status=="Resolved" else None
    c=db()
    c.execute("""UPDATE complaints SET status=?,assigned_to=?,updated_at=?,
                 resolved_at=CASE WHEN ?='Resolved' THEN ? ELSE resolved_at END
                 WHERE id=?""",(status,assigned,now,status,resolved,cid))
    c.commit(); c.close()
    flash(f"Complaint #{cid} updated.","success")
    return redirect(url_for("complaint",cid=cid))

@app.route("/complaint/<int:cid>/feedback", methods=["POST"])
def feedback(cid):
    if not login_required(): return redirect(url_for("login"))
    rating=int(request.form["rating"])
    text=request.form.get("feedback","").strip()
    c=db()
    c.execute("""UPDATE complaints SET rating=?,feedback=? WHERE id=? AND user_id=? AND status='Resolved'""",
              (rating,text,cid,session["user_id"]))
    c.commit(); c.close()
    flash("Thank you for your feedback.","success")
    return redirect(url_for("complaint",cid=cid))

@app.route("/api/stats")
def stats():
    if not admin_required(): return jsonify({"error":"unauthorized"}),403
    c=db()
    rows=c.execute("SELECT status,COUNT(*) n FROM complaints GROUP BY status").fetchall()
    cats=c.execute("SELECT category,COUNT(*) n FROM complaints GROUP BY category ORDER BY n DESC").fetchall()
    c.close()
    return jsonify({"status":[dict(x) for x in rows],"categories":[dict(x) for x in cats]})

if __name__=="__main__":
    init_db()
    app.run(debug=True)
