"""
Configuration settings for the Patient Monitoring Blockchain system.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# Database configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "pmb")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

# MQTT configuration
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))

# OAuth 2.0 / OIDC configuration
# You should update these values to point to your OAuth provider
AUTH_SERVER_URL = os.getenv("AUTH_SERVER_URL", "https://your-auth-server.com")
JWKS_URI = os.getenv("JWKS_URI", f"{AUTH_SERVER_URL}/.well-known/jwks.json")
TOKEN_ENDPOINT = os.getenv("TOKEN_ENDPOINT", f"{AUTH_SERVER_URL}/oauth/token")
AUTHORIZATION_ENDPOINT = os.getenv("AUTHORIZATION_ENDPOINT", f"{AUTH_SERVER_URL}/authorize")
ISSUER = os.getenv("TOKEN_ISSUER", "https://your-auth-server.com/")
AUDIENCE = os.getenv("API_AUDIENCE", "https://patientmonitor.api")

# Web application configuration
APP_URL = os.getenv("APP_URL", "http://localhost:8080")
REDIRECT_URI = os.getenv("REDIRECT_URI", f"{APP_URL}/callback")

# Client credentials for different services
# These would normally be stored securely and not in code
WEB_APP_CLIENT_ID = os.getenv("WEB_APP_CLIENT_ID", "patient-monitor-web-app")
WEB_APP_CLIENT_SECRET = os.getenv("WEB_APP_CLIENT_SECRET", "web-app-secret")

BACKEND_SERVICE_CLIENT_ID = os.getenv("BACKEND_SERVICE_CLIENT_ID", "patient-monitor-backend")
BACKEND_SERVICE_CLIENT_SECRET = os.getenv("BACKEND_SERVICE_CLIENT_SECRET", "backend-secret")

MQTT_SIMULATOR_CLIENT_ID = os.getenv("MQTT_SIMULATOR_CLIENT_ID", "patient-monitor-simulator")
MQTT_SIMULATOR_CLIENT_SECRET = os.getenv("MQTT_SIMULATOR_CLIENT_SECRET", "simulator-secret") 

# Security configuration
JWKS_CACHE_TTL = int(os.getenv("JWKS_CACHE_TTL", "3600"))  # 1 hour in seconds
ACCESS_TOKEN_TTL = int(os.getenv("ACCESS_TOKEN_TTL", "900"))  # 15 minutes in seconds
REFRESH_TOKEN_TTL = int(os.getenv("REFRESH_TOKEN_TTL", "2592000"))  # 30 days in seconds

# HTTPS/TLS configuration
USE_HTTPS = os.getenv("USE_HTTPS", "False").lower() == "true"
TLS_CERT_FILE = os.getenv("TLS_CERT_FILE", "cert.pem")
TLS_KEY_FILE = os.getenv("TLS_KEY_FILE", "key.pem")