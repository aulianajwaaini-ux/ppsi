from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
import sqlite3, os, csv, io
from functools import wraps
from datetime import date

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "pad_okus.db")
app = Flask(__name__)
app.secret_key = os.environ.get("PAD_OKUS_SECRET", "ubah-secret-key-untuk-deployment")

CATEGORIES = ["Pajak Daerah", "Retribusi Daerah", "Hasil Pengelolaan Kekayaan Daerah", "Lain-lain PAD yang Sah"]

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS revenues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            period TEXT NOT NULL,
            target REAL NOT NULL DEFAULT 0,
            realization REAL NOT NULL DEFAULT 0,
            location TEXT NOT NULL DEFAULT 'Muaradua',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL DEFAULT 'Petugas'
        )""")
        count = con.execute("SELECT COUNT(*) FROM revenues").fetchone()[0]
        if count == 0:
            demo = [
                ("Pajak Daerah","Pajak restoran dan rumah makan","2026-01",150000000,112500000,"Muaradua","DATA SIMULASI"),
                ("Pajak Daerah","Pajak hotel/penginapan","2026-02",80000000,61000000,"Muaradua","DATA SIMULASI"),
                ("Retribusi Daerah","Retribusi pasar","2026-02",50000000,42000000,"Muaradua","DATA SIMULASI"),
                ("Retribusi Daerah","Retribusi pelayanan umum","2026-03",70000000,73500000,"Muaradua","DATA SIMULASI"),
                ("Lain-lain PAD yang Sah","Pendapatan layanan daerah","2026-03",90000000,54000000,"OKU Selatan","DATA SIMULASI"),
                ("Hasil Pengelolaan Kekayaan Daerah","Bagian laba penyertaan modal","2026-04",60000000,38000000,"OKU Selatan","DATA SIMULASI"),
            ]
            con.executemany("INSERT INTO revenues(category,description,period,target,realization,location,notes) VALUES(?,?,?,?,?,?,?)", demo)
        count_users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count_users == 0:
            con.executemany("INSERT INTO users(name,email,role) VALUES(?,?,?)", [
                ("Administrator Demo","admin@padokus.local","Administrator"),
                ("Petugas Demo","petugas@padokus.local","Petugas"),
                ("Pimpinan Demo","pimpinan@padokus.local","Pimpinan"),
            ])

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def get_summary():
    with db() as con:
        rows = con.execute("SELECT COALESCE(SUM(target),0) target, COALESCE(SUM(realization),0) realization FROM revenues").fetchone()
    target, realization = float(rows["target"]), float(rows["realization"])
    return {"target": target, "realization": realization,
            "achievement": realization / target * 100 if target else 0,
            "gap": target - realization}

@app.template_filter("rupiah")
def rupiah(value):
    try:
        return "Rp " + f"{float(value):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "Rp 0"

@app.route("/")
def index():
    return redirect(url_for("dashboard") if session.get("user") else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        # Demo-only sign-in: replace with hashed passwords and real authentication before deployment.
        with db() as con:
            user = con.execute("SELECT * FROM users WHERE lower(email)=?", (email,)).fetchone()
        if user:
            session["user"] = {"name": user["name"], "email": user["email"], "role": user["role"]}
            return redirect(url_for("dashboard"))
        flash("Email tidak ditemukan. Gunakan akun demo yang tercantum di halaman login.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    summary = get_summary()
    with db() as con:
        rows = con.execute("SELECT category, SUM(target) target, SUM(realization) realization FROM revenues GROUP BY category ORDER BY realization DESC").fetchall()
        recent = con.execute("SELECT * FROM revenues ORDER BY period DESC, id DESC LIMIT 5").fetchall()
    return render_template("dashboard.html", summary=summary, categories=rows, recent=recent)

@app.route("/pendapatan", methods=["GET", "POST"])
@login_required
def revenues():
    if request.method == "POST":
        try:
            category = request.form["category"]
            description = request.form["description"].strip()
            period = request.form["period"]
            target = float(request.form.get("target", 0))
            realization = float(request.form.get("realization", 0))
            location = request.form.get("location", "Muaradua").strip() or "Muaradua"
            notes = request.form.get("notes", "").strip()
            if not description or target < 0 or realization < 0:
                raise ValueError("Periksa kembali data yang diisi.")
            with db() as con:
                con.execute("INSERT INTO revenues(category,description,period,target,realization,location,notes) VALUES(?,?,?,?,?,?,?)",
                            (category, description, period, target, realization, location, notes))
            flash("Data pendapatan berhasil ditambahkan.")
        except (ValueError, KeyError):
            flash("Data belum valid. Target dan realisasi harus berupa angka nol atau lebih.")
        return redirect(url_for("revenues"))
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    with db() as con:
        sql = "SELECT * FROM revenues WHERE (description LIKE ? OR category LIKE ? OR location LIKE ?)"
        params = [f"%{q}%", f"%{q}%", f"%{q}%"]
        if category in CATEGORIES:
            sql += " AND category=?"
            params.append(category)
        sql += " ORDER BY period DESC, id DESC"
        rows = con.execute(sql, params).fetchall()
    return render_template("revenues.html", rows=rows, categories=CATEGORIES, q=q, selected_category=category)

@app.route("/pendapatan/<int:item_id>/hapus", methods=["POST"])
@login_required
def delete_revenue(item_id):
    with db() as con:
        con.execute("DELETE FROM revenues WHERE id=?", (item_id,))
    flash("Data pendapatan dihapus.")
    return redirect(url_for("revenues"))

@app.route("/analisis")
@login_required
def analysis():
    with db() as con:
        rows = con.execute("SELECT category, SUM(target) target, SUM(realization) realization FROM revenues GROUP BY category ORDER BY category").fetchall()
    return render_template("analysis.html", rows=rows)

@app.route("/laporan")
@login_required
def reports():
    summary = get_summary()
    with db() as con:
        rows = con.execute("SELECT * FROM revenues ORDER BY period DESC, id DESC").fetchall()
    return render_template("reports.html", summary=summary, rows=rows)

@app.route("/laporan/csv")
@login_required
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Kategori", "Uraian", "Periode", "Target (Rp)", "Realisasi (Rp)", "Lokasi", "Catatan"])
    with db() as con:
        rows = con.execute("SELECT category,description,period,target,realization,location,notes FROM revenues ORDER BY period DESC").fetchall()
    for row in rows:
        writer.writerow(list(row))
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=laporan_pad_okus.csv"})

@app.route("/pengguna", methods=["GET", "POST"])
@login_required
def users():
    if session["user"]["role"] != "Administrator":
        flash("Halaman pengguna hanya tersedia untuk Administrator.")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name, email, role = request.form.get("name","").strip(), request.form.get("email","").strip().lower(), request.form.get("role","Petugas")
        if name and email and role in ["Administrator", "Petugas", "Pimpinan"]:
            try:
                with db() as con:
                    con.execute("INSERT INTO users(name,email,role) VALUES(?,?,?)", (name,email,role))
                flash("Pengguna berhasil ditambahkan.")
            except sqlite3.IntegrityError:
                flash("Email tersebut sudah terdaftar.")
        else:
            flash("Lengkapi nama, email, dan peran.")
        return redirect(url_for("users"))
    with db() as con:
        rows = con.execute("SELECT * FROM users ORDER BY id").fetchall()
    return render_template("users.html", rows=rows)

@app.route("/pengaturan")
@login_required
def settings():
    return render_template("settings.html")

@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
