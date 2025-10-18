from django.core.management.base import BaseCommand
from faker import Faker
import random
from clients.models import Client 

class Command(BaseCommand):
    help = "Seed the database with random clients for testing"

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=20)

    def handle(self, *args, **options):
        fake = Faker()
        count = options['count']
        
        # Algerian provinces for realistic addresses
        algerian_provinces = [
            "Algiers", "Oran", "Constantine", "Annaba", "Blida", "Batna", "Sétif", 
            "Tlemcen", "Béjaïa", "Biskra", "Tizi Ouzou", "Mostaganem", "Msila",
            "Tiaret", "Ouargla", "Djelfa", "Sidi Bel Abbès", "Guelma", "Skikda",
            "Laghouat", "Mascara", "Médéa", "Tébessa", "Saïda", "El Oued"
        ]

        for _ in range(count):
            is_corporate = random.choice([True, False])
            
            # Generate address data
            address_data = {
                "street": fake.street_address(),
                "city": fake.city(),
                "province": random.choice(algerian_provinces),
                "postal_code": fake.postcode()
            }
            
            # Generate appropriate identification numbers based on client type
            if is_corporate:
                # Corporate clients have RC and NIF
                rc = f"RC-{random.randint(10000, 99999)}"
                nif = f"NIF-{random.randint(100000000, 999999999)}"
                nis = None
                ai = None
                company_suffix = random.choice(['SARL', 'SPA', 'EURL', 'SNC'])
                name = f"{fake.company()} {company_suffix}"
            else:
                # Individual clients have NIS and possibly AI
                rc = None
                nif = None
                nis = f"NIS-{random.randint(1000000000, 9999999999)}"
                ai = f"AI-{random.randint(10000, 99999)}" if random.choice([True, False]) else None
                name = f"{fake.first_name()} {fake.last_name()}"

            Client.objects.create(
                name=name,
                address=address_data,
                phone_number=f"0{random.randint(5, 7)}{random.randint(10, 99)}{random.randint(10, 99)}{random.randint(10, 99)}{random.randint(10, 99)}",  # Algerian phone format
                email=fake.email() if random.choice([True, False]) else None,
                is_corporate=is_corporate,
                rc=rc,
                nif=nif,
                nis=nis,
                ai=ai,
                notes=fake.text(max_nb_chars=200) if random.choice([True, False]) else None
            )

        self.stdout.write(self.style.SUCCESS(f"✅ Successfully created {count} clients!"))