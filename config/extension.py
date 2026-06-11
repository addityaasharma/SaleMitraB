from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import redis, os, resend, boto3
from dotenv import load_dotenv
from celery import Celery
import razorpay

load_dotenv()

db = SQLAlchemy()
socketio = SocketIO(cors_allowed_origins="*", async_mode="gevent")
migrate = Migrate()
jwt = JWTManager()
cors = CORS(resources={r"/*": {
    "origins": "*",
    "allow_headers": ["Authorization", "Content-Type"],
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "expose_headers": ["Authorization"]
}})
limiter = Limiter(
    key_func=get_remote_address, default_limits=["2000 per day", "200 per hour"]
)
redis = redis.Redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)
resend.api_key = os.getenv("RESEND_API_KEY")
celery = Celery("tasks", broker=os.getenv("REDIS_URL"), backend=os.getenv("REDIS_URL"))
s3 = boto3.client(
    "s3",
    endpoint_url=os.getenv("R2_ENDPOINT"),
    aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
    region_name="auto",
)
razorpay_client = razorpay.Client(
    auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET"))
)
