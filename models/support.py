from config.extension import db


class SupportConversation(db.Model):
    __tablename__ = "support_conversation"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status = db.Column(db.String(20), nullable=False, default="open")  # open / closed
    last_message = db.Column(db.String(255), nullable=True)
    last_message_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    unread_by_admin = db.Column(db.Integer, nullable=False, default=0)
    unread_by_user = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )
    user = db.relationship(
        "User", backref="support_conversation", lazy=True, uselist=False
    )
    messages = db.relationship(
        "SupportMessage",
        backref="conversation",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="SupportMessage.created_at",
    )


class SupportMessage(db.Model):
    __tablename__ = "support_message"
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("support_conversation.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_type = db.Column(db.String(10), nullable=False)  # "user" or "admin"
    sender_id = db.Column(db.Integer, nullable=False)
    message = db.Column(db.Text, nullable=True)
    attachment_url = db.Column(db.String(500), nullable=True)
    attachment_type = db.Column(db.String(20), nullable=True)  # "image" or "file"
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
