# apps/invoices/management/commands/seed_invoices.py
from django.core.management.base import BaseCommand
from faker import Faker
import random
from decimal import Decimal
from datetime import datetime, timedelta
from apps.invoices.models import Invoice, InvoiceLine
from apps.projects.models import Project
from apps.stock.models import Product
from django.contrib.auth import get_user_model
from django.db import models, transaction

User = get_user_model()

class Command(BaseCommand):
    help = "Seed the database with random invoices (respecting strict stock logic)"

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=30, help='Number of invoices to create')
        parser.add_argument('--max-lines', type=int, default=8, help='Maximum number of line items per invoice')
        parser.add_argument('--issue-percent', type=int, default=60, help='Percentage of invoices to issue (0-100)')
        parser.add_argument('--paid-percent', type=int, default=30, help='Percentage of issued to mark as paid (0-100)')

    def handle(self, *args, **options):
        fake = Faker()
        count = options['count']
        max_lines = options['max_lines']
        issue_percent = options['issue_percent']
        paid_percent = options['paid_percent']
        
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
        invoices_issued = 0
        invoices_paid = 0
        lines_created = 0

        for i in range(count):
            try:
                with transaction.atomic():
                    # Select random project and creator
                    project = random.choice(projects)
                    created_by = random.choice(admin_users)
                    
                    # Generate document numbers
                    year_suffix = datetime.now().year % 100
                    bon_de_commande = f"BC{random.randint(1000, 9999)}/{year_suffix}" if random.choice([True, False]) else None
                    bon_de_versement = f"BV{random.randint(1000, 9999)}/{year_suffix}" if random.choice([True, False]) else None
                    bon_de_reception = f"BR{random.randint(1000, 9999)}/{year_suffix}" if random.choice([True, False]) else None
                    # facture = f"FAC{random.randint(1000, 9999)}/{year_suffix}" if random.choice([True, False]) else None
                    
                    # Generate dates
                    issued_date = fake.date_between(start_date='-1y', end_date='today')
                    due_date = issued_date + timedelta(days=random.randint(15, 90))
                    
                    # Random TVA (most common rates in Algeria)
                    tva_rates = [Decimal('19.00'), Decimal('9.00'), Decimal('0.00')]
                    tva = random.choice(tva_rates)
                    
                    # Create invoice in DRAFT status
                    invoice = Invoice.objects.create(
                        project=project,
                        bon_de_commande=bon_de_commande,
                        bon_de_versement=bon_de_versement,
                        bon_de_reception=bon_de_reception,
                        facture=None,
                        due_date=due_date,
                        tva=tva,
                        deposit_price=Decimal(str(round(random.uniform(0, 500), 2))),
                        status=Invoice.STATUS_DRAFT,
                        created_by=created_by
                    )
                    
                    # Add line items (stock NOT affected yet - invoice is DRAFT)
                    num_lines = random.randint(1, max_lines)
                    
                    for j in range(num_lines):
                        product = random.choice(products)
                        
                        # Limit quantity to available stock for later issuing
                        max_qty = min(product.quantity, 10)
                        if max_qty < 1:
                            continue  # Skip if no stock
                        
                        quantity = Decimal(str(random.randint(1, max_qty)))
                        
                        # Use product selling price as base
                        base_price = product.selling_price
                        variation = Decimal(str(random.uniform(0.8, 1.5)))
                        unit_price = (base_price * variation).quantize(Decimal('0.01'))
                        
                        # Calculate discount
                        if random.choice([True, False]):
                            discount_rate = Decimal(str(random.uniform(0, 0.15)))
                            discount = (unit_price * quantity * discount_rate).quantize(Decimal('0.01'))
                        else:
                            discount = Decimal('0.00')
                        
                        # Create line (no stock change - DRAFT)
                        line = InvoiceLine.objects.create(
                            invoice=invoice,
                            product=product,
                            description=fake.sentence(nb_words=6) if random.choice([True, False]) else "",
                            quantity=quantity,
                            unit_price=unit_price,
                            discount=discount
                        )
                        lines_created += 1
                    
                    # Calculate totals
                    invoice.calculate_totals()
                    
                    invoices_created += 1
                    self.stdout.write(f"   ✅ Created DRAFT invoice: {invoice.facture or invoice.bon_de_commande or f'INV-{invoice.id}'}")
                    self.stdout.write(f"      📊 Subtotal: {invoice.subtotal} | TVA {invoice.tva}%: {invoice.tax_amount} | Total: {invoice.total}")
                    
                    # Decide if we should issue this invoice
                    if random.randint(1, 100) <= issue_percent:
                        try:
                            invoice.issue()  # This affects stock
                            invoices_issued += 1
                            self.stdout.write(f"      ✅ Invoice ISSUED (stock deducted)")
                            
                            # Decide if we should mark as paid
                            if random.randint(1, 100) <= paid_percent:
                                invoice.mark_paid()
                                invoices_paid += 1
                                self.stdout.write(f"      💰 Invoice PAID (locked)")
                        except Exception as e:
                            self.stdout.write(f"      ⚠️  Could not issue: {e}")
                    
            except Exception as e:
                self.stdout.write(f"   ❌ Error creating invoice {i+1}: {e}")
                import traceback
                self.stdout.write(f"   🔍 Detailed error: {traceback.format_exc()}")

        # Summary
        self.stdout.write(self.style.SUCCESS(
            f"\n🎉 Successfully created {invoices_created} invoices with {lines_created} line items!"
        ))
        
        self.stdout.write(f"\n📊 Invoice Status Summary:")
        self.stdout.write(f"   📋 DRAFT: {invoices_created - invoices_issued}")
        self.stdout.write(f"   📤 ISSUED: {invoices_issued - invoices_paid}")
        self.stdout.write(f"   💰 PAID: {invoices_paid}")
        
        # Financial summary
        draft_total = Invoice.objects.filter(status=Invoice.STATUS_DRAFT).aggregate(
            total=models.Sum('total')
        )['total'] or Decimal('0.00')
        
        issued_total = Invoice.objects.filter(status=Invoice.STATUS_ISSUED).aggregate(
            total=models.Sum('total')
        )['total'] or Decimal('0.00')
        
        paid_total = Invoice.objects.filter(status=Invoice.STATUS_PAID).aggregate(
            total=models.Sum('total')
        )['total'] or Decimal('0.00')
        
        self.stdout.write(f"\n💰 Financial Summary:")
        self.stdout.write(f"   📋 Draft Total: {draft_total:.2f} (stock not affected)")
        self.stdout.write(f"   📤 Issued Total: {issued_total:.2f} (stock affected)")
        self.stdout.write(f"   💵 Paid Total: {paid_total:.2f} (locked)")
        self.stdout.write(f"   📈 Grand Total: {(draft_total + issued_total + paid_total):.2f}")