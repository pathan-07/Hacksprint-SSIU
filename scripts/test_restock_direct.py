from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import process_inventory_transaction

shop_phone = "+919876543210"

payload = {
    "customer_name": "Supplier",
    "transaction_type": "RESTOCK",
    "amount": 0,
    "items": [
        {"product_name": "Demo Item A", "quantity": 10, "unit": "pcs", "cost_price": 5},
        {"product_name": "Demo Item B", "quantity": 5, "unit": "kg", "cost_price": 40},
    ],
    "raw_text": "direct restock test",
}

print("Running direct restock test...")
result = process_inventory_transaction(shop_phone, payload)
print("Result:", result)
