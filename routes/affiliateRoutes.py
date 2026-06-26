from models.user import *
from models.admin import *
from flask import request, jsonify, Blueprint, g, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from config.extension import *
from functions.helper_function import *
from functions.background_functions import *
import json, jwt, hashlib, hmac
from datetime import datetime, timedelta

affiliateBP = Blueprint("affiliate", __name__, url_prefix="/affiliate")


# 1. BECOME AN AFFILIATE PARTNER
@affiliateBP.route("/partner", methods=["POST"])
@middleware
def become_affiliate():
    try:
        if g.user.is_affiliate or g.user.affiliate_id:
            return (
                jsonify({"status": "success", "message": "Already an affiliate"}),
                200,
            )

        g.user.is_affiliate = True
        g.user.role = "affiliate"
        g.user.affiliate_id = generate_affiliate_id()

        dashboard = AffiliateDashboard(user_id=g.user.id)
        db.session.add(dashboard)
        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "You are now an affiliate partner",
                    "data": {"affiliate_id": g.user.affiliate_id},
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
                    "message": "Failed to register as affiliate partner",
                    "error": str(e),
                }
            ),
            500,
        )


# 2. GET DASHBOARD
@affiliateBP.route("/dashboard", methods=["GET"])
@middleware
def get_dashboard():
    try:
        dashboard = AffiliateDashboard.query.filter_by(user_id=g.user.id).first()
        if not dashboard:
            return jsonify({"status": "error", "message": "Dashboard not found"}), 404

        return (
            jsonify(
                {
                    "status": "success",
                    "data": {
                        "total_orders": dashboard.total_orders,
                        "total_revenue": dashboard.total_revenue,
                        "total_withdrawal": dashboard.total_withdrawal,
                        "upi_id": dashboard.upi_id,
                        "created_at": dashboard.created_at,
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
                    "message": "Failed to fetch dashboard",
                    "error": str(e),
                }
            ),
            500,
        )


# 3. UPDATE UPI ID
@affiliateBP.route("/upi", methods=["PUT"])
@middleware
def update_upi():
    try:
        data = request.get_json()
        upi_id = data.get("upi_id", "").strip()

        if not upi_id:
            return jsonify({"status": "error", "message": "UPI ID is required"}), 400

        dashboard = AffiliateDashboard.query.filter_by(user_id=g.user.id).first()
        if not dashboard:
            return jsonify({"status": "error", "message": "Dashboard not found"}), 404

        dashboard.upi_id = upi_id
        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "UPI ID updated successfully",
                    "data": {"upi_id": dashboard.upi_id},
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
                    "message": "Failed to update UPI ID",
                    "error": str(e),
                }
            ),
            500,
        )


# 4. GET ALL ORDERS
@affiliateBP.route("/orders", methods=["GET"])
@middleware
def get_orders():
    try:
        dashboard = AffiliateDashboard.query.filter_by(user_id=g.user.id).first()
        if not dashboard:
            return jsonify({"status": "error", "message": "Dashboard not found"}), 404

        # --- pagination ---
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)
        per_page = min(per_page, 50)  # cap at 50

        status = request.args.get("status")
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")
        sort_by = request.args.get("sort_by", "created_at")
        order = request.args.get("order", "desc")

        query = OrderList.query.filter_by(affiliate_id=dashboard.id)

        if status:
            query = query.filter(OrderList.status == status)
        if date_from:
            query = query.filter(OrderList.created_at >= date_from)
        if date_to:
            query = query.filter(OrderList.created_at <= date_to)

        # sorting
        sort_column = getattr(OrderList, sort_by, OrderList.created_at)
        query = query.order_by(
            sort_column.desc() if order == "desc" else sort_column.asc()
        )

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)

        orders = [
            {
                "id": o.id,
                "order_id": o.order_id,
                "product_id": o.product_id,
                "commission": o.commission,
                "revenue": o.revenue,
                "status": o.status,
                "created_at": o.created_at,
                "updated_at": o.updated_at,
            }
            for o in paginated.items
        ]

        return (
            jsonify(
                {
                    "status": "success",
                    "data": orders,
                    "pagination": {
                        "page": paginated.page,
                        "per_page": paginated.per_page,
                        "total_pages": paginated.pages,
                        "total_items": paginated.total,
                        "has_next": paginated.has_next,
                        "has_prev": paginated.has_prev,
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
                    "message": "Failed to fetch orders",
                    "error": str(e),
                }
            ),
            500,
        )


# 5. GET SINGLE ORDER
@affiliateBP.route("/orders/<int:order_id>", methods=["GET"])
@middleware
def get_order(order_id):
    try:
        dashboard = AffiliateDashboard.query.filter_by(user_id=g.user.id).first()
        if not dashboard:
            return jsonify({"status": "error", "message": "Dashboard not found"}), 404

        order = OrderList.query.filter_by(
            id=order_id, affiliate_id=dashboard.id
        ).first()
        if not order:
            return jsonify({"status": "error", "message": "Order not found"}), 404

        return (
            jsonify(
                {
                    "status": "success",
                    "data": {
                        "id": order.id,
                        "order_id": order.order_id,
                        "product_id": order.product_id,
                        "commission": order.commission,
                        "revenue": order.revenue,
                        "status": order.status,
                        "created_at": order.created_at,
                        "updated_at": order.updated_at,
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
                    "message": "Failed to fetch order",
                    "error": str(e),
                }
            ),
            500,
        )


# 6. REQUEST WITHDRAWAL
@affiliateBP.route("/withdrawal", methods=["POST"])
@middleware
def request_withdrawal():
    try:
        dashboard = AffiliateDashboard.query.filter_by(user_id=g.user.id).first()
        if not dashboard:
            return jsonify({"status": "error", "message": "Dashboard not found"}), 404

        if not dashboard.upi_id:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Please add UPI ID before withdrawal",
                    }
                ),
                400,
            )

        data = request.get_json()
        amount = data.get("amount")

        if not amount or amount <= 0:
            return jsonify({"status": "error", "message": "Invalid amount"}), 400

        available_balance = dashboard.total_revenue - dashboard.total_withdrawal
        if amount > available_balance:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Insufficient balance",
                        "data": {"available_balance": available_balance},
                    }
                ),
                400,
            )

        # check for any pending withdrawal already
        pending = Withdrawal.query.filter_by(
            affiliate_id=dashboard.id, status="pending"
        ).first()
        if pending:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "You already have a pending withdrawal request",
                    }
                ),
                400,
            )

        withdrawal = Withdrawal(affiliate_id=dashboard.id, amount=amount)
        db.session.add(withdrawal)
        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Withdrawal request submitted",
                    "data": {
                        "withdrawal_id": withdrawal.id,
                        "amount": withdrawal.amount,
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
                    "message": "Failed to request withdrawal",
                    "error": str(e),
                }
            ),
            500,
        )


# 7. GET ALL WITHDRAWALS
@affiliateBP.route("/withdrawals", methods=["GET"])
@middleware
def get_withdrawals():
    try:
        dashboard = AffiliateDashboard.query.filter_by(user_id=g.user.id).first()
        if not dashboard:
            return jsonify({"status": "error", "message": "Dashboard not found"}), 404

        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)
        per_page = min(per_page, 50)

        status = request.args.get("status")  # pending | approved
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")
        order = request.args.get("order", "desc")

        query = Withdrawal.query.filter_by(affiliate_id=dashboard.id)

        if status:
            query = query.filter(Withdrawal.status == status)
        if date_from:
            query = query.filter(Withdrawal.created_at >= date_from)
        if date_to:
            query = query.filter(Withdrawal.created_at <= date_to)

        query = query.order_by(
            Withdrawal.created_at.desc()
            if order == "desc"
            else Withdrawal.created_at.asc()
        )

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)

        withdrawals = [
            {
                "id": w.id,
                "amount": w.amount,
                "payslip": w.payslip,
                "status": w.status,
                "created_at": w.created_at,
                "updated_at": w.updated_at,
            }
            for w in paginated.items
        ]

        return (
            jsonify(
                {
                    "status": "success",
                    "data": withdrawals,
                    "pagination": {
                        "page": paginated.page,
                        "per_page": paginated.per_page,
                        "total_pages": paginated.pages,
                        "total_items": paginated.total,
                        "has_next": paginated.has_next,
                        "has_prev": paginated.has_prev,
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
                    "message": "Failed to fetch withdrawals",
                    "error": str(e),
                }
            ),
            500,
        )



# 9. GET ALL NOTIFICATIONS (with pagination)
@affiliateBP.route("/notifications", methods=["GET"])
@middleware
def get_notifications():
    try:
        dashboard = AffiliateDashboard.query.filter_by(user_id=g.user.id).first()
        if not dashboard:
            return jsonify({"status": "error", "message": "Dashboard not found"}), 404

        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)
        per_page = min(per_page, 50)

        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")
        order = request.args.get("order", "desc")

        query = Notification.query.filter_by(affiliate_id=dashboard.id)

        if date_from:
            query = query.filter(Notification.created_at >= date_from)
        if date_to:
            query = query.filter(Notification.created_at <= date_to)

        query = query.order_by(
            Notification.created_at.desc()
            if order == "desc"
            else Notification.created_at.asc()
        )

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)

        notifications = [
            {
                "id": n.id,
                "message": n.message,
                "created_at": n.created_at,
            }
            for n in paginated.items
        ]

        return (
            jsonify(
                {
                    "status": "success",
                    "data": notifications,
                    "pagination": {
                        "page": paginated.page,
                        "per_page": paginated.per_page,
                        "total_pages": paginated.pages,
                        "total_items": paginated.total,
                        "has_next": paginated.has_next,
                        "has_prev": paginated.has_prev,
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
                    "message": "Failed to fetch notifications",
                    "error": str(e),
                }
            ),
            500,
        )


# 10. DELETE NOTIFICATION
@affiliateBP.route("/notifications/<int:notification_id>", methods=["DELETE"])
@middleware
def delete_notification(notification_id):
    try:
        dashboard = AffiliateDashboard.query.filter_by(user_id=g.user.id).first()
        if not dashboard:
            return jsonify({"status": "error", "message": "Dashboard not found"}), 404

        notification = Notification.query.filter_by(
            id=notification_id, affiliate_id=dashboard.id
        ).first()
        if not notification:
            return (
                jsonify({"status": "error", "message": "Notification not found"}),
                404,
            )

        db.session.delete(notification)
        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Notification deleted",
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
                    "message": "Failed to delete notification",
                    "error": str(e),
                }
            ),
            500,
        )
