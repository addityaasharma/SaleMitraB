import random, secrets, os
from dotenv import load_dotenv
from config.extension import resend, s3
from functools import wraps
from flask import request, jsonify, g
from models.user import *
from models.admin import *
import jwt, os, uuid, datetime
from werkzeug.utils import secure_filename

load_dotenv()


def generateOTP_function():
    return str(secrets.randbelow(900000) + 100000)


def sendMail_function(email, otp):
    resend.Emails.send(
        {
            "from": os.getenv("EMAIL_FROM"),
            "to": [email],
            "subject": "Verify Your Email",
            "html": f"""
        <div style="font-family: Arial, sans-serif;">
            <h2>Email Verification</h2>
            <p>Your OTP code is:</p>
            <h1>{otp}</h1>
            <p>This code will expire in 5 minutes.</p>
        </div>
        """,
        }
    )


def middleware(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get("user_auth_token")
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
    date_str = datetime.now().strftime("%Y%m%d")
    unique = str(uuid.uuid4()).split("-")[0].upper()
    return f"ORD-{date_str}-{unique}"


def to_bool(val, default=False):
    if isinstance(val, bool): return val
    if isinstance(val, str): return val.lower() == 'true'
    return default

def to_float(val, default=None):
    try: return float(val) if val not in (None, '') else default
    except (ValueError, TypeError): return default

def to_int(val, default=None):
    try: return int(val) if val not in (None, '') else default
    except (ValueError, TypeError): return default