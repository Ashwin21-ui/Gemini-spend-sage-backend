from app.db.base import Base, engine
from app.schema.bank_statement import AccountDetails, Transaction


print("Dropping all tables...")
Base.metadata.drop_all(bind=engine)

print("Creating all tables...")
Base.metadata.create_all(bind=engine)

print("Tables created successfully!")
