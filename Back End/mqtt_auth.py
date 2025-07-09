"""
MQTT Authentication Module

This module provides JWT authentication for MQTT connections.
"""

import json
import paho.mqtt.client as mqtt
from auth import verify_token

class MQTTAuthClient(mqtt.Client):
    """
    Extended MQTT client that includes token authentication
    in the CONNECT message
    """
    def __init__(self, access_token, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.access_token = access_token
        # Set the username to 'token' and password to the JWT
        # This is a common pattern for bearer token auth in MQTT
        self.username_pw_set("token", password=access_token)
        
def on_mqtt_connect_auth(client, userdata, flags, rc, properties=None):
    """
    Authentication handler for MQTT connections
    """
    if rc == 0:
        print("✅ MQTT client connected successfully with authentication")
    else:
        print(f"❌ MQTT connection failed with code {rc}")
        # Common MQTT connection error codes:
        # 1: Incorrect protocol version
        # 2: Invalid client identifier
        # 3: Server unavailable
        # 4: Bad username or password (token)
        # 5: Not authorized

def validate_mqtt_token(client_id, username, password):
    """
    Validate the MQTT client's credentials
    
    This function would be used by the MQTT broker for authentication.
    For Mosquitto, this would be called from an auth plugin.
    
    Args:
        client_id: The MQTT client ID
        username: Should be 'token' for JWT auth
        password: The JWT access token
        
    Returns:
        bool: True if authentication successful, False otherwise
    """
    # Check if using token authentication
    if username != "token":
        print(f"❌ MQTT auth failed: Invalid username: {username}")
        return False
    
    # Verify the JWT token
    payload = verify_token(password)
    if not payload:
        print("❌ MQTT auth failed: Invalid token")
        return False
    
    # Check for MQTT permissions in scopes
    scopes = payload.get("scope", "").split()
    if not any(scope in scopes for scope in ["mqtt:publish", "mqtt:subscribe", "write:vitals"]):
        print("❌ MQTT auth failed: Missing required scope")
        return False
    
    print(f"✅ MQTT auth successful for client: {client_id}")
    return True

def start_mqtt_with_auth(broker, port, access_token, on_connect, on_message):
    """
    Start an authenticated MQTT client
    
    Args:
        broker: MQTT broker hostname
        port: MQTT broker port
        access_token: JWT access token
        on_connect: Callback function when connected
        on_message: Callback function for messages
    
    Returns:
        MQTTAuthClient: The connected client
    """
    client = MQTTAuthClient(access_token)
    client.on_connect = on_connect
    client.on_message = on_message
    
    client.connect(broker, port)
    client.loop_start()
    
    return client