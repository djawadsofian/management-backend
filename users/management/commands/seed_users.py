from django.core.management.base import BaseCommand
from faker import Faker
import random
from users.models import CustomUser

class Command(BaseCommand):
    help = "Seed the database with random employers and assistants for testing"

    def add_arguments(self, parser):
        parser.add_argument('--employers', type=int, default=10, help='Number of employers to create')
        parser.add_argument('--assistants', type=int, default=5, help='Number of assistants to create')
        parser.add_argument('--password', type=str, default='djawad', help='Default password for all users')

    def handle(self, *args, **options):
        fake = Faker()
        employers_count = options['employers']
        assistants_count = options['assistants']
        default_password = options['password']
        
        # Algerian wilayas for realistic data
        algerian_wilayas = [
            "Adrar", "Chlef", "Laghouat", "Oum El Bouaghi", "Batna", "Béjaïa", "Biskra",
            "Béchar", "Blida", "Bouira", "Tamanrasset", "Tébessa", "Tlemcen", "Tiaret",
            "Tizi Ouzou", "Algiers", "Djelfa", "Jijel", "Sétif", "Saïda", "Skikda",
            "Sidi Bel Abbès", "Annaba", "Guelma", "Constantine", "Médéa", "Mostaganem",
            "M'Sila", "Mascara", "Ouargla", "Oran", "El Bayadh", "Illizi", "Bordj Bou Arréridj",
            "Boumerdès", "El Tarf", "Tindouf", "Tissemsilt", "El Oued", "Khenchela",
            "Souk Ahras", "Tipaza", "Mila", "Aïn Defla", "Naâma", "Aïn Témouchent",
            "Ghardaïa", "Relizane"
        ]

        self.stdout.write("👥 Starting user seeding...")

        # Create employers
        employers_created = 0
        for i in range(employers_count):
            try:
                username = f"employer_{fake.user_name()}_{random.randint(1000, 9999)}"
                email = f"employer_{i+1}@company.dz"
                
                user = CustomUser.objects.create(
                    username=username,
                    email=email,
                    first_name=fake.first_name(),
                    last_name=fake.last_name(),
                    phone_number=f"0{random.randint(5, 7)}{random.randint(10, 99)}{random.randint(10, 99)}{random.randint(10, 99)}{random.randint(10, 99)}",
                    role=CustomUser.ROLE_EMPLOYER,
                    wilaya=random.choice(algerian_wilayas),
                    group = random.choice(['Group A', 'Group B', 'Group C']) 
                )
                user.set_password(default_password)
                user.save()
                employers_created += 1
                self.stdout.write(f"   ✅ Created employer: {user.username}")
            except Exception as e:
                self.stdout.write(f"   ❌ Error creating employer {i+1}: {e}")

        # Create assistants
        assistants_created = 0
        for i in range(assistants_count):
            try:
                username = f"assistant_{fake.user_name()}_{random.randint(1000, 9999)}"
                email = f"assistant_{i+1}@company.dz"
                
                user = CustomUser.objects.create(
                    username=username,
                    email=email,
                    first_name=fake.first_name(),
                    last_name=fake.last_name(),
                    phone_number=f"0{random.randint(5, 7)}{random.randint(10, 99)}{random.randint(10, 99)}{random.randint(10, 99)}{random.randint(10, 99)}",
                    role=CustomUser.ROLE_ASSISTANT,
                    wilaya=random.choice(algerian_wilayas)
                )
                user.set_password(default_password)
                user.save()
                assistants_created += 1
                self.stdout.write(f"   ✅ Created assistant: {user.username}")
            except Exception as e:
                self.stdout.write(f"   ❌ Error creating assistant {i+1}: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"🎉 Successfully created {employers_created} employers and {assistants_created} assistants!"
        ))
        self.stdout.write(f"🔑 Default password for all users: {default_password}")