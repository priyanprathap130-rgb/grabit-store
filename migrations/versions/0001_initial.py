"""Initial GRABIT schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("compare_at_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("image", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_name", sa.String(length=180), nullable=False),
        sa.Column("customer_email", sa.String(length=180), nullable=True),
        sa.Column("customer_phone", sa.String(length=40), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("payment_status", sa.String(length=30), nullable=False),
        sa.Column("razorpay_order_id", sa.String(length=80), nullable=True),
        sa.Column("razorpay_payment_id", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("reservation_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stock_reserved", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("razorpay_order_id", name="uq_orders_razorpay_order_id"),
        sa.UniqueConstraint("razorpay_payment_id", name="uq_orders_razorpay_payment_id"),
    )
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(length=180), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("event_id", name="uq_payment_events_event_id"),
    )
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )
    op.create_index("ix_products_active", "products", ["active"])
    op.create_index("ix_orders_payment_status", "orders", ["payment_status"])
    op.create_index("ix_orders_created_at", "orders", ["created_at"])


def downgrade():
    op.drop_index("ix_orders_created_at", table_name="orders")
    op.drop_index("ix_orders_payment_status", table_name="orders")
    op.drop_index("ix_products_active", table_name="products")
    op.drop_table("settings")
    op.drop_table("payment_events")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("products")
