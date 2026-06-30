from app import app, db

with app.app_context():
    db.session.execute(db.text("ALTER TYPE affiliate_status ADD VALUE 'rejected'"))
    db.session.commit()
    print("Done!")