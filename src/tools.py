"""LangChain tools used by the shopping agent."""

import os
import sqlite3

from langchain_core.tools import tool

from reviews_api import get_ratings_for_products
from setup_db import DB_PATH, create_database


def _ensure_db() -> None:
    if not os.path.exists(DB_PATH):
        create_database()


@tool
def search_products(
    keyword: str = "",
    category: str = "",
    max_price: float | None = None,
    min_price: float | None = None,
    organic_only: bool = False,
    min_rating: float | None = None,
) -> str:
    """Search the product catalog.

    Args:
        keyword: Matched against product name, description and category (e.g. "honey"). Optional.
        category: One of honey, oil, nuts, seeds, grains, tea, coffee, snacks, dairy-alt. Optional.
        max_price: Maximum price in USD (inclusive).
        min_price: Minimum price in USD (inclusive).
        organic_only: True to return only organic products.
        min_rating: Minimum average customer rating (0-5, inclusive).

    Returns products sorted by rating (highest first), each with id, name, category,
    price, description, organic flag, average rating and review count.
    """
    _ensure_db()
    sql = "SELECT id, name, category, price, description, is_organic FROM products WHERE 1=1"
    params: list = []
    if keyword:
        sql += " AND (name LIKE ? OR description LIKE ? OR category LIKE ?)"
        params += [f"%{keyword}%"] * 3
    if category:
        sql += " AND category = ?"
        params.append(category.lower())
    if max_price is not None:
        sql += " AND price <= ?"
        params.append(max_price)
    if min_price is not None:
        sql += " AND price >= ?"
        params.append(min_price)
    if organic_only:
        sql += " AND is_organic = 1"

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    ratings = {r["product_id"]: r for r in get_ratings_for_products([r[0] for r in rows])}
    items = []
    for pid, name, cat, price, desc, organic in rows:
        rating = ratings[pid]["average_rating"]
        if min_rating is not None and rating < min_rating:
            continue
        items.append((rating, pid, name, cat, price, desc, organic, ratings[pid]["review_count"]))
    items.sort(reverse=True)

    lines = [
        f"ID {pid}: {name} | ${price:.2f} | {rating} stars ({count} reviews) "
        f"| {'organic' if organic else 'non-organic'} | {cat} | {desc}"
        for rating, pid, name, cat, price, desc, organic, count in items
    ]
    return "\n".join(lines) if lines else "No products matched."


@tool
def place_order(product_id: int) -> str:
    """Place an order for a single product by its ID (prototype: just records the order)."""
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT name, price FROM products WHERE id = ?", (product_id,)).fetchone()
    if not row:
        conn.close()
        return f"Product {product_id} not found."
    cur = conn.execute(
        "INSERT INTO orders (product_id, product_name, price) VALUES (?, ?, ?)",
        (product_id, row[0], row[1]),
    )
    conn.commit()
    order_id = cur.lastrowid
    conn.close()
    return f"Order #{order_id} placed: {row[0]} (product {product_id}) for ${row[1]:.2f}."


@tool
def list_orders() -> str:
    """List all orders recorded in the database (most recent first), with a total."""
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, product_id, product_name, price, ordered_at FROM orders ORDER BY id DESC"
    ).fetchall()
    conn.close()
    if not rows:
        return "No orders have been placed yet."
    lines = [f"Order #{i}: {n} (product {p}) | ${pr:.2f} | {t}" for i, p, n, pr, t in rows]
    total = sum(r[3] for r in rows)
    return "\n".join(lines) + f"\nTotal: {len(rows)} orders, ${total:.2f}"
