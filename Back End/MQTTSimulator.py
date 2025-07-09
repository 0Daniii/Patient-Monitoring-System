import time
import json
import random
import os
import paho.mqtt.client as mqtt
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment variables from docker-compose.yml or .env
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
NUM_PATIENTS = int(os.getenv("NUM_PATIENTS", "5"))
PUBLISH_INTERVAL = int(os.getenv("PUBLISH_INTERVAL", "5"))  # seconds

# Authentication settings
AUTH_SERVER_URL = os.getenv("AUTH_SERVER_URL", "http://localhost:8888/realms/pmb")
TOKEN_ENDPOINT = os.getenv("TOKEN_ENDPOINT", f"{AUTH_SERVER_URL}/protocol/openid-connect/token")
CLIENT_ID = os.getenv("MQTT_SIMULATOR_CLIENT_ID", "patient-monitor-mqtt")
CLIENT_SECRET = os.getenv("MQTT_SIMULATOR_CLIENT_SECRET", "fbLqxUc4I2zWD2yAo8e1MkmnUXARnxHw")
TOKEN_REFRESH_INTERVAL = 600  # 10 minutes

# Global token storage
current_token = None
token_expiry = 0

def get_token():
    """
    Get a new access token using the client credentials flow
    """
    global current_token, token_expiry
    
    # Check if we have a valid token already
    if current_token and time.time() < token_expiry - 60:  # 1 minute buffer
        return current_token
    
    # Get a new token
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "audience": os.getenv("API_AUDIENCE", "https://patientmonitor.api"),
        "scope": "mqtt:publish write:vitals"
    }
    
    try:
        print(f"🔑 Requesting token for client {CLIENT_ID}")
        print(f"🔗 Token endpoint: {TOKEN_ENDPOINT}")
        
        response = requests.post(TOKEN_ENDPOINT, data=payload)
        if response.status_code != 200:
            print(f"❌ Token request failed: {response.status_code} {response.text}")
            return None
            
        response.raise_for_status()
        
        token_data = response.json()
        current_token = token_data["access_token"]
        token_expiry = time.time() + token_data["expires_in"]
        
        print(f"✅ Obtained new access token, expires in {token_data['expires_in']} seconds")
        return current_token
    except Exception as e:
        print(f"❌ Failed to get token: {e}")
        # In case of failure, return the current token (might be expired)
        # or None if we don't have one
        return current_token

def connect_with_retries(client, broker, port, max_retries=10, delay=5):
    """
    Connect to the MQTT broker with retries.
    """
    for attempt in range(max_retries):
        try:
            print(f"🚀 Attempting to connect to MQTT broker at {broker}:{port}...")
            
            # Try to get a token for authentication
            token = get_token()
            if token:
                # Set username to 'token' and password to the JWT
                client.username_pw_set("token", password=token)
                print("✅ Using OAuth token for MQTT authentication")
            else:
                print("⚠️ No token available, connecting without authentication")
                # Try anonymous connection as fallback
            
            client.connect(broker, port)
            print(f"✅ Connected to MQTT broker at {broker}:{port}")
            return True
        except Exception as e:
            print(f"❌ Connection failed: {e}. Retrying in {delay} seconds... (Attempt {attempt+1}/{max_retries})")
            time.sleep(delay)
            
    print("❌ Failed to connect to MQTT broker after several attempts.")
    return False

def publish_vitals(client):
    """
    Publish simulated vitals for multiple patients.
    """
    last_token_refresh = time.time()
    
    while True:
        # Check if we need to refresh the token
        if time.time() - last_token_refresh > TOKEN_REFRESH_INTERVAL:
            token = get_token()
            if token:
                # Update the client's credentials with the new token
                client.username_pw_set("token", password=token)
                print("✅ Refreshed MQTT authentication token")
            last_token_refresh = time.time()
        
        for patient_id in range(1, NUM_PATIENTS + 1):
            # Generate random vitals with some clinical awareness
            # Normal ranges with occasional out-of-range values
            
            # Heart rate (pulse) - normal 60-100
            if random.random() < 0.9:  # 90% of the time in normal range
                pulse = random.randint(60, 100)
            else:  # 10% abnormal
                pulse = random.choice([random.randint(40, 59), random.randint(101, 140)])
                
            # SpO2 - normal 95-100%
            if random.random() < 0.9:  # 90% normal
                spo2 = random.randint(95, 100)
            else:  # 10% abnormal
                spo2 = random.randint(85, 94)
                
            # Blood pressure - normal sys: 90-120, dia: 60-80
            if random.random() < 0.9:  # 90% normal
                bp_sys = random.randint(90, 120)
                bp_dia = random.randint(60, 80)
            else:  # 10% abnormal
                if random.random() < 0.5:  # High BP
                    bp_sys = random.randint(121, 160)
                    bp_dia = random.randint(81, 100)
                else:  # Low BP
                    bp_sys = random.randint(70, 89)
                    bp_dia = random.randint(40, 59)
            
            # Temperature (36.5-37.5°C normal)
            if random.random() < 0.9:  # 90% normal
                temp = round(random.uniform(36.5, 37.5), 1)
            else:  # 10% abnormal
                temp = round(random.uniform(37.6, 39.5), 1)
            
            # Create payload with vitals data
            vitals_data = {
                "patient_id": patient_id,
                "pulse": pulse,
                "spo2": spo2,
                "bp_systolic": bp_sys,
                "bp_diastolic": bp_dia,
                "temperature": temp,
                "timestamp": time.time()
            }
            
            # Publish to MQTT topic
            topic = f"devices/patient{patient_id}/vitals"
            
            try:
                client.publish(topic, json.dumps(vitals_data))
                print(f"📤 Published to {topic}: {vitals_data}")
            except Exception as e:
                print(f"❌ Failed to publish: {e}")
        
        time.sleep(PUBLISH_INTERVAL)

def on_connect(client, userdata, flags, rc, properties=None):
    """Callback when connected (or failed to connect) to the MQTT broker"""
    if rc == 0:
        print("✅ MQTT client connected successfully")
    else:
        print(f"❌ MQTT connection failed with code {rc}")
        # Common MQTT connection error codes:
        # 1: Incorrect protocol version
        # 2: Invalid client identifier
        # 3: Server unavailable
        # 4: Bad username or password (token)
        # 5: Not authorized

if __name__ == "__main__":
    print("🏥 Starting Patient Vitals Simulator")
    print(f"🔧 Configuration:")
    print(f"  - MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"  - Patients: {NUM_PATIENTS}")
    print(f"  - Publish interval: {PUBLISH_INTERVAL} seconds")
    print(f"  - Auth server: {AUTH_SERVER_URL}")
    
    # Create MQTT client
    client = mqtt.Client(client_id=f"vitals-simulator-{random.randint(1000, 9999)}")
    client.on_connect = on_connect
    
    # Connect to MQTT broker with retries
    if connect_with_retries(client, MQTT_BROKER, MQTT_PORT):
        # Start publishing vitals
        try:
            publish_vitals(client)
        except KeyboardInterrupt:
            print("🛑 Simulator stopped by user")
        except Exception as e:
            print(f"❌ Error in simulator: {e}")
        finally:
            print("👋 Disconnecting from MQTT broker")
            client.disconnect()
    else:
        print("🛑 Exiting because MQTT connection could not be established")