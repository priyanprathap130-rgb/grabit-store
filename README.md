# GRABIT — Production Ecommerce Foundation

A production-oriented Flask ecommerce application for **Render + PostgreSQL + Razorpay**.

## What this build does

- Flask served by Gunicorn in production.
- Render Blueprint for a paid web service and managed PostgreSQL.
- SQLAlchemy + Flask-Migrate database migrations.
- PostgreSQL connection pooling/pre-ping.
- Server-side pricing: customers cannot submit their own product prices.
- Row locking and stock reservation at checkout to reduce overselling.
- 30-minute stock reservation expiry.
- Razorpay Orders API created server-side.
- Razorpay checkout signature verification.
- Backend fetch of the Razorpay payment and checks for order ID, amount and `captured` status before marking an order paid.
- Razorpay webhook HMAC verification and event-id deduplication.
- Admin login with a password hash, secure session cookie settings and CSRF protection for admin mutations.
- Product, stock, order and store-setting management.
- `/health` endpoint for Render.
- Local SQLite auto-initialization for beginner-friendly PyCharm development.
- Production does **not** use the local filesystem as the database.
- Product images are stored as validated HTTPS/HTTP URLs, avoiding ephemeral Render upload storage.
- Basic security response headers.

## Local Windows / PyCharm

1. Create/select a project virtual environment.
2. Install dependencies:
   `python -m pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and set local values.
4. Start:
   `python app.py`
5. Store: `http://127.0.0.1:5000`
6. Admin: `http://127.0.0.1:5000/admin`

The local SQLite schema is automatically created when `AUTO_INIT_LOCAL_DB=1`.

## Render deployment

The included `render.yaml` provisions:

- Web service: `1c-2g` paid plan.
- PostgreSQL: `0.5c-1g` paid plan.
- Database migrations before each deploy.
- Generated application secret.
- Database connection from Render Postgres.

Render build command:
`pip install -r requirements.txt`

Render pre-deploy command:
`flask db upgrade && flask seed-defaults`

Render start command:
`gunicorn --workers 2 --threads 2 --timeout 120 app:app`

## Required production secrets

Set these in Render and never commit them to GitHub:

- `ADMIN_EMAIL`
- `ADMIN_PASSWORD_HASH`
- `RAZORPAY_KEY_ID`
- `RAZORPAY_KEY_SECRET`
- `RAZORPAY_WEBHOOK_SECRET`

Generate the admin hash locally:

`python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('YOUR-STRONG-PASSWORD'))"`

Use Razorpay **Test Mode** keys first. Switch to Live Mode only after the complete checkout, capture and webhook flow has been tested.

## Razorpay webhook

After deployment, configure a Razorpay webhook to:

`https://YOUR-DOMAIN/api/razorpay/webhook`

Use the same webhook secret in `RAZORPAY_WEBHOOK_SECRET`. Subscribe to `payment.captured` and `payment.failed`.

## Important production/business work still required

This is a production-oriented software foundation, not a guarantee of legal, tax, operational or business compliance. Before taking real orders, configure and test:

- Business/legal identity, GST/tax treatment and invoices as applicable to the business.
- Shipping zones, delivery charges, returns/refunds, cancellation and warranty policies.
- Privacy policy, terms of service and customer support/contact details.
- Razorpay KYC, bank settlement and Live Mode configuration.
- Automated email/SMS/WhatsApp order notifications if required.
- Persistent image storage/CDN if the business needs product uploads instead of image URLs.
- Backups and recovery plan for PostgreSQL.
- Monitoring and error alerting.
- End-to-end payment tests in Razorpay Test Mode.

**Do not use Render Free resources for the live store.** Render documents Free resources as limited/testing-oriented; the Blueprint in this package uses paid production plans.
