from flask import Blueprint, request, jsonify, g
from config.extension import db
from models.support import SupportConversation, SupportMessage
from functions.helper_function import * 

supportBP = Blueprint("support", __name__)


@supportBP.route("/support/conversation", methods=["GET"])
@middleware
def get_my_conversation():
    conversation = SupportConversation.query.filter_by(user_id=g.user.id).first()
    if not conversation:
        conversation = SupportConversation(user_id=g.user.id)
        db.session.add(conversation)
        db.session.commit()

    messages = (
        SupportMessage.query.filter_by(conversation_id=conversation.id)
        .order_by(SupportMessage.created_at.asc())
        .all()
    )

    SupportMessage.query.filter_by(
        conversation_id=conversation.id, sender_type="admin", is_read=False
    ).update({"is_read": True})
    conversation.unread_by_user = 0
    db.session.commit()

    return jsonify(
        {
            "status": "success",
            "conversation": {"id": conversation.id, "status": conversation.status},
            "messages": [_serialize_message(m) for m in messages],
        }
    )


@supportBP.route("/support/upload", methods=["POST"])
@middleware
def user_upload_attachment():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file provided"}), 400

    file = request.files["file"]
    url = upload_file(file, folder="support_attachments")
    attachment_type = "image" if file.content_type.startswith("image/") else "file"

    return jsonify(
        {"status": "success", "attachment_url": url, "attachment_type": attachment_type}
    )




@supportBP.route("/admin/support/conversations", methods=["GET"])
@admin_middleware
def get_all_conversations():
    conversations = SupportConversation.query.order_by(
        SupportConversation.last_message_at.desc()
    ).all()

    return jsonify(
        {
            "status": "success",
            "conversations": [
                {
                    "id": c.id,
                    "user_id": c.user_id,
                    "user_name": c.user.username if c.user else None,
                    "user_profile_picture": c.user.profile_picture if c.user else None,
                    "status": c.status,
                    "last_message": c.last_message,
                    "last_message_at": (
                        c.last_message_at.isoformat() if c.last_message_at else None
                    ),
                    "unread_by_admin": c.unread_by_admin,
                }
                for c in conversations
            ],
        }
    )


@supportBP.route(
    "/admin/support/conversations/<int:conversation_id>/messages", methods=["GET"]
)
@admin_middleware
def get_conversation_messages(conversation_id):
    conversation = db.session.get(SupportConversation, conversation_id)
    if not conversation:
        return jsonify({"status": "error", "message": "Conversation not found"}), 404

    messages = (
        SupportMessage.query.filter_by(conversation_id=conversation_id)
        .order_by(SupportMessage.created_at.asc())
        .all()
    )

    SupportMessage.query.filter_by(
        conversation_id=conversation_id, sender_type="user", is_read=False
    ).update({"is_read": True})
    conversation.unread_by_admin = 0
    db.session.commit()

    return jsonify(
        {
            "status": "success",
            "conversation": {
                "id": conversation.id,
                "user_id": conversation.user_id,
                "user_name": conversation.user.username if conversation.user else None,
                "status": conversation.status,
            },
            "messages": [_serialize_message(m) for m in messages],
        }
    )


@supportBP.route("/admin/support/upload", methods=["POST"])
@admin_middleware
def admin_upload_attachment():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file provided"}), 400

    file = request.files["file"]
    url = upload_file(file, folder="support_attachments")
    attachment_type = "image" if file.content_type.startswith("image/") else "file"

    return jsonify(
        {"status": "success", "attachment_url": url, "attachment_type": attachment_type}
    )


@supportBP.route(
    "/admin/support/conversations/<int:conversation_id>/close", methods=["PATCH"]
)
@admin_middleware
def close_conversation(conversation_id):
    conversation = db.session.get(SupportConversation, conversation_id)
    if not conversation:
        return jsonify({"status": "error", "message": "Conversation not found"}), 404

    conversation.status = "closed"
    db.session.commit()
    return jsonify({"status": "success", "message": "Conversation closed"})


def _serialize_message(m):
    return {
        "id": m.id,
        "sender_type": m.sender_type,
        "sender_id": m.sender_id,
        "message": m.message,
        "attachment_url": m.attachment_url,
        "attachment_type": m.attachment_type,
        "is_read": m.is_read,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }
