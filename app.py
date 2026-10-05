"""FIND MY MECH - motorcycle shop finder, queue and reservation prototype."""
import os, sqlite3, math, json
from datetime import date
from functools import wraps
from flask import (Flask, g, render_template, request, redirect, url_for,
                   session, flash, jsonify, abort)
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "database", "findmymech.db")
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me")

USER_LOCATION = (9.6477, 123.8554)  # default user spot (Tagbilaran); swap for browser GPS later
ACTIVE_Q = ("Waiting", "Called", "In Service")
Q_STATUS = ("Waiting", "Called", "In Service", "Completed", "Cancelled")
R_STATUS = ("Pending", "Confirmed", "In Service", "Completed", "Cancelled")
SHOP_STATUS = ("AVAILABLE", "MODERATE", "BUSY")
MODELS = {"Honda": ["Click 125i", "Click 160", "Beat", "Wave"], "Yamaha": ["Mio i125", "NMAX", "Aerox"],
          "Suzuki": ["Raider"], "Kawasaki": ["Barako"], "Rusi": ["Other"], "Motorstar": ["Other"], "Other": ["Other"]}
MODEL_TYPE = {"Click 125i": "Scooter", "Click 160": "Scooter", "Beat": "Scooter", "Wave": "Underbone",
              "Mio i125": "Scooter", "NMAX": "Maxi-scooter", "Aerox": "Maxi-scooter", "Raider": "Underbone",
              "Barako": "Standard", "Other": "Standard"}
TYPE_MULT = {"Scooter": 1.0, "Underbone": 1.0, "Maxi-scooter": 1.4, "Standard": 1.1, "Sport": 1.5, "Big bike": 2.0}
BRAND_MULT = {"Honda": 1.0, "Yamaha": 1.05, "Suzuki": 1.05, "Kawasaki": 1.15, "Rusi": 0.9, "Motorstar": 0.9, "Other": 1.0}
MODEL_MULT = {"Click 160": 1.1, "NMAX": 1.15, "Aerox": 1.15}

# ---------------------------------------------------------------- database
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d: d.close()

def q(sql, args=(), one=False):
    cur = db().execute(sql, args); rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows

def run(sql, args=()):
    cur = db().execute(sql, args); db().commit(); return cur.lastrowid

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL, contact_number TEXT, role TEXT DEFAULT 'user', shop_id INTEGER);
CREATE TABLE IF NOT EXISTS shops(id INTEGER PRIMARY KEY, name TEXT, address TEXT, phone TEXT, latitude REAL,
  longitude REAL, opening_time TEXT, closing_time TEXT, status TEXT, available_mechanics INTEGER,
  rating REAL, minutes_per_customer INTEGER DEFAULT 10, wait_override INTEGER);
CREATE TABLE IF NOT EXISTS services(id INTEGER PRIMARY KEY, shop_id INTEGER, service_name TEXT,
  base_price REAL, estimated_duration INTEGER);
CREATE TABLE IF NOT EXISTS motorcycles(id INTEGER PRIMARY KEY, user_id INTEGER, brand TEXT, model TEXT, motorcycle_type TEXT);
CREATE TABLE IF NOT EXISTS queues(id INTEGER PRIMARY KEY, user_id INTEGER, shop_id INTEGER, service_id INTEGER,
  motorcycle_id INTEGER, queue_number TEXT, queue_status TEXT DEFAULT 'Waiting', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS reservations(id INTEGER PRIMARY KEY, user_id INTEGER, shop_id INTEGER, service_id INTEGER,
  motorcycle_id INTEGER, reservation_number TEXT, reservation_date TEXT, reservation_time TEXT, concern TEXT,
  status TEXT DEFAULT 'Pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""
SERVICES = [("Change Oil", 150, 15), ("Tire Change", 200, 30), ("Tire Repair", 100, 20), ("Brake Adjustment", 150, 20),
            ("Brake Pad Replacement", 300, 30), ("Spark Plug Replacement", 150, 15), ("Chain Adjustment", 100, 15),
            ("Battery Check", 100, 15), ("Engine Tune-Up", 500, 60), ("General Check-Up", 300, 30)]
# name, address, phone, lat, lng, open, close, status, mechanics, rating, waiting-now, min/customer
SHOPS = [("CDLM Motor Shop", "Carlos P. Garcia Ave, Tagbilaran City", "0917-100-0001", 9.6510, 123.8520, "08:00", "18:00", "AVAILABLE", 3, 4.6, 1, 10),
         ("ANMAR Motor Shop", "J.A. Clarin St, Tagbilaran City", "0917-100-0002", 9.6560, 123.8600, "08:00", "17:30", "MODERATE", 2, 4.3, 3, 10),
         ("AGRT Motor Shop", "Dampas District, Tagbilaran City", "0917-100-0003", 9.6700, 123.8480, "07:30", "18:00", "BUSY", 2, 4.1, 7, 9),
         ("PUG Motor Shop", "Cogon District, Tagbilaran City", "0917-100-0004", 9.6390, 123.8650, "09:00", "19:00", "AVAILABLE", 2, 4.8, 0, 10)]

def init_db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB); c.executescript(SCHEMA)
    if not c.execute("SELECT 1 FROM shops").fetchone():
        c.execute("INSERT INTO users(name,email,password,contact_number) VALUES('Walk-in','walkin@local',?, '')", (generate_password_hash("x"),))
        c.execute("INSERT INTO motorcycles(user_id,brand,model,motorcycle_type) VALUES(1,'Honda','Beat','Scooter')")
        c.execute("INSERT INTO users(name,email,password,contact_number) VALUES('Demo Rider','demo@findmymech.test',?, '09171234567')", (generate_password_hash("demo123"),))
        for i, s in enumerate(SHOPS, 1):
            c.execute("INSERT INTO shops(name,address,phone,latitude,longitude,opening_time,closing_time,status,available_mechanics,rating,minutes_per_customer) VALUES(?,?,?,?,?,?,?,?,?,?,?)", s[:10] + (s[11],))
            for n, (nm, p, d) in enumerate(SERVICES):
                c.execute("INSERT INTO services(shop_id,service_name,base_price,estimated_duration) VALUES(?,?,?,?)", (i, nm, p + (i % 2) * 10 * (n % 3), d))
            c.execute("INSERT INTO users(name,email,password,contact_number,role,shop_id) VALUES(?,?,?,?, 'admin',?)",
                      (s[0] + " Owner", f"owner{i}@findmymech.test", generate_password_hash("admin123"), s[2], i))
            for k in range(s[10]):
                c.execute("INSERT INTO queues(user_id,shop_id,service_id,motorcycle_id,queue_number) VALUES(1,?,?,1,?)", (i, (i - 1) * 10 + 1, f"Q-{k+1:03d}"))
        c.commit()
    c.close()

# ---------------------------------------------------------------- helpers
def current_user():
    return q("SELECT * FROM users WHERE id=?", (session["uid"],), one=True) if "uid" in session else None

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not current_user(): return redirect(url_for("login"))
        return f(*a, **k)
    return w

def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        u = current_user()
        if not u: return redirect(url_for("login"))
        if u["role"] != "admin": abort(403)
        return f(*a, **k)
    return w

def km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))

def fmt_wait(m):
    if m <= 0: return "No waiting"
    if m < 60: return f"{m} min"
    h, r = divmod(m, 60)
    return f"{h} hr" + (f" {r} min" if r else "")

def shop_info(s):
    waiting = q("SELECT COUNT(*) c FROM queues WHERE shop_id=? AND queue_status IN (?,?,?)", (s["id"],) + ACTIVE_Q, one=True)["c"]
    mins = s["wait_override"] if s["wait_override"] is not None else waiting * s["minutes_per_customer"]
    d = dict(s); d.update(waiting=waiting, wait_min=mins, wait_text=fmt_wait(mins),
                          dist=round(km(*USER_LOCATION, s["latitude"], s["longitude"]), 1),
                          cls={"AVAILABLE": "green", "MODERATE": "yellow", "BUSY": "red"}[s["status"]],
                          label={"AVAILABLE": "Available", "MODERATE": "Moderate", "BUSY": "Busy"}[s["status"]],
                          hours=f"{s['opening_time']} - {s['closing_time']}")
    return d

def all_shops(search=""):
    rows = q("SELECT * FROM shops WHERE name LIKE ? OR address LIKE ?", (f"%{search}%",) * 2)
    return sorted((shop_info(r) for r in rows), key=lambda x: (SHOP_STATUS.index(x["status"]), x["wait_min"], x["dist"]))

def estimate(base, brand, model, mtype):
    return round(base * TYPE_MULT.get(mtype, 1) * BRAND_MULT.get(brand, 1) * MODEL_MULT.get(model, 1) / 5) * 5

def moto(uid, brand, model, mtype):
    r = q("SELECT id FROM motorcycles WHERE user_id=? AND brand=? AND model=? AND motorcycle_type=?", (uid, brand, model, mtype), one=True)
    return r["id"] if r else run("INSERT INTO motorcycles(user_id,brand,model,motorcycle_type) VALUES(?,?,?,?)", (uid, brand, model, mtype))

def moto_form():
    f = request.form
    brand, model, mtype = f.get("brand", "Other"), f.get("model", "Other"), f.get("motorcycle_type", "Standard")
    if brand not in MODELS or mtype not in TYPE_MULT: return None
    if model not in MODELS[brand]: model = MODELS[brand][0]
    return brand, model, mtype

def get_service(sid, shop_id):
    return q("SELECT * FROM services WHERE id=? AND shop_id=?", (sid, shop_id), one=True)

@app.context_processor
def inject():
    return dict(user=current_user(), MODELS=MODELS, MODEL_TYPE=MODEL_TYPE, TYPE_MULT=TYPE_MULT,
                MODELS_JSON=json.dumps(MODELS), TYPES_JSON=json.dumps(MODEL_TYPE), today=date.today().isoformat())

# ---------------------------------------------------------------- auth
@app.route("/")
def index():
    return redirect(url_for("dashboard" if current_user() else "login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ident = request.form.get("identity", "").strip().lower()
        u = q("SELECT * FROM users WHERE lower(email)=? OR lower(name)=?", (ident, ident), one=True)
        if u and check_password_hash(u["password"], request.form.get("password", "")):
            session.clear(); session["uid"] = u["id"]
            return redirect(url_for("admin" if u["role"] == "admin" else "dashboard"))
        flash("Wrong email/username or password.", "error")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form; name, email = f.get("name", "").strip(), f.get("email", "").strip().lower()
        if not name or not email or len(f.get("password", "")) < 6:
            flash("Enter your name, email and a password of at least 6 characters.", "error")
        elif q("SELECT 1 FROM users WHERE email=?", (email,), one=True):
            flash("That email is already registered. Try logging in.", "error")
        else:
            run("INSERT INTO users(name,email,password,contact_number) VALUES(?,?,?,?)",
                (name, email, generate_password_hash(f["password"]), f.get("contact_number", "")))
            flash("Account created. Log in to continue.", "ok"); return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/forgot")
def forgot():
    flash("Password reset is not available in the prototype. Ask the shop owner or re-register.", "ok")
    return redirect(url_for("login"))

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    u = current_user()
    if request.method == "POST":
        run("UPDATE users SET name=?, contact_number=? WHERE id=?", (request.form["name"].strip() or u["name"], request.form.get("contact_number", ""), u["id"]))
        flash("Profile saved.", "ok"); return redirect(url_for("profile"))
    return render_template("profile.html", bikes=q("SELECT * FROM motorcycles WHERE user_id=?", (u["id"],)))

# ---------------------------------------------------------------- shops
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", shops=all_shops())

@app.route("/shops")
@login_required
def shops():
    term = request.args.get("q", "").strip(); lst = all_shops(term)
    la = [s["latitude"] for s in lst] or [0]; lo = [s["longitude"] for s in lst] or [0]
    for s in lst:  # position pins on the placeholder map
        s["px"] = 10 + 80 * (s["longitude"] - min(lo)) / ((max(lo) - min(lo)) or 1)
        s["py"] = 10 + 80 * (max(la) - s["latitude"]) / ((max(la) - min(la)) or 1)
    return render_template("shops.html", shops=lst, term=term)

@app.route("/shops/<int:sid>")
@login_required
def shop_details(sid):
    s = q("SELECT * FROM shops WHERE id=?", (sid,), one=True) or abort(404)
    return render_template("shop_details.html", s=shop_info(s), services=q("SELECT * FROM services WHERE shop_id=?", (sid,)))

@app.route("/services")
@login_required
def services():
    sid = request.args.get("shop", type=int) or all_shops()[0]["id"]
    s = q("SELECT * FROM shops WHERE id=?", (sid,), one=True) or abort(404)
    return render_template("services.html", s=shop_info(s), shops=q("SELECT id,name FROM shops"), services=q("SELECT * FROM services WHERE shop_id=?", (sid,)))

@app.route("/api/estimate")
def api_estimate():
    s = q("SELECT * FROM services WHERE id=?", (request.args.get("service_id", type=int),), one=True)
    if not s: return jsonify(error="service not found"), 404
    a = request.args
    return jsonify(estimate=estimate(s["base_price"], a.get("brand"), a.get("model"), a.get("type")), base=s["base_price"])

# ---------------------------------------------------------------- queue
@app.route("/queue/join/<int:sid>", methods=["GET", "POST"])
@login_required
def join_queue(sid):
    s = q("SELECT * FROM shops WHERE id=?", (sid,), one=True) or abort(404); u = current_user()
    svcs = q("SELECT * FROM services WHERE shop_id=?", (sid,))
    if request.method == "POST":
        m, sv = moto_form(), get_service(request.form.get("service_id", type=int), sid)
        if not m or not sv: flash("Choose a service and your motorcycle.", "error")
        elif q("SELECT 1 FROM queues WHERE user_id=? AND shop_id=? AND queue_status IN (?,?,?)", (u["id"], sid) + ACTIVE_Q, one=True):
            flash("You already have an active queue at this shop. Cancel it first to rejoin.", "error")
        else:
            n = q("SELECT COUNT(*) c FROM queues WHERE shop_id=?", (sid,), one=True)["c"] + 1
            run("INSERT INTO queues(user_id,shop_id,service_id,motorcycle_id,queue_number) VALUES(?,?,?,?,?)", (u["id"], sid, sv["id"], moto(u["id"], *m), f"Q-{n:03d}"))
            flash("You joined the queue.", "ok"); return redirect(url_for("my_activity"))
    return render_template("queue_join.html", s=shop_info(s), services=svcs, pick=request.args.get("service", type=int))

@app.route("/queue/cancel/<int:qid>", methods=["POST"])
@login_required
def cancel_queue(qid):
    run("UPDATE queues SET queue_status='Cancelled' WHERE id=? AND user_id=? AND queue_status IN ('Waiting','Called')", (qid, session["uid"]))
    flash("Queue cancelled.", "ok"); return redirect(url_for("my_activity"))

@app.route("/my")
@login_required
def my_activity():
    uid = session["uid"]
    qs = [dict(r) for r in q("""SELECT q.*, s.name shop, s.minutes_per_customer mpc, sv.service_name, m.brand||' '||m.model bike
        FROM queues q JOIN shops s ON s.id=q.shop_id JOIN services sv ON sv.id=q.service_id JOIN motorcycles m ON m.id=q.motorcycle_id
        WHERE q.user_id=? ORDER BY q.id DESC""", (uid,))]
    for r in qs:
        r["ahead"] = q("SELECT COUNT(*) c FROM queues WHERE shop_id=? AND queue_status IN (?,?,?) AND id<?", (r["shop_id"],) + ACTIVE_Q + (r["id"],), one=True)["c"]
        r["wait"] = fmt_wait(r["ahead"] * r["mpc"]) if r["queue_status"] in ACTIVE_Q else "-"
    rs = q("""SELECT r.*, s.name shop, sv.service_name, m.brand||' '||m.model bike FROM reservations r JOIN shops s ON s.id=r.shop_id
        JOIN services sv ON sv.id=r.service_id JOIN motorcycles m ON m.id=r.motorcycle_id WHERE r.user_id=? ORDER BY r.reservation_date DESC""", (uid,))
    return render_template("queue.html", queues=qs, reservations=rs)

# ---------------------------------------------------------------- reservations
@app.route("/reserve", methods=["GET", "POST"])
@login_required
def reserve():
    u = current_user(); sid = request.values.get("shop_id", type=int) or all_shops()[0]["id"]
    s = q("SELECT * FROM shops WHERE id=?", (sid,), one=True) or abort(404)
    if request.method == "POST":
        f = request.form; m, sv = moto_form(), get_service(f.get("service_id", type=int), sid)
        d, t = f.get("date", ""), f.get("time", "")
        if not m or not sv or not d or not t or d < date.today().isoformat():
            flash("Complete the form and pick today or a later date.", "error")
        elif not (s["opening_time"] <= t <= s["closing_time"]):
            flash(f"Pick a time between {s['opening_time']} and {s['closing_time']}.", "error")
        else:
            rid = run("INSERT INTO reservations(user_id,shop_id,service_id,motorcycle_id,reservation_date,reservation_time,concern) VALUES(?,?,?,?,?,?,?)",
                      (u["id"], sid, sv["id"], moto(u["id"], *m), d, t, f.get("concern", "")))
            run("UPDATE reservations SET reservation_number=? WHERE id=?", (f"RES-{rid:04d}", rid))
            run("UPDATE users SET contact_number=? WHERE id=? AND (contact_number IS NULL OR contact_number='')", (f.get("contact", ""), u["id"]))
            return redirect(url_for("reservation_confirm", rid=rid))
    return render_template("reservation.html", s=shop_info(s), shops=q("SELECT id,name FROM shops"), services=q("SELECT * FROM services WHERE shop_id=?", (sid,)), pick=request.args.get("service", type=int))

@app.route("/reservation/<int:rid>")
@login_required
def reservation_confirm(rid):
    r = q("""SELECT r.*, s.name shop, sv.service_name, sv.base_price, m.brand, m.model, m.motorcycle_type FROM reservations r
        JOIN shops s ON s.id=r.shop_id JOIN services sv ON sv.id=r.service_id JOIN motorcycles m ON m.id=r.motorcycle_id
        WHERE r.id=? AND r.user_id=?""", (rid, session["uid"]), one=True) or abort(404)
    return render_template("confirmation.html", r=r, est=estimate(r["base_price"], r["brand"], r["model"], r["motorcycle_type"]))

@app.route("/reservation/cancel/<int:rid>", methods=["POST"])
@login_required
def cancel_reservation(rid):
    run("UPDATE reservations SET status='Cancelled' WHERE id=? AND user_id=? AND status IN ('Pending','Confirmed')", (rid, session["uid"]))
    flash("Reservation cancelled.", "ok"); return redirect(url_for("my_activity") + "#reservations")

# ---------------------------------------------------------------- admin
@app.route("/admin")
@admin_required
def admin():
    sid = current_user()["shop_id"]; s = q("SELECT * FROM shops WHERE id=?", (sid,), one=True)
    qs = q("""SELECT q.*, u.name cust, sv.service_name, m.brand||' '||m.model bike FROM queues q JOIN users u ON u.id=q.user_id
        JOIN services sv ON sv.id=q.service_id JOIN motorcycles m ON m.id=q.motorcycle_id WHERE q.shop_id=? ORDER BY q.id DESC""", (sid,))
    rs = q("""SELECT r.*, u.name cust, u.contact_number, sv.service_name, m.brand||' '||m.model bike FROM reservations r JOIN users u ON u.id=r.user_id
        JOIN services sv ON sv.id=r.service_id JOIN motorcycles m ON m.id=r.motorcycle_id WHERE r.shop_id=? ORDER BY r.reservation_date, r.reservation_time""", (sid,))
    return render_template("admin.html", s=shop_info(s), queues=qs, reservations=rs, services=q("SELECT * FROM services WHERE shop_id=?", (sid,)),
                           Q_STATUS=Q_STATUS, R_STATUS=R_STATUS, SHOP_STATUS=SHOP_STATUS)

@app.route("/admin/queue/<int:qid>", methods=["POST"])
@admin_required
def admin_queue(qid):
    st = request.form.get("status")
    if st in Q_STATUS: run("UPDATE queues SET queue_status=? WHERE id=? AND shop_id=?", (st, qid, current_user()["shop_id"]))
    return redirect(url_for("admin"))

@app.route("/admin/reservation/<int:rid>", methods=["POST"])
@admin_required
def admin_reservation(rid):
    st = request.form.get("status")
    if st in R_STATUS: run("UPDATE reservations SET status=? WHERE id=? AND shop_id=?", (st, rid, current_user()["shop_id"]))
    return redirect(url_for("admin") + "#reservations")

@app.route("/admin/shop", methods=["POST"])
@admin_required
def admin_shop():
    f = request.form; ov = f.get("wait_override", "").strip()
    if f.get("status") in SHOP_STATUS:
        run("UPDATE shops SET status=?, available_mechanics=?, wait_override=? WHERE id=?",
            (f["status"], max(0, f.get("mechanics", 0, type=int)), int(ov) if ov.isdigit() else None, current_user()["shop_id"]))
        flash("Shop status updated.", "ok")
    return redirect(url_for("admin"))

@app.route("/admin/service", methods=["POST"])
@admin_required
def admin_service():
    f, sid = request.form, current_user()["shop_id"]
    try: price, dur = float(f["base_price"]), int(f.get("duration", 30))
    except (KeyError, ValueError): flash("Enter a valid price.", "error"); return redirect(url_for("admin") + "#services")
    if f.get("service_id"):
        run("UPDATE services SET base_price=?, estimated_duration=? WHERE id=? AND shop_id=?", (price, dur, f.get("service_id", type=int), sid))
    elif f.get("service_name", "").strip():
        run("INSERT INTO services(shop_id,service_name,base_price,estimated_duration) VALUES(?,?,?,?)", (sid, f["service_name"].strip(), price, dur))
    return redirect(url_for("admin") + "#services")

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
