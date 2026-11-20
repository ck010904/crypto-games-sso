import os
import sys
from datetime import timedelta
from pathlib import Path

from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, session, url_for


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SITE_CONFIG = {
    "a": {
        "name": "오목 커뮤니티",
        "client_id": "service-a",
        "port": 5000,
        "other_name": "바둑 커뮤니티",
        "other_url": "http://localhost:5001",
    },
    "b": {
        "name": "바둑 커뮤니티",
        "client_id": "service-b",
        "port": 5001,
        "other_name": "오목 커뮤니티",
        "other_url": "http://localhost:5000",
    },
}

if len(sys.argv) != 2 or sys.argv[1] not in SITE_CONFIG:
    raise SystemExit("실행 방법: python app.py a 또는 python app.py b")

site_id = sys.argv[1]
site = SITE_CONFIG[site_id]
suffix = site_id.upper()

client_secret = os.getenv(f"CLIENT_{suffix}_SECRET")
session_secret = os.getenv(f"SESSION_SECRET_{suffix}")

if not client_secret or not session_secret:
    raise SystemExit(".env의 Client secret과 SESSION_SECRET을 확인하세요.")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=session_secret,
    SESSION_COOKIE_NAME=f"community_{site_id}_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
)

KEYCLOAK_REALM = "http://localhost:8080/realms/sso-demo"

oauth = OAuth(app)
oauth.register(
    name="keycloak",
    client_id=site["client_id"],
    client_secret=client_secret,
    server_metadata_url=(
        f"{KEYCLOAK_REALM}/.well-known/openid-configuration"
    ),
    client_kwargs={
        "scope": "openid profile email",
        "code_challenge_method": "S256",
    },
)


@app.get("/")
def index():
    return render_template(
        "index.html",
        site=site,
        site_id=site_id,
        user=session.get("user"),
    )


@app.get("/login")
def login():
    callback_url = f"http://localhost:{site['port']}/callback"
    return oauth.keycloak.authorize_redirect(callback_url)


@app.get("/callback")
def callback():
    token = oauth.keycloak.authorize_access_token()
    userinfo = token["userinfo"]

    session.clear()
    session.permanent = True
    session["user"] = {
        "id": userinfo["sub"],
        "name": userinfo.get("preferred_username", userinfo["sub"]),
    }

    return redirect(url_for("index"))



import secrets
from urllib.parse import urlencode
from flask import abort, request


@app.context_processor
def logout_form_token():
    if "logout_csrf" not in session:
        session["logout_csrf"] = secrets.token_hex(32)
    return {"logout_csrf": session["logout_csrf"]}


@app.post("/logout")
def logout():
    expected = session.get("logout_csrf", "")
    submitted = request.form.get("csrf_token", "")

    if not expected or not secrets.compare_digest(expected, submitted):
        abort(400, description="페이지를 새로고침한 뒤 다시 시도하세요.")

    session.clear()

    params = urlencode({
        "client_id": site["client_id"],
        "post_logout_redirect_uri": f"http://localhost:{site['port']}/",
    })

    response = redirect(
        f"{KEYCLOAK_REALM}/protocol/openid-connect/logout?{params}"
    )

    # 두 사이트가 localhost를 사용하므로 두 로그인 쿠키를 함께 삭제
    response.delete_cookie("community_a_session", path="/")
    response.delete_cookie("community_b_session", path="/")
    return response


from account_profile import register_profile
register_profile(app, site, site_id)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=site["port"], debug=False)
