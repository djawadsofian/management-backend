from django.core.management.base import BaseCommand
from faker import Faker
import random

class Command(BaseCommand):
    help = "Seed the database with random products for testing"

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=20)

    def handle(self, *args, **options):
        # Try importing from different apps
        try:
            from inventory.models import Product
        except ImportError:
            try:
                from stock.models import Product
            except ImportError:
                self.stdout.write(self.style.ERROR("❌ Could not import Product model from inventory or stock apps"))
                return

        fake = Faker()
        count = options['count']
        units = ["pcs", "kg", "liters", "boxes", "packs", "bottles"]

        for _ in range(count):
            # Generate realistic buying and selling prices
            buying_price = round(random.uniform(1.0, 100.0), 2)
            
            # Ensure selling price is higher than buying price (with reasonable profit margin)
            min_selling_price = buying_price * 1.1  # At least 10% profit
            max_selling_price = buying_price * 2.5  # Up to 150% profit
            selling_price = round(random.uniform(min_selling_price, max_selling_price), 2)

            Product.objects.create(
                name=fake.word().capitalize() + " " + fake.word().capitalize(),
                sku=f"SKU-{random.randint(1000,9999)}",
                quantity=random.randint(1, 200),
                unit=random.choice(units),
                reorder_threshold=random.randint(5, 30),
                buying_price=buying_price,
                selling_price=selling_price
            )

        self.stdout.write(self.style.SUCCESS(f"✅ Successfully created {count} products with buying/selling prices!"))