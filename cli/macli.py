import click
import csv
from datetime import date
from sqlmodel import Session, select
from apps.api.db import engine, init_db
from apps.api.services.plugin_loader import load_provider
from apps.api.services.fx_service import FXService
from apps.api.services.market_service import MarketService
from apps.api.services.ledger_service import LedgerService
from apps.api.models.models import Account

@click.group()
def cli():
    """Modular Accounting CLI"""

@cli.command()
@click.option("--base", default="USD")
@click.option("--provider", default="plugins.fx_ecb.provider")
def sync_fx(base, provider):
    init_db()
    prov = load_provider(provider)
    with Session(engine) as s:
        svc = FXService(s, prov)
        n = svc.sync(base=base)
        click.echo(f"Synced {n} FX rates via {prov.name}")

@cli.command()
@click.argument("symbol")
@click.option("--start", required=True)
@click.option("--end", required=True)
@click.option("--provider", default="plugins.market_yfinance.provider")
def sync_prices(symbol, start, end, provider):
    init_db()
    prov = load_provider(provider)
    with Session(engine) as s:
        svc = MarketService(s, prov)
        n = svc.sync_prices(symbol, date.fromisoformat(start), date.fromisoformat(end))
        click.echo(f"Synced {n} prices for {symbol} via {prov.name}")

@cli.command()
@click.option("--file", "file_", required=True, type=click.Path(exists=True))
def import_csv(file_):
    """Import a simple CSV of postings: date,description,account_code,debit,credit,currency"""
    init_db()
    with Session(engine) as s:
        ls = LedgerService(s)
        with open(file_, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Assume columns: date,description,account_code,debit,credit,currency
                txn_date = date.fromisoformat(row['date'])
                description = row['description']
                account_code = row['account_code']
                debit = float(row.get('debit', 0))
                credit = float(row.get('credit', 0))
                currency = row.get('currency', 'USD')
                
                # Find or create account by code
                acct = s.exec(select(Account).where(Account.code == account_code)).first()
                if not acct:
                    click.echo(f"Account {account_code} not found, skipping")
                    continue
                
                postings = [{
                    'account_id': acct.id,
                    'debit': debit,
                    'credit': credit,
                    'currency': currency
                }]
                ls.post_transaction(txn_date, description, postings)
        click.echo(f"Imported CSV from {file_}")

if __name__ == "__main__":
    cli()
