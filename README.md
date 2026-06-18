# SaleMitra Backend

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Flask-3.x-black?style=for-the-badge&logo=flask&logoColor=white" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-316192?style=for-the-badge&logo=postgresql&logoColor=white" />
  <img src="https://img.shields.io/badge/Redis-7-DC382D?style=for-the-badge&logo=redis&logoColor=white" />
  <img src="https://img.shields.io/badge/Cloudflare_R2-F38020?style=for-the-badge&logo=cloudflare&logoColor=white" />
  <img src="https://img.shields.io/badge/Razorpay-02042B?style=for-the-badge&logo=razorpay&logoColor=white" />
</p>

<p align="center">
  A production-ready, full-featured e-commerce backend powering <strong>SaleMitra</strong> — a Shopify-style platform built with Flask, PostgreSQL, and Redis.
</p>

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Features](#features)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Deployment](#deployment)
- [License](#license)

---

## Overview

SaleMitra Backend is a REST API server that powers both an admin panel and a user-facing storefront. It handles everything from product management and order processing to payment verification and file uploads — all built to be production-ready and deployable on any VPS or cloud provider.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Framework | Flask + Flask-Blueprints |
| Database | PostgreSQL + SQLAlchemy ORM |
| Auth | Flask-JWT-Extended |
| Cache / OTP | Redis |
| Real-time | Flask-SocketIO (gevent) |
| Rate Limiting | Flask-Limiter |
| Background Jobs | Celery + Redis |
| File Storage | Cloudflare R2 (S3-compatible) |
| Payments | Razorpay |
| Shipping | Shiprocket |
| Email | Resend |
| Server | Gunicorn (gevent worker) |

---

## Features

### Admin
- JWT-based admin authentication with role support
- Store settings management (name, logo, address, social links)
- Full CRUD for products (with image upload to R2), categories, collections, banners
- Order management with status updates and fulfillment via Shiprocket
- User management (view, block/unblock)
- Notification and payment settings
- Dashboard stats

### User / Storefront
- OTP-based signup and login via email
- Forgot / reset password with OTP
- Profile management with avatar upload
- Address book (CRUD)
- Product browsing with filters, search, sorting, pagination
- Product reviews (add, edit, delete)
- Wishlist and Cart management
- Order placement with Razorpay payment integration
- Order tracking and cancellation
- Refund requests

### Platform
- Gevent-powered async handling for WebSocket support
- Rate limiting on sensitive routes
- CORS configured for frontend domains
- Consistent `{"status": "success/error", ...}` API response shape
- File uploads via UUID-based keys to Cloudflare R2
- Shiprocket integration (non-blocking — failures don't prevent order creation)

---

## Project Structure

```
salemitra-backend/
├── app.py                  # Entry point, monkey-patching, app factory
├── config.py               # Config from environment variables
├── extensions.py           # db, jwt, redis, limiter instances
├── models/
│   ├── admin.py            # Admin, Store, Category, Products, Banner, Collection, etc.
│   └── user.py             # User, Address, Cart, WishList, Orders, Payment, Refund, etc.
├── routes/
│   ├── adminRoutes.py      # All /admin/* endpoints
│   └── userRoutes.py       # All /user/* endpoints
├── middleware/
│   ├── adminMiddleware.py  # @admin_middleware decorator
│   └── userMiddleware.py   # @middleware decorator
├── helpers/
│   ├── upload.py           # R2 file upload helper
│   ├── mail.py             # Email via Resend
│   ├── otp.py              # OTP generator
│   └── shiprocket.py       # Shiprocket API integration
├── requirements.txt
└── .env
```

---

## Getting Started

### Prerequisites

- Python 3.11
- PostgreSQL
- Redis
- Git

### Local Setup

```bash
# Clone the repo
git clone https://github.com/addityaasharma/SaleMitraB.git
cd SaleMitraB

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file (see Environment Variables section)
cp .env.example .env

# Run the development server
python app.py
```

The server will start at `http://localhost:5000`.

---

## Environment Variables

Create a `.env` file in the root directory:

```env
# App
SECRET_KEY=your_secret_key_here

# Database
DATABASE_URL=postgresql://user:password@localhost/salemitra_db

# Redis
REDIS_URL=redis://localhost:6379/0
RATELIMIT_STORAGE_URL=redis://localhost:6379/0

# Cloudflare R2
R2_BUCKET_NAME=your-bucket-name
R2_PUBLIC_URL=https://your-r2-public-url
R2_ACCESS_KEY=
R2_SECRET_KEY=
R2_ENDPOINT_URL=https://your-account-id.r2.cloudflarestorage.com

# Razorpay
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=

# Shiprocket
SHIPROCKET_EMAIL=
SHIPROCKET_PASSWORD=
SHIPROCKET_CHANNEL_ID=
WAREHOUSE_PINCODE=

# Email (Resend)
RESEND_API_KEY=

# Frontend
CLIENT_URL=https://yourdomain.com
```

---

## API Reference

### Admin Routes — `/admin`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/admin/login` | Admin login |
| POST | `/admin/logout` | Admin logout |
| GET | `/admin/profile` | Get admin profile |
| PUT | `/admin/profile` | Update admin profile |
| GET/POST/PUT | `/admin/store` | Store settings |
| GET/POST/PUT | `/admin/notifications` | Notification settings |
| GET/POST/PUT | `/admin/payment-settings` | Payment settings |
| GET/POST | `/admin/categories` | List / create categories |
| GET/PUT/DELETE | `/admin/categories/:id` | Get / update / delete category |
| GET/POST | `/admin/products` | List / create products |
| GET/PUT/DELETE | `/admin/products/:id` | Get / update / delete product |
| GET/POST | `/admin/collections` | List / create collections |
| GET/PUT/DELETE | `/admin/collections/:id` | Get / update / delete collection |
| GET/POST | `/admin/banners` | List / create banners |
| GET/PUT/DELETE | `/admin/banners/:id` | Get / update / delete banner |
| GET | `/admin/orders` | List all orders |
| GET/PUT | `/admin/orders/:id` | Get / update order status |
| GET | `/admin/users` | List all users |
| PUT | `/admin/users/:id` | Update user (block/unblock) |
| GET | `/admin/dashboard` | Dashboard stats |

### User Routes — `/user`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/user/signup` | Send OTP for signup |
| POST | `/user/signup/verify` | Verify OTP and create account |
| POST | `/user/login` | User login |
| POST | `/user/logout` | User logout |
| POST | `/user/password/forget` | Send password reset OTP |
| POST | `/user/password/reset` | Reset password with OTP |
| GET/PUT | `/user/me` | Get / update profile |
| GET/POST | `/user/me/address` | List / add address |
| PUT/DELETE | `/user/me/address/:id` | Update / delete address |
| GET/POST/DELETE | `/user/me/cart` | Cart operations |
| PUT/DELETE | `/user/me/cart/:id` | Update / remove cart item |
| GET/POST/DELETE | `/user/me/wishlist` | Wishlist operations |
| DELETE | `/user/me/wishlist/:id` | Remove wishlist item |
| GET | `/user/me/orders` | List user orders |
| POST | `/user/me/order/create` | Create order + Razorpay |
| POST | `/user/me/order/razorpay/verify` | Verify Razorpay payment |
| GET | `/user/me/order/:id` | Get order detail |
| PUT | `/user/me/order/:id/cancel` | Cancel order |
| GET/POST/DELETE | `/user/me/order/:id/refund` | Refund operations |
| GET | `/user/products` | List products with filters |
| GET | `/user/products/:id` | Get product detail |
| GET | `/user/products/:id/related` | Related products |
| POST/PUT/DELETE | `/user/products/:id/review` | Review operations |
| GET | `/user/categories` | List categories |
| GET | `/user/categories/:id` | Category with products |
| GET | `/user/collections` | List collections |
| GET | `/user/collections/:id` | Collection with products |
| GET | `/user/banners` | Active banners |
| GET | `/user/store` | Public store info |
| GET | `/user/search` | Search products |

---

## Deployment

### VPS (Ubuntu 22.04 + Nginx + Gunicorn)

```bash
# Install Python 3.11
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update && sudo apt install -y python3.11 python3.11-venv

# Clone and setup
git clone https://github.com/addityaasharma/SaleMitraB.git /var/www/salemitrabackend
cd /var/www/salemitrabackend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create tables
python3 -c "from app import app, db; app.app_context().push(); db.create_all()"

# Start with Gunicorn
gunicorn --worker-class gevent -w 1 --bind 127.0.0.1:8000 "app:app"
```

### Systemd Service

```ini
[Unit]
Description=SaleMitra Flask Backend
After=network.target postgresql.service redis.service

[Service]
User=root
WorkingDirectory=/var/www/salemitrabackend
EnvironmentFile=/var/www/salemitrabackend/.env
ExecStart=/var/www/salemitrabackend/venv/bin/gunicorn \
    --worker-class gevent -w 1 \
    --bind 127.0.0.1:8000 \
    --timeout 120 \
    "app:app"
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### Nginx Proxy

```nginx
server {
    listen 443 ssl;
    server_name api.salemitra.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        client_max_body_size 50M;
    }
}
```

> **Note:** Python 3.14 is incompatible with gevent. Always use Python 3.11.  
> `monkey.patch_all()` must be at the very top of `app.py` before all other imports.

---

## License

MIT License © 2025 Aditya Sharma
