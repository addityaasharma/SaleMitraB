from models.user import *
from models.admin import *
from flask import request, jsonify, Blueprint, g
from werkzeug.security import generate_password_hash, check_password_hash
from config.extension import *
from functions.helper_function import *
from functions.background_functions import *
import json, jwt
from datetime import datetime, timedelta

userBP = Blueprint("user", __name__, url_prefix="/user")


@userBP.route("/signup", methods=["POST"])
def signup_otp():
    data = request.get_json()
    try:
        required_fields = ["email", "password", "username"]
        for field in required_fields:
            if not data.get(field):
                return (
                    jsonify({"status": "error", "message": "All field are required"}),
                    400,
                )

        check_user = User.query.filter_by(email=data["email"]).first()
        if check_user:
            return (
                jsonify(
                    {"status": "error", "message": "User already exist. Please Login"}
                ),
                400,
            )

        otp = generateOTP_function()
        redis.setex(
            f"otp:{data.get('email')}",
            300,
            json.dumps(
                {
                    "username": data.get("username"),
                    "email": data.get("email"),
                    "password": data.get("password"),
                    "otp": otp,
                }
            ),
        )
        send_otp_task.delay(data["email"], otp)

        return jsonify({"status": "success", "message": "OTP sent successfully"}), 200
    except Exception as e:
        return (
            jsonify(
                {"status": "error", "message": "Failed to send otp", "error": str(e)}
            ),
            500,
        )


@userBP.route("/signup/verify", methods=["POST"])
def verify_otp():
    data = request.get_json()
    try:
        required_fields = ["email", "otp"]
        for field in required_fields:
            if not data.get(field):
                return (
                    jsonify({"status": "error", "message": "Please provide otp"}),
                    400,
                )

        check_user = User.query.filter_by(email=data["email"]).first()
        if check_user:
            return (
                jsonify(
                    {"status": "error", "message": "User already exist. Please Login"}
                ),
                400,
            )

        user_data = redis.get(f"otp:{data.get('email')}")
        if not user_data:
            return jsonify({"status": "error", "message": "OTP expired"}), 404

        user_data = json.loads(user_data)
        if data["otp"] != user_data["otp"]:
            return jsonify({"status": "error", "message": "Invalid OTP."}), 400

        hash_pass = generate_password_hash(user_data["password"])
        new_user = User(
            email=data["email"],
            username=user_data["username"],
            password=hash_pass,
            role="user",
        )
        db.session.add(new_user)
        db.session.commit()
        redis.delete(f"otp:{data['email']}")
        token = jwt.encode(
            {
                "userID": new_user.id,
                "role": "user",
                "exp": datetime.utcnow() + timedelta(days=7),
            },
            os.getenv("SECRET_KEY"),
            algorithm="HS256",
        )
        response = jsonify({"status": "success", "message": "User signup successfully"})
        response.set_cookie(
            "user_auth_token",
            token,
            httponly=True,
            max_age=7 * 24 * 60 * 60,
        )

        return response

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Failed to signup", "error": str(e)}
            ),
            500,
        )


@userBP.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    try:
        required_fields = ["email", "password"]
        for field in required_fields:
            if not data.get(field):
                return (
                    jsonify({"status": "error", "message": f"{field} is required"}),
                    400,
                )

        check_user = User.query.filter_by(email=data.get("email")).first()
        if not check_user:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Account does not exist. Please signup.",
                    }
                ),
                404,
            )

        if not check_password_hash(check_user.password, data["password"]):
            return jsonify({"status": "error", "message": "wrong password"}), 400

        token = jwt.encode(
            {
                "userID": check_user.id,
                "role": "user",
                "exp": datetime.utcnow() + timedelta(days=7),
            },
            os.getenv("SECRET_KEY"),
            algorithm="HS256",
        )
        response = jsonify({"status": "success", "message": "User Login successfully"})
        response.set_cookie(
            "user_auth_token",
            token,
            httponly=True,
            max_age=7 * 24 * 60 * 60,
        )

        return response
    except Exception as e:
        return (
            jsonify({"status": "error", "message": "Failed to login", "error": str(e)}),
            500,
        )


@userBP.route("/logout", methods=["POST"])
def logout():
    try:
        response = jsonify({"status": "success", "message": "Logout successfully"})
        response.delete_cookie("user_auth_token")
    except Exception as e:
        return (
            jsonify({"status": "error", "message": "Something error", "error": str(e)}),
            500,
        )


@userBP.route("/password/forget", methods=["POST"])
def forgot_password():
    data = request.get_json()
    try:
        required_fields = ["email"]
        for field in required_fields:
            if not data.get(field):
                return (
                    jsonify({"status": "error", "message": f"{field} is required"}),
                    400,
                )

        check_user = User.query.filter_by(email=data.get("email")).first()
        if not check_user:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Account does not exist",
                    }
                ),
                404,
            )

        otp = generateOTP_function()
        redis.setex(f"otp:{data.get('email')}", 300, otp)
        send_otp_task.delay(data["email"], otp)
        return jsonify({"status": "success", "message": "OTP sent successfully"}), 200
    except Exception as e:
        return (
            jsonify({"status": "error", "message": "Something error", "error": str(e)}),
            500,
        )


@userBP.route("/password/reset", methods=["POST"])
def reset_password():
    data = request.get_json()

    try:
        required_fields = ["email", "otp", "password"]
        for field in required_fields:
            if not data.get(field):
                return (
                    jsonify({"status": "error", "message": f"{field} is required"}),
                    400,
                )

        check_user = User.query.filter_by(email=data.get("email")).first()
        if not check_user:
            return (
                jsonify({"status": "error", "message": "Account does not exist"}),
                404,
            )

        stored_otp = redis.get(f"reset_otp:{data.get('email')}")
        if not stored_otp:
            return jsonify({"status": "error", "message": "OTP expired"}), 400

        if data.get("otp") != stored_otp:
            return jsonify({"status": "error", "message": "Invalid OTP"}), 400

        check_user.password = generate_password_hash(data.get("password"))
        db.session.commit()
        redis.delete(f"reset_otp:{data.get('email')}")

        return (
            jsonify({"status": "success", "message": "Password reset successfully"}),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Something went wrong", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me", methods=["GET"])
@middleware
def profile():
    try:
        return (
            jsonify(
                {
                    "status": "success",
                    "data": {
                        "id": g.user.id,
                        "username": g.user.username,
                        "email": g.user.email,
                        "profile_picture": g.user.profile_picture,
                        "phone_number": g.user.phone_number,
                        "bio": g.user.bio,
                        "role": g.user.role,
                        "created_at": g.user.created_at,
                        "updated_at": g.user.updated_at,
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


@userBP.route("/me", methods=["PUT"])
@middleware
def update_profile():
    try:
        username = request.form.get("username")
        phone_number = request.form.get("phone_number")
        bio = request.form.get("bio")
        profile_picture = request.files.get("profile_picture")

        if username:
            existing_user = User.query.filter(
                User.username == username, User.id != g.user.id
            ).first()
            if existing_user:
                return (
                    jsonify({"status": "error", "message": "Username already exists"}),
                    400,
                )

            g.user.username = username

        if phone_number:
            g.user.phone_number = phone_number

        if bio:
            g.user.bio = bio

        if profile_picture:
            image_url = upload_file(profile_picture, folder="profiles")
            g.user.profile_picture = image_url

        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Profile updated successfully",
                    "data": {
                        "id": g.user.id,
                        "username": g.user.username,
                        "email": g.user.email,
                        "phone_number": g.user.phone_number,
                        "bio": g.user.bio,
                        "profile_picture": g.user.profile_picture,
                        "role": g.user.role,
                    },
                }
            ),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Failed to update", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/address", methods=["POST"])
@middleware
def add_address():
    try:
        user = g.user
        existing_addresses = Address.query.filter_by(user_id=user.id).count()
        if existing_addresses >= 3:
            return (
                jsonify(
                    {"status": "error", "message": "Maximum of 3 addresses allowed"}
                ),
                400,
            )

        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        required_fields = ["street", "city", "state", "postal_code", "country"]
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Missing required fields: {', '.join(missing_fields)}",
                    }
                ),
                400,
            )

        new_address = Address(
            user_id=user.id,
            street=data["street"],
            city=data["city"],
            state=data["state"],
            postal_code=data["postal_code"],
            country=data["country"],
        )

        db.session.add(new_address)
        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Address added successfully",
                    "data": {
                        "id": new_address.id,
                        "street": new_address.street,
                        "city": new_address.city,
                        "state": new_address.state,
                        "postal_code": new_address.postal_code,
                        "country": new_address.country,
                        "created_at": new_address.created_at,
                    },
                }
            ),
            201,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/address", methods=["GET"])
@middleware
def get_addresses():
    try:
        user = g.user
        addresses = Address.query.filter_by(user_id=user.id).all()

        return (
            jsonify(
                {
                    "status": "success",
                    "data": [
                        {
                            "id": address.id,
                            "street": address.street,
                            "city": address.city,
                            "state": address.state,
                            "postal_code": address.postal_code,
                            "country": address.country,
                            "created_at": address.created_at,
                            "updated_at": address.updated_at,
                        }
                        for address in addresses
                    ],
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/address/<int:address_id>", methods=["PUT"])
@middleware
def update_address(address_id):
    try:
        user = g.user
        address = Address.query.filter_by(id=address_id, user_id=user.id).first()
        if not address:
            return jsonify({"status": "error", "message": "Address not found"}), 404

        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        updatable_fields = ["street", "city", "state", "postal_code", "country"]
        for field in updatable_fields:
            if field in data:
                setattr(address, field, data[field])

        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Address updated successfully",
                    "data": {
                        "id": address.id,
                        "street": address.street,
                        "city": address.city,
                        "state": address.state,
                        "postal_code": address.postal_code,
                        "country": address.country,
                        "updated_at": address.updated_at,
                    },
                }
            ),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/address/<int:address_id>", methods=["DELETE"])
@middleware
def delete_address(address_id):
    try:
        user = g.user
        address = Address.query.filter_by(id=address_id, user_id=user.id).first()
        if not address:
            return jsonify({"status": "error", "message": "Address not found"}), 404

        db.session.delete(address)
        db.session.commit()

        return (
            jsonify({"status": "success", "message": "Address deleted successfully"}),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/cart", methods=["GET"])
@middleware
def get_cart():
    try:
        user = g.user
        cart_items = Cart.query.filter_by(user_id=user.id).all()

        items_data = []
        subtotal = 0
        total_discount = 0
        total_tax = 0
        total_items_count = 0

        for item in cart_items:
            product = Products.query.get(item.product_id)

            if product:
                original_price = product.compare_at_price or product.price
                current_price = product.price
                discount = (
                    round(original_price - current_price, 2)
                    if product.compare_at_price
                    else 0
                )
                discount_percentage = (
                    round((discount / original_price) * 100) if discount > 0 else 0
                )

                item_total = round(current_price * item.quantity, 2)

                # Tax calculation
                tax_amount = 0
                if product.charge_tax and product.tax_rate:
                    tax_amount = round((item_total * product.tax_rate) / 100, 2)

                subtotal += item_total
                total_discount += round(discount * item.quantity, 2)
                total_tax += tax_amount
                total_items_count += item.quantity

                items_data.append(
                    {
                        "id": item.id,
                        "product_id": item.product_id,
                        "quantity": item.quantity,
                        "product": {
                            "name": product.name,
                            "description": product.description,
                            "image": product.product_image,
                            "sku": product.sku,
                            "status": product.status,
                            "price": current_price,
                            "compare_at_price": product.compare_at_price,
                            "discount": round(discount * item.quantity, 2),
                            "discount_percentage": f"{discount_percentage}%",
                            "item_total": item_total,
                            "tax_amount": tax_amount,
                            "tax_rate": product.tax_rate,
                            "charge_tax": product.charge_tax,
                            "in_stock": product.stock > 0
                            or product.sell_when_out_of_stock,
                            "stock": product.stock,
                            "weight": product.weight,
                            "weight_unit": product.weight_unit,
                        },
                        "created_at": item.created_at,
                        "updated_at": item.updated_at,
                    }
                )

            else:
                items_data.append(
                    {
                        "id": item.id,
                        "product_id": item.product_id,
                        "quantity": item.quantity,
                        "product": None,
                        "created_at": item.created_at,
                        "updated_at": item.updated_at,
                    }
                )

        grand_total = round(subtotal + total_tax, 2)

        return (
            jsonify(
                {
                    "status": "success",
                    "summary": {
                        "total_unique_items": len(cart_items),
                        "total_items_count": total_items_count,
                        "subtotal": round(subtotal, 2),
                        "total_discount": round(total_discount, 2),
                        "total_tax": round(total_tax, 2),
                        "grand_total": grand_total,
                    },
                    "data": items_data,
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/cart", methods=["POST"])
@middleware
def add_to_cart():
    try:
        user = g.user
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        required_fields = ["product_id", "quantity"]
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Missing required fields: {', '.join(missing_fields)}",
                    }
                ),
                400,
            )

        if data["quantity"] < 1:
            return (
                jsonify({"status": "error", "message": "Quantity must be at least 1"}),
                400,
            )

        product = Products.query.get(data["product_id"])
        if not product:
            return jsonify({"status": "error", "message": "Product not found"}), 404

        if product.status != "active":
            return (
                jsonify({"status": "error", "message": "Product is not available"}),
                400,
            )

        if not product.sell_when_out_of_stock and product.stock < data["quantity"]:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Insufficient stock. Only {product.stock} items available",
                    }
                ),
                400,
            )

        existing_item = Cart.query.filter_by(
            user_id=user.id, product_id=data["product_id"]
        ).first()

        if existing_item:
            new_quantity = existing_item.quantity + data["quantity"]
            if not product.sell_when_out_of_stock and new_quantity > product.stock:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": f"Insufficient stock. Only {product.stock} items available",
                        }
                    ),
                    400,
                )

            existing_item.quantity = new_quantity
            db.session.commit()

            return (
                jsonify(
                    {
                        "status": "success",
                        "message": "Cart quantity updated",
                        "data": {
                            "id": existing_item.id,
                            "product_id": existing_item.product_id,
                            "quantity": existing_item.quantity,
                            "updated_at": existing_item.updated_at,
                        },
                    }
                ),
                200,
            )

        new_cart_item = Cart(
            user_id=user.id, product_id=data["product_id"], quantity=data["quantity"]
        )

        db.session.add(new_cart_item)
        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Item added to cart",
                    "data": {
                        "id": new_cart_item.id,
                        "product_id": new_cart_item.product_id,
                        "quantity": new_cart_item.quantity,
                        "created_at": new_cart_item.created_at,
                    },
                }
            ),
            201,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/cart/<int:cart_id>", methods=["PUT"])
@middleware
def update_cart(cart_id):
    try:
        user = g.user
        cart_item = Cart.query.filter_by(id=cart_id, user_id=user.id).first()
        if not cart_item:
            return jsonify({"status": "error", "message": "Cart item not found"}), 404

        data = request.get_json()
        if not data or "quantity" not in data:
            return jsonify({"status": "error", "message": "Quantity is required"}), 400

        if data["quantity"] < 1:
            return (
                jsonify({"status": "error", "message": "Quantity must be at least 1"}),
                400,
            )

        product = Products.query.get(cart_item.product_id)
        if not product:
            return jsonify({"status": "error", "message": "Product not found"}), 404

        if not product.sell_when_out_of_stock and data["quantity"] > product.stock:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Insufficient stock. Only {product.stock} items available",
                    }
                ),
                400,
            )

        cart_item.quantity = data["quantity"]
        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Cart updated successfully",
                    "data": {
                        "id": cart_item.id,
                        "product_id": cart_item.product_id,
                        "quantity": cart_item.quantity,
                        "updated_at": cart_item.updated_at,
                    },
                }
            ),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/cart/<int:cart_id>", methods=["DELETE"])
@middleware
def delete_cart_item(cart_id):
    try:
        user = g.user
        cart_item = Cart.query.filter_by(id=cart_id, user_id=user.id).first()
        if not cart_item:
            return jsonify({"status": "error", "message": "Cart item not found"}), 404

        db.session.delete(cart_item)
        db.session.commit()

        return jsonify({"status": "success", "message": "Item removed from cart"}), 200

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/cart", methods=["DELETE"])
@middleware
def clear_cart():
    try:
        user = g.user
        Cart.query.filter_by(user_id=user.id).delete()
        db.session.commit()

        return (
            jsonify({"status": "success", "message": "Cart cleared successfully"}),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/wishlist", methods=["GET"])
@middleware
def get_wishlist():
    try:
        user = g.user
        wishlist_items = WishList.query.filter_by(user_id=user.id).all()

        items_data = []
        total_price = 0
        total_discount = 0

        for item in wishlist_items:
            product = Products.query.get(item.product_id)

            if product:
                original_price = product.compare_at_price or product.price
                current_price = product.price
                discount = (
                    round(original_price - current_price, 2)
                    if product.compare_at_price
                    else 0
                )
                discount_percentage = (
                    round((discount / original_price) * 100) if discount > 0 else 0
                )

                total_price += current_price
                total_discount += discount

                items_data.append(
                    {
                        "id": item.id,
                        "product_id": item.product_id,
                        "product": {
                            "name": product.name,
                            "description": product.description,
                            "image": product.product_image,
                            "price": current_price,
                            "compare_at_price": product.compare_at_price,
                            "discount": discount,
                            "discount_percentage": f"{discount_percentage}%",
                            "sku": product.sku,
                            "status": product.status,
                            "in_stock": product.stock > 0
                            or product.sell_when_out_of_stock,
                            "stock": product.stock,
                        },
                        "created_at": item.created_at,
                        "updated_at": item.updated_at,
                    }
                )

            else:
                items_data.append(
                    {
                        "id": item.id,
                        "product_id": item.product_id,
                        "product": None,
                        "created_at": item.created_at,
                        "updated_at": item.updated_at,
                    }
                )

        return (
            jsonify(
                {
                    "status": "success",
                    "summary": {
                        "total_items": len(wishlist_items),
                        "total_price": round(total_price, 2),
                        "total_discount": round(total_discount, 2),
                        "final_price": round(total_price, 2),
                    },
                    "data": items_data,
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/wishlist", methods=["POST"])
@middleware
def add_to_wishlist():
    try:
        user = g.user
        data = request.get_json()
        if not data or not data.get("product_id"):
            return (
                jsonify({"status": "error", "message": "product_id is required"}),
                400,
            )

        product = Products.query.get(data["product_id"])
        if not product:
            return jsonify({"status": "error", "message": "Product not found"}), 404

        existing = WishList.query.filter_by(
            user_id=user.id, product_id=data["product_id"]
        ).first()

        if existing:
            return (
                jsonify({"status": "error", "message": "Product already in wishlist"}),
                409,
            )

        new_wishlist_item = WishList(user_id=user.id, product_id=data["product_id"])

        db.session.add(new_wishlist_item)
        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Item added to wishlist",
                    "data": {
                        "id": new_wishlist_item.id,
                        "product_id": new_wishlist_item.product_id,
                        "created_at": new_wishlist_item.created_at,
                    },
                }
            ),
            201,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/wishlist/<int:wishlist_id>", methods=["DELETE"])
@middleware
def delete_wishlist_item(wishlist_id):
    try:
        user = g.user

        wishlist_item = WishList.query.filter_by(
            id=wishlist_id, user_id=user.id
        ).first()
        if not wishlist_item:
            return (
                jsonify({"status": "error", "message": "Wishlist item not found"}),
                404,
            )

        db.session.delete(wishlist_item)
        db.session.commit()

        return (
            jsonify({"status": "success", "message": "Item removed from wishlist"}),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/wishlist", methods=["DELETE"])
@middleware
def clear_wishlist():
    try:
        user = g.user

        WishList.query.filter_by(user_id=user.id).delete()
        db.session.commit()

        return (
            jsonify({"status": "success", "message": "Wishlist cleared successfully"}),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/order/create", methods=["POST"])
@middleware
def create_order():
    try:
        user = g.user
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        required_fields = ["address_id", "payment_method", "order_source"]
        missing = [f for f in required_fields if not data.get(f)]
        if missing:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Missing required fields: {', '.join(missing)}",
                    }
                ),
                400,
            )

        if data["payment_method"] not in ["cod", "razorpay"]:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "payment_method must be 'cod' or 'razorpay'",
                    }
                ),
                400,
            )

        if data["order_source"] not in ["cart", "buy_now"]:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "order_source must be 'cart' or 'buy_now'",
                    }
                ),
                400,
            )

        address = Address.query.filter_by(
            id=data["address_id"], user_id=user.id
        ).first()

        if not address:
            return jsonify({"status": "error", "message": "Address not found"}), 404

        shipping_address_snapshot = {
            "street": address.street,
            "city": address.city,
            "state": address.state,
            "postal_code": address.postal_code,
            "country": address.country,
        }

        order_items_raw = []
        if data["order_source"] == "buy_now":
            if not data.get("product_id") or not data.get("quantity"):
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "product_id and quantity are required for buy_now",
                        }
                    ),
                    400,
                )

            if data["quantity"] < 1:
                return (
                    jsonify(
                        {"status": "error", "message": "Quantity must be at least 1"}
                    ),
                    400,
                )

            order_items_raw.append(
                {"product_id": data["product_id"], "quantity": data["quantity"]}
            )

        elif data["order_source"] == "cart":
            cart_item_ids = data.get("cart_item_ids")

            if cart_item_ids:
                cart_items = Cart.query.filter(
                    Cart.user_id == user.id, Cart.id.in_(cart_item_ids)
                ).all()
            else:
                cart_items = Cart.query.filter_by(user_id=user.id).all()

            if not cart_items:
                return jsonify({"status": "error", "message": "Cart is empty"}), 400

            for item in cart_items:
                order_items_raw.append(
                    {
                        "product_id": item.product_id,
                        "quantity": item.quantity,
                        "cart_item_id": item.id,
                    }
                )

        ordered_items_data = []
        subtotal = 0
        total_tax = 0
        total_discount = 0

        for item in order_items_raw:
            product = Products.query.get(item["product_id"])
            if not product:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": f"Product with id {item['product_id']} not found",
                        }
                    ),
                    404,
                )

            if product.status != "active":
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": f"Product '{product.name}' is not available",
                        }
                    ),
                    400,
                )

            if not product.sell_when_out_of_stock and product.stock < item["quantity"]:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": f"Insufficient stock for '{product.name}'. Only {product.stock} available",
                        }
                    ),
                    400,
                )

            unit_price = product.price
            item_discount = 0
            if product.compare_at_price and product.compare_at_price > product.price:
                item_discount = round(
                    (product.compare_at_price - product.price) * item["quantity"], 2
                )

            item_subtotal = round(unit_price * item["quantity"], 2)

            tax_rate = (
                product.tax_rate if product.charge_tax and product.tax_rate else 0
            )
            tax_amount = round((item_subtotal * tax_rate) / 100, 2)
            item_total = round(item_subtotal + tax_amount, 2)

            subtotal += item_subtotal
            total_tax += tax_amount
            total_discount += item_discount

            ordered_items_data.append(
                {
                    "product_id": product.id,
                    "product_name": product.name,
                    "product_sku": product.sku,
                    "product_image": product.product_image,
                    "quantity": item["quantity"],
                    "unit_price": unit_price,
                    "tax_rate": tax_rate,
                    "tax_amount": tax_amount,
                    "discount": item_discount,
                    "total_price": item_total,
                    "cart_item_id": item.get("cart_item_id"),
                }
            )

        shipping_charges = data.get("shipping_charges", 0)
        coupon_discount = data.get("coupon_discount", 0)
        total_discount += coupon_discount

        grand_total = round(
            subtotal + total_tax + shipping_charges - coupon_discount, 2
        )

        new_order = Orders(
            user_id=user.id,
            order_id=generate_order_id(),
            address_id=address.id,
            shipping_address=shipping_address_snapshot,
            subtotal=round(subtotal, 2),
            tax_amount=round(total_tax, 2),
            discount=round(total_discount, 2),
            shipping_charges=shipping_charges,
            total_price=grand_total,
            order_source=data["order_source"],
            status="pending",
            payment_method=data["payment_method"],
            payment_status="unpaid",
        )
        db.session.add(new_order)
        db.session.flush()

        for item in ordered_items_data:
            ordered_item = OrderedItems(
                order_id=new_order.id,
                product_id=item["product_id"],
                product_name=item["product_name"],
                product_sku=item["product_sku"],
                product_image=item["product_image"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                tax_rate=item["tax_rate"],
                tax_amount=item["tax_amount"],
                discount=item["discount"],
                total_price=item["total_price"],
            )
            db.session.add(ordered_item)

        if data["payment_method"] == "cod":
            new_payment = Payment(
                order_id=new_order.id,
                user_id=user.id,
                payment_method="cod",
                amount=grand_total,
                currency="INR",
                status="pending",
            )
            db.session.add(new_payment)

            for item in ordered_items_data:
                product = Products.query.get(item["product_id"])
                product.stock -= item["quantity"]

            if data["order_source"] == "cart":
                for item in ordered_items_data:
                    if item.get("cart_item_id"):
                        Cart.query.filter_by(id=item["cart_item_id"]).delete()

            new_order.status = "confirmed"
            db.session.commit()

            return (
                jsonify(
                    {
                        "status": "success",
                        "message": "Order placed successfully",
                        "data": {
                            "order_id": new_order.order_id,
                            "total_price": grand_total,
                            "payment_method": "cod",
                            "status": "confirmed",
                        },
                    }
                ),
                201,
            )

        elif data["payment_method"] == "razorpay":
            razorpay_order = razorpay_client.order.create(
                {
                    "amount": int(grand_total * 100),  # paise
                    "currency": "INR",
                    "receipt": new_order.order_id,
                    "payment_capture": 1,
                }
            )

            new_payment = Payment(
                order_id=new_order.id,
                user_id=user.id,
                payment_method="razorpay",
                amount=grand_total,
                currency="INR",
                status="pending",
                razorpay_order_id=razorpay_order["id"],
            )
            db.session.add(new_payment)
            db.session.commit()

            return (
                jsonify(
                    {
                        "status": "success",
                        "message": "Razorpay order created, proceed to payment",
                        "data": {
                            "order_id": new_order.order_id,
                            "razorpay_order_id": razorpay_order["id"],
                            "amount": int(grand_total * 100),
                            "currency": "INR",
                            "key": os.getenv("RAZORPAY_KEY_ID"),
                        },
                    }
                ),
                201,
            )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/order/razorpay/verify", methods=["POST"])
@middleware
def verify_razorpay_payment():
    try:
        user = g.user
        data = request.get_json()

        required_fields = [
            "razorpay_order_id",
            "razorpay_payment_id",
            "razorpay_signature",
        ]
        missing = [f for f in required_fields if not data.get(f)]
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

        payment = Payment.query.filter_by(
            razorpay_order_id=data["razorpay_order_id"], user_id=user.id
        ).first()

        if not payment:
            return (
                jsonify({"status": "error", "message": "Payment record not found"}),
                404,
            )

        order = Orders.query.get(payment.order_id)
        if not order:
            return jsonify({"status": "error", "message": "Order not found"}), 404

        body = f"{data['razorpay_order_id']}|{data['razorpay_payment_id']}"
        expected_signature = hmac.new(
            os.getenv("RAZORPAY_KEY_SECRET").encode(), body.encode(), hashlib.sha256
        ).hexdigest()

        if expected_signature != data["razorpay_signature"]:
            payment.status = "failed"
            payment.failure_reason = "Signature verification failed"
            order.payment_status = "failed"
            db.session.commit()

            return (
                jsonify({"status": "error", "message": "Payment verification failed"}),
                400,
            )

        payment.status = "success"
        payment.razorpay_payment_id = data["razorpay_payment_id"]
        payment.razorpay_signature = data["razorpay_signature"]
        payment.payment_response = data.get("payment_response", {})
        payment.paid_at = datetime.utcnow()

        order.status = "confirmed"
        order.payment_status = "paid"

        ordered_items = OrderedItems.query.filter_by(order_id=order.id).all()
        for item in ordered_items:
            product = Products.query.get(item.product_id)
            if product:
                product.stock -= item.quantity

        if order.order_source == "cart":
            for item in ordered_items:
                Cart.query.filter_by(
                    user_id=user.id, product_id=item.product_id
                ).delete()

        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Payment verified, order confirmed",
                    "data": {
                        "order_id": order.order_id,
                        "payment_id": payment.razorpay_payment_id,
                        "total_price": order.total_price,
                        "status": order.status,
                        "payment_status": order.payment_status,
                    },
                }
            ),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/orders", methods=["GET"])
@middleware
def get_orders():
    try:
        user = g.user
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 10, type=int)
        status_filter = request.args.get("status")

        query = Orders.query.filter_by(user_id=user.id)

        if status_filter:
            query = query.filter_by(status=status_filter)

        orders = query.order_by(Orders.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        return (
            jsonify(
                {
                    "status": "success",
                    "pagination": {
                        "total": orders.total,
                        "pages": orders.pages,
                        "current_page": orders.page,
                        "per_page": orders.per_page,
                        "has_next": orders.has_next,
                        "has_prev": orders.has_prev,
                    },
                    "data": [
                        {
                            "id": o.id,
                            "order_id": o.order_id,
                            "status": o.status,
                            "payment_method": o.payment_method,
                            "payment_status": o.payment_status,
                            "total_price": o.total_price,
                            "total_items": sum(i.quantity for i in o.ordered_items),
                            "order_source": o.order_source,
                            "created_at": o.created_at,
                        }
                        for o in orders.items
                    ],
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/order/<string:order_id>", methods=["GET"])
@middleware
def get_order(order_id):
    try:
        user = g.user
        order = Orders.query.filter_by(order_id=order_id, user_id=user.id).first()
        if not order:
            return jsonify({"status": "error", "message": "Order not found"}), 404

        payment = Payment.query.filter_by(order_id=order.id).first()

        return (
            jsonify(
                {
                    "status": "success",
                    "data": {
                        "id": order.id,
                        "order_id": order.order_id,
                        "status": order.status,
                        "order_source": order.order_source,
                        "shipping_address": order.shipping_address,
                        "subtotal": order.subtotal,
                        "tax_amount": order.tax_amount,
                        "discount": order.discount,
                        "shipping_charges": order.shipping_charges,
                        "total_price": order.total_price,
                        "payment": (
                            {
                                "method": payment.payment_method,
                                "status": payment.status,
                                "amount": payment.amount,
                                "paid_at": payment.paid_at,
                                "razorpay_payment_id": payment.razorpay_payment_id,
                                "refund_status": payment.refund_status,
                                "refund_amount": payment.refund_amount,
                            }
                            if payment
                            else None
                        ),
                        "items": [
                            {
                                "id": item.id,
                                "product_id": item.product_id,
                                "product_name": item.product_name,
                                "product_sku": item.product_sku,
                                "product_image": item.product_image,
                                "quantity": item.quantity,
                                "unit_price": item.unit_price,
                                "tax_amount": item.tax_amount,
                                "discount": item.discount,
                                "total_price": item.total_price,
                            }
                            for item in order.ordered_items
                        ],
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
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/order/<string:order_id>/cancel", methods=["PUT"])
@middleware
def cancel_order(order_id):
    try:
        user = g.user
        order = Orders.query.filter_by(order_id=order_id, user_id=user.id).first()
        if not order:
            return jsonify({"status": "error", "message": "Order not found"}), 404

        if order.status not in ["pending", "confirmed"]:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Order cannot be cancelled. Current status: '{order.status}'",
                    }
                ),
                400,
            )

        for item in order.ordered_items:
            product = Products.query.get(item.product_id)
            if product:
                product.stock += item.quantity

        order.status = "cancelled"

        payment = Payment.query.filter_by(order_id=order.id).first()
        if payment and payment.status == "success" and payment.razorpay_payment_id:
            try:
                refund = razorpay_client.payment.refund(
                    payment.razorpay_payment_id,
                    {"amount": int(payment.amount * 100)},  # paise
                )
                payment.refund_id = refund["id"]
                payment.refund_amount = payment.amount
                payment.refund_status = "pending"
                payment.refund_reason = "Order cancelled by user"
                order.payment_status = "refunded"
            except Exception as refund_error:
                payment.refund_status = "failed"
                payment.failure_reason = str(refund_error)

        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Order cancelled successfully",
                    "data": {
                        "order_id": order.order_id,
                        "status": order.status,
                        "refund_status": payment.refund_status if payment else None,
                    },
                }
            ),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/order/<string:order_id>/refund", methods=["POST"])
@middleware
def request_refund(order_id):
    try:
        user = g.user
        order = Orders.query.filter_by(order_id=order_id, user_id=user.id).first()
        if not order:
            return jsonify({"status": "error", "message": "Order not found"}), 404

        if order.status != "delivered":
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Refund can only be requested for delivered orders. Current status: '{order.status}'",
                    }
                ),
                400,
            )

        payment = Payment.query.filter_by(order_id=order.id).first()
        if not payment:
            return (
                jsonify({"status": "error", "message": "Payment record not found"}),
                404,
            )

        existing_refund = Refund.query.filter_by(
            order_id=order.id, user_id=user.id
        ).first()

        if existing_refund:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Refund already {existing_refund.status}",
                    }
                ),
                400,
            )

        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        if not data.get("reason"):
            return (
                jsonify({"status": "error", "message": "Refund reason is required"}),
                400,
            )

        valid_reasons = [
            "damaged_product",
            "wrong_product",
            "product_not_as_described",
            "missing_items",
            "other",
        ]
        if data["reason"] not in valid_reasons:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Invalid reason. Valid reasons: {', '.join(valid_reasons)}",
                    }
                ),
                400,
            )

        refund_item_ids = data.get("item_ids")  # optional - partial refund
        refund_amount = 0

        if refund_item_ids:
            refund_items = OrderedItems.query.filter(
                OrderedItems.order_id == order.id, OrderedItems.id.in_(refund_item_ids)
            ).all()

            if not refund_items:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "No valid items found for refund",
                        }
                    ),
                    404,
                )

            found_ids = [item.id for item in refund_items]
            invalid_ids = [i for i in refund_item_ids if i not in found_ids]
            if invalid_ids:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": f"Item ids {invalid_ids} do not belong to this order",
                        }
                    ),
                    400,
                )

            for item in refund_items:
                refund_amount += item.total_price
            refund_amount = round(refund_amount, 2)

        else:
            refund_amount = payment.amount

        new_refund = Refund(
            order_id=order.id,
            user_id=user.id,
            payment_id=payment.id,
            reason=data["reason"],
            description=data.get("description", ""),
            refund_amount=refund_amount,
            refund_type="partial" if refund_item_ids else "full",
            item_ids=refund_item_ids or [],
            status="pending",
        )
        db.session.add(new_refund)

        order.status = "refund_requested"
        payment.refund_status = "pending"
        payment.refund_reason = data["reason"]
        payment.refund_amount = refund_amount

        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Refund request submitted successfully. Our team will review it shortly.",
                    "data": {
                        "refund_id": new_refund.id,
                        "order_id": order.order_id,
                        "refund_type": new_refund.refund_type,
                        "refund_amount": refund_amount,
                        "reason": new_refund.reason,
                        "description": new_refund.description,
                        "status": new_refund.status,
                        "created_at": new_refund.created_at,
                    },
                }
            ),
            201,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/order/<string:order_id>/refund", methods=["GET"])
@middleware
def get_refund_status(order_id):
    try:
        user = g.user

        order = Orders.query.filter_by(order_id=order_id, user_id=user.id).first()
        if not order:
            return jsonify({"status": "error", "message": "Order not found"}), 404

        refund = Refund.query.filter_by(order_id=order.id, user_id=user.id).first()
        if not refund:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "No refund request found for this order",
                    }
                ),
                404,
            )

        refund_items_detail = []
        if refund.refund_type == "partial" and refund.item_ids:
            refund_items = OrderedItems.query.filter(
                OrderedItems.id.in_(refund.item_ids)
            ).all()
            refund_items_detail = [
                {
                    "id": item.id,
                    "product_name": item.product_name,
                    "product_image": item.product_image,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "total_price": item.total_price,
                }
                for item in refund_items
            ]

        return (
            jsonify(
                {
                    "status": "success",
                    "data": {
                        "refund_id": refund.id,
                        "order_id": order.order_id,
                        "refund_type": refund.refund_type,
                        "refund_amount": refund.refund_amount,
                        "reason": refund.reason,
                        "description": refund.description,
                        "status": refund.status,
                        # pending   = waiting for admin review
                        # processed = refund done, money on the way
                        # rejected  = admin rejected the request
                        # failed    = something went wrong
                        "rejection_reason": (
                            refund.rejection_reason
                            if refund.status == "rejected"
                            else None
                        ),
                        "razorpay_refund_id": (
                            refund.razorpay_refund_id
                            if refund.status == "processed"
                            else None
                        ),
                        "refund_items": refund_items_detail,
                        "processed_at": refund.processed_at,
                        "created_at": refund.created_at,
                    },
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/me/order/<string:order_id>/refund", methods=["DELETE"])
@middleware
def cancel_refund_request(order_id):
    try:
        user = g.user

        order = Orders.query.filter_by(order_id=order_id, user_id=user.id).first()
        if not order:
            return jsonify({"status": "error", "message": "Order not found"}), 404

        refund = Refund.query.filter_by(order_id=order.id, user_id=user.id).first()
        if not refund:
            return (
                jsonify({"status": "error", "message": "No refund request found"}),
                404,
            )

        if refund.status != "pending":
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Refund cannot be cancelled. Current status: '{refund.status}'",
                    }
                ),
                400,
            )

        payment = Payment.query.get(refund.payment_id)
        db.session.delete(refund)
        order.status = "delivered"
        payment.refund_status = None
        payment.refund_reason = None
        payment.refund_amount = None

        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Refund request cancelled successfully",
                    "data": {"order_id": order.order_id, "order_status": order.status},
                }
            ),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/products", methods=["GET"])
def get_products():
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 12, type=int)
        per_page = min(per_page, 100)
        query = Products.query
        status = request.args.get("status", "active")
        query = query.filter(Products.status == status)
        search = request.args.get("search")
        if search:
            query = query.filter(Products.name.ilike(f"%{search}%"))

        category_id = request.args.get("category_id", type=int)
        if category_id:
            query = query.filter(Products.category_id == category_id)

        product_type = request.args.get("product_type")
        if product_type:
            query = query.filter(Products.product_type.ilike(f"%{product_type}%"))

        min_price = request.args.get("min_price", type=float)
        max_price = request.args.get("max_price", type=float)
        if min_price is not None:
            query = query.filter(Products.price >= min_price)
        if max_price is not None:
            query = query.filter(Products.price <= max_price)

        in_stock = request.args.get("in_stock")
        if in_stock and in_stock.lower() == "true":
            query = query.filter(
                db.or_(Products.stock > 0, Products.sell_when_out_of_stock == True)
            )

        on_sale = request.args.get("on_sale")
        if on_sale and on_sale.lower() == "true":
            query = query.filter(
                db.and_(
                    Products.compare_at_price != None,
                    Products.compare_at_price > Products.price,
                )
            )

        country_of_origin = request.args.get("country_of_origin")
        if country_of_origin:
            query = query.filter(
                Products.country_of_origin.ilike(f"%{country_of_origin}%")
            )

        min_weight = request.args.get("min_weight", type=float)
        max_weight = request.args.get("max_weight", type=float)
        if min_weight is not None:
            query = query.filter(Products.weight >= min_weight)
        if max_weight is not None:
            query = query.filter(Products.weight <= max_weight)

        sku = request.args.get("sku")
        if sku:
            query = query.filter(Products.sku == sku)

        barcode = request.args.get("barcode")
        if barcode:
            query = query.filter(Products.barcode == barcode)

        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")

        allowed_sort_fields = {
            "name": Products.name,
            "price": Products.price,
            "created_at": Products.created_at,
            "stock": Products.stock,
            "weight": Products.weight,
        }

        sort_column = allowed_sort_fields.get(sort_by, Products.created_at)
        if sort_order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        products = query.paginate(page=page, per_page=per_page, error_out=False)

        products_data = []
        for product in products.items:
            discount = 0
            discount_percentage = 0
            if product.compare_at_price and product.compare_at_price > product.price:
                discount = round(product.compare_at_price - product.price, 2)
                discount_percentage = round((discount / product.compare_at_price) * 100)

            reviews = product.product_reviews
            avg_rating = 0
            if reviews:
                avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1)

            products_data.append(
                {
                    "id": product.id,
                    "name": product.name,
                    "description": product.description,
                    "product_image": product.product_image,
                    "product_images": product.product_images,
                    "category_id": product.category_id,
                    "category": product.category.name if product.category else None,
                    "product_type": product.product_type,
                    "price": product.price,
                    "compare_at_price": product.compare_at_price,
                    "discount": discount,
                    "discount_percentage": f"{discount_percentage}%",
                    "sizes": product.sizes,
                    "colors": product.colors,
                    "sku": product.sku,
                    "barcode": product.barcode,
                    "stock": product.stock,
                    "in_stock": product.stock > 0 or product.sell_when_out_of_stock,
                    "weight": product.weight,
                    "weight_unit": product.weight_unit,
                    "country_of_origin": product.country_of_origin,
                    "charge_tax": product.charge_tax,
                    "tax_rate": product.tax_rate,
                    "status": product.status,
                    "avg_rating": avg_rating,
                    "total_reviews": len(reviews),
                    "created_at": product.created_at,
                }
            )

        return (
            jsonify(
                {
                    "status": "success",
                    "pagination": {
                        "total": products.total,
                        "pages": products.pages,
                        "current_page": products.page,
                        "per_page": products.per_page,
                        "has_next": products.has_next,
                        "has_prev": products.has_prev,
                    },
                    "filters_applied": {
                        "search": search,
                        "category_id": category_id,
                        "product_type": product_type,
                        "min_price": min_price,
                        "max_price": max_price,
                        "in_stock": in_stock,
                        "on_sale": on_sale,
                        "country_of_origin": country_of_origin,
                        "min_weight": min_weight,
                        "max_weight": max_weight,
                        "sku": sku,
                        "barcode": barcode,
                        "sort_by": sort_by,
                        "sort_order": sort_order,
                    },
                    "data": products_data,
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/products/<int:product_id>", methods=["GET"])
def get_product(product_id):
    try:
        product = Products.query.filter_by(id=product_id, status="active").first()

        if not product:
            return jsonify({"status": "error", "message": "Product not found"}), 404

        reviews = []
        avg_rating = 0
        rating_breakdown = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

        for review in product.product_reviews:
            reviewer = User.query.get(review.user_id)
            reviews.append(
                {
                    "id": review.id,
                    "rating": review.rating,
                    "review": review.review,
                    "user": (
                        {
                            "id": reviewer.id,
                            "username": reviewer.username,
                            "profile_picture": reviewer.profile_picture,
                        }
                        if reviewer
                        else None
                    ),
                    "created_at": review.created_at,
                }
            )
            rating_breakdown[review.rating] = rating_breakdown.get(review.rating, 0) + 1

        if reviews:
            avg_rating = round(sum(r["rating"] for r in reviews) / len(reviews), 1)

        discount = 0
        discount_percentage = 0
        if product.compare_at_price and product.compare_at_price > product.price:
            discount = round(product.compare_at_price - product.price, 2)
            discount_percentage = round((discount / product.compare_at_price) * 100)

        return (
            jsonify(
                {
                    "status": "success",
                    "data": {
                        "id": product.id,
                        "name": product.name,
                        "description": product.description,
                        "product_image": product.product_image,
                        "product_images": product.product_images,
                        "category_id": product.category_id,
                        "category": product.category.name if product.category else None,
                        "product_type": product.product_type,
                        "price": product.price,
                        "compare_at_price": product.compare_at_price,
                        "discount": discount,
                        "discount_percentage": f"{discount_percentage}%",
                        "sizes": product.sizes,
                        "colors": product.colors,
                        "sku": product.sku,
                        "barcode": product.barcode,
                        "stock": product.stock,
                        "in_stock": product.stock > 0 or product.sell_when_out_of_stock,
                        "weight": product.weight,
                        "weight_unit": product.weight_unit,
                        "country_of_origin": product.country_of_origin,
                        "charge_tax": product.charge_tax,
                        "tax_rate": product.tax_rate,
                        "status": product.status,
                        "ratings": {
                            "average": avg_rating,
                            "total": len(reviews),
                            "breakdown": rating_breakdown,
                            # breakdown example:
                            # { "1": 2, "2": 1, "3": 5, "4": 10, "5": 20 }
                        },
                        "reviews": reviews,
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
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/products/<int:product_id>/related", methods=["GET"])
def get_related_products(product_id):
    try:
        product = Products.query.filter_by(id=product_id, status="active").first()
        if not product:
            return jsonify({"status": "error", "message": "Product not found"}), 404

        limit = request.args.get("limit", 8, type=int)

        related = (
            Products.query.filter(
                Products.id != product_id,
                Products.status == "active",
                db.or_(
                    Products.category_id == product.category_id,
                    Products.product_type == product.product_type,
                ),
            )
            .limit(limit)
            .all()
        )

        return (
            jsonify(
                {
                    "status": "success",
                    "data": [
                        {
                            "id": p.id,
                            "name": p.name,
                            "product_image": p.product_image,
                            "price": p.price,
                            "compare_at_price": p.compare_at_price,
                            "discount_percentage": (
                                f"{round(((p.compare_at_price - p.price) / p.compare_at_price) * 100)}%"
                                if p.compare_at_price and p.compare_at_price > p.price
                                else "0%"
                            ),
                            "in_stock": p.stock > 0 or p.sell_when_out_of_stock,
                            "avg_rating": (
                                round(
                                    sum(r.rating for r in p.product_reviews)
                                    / len(p.product_reviews),
                                    1,
                                )
                                if p.product_reviews
                                else 0
                            ),
                        }
                        for p in related
                    ],
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


# ─── REVIEWS ──────────────────────────────────────────────────────────────────


@userBP.route("/products/<int:product_id>/review", methods=["POST"])
@middleware
def add_review(product_id):
    try:
        user = g.user
        product = Products.query.filter_by(id=product_id, status="active").first()
        if not product:
            return jsonify({"status": "error", "message": "Product not found"}), 404

        # only allow review if user has a delivered order with this product
        ordered_item = (
            OrderedItems.query.join(Orders)
            .filter(
                Orders.user_id == user.id,
                Orders.status == "delivered",
                OrderedItems.product_id == product_id,
            )
            .first()
        )
        if not ordered_item:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "You can only review products you have purchased and received",
                    }
                ),
                403,
            )

        existing = ProductReview.query.filter_by(
            product_id=product_id, user_id=user.id
        ).first()
        if existing:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "You have already reviewed this product",
                    }
                ),
                409,
            )

        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        rating = data.get("rating")
        if not rating:
            return jsonify({"status": "error", "message": "Rating is required"}), 400
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Rating must be an integer between 1 and 5",
                    }
                ),
                400,
            )

        review = ProductReview(
            product_id=product_id,
            user_id=user.id,
            rating=rating,
            review=data.get("review"),
        )
        db.session.add(review)
        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Review added successfully",
                    "data": {
                        "id": review.id,
                        "product_id": review.product_id,
                        "rating": review.rating,
                        "review": review.review,
                        "created_at": review.created_at,
                    },
                }
            ),
            201,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/products/<int:product_id>/review/<int:review_id>", methods=["PUT"])
@middleware
def update_review(product_id, review_id):
    try:
        user = g.user
        review = ProductReview.query.filter_by(
            id=review_id, product_id=product_id, user_id=user.id
        ).first()
        if not review:
            return jsonify({"status": "error", "message": "Review not found"}), 404

        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        if "rating" in data:
            if (
                not isinstance(data["rating"], int)
                or data["rating"] < 1
                or data["rating"] > 5
            ):
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Rating must be an integer between 1 and 5",
                        }
                    ),
                    400,
                )
            review.rating = data["rating"]

        if "review" in data:
            review.review = data["review"]

        db.session.commit()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "Review updated successfully",
                    "data": {
                        "id": review.id,
                        "product_id": review.product_id,
                        "rating": review.rating,
                        "review": review.review,
                        "updated_at": review.updated_at,
                    },
                }
            ),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/products/<int:product_id>/review/<int:review_id>", methods=["DELETE"])
@middleware
def delete_review(product_id, review_id):
    try:
        user = g.user
        review = ProductReview.query.filter_by(
            id=review_id, product_id=product_id, user_id=user.id
        ).first()
        if not review:
            return jsonify({"status": "error", "message": "Review not found"}), 404

        db.session.delete(review)
        db.session.commit()

        return (
            jsonify({"status": "success", "message": "Review deleted successfully"}),
            200,
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


# ─── CATEGORIES (PUBLIC) ──────────────────────────────────────────────────────


@userBP.route("/categories", methods=["GET"])
def get_categories():
    try:
        search = request.args.get("search")
        query = Category.query

        if search:
            query = query.filter(
                db.or_(
                    Category.name.ilike(f"%{search}%"),
                    Category.description.ilike(f"%{search}%"),
                )
            )

        categories = query.order_by(Category.name.asc()).all()

        return (
            jsonify(
                {
                    "status": "success",
                    "data": [
                        {
                            "id": c.id,
                            "name": c.name,
                            "slug": c.slug,
                            "description": c.description,
                            "icon": c.icon,
                            "color": c.color,
                            "total_products": Products.query.filter_by(
                                category_id=c.id, status="active"
                            ).count(),
                        }
                        for c in categories
                    ],
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/categories/<int:category_id>", methods=["GET"])
def get_category(category_id):
    try:
        category = Category.query.get(category_id)
        if not category:
            return jsonify({"status": "error", "message": "Category not found"}), 404

        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 12, type=int)
        per_page = min(per_page, 100)
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")
        min_price = request.args.get("min_price", type=float)
        max_price = request.args.get("max_price", type=float)
        in_stock = request.args.get("in_stock")
        on_sale = request.args.get("on_sale")

        allowed_sort_fields = {
            "name": Products.name,
            "price": Products.price,
            "created_at": Products.created_at,
            "stock": Products.stock,
        }

        product_query = Products.query.filter_by(
            category_id=category_id, status="active"
        )

        if min_price is not None:
            product_query = product_query.filter(Products.price >= min_price)
        if max_price is not None:
            product_query = product_query.filter(Products.price <= max_price)
        if in_stock and in_stock.lower() == "true":
            product_query = product_query.filter(
                db.or_(Products.stock > 0, Products.sell_when_out_of_stock == True)
            )
        if on_sale and on_sale.lower() == "true":
            product_query = product_query.filter(
                db.and_(
                    Products.compare_at_price != None,
                    Products.compare_at_price > Products.price,
                )
            )

        sort_column = allowed_sort_fields.get(sort_by, Products.created_at)
        product_query = product_query.order_by(
            sort_column.asc() if sort_order == "asc" else sort_column.desc()
        )
        pagination = product_query.paginate(
            page=page, per_page=per_page, error_out=False
        )

        products = []
        for p in pagination.items:
            discount = 0
            discount_percentage = 0
            if p.compare_at_price and p.compare_at_price > p.price:
                discount = round(p.compare_at_price - p.price, 2)
                discount_percentage = round((discount / p.compare_at_price) * 100)

            avg_rating = (
                round(
                    sum(r.rating for r in p.product_reviews) / len(p.product_reviews), 1
                )
                if p.product_reviews
                else 0
            )

            products.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "product_image": p.product_image,
                    "product_images": p.product_images,
                    "price": p.price,
                    "compare_at_price": p.compare_at_price,
                    "discount": discount,
                    "discount_percentage": f"{discount_percentage}%",
                    "sizes": p.sizes,
                    "colors": p.colors,
                    "sku": p.sku,
                    "stock": p.stock,
                    "in_stock": p.stock > 0 or p.sell_when_out_of_stock,
                    "avg_rating": avg_rating,
                    "total_reviews": len(p.product_reviews),
                    "created_at": p.created_at,
                }
            )

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
                    },
                    "pagination": {
                        "total": pagination.total,
                        "pages": pagination.pages,
                        "current_page": pagination.page,
                        "per_page": pagination.per_page,
                        "has_next": pagination.has_next,
                        "has_prev": pagination.has_prev,
                    },
                    "data": products,
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


# ─── BANNERS (PUBLIC) ─────────────────────────────────────────────────────────


@userBP.route("/banners", methods=["GET"])
def get_banners():
    try:
        banners = (
            Banner.query.filter_by(status="active")
            .order_by(Banner.created_at.desc())
            .all()
        )

        return (
            jsonify(
                {
                    "status": "success",
                    "data": [
                        {
                            "id": b.id,
                            "title": b.title,
                            "description": b.description,
                            "link_name": b.link_name,
                            "link": b.link,
                            "code": b.code,
                        }
                        for b in banners
                    ],
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


# ─── STORE (PUBLIC) ───────────────────────────────────────────────────────────


@userBP.route("/store", methods=["GET"])
def get_store():
    try:
        store = Store.query.first()
        if not store:
            return jsonify({"status": "error", "message": "Store not found"}), 404

        return (
            jsonify(
                {
                    "status": "success",
                    "data": {
                        "name": store.name,
                        "description": store.description,
                        "logo": store.logo,
                        "address": store.address,
                        "support_email": store.support_email,
                        "support_phone": store.support_phone,
                    },
                }
            ),
            200,
        )

    except Exception as e:
        return (
            jsonify(
                {"status": "error", "message": "Internal server error", "error": str(e)}
            ),
            500,
        )


@userBP.route("/collections", methods=["GET"])
def get_collections():
    try:
        collections = Collection.query.all()
        result = []
        for c in collections:
            result.append({
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "image": c.image,
                "product_count": len(c.collection_products),
            })
        return jsonify({"status": "success", "collections": result}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": "Failed to fetch collections", "error": str(e)}), 500


@userBP.route("/collections/<int:collection_id>", methods=["GET"])
def get_collection(collection_id):
    try:
        c = Collection.query.get(collection_id)
        if not c:
            return jsonify({"status": "error", "message": "Collection not found"}), 404

        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 20, type=int)
        sort_by = request.args.get("sort_by", "created_at")   # created_at | price | name
        order = request.args.get("order", "desc")              # asc | desc

        valid_sort_fields = {
            "created_at": Products.created_at,
            "price": Products.price,
            "name": Products.name,
        }
        sort_col = valid_sort_fields.get(sort_by, Products.created_at)
        sort_dir = sort_col.desc() if order == "desc" else sort_col.asc()

        query = (
            Products.query
            .join(CollectionProducts, CollectionProducts.product_id == Products.id)
            .filter(
                CollectionProducts.collection_id == collection_id,
                Products.status == "active",
            )
            .order_by(sort_dir)
        )

        paginated = query.paginate(page=page, per_page=limit, error_out=False)

        products = []
        for p in paginated.items:
            products.append({
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "product_image": p.product_image,
                "product_images": p.product_images,
                "price": p.price,
                "compare_at_price": p.compare_at_price,
                "sizes": p.sizes,
                "colors": p.colors,
                "stock": p.stock,
                "quantity": p.quantity,
                "status": p.status,
                "sell_when_out_of_stock": p.sell_when_out_of_stock,
                "sku": p.sku,
                "category_id": p.category_id,
            })

        return jsonify({
            "status": "success",
            "collection": {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "image": c.image,
            },
            "products": products,
            "pagination": {
                "page": paginated.page,
                "limit": limit,
                "total_products": paginated.total,
                "total_pages": paginated.pages,
                "has_next": paginated.has_next,
                "has_prev": paginated.has_prev,
            },
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": "Failed to fetch collection", "error": str(e)}), 500
    
    
@userBP.route("/search", methods=["GET"])
def search_products():
    try:
        search_query = request.args.get("q", "").strip()
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 20, type=int)
        category_id = request.args.get("category_id", type=int)
        min_price = request.args.get("min_price", type=float)
        max_price = request.args.get("max_price", type=float)
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")

        allowed_sort_fields = ["created_at", "price", "name"]
        if sort_by not in allowed_sort_fields:
            return jsonify({
                "status": "error",
                "message": f"Invalid sort_by. Allowed: {', '.join(allowed_sort_fields)}"
            }), 400

        stmt = Products.query.filter(Products.status == "active")

        if search_query:
            stmt = stmt.filter(
                db.or_(
                    Products.name.ilike(f"%{search_query}%"),
                    Products.description.ilike(f"%{search_query}%"),
                    Products.sku.ilike(f"%{search_query}%"),
                    Products.product_type.ilike(f"%{search_query}%"),
                )
            )

        if category_id:
            stmt = stmt.filter(Products.category_id == category_id)

        if min_price is not None:
            stmt = stmt.filter(Products.price >= min_price)

        if max_price is not None:
            stmt = stmt.filter(Products.price <= max_price)

        sort_column = getattr(Products, sort_by)
        stmt = stmt.order_by(sort_column.desc() if sort_order == "desc" else sort_column.asc())

        pagination = stmt.paginate(page=page, per_page=limit, error_out=False)

        products = [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "product_image": p.product_image,
                "price": p.price,
                "compare_at_price": p.compare_at_price,
                "stock": p.stock,
                "sku": p.sku,
                "sizes": p.sizes,
                "colors": p.colors,
                "status": p.status,
                "category_id": p.category_id,
                "category_name": p.category.name if p.category else None,
            }
            for p in pagination.items
        ]

        return jsonify({
            "status": "success",
            "query": search_query,
            "products": products,
            "total": pagination.total,
            "pages": pagination.pages,
            "page": page,
            "limit": limit,
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Search failed",
            "error": str(e),
        }), 500