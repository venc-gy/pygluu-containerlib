"""This module contains various helpers related to SQL persistence."""

import contextlib
import logging
import os
import re
import warnings
from collections import defaultdict

from sqlalchemy import create_engine
from sqlalchemy import MetaData
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.exc import SAWarning
from ldap3.utils import dn as dnutils

from pygluu.containerlib.utils import encode_text

logger = logging.getLogger(__name__)

SERVER_VERSION_RE = re.compile(r"\d+(.\d+)+")


def get_sql_password() -> str:
    """Get password used for SQL database user.

    :returns: Plaintext password.
    """
    password_file = os.environ.get("GLUU_SQL_PASSWORD_FILE", "/etc/gluu/conf/sql_password")

    password = ""  # nosec: B105
    with contextlib.suppress(FileNotFoundError):
        with open(password_file) as f:
            password = f.read().strip()
    return password


class SQLClient:
    """Base class for SQL client adapter."""

    def __init__(self):
        self._metadata = None
        self._engine = None

        dialect = os.environ.get("GLUU_SQL_DB_DIALECT", "mysql")
        if dialect in ("pgsql", "postgresql"):
            self.adapter = PostgresqlAdapter()
        elif dialect == "mysql":
            self.adapter = MysqlAdapter()

    @property
    def engine(self):
        """Lazy init of engine instance object."""
        if not self._engine:
            self._engine = create_engine(self.engine_url, pool_pre_ping=True, hide_parameters=True)
        return self._engine

    @property
    def engine_url(self) -> str:
        """Engine connection URL."""
        host = os.environ.get("GLUU_SQL_DB_HOST", "localhost")
        port = os.environ.get("GLUU_SQL_DB_PORT", 3306)
        database = os.environ.get("GLUU_SQL_DB_NAME", "gluu")
        user = os.environ.get("GLUU_SQL_DB_USER", "gluu")
        password = get_sql_password()
        return f"{self.adapter.connector}://{user}:{password}@{host}:{port}/{database}"

    @property
    def metadata(self):
        """Lazy init of metadata."""
        with warnings.catch_warnings():
            # postgresql driver will show warnings about unsupported reflection
            # on expression-based index, i.e. `lower(uid::text)`; but we don't
            # want to clutter the logs with these warnings, hence we suppress the
            # warnings
            warnings.filterwarnings(
                "ignore",
                message="Skipped unsupported reflection of expression-based index",
                category=SAWarning,
            )

            if not self._metadata:
                # do reflection on database table
                self._metadata = MetaData(bind=self.engine)
                self._metadata.reflect()
            return self._metadata

    @property
    def dialect(self) -> str:
        """Dialect name."""
        return self.adapter.dialect

    def connected(self) -> bool:
        """Check whether connection is alive by executing simple query."""
        with self.engine.connect() as conn:
            result = conn.execute("SELECT 1 AS is_alive")
            return result.fetchone()[0] > 0

    def get_table_mapping(self) -> dict:
        """Get mapping of column name and type from all tables."""
        table_mapping = defaultdict(dict)
        for table_name, table in self.metadata.tables.items():
            for column in table.c:
                if getattr(column.type, "collation", None):
                    column.type.collation = None
                table_mapping[table_name][column.name] = str(column.type)
        return dict(table_mapping)

    def row_exists(self, table_name, id_) -> bool:
        """Check whether a row is exist."""
        table = self.metadata.tables.get(table_name)
        if table is None:
            return False

        query = select([func.count()]).select_from(table).where(
            table.c.doc_id == id_
        )
        with self.engine.connect() as conn:
            result = conn.execute(query)
            return result.fetchone()[0] > 0

    def quoted_id(self, identifier):
        """Get quoted identifier name."""
        return f"{self.adapter.quote_char}{identifier}{self.adapter.quote_char}"

    def create_table(self, table_name: str, column_mapping: dict, pk_column: str):
        """Create table with its columns."""
        columns = []
        for column_name, column_type in column_mapping.items():
            column_def = f"{self.quoted_id(column_name)} {column_type}"

            if column_name == pk_column:
                column_def += " NOT NULL UNIQUE"
            columns.append(column_def)

        columns_fmt = ", ".join(columns)
        pk_def = f"PRIMARY KEY ({self.quoted_id(pk_column)})"
        query = f"CREATE TABLE {self.quoted_id(table_name)} ({columns_fmt}, {pk_def})"

        with self.engine.connect() as conn:
            try:
                conn.execute(query)
                # refresh metadata as we have newly created table
                self.metadata.reflect()
            except Exception as exc:  # noqa: B902
                self.adapter.on_create_table_error(exc)

    def create_index(self, query):
        """Create index using raw query."""
        with self.engine.connect() as conn:
            try:
                conn.execute(query)
            except Exception as exc:  # noqa: B902
                self.adapter.on_create_index_error(exc)

    def insert_into(self, table_name, column_mapping):
        """Insert a row into a table."""
        table = self.metadata.tables.get(table_name)

        for column in table.c:
            unmapped = column.name not in column_mapping

            if self.dialect == "mysql":
                json_type = "json"
                json_default_values = {"v": []}
            else:
                json_type = "jsonb"
                json_default_values = []

            is_json = bool(column.type.__class__.__name__.lower() == json_type)

            if not all([unmapped, is_json]):
                continue
            column_mapping[column.name] = json_default_values

        query = table.insert().values(column_mapping)
        with self.engine.connect() as conn:
            try:
                conn.execute(query)
            except Exception as exc:  # noqa: B902
                self.adapter.on_insert_into_error(exc)

    def get(self, table_name, id_, column_names=None) -> dict:
        """Get a row from a table with matching ID."""
        table = self.metadata.tables.get(table_name)

        attrs = column_names or []
        if attrs:
            cols = [table.c[attr] for attr in attrs]
        else:
            cols = [table]

        query = select(cols).select_from(table).where(
            table.c.doc_id == id_
        )
        with self.engine.connect() as conn:
            result = conn.execute(query)
            entry = result.fetchone()

        if not entry:
            return {}
        return dict(entry)

    def update(self, table_name, id_, column_mapping) -> bool:
        """Update a table row with matching ID."""
        table = self.metadata.tables.get(table_name)

        query = table.update().where(table.c.doc_id == id_).values(column_mapping)
        with self.engine.connect() as conn:
            result = conn.execute(query)
        return bool(result.rowcount)

    def search(self, table_name, column_names=None) -> dict:
        """Get a row from a table with matching ID."""
        table = self.metadata.tables.get(table_name)

        attrs = column_names or []
        if attrs:
            cols = [table.c[attr] for attr in attrs]
        else:
            cols = [table]

        query = select(cols).select_from(table)
        with self.engine.connect() as conn:
            result = conn.execute(query)
            for entry in result:
                yield dict(entry)

    @property
    def server_version(self):
        """Display server version."""
        return self.engine.scalar(self.adapter.server_version_query)

    def get_server_version(self):
        """Get server version as tuple."""
        # major and minor format
        version = [0, 0]

        pattern = SERVER_VERSION_RE.search(self.server_version)
        if pattern:
            version = [int(comp) for comp in pattern.group().split(".")]
        return tuple(version)


class PostgresqlAdapter:
    """Class for PostgreSQL adapter."""

    @property
    def dialect(self):
        """Dialect name."""
        return "pgsql"

    @property
    def connector(self):
        """Connector name."""
        return "postgresql+psycopg2"

    @property
    def quote_char(self):
        """Character used for quoting identifier."""
        return '"'

    def on_create_table_error(self, exc):
        """Handle table creation error.

        :param exc: Exception instance.
        """
        # errors other than code listed below will be raised
        # - 42P07: relation exists
        if exc.orig.pgcode not in ["42P07"]:
            raise exc

    def on_create_index_error(self, exc):
        """Handle index creation error.

        :param exc: Exception instance.
        """
        # errors other than code listed below will be raised
        # - 42P07: relation exists
        if exc.orig.pgcode not in ["42P07"]:
            raise exc

    def on_insert_into_error(self, exc):
        """Handle row insertion error.

        :param exc: Exception instance.
        """
        # errors other than code listed below will be raised
        # - 23505: unique violation
        if exc.orig.pgcode not in ["23505"]:
            raise exc

    @property
    def server_version(self):
        """Query string to display server version."""
        return "SHOW server_version"


class MysqlAdapter:
    """Class for MySQL adapter."""

    @property
    def dialect(self):
        """Dialect name."""
        return "mysql"

    @property
    def connector(self):
        """Connector name."""
        return "mysql+pymysql"

    @property
    def quote_char(self):
        """Character used for quoting identifier."""
        return "`"

    def on_create_table_error(self, exc):
        """Handle table creation error.

        :param exc: Exception instance.
        """
        # errors other than code listed below will be raised
        # - 1050: table exists
        if exc.orig.args[0] not in [1050]:
            raise exc

    def on_create_index_error(self, exc):
        """Handle index creation error.

        :param exc: Exception instance.
        """
        # errors other than code listed below will be raised
        # - 1061: duplicate key name (index)
        if exc.orig.args[0] not in [1061]:
            raise exc

    def on_insert_into_error(self, exc):
        """Handle row insertion error.

        :param exc: Exception instance.
        """
        # errors other than code listed below will be raised
        # - 1062: duplicate entry
        if exc.orig.args[0] not in [1062]:
            raise exc

    @property
    def server_version_query(self):
        """Query string to display server version."""
        return "SELECT VERSION()"


def render_sql_properties(manager, src: str, dest: str) -> None:
    """Render file contains properties to connect to SQL database server.

    :param manager: An instance of :class:`~pygluu.containerlib.manager._Manager`.
    :param src: Absolute path to the template.
    :param dest: Absolute path where generated file is located.
    """
    with open(src) as f:
        txt = f.read()

    with open(dest, "w") as f:
        db_dialect = os.environ.get("GLUU_SQL_DB_DIALECT", "mysql")
        db_name = os.environ.get("GLUU_SQL_DB_NAME", "gluu")

        # In MySQL, physically, a schema is synonymous with a database
        if db_dialect == "mysql":
            default_schema = db_name
        else:  # likely postgres
            # by default, PostgreSQL creates schema called `public` upon database creation
            default_schema = "public"
        db_schema = os.environ.get("GLUU_SQL_DB_SCHEMA", "") or default_schema

        rendered_txt = txt % {
            "rdbm_db": db_name,
            "rdbm_schema": db_schema,
            "rdbm_type": "postgresql" if db_dialect == "pgsql" else "mysql",
            "rdbm_host": os.environ.get("GLUU_SQL_DB_HOST", "localhost"),
            "rdbm_port": os.environ.get("GLUU_SQL_DB_PORT", 3306),
            "rdbm_user": os.environ.get("GLUU_SQL_DB_USER", "gluu"),
            "rdbm_password_enc": encode_text(
                get_sql_password(),
                manager.secret.get("encoded_salt"),
            ).decode(),
            "server_time_zone": os.environ.get("GLUU_SQL_DB_TIMEZONE", "UTC"),
        }
        f.write(rendered_txt)


def doc_id_from_dn(dn: str) -> str:
    """Resolve row ID from an LDAP DN.

    :param dn: LDAP DN string.
    """
    parsed_dn = dnutils.parse_dn(dn)
    doc_id = parsed_dn[0][1]

    if doc_id == "gluu":
        doc_id = "_"
    return doc_id
