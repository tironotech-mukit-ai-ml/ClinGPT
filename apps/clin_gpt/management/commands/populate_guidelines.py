"""
Django Management Command: Populate Clinical Guidelines

This command populates the clinical guidelines database with sample medical
guidelines for RAG (Retrieval-Augmented Generation).

Sources can include:
- Sample JSON file
- CSV file
- External API
- Manual text files
"""

from django.core.management.base import BaseCommand
from apps.clin_gpt.models import ClinicalGuideline
from apps.clin_gpt.services.rag_service import get_rag_service
import json
import os


class Command(BaseCommand):
    help = 'Populate clinical guidelines database for RAG system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            help='Path to JSON file containing guidelines',
            default='data/sample_guidelines.json'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing guidelines before populating',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('Populating Clinical Guidelines Database'))
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))

        # Step 1: Clear existing data if requested
        if options['clear']:
            self.clear_existing_guidelines()

        # Step 2: Load guidelines from file
        guidelines_file = options['file']
        guidelines_data = self.load_guidelines_file(guidelines_file)

        if not guidelines_data:
            self.stdout.write(self.style.ERROR('❌ No guidelines to import'))
            return

        # Step 3: Initialize RAG service for embedding generation
        rag_service = get_rag_service()
        if not rag_service.enabled or rag_service.embedding_model is None:
            self.stdout.write(
                self.style.ERROR(
                    '❌ RAG service not initialized. Run setup_guardrails_rag first.'
                )
            )
            return

        # Step 4: Import guidelines
        self.import_guidelines(guidelines_data, rag_service)

        # Step 5: Summary
        self.show_summary()

    def clear_existing_guidelines(self):
        """Delete all existing guidelines"""
        count = ClinicalGuideline.objects.count()
        if count > 0:
            self.stdout.write(f'Clearing {count} existing guidelines...')
            ClinicalGuideline.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('✅ Existing guidelines cleared'))
        else:
            self.stdout.write('No existing guidelines to clear')

    def load_guidelines_file(self, file_path):
        """Load guidelines from JSON file"""
        self.stdout.write(f'Loading guidelines from {file_path}...')

        if not os.path.exists(file_path):
            self.stdout.write(
                self.style.ERROR(
                    f'❌ File not found: {file_path}\n'
                    f'Create a sample file first or specify a different path with --file'
                )
            )
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, list):
                self.stdout.write(self.style.SUCCESS(f'✅ Loaded {len(data)} guidelines'))
                return data
            else:
                self.stdout.write(self.style.ERROR('❌ Invalid file format (expected JSON array)'))
                return None

        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f'❌ Invalid JSON: {str(e)}'))
            return None
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error loading file: {str(e)}'))
            return None

    def import_guidelines(self, guidelines_data, rag_service):
        """Import guidelines into database with embeddings"""
        self.stdout.write(f'\nImporting {len(guidelines_data)} guidelines...')
        self.stdout.write('(Generating embeddings for each guideline...)\n')

        imported_count = 0
        error_count = 0

        for i, guideline_data in enumerate(guidelines_data, 1):
            try:
                # Validate required fields
                if not guideline_data.get('title') or not guideline_data.get('content'):
                    self.stdout.write(
                        self.style.WARNING(f'⚠️  Skipping guideline {i}: Missing title or content')
                    )
                    error_count += 1
                    continue

                # Generate embedding
                text_for_embedding = f"{guideline_data['title']} {guideline_data['content']}"
                embedding = rag_service.generate_embedding(text_for_embedding)

                if not embedding:
                    self.stdout.write(
                        self.style.WARNING(f'⚠️  Skipping guideline {i}: Failed to generate embedding')
                    )
                    error_count += 1
                    continue

                # Create guideline
                ClinicalGuideline.objects.create(
                    title=guideline_data.get('title', ''),
                    content=guideline_data.get('content', ''),
                    source=guideline_data.get('source', 'Unknown'),
                    category=guideline_data.get('category', 'general'),
                    subcategory=guideline_data.get('subcategory', ''),
                    year=guideline_data.get('year'),
                    url=guideline_data.get('url', ''),
                    keywords=guideline_data.get('keywords', []),
                    embedding=embedding
                )

                imported_count += 1

                # Progress indicator
                if i % 10 == 0:
                    self.stdout.write(f'  Progress: {i}/{len(guidelines_data)} guidelines processed')

            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'⚠️  Error importing guideline {i}: {str(e)}')
                )
                error_count += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'✅ Successfully imported {imported_count} guidelines'))
        if error_count > 0:
            self.stdout.write(self.style.WARNING(f'⚠️  Failed to import {error_count} guidelines'))

    def show_summary(self):
        """Display database statistics"""
        self.stdout.write('\n' + '='*60)
        self.stdout.write('Database Summary')
        self.stdout.write('='*60)

        total = ClinicalGuideline.objects.count()
        self.stdout.write(f'Total guidelines: {total}')

        # Group by category
        categories = ClinicalGuideline.objects.values_list('category', flat=True).distinct()
        self.stdout.write(f'\nCategories ({len(categories)}):')
        for category in sorted(categories):
            count = ClinicalGuideline.objects.filter(category=category).count()
            self.stdout.write(f'  - {category}: {count} guidelines')

        # Group by source
        sources = ClinicalGuideline.objects.values_list('source', flat=True).distinct()
        self.stdout.write(f'\nSources ({len(sources)}):')
        for source in sorted(sources):
            count = ClinicalGuideline.objects.filter(source=source).count()
            self.stdout.write(f'  - {source}: {count} guidelines')

        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('✅ Clinical guidelines database ready!'))
        self.stdout.write('='*60)
        self.stdout.write('\nThe RAG system is now ready to use.')
        self.stdout.write('Test it with: python manage.py test apps.clin_gpt\n')
