# run_tests.py
"""
Comprehensive test runner for the entire application
Run this file to execute all tests with detailed reporting
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.core.management import call_command
from django.test.utils import get_runner
from django.conf import settings


def run_all_tests():
    """Run all tests with coverage and detailed reporting"""
    print("=" * 80)
    print("COMPREHENSIVE TEST SUITE")
    print("=" * 80)
    print()
    
    # Run tests by app
    test_apps = [
        'apps.core',
        'apps.users',
        'apps.clients',
        'apps.stock',
        'apps.projects',
        'apps.invoices',
        'apps.dashboard',
    ]
    
    print("🧪 Running tests for all apps...")
    print()
    
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=False, keepdb=True)
    
    failures = test_runner.run_tests(test_apps)
    
    print()
    print("=" * 80)
    if failures:
        print(f"❌ TESTS FAILED: {failures} failure(s)")
    else:
        print("✅ ALL TESTS PASSED!")
    print("=" * 80)
    
    return failures


def run_specific_app(app_name):
    """Run tests for a specific app"""
    print(f"🧪 Running tests for {app_name}...")
    call_command('test', f'apps.{app_name}', verbosity=2)


def run_critical_tests_only():
    """Run only critical tests (invoices and stock management)"""
    print("=" * 80)
    print("CRITICAL TESTS - Stock Management & Invoices")
    print("=" * 80)
    print()
    
    critical_apps = [
        'apps.stock',
        'apps.invoices',
    ]
    
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=False, keepdb=True)
    
    failures = test_runner.run_tests(critical_apps)
    
    print()
    print("=" * 80)
    if failures:
        print(f"❌ CRITICAL TESTS FAILED: {failures} failure(s)")
    else:
        print("✅ ALL CRITICAL TESTS PASSED!")
    print("=" * 80)
    
    return failures


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Run tests for the application')
    parser.add_argument(
        '--app',
        type=str,
        help='Run tests for a specific app (e.g., stock, invoices, projects)'
    )
    parser.add_argument(
        '--critical',
        action='store_true',
        help='Run only critical tests (stock and invoices)'
    )
    parser.add_argument(
        '--coverage',
        action='store_true',
        help='Run tests with coverage report'
    )
    
    args = parser.parse_args()
    
    if args.coverage:
        print("Running tests with coverage...")
        os.system('coverage run --source="." manage.py test')
        os.system('coverage report')
        os.system('coverage html')
        print("\n📊 Coverage report generated in htmlcov/index.html")
    elif args.critical:
        sys.exit(run_critical_tests_only())
    elif args.app:
        run_specific_app(args.app)
    else:
        sys.exit(run_all_tests())