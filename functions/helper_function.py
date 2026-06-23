import os
import jwt
import uuid
import random
import secrets
import requests
import threading
from functools import wraps
from datetime import datetime, timezone
from flask import request, jsonify, g
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import resend
from config.extension import *
from models.user import *
from models.admin import *

load_dotenv()
SHIPROCKET_BASE = "https://apiv2.shiprocket.in/v1/external"


def generateOTP_function():
    return str(secrets.randbelow(900000) + 100000)


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


def _create_shiprocket_shipment(order_id):
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
                f"[shiprocket] Shipment created for {order_id}: {sr_data['shipment_id']}"
            )
        else:
            print(f"[shiprocket] Error for {order_id}: {sr_error}")

    except Exception as e:
        print(f"[shiprocket] Exception for {order_id}: {str(e)}")


def create_shipment_async(order_id):
    thread = threading.Thread(
        target=_create_shiprocket_shipment, args=(order_id,), daemon=True
    )
    thread.start()


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


def get_shiprocket_token():
    res = requests.post(
        f"{SHIPROCKET_BASE}/auth/login",
        json={
            "email": os.getenv("SHIPROCKET_EMAIL"),
            "password": os.getenv("SHIPROCKET_PASSWORD"),
        },
    )
    if res.status_code == 200:
        return res.json().get("token")
    return None


def create_shiprocket_order(order, user):
    token = get_shiprocket_token()
    if not token:
        return None, "Failed to authenticate with Shiprocket"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    addr = order.shipping_address  # your JSON field

    order_items = []
    for item in order.ordered_items:
        order_items.append(
            {
                "name": item.product_name,
                "sku": item.product_sku,
                "units": item.quantity,
                "selling_price": str(item.unit_price),
                "discount": "0",
                "tax": str(item.tax_amount or 0),
            }
        )

    payload = {
        "order_id": order.order_id,
        "order_date": order.created_at.strftime("%Y-%m-%d %H:%M"),
        "pickup_location": "Primary",  # name of your pickup location in Shiprocket
        "channel_id": os.getenv("SHIPROCKET_CHANNEL_ID", ""),
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
        "length": 10,  # cm — update per product
        "breadth": 10,
        "height": 10,
        "weight": 0.5,  # kg — update per product
    }

    res = requests.post(
        f"{SHIPROCKET_BASE}/orders/create/adhoc", json=payload, headers=headers
    )

    if res.status_code in [200, 201]:
        data = res.json()
        return {
            "shiprocket_order_id": data.get("order_id"),
            "shipment_id": data.get("shipment_id"),
        }, None
    else:
        return None, res.json().get("message", "Shiprocket order creation failed")


def get_tracking(shipment_id):
    token = get_shiprocket_token()
    if not token:
        return None

    res = requests.get(
        f"{SHIPROCKET_BASE}/courier/track/shipment/{shipment_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    if res.status_code == 200:
        return res.json()
    return None


def cancel_shiprocket_order(shiprocket_order_id):
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
    )
    return res.status_code == 200


def init_oauth(app):
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
