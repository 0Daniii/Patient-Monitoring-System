import time
import requests

KEYCLOAK_URL = "http://auth-server:8080"
REALM = "pmb"
ADMIN_USER = "admin"
ADMIN_PASS = "admin"

def get_admin_token():
    print("🔐 Getting admin token...")
    resp = requests.post(
        f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": ADMIN_USER,
            "password": ADMIN_PASS
        }
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

def realm_exists(token):
    resp = requests.get(
        f"{KEYCLOAK_URL}/admin/realms",
        headers={"Authorization": f"Bearer {token}"}
    )
    return any(realm["realm"] == REALM for realm in resp.json())

def create_realm(token):
    print(f"🌍 Creating realm '{REALM}'...")
    resp = requests.post(
        f"{KEYCLOAK_URL}/admin/realms",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"realm": REALM, "enabled": True}
    )
    if resp.status_code == 409:
        print(f"⚠️ Realm '{REALM}' already exists.")
    else:
        resp.raise_for_status()

def create_client(token, payload):
    resp = requests.post(
        f"{KEYCLOAK_URL}/admin/realms/{REALM}/clients",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload
    )
    if resp.status_code == 409:
        print(f"⚠️ Client {payload['clientId']} already exists.")
    else:
        resp.raise_for_status()

def wait_for_keycloak(timeout=90):
    print("⏳ Waiting for Keycloak token endpoint...")

    for attempt in range(timeout):
        try:
            resp = requests.post(
                f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "client_id": "admin-cli",
                    "username": ADMIN_USER,
                    "password": ADMIN_PASS
                }
            )
            if resp.status_code == 200:
                print("✅ Keycloak is ready! Token obtained.")
                return resp.json()["access_token"]
        except Exception:
            print(f"⌛ Attempt {attempt+1}: token endpoint not ready yet...")
        time.sleep(1)

    raise Exception("❌ Timed out waiting for Keycloak token endpoint")

def main():
    token = wait_for_keycloak()
    if not realm_exists(token):
        create_realm(token)

    print("📦 Creating clients...")
    create_client(token, {
        "clientId": "patient-monitor-backend",
        "secret": "dXA2MECL1mBl8M3FRKYITHM9SCMIMfhM",
        "enabled": True,
        "clientAuthenticatorType": "client-secret",
        "directAccessGrantsEnabled": True,
        "serviceAccountsEnabled": True,
        "standardFlowEnabled": False
    })

    create_client(token, {
        "clientId": "patient-monitor-web-app",
        "secret": "nYU5roKff6KutfL6CO6NcjHUBuwsi4o6",
        "enabled": True,
        "clientAuthenticatorType": "client-secret",
        "redirectUris": ["http://localhost:8080/callback"],
        "publicClient": False,
        "standardFlowEnabled": True
    })

    create_client(token, {
        "clientId": "patient-monitor-simulator",
        "secret": "gdykGlAOxiEOZ88d786MhCJ4TZvWDAjV",
        "enabled": True,
        "clientAuthenticatorType": "client-secret",
        "directAccessGrantsEnabled": True,
        "serviceAccountsEnabled": True,
        "standardFlowEnabled": False
    })

    print("✅ Keycloak setup complete!")

if __name__ == "__main__":
    main()
