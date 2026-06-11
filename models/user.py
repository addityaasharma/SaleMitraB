from config.extension import db


class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    profile_picture = db.Column(db.String(255), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    role = db.Column(db.String(50), nullable=False, default="customer")
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )
    addresses = db.relationship(
        "Address", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    wishlist = db.relationship(
        "WishList", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    cart = db.relationship(
        "Cart", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    orders = db.relationship(
        "Orders", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    payments = db.relationship(
        "Payment", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    refunds = db.relationship(
        "Refund", backref="user", lazy=True, cascade="all, delete-orphan"
    )


class Address(db.Model):
    __tablename__ = "address"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    street = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(255), nullable=False)
    state = db.Column(db.String(255), nullable=False)
    postal_code = db.Column(db.String(20), nullable=False)
    country = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class WishList(db.Model):
    __tablename__ = "wishlist"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    product_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class Cart(db.Model):
    __tablename__ = "cart"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    product_id = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class Orders(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    order_id = db.Column(db.String(255), unique=True, nullable=False)
    address_id = db.Column(
        db.Integer, db.ForeignKey("address.id", ondelete="SET NULL"), nullable=True
    )
    shipping_address = db.Column(db.JSON, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    tax_amount = db.Column(db.Float, nullable=True, default=0)
    razorpay_order_id = db.Column(db.String(255), nullable=True)
    discount = db.Column(db.Float, nullable=True, default=0)
    shipping_charges = db.Column(db.Float, nullable=False, default=0)
    total_price = db.Column(db.Float, nullable=False)
    order_source = db.Column(db.String(50), nullable=False, default="cart")
    status = db.Column(db.String(50), nullable=False, default="pending")
    payment_method = db.Column(db.String(50), nullable=False)
    payment_status = db.Column(db.String(50), nullable=False, default="unpaid")
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )
    ordered_items = db.relationship(
        "OrderedItems", backref="orders", lazy=True, cascade="all, delete-orphan"
    )
    payment = db.relationship(  # ✅ added
        "Payment", backref="order", lazy=True, cascade="all, delete-orphan"
    )
    refund = db.relationship("Refund", backref="order", lazy=True)


class OrderedItems(db.Model):
    __tablename__ = "ordered_items"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    product_name = db.Column(db.String(255), nullable=False)
    product_sku = db.Column(db.String(255), nullable=False)
    product_image = db.Column(db.String(255), nullable=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    tax_rate = db.Column(db.Float, nullable=True)
    tax_amount = db.Column(db.Float, nullable=True)
    discount = db.Column(db.Float, nullable=True, default=0)
    total_price = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class Payment(db.Model):
    __tablename__ = "payment"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    payment_method = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), nullable=False, default="INR")
    status = db.Column(db.String(50), nullable=False, default="pending")
    razorpay_order_id = db.Column(db.String(255), nullable=True)
    razorpay_payment_id = db.Column(db.String(255), nullable=True)
    razorpay_signature = db.Column(db.String(255), nullable=True)
    payment_response = db.Column(db.JSON, nullable=True)
    refund_id = db.Column(db.String(255), nullable=True)
    refund_amount = db.Column(db.Float, nullable=True)
    refund_status = db.Column(db.String(50), nullable=True)
    # pending -> processed -> failed
    refund_reason = db.Column(db.String(255), nullable=True)
    failure_reason = db.Column(db.String(255), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )
    refund = db.relationship("Refund", backref="payment", lazy=True)


class Refund(db.Model):
    __tablename__ = "refund"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    payment_id = db.Column(
        db.Integer, db.ForeignKey("payment.id", ondelete="CASCADE"), nullable=False
    )
    reason = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)  # user's detailed explanation
    refund_amount = db.Column(db.Float, nullable=False)
    refund_type = db.Column(db.String(20), nullable=False)  # "full" or "partial"
    item_ids = db.Column(db.JSON, nullable=True)  # which items in partial refund
    status = db.Column(db.String(50), nullable=False, default="pending")
    razorpay_refund_id = db.Column(db.String(255), nullable=True)
    bank_reference = db.Column(db.String(255), nullable=True)  # for COD refunds
    rejection_reason = db.Column(db.Text, nullable=True)
    processed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )
