import os
import jwt
import uuid
import hmac
import hashlib
import secrets
import requests
import threading
from functools import wraps
from datetime import datetime, timezone
from flask import request, jsonify, g
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import resend
from config.extension import s3, oauth
from models.user import *
from models.admin import *

load_dotenv()

SHIPROCKET_BASE = "https://apiv2.shiprocket.in/v1/external"

_sr_token: str | None = None
_sr_token_fetched_at: datetime | None = None
_SR_TOKEN_TTL_SECONDS = 23 * 3600  # refresh 1 h before the 24-h expiry
_sr_token_lock = threading.Lock()


def get_shiprocket_token() -> str | None:
    """
    Return a valid Shiprocket JWT, re-fetching only when the cached one is
    about to expire (or has never been fetched).  Thread-safe.
    """
    global _sr_token, _sr_token_fetched_at

    with _sr_token_lock:
        now = datetime.now(timezone.utc)
        if (
            _sr_token is None
            or _sr_token_fetched_at is None
            or (now - _sr_token_fetched_at).total_seconds() >= _SR_TOKEN_TTL_SECONDS
        ):
            try:
                res = requests.post(
                    f"{SHIPROCKET_BASE}/auth/login",
                    json={
                        "email": os.getenv("SHIPROCKET_EMAIL"),
                        "password": os.getenv("SHIPROCKET_PASSWORD"),
                    },
                    timeout=10,
                )
                if res.status_code == 200:
                    _sr_token = res.json().get("token")
                    _sr_token_fetched_at = now
                    print("[shiprocket] Token refreshed")
                else:
                    print(f"[shiprocket] Login failed: {res.status_code} {res.text}")
                    _sr_token = None
            except Exception as exc:
                print(f"[shiprocket] Login exception: {exc}")
                _sr_token = None

        return _sr_token


# ---------------------------------------------------------------------------
# Auth middlewares
# ---------------------------------------------------------------------------


def middleware(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.split(" ")[1] if auth_header.startswith("Bearer ") else None

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


# ---------------------------------------------------------------------------
# S3 / R2 upload
# ---------------------------------------------------------------------------


def upload_file(files, folder="uploads"):
    if isinstance(files, list):
        return [upload_file(f, folder) for f in files]

    file_extension = os.path.splitext(secure_filename(files.filename))[1]
    filename = f"{folder}/{uuid.uuid4()}{file_extension}"
    s3.upload_fileobj(
        files,
        os.getenv("R2_BUCKET_NAME"),
        filename,
        ExtraArgs={"ContentType": files.content_type},
    )
    return f"{os.getenv('R2_PUBLIC_URL')}/{filename}"


# ---------------------------------------------------------------------------
# OTP
# ---------------------------------------------------------------------------


def generateOTP_function():
    return str(secrets.randbelow(900000) + 100000)


def _send_otp(email: str, otp: str):
    try:
        resend.Emails.send(
            {
                "from": os.getenv("EMAIL_FROM"),
                "to": [email],
                "subject": "Verify Your Email",
                "html": f"""
            <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:32px;
                        background:#fff;border-radius:16px;border:1px solid #eee;">
                <h2 style="font-size:22px;font-weight:700;color:#000;margin-bottom:4px;">
                    Verify your account</h2>
                <p style="color:#666;font-size:14px;margin-bottom:24px;">
                    Use the OTP below to verify your SaleMitra account.</p>
                <div style="background:#f5f5f5;border-radius:12px;padding:24px;
                            text-align:center;margin-bottom:24px;">
                    <p style="font-size:36px;font-weight:800;letter-spacing:8px;
                               color:#000;margin:0;">{otp}</p>
                </div>
                <p style="color:#999;font-size:12px;">
                    This OTP expires in 5 minutes. Do not share it with anyone.</p>
                <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
                <p style="color:#ccc;font-size:11px;text-align:center;">SaleMitra</p>
            </div>
            """,
            }
        )
    except Exception as exc:
        print(f"[mailer] OTP send failed to {email}: {exc}")


def sendMail_function(email: str, otp: str):
    threading.Thread(target=_send_otp, args=(email, otp), daemon=True).start()


# ---------------------------------------------------------------------------
# Order helpers
# ---------------------------------------------------------------------------


def generate_order_id() -> str:
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
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


# ---------------------------------------------------------------------------
# Shiprocket integration
# ---------------------------------------------------------------------------


def create_shiprocket_order(order, user):
    """
    Create an order on Shiprocket and return
        ({ shiprocket_order_id, shipment_id }, None)   on success
        (None, error_message)                          on failure
    """
    token = get_shiprocket_token()
    if not token:
        return None, "Failed to authenticate with Shiprocket"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    addr = order.shipping_address  # dict snapshot stored on the order

    order_items = [
        {
            "name": item.product_name,
            "sku": item.product_sku or f"SKU-{item.product_id}",
            "units": item.quantity,
            "selling_price": str(item.unit_price),
            "discount": "0",
            "tax": str(item.tax_amount or 0),
        }
        for item in order.ordered_items
    ]

    payload = {
        "order_id": order.order_id,
        "order_date": order.created_at.strftime("%Y-%m-%d %H:%M"),
        "pickup_location": os.getenv("SHIPROCKET_PICKUP_LOCATION", "Primary"),
        "billing_customer_name": user.username,
        "billing_last_name": "",
        "billing_address": addr.get("street", ""),
        "billing_city": addr.get("city", ""),
        "billing_pincode": addr.get("postal_code", ""),
        "billing_state": addr.get("state", ""),
        "billing_country": addr.get("country", "India"),
        "billing_email": user.email,
        "billing_phone": user.phone_number or "9999999999",
        "shipping_is_billing": True,
        "order_items": order_items,
        "payment_method": "Prepaid" if order.payment_method == "razorpay" else "COD",
        "sub_total": str(order.subtotal),
        # Physical dimensions — move to product model if you have per-product data
        "length": 10,
        "breadth": 10,
        "height": 10,
        "weight": 0.5,
    }

    # Only include channel_id when it is actually set
    channel_id = os.getenv("SHIPROCKET_CHANNEL_ID", "").strip()
    if channel_id:
        payload["channel_id"] = channel_id

    try:
        res = requests.post(
            f"{SHIPROCKET_BASE}/orders/create/adhoc",
            json=payload,
            headers=headers,
            timeout=15,
        )
    except requests.RequestException as exc:
        return None, f"Shiprocket request failed: {exc}"

    if res.status_code in (200, 201):
        body = res.json()
        return {
            "shiprocket_order_id": body.get("order_id"),
            "shipment_id": body.get("shipment_id"),
        }, None

    if res.status_code == 401:
        global _sr_token, _sr_token_fetched_at
        with _sr_token_lock:
            _sr_token = None
            _sr_token_fetched_at = None

    return None, res.json().get("message", "Shiprocket order creation failed")


def _create_shiprocket_shipment(order_id: str):
    """Background worker — called from create_shipment_async."""
    try:
        order = Orders.query.filter_by(order_id=order_id).first()
        if not order:
            print(f"[shiprocket] Order {order_id} not found")
            return

        user = db.session.get(User, order.user_id)
        if not user:
            print(f"[shiprocket] User not found for order {order_id}")
            return

        sr_data, sr_error = create_shiprocket_order(order, user)
        if sr_data:
            order.shiprocket_order_id = str(sr_data["shiprocket_order_id"])
            order.shipment_id = str(sr_data["shipment_id"])
            order.tracking_url = (
                f"https://shiprocket.co/tracking/{sr_data['shipment_id']}"
            )
            db.session.commit()
            print(
                f"[shiprocket] Shipment created for {order_id}: "
                f"{sr_data['shipment_id']}"
            )
        else:
            print(f"[shiprocket] Error for {order_id}: {sr_error}")

    except Exception as exc:
        print(f"[shiprocket] Exception for {order_id}: {exc}")


def create_shipment_async(order_id: str):
    """Fire-and-forget: push order to Shiprocket in a background thread."""
    threading.Thread(
        target=_create_shiprocket_shipment,
        args=(order_id,),
        daemon=True,
    ).start()


# ---------------------------------------------------------------------------
# Shiprocket tracking / cancel helpers
# ---------------------------------------------------------------------------


def get_tracking(shipment_id: str):
    token = get_shiprocket_token()
    if not token:
        return None

    res = requests.get(
        f"{SHIPROCKET_BASE}/courier/track/shipment/{shipment_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    return res.json() if res.status_code == 200 else None


def cancel_shiprocket_order(shiprocket_order_id: str) -> bool:
    token = get_shiprocket_token()
    if not token:
        return False

    res = requests.post(
        f"{SHIPROCKET_BASE}/orders/cancel",
        json={"ids": [shiprocket_order_id]},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=10,
    )
    return res.status_code == 200


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------


def init_oauth(app):
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url=(
            "https://accounts.google.com/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid email profile"},
    )
