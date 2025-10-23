from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = "Create superuser and seed database with sample data"

    def add_arguments(self, parser):
        parser.add_argument('--users', type=int, default=15, help='Number of users to create (employers + assistants)')
        parser.add_argument('--employers', type=int, default=10, help='Number of employers to create')
        parser.add_argument('--assistants', type=int, default=5, help='Number of assistants to create')
        parser.add_argument('--clients', type=int, default=20, help='Number of clients to create')
        parser.add_argument('--products', type=int, default=25, help='Number of products to create')
        parser.add_argument('--projects', type=int, default=15, help='Number of projects to create')
        parser.add_argument('--password', type=str, default='djawad', help='Default password for users')
        parser.add_argument('--maintenance-chance', type=int, default=70, help='Percentage chance to add maintenance to projects')
        parser.add_argument('--no-input', action='store_true', help='Run without confirmation prompt')

    def create_superuser(self):
        """Create a superuser with specified credentials"""
        if not User.objects.filter(username='djawad').exists():
            User.objects.create_superuser(
                username='djawad',
                email='djawad@gmail.com',
                password='djawad',
                first_name='Jawad',
                last_name='Admin'
            )
            return True
        return False

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO("🌱 DATABASE SEEDING OPERATION"))
        self.stdout.write("=" * 50)
        self.stdout.write("This will:")
        self.stdout.write("  • Create superuser: djawad/djawad")
        self.stdout.write("  • Seed the database with sample data")
        self.stdout.write("  • Will NOT delete any existing data")
        self.stdout.write("=" * 50)

        # Confirmation prompt
        if not options['no_input']:
            confirm = input("Are you sure you want to continue? (yes/no): ")
            if confirm.lower() not in ['yes', 'y']:
                self.stdout.write(self.style.WARNING("Operation cancelled."))
                return

        try:
            # STEP 1: Create Superuser
            self.stdout.write(self.style.HTTP_INFO("👑 Step 1: Creating superuser..."))
            if self.create_superuser():
                self.stdout.write(self.style.SUCCESS("   ✅ Superuser created: djawad / djawad"))
                self.stdout.write("   📧 Email: djawad@gmail.com")
            else:
                self.stdout.write("   ℹ️  Superuser already exists")

            # STEP 2: Seed Data
            self.stdout.write(self.style.HTTP_INFO("🌱 Step 2: Seeding database with sample data..."))
            self.stdout.write("-" * 40)

            seeding_steps = [
                ('seed_users', "Users", {
                    'employers': options['employers'],
                    'assistants': options['assistants'], 
                    'password': options['password']
                }),
                ('seed_clients', "Clients", {'count': options['clients']}),
                ('seed_products', "Products", {'count': options['products']}),
                ('seed_projects', "Projects", {
                    'count': options['projects'],
                    'maintenance_chance': options['maintenance_chance']
                }),
            ]

            for command, description, kwargs in seeding_steps:
                self.stdout.write(f"   📝 {description}...")
                try:
                    call_command(command, **kwargs)
                    self.stdout.write(self.style.SUCCESS(f"      ✅ {description} seeded"))
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"      ⚠️  {description} failed: {e}"))

            # FINAL SUMMARY
            self.stdout.write("=" * 50)
            self.stdout.write(self.style.SUCCESS("🎉 Database seeding completed!"))
            self.stdout.write(f"\n📊 Summary:")
            self.stdout.write(f"   👑 Superuser: djawad / djawad")
            self.stdout.write(f"   👥 Users: {options['employers']} employers + {options['assistants']} assistants")
            self.stdout.write(f"   🏢 Clients: {options['clients']} clients")
            self.stdout.write(f"   📦 Products: {options['products']} products")
            self.stdout.write(f"   🏗️  Projects: {options['projects']} projects")
            self.stdout.write(f"   🔑 User password: {options['password']}")
            self.stdout.write("\n🚀 Your database is now populated with sample data!")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Operation failed: {e}"))