# apps/supplier/management/commands/seed_suppliers.py
from django.core.management.base import BaseCommand
from faker import Faker
import random
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum
from apps.supplier.models import Supplier, Debt

class Command(BaseCommand):
    help = "Seed the database with random suppliers and debts for testing"

    def add_arguments(self, parser):
        parser.add_argument('--suppliers', type=int, default=15, help='Number of suppliers to create')
        parser.add_argument('--debts', type=int, default=50, help='Number of debts to create')
        parser.add_argument('--clear', action='store_true', help='Clear existing data before seeding')

    def handle(self, *args, **options):
        fake = Faker()
        supplier_count = options['suppliers']
        debt_count = options['debts']
        
        if options['clear']:
            self.stdout.write("🗑️ Clearing existing suppliers and debts...")
            Debt.objects.all().delete()
            Supplier.objects.all().delete()
            self.stdout.write("✅ Existing data cleared")

        # Algerian provinces and cities for realistic addresses
        algerian_provinces = [
            "Alger", "Oran", "Constantine", "Annaba", "Blida", "Batna", "Sétif", 
            "Tlemcen", "Béjaïa", "Biskra", "Tizi Ouzou", "Mostaganem", "Msila",
            "Tiaret", "Ouargla", "Djelfa", "Sidi Bel Abbès", "Guelma", "Skikda",
            "Laghouat", "Mascara", "Médéa", "Tébessa", "Saïda", "El Oued"
        ]

        algerian_cities = {
            "Alger": ["Alger Centre", "Bab El Oued", "Hussein Dey", "Sidi M'Hamed", "El Biar"],
            "Oran": ["Oran Centre", "Bir El Djir", "Es Senia", "Aïn El Turk", "Mers El Kébir"],
            "Constantine": ["Constantine Centre", "El Khroub", "Aïn Smara", "Zighoud Youcef"],
            "Annaba": ["Annaba Centre", "El Bouni", "Sidi Amar", "Berrahal"],
            "Blida": ["Blida Centre", "Ouled Yaich", "Boufarik", "Bouinan"],
            "Batna": ["Batna Centre", "Tazoult", "Merouana", "Arris"],
            "Sétif": ["Sétif Centre", "Aïn Arnat", "El Eulma", "Aïn Oulmene"],
            "Tlemcen": ["Tlemcen Centre", "Mansourah", "Beni Mester", "Hennaya"]
        }

        # Company types and business categories
        company_types = ['SARL', 'SPA', 'EURL', 'SNC', 'SCS', 'GIE']
        business_categories = [
            "Électronique", "Informatique", "Bureau", "Mobilier", "Fournitures", 
            "Équipement", "Matériel", "Services", "Construction", "Textile",
            "Alimentation", "Automobile", "Médical", "Industriel"
        ]

        self.stdout.write(f"🏭 Creating {supplier_count} suppliers...")
        
        suppliers = []
        for i in range(supplier_count):
            is_company = random.choice([True, False])
            province = random.choice(algerian_provinces)
            city_options = algerian_cities.get(province, [f"{province} Ville"])
            city = random.choice(city_options)
            
            if is_company:
                company_suffix = random.choice(company_types)
                business_type = random.choice(business_categories)
                name = f"{fake.company()} {business_type} {company_suffix}"
                company = name
            else:
                name = f"{fake.first_name()} {fake.last_name()}"
                company = None

            # Generate contact information
            phone_base = f"0{random.randint(5, 7)}{random.randint(10, 99)}{random.randint(10, 99)}{random.randint(10, 99)}{random.randint(10, 99)}"
            
            supplier = Supplier.objects.create(
                name=name,
                company=company,
                email=fake.email() if random.choice([True, False, True]) else None,  # More likely to have email
                phone=phone_base,
                address=fake.street_address(),
                city=city,
                wilaya=province,
                postal_code=fake.postcode(),
                tax_id=f"MF/{random.randint(1000000, 9999999)}/{province[:3].upper()}" if is_company else None,
                website=f"www.{name.lower().replace(' ', '')}.com" if random.choice([True, False]) else None,
                notes=fake.text(max_nb_chars=150) if random.choice([True, False]) else None,
                is_active=random.choice([True, True, True, False])  # Mostly active
            )
            suppliers.append(supplier)
            
            if (i + 1) % 5 == 0:
                self.stdout.write(f"✅ Created {i + 1}/{supplier_count} suppliers")

        self.stdout.write(f"💰 Creating {debt_count} debts...")

        # Debt descriptions and categories
        debt_descriptions = [
            "Achat de matériel informatique",
            "Fourniture de bureau",
            "Services de maintenance",
            "Achat de composants électroniques",
            "Prestation de consulting",
            "Location d'équipement",
            "Services de réparation",
            "Achat de matières premières",
            "Services de transport",
            "Facture de télécommunications",
            "Services de nettoyage",
            "Achat de mobilier",
            "Services de sécurité",
            "Facture d'électricité",
            "Services informatiques"
        ]

        for i in range(debt_count):
            supplier = random.choice(suppliers)
            
            # Generate debt date (within last 2 years)
            debt_date = fake.date_between(start_date='-2y', end_date='today')
            
            # Generate due date (15-90 days after debt date)
            due_date = debt_date + timedelta(days=random.randint(15, 90))
            
            # Generate realistic amounts based on supplier type
            if supplier.company:  # Corporate supplier
                total_price = Decimal(str(round(random.uniform(5000, 50000), 2)))
            else:  # Individual supplier
                total_price = Decimal(str(round(random.uniform(500, 10000), 2)))
            
            # Determine payment status and amounts
            is_paid = random.choice([True, False, False, False])  # 25% paid, 75% pending
            
            if is_paid:
                paid_price = total_price
            else:
                # For pending debts, determine how much is paid (0% to 90%)
                payment_ratio = random.choice([0, 0, 0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9])
                paid_price = total_price * Decimal(str(payment_ratio))
            
            debt = Debt.objects.create(
                supplier=supplier,
                description=random.choice(debt_descriptions),
                date=debt_date,
                due_date=due_date,
                total_price=total_price,
                paid_price=paid_price,
                reference_number=f"FAC-{random.randint(1000, 9999)}-{random.randint(100, 999)}" if random.choice([True, False]) else None
            )
            
            if (i + 1) % 10 == 0:
                self.stdout.write(f"✅ Created {i + 1}/{debt_count} debts")

        # Generate summary statistics
        total_suppliers = Supplier.objects.count()
        total_debts = Debt.objects.count()
        active_suppliers = Supplier.objects.filter(is_active=True).count()
        
        debt_stats = Debt.objects.aggregate(
            total_amount=Sum('total_price'),
            total_paid=Sum('paid_price')
        )
        
        total_amount = debt_stats['total_amount'] or Decimal('0')
        total_paid = debt_stats['total_paid'] or Decimal('0')
        remaining = total_amount - total_paid
        
        paid_debts = Debt.objects.filter(is_paid=True).count()
        pending_debts = Debt.objects.filter(is_paid=False).count()
        overdue_debts = Debt.objects.filter(
            is_paid=False, 
            due_date__lt=timezone.now().date()
        ).count()

        self.stdout.write(self.style.SUCCESS("🎉 Successfully seeded supplier data!"))
        self.stdout.write("")
        self.stdout.write("📊 SEEDING SUMMARY:")
        self.stdout.write(f"   • Suppliers created: {total_suppliers} ({active_suppliers} active)")
        self.stdout.write(f"   • Debts created: {total_debts}")
        self.stdout.write(f"   • Total debt amount: {total_amount:,.2f} DZD")
        self.stdout.write(f"   • Total paid: {total_paid:,.2f} DZD")
        self.stdout.write(f"   • Remaining: {remaining:,.2f} DZD")
        self.stdout.write(f"   • Paid debts: {paid_debts}")
        self.stdout.write(f"   • Pending debts: {pending_debts}")
        self.stdout.write(f"   • Overdue debts: {overdue_debts}")
        self.stdout.write("")
        self.stdout.write("💡 You can now test the supplier endpoints:")
        self.stdout.write("   • GET /api/suppliers/ - List all suppliers")
        self.stdout.write("   • GET /api/suppliers/debt-summary/ - Overall debt summary")
        self.stdout.write("   • GET /api/debts/overdue/ - Overdue debts")
        self.stdout.write("   • GET /api/suppliers/1/debts/ - Supplier's specific debts")