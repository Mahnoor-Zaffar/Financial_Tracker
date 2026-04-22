import sqlite3

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Log in to continue."
login_manager.login_message_category = "warning"


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@event.listens_for(Session, "before_flush")
def _validate_transaction_invariants(session, flush_context, instances):
    from finance_tracker.models import Transaction
    from finance_tracker.services.transactions import validate_transaction_persistence

    for instance in session.new.union(session.dirty):
        if isinstance(instance, Transaction) and instance not in session.deleted:
            validate_transaction_persistence(instance)
