from __future__ import annotations

from datetime import date

from sqlmodel import SQLModel, Session, create_engine, select

from apps.api.audit import AuditActor, use_actor
from apps.api.models.models import AuditAction, AuditLog, Organization, User, Price, Rate, TaxRule
from apps.api.security import get_password_hash
from apps.api.services.fx_service import BaseFXProvider, FXService
from apps.api.services.ledger_service import LedgerService
from apps.api.services.market_service import BaseMarketProvider, MarketService
from apps.api.services.tax_service import BaseTaxProvider, TaxService


def _create_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine, expire_on_commit=False)


def _seed_actor(session: Session) -> AuditActor:
    org = Organization(name="Test Org")
    session.add(org)
    session.commit()
    session.refresh(org)

    user = User(
        email="test@example.com",
        name="Tester",
        organization_id=org.id,
        password_hash=get_password_hash("secret"),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    return AuditActor(
        request_id="test-request",
        user_id=user.id,
        organization_id=org.id,
        source="tests",
        user_label=user.email,
    )


class _StubFXProvider(BaseFXProvider):
    name = "stubfx"

    def sync_daily_rates(self, base: str = "USD", date_: date | None = None):
        yield Rate(base=base, quote="EUR", date=date(2024, 1, 1), value=1.1, provider=self.name)


class _StubMarketProvider(BaseMarketProvider):
    name = "stubmarket"

    def fetch_prices(self, symbol: str, start: date, end: date):
        yield Price(date=start, close=101.5, provider=self.name)


class _StubTaxProvider(BaseTaxProvider):
    name = "stubtax"

    def upsert_rules(self):
        yield TaxRule(jurisdiction="US-FED", scope="vat", expression="rate * 0.2")


def test_ledger_post_transaction_creates_audit_entry() -> None:
    with _create_session() as session:
        actor = _seed_actor(session)
        with use_actor(actor):
            ledger = LedgerService(session)
            cash = ledger.create_account(name="Cash", type="ASSET", code="1000")
            revenue = ledger.create_account(name="Revenue", type="REVENUE", code="4000")
            ledger.post_transaction(
                date=date(2024, 1, 1),
                description="Sale",
                postings=[
                    {"account_id": cash.id, "debit": 150.0, "credit": 0.0},
                    {"account_id": revenue.id, "debit": 0.0, "credit": 150.0},
                ],
            )

        stmt = select(AuditLog).where(AuditLog.entity_name == "Transaction").order_by(AuditLog.ts.desc())
        log = session.exec(stmt).first()
        assert log is not None
        assert log.action == AuditAction.CREATE
        assert log.actor_user_id == actor.user_id
        assert log.after_state is not None
        assert log.after_state["description"] == "Sale"


def test_fx_sync_produces_audit_entry() -> None:
    with _create_session() as session:
        actor = _seed_actor(session)
        provider = _StubFXProvider()
        with use_actor(actor):
            svc = FXService(session, provider)
            count = svc.sync(base="USD")

        assert count == 1
        stmt = select(AuditLog).where(AuditLog.entity_name == "Rate").order_by(AuditLog.ts.desc())
        log = session.exec(stmt).first()
        assert log is not None
        assert log.after_state is not None
        assert log.after_state["rates"][0]["provider"] == provider.name


def test_market_sync_produces_audit_entry() -> None:
    with _create_session() as session:
        actor = _seed_actor(session)
        provider = _StubMarketProvider()
        with use_actor(actor):
            svc = MarketService(session, provider)
            count = svc.sync_prices("TEST", date(2024, 1, 1), date(2024, 1, 1))

        assert count == 1
        stmt = select(AuditLog).where(AuditLog.entity_name == "Price").order_by(AuditLog.ts.desc())
        log = session.exec(stmt).first()
        assert log is not None
        assert log.after_state is not None
        assert log.after_state["provider"] == provider.name


def test_tax_sync_produces_audit_entry() -> None:
    with _create_session() as session:
        actor = _seed_actor(session)
        provider = _StubTaxProvider()
        with use_actor(actor):
            svc = TaxService(session, provider)
            count = svc.sync_rules()

        assert count == 1
        stmt = select(AuditLog).where(AuditLog.entity_name == "TaxRule").order_by(AuditLog.ts.desc())
        log = session.exec(stmt).first()
        assert log is not None
        assert log.after_state is not None
        assert log.after_state["provider"] == provider.name
