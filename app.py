import hashlib
import hmac
import os
import secrets
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from urllib.parse import urlparse

import razorpay
from flask import Flask, jsonify, redirect, request, send_from_directory, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")

app = Flask(__name__, static_folder=PUBLIC_DIR, static_url_path="")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.config.update(
    SECRET_KEY=os.getenv("APP_SECRET_KEY") or os.getenv("FLASK_SECRET") or "dev-only-change-me",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "pool_recycle": 300},
)

@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if os.getenv("RENDER") == "true" or os.getenv("RENDER") == "1":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///grabit.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL

db = SQLAlchemy(app)
migrate = Migrate(app, db)

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@grabit.store").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()

rz_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET else None


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(100), nullable=False, default="General")
    price = db.Column(db.Numeric(12, 2), nullable=False)
    compare_at_price = db.Column(db.Numeric(12, 2), nullable=True)
    stock = db.Column(db.Integer, nullable=False, default=0)
    image = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)


class Order(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(180), nullable=False)
    customer_email = db.Column(db.String(180), nullable=True)
    customer_phone = db.Column(db.String(40), nullable=False)
    address = db.Column(db.Text, nullable=False)
    total = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="created")
    payment_status = db.Column(db.String(30), nullable=False, default="created")
    razorpay_order_id = db.Column(db.String(80), unique=True, nullable=True)
    razorpay_payment_id = db.Column(db.String(80), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    reservation_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    stock_reserved = db.Column(db.Boolean, nullable=False, default=False)
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan", lazy=True)


class OrderItem(db.Model):
    __tablename__ = "order_items"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id = db.Column(db.Integer, nullable=False)
    product_name = db.Column(db.String(180), nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)


class PaymentEvent(db.Model):
    __tablename__ = "payment_events"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(100), unique=True, nullable=False)
    event_type = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)


class Setting(db.Model):
    __tablename__ = "settings"
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=False, default="")


DEFAULT_SETTINGS = {
    "storeName": "GRABIT",
    "tagline": "Shop smart. GRAB it.",
    "phone": "",
    "whatsapp": "",
    "email": "",
    "address": "",
    "heroTitle": "Shop smart. GRAB it.",
    "heroSubtitle": "Quality products at great prices.",
    "heroButton": "Shop now",
    "announcement": "",
    "shippingCharge": "0",
    "freeShippingAbove": "999",
}


def seed_default_settings():
    """Seed settings after migrations have created the tables."""
    with app.app_context():
        for key, value in DEFAULT_SETTINGS.items():
            if db.session.get(Setting, key) is None:
                db.session.add(Setting(key=key, value=value))
        db.session.commit()


def maybe_init_local_db():
    if DATABASE_URL.startswith("sqlite") and os.getenv("AUTO_INIT_LOCAL_DB", "1") == "1":
        with app.app_context():
            db.create_all()
            for key, value in DEFAULT_SETTINGS.items():
                if db.session.get(Setting, key) is None:
                    db.session.add(Setting(key=key, value=value))
            db.session.commit()


@app.cli.command("seed-defaults")
def seed_defaults_command():
    seed_default_settings()
    print("Default settings seeded.")


def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def paise(value):
    return int((money(value) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def product_dict(p):
    return {
        "id": p.id,
        "name": p.name,
        "category": p.category,
        "price": float(p.price),
        "compareAtPrice": float(p.compare_at_price) if p.compare_at_price is not None else None,
        "stock": p.stock,
        "image": p.image or "",
        "description": p.description or "",
        "active": p.active,
    }


def order_dict(o):
    return {
        "id": o.id,
        "customer": {
            "name": o.customer_name,
            "email": o.customer_email or "",
                        "phone": f"{o.customer_phone} | {o.customer_email or ''} | {o.address}",
            "address": o.address,
        },
        "total": float(o.total),
        "status": o.status,
        "paymentStatus": o.payment_status,
        "razorpayOrderId": o.razorpay_order_id,
        "razorpayPaymentId": o.razorpay_payment_id,
        "createdAt": o.created_at.isoformat() if o.created_at else None,
        "items": [
            {
                "productId": i.product_id,
                "name": i.product_name,
                "price": float(i.unit_price),
                "quantity": i.quantity,
            }
            for i in o.items
        ],
    }


def settings_dict():
    values = dict(DEFAULT_SETTINGS)
    for s in Setting.query.all():
        values[s.key] = s.value
    return values


maybe_init_local_db()

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def validate_customer(name, phone, email, address):
    if not name or len(name) > 180 or len(phone) > 40 or len(address) > 2000:
        return False
    if email and (len(email) > 180 or not EMAIL_RE.match(email)):
        return False
    return True


def release_expired_reservations():
    now = datetime.now(timezone.utc)
    orders = Order.query.filter(
        Order.stock_reserved.is_(True),
        Order.payment_status == "created",
        Order.reservation_expires_at.isnot(None),
        Order.reservation_expires_at < now,
    ).all()
    for order in orders:
        for item in order.items:
            product = db.session.get(Product, item.product_id)
            if product:
                product.stock += item.quantity
        order.stock_reserved = False
        order.payment_status = "expired"
        order.status = "cancelled"
    if orders:
        db.session.commit()


def mark_order_paid(order, payment_id):
    if order.payment_status == "paid":
        return
    order.payment_status = "paid"
    order.status = "paid"
    order.razorpay_payment_id = payment_id
    order.stock_reserved = False


def release_order_stock(order):
    if not order.stock_reserved:
        return
    for item in order.items:
        product = db.session.get(Product, item.product_id)
        if product:
            product.stock += item.quantity
    order.stock_reserved = False


def admin_password_ok(password):
    if ADMIN_PASSWORD_HASH:
        return check_password_hash(ADMIN_PASSWORD_HASH, password)
    return bool(ADMIN_PASSWORD) and hmac.compare_digest(password, ADMIN_PASSWORD)


def is_admin():
    return session.get("admin") is True


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_admin():
            return jsonify({"error": "Authentication required"}), 401
        return fn(*args, **kwargs)
    return wrapper


def csrf_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_admin():
            return jsonify({"error": "Authentication required"}), 401
        token = request.headers.get("X-CSRF-Token", "")
        if not token or not hmac.compare_digest(token, session.get("csrf_token", "")):
            return jsonify({"error": "Invalid CSRF token"}), 403
        return fn(*args, **kwargs)
    return wrapper


@app.get("/health")
def health():
    try:
        db.session.execute(db.text("SELECT 1"))
        return jsonify({"ok": True, "database": "connected"})
    except Exception:
        db.session.rollback()
        return jsonify({"ok": False, "database": "unavailable"}), 503


@app.get("/")
def home():
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.get("/admin")
def admin_page():
    return send_from_directory(os.path.join(PUBLIC_DIR, "admin"), "index.html")


@app.get("/api/store")
def store_api():
    products = Product.query.filter_by(active=True).order_by(Product.id.desc()).all()
    return jsonify({"settings": settings_dict(), "products": [{**product_dict(p), "id": str(p.id)} for p in products]})


@app.get("/api/products")
def products_api():
    products = Product.query.order_by(Product.id.desc()).all()
    return jsonify([product_dict(p) for p in products])


@app.post("/api/admin/login")
def admin_login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    if not secrets.compare_digest(email, ADMIN_EMAIL) or not admin_password_ok(password):
        return jsonify({"error": "Invalid email or password"}), 401
    session.clear()
    session["admin"] = True
    session["csrf_token"] = secrets.token_urlsafe(32)
    return jsonify({"ok": True, "csrfToken": session["csrf_token"]})


@app.post("/api/admin/logout")
def admin_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/admin/me")
def admin_me():
    if not is_admin():
        return jsonify({"error": "Not logged in"}), 401
    return jsonify({"ok": True, "csrfToken": session.get("csrf_token", "")})


@app.get("/api/admin/dashboard")
@admin_required
def admin_dashboard():
    active_products = Product.query.filter_by(active=True).count()
    order_count = Order.query.count()
    pending = Order.query.filter(Order.status.in_(["created", "paid", "processing"])).count()
    revenue = db.session.query(db.func.coalesce(db.func.sum(Order.total), 0)).filter(Order.payment_status == "paid").scalar() or 0
    recent = Order.query.order_by(Order.id.desc()).limit(10).all()
    return jsonify({
        "activeProducts": active_products,
        "orders": order_count,
        "pending": pending,
        "revenue": float(revenue),
        "recent": [order_dict(o) for o in recent],
    })


@app.get("/api/admin/settings")
@admin_required
def admin_settings():
    return jsonify(settings_dict())


@app.put("/api/admin/settings")
@csrf_required
def save_settings():
    data = request.get_json(silent=True) or {}
    allowed = set(DEFAULT_SETTINGS)
    for key, value in data.items():
        if key not in allowed:
            continue
        setting = db.session.get(Setting, key)
        if setting is None:
            setting = Setting(key=key, value=str(value))
            db.session.add(setting)
        else:
            setting.value = str(value)
    db.session.commit()
    return jsonify(settings_dict())


def valid_image_url(value):
    if not value:
        return True
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and len(value) <= 2000
    except Exception:
        return False


@app.post("/api/admin/products")
@csrf_required
def create_product():
    data = request.get_json(silent=True) or {}
    try:
        price = money(data.get("price", 0))
        compare = data.get("compareAtPrice")
        compare = money(compare) if compare not in (None, "") else None
        stock = int(data.get("stock", 0))
    except (InvalidOperation, ValueError):
        return jsonify({"error": "Invalid price or stock"}), 400
    if not data.get("name") or price < 0 or stock < 0:
        return jsonify({"error": "Product name, price and stock are required"}), 400
    if not valid_image_url(str(data.get("image") or "").strip()):
        return jsonify({"error": "Image must be a valid http(s) URL"}), 400
    product = Product(
        name=str(data["name"]).strip(),
        category=str(data.get("category") or "General").strip(),
        price=price,
        compare_at_price=compare,
        stock=stock,
        image=str(data.get("image") or "").strip(),
        description=str(data.get("description") or "").strip(),
        active=bool(data.get("active", True)),
    )
    db.session.add(product)
    db.session.commit()
    return jsonify(product_dict(product)), 201


@app.put("/api/admin/products/<int:product_id>")
@csrf_required
def update_product(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({"error": "Product not found"}), 404
    data = request.get_json(silent=True) or {}
    try:
        product.price = money(data.get("price", product.price))
        compare = data.get("compareAtPrice")
        product.compare_at_price = money(compare) if compare not in (None, "") else None
        product.stock = int(data.get("stock", product.stock))
    except (InvalidOperation, ValueError):
        return jsonify({"error": "Invalid price or stock"}), 400
    product.name = str(data.get("name", product.name)).strip()
    product.category = str(data.get("category", product.category)).strip() or "General"
    product.image = str(data.get("image", product.image or "")).strip()
    product.description = str(data.get("description", product.description or "")).strip()
    if not valid_image_url(product.image):
        return jsonify({"error": "Image must be a valid http(s) URL"}), 400
    product.active = bool(data.get("active", product.active))
    if product.stock < 0 or product.price < 0:
        return jsonify({"error": "Price and stock cannot be negative"}), 400
    db.session.commit()
    return jsonify(product_dict(product))


@app.delete("/api/admin/products/<int:product_id>")
@csrf_required
def delete_product(product_id):
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({"error": "Product not found"}), 404
    product.active = False
    db.session.commit()
    return jsonify({"ok": True})


@app.get("/api/admin/orders")
@admin_required
def admin_orders():
    return jsonify([order_dict(o) for o in Order.query.order_by(Order.id.desc()).all()])


VALID_STATUSES = {"created", "paid", "processing", "shipped", "delivered", "cancelled"}


@app.patch("/api/admin/orders/<int:order_id>")
@csrf_required
def update_order(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    status = str((request.get_json(silent=True) or {}).get("status", "")).lower()
    if status not in VALID_STATUSES:
        return jsonify({"error": "Invalid status"}), 400
    if status in {"processing", "shipped", "delivered"} and order.payment_status != "paid":
        return jsonify({"error": "A paid order is required before fulfilment"}), 409
    if status == "cancelled" and order.payment_status == "paid":
        return jsonify({"error": "Refund the payment in Razorpay before cancelling a paid order"}), 409
    if status == "cancelled" and order.payment_status != "paid":
        release_order_stock(order)
        order.payment_status = "cancelled"
    order.status = status
    db.session.commit()
    return jsonify(order_dict(order))


@app.post("/api/checkout/create-order")
def create_checkout_order():
    data = request.get_json(silent=True) or {}
    raw_items = data.get("items") or []
    customer = data.get("customer") or {}
    if not raw_items:
        return jsonify({"error": "Your cart is empty"}), 400
    name = str(customer.get("name", "")).strip()
    phone = str(customer.get("phone", "")).strip()
    email = str(customer.get("email", "")).strip()
    address = ", ".join(x for x in [
        str(customer.get("address", "")).strip(),
        str(customer.get("city", "")).strip(),
        str(customer.get("pincode", "")).strip(),
    ] if x)
    if not validate_customer(name, phone, email, address):
        return jsonify({"error": "Please enter valid customer details"}), 400
    if not rz_client:
        return jsonify({"error": "Razorpay is not configured yet"}), 503

    release_expired_reservations()
    quantities = {}
    for row in raw_items:
        try:
            pid = int(row.get("productId"))
            qty = int(row.get("quantity", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid cart item"}), 400
        if pid <= 0 or qty < 1 or qty > 100:
            return jsonify({"error": "Invalid quantity"}), 400
        quantities[pid] = quantities.get(pid, 0) + qty
        if quantities[pid] > 100:
            return jsonify({"error": "Maximum quantity exceeded"}), 400

    try:
        db.session.commit()
        with db.session.begin():
            products = Product.query.filter(Product.id.in_(list(quantities)), Product.active.is_(True)).with_for_update().all()
            by_id = {p.id: p for p in products}
            if len(by_id) != len(quantities):
                return jsonify({"error": "One or more products are unavailable"}), 400

            total = Decimal("0.00")
            checked_items = []
            for pid, qty in quantities.items():
                p = by_id[pid]
                if p.stock < qty:
                    return jsonify({"error": f"Not enough stock for {p.name}"}), 409
                unit = money(p.price)
                total += unit * qty
                p.stock -= qty
                checked_items.append((p, qty, unit))

            total = money(total)
            order = Order(
                customer_name=name,
                customer_email=email or None,
                customer_phone=phone,
                address=address,
                total=total,
                status="created",
                payment_status="created",
                stock_reserved=True,
                reservation_expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            )
            db.session.add(order)
            db.session.flush()
            for p, qty, unit in checked_items:
                db.session.add(OrderItem(order_id=order.id, product_id=p.id, product_name=p.name, unit_price=unit, quantity=qty))
    except Exception:
        db.session.rollback()
        app.logger.exception("Could not reserve stock")
        return jsonify({"error": "Could not create the order. Please try again."}), 500

    try:
        receipt = f"GRB-{order.id}"
        rz_order = rz_client.order.create(data={"amount": paise(total), "currency": "INR", "receipt": receipt, "partial_payment": False})
        order.razorpay_order_id = rz_order["id"]
        db.session.commit()
    except Exception:
        db.session.rollback()
        order = db.session.get(Order, order.id)
        if order:
            release_order_stock(order)
            order.payment_status = "failed"
            order.status = "cancelled"
            db.session.commit()
        app.logger.exception("Razorpay order creation failed")
        return jsonify({"error": "Could not create the payment order. Please try again."}), 502

    return jsonify({
        "orderId": order.id,
        "razorpayOrderId": order.razorpay_order_id,
        "amount": paise(total),
        "currency": "INR",
        "key": RAZORPAY_KEY_ID,
        "storeName": settings_dict().get("storeName", "GRABIT"),
    })


@app.post("/api/checkout/verify")
def verify_payment():
    data = request.get_json(silent=True) or {}
    required = ["orderId", "razorpay_order_id", "razorpay_payment_id", "razorpay_signature"]
    if any(not data.get(k) for k in required):
        return jsonify({"error": "Missing payment fields"}), 400
    try:
        order_id = int(data["orderId"])
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid order"}), 400
    order = db.session.get(Order, order_id)
    if not order or order.razorpay_order_id != data["razorpay_order_id"]:
        return jsonify({"error": "Order not found"}), 404
    if order.payment_status == "paid":
        return jsonify({"ok": True, "orderId": order.id})
    try:
        rz_client.utility.verify_payment_signature({
            "razorpay_order_id": order.razorpay_order_id,
            "razorpay_payment_id": data["razorpay_payment_id"],
            "razorpay_signature": data["razorpay_signature"],
        })
        payment = rz_client.payment.fetch(data["razorpay_payment_id"])
        if payment.get("order_id") != order.razorpay_order_id or int(payment.get("amount", -1)) != paise(order.total):
            return jsonify({"error": "Payment details do not match this order"}), 400
        if payment.get("status") != "captured":
            return jsonify({"error": "Payment is not captured yet"}), 409
    except Exception:
        app.logger.exception("Payment verification failed")
        return jsonify({"error": "Payment verification failed"}), 400

    mark_order_paid(order, data["razorpay_payment_id"])
    db.session.commit()
    return jsonify({"ok": True, "orderId": order.id})


@app.post("/api/razorpay/webhook")
def razorpay_webhook():
    if not RAZORPAY_WEBHOOK_SECRET:
        return jsonify({"error": "Webhook is not configured"}), 503
    signature = request.headers.get("X-Razorpay-Signature", "")
    body = request.get_data()
    expected = hmac.new(RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        return jsonify({"error": "Invalid webhook signature"}), 400

    payload = request.get_json(silent=True) or {}
    event = payload.get("event", "")
    event_id = request.headers.get("X-Razorpay-Event-Id") or payload.get("id")
    if not event_id:
        event_id = hashlib.sha256(body).hexdigest()
    if PaymentEvent.query.filter_by(event_id=event_id).first():
        return jsonify({"ok": True})

    payment_entity = ((payload.get("payload") or {}).get("payment") or {}).get("entity") or {}
    order_entity = ((payload.get("payload") or {}).get("order") or {}).get("entity") or {}
    payment_id = payment_entity.get("id")
    razorpay_order_id = payment_entity.get("order_id") or order_entity.get("id")
    if not razorpay_order_id:
        return jsonify({"ok": True})

    order = Order.query.filter_by(razorpay_order_id=razorpay_order_id).first()
    db.session.add(PaymentEvent(event_id=event_id, event_type=event))
    if not order:
        db.session.commit()
        return jsonify({"ok": True})

    if event == "payment.captured" and payment_id:
        try:
            payment = rz_client.payment.fetch(payment_id)
            if payment.get("order_id") == order.razorpay_order_id and int(payment.get("amount", -1)) == paise(order.total) and payment.get("status") == "captured":
                mark_order_paid(order, payment_id)
        except Exception:
            db.session.rollback()
            app.logger.exception("Webhook payment verification failed")
            return jsonify({"error": "Temporary webhook processing failure"}), 500
    elif event == "payment.failed" and order.payment_status != "paid":
        release_order_stock(order)
        order.payment_status = "failed"
        order.status = "cancelled"
    db.session.commit()
    return jsonify({"ok": True})


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "Request is too large"}), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
