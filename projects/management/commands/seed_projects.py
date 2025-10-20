from django.core.management.base import BaseCommand
from faker import Faker
import random
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from projects.models import Project, Maintenance
from clients.models import Client
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = "Seed the database with random projects and maintenances for testing"

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=15, help='Number of projects to create')
        parser.add_argument('--maintenance-chance', type=int, default=70, help='Percentage chance to add maintenance (0-100)')

    def handle(self, *args, **options):
        fake = Faker()
        count = options['count']
        maintenance_chance = options['maintenance_chance']
        
        # Get available clients and employers
        clients = Client.objects.all()
        employers = User.objects.filter(role=User.ROLE_EMPLOYER)
        admin_users = User.objects.filter(role=User.ROLE_ADMIN)
        
        if not clients.exists():
            self.stdout.write(self.style.ERROR("❌ No clients found. Please seed clients first."))
            return
            
        if not employers.exists():
            self.stdout.write(self.style.ERROR("❌ No employers found. Please seed users first."))
            return
            
        if not admin_users.exists():
            self.stdout.write(self.style.ERROR("❌ No admin users found. Please create an admin user first."))
            return

        self.stdout.write("🏗️ Starting project seeding...")

        projects_created = 0
        maintenances_created = 0
        
        # Project type categories for realistic names
        project_types = [
            "Installation", "Implementation", "Deployment", "Setup", "Configuration",
            "Integration", "Migration", "Upgrade", "Customization", "Development",
            "Training", "Consulting", "Support", "Maintenance", "Optimization"
        ]
        
        project_domains = [
            "Network", "Software", "Hardware", "Security", "Database", "Cloud",
            "Web", "Mobile", "ERP", "CRM", "IoT", "AI", "BI", "IT Infrastructure",
            "Communication", "Storage", "Backup", "Monitoring"
        ]

        for i in range(count):
            try:
                # Select random client and creator
                client = random.choice(clients)
                created_by = random.choice(admin_users)
                
                # Generate project name
                project_type = random.choice(project_types)
                project_domain = random.choice(project_domains)
                name = f"{project_type} {project_domain} for {client.name}"
                
                # Generate dates
                start_date = fake.date_between(start_date='-1y', end_date='+6m')
                
                # 70% chance to have end date, 30% ongoing projects
                if random.randint(1, 100) <= 70:
                    end_date = start_date + timedelta(days=random.randint(30, 365))
                else:
                    end_date = None
                
                # Create project
                project = Project.objects.create(
                    name=name,
                    client=client,
                    start_date=start_date,
                    end_date=end_date,
                    description=fake.paragraph(nb_sentences=3),
                    warranty_duration=random.choice([0, 6, 12, 24, 36]),
                    is_verified=random.choice([True, False]),
                    created_by=created_by
                )
                
                # Set verified info if project is verified
                if project.is_verified:
                    project.verified_at = fake.date_time_between(
                        start_date=datetime.combine(project.start_date, datetime.min.time()),
                        end_date='now'
                    )
                    project.verified_by = random.choice(admin_users)
                    project.save()
                
                # Assign random employers (1-3 employers per project)
                num_employers = random.randint(1, min(3, employers.count()))
                assigned_employers = random.sample(list(employers), num_employers)
                project.assigned_employers.set(assigned_employers)
                
                projects_created += 1
                self.stdout.write(f"   ✅ Created project: {project.name}")
                
                # Add maintenance records (70% chance per project)
                if random.randint(1, 100) <= maintenance_chance:
                    num_maintenances = random.randint(1, 3)
                    
                    for j in range(num_maintenances):
                        duration = random.choice([6, 12, 24, 36])
                        interval = random.choice([3, 6, 12])
                        
                        maintenance = Maintenance.objects.create(
                            project=project,
                            duration=duration,
                            interval=interval
                        )
                        maintenances_created += 1
                        
                    self.stdout.write(f"   🔧 Added {num_maintenances} maintenance records")
                
            except Exception as e:
                self.stdout.write(f"   ❌ Error creating project {i+1}: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"🎉 Successfully created {projects_created} projects with {maintenances_created} maintenance records!"
        ))
        
        # Display project status summary
        active = Project.objects.filter(start_date__lte=datetime.now().date(), end_date__gte=datetime.now().date()).count()
        completed = Project.objects.filter(end_date__lt=datetime.now().date()).count()
        upcoming = Project.objects.filter(start_date__gt=datetime.now().date()).count()
        
        self.stdout.write(f"📊 Project Status Summary:")
        self.stdout.write(f"   🟢 Active: {active}")
        self.stdout.write(f"   🔵 Completed: {completed}")
        self.stdout.write(f"   🟡 Upcoming: {upcoming}")
        self.stdout.write(f"   ✅ Verified: {Project.objects.filter(is_verified=True).count()}")