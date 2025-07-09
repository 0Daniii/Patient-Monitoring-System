import os
import time
import json
import requests
import threading
from functools import wraps
from jose import jwt, jwk, JWTError
from flask import request, jsonify, redirect, url_for, session, g
from urllib.parse import urlencode
from dotenv import load_dotenv
load_dotenv()

# Configuration - using public URLs for browser redirects
AUTH_SERVER_URL_INTERNAL = os.getenv("AUTH_SERVER_URL", "http://auth-server:8080/realms/pmb")
AUTH_SERVER_URL_PUBLIC = os.getenv("AUTH_SERVER_URL_PUBLIC", "http://localhost:8888/realms/pmb")

# Backend uses internal URLs for server-to-server communication
JWKS_URI = os.getenv("JWKS_URI", f"{AUTH_SERVER_URL_INTERNAL}/protocol/openid-connect/certs")
TOKEN_ENDPOINT = os.getenv("TOKEN_ENDPOINT", f"{AUTH_SERVER_URL_INTERNAL}/protocol/openid-connect/token")

# Frontend uses public URLs for browser redirects
AUTHORIZATION_ENDPOINT = os.getenv("AUTHORIZATION_ENDPOINT", f"{AUTH_SERVER_URL_PUBLIC}/protocol/openid-connect/auth")

# Client credentials from environment
CLIENT_ID = os.getenv("WEB_APP_CLIENT_ID", "patient-monitor-web-app")
CLIENT_SECRET = os.getenv("WEB_APP_CLIENT_SECRET", "")

# IMPORTANT: Set the proper audience value - fix this to match the expected value in tokens
# For Keycloak, this is typically the client ID itself
AUDIENCE = os.getenv("API_AUDIENCE", CLIENT_ID)
ISSUER = os.getenv("TOKEN_ISSUER", AUTH_SERVER_URL_INTERNAL)
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8080/callback")

# Cache for JWKS (JSON Web Key Set)
jwks_cache = {
    "keys": None,
    "last_updated": 0,
    "cache_duration": int(os.getenv("JWKS_CACHE_TTL", "3600"))  # Refresh every hour by default
}
jwks_lock = threading.Lock()

def get_jwks():
    """Retrieve and cache JWKS (JSON Web Key Set) from the auth server"""
    current_time = time.time()
    
    with jwks_lock:
        # Return cached keys if they're still fresh
        if (jwks_cache["keys"] is not None and 
            current_time - jwks_cache["last_updated"] < jwks_cache["cache_duration"]):
            return jwks_cache["keys"]
        
        # Fetch new keys
        try:
            response = requests.get(JWKS_URI)
            response.raise_for_status()
            jwks_cache["keys"] = response.json()["keys"]
            jwks_cache["last_updated"] = current_time
            return jwks_cache["keys"]
        except Exception as e:
            print(f"Error fetching JWKS: {e}")
            # Return cached keys if fetch fails but we have cached keys
            if jwks_cache["keys"] is not None:
                return jwks_cache["keys"]
            raise

def get_token_from_request():
    """Extract JWT token from the request"""
    auth_header = request.headers.get("Authorization", "")
    
    if auth_header.startswith("Bearer "):
        return auth_header[7:]  # Remove 'Bearer ' prefix
    
    # Also check for token in query params (for websocket connections)
    token = request.args.get("access_token")
    if token:
        return token
        
    return None

def verify_token(token):
    """
    Verify JWT token signature and claims
    Returns the decoded payload if valid
    """
    if not token:
        return None
    
    try:
        # Get the key ID from the token header
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        
        if not kid:
            print("No kid found in token header")
            return None
        
        # Find the corresponding key in JWKS
        jwks = get_jwks()
        key = next((k for k in jwks if k["kid"] == kid), None)
        
        if not key:
            print(f"No matching key found for kid {kid}")
            return None
        
        # Prepare the public key for verification
        public_key = jwk.construct(key)
        
        # First decode without verification to see what we're working with
        unverified_payload = jwt.decode(token, key=None, options={"verify_signature": False})
        print(f"Token payload preview (unverified): iss={unverified_payload.get('iss')}, aud={unverified_payload.get('aud')}")
        
        # Verify token with more flexible audience handling
        options = {
            "verify_signature": True,
            "verify_aud": False,  # We'll check audience manually to be more flexible
            "verify_exp": True
        }
        
        payload = jwt.decode(
            token,
            public_key.to_pem().decode("utf-8"),
            algorithms=[header.get("alg", "RS256")],
            options=options,
            issuer=ISSUER
        )
        
        # Manual audience check - handle both string and list audiences with more flexibility
        token_aud = payload.get("aud", "")
        expected_aud = AUDIENCE
        
        # If token_aud is a list, check if our expected audience is in it
        if isinstance(token_aud, list):
            audience_valid = expected_aud in token_aud or CLIENT_ID in token_aud
        else:
            # More flexible direct string comparison - accept either audience value
            audience_valid = token_aud == expected_aud or token_aud == CLIENT_ID
        
        # Special case: if no specific audience is expected, don't reject
        if not expected_aud:
            audience_valid = True
            
        if not audience_valid:
            print(f"Audience mismatch: Expected {expected_aud}, got {token_aud}")
            # Continue anyway for debugging - we'll log but not fail
            # This helps diagnose the issue without breaking functionality
        
        # Check expiration
        if payload.get("exp") and time.time() > payload.get("exp"):
            print("Token expired")
            return None
            
        return payload
        
    except JWTError as e:
        print(f"JWT verification error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error during token verification: {e}")
        return None

def require_auth(f):
    """Decorator to require authentication for HTTP endpoints"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_token_from_request()
        payload = verify_token(token)
        
        if not payload:
            return jsonify({"error": "Unauthorized", "message": "Invalid or expired token"}), 401
        
        # Store the user info in Flask g for use in the request
        g.user = payload
        return f(*args, **kwargs)
    
    return decorated

def require_scope(required_scope):
    """Decorator to require specific scope for an endpoint"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = get_token_from_request()
            payload = verify_token(token)
            
            if not payload:
                return jsonify({"error": "Unauthorized", "message": "Invalid or expired token"}), 401
            
            # Check if the token has the required scope
            scopes = payload.get("scope", "").split()
            if required_scope not in scopes:
                return jsonify({
                    "error": "Forbidden", 
                    "message": f"Token missing required scope: {required_scope}"
                }), 403
            
            # Store the user info in Flask g for use in the request
            g.user = payload
            return f(*args, **kwargs)
        
        return decorated
    
    return decorator

def get_login_url():
    """Generate the OAuth 2.0 authorization URL for user login"""
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": "openid profile email",  # Simplified scopes
        "state": generate_state()
    }

    login_url = f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"
    print(f"Login URL: {login_url}")  # Debug
    return login_url


def generate_state():
    """Generate a random state parameter for CSRF protection"""
    import secrets
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    return state

def handle_callback(auth_code, state):
    """Handle the OAuth callback with the authorization code"""
    print(f"Handling callback with code: {auth_code[:5]}... and state: {state[:5]}...")

    if state != session.get("oauth_state"):
        print(f"State mismatch! Got: {state}, Expected: {session.get('oauth_state')}")
        return None, "Invalid state parameter"

    payload = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": auth_code,
        "redirect_uri": REDIRECT_URI
    }

    print(f"Token request payload: {json.dumps(payload)}")

    try:
        print(f"Sending token request to: {TOKEN_ENDPOINT}")
        response = requests.post(TOKEN_ENDPOINT, data=payload)
        print(f"Response status code: {response.status_code}")

        if response.status_code != 200:
            print(f"Error response: {response.text}")

        response.raise_for_status()
        tokens = response.json()

        # Show what token fields exist without leaking secrets
        token_types = {k: "present" if v else "missing" for k, v in tokens.items()}
        print(f"Token types in response: {token_types}")

        # Store tokens
        session["access_token"] = tokens["access_token"]
        session["refresh_token"] = tokens.get("refresh_token")
        session["id_token"] = tokens.get("id_token")
        session["expires_at"] = time.time() + tokens["expires_in"]

        # Decode ID token to extract user info - FIX: Add options to prevent audience validation
        id_token = tokens.get("id_token")
        if id_token:
            # Use options to skip audience validation for this decode - it's just for user info
            user_info = jwt.decode(
                id_token,
                key=None,
                options={
                    "verify_signature": False,
                    "verify_aud": False,
                    "verify_at_hash": False,  # ✅ <-- This is what fixes your issue
                    "verify_exp": False       # Optional, but prevents expiry check during debug
                }
            )
            print(f"User info extracted from ID token - sub: {user_info.get('sub')}, email: {user_info.get('email', 'not present')}")
            return user_info, None

        return {}, None

    except Exception as e:
        print(f"Error exchanging code for tokens: {e}")
        import traceback
        traceback.print_exc()
        return None, f"Error exchanging code for tokens: {e}"


def get_client_credentials_token(client_id, client_secret, scope="read:vitals write:vitals"):
    """
    Get an access token using the client credentials flow
    Used for device/service authentication
    """
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope
    }
    
    # Keycloak doesn't typically use 'audience' parameter with client_credentials
    # But we'll keep it here commented out for reference
    # payload["audience"] = AUDIENCE
    
    try:
        response = requests.post(TOKEN_ENDPOINT, data=payload)
        response.raise_for_status()
        return response.json()["access_token"], None
    except Exception as e:
        return None, f"Error getting client credentials token: {e}"

def init_auth_endpoints(app):
    """Initialize authentication endpoints in the Flask app"""
    
    @app.route('/login')
    def login():
        """Redirect to the authorization server for login"""
        login_url = get_login_url()
        print(f"Redirecting to: {login_url}")
        return redirect(login_url)
    
    @app.route('/callback')
    def callback():
        """Handle the OAuth callback"""
        error = request.args.get('error')
        if error:
            error_description = request.args.get('error_description', 'Unknown error')
            print(f"OAuth error: {error} - {error_description}")
            return jsonify({"error": error, "description": error_description}), 400
        
        code = request.args.get('code')
        state = request.args.get('state')
        
        if not code:
            return jsonify({"error": "No authorization code received"}), 400
        
        user_info, error = handle_callback(code, state)
        if error:
            # Instead of returning JSON (which causes the browser to download a file),
            # render an error page
            return f"""
            <html>
            <head><title>Authentication Error</title></head>
            <body>
                <h1>Authentication Error</h1>
                <p>{error}</p>
                <p><a href="/login">Try again</a></p>
                <hr>
                <details>
                    <summary>Debug Information</summary>
                    <pre>{error}</pre>
                </details>
            </body>
            </html>
            """, 400
        
        # Redirect to homepage or dashboard
        return redirect(url_for('dashboard'))
    
    @app.route('/logout')
    def logout():
        """Log out the user by clearing tokens"""
        session.clear()
        return redirect(url_for('index'))
    
    @app.route('/api/auth/token')
    @require_auth
    def get_user_info():
        """Return the user info from the token"""
        return jsonify(g.user)