from sqlmodel import SQLModel, create_engine, Session
from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)

def init_db():
    from .models import models  # noqa: F401 (imports to register models)
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
