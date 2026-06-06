from config.extension import *
from config.settings import BaseConfig
from flask import Flask

app = Flask(__name__)
app.config.from_object(BaseConfig)

db.init_app(app)
migrate.init_app(app, db)
jwt.init_app(app)
socketio.init_app(app)
cors.init_app(app)
limiter.init_app(app)

from routes import *

if __name__ == "__main__":
    socketio.run(app, debug=True)