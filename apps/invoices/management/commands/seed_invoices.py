from django.core.management.base import BaseCommand
from faker import Faker
import random
from decimal import Decimal
from datetime import datetime, timedelta
from apps.invoices.models import Invoice, InvoiceLine
from apps.projects.models import Project
from apps.stock.models import Product
from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()

class Command(BaseCommand):
    help = "Seed the database with random invoices for testing"

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=30, help='Number of invoices to create')
        parser.add_argument('--max-lines', type=int, default=8, help='Maximum number of line items per invoice')

    def handle(self, *args, **options):
        fake = Faker()
        count = options['count']
        max_lines = options['max_lines']
        
        # Get available data
        projects = Project.objects.all()
        products = Product.objects.all()
        admin_users = User.objects.filter(role=User.ROLE_ADMIN)
        
        if not projects.exists():
            self.stdout.write(self.style.ERROR("❌ No projects found. Please seed projects first."))
            return
            
        if not products.exists():
            self.stdout.write(self.style.ERROR("❌ No products found. Please seed products first."))
            return
            
        if not admin_users.exists():
            self.stdout.write(self.style.ERROR("❌ No admin users found. Please create an admin user first."))
            return

        self.stdout.write("🧾 Starting invoice seeding...")

        invoices_created = 0
        lines_created = 0
        
        # Document types for realistic data
        bon_types = ["BC", "BV", "BR", "FAC"]
        status_choices = [Invoice.STATUS_DRAFT, Invoice.STATUS_ISSUED, Invoice.STATUS_PAID, Invoice.STATUS_CANCELLED]

        for i in range(count):
            try:
                # Select random project and creator
                project = random.choice(projects)
                created_by = random.choice(admin_users)
                
                # Generate document numbers
                year_suffix = datetime.now().year % 100
                bon_de_commande = f"BC{random.randint(1000, 9999)}/{year_suffix}" if random.choice([True, False]) else None
                bon_de_versement = f"BV{random.randint(1000, 9999)}/{year_suffix}" if random.choice([True, False]) else None
                bon_de_reception = f"BR{random.randint(1000, 9999)}/{year_suffix}" if random.choice([True, False]) else None
                facture = f"FAC{random.randint(1000, 9999)}/{year_suffix}" if random.choice([True, False]) else None
                
                # Generate dates
                issued_date = fake.date_between(start_date='-1y', end_date='today')
                due_date = issued_date + timedelta(days=random.randint(15, 90))
                
                # Select status
                status = random.choice(status_choices)
                
                # Create invoice
                invoice = Invoice.objects.create(
                    project=project,
                    bon_de_commande=bon_de_commande,
                    bon_de_versement=bon_de_versement,
                    bon_de_reception=bon_de_reception,
                    facture=facture,
                    issued_date=issued_date,
                    due_date=due_date,
                    deposit_price=Decimal(str(round(random.uniform(0, 1000), 2))),
                    status=status,
                    created_by=created_by
                )
                
                # Add line items
                num_lines = random.randint(1, max_lines)
                invoice_lines = []
                
                for j in range(num_lines):
                    product = random.choice(products)
                    quantity = Decimal(str(random.randint(1, 10)))
                    
                    # Use product selling price as base, with some variation
                    base_price = product.selling_price
                    # Convert float operations to Decimal
                    variation = Decimal(str(random.uniform(0.8, 1.5)))
                    unit_price = (base_price * variation).quantize(Decimal('0.01'))
                    
                    # Calculate discount
                    if random.choice([True, False]):
                        discount_rate = Decimal(str(random.uniform(0, 0.2)))
                        discount = (unit_price * discount_rate).quantize(Decimal('0.01'))
                    else:
                        discount = Decimal('0.00')
                    
                    line = InvoiceLine.objects.create(
                        invoice=invoice,
                        product=product,
                        description=fake.sentence(nb_words=6) if random.choice([True, False]) else "",
                        quantity=quantity,
                        unit_price=unit_price,
                        discount=discount
                    )
                    invoice_lines.append(line)
                    lines_created += 1
                
                
                invoices_created += 1
                self.stdout.write(f"   ✅ Created invoice: {invoice.facture or invoice.bon_de_commande or 'No Number'}")
                self.stdout.write(f"      📊 Total: {invoice.total} | Lines: {num_lines} | Status: {invoice.get_status_display()}")
                
            except Exception as e:
                self.stdout.write(f"   ❌ Error creating invoice {i+1}: {e}")
                import traceback
                self.stdout.write(f"   🔍 Detailed error: {traceback.format_exc()}")

        self.stdout.write(self.style.SUCCESS(
            f"🎉 Successfully created {invoices_created} invoices with {lines_created} line items!"
        ))
        
        # Display invoice status summary
        status_summary = {}
        for status_code, status_name in Invoice.STATUS_CHOICES:
            count = Invoice.objects.filter(status=status_code).count()
            status_summary[status_name] = count
        
        self.stdout.write(f"📊 Invoice Status Summary:")
        for status_name, count in status_summary.items():
            self.stdout.write(f"   📋 {status_name}: {count}")
        
        # Display financial summary
        total_invoiced = Invoice.objects.aggregate(total=models.Sum('total'))['total'] or Decimal('0.00')
        paid_invoices = Invoice.objects.filter(status=Invoice.STATUS_PAID).aggregate(total=models.Sum('total'))['total'] or Decimal('0.00')
        
        collection_rate = (paid_invoices / total_invoiced * Decimal('100.00')).quantize(Decimal('0.1')) if total_invoiced > Decimal('0.00') else Decimal('0.0')
        
        self.stdout.write(f"💰 Financial Summary:")
        self.stdout.write(f"   💵 Total Invoiced: {total_invoiced:.2f}")
        self.stdout.write(f"   💰 Total Paid: {paid_invoices:.2f}")
        self.stdout.write(f"   📈 Collection Rate: {collection_rate}%")