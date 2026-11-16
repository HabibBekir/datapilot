"""
datapilot.warehouse.seed — generate ShopFlow's synthetic warehouse.

Creates data/warehouse.db with 6 months of fake e-commerce data:
    customers(customer_id, name, email, country, signup_date)
    products(product_id, name, category, price)
    orders(order_id, customer_id, order_date, status, amount)
    order_items(order_id, product_id, quantity, unit_price)

Realistic problems are planted ON PURPOSE, so the agents have something to find:
    1. ~3% of customers have no country (NULL)
    2. 25 orders are duplicated (same order_id twice: a classic bad ETL re-run)
    3. 8 orders have a negative amount (refunds wrongly loaded as orders)
    4. A payment outage 2026-10-19 -> 2026-10-25: most orders that week "failed"

random.seed(42) -> everyone gets exactly the same data, so results are reproducible.

Run:  uv run python -m datapilot.warehouse.seed   (or: uv run datapilot seed)
"""
import random
import sqlite3
from datetime import date, timedelta

from datapilot import settings

START, END = date(2026, 5, 1), date(2026, 10, 31)
OUTAGE = (date(2026, 10, 19), date(2026, 10, 25))
COUNTRIES = ["France", "Germany", "Spain", "Italy", "Belgium", "Netherlands"]
CATALOG = {
    "Electronics": [("Wireless earbuds", 59.0), ("USB-C hub", 39.0), ("Smart watch", 149.0)],
    "Home": [("Coffee grinder", 45.0), ("Desk lamp", 29.0), ("Air purifier", 129.0)],
    "Sports": [("Yoga mat", 25.0), ("Running belt", 19.0), ("Dumbbell set", 89.0)],
    "Books": [("Data Engineering 101", 35.0), ("SQL Cookbook", 42.0), ("Python for Analysts", 38.0)],
}
FIRST = ["Lea", "Hugo", "Emma", "Lucas", "Mia", "Noah", "Ines", "Adam", "Sara", "Yanis",
         "Lina", "Omar", "Julia", "Max", "Nora", "Elias"]
LAST = ["Martin", "Bernard", "Muller", "Garcia", "Rossi", "Dubois", "Schmidt", "Lopez",
        "Peeters", "De Vries", "Moreau", "Ricci"]

SCHEMA = """
DROP TABLE IF EXISTS order_items; DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;    DROP TABLE IF EXISTS customers;
CREATE TABLE customers(customer_id INTEGER PRIMARY KEY, name TEXT, email TEXT,
                       country TEXT, signup_date TEXT);
CREATE TABLE products(product_id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL);
-- no PRIMARY KEY on orders: that's how duplicates can sneak in (problem #2)
CREATE TABLE orders(order_id INTEGER, customer_id INTEGER, order_date TEXT,
                    status TEXT, amount REAL);
CREATE TABLE order_items(order_id INTEGER, product_id INTEGER, quantity INTEGER, unit_price REAL);
"""


def days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def build(db_path=None) -> dict:
    db_path = db_path or settings.WAREHOUSE_DB
    rng = random.Random(42)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)

    # products
    products = []
    for category, items in CATALOG.items():
        for name, price in items:
            products.append((len(products) + 1, name, category, price))
    con.executemany("INSERT INTO products VALUES (?,?,?,?)", products)

    # customers (problem #1: some NULL countries)
    customers = []
    for cid in range(1, 801):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        country = None if rng.random() < 0.03 else rng.choice(COUNTRIES)
        signup = START - timedelta(days=rng.randint(0, 365))
        email = f"{first}.{last}{cid}@example.com".lower().replace(" ", "")
        customers.append((cid, f"{first} {last}", email, country, signup.isoformat()))
    con.executemany("INSERT INTO customers VALUES (?,?,?,?,?)", customers)

    # orders + items
    orders, items, oid = [], [], 0
    for d in days(START, END):
        weekend = d.weekday() >= 5
        n_orders = rng.randint(14, 22) + (6 if weekend else 0)
        for _ in range(n_orders):
            oid += 1
            in_outage = OUTAGE[0] <= d <= OUTAGE[1]
            # problem #4: during the outage ~75% of payments fail
            r = rng.random()
            if in_outage:
                status = "failed" if r < 0.75 else "paid"
            else:
                status = "paid" if r < 0.90 else ("refunded" if r < 0.95 else "failed")
            total = 0.0
            for _ in range(rng.randint(1, 3)):
                pid, _, _, price = rng.choice(products)
                qty = rng.randint(1, 2)
                items.append((oid, pid, qty, price))
                total += qty * price
            orders.append((oid, rng.randint(1, 800), d.isoformat(), status, round(total, 2)))

    # problem #3: refunds loaded as negative orders
    for o in rng.sample(range(len(orders)), 8):
        oid_, cid_, d_, _, amt = orders[o]
        orders[o] = (oid_, cid_, d_, "paid", -amt)
    # problem #2: duplicated rows (bad ETL re-run)
    orders += rng.sample(orders, 25)

    con.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", orders)
    con.executemany("INSERT INTO order_items VALUES (?,?,?,?)", items)
    con.commit()
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("customers", "products", "orders", "order_items")}
    con.close()
    return counts


if __name__ == "__main__":
    counts = build()
    print(f"Warehouse created at {settings.WAREHOUSE_DB}")
    for table, n in counts.items():
        print(f"  {table:<12} {n:>6} rows")