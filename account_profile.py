import os
import json
from datetime import date
import re
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import abort, redirect, render_template, request, session, url_for


def register_profile(app, site, site_id):
    key_text = os.environ.get("PROFILE_ENCRYPTION_KEY", "")

    try:
        key = bytes.fromhex(key_text)
        if len(key) != 32:
            raise ValueError
    except ValueError:
        raise RuntimeError(".env의 개인정보 암호화 키를 확인하세요.") from None

    cipher = AESGCM(key)
    folder = Path(app.root_path) / "instance"
    folder.mkdir(exist_ok=True)
    db_path = folder / "profiles.db"

    @contextmanager
    def database():
        connection = sqlite3.connect(db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    with database() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                user_id TEXT PRIMARY KEY,
                nonce BLOB NOT NULL,
                ciphertext BLOB NOT NULL
            )
        """)

    db_path.chmod(0o600)

    @app.after_request
    def protect_profile_response(response):
        if request.endpoint == "profile":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/profile", methods=["GET", "POST"])
    def profile():
        user = session.get("user")
        if not user:
            return redirect(url_for("login"))

        # 사용자 번호는 입력값이 아니라 인증된 로그인 정보에서 가져온다.
        user_id = user["id"]

        if "profile_csrf" not in session:
            session["profile_csrf"] = secrets.token_hex(32)

        phone = ""
        email = ""
        birthdate = ""
        error = None
        saved = session.pop("profile_saved", False)

        # 암호문을 해당 사용자 계정과 연결한다.
        associated_data = ("profile-v1:" + user_id).encode("utf-8")

        if request.method == "POST":
            if request.content_length and request.content_length > 8192:
                abort(413)

            expected = session["profile_csrf"]
            submitted = request.form.get("csrf_token", "")

            if not secrets.compare_digest(expected, submitted):
                abort(400, description="새로고침한 뒤 다시 시도하세요.")

            phone = request.form.get("phone", "").strip()
            email = request.form.get("email", "").strip()
            birthdate = request.form.get("birthdate", "").strip()

            birthdate_valid = False
            try:
                if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", birthdate):
                    birthdate_valid = date.fromisoformat(birthdate) <= date.today()
            except ValueError:
                pass
            digits = re.sub(r"[^0-9]", "", phone)

            if (
                len(phone) > 30
                or not re.fullmatch(r"[0-9+() -]+", phone)
                or not 7 <= len(digits) <= 15
            ):
                error = "연락처를 확인해 주세요. 숫자와 +, -, 괄호, 공백을 사용할 수 있습니다."
            elif (
                len(email) > 254
                or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
            ):
                error = "이메일 주소를 확인해 주세요."
            elif not birthdate_valid:
                error = "생년월일을 확인해 주세요. 미래 날짜는 입력할 수 없습니다."
            else:
                # 저장할 때마다 새로운 nonce를 생성한다.
                nonce = os.urandom(12)
                ciphertext = cipher.encrypt(
                    nonce,
                    json.dumps(
                        {
                            "version": 1,
                            "phone": phone,
                            "email": email,
                            "birthdate": birthdate,
                        },
                        ensure_ascii=False,
                    ).encode("utf-8"),
                    associated_data,
                )

                # 연락처 원문은 DB에 저장하지 않는다.
                with database() as db:
                    db.execute("""
                        INSERT INTO profiles (user_id, nonce, ciphertext)
                        VALUES (?, ?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET
                            nonce = excluded.nonce,
                            ciphertext = excluded.ciphertext
                    """, (user_id, nonce, ciphertext))

                session["profile_saved"] = True
                return redirect(url_for("profile"))

        else:
            with database() as db:
                row = db.execute(
                    "SELECT nonce, ciphertext FROM profiles WHERE user_id = ?",
                    (user_id,),
                ).fetchone()

            if row is not None:
                try:
                    plaintext = cipher.decrypt(
                        row["nonce"],
                        row["ciphertext"],
                        associated_data,
                    ).decode("utf-8")

                    if plaintext.startswith("{"):
                        profile_data = json.loads(plaintext)
                        if not isinstance(profile_data, dict):
                            raise ValueError("Invalid profile")

                        phone = profile_data.get("phone", "")
                        email = profile_data.get("email", "")
                        birthdate = profile_data.get("birthdate", "")

                        if not all(
                            isinstance(value, str)
                            for value in (phone, email, birthdate)
                        ):
                            raise ValueError("Invalid profile fields")
                    else:
                        # 이전 버전에서 저장한 연락처도 읽을 수 있게 유지
                        phone = plaintext
                except (InvalidTag, ValueError, UnicodeDecodeError):
                    abort(
                        409,
                        description=(
                            "저장된 정보의 무결성을 확인할 수 없습니다. "
                            "암호화 키 또는 저장 데이터 확인이 필요합니다."
                        ),
                    )

        return render_template(
            "profile.html",
            site=site,
            site_id=site_id,
            user=user,
            phone=phone,
            email=email,
            birthdate=birthdate,
            error=error,
            saved=saved,
            profile_csrf=session["profile_csrf"],
        )
