from typing import List
from sqlmodel import Session
from ..models.models import TaxRule

class BaseTaxProvider:
    name: str
    def upsert_rules(self) -> List[TaxRule]:
        raise NotImplementedError

class TaxService:
    def __init__(self, session: Session, provider: BaseTaxProvider):
        self.s = session
        self.provider = provider

    def sync_rules(self) -> int:
        rules = self.provider.upsert_rules()
        for r in rules:
            self.s.add(r)
        self.s.commit()
        return len(rules)
