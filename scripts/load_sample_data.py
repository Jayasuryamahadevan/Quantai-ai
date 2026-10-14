"""scripts/load_sample_data.py — Generate and upload sample retail data."""
import asyncio
import uuid
import pandas as pd
import numpy as np
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from app.utils.import_pipeline import import_file
from app.storage.database import Base, get_app_engine
from app.storage.models import Source, ColumnCatalog
from app.storage.database import app_session

async def main():
    print("Generating sample data...")
    # Generate 1000 rows of retail data
    np.random.seed(42)
    n = 1000
    dates = pd.date_range(start="2024-01-01", periods=n, freq="4H")
    regions = ["North America", "Europe", "Asia", "South America"]
    categories = ["Electronics", "Clothing", "Home", "Sports"]
    
    df = pd.DataFrame({
        "order_id": [f"ORD-{i:05d}" for i in range(1, n + 1)],
        "order_date": dates,
        "region": np.random.choice(regions, n),
        "category": np.random.choice(categories, n),
        "sales_amount": np.round(np.random.uniform(50.0, 1500.0, n), 2),
        "quantity": np.random.randint(1, 10, n),
        "discount_pct": np.random.choice([0, 5, 10, 15, 20], n),
        "is_returned": np.random.choice([True, False], n, p=[0.05, 0.95]),
        "customer_rating": np.random.randint(1, 6, n),
    })
    
    uploads_dir = Path("data/uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / "sample_retail.csv"
    df.to_csv(file_path, index=False)
    
    print("Importing sample data...")
    Base.metadata.create_all(get_app_engine())
    
    result = await asyncio.to_thread(import_file, file_path, "sample_retail.csv")
    
    source_id = str(uuid.uuid4())
    with app_session() as session:
        src = Source(
            id=source_id,
            name="sample_retail.csv",
            source_type="csv",
            table_name=result["table_name"],
            schema_name=result["schema_name"],
            row_count=result["row_count"],
            col_count=result["col_count"],
            file_path=str(file_path),
        )
        session.add(src)
        
        for entry in result["catalog_entries"]:
            col = ColumnCatalog(
                source_id=source_id,
                **{k: v for k, v in entry.items() if k != "source_id"},
            )
            session.add(col)
            
    print(f"Success! Uploaded {result['row_count']} rows. Source ID: {source_id}")

if __name__ == "__main__":
    asyncio.run(main())
