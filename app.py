import sqlite3
import os
import io
import csv
from datetime import datetime, date
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g, send_file, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "aes-stoerung-2026-changeme")

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "stoerungen.db"))

# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db:
        db.close()

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS benutzer (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT    NOT NULL UNIQUE,
            passwort  TEXT    NOT NULL,
            rolle     TEXT    NOT NULL CHECK(rolle IN ('bereitschaft','meister','tl')),
            aktiv     INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS stoerung (
            id                INTEGER  PRIMARY KEY AUTOINCREMENT,
            nummer            TEXT     NOT NULL UNIQUE,
            aufgabenbereich   TEXT     NOT NULL,
            spez_ort          TEXT,
            datum_beginn      TEXT     NOT NULL,
            uhrzeit_beginn    TEXT,
            uhrzeit_ende      TEXT,
            meldetext         TEXT     NOT NULL,
            ursache           TEXT,
            massnahmen        TEXT,
            bemerkungen       TEXT,
            laptop_einsatz    INTEGER  NOT NULL DEFAULT 0,
            bereich_typ       TEXT     DEFAULT 'Klärwerk',
            status            TEXT     NOT NULL DEFAULT 'entwurf'
                              CHECK(status IN ('entwurf','eingereicht','freigegeben','abgelehnt')),
            erstellt_von      INTEGER  NOT NULL REFERENCES benutzer(id),
            erstellt_am       TEXT     NOT NULL,
            geaendert_am      TEXT
        );

        CREATE TABLE IF NOT EXISTS kosten (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            stoerung_id     INTEGER NOT NULL REFERENCES stoerung(id) ON DELETE CASCADE,
            verursacher     TEXT,
            kostentraeger   TEXT    DEFAULT 'AES',
            auftragsnummer  TEXT,
            weiterberechnung INTEGER NOT NULL DEFAULT 0,
            eingetragen_von INTEGER REFERENCES benutzer(id),
            eingetragen_am  TEXT
        );

        CREATE TABLE IF NOT EXISTS freigabe_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            stoerung_id INTEGER NOT NULL REFERENCES stoerung(id) ON DELETE CASCADE,
            aktion      TEXT    NOT NULL,
            von_user    INTEGER NOT NULL REFERENCES benutzer(id),
            zeitstempel TEXT    NOT NULL,
            kommentar   TEXT
        );

        CREATE TABLE IF NOT EXISTS nummer_seq (
            jahr    INTEGER PRIMARY KEY,
            letzter INTEGER NOT NULL DEFAULT 0
        );
    """)
    db.commit()
    # Sync sequence counter with highest existing number per year
    for row in db.execute("""
        SELECT substr(nummer,1,4) AS j,
               MAX(CAST(substr(nummer,6,10) AS INTEGER)) AS mx
        FROM stoerung
        WHERE length(nummer) >= 8
        GROUP BY j
    """).fetchall():
        try:
            year = int(row[0])
            mx   = int(row[1]) if row[1] else 0
            db.execute(
                "INSERT INTO nummer_seq(jahr,letzter) VALUES(?,?) "
                "ON CONFLICT(jahr) DO UPDATE SET letzter=MAX(letzter,?)",
                (year, mx, mx)
            )
        except (TypeError, ValueError):
            pass
    db.commit()

    # Seed default users if table is empty
    row = db.execute("SELECT COUNT(*) as c FROM benutzer").fetchone()
    if row["c"] == 0:
        users = [
            ("Meister",      generate_password_hash("meister123"),  "meister"),
            ("Bereitschaft", generate_password_hash("bereit123"),   "bereitschaft"),
            ("TL",           generate_password_hash("tl123"),       "tl"),
        ]
        db.executemany(
            "INSERT INTO benutzer(name,passwort,rolle) VALUES(?,?,?)", users
        )
        db.commit()

def next_nummer():
    db = get_db()
    jahr = date.today().year
    db.execute(
        "INSERT INTO nummer_seq(jahr,letzter) VALUES(?,1) ON CONFLICT(jahr) DO UPDATE SET letzter=letzter+1",
        (jahr,)
    )
    db.commit()
    row = db.execute("SELECT letzter FROM nummer_seq WHERE jahr=?", (jahr,)).fetchone()
    return f"{jahr}-{row['letzter']:03d}"

# ── Auth helpers ──────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if session.get("rolle") not in roles:
                abort(403)
            return f(*args, **kwargs)
        return login_required(wrapped)
    return decorator

def current_user():
    return {
        "id":    session.get("user_id"),
        "name":  session.get("name"),
        "rolle": session.get("rolle"),
    }

app.jinja_env.globals["current_user"] = current_user

# ── Routes: Auth ──────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        pw   = request.form.get("passwort", "")
        db   = get_db()
        user = db.execute(
            "SELECT * FROM benutzer WHERE name=? AND aktiv=1", (name,)
        ).fetchone()
        if user and check_password_hash(user["passwort"], pw):
            session.clear()
            session["user_id"] = user["id"]
            session["name"]    = user["name"]
            session["rolle"]   = user["rolle"]
            return redirect(url_for("index"))
        flash("Benutzername oder Passwort falsch.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ── Routes: Index ─────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    rolle = session.get("rolle")
    if rolle == "meister":
        return redirect(url_for("posteingang"))
    if rolle == "tl":
        return redirect(url_for("dashboard"))
    return redirect(url_for("meine_stoerungen"))

# ── Routes: Bereitschaft – eigene Meldungen ───────────────────────────────────

@app.route("/meine")
@login_required
def meine_stoerungen():
    db   = get_db()
    uid  = session["user_id"]
    rows = db.execute(
        "SELECT * FROM stoerung WHERE erstellt_von=? ORDER BY erstellt_am DESC", (uid,)
    ).fetchall()
    return render_template("meine_stoerungen.html", stoerungen=rows)

@app.route("/neu", methods=["GET", "POST"])
@login_required
def neu():
    if request.method == "POST":
        db  = get_db()
        num = next_nummer()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute("""
            INSERT INTO stoerung
              (nummer, aufgabenbereich, spez_ort, datum_beginn, uhrzeit_beginn,
               uhrzeit_ende, meldetext, ursache, massnahmen, bemerkungen,
               laptop_einsatz, bereich_typ, status, erstellt_von, erstellt_am)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            num,
            request.form["aufgabenbereich"],
            request.form.get("spez_ort", ""),
            request.form["datum_beginn"],
            request.form.get("uhrzeit_beginn", ""),
            request.form.get("uhrzeit_ende", ""),
            request.form["meldetext"],
            request.form.get("ursache", ""),
            request.form.get("massnahmen", ""),
            request.form.get("bemerkungen", ""),
            1 if request.form.get("laptop_einsatz") else 0,
            request.form.get("bereich_typ", "Klärwerk"),
            "entwurf",
            session["user_id"],
            now,
        ))
        db.commit()
        sid = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        aktion = request.form.get("aktion", "speichern")
        if aktion == "einreichen":
            return redirect(url_for("einreichen", sid=sid))
        flash(f"Störung {num} als Entwurf gespeichert.", "success")
        return redirect(url_for("meine_stoerungen"))
    return render_template("stoerung_form.html", stoerung=None, readonly=False)

@app.route("/stoerung/<int:sid>/bearbeiten", methods=["GET", "POST"])
@login_required
def bearbeiten(sid):
    db = get_db()
    s  = db.execute("SELECT * FROM stoerung WHERE id=?", (sid,)).fetchone()
    if not s:
        abort(404)
    rolle = session.get("rolle")
    if rolle == "bereitschaft" and s["erstellt_von"] != session["user_id"]:
        abort(403)
    if s["status"] not in ("entwurf", "abgelehnt") and rolle == "bereitschaft":
        flash("Eingereichte Meldungen können nicht mehr bearbeitet werden.", "error")
        return redirect(url_for("meine_stoerungen"))

    if request.method == "POST":
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute("""
            UPDATE stoerung SET
              aufgabenbereich=?, spez_ort=?, datum_beginn=?, uhrzeit_beginn=?,
              uhrzeit_ende=?, meldetext=?, ursache=?, massnahmen=?, bemerkungen=?,
              laptop_einsatz=?, bereich_typ=?, geaendert_am=?
            WHERE id=?
        """, (
            request.form["aufgabenbereich"],
            request.form.get("spez_ort", ""),
            request.form["datum_beginn"],
            request.form.get("uhrzeit_beginn", ""),
            request.form.get("uhrzeit_ende", ""),
            request.form["meldetext"],
            request.form.get("ursache", ""),
            request.form.get("massnahmen", ""),
            request.form.get("bemerkungen", ""),
            1 if request.form.get("laptop_einsatz") else 0,
            request.form.get("bereich_typ", "Klärwerk"),
            now, sid,
        ))
        if s["status"] == "abgelehnt":
            db.execute("UPDATE stoerung SET status='entwurf' WHERE id=?", (sid,))
        db.commit()
        aktion = request.form.get("aktion", "speichern")
        if aktion == "einreichen":
            return redirect(url_for("einreichen", sid=sid))
        flash("Störung aktualisiert.", "success")
        return redirect(url_for("meine_stoerungen"))

    log  = db.execute(
        "SELECT fl.*, b.name FROM freigabe_log fl JOIN benutzer b ON fl.von_user=b.id WHERE fl.stoerung_id=? ORDER BY fl.zeitstempel DESC",
        (sid,)
    ).fetchall()
    return render_template("stoerung_form.html", stoerung=s, log=log, readonly=False)

@app.route("/stoerung/<int:sid>/einreichen")
@login_required
def einreichen(sid):
    db = get_db()
    s  = db.execute("SELECT * FROM stoerung WHERE id=?", (sid,)).fetchone()
    if not s or s["status"] not in ("entwurf", "abgelehnt"):
        flash("Diese Meldung kann nicht (mehr) eingereicht werden.", "error")
        return redirect(url_for("meine_stoerungen"))
    rolle = session.get("rolle")
    if rolle == "bereitschaft" and s["erstellt_von"] != session["user_id"]:
        abort(403)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("UPDATE stoerung SET status='eingereicht', geaendert_am=? WHERE id=?", (now, sid))
    db.execute(
        "INSERT INTO freigabe_log(stoerung_id,aktion,von_user,zeitstempel) VALUES(?,?,?,?)",
        (sid, "eingereicht", session["user_id"], now)
    )
    db.commit()
    flash(f"Störung {s['nummer']} wurde eingereicht und wartet auf Meister-Freigabe.", "success")
    return redirect(url_for("meine_stoerungen"))

# ── Routes: Detail (alle Rollen) ──────────────────────────────────────────────

@app.route("/stoerung/<int:sid>")
@login_required
def detail(sid):
    db   = get_db()
    s    = db.execute(
        "SELECT s.*, b.name AS ersteller FROM stoerung s JOIN benutzer b ON s.erstellt_von=b.id WHERE s.id=?",
        (sid,)
    ).fetchone()
    if not s:
        abort(404)
    rolle = session.get("rolle")
    if rolle == "bereitschaft" and s["erstellt_von"] != session["user_id"]:
        abort(403)
    log = db.execute(
        "SELECT fl.*, b.name FROM freigabe_log fl JOIN benutzer b ON fl.von_user=b.id WHERE fl.stoerung_id=? ORDER BY fl.zeitstempel DESC",
        (sid,)
    ).fetchall()
    kosten = db.execute("SELECT * FROM kosten WHERE stoerung_id=?", (sid,)).fetchone()
    return render_template("stoerung_detail.html", s=s, log=log, kosten=kosten, readonly=True)

# ── Routes: Meister – Posteingang & Freigabe ──────────────────────────────────

@app.route("/posteingang")
@role_required("meister", "tl")
def posteingang():
    db    = get_db()
    offen = db.execute("""
        SELECT s.*, b.name AS ersteller
        FROM stoerung s JOIN benutzer b ON s.erstellt_von=b.id
        WHERE s.status='eingereicht'
        ORDER BY s.datum_beginn ASC, s.uhrzeit_beginn ASC
    """).fetchall()
    return render_template("posteingang.html", stoerungen=offen)

@app.route("/stoerung/<int:sid>/freigeben", methods=["GET","POST"])
@role_required("meister")
def freigeben(sid):
    db = get_db()
    s  = db.execute("SELECT * FROM stoerung WHERE id=?", (sid,)).fetchone()
    if not s or s["status"] != "eingereicht":
        flash("Diese Meldung kann nicht freigegeben werden.", "error")
        return redirect(url_for("posteingang"))

    if request.method == "POST":
        aktion    = request.form.get("aktion")
        kommentar = request.form.get("kommentar", "").strip()
        now       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if aktion == "freigeben":
            db.execute("UPDATE stoerung SET status='freigegeben', geaendert_am=? WHERE id=?", (now, sid))
            db.execute(
                "INSERT INTO freigabe_log(stoerung_id,aktion,von_user,zeitstempel,kommentar) VALUES(?,?,?,?,?)",
                (sid, "freigegeben", session["user_id"], now, kommentar or None)
            )
            # Kosten speichern
            vur = request.form.get("verursacher","").strip()
            kt  = request.form.get("kostentraeger","AES").strip()
            aun = request.form.get("auftragsnummer","").strip()
            wb  = 1 if request.form.get("weiterberechnung") else 0
            if any([vur, kt != "AES", aun, wb]):
                existing = db.execute("SELECT id FROM kosten WHERE stoerung_id=?", (sid,)).fetchone()
                if existing:
                    db.execute(
                        "UPDATE kosten SET verursacher=?,kostentraeger=?,auftragsnummer=?,weiterberechnung=?,eingetragen_von=?,eingetragen_am=? WHERE stoerung_id=?",
                        (vur, kt, aun, wb, session["user_id"], now, sid)
                    )
                else:
                    db.execute(
                        "INSERT INTO kosten(stoerung_id,verursacher,kostentraeger,auftragsnummer,weiterberechnung,eingetragen_von,eingetragen_am) VALUES(?,?,?,?,?,?,?)",
                        (sid, vur, kt, aun, wb, session["user_id"], now)
                    )
            db.commit()
            flash(f"Störung {s['nummer']} freigegeben.", "success")

        elif aktion == "ablehnen":
            if not kommentar:
                flash("Bitte einen Ablehnungsgrund angeben.", "error")
                log = db.execute(
                    "SELECT fl.*, b.name FROM freigabe_log fl JOIN benutzer b ON fl.von_user=b.id WHERE fl.stoerung_id=? ORDER BY fl.zeitstempel DESC",
                    (sid,)
                ).fetchall()
                return render_template("freigabe.html", s=s, log=log)
            db.execute("UPDATE stoerung SET status='abgelehnt', geaendert_am=? WHERE id=?", (now, sid))
            db.execute(
                "INSERT INTO freigabe_log(stoerung_id,aktion,von_user,zeitstempel,kommentar) VALUES(?,?,?,?,?)",
                (sid, "abgelehnt", session["user_id"], now, kommentar)
            )
            db.commit()
            flash(f"Störung {s['nummer']} abgelehnt. Bereitschaft wurde informiert.", "error")

        return redirect(url_for("posteingang"))

    log = db.execute(
        "SELECT fl.*, b.name FROM freigabe_log fl JOIN benutzer b ON fl.von_user=b.id WHERE fl.stoerung_id=? ORDER BY fl.zeitstempel DESC",
        (sid,)
    ).fetchall()
    return render_template("freigabe.html", s=s, log=log)

# ── Routes: Übersicht (alle freigegebenen) ────────────────────────────────────

@app.route("/uebersicht")
@role_required("meister", "tl")
def uebersicht():
    db = get_db()
    rows = db.execute("""
        SELECT s.*, b.name AS ersteller
        FROM stoerung s JOIN benutzer b ON s.erstellt_von=b.id
        WHERE s.status='freigegeben'
        ORDER BY s.datum_beginn DESC, s.uhrzeit_beginn DESC
    """).fetchall()
    return render_template("uebersicht.html", stoerungen=rows)

# ── Routes: Dashboard ─────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    db   = get_db()
    jahr = request.args.get("jahr", str(date.today().year))

    rows = db.execute("""
        SELECT s.*, b.name AS ersteller
        FROM stoerung s JOIN benutzer b ON s.erstellt_von=b.id
        WHERE s.status='freigegeben' AND substr(s.datum_beginn,1,4)=?
        ORDER BY s.datum_beginn ASC
    """, (jahr,)).fetchall()

    # Monatszählung
    monate = {str(m).zfill(2): 0 for m in range(1, 13)}
    laptop = 0
    vor_ort = 0
    bereiche: dict = {}
    meldungen: dict = {}

    for s in rows:
        m = s["datum_beginn"][5:7] if s["datum_beginn"] else None
        if m and m in monate:
            monate[m] += 1
        if s["laptop_einsatz"]:
            laptop += 1
        else:
            vor_ort += 1
        b = s["aufgabenbereich"] or "Unbekannt"
        bereiche[b] = bereiche.get(b, 0) + 1
        mt = (s["meldetext"] or "")[:60]
        meldungen[mt] = meldungen.get(mt, 0) + 1

    top_bereiche = sorted(bereiche.items(), key=lambda x: -x[1])[:8]
    top_meldungen = sorted(meldungen.items(), key=lambda x: -x[1])[:10]

    jahre = db.execute("""
        SELECT DISTINCT substr(datum_beginn,1,4) AS j FROM stoerung
        WHERE status='freigegeben' ORDER BY j DESC
    """).fetchall()

    return render_template("dashboard.html",
        rows=rows, jahr=jahr, jahre=jahre,
        monate=monate,
        gesamt=len(rows),
        laptop=laptop, vor_ort=vor_ort,
        top_bereiche=top_bereiche,
        top_meldungen=top_meldungen,
    )

# ── Routes: Export ────────────────────────────────────────────────────────────

@app.route("/export/csv")
@role_required("meister", "tl")
def export_csv():
    db   = get_db()
    jahr = request.args.get("jahr", str(date.today().year))
    rows = db.execute("""
        SELECT s.nummer, s.aufgabenbereich, s.spez_ort, s.datum_beginn,
               s.uhrzeit_beginn, s.uhrzeit_ende, s.meldetext, b.name AS bereitschaftler,
               CASE WHEN s.laptop_einsatz=1 THEN 'Laptop-Einsatz' ELSE 'Vor-Ort' END AS einsatzart,
               s.ursache, s.massnahmen, s.bemerkungen,
               s.bereich_typ, s.geaendert_am
        FROM stoerung s JOIN benutzer b ON s.erstellt_von=b.id
        WHERE s.status='freigegeben' AND substr(s.datum_beginn,1,4)=?
        ORDER BY s.datum_beginn ASC
    """, (jahr,)).fetchall()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Nummer","Aufgabenbereich","Spez. Ort","Datum","Beginn","Ende",
        "Meldetext","Bereitschaftler","Einsatzart","Ursache","Maßnahmen",
        "Bemerkungen","Bereich","Freigegeben am"
    ])
    for r in rows:
        writer.writerow(list(r))
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"Stoerungen_{jahr}.csv"
    )

# ── Routes: Admin (Meister) ───────────────────────────────────────────────────

@app.route("/admin/benutzer")
@role_required("meister")
def admin_benutzer():
    db    = get_db()
    users = db.execute("SELECT id,name,rolle,aktiv FROM benutzer ORDER BY rolle,name").fetchall()
    return render_template("admin_benutzer.html", users=users)

@app.route("/admin/benutzer/neu", methods=["POST"])
@role_required("meister")
def admin_benutzer_neu():
    db   = get_db()
    name = request.form["name"].strip()
    pw   = request.form["passwort"]
    roll = request.form["rolle"]
    try:
        db.execute(
            "INSERT INTO benutzer(name,passwort,rolle) VALUES(?,?,?)",
            (name, generate_password_hash(pw), roll)
        )
        db.commit()
        flash(f"Benutzer '{name}' angelegt.", "success")
    except sqlite3.IntegrityError:
        flash(f"Benutzername '{name}' existiert bereits.", "error")
    return redirect(url_for("admin_benutzer"))

@app.route("/admin/benutzer/<int:uid>/passwort", methods=["POST"])
@role_required("meister")
def admin_passwort(uid):
    db = get_db()
    pw = request.form["passwort"]
    db.execute("UPDATE benutzer SET passwort=? WHERE id=?", (generate_password_hash(pw), uid))
    db.commit()
    flash("Passwort geändert.", "success")
    return redirect(url_for("admin_benutzer"))

@app.route("/admin/benutzer/<int:uid>/toggle")
@role_required("meister")
def admin_toggle(uid):
    db = get_db()
    db.execute("UPDATE benutzer SET aktiv = 1-aktiv WHERE id=?", (uid,))
    db.commit()
    return redirect(url_for("admin_benutzer"))

# ── Eigenes Passwort ändern ───────────────────────────────────────────────────

@app.route("/passwort", methods=["GET", "POST"])
@login_required
def passwort_aendern():
    if request.method == "POST":
        db     = get_db()
        alt    = request.form["alt"]
        neu    = request.form["neu"]
        neu2   = request.form["neu2"]
        user   = db.execute("SELECT * FROM benutzer WHERE id=?", (session["user_id"],)).fetchone()
        if not check_password_hash(user["passwort"], alt):
            flash("Altes Passwort falsch.", "error")
        elif neu != neu2:
            flash("Neue Passwörter stimmen nicht überein.", "error")
        elif len(neu) < 6:
            flash("Passwort muss mindestens 6 Zeichen haben.", "error")
        else:
            db.execute("UPDATE benutzer SET passwort=? WHERE id=?",
                       (generate_password_hash(neu), session["user_id"]))
            db.commit()
            flash("Passwort erfolgreich geändert.", "success")
    return render_template("passwort.html")

# ── Context / filters ─────────────────────────────────────────────────────────

@app.template_filter("statuslabel")
def statuslabel(s):
    return {
        "entwurf":     "Entwurf",
        "eingereicht": "Eingereicht",
        "freigegeben": "Freigegeben",
        "abgelehnt":   "Abgelehnt",
    }.get(s, s)

@app.template_filter("datefmt")
def datefmt(s):
    if not s:
        return "–"
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return s

@app.context_processor
def inject_pending():
    count = 0
    if session.get("rolle") in ("meister", "tl"):
        try:
            db    = get_db()
            count = db.execute(
                "SELECT COUNT(*) AS c FROM stoerung WHERE status='eingereicht'"
            ).fetchone()["c"]
        except Exception:
            pass
    return {"pending_count": count}

# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
