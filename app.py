from flask import Flask, jsonify, render_template, request
import requests
import configparser
from datetime import datetime, timezone
import os
import json
from supabase import create_client, Client
from dotenv import load_dotenv

# Load .env
load_dotenv()

app = Flask(__name__)


# ====== Konfigurasi ======
config = configparser.ConfigParser()
config.read('config.ini')
API_KEY = config['DEFAULT']['API_KEY']
BASE_URL = 'https://smshub.org/stubs/handler_api.php'

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Set SUPABASE_URL & SUPABASE_KEY di environment/.env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Layanan & Negara (fallback jika static/countries.json tidak ada)
SERVICES = {
    "go": "Google",
    "ni": "Gojek",
    "wa": "WhatsApp",
    "bnu": "Qpon",
    "tg": "Telegram",
    "eh": "Telegram 2.0",
    "ot": "Any Other"
}

COUNTRIES_FILE = os.path.join('static', 'countries.json')
if os.path.exists(COUNTRIES_FILE):
    with open(COUNTRIES_FILE, 'r') as f:
        COUNTRIES = json.load(f)
else:
    COUNTRIES = {
        "6": "Indonesia",
        "0": "Russia",
        "3": "China",
        "4": "Philippines",
        "10": "Vietnam"
    }
    print("Warning: countries.json not found, using fallback.")

TERMINAL_STATUSES = {'CANCELED', 'TIMEOUT', 'DELETED', 'COMPLETED'}

# ====== Utils ======
def now_iso():
    # UTC untuk konsisten dengan timestamptz
    return datetime.now(timezone.utc).isoformat()

def get_smshub_data(action, params=None):
    try:
        params = params or {}
        params.update({'api_key': API_KEY, 'action': action})
        response = requests.get(BASE_URL, params=params, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"API Error: {str(e)}")
        return None

def get_prices(service, country):
    """Ambil daftar harga dari SMSHub"""
    try:
        response = get_smshub_data('getPrices', {'service': service, 'country': country, 'currency': '643'})
        if response:
            data = json.loads(response)
            key = str(country)
            if key in data and service in data[key]:
                prices = data[key][service]
                return sorted([float(price) for price in prices.keys() if prices[price] > 0])
        return []
    except Exception as e:
        print(f"Error getting prices: {str(e)}")
        return []

# ====== Data Access (Supabase) ======
def db_insert_order(order: dict):
    supabase.table('orders').upsert(order, on_conflict='id').execute()

def db_update_order(order_id: str, updates: dict):
    updates = {**updates, 'updated_at': now_iso()}
    if 'status' in updates and str(updates['status']).upper() in TERMINAL_STATUSES:
        updates.setdefault('closed_at', now_iso())
    supabase.table('orders').update(updates).eq('id', order_id).execute()

def db_get_active_orders():
    res = (supabase.table('orders')
           .select('*')
           .in_('status', ['WAITING', 'COMPLETED'])
           .order('created_at', desc=True)
           .execute())
    return res.data or []

def db_get_history_orders():
    res = (supabase.table('orders')
           .select('*')
           .not_.in_('status', ['WAITING', 'COMPLETED'])
           .order('updated_at', desc=True)
           .order('created_at', desc=True)
           .execute())
    return res.data or []

# ====== Routes ======
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/history')
def history_page():
    # kalau belum punya history.html, boleh sementara return index.html
    try:
        return render_template('history.html')
    except:
        return render_template('index.html')

@app.route('/api/services')
def get_services():
    return jsonify(SERVICES)

@app.route('/api/countries')
def get_countries():
    return jsonify(COUNTRIES)

@app.route('/api/prices', methods=['POST'])
def get_available_prices():
    data = request.json
    service = data.get('service')
    country = data.get('country')
    if service not in SERVICES:
        return jsonify({'success': False, 'error': 'Invalid service'})
    if country not in COUNTRIES:
        return jsonify({'success': False, 'error': 'Invalid country'})
    prices = get_prices(service, country)
    return jsonify({'success': True, 'prices': prices})

@app.route('/api/balance')
def get_balance():
    response = get_smshub_data('getBalance')
    if response and response.startswith('ACCESS_BALANCE:'):
        return jsonify({'success': True, 'balance': response.split(':')[1]})
    return jsonify({'success': False, 'error': 'Failed to get balance'})

@app.route('/api/orders')
def get_orders():
    return jsonify({'success': True, 'orders': db_get_active_orders()})

@app.route('/api/history')
def get_history():
    return jsonify({'success': True, 'orders': db_get_history_orders()})

@app.route('/api/create', methods=['POST'])
def create_order():
    data = request.json
    service = data.get('service')
    country = data.get('country')
    max_price = data.get('maxPrice')

    if service not in SERVICES:
        return jsonify({'success': False, 'error': 'Invalid service'})
    if country not in COUNTRIES:
        return jsonify({'success': False, 'error': 'Invalid country'})

    params = {'service': service, 'country': country}
    if max_price:
        params['maxPrice'] = max_price

    response = get_smshub_data('getNumber', params)
    if response and response.startswith('ACCESS_NUMBER:'):
        _, order_id, number = response.split(':')

        prices = get_prices(service, country)
        price = float(max_price) if (max_price and prices and float(max_price) in prices) else (prices[0] if prices else 0.0)

        created_ts = now_iso()
        order = {
            'id': order_id,
            'number': number,
            'service': service,
            'service_name': SERVICES[service],
            'country': country,
            'country_name': COUNTRIES[country],
            'status': 'WAITING',
            'created_at': created_ts,
            'sms': '',
            'price': price,
            'updated_at': created_ts,
            'closed_at': None
        }
        db_insert_order(order)
        return jsonify({'success': True, 'order': order})

    return jsonify({'success': False, 'error': response or 'Failed to create order'})

@app.route('/api/status/<order_id>')
def get_status(order_id):
    response = get_smshub_data('getStatus', {'id': order_id})
    if response:
        if response.startswith('STATUS_OK:'):
            sms = response.split(':', 1)[1]
            db_update_order(order_id, {'sms': sms, 'status': 'COMPLETED'})
            return jsonify({'status': 'COMPLETED', 'sms': sms})
        return jsonify({'status': response})
    return jsonify({'status': 'UNKNOWN'})

@app.route('/api/finish/<order_id>', methods=['POST'])
def finish_order(order_id):
    response = get_smshub_data('setStatus', {'status': 6, 'id': order_id})
    if response == 'ACCESS_ACTIVATION':
        db_update_order(order_id, {'status': 'FINISHED'})
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': response or 'Unknown error'})

@app.route('/api/cancel/<order_id>', methods=['POST'])
def cancel_order(order_id):
    response = get_smshub_data('setStatus', {'status': 8, 'id': order_id})
    if response == 'ACCESS_CANCEL':
        db_update_order(order_id, {'status': 'CANCELED'})
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': response})

@app.route('/api/request_again/<order_id>', methods=['POST'])
def request_again(order_id):
    response = get_smshub_data('setStatus', {'status': 3, 'id': order_id})
    if not response:
        return jsonify({'success': False, 'error': 'No response from API'})
    resp_clean = response.strip().upper()
    if resp_clean in ('ACCESS_READY', 'ACCESS_RETRY_GET'):
        db_update_order(order_id, {'status': 'WAITING'})
        return jsonify({'success': True, 'message': resp_clean})
    return jsonify({'success': False, 'error': resp_clean})

@app.route('/api/remove_order/<order_id>', methods=['POST'])
def remove_order(order_id):
    db_update_order(order_id, {'status': 'DELETED'})
    return jsonify({'success': True})

@app.route('/api/timeout/<order_id>', methods=['POST'])
def timeout_order(order_id):
    db_update_order(order_id, {'status': 'TIMEOUT'})
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True)
