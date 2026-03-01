import threading
import webbrowser
from flask import Flask, jsonify, request, render_template_string, send_file
from flask_sqlalchemy import SQLAlchemy
import datetime, uuid, os, io
import barcode
from barcode.writer import ImageWriter
from reportlab.pdfgen import canvas
import csv
from flask import send_file

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pallets.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ------------------ MODELY ------------------
class Pallet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    barcode = db.Column(db.String(50), unique=True, nullable=False)
    material = db.Column(db.String(50), nullable=False)
    pallet_type = db.Column(db.String(50), nullable=False)
    supplier = db.Column(db.String(50), nullable=False)
    weight = db.Column(db.Float)
    process_position = db.Column(db.String(50))
    status = db.Column(db.String(50), default="CREATED")  # CREATED, PRINTED, IN_PROCESS, PROCESSED
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    processed_at = db.Column(db.DateTime)

with app.app_context():
    db.create_all()

# ------------------ SLUŽBY ------------------
def generate_barcode_image(code):
    if not os.path.exists("barcodes"):
        os.makedirs("barcodes")
    CODE128 = barcode.get_barcode_class('code128')
    my_code = CODE128(code, writer=ImageWriter())
    filename = f"barcodes/{code}.png"
    my_code.save(filename)
    return filename

def generate_label_pdf(pallet):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(100, 800, f"Material: {pallet.material}")
    c.drawString(100, 780, f"Typ palety: {pallet.pallet_type}")
    c.drawString(100, 760, f"Dodávateľ: {pallet.supplier}")
    c.drawString(100, 740, f"Barcode: {pallet.barcode}")
    c.save()
    buffer.seek(0)
    return buffer

# ------------------ ROUTES ------------------

# Hlavná stránka
@app.route("/")
def index():
    pallets_created = Pallet.query.filter_by(status="CREATED").all()
    html = """
    <html>
    <head>
    <title>Správa paliet</title>
    <style>
    body {
        font-size: 18px;  /* základná veľkosť písma */
        font-family: Arial, sans-serif;
    }
    h2, h3 {
        font-size: 22px;  /* nadpisy väčšie */
    }
    table {
        font-size: 16px;  /* tabuľky čitateľnejšie */
    }
    input, select, button {
        font-size: 16px;  /* formuláre väčšie */
    }
    </style>
    </head>
    <body>
    <h2>Správa paliet</h2>

    <h3>Vytvoriť lejbly</h3>
    <form action="/create" method="post">
    Materiál: <select name="material">
        <option value="Cartidge">Cartidge</option>
        <option value="Bottles Bulk">Bottles Bulk</option>
        <option value="Waste">Waste</option>
        <option value="PS bottles">PS bottles</option>
    </select>
    Typ palety: <select name="pallet_type">
      <option value="EURO">EURO</option>
      <option value="BLOCK">BLOCK</option>
    </select>
    Dodávateľ: <select name="supplier">
      <option value="ECOLOGIC">ECOLOGIC</option>
      <option value="HP">HP</option>
      <option value="Xerox">Xerox</option>
    </select>
    Počet: <input type="number" name="count" value="1" min="1">
    <input type="submit" value="Vytvoriť lejbly">
    </form>

    <h3>Palety pripravené na tlač</h3>
    <form action="/print_all" method="post">
    <input type="submit" value="Tlač všetkých lejblov">
    </form>
    <h3>Správa vytvorených lejblov</h3>
    <form action="/delete_unprocessed" method="post" onsubmit="return confirm('Naozaj chcete vymazať všetky nevytlačené / nespracované palety?');">
    <input type="submit" value="Vymazať palety">
    </form>
    
    <table border=1>
    <tr><th>ID</th><th>Barcode</th><th>Material</th><th>Typ</th><th>Dodávateľ</th><th>Lejbl PDF</th></tr>
    {% for p in pallets_created %}
    <tr>
    <td>{{p.id}}</td>
    <td>{{p.barcode}}</td>
    <td>{{p.material}}</td>
    <td>{{p.pallet_type}}</td>
    <td>{{p.supplier}}</td>
    <td><a href="/label/{{p.barcode}}" target="_blank">Tlač</a></td>
    </tr>
    {% endfor %}
    </table>

    <h3>Pridávanie váhy</h3>
    <a href="/add_weight"><button>Prejsť na pridávanie váhy</button></a>

    <h3>Sprocesovanie</h3>
    <a href="/process_page"><button>Prejsť na sprocesovanie paliet</button></a>

    <h3>Report</h3>
    <a href="/report_page"><button>Prejsť na report</button></a>

    </body>
    </html>
    """
    return render_template_string(html, pallets_created=pallets_created)

# Vytváranie paliet
@app.route("/create", methods=["POST"])
def create_pallet():
    material = request.form.get("material")
    pallet_type = request.form.get("pallet_type")
    supplier = request.form.get("supplier")
    count = int(request.form.get("count",1))
    created = []
    for _ in range(count):
        code = str(uuid.uuid4())[:12]
        pallet = Pallet(barcode=code, material=material, pallet_type=pallet_type, supplier=supplier)
        db.session.add(pallet)
        db.session.commit()
        generate_barcode_image(code)
        created.append(code)
    return f"Vytvorené palety: {created} <br><a href='/'>Späť</a>"

# Tlač jedného lejbl
@app.route("/label/<barcode_value>")
def label(barcode_value):
    pallet = Pallet.query.filter_by(barcode=barcode_value).first()
    if not pallet:
        return "Paleta nenájdená"
    pallet.status = "PRINTED"
    db.session.commit()
    pdf = generate_label_pdf(pallet)
    return send_file(pdf, attachment_filename=f"{barcode_value}.pdf", as_attachment=True)

# Tlač všetkých lejblov
@app.route("/print_all", methods=["POST"])
def print_all():
    pallets_created = Pallet.query.filter_by(status="CREATED").all()
    for p in pallets_created:
        p.status = "PRINTED"
        db.session.commit()
        generate_label_pdf(p)
    return f"Všetky lejblí boli vytlačené. <br><a href='/'>Späť</a>"
# Vymazanie lejblov
@app.route("/delete_unprocessed", methods=["POST"])
def delete_unprocessed():
    # Vymaže všetky palety so stavom CREATED alebo PRINTED
    deleted_count = Pallet.query.filter(Pallet.status.in_(["CREATED", "PRINTED"])).delete(synchronize_session=False)
    db.session.commit()
    return f"Vymazaných paliet: {deleted_count} <br><a href='/'>Späť na hlavnú stránku</a>"
# Podstránka pridávanie váhy
@app.route("/add_weight")
def add_weight_page():
    pallets_printed = Pallet.query.filter_by(status="PRINTED").all()
    html = """
    <html>
    <head><title>Pridávanie váhy</title></head>
    <body>
    <h2>Pridávanie váhy</h2>
    <form action="/add_weight" method="post">
    Barcode: <input type="text" name="barcode">
    Váha: <input type="number" step="0.1" name="weight">
    Pozícia: 
    <select name="position">
    <option value="LTR1">LTR1</option>
    <option value="LTR2">LTR2</option>
    <option value="sorting">sorting</option>
    </select>
    <input type="submit" value="Aktualizovať">
    </form>
    <h3>Palety čakajúce na váhu</h3>
    <table border=1>
    <tr><th>ID</th><th>Barcode</th><th>Material</th><th>Typ</th><th>Dodávateľ</th></tr>
    {% for p in pallets_printed %}
    <tr>
    <td>{{p.id}}</td>
    <td>{{p.barcode}}</td>
    <td>{{p.material}}</td>
    <td>{{p.pallet_type}}</td>
    <td>{{p.supplier}}</td>
    </tr>
    {% endfor %}
    </table>
    <a href="/"><button>Späť na hlavnú stránku</button></a>
    </body>
    </html>
    """
    return render_template_string(html, pallets_printed=pallets_printed)

@app.route("/add_weight", methods=["POST"])
def add_weight():
    barcode_value = request.form.get("barcode")
    weight = request.form.get("weight")
    position = request.form.get("position")
    pallet = Pallet.query.filter_by(barcode=barcode_value, status="PRINTED").first()
    if not pallet:
        return f"Paleta {barcode_value} nenájdená alebo už spracovaná <br><a href='/add_weight'>Späť</a>"
    pallet.weight = float(weight) if weight else pallet.weight
    pallet.process_position = position if position else pallet.process_position
    pallet.status = "IN_PROCESS"
    db.session.commit()
    return f"Paleta {barcode_value} aktualizovaná <br><a href='/add_weight'>Späť</a>"

# Podstránka sprocesovanie paliet
@app.route("/process_page")
def process_page():
    html = """
    <html>
    <head><title>Sprocesovanie paliet</title></head>
    <body>
    <h2>Sprocesovanie paliet</h2>
    <form action="/process" method="post">
    Barcode: <input type="text" name="barcode">
    <input type="submit" value="Zobraziť a sprocesovať">
    </form>
    <a href="/"><button>Späť na hlavnú stránku</button></a>
    </body>
    </html>
    """
    return html

@app.route("/process", methods=["POST"])
def process_pallet():
    barcode_value = request.form.get("barcode")
    pallet = Pallet.query.filter_by(barcode=barcode_value, status="IN_PROCESS").first()
    if not pallet:
        return f"Paleta {barcode_value} nenájdená alebo ešte nie je v procese <br><a href='/process_page'>Späť</a>"
    html = f"""
    <html>
    <head><title>Sprocesovanie palety</title></head>
    <body>
    <h2>Paleta {pallet.barcode}</h2>
    <p>Material: {pallet.material}</p>
    <p>Typ: {pallet.pallet_type}</p>
    <p>Dodávateľ: {pallet.supplier}</p>
    <p>Váha: {pallet.weight}</p>
    <p>Pozícia: {pallet.process_position}</p>
    <form action="/mark_processed" method="post">
    <input type="hidden" name="barcode" value="{pallet.barcode}">
    <input type="submit" value="Označiť ako sprocesované">
    </form>
    <a href="/process_page"><button>Späť</button></a>
    </body>
    </html>
    """
    return html

@app.route("/mark_processed", methods=["POST"])
def mark_processed():
    barcode_value = request.form.get("barcode")
    pallet = Pallet.query.filter_by(barcode=barcode_value, status="IN_PROCESS").first()
    if not pallet:
        return f"Paleta {barcode_value} nenájdená alebo už sprocesovaná <br><a href='/process_page'>Späť</a>"
    pallet.status = "PROCESSED"
    pallet.processed_at = datetime.datetime.utcnow()
    db.session.commit()
    return f"Paleta {barcode_value} označená ako sprocesovaná <br><a href='/process_page'>Späť</a>"

# Report page s filtrami a detailom
@app.route("/report_page")
def report_page():
    supplier = request.args.get("supplier","All")
    position = request.args.get("position","All")
    
    inprocess_from = request.args.get("inprocess_from","")
    inprocess_to = request.args.get("inprocess_to","")
    
    processed_from = request.args.get("processed_from","")
    processed_to = request.args.get("processed_to","")

    # Query pre IN_PROCESS
    query_inprocess = Pallet.query.filter_by(status="IN_PROCESS")
    if supplier != "All":
        query_inprocess = query_inprocess.filter_by(supplier=supplier)
    if position != "All":
        query_inprocess = query_inprocess.filter_by(process_position=position)
    if inprocess_from:
        query_inprocess = query_inprocess.filter(Pallet.created_at >= inprocess_from)
    if inprocess_to:
        query_inprocess = query_inprocess.filter(Pallet.created_at <= inprocess_to)
    pallets_inprocess = query_inprocess.all()

    # Query pre PROCESSED
    query_processed = Pallet.query.filter_by(status="PROCESSED")
    if supplier != "All":
        query_processed = query_processed.filter_by(supplier=supplier)
    if position != "All":
        query_processed = query_processed.filter_by(process_position=position)
    if processed_from:
        query_processed = query_processed.filter(Pallet.processed_at >= processed_from)
    if processed_to:
        query_processed = query_processed.filter(Pallet.processed_at <= processed_to)
    pallets_processed = query_processed.all()

    html = """
    <html>
    <head><title>Report paliet</title></head>
    <body>
    <h2>Report paliet</h2>

    <form method="get">
        Filter podľa dodávateľa: 
        <select name="supplier" onchange="this.form.submit()">
            <option value="All" {% if supplier=="All" %}selected{% endif %}>All</option>
            <option value="ECOLOGIC" {% if supplier=="ECOLOGIC" %}selected{% endif %}>ECOLOGIC</option>
            <option value="HP" {% if supplier=="HP" %}selected{% endif %}>HP</option>
            <option value="Xerox" {% if supplier=="Xerox" %}selected{% endif %}>Xerox</option>
        </select>

        Filter podľa pracovnej pozície: 
        <select name="position" onchange="this.form.submit()">
            <option value="All" {% if position=="All" %}selected{% endif %}>All</option>
            <option value="LTR1" {% if position=="LTR1" %}selected{% endif %}>LTR1</option>
            <option value="LTR2" {% if position=="LTR2" %}selected{% endif %}>LTR2</option>
            <option value="sorting" {% if position=="sorting" %}selected{% endif %}>sorting</option>
        </select>

        <h4>Palety v procese – filter podľa dátumu vytvorenia</h4>
        Od: <input type="date" name="inprocess_from" value="{{inprocess_from}}" onchange="this.form.submit()">
        Do: <input type="date" name="inprocess_to" value="{{inprocess_to}}" onchange="this.form.submit()">

        <h4>Spracované palety – filter podľa dátumu spracovania</h4>
        Od: <input type="date" name="processed_from" value="{{processed_from}}" onchange="this.form.submit()">
        Do: <input type="date" name="processed_to" value="{{processed_to}}" onchange="this.form.submit()">
    </form>

    <h3>Palety v procese (IN_PROCESS)</h3>
    <table border=1>
    <tr><th>ID</th><th>Barcode</th><th>Material</th><th>Typ</th><th>Dodávateľ</th><th>Váha</th><th>Pozícia</th><th>Dátum vytvorenia</th></tr>
    {% for p in pallets_inprocess %}
    <tr>
    <td>{{p.id}}</td>
    <td>{{p.barcode}}</td>
    <td>{{p.material}}</td>
    <td>{{p.pallet_type}}</td>
    <td>{{p.supplier}}</td>
    <td>{{p.weight}}</td>
    <td>{{p.process_position}}</td>
    <td>{{p.created_at}}</td>
    </tr>
    {% endfor %}
    </table>

    <h3>Spracované palety (PROCESSED)</h3>
    <table border=1>
    <tr><th>ID</th><th>Barcode</th><th>Material</th><th>Typ</th><th>Dodávateľ</th><th>Váha</th><th>Pozícia</th><th>Dátum spracovania</th></tr>
    {% for p in pallets_processed %}
    <tr>
    <td>{{p.id}}</td>
    <td>{{p.barcode}}</td>
    <td>{{p.material}}</td>
    <td>{{p.pallet_type}}</td>
    <td>{{p.supplier}}</td>
    <td>{{p.weight}}</td>
    <td>{{p.process_position}}</td>
    <td>{{p.processed_at}}</td>
    </tr>
    {% endfor %}
    </table>

    <a href="/"><button>Späť na hlavnú stránku</button></a>
    </body>
    </html>
    """
    return render_template_string(html,
                                  pallets_inprocess=pallets_inprocess,
                                  pallets_processed=pallets_processed,
                                  supplier=supplier,
                                  position=position,
                                  inprocess_from=inprocess_from,
                                  inprocess_to=inprocess_to,
                                  processed_from=processed_from,
                                  processed_to=processed_to)
#--------- Čistenie databázy-------------
@app.route("/cleanup", methods=["GET", "POST"])
def cleanup():
    if request.method == "GET":
        # Zobrazenie tlačidla na stránke reportu
        html = """
        <html>
        <head><title>Údržba paliet</title></head>
        <body>
        <h2>Údržba paliet</h2>
        <p>Vymaže palety staršie ako 30 dní a uloží ich zálohu do CSV.</p>
        <form method="post">
            <input type="submit" value="Stiahnuť a vymazať staré palety">
        </form>
        <a href="/report_page"><button>Späť na report</button></a>
        </body>
        </html>
        """
        return html

    elif request.method == "POST":
        # Dátum pred 30 dňami
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=30)

        # Vybrať všetky palety staršie ako 30 dní
        old_pallets = Pallet.query.filter(
            (Pallet.status=="PROCESSED") & (Pallet.processed_at <= cutoff) |
            (Pallet.status=="IN_PROCESS") & (Pallet.created_at <= cutoff)
        ).all()

        if not old_pallets:
            return "Žiadne palety staršie ako 30 dní <br><a href='/cleanup'>Späť</a>"

        # Uloženie do CSV
        filename = f"pallets_backup_{datetime.datetime.utcnow().strftime('%Y%m%d')}.csv"
        with open(filename, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["ID","Barcode","Material","Typ","Dodávateľ","Váha","Pozícia","Status","Vytvorené","Spracované"])
            for p in old_pallets:
                writer.writerow([p.id, p.barcode, p.material, p.pallet_type, p.supplier,
                                 p.weight, p.process_position, p.status,
                                 p.created_at, p.processed_at])

        # Vymazanie z DB
        for p in old_pallets:
            db.session.delete(p)
        db.session.commit()

        return send_file(filename, as_attachment=True)
# ------------------ SPUSTENIE ------------------
def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000/")

if __name__=="__main__":
    import socket
    # Zistí lokálnu IP adresu počítača
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"Server beží na lokálnej IP: {local_ip}:5000")
    
    # Otvor prehliadač na tejto IP
    threading.Timer(1.0, lambda: webbrowser.open_new(f"http://{local_ip}:5000")).start()
    
    # Spustí Flask server pre všetky zariadenia vo Wi-Fi
    app.run(host="0.0.0.0", port=5000, debug=True)