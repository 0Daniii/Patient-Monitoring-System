# DeviceAPI.py V7
import json
import threading
import paho.mqtt.client as mqtt
import os
import time
import json
import signal
import sys

from Blockchain import Blockchain
from flask import Blueprint, request, jsonify, g
from Database.DatabaseAppPMB import get_db
from Broadcaster import broadcaster
from flask import jsonify
from dotenv import load_dotenv
load_dotenv()

# Import auth modules
from auth import require_auth, require_scope, verify_token
from mqtt_auth import start_mqtt_with_auth, on_mqtt_connect_auth

device_bp = Blueprint('device_api', __name__)

# Setup blockchain
blockchain = None

# Define path to backup file
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backup_path = os.path.join(base_dir, 'Database', 'blockchain_backup.json')

# Try to restore blockchain
if os.path.exists(backup_path):
    print("🔄 Blockchain backup found, loading from file...")
    with open(backup_path, 'r') as f:
        data = json.load(f)

    # Rebuild chain
    blockchain = Blockchain()
    blockchain.chain = []

    for block_data in data:
        # Recreate each Block manually
        from Blockchain import Block
        block = Block(
            index=block_data['index'],
            timestamp=block_data['timestamp'],
            data=block_data['data'],
            previous_hash=block_data['previous_hash']
        )
        block.hash = block_data['hash']
        blockchain.chain.append(block)

    print(f"✅ Blockchain restored with {len(blockchain.chain)} blocks!")
else:
    print("🚀 No blockchain backup found, creating new blockchain...")
    blockchain = Blockchain()

def graceful_shutdown(signal, frame):
    print("🛑 Caught shutdown signal! Saving blockchain to file...")
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backup_path = os.path.join(base_dir, 'Database', 'blockchain_backup.json')
    with open(backup_path, 'w') as f:
        json.dump(blockchain.to_dict(), f, indent=4)
    print("✅ Blockchain saved successfully. Exiting now.")
    sys.exit(0)

# Attach the signal handler
signal.signal(signal.SIGINT, graceful_shutdown)


@device_bp.route('/fhir', methods=['POST'])
@require_auth  # Add authentication requirement
@require_scope('write:vitals')  # Add scope requirement
def ingest_fhir_observation():
    """API endpoint to accept FHIR Observation resources with auth"""
    obs = request.get_json()
    pid = int(obs['subject']['reference'].split('/')[-1])
    pulse = obs['pulse']
    spo2 = obs['spo2']
    bp_str = obs['bp']
    
    # Add user ID to the blockchain record for audit trail
    user_id = g.user.get('sub', 'unknown')
    client_id = g.user.get('azp', 'unknown')
    
    _store_and_emit(pid, pulse, spo2, bp_str, user_id, client_id)
    return jsonify(status="ok"), 201

# MQTT setup
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = 'devices/+/vitals'
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "pmb-app")
MQTT_CLIENT_SECRET = os.getenv("MQTT_CLIENT_SECRET", "your-client-secret")

def _on_connect(client, userdata, flags, rc):
    """Callback when MQTT connects successfully"""
    if rc == 0:
        print(f"✅ MQTT connected, subscribing to {MQTT_TOPIC}")
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"❌ MQTT connection failed with code {rc}")

def _on_message(client, userdata, msg):
    """Callback for received MQTT messages with token validation"""
    # Extract the topic to determine device ID for validation
    topic_parts = msg.topic.split('/')
    if len(topic_parts) < 3:
        print(f"❌ Invalid MQTT topic format: {msg.topic}")
        return
    
    device_id = topic_parts[1].replace('patient', '')
    
    text = msg.payload.decode()
    print(f"🛰️ MQTT msg on {msg.topic}: {text}")
    
    try:
        # Parse the payload containing the data and the token
        full_payload = json.loads(text)
        
        # Extract the actual payload and the JWT token
        # Check if this is a new-style authenticated message
        if isinstance(full_payload, dict) and 'data' in full_payload and 'token' in full_payload:
            # Authenticate the message
            token = full_payload['token']
            payload = full_payload['data']
            
            # Verify token
            token_payload = verify_token(token)
            if not token_payload:
                print(f"❌ Invalid token in MQTT message: {msg.topic}")
                return
                
            # Check token scopes
            scopes = token_payload.get('scope', '').split()
            if not any(scope in scopes for scope in ['write:vitals', 'mqtt:publish']):
                print(f"❌ Token missing required scope for MQTT publish")
                return
                
            # Capture the authenticated user/client ID
            user_id = token_payload.get('sub', 'unknown')
            client_id = token_payload.get('azp', 'unknown')
        else:
            # For backward compatibility - but log a warning
            print("⚠️ Warning: Unauthenticated MQTT message received")
            payload = full_payload
            user_id = 'legacy'
            client_id = 'legacy'
        
        print(f"✅ Parsed payload: {payload}")
        
        _store_and_emit(
            payload['patient_id'],
            payload['pulse'],
            payload['spo2'],
            payload['bp'],
            user_id,
            client_id
        )
    except Exception as e:
        print(f"❌ MQTT error: {e}")

def start_mqtt():
    """Start MQTT client with authentication"""
    try:
        # Get a token for the MQTT client using Client Credentials flow
        from auth import get_client_credentials_token
        mqtt_token, error = get_client_credentials_token(
            MQTT_CLIENT_ID, 
            MQTT_CLIENT_SECRET,
            "mqtt:subscribe mqtt:publish read:vitals write:vitals"
        )
        
        if error or not mqtt_token:
            print(f"❌ Failed to get MQTT client token: {error}")
            print("⚠️ Starting MQTT without authentication for backward compatibility")
            # Fall back to unauthenticated connection
            client = mqtt.Client()
            client.on_connect = _on_connect
            client.on_message = _on_message
        else:
            print("✅ Got MQTT client token, connecting with authentication")
            # Use authenticated client
            from mqtt_auth import MQTTAuthClient
            client = MQTTAuthClient(mqtt_token)
            client.on_connect = _on_connect
            client.on_message = _on_message
    
        # Retry until broker is up
        while True:
            try:
                client.connect(MQTT_BROKER, MQTT_PORT)
                break
            except ConnectionRefusedError:
                print("❌ MQTT broker not ready, retrying in 1s…")
                time.sleep(1)
    
        threading.Thread(target=client.loop_forever, daemon=True).start()
        
    except Exception as e:
        print(f"❌ Error setting up MQTT client: {e}")
        # Continue without MQTT if it fails

def _store_and_emit(patient_id, pulse, spo2, bp_str, user_id='unknown', client_id='unknown'):
    """
    Persist into Postgres and blockchain, then broadcast via SSE.
    Now includes authenticated user and client information.
    """
    # delayed import to avoid circular dependency at module load time
    from PMBAppBackEnd import app

    # 1) push the Flask app context so get_db() (which uses flask.g) works:
    with app.app_context():
        conn = get_db()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO vitals(patient_id,pulse,bp,spo2) "
                    "VALUES (%s,%s,%s,%s) RETURNING timestamp;",
                    (patient_id, pulse, bp_str, spo2)
                )
                ts = cur.fetchone()['timestamp']

    # 2) now broadcast to any connected SSE clients
    msg = json.dumps({
        "id": patient_id,
        "pulse": pulse,
        "bp": bp_str,
        "spo2": spo2,
        "timestamp": ts.isoformat()
    })

    # 3) Add to blockchain with authentication info for audit trail
    blockchain.add_block({
        "patient_id": patient_id,
        "pulse": pulse,
        "bp": bp_str,
        "spo2": spo2,
        "timestamp": time.time(),
        "auth": {
            "user_id": user_id,
            "client_id": client_id
        }
    })
    
    print(f"✅ Block added! Current blockchain length: {len(blockchain.chain)}")
    print(f"Last block: {blockchain.chain[-1].__dict__}")

    # Save blockchain to file after every new block
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_folder = os.path.join(base_dir, "Database")
    if not os.path.exists(db_folder):
        os.makedirs(db_folder)

    # Now save blockchain correctly
    with open(os.path.join(db_folder, 'blockchain_backup.json'), 'w') as f:
        json.dump(blockchain.to_dict(), f, indent=4)
        
    print(f"📣 Broadcasting to {len(broadcaster.listeners)} client(s): {msg}")
    broadcaster.broadcast(msg)

@device_bp.route('/blockchain', methods=['GET'])
@require_auth  # Add authentication
@require_scope('read:vitals')  # Add scope requirement
def get_blockchain():
    chain_data = blockchain.to_dict()
    return jsonify(chain_data), 200

def init_app(app):
    # register the Blueprint
    app.register_blueprint(device_bp, url_prefix='/api/devices')
    # start MQTT listener once app is up
    start_mqtt()