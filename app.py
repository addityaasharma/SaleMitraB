from gevent import monkey
monkey.patch_all()

from config.extension import *
from config.settings import BaseConfig
from flask import Flask
from functions.helper_function import init_oauth
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.config.from_object(BaseConfig)

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1
)

app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "None"

db.init_app(app)
migrate.init_app(app, db)
print("JWT OBJECT:", jwt)
print("JWT TYPE:", type(jwt))
jwt.init_app(app)
socketio.init_app(app, async_mode="gevent")
cors.init_app(app)
limiter.init_app(app)
init_oauth(app)

from routes.adminRouter import *
from routes.userRoutes import *
from routes.supportRoutes import *
from routes.affiliateRoutes import *
from sockets.support_socket import *

app.register_blueprint(userBP)
app.register_blueprint(adminBP)
app.register_blueprint(supportBP)
app.register_blueprint(affiliateBP)

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    socketio.run(app, debug=False, use_reloader=False)
    # socketio.run(app, debug=True)
