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
from flask import Flask, Response, abort, jsonify, redirect, request, send_from_directory, session
from markupsafe import escape
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
    "themePreset": "classic",
    "themeFont": "modern",
    "themeBtn": "",
    "themeBg": "",
    "themeInk": "",
    "themeHero1": "",
    "themeHero2": "",
    "banner1": "",
    "banner2": "",
    "banner3": "",
    "bizName": "",
    "gstin": "",
    "hours": "",
    "shipAreas": "across India",
    "dispatchDays": "1-2",
    "deliveryDays": "3-7",
    "returnDays": "7",
    "refundDays": "5-7",
    "nonReturnable": "",
    "priceNote": "Prices are inclusive of all applicable taxes.",
    "grievanceName": "",
    "grievanceEmail": "",
    "jurisdiction": "",
}

POLICY_KEYS = {"bizName", "gstin", "hours", "shipAreas", "dispatchDays", "deliveryDays", "returnDays",
               "refundDays", "nonReturnable", "priceNote", "grievanceName", "grievanceEmail", "jurisdiction"}

BANNER_KEYS = {"banner1", "banner2", "banner3"}

THEME_COLOR_KEYS = {"themeBtn", "themeBg", "themeInk", "themeHero1", "themeHero2"}
THEME_PRESETS = {"classic", "midnight", "forest", "ocean", "rose", "mono"}
THEME_FONTS = {"modern", "serif"}


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
        "images": split_images(p.image),
        "description": p.description or "",
        "active": p.active,
    }


def order_dict(o):
    return {
        "id": o.id,
        "customer": {
            "name": o.customer_name,
            "email": o.customer_email or "",
            "phone": f"{o.customer_phone} | {o.customer_email or ''} | {o.address} | ITEMS: " + ", ".join(
                f"{i.product_name} x{i.quantity}" for i in o.items),
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


POLICY_PAGES = [
    ("about-us", "About Us"),
    ("contact-us", "Contact Us"),
    ("pricing", "Pricing Details"),
    ("shipping-policy", "Shipping Policy"),
    ("refund-policy", "Cancellation & Refund Policy"),
    ("terms", "Terms & Conditions"),
    ("privacy-policy", "Privacy Policy"),
]

THEME_PRESET_VARS = {
    "classic": dict(btn="#111111", bg="#ffffff", surface="#ffffff", ink="#161616", muted="#6b6b6b", line="#e7e7e7", soft="#f6f5f1", radius="18px"),
    "midnight": dict(btn="#ff5a36", bg="#0f1115", surface="#181b22", ink="#f2f3f5", muted="#9aa0ab", line="#2a2f3a", soft="#20242d", radius="16px"),
    "forest": dict(btn="#14532d", bg="#ffffff", surface="#ffffff", ink="#10231a", muted="#5b6f64", line="#dfe9e2", soft="#f1f7f3", radius="14px"),
    "ocean": dict(btn="#1d4ed8", bg="#ffffff", surface="#ffffff", ink="#0f172a", muted="#64748b", line="#e2e8f0", soft="#f1f5f9", radius="14px"),
    "rose": dict(btn="#be185d", bg="#fffafb", surface="#ffffff", ink="#2a1520", muted="#7a5c69", line="#f1dfe6", soft="#fbf1f5", radius="22px"),
    "mono": dict(btn="#000000", bg="#ffffff", surface="#ffffff", ink="#000000", muted="#666666", line="#dddddd", soft="#f5f5f5", radius="4px"),
}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _luminance(hex_color):
    channels = []
    for i in (1, 3, 5):
        v = int(hex_color[i:i + 2], 16) / 255
        channels.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def theme_vars(s):
    t = dict(THEME_PRESET_VARS.get(s.get("themePreset"), THEME_PRESET_VARS["classic"]))
    if _HEX.match(s.get("themeBtn") or ""):
        t["btn"] = s["themeBtn"]
    if _HEX.match(s.get("themeBg") or ""):
        t["bg"] = t["surface"] = s["themeBg"]
    if _HEX.match(s.get("themeInk") or ""):
        t["ink"] = s["themeInk"]
    t["btnText"] = "#111111" if _luminance(t["btn"]) > 0.55 else "#ffffff"
    t["font"] = 'Georgia,"Times New Roman",serif' if s.get("themeFont") == "serif" else "Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif"
    return t


def _p(s, key, default=""):
    return str(escape((s.get(key) or default).strip()))


def _ship_text(s):
    try:
        charge = float(s.get("shippingCharge") or 0)
        free = float(s.get("freeShippingAbove") or 0)
    except ValueError:
        charge, free = 0.0, 0.0
    if not charge:
        return "Delivery is free on all orders."
    if free:
        return f"A delivery charge of ₹{charge:g} applies to orders below ₹{free:g}. Delivery is free on orders of ₹{free:g} and above."
    return f"A delivery charge of ₹{charge:g} applies to every order."


def _contact_list(s):
    rows = []
    biz = _p(s, "bizName") or _p(s, "storeName", "Our store")
    rows.append(f"<li><b>Business name:</b> {biz}</li>")
    if _p(s, "gstin"):
        rows.append(f"<li><b>GSTIN:</b> {_p(s, 'gstin')}</li>")
    if _p(s, "address"):
        rows.append(f"<li><b>Address:</b> {_p(s, 'address')}</li>")
    if _p(s, "phone"):
        rows.append(f"<li><b>Phone:</b> {_p(s, 'phone')}</li>")
    if _p(s, "email"):
        rows.append(f"<li><b>Email:</b> <a href=\"mailto:{_p(s, 'email')}\">{_p(s, 'email')}</a></li>")
    if _p(s, "hours"):
        rows.append(f"<li><b>Working hours:</b> {_p(s, 'hours')}</li>")
    return "<ul>" + "".join(rows) + "</ul>"


def build_policy_pages(s):
    store = _p(s, "storeName", "Our store")
    biz = _p(s, "bizName") or store
    email = _p(s, "email")
    contact_line = f'Write to us at <a href="mailto:{email}">{email}</a>' if email else "Contact us using the details on our Contact Us page"
    if _p(s, "phone"):
        contact_line += f" or call {_p(s, 'phone')}"
    contact_line += "."
    dispatch = _p(s, "dispatchDays", "1-2")
    delivery = _p(s, "deliveryDays", "3-7")
    areas = _p(s, "shipAreas", "across India")
    ret = _p(s, "returnDays", "7")
    refund = _p(s, "refundDays", "5-7")
    juris = _p(s, "jurisdiction") or "India"
    g_name = _p(s, "grievanceName")
    g_mail = _p(s, "grievanceEmail") or email
    non_ret = _p(s, "nonReturnable")
    non_ret_html = f"<p><b>Items that cannot be returned:</b> {non_ret}</p>" if non_ret else ""
    tagline = _p(s, "tagline")
    pages = {}

    pages["about-us"] = f"""
<p>{store} is an online store operated by {biz}. {tagline}</p>
<p>We aim to offer useful products at fair prices, with clear information, secure payments and support you can reach.</p>
<h2>Contact</h2>
<p>{contact_line}</p>
"""

    pages["contact-us"] = f"""
<p>We are happy to help with questions about products, orders, delivery, returns or refunds.</p>
<h2>Business details</h2>
{_contact_list(s)}
<h2>Grievance officer</h2>
<p>{('Name: ' + g_name + '<br>') if g_name else ''}{('Email: <a href="mailto:' + g_mail + '">' + g_mail + '</a>') if g_mail else ''}</p>
<p>We acknowledge complaints within 48 hours and work to resolve them within one month.</p>
"""

    pages["pricing"] = f"""
<p>All prices on {store} are in Indian Rupees (INR).</p>
<ul>
<li>The selling price is shown on each product. A crossed-out price, where shown, is the original price for comparison.</li>
<li>{_p(s, 'priceNote', 'Prices are inclusive of all applicable taxes.')}</li>
<li>{_ship_text(s)}</li>
<li>The final amount you pay, including any delivery charge, is shown at checkout before you pay. There are no hidden charges.</li>
</ul>
<p>We may correct pricing or listing errors. If a product is listed at a wrong price, we will contact you before dispatch, and you may cancel for a full refund.</p>
"""

    pages["shipping-policy"] = f"""
<h2>Where we deliver</h2>
<p>We deliver {areas}.</p>
<h2>Dispatch and delivery time</h2>
<ul>
<li>Orders are dispatched within {dispatch} business days after payment is confirmed.</li>
<li>Delivery usually takes {delivery} business days after dispatch, depending on your location and the courier.</li>
<li>Delays can happen because of weather, holidays or courier issues. We will help you track and resolve them.</li>
</ul>
<h2>Delivery charges</h2>
<p>{_ship_text(s)}</p>
<h2>Tracking your order</h2>
<p>Use <b>Track order</b> on our website and enter the phone number you used at checkout to see your order status.</p>
<h2>Wrong or incomplete address</h2>
<p>Please check your address and PIN code before paying. If a parcel cannot be delivered because of a wrong or incomplete address, extra delivery charges may apply for re-sending it.</p>
<p>{contact_line}</p>
"""

    pages["refund-policy"] = f"""
<h2>Cancellation</h2>
<ul>
<li>You can cancel an order before it is dispatched. Contact us as soon as possible with your order number.</li>
<li>Once an order has been dispatched it cannot be cancelled, but you may be able to return it as described below.</li>
</ul>
<h2>Returns</h2>
<ul>
<li>You can request a return within {ret} days of delivery if the product is damaged, defective, or different from what you ordered.</li>
<li>Please share photos of the product and the packaging when you contact us.</li>
<li>Returned products must be unused and in their original packaging.</li>
</ul>
{non_ret_html}
<h2>Refunds</h2>
<ul>
<li>Approved refunds are sent to your original payment method within {refund} business days.</li>
<li>If money was deducted but your order was not confirmed, the amount is usually returned automatically by your bank or payment provider within 5 to 7 business days. If it is not, contact us with your payment details.</li>
</ul>
<h2>How to request a return or refund</h2>
<p>{contact_line} Please include your order number and phone number.</p>
"""

    pages["terms"] = f"""
<p>These terms apply to your use of {store}, operated by {biz}. By placing an order you agree to them.</p>
<h2>1. Eligibility</h2>
<p>You must be at least 18 years old, or use the store with a parent or guardian, to place an order.</p>
<h2>2. Products and prices</h2>
<p>We try to describe products and prices accurately. Product photos are for reference and colours may vary slightly. We may correct errors and may cancel an order affected by one, with a full refund.</p>
<h2>3. Orders and payment</h2>
<p>Your order is confirmed once payment is successful. Payments are processed securely by Razorpay. We do not see or store your card, UPI or bank details.</p>
<h2>4. Delivery, returns and refunds</h2>
<p>Please read our <a href="/policy/shipping-policy">Shipping Policy</a> and <a href="/policy/refund-policy">Cancellation &amp; Refund Policy</a>, which are part of these terms.</p>
<h2>5. Your responsibilities</h2>
<p>Provide correct contact and delivery details. Do not misuse the website, attempt to interfere with its operation, or use it for unlawful purposes.</p>
<h2>6. Intellectual property</h2>
<p>The content on this website, including text, images and design, belongs to {biz} or its licensors and may not be copied without permission.</p>
<h2>7. Limitation of liability</h2>
<p>To the extent permitted by law, we are not liable for indirect or consequential losses. Our total liability for any order is limited to the amount you paid for it.</p>
<h2>8. Governing law</h2>
<p>These terms are governed by the laws of India. Courts at {juris} have jurisdiction over any dispute.</p>
<h2>9. Changes</h2>
<p>We may update these terms from time to time. The version on this page applies when you place your order.</p>
<h2>10. Contact</h2>
<p>{contact_line}</p>
"""

    pages["privacy-policy"] = f"""
<p>{biz} respects your privacy. This policy explains what personal data {store} collects, why, and your choices. We handle personal data in line with applicable Indian law, including the Digital Personal Data Protection Act, 2023.</p>
<h2>Information we collect</h2>
<ul>
<li>Details you enter at checkout: name, phone number, email address (optional), delivery address, city and PIN code.</li>
<li>Order details: products bought, amounts, order status and payment status.</li>
<li>Technical data stored in your browser, such as your cart and display preferences.</li>
</ul>
<p>Payments are handled by Razorpay. We do not receive or store your card, UPI or bank details.</p>
<h2>How we use it</h2>
<ul>
<li>To process, deliver and support your order, and to show you your order status.</li>
<li>To handle returns, refunds and complaints.</li>
<li>To meet accounting, tax and legal requirements.</li>
</ul>
<h2>Who we share it with</h2>
<p>Only with those needed to complete your order: our payment provider (Razorpay), courier and delivery partners, and authorities where the law requires. We do not sell your personal data.</p>
<h2>Order tracking</h2>
<p>The Track order page shows the status of orders linked to a phone number. It does not show your address or email.</p>
<h2>How long we keep it</h2>
<p>We keep order records for as long as needed for orders, returns, accounting and legal obligations, then delete or anonymise them.</p>
<h2>Your rights</h2>
<p>You can ask to access, correct or delete your personal data, or withdraw consent, by contacting us. We will respond within a reasonable time, subject to legal retention requirements.</p>
<h2>Security</h2>
<p>We use reasonable safeguards, including encrypted connections (HTTPS) and restricted admin access. No online system is completely risk-free.</p>
<h2>Contact and grievances</h2>
<p>{contact_line}</p>
{('<p>Grievance officer: ' + g_name + '</p>') if g_name else ''}
"""
    return pages


POLICY_TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>%%TITLE%% | %%STORE%%</title><link rel="icon" type="image/svg+xml" href="/favicon.svg"><style>
:root{%%VARS%%}
*{box-sizing:border-box}body{margin:0;font-family:var(--font);color:var(--ink);background:var(--bg);line-height:1.65}
header{display:flex;align-items:center;justify-content:space-between;padding:18px 5%;border-bottom:1px solid var(--line);background:var(--surface)}
.logo{font-size:24px;font-weight:900;letter-spacing:-1px;color:var(--ink);text-decoration:none}
.back{color:var(--ink);text-decoration:none;font-weight:600}
main{max-width:780px;margin:0 auto;padding:40px 20px 60px}
h1{font-size:34px;line-height:1.2;margin:0 0 22px;letter-spacing:-1px}
h2{font-size:20px;margin:30px 0 8px}
p,li{color:var(--ink)}li{margin:6px 0}
a{color:var(--btn)}
ul{padding-left:22px}
footer{background:var(--btn);color:var(--btn-text);padding:28px 5%;text-align:center}
footer a{color:var(--btn-text);opacity:.85;margin:0 10px;text-decoration:none;white-space:nowrap;display:inline-block;line-height:2}
footer a:hover{opacity:1;text-decoration:underline}
</style></head><body>
<header><a class="logo" href="/">%%STORE%%</a><a class="back" href="/">&larr; Back to store</a></header>
<main><h1>%%TITLE%%</h1>%%BODY%%</main>
<footer>%%NAV%%</footer>
</body></html>"""


def render_policy_page(s, slug, title, body):
    t = theme_vars(s)
    css = (f"--btn:{t['btn']};--btn-text:{t['btnText']};--bg:{t['bg']};--surface:{t['surface']};--ink:{t['ink']};"
           f"--muted:{t['muted']};--line:{t['line']};--soft:{t['soft']};--font:{t['font']}")
    nav = "".join(f'<a href="/policy/{sl}">{escape(tt)}</a>' for sl, tt in POLICY_PAGES)
    html = POLICY_TEMPLATE
    for key, value in (("%%TITLE%%", str(escape(title))), ("%%STORE%%", _p(s, "storeName", "Store")),
                       ("%%VARS%%", css), ("%%BODY%%", body), ("%%NAV%%", nav)):
        html = html.replace(key, value)
    return html


@app.get("/policy/<slug>")
def policy_page(slug):
    s = settings_dict()
    pages = build_policy_pages(s)
    if slug not in pages:
        abort(404)
    title = dict(POLICY_PAGES)[slug]
    return Response(render_policy_page(s, slug, title, pages[slug]), mimetype="text/html")


@app.get("/favicon.svg")
@app.get("/favicon.ico")
def favicon():
    s = settings_dict()
    t = theme_vars(s)
    letter = (_p(s, "storeName", "G") or "G")[:1].upper()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="{t["btn"]}"/>'
           f'<text x="32" y="45" font-size="38" font-weight="800" text-anchor="middle" font-family="Arial,sans-serif" fill="{t["btnText"]}">{letter}</text></svg>')
    resp = Response(svg, mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


LOGIN_FAILS = {}


def _login_blocked(ip):
    now = datetime.now(timezone.utc).timestamp()
    recent = [t for t in LOGIN_FAILS.get(ip, []) if now - t < 900]
    LOGIN_FAILS[ip] = recent
    if len(LOGIN_FAILS) > 5000:
        LOGIN_FAILS.clear()
    return len(recent) >= 8



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
    query = Product.query.order_by(Product.id.desc())
    if not is_admin():
        query = query.filter_by(active=True)
    return jsonify([{**product_dict(p), "id": str(p.id)} for p in query.all()])


@app.post("/api/admin/login")
def admin_login():
    ip = request.remote_addr or "unknown"
    if _login_blocked(ip):
        return jsonify({"error": "Too many failed attempts. Please wait 15 minutes and try again."}), 429
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    if not secrets.compare_digest(email, ADMIN_EMAIL) or not admin_password_ok(password):
        LOGIN_FAILS.setdefault(ip, []).append(datetime.now(timezone.utc).timestamp())
        return jsonify({"error": "Invalid email or password"}), 401
    LOGIN_FAILS.pop(ip, None)
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
    # ---------------------------------
    # Revenue filter
    # ---------------------------------
    period = request.args.get("period", "daily")

    try:
        year = int(request.args.get("year", datetime.now().year))
        month = int(request.args.get("month", datetime.now().month))
        day = int(request.args.get("day", datetime.now().day))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid date"}), 400

    # Validate year
    if year < 2000 or year > 2100:
        return jsonify({"error": "Invalid year"}), 400

    # ---------------------------------
    # Create revenue date range
    # ---------------------------------
    try:
        if period == "yearly":

            start_date = datetime(year, 1, 1)
            end_date = datetime(year + 1, 1, 1)

            revenue_label = f"Year {year}"

        elif period == "monthly":

            start_date = datetime(year, month, 1)

            if month == 12:
                end_date = datetime(year + 1, 1, 1)
            else:
                end_date = datetime(year, month + 1, 1)

            revenue_label = f"{month:02d}/{year}"

        elif period == "daily":

            start_date = datetime(year, month, day)
            end_date = start_date + timedelta(days=1)

            revenue_label = f"{day:02d}/{month:02d}/{year}"

        else:
            return jsonify({"error": "Invalid revenue period"}), 400

    except ValueError:
        return jsonify({"error": "Invalid date"}), 400

    # ---------------------------------
    # Calculate revenue
    # ---------------------------------
    revenue = db.session.query(
        db.func.coalesce(db.func.sum(Order.total), 0)
    ).filter(
        Order.payment_status == "paid",
        Order.created_at >= start_date,
        Order.created_at < end_date
    ).scalar() or 0

    # Number of paid orders for selected period
    paid_orders = db.session.query(
        db.func.count(Order.id)
    ).filter(
        Order.payment_status == "paid",
        Order.created_at >= start_date,
        Order.created_at < end_date
    ).scalar() or 0

    # ---------------------------------
    # Existing dashboard calculations
    # ---------------------------------
    active_products = Product.query.filter_by(active=True).count()

    order_count = Order.query.count()

    pending = Order.query.filter(
        Order.payment_status == "paid",
        Order.status.in_(["paid", "processing", "shipped"]),
    ).count()

    recent = Order.query.order_by(
        Order.created_at.desc()
    ).limit(10).all()

    return jsonify({
        "activeProducts": active_products,
        "orders": order_count,
        "pending": pending,

        # Selected-period revenue
        "revenue": float(revenue),
        "paidOrders": paid_orders,
        "revenueLabel": revenue_label,

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
        value = str(value)
        if key in THEME_COLOR_KEYS and value and not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            continue
        if key in BANNER_KEYS and value and not (len(split_images(value)) == 1 and valid_image_url(value)):
            continue
        if key in POLICY_KEYS:
            value = re.sub(r"[\r\n]+", " ", value).strip()[:300]
        if key == "themePreset" and value not in THEME_PRESETS:
            continue
        if key == "themeFont" and value not in THEME_FONTS:
            continue
        setting = db.session.get(Setting, key)
        if setting is None:
            setting = Setting(key=key, value=value)
            db.session.add(setting)
        else:
            setting.value = value
    db.session.commit()
    return jsonify(settings_dict())


def split_images(value):
    return [u for u in re.split(r"[,\s]+", value or "") if u]


def valid_image_url(value):
    if not value:
        return True
    try:
        urls = split_images(value)
        if not urls or len(urls) > 8 or len(value) > 4000:
            return False
        for u in urls:
            parsed = urlparse(u)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return False
        return True
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


TRACK_HITS = {}


def _digits(value):
    return re.sub(r"\D", "", str(value or ""))


@app.post("/api/orders/lookup")
def lookup_orders():
    ip = request.remote_addr or "unknown"
    now = datetime.now(timezone.utc).timestamp()
    if len(TRACK_HITS) > 5000:
        TRACK_HITS.clear()
    hits = [t for t in TRACK_HITS.get(ip, []) if now - t < 600]
    if len(hits) >= 10:
        return jsonify({"error": "Too many attempts. Please try again in a few minutes."}), 429
    hits.append(now)
    TRACK_HITS[ip] = hits

    data = request.get_json(silent=True) or {}
    phone = _digits(data.get("phone"))
    if len(phone) < 10:
        return jsonify({"error": "Please enter your 10-digit phone number."}), 400
    wanted = phone[-10:]
    recent = (
        Order.query.filter(Order.payment_status == "paid")
        .order_by(Order.id.desc())
        .limit(3000)
        .all()
    )
    mine = [o for o in recent if _digits(o.customer_phone)[-10:] == wanted][:100]
    return jsonify({
        "orders": [
            {
                "id": o.id,
                "status": o.status,
                "paymentStatus": o.payment_status,
                "total": float(o.total),
                "createdAt": o.created_at.isoformat() if o.created_at else None,
                "items": [
                    {"name": i.product_name, "price": float(i.unit_price), "quantity": i.quantity}
                    for i in o.items
                ],
            }
            for o in mine
        ]
    })


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
