"""Data-layer client placeholder.

The zero-secrets demo is backed entirely by the in-memory repository in
``app.store``. Real PostgreSQL(+pgvector) / Neo4j / Redis / MinIO clients land
in milestone M1+ and will live in this package; ``docker-compose`` provisions
them. The application must NOT require any of these to boot or to serve a full
conversation loop (see CONTRACT.md §0).
"""
