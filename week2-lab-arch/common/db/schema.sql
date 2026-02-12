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

CREATE TABLE IF NOT EXISTS reservations (
  order_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  qty INTEGER NOT NULL,
  reserved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
  order_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  message TEXT NOT NULL,
  sent_at TEXT NOT NULL
);

INSERT OR IGNORE INTO inventory (item_id, name, quantity) VALUES
  ("burger", "Campus Burger", 100),
  ("burrito", "Veg Burrito", 100),
  ("salad", "Green Salad", 100);
