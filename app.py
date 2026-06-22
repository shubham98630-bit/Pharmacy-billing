from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
from datetime import datetime, timedelta
import uuid

app = Flask(__name__)
app.secret_key = 'super_secret_pharma_key_123'
DB_FILE = 'pharma_enterprise.db'

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_enterprise_db():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                mobile TEXT PRIMARY KEY, password TEXT, shop_name TEXT, role TEXT DEFAULT 'admin', gstin TEXT DEFAULT '19ABCDE1234F1Z5'
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, packing_desc TEXT,
                qty_per_strip INTEGER DEFAULT 10, batch TEXT NOT NULL, hsn TEXT, exp_date TEXT,
                mrp_per_strip REAL, rate_per_strip REAL, cgst REAL DEFAULT 2.5,
                sgst REAL DEFAULT 2.5, stock_strips INTEGER DEFAULT 0, stock_pieces INTEGER DEFAULT 0,
                supplier_name TEXT, product_type TEXT, min_stock INTEGER DEFAULT 5
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT, supplier_name TEXT UNIQUE NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ordered_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT, medicine_name TEXT UNIQUE NOT NULL, date_added TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invoices (
                invoice_no TEXT PRIMARY KEY, customer_name TEXT, date_time TEXT, grand_total REAL, billed_by TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS outgoing_stock (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, batch TEXT, qty_strips INTEGER, type TEXT, date_time TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS incoming_stock_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, batch TEXT, qty_strips INTEGER, supplier_name TEXT, date_time TEXT
            )
        ''')
        conn.commit()
    finally:
        conn.close()

init_enterprise_db()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mobile = request.form.get('mobile')
        password = request.form.get('password')
        conn = get_db_connection()
        try:
            user = conn.execute("SELECT * FROM users WHERE mobile = ? AND password = ?", (mobile, password)).fetchone()
            if user:
                session['user_mobile'] = user['mobile']
                session['shop_name'] = user['shop_name'] if user['shop_name'] else "MY MEDICAL SHOP"
                session['gstin'] = user['gstin'] if user['gstin'] else "19ABCDE1234F1Z5"
                return redirect(url_for('index'))
            return render_template('login.html', error="Invalid Credentials!")
        finally:
            conn.close()
    return render_template('login.html')

@app.route('/guest_login')
def guest_login():
    session['user_mobile'] = "GUEST_USER"
    session['shop_name'] = "GUEST MEDICAL SHOP"
    session['gstin'] = "19ABCDE1234F1Z5"
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user_mobile' not in session: return redirect(url_for('login'))
    return render_template('billing.html', date=datetime.now().strftime('%d/%m/%Y'), shop_name=session.get('shop_name', 'MY MEDICAL SHOP'), gstin=session.get('gstin', '19ABCDE1234F1Z5'))

@app.route('/update_profile', methods=['POST'])
def update_profile():
    data = request.json
    shop_name = data.get('shop_name', '').upper().strip()
    gstin = data.get('gstin', '').upper().strip()
    session['shop_name'] = shop_name
    session['gstin'] = gstin
    if session.get('user_mobile') != "GUEST_USER":
        conn = get_db_connection()
        try:
            conn.execute("UPDATE users SET shop_name = ?, gstin = ? WHERE mobile = ?", (shop_name, gstin, session['user_mobile']))
            conn.commit()
        finally:
            conn.close()
    return jsonify({"status": "success", "message": "Profile updated!"})

@app.route('/get_suppliers', methods=['GET'])
def get_suppliers():
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT * FROM suppliers ORDER BY supplier_name ASC").fetchall()
        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()

@app.route('/add_standalone_supplier', methods=['POST'])
def add_standalone_supplier():
    supplier_name = request.json.get('supplier_name', '').upper().strip()
    if not supplier_name: return jsonify({"status": "error", "message": "Supplier name cannot be empty!"}), 400
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO suppliers (supplier_name) VALUES (?)", (supplier_name,))
        conn.commit()
        return jsonify({"status": "success", "message": f"Supplier '{supplier_name}' saved successfully!"})
    except sqlite3.IntegrityError:
        return jsonify({"status": "error", "message": "Supplier name already exists!"}), 400
    finally:
        conn.close()

@app.route('/delete_supplier', methods=['POST'])
def delete_supplier():
    sup_id = request.json.get('id')
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM suppliers WHERE id = ?", (sup_id,))
        conn.commit()
        return jsonify({"status": "success", "message": "Supplier removed successfully!"})
    finally:
        conn.close()

@app.route('/get_custom_order_requests', methods=['GET'])
def get_custom_order_requests():
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT * FROM ordered_requests ORDER BY date_added DESC").fetchall()
        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()

@app.route('/add_custom_order_request', methods=['POST'])
def add_custom_order_request():
    med_name = request.json.get('medicine_name', '').upper().strip()
    if not med_name: return jsonify({"status": "error", "message": "Name cannot be blank"}), 400
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        conn = get_db_connection()
        conn.execute("INSERT INTO ordered_requests (medicine_name, date_added) VALUES (?, ?)", (med_name, now_str))
        conn.commit()
        return jsonify({"status": "success", "message": f"Medicine '{med_name}' added to Order Request List!"})
    except sqlite3.IntegrityError:
        return jsonify({"status": "error", "message": "Already added to the Order Book list!"}), 400
    finally:
        conn.close()

@app.route('/remove_custom_order_request', methods=['POST'])
def remove_custom_order_request():
    req_id = request.json.get('id')
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM ordered_requests WHERE id = ?", (req_id,))
        conn.commit()
        return jsonify({"status": "success", "message": "Request item removed!"})
    finally:
        conn.close()

@app.route('/search_supplier', methods=['GET'])
def search_supplier():
    query = request.args.get('q', '')
    conn = get_db_connection()
    try:
        suppliers = conn.execute("SELECT DISTINCT supplier_name FROM suppliers WHERE supplier_name LIKE ?", ('%' + query + '%',)).fetchall()
        return jsonify([dict(row) for row in suppliers])
    finally:
        conn.close()

@app.route('/search_product', methods=['GET'])
def search_product():
    query = request.args.get('q', '')
    conn = get_db_connection()
    try:
        products = conn.execute('''
            SELECT i.*, (SELECT SUM(stock_strips) FROM inventory WHERE name = i.name) as total_medicine_stock 
            FROM inventory i WHERE name LIKE ? AND name != '' GROUP BY name, batch
        ''', ('%' + query + '%',)).fetchall()
        return jsonify([dict(ix) for ix in products])
    finally:
        conn.close()

@app.route('/search_product_type', methods=['GET'])
def search_product_type():
    query = request.args.get('q', '')
    conn = get_db_connection()
    try:
        types = conn.execute("SELECT DISTINCT product_type FROM inventory WHERE product_type LIKE ? AND product_type IS NOT NULL AND product_type != ''", ('%' + query + '%',)).fetchall()
        return jsonify([dict(row) for row in types])
    finally:
        conn.close()

@app.route('/get_all_stock', methods=['GET'])
def get_all_stock():
    conn = get_db_connection()
    try:
        unique_medicines = conn.execute('''
            SELECT name, MAX(rate_per_strip) as rate_per_strip, MAX(min_stock) as min_stock, SUM(stock_strips) as total_medicine_stock 
            FROM inventory WHERE name != '' GROUP BY name ORDER BY name ASC
        ''').fetchall()
        
        result_list = []
        for med in unique_medicines:
            med_dict = dict(med)
            batches = conn.execute('''
                SELECT batch, stock_strips, exp_date, supplier_name, product_type 
                FROM inventory WHERE name = ? ORDER BY exp_date ASC
            ''', (med['name'],)).fetchall()
            med_dict['batch_details'] = [dict(b) for b in batches]
            result_list.append(med_dict)
            
        return jsonify(result_list)
    finally:
        conn.close()

@app.route('/add_stock', methods=['POST'])
def add_stock():
    data = request.json
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        name_upper = data['name'].upper().strip()
        batch_upper = data['batch'].upper().strip()
        supplier_upper = data['supplier_name'].upper().strip()
        type_upper = data['product_type'].upper().strip()
        incoming_qty = int(data['strips'] if data['strips'] else 0)
        qty_per = int(data['qty_per_strip'] if data['qty_per_strip'] else 10)
        min_stock = int(data['min_stock'] if data['min_stock'] else 5)
        
        if supplier_upper:
            cursor.execute("INSERT OR IGNORE INTO suppliers (supplier_name) VALUES (?)", (supplier_upper,))
            
        cursor.execute("UPDATE inventory SET min_stock = ? WHERE name = ?", (min_stock, name_upper))
            
        existing = cursor.execute("SELECT id FROM inventory WHERE name = ? AND batch = ?", (name_upper, batch_upper)).fetchone()
        if existing:
            cursor.execute('UPDATE inventory SET stock_strips = stock_strips + ?, supplier_name = ?, product_type = ?, min_stock = ? WHERE id = ?', (incoming_qty, supplier_upper, type_upper, min_stock, existing['id']))
        else:
            cursor.execute('''
                INSERT INTO inventory (name, packing_desc, qty_per_strip, batch, hsn, exp_date, mrp_per_strip, rate_per_strip, stock_strips, stock_pieces, supplier_name, product_type, min_stock)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            ''', (name_upper, data['packing'], qty_per, batch_upper, data['hsn'], data['exp_date'], float(data['mrp']), float(data['rate']), incoming_qty, supplier_upper, type_upper, min_stock))
        
        cursor.execute("DELETE FROM ordered_requests WHERE medicine_name = ?", (name_upper,))
        cursor.execute("INSERT INTO incoming_stock_logs (name, batch, qty_strips, supplier_name, date_time) VALUES (?, ?, ?, ?, ?)", (name_upper, batch_upper, incoming_qty, supplier_upper, now_str))
        conn.commit()
        return jsonify({"status": "success", "message": "Stock Added Successfully!"})
    except Exception as e: 
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@app.route('/quick_stock_out', methods=['POST'])
def quick_stock_out():
    data = request.json
    items = data.get('items', [])
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for item in items:
            prod = cursor.execute("SELECT * FROM inventory WHERE name = ? AND batch = ?", (item['name'], item['batch'])).fetchone()
            if not prod or prod['stock_strips'] < int(item['qty']): return jsonify({"status": "error", "message": f"{item['name']}-Insufficient Stock!"}), 400
            cursor.execute("UPDATE inventory SET stock_strips = stock_strips - ? WHERE id = ?", (int(item['qty']), prod['id']))
            cursor.execute("INSERT INTO outgoing_stock (name, batch, qty_strips, type, date_time) VALUES (?, ?, ?, ?, ?)", (item['name'], item['batch'], int(item['qty']), 'Running Customer', now_str))
        conn.commit()
        return jsonify({"status": "success", "message": "Stock updated successfully!"})
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500
    finally: conn.close()

@app.route('/submit_invoice', methods=['POST'])
def submit_invoice():
    data = request.json
    items = data.get('items', [])
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        inv_no = "INV-" + datetime.now().strftime('%Y%M%S') + "-" + str(uuid.uuid4().hex[:4]).upper()
        grand_total = 0
        for item in items:
            prod = cursor.execute("SELECT * FROM inventory WHERE name = ? AND batch = ?", (item['name'], item['batch'])).fetchone()
            if int(item['sell_strips']) > prod['stock_strips']: return jsonify({"status": "error", "message": "Out of Stock!"}), 400
            cursor.execute("UPDATE inventory SET stock_strips = stock_strips - ? WHERE id = ?", (int(item['sell_strips']), prod['id']))
            cursor.execute("INSERT INTO outgoing_stock (name, batch, qty_strips, type, date_time) VALUES (?, ?, ?, ?, ?)", (item['name'], item['batch'], int(item['sell_strips']), f'Billed ({inv_no})', now_str))
            grand_total += float(item['net_total'])
        cursor.execute("INSERT INTO invoices VALUES (?, ?, ?, ?, ?)", (inv_no, data.get('customer_name'), now_str, round(grand_total), session.get('user_mobile')))
        conn.commit()
        return jsonify({"status": "success", "invoice_no": inv_no})
    except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500
    finally: conn.close()

def parse_filter_to_date(filter_type):
    now = datetime.now()
    if filter_type == '5month': return now - timedelta(days=5*30)
    elif filter_type == '1year': return now - timedelta(days=365)
    elif filter_type == '5year': return now - timedelta(days=5*365)
    return now - timedelta(days=30)

@app.route('/get_bill_history', methods=['GET'])
def get_bill_history():
    target_str = parse_filter_to_date(request.args.get('filter', '1month')).strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db_connection()
    try:
        bills = conn.execute("SELECT * FROM invoices WHERE date_time >= ? ORDER BY date_time DESC", (target_str,)).fetchall()
        return jsonify([dict(b) for b in bills])
    finally:
        conn.close()

@app.route('/get_outgoing_stock', methods=['GET'])
def get_outgoing_stock():
    target_str = parse_filter_to_date(request.args.get('filter', '1month')).strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db_connection()
    try:
        logs = conn.execute("SELECT * FROM outgoing_stock WHERE date_time >= ? ORDER BY date_time DESC", (target_str,)).fetchall()
        return jsonify([dict(l) for l in logs])
    finally:
        conn.close()

@app.route('/get_incoming_stock_history', methods=['GET'])
def get_incoming_stock_history():
    target_str = parse_filter_to_date(request.args.get('filter', '1month')).strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db_connection()
    try:
        logs = conn.execute("SELECT * FROM incoming_stock_logs WHERE date_time >= ? ORDER BY date_time DESC", (target_str,)).fetchall()
        return jsonify([dict(l) for l in logs])
    finally:
        conn.close()
import os

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
    
