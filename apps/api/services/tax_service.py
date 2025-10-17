from typing import Sequence

from sqlmodel import Session

from ..models.models import TaxRule

class BaseTaxProvider:
    name: str

    def upsert_rules(self) -> Sequence[TaxRule]:
        raise NotImplementedError

class TaxService:
    def __init__(self, session: Session, provider: BaseTaxProvider):
        self.s = session
        self.provider = provider

    def sync_rules(self) -> int:
        rules = list(self.provider.upsert_rules())
        for rule in rules:
            self.s.add(rule)
        self.s.commit()
        return len(rules)
