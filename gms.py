# app.py
from flask import Flask, request, redirect, url_for, render_template_string, send_file, flash
import sqlite3, os, io
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

# Image / PDF libs
try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

try:
    import qrcode
    QRCODE_AVAILABLE = True
except Exception:
    QRCODE_AVAILABLE = False

# ---------- Config ----------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(APP_DIR, "bank_flask_singlefile.db")
LOGO_FILE = os.path.join(APP_DIR, "sbi_logo.png")   # place file here to include in PDF & header
UPI_ID = "9817179377"   # user-provided UPI

ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

# ---------- Flask setup ----------
app = Flask(__name__)
app.secret_key = "supersecret-om"  # change in production

# ---------- DB helpers ----------
def get_conn():
    c = sqlite3.connect(DB_FILE)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = get_conn()
    cur = c.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS customers(
        account_no INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        age INTEGER,
        mobile TEXT,
        pin TEXT,
        balance REAL DEFAULT 0,
        created_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions(
        trans_id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_no INTEGER,
        type TEXT,
        amount REAL,
        date TEXT,
        note TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS fds(
        fd_id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_no INTEGER,
        amount REAL,
        interest_rate REAL,
        tenure_months INTEGER,
        maturity_amount REAL,
        created_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS loans(
        loan_id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_no INTEGER,
        loan_amount REAL,
        interest_rate REAL,
        tenure_months INTEGER,
        approved INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)
    c.commit()
    c.close()

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def record_tx(account_no, ttype, amount, note=""):
    c = get_conn()
    c.execute("INSERT INTO transactions(account_no,type,amount,date,note) VALUES(?,?,?,?,?)",
              (account_no, ttype, float(amount), now_str(), note))
    c.commit()
    c.close()

# rounding helper
def fmt_amount(x):
    return float(Decimal(x).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

# initialize DB on start
init_db()

# ---------- HTML Template (single page, multiple sections via anchors) ----------
# We'll render all views within different sections of same page using anchor links and forms.
TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>OM BANK MANAGEMENT SYSTEM - SBI</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">

  <!-- Bootstrap 5 CDN -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">

  <style>
    :root{
      --primary: #1A73E8;
      --dark-primary: #0B3D91;
      --bg: #ECF3FF;
      --card: #ffffff;
      --text: #0B2545;
      --sub: #4b6b8f;
    }
    body { background: var(--bg); color: var(--text); font-family: "Segoe UI", Roboto, Arial, sans-serif; }
    .header {
      height: 88px;
      background: linear-gradient(90deg, var(--dark-primary), var(--primary));
      color: white;
      display:flex;
      align-items:center;
      padding: 0 20px;
    }
    .header img { height:64px; width:auto; margin-right:14px; }
    .header .title { font-weight:700; font-size:20px; }
    .header .subtitle { font-size:12px; color:#D7E9FF; }
    .top-buttons button { margin-left:8px; }
    .card-lift { transition: transform .12s ease, box-shadow .12s ease; }
    .card-lift:hover { transform: translateY(-6px); box-shadow: 0 12px 30px rgba(0,0,0,0.12); }
    .btn-primary-custom { background: var(--primary); border: none; }
    .btn-primary-custom:hover { background: #4C8BF5; }
    .menu { min-width: 220px; }
    .menu .list-group-item { border:none; }
    textarea[readonly] { background: #f9fbff; }
    footer { padding:10px; text-align:center; color:var(--sub); }
    .small-muted { color: var(--sub); font-size:13px; }
    .table-sm td, .table-sm th { padding: .45rem; }
  </style>
</head>
<body>

<div class="header">
  {% if logo_exists %}
    <img src="/logo" alt="logo">
  {% else %}
    <div style="font-size:34px; margin-right:12px;">🔵</div>
  {% endif %}
  <div>
    <div class="title">OM BANK MANAGEMENT SYSTEM - SBI</div>
    <div class="subtitle">Premium Banking Portal</div>
  </div>
  <div class="ms-auto top-buttons">
    <!-- quick actions -->
    <button class="btn btn-sm btn-outline-light" data-bs-toggle="modal" data-bs-target="#adminModal">Admin Login</button>
    <a href="#customer-login" class="btn btn-sm btn-outline-light">Customer Login</a>
    <a href="#atm" class="btn btn-sm btn-outline-light">ATM</a>
  </div>
</div>

<div class="container-fluid mt-4">
  <div class="row">
    <!-- Left menu -->
    <div class="col-md-3">
      <div class="card menu">
        <div class="card-body">
          <h6 class="card-title">MENU</h6>
          <div class="list-group">
            <a href="#dashboard" class="list-group-item list-group-item-action">Dashboard</a>
            <a href="#create" class="list-group-item list-group-item-action">Create Account</a>
            <a href="#deposit" class="list-group-item list-group-item-action">Deposit</a>
            <a href="#withdraw" class="list-group-item list-group-item-action">Withdraw</a>
            <a href="#fd" class="list-group-item list-group-item-action">Fixed Deposit</a>
            <a href="#loan" class="list-group-item list-group-item-action">Loan</a>
            <a href="#transactions" class="list-group-item list-group-item-action">Transactions</a>
            <a href="#exports" class="list-group-item list-group-item-action">Export / PDFs</a>
            <a href="#atm" class="list-group-item list-group-item-action">ATM</a>
          </div>
        </div>
      </div>
      <div class="small-muted mt-3">Tip: Hover cards to see lift animation. Use Admin Login to approve loans.</div>
    </div>

    <!-- Main content (single page with sections) -->
    <div class="col-md-9">
      <!-- DASHBOARD -->
      <section id="dashboard">
        <div class="d-flex justify-content-between mb-3">
          <h4>Dashboard</h4>
          <div>
            <a href="#create" class="btn btn-primary btn-primary-custom">Create Account</a>
          </div>
        </div>

        <div class="row mb-3">
          <!-- stat cards -->
          <div class="col-md-3">
            <div class="card card-lift">
              <div class="card-body">
                <small class="small-muted">Total Customers</small>
                <h5>{{ stats.customers }}</h5>
              </div>
            </div>
          </div>
          <div class="col-md-3">
            <div class="card card-lift">
              <div class="card-body">
                <small class="small-muted">Total Deposits (₹)</small>
                <h5>{{ stats.total_deposits }}</h5>
              </div>
            </div>
          </div>
          <div class="col-md-3">
            <div class="card card-lift">
              <div class="card-body">
                <small class="small-muted">Active FDs</small>
                <h5>{{ stats.fds }}</h5>
              </div>
            </div>
          </div>
          <div class="col-md-3">
            <div class="card card-lift">
              <div class="card-body">
                <small class="small-muted">Approved Loans</small>
                <h5>{{ stats.loans }}</h5>
              </div>
            </div>
          </div>
        </div>

        <!-- recent transactions -->
        <div class="card mb-3">
          <div class="card-body">
            <h5 class="card-title">Recent Transactions</h5>
            {% if recent_txs %}
              <div style="max-height:220px; overflow:auto;">
                <table class="table table-sm">
                  <thead><tr><th>Account</th><th>Type</th><th>Amount</th><th>Date</th></tr></thead>
                  <tbody>
                    {% for t in recent_txs %}
                      <tr><td>{{ t.account_no }}</td><td>{{ t.type }}</td><td>₹{{ '%.2f'|format(t.amount) }}</td><td>{{ t.date }}</td></tr>
                    {% endfor %}
                  </tbody>
                </table>
              </div>
            {% else %}
              <div class="small-muted">No transactions yet.</div>
            {% endif %}
          </div>
        </div>
      </section>

      <!-- CREATE ACCOUNT -->
      <section id="create" class="mt-4">
        <div class="card">
          <div class="card-body">
            <h5>Create Account</h5>
            <form method="post" action="/create">
              <div class="row">
                <div class="col-md-6 mb-2"><input name="name" class="form-control" placeholder="Name" required></div>
                <div class="col-md-3 mb-2"><input name="age" class="form-control" placeholder="Age" required type="number"></div>
                <div class="col-md-3 mb-2"><input name="mobile" class="form-control" placeholder="Mobile" required></div>
                <div class="col-md-4 mb-2"><input name="initial" class="form-control" placeholder="Initial Deposit" required type="number" step="0.01"></div>
                <div class="col-md-4 mb-2"><input name="pin" class="form-control" placeholder="4-digit PIN" required maxlength="6"></div>
                <div class="col-md-4 mb-2"><button class="btn btn-primary btn-primary-custom w-100">Create Account</button></div>
              </div>
            </form>
            {% if created_acc %}
              <div class="alert alert-success mt-2">Account created: <strong>{{ created_acc }}</strong></div>
            {% endif %}
          </div>
        </div>
      </section>

      <!-- DEPOSIT -->
      <section id="deposit" class="mt-4">
        <div class="card">
          <div class="card-body">
            <h5>Deposit</h5>
            <form method="post" action="/deposit">
              <div class="row">
                <div class="col-md-4 mb-2"><input name="acc" class="form-control" placeholder="Account No" required type="number"></div>
                <div class="col-md-4 mb-2"><input name="amt" class="form-control" placeholder="Amount" required type="number" step="0.01"></div>
                <div class="col-md-4 mb-2"><button class="btn btn-primary btn-primary-custom w-100">Deposit</button></div>
              </div>
            </form>
            {% if deposit_msg %}
              <div class="alert alert-info mt-2">{{ deposit_msg }}</div>
            {% endif %}
          </div>
        </div>
      </section>

      <!-- WITHDRAW -->
      <section id="withdraw" class="mt-4">
        <div class="card">
          <div class="card-body">
            <h5>Withdraw</h5>
            <form method="post" action="/withdraw">
              <div class="row">
                <div class="col-md-4 mb-2"><input name="acc" class="form-control" placeholder="Account No" required type="number"></div>
                <div class="col-md-4 mb-2"><input name="amt" class="form-control" placeholder="Amount" required type="number" step="0.01"></div>
                <div class="col-md-4 mb-2"><button class="btn btn-primary btn-primary-custom w-100">Withdraw</button></div>
              </div>
            </form>
            {% if withdraw_msg %}
              <div class="alert alert-info mt-2">{{ withdraw_msg }}</div>
            {% endif %}
          </div>
        </div>
      </section>

      <!-- FD -->
      <section id="fd" class="mt-4">
        <div class="card">
          <div class="card-body">
            <h5>Fixed Deposit</h5>
            <form method="post" action="/fd">
              <div class="row">
                <div class="col-md-3 mb-2"><input name="acc" class="form-control" placeholder="Account No" required type="number"></div>
                <div class="col-md-3 mb-2"><input name="amt" class="form-control" placeholder="Amount" required type="number" step="0.01"></div>
                <div class="col-md-3 mb-2"><input name="tenure" class="form-control" placeholder="Tenure (months)" required type="number"></div>
                <div class="col-md-3 mb-2"><button class="btn btn-primary btn-primary-custom w-100">Create FD</button></div>
              </div>
            </form>
            {% if fd_msg %}<div class="alert alert-info mt-2">{{ fd_msg }}</div>{% endif %}
          </div>
        </div>
      </section>

      <!-- LOAN -->
      <section id="loan" class="mt-4">
        <div class="card">
          <div class="card-body">
            <h5>Loan</h5>
            <form method="post" action="/loan">
              <div class="row">
                <div class="col-md-3 mb-2"><input name="acc" class="form-control" placeholder="Account No" required type="number"></div>
                <div class="col-md-3 mb-2"><input name="amt" class="form-control" placeholder="Loan Amount" required type="number" step="0.01"></div>
                <div class="col-md-3 mb-2"><input name="tenure" class="form-control" placeholder="Tenure (months)" required type="number"></div>
                <div class="col-md-3 mb-2"><button class="btn btn-primary btn-primary-custom w-100">Apply Loan</button></div>
              </div>
            </form>
            {% if loan_msg %}<div class="alert alert-info mt-2">{{ loan_msg }}</div>{% endif %}
          </div>
        </div>
      </section>

      <!-- Transactions list -->
      <section id="transactions" class="mt-4">
        <div class="card">
          <div class="card-body">
            <h5>All Transactions</h5>
            <div style="max-height:300px; overflow:auto;">
              <table class="table table-sm">
                <thead><tr><th>Date</th><th>Acc</th><th>Type</th><th>Amount</th><th>Note</th></tr></thead>
                <tbody>
                  {% for t in all_txs %}
                    <tr><td>{{ t.date }}</td><td>{{ t.account_no }}</td><td>{{ t.type }}</td><td>₹{{ '%.2f'|format(t.amount) }}</td><td>{{ t.note }}</td></tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      <!-- EXPORTS -->
      <section id="exports" class="mt-4">
        <div class="card">
          <div class="card-body">
            <h5>PDF / Export</h5>
            <form method="post" action="/export" class="row g-2">
              <div class="col-md-3"><input name="acc" class="form-control" placeholder="Account No" type="number" required></div>
              <div class="col-md-3">
                <select name="type" class="form-select">
                  <option value="account">Account Details (PDF)</option>
                  <option value="transactions">Transactions (PDF)</option>
                  <option value="fd">FDs (PDF)</option>
                  <option value="loans">Loans (PDF)</option>
                  <option value="all">All (zipped multiple)</option>
                </select>
              </div>
              <div class="col-md-3"><button class="btn btn-primary btn-primary-custom w-100">Export</button></div>
            </form>
          </div>
        </div>
      </section>

      <!-- ATM -->
      <section id="atm" class="mt-4">
        <div class="card">
          <div class="card-body">
            <h5>ATM (Simple)</h5>
            <form method="post" action="/atm_check">
              <div class="row">
                <div class="col-md-4"><input name="acc" class="form-control" placeholder="Account No" required type="number"></div>
                <div class="col-md-4"><input name="pin" class="form-control" placeholder="PIN" required type="password"></div>
                <div class="col-md-4"><button class="btn btn-primary btn-primary-custom w-100">Login ATM</button></div>
              </div>
            </form>
            {% if atm_msg %}<div class="alert alert-info mt-2">{{ atm_msg }}</div>{% endif %}
          </div>
        </div>
      </section>
      
    </div>
  </div>

  <footer class="mt-4">
    OM BANK MANAGEMENT SYSTEM — SBI • Built with Flask • UPI: {{ upi }}
  </footer>
</div>

<!-- Admin Login Modal -->
<div class="modal fade" id="adminModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog modal-sm">
    <form method="post" action="/admin_login" class="modal-content">
      <div class="modal-header"><h5 class="modal-title">Admin Login</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
      <div class="modal-body">
        <input name="user" class="form-control mb-2" placeholder="Username" required>
        <input name="pass" class="form-control mb-2" placeholder="Password" required type="password">
      </div>
      <div class="modal-footer"><button class="btn btn-primary">Login</button></div>
    </form>
  </div>
</div>

<!-- Bootstrap JS -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# ---------- Flask routes & logic ----------
@app.route("/", methods=["GET"])
def index():
    # gather stats & recent data
    c = get_conn()
    stats = {}
    stats['customers'] = c.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    td = c.execute("SELECT SUM(balance) FROM customers").fetchone()[0] or 0.0
    stats['total_deposits'] = f"{td:.2f}"
    stats['fds'] = c.execute("SELECT COUNT(*) FROM fds").fetchone()[0]
    stats['loans'] = c.execute("SELECT COUNT(*) FROM loans WHERE approved=1").fetchone()[0]
    recent_txs = c.execute("SELECT account_no,type,amount,date FROM transactions ORDER BY date DESC LIMIT 10").fetchall()
    all_txs = c.execute("SELECT date,account_no,type,amount,note FROM transactions ORDER BY date DESC LIMIT 200").fetchall()
    logo_exists = os.path.exists(LOGO_FILE)
    c.close()
    return render_template_string(TEMPLATE, stats=stats, recent_txs=recent_txs, all_txs=all_txs, logo_exists=logo_exists, upi=UPI_ID,
                                  created_acc=None, deposit_msg=None, withdraw_msg=None, fd_msg=None, loan_msg=None, atm_msg=None)

# create account
@app.route("/create", methods=["POST"])
def create():
    name = request.form.get("name","").strip()
    age = request.form.get("age","").strip()
    mobile = request.form.get("mobile","").strip()
    initial = safe_float(request.form.get("initial","0"))
    pin = request.form.get("pin","").strip()
    if not name or not age or not mobile or initial is None or not pin:
        flash("All fields required", "danger")
        return redirect(url_for("index") + "#create")
    try:
        age_int = int(age)
    except:
        flash("Age must be number", "danger")
        return redirect(url_for("index") + "#create")
    c = get_conn()
    c.execute("INSERT INTO customers(name,age,mobile,pin,balance,created_at) VALUES(?,?,?,?,?,?)",
              (name, age_int, mobile, pin, float(initial), now_str()))
    c.commit()
    acc = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    if float(initial) > 0:
        record_tx(acc, "Deposit", float(initial), note="Initial deposit")
    c.close()
    flash(f"Account created: {acc}", "success")
    return redirect(url_for("index") + "#create")

# deposit
@app.route("/deposit", methods=["POST"])
def deposit():
    acc = request.form.get("acc")
    amt = safe_float(request.form.get("amt"))
    if not acc or amt is None or amt <= 0:
        flash("Valid account & amount required", "danger")
        return redirect(url_for("index") + "#deposit")
    c = get_conn()
    cust = c.execute("SELECT balance,mobile,name FROM customers WHERE account_no=?", (acc,)).fetchone()
    if not cust:
        flash("Account not found", "danger")
        c.close()
        return redirect(url_for("index") + "#deposit")
    newbal = cust["balance"] + float(amt)
    c.execute("UPDATE customers SET balance=? WHERE account_no=?", (newbal, acc))
    c.commit(); c.close()
    record_tx(int(acc), "Deposit", float(amt))
    flash(f"Deposited ₹{float(amt):.2f}. New balance ₹{newbal:.2f}", "success")
    return redirect(url_for("index") + "#deposit")

# withdraw
@app.route("/withdraw", methods=["POST"])
def withdraw():
    acc = request.form.get("acc")
    amt = safe_float(request.form.get("amt"))
    if not acc or amt is None or amt <= 0:
        flash("Valid account & amount required", "danger")
        return redirect(url_for("index") + "#withdraw")
    c = get_conn()
    cust = c.execute("SELECT balance,mobile,name FROM customers WHERE account_no=?", (acc,)).fetchone()
    if not cust:
        flash("Account not found", "danger")
        c.close(); return redirect(url_for("index") + "#withdraw")
    if cust["balance"] < float(amt):
        flash("Insufficient balance", "danger"); c.close(); return redirect(url_for("index") + "#withdraw")
    newbal = cust["balance"] - float(amt)
    c.execute("UPDATE customers SET balance=? WHERE account_no=?", (newbal, acc)); c.commit(); c.close()
    record_tx(int(acc), "Withdraw", float(amt))
    flash(f"Withdrawn ₹{float(amt):.2f}. New balance ₹{newbal:.2f}", "success")
    return redirect(url_for("index") + "#withdraw")

# FD
@app.route("/fd", methods=["POST"])
def fd():
    acc = request.form.get("acc")
    amt = safe_float(request.form.get("amt"))
    tenure = request.form.get("tenure")
    try:
        tenure_i = int(tenure)
    except:
        flash("Invalid tenure", "danger"); return redirect(url_for("index") + "#fd")
    if not acc or amt is None or amt <= 0 or tenure_i <= 0:
        flash("Valid account, amount and tenure required", "danger"); return redirect(url_for("index") + "#fd")
    c = get_conn()
    cust = c.execute("SELECT balance,mobile,name FROM customers WHERE account_no=?", (acc,)).fetchone()
    if not cust:
        flash("Account not found", "danger"); c.close(); return redirect(url_for("index") + "#fd")
    if cust["balance"] < float(amt):
        flash("Insufficient balance", "danger"); c.close(); return redirect(url_for("index") + "#fd")
    rate = 0.055
    maturity = float(amt) + float(amt) * rate * (tenure_i / 12.0)
    c.execute("INSERT INTO fds(account_no,amount,interest_rate,tenure_months,maturity_amount,created_at) VALUES(?,?,?,?,?,?)",
              (int(acc), float(amt), rate, tenure_i, float(maturity), now_str()))
    newbal = cust["balance"] - float(amt)
    c.execute("UPDATE customers SET balance=? WHERE account_no=?", (newbal, acc))
    c.commit(); c.close()
    record_tx(int(acc), "FD_Create", float(amt), note=f"FD {tenure_i} mo")
    flash(f"FD Created. Maturity: ₹{maturity:.2f}", "success")
    return redirect(url_for("index") + "#fd")

# Loan
@app.route("/loan", methods=["POST"])
def loan():
    acc = request.form.get("acc")
    amt = safe_float(request.form.get("amt"))
    tenure = request.form.get("tenure")
    try:
        tenure_i = int(tenure)
    except:
        flash("Invalid tenure", "danger"); return redirect(url_for("index") + "#loan")
    if not acc or amt is None or amt <= 0 or tenure_i <= 0:
        flash("Valid account, amount and tenure required", "danger"); return redirect(url_for("index") + "#loan")
    c = get_conn()
    if not c.execute("SELECT 1 FROM customers WHERE account_no=?", (acc,)).fetchone():
        flash("Account not found", "danger"); c.close(); return redirect(url_for("index") + "#loan")
    rate = 0.1
    c.execute("INSERT INTO loans(account_no,loan_amount,interest_rate,tenure_months,approved,created_at) VALUES(?,?,?,?,?,?)",
              (int(acc), float(amt), rate, tenure_i, 0, now_str()))
    c.commit(); c.close()
    flash("Loan application submitted. Awaiting admin approval.", "info")
    return redirect(url_for("index") + "#loan")

# Admin login (modal)
@app.route("/admin_login", methods=["POST"])
def admin_login():
    user = request.form.get("user")
    pw = request.form.get("pass")
    if user == ADMIN_USER and pw == ADMIN_PASS:
        # show admin panel as flash messages for simplicity; in real app implement sessions
        # Approve loans page link: /admin_loans
        return redirect(url_for("admin_loans"))
    else:
        flash("Invalid admin credentials", "danger")
        return redirect(url_for("index"))

# Admin loans / approve
@app.route("/admin/loans", methods=["GET", "POST"])
def admin_loans():
    c = get_conn()
    if request.method == "POST":
        lid = request.form.get("loan_id")
        if lid:
            loan = c.execute("SELECT account_no,loan_amount FROM loans WHERE loan_id=?", (lid,)).fetchone()
            if not loan:
                flash("Loan ID not found", "danger"); c.close(); return redirect(url_for("admin_loans"))
            acc = loan["account_no"]; amt = loan["loan_amount"]
            c.execute("UPDATE loans SET approved=1 WHERE loan_id=?", (lid,))
            cur = c.execute("SELECT balance,mobile,name FROM customers WHERE account_no=?", (acc,)).fetchone()
            if cur:
                newbal = cur["balance"] + amt
                c.execute("UPDATE customers SET balance=? WHERE account_no=?", (newbal, acc))
                record_tx(acc, "LoanCredit", amt, note=f"LoanID:{lid}")
                send_sms = f"Dear {cur['name']}, loan of ₹{amt:.2f} approved and credited."
                print("[SMS]", cur["mobile"], send_sms)
            c.commit()
            flash(f"Loan {lid} approved", "success")
            c.close()
            return redirect(url_for("admin_loans"))
    loans = c.execute("SELECT loan_id,account_no,loan_amount,tenure_months,approved,created_at FROM loans ORDER BY created_at DESC").fetchall()
    c.close()
    # simple admin page single-file style
    html = """
    <h3>Admin - Loans</h3>
    <p><a href="/">Back to dashboard</a></p>
    <form method="post">
      <div>Pending loans list:</div>
      <pre>{{ loans_text }}</pre>
      <div class="mb-2"><input name="loan_id" class="form-control" placeholder="Loan ID to approve"></div>
      <button class="btn btn-primary">Approve</button>
    </form>
    """
    loans_text = "\n".join([f"LoanID:{r['loan_id']} | A/c:{r['account_no']} | ₹{r['loan_amount']:.2f} | Tenure:{r['tenure_months']} mo | Approved:{'Yes' if r['approved'] else 'No'}" for r in loans])
    return render_template_string(html, loans_text=loans_text)

# ATM check
@app.route("/atm_check", methods=["POST"])
def atm_check():
    acc = request.form.get("acc"); pin = request.form.get("pin")
    c = get_conn()
    cust = c.execute("SELECT * FROM customers WHERE account_no=?",(acc,)).fetchone()
    c.close()
    if not cust: flash("Account not found", "danger"); return redirect(url_for("index") + "#atm")
    if cust["pin"] != pin: flash("Incorrect PIN", "danger"); return redirect(url_for("index") + "#atm")
    # show simple ATM options page
    flash("ATM login success. Use the Deposit/Withdraw sections or export mini-PDF from dashboard.", "success")
    return redirect(url_for("index") + "#atm")

# Export PDFs
@app.route("/export", methods=["POST"])
def export():
    acc = request.form.get("acc")
    typ = request.form.get("type")
    if not acc:
        flash("Account required", "danger"); return redirect(url_for("index") + "#exports")
    if not REPORTLAB_AVAILABLE:
        flash("reportlab library not installed — install reportlab for PDF export", "danger"); return redirect(url_for("index") + "#exports")
    # dispatch
    if typ == "account":
        return export_account_pdf(int(acc))
    elif typ == "transactions":
        return export_transactions_pdf(int(acc))
    elif typ == "fd":
        return export_fd_pdf(int(acc))
    elif typ == "loans":
        return export_loan_pdf(int(acc))
    elif typ == "all":
        # create multiple PDFs in-memory and return a zip - to keep simple we'll return account pdf
        return export_account_pdf(int(acc))
    else:
        flash("Unknown export type", "danger"); return redirect(url_for("index") + "#exports")

# Utilities: build PDF using reportlab
def generate_qr_pil(upi):
    if not QRCODE_AVAILABLE:
        return None
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(upi)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return img

def pdf_bytes_account(customer_row):
    """Return bytes of account details PDF"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    styles = getSampleStyleSheet()
    # header table with logo (if exists) and title
    logo_rl = None
    if os.path.exists(LOGO_FILE) and PIL_AVAILABLE:
        try:
            pil = Image.open(LOGO_FILE)
            pil.thumbnail((80,80))
            bio = io.BytesIO()
            pil.save(bio, "PNG")
            bio.seek(0)
            logo_rl = RLImage(bio, width=64, height=64)
        except:
            logo_rl = None
    bank_para = Paragraph("<b>OM BANK MANAGEMENT SYSTEM - SBI</b><br/><font size=9>Official Statement</font>", styles["Heading2"])
    if logo_rl:
        header_table = Table([[logo_rl, bank_para]], colWidths=[70, 420])
    else:
        header_table = Table([[bank_para]], colWidths=[490])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1), colors.HexColor(DARK_PRIMARY)),
        ("TEXTCOLOR",(0,0),(-1,-1), colors.white),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),10),
        ("RIGHTPADDING",(0,0),(-1,-1),10),
        ("BOTTOMPADDING",(0,0),(-1,-1),10),
        ("TOPPADDING",(0,0),(-1,-1),10),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1,12))
    # customer details table
    cust = customer_row
    info = [
        ["Account No", str(cust["account_no"])],
        ["Name", cust["name"]],
        ["Mobile", cust["mobile"]],
        ["Balance", f"₹{cust['balance']:.2f}"],
        ["Created At", cust["created_at"] or ""]
    ]
    t = Table([["Field","Value"]] + info, colWidths=[120, 340])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), colors.HexColor(PRIMARY)),
        ("TEXTCOLOR",(0,0),(-1,0), colors.white),
        ("ALIGN",(0,0),(-1,-1),"LEFT"),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("GRID",(0,0),(-1,-1),0.6,colors.HexColor("#888888")),
        ("BACKGROUND",(0,1),(-1,-1), colors.whitesmoke),
    ]))
    elements.append(t)
    elements.append(Spacer(1,16))
    # QR + signature
    qr_img = generate_qr_pil(f"upi://pay?pa={UPI_ID}&pn=OM+Bank")
    if qr_img:
        bio = io.BytesIO(); qr_img.save(bio, "PNG"); bio.seek(0)
        rl_qr = RLImage(bio, width=90, height=90)
        sig_table = Table([[rl_qr, Paragraph("<b>Authorized Signature</b><br/><br/>__________________________<br/>Manager, SBI Branch", styles["Normal"])]], colWidths=[100, 360])
        sig_table.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP")]))
        elements.append(sig_table)
    else:
        elements.append(Paragraph("<b>Authorized Signature</b>", styles["Normal"]))
        elements.append(Spacer(1,40))
        elements.append(Paragraph("__________________________", styles["Normal"]))
        elements.append(Paragraph("Manager, SBI Branch", styles["Normal"]))
    # build
    doc.build(elements)
    buf.seek(0)
    return buf.getvalue()

def export_account_pdf(acc):
    c = get_conn()
    cust = c.execute("SELECT * FROM customers WHERE account_no=?", (acc,)).fetchone()
    c.close()
    if not cust:
        flash("Account not found for PDF", "danger"); return redirect(url_for("index") + "#exports")
    pdfdata = pdf_bytes_account(cust)
    return send_bytes(pdfdata, f"Account_{acc}.pdf")

def pdf_bytes_transactions(acc, only_recent=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    styles = getSampleStyleSheet()
    # header
    bank_para = Paragraph("<b>OM BANK MANAGEMENT SYSTEM - SBI</b><br/><font size=9>Transaction Statement</font>", styles["Heading2"])
    header_table = Table([[bank_para]], colWidths=[490])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1), colors.HexColor(DARK_PRIMARY)),
        ("TEXTCOLOR",(0,0),(-1,-1), colors.white),
        ("LEFTPADDING",(0,0),(-1,-1),10),
        ("RIGHTPADDING",(0,0),(-1,-1),10),
        ("BOTTOMPADDING",(0,0),(-1,-1),10),
        ("TOPPADDING",(0,0),(-1,-1),10),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1,12))
    c = get_conn()
    cust = c.execute("SELECT * FROM customers WHERE account_no=?", (acc,)).fetchone()
    rows = c.execute("SELECT date,type,amount,note FROM transactions WHERE account_no=? ORDER BY date DESC", (acc,)).fetchall()
    c.close()
    elements.append(Paragraph(f"<b>Account:</b> {cust['account_no']} &nbsp;&nbsp; <b>Name:</b> {cust['name']}", styles["Normal"]))
    elements.append(Spacer(1,8))
    # table
    table_data = [["Date","Type","Amount","Note"]]
    if only_recent:
        rows = rows[:only_recent]
    for r in rows:
        table_data.append([r["date"], r["type"], f"₹{r['amount']:.2f}", r["note"] or ""])
    t = Table(table_data, colWidths=[140,110,100,140])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), colors.HexColor(PRIMARY)),
        ("TEXTCOLOR",(0,0),(-1,0), colors.white),
        ("ALIGN",(0,0),(-1,-1),"LEFT"),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#888888")),
        ("BACKGROUND",(0,1),(-1,-1), colors.whitesmoke),
    ]))
    elements.append(t)
    elements.append(Spacer(1,14))
    # QR + signature
    qr_img = generate_qr_pil(f"upi://pay?pa={UPI_ID}&pn=OM+Bank")
    if qr_img:
        bio = io.BytesIO(); qr_img.save(bio,"PNG"); bio.seek(0)
        rl_qr = RLImage(bio, width=90, height=90)
        sig_table = Table([[rl_qr, Paragraph("<b>Authorized Signature</b><br/><br/>__________________________<br/>Manager, SBI Branch", styles["Normal"])]], colWidths=[100,360])
        elements.append(sig_table)
    else:
        elements.append(Paragraph("<b>Authorized Signature</b>", styles["Normal"]))
    doc.build(elements)
    buf.seek(0)
    return buf.getvalue()

def export_transactions_pdf(acc):
    c = get_conn()
    if not c.execute("SELECT 1 FROM customers WHERE account_no=?", (acc,)).fetchone():
        flash("Account not found", "danger"); c.close(); return redirect(url_for("index") + "#exports")
    data = pdf_bytes_transactions(acc)
    return send_bytes(data, f"Transactions_{acc}.pdf")

def pdf_bytes_fd(acc):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)
    elements = []; styles = getSampleStyleSheet()
    header_table = Table([[Paragraph("<b>OM BANK MANAGEMENT SYSTEM - SBI</b><br/><font size=9>FD Report</font>", styles["Heading2"])]], colWidths=[490])
    header_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1), colors.HexColor(DARK_PRIMARY)),("TEXTCOLOR",(0,0),(-1,-1),colors.white),("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),10)]))
    elements.append(header_table); elements.append(Spacer(1,12))
    c = get_conn()
    cust = c.execute("SELECT * FROM customers WHERE account_no=?", (acc,)).fetchone()
    rows = c.execute("SELECT fd_id,amount,interest_rate,tenure_months,maturity_amount,created_at FROM fds WHERE account_no=? ORDER BY created_at DESC", (acc,)).fetchall()
    c.close()
    elements.append(Paragraph(f"<b>Account:</b> {cust['account_no']} &nbsp;&nbsp; <b>Name:</b> {cust['name']}", styles["Normal"]))
    elements.append(Spacer(1,8))
    table_data = [["FD ID","Amount","Interest","Tenure","Maturity","Created"]]
    for r in rows:
        table_data.append([r["fd_id"], f"₹{r['amount']:.2f}", f"{r['interest_rate']*100:.2f}%", str(r["tenure_months"]), f"₹{r['maturity_amount']:.2f}", r["created_at"]])
    t = Table(table_data, colWidths=[60,80,70,70,110,100])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor(PRIMARY)),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#888888")),("BACKGROUND",(0,1),(-1,-1), colors.whitesmoke)]))
    elements.append(t)
    doc.build(elements); buf.seek(0)
    return buf.getvalue()

def export_fd_pdf(acc):
    c = get_conn()
    if not c.execute("SELECT 1 FROM customers WHERE account_no=?", (acc,)).fetchone():
        flash("Account not found", "danger"); c.close(); return redirect(url_for("index") + "#exports")
    data = pdf_bytes_fd(acc)
    return send_bytes(data, f"FDs_{acc}.pdf")

def pdf_bytes_loans(acc):
    buf = io.BytesIO(); doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)
    elements = []; styles = getSampleStyleSheet()
    header_table = Table([[Paragraph("<b>OM BANK MANAGEMENT SYSTEM - SBI</b><br/><font size=9>Loan Report</font>", styles["Heading2"])]], colWidths=[490])
    header_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1), colors.HexColor(DARK_PRIMARY)),("TEXTCOLOR",(0,0),(-1,-1),colors.white),("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),10)]))
    elements.append(header_table); elements.append(Spacer(1,12))
    c = get_conn(); cust = c.execute("SELECT * FROM customers WHERE account_no=?", (acc,)).fetchone()
    rows = c.execute("SELECT loan_id,loan_amount,interest_rate,tenure_months,approved,created_at FROM loans WHERE account_no=? ORDER BY created_at DESC", (acc,)).fetchall()
    c.close()
    elements.append(Paragraph(f"<b>Account:</b> {cust['account_no']} &nbsp;&nbsp; <b>Name:</b> {cust['name']}", styles["Normal"])); elements.append(Spacer(1,8))
    table_data = [["Loan ID","Amount","Interest","Tenure","Approved","Created"]]
    for r in rows:
        table_data.append([r["loan_id"], f"₹{r['loan_amount']:.2f}", f"{r['interest_rate']*100:.2f}%", r["tenure_months"], "Yes" if r["approved"] else "No", r["created_at"]])
    t = Table(table_data, colWidths=[60,80,70,70,60,150])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor(PRIMARY)),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#888888")),("BACKGROUND",(0,1),(-1,-1), colors.whitesmoke)]))
    elements.append(t)
    doc.build(elements); buf.seek(0)
    return buf.getvalue()

def export_loan_pdf(acc):
    c = get_conn()
    if not c.execute("SELECT 1 FROM customers WHERE account_no=?", (acc,)).fetchone():
        flash("Account not found", "danger"); c.close(); return redirect(url_for("index") + "#exports")
    data = pdf_bytes_loans(acc)
    return send_bytes(data, f"Loans_{acc}.pdf")

def send_bytes(data_bytes, filename):
    return send_file(io.BytesIO(data_bytes), mimetype="application/pdf", as_attachment=True, attachment_filename=filename)

# route to serve logo image inline
@app.route("/logo")
def logo():
    if os.path.exists(LOGO_FILE):
        return send_file(LOGO_FILE)
    else:
        return ("",204)

# ---------- Run ----------
if __name__ == "__main__":
    # create DB for demo if empty (optional)
    print("Starting OM Bank Flask app. DB:", DB_FILE)
    app.run(debug=True)
