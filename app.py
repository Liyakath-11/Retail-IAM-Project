from flask import Flask, render_template, request, redirect, session
import sqlite3, datetime, random, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secretkey"

# ---------------- HOME ----------------
@app.route("/")
def home():
    return redirect("/login")

# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT,
        is_verified INTEGER DEFAULT 0,
        failed_attempts INTEGER DEFAULT 0,
        lock_time TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS login_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        ip_address TEXT,
        login_time TEXT,
        status TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS inventory(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT NOT NULL,
        category TEXT,
        quantity INTEGER DEFAULT 0,
        price REAL DEFAULT 0,
        low_stock_threshold INTEGER DEFAULT 5
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sales(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        product_name TEXT,
        quantity INTEGER,
        total_price REAL,
        staff_username TEXT,
        sale_time TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS returns(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT,
        quantity INTEGER,
        reason TEXT,
        staff_username TEXT,
        return_time TEXT,
        status TEXT DEFAULT 'Pending'
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS announcements(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        message TEXT,
        posted_by TEXT,
        posted_time TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS complaints(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        subject TEXT,
        message TEXT,
        status TEXT DEFAULT 'Open',
        submitted_time TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS staff_hours(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        date TEXT,
        clock_in TEXT,
        clock_out TEXT,
        hours_worked REAL DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS salary(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        month TEXT,
        amount REAL,
        status TEXT DEFAULT 'Paid',
        paid_date TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS customer_orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        product_name TEXT,
        quantity INTEGER,
        total_price REAL,
        order_time TEXT,
        status TEXT DEFAULT 'Confirmed'
    )
    """)

    # AUTO ADMIN
    cur.execute("SELECT * FROM users WHERE username='admin'")
    if not cur.fetchone():
        cur.execute("""
        INSERT INTO users(username,email,password,role,is_verified)
        VALUES(?,?,?,?,?)
        """, ("admin","adminretail841@gmail.com",
              generate_password_hash("admin123"),"Admin",1))

    # Sample inventory
    cur.execute("SELECT COUNT(*) FROM inventory")
    if cur.fetchone()[0] == 0:
        sample = [
            ("Apple", "Fruits", 50, 10.00, 10),
            ("Milk 1L", "Dairy", 30, 25.00, 8),
            ("Bread", "Bakery", 20, 35.00, 5),
            ("Rice 1kg", "Grains", 100, 60.00, 15),
            ("Eggs (12)", "Dairy", 40, 80.00, 10),
            ("Tomato", "Vegetables", 4, 15.00, 5),
            ("Chicken 1kg", "Meat", 2, 220.00, 5),
        ]
        cur.executemany("INSERT INTO inventory(product_name,category,quantity,price,low_stock_threshold) VALUES(?,?,?,?,?)", sample)

    # Sample announcement
    cur.execute("SELECT COUNT(*) FROM announcements")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO announcements(title,message,posted_by,posted_time) VALUES(?,?,?,?)",
                    ("Welcome to Retail Security System",
                     "All staff must verify identity via OTP before accessing the system. Report any suspicious activity to admin immediately.",
                     "admin",
                     datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    # Sample salary for existing staff
    cur.execute("SELECT username FROM users WHERE role='Staff'")
    staff_users = cur.fetchall()
    for s in staff_users:
        cur.execute("SELECT COUNT(*) FROM salary WHERE username=?", (s[0],))
        if cur.fetchone()[0] == 0:
            for m in ["2026-01","2026-02","2026-03"]:
                cur.execute("INSERT INTO salary(username,month,amount,status,paid_date) VALUES(?,?,?,?,?)",
                            (s[0], m, 15000.00, "Paid", m+"-28"))

    conn.commit()
    conn.close()

init_db()

# ---------------- HELPERS ----------------
def strong_password(p):
    return len(p)>=8 and any(c.isupper() for c in p) and any(c.isdigit() for c in p)

def generate_otp():
    return str(random.randint(100000,999999))

def otp_expired(t):
    t=datetime.datetime.strptime(t,"%Y-%m-%d %H:%M:%S")
    return datetime.datetime.now()>t+datetime.timedelta(minutes=5)

def can_resend(t):
    t=datetime.datetime.strptime(t,"%Y-%m-%d %H:%M:%S")
    return datetime.datetime.now()>t+datetime.timedelta(seconds=30)

def set_error(msg):
    session["error"] = msg

def get_error():
    return session.pop("error", None)

# ---------------- EMAIL ----------------
def send_otp(email, otp):
    print("OTP:", otp)
    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:40px 0;">
    <tr><td align="center">
      <table width="480" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
        <tr><td style="background:#1A3C5E;padding:32px 40px;text-align:center;">
          <div style="font-size:28px;margin-bottom:8px;">🔐</div>
          <h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:700;">Retail Security System</h1>
        </td></tr>
        <tr><td style="padding:40px 40px 24px;">
          <p style="margin:0 0 8px;color:#5a6a7a;font-size:14px;">Your One-Time Password</p>
          <p style="margin:0 0 24px;color:#1a1a2e;font-size:14px;line-height:1.6;">Use the code below to complete your verification. Do <strong>not</strong> share this code with anyone.</p>
          <div style="background:#f0f5ff;border:2px dashed #2E75B6;border-radius:10px;padding:24px;text-align:center;margin-bottom:28px;">
            <p style="margin:0 0 6px;color:#5a6a7a;font-size:12px;letter-spacing:1px;text-transform:uppercase;">Your OTP Code</p>
            <p style="margin:0;color:#1A3C5E;font-size:42px;font-weight:700;letter-spacing:16px;">{otp}</p>
          </div>
          <table width="100%" cellpadding="0" cellspacing="0"><tr>
            <td style="background:#fff8e1;border-left:4px solid #f57f17;border-radius:4px;padding:12px 16px;">
              <p style="margin:0;color:#e65100;font-size:13px;">⏱ This code expires in <strong>5 minutes</strong></p>
            </td>
          </tr></table>
          <p style="margin:24px 0 0;color:#888;font-size:12px;line-height:1.6;">If you did not request this code, please ignore this email.</p>
        </td></tr>
        <tr><td style="background:#f8fafc;border-top:1px solid #e8edf2;padding:20px 40px;text-align:center;">
          <p style="margin:0;color:#aab4be;font-size:11px;">Retail Security Team</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    msg = MIMEMultipart("alternative")
    msg['Subject'] = "🔐 Your OTP — Retail Security System"
    msg['From']    = "isfretailteam@gmail.com"
    msg['To']      = email
    plain = f"Retail Security System\n\nYour OTP: {otp}\nValid for 5 minutes.\n\nDo not share this code with anyone."
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))
    try:
        s=smtplib.SMTP("smtp.gmail.com",587)
        s.starttls()
        s.login("isfretailteam@gmail.com","dxpcoojgvplczgcz")
        s.send_message(msg)
        s.quit()
    except Exception as e:
        print("Mail failed:", e)

# ---------------- SIGNUP ----------------
@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method=="POST":
        username=request.form["username"]
        email=request.form["email"]
        password=request.form["password"]
        role=request.form.get("role","Customer")
        if role not in ("Customer","Staff"):
            role="Customer"
        if not strong_password(password):
            set_error("Password must be at least 8 characters with an uppercase letter and a number.")
            return redirect("/signup")
        otp=generate_otp()
        session["signup_data"]={"username":username,"email":email,"password":generate_password_hash(password),"role":role}
        session["signup_otp"]=otp
        session["signup_time"]=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        send_otp(email,otp)
        return redirect("/verify_signup")
    error=get_error()
    return render_template("signup.html", error=error)

@app.route("/verify_signup",methods=["GET","POST"])
def verify_signup():
    if request.method=="POST":
        if otp_expired(session.get("signup_time")):
            session.pop("signup_data", None)
            session.pop("signup_otp", None)
            session.pop("signup_time", None)
            set_error("OTP has expired. Please sign up again.")
            return redirect("/signup")
        if request.form["otp"]==session.get("signup_otp"):
            d=session["signup_data"]
            conn=sqlite3.connect("database.db")
            cur=conn.cursor()
            try:
                cur.execute("INSERT INTO users(username,email,password,role,is_verified) VALUES(?,?,?,?,?)",
                            (d["username"],d["email"],d["password"],d["role"],1))
                conn.commit()
                # Add salary records for new staff
                if d["role"] == "Staff":
                    for m in ["2026-01","2026-02","2026-03"]:
                        cur.execute("INSERT INTO salary(username,month,amount,status,paid_date) VALUES(?,?,?,?,?)",
                                    (d["username"], m, 15000.00, "Paid", m+"-28"))
                    conn.commit()
            except sqlite3.IntegrityError:
                conn.close()
                session.clear()
                set_error("Username or email already registered.")
                return redirect("/signup")
            conn.close()
            session.clear()
            return redirect("/login")
        set_error("Invalid OTP. Please try again.")
        return redirect("/verify_signup")
    error=get_error()
    return render_template("otp.html", error=error)

@app.route("/resend_signup_otp")
def resend_signup_otp():
    d=session.get("signup_data")
    if not d: return redirect("/signup")
    if not can_resend(session.get("signup_time")):
        set_error("Please wait 30 seconds before resending.")
        return redirect("/verify_signup")
    otp=generate_otp()
    session["signup_otp"]=otp
    session["signup_time"]=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    send_otp(d["email"],otp)
    return redirect("/verify_signup")

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=request.form["username"]
        p=request.form["password"]
        conn=sqlite3.connect("database.db")
        cur=conn.cursor()
        cur.execute("SELECT password,role,email,failed_attempts,lock_time FROM users WHERE username=?", (u,))
        user=cur.fetchone()
        if not user:
            conn.close()
            set_error("Username not found.")
            return redirect("/login")
        db_pass, role, email, attempts, lock_time = user
        if lock_time:
            lock_dt = datetime.datetime.strptime(lock_time, "%Y-%m-%d %H:%M:%S")
            unlock_dt = lock_dt + datetime.timedelta(minutes=10)
            if datetime.datetime.now() < unlock_dt:
                remaining = int((unlock_dt - datetime.datetime.now()).total_seconds() // 60) + 1
                conn.close()
                set_error(f"Account locked. Try again in {remaining} minute(s).")
                return redirect("/login")
            else:
                cur.execute("UPDATE users SET failed_attempts=0, lock_time=NULL WHERE username=?", (u,))
                conn.commit()
                attempts = 0
        if check_password_hash(db_pass, p):
            cur.execute("UPDATE users SET failed_attempts=0, lock_time=NULL WHERE username=?", (u,))
            cur.execute("INSERT INTO login_logs(username,ip_address,login_time,status) VALUES(?,?,?,?)",
                        (u, request.remote_addr, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "SUCCESS"))
            conn.commit()
            conn.close()
            otp=generate_otp()
            session["temp_user"]=u
            session["temp_role"]=role
            session["login_otp"]=otp
            session["login_otp_time"]=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            send_otp(email, otp)
            return redirect("/verify_login_otp")
        else:
            attempts += 1
            cur.execute("INSERT INTO login_logs(username,ip_address,login_time,status) VALUES(?,?,?,?)",
                        (u, request.remote_addr, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "FAILED"))
            if attempts >= 5:
                cur.execute("UPDATE users SET failed_attempts=?, lock_time=? WHERE username=?",
                            (attempts, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), u))
                conn.commit()
                conn.close()
                set_error("Account locked for 10 minutes after 5 failed attempts.")
            else:
                cur.execute("UPDATE users SET failed_attempts=? WHERE username=?", (attempts, u))
                conn.commit()
                conn.close()
                set_error(f"Incorrect password. Attempt {attempts} of 5.")
            return redirect("/login")
    error=get_error()
    return render_template("login.html", error=error)

@app.route("/verify_login_otp", methods=["GET","POST"])
def verify_login_otp():
    if "temp_user" not in session:
        return redirect("/login")
    if request.method=="POST":
        if otp_expired(session.get("login_otp_time")):
            session.pop("temp_user", None)
            session.pop("temp_role", None)
            session.pop("login_otp", None)
            session.pop("login_otp_time", None)
            set_error("OTP has expired. Please login again.")
            return redirect("/login")
        if request.form["otp"]==session.get("login_otp"):
            session["user"]=session.pop("temp_user")
            session["role"]=session.pop("temp_role")
            session.pop("login_otp", None)
            session.pop("login_otp_time", None)
            if session["role"] == "Admin":
                return redirect("/admin")
            elif session["role"] == "Staff":
                return redirect("/staff")
            else:
                return redirect("/dashboard")
        set_error("Invalid OTP. Please try again.")
        return redirect("/verify_login_otp")
    error=get_error()
    return render_template("otp.html", error=error)

# ---------------- FORGOT / RESET ----------------
@app.route("/forgot",methods=["GET","POST"])
def forgot():
    if request.method=="POST":
        email=request.form["email"]
        conn=sqlite3.connect("database.db")
        cur=conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        user=cur.fetchone()
        conn.close()
        if not user:
            set_error("No account found with that email address.")
            return redirect("/forgot")
        otp=generate_otp()
        session["otp"]=otp
        session["otp_time"]=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session["reset_email"]=email
        send_otp(email,otp)
        return redirect("/otp")
    error=get_error()
    return render_template("forgot.html", error=error)

@app.route("/otp",methods=["GET","POST"])
def otp():
    if request.method=="POST":
        if otp_expired(session.get("otp_time")):
            set_error("OTP has expired. Please request a new one.")
            return redirect("/forgot")
        if request.form["otp"]==session.get("otp"):
            return redirect("/reset")
        set_error("Invalid OTP. Please try again.")
        return redirect("/otp")
    error=get_error()
    return render_template("otp.html", error=error)

@app.route("/resend_reset_otp")
def resend_reset_otp():
    if not can_resend(session.get("otp_time")):
        set_error("Please wait 30 seconds before resending.")
        return redirect("/otp")
    email=session.get("reset_email")
    otp=generate_otp()
    session["otp"]=otp
    session["otp_time"]=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    send_otp(email,otp)
    return redirect("/otp")

@app.route("/reset",methods=["GET","POST"])
def reset():
    if request.method=="POST":
        p=request.form["password"]
        c=request.form["confirm_password"]
        if p!=c:
            set_error("Passwords do not match.")
            return redirect("/reset")
        if not strong_password(p):
            set_error("Password must be at least 8 characters with an uppercase letter and a number.")
            return redirect("/reset")
        email=session["reset_email"]
        conn=sqlite3.connect("database.db")
        cur=conn.cursor()
        cur.execute("SELECT password FROM users WHERE email=?", (email,))
        old=cur.fetchone()[0]
        if check_password_hash(old,p):
            conn.close()
            set_error("You cannot reuse your previous password.")
            return redirect("/reset")
        cur.execute("UPDATE users SET password=? WHERE email=?", (generate_password_hash(p),email))
        conn.commit()
        conn.close()
        session.clear()
        return redirect("/login")
    error=get_error()
    return render_template("reset.html", error=error)

# ================================================================
# DASHBOARDS
# ================================================================

@app.route("/dashboard")
def dashboard():
    if "user" not in session or session.get("role") != "Customer":
        return redirect("/login")
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(total_price) FROM customer_orders WHERE username=?", (session["user"],))
    stats = cur.fetchone()
    score = min(int((stats[1] or 0) / 100), 100)
    cur.execute("SELECT COUNT(*) FROM complaints WHERE username=? AND status='Open'", (session["user"],))
    open_complaints = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM announcements")
    ann_count = cur.fetchone()[0]
    conn.close()
    return render_template("dashboard.html", user=session["user"],
                           order_count=stats[0] or 0,
                           total_spent=stats[1] or 0,
                           score=score,
                           open_complaints=open_complaints,
                           ann_count=ann_count)

@app.route("/staff")
def staff():
    if "user" not in session or session.get("role") != "Staff":
        return redirect("/login")
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM inventory")
    stock_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM inventory WHERE quantity <= low_stock_threshold")
    low_stock = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM complaints WHERE status='Open'")
    open_complaints = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM announcements")
    ann_count = cur.fetchone()[0]
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT clock_in, clock_out, hours_worked FROM staff_hours WHERE username=? AND date=?",
                (session["user"], today))
    today_hours = cur.fetchone()
    conn.close()
    return render_template("staff.html", user=session["user"],
                           stock_count=stock_count,
                           low_stock=low_stock,
                           open_complaints=open_complaints,
                           ann_count=ann_count,
                           today_hours=today_hours)

# ================================================================
# ADMIN
# ================================================================

@app.route("/admin")
def admin():
    if session.get("role") != "Admin":
        return redirect("/login")
    conn=sqlite3.connect("database.db")
    cur=conn.cursor()
    cur.execute("SELECT username,email,role,failed_attempts,lock_time FROM users")
    users=cur.fetchall()
    cur.execute("SELECT username,ip_address,login_time,status FROM login_logs ORDER BY id DESC LIMIT 20")
    logs=cur.fetchall()
    total_users   = len(users)
    locked_users  = sum(1 for u in users if u[4])
    failed_logins = cur.execute("SELECT COUNT(*) FROM login_logs WHERE status='FAILED'").fetchone()[0]
    conn.close()
    return render_template("admin.html", users=users, logs=logs,
                           total_users=total_users, locked_users=locked_users,
                           failed_logins=failed_logins)

@app.route("/unlock/<username>")
def unlock(username):
    if session.get("role") != "Admin": return redirect("/login")
    conn=sqlite3.connect("database.db")
    conn.execute("UPDATE users SET failed_attempts=0, lock_time=NULL WHERE username=?", (username,))
    conn.commit(); conn.close()
    return redirect("/admin")

@app.route("/delete/<username>")
def delete(username):
    if session.get("role") != "Admin": return redirect("/login")
    if username == "admin":
        set_error("Cannot delete the admin account.")
        return redirect("/admin")
    conn=sqlite3.connect("database.db")
    conn.execute("DELETE FROM users WHERE username=?", (username,))
    conn.commit(); conn.close()
    return redirect("/admin")

# ================================================================
# STAFF SERVICES
# ================================================================

@app.route("/inventory")
def inventory():
    if "user" not in session or session.get("role") != "Staff":
        return redirect("/login")
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM inventory ORDER BY quantity ASC")
    items = cur.fetchall()
    conn.close()
    low_stock = [i for i in items if i[3] <= i[5]]
    return render_template("inventory.html", items=items, low_stock=low_stock, user=session["user"])

@app.route("/inventory/add", methods=["POST"])
def add_inventory():
    if "user" not in session or session.get("role") != "Staff": return redirect("/login")
    conn = sqlite3.connect("database.db")
    conn.execute("INSERT INTO inventory(product_name,category,quantity,price,low_stock_threshold) VALUES(?,?,?,?,?)",
                 (request.form["product_name"], request.form["category"],
                  int(request.form["quantity"]), float(request.form["price"]),
                  int(request.form.get("threshold", 5))))
    conn.commit(); conn.close()
    return redirect("/inventory")

@app.route("/inventory/delete/<int:item_id>")
def delete_inventory(item_id):
    if "user" not in session or session.get("role") != "Staff": return redirect("/login")
    conn = sqlite3.connect("database.db")
    conn.execute("DELETE FROM inventory WHERE id=?", (item_id,))
    conn.commit(); conn.close()
    return redirect("/inventory")

@app.route("/reports")
def reports():
    if "user" not in session or session.get("role") != "Staff": return redirect("/login")
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    week  = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    month = datetime.datetime.now().strftime("%Y-%m")
    cur.execute("SELECT SUM(total_price), COUNT(*) FROM sales WHERE sale_time LIKE ?", (today+"%",))
    daily = cur.fetchone()
    cur.execute("SELECT SUM(total_price), COUNT(*) FROM sales WHERE sale_time >= ?", (week,))
    weekly = cur.fetchone()
    cur.execute("SELECT SUM(total_price), COUNT(*) FROM sales WHERE sale_time LIKE ?", (month+"%",))
    monthly = cur.fetchone()
    cur.execute("SELECT product_name, SUM(quantity), SUM(total_price) FROM sales GROUP BY product_name ORDER BY SUM(quantity) DESC LIMIT 5")
    top_products = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM inventory WHERE quantity <= low_stock_threshold")
    low_stock_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM returns WHERE status='Pending'")
    pending_returns = cur.fetchone()[0]
    conn.close()
    return render_template("reports.html", daily=daily, weekly=weekly, monthly=monthly,
                           top_products=top_products, low_stock_count=low_stock_count,
                           pending_returns=pending_returns, user=session["user"])

@app.route("/announcements")
def announcements():
    if "user" not in session or session.get("role") != "Staff": return redirect("/login")
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM announcements ORDER BY id DESC")
    ann_list = cur.fetchall()
    conn.close()
    return render_template("announcements.html", announcements=ann_list, user=session["user"])

@app.route("/announcements/add", methods=["POST"])
def add_announcement():
    if session.get("role") != "Admin": return redirect("/login")
    conn = sqlite3.connect("database.db")
    conn.execute("INSERT INTO announcements(title,message,posted_by,posted_time) VALUES(?,?,?,?)",
                 (request.form["title"], request.form["message"], session["user"],
                  datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit(); conn.close()
    return redirect("/admin")

@app.route("/work_hours", methods=["GET","POST"])
def work_hours():
    if "user" not in session or session.get("role") != "Staff": return redirect("/login")
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if request.method == "POST":
        action = request.form.get("action")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("SELECT id, clock_in, clock_out FROM staff_hours WHERE username=? AND date=?",
                    (session["user"], today))
        record = cur.fetchone()
        if action == "clock_in":
            if not record:
                conn.execute("INSERT INTO staff_hours(username,date,clock_in) VALUES(?,?,?)",
                             (session["user"], today, now_str))
                conn.commit()
                set_error("Clocked in successfully.")
            else:
                set_error("Already clocked in today.")
        elif action == "clock_out":
            if record and record[1] and not record[2]:
                ci = datetime.datetime.strptime(record[1], "%Y-%m-%d %H:%M:%S")
                co = datetime.datetime.strptime(now_str, "%Y-%m-%d %H:%M:%S")
                hours = round((co - ci).total_seconds() / 3600, 2)
                conn.execute("UPDATE staff_hours SET clock_out=?, hours_worked=? WHERE id=?",
                             (now_str, hours, record[0]))
                conn.commit()
                set_error(f"Clocked out. Hours worked today: {hours}")
            else:
                set_error("Clock in first before clocking out.")
        conn.close()
        return redirect("/work_hours")
    cur.execute("SELECT * FROM staff_hours WHERE username=? ORDER BY date DESC LIMIT 30", (session["user"],))
    hours_log = cur.fetchall()
    cur.execute("SELECT SUM(hours_worked) FROM staff_hours WHERE username=?", (session["user"],))
    total_hours = cur.fetchone()[0] or 0
    cur.execute("SELECT id, clock_in, clock_out FROM staff_hours WHERE username=? AND date=?",
                (session["user"], today))
    today_record = cur.fetchone()
    conn.close()
    error = get_error()
    return render_template("work_hours.html", hours_log=hours_log,
                           total_hours=round(total_hours, 2),
                           today_record=today_record, user=session["user"], error=error)

@app.route("/salary")
def salary():
    if "user" not in session or session.get("role") != "Staff": return redirect("/login")
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM salary WHERE username=? ORDER BY id DESC", (session["user"],))
    salary_list = cur.fetchall()
    cur.execute("SELECT SUM(amount) FROM salary WHERE username=? AND status='Paid'", (session["user"],))
    total_earned = cur.fetchone()[0] or 0
    conn.close()
    return render_template("salary.html", salary_list=salary_list,
                           total_earned=total_earned, user=session["user"])

@app.route("/staff_complaints")
def staff_complaints():
    if "user" not in session or session.get("role") != "Staff": return redirect("/login")
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM complaints ORDER BY id DESC")
    all_complaints = cur.fetchall()
    conn.close()
    return render_template("staff_complaints.html", complaints=all_complaints, user=session["user"])

@app.route("/resolve_complaint/<int:cid>")
def resolve_complaint(cid):
    if "user" not in session or session.get("role") not in ("Staff","Admin"): return redirect("/login")
    conn = sqlite3.connect("database.db")
    conn.execute("UPDATE complaints SET status='Resolved' WHERE id=?", (cid,))
    conn.commit(); conn.close()
    return redirect("/staff_complaints" if session.get("role")=="Staff" else "/admin")

# ================================================================
# CUSTOMER FEATURES
# ================================================================

@app.route("/profile", methods=["GET","POST"])
def profile():
    if "user" not in session or session.get("role") != "Customer": return redirect("/login")
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    if request.method == "POST":
        new_email = request.form.get("email","").strip()
        cur.execute("UPDATE users SET email=? WHERE username=?", (new_email, session["user"]))
        conn.commit()
        set_error("Profile updated successfully.")
    cur.execute("SELECT username, email, role FROM users WHERE username=?", (session["user"],))
    user_data = cur.fetchone()
    cur.execute("SELECT COUNT(*), SUM(total_price) FROM customer_orders WHERE username=?", (session["user"],))
    order_stats = cur.fetchone()
    conn.close()
    error = get_error()
    return render_template("profile.html", user_data=user_data,
                           order_count=order_stats[0] or 0,
                           total_spent=order_stats[1] or 0,
                           user=session["user"], error=error)

@app.route("/change_password", methods=["GET","POST"])
def change_password():
    if "user" not in session: return redirect("/login")
    if request.method == "POST":
        current = request.form.get("current_password","")
        new_pwd = request.form.get("new_password","")
        confirm = request.form.get("confirm_password","")
        conn = sqlite3.connect("database.db")
        cur = conn.cursor()
        cur.execute("SELECT password FROM users WHERE username=?", (session["user"],))
        row = cur.fetchone()
        if not check_password_hash(row[0], current):
            conn.close()
            set_error("Current password is incorrect.")
            return redirect("/change_password")
        if new_pwd != confirm:
            conn.close()
            set_error("New passwords do not match.")
            return redirect("/change_password")
        if not strong_password(new_pwd):
            conn.close()
            set_error("Password must be at least 8 characters with uppercase and a number.")
            return redirect("/change_password")
        if check_password_hash(row[0], new_pwd):
            conn.close()
            set_error("New password cannot be the same as current password.")
            return redirect("/change_password")
        conn.execute("UPDATE users SET password=? WHERE username=?",
                     (generate_password_hash(new_pwd), session["user"]))
        conn.commit(); conn.close()
        set_error("Password changed successfully. Please login again.")
        session.clear()
        return redirect("/login")
    error = get_error()
    return render_template("change_password.html", user=session["user"],
                           role=session.get("role"), error=error)

@app.route("/my_orders", methods=["GET","POST"])
def my_orders():
    if "user" not in session or session.get("role") != "Customer": return redirect("/login")
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    if request.method == "POST":
        product_name = request.form.get("product_name","")
        quantity     = int(request.form.get("quantity", 1))
        cur.execute("SELECT id, price, quantity FROM inventory WHERE product_name=?", (product_name,))
        product = cur.fetchone()
        if not product:
            conn.close()
            set_error("Product not found in store.")
            return redirect("/my_orders")
        if product[2] < quantity:
            conn.close()
            set_error(f"Only {product[2]} units available.")
            return redirect("/my_orders")
        total = product[1] * quantity
        now   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO customer_orders(username,product_name,quantity,total_price,order_time,status) VALUES(?,?,?,?,?,?)",
                     (session["user"], product_name, quantity, total, now, "Confirmed"))
        conn.execute("UPDATE inventory SET quantity=quantity-? WHERE id=?", (quantity, product[0]))
        conn.commit()
    cur.execute("SELECT * FROM customer_orders WHERE username=? ORDER BY id DESC", (session["user"],))
    orders = cur.fetchall()
    cur.execute("SELECT product_name FROM inventory ORDER BY product_name")
    products = cur.fetchall()
    cur.execute("SELECT COUNT(*), SUM(total_price) FROM customer_orders WHERE username=?", (session["user"],))
    stats = cur.fetchone()
    score = min(int((stats[1] or 0) / 100), 100)
    conn.close()
    error = get_error()
    return render_template("my_orders.html", orders=orders, products=products,
                           order_count=stats[0] or 0, total_spent=stats[1] or 0,
                           score=score, user=session["user"], error=error)

@app.route("/invoice/<int:order_id>")
def invoice(order_id):
    if "user" not in session or session.get("role") != "Customer": return redirect("/login")
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM customer_orders WHERE id=? AND username=?", (order_id, session["user"]))
    order = cur.fetchone()
    conn.close()
    if not order: return redirect("/my_orders")
    return render_template("invoice.html", order=order, user=session["user"])

@app.route("/my_announcements")
def my_announcements():
    if "user" not in session or session.get("role") != "Customer": return redirect("/login")
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM announcements ORDER BY id DESC")
    ann_list = cur.fetchall()
    conn.close()
    return render_template("my_announcements.html", announcements=ann_list, user=session["user"])

@app.route("/complaints", methods=["GET","POST"])
def complaints():
    if "user" not in session: return redirect("/login")
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    if request.method == "POST":
        subject = request.form.get("subject","")
        message = request.form.get("message","")
        now     = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO complaints(username,subject,message,status,submitted_time) VALUES(?,?,?,?,?)",
                     (session["user"], subject, message, "Open", now))
        conn.commit()
        set_error("Complaint submitted successfully.")
        return redirect("/complaints")
    cur.execute("SELECT * FROM complaints WHERE username=? ORDER BY id DESC", (session["user"],))
    my_complaints = cur.fetchall()
    conn.close()
    error = get_error()
    return render_template("complaints.html", complaints=my_complaints,
                           user=session["user"], role=session.get("role"), error=error)

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)