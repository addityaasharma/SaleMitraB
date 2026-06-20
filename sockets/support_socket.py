import os
import jwt
from flask import request
from flask_socketio import emit, join_room
from config.extension import socketio, db
from models.user import User
from models.admin import Admin
from models.support import SupportConversation, SupportMessage

connected_clients = {}
online_admins = {}
online_users = {}


def admin_room():
    return "support_admin_room"


def conversation_room(conversation_id):
    return f"support_conversation_{conversation_id}"


def authenticate(auth):
    if not auth or "token" not in auth or "role" not in auth:
        return None

    try:
        decoded = jwt.decode(
            auth["token"], os.getenv("SECRET_KEY"), algorithms=["HS256"]
        )
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

    if auth["role"] == "admin":
        admin = Admin.query.get(decoded.get("id"))
        return {"role": "admin", "id": admin.id} if admin else None

    if auth["role"] == "user":
        user = User.query.get(decoded.get("userID"))
        return {"role": "user", "id": user.id} if user else None

    return None


@socketio.on("connect", namespace="/support")
def handle_connect(auth):
    identity = authenticate(auth)
    if not identity:
        db.session.remove()
        return False

    connected_clients[request.sid] = identity

    try:
        if identity["role"] == "admin":
            join_room(admin_room(), namespace="/support")
            online_admins.setdefault(identity["id"], set()).add(request.sid)
            emit(
                "admin_online",
                {"online": True},
                room=admin_room(),
                namespace="/support",
            )
            emit(
                "online_users",
                {"user_ids": list(online_users.keys())},
                namespace="/support",
            )
        else:
            conversation = SupportConversation.query.filter_by(
                user_id=identity["id"]
            ).first()
            if not conversation:
                conversation = SupportConversation(user_id=identity["id"])
                db.session.add(conversation)
                db.session.commit()

            join_room(conversation_room(conversation.id), namespace="/support")
            online_users.setdefault(identity["id"], set()).add(request.sid)

            emit(
                "admin_status", {"online": len(online_admins) > 0}, namespace="/support"
            )
            emit(
                "user_online",
                {"user_id": identity["id"], "conversation_id": conversation.id},
                room=admin_room(),
                namespace="/support",
            )
    finally:
        db.session.remove()


@socketio.on("disconnect", namespace="/support")
def handle_disconnect():
    identity = connected_clients.pop(request.sid, None)
    if not identity:
        db.session.remove()
        return

    try:
        if identity["role"] == "admin":
            sids = online_admins.get(identity["id"])
            if sids:
                sids.discard(request.sid)
                if not sids:
                    online_admins.pop(identity["id"], None)
            if not online_admins:
                emit(
                    "admin_online",
                    {"online": False},
                    room=admin_room(),
                    namespace="/support",
                )
        else:
            sids = online_users.get(identity["id"])
            if sids:
                sids.discard(request.sid)
                if not sids:
                    online_users.pop(identity["id"], None)
                    emit(
                        "user_offline",
                        {"user_id": identity["id"]},
                        room=admin_room(),
                        namespace="/support",
                    )
    finally:
        db.session.remove()


@socketio.on("join_conversation", namespace="/support")
def handle_join_conversation(data):
    identity = connected_clients.get(request.sid)
    if not identity or identity["role"] != "admin":
        db.session.remove()
        return

    conversation_id = data.get("conversation_id")
    if not conversation_id:
        db.session.remove()
        return

    try:
        join_room(conversation_room(conversation_id), namespace="/support")

        SupportMessage.query.filter_by(
            conversation_id=conversation_id, sender_type="user", is_read=False
        ).update({"is_read": True})
        conversation = db.session.get(SupportConversation, conversation_id)
        if conversation:
            conversation.unread_by_admin = 0
            db.session.commit()

        emit(
            "messages_read",
            {"conversation_id": conversation_id, "reader": "admin"},
            room=conversation_room(conversation_id),
            namespace="/support",
        )
    finally:
        db.session.remove()


def _resolve_conversation(identity, data):
    if identity["role"] == "user":
        conversation = SupportConversation.query.filter_by(
            user_id=identity["id"]
        ).first()
        if not conversation:
            conversation = SupportConversation(user_id=identity["id"])
            db.session.add(conversation)
            db.session.commit()
        return conversation

    conversation_id = data.get("conversation_id")
    return (
        db.session.get(SupportConversation, conversation_id)
        if conversation_id
        else None
    )


@socketio.on("send_message", namespace="/support")
def handle_send_message(data):
    identity = connected_clients.get(request.sid)
    if not identity:
        db.session.remove()
        return

    try:
        message_text = (data.get("message") or "").strip()
        attachment_url = data.get("attachment_url")
        attachment_type = data.get("attachment_type")

        if not message_text and not attachment_url:
            return

        conversation = _resolve_conversation(identity, data)
        if not conversation:
            return

        msg = SupportMessage(
            conversation_id=conversation.id,
            sender_type=identity["role"],
            sender_id=identity["id"],
            message=message_text or None,
            attachment_url=attachment_url,
            attachment_type=attachment_type,
        )
        db.session.add(msg)
        db.session.flush()

        preview = (
            message_text
            if message_text
            else ("Photo" if attachment_type == "image" else "Attachment")
        )
        conversation.last_message = preview[:255]
        conversation.last_message_at = msg.created_at
        conversation.status = "open"

        if identity["role"] == "user":
            conversation.unread_by_admin += 1
        else:
            conversation.unread_by_user += 1

        db.session.commit()

        payload = {
            "id": msg.id,
            "conversation_id": conversation.id,
            "sender_type": msg.sender_type,
            "sender_id": msg.sender_id,
            "message": msg.message,
            "attachment_url": msg.attachment_url,
            "attachment_type": msg.attachment_type,
            "created_at": msg.created_at.isoformat(),
        }

        emit(
            "new_message",
            payload,
            room=conversation_room(conversation.id),
            namespace="/support",
        )
        emit(
            "conversation_updated",
            {
                "conversation_id": conversation.id,
                "last_message": conversation.last_message,
                "last_message_at": conversation.last_message_at.isoformat(),
                "unread_by_admin": conversation.unread_by_admin,
            },
            room=admin_room(),
            namespace="/support",
        )
    finally:
        db.session.remove()


def _conversation_id_for(identity, data):
    conversation_id = data.get("conversation_id")
    if conversation_id:
        return conversation_id
    if identity["role"] == "user":
        conversation = SupportConversation.query.filter_by(
            user_id=identity["id"]
        ).first()
        return conversation.id if conversation else None
    return None


@socketio.on("typing", namespace="/support")
def handle_typing(data):
    identity = connected_clients.get(request.sid)
    if not identity:
        db.session.remove()
        return
    try:
        conversation_id = _conversation_id_for(identity, data)
        if not conversation_id:
            return
        emit(
            "typing",
            {"conversation_id": conversation_id, "sender_type": identity["role"]},
            room=conversation_room(conversation_id),
            namespace="/support",
            include_self=False,
        )
    finally:
        db.session.remove()


@socketio.on("stop_typing", namespace="/support")
def handle_stop_typing(data):
    identity = connected_clients.get(request.sid)
    if not identity:
        db.session.remove()
        return
    try:
        conversation_id = _conversation_id_for(identity, data)
        if not conversation_id:
            return
        emit(
            "stop_typing",
            {"conversation_id": conversation_id, "sender_type": identity["role"]},
            room=conversation_room(conversation_id),
            namespace="/support",
            include_self=False,
        )
    finally:
        db.session.remove()


@socketio.on("mark_read", namespace="/support")
def handle_mark_read(data):
    identity = connected_clients.get(request.sid)
    if not identity:
        db.session.remove()
        return

    try:
        conversation_id = _conversation_id_for(identity, data)
        if not conversation_id:
            return

        conversation = db.session.get(SupportConversation, conversation_id)
        if not conversation:
            return

        if identity["role"] == "user":
            SupportMessage.query.filter_by(
                conversation_id=conversation_id, sender_type="admin", is_read=False
            ).update({"is_read": True})
            conversation.unread_by_user = 0
            reader = "user"
        else:
            SupportMessage.query.filter_by(
                conversation_id=conversation_id, sender_type="user", is_read=False
            ).update({"is_read": True})
            conversation.unread_by_admin = 0
            reader = "admin"

        db.session.commit()
        emit(
            "messages_read",
            {"conversation_id": conversation_id, "reader": reader},
            room=conversation_room(conversation_id),
            namespace="/support",
        )
    finally:
        db.session.remove()
