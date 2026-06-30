from models.user import *
from models.admin import *
from flask import request, jsonify, Blueprint, g
from werkzeug.security import generate_password_hash, check_password_hash
from config.extension import *
from functions.helper_function import *
from functions.background_functions import *
import json, jwt
from functools import wraps
from datetime import datetime, timedelta, timezone
import os, calendar
from dotenv import load_dotenv

load_dotenv()

vendorBP = Blueprint("vendorBP", __name__, url_prefix="/vendor")


def clean(val):
    return val if val not in (None, "") else None


def vendor_middleware(f):
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
            if admin.role != "vendor":
                return (
                    jsonify({"status": "error", "message": "Vendor access required"}),
                    403,
                )

            vendor = admin.vendor_profile
            if not vendor:
                return (
                    jsonify({"status": "error", "message": "Vendor profile not found"}),
                    404,
                )
            if vendor.approval_status == "pending":
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Account pending admin approval",
                        }
                    ),
                    403,
                )
            if vendor.approval_status == "rejected":
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Vendor application was rejected",
                        }
                    ),
                    403,
                )
            if not vendor.is_active:
                return (
                    jsonify(
                        {"status": "error", "message": "Vendor account is disabled"}
                    ),
                    403,
                )

            g.admin = admin
            g.vendor = vendor
        except jwt.ExpiredSignatureError:
            return jsonify({"status": "error", "message": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"status": "error", "message": "Invalid token"}), 401

        return f(*args, **kwargs)

    return decorated


@vendorBP.route("/signup", methods=["POST"])
def vendor_signup():
    try:
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")
        store_name = data.get("store_name")

        missing = [
            name
            for name, val in [
                ("username", username),
                ("password", password),
                ("store_name", store_name),
            ]
            if not val
        ]
        if missing:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Missing fields: {', '.join(missing)}",
                    }
                ),
                400,
            )

        existing = Admin.query.filter_by(username=username).first()
        if existing:
            return (
                jsonify({"status": "error", "message": "Username already exists"}),
                409,
            )

        admin = Admin(
            username=username,
            password=generate_password_hash(password),
            role="vendor",
            phone_number=data.get("phone_number"),
            bio=data.get("bio"),
        )
        db.session.add(admin)
        db.session.flush()  # get admin.id before commit

        vendor = Vendor(
            admin_id=admin.id,
            store_name=store_name,
            store_description=clean(data.get("store_description")),
            gst_number=clean(data.get("gst_number")),
            upi_id=clean(data.get("upi_id")),
            approval_status="pending",
        )
        db.session.add(vendor)
        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Registration submitted. Awaiting admin approval.",
                    "id": admin.id,
                    "vendor_id": vendor.id,
                }
            ),
            201,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Failed to signup", "error": str(e)}
            ),
            500,
        )


@vendorBP.route("/login", methods=["POST"])
def vendor_login():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"status": "error", "message": "Invalid JSON body"}), 400

        username = data.get("username")
        password = data.get("password")
        if not username or not password:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Username and password are required",
                    }
                ),
                400,
            )

        admin = Admin.query.filter_by(username=username, role="vendor").first()
        if not admin or not check_password_hash(admin.password, password):
            return jsonify({"status": "error", "message": "Invalid credentials"}), 401

        vendor = admin.vendor_profile
        if not vendor:
            return (
                jsonify({"status": "error", "message": "Vendor profile not found"}),
                404,
            )

        if vendor.approval_status == "pending":
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Account pending admin approval",
                        "approval_status": "pending",
                    }
                ),
                403,
            )
        if vendor.approval_status == "rejected":
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Vendor application was rejected",
                        "approval_status": "rejected",
                    }
                ),
                403,
            )
        if not vendor.is_active:
            return (
                jsonify({"status": "error", "message": "Vendor account is disabled"}),
                403,
            )

        token = jwt.encode(
            {
                "id": admin.id,
                "username": admin.username,
                "role": admin.role,
                "exp": datetime.now(timezone.utc) + timedelta(days=7),
            },
            os.getenv("SECRET_KEY"),
            algorithm="HS256",
        )

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Login successful",
                    "token": token,
                    "admin": {
                        "id": admin.id,
                        "username": admin.username,
                        "role": admin.role,
                        "profile_picture": admin.profile_picture,
                        "phone_number": admin.phone_number,
                        "bio": admin.bio,
                    },
                    "vendor": {
                        "id": vendor.id,
                        "store_name": vendor.store_name,
                        "approval_status": vendor.approval_status,
                        "commission_rate": vendor.commission_rate,
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


@vendorBP.route("/logout", methods=["POST"])
@vendor_middleware
def vendor_logout():
    return jsonify({"status": "success", "message": "Logged out successfully"}), 200


@vendorBP.route("/profile", methods=["GET"])
@vendor_middleware
def get_vendor_profile():
    try:
        admin = g.admin
        vendor = g.vendor
        return (
            jsonify(
                {
                    "status": "success",
                    "admin": {
                        "id": admin.id,
                        "username": admin.username,
                        "role": admin.role,
                        "profile_picture": admin.profile_picture,
                        "phone_number": admin.phone_number,
                        "bio": admin.bio,
                        "created_at": admin.created_at,
                        "updated_at": admin.updated_at,
                    },
                    "vendor": {
                        "id": vendor.id,
                        "store_name": vendor.store_name,
                        "store_description": vendor.store_description,
                        "gst_number": vendor.gst_number,
                        "upi_id": vendor.upi_id,
                        "bank_account_number": vendor.bank_account_number,
                        "bank_ifsc": vendor.bank_ifsc,
                        "bank_account_holder": vendor.bank_account_holder,
                        "commission_rate": vendor.commission_rate,
                        "approval_status": vendor.approval_status,
                        "is_active": vendor.is_active,
                        "created_at": vendor.created_at,
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
                    "message": "Failed to fetch profile",
                    "error": str(e),
                }
            ),
            500,
        )


@vendorBP.route("/profile", methods=["PUT"])
@vendor_middleware
def update_vendor_profile():
    try:
        admin = g.admin
        vendor = g.vendor
        data = request.get_json()

        if "username" in data:
            existing = Admin.query.filter_by(username=data["username"]).first()
            if existing and existing.id != admin.id:
                return (
                    jsonify({"status": "error", "message": "Username already taken"}),
                    409,
                )
            admin.username = data["username"]

        if "password" in data:
            admin.password = generate_password_hash(data["password"])

        admin.phone_number = data.get("phone_number", admin.phone_number)
        admin.bio = data.get("bio", admin.bio)
        admin.profile_picture = data.get("profile_picture", admin.profile_picture)

        vendor.store_name = data.get("store_name", vendor.store_name)
        vendor.store_description = data.get(
            "store_description", vendor.store_description
        )
        vendor.gst_number = data.get("gst_number", vendor.gst_number)
        vendor.upi_id = data.get("upi_id", vendor.upi_id)
        vendor.bank_account_number = data.get(
            "bank_account_number", vendor.bank_account_number
        )
        vendor.bank_ifsc = data.get("bank_ifsc", vendor.bank_ifsc)
        vendor.bank_account_holder = data.get(
            "bank_account_holder", vendor.bank_account_holder
        )

        db.session.commit()
        return (
            jsonify({"status": "success", "message": "Profile updated successfully"}),
            200,
        )
    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to update profile",
                    "error": str(e),
                }
            ),
            500,
        )


# Products
@vendorBP.route("/product", methods=["POST"])
@vendor_middleware
def create_vendor_product():
    try:
        vendor = g.vendor
        data = request.form

        existing = Products.query.filter_by(sku=data.get("sku")).first()
        if existing:
            return jsonify({"status": "error", "message": "SKU already exists"}), 409

        main_image_file = request.files.get("product_image")
        if not main_image_file:
            return (
                jsonify({"status": "error", "message": "product_image is required"}),
                400,
            )

        product_image_url = upload_file(main_image_file, folder="products")

        additional_files = request.files.getlist("product_images")
        product_images_urls = (
            upload_file(additional_files, folder="products") if additional_files else []
        )

        category_id = to_int(data.get("category_id"))
        price = to_float(data.get("price"))
        compare_at = to_float(data.get("compare_at_price"))
        stock = to_int(data.get("stock"))
        unit_price = to_float(data.get("unit_price"))
        charge_tax = to_bool(data.get("charge_tax"))
        tax_rate = to_float(data.get("tax_rate"), default=0.0)
        cost_price = to_float(data.get("cost_price"))
        weight = to_float(data.get("weight"))
        quantity = to_int(data.get("quantity"))
        sell_oos = to_bool(data.get("sell_when_out_of_stock"))

        if category_id is None:
            return jsonify({"status": "error", "message": "Category is required"}), 400
        if price is None:
            return jsonify({"status": "error", "message": "Price is required"}), 400
        if stock is None:
            return jsonify({"status": "error", "message": "Stock is required"}), 400
        if quantity is None:
            return jsonify({"status": "error", "message": "Quantity is required"}), 400

        product = Products(
            category_id=category_id,
            vendor_id=vendor.id,
            name=data.get("name"),
            description=clean(data.get("description")),
            product_image=product_image_url,
            product_images=product_images_urls,
            sizes=json.loads(data.get("sizes", "[]")),
            colors=json.loads(data.get("colors", "[]")),
            price=price,
            compare_at_price=compare_at,
            stock=stock,
            unit_price=unit_price,
            charge_tax=charge_tax,
            tax_rate=tax_rate,
            cost_price=cost_price,
            sku=data.get("sku"),
            barcode=clean(data.get("barcode")),
            country_of_origin=clean(data.get("country_of_origin")),
            weight=weight,
            weight_unit=clean(data.get("weight_unit")),
            product_type=clean(data.get("product_type")),
            sell_when_out_of_stock=sell_oos,
            quantity=quantity,
            status="pending_review",
        )
        db.session.add(product)
        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Product submitted for review",
                    "id": product.id,
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
                    "message": "Failed to create product",
                    "error": str(e),
                }
            ),
            500,
        )


@vendorBP.route("/product/<int:product_id>", methods=["PUT"])
@vendor_middleware
def update_vendor_product(product_id):
    try:
        vendor = g.vendor
        product = Products.query.get(product_id)
        if not product:
            return jsonify({"status": "error", "message": "Product not found"}), 404
        if product.vendor_id != vendor.id:
            return jsonify({"status": "error", "message": "Not your product"}), 403

        data = request.form

        if data.get("sku") and data.get("sku") != product.sku:
            existing = Products.query.filter_by(sku=data.get("sku")).first()
            if existing:
                return (
                    jsonify({"status": "error", "message": "SKU already exists"}),
                    409,
                )
            product.sku = data.get("sku")

        main_image_file = request.files.get("product_image")
        if main_image_file:
            product.product_image = upload_file(main_image_file, folder="products")

        additional_files = request.files.getlist("product_images")
        if additional_files:
            product.product_images = upload_file(additional_files, folder="products")

        if "category_id" in data:
            product.category_id = to_int(data.get("category_id"))
        if "name" in data:
            product.name = data.get("name")
        if "description" in data:
            product.description = clean(data.get("description"))
        if "sizes" in data:
            product.sizes = json.loads(data.get("sizes", "[]"))
        if "colors" in data:
            product.colors = json.loads(data.get("colors", "[]"))
        if "price" in data:
            product.price = to_float(data.get("price"))
        if "compare_at_price" in data:
            product.compare_at_price = to_float(data.get("compare_at_price"))
        if "stock" in data:
            product.stock = to_int(data.get("stock"))
        if "unit_price" in data:
            product.unit_price = to_float(data.get("unit_price"))
        if "charge_tax" in data:
            product.charge_tax = to_bool(data.get("charge_tax"))
        if "tax_rate" in data:
            product.tax_rate = to_float(data.get("tax_rate"), default=0.0)
        if "cost_price" in data:
            product.cost_price = to_float(data.get("cost_price"))
        if "barcode" in data:
            product.barcode = clean(data.get("barcode"))
        if "country_of_origin" in data:
            product.country_of_origin = clean(data.get("country_of_origin"))
        if "weight" in data:
            product.weight = to_float(data.get("weight"))
        if "weight_unit" in data:
            product.weight_unit = clean(data.get("weight_unit"))
        if "product_type" in data:
            product.product_type = clean(data.get("product_type"))
        if "sell_when_out_of_stock" in data:
            product.sell_when_out_of_stock = to_bool(data.get("sell_when_out_of_stock"))
        if "quantity" in data:
            product.quantity = to_int(data.get("quantity"))

        # Any edit to a previously approved/rejected product sends it back for re-review.
        if product.status in ("active", "rejected"):
            product.status = "pending_review"

        db.session.commit()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Product updated and submitted for re-review",
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
                    "message": "Failed to update product",
                    "error": str(e),
                }
            ),
            500,
        )


@vendorBP.route("/product/<int:product_id>", methods=["GET"])
@vendor_middleware
def get_vendor_product(product_id):
    try:
        vendor = g.vendor
        product = Products.query.get(product_id)
        if not product:
            return jsonify({"status": "error", "message": "Product not found"}), 404
        if product.vendor_id != vendor.id:
            return jsonify({"status": "error", "message": "Not your product"}), 403

        return (
            jsonify(
                {
                    "status": "success",
                    "product": {
                        "id": product.id,
                        "name": product.name,
                        "description": product.description,
                        "product_image": product.product_image,
                        "product_images": product.product_images,
                        "category_id": product.category_id,
                        "category": (
                            product.category.name if product.category else None
                        ),
                        "sizes": product.sizes,
                        "colors": product.colors,
                        "price": product.price,
                        "compare_at_price": product.compare_at_price,
                        "stock": product.stock,
                        "unit_price": product.unit_price,
                        "charge_tax": product.charge_tax,
                        "tax_rate": product.tax_rate,
                        "cost_price": product.cost_price,
                        "sku": product.sku,
                        "barcode": product.barcode,
                        "country_of_origin": product.country_of_origin,
                        "weight": product.weight,
                        "weight_unit": product.weight_unit,
                        "product_type": product.product_type,
                        "sell_when_out_of_stock": product.sell_when_out_of_stock,
                        "quantity": product.quantity,
                        "status": product.status,
                        "created_at": product.created_at,
                        "updated_at": product.updated_at,
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
                    "message": "Failed to fetch product",
                    "error": str(e),
                }
            ),
            500,
        )


@vendorBP.route("/product", methods=["GET"])
@vendor_middleware
def get_vendor_products():
    try:
        vendor = g.vendor
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)
        status = request.args.get("status")
        search = request.args.get("search")

        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")
        allowed_sort_fields = [
            "created_at",
            "updated_at",
            "price",
            "stock",
            "quantity",
            "name",
        ]
        if sort_by not in allowed_sort_fields:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Invalid sort_by field. Allowed: {', '.join(allowed_sort_fields)}",
                    }
                ),
                400,
            )

        query = Products.query.filter(Products.vendor_id == vendor.id)

        if status:
            query = query.filter(Products.status == status)
        if search:
            query = query.filter(
                db.or_(
                    Products.name.ilike(f"%{search}%"),
                    Products.sku.ilike(f"%{search}%"),
                )
            )

        sort_column = getattr(Products, sort_by)
        query = query.order_by(
            sort_column.desc() if sort_order == "desc" else sort_column.asc()
        )

        pagination = query.paginate(page=page, per_page=limit, error_out=False)

        products = [
            {
                "id": p.id,
                "name": p.name,
                "product_image": p.product_image,
                "price": p.price,
                "compare_at_price": p.compare_at_price,
                "stock": p.stock,
                "quantity": p.quantity,
                "sku": p.sku,
                "status": p.status,
                "created_at": p.created_at,
                "updated_at": p.updated_at,
            }
            for p in pagination.items
        ]

        return (
            jsonify(
                {
                    "status": "success",
                    "products": products,
                    "total": pagination.total,
                    "pages": pagination.pages,
                    "page": page,
                    "limit": limit,
                }
            ),
            200,
        )
    except Exception as e:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to fetch products",
                    "error": str(e),
                }
            ),
            500,
        )


@vendorBP.route("/product", methods=["DELETE"])
@vendor_middleware
def delete_vendor_products():
    try:
        vendor = g.vendor
        data = request.get_json()
        ids = data.get("ids", [])

        if not ids:
            return (
                jsonify({"status": "error", "message": "No product ids provided"}),
                400,
            )
        if len(ids) > 10:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Maximum 10 products can be deleted at once",
                    }
                ),
                400,
            )

        products = Products.query.filter(
            Products.id.in_(ids), Products.vendor_id == vendor.id
        ).all()

        if not products:
            return jsonify({"status": "error", "message": "No products found"}), 404

        for product in products:
            db.session.delete(product)

        db.session.commit()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": f"{len(products)} product(s) deleted successfully",
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
                    "message": "Failed to delete products",
                    "error": str(e),
                }
            ),
            500,
        )


REVENUE_STATUSES = ["pending", "processing", "shipped", "delivered"]


@vendorBP.route("/orders", methods=["GET"])
@vendor_middleware
def get_vendor_orders():
    try:
        vendor = g.vendor
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)
        status = request.args.get("status")
        from_date = request.args.get("from_date")
        to_date = request.args.get("to_date")

        order_ids_subq = (
            db.session.query(OrderedItems.order_id)
            .join(Products, Products.id == OrderedItems.product_id)
            .filter(Products.vendor_id == vendor.id)
            .distinct()
            .subquery()
        )

        query = Orders.query.filter(
            Orders.id.in_(db.session.query(order_ids_subq.c.order_id))
        )

        if status:
            query = query.filter(Orders.status == status)
        if from_date:
            query = query.filter(
                Orders.created_at >= datetime.strptime(from_date, "%Y-%m-%d")
            )
        if to_date:
            query = query.filter(
                Orders.created_at <= datetime.strptime(to_date, "%Y-%m-%d")
            )

        query = query.order_by(Orders.created_at.desc())
        pagination = query.paginate(page=page, per_page=limit, error_out=False)

        orders = []
        for o in pagination.items:
            vendor_items = (
                db.session.query(OrderedItems)
                .join(Products, Products.id == OrderedItems.product_id)
                .filter(OrderedItems.order_id == o.id, Products.vendor_id == vendor.id)
                .all()
            )
            vendor_subtotal = round(sum(i.total_price for i in vendor_items), 2)

            orders.append(
                {
                    "id": o.id,
                    "order_id": o.order_id,
                    "status": o.status,
                    "payment_status": o.payment_status,
                    "payment_method": o.payment_method,
                    "created_at": o.created_at,
                    "updated_at": o.updated_at,
                    "items": [
                        {
                            "id": i.id,
                            "product_id": i.product_id,
                            "product_name": i.product_name,
                            "product_sku": i.product_sku,
                            "product_image": i.product_image,
                            "quantity": i.quantity,
                            "unit_price": i.unit_price,
                            "total_price": i.total_price,
                        }
                        for i in vendor_items
                    ],
                    "vendor_subtotal": vendor_subtotal,
                }
            )

        return (
            jsonify(
                {
                    "status": "success",
                    "orders": orders,
                    "total": pagination.total,
                    "pages": pagination.pages,
                    "page": page,
                    "limit": limit,
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


@vendorBP.route("/orders/<int:order_id>", methods=["GET"])
@vendor_middleware
def get_vendor_order(order_id):
    try:
        vendor = g.vendor
        order = Orders.query.get(order_id)
        if not order:
            return jsonify({"status": "error", "message": "Order not found"}), 404

        vendor_items = (
            db.session.query(OrderedItems)
            .join(Products, Products.id == OrderedItems.product_id)
            .filter(OrderedItems.order_id == order.id, Products.vendor_id == vendor.id)
            .all()
        )
        if not vendor_items:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "No items from your store in this order",
                    }
                ),
                403,
            )

        vendor_subtotal = round(sum(i.total_price for i in vendor_items), 2)

        return (
            jsonify(
                {
                    "status": "success",
                    "order": {
                        "id": order.id,
                        "order_id": order.order_id,
                        "status": order.status,
                        "payment_status": order.payment_status,
                        "payment_method": order.payment_method,
                        "shipping_address": order.shipping_address,
                        "tracking_url": order.tracking_url,
                        "created_at": order.created_at,
                        "updated_at": order.updated_at,
                        "items": [
                            {
                                "id": i.id,
                                "product_id": i.product_id,
                                "product_name": i.product_name,
                                "product_sku": i.product_sku,
                                "product_image": i.product_image,
                                "quantity": i.quantity,
                                "unit_price": i.unit_price,
                                "tax_rate": i.tax_rate,
                                "tax_amount": i.tax_amount,
                                "discount": i.discount,
                                "total_price": i.total_price,
                            }
                            for i in vendor_items
                        ],
                        "vendor_subtotal": vendor_subtotal,
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


@vendorBP.route("/dashboard", methods=["GET"])
@vendor_middleware
def vendor_dashboard():
    try:
        vendor = g.vendor

        order_ids_subq = (
            db.session.query(OrderedItems.order_id)
            .join(Products, Products.id == OrderedItems.product_id)
            .filter(Products.vendor_id == vendor.id)
            .distinct()
            .subquery()
        )

        vendor_orders = Orders.query.filter(
            Orders.id.in_(db.session.query(order_ids_subq.c.order_id))
        ).all()

        status_counts = {
            "pending": 0,
            "processing": 0,
            "shipped": 0,
            "delivered": 0,
            "cancelled": 0,
            "returned": 0,
        }
        for o in vendor_orders:
            if o.status in status_counts:
                status_counts[o.status] += 1

        vendor_items_all = (
            db.session.query(OrderedItems, Orders.status, Orders.created_at)
            .join(Orders, Orders.id == OrderedItems.order_id)
            .join(Products, Products.id == OrderedItems.product_id)
            .filter(Products.vendor_id == vendor.id)
            .all()
        )

        gross_revenue = round(
            sum(
                item.total_price
                for item, status, created_at in vendor_items_all
                if status in REVENUE_STATUSES
            ),
            2,
        )
        commission_amount = round(gross_revenue * (vendor.commission_rate / 100), 2)
        net_payable = round(gross_revenue - commission_amount, 2)

        now = datetime.utcnow()
        this_month_start = datetime(now.year, now.month, 1)
        month_gross = round(
            sum(
                item.total_price
                for item, status, created_at in vendor_items_all
                if status in REVENUE_STATUSES and created_at >= this_month_start
            ),
            2,
        )
        month_commission = round(month_gross * (vendor.commission_rate / 100), 2)
        month_net = round(month_gross - month_commission, 2)
        month_orders_count = len(
            {o.id for o in vendor_orders if o.created_at >= this_month_start}
        )

        month_param = request.args.get("month")
        filtered = None
        if month_param:
            try:
                year, month = map(int, month_param.split("-"))
                f_start = datetime(year, month, 1)
                last_day = calendar.monthrange(year, month)[1]
                f_end = datetime(year, month, last_day, 23, 59, 59)
            except (ValueError, TypeError):
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "month must be in YYYY-MM format",
                        }
                    ),
                    400,
                )

            f_gross = round(
                sum(
                    item.total_price
                    for item, status, created_at in vendor_items_all
                    if status in REVENUE_STATUSES and f_start <= created_at <= f_end
                ),
                2,
            )
            f_commission = round(f_gross * (vendor.commission_rate / 100), 2)
            f_orders_count = len(
                {o.id for o in vendor_orders if f_start <= o.created_at <= f_end}
            )
            filtered = {
                "month": month_param,
                "orders": f_orders_count,
                "gross_revenue": f_gross,
                "platform_commission": f_commission,
                "net_payable": round(f_gross - f_commission, 2),
            }

        total_paid_out = (
            db.session.query(db.func.coalesce(db.func.sum(VendorPayout.amount), 0.0))
            .filter(
                VendorPayout.vendor_id == vendor.id, VendorPayout.status == "approved"
            )
            .scalar()
        )
        total_pending_payout = (
            db.session.query(db.func.coalesce(db.func.sum(VendorPayout.amount), 0.0))
            .filter(
                VendorPayout.vendor_id == vendor.id, VendorPayout.status == "pending"
            )
            .scalar()
        )
    
        available_balance = round(
            net_payable - total_paid_out - total_pending_payout, 2
        )

        today = datetime.utcnow().date()
        today_orders = [o for o in vendor_orders if o.created_at.date() == today]

        product_query = Products.query.filter(Products.vendor_id == vendor.id)
        total_products = product_query.count()
        active_products = product_query.filter(Products.status == "active").count()
        pending_products = product_query.filter(
            Products.status == "pending_review"
        ).count()
        low_stock = product_query.filter(Products.stock <= 5).count()

        return (
            jsonify(
                {
                    "status": "success",
                    "dashboard": {
                        "cards": {
                            "total_orders": len(vendor_orders),
                            "today_orders": len(today_orders),
                            "gross_revenue": gross_revenue,
                            "platform_commission": commission_amount,
                            "net_payable": net_payable,
                            "available_balance": available_balance,
                            "total_paid_out": round(total_paid_out, 2),
                            "total_pending_payout": round(total_pending_payout, 2),
                            "total_products": total_products,
                            "active_products": active_products,
                            "pending_products": pending_products,
                            "low_stock_count": low_stock,
                        },
                        "this_month": {
                            "orders": month_orders_count,
                            "gross_revenue": month_gross,
                            "platform_commission": month_commission,
                            "net_payable": month_net,
                        },
                        "filtered_month": filtered,
                        "order_status_breakdown": status_counts,
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


# Payouts
@vendorBP.route("/payout-request", methods=["POST"])
@vendor_middleware
def request_vendor_payout():
    try:
        vendor = g.vendor
        data = request.get_json()
        amount = to_float(data.get("amount"))

        if not amount or amount <= 0:
            return (
                jsonify({"status": "error", "message": "Valid amount required"}),
                400,
            )

        total_revenue = (
            db.session.query(
                db.func.coalesce(db.func.sum(OrderedItems.total_price), 0.0)
            )
            .join(Products, Products.id == OrderedItems.product_id)
            .filter(Products.vendor_id == vendor.id)
            .scalar()
        )

        commission_owed = total_revenue * (vendor.commission_rate / 100.0)
        net_earnings = total_revenue - commission_owed

        already_paid_out = (
            db.session.query(db.func.coalesce(db.func.sum(VendorPayout.amount), 0.0))
            .filter(
                VendorPayout.vendor_id == vendor.id,
                VendorPayout.status == "approved",
            )
            .scalar()
        )

        already_pending = (
            db.session.query(db.func.coalesce(db.func.sum(VendorPayout.amount), 0.0))
            .filter(
                VendorPayout.vendor_id == vendor.id,
                VendorPayout.status == "pending",
            )
            .scalar()
        )

        available_balance = net_earnings - already_paid_out - already_pending

        if amount > available_balance:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Requested amount exceeds available balance of ₹{round(available_balance, 2)}",
                        "available_balance": round(available_balance, 2),
                    }
                ),
                400,
            )

        payout = VendorPayout(
            vendor_id=vendor.id,
            amount=amount,
            note=clean(data.get("note")),
        )
        db.session.add(payout)
        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Payout request submitted",
                    "id": payout.id,
                    "remaining_balance": round(available_balance - amount, 2),
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
                    "message": "Failed to submit payout request",
                    "error": str(e),
                }
            ),
            500,
        )


@vendorBP.route("/payout-request", methods=["GET"])
@vendor_middleware
def get_vendor_payouts():
    try:
        vendor = g.vendor
        payouts = (
            VendorPayout.query.filter_by(vendor_id=vendor.id)
            .order_by(VendorPayout.created_at.desc())
            .all()
        )
        return (
            jsonify(
                {
                    "status": "success",
                    "payouts": [
                        {
                            "id": p.id,
                            "amount": p.amount,
                            "status": p.status,
                            "payment_screenshot": p.payment_screenshot,
                            "note": p.note,
                            "created_at": p.created_at,
                            "updated_at": p.updated_at,
                        }
                        for p in payouts
                    ],
                }
            ),
            200,
        )
    except Exception as e:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to fetch payouts",
                    "error": str(e),
                }
            ),
            500,
        )
