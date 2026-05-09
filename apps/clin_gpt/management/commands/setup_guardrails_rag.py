"""
Django Management Command: Setup Guardrails and RAG System

This command sets up the complete Guardrails and RAG infrastructure:
1. Downloads required Spacy models for Presidio
2. Creates database tables (pgvector extension)
3. Creates vector indexes
4. Validates configuration
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings
import subprocess
import sys


class Command(BaseCommand):
    help = 'Setup Guardrails (PHI detection) and RAG (pgvector) system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-spacy',
            action='store_true',
            help='Skip downloading Spacy model (if already installed)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('InTEAM AI Service - Guardrails & RAG Setup'))
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))

        # Step 1: Install Spacy model for Presidio
        if not options['skip_spacy']:
            self.stdout.write('Step 1: Installing Spacy language model...')
            self.install_spacy_model()
        else:
            self.stdout.write(self.style.WARNING('Step 1: Skipped (--skip-spacy flag)'))

        # Step 2: Enable pgvector extension
        self.stdout.write('\nStep 2: Enabling pgvector extension in PostgreSQL...')
        self.enable_pgvector()

        # Step 3: Run migrations
        self.stdout.write('\nStep 3: Running database migrations...')
        self.run_migrations()

        # Step 4: Create vector indexes
        self.stdout.write('\nStep 4: Creating vector indexes for fast similarity search...')
        self.create_vector_indexes()

        # Step 5: Validate setup
        self.stdout.write('\nStep 5: Validating Guardrails and RAG setup...')
        self.validate_setup()

        # Final summary
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('✅ Setup Complete!'))
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write('\nNext steps:')
        self.stdout.write('  1. Populate clinical guidelines:')
        self.stdout.write('     python manage.py populate_guidelines')
        self.stdout.write('  2. Test the system:')
        self.stdout.write('     python manage.py test apps.clin_gpt')
        self.stdout.write('')

    def install_spacy_model(self):
        """Download and install Spacy language model for NER"""
        try:
            spacy_model = settings.SPACY_MODEL
            self.stdout.write(f'   Downloading {spacy_model}...')

            # Install using pip
            subprocess.check_call(
                [sys.executable, '-m', 'spacy', 'download', spacy_model],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            self.stdout.write(self.style.SUCCESS(f'   ✅ {spacy_model} installed successfully'))

        except subprocess.CalledProcessError as e:
            self.stdout.write(
                self.style.WARNING(
                    f'   ⚠️  Failed to install {spacy_model}. '
                    f'You may need to install it manually:\n'
                    f'   python -m spacy download {spacy_model}'
                )
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ❌ Error: {str(e)}'))

    def enable_pgvector(self):
        """Enable pgvector extension in PostgreSQL"""
        try:
            with connection.cursor() as cursor:
                # Check if extension already exists
                cursor.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
                )
                exists = cursor.fetchone()[0]

                if exists:
                    self.stdout.write(self.style.SUCCESS('   ✅ pgvector extension already enabled'))
                else:
                    # Create extension
                    cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')
                    self.stdout.write(self.style.SUCCESS('   ✅ pgvector extension enabled successfully'))

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'   ❌ Failed to enable pgvector: {str(e)}\n'
                    f'   Make sure you are using PostgreSQL with pgvector support.\n'
                    f'   Docker image: pgvector/pgvector:pg15'
                )
            )
            sys.exit(1)

    def run_migrations(self):
        """Run Django migrations to create tables"""
        try:
            from django.core.management import call_command

            call_command('migrate', verbosity=0)
            self.stdout.write(self.style.SUCCESS('   ✅ Database migrations applied'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ❌ Migration failed: {str(e)}'))
            sys.exit(1)

    def create_vector_indexes(self):
        """Create HNSW index for fast vector similarity search"""
        try:
            with connection.cursor() as cursor:
                # Check if index already exists
                cursor.execute("""
                    SELECT EXISTS(
                        SELECT 1 FROM pg_indexes
                        WHERE indexname = 'clinical_guidelines_embedding_hnsw_idx'
                    )
                """)
                exists = cursor.fetchone()[0]

                if exists:
                    self.stdout.write(self.style.SUCCESS('   ✅ Vector index already exists'))
                else:
                    # Create HNSW index for fast approximate nearest neighbor search
                    self.stdout.write('   Creating HNSW index (this may take a few minutes)...')
                    cursor.execute("""
                        CREATE INDEX clinical_guidelines_embedding_hnsw_idx
                        ON clinical_guidelines
                        USING hnsw (embedding vector_cosine_ops)
                        WITH (m = 16, ef_construction = 64);
                    """)
                    self.stdout.write(self.style.SUCCESS('   ✅ HNSW vector index created'))

        except Exception as e:
            # Index creation is optional - warn but don't fail
            self.stdout.write(
                self.style.WARNING(
                    f'   ⚠️  Could not create vector index: {str(e)}\n'
                    f'   System will still work, but searches may be slower.'
                )
            )

    def validate_setup(self):
        """Validate that Guardrails and RAG are working"""
        errors = []

        # Check 1: Presidio imports
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
            self.stdout.write(self.style.SUCCESS('   ✅ Presidio libraries imported'))
        except ImportError as e:
            errors.append(f'Presidio import failed: {str(e)}')

        # Check 2: Sentence transformers
        try:
            from sentence_transformers import SentenceTransformer
            self.stdout.write(self.style.SUCCESS('   ✅ Sentence Transformers imported'))
        except ImportError as e:
            errors.append(f'Sentence Transformers import failed: {str(e)}')

        # Check 3: pgvector Django integration
        try:
            from pgvector.django import VectorField
            self.stdout.write(self.style.SUCCESS('   ✅ pgvector Django integration imported'))
        except ImportError as e:
            errors.append(f'pgvector import failed: {str(e)}')

        # Check 4: Database tables exist
        try:
            from apps.clin_gpt.models import ClinicalGuideline, PHIDetectionLog
            ClinicalGuideline.objects.count()
            PHIDetectionLog.objects.count()
            self.stdout.write(self.style.SUCCESS('   ✅ Database tables created'))
        except Exception as e:
            errors.append(f'Database tables check failed: {str(e)}')

        # Check 5: Initialize Guardrails
        try:
            from apps.clin_gpt.services.phi_guardrail import PHIGuardrail
            guardrail = PHIGuardrail()
            if guardrail.enabled:
                # Test redaction
                test_text = "Patient John Smith, SSN 123-45-6789"
                redacted, detections = guardrail.redact_phi(test_text)
                if len(detections) > 0:
                    self.stdout.write(self.style.SUCCESS(
                        f'   ✅ Guardrails working (detected {len(detections)} PHI entities in test)'
                    ))
                else:
                    errors.append('Guardrails: No PHI detected in test string')
            else:
                errors.append('Guardrails: Service disabled')
        except Exception as e:
            errors.append(f'Guardrails initialization failed: {str(e)}')

        # Check 6: Initialize RAG
        try:
            from apps.clin_gpt.services.rag_service import get_rag_service
            rag = get_rag_service()
            if rag.enabled and rag.embedding_model is not None:
                # Test embedding generation
                test_embedding = rag.generate_embedding("chest pain hypertension")
                if len(test_embedding) == settings.RAG_EMBEDDING_DIMENSION:
                    self.stdout.write(self.style.SUCCESS('   ✅ RAG service working (embeddings generated)'))
                else:
                    errors.append(f'RAG: Wrong embedding dimension ({len(test_embedding)} vs {settings.RAG_EMBEDDING_DIMENSION})')
            else:
                errors.append('RAG: Service disabled or model not loaded')
        except Exception as e:
            errors.append(f'RAG initialization failed: {str(e)}')

        # Report errors
        if errors:
            self.stdout.write(self.style.ERROR('\n   ❌ Validation failed with errors:'))
            for error in errors:
                self.stdout.write(self.style.ERROR(f'      - {error}'))
            sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS('   ✅ All validation checks passed'))
