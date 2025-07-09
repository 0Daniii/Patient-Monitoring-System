# PMBAppBackEnd.py
import json
import queue
import random
import threading
import time
import sys
import os
from flask import Flask, Response, render_template, request, redirect, url_for, jsonify, session
from flask_session import Session  # For server-side sessions
from dotenv import load_dotenv
import secrets
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Database.DatabaseAppPMB import get_db, close_db, init_db
from DeviceAPI import init_app
from Broadcaster import broadcaster  # the shared EventBroadcaster instance
from auth import init_auth_endpoints, require_auth, require_scope
load_dotenv()

app = Flask(__name__)

# Configure secure session
app.config.update(
    SECRET_KEY=os.getenv('SECRET_KEY', secrets.token_hex(32)),
    SESSION_TYPE='filesystem',
    SESSION_COOKIE_SECURE=os.getenv('USE_HTTPS', 'False').lower() == 'true',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=int(os.getenv('REFRESH_TOKEN_TTL', '2592000'))  # 30 days in seconds
)
Session(app)

app.teardown_appcontext(close_db)

# Add debugging route to check environment variables
@app.route('/debug/env')
def debug_env():
    if app.config.get('FLASK_ENV') != 'development':
        return jsonify({"error": "Debug endpoints only available in development"}), 403
        
    # Only return non-sensitive env vars
    safe_vars = {
        "AUTH_SERVER_URL": os.getenv("AUTH_SERVER_URL"),
        "AUTH_SERVER_URL_PUBLIC": os.getenv("AUTH_SERVER_URL_PUBLIC"),
        "REDIRECT_URI": os.getenv("REDIRECT_URI"),
        "APP_URL": os.getenv("APP_URL"),
        "FLASK_ENV": os.getenv("FLASK_ENV"),
        "API_AUDIENCE": os.getenv("API_AUDIENCE"),
        "CLIENT_ID": os.getenv("WEB_APP_CLIENT_ID")
    }
    return jsonify(safe_vars)

# 1) Initialize auth endpoints
init_auth_endpoints(app)

# 2) Register the device‐integration routes on /api/devices
init_app(app)

# 3) SSE endpoint: clients connect here to receive live JSON messages
@app.route('/stream')
@require_auth  # Require authentication for SSE stream
@require_scope('read:vitals')  # Require proper scope
def stream():
    print("🔗 /stream requested")
    q = broadcaster.listen()
    
    def event_stream():
        print("   🎧 client subscribed, starting event_stream")
        try:
            while True:
                msg = q.get()
                yield f"data: {msg}\n\n"
        finally:
            print("   🛑 client disconnected")
            with broadcaster.lock:
                if q in broadcaster.listeners:
                    broadcaster.listeners.remove(q)
    
    return Response(event_stream(),
                    content_type='text/event-stream',
                    headers={'Cache-Control': 'no-cache'})

# 4) Optional: return the full history of vitals readings
@app.route('/vitals', methods=['GET'])
@require_auth  # Require authentication
@require_scope('read:vitals')  # Require proper scope
def get_vitals():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT patient_id AS id, timestamp, pulse, bp, spo2
              FROM vitals
             ORDER BY timestamp;
        """)
        rows = cur.fetchall()
    return jsonify(rows)

# 5) Public Landing Page or Dashboard depending on login
@app.route('/')
def index():
    logged_in = 'access_token' in session
    if logged_in:
        return render_template('dashboard.html', logged_in=logged_in)
    else:
        return render_template('landing.html')

# 6) Protected Dashboard Route
@app.route('/dashboard')
def dashboard():
    logged_in = 'access_token' in session
    if logged_in:
        return render_template('dashboard.html', logged_in=True)
    else:
        return redirect(url_for('login'))

# 7) Optional Redirect Helper
@app.route('/vitals-monitor')
def vitals_monitor():
    logged_in = 'access_token' in session
    if logged_in:
        return redirect(url_for('dashboard'))
    else:
        return redirect(url_for('login'))

# 8) Simulator to generate data if no real devices are hooked up
def simulate_loop():
    from auth import get_client_credentials_token
    
    # Get client credentials token for simulator
    client_id = os.getenv("MQTT_SIMULATOR_CLIENT_ID", "patient-monitor-simulator")
    client_secret = os.getenv("MQTT_SIMULATOR_CLIENT_SECRET", "simulator-secret")
    
    token, error = get_client_credentials_token(
        client_id, 
        client_secret, 
        "mqtt:publish write:vitals"
    )
    
    if error:
        print(f"❌ Error getting simulator token: {error}")
        print("⚠️ Running simulator without authentication")
    
    with app.app_context():
        while True:
            for pid in range(1, 6):
                pulse = random.randint(60, 100)
                sys   = random.randint(110, 140)
                dia   = random.randint(70,  90)
                spo2  = random.randint(90, 100)
                bp    = f"{sys}/{dia}"
                
                # store in DB and get timestamp
                conn = get_db()
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO vitals(patient_id,pulse,bp,spo2) "
                            "VALUES (%s,%s,%s,%s) RETURNING timestamp;",
                            (pid, pulse, bp, spo2)
                        )
                        ts = cur.fetchone()['timestamp']
                
                # Store auth information for blockchain audit trail
                user_id = 'simulator'
                client_id = client_id
                
                # Add to blockchain with auth info
                from DeviceAPI import blockchain
                blockchain.add_block({
                    "patient_id": pid,
                    "pulse": pulse,
                    "bp": bp,
                    "spo2": spo2,
                    "timestamp": time.time(),
                    "auth": {
                        "user_id": user_id,
                        "client_id": client_id,
                        "token": token[:20] + "..." if token else "none"
                    }
                })
                
                # broadcast to all SSE clients
                payload = json.dumps({
                    "id":        pid,
                    "pulse":     pulse,
                    "bp":        bp,
                    "spo2":      spo2,
                    "timestamp": ts.isoformat()
                })
                broadcaster.broadcast(payload)
                time.sleep(1)

if __name__ == '__main__':
    # Initialize DB and seed patients
    with app.app_context():
        init_db()
    
    # Start simulator with random numbers (comment out if using real device ingestion only)
    # threading.Thread(target=simulate_loop, daemon=True).start()
    
    # Enable HTTPS in production
    context = None
    if os.getenv('USE_HTTPS', 'False').lower() == 'true':
        context = ('cert.pem', 'key.pem')
    
    # Run on port 8080, listening on all interfaces
    app.run(host='0.0.0.0', port=8080, ssl_context=context, debug=os.getenv('FLASK_ENV') == 'development')