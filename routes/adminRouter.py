from models.user import *
from models.admin import *
from flask import request, jsonify, Blueprint, g
from werkzeug.security import generate_password_hash, check_password_hash
from config.extension import *
from functions.helper_function import *
from functions.background_functions import *
from functions.wallet_helper import credit_wallet, debit_wallet, get_or_create_wallet
import json, jwt
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

adminBP = Blueprint("admin", __name__, url_prefix="/admin")


@adminBP.route("/signup", methods=["POST"])
def signup():
    data = request.get_json()
    try:
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return (
                jsonify(
                    {"status": "error", "message": "Username and password are required"}
                ),
                400,
            )

        existing = Admin.query.filter_by(username=username).first()
        if existing:
            return (
                jsonify({"status": "error", "message": "Username already exists"}),
                409,
            )

        hashed_password = generate_password_hash(password)
        admin = Admin(
            username=username,
            password=hashed_password,
            role=data.get("role", "admin"),
            phone_number=data.get("phone_number"),
            bio=data.get("bio"),
        )
        db.session.add(admin)
        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Admin created successfully",
                    "id": admin.id,
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


@adminBP.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"status": "error", "message": "Invalid JSON body"}), 400

        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return (
                jsonify(
                    {"status": "error", "message": "Username and password are required"}
                ),
                400,
            )

        admin = Admin.query.filter_by(username=username).first()
        if not admin or not check_password_hash(admin.password, password):
            return jsonify({"status": "error", "message": "Invalid credentials"}), 401

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
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify({"status": "error", "message": "Failed to login", "error": str(e)}),
            500,
        )


@adminBP.route("/logout", methods=["POST"])
@admin_middleware
def logout():
    return jsonify({"status": "success", "message": "Logged out successfully"}), 200


@adminBP.route("/profile", methods=["GET"])
@admin_middleware
def get_admin():
    try:
        admin = g.admin
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


@adminBP.route("/profile", methods=["PUT"])
@admin_middleware
def update_admin():
    try:
        admin = g.admin
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


@adminBP.route("/product", methods=["POST"])
@admin_middleware
def create_product():
    try:
        content_type = request.content_type or ""

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

        def clean(val):
            """Convert empty string to None for optional unique/nullable fields."""
            return val if val not in (None, "") else None

        if "application/json" in content_type:
            data = request.get_json()
            products_data = data if isinstance(data, list) else [data]

            if len(products_data) > 10:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Maximum 10 products allowed at once",
                        }
                    ),
                    400,
                )

            created = []
            for item in products_data:
                existing = Products.query.filter_by(sku=item.get("sku")).first()
                if existing:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": f"SKU {item.get('sku')} already exists",
                            }
                        ),
                        409,
                    )

                product = Products(
                    category_id=item.get("category_id"),
                    name=item.get("name"),
                    description=clean(item.get("description")),
                    product_image=item.get("product_image"),
                    product_images=item.get("product_images", []),
                    sizes=item.get("sizes", []),
                    colors=item.get("colors", []),
                    price=item.get("price"),
                    compare_at_price=item.get("compare_at_price"),
                    stock=item.get("stock"),
                    unit_price=item.get("unit_price"),
                    charge_tax=item.get("charge_tax", False),
                    tax_rate=item.get("tax_rate"),
                    cost_price=item.get("cost_price"),
                    sku=item.get("sku"),
                    barcode=clean(item.get("barcode")),
                    country_of_origin=clean(item.get("country_of_origin")),
                    weight=item.get("weight"),
                    weight_unit=clean(item.get("weight_unit")),
                    product_type=clean(item.get("product_type")),
                    sell_when_out_of_stock=item.get("sell_when_out_of_stock", False),
                    quantity=item.get("quantity"),
                    status=item.get("status", "active"),
                )
                db.session.add(product)
                created.append(product)

            db.session.commit()
            return (
                jsonify(
                    {
                        "status": "success",
                        "message": f"{len(created)} product(s) created successfully",
                        "ids": [p.id for p in created],
                    }
                ),
                201,
            )

        else:
            data = request.form

            existing = Products.query.filter_by(sku=data.get("sku")).first()
            if existing:
                return (
                    jsonify({"status": "error", "message": "SKU already exists"}),
                    409,
                )

            main_image_file = request.files.get("product_image")
            if not main_image_file:
                return (
                    jsonify(
                        {"status": "error", "message": "product_image is required"}
                    ),
                    400,
                )

            product_image_url = upload_file(main_image_file, folder="products")

            additional_files = request.files.getlist("product_images")
            product_images_urls = (
                upload_file(additional_files, folder="products")
                if additional_files
                else []
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
                return (
                    jsonify({"status": "error", "message": "Category is required"}),
                    400,
                )
            if price is None:
                return jsonify({"status": "error", "message": "Price is required"}), 400
            if stock is None:
                return jsonify({"status": "error", "message": "Stock is required"}), 400
            if quantity is None:
                return (
                    jsonify({"status": "error", "message": "Quantity is required"}),
                    400,
                )

            product = Products(
                category_id=category_id,
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
                status=data.get("status", "active"),
            )
            db.session.add(product)
            db.session.commit()

            return (
                jsonify(
                    {
                        "status": "success",
                        "message": "Product created successfully",
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


@adminBP.route("/product/<int:product_id>", methods=["PUT"])
@admin_middleware
def update_product(product_id):
    try:
        product = Products.query.get(product_id)
        if not product:
            return jsonify({"status": "error", "message": "Product not found"}), 404

        content_type = request.content_type or ""

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

        def clean(val):
            return val if val not in (None, "") else None

        if "multipart/form-data" in content_type:
            data = request.form

            if "product_image" in request.files:
                product.product_image = upload_file(
                    request.files["product_image"], folder="products"
                )

            additional_files = request.files.getlist("product_images")
            if additional_files:
                product.product_images = upload_file(
                    additional_files, folder="products"
                )

            if "sizes" in data:
                product.sizes = json.loads(data.get("sizes"))
            if "colors" in data:
                product.colors = json.loads(data.get("colors"))

            coerce_map = {
                "category_id": lambda v: to_int(v),
                "price": lambda v: to_float(v),
                "compare_at_price": lambda v: to_float(v),
                "stock": lambda v: to_int(v),
                "unit_price": lambda v: to_float(v),
                "charge_tax": lambda v: to_bool(v),
                "tax_rate": lambda v: to_float(v, default=0.0),
                "cost_price": lambda v: to_float(v),
                "weight": lambda v: to_float(v),
                "quantity": lambda v: to_int(v),
                "sell_when_out_of_stock": lambda v: to_bool(v),
                # clean fields — empty string → None
                "barcode": lambda v: clean(v),
                "country_of_origin": lambda v: clean(v),
                "weight_unit": lambda v: clean(v),
                "product_type": lambda v: clean(v),
                "description": lambda v: clean(v),
            }

            fields = [
                "name",
                "description",
                "category_id",
                "price",
                "compare_at_price",
                "stock",
                "unit_price",
                "charge_tax",
                "tax_rate",
                "cost_price",
                "barcode",
                "country_of_origin",
                "weight",
                "weight_unit",
                "product_type",
                "sell_when_out_of_stock",
                "quantity",
                "status",
            ]
            for field in fields:
                value = data.get(field)
                if value is not None:
                    coerced = coerce_map[field](value) if field in coerce_map else value
                    setattr(product, field, coerced)

            if "sku" in data:
                existing = Products.query.filter_by(sku=data["sku"]).first()
                if existing and existing.id != product_id:
                    return (
                        jsonify({"status": "error", "message": "SKU already exists"}),
                        409,
                    )
                product.sku = data["sku"]

        else:
            data = request.get_json()

            if "sizes" in data:
                product.sizes = data["sizes"]
            if "colors" in data:
                product.colors = data["colors"]
            if "product_image" in data:
                product.product_image = data["product_image"]
            if "product_images" in data:
                product.product_images = data["product_images"]

            fields = [
                "name",
                "description",
                "category_id",
                "price",
                "compare_at_price",
                "stock",
                "unit_price",
                "charge_tax",
                "tax_rate",
                "cost_price",
                "barcode",
                "country_of_origin",
                "weight",
                "weight_unit",
                "product_type",
                "sell_when_out_of_stock",
                "quantity",
                "status",
            ]
            clean_fields = {
                "barcode",
                "country_of_origin",
                "weight_unit",
                "product_type",
                "description",
            }

            for field in fields:
                if field in data:
                    value = data[field]
                    setattr(
                        product, field, clean(value) if field in clean_fields else value
                    )

            if "sku" in data:
                existing = Products.query.filter_by(sku=data["sku"]).first()
                if existing and existing.id != product_id:
                    return (
                        jsonify({"status": "error", "message": "SKU already exists"}),
                        409,
                    )
                product.sku = data["sku"]

        db.session.commit()
        return (
            jsonify({"status": "success", "message": "Product updated successfully"}),
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


@adminBP.route("/product/bulk-update", methods=["PUT"])
@admin_middleware
def bulk_update_products():
    try:
        data = request.get_json()
        ids = data.get("ids", [])
        updates = data.get("updates", {})

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
                        "message": "Maximum 10 products can be updated at once",
                    }
                ),
                400,
            )
        if not updates:
            return jsonify({"status": "error", "message": "No updates provided"}), 400

        allowed_fields = [
            "category_id",
            "status",
            "price",
            "compare_at_price",
            "stock",
            "charge_tax",
            "tax_rate",
            "cost_price",
            "country_of_origin",
            "weight",
            "weight_unit",
            "product_type",
            "sell_when_out_of_stock",
        ]
        clean_fields = {"country_of_origin", "weight_unit", "product_type"}

        invalid_fields = [f for f in updates if f not in allowed_fields]
        if invalid_fields:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Fields not allowed in bulk update: {', '.join(invalid_fields)}",
                    }
                ),
                400,
            )

        products = Products.query.filter(Products.id.in_(ids)).all()
        if not products:
            return jsonify({"status": "error", "message": "No products found"}), 404

        if "category_id" in updates:
            category = Category.query.get(updates["category_id"])
            if not category:
                return (
                    jsonify({"status": "error", "message": "Category not found"}),
                    404,
                )

        for product in products:
            for field, value in updates.items():
                setattr(
                    product,
                    field,
                    (
                        (value if value not in (None, "") else None)
                        if field in clean_fields
                        else value
                    ),
                )

        db.session.commit()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": f"{len(products)} product(s) updated successfully",
                    "ids": [p.id for p in products],
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
                    "message": "Failed to bulk update products",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/product/stats", methods=["GET"])
@admin_middleware
def get_product_stats():
    total = Products.query.count()
    active = Products.query.filter(Products.status == "active").count()
    out_of_stock = Products.query.filter(Products.stock <= 10).count()
    draft = Products.query.filter(Products.status == "draft").count()
    return (
        jsonify(
            {
                "status": "success",
                "total": total,
                "active": active,
                "out_of_stock": out_of_stock,
                "draft": draft,
            }
        ),
        200,
    )


@adminBP.route("/product/<int:product_id>", methods=["GET"])
@admin_middleware
def get_product(product_id):
    try:
        product = Products.query.get(product_id)
        if not product:
            return jsonify({"status": "error", "message": "Product not found"}), 404

        reviews = product.product_reviews
        ratings = [r.rating for r in reviews]

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
                        "category": product.category.name if product.category else None,
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
                        "ratings": {
                            "average": (
                                round(sum(ratings) / len(ratings), 2) if ratings else 0
                            ),
                            "total": len(ratings),
                            "breakdown": {
                                i: sum(1 for r in reviews if r.rating == i)
                                for i in range(1, 6)
                            },
                        },
                        "reviews": [
                            {
                                "id": r.id,
                                "rating": r.rating,
                                "review": r.review,
                                "user": {
                                    "id": r.user_id,
                                    "username": (
                                        User.query.get(r.user_id).username
                                        if User.query.get(r.user_id)
                                        else None
                                    ),
                                    "profile_picture": (
                                        User.query.get(r.user_id).profile_picture
                                        if User.query.get(r.user_id)
                                        else None
                                    ),
                                },
                                "created_at": r.created_at,
                            }
                            for r in reviews
                        ],
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


@adminBP.route("/product", methods=["GET"])
@admin_middleware
def get_products():
    try:
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)

        # filters
        status = request.args.get("status")
        category_id = request.args.get("category_id", type=int)
        search = request.args.get("search")
        product_type = request.args.get("product_type")
        country_of_origin = request.args.get("country_of_origin")
        weight_unit = request.args.get("weight_unit")
        charge_tax = request.args.get("charge_tax")
        sell_when_out_of_stock = request.args.get("sell_when_out_of_stock")

        # range filters
        min_price = request.args.get("min_price", type=float)
        max_price = request.args.get("max_price", type=float)
        min_compare_at_price = request.args.get("min_compare_at_price", type=float)
        max_compare_at_price = request.args.get("max_compare_at_price", type=float)
        min_stock = request.args.get("min_stock", type=int)
        max_stock = request.args.get("max_stock", type=int)
        min_quantity = request.args.get("min_quantity", type=int)
        max_quantity = request.args.get("max_quantity", type=int)
        min_cost_price = request.args.get("min_cost_price", type=float)
        max_cost_price = request.args.get("max_cost_price", type=float)
        min_weight = request.args.get("min_weight", type=float)
        max_weight = request.args.get("max_weight", type=float)

        # sort
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")

        allowed_sort_fields = [
            "created_at",
            "updated_at",
            "price",
            "compare_at_price",
            "stock",
            "quantity",
            "cost_price",
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

        query = Products.query

        # exact filters
        if status:
            query = query.filter(Products.status == status)
        if category_id:
            query = query.filter(Products.category_id == category_id)
        if product_type:
            query = query.filter(Products.product_type == product_type)
        if country_of_origin:
            query = query.filter(Products.country_of_origin == country_of_origin)
        if weight_unit:
            query = query.filter(Products.weight_unit == weight_unit)
        if charge_tax is not None:
            query = query.filter(Products.charge_tax == (charge_tax.lower() == "true"))
        if sell_when_out_of_stock is not None:
            query = query.filter(
                Products.sell_when_out_of_stock
                == (sell_when_out_of_stock.lower() == "true")
            )

        # search
        if search:
            query = query.filter(
                db.or_(
                    Products.name.ilike(f"%{search}%"),
                    Products.description.ilike(f"%{search}%"),
                    Products.sku.ilike(f"%{search}%"),
                    Products.barcode.ilike(f"%{search}%"),
                )
            )

        # range filters
        if min_price is not None:
            query = query.filter(Products.price >= min_price)
        if max_price is not None:
            query = query.filter(Products.price <= max_price)
        if min_compare_at_price is not None:
            query = query.filter(Products.compare_at_price >= min_compare_at_price)
        if max_compare_at_price is not None:
            query = query.filter(Products.compare_at_price <= max_compare_at_price)
        if min_stock is not None:
            query = query.filter(Products.stock >= min_stock)
        if max_stock is not None:
            query = query.filter(Products.stock <= max_stock)
        if min_quantity is not None:
            query = query.filter(Products.quantity >= min_quantity)
        if max_quantity is not None:
            query = query.filter(Products.quantity <= max_quantity)
        if min_cost_price is not None:
            query = query.filter(Products.cost_price >= min_cost_price)
        if max_cost_price is not None:
            query = query.filter(Products.cost_price <= max_cost_price)
        if min_weight is not None:
            query = query.filter(Products.weight >= min_weight)
        if max_weight is not None:
            query = query.filter(Products.weight <= max_weight)

        # sorting
        sort_column = getattr(Products, sort_by)
        query = query.order_by(
            sort_column.desc() if sort_order == "desc" else sort_column.asc()
        )

        pagination = query.paginate(page=page, per_page=limit, error_out=False)

        products = [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "product_image": p.product_image,
                "product_images": p.product_images,
                "category_id": p.category_id,
                "sizes": p.sizes,
                "colors": p.colors,
                "price": p.price,
                "compare_at_price": p.compare_at_price,
                "stock": p.stock,
                "unit_price": p.unit_price,
                "charge_tax": p.charge_tax,
                "tax_rate": p.tax_rate,
                "cost_price": p.cost_price,
                "sku": p.sku,
                "barcode": p.barcode,
                "country_of_origin": p.country_of_origin,
                "weight": p.weight,
                "weight_unit": p.weight_unit,
                "product_type": p.product_type,
                "sell_when_out_of_stock": p.sell_when_out_of_stock,
                "quantity": p.quantity,
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


@adminBP.route("/product", methods=["DELETE"])
@admin_middleware
def delete_products():
    try:
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

        products = Products.query.filter(Products.id.in_(ids)).all()

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


@adminBP.route("/category", methods=["POST"])
@admin_middleware
def create_category():
    try:
        content_type = request.content_type or ""

        if "multipart/form-data" in content_type:
            # single category with icon image upload
            data = request.form

            name = data.get("name")
            slug = data.get("slug")

            if not name or not slug:
                return (
                    jsonify(
                        {"status": "error", "message": "Name and slug are required"}
                    ),
                    400,
                )

            existing = Category.query.filter(
                db.or_(Category.name == name, Category.slug == slug)
            ).first()
            if existing:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Category name or slug already exists",
                        }
                    ),
                    409,
                )

            icon_url = None
            if "icon" in request.files:
                icon_url = upload_file(request.files["icon"], folder="categories")

            category = Category(
                name=name,
                slug=slug,
                description=data.get("description"),
                color=data.get("color"),
                icon=icon_url,
            )
            db.session.add(category)
            db.session.commit()

            return (
                jsonify(
                    {
                        "status": "success",
                        "message": "Category created successfully",
                        "id": category.id,
                    }
                ),
                201,
            )

        else:
            # single or bulk via JSON
            data = request.get_json()
            categories_data = data if isinstance(data, list) else [data]

            if len(categories_data) > 10:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Maximum 10 categories allowed at once",
                        }
                    ),
                    400,
                )

            created = []
            for item in categories_data:
                name = item.get("name")
                slug = item.get("slug")

                if not name or not slug:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": f"Name and slug are required for all categories",
                            }
                        ),
                        400,
                    )

                existing = Category.query.filter(
                    db.or_(Category.name == name, Category.slug == slug)
                ).first()
                if existing:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": f"Category '{name}' or slug '{slug}' already exists",
                            }
                        ),
                        409,
                    )

                category = Category(
                    name=name,
                    slug=slug,
                    description=item.get("description"),
                    color=item.get("color"),
                    icon=item.get("icon"),
                )
                db.session.add(category)
                created.append(category)

            db.session.commit()
            return (
                jsonify(
                    {
                        "status": "success",
                        "message": f"{len(created)} category(s) created successfully",
                        "ids": [c.id for c in created],
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
                    "message": "Failed to create category",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/category", methods=["GET"])
@admin_middleware
def get_categories():
    try:
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)

        # filters
        search = request.args.get("search")
        color = request.args.get("color")

        # product filters within category
        product_status = request.args.get("product_status")
        min_products = request.args.get("min_products", type=int)
        max_products = request.args.get("max_products", type=int)

        # sort
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")

        allowed_sort_fields = ["created_at", "updated_at", "name"]
        if sort_by not in allowed_sort_fields:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Invalid sort_by. Allowed: {', '.join(allowed_sort_fields)}",
                    }
                ),
                400,
            )

        query = Category.query

        if search:
            query = query.filter(
                db.or_(
                    Category.name.ilike(f"%{search}%"),
                    Category.description.ilike(f"%{search}%"),
                )
            )
        if color:
            query = query.filter(Category.color == color)

        sort_column = getattr(Category, sort_by)
        query = query.order_by(
            sort_column.desc() if sort_order == "desc" else sort_column.asc()
        )

        pagination = query.paginate(page=page, per_page=limit, error_out=False)

        categories = []
        for c in pagination.items:
            # build product query per category
            product_query = Products.query.filter_by(category_id=c.id)
            if product_status:
                product_query = product_query.filter(Products.status == product_status)

            # product pagination
            product_page = request.args.get("product_page", 1, type=int)
            product_limit = request.args.get("product_limit", 10, type=int)
            product_pagination = product_query.order_by(
                Products.created_at.desc()
            ).paginate(page=product_page, per_page=product_limit, error_out=False)

            all_products = product_query.all()

            # skip category if product count out of range
            total_products = len(all_products)
            if min_products is not None and total_products < min_products:
                continue
            if max_products is not None and total_products > max_products:
                continue

            # aggregate stats
            prices = [p.price for p in all_products if p.price is not None]
            stocks = [p.stock for p in all_products if p.stock is not None]
            active_count = sum(1 for p in all_products if p.status == "active")
            inactive_count = sum(1 for p in all_products if p.status == "inactive")
            out_of_stock_count = sum(1 for p in all_products if p.stock == 0)
            total_stock = sum(stocks)
            avg_price = round(sum(prices) / len(prices), 2) if prices else 0
            min_price_val = min(prices) if prices else 0
            max_price_val = max(prices) if prices else 0

            products = [
                {
                    "id": p.id,
                    "name": p.name,
                    "product_image": p.product_image,
                    "price": p.price,
                    "compare_at_price": p.compare_at_price,
                    "status": p.status,
                    "stock": p.stock,
                    "quantity": p.quantity,
                    "sku": p.sku,
                }
                for p in product_pagination.items
            ]

            categories.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "slug": c.slug,
                    "description": c.description,
                    "icon": c.icon,
                    "color": c.color,
                    "created_at": c.created_at,
                    "updated_at": c.updated_at,
                    "products": products,
                    "product_pagination": {
                        "total": product_pagination.total,
                        "pages": product_pagination.pages,
                        "page": product_page,
                        "limit": product_limit,
                    },
                    "stats": {
                        "total_products": total_products,
                        "active_products": active_count,
                        "inactive_products": inactive_count,
                        "out_of_stock_products": out_of_stock_count,
                        "total_stock": total_stock,
                        "avg_price": avg_price,
                        "min_price": min_price_val,
                        "max_price": max_price_val,
                    },
                }
            )

        # overall summary cards data
        all_categories = Category.query.all()
        all_products_q = Products.query.all()
        total_active_categories = sum(1 for c in all_categories if c.products)
        total_empty_categories = sum(1 for c in all_categories if not c.products)
        all_prices = [p.price for p in all_products_q if p.price]
        summary = {
            "total_categories": len(all_categories),
            "active_categories": total_active_categories,
            "empty_categories": total_empty_categories,
            "total_products": len(all_products_q),
            "overall_avg_price": (
                round(sum(all_prices) / len(all_prices), 2) if all_prices else 0
            ),
            "overall_out_of_stock": sum(1 for p in all_products_q if p.stock == 0),
            "overall_active_products": sum(
                1 for p in all_products_q if p.status == "active"
            ),
            "overall_inactive_products": sum(
                1 for p in all_products_q if p.status == "inactive"
            ),
        }

        return (
            jsonify(
                {
                    "status": "success",
                    "categories": categories,
                    "total": pagination.total,
                    "pages": pagination.pages,
                    "page": page,
                    "limit": limit,
                    "summary": summary,
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to fetch categories",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/category/<int:category_id>", methods=["GET"])
@admin_middleware
def get_category(category_id):
    try:
        category = Category.query.get(category_id)
        if not category:
            return jsonify({"status": "error", "message": "Category not found"}), 404

        product_page = request.args.get("product_page", 1, type=int)
        product_limit = request.args.get("product_limit", 10, type=int)
        product_status = request.args.get("product_status")
        product_search = request.args.get("product_search")
        min_price = request.args.get("min_price", type=float)
        max_price = request.args.get("max_price", type=float)
        min_stock = request.args.get("min_stock", type=int)
        max_stock = request.args.get("max_stock", type=int)
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")

        allowed_sort_fields = ["created_at", "updated_at", "price", "stock", "name"]
        if sort_by not in allowed_sort_fields:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Invalid sort_by. Allowed: {', '.join(allowed_sort_fields)}",
                    }
                ),
                400,
            )

        product_query = Products.query.filter_by(category_id=category_id)

        if product_status:
            product_query = product_query.filter(Products.status == product_status)
        if product_search:
            product_query = product_query.filter(
                db.or_(
                    Products.name.ilike(f"%{product_search}%"),
                    Products.sku.ilike(f"%{product_search}%"),
                )
            )
        if min_price is not None:
            product_query = product_query.filter(Products.price >= min_price)
        if max_price is not None:
            product_query = product_query.filter(Products.price <= max_price)
        if min_stock is not None:
            product_query = product_query.filter(Products.stock >= min_stock)
        if max_stock is not None:
            product_query = product_query.filter(Products.stock <= max_stock)

        sort_column = getattr(Products, sort_by)
        product_query = product_query.order_by(
            sort_column.desc() if sort_order == "desc" else sort_column.asc()
        )

        product_pagination = product_query.paginate(
            page=product_page, per_page=product_limit, error_out=False
        )
        all_products = Products.query.filter_by(category_id=category_id).all()

        prices = [p.price for p in all_products if p.price is not None]
        stocks = [p.stock for p in all_products if p.stock is not None]

        products = [
            {
                "id": p.id,
                "name": p.name,
                "product_image": p.product_image,
                "price": p.price,
                "compare_at_price": p.compare_at_price,
                "status": p.status,
                "stock": p.stock,
                "quantity": p.quantity,
                "sku": p.sku,
            }
            for p in product_pagination.items
        ]

        return (
            jsonify(
                {
                    "status": "success",
                    "category": {
                        "id": category.id,
                        "name": category.name,
                        "slug": category.slug,
                        "description": category.description,
                        "icon": category.icon,
                        "color": category.color,
                        "created_at": category.created_at,
                        "updated_at": category.updated_at,
                        "products": products,
                        "product_pagination": {
                            "total": product_pagination.total,
                            "pages": product_pagination.pages,
                            "page": product_page,
                            "limit": product_limit,
                        },
                        "stats": {
                            "total_products": len(all_products),
                            "active_products": sum(
                                1 for p in all_products if p.status == "active"
                            ),
                            "inactive_products": sum(
                                1 for p in all_products if p.status == "inactive"
                            ),
                            "out_of_stock_products": sum(
                                1 for p in all_products if p.stock == 0
                            ),
                            "total_stock": sum(stocks),
                            "avg_price": (
                                round(sum(prices) / len(prices), 2) if prices else 0
                            ),
                            "min_price": min(prices) if prices else 0,
                            "max_price": max(prices) if prices else 0,
                        },
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
                    "message": "Failed to fetch category",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/category/<int:category_id>", methods=["PUT"])
@admin_middleware
def update_category(category_id):
    try:
        category = Category.query.get(category_id)
        if not category:
            return jsonify({"status": "error", "message": "Category not found"}), 404

        content_type = request.content_type or ""

        if "multipart/form-data" in content_type:
            data = request.form

            if "icon" in request.files:
                category.icon = upload_file(request.files["icon"], folder="categories")

            if "name" in data:
                existing = Category.query.filter(
                    Category.name == data["name"], Category.id != category_id
                ).first()
                if existing:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": "Category name already exists",
                            }
                        ),
                        409,
                    )
                category.name = data["name"]

            if "slug" in data:
                existing = Category.query.filter(
                    Category.slug == data["slug"], Category.id != category_id
                ).first()
                if existing:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": "Category slug already exists",
                            }
                        ),
                        409,
                    )
                category.slug = data["slug"]

            if "description" in data:
                category.description = data["description"]
            if "color" in data:
                category.color = data["color"]

        else:
            data = request.get_json()

            if "name" in data:
                existing = Category.query.filter(
                    Category.name == data["name"], Category.id != category_id
                ).first()
                if existing:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": "Category name already exists",
                            }
                        ),
                        409,
                    )
                category.name = data["name"]

            if "slug" in data:
                existing = Category.query.filter(
                    Category.slug == data["slug"], Category.id != category_id
                ).first()
                if existing:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": "Category slug already exists",
                            }
                        ),
                        409,
                    )
                category.slug = data["slug"]

            if "description" in data:
                category.description = data["description"]
            if "color" in data:
                category.color = data["color"]
            if "icon" in data:
                category.icon = data["icon"]

            if "add_product_ids" in data:
                add_ids = data["add_product_ids"]
                if not isinstance(add_ids, list):
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": "add_product_ids must be a list",
                            }
                        ),
                        400,
                    )

                products_to_add = Products.query.filter(Products.id.in_(add_ids)).all()
                if len(products_to_add) != len(add_ids):
                    found_ids = {p.id for p in products_to_add}
                    missing = [i for i in add_ids if i not in found_ids]
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": f"Products not found: {missing}",
                            }
                        ),
                        404,
                    )

                for product in products_to_add:
                    product.category_id = category_id

            if "remove_product_ids" in data:
                remove_ids = data["remove_product_ids"]
                if not isinstance(remove_ids, list):
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": "remove_product_ids must be a list",
                            }
                        ),
                        400,
                    )

                products_to_remove = Products.query.filter(
                    Products.id.in_(remove_ids), Products.category_id == category_id
                ).all()
                if len(products_to_remove) != len(remove_ids):
                    found_ids = {p.id for p in products_to_remove}
                    missing = [i for i in remove_ids if i not in found_ids]
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": f"Products not found in this category: {missing}",
                            }
                        ),
                        404,
                    )

                for product in products_to_remove:
                    product.category_id = None

        db.session.commit()
        return (
            jsonify({"status": "success", "message": "Category updated successfully"}),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to update category",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/category", methods=["DELETE"])
@admin_middleware
def delete_categories():
    try:
        data = request.get_json()
        ids = data.get("ids", [])

        if not ids:
            return (
                jsonify({"status": "error", "message": "No category ids provided"}),
                400,
            )

        if len(ids) > 10:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Maximum 10 categories can be deleted at once",
                    }
                ),
                400,
            )

        categories = Category.query.filter(Category.id.in_(ids)).all()
        if not categories:
            return jsonify({"status": "error", "message": "No categories found"}), 404

        not_found_ids = set(ids) - {c.id for c in categories}
        if not_found_ids:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Categories not found for ids: {', '.join(map(str, not_found_ids))}",
                    }
                ),
                404,
            )

        deleted_names = [c.name for c in categories]

        for category in categories:
            db.session.delete(category)

        db.session.commit()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": f"{len(categories)} category(s) deleted successfully",
                    "deleted": deleted_names,
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
                    "message": "Failed to delete categories",
                    "error": str(e),
                }
            ),
            500,
        )


# ─── USERS ───────────────────────────────────────────────────────────────────
@adminBP.route("/users", methods=["GET"])
@admin_middleware
def get_users():
    try:
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)

        # filters
        search = request.args.get("search")
        role = request.args.get("role")
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")

        allowed_sort_fields = ["created_at", "updated_at", "username", "email"]
        if sort_by not in allowed_sort_fields:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Invalid sort_by. Allowed: {', '.join(allowed_sort_fields)}",
                    }
                ),
                400,
            )

        query = User.query

        if search:
            query = query.filter(
                db.or_(
                    User.username.ilike(f"%{search}%"),
                    User.email.ilike(f"%{search}%"),
                    User.phone_number.ilike(f"%{search}%"),
                )
            )
        if role:
            query = query.filter(User.role == role)

        sort_column = getattr(User, sort_by)
        query = query.order_by(
            sort_column.desc() if sort_order == "desc" else sort_column.asc()
        )

        pagination = query.paginate(page=page, per_page=limit, error_out=False)

        users = []
        for u in pagination.items:
            orders = Orders.query.filter_by(user_id=u.id).all()

            total_orders = len(orders)
            delivered = sum(1 for o in orders if o.status == "delivered")
            cancelled = sum(1 for o in orders if o.status == "cancelled")
            pending = sum(1 for o in orders if o.status == "pending")
            processing = sum(1 for o in orders if o.status == "processing")
            returned = sum(1 for o in orders if o.status == "returned")
            total_spent = sum(
                o.total_price
                for o in orders
                if o.total_price and o.status != "cancelled"
            )
            avg_order_value = round(total_spent / delivered, 2) if delivered > 0 else 0
            last_order = (
                max(orders, key=lambda o: o.created_at).created_at if orders else None
            )

            users.append(
                {
                    "id": u.id,
                    "username": u.username,
                    "email": u.email,
                    "phone_number": u.phone_number,
                    "profile_picture": u.profile_picture,
                    "bio": u.bio,
                    "role": u.role,
                    "created_at": u.created_at,
                    "updated_at": u.updated_at,
                    "order_stats": {
                        "total_orders": total_orders,
                        "delivered": delivered,
                        "cancelled": cancelled,
                        "pending": pending,
                        "processing": processing,
                        "returned": returned,
                        "total_spent": round(total_spent, 2),
                        "avg_order_value": avg_order_value,
                        "last_order_at": last_order,
                    },
                }
            )

        all_users = User.query.all()
        all_orders = Orders.query.all()
        summary = {
            "total_users": len(all_users),
            "total_customers": sum(1 for u in all_users if u.role == "customer"),
            "total_orders": len(all_orders),
            "total_revenue": round(
                sum(
                    o.total_price
                    for o in all_orders
                    if o.total_price and o.status != "cancelled"
                ),
                2,
            ),
        }

        return (
            jsonify(
                {
                    "status": "success",
                    "users": users,
                    "total": pagination.total,
                    "pages": pagination.pages,
                    "page": page,
                    "limit": limit,
                    "summary": summary,
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "error", "message": "Failed to fetch users", "error": str(e)}
            ),
            500,
        )


@adminBP.route("/users/<int:user_id>", methods=["GET"])
@admin_middleware
def get_user(user_id):
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"status": "error", "message": "User not found"}), 404

        order_page = request.args.get("order_page", 1, type=int)
        order_limit = request.args.get("order_limit", 10, type=int)
        order_status = request.args.get("order_status")
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")

        order_query = Orders.query.filter_by(user_id=user_id)
        if order_status:
            order_query = order_query.filter(Orders.status == order_status)

        sort_column = getattr(Orders, sort_by)
        order_query = order_query.order_by(
            sort_column.desc() if sort_order == "desc" else sort_column.asc()
        )
        order_pagination = order_query.paginate(
            page=order_page, per_page=order_limit, error_out=False
        )

        all_orders = Orders.query.filter_by(user_id=user_id).all()
        total_spent = sum(
            o.total_price
            for o in all_orders
            if o.total_price and o.status != "cancelled"
        )
        delivered = sum(1 for o in all_orders if o.status == "delivered")

        addresses = [
            {
                "id": a.id,
                "street": a.street,
                "city": a.city,
                "state": a.state,
                "postal_code": a.postal_code,
                "country": a.country,
            }
            for a in user.addresses
        ]

        orders = [
            {
                "id": o.id,
                "order_id": o.order_id,
                "status": o.status,
                "total_price": o.total_price,
                "subtotal": o.subtotal,
                "tax_amount": o.tax_amount,
                "discount": o.discount,
                "shipping_charges": o.shipping_charges,
                "payment_status": o.payment_status,
                "payment_method": o.payment_method,
                "order_source": o.order_source,
                "created_at": o.created_at,
                "updated_at": o.updated_at,
            }
            for o in order_pagination.items
        ]

        return (
            jsonify(
                {
                    "status": "success",
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "phone_number": user.phone_number,
                        "profile_picture": user.profile_picture,
                        "bio": user.bio,
                        "role": user.role,
                        "created_at": user.created_at,
                        "updated_at": user.updated_at,
                        "addresses": addresses,
                        "orders": orders,
                        "order_pagination": {
                            "total": order_pagination.total,
                            "pages": order_pagination.pages,
                            "page": order_page,
                            "limit": order_limit,
                        },
                        "order_stats": {
                            "total_orders": len(all_orders),
                            "delivered": delivered,
                            "cancelled": sum(
                                1 for o in all_orders if o.status == "cancelled"
                            ),
                            "pending": sum(
                                1 for o in all_orders if o.status == "pending"
                            ),
                            "processing": sum(
                                1 for o in all_orders if o.status == "processing"
                            ),
                            "returned": sum(
                                1 for o in all_orders if o.status == "returned"
                            ),
                            "total_spent": round(total_spent, 2),
                            "avg_order_value": (
                                round(total_spent / delivered, 2)
                                if delivered > 0
                                else 0
                            ),
                            "last_order_at": (
                                max(all_orders, key=lambda o: o.created_at).created_at
                                if all_orders
                                else None
                            ),
                        },
                    },
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "error", "message": "Failed to fetch user", "error": str(e)}
            ),
            500,
        )


# ─── ORDERS ──────────────────────────────────────────────────────────────────
@adminBP.route("/orders", methods=["GET"])
@admin_middleware
def get_orders():
    try:
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)

        # filters
        search = request.args.get("search")
        status = request.args.get("status")
        payment_status = request.args.get("payment_status")
        payment_method = request.args.get("payment_method")
        order_source = request.args.get("order_source")
        user_id = request.args.get("user_id", type=int)
        from_date = request.args.get("from_date")
        to_date = request.args.get("to_date")
        min_amount = request.args.get("min_amount", type=float)
        max_amount = request.args.get("max_amount", type=float)
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")

        allowed_sort_fields = ["created_at", "updated_at", "total_price", "subtotal"]
        if sort_by not in allowed_sort_fields:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Invalid sort_by. Allowed: {', '.join(allowed_sort_fields)}",
                    }
                ),
                400,
            )

        query = Orders.query

        if status:
            query = query.filter(Orders.status == status)
        if payment_status:
            query = query.filter(Orders.payment_status == payment_status)
        if payment_method:
            query = query.filter(Orders.payment_method == payment_method)
        if order_source:
            query = query.filter(Orders.order_source == order_source)
        if user_id:
            query = query.filter(Orders.user_id == user_id)
        if min_amount is not None:
            query = query.filter(Orders.total_price >= min_amount)
        if max_amount is not None:
            query = query.filter(Orders.total_price <= max_amount)
        if from_date:
            query = query.filter(
                Orders.created_at >= datetime.strptime(from_date, "%Y-%m-%d")
            )
        if to_date:
            query = query.filter(
                Orders.created_at <= datetime.strptime(to_date, "%Y-%m-%d")
            )
        if search:
            query = query.join(User).filter(
                db.or_(
                    User.username.ilike(f"%{search}%"),
                    User.email.ilike(f"%{search}%"),
                    User.phone_number.ilike(f"%{search}%"),
                    Orders.order_id.ilike(f"%{search}%"),
                )
            )

        sort_column = getattr(Orders, sort_by)
        query = query.order_by(
            sort_column.desc() if sort_order == "desc" else sort_column.asc()
        )

        pagination = query.paginate(page=page, per_page=limit, error_out=False)

        orders = []
        for o in pagination.items:
            user = User.query.get(o.user_id)
            items = OrderedItems.query.filter_by(order_id=o.id).all()

            orders.append(
                {
                    "id": o.id,
                    "order_id": o.order_id,
                    "status": o.status,
                    "payment_status": o.payment_status,
                    "payment_method": o.payment_method,
                    "order_source": o.order_source,
                    "subtotal": o.subtotal,
                    "tax_amount": o.tax_amount,
                    "discount": o.discount,
                    "shipping_charges": o.shipping_charges,
                    "total_price": o.total_price,
                    "created_at": o.created_at,
                    "updated_at": o.updated_at,
                    "user": (
                        {
                            "id": user.id,
                            "username": user.username,
                            "email": user.email,
                            "phone_number": user.phone_number,
                            "profile_picture": user.profile_picture,
                        }
                        if user
                        else None
                    ),
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
                        for i in items
                    ],
                    "total_items": len(items),
                }
            )

        # dashboard summary
        all_orders = Orders.query.all()
        total_revenue = sum(
            o.total_price
            for o in all_orders
            if o.total_price and o.status != "cancelled"
        )
        today = datetime.utcnow().date()
        today_orders = [o for o in all_orders if o.created_at.date() == today]
        today_revenue = sum(
            o.total_price
            for o in today_orders
            if o.total_price and o.status != "cancelled"
        )
        this_month = [
            o
            for o in all_orders
            if o.created_at.month == today.month and o.created_at.year == today.year
        ]
        month_revenue = sum(
            o.total_price
            for o in this_month
            if o.total_price and o.status != "cancelled"
        )
        total_discount = sum(o.discount for o in all_orders if o.discount)
        total_tax = sum(o.tax_amount for o in all_orders if o.tax_amount)

        summary = {
            "total_orders": len(all_orders),
            "total_revenue": round(total_revenue, 2),
            "total_discount_given": round(total_discount, 2),
            "total_tax_collected": round(total_tax, 2),
            "today_orders": len(today_orders),
            "today_revenue": round(today_revenue, 2),
            "this_month_orders": len(this_month),
            "this_month_revenue": round(month_revenue, 2),
            "pending_orders": sum(1 for o in all_orders if o.status == "pending"),
            "processing_orders": sum(1 for o in all_orders if o.status == "processing"),
            "shipped_orders": sum(1 for o in all_orders if o.status == "shipped"),
            "delivered_orders": sum(1 for o in all_orders if o.status == "delivered"),
            "cancelled_orders": sum(1 for o in all_orders if o.status == "cancelled"),
            "returned_orders": sum(1 for o in all_orders if o.status == "returned"),
            "paid_orders": sum(1 for o in all_orders if o.payment_status == "paid"),
            "unpaid_orders": sum(1 for o in all_orders if o.payment_status == "unpaid"),
            "cod_orders": sum(1 for o in all_orders if o.payment_method == "cod"),
            "avg_order_value": (
                round(total_revenue / len(all_orders), 2) if all_orders else 0
            ),
            "refund_requested_orders": sum(
                1 for o in all_orders if o.status == "refund_requested"
            ),
        }

        return (
            jsonify(
                {
                    "status": "success",
                    "orders": orders,
                    "total": pagination.total,
                    "pages": pagination.pages,
                    "page": page,
                    "limit": limit,
                    "summary": summary,
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


@adminBP.route("/orders/<int:order_id>", methods=["GET"])
@admin_middleware
def get_order(order_id):
    try:
        order = Orders.query.get(order_id)
        if not order:
            return jsonify({"status": "error", "message": "Order not found"}), 404

        user = User.query.get(order.user_id)
        items = OrderedItems.query.filter_by(order_id=order_id).all()
        payment = Payment.query.filter_by(order_id=order_id).first()
        refund = Refund.query.filter_by(order_id=order_id).first()

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
                        "order_source": order.order_source,
                        "shipping_address": order.shipping_address,
                        "subtotal": order.subtotal,
                        "tax_amount": order.tax_amount,
                        "discount": order.discount,
                        "shipping_charges": order.shipping_charges,
                        "total_price": order.total_price,
                        "created_at": order.created_at,
                        "updated_at": order.updated_at,
                        "user": (
                            {
                                "id": user.id,
                                "username": user.username,
                                "email": user.email,
                                "phone_number": user.phone_number,
                                "profile_picture": user.profile_picture,
                                "bio": user.bio,
                                "role": user.role,
                            }
                            if user
                            else None
                        ),
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
                                "subtotal": round(i.quantity * i.unit_price, 2),
                            }
                            for i in items
                        ],
                        "total_items": len(items),
                        "total_quantity": sum(i.quantity for i in items),
                        "payment": (
                            {
                                "id": payment.id,
                                "payment_method": payment.payment_method,
                                "amount": payment.amount,
                                "currency": payment.currency,
                                "status": payment.status,
                                "razorpay_order_id": payment.razorpay_order_id,
                                "razorpay_payment_id": payment.razorpay_payment_id,
                                "failure_reason": payment.failure_reason,
                                "refund_id": payment.refund_id,
                                "refund_amount": payment.refund_amount,
                                "refund_status": payment.refund_status,
                                "paid_at": payment.paid_at,
                            }
                            if payment
                            else None
                        ),
                        "refund": (
                            {
                                "id": refund.id,
                                "reason": refund.reason,
                                "description": refund.description,
                                "refund_amount": refund.refund_amount,
                                "refund_type": refund.refund_type,
                                "item_ids": refund.item_ids,
                                "status": refund.status,
                                "razorpay_refund_id": refund.razorpay_refund_id,
                                "bank_reference": refund.bank_reference,
                                "rejection_reason": refund.rejection_reason,
                                "processed_at": refund.processed_at,
                                "created_at": refund.created_at,
                            }
                            if refund
                            else None
                        ),
                    },
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "error", "message": "Failed to fetch order", "error": str(e)}
            ),
            500,
        )


@adminBP.route("/orders/<int:order_id>", methods=["PUT"])
@admin_middleware
def update_order(order_id):
    try:
        order = db.session.get(Orders, order_id)
        if not order:
            return jsonify({"status": "error", "message": "Order not found"}), 404

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        allowed_statuses = [
            "pending",
            "processing",
            "shipped",
            "delivered",
            "cancelled",
            "returned",
        ]
        allowed_payment_statuses = ["paid", "unpaid", "refunded", "failed"]
        allowed_refund_statuses = [
            "pending",
            "approved",
            "rejected",
            "picked_up",
            "parcel_received",
            "payment_initiated",
            "refund_done",
        ]

        if "refund_status" in data:
            if data["refund_status"] not in allowed_refund_statuses:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": f"Invalid refund_status. Allowed: {', '.join(allowed_refund_statuses)}",
                        }
                    ),
                    400,
                )

            refund = Refund.query.filter_by(order_id=order.id).first()
            if not refund:
                return (
                    jsonify(
                        {"status": "error", "message": "No refund found for this order"}
                    ),
                    404,
                )

            refund.status = data["refund_status"]

            if data["refund_status"] == "rejected":
                refund.rejection_reason = data.get("rejection_reason")
            if data["refund_status"] == "picked_up":
                refund.picked_up_at = datetime.utcnow()
            if data["refund_status"] == "refund_done":
                refund.processed_at = datetime.utcnow()
                order.payment_status = "refunded"

        old_status = order.status

        if "status" in data:
            if data["status"] not in allowed_statuses:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": f"Invalid status. Allowed: {', '.join(allowed_statuses)}",
                        }
                    ),
                    400,
                )

            order.status = data["status"]

            if (
                data["status"] == "delivered"
                and order.payment_method == "cod"
                and order.payment_status == "unpaid"
            ):
                order.payment_status = "paid"

            if data["status"] == "cancelled" and old_status not in (
                "cancelled",
                "returned",
            ):
                for item in order.ordered_items:
                    product = db.session.get(Products, item.product_id)
                    if product:
                        product.stock += item.quantity

            try:
                order_list = OrderList.query.filter_by(order_id=order.id).all()
                for ol in order_list:
                    ol.status = data["status"]

                if data["status"] == "cancelled" and order_list:
                    dashboard = AffiliateDashboard.query.get(order_list[0].affiliate_id)
                    if dashboard:
                        cancelled_commission = sum(ol.commission for ol in order_list)
                        dashboard.total_revenue -= cancelled_commission
                        dashboard.total_orders -= len(order_list)
            except Exception as e:
                print(f"[AFFILIATE ERROR] update order_id={order.id} error={str(e)}")

            # ---- Vendor wallet sync ----
            try:
                if data["status"] == "delivered" and old_status != "delivered":
                    already_credited = (
                        VendorWalletTransaction.query.filter_by(
                            source="order_earning", reference_id=order.id
                        ).first()
                        is not None
                    )
                    if not already_credited:
                        vendor_rows = (
                            db.session.query(
                                OrderedItems, Products.vendor_id, Vendor.commission_rate
                            )
                            .join(Products, Products.id == OrderedItems.product_id)
                            .join(Vendor, Vendor.id == Products.vendor_id)
                            .filter(
                                OrderedItems.order_id == order.id,
                                Products.vendor_id.isnot(None),
                            )
                            .all()
                        )
                        vendor_totals = {}
                        for item, vendor_id, commission_rate in vendor_rows:
                            net = item.total_price * (1 - commission_rate / 100.0)
                            vendor_totals[vendor_id] = (
                                vendor_totals.get(vendor_id, 0.0) + net
                            )

                        for vendor_id, net_amount in vendor_totals.items():
                            if net_amount > 0:
                                credit_wallet(
                                    vendor_id=vendor_id,
                                    amount=round(net_amount, 2),
                                    source="order_earning",
                                    reference_id=order.id,
                                    note=f"Order #{order.order_id} delivered",
                                )

                elif data["status"] == "returned" and old_status != "returned":
                    already_reversed = (
                        VendorWalletTransaction.query.filter_by(
                            source="refund_reversal", reference_id=order.id
                        ).first()
                        is not None
                    )
                    if not already_reversed:
                        credit_txns = VendorWalletTransaction.query.filter_by(
                            source="order_earning", reference_id=order.id
                        ).all()
                        vendor_credit_map = {}
                        for t in credit_txns:
                            v_id = t.wallet.vendor_id
                            vendor_credit_map[v_id] = (
                                vendor_credit_map.get(v_id, 0.0) + t.amount
                            )

                        for vendor_id, credited_amount in vendor_credit_map.items():
                            try:
                                debit_wallet(
                                    vendor_id=vendor_id,
                                    amount=round(credited_amount, 2),
                                    source="refund_reversal",
                                    reference_id=order.id,
                                    note=f"Order #{order.order_id} returned",
                                )
                            except ValueError as balance_err:
                                print(
                                    f"[WALLET] Reversal shortfall on order {order.id}, "
                                    f"vendor {vendor_id}: {balance_err}"
                                )
            except Exception as wallet_err:
                print(
                    f"[WALLET ERROR] update order_id={order.id} error={str(wallet_err)}"
                )
            # ---- end vendor wallet sync ----

        if "payment_status" in data:
            if data["payment_status"] not in allowed_payment_statuses:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": f"Invalid payment_status. Allowed: {', '.join(allowed_payment_statuses)}",
                        }
                    ),
                    400,
                )
            order.payment_status = data["payment_status"]

        if "payment_method" in data:
            order.payment_method = data["payment_method"]
        if "shipping_address" in data:
            order.shipping_address = data["shipping_address"]
        if "discount" in data:
            order.discount = data["discount"]
        if "shipping_charges" in data:
            order.shipping_charges = data["shipping_charges"]

        db.session.commit()

        if data.get("status") == "confirmed" and not order.shipment_id:
            try:
                create_shipment_async(order.order_id)
            except Exception as e:
                print(f"[SHIPROCKET] Create error for {order.order_id}: {e}")

        if (
            data.get("status") in ("cancelled", "returned", "delivered")
            and order.shiprocket_order_id
        ):
            try:
                cancelled = cancel_shiprocket_order(order.shiprocket_order_id)
                if not cancelled:
                    print(
                        f"[SHIPROCKET] Failed to cancel order {order.shiprocket_order_id}"
                    )
            except Exception as e:
                print(f"[SHIPROCKET] Cancel error for {order.shiprocket_order_id}: {e}")

        return (
            jsonify({"status": "success", "message": "Order updated successfully"}),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to update order",
                    "error": str(e),
                }
            ),
            500,
        )


from functions.wallet_helper import credit_wallet, debit_wallet
from models.admin import Vendor, VendorWalletTransaction


@adminBP.route("/orders/bulk-update", methods=["PUT"])
@admin_middleware
def bulk_update_orders():
    try:
        data = request.get_json()
        ids = data.get("ids", [])
        updates = data.get("updates", {})

        if not ids:
            return jsonify({"status": "error", "message": "No order ids provided"}), 400
        if not updates:
            return jsonify({"status": "error", "message": "No updates provided"}), 400
        if len(ids) > 20:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Maximum 20 orders can be updated at once",
                    }
                ),
                400,
            )

        allowed_statuses = [
            "pending",
            "processing",
            "shipped",
            "delivered",
            "cancelled",
            "returned",
        ]
        allowed_payment_statuses = ["paid", "unpaid", "refunded", "failed"]
        allowed_fields = ["status", "payment_status", "payment_method"]

        invalid_fields = [f for f in updates if f not in allowed_fields]
        if invalid_fields:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Fields not allowed in bulk update: {', '.join(invalid_fields)}",
                    }
                ),
                400,
            )

        if "status" in updates and updates["status"] not in allowed_statuses:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Invalid status. Allowed: {', '.join(allowed_statuses)}",
                    }
                ),
                400,
            )

        if (
            "payment_status" in updates
            and updates["payment_status"] not in allowed_payment_statuses
        ):
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Invalid payment_status. Allowed: {', '.join(allowed_payment_statuses)}",
                    }
                ),
                400,
            )

        orders = Orders.query.filter(Orders.id.in_(ids)).all()
        if not orders:
            return jsonify({"status": "error", "message": "No orders found"}), 404

        new_status = updates.get("status")

        for order in orders:
            old_status = order.status

            for field, value in updates.items():
                setattr(order, field, value)

            if (
                new_status == "delivered"
                and order.payment_method == "cod"
                and order.payment_status == "unpaid"
            ):
                order.payment_status = "paid"

            # Restore stock if cancelling
            if new_status == "cancelled" and old_status not in (
                "cancelled",
                "returned",
            ):
                for item in order.ordered_items:
                    product = db.session.get(Products, item.product_id)
                    if product:
                        product.stock += item.quantity

            if new_status in ("cancelled",):
                try:
                    order_list = OrderList.query.filter_by(order_id=order.id).all()
                    for ol in order_list:
                        ol.status = new_status

                    if order_list:
                        dashboard = AffiliateDashboard.query.get(
                            order_list[0].affiliate_id
                        )
                        if dashboard:
                            cancelled_commission = sum(
                                ol.commission for ol in order_list
                            )
                            dashboard.total_revenue -= cancelled_commission
                            dashboard.total_orders -= len(order_list)
                except Exception as e:
                    print(
                        f"[AFFILIATE ERROR] bulk update order_id={order.id} error={str(e)}"
                    )

            try:
                if new_status == "delivered" and old_status != "delivered":
                    already_credited = (
                        VendorWalletTransaction.query.filter_by(
                            source="order_earning", reference_id=order.id
                        ).first()
                        is not None
                    )
                    if not already_credited:
                        vendor_rows = (
                            db.session.query(
                                OrderedItems, Products.vendor_id, Vendor.commission_rate
                            )
                            .join(Products, Products.id == OrderedItems.product_id)
                            .join(Vendor, Vendor.id == Products.vendor_id)
                            .filter(
                                OrderedItems.order_id == order.id,
                                Products.vendor_id.isnot(None),
                            )
                            .all()
                        )
                        vendor_totals = {}
                        for item, vendor_id, commission_rate in vendor_rows:
                            net = item.total_price * (1 - commission_rate / 100.0)
                            vendor_totals[vendor_id] = (
                                vendor_totals.get(vendor_id, 0.0) + net
                            )

                        for vendor_id, net_amount in vendor_totals.items():
                            if net_amount > 0:
                                credit_wallet(
                                    vendor_id=vendor_id,
                                    amount=round(net_amount, 2),
                                    source="order_earning",
                                    reference_id=order.id,
                                    note=f"Order #{order.order_id} delivered (bulk update)",
                                )

                elif new_status == "returned" and old_status != "returned":
                    already_reversed = (
                        VendorWalletTransaction.query.filter_by(
                            source="refund_reversal", reference_id=order.id
                        ).first()
                        is not None
                    )
                    if not already_reversed:
                        credit_txns = VendorWalletTransaction.query.filter_by(
                            source="order_earning", reference_id=order.id
                        ).all()
                        vendor_credit_map = {}
                        for t in credit_txns:
                            v_id = t.wallet.vendor_id
                            vendor_credit_map[v_id] = (
                                vendor_credit_map.get(v_id, 0.0) + t.amount
                            )

                        for vendor_id, credited_amount in vendor_credit_map.items():
                            try:
                                debit_wallet(
                                    vendor_id=vendor_id,
                                    amount=round(credited_amount, 2),
                                    source="refund_reversal",
                                    reference_id=order.id,
                                    note=f"Order #{order.order_id} returned (bulk update)",
                                )
                            except ValueError as balance_err:
                                print(
                                    f"[WALLET] Reversal shortfall on order {order.id}, "
                                    f"vendor {vendor_id}: {balance_err}"
                                )
            except Exception as wallet_err:
                print(
                    f"[WALLET ERROR] bulk update order_id={order.id} error={str(wallet_err)}"
                )

        db.session.commit()

        if new_status:
            from functions.helper_function import (
                create_shipment_async,
                cancel_shiprocket_order,
            )

            for order in orders:
                if new_status == "confirmed" and not order.shipment_id:
                    try:
                        create_shipment_async(order.order_id)
                    except Exception as e:
                        print(f"[SHIPROCKET] Create error for {order.order_id}: {e}")

                if new_status == "cancelled" and order.shiprocket_order_id:
                    try:
                        cancelled = cancel_shiprocket_order(order.shiprocket_order_id)
                        if not cancelled:
                            print(
                                f"[SHIPROCKET] Failed to cancel {order.shiprocket_order_id}"
                            )
                    except Exception as e:
                        print(
                            f"[SHIPROCKET] Cancel error for {order.shiprocket_order_id}: {e}"
                        )

        return (
            jsonify(
                {
                    "status": "success",
                    "message": f"{len(orders)} order(s) updated successfully",
                    "ids": [o.id for o in orders],
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
                    "message": "Failed to bulk update orders",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/banner", methods=["POST"])
@admin_middleware
def create_banner():
    try:
        data = request.get_json()
        banners_data = data if isinstance(data, list) else [data]

        if len(banners_data) > 10:
            return (
                jsonify(
                    {"status": "error", "message": "Maximum 10 banners allowed at once"}
                ),
                400,
            )

        created = []
        for item in banners_data:
            if not item.get("title"):
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Title is required for all banners",
                        }
                    ),
                    400,
                )
            banner = Banner(
                title=item.get("title"),
                description=item.get("description"),
                link_name=item.get("link_name"),
                link=item.get("link"),
                code=item.get("code"),
                status=item.get("status", "active"),
            )
            db.session.add(banner)
            created.append(banner)

        db.session.commit()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": f"{len(created)} banner(s) created successfully",
                    "ids": [b.id for b in created],
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
                    "message": "Failed to create banner",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/banner", methods=["GET"])
@admin_middleware
def get_banners():
    try:
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)
        status = request.args.get("status")
        search = request.args.get("search")
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")

        allowed_sort_fields = ["created_at", "updated_at", "title"]
        if sort_by not in allowed_sort_fields:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Invalid sort_by. Allowed: {', '.join(allowed_sort_fields)}",
                    }
                ),
                400,
            )

        query = Banner.query
        if status:
            query = query.filter(Banner.status == status)
        if search:
            query = query.filter(
                db.or_(
                    Banner.title.ilike(f"%{search}%"),
                    Banner.description.ilike(f"%{search}%"),
                    Banner.code.ilike(f"%{search}%"),
                )
            )

        sort_column = getattr(Banner, sort_by)
        query = query.order_by(
            sort_column.desc() if sort_order == "desc" else sort_column.asc()
        )
        pagination = query.paginate(page=page, per_page=limit, error_out=False)

        banners = [
            {
                "id": b.id,
                "title": b.title,
                "description": b.description,
                "link_name": b.link_name,
                "link": b.link,
                "code": b.code,
                "status": b.status,
                "created_at": b.created_at,
                "updated_at": b.updated_at,
            }
            for b in pagination.items
        ]

        all_banners = Banner.query.all()
        summary = {
            "total_banners": len(all_banners),
            "active_banners": sum(1 for b in all_banners if b.status == "active"),
            "inactive_banners": sum(1 for b in all_banners if b.status == "inactive"),
        }

        return (
            jsonify(
                {
                    "status": "success",
                    "banners": banners,
                    "total": pagination.total,
                    "pages": pagination.pages,
                    "page": page,
                    "limit": limit,
                    "summary": summary,
                }
            ),
            200,
        )
    except Exception as e:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to fetch banners",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/banner/<int:banner_id>", methods=["PUT"])
@admin_middleware
def update_banner(banner_id):
    try:
        banner = Banner.query.get(banner_id)
        if not banner:
            return jsonify({"status": "error", "message": "Banner not found"}), 404

        data = request.get_json()
        fields = ["title", "description", "link_name", "link", "code", "status"]
        for field in fields:
            if field in data:
                setattr(banner, field, data[field])

        db.session.commit()
        return (
            jsonify({"status": "success", "message": "Banner updated successfully"}),
            200,
        )
    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to update banner",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/banner", methods=["DELETE"])
@admin_middleware
def delete_banners():
    try:
        data = request.get_json()
        ids = data.get("ids", [])
        if not ids:
            return (
                jsonify({"status": "error", "message": "No banner ids provided"}),
                400,
            )
        if len(ids) > 10:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Maximum 10 banners can be deleted at once",
                    }
                ),
                400,
            )

        banners = Banner.query.filter(Banner.id.in_(ids)).all()
        if not banners:
            return jsonify({"status": "error", "message": "No banners found"}), 404

        for banner in banners:
            db.session.delete(banner)
        db.session.commit()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": f"{len(banners)} banner(s) deleted successfully",
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
                    "message": "Failed to delete banners",
                    "error": str(e),
                }
            ),
            500,
        )


# ─── REVIEWS ──────────────────────────────────────────────────────────────────


@adminBP.route("/reviews", methods=["GET"])
@admin_middleware
def get_reviews():
    try:
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)
        product_id = request.args.get("product_id", type=int)
        user_id = request.args.get("user_id", type=int)
        min_rating = request.args.get("min_rating", type=int)
        max_rating = request.args.get("max_rating", type=int)
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")

        allowed_sort_fields = ["created_at", "updated_at", "rating"]
        if sort_by not in allowed_sort_fields:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Invalid sort_by. Allowed: {', '.join(allowed_sort_fields)}",
                    }
                ),
                400,
            )

        query = ProductReview.query
        if product_id:
            query = query.filter(ProductReview.product_id == product_id)
        if user_id:
            query = query.filter(ProductReview.user_id == user_id)
        if min_rating is not None:
            query = query.filter(ProductReview.rating >= min_rating)
        if max_rating is not None:
            query = query.filter(ProductReview.rating <= max_rating)

        sort_column = getattr(ProductReview, sort_by)
        query = query.order_by(
            sort_column.desc() if sort_order == "desc" else sort_column.asc()
        )
        pagination = query.paginate(page=page, per_page=limit, error_out=False)

        reviews = []
        for r in pagination.items:
            user = User.query.get(r.user_id)
            product = Products.query.get(r.product_id)
            reviews.append(
                {
                    "id": r.id,
                    "rating": r.rating,
                    "review": r.review,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                    "user": (
                        {
                            "id": user.id,
                            "username": user.username,
                            "email": user.email,
                            "profile_picture": user.profile_picture,
                        }
                        if user
                        else None
                    ),
                    "product": (
                        {
                            "id": product.id,
                            "name": product.name,
                            "product_image": product.product_image,
                            "sku": product.sku,
                        }
                        if product
                        else None
                    ),
                }
            )

        all_reviews = ProductReview.query.all()
        ratings = [r.rating for r in all_reviews]
        summary = {
            "total_reviews": len(all_reviews),
            "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0,
            "five_star": sum(1 for r in all_reviews if r.rating == 5),
            "four_star": sum(1 for r in all_reviews if r.rating == 4),
            "three_star": sum(1 for r in all_reviews if r.rating == 3),
            "two_star": sum(1 for r in all_reviews if r.rating == 2),
            "one_star": sum(1 for r in all_reviews if r.rating == 1),
        }

        return (
            jsonify(
                {
                    "status": "success",
                    "reviews": reviews,
                    "total": pagination.total,
                    "pages": pagination.pages,
                    "page": page,
                    "limit": limit,
                    "summary": summary,
                }
            ),
            200,
        )
    except Exception as e:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to fetch reviews",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/reviews", methods=["DELETE"])
@admin_middleware
def delete_reviews():
    try:
        data = request.get_json()
        ids = data.get("ids", [])
        if not ids:
            return (
                jsonify({"status": "error", "message": "No review ids provided"}),
                400,
            )
        if len(ids) > 20:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Maximum 20 reviews can be deleted at once",
                    }
                ),
                400,
            )

        reviews = ProductReview.query.filter(ProductReview.id.in_(ids)).all()
        if not reviews:
            return jsonify({"status": "error", "message": "No reviews found"}), 404

        for review in reviews:
            db.session.delete(review)
        db.session.commit()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": f"{len(reviews)} review(s) deleted successfully",
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
                    "message": "Failed to delete reviews",
                    "error": str(e),
                }
            ),
            500,
        )


# ─── PAYMENTS ─────────────────────────────────────────────────────────────────


@adminBP.route("/payments", methods=["GET"])
@admin_middleware
def get_payments():
    try:
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)
        status = request.args.get("status")
        payment_method = request.args.get("payment_method")
        user_id = request.args.get("user_id", type=int)
        refund_status = request.args.get("refund_status")
        from_date = request.args.get("from_date")
        to_date = request.args.get("to_date")
        min_amount = request.args.get("min_amount", type=float)
        max_amount = request.args.get("max_amount", type=float)
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")

        allowed_sort_fields = ["created_at", "updated_at", "amount", "paid_at"]
        if sort_by not in allowed_sort_fields:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Invalid sort_by. Allowed: {', '.join(allowed_sort_fields)}",
                    }
                ),
                400,
            )

        query = Payment.query
        if status:
            query = query.filter(Payment.status == status)
        if payment_method:
            query = query.filter(Payment.payment_method == payment_method)
        if user_id:
            query = query.filter(Payment.user_id == user_id)
        if refund_status:
            query = query.filter(Payment.refund_status == refund_status)
        if min_amount is not None:
            query = query.filter(Payment.amount >= min_amount)
        if max_amount is not None:
            query = query.filter(Payment.amount <= max_amount)
        if from_date:
            query = query.filter(
                Payment.created_at >= datetime.strptime(from_date, "%Y-%m-%d")
            )
        if to_date:
            query = query.filter(
                Payment.created_at <= datetime.strptime(to_date, "%Y-%m-%d")
            )

        sort_column = getattr(Payment, sort_by)
        query = query.order_by(
            sort_column.desc() if sort_order == "desc" else sort_column.asc()
        )
        pagination = query.paginate(page=page, per_page=limit, error_out=False)

        payments = []
        for p in pagination.items:
            user = User.query.get(p.user_id)
            order = Orders.query.get(p.order_id)
            payments.append(
                {
                    "id": p.id,
                    "payment_method": p.payment_method,
                    "amount": p.amount,
                    "currency": p.currency,
                    "status": p.status,
                    "razorpay_order_id": p.razorpay_order_id,
                    "razorpay_payment_id": p.razorpay_payment_id,
                    "refund_id": p.refund_id,
                    "refund_amount": p.refund_amount,
                    "refund_status": p.refund_status,
                    "refund_reason": p.refund_reason,
                    "failure_reason": p.failure_reason,
                    "paid_at": p.paid_at,
                    "created_at": p.created_at,
                    "updated_at": p.updated_at,
                    "user": (
                        {
                            "id": user.id,
                            "username": user.username,
                            "email": user.email,
                            "phone_number": user.phone_number,
                        }
                        if user
                        else None
                    ),
                    "order": (
                        {
                            "id": order.id,
                            "order_id": order.order_id,
                            "status": order.status,
                            "total_price": order.total_price,
                        }
                        if order
                        else None
                    ),
                }
            )

        all_payments = Payment.query.all()
        total_collected = sum(p.amount for p in all_payments if p.status == "captured")
        total_refunded = sum(p.refund_amount for p in all_payments if p.refund_amount)
        summary = {
            "total_payments": len(all_payments),
            "total_collected": round(total_collected, 2),
            "total_refunded": round(total_refunded, 2),
            "pending_payments": sum(1 for p in all_payments if p.status == "pending"),
            "captured_payments": sum(1 for p in all_payments if p.status == "captured"),
            "failed_payments": sum(1 for p in all_payments if p.status == "failed"),
            "refund_pending": sum(
                1 for p in all_payments if p.refund_status == "pending"
            ),
            "refund_processed": sum(
                1 for p in all_payments if p.refund_status == "processed"
            ),
        }

        return (
            jsonify(
                {
                    "status": "success",
                    "payments": payments,
                    "total": pagination.total,
                    "pages": pagination.pages,
                    "page": page,
                    "limit": limit,
                    "summary": summary,
                }
            ),
            200,
        )
    except Exception as e:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to fetch payments",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/payments/<int:payment_id>", methods=["GET"])
@admin_middleware
def get_payment(payment_id):
    try:
        payment = Payment.query.get(payment_id)
        if not payment:
            return jsonify({"status": "error", "message": "Payment not found"}), 404

        user = User.query.get(payment.user_id)
        order = Orders.query.get(payment.order_id)
        refund = Refund.query.filter_by(payment_id=payment_id).first()

        return (
            jsonify(
                {
                    "status": "success",
                    "payment": {
                        "id": payment.id,
                        "payment_method": payment.payment_method,
                        "amount": payment.amount,
                        "currency": payment.currency,
                        "status": payment.status,
                        "razorpay_order_id": payment.razorpay_order_id,
                        "razorpay_payment_id": payment.razorpay_payment_id,
                        "razorpay_signature": payment.razorpay_signature,
                        "payment_response": payment.payment_response,
                        "refund_id": payment.refund_id,
                        "refund_amount": payment.refund_amount,
                        "refund_status": payment.refund_status,
                        "refund_reason": payment.refund_reason,
                        "failure_reason": payment.failure_reason,
                        "paid_at": payment.paid_at,
                        "created_at": payment.created_at,
                        "updated_at": payment.updated_at,
                        "user": (
                            {
                                "id": user.id,
                                "username": user.username,
                                "email": user.email,
                                "phone_number": user.phone_number,
                                "profile_picture": user.profile_picture,
                            }
                            if user
                            else None
                        ),
                        "order": (
                            {
                                "id": order.id,
                                "order_id": order.order_id,
                                "status": order.status,
                                "total_price": order.total_price,
                                "payment_status": order.payment_status,
                            }
                            if order
                            else None
                        ),
                        "refund": (
                            {
                                "id": refund.id,
                                "reason": refund.reason,
                                "description": refund.description,
                                "refund_amount": refund.refund_amount,
                                "refund_type": refund.refund_type,
                                "status": refund.status,
                                "razorpay_refund_id": refund.razorpay_refund_id,
                                "bank_reference": refund.bank_reference,
                                "rejection_reason": refund.rejection_reason,
                                "processed_at": refund.processed_at,
                                "created_at": refund.created_at,
                            }
                            if refund
                            else None
                        ),
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
                    "message": "Failed to fetch payment",
                    "error": str(e),
                }
            ),
            500,
        )


# ─── REFUNDS ──────────────────────────────────────────────────────────────────
@adminBP.route("/refunds", methods=["GET"])
@admin_middleware
def get_refunds():
    try:
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)
        status = request.args.get("status")
        refund_type = request.args.get("refund_type")
        user_id = request.args.get("user_id", type=int)
        from_date = request.args.get("from_date")
        to_date = request.args.get("to_date")
        min_amount = request.args.get("min_amount", type=float)
        max_amount = request.args.get("max_amount", type=float)
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")

        allowed_sort_fields = [
            "created_at",
            "updated_at",
            "refund_amount",
            "processed_at",
        ]
        if sort_by not in allowed_sort_fields:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Invalid sort_by. Allowed: {', '.join(allowed_sort_fields)}",
                    }
                ),
                400,
            )

        query = Refund.query
        if status:
            query = query.filter(Refund.status == status)
        if refund_type:
            query = query.filter(Refund.refund_type == refund_type)
        if user_id:
            query = query.filter(Refund.user_id == user_id)
        if min_amount is not None:
            query = query.filter(Refund.refund_amount >= min_amount)
        if max_amount is not None:
            query = query.filter(Refund.refund_amount <= max_amount)
        if from_date:
            query = query.filter(
                Refund.created_at >= datetime.strptime(from_date, "%Y-%m-%d")
            )
        if to_date:
            query = query.filter(
                Refund.created_at <= datetime.strptime(to_date, "%Y-%m-%d")
            )

        sort_column = getattr(Refund, sort_by)
        query = query.order_by(
            sort_column.desc() if sort_order == "desc" else sort_column.asc()
        )
        pagination = query.paginate(page=page, per_page=limit, error_out=False)

        refunds = []
        for r in pagination.items:
            user = User.query.get(r.user_id)
            order = Orders.query.get(r.order_id)
            refunds.append(
                {
                    "id": r.id,
                    "reason": r.reason,
                    "description": r.description,
                    "refund_amount": r.refund_amount,
                    "refund_type": r.refund_type,
                    "item_ids": r.item_ids,
                    "status": r.status,
                    "razorpay_refund_id": r.razorpay_refund_id,
                    "bank_reference": r.bank_reference,
                    "rejection_reason": r.rejection_reason,
                    "processed_at": r.processed_at,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                    "user": (
                        {
                            "id": user.id,
                            "username": user.username,
                            "email": user.email,
                            "phone_number": user.phone_number,
                            "profile_picture": user.profile_picture,
                        }
                        if user
                        else None
                    ),
                    "order": (
                        {
                            "id": order.id,
                            "order_id": order.order_id,
                            "status": order.status,
                            "total_price": order.total_price,
                        }
                        if order
                        else None
                    ),
                }
            )

        all_refunds = Refund.query.all()
        total_refunded = sum(
            r.refund_amount for r in all_refunds if r.status == "processed"
        )
        summary = {
            "total_refunds": len(all_refunds),
            "total_refunded_amount": round(total_refunded, 2),
            "pending_refunds": sum(1 for r in all_refunds if r.status == "pending"),
            "processed_refunds": sum(1 for r in all_refunds if r.status == "processed"),
            "rejected_refunds": sum(1 for r in all_refunds if r.status == "rejected"),
            "full_refunds": sum(1 for r in all_refunds if r.refund_type == "full"),
            "partial_refunds": sum(
                1 for r in all_refunds if r.refund_type == "partial"
            ),
        }

        return (
            jsonify(
                {
                    "status": "success",
                    "refunds": refunds,
                    "total": pagination.total,
                    "pages": pagination.pages,
                    "page": page,
                    "limit": limit,
                    "summary": summary,
                }
            ),
            200,
        )
    except Exception as e:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to fetch refunds",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/refunds/<int:refund_id>", methods=["GET"])
@admin_middleware
def get_refund(refund_id):
    try:
        refund = Refund.query.get(refund_id)
        if not refund:
            return jsonify({"status": "error", "message": "Refund not found"}), 404

        user = User.query.get(refund.user_id)
        order = Orders.query.get(refund.order_id)
        payment = Payment.query.get(refund.payment_id)
        items = []
        if refund.item_ids:
            items = [
                {
                    "id": i.id,
                    "product_name": i.product_name,
                    "product_sku": i.product_sku,
                    "product_image": i.product_image,
                    "quantity": i.quantity,
                    "unit_price": i.unit_price,
                    "total_price": i.total_price,
                }
                for i in OrderedItems.query.filter(
                    OrderedItems.id.in_(refund.item_ids)
                ).all()
            ]

        return (
            jsonify(
                {
                    "status": "success",
                    "refund": {
                        "id": refund.id,
                        "reason": refund.reason,
                        "description": refund.description,
                        "refund_amount": refund.refund_amount,
                        "refund_type": refund.refund_type,
                        "item_ids": refund.item_ids,
                        "status": refund.status,
                        "razorpay_refund_id": refund.razorpay_refund_id,
                        "bank_reference": refund.bank_reference,
                        "rejection_reason": refund.rejection_reason,
                        "processed_at": refund.processed_at,
                        "created_at": refund.created_at,
                        "updated_at": refund.updated_at,
                        "user": (
                            {
                                "id": user.id,
                                "username": user.username,
                                "email": user.email,
                                "phone_number": user.phone_number,
                                "profile_picture": user.profile_picture,
                            }
                            if user
                            else None
                        ),
                        "order": (
                            {
                                "id": order.id,
                                "order_id": order.order_id,
                                "status": order.status,
                                "total_price": order.total_price,
                                "payment_method": order.payment_method,
                            }
                            if order
                            else None
                        ),
                        "payment": (
                            {
                                "id": payment.id,
                                "payment_method": payment.payment_method,
                                "amount": payment.amount,
                                "status": payment.status,
                                "razorpay_payment_id": payment.razorpay_payment_id,
                            }
                            if payment
                            else None
                        ),
                        "refund_items": items,
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
                    "message": "Failed to fetch refund",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/refunds/<int:refund_id>", methods=["PUT"])
@admin_middleware
def update_refund(refund_id):
    try:
        refund = Refund.query.get(refund_id)
        if not refund:
            return jsonify({"status": "error", "message": "Refund not found"}), 404

        data = request.get_json()
        allowed_statuses = ["pending", "processed", "rejected"]

        if "status" in data:
            if data["status"] not in allowed_statuses:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": f"Invalid status. Allowed: {', '.join(allowed_statuses)}",
                        }
                    ),
                    400,
                )

            refund.status = data["status"]

            if data["status"] == "processed":
                refund.processed_at = datetime.utcnow()
                payment = Payment.query.get(refund.payment_id)
                if payment:
                    payment.refund_status = "processed"
                    payment.refund_amount = refund.refund_amount
                order = Orders.query.get(refund.order_id)
                if order:
                    old_order_status = order.status
                    order.status = "returned"
                    order.payment_status = "refunded"

                    try:
                        if old_order_status != "returned":
                            already_reversed = (
                                VendorWalletTransaction.query.filter_by(
                                    source="refund_reversal", reference_id=order.id
                                ).first()
                                is not None
                            )
                            if not already_reversed:
                                credit_txns = VendorWalletTransaction.query.filter_by(
                                    source="order_earning", reference_id=order.id
                                ).all()
                                vendor_credit_map = {}
                                for t in credit_txns:
                                    v_id = t.wallet.vendor_id
                                    vendor_credit_map[v_id] = (
                                        vendor_credit_map.get(v_id, 0.0) + t.amount
                                    )

                                for (
                                    vendor_id,
                                    credited_amount,
                                ) in vendor_credit_map.items():
                                    try:
                                        debit_wallet(
                                            vendor_id=vendor_id,
                                            amount=round(credited_amount, 2),
                                            source="refund_reversal",
                                            reference_id=order.id,
                                            note=f"Refund #{refund.id} processed — order #{order.order_id} returned",
                                        )
                                    except ValueError as balance_err:
                                        print(
                                            f"[WALLET] Reversal shortfall on refund {refund.id}, "
                                            f"order {order.id}, vendor {vendor_id}: {balance_err}"
                                        )
                    except Exception as wallet_err:
                        print(
                            f"[WALLET ERROR] refund_id={refund.id} order_id={order.id} "
                            f"error={str(wallet_err)}"
                        )

            if data["status"] == "rejected":
                if not data.get("rejection_reason"):
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "message": "rejection_reason is required when rejecting",
                            }
                        ),
                        400,
                    )
                refund.rejection_reason = data["rejection_reason"]

        if "razorpay_refund_id" in data:
            refund.razorpay_refund_id = data["razorpay_refund_id"]
        if "bank_reference" in data:
            refund.bank_reference = data["bank_reference"]

        db.session.commit()
        return (
            jsonify({"status": "success", "message": "Refund updated successfully"}),
            200,
        )
    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to update refund",
                    "error": str(e),
                }
            ),
            500,
        )


# STORE SETTINGS
@adminBP.route("/store", methods=["POST"])
@admin_middleware
def create_store():
    try:
        existing = Store.query.first()
        if existing:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Store already exists, use PUT to update",
                    }
                ),
                409,
            )

        content_type = request.content_type or ""
        if "multipart/form-data" in content_type:
            data = request.form
            logo_url = None
            if "logo" in request.files:
                logo_url = upload_file(request.files["logo"], folder="store")
        else:
            data = request.get_json()
            logo_url = data.get("logo")

        if not data.get("name"):
            return (
                jsonify({"status": "error", "message": "Store name is required"}),
                400,
            )

        store = Store(
            name=data.get("name"),
            description=data.get("description"),
            logo=logo_url,
            address=data.get("address"),
            gst_number=data.get("gst_number"),
            support_email=data.get("support_email"),
            support_phone=data.get("support_phone"),
        )
        db.session.add(store)
        db.session.commit()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Store created successfully",
                    "id": store.id,
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
                    "message": "Failed to create store",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/store", methods=["GET"])
@admin_middleware
def get_store():
    try:
        store = Store.query.first()
        if not store:
            return jsonify({"status": "error", "message": "Store not found"}), 404

        return (
            jsonify(
                {
                    "status": "success",
                    "store": {
                        "id": store.id,
                        "name": store.name,
                        "description": store.description,
                        "logo": store.logo,
                        "address": store.address,
                        "gst_number": store.gst_number,
                        "support_email": store.support_email,
                        "support_phone": store.support_phone,
                        "created_at": store.created_at,
                        "updated_at": store.updated_at,
                    },
                }
            ),
            200,
        )
    except Exception as e:
        return (
            jsonify(
                {"status": "error", "message": "Failed to fetch store", "error": str(e)}
            ),
            500,
        )


@adminBP.route("/store", methods=["PUT"])
@admin_middleware
def update_store():
    try:
        store = Store.query.first()
        if not store:
            return jsonify({"status": "error", "message": "Store not found"}), 404

        content_type = request.content_type or ""
        if "multipart/form-data" in content_type:
            data = request.form
            if "logo" in request.files:
                store.logo = upload_file(request.files["logo"], folder="store")
        else:
            data = request.get_json()
            if "logo" in data:
                store.logo = data["logo"]

        fields = [
            "name",
            "description",
            "address",
            "gst_number",
            "support_email",
            "support_phone",
        ]
        for field in fields:
            if field in data:
                setattr(store, field, data[field])

        db.session.commit()
        return (
            jsonify({"status": "success", "message": "Store updated successfully"}),
            200,
        )
    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to update store",
                    "error": str(e),
                }
            ),
            500,
        )


# ─── NOTIFICATION SETTINGS ────────────────────────────────────────────────────


@adminBP.route("/notifications", methods=["POST"])
@admin_middleware
def create_notification_settings():
    try:
        existing = Notification.query.first()
        if existing:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Notification settings already exist, use PUT to update",
                    }
                ),
                409,
            )

        data = request.get_json()
        notification = Notification(
            order_placed=data.get("order_placed", False),
            payment_failed=data.get("payment_failed", False),
            low_stock=data.get("low_stock", False),
            new_user_registration=data.get("new_user_registration", False),
            new_product_review=data.get("new_product_review", False),
            email_notifications=data.get("email_notifications", False),
            sms_notifications=data.get("sms_notifications", False),
            push_notifications=data.get("push_notifications", False),
        )
        db.session.add(notification)
        db.session.commit()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Notification settings created successfully",
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
                    "message": "Failed to create notification settings",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/notifications", methods=["GET"])
@admin_middleware
def get_notification_settings():
    try:
        notification = Notification.query.first()
        if not notification:
            return (
                jsonify(
                    {"status": "error", "message": "Notification settings not found"}
                ),
                404,
            )

        return (
            jsonify(
                {
                    "status": "success",
                    "notifications": {
                        "id": notification.id,
                        "order_placed": notification.order_placed,
                        "payment_failed": notification.payment_failed,
                        "low_stock": notification.low_stock,
                        "new_user_registration": notification.new_user_registration,
                        "new_product_review": notification.new_product_review,
                        "email_notifications": notification.email_notifications,
                        "sms_notifications": notification.sms_notifications,
                        "push_notifications": notification.push_notifications,
                        "created_at": notification.created_at,
                        "updated_at": notification.updated_at,
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
                    "message": "Failed to fetch notification settings",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/notifications", methods=["PUT"])
@admin_middleware
def update_notification_settings():
    try:
        notification = Notification.query.first()
        if not notification:
            return (
                jsonify(
                    {"status": "error", "message": "Notification settings not found"}
                ),
                404,
            )

        data = request.get_json()
        fields = [
            "order_placed",
            "payment_failed",
            "low_stock",
            "new_user_registration",
            "new_product_review",
            "email_notifications",
            "sms_notifications",
            "push_notifications",
        ]
        for field in fields:
            if field in data:
                setattr(notification, field, data[field])

        db.session.commit()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Notification settings updated successfully",
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
                    "message": "Failed to update notification settings",
                    "error": str(e),
                }
            ),
            500,
        )


# ─── PAYMENT SETTINGS ─────────────────────────────────────────────────────────


@adminBP.route("/payment-settings", methods=["POST"])
@admin_middleware
def create_payment_settings():
    try:
        existing = PaymentSettings.query.first()
        if existing:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Payment settings already exist, use PUT to update",
                    }
                ),
                409,
            )

        data = request.get_json()
        if (
            not data.get("payment_gateway")
            or not data.get("api_key")
            or not data.get("api_secret")
        ):
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "payment_gateway, api_key and api_secret are required",
                    }
                ),
                400,
            )

        settings = PaymentSettings(
            payment_gateway=data.get("payment_gateway"),
            api_key=data.get("api_key"),
            api_secret=data.get("api_secret"),
            upi_id=data.get("upi_id"),
            cod=data.get("cod", False),
        )
        db.session.add(settings)
        db.session.commit()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Payment settings created successfully",
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
                    "message": "Failed to create payment settings",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/payment-settings", methods=["GET"])
@admin_middleware
def get_payment_settings():
    try:
        settings = PaymentSettings.query.first()
        if not settings:
            return (
                jsonify({"status": "error", "message": "Payment settings not found"}),
                404,
            )

        return (
            jsonify(
                {
                    "status": "success",
                    "payment_settings": {
                        "id": settings.id,
                        "payment_gateway": settings.payment_gateway,
                        "api_key": settings.api_key,
                        "api_secret": settings.api_secret,
                        "upi_id": settings.upi_id,
                        "cod": settings.cod,
                        "created_at": settings.created_at,
                        "updated_at": settings.updated_at,
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
                    "message": "Failed to fetch payment settings",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/payment-settings", methods=["PUT"])
@admin_middleware
def update_payment_settings():
    try:
        settings = PaymentSettings.query.first()
        if not settings:
            return (
                jsonify({"status": "error", "message": "Payment settings not found"}),
                404,
            )

        data = request.get_json()
        fields = ["payment_gateway", "api_key", "api_secret", "upi_id", "cod"]
        for field in fields:
            if field in data:
                setattr(settings, field, data[field])

        db.session.commit()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Payment settings updated successfully",
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
                    "message": "Failed to update payment settings",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/dashboard", methods=["GET"])
@admin_middleware
def get_dashboard():
    try:
        today = datetime.utcnow().date()
        this_month_start = datetime(today.year, today.month, 1)
        last_month_start = (
            datetime(today.year, today.month - 1, 1)
            if today.month > 1
            else datetime(today.year - 1, 12, 1)
        )
        last_month_end = this_month_start

        all_orders = Orders.query.all()
        all_users = User.query.all()
        all_products = Products.query.all()
        all_categories = Category.query.all()
        all_payments = Payment.query.all()
        all_refunds = Refund.query.all()
        all_reviews = ProductReview.query.all()

        # revenue
        total_revenue = sum(
            o.total_price
            for o in all_orders
            if o.total_price and o.status != "cancelled"
        )
        today_orders = [o for o in all_orders if o.created_at.date() == today]
        today_revenue = sum(
            o.total_price
            for o in today_orders
            if o.total_price and o.status != "cancelled"
        )
        month_orders = [o for o in all_orders if o.created_at >= this_month_start]
        month_revenue = sum(
            o.total_price
            for o in month_orders
            if o.total_price and o.status != "cancelled"
        )
        last_month_orders = [
            o for o in all_orders if last_month_start <= o.created_at < last_month_end
        ]
        last_month_revenue = sum(
            o.total_price
            for o in last_month_orders
            if o.total_price and o.status != "cancelled"
        )

        # monthly revenue chart (last 6 months)
        monthly_revenue = []
        for i in range(5, -1, -1):
            month = today.month - i
            year = today.year
            if month <= 0:
                month += 12
                year -= 1
            month_data = [
                o
                for o in all_orders
                if o.created_at.month == month
                and o.created_at.year == year
                and o.status != "cancelled"
            ]
            monthly_revenue.append(
                {
                    "month": datetime(year, month, 1).strftime("%b %Y"),
                    "revenue": round(
                        sum(o.total_price for o in month_data if o.total_price), 2
                    ),
                    "orders": len(month_data),
                }
            )

        # top products by order count
        from collections import Counter

        all_ordered_items = OrderedItems.query.all()
        product_counts = Counter(i.product_id for i in all_ordered_items)
        top_product_ids = [pid for pid, _ in product_counts.most_common(5)]
        top_products = []
        for pid in top_product_ids:
            p = Products.query.get(pid)
            if p:
                top_products.append(
                    {
                        "id": p.id,
                        "name": p.name,
                        "product_image": p.product_image,
                        "price": p.price,
                        "sku": p.sku,
                        "orders": product_counts[pid],
                    }
                )

        # top categories by product count
        top_categories = sorted(
            all_categories, key=lambda c: len(c.products), reverse=True
        )[:5]

        # low stock products
        low_stock_products = [
            {
                "id": p.id,
                "name": p.name,
                "product_image": p.product_image,
                "sku": p.sku,
                "stock": p.stock,
                "quantity": p.quantity,
            }
            for p in all_products
            if p.stock <= 5
        ]

        # recent orders
        recent_orders = Orders.query.order_by(Orders.created_at.desc()).limit(5).all()
        recent_orders_data = []
        for o in recent_orders:
            user = User.query.get(o.user_id)
            recent_orders_data.append(
                {
                    "id": o.id,
                    "order_id": o.order_id,
                    "status": o.status,
                    "total_price": o.total_price,
                    "payment_method": o.payment_method,
                    "created_at": o.created_at,
                    "user": (
                        {
                            "id": user.id,
                            "username": user.username,
                            "email": user.email,
                            "profile_picture": user.profile_picture,
                        }
                        if user
                        else None
                    ),
                }
            )

        # recent users
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        recent_users_data = [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "profile_picture": u.profile_picture,
                "role": u.role,
                "created_at": u.created_at,
            }
            for u in recent_users
        ]

        ratings = [r.rating for r in all_reviews]

        return (
            jsonify(
                {
                    "status": "success",
                    "dashboard": {
                        # top cards
                        "cards": {
                            "total_revenue": round(total_revenue, 2),
                            "today_revenue": round(today_revenue, 2),
                            "month_revenue": round(month_revenue, 2),
                            "last_month_revenue": round(last_month_revenue, 2),
                            "total_orders": len(all_orders),
                            "today_orders": len(today_orders),
                            "month_orders": len(month_orders),
                            "total_users": len(all_users),
                            "new_users_today": sum(
                                1 for u in all_users if u.created_at.date() == today
                            ),
                            "new_users_this_month": sum(
                                1 for u in all_users if u.created_at >= this_month_start
                            ),
                            "total_products": len(all_products),
                            "active_products": sum(
                                1 for p in all_products if p.status == "active"
                            ),
                            "out_of_stock": sum(
                                1 for p in all_products if p.stock == 0
                            ),
                            "low_stock_count": len(low_stock_products),
                            "total_categories": len(all_categories),
                            "total_reviews": len(all_reviews),
                            "avg_rating": (
                                round(sum(ratings) / len(ratings), 2) if ratings else 0
                            ),
                            "pending_refunds": sum(
                                1 for r in all_refunds if r.status == "pending"
                            ),
                            "total_refunded": round(
                                sum(
                                    r.refund_amount
                                    for r in all_refunds
                                    if r.status == "processed"
                                ),
                                2,
                            ),
                            "failed_payments": sum(
                                1 for p in all_payments if p.status == "failed"
                            ),
                        },
                        # order breakdown
                        "order_status_breakdown": {
                            "pending": sum(
                                1 for o in all_orders if o.status == "pending"
                            ),
                            "processing": sum(
                                1 for o in all_orders if o.status == "processing"
                            ),
                            "shipped": sum(
                                1 for o in all_orders if o.status == "shipped"
                            ),
                            "delivered": sum(
                                1 for o in all_orders if o.status == "delivered"
                            ),
                            "cancelled": sum(
                                1 for o in all_orders if o.status == "cancelled"
                            ),
                            "returned": sum(
                                1 for o in all_orders if o.status == "returned"
                            ),
                        },
                        # payment breakdown
                        "payment_breakdown": {
                            "cod": sum(
                                1 for o in all_orders if o.payment_method == "cod"
                            ),
                            "razorpay": sum(
                                1 for o in all_orders if o.payment_method == "razorpay"
                            ),
                            "paid": sum(
                                1 for o in all_orders if o.payment_status == "paid"
                            ),
                            "unpaid": sum(
                                1 for o in all_orders if o.payment_status == "unpaid"
                            ),
                            "refunded": sum(
                                1 for o in all_orders if o.payment_status == "refunded"
                            ),
                        },
                        # charts
                        "monthly_revenue_chart": monthly_revenue,
                        # lists
                        "top_products": top_products,
                        "top_categories": [
                            {
                                "id": c.id,
                                "name": c.name,
                                "slug": c.slug,
                                "icon": c.icon,
                                "color": c.color,
                                "total_products": len(c.products),
                            }
                            for c in top_categories
                        ],
                        "low_stock_products": low_stock_products,
                        "recent_orders": recent_orders_data,
                        "recent_users": recent_users_data,
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


@adminBP.route("/collection", methods=["POST"])
@admin_middleware
def create_collection():
    try:
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        product_ids = request.form.getlist("product_ids")  # list of int strings

        if not name:
            return jsonify({"status": "error", "message": "Name is required"}), 400

        if Collection.query.filter_by(name=name).first():
            return (
                jsonify(
                    {"status": "error", "message": "Collection name already exists"}
                ),
                409,
            )

        image_url = None
        if "image" in request.files:
            image_url = upload_file(request.files["image"], folder="collections")

        collection = Collection(name=name, description=description, image=image_url)
        db.session.add(collection)
        db.session.flush()  # get collection.id before commit

        added_products = []
        skipped_products = []

        for pid in product_ids:
            try:
                pid = int(pid)
            except ValueError:
                skipped_products.append({"id": pid, "reason": "Invalid ID"})
                continue

            product = Products.query.get(pid)
            if not product:
                skipped_products.append({"id": pid, "reason": "Product not found"})
                continue

            cp = CollectionProducts(product_id=pid, collection_id=collection.id)
            db.session.add(cp)
            added_products.append(pid)

        db.session.commit()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Collection created",
                    "collection_id": collection.id,
                    "added_products": added_products,
                    "skipped_products": skipped_products,
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
                    "message": "Failed to create collection",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/collection", methods=["GET"])
@admin_middleware
def get_collections():
    try:
        collections = Collection.query.all()
        result = []
        for c in collections:
            result.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "description": c.description,
                    "image": c.image,
                    "product_count": len(c.collection_products),
                    "products": [
                        {
                            "id": cp.product.id,
                            "name": cp.product.name,
                            "product_image": cp.product.product_image,
                            "price": cp.product.price,
                            "status": cp.product.status,
                        }
                        for cp in c.collection_products
                    ],
                }
            )
        return jsonify({"status": "success", "collections": result}), 200

    except Exception as e:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to fetch collections",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/collection/<int:collection_id>", methods=["GET"])
@admin_middleware
def get_collection(collection_id):
    try:
        c = Collection.query.get(collection_id)
        if not c:
            return jsonify({"status": "error", "message": "Collection not found"}), 404

        return (
            jsonify(
                {
                    "status": "success",
                    "collection": {
                        "id": c.id,
                        "name": c.name,
                        "description": c.description,
                        "image": c.image,
                        "product_count": len(c.collection_products),
                        "products": [
                            {
                                "id": cp.product.id,
                                "name": cp.product.name,
                                "product_image": cp.product.product_image,
                                "price": cp.product.price,
                                "compare_at_price": cp.product.compare_at_price,
                                "stock": cp.product.stock,
                                "status": cp.product.status,
                                "sku": cp.product.sku,
                            }
                            for cp in c.collection_products
                        ],
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
                    "message": "Failed to fetch collection",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/collection/<int:collection_id>", methods=["PUT"])
@admin_middleware
def edit_collection(collection_id):
    try:
        c = Collection.query.get(collection_id)
        if not c:
            return jsonify({"status": "error", "message": "Collection not found"}), 404

        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        add_product_ids = request.form.getlist("add_product_ids")  # products to add
        remove_product_ids = request.form.getlist(
            "remove_product_ids"
        )  # products to remove

        if name:
            existing = Collection.query.filter(
                Collection.name == name, Collection.id != collection_id
            ).first()
            if existing:
                return (
                    jsonify(
                        {"status": "error", "message": "Collection name already exists"}
                    ),
                    409,
                )
            c.name = name

        if description:
            c.description = description

        if "image" in request.files:
            c.image = upload_file(request.files["image"], folder="collections")

        removed = []
        skipped_remove = []
        for pid in remove_product_ids:
            try:
                pid = int(pid)
            except ValueError:
                skipped_remove.append({"id": pid, "reason": "Invalid ID"})
                continue

            cp = CollectionProducts.query.filter_by(
                product_id=pid, collection_id=collection_id
            ).first()
            if not cp:
                skipped_remove.append({"id": pid, "reason": "Not in collection"})
                continue

            db.session.delete(cp)
            removed.append(pid)

        added = []
        skipped_add = []
        for pid in add_product_ids:
            try:
                pid = int(pid)
            except ValueError:
                skipped_add.append({"id": pid, "reason": "Invalid ID"})
                continue

            if not Products.query.get(pid):
                skipped_add.append({"id": pid, "reason": "Product not found"})
                continue

            already_exists = CollectionProducts.query.filter_by(
                product_id=pid, collection_id=collection_id
            ).first()
            if already_exists:
                skipped_add.append({"id": pid, "reason": "Already in collection"})
                continue

            db.session.add(
                CollectionProducts(product_id=pid, collection_id=collection_id)
            )
            added.append(pid)

        db.session.commit()
        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Collection updated",
                    "added": added,
                    "removed": removed,
                    "skipped_add": skipped_add,
                    "skipped_remove": skipped_remove,
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
                    "message": "Failed to update collection",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/collection/<int:collection_id>", methods=["DELETE"])
@admin_middleware
def delete_collection(collection_id):
    try:
        c = Collection.query.get(collection_id)
        if not c:
            return jsonify({"status": "error", "message": "Collection not found"}), 404

        db.session.delete(c)
        db.session.commit()
        return jsonify({"status": "success", "message": "Collection deleted"}), 200

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to delete collection",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/affiliates", methods=["GET"])
@admin_middleware
def get_all_affiliates():
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)
        per_page = min(per_page, 50)

        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")
        sort_by = request.args.get(
            "sort_by", "created_at"
        )  # created_at | total_revenue | total_orders | total_withdrawal
        order = request.args.get("order", "desc")

        query = AffiliateDashboard.query

        if date_from:
            query = query.filter(AffiliateDashboard.created_at >= date_from)
        if date_to:
            query = query.filter(AffiliateDashboard.created_at <= date_to)

        sort_column = getattr(
            AffiliateDashboard, sort_by, AffiliateDashboard.created_at
        )
        query = query.order_by(
            sort_column.desc() if order == "desc" else sort_column.asc()
        )

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)

        affiliates = [
            {
                "id": a.id,
                "user_id": a.user_id,
                "username": a.user.username,
                "email": a.user.email,
                "affiliate_id": a.user.affiliate_id,
                "total_orders": a.total_orders,
                "total_revenue": a.total_revenue,
                "total_withdrawal": a.total_withdrawal,
                "upi_id": a.upi_id,
                "created_at": a.created_at,
            }
            for a in paginated.items
        ]

        return (
            jsonify(
                {
                    "status": "success",
                    "data": affiliates,
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
                    "message": "Failed to fetch affiliates",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/affiliates/<int:affiliate_id>", methods=["GET"])
@admin_middleware
def get_affiliate(affiliate_id):
    try:
        dashboard = AffiliateDashboard.query.get(affiliate_id)
        if not dashboard:
            return jsonify({"status": "error", "message": "Affiliate not found"}), 404

        available_balance = dashboard.total_revenue - dashboard.total_withdrawal

        recent_withdrawals = [
            {
                "id": w.id,
                "amount": w.amount,
                "status": w.status,
                "payslip": w.payslip,
                "created_at": w.created_at,
            }
            for w in dashboard.withdrawals[-5:]
        ]

        recent_orders = [
            {
                "id": o.id,
                "order_id": o.order_id,
                "product_id": o.product_id,
                "commission": o.commission,
                "revenue": o.revenue,
                "status": o.status,
                "created_at": o.created_at,
            }
            for o in dashboard.orderlist[-5:]
        ]

        return (
            jsonify(
                {
                    "status": "success",
                    "data": {
                        "id": affiliate_id,
                        "user_id": dashboard.user_id,
                        "username": dashboard.user.username,
                        "email": dashboard.user.email,
                        "phone": dashboard.user.phone_number,
                        "affiliate_id": dashboard.user.affiliate_id,
                        "upi_id": dashboard.upi_id,
                        "total_orders": dashboard.total_orders,
                        "total_revenue": dashboard.total_revenue,
                        "total_withdrawal": dashboard.total_withdrawal,
                        "available_balance": available_balance,
                        "recent_orders": recent_orders,
                        "recent_withdrawals": recent_withdrawals,
                        "created_at": dashboard.created_at,
                        "updated_at": dashboard.updated_at,
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
                    "message": "Failed to fetch affiliate",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/withdrawals", methods=["GET"])
@admin_middleware
def get_all_withdrawals():
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)
        per_page = min(per_page, 50)

        status = request.args.get("status")  # pending | approved
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")
        order = request.args.get("order", "desc")

        query = Withdrawal.query

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
                "affiliate_id": w.affiliate_id,
                "username": w.affiliate.user.username,
                "email": w.affiliate.user.email,
                "upi_id": w.affiliate.upi_id,
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


# 8. ADMIN — APPROVE WITHDRAWAL + UPLOAD PAYSLIP
@adminBP.route("/withdrawal/<int:withdrawal_id>", methods=["PUT"])
@admin_middleware
def approve_withdrawal(withdrawal_id):
    try:
        status = request.form.get("status")
        note = request.form.get("note")
        payslip_file = request.files.get("payslip")

        if status not in ("approved", "pending", "rejected"):
            return jsonify({"status": "error", "message": "Invalid status"}), 400

        withdrawal = Withdrawal.query.get(withdrawal_id)
        if not withdrawal:
            return jsonify({"status": "error", "message": "Withdrawal not found"}), 404

        withdrawal.status = status

        if status == "approved":
            if not payslip_file or note:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Payslip file is required for approval",
                        }
                    ),
                    400,
                )

            payslip_url = upload_file(payslip_file, folder="payslips")
            withdrawal.payslip = payslip_url

            dashboard = AffiliateDashboard.query.get(withdrawal.affiliate_id)
            dashboard.total_withdrawal += withdrawal.amount

            notification = Notifications(
                affiliate_id=withdrawal.affiliate_id,
                message=f"Your withdrawal of ₹{withdrawal.amount} has been approved.",
            )
            db.session.add(notification)

        if status == "rejected":
            if not payslip_file:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Payslip file and reason is required for rejected",
                        }
                    ),
                    400,
                )

            payslip_url = upload_file(payslip_file, folder="payslips")
            withdrawal.payslip = payslip_url
            withdrawal.note = note

            dashboard = AffiliateDashboard.query.get(withdrawal.affiliate_id)
            dashboard.total_withdrawal -= withdrawal.amount
            notification = Notifications(
                affiliate_id=withdrawal.affiliate_id,
                message=f"Your withdrawal of ₹{withdrawal.amount} has been rejected.",
            )
            db.session.add(notification)

        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": f"Withdrawal {status}",
                    "data": {
                        "withdrawal_id": withdrawal.id,
                        "status": withdrawal.status,
                        "payslip": withdrawal.payslip,
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
                    "message": "Failed to update withdrawal",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/vendor", methods=["GET"])
@admin_middleware
def list_vendors():
    try:
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)
        approval_status = request.args.get("approval_status")
        is_active = request.args.get("is_active")
        search = request.args.get("search")

        query = Vendor.query

        if approval_status:
            query = query.filter(Vendor.approval_status == approval_status)
        if is_active is not None:
            query = query.filter(Vendor.is_active == (is_active.lower() == "true"))
        if search:
            query = query.join(Admin).filter(
                db.or_(
                    Vendor.store_name.ilike(f"%{search}%"),
                    Admin.username.ilike(f"%{search}%"),
                )
            )

        query = query.order_by(Vendor.created_at.desc())
        pagination = query.paginate(page=page, per_page=limit, error_out=False)

        vendors = []
        for v in pagination.items:
            admin = Admin.query.get(v.admin_id)
            total_products = Products.query.filter_by(vendor_id=v.id).count()
            vendors.append(
                {
                    "id": v.id,
                    "store_name": v.store_name,
                    "gst_number": v.gst_number,
                    "commission_rate": v.commission_rate,
                    "approval_status": v.approval_status,
                    "is_active": v.is_active,
                    "total_products": total_products,
                    "created_at": v.created_at,
                    "admin": (
                        {
                            "id": admin.id,
                            "username": admin.username,
                            "phone_number": admin.phone_number,
                        }
                        if admin
                        else None
                    ),
                }
            )

        return (
            jsonify(
                {
                    "status": "success",
                    "vendors": vendors,
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
                    "message": "Failed to fetch vendors",
                    "error": str(e),
                }
            ),
            500,
        )


import calendar


@adminBP.route("/vendor/<int:vendor_id>", methods=["GET"])
@admin_middleware
def get_vendor_detail(vendor_id):
    try:
        vendor = Vendor.query.get(vendor_id)
        if not vendor:
            return jsonify({"status": "error", "message": "Vendor not found"}), 404

        admin = Admin.query.get(vendor.admin_id)

        all_products = Products.query.filter_by(vendor_id=vendor.id).all()
        product_stats = {
            "total": len(all_products),
            "active": sum(1 for p in all_products if p.status == "active"),
            "pending_review": sum(
                1 for p in all_products if p.status == "pending_review"
            ),
            "rejected": sum(1 for p in all_products if p.status == "rejected"),
        }

        base_items_query = (
            db.session.query(OrderedItems, Orders)
            .join(Orders, Orders.id == OrderedItems.order_id)
            .join(Products, Products.id == OrderedItems.product_id)
            .filter(Products.vendor_id == vendor.id)
        )

        def is_revenue_eligible(order):
            return order.status == "delivered" and order.payment_status == "paid"

        month_param = request.args.get("month")
        month_start = month_end = None
        if month_param:
            try:
                year, month = map(int, month_param.split("-"))
                month_start = datetime(year, month, 1)
                last_day = calendar.monthrange(year, month)[1]
                month_end = datetime(year, month, last_day, 23, 59, 59)
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

        filtered_items_query = base_items_query
        if month_start and month_end:
            filtered_items_query = filtered_items_query.filter(
                Orders.created_at >= month_start, Orders.created_at <= month_end
            )

        # ---- Overall lifetime stats ----
        # total_orders counts ALL orders touching this vendor (any status), but
        # total_revenue only counts revenue-eligible (delivered + paid) items —
        # these are intentionally different metrics.
        all_rows = base_items_query.all()
        total_orders = len({o.id for _, o in all_rows})
        total_revenue = sum(
            item.total_price for item, o in all_rows if is_revenue_eligible(o)
        )

        # ---- Current month stats ----
        now = datetime.utcnow()
        this_month_start = datetime(now.year, now.month, 1)
        this_month_rows = base_items_query.filter(
            Orders.created_at >= this_month_start
        ).all()
        this_month_orders = len({o.id for _, o in this_month_rows})
        this_month_revenue = sum(
            item.total_price for item, o in this_month_rows if is_revenue_eligible(o)
        )

        # ---- Filtered (month-param) order + revenue list, paginated ----
        order_page = request.args.get("order_page", 1, type=int)
        order_limit = request.args.get("order_limit", 10, type=int)

        filtered_rows = filtered_items_query.order_by(Orders.created_at.desc()).all()
        filtered_revenue = sum(
            item.total_price for item, o in filtered_rows if is_revenue_eligible(o)
        )

        orders_map = {}
        for item, order in filtered_rows:
            if order.id not in orders_map:
                orders_map[order.id] = {
                    "order_id": order.id,
                    "order_number": order.order_id,
                    "status": order.status,
                    "payment_status": order.payment_status,
                    "created_at": order.created_at,
                    "items": [],
                    "order_revenue": 0.0,
                    "revenue_eligible": is_revenue_eligible(order),
                }
            orders_map[order.id]["items"].append(
                {
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "total_price": item.total_price,
                }
            )
            orders_map[order.id]["order_revenue"] += item.total_price

        order_list_all = sorted(
            orders_map.values(), key=lambda o: o["created_at"], reverse=True
        )
        orders_total = len(order_list_all)
        start = (order_page - 1) * order_limit
        order_list_page = order_list_all[start : start + order_limit]

        # ---- Payout requests ----
        payout_status = request.args.get("payout_status")
        payout_page = request.args.get("payout_page", 1, type=int)
        payout_limit = request.args.get("payout_limit", 10, type=int)

        payout_query = VendorPayout.query.filter_by(vendor_id=vendor.id)
        if payout_status:
            payout_query = payout_query.filter(VendorPayout.status == payout_status)
        payout_query = payout_query.order_by(VendorPayout.created_at.desc())
        payout_pagination = payout_query.paginate(
            page=payout_page, per_page=payout_limit, error_out=False
        )

        payouts_list = [
            {
                "id": p.id,
                "amount": p.amount,
                "status": p.status,
                "payment_screenshot": p.payment_screenshot,
                "note": p.note,
                "created_at": p.created_at,
                "updated_at": p.updated_at,
            }
            for p in payout_pagination.items
        ]

        all_payouts = VendorPayout.query.filter_by(vendor_id=vendor.id).all()
        payout_counts = {
            "total": len(all_payouts),
            "pending": sum(1 for p in all_payouts if p.status == "pending"),
            "approved": sum(1 for p in all_payouts if p.status == "approved"),
            "rejected": sum(1 for p in all_payouts if p.status == "rejected"),
        }
        total_paid_out = sum(p.amount for p in all_payouts if p.status == "approved")

        return (
            jsonify(
                {
                    "status": "success",
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
                        "updated_at": vendor.updated_at,
                        "admin": (
                            {
                                "id": admin.id,
                                "username": admin.username,
                                "phone_number": admin.phone_number,
                                "bio": admin.bio,
                            }
                            if admin
                            else None
                        ),
                        "product_stats": product_stats,
                        "stats": {
                            "total_orders": total_orders,
                            "total_revenue": round(total_revenue, 2),
                            "this_month_orders": this_month_orders,
                            "this_month_revenue": round(this_month_revenue, 2),
                            "total_paid_out": round(total_paid_out, 2),
                        },
                        "filter": {
                            "month": month_param,
                            "filtered_orders_total": orders_total,
                            "filtered_revenue": round(filtered_revenue, 2),
                        },
                        "orders": {
                            "items": order_list_page,
                            "total": orders_total,
                            "page": order_page,
                            "limit": order_limit,
                            "pages": (
                                (orders_total + order_limit - 1) // order_limit
                                if order_limit
                                else 0
                            ),
                        },
                        "payouts": {
                            "items": payouts_list,
                            "total": payout_pagination.total,
                            "pages": payout_pagination.pages,
                            "page": payout_page,
                            "limit": payout_limit,
                            "counts": payout_counts,
                        },
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
                    "message": "Failed to fetch vendor",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/vendor/<int:vendor_id>/approve", methods=["PUT"])
@admin_middleware
def approve_vendor(vendor_id):
    try:
        vendor = Vendor.query.get(vendor_id)
        if not vendor:
            return jsonify({"status": "error", "message": "Vendor not found"}), 404

        vendor.approval_status = "approved"
        vendor.is_active = True
        db.session.commit()

        return (
            jsonify({"status": "success", "message": "Vendor approved successfully"}),
            200,
        )
    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to approve vendor",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/vendor/<int:vendor_id>/reject", methods=["PUT"])
@admin_middleware
def reject_vendor(vendor_id):
    try:
        vendor = Vendor.query.get(vendor_id)
        if not vendor:
            return jsonify({"status": "error", "message": "Vendor not found"}), 404

        vendor.approval_status = "rejected"
        db.session.commit()

        return (
            jsonify({"status": "success", "message": "Vendor application rejected"}),
            200,
        )
    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to reject vendor",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/vendor/<int:vendor_id>/toggle-active", methods=["PUT"])
@admin_middleware
def toggle_vendor_active(vendor_id):
    try:
        vendor = Vendor.query.get(vendor_id)
        if not vendor:
            return jsonify({"status": "error", "message": "Vendor not found"}), 404
        if vendor.approval_status != "approved":
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Only approved vendors can be activated/deactivated",
                    }
                ),
                400,
            )

        vendor.is_active = not vendor.is_active
        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": f"Vendor {'activated' if vendor.is_active else 'deactivated'} successfully",
                    "is_active": vendor.is_active,
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
                    "message": "Failed to update vendor status",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/vendor/<int:vendor_id>/commission", methods=["PUT"])
@admin_middleware
def update_vendor_commission(vendor_id):
    try:
        vendor = Vendor.query.get(vendor_id)
        if not vendor:
            return jsonify({"status": "error", "message": "Vendor not found"}), 404

        data = request.get_json()
        rate = data.get("commission_rate")

        if rate is None:
            return (
                jsonify({"status": "error", "message": "commission_rate is required"}),
                400,
            )
        try:
            rate = float(rate)
        except (ValueError, TypeError):
            return (
                jsonify(
                    {"status": "error", "message": "commission_rate must be a number"}
                ),
                400,
            )
        if rate < 0 or rate > 100:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "commission_rate must be between 0 and 100",
                    }
                ),
                400,
            )

        vendor.commission_rate = rate
        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Commission rate updated successfully",
                    "commission_rate": vendor.commission_rate,
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
                    "message": "Failed to update commission rate",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/product/<int:product_id>/approve", methods=["PUT"])
@admin_middleware
def approve_vendor_product(product_id):
    try:
        product = Products.query.get(product_id)
        if not product:
            return jsonify({"status": "error", "message": "Product not found"}), 404

        product.status = "active"
        db.session.commit()

        return (
            jsonify(
                {"status": "success", "message": "Product approved and is now live"}
            ),
            200,
        )
    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to approve product",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/product/<int:product_id>/reject", methods=["PUT"])
@admin_middleware
def reject_vendor_product(product_id):
    try:
        product = Products.query.get(product_id)
        if not product:
            return jsonify({"status": "error", "message": "Product not found"}), 404

        product.status = "rejected"
        db.session.commit()

        return (
            jsonify({"status": "success", "message": "Product rejected"}),
            200,
        )
    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to reject product",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/vendor-payout", methods=["GET"])
@admin_middleware
def list_vendor_payouts():
    try:
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)
        status = request.args.get("status")

        query = VendorPayout.query
        if status:
            query = query.filter(VendorPayout.status == status)

        query = query.order_by(VendorPayout.created_at.desc())
        pagination = query.paginate(page=page, per_page=limit, error_out=False)

        payouts = []
        for p in pagination.items:
            vendor = Vendor.query.get(p.vendor_id)
            payouts.append(
                {
                    "id": p.id,
                    "amount": p.amount,
                    "status": p.status,
                    "payment_screenshot": p.payment_screenshot,
                    "note": p.note,
                    "created_at": p.created_at,
                    "updated_at": p.updated_at,
                    "vendor": (
                        {
                            "id": vendor.id,
                            "store_name": vendor.store_name,
                            "upi_id": vendor.upi_id,
                            "bank_account_number": vendor.bank_account_number,
                            "bank_ifsc": vendor.bank_ifsc,
                            "bank_account_holder": vendor.bank_account_holder,
                        }
                        if vendor
                        else None
                    ),
                }
            )

        return (
            jsonify(
                {
                    "status": "success",
                    "payouts": payouts,
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
                    "message": "Failed to fetch payouts",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/vendor-payout/<int:payout_id>", methods=["GET"])
@admin_middleware
def get_vendor_payout_detail(payout_id):
    try:
        payout = VendorPayout.query.get(payout_id)
        if not payout:
            return (
                jsonify({"status": "error", "message": "Payout request not found"}),
                404,
            )

        vendor = Vendor.query.get(payout.vendor_id)

        # --- Wallet snapshot at time of viewing ---
        wallet = get_or_create_wallet(payout.vendor_id)
        db.session.commit()  # persist if wallet was just created

        # Money already tied up in OTHER pending requests (exclude this one)
        other_pending = (
            db.session.query(db.func.coalesce(db.func.sum(VendorPayout.amount), 0.0))
            .filter(
                VendorPayout.vendor_id == payout.vendor_id,
                VendorPayout.status == "pending",
                VendorPayout.id != payout.id,
            )
            .scalar()
        )

        requestable_balance = round(wallet.balance - other_pending, 2)

        if payout.status != "pending":
            is_valid_amount = True
            flag_reason = None
        elif payout.amount > wallet.balance:
            is_valid_amount = False
            flag_reason = "Requested amount exceeds total wallet balance"
        elif payout.amount > requestable_balance:
            is_valid_amount = False
            flag_reason = "Requested amount exceeds balance after accounting for other pending requests"
        else:
            is_valid_amount = True
            flag_reason = None

        recent_txns = (
            VendorWalletTransaction.query.filter_by(wallet_id=wallet.id)
            .order_by(VendorWalletTransaction.created_at.desc())
            .limit(10)
            .all()
        )

        payout_history_counts = {
            "total": VendorPayout.query.filter_by(vendor_id=payout.vendor_id).count(),
            "approved": VendorPayout.query.filter_by(
                vendor_id=payout.vendor_id, status="approved"
            ).count(),
            "rejected": VendorPayout.query.filter_by(
                vendor_id=payout.vendor_id, status="rejected"
            ).count(),
            "pending": VendorPayout.query.filter_by(
                vendor_id=payout.vendor_id, status="pending"
            ).count(),
        }

        return (
            jsonify(
                {
                    "status": "success",
                    "payout": {
                        "id": payout.id,
                        "amount": payout.amount,
                        "status": payout.status,
                        "payment_screenshot": payout.payment_screenshot,
                        "note": payout.note,
                        "created_at": payout.created_at,
                        "updated_at": payout.updated_at,
                        "vendor": (
                            {
                                "id": vendor.id,
                                "store_name": vendor.store_name,
                                "upi_id": vendor.upi_id,
                                "bank_account_number": vendor.bank_account_number,
                                "bank_ifsc": vendor.bank_ifsc,
                                "bank_account_holder": vendor.bank_account_holder,
                            }
                            if vendor
                            else None
                        ),
                        "wallet_check": {
                            "current_balance": wallet.balance,
                            "total_earned": wallet.total_earned,
                            "total_withdrawn": wallet.total_withdrawn,
                            "other_pending_requests": round(other_pending, 2),
                            "requestable_balance": requestable_balance,
                            "is_valid_amount": is_valid_amount,
                            "flag_reason": flag_reason,
                        },
                        "vendor_payout_history": payout_history_counts,
                        "recent_wallet_transactions": [
                            {
                                "id": t.id,
                                "type": t.type,
                                "source": t.source,
                                "amount": t.amount,
                                "balance_after": t.balance_after,
                                "reference_id": t.reference_id,
                                "note": t.note,
                                "created_at": t.created_at,
                            }
                            for t in recent_txns
                        ],
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
                    "message": "Failed to fetch payout",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/vendor-payout/<int:payout_id>/approve", methods=["PUT"])
@admin_middleware
def approve_vendor_payout(payout_id):
    try:
        payout = VendorPayout.query.get(payout_id)
        if not payout:
            return (
                jsonify({"status": "error", "message": "Payout request not found"}),
                404,
            )
        if payout.status != "pending":
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Payout already {payout.status}, cannot re-approve",
                    }
                ),
                400,
            )

        screenshot_file = request.files.get("payment_screenshot")
        if not screenshot_file:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "payment_screenshot is required to approve a payout",
                    }
                ),
                400,
            )

        # Debit wallet BEFORE marking approved — if this fails, nothing else changes.
        try:
            txn = debit_wallet(
                vendor_id=payout.vendor_id,
                amount=payout.amount,
                source="payout_withdrawal",
                reference_id=payout.id,
                note=f"Payout #{payout.id} approved",
            )
        except ValueError as balance_error:
            return (
                jsonify({"status": "error", "message": str(balance_error)}),
                400,
            )

        payout.payment_screenshot = upload_file(
            screenshot_file, folder="vendor_payouts"
        )
        payout.status = "approved"
        payout.note = request.form.get("note", payout.note)
        payout.wallet_transaction_id = txn.id
        db.session.commit()

        return (
            jsonify(
                {"status": "success", "message": "Payout approved and marked as paid"}
            ),
            200,
        )
    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to approve payout",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/vendor-payout/<int:payout_id>/reject", methods=["PUT"])
@admin_middleware
def reject_vendor_payout(payout_id):
    try:
        payout = VendorPayout.query.get(payout_id)
        if not payout:
            return (
                jsonify({"status": "error", "message": "Payout request not found"}),
                404,
            )
        if payout.status != "pending":
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Payout already {payout.status}, cannot re-reject",
                    }
                ),
                400,
            )

        data = request.get_json(silent=True) or {}
        payout.status = "rejected"
        payout.note = data.get("note", payout.note)
        db.session.commit()

        return (
            jsonify({"status": "success", "message": "Payout request rejected"}),
            200,
        )
    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Failed to reject payout",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/vendor/overview", methods=["GET"])
@admin_middleware
def vendor_overview():
    try:
        total_vendors = Vendor.query.count()
        pending_vendors = Vendor.query.filter_by(approval_status="pending").count()
        approved_vendors = Vendor.query.filter_by(approval_status="approved").count()
        rejected_vendors = Vendor.query.filter_by(approval_status="rejected").count()
        active_vendors = Vendor.query.filter_by(is_active=True).count()
        inactive_vendors = Vendor.query.filter_by(is_active=False).count()

        total_vendor_products = Products.query.filter(
            Products.vendor_id.isnot(None)
        ).count()
        products_awaiting = Products.query.filter(
            Products.vendor_id.isnot(None), Products.status == "pending_review"
        ).count()
        products_active = Products.query.filter(
            Products.vendor_id.isnot(None), Products.status == "active"
        ).count()
        products_rejected = Products.query.filter(
            Products.vendor_id.isnot(None), Products.status == "rejected"
        ).count()

        pending_payouts = VendorPayout.query.filter_by(status="pending").count()
        approved_payouts = VendorPayout.query.filter_by(status="approved").count()
        rejected_payouts = VendorPayout.query.filter_by(status="rejected").count()
        total_payout_requests = pending_payouts + approved_payouts + rejected_payouts

        total_paid_out = (
            db.session.query(db.func.coalesce(db.func.sum(VendorPayout.amount), 0.0))
            .filter(VendorPayout.status == "approved")
            .scalar()
        )
        pending_payout_amount = (
            db.session.query(db.func.coalesce(db.func.sum(VendorPayout.amount), 0.0))
            .filter(VendorPayout.status == "pending")
            .scalar()
        )
        total_wallet_balance = db.session.query(
            db.func.coalesce(db.func.sum(VendorWallet.balance), 0.0)
        ).scalar()

        revenue_by_vendor = (
            db.session.query(
                Products.vendor_id,
                db.func.coalesce(db.func.sum(OrderedItems.total_price), 0.0),
            )
            .join(OrderedItems, OrderedItems.product_id == Products.id)
            .join(Orders, Orders.id == OrderedItems.order_id)
            .filter(
                Products.vendor_id.isnot(None),
                Orders.status == "delivered",
                Orders.payment_status == "paid",
            )
            .group_by(Products.vendor_id)
            .all()
        )

        commission_rates = {
            v.id: v.commission_rate
            for v in Vendor.query.with_entities(Vendor.id, Vendor.commission_rate).all()
        }

        total_revenue = 0.0
        total_commission = 0.0
        for vendor_id, revenue in revenue_by_vendor:
            total_revenue += revenue
            rate = commission_rates.get(vendor_id, 0.0)
            total_commission += revenue * (rate / 100.0)

        vendor_payout_owed = total_revenue - total_commission - total_paid_out

        return (
            jsonify(
                {
                    "status": "success",
                    "overview": {
                        "vendors": {
                            "total": total_vendors,
                            "pending": pending_vendors,
                            "approved": approved_vendors,
                            "rejected": rejected_vendors,
                            "active": active_vendors,
                            "inactive": inactive_vendors,
                        },
                        "products": {
                            "total": total_vendor_products,
                            "awaiting_review": products_awaiting,
                            "active": products_active,
                            "rejected": products_rejected,
                        },
                        "payouts": {
                            "total_requests": total_payout_requests,
                            "pending": pending_payouts,
                            "approved": approved_payouts,
                            "rejected": rejected_payouts,
                            "total_paid_out": round(total_paid_out, 2),
                            "pending_amount": round(pending_payout_amount, 2),
                        },
                        "revenue": {
                            "total_revenue": round(total_revenue, 2),
                            "total_commission_earned": round(total_commission, 2),
                            "vendor_payout_owed": round(vendor_payout_owed, 2),
                            "total_wallet_balance": round(total_wallet_balance, 2),
                        },
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
                    "message": "Failed to fetch vendor overview",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/vendor/<int:vendor_id>/wallet", methods=["GET"])
@admin_middleware
def get_vendor_wallet_admin(vendor_id):
    try:
        vendor = Vendor.query.get(vendor_id)
        if not vendor:
            return jsonify({"status": "error", "message": "Vendor not found"}), 404

        wallet = get_or_create_wallet(vendor.id)
        db.session.commit()

        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 20, type=int)

        txn_query = VendorWalletTransaction.query.filter_by(
            wallet_id=wallet.id
        ).order_by(VendorWalletTransaction.created_at.desc())
        pagination = txn_query.paginate(page=page, per_page=limit, error_out=False)

        return (
            jsonify(
                {
                    "status": "success",
                    "wallet": {
                        "balance": wallet.balance,
                        "total_earned": wallet.total_earned,
                        "total_withdrawn": wallet.total_withdrawn,
                        "updated_at": wallet.updated_at,
                    },
                    "transactions": [
                        {
                            "id": t.id,
                            "type": t.type,
                            "source": t.source,
                            "amount": t.amount,
                            "balance_after": t.balance_after,
                            "reference_id": t.reference_id,
                            "note": t.note,
                            "created_at": t.created_at,
                        }
                        for t in pagination.items
                    ],
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
                    "message": "Failed to fetch wallet",
                    "error": str(e),
                }
            ),
            500,
        )


@adminBP.route("/vendor/<int:vendor_id>/wallet/adjust", methods=["POST"])
@admin_middleware
def adjust_vendor_wallet(vendor_id):
    try:
        vendor = Vendor.query.get(vendor_id)
        if not vendor:
            return jsonify({"status": "error", "message": "Vendor not found"}), 404

        data = request.get_json()
        amount = to_float(data.get("amount"))
        direction = data.get("direction")  # "credit" or "debit"
        note = data.get("note")

        if not amount or amount <= 0:
            return jsonify({"status": "error", "message": "Valid amount required"}), 400
        if direction not in ("credit", "debit"):
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "direction must be 'credit' or 'debit'",
                    }
                ),
                400,
            )
        if not note:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "note is required for manual adjustments",
                    }
                ),
                400,
            )

        try:
            if direction == "credit":
                txn = credit_wallet(vendor_id, amount, source="adjustment", note=note)
            else:
                txn = debit_wallet(vendor_id, amount, source="adjustment", note=note)
        except ValueError as balance_error:
            return jsonify({"status": "error", "message": str(balance_error)}), 400

        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": f"Wallet {direction}ed successfully",
                    "balance_after": txn.balance_after,
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
                    "message": "Failed to adjust wallet",
                    "error": str(e),
                }
            ),
            500,
        )
