CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'partner', 'customer')),
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'pending', 'suspended')),
    wallet_balance REAL DEFAULT 0.0,
    is_online BOOLEAN DEFAULT 0,
    current_area_id INTEGER,
    FOREIGN KEY (current_area_id) REFERENCES areas (id)
);

CREATE TABLE IF NOT EXISTS areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS charges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_area_id INTEGER NOT NULL,
    to_area_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    FOREIGN KEY (from_area_id) REFERENCES areas (id),
    FOREIGN KEY (to_area_id) REFERENCES areas (id)
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    partner_id INTEGER,
    pickup_area_id INTEGER NOT NULL,
    drop_area_id INTEGER NOT NULL,
    pickup_address TEXT NOT NULL,
    drop_address TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'accepted', 'picked_up', 'arrived', 'completed', 'cancelled')),
    amount REAL NOT NULL,
    commission REAL DEFAULT 0.0,
    rating INTEGER CHECK(rating BETWEEN 1 AND 5),
    rating_comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES users (id),
    FOREIGN KEY (partner_id) REFERENCES users (id),
    FOREIGN KEY (pickup_area_id) REFERENCES areas (id),
    FOREIGN KEY (drop_area_id) REFERENCES areas (id)
);
