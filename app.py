from gevent import monkey

monkey.patch_all()

from config.extension import *
from config.settings import BaseConfig
from flask import Flask

app = Flask(__name__)
app.config.from_object(BaseConfig)

db.init_app(app)
migrate.init_app(app, db)
jwt.init_app(app)
socketio.init_app(app, async_mode="gevent")
cors.init_app(app)
limiter.init_app(app)

from routes.adminRouter import *
from routes.userRoutes import *
from routes.supportRoutes import *
from sockets.support_socket import *

app.register_blueprint(userBP)
app.register_blueprint(adminBP)
app.register_blueprint(supportBP)

@app.route('/', methods=["GET"])
def check_server():
    try:
        return "Running  :)"
    except Exception as e:
        return jsonify({"status" : False , "message"  : str(e)}), 500

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    socketio.run(app, debug=False, use_reloader=False)
