from config.extension import db
from sqlalchemy.dialects.postgresql import JSON


class Admin(db.Model):
    __tablename__ = "admin"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    profile_picture = db.Column(db.String(255), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    role = db.Column(db.String(50), nullable=False, default="admin")
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class Vendor(db.Model):
    __tablename__ = "vendor"
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(
        db.Integer,
        db.ForeignKey("admin.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    store_name = db.Column(db.String(255), nullable=False)
    store_description = db.Column(db.Text, nullable=True)
    gst_number = db.Column(db.String(255), nullable=True)
    upi_id = db.Column(db.String(255), nullable=True)
    bank_account_number = db.Column(db.String(255), nullable=True)
    bank_ifsc = db.Column(db.String(20), nullable=True)
    bank_account_holder = db.Column(db.String(255), nullable=True)
    commission_rate = db.Column(db.Float, nullable=False, default=10.0)
    approval_status = db.Column(db.String(20), nullable=False, default="pending")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )
    admin = db.relationship(
        "Admin", backref=db.backref("vendor_profile", uselist=False)
    )
    products = db.relationship("Products", back_populates="vendor", lazy=True)
    payout_requests = db.relationship(
        "VendorPayout", back_populates="vendor", cascade="all, delete-orphan", lazy=True
    )


class VendorWallet(db.Model):
    __tablename__ = "vendor_wallet"
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(
        db.Integer,
        db.ForeignKey("vendor.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    balance = db.Column(db.Float, nullable=False, default=0.0)  # withdrawable right now
    total_earned = db.Column(db.Float, nullable=False, default=0.0)  # lifetime credits
    total_withdrawn = db.Column(
        db.Float, nullable=False, default=0.0
    )  # lifetime approved payouts
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    vendor = db.relationship(
        "Vendor",
        backref=db.backref("wallet", uselist=False, cascade="all, delete-orphan"),
    )
    transactions = db.relationship(
        "VendorWalletTransaction",
        back_populates="wallet",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="VendorWalletTransaction.created_at.desc()",
    )


class VendorWalletTransaction(db.Model):
    __tablename__ = "vendor_wallet_transaction"
    id = db.Column(db.Integer, primary_key=True)
    wallet_id = db.Column(
        db.Integer,
        db.ForeignKey("vendor_wallet.id", ondelete="CASCADE"),
        nullable=False,
    )
    type = db.Column(
        db.Enum("credit", "debit", name="vendor_wallet_txn_type"),
        nullable=False,
    )
    source = db.Column(
        db.Enum(
            "order_earning",
            "payout_withdrawal",
            "refund_reversal",
            "adjustment",
            name="vendor_wallet_txn_source",
        ),
        nullable=False,
    )
    amount = db.Column(db.Float, nullable=False)
    balance_after = db.Column(db.Float, nullable=False)
    reference_id = db.Column(
        db.Integer, nullable=True
    )  # order_id / payout_id depending on source
    note = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    wallet = db.relationship("VendorWallet", back_populates="transactions")


class VendorPayout(db.Model):
    __tablename__ = "vendor_payout"
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(
        db.Integer, db.ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False
    )
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(
        db.Enum("pending", "approved", "rejected", name="vendor_payout_status"),
        default="pending",
        nullable=False,
    )
    payment_screenshot = db.Column(db.String(255), nullable=True)
    note = db.Column(db.String(255), nullable=True)
    wallet_transaction_id = db.Column(
        db.Integer, db.ForeignKey("vendor_wallet_transaction.id"), nullable=True
    )
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )
    vendor = db.relationship("Vendor", back_populates="payout_requests")
    wallet_transaction = db.relationship("VendorWalletTransaction")


class Store(db.Model):
    __tablename__ = "store"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    logo = db.Column(db.String(255), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    gst_number = db.Column(db.String(255), unique=True, nullable=True)
    support_email = db.Column(db.String(255), nullable=True)
    support_phone = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class Notification(db.Model):
    __tablename__ = "notification"
    id = db.Column(db.Integer, primary_key=True)
    order_placed = db.Column(db.Boolean, default=False)
    payment_failed = db.Column(db.Boolean, default=False)
    low_stock = db.Column(db.Boolean, default=False)
    new_user_registration = db.Column(db.Boolean, default=False)
    new_product_review = db.Column(db.Boolean, default=False)
    email_notifications = db.Column(db.Boolean, default=False)
    sms_notifications = db.Column(db.Boolean, default=False)
    push_notifications = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class PaymentSettings(db.Model):
    __tablename__ = "payment_settings"
    id = db.Column(db.Integer, primary_key=True)
    payment_gateway = db.Column(db.String(255), nullable=False)
    api_key = db.Column(db.String(255), nullable=False)
    api_secret = db.Column(db.String(255), nullable=False)
    upi_id = db.Column(db.String(255), nullable=True)
    cod = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class Category(db.Model):
    __tablename__ = "category"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    slug = db.Column(db.String(255), unique=True, nullable=False)
    icon = db.Column(db.String(255), nullable=True)
    color = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )
    products = db.relationship(
        "Products",
        back_populates="category",
        lazy=True,
        uselist=True,
        cascade="save-update, merge",
    )


class Products(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(
        db.Integer, db.ForeignKey("category.id", ondelete="SET NULL"), nullable=True
    )
    vendor_id = db.Column(
        db.Integer, db.ForeignKey("vendor.id", ondelete="SET NULL"), nullable=True
    )
    name = db.Column(db.String(255), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    product_image = db.Column(db.String(255), nullable=False)
    product_images = db.Column(JSON, nullable=True)
    sizes = db.Column(JSON, nullable=True)
    colors = db.Column(JSON, nullable=True)

    price = db.Column(db.Float, nullable=False)
    compare_at_price = db.Column(db.Float, nullable=True)
    stock = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=True)
    charge_tax = db.Column(db.Boolean, default=False)
    tax_rate = db.Column(db.Float, nullable=True)
    cost_price = db.Column(db.Float, nullable=True)

    sku = db.Column(db.String(255), unique=True, nullable=False)
    barcode = db.Column(db.String(255), unique=True, nullable=True)
    country_of_origin = db.Column(db.String(255), nullable=True)
    weight = db.Column(db.Float, nullable=True)
    weight_unit = db.Column(db.String(20), nullable=True)
    commission = db.Column(db.Integer, default=2)
    product_type = db.Column(db.String(255), nullable=True)
    sell_when_out_of_stock = db.Column(db.Boolean, default=False)
    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), nullable=False, default="active")
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )
    category = db.relationship("Category", back_populates="products", lazy=True)
    product_reviews = db.relationship(
        "ProductReview", backref="products", lazy=True, cascade="all, delete-orphan"
    )
    collection_products = db.relationship(
        "CollectionProducts",
        lazy=True,
        back_populates="product",
        cascade="all, delete-orphan",
    )
    orderlist = db.relationship(
        "OrderList",
        back_populates="products",
        uselist=True,
        cascade="all, delete-orphan",
    )
    vendor = db.relationship("Vendor", back_populates="products")


class ProductReview(db.Model):
    __tablename__ = "product_review"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    rating = db.Column(db.Integer, nullable=False)
    review = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class Banner(db.Model):
    __tablename__ = "banner"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    link_name = db.Column(db.String(255), nullable=True)
    link = db.Column(db.String(255), nullable=True)
    code = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(50), nullable=False, default="active")
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class Collection(db.Model):
    __tablename__ = "collection"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=True)
    image = db.Column(db.String(255), nullable=True)

    collection_products = db.relationship(
        "CollectionProducts",
        back_populates="collection",
        cascade="all, delete-orphan",
        lazy=True,
    )


class CollectionProducts(db.Model):
    __tablename__ = "collection_products"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    collection_id = db.Column(
        db.Integer, db.ForeignKey("collection.id", ondelete="CASCADE"), nullable=False
    )
    collection = db.relationship("Collection", back_populates="collection_products")
    product = db.relationship(
        "Products", back_populates="collection_products"
    )  # singular, no uselist
    __table_args__ = (
        db.UniqueConstraint(
            "product_id", "collection_id", name="uq_product_collection"
        ),
    )
