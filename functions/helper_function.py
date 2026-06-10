import random, secrets, os
from dotenv import load_dotenv
from config.extension import resend, s3
from functools import wraps
from flask import request, jsonify, g
from models.user import *
from models.admin import *
import jwt, os, uuid, datetime, threading
from werkzeug.utils import secure_filename

load_dotenv()


def generateOTP_function():
    return str(secrets.randbelow(900000) + 100000)


import os
import threading
import resend


def _send_otp(email, otp):
    try:
        resend.Emails.send(
            {
                "from": os.getenv("EMAIL_FROM"),
                "to": [email],
                "subject": "Verify Your Email",
                "html": f"""
            <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:32px;background:#fff;border-radius:16px;border:1px solid #eee;">
                <h2 style="font-size:22px;font-weight:700;color:#000;margin-bottom:4px;">Verify your account</h2>
                <p style="color:#666;font-size:14px;margin-bottom:24px;">Use the OTP below to verify your SaleMitra account.</p>
                <div style="background:#f5f5f5;border-radius:12px;padding:24px;text-align:center;margin-bottom:24px;">
                    <p style="font-size:36px;font-weight:800;letter-spacing:8px;color:#000;margin:0;">{otp}</p>
                </div>
                <p style="color:#999;font-size:12px;">This OTP expires in 5 minutes. Do not share it with anyone.</p>
                <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
                <p style="color:#ccc;font-size:11px;text-align:center;">SaleMitra</p>
            </div>
            """,
            }
        )
    except Exception as e:
        print(f"[mailer] OTP send failed to {email}: {e}")


def sendMail_function(email, otp):
    thread = threading.Thread(target=_send_otp, args=(email, otp), daemon=True)
    thread.start()


def middleware(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # get token from Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

        if not token:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

        try:
            decoded = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=["HS256"])

            user = User.query.get(decoded["userID"])
            if not user:
                return jsonify({"status": "error", "message": "User not found"}), 404

            g.user = user

        except jwt.ExpiredSignatureError:
            return jsonify({"status": "error", "message": "Token expired"}), 401

        except jwt.InvalidTokenError:
            return jsonify({"status": "error", "message": "Invalid token"}), 401

        return f(*args, **kwargs)

    return decorated


def admin_middleware(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

        try:
            decoded = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=["HS256"])
            admin = Admin.query.get(decoded["id"])
            if not admin:
                return jsonify({"status": "error", "message": "Admin not found"}), 404

            g.admin = admin

        except jwt.ExpiredSignatureError:
            return jsonify({"status": "error", "message": "Token expired"}), 401

        except jwt.InvalidTokenError:
            return jsonify({"status": "error", "message": "Invalid token"}), 401

        return f(*args, **kwargs)

    return decorated


def upload_file(files, folder="uploads"):
    if isinstance(files, list):
        return [upload_file(file, folder) for file in files]

    file_extension = os.path.splitext(secure_filename(files.filename))[1]
    filename = f"{folder}/{uuid.uuid4()}{file_extension}"
    s3.upload_fileobj(
        files,
        os.getenv("R2_BUCKET_NAME"),
        filename,
        ExtraArgs={"ContentType": files.content_type},
    )
    return f"{os.getenv('R2_PUBLIC_URL')}/{filename}"


def generate_order_id():
    date_str = datetime.utcnow().strftime("%Y%m%d")
    unique = str(uuid.uuid4()).split("-")[0].upper()
    return f"ORD-{date_str}-{unique}"


def to_bool(val, default=False):
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() == "true"
    return default


def to_float(val, default=None):
    try:
        return float(val) if val not in (None, "") else default
    except (ValueError, TypeError):
        return default


def to_int(val, default=None):
    try:
        return int(val) if val not in (None, "") else default
    except (ValueError, TypeError):
        return default
