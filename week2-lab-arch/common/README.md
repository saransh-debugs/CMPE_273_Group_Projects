# Common assets

This folder contains shared utilities and the shared SQLite database.

- db/schema.sql defines the schema and seed data.
- db/shared.db is a repo-tracked SQLite database used by all parts.
- db.py provides helpers for opening the database with WAL enabled.
- ids.py provides ID helpers for orders.

SQLite is committed so group members can pull both code and data.
