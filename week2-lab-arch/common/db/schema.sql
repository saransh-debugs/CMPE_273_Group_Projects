CREATE TABLE IF NOT EXISTS inventory (
  item_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  quantity INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  qty INTEGER NOT NULL,
  user_id TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- Reservations (idempotency lives here: order_id PK)
CREATE TABLE IF NOT EXISTS reservations (
  order_id    TEXT PRIMARY KEY,
  item_id     TEXT NOT NULL,
  qty         INTEGER NOT NULL,
  reserved_at REAL NOT NULL,
  status      TEXT NOT NULL            -- reserved | failed
);

-- Notifications (optional; allow multiple notifications)
CREATE TABLE IF NOT EXISTS notifications (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT NOT NULL,
  user_id  TEXT NOT NULL,
  message  TEXT NOT NULL,
  sent_at  REAL NOT NULL
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_reservations_item_id ON reservations(item_id);
CREATE INDEX IF NOT EXISTS idx_notifications_order_id ON notifications(order_id);

-- Seed inventory (idempotent)
INSERT INTO inventory (item_id, name, quantity) VALUES
  ("burger", "Campus Burger", 20000),
  ("burrito", "Veg Burrito", 20000),
  ("salad", "Green Salad", 20000),
  ("pizza", "Cheese Pizza", 20000),
  ("fries", "Crispy Fries", 20000)
ON CONFLICT(item_id) DO UPDATE SET
  name=excluded.name,
  quantity=excluded.quantity;