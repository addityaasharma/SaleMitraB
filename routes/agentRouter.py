from models.user import *
from models.admin import *
from flask import request, jsonify, Blueprint, g
from werkzeug.security import generate_password_hash, check_password_hash
from config.extension import *
from functions.helper_function import *
from functions.background_functions import *
import json, jwt
from datetime import datetime, timedelta
from functools import wraps
import os, random
from dotenv import load_dotenv

load_dotenv()

agentBP = Blueprint("agent", __name__, url_prefix="/agent")


def generate_agent_id():
    for _ in range(20):  # sane retry cap, in case the pool is nearly exhausted
        candidate = str(random.randint(1000, 9999))
        if not Agent.query.filter_by(agent_id=candidate).first():
            return candidate
    raise RuntimeError("Could not generate a unique agent_id")


def agent_middleware(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.split(" ")[1] if auth_header.startswith("Bearer ") else None

        if not token:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

        try:
            decoded = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=["HS256"])
            if decoded.get("role") != "agent":
                return jsonify({"status": "error", "message": "Unauthorized"}), 401

            agent = Agent.query.get(decoded["agentID"])
            if not agent:
                return jsonify({"status": "error", "message": "Agent not found"}), 404
            g.agent = agent
        except jwt.ExpiredSignatureError:
            return jsonify({"status": "error", "message": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"status": "error", "message": "Invalid token"}), 401

        return f(*args, **kwargs)

    return decorated


@agentBP.route("/signup", methods=["POST"])
def agent_signup():
    data = request.get_json()
    try:
        required_fields = ["name", "phone_number", "password"]
        for field in required_fields:
            if not data.get(field):
                return (
                    jsonify({"status": "error", "message": f"{field} is required"}),
                    400,
                )

        check_agent = Agent.query.filter_by(
            phone_number=data.get("phone_number")
        ).first()
        if check_agent:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Account already exists with this phone number. Please login.",
                    }
                ),
                400,
            )

        new_agent = Agent(
            name=data["name"],
            phone_number=data["phone_number"],
            password=generate_password_hash(data["password"]),
            agent_id=generate_agent_id(),
        )
        db.session.add(new_agent)
        db.session.commit()

        token = jwt.encode(
            {
                "agentID": new_agent.id,
                "role": "agent",
                "exp": datetime.utcnow() + timedelta(days=7),
            },
            os.getenv("SECRET_KEY"),
            algorithm="HS256",
        )

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Agent registered successfully",
                    "token": token,
                    "agent": {
                        "id": new_agent.id,
                        "name": new_agent.name,
                        "phone_number": new_agent.phone_number,
                        "agent_id": new_agent.agent_id,
                    },
                }
            ),
            201,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to register agent",
                    "error": str(e),
                }
            ),
            500,
        )


@agentBP.route("/login", methods=["POST"])
def agent_login():
    data = request.get_json()
    try:
        required_fields = ["phone_number", "password"]
        for field in required_fields:
            if not data.get(field):
                return (
                    jsonify({"status": "error", "message": f"{field} is required"}),
                    400,
                )

        check_agent = Agent.query.filter_by(
            phone_number=data.get("phone_number")
        ).first()
        if not check_agent:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Account does not exist. Please signup.",
                    }
                ),
                404,
            )

        if not check_password_hash(check_agent.password, data["password"]):
            return jsonify({"status": "error", "message": "Wrong password"}), 400

        token = jwt.encode(
            {
                "agentID": check_agent.id,
                "role": "agent",
                "exp": datetime.utcnow() + timedelta(days=7),
            },
            os.getenv("SECRET_KEY"),
            algorithm="HS256",
        )

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Agent login successfully",
                    "token": token,
                    "agent": {
                        "id": check_agent.id,
                        "name": check_agent.name,
                        "phone_number": check_agent.phone_number,
                        "agent_id": check_agent.agent_id,
                    },
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify({"status": "error", "message": "Failed to login", "error": str(e)}),
            500,
        )


@agentBP.route("/refund/pickup", methods=["PATCH"])
@agent_middleware
def update_pickup_status():
    data = request.get_json()
    try:
        if not data.get("order_id"):
            return jsonify({"status": "error", "message": "order_id is required"}), 400

        order = Orders.query.filter_by(order_id=data["order_id"]).first()
        if not order:
            return jsonify({"status": "error", "message": "Order not found"}), 404

        refund = Refund.query.filter_by(order_id=order.id).first()
        if not refund:
            return (
                jsonify(
                    {"status": "error", "message": "No refund found for this order"}
                ),
                404,
            )

        refund.status = "picked_up"
        refund.pickup_agent_id = g.agent.id
        refund.picked_up_at = datetime.utcnow()

        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Parcel marked as picked up",
                    "refund": {
                        "id": refund.id,
                        "order_id": order.order_id,
                        "status": refund.status,
                        "picked_up_at": refund.picked_up_at,
                    },
                }
            ),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to update pickup status",
                    "error": str(e),
                }
            ),
            500,
        )


@agentBP.route("/me", methods=["GET"])
@agent_middleware
def get_agent_profile():
    try:
        agent = g.agent
        return (
            jsonify(
                {
                    "status": "success",
                    "agent": {
                        "id": agent.id,
                        "name": agent.name,
                        "phone_number": agent.phone_number,
                        "agent_id": agent.agent_id,
                    },
                }
            ),
            200,
        )
    except Exception as e:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to fetch agent profile",
                    "error": str(e),
                }
            ),
            500,
        )
