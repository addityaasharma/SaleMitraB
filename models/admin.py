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
    orderlist = db.relationship("OrderList", back_populates="products", uselist=True, cascade="all, delete-orphan")


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
