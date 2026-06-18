from app import app
from config.extension import db
import models.support  # registers SupportConversation / SupportMessage

with app.app_context():
    db.create_all()