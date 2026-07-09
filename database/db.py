import json
import random
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "cafeteria.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tools_used TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                stock REAL NOT NULL DEFAULT 0,
                price REAL NOT NULL DEFAULT 0,
                min_stock REAL NOT NULL DEFAULT 5
            );

            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                quantity REAL NOT NULL,
                total REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                concept TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                customer_name TEXT,
                delivery_type TEXT NOT NULL,
                address TEXT,
                latitude REAL,
                longitude REAL,
                items_json TEXT NOT NULL,
                subtotal REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );

            CREATE TABLE IF NOT EXISTS conversation_state (
                conversation_id TEXT PRIMARY KEY,
                current_state TEXT NOT NULL DEFAULT 'IDLE',
                cart_json TEXT DEFAULT '[]',
                collected_data_json TEXT DEFAULT '{}',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );
        """)

        count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if count == 0:
            seed_products = [
                ("Café molido", float(random.randint(5, 30)), 120.0, 10.0),
                ("Leche entera", float(random.randint(5, 30)), 35.0, 8.0),
                ("Azúcar", float(random.randint(5, 30)), 25.0, 5.0),
                ("Vasos desechables", float(random.randint(5, 30)), 0.50, 5.0),
                ("Croissant", float(random.randint(5, 30)), 15.0, 10.0),
                ("Muffin", float(random.randint(5, 30)), 18.0, 8.0),
                ("Té verde", float(random.randint(5, 30)), 45.0, 5.0),
                ("Chocolate caliente", float(random.randint(5, 30)), 55.0, 5.0),
            ]
            conn.executemany(
                "INSERT INTO products (name, stock, price, min_stock) VALUES (?, ?, ?, ?)",
                seed_products,
            )

        _migrate_messages_tools_used(conn)
        _migrate_conversations_order_state(conn)
        _migrate_orders_v2(conn)
        _migrate_conversation_state_table(conn)
        _migrate_products_menu_visible(conn)
        _migrate_products_temperature_and_category(conn)
        _seed_menu_products(conn)
        _migrate_state_from_conversations(conn)
        _migrate_auth(conn)
        _cap_stock_max_30(conn)


def _migrate_auth(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS user_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)

    for table in ("conversations", "orders"):
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if columns and "user_id" not in columns:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id)"
            )

    from services.auth_service import _hash_password

    seeds = [
        ("admin", "admin123", "Administrador", "ADMIN"),
        ("cliente", "cliente123", "Cliente Demo", "CUSTOMER"),
    ]
    for username, password, full_name, role in seeds:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not exists:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, full_name, role)
                VALUES (?, ?, ?, ?)
                """,
                (username, _hash_password(password), full_name, role),
            )


def _migrate_orders_v2(conn: sqlite3.Connection):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(orders)").fetchall()}
    if not columns:
        return

    # Esquema legacy: columna "items" NOT NULL coexistiendo con "items_json"
    if "items" in columns:
        _rebuild_orders_table(conn)
        return

    migrations = {
        "customer_name": "TEXT",
        "latitude": "REAL",
        "longitude": "REAL",
        "items_json": "TEXT",
        "subtotal": "REAL DEFAULT 0",
    }
    for col, definition in migrations.items():
        if col not in columns:
            conn.execute(f"ALTER TABLE orders ADD COLUMN {col} {definition}")


def _rebuild_orders_table(conn: sqlite3.Connection):
    """Migra esquema legacy (items NOT NULL) → esquema unificado (items_json NOT NULL)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            customer_name TEXT,
            delivery_type TEXT NOT NULL,
            address TEXT,
            latitude REAL,
            longitude REAL,
            items_json TEXT NOT NULL,
            subtotal REAL NOT NULL DEFAULT 0,
            total REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        )
    """)

    rows = conn.execute("SELECT * FROM orders").fetchall()
    for row in rows:
        r = dict(row)
        items_json = r.get("items_json") or r.get("items") or "[]"
        address = r.get("address") or r.get("location")
        status = r.get("status") or "PENDING"
        if status == "completed":
            status = "CONFIRMED"
        subtotal = r.get("subtotal")
        if subtotal is None:
            try:
                items = json.loads(items_json)
                subtotal = sum(
                    i.get("subtotal", i.get("precio", 0) * i.get("cantidad", 1))
                    for i in items
                )
            except (json.JSONDecodeError, TypeError):
                subtotal = r.get("total") or 0

        conn.execute(
            """
            INSERT INTO orders_new (
                id, conversation_id, customer_name, delivery_type, address,
                latitude, longitude, items_json, subtotal, total, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r["id"],
                r["conversation_id"],
                r.get("customer_name"),
                r["delivery_type"],
                address,
                r.get("latitude"),
                r.get("longitude"),
                items_json,
                subtotal,
                r["total"],
                status,
                r.get("created_at"),
            ),
        )

    conn.execute("DROP TABLE orders")
    conn.execute("ALTER TABLE orders_new RENAME TO orders")


def _migrate_conversation_state_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_state (
            conversation_id TEXT PRIMARY KEY,
            current_state TEXT NOT NULL DEFAULT 'IDLE',
            cart_json TEXT DEFAULT '[]',
            collected_data_json TEXT DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        )
    """)


def _migrate_state_from_conversations(conn: sqlite3.Connection):
    """Migra estado legacy de conversations → conversation_state."""
    conv_columns = {row[1] for row in conn.execute("PRAGMA table_info(conversations)").fetchall()}
    if "state" not in conv_columns:
        return

    rows = conn.execute("""
        SELECT id, state, cart_data, delivery_type, delivery_address, delivery_location
        FROM conversations
    """).fetchall()

    for row in rows:
        exists = conn.execute(
            "SELECT 1 FROM conversation_state WHERE conversation_id = ?",
            (row["id"],),
        ).fetchone()
        if exists:
            continue

        collected = {}
        if row["delivery_type"]:
            collected["delivery_type"] = row["delivery_type"]
        if row["delivery_address"]:
            collected["address"] = row["delivery_address"]
        if row["delivery_location"]:
            collected["location_text"] = row["delivery_location"]

        conn.execute(
            """
            INSERT INTO conversation_state (conversation_id, current_state, cart_json, collected_data_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                row["id"],
                row["state"] or "IDLE",
                row["cart_data"] or "[]",
                json.dumps(collected, ensure_ascii=False),
            ),
        )

    all_convs = conn.execute("SELECT id FROM conversations").fetchall()
    for row in all_convs:
        exists = conn.execute(
            "SELECT 1 FROM conversation_state WHERE conversation_id = ?",
            (row["id"],),
        ).fetchone()
        if not exists:
            conn.execute(
                """
                INSERT INTO conversation_state (conversation_id, current_state, cart_json, collected_data_json)
                VALUES (?, 'IDLE', '[]', '{}')
                """,
                (row["id"],),
            )


def _migrate_products_menu_visible(conn: sqlite3.Connection):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(products)").fetchall()}
    if "menu_visible" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN menu_visible INTEGER NOT NULL DEFAULT 1")
        conn.execute(
            """
            UPDATE products SET menu_visible = 0
            WHERE name IN ('Azúcar', 'Café molido', 'Leche entera', 'Vasos desechables')
            """
        )


def _migrate_products_temperature_and_category(conn: sqlite3.Connection):
    """Agrega columnas `temperature` y `category` a products y actualiza valores por defecto."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(products)").fetchall()}
    if "temperature" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN temperature TEXT NOT NULL DEFAULT 'AMBIENTE'")
    if "category" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN category TEXT NOT NULL DEFAULT 'BEBIDA'")

    # Actualizar temperaturas conocidas según reglas de negocio
    # Productos fríos
    conn.execute("UPDATE products SET temperature = 'FRIA' WHERE LOWER(name) LIKE '%frappe%'")
    conn.execute("UPDATE products SET temperature = 'FRIA' WHERE LOWER(name) LIKE '%té verde%' OR LOWER(name) LIKE '%te verde%'")
    # Productos calientes
    conn.execute("UPDATE products SET temperature = 'CALIENTE' WHERE LOWER(name) LIKE '%café americano%' OR LOWER(name) LIKE '%cafe americano%'")
    conn.execute("UPDATE products SET temperature = 'CALIENTE' WHERE LOWER(name) LIKE '%capuchino%'")
    conn.execute("UPDATE products SET temperature = 'CALIENTE' WHERE LOWER(name) LIKE '%chocolate caliente%'")
    # Alimentos calientes
    conn.execute("UPDATE products SET temperature = 'CALIENTE', category = 'ALIMENTO' WHERE LOWER(name) LIKE '%crepa%'")
    conn.execute("UPDATE products SET temperature = 'CALIENTE', category = 'ALIMENTO' WHERE LOWER(name) LIKE '%croissant%'")
    # Ambiente
    conn.execute("UPDATE products SET temperature = 'AMBIENTE' WHERE LOWER(name) LIKE '%muffin%'")



def _migrate_conversations_order_state(conn: sqlite3.Connection):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(conversations)").fetchall()}
    migrations = {
        "state": "TEXT NOT NULL DEFAULT 'IDLE'",
        "cart_data": "TEXT",
        "delivery_type": "TEXT",
        "delivery_address": "TEXT",
        "delivery_location": "TEXT",
    }
    for col, definition in migrations.items():
        if col not in columns:
            conn.execute(f"ALTER TABLE conversations ADD COLUMN {col} {definition}")


def _seed_menu_products(conn: sqlite3.Connection):
    menu_products = [
        ("Frappe de oreo", float(random.randint(5, 30)), 65.0, 10.0),
        ("Frappe de caramelo", float(random.randint(5, 30)), 60.0, 10.0),
        ("Crepa de nutella", float(random.randint(5, 30)), 55.0, 8.0),
        ("Crepa de queso", float(random.randint(5, 30)), 50.0, 8.0),
        ("Café americano", float(random.randint(5, 30)), 35.0, 10.0),
        ("Capuchino", float(random.randint(5, 30)), 45.0, 10.0),
    ]
    for product in menu_products:
        conn.execute(
            """
            INSERT OR IGNORE INTO products (name, stock, price, min_stock)
            VALUES (?, ?, ?, ?)
            """,
            product,
        )


def _migrate_messages_tools_used(conn: sqlite3.Connection):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
    if "tools_used" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN tools_used TEXT")


def _cap_stock_max_30(conn: sqlite3.Connection):
    """Limita el stock máximo a 30 unidades por producto.
    Si un producto tiene más de 30, se le asigna un valor aleatorio entre 5 y 30."""
    rows = conn.execute("SELECT id, stock FROM products WHERE stock > 30").fetchall()
    for row in rows:
        new_stock = float(random.randint(5, 30))
        conn.execute("UPDATE products SET stock = ? WHERE id = ?", (new_stock, row["id"]))
