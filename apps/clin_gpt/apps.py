from django.apps import AppConfig
from django.core.checks import Error, Warning, register, Tags


class ClinGptConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.clin_gpt'

    def ready(self):
        """
        Perform startup checks and initialization
        """
        # Register system checks
        register_settings_checks()


def register_settings_checks():
    """
    Register Django system checks for critical settings validation
    """

    @register(Tags.security)
    def check_openai_settings(app_configs, **kwargs):
        """Validate OpenAI configuration"""
        from django.conf import settings
        errors = []

        # Check OpenAI API key
        if not getattr(settings, 'OPENAI_API_KEY', None):
            errors.append(
                Error(
                    'OPENAI_API_KEY is not configured',
                    hint='Set OPENAI_API_KEY in your environment or settings',
                    id='clingpt.E001',
                )
            )
        elif settings.OPENAI_API_KEY == 'your-openai-api-key-here':
            errors.append(
                Warning(
                    'OPENAI_API_KEY appears to be using default placeholder value',
                    hint='Update OPENAI_API_KEY with your actual API key',
                    id='clingpt.W001',
                )
            )

        # Check OpenAI model
        if not getattr(settings, 'OPENAI_MODEL', None):
            errors.append(
                Error(
                    'OPENAI_MODEL is not configured',
                    hint='Set OPENAI_MODEL in your settings (e.g., "gpt-4-turbo-preview")',
                    id='clingpt.E002',
                )
            )

        return errors

    @register(Tags.database)
    def check_rag_settings(app_configs, **kwargs):
        """Validate RAG configuration"""
        from django.conf import settings
        errors = []

        if getattr(settings, 'RAG_ENABLED', False):
            # Check embedding model
            if not getattr(settings, 'RAG_EMBEDDING_MODEL', None):
                errors.append(
                    Error(
                        'RAG_EMBEDDING_MODEL must be set when RAG_ENABLED=True',
                        hint='Set RAG_EMBEDDING_MODEL (e.g., "sentence-transformers/all-MiniLM-L6-v2")',
                        id='clingpt.E003',
                    )
                )

            # Check embedding dimension
            if not getattr(settings, 'RAG_EMBEDDING_DIMENSION', None):
                errors.append(
                    Error(
                        'RAG_EMBEDDING_DIMENSION must be set when RAG_ENABLED=True',
                        hint='Set RAG_EMBEDDING_DIMENSION (384 for all-MiniLM-L6-v2)',
                        id='clingpt.E004',
                    )
                )

            # Check similarity threshold
            threshold = getattr(settings, 'RAG_SIMILARITY_THRESHOLD', None)
            if threshold is not None and (threshold < 0 or threshold > 1):
                errors.append(
                    Error(
                        'RAG_SIMILARITY_THRESHOLD must be between 0 and 1',
                        hint=f'Current value: {threshold}. Use a value between 0.0 and 1.0',
                        id='clingpt.E005',
                    )
                )

        return errors

    @register(Tags.security)
    def check_guardrails_settings(app_configs, **kwargs):
        """Validate Guardrails configuration"""
        from django.conf import settings
        errors = []

        if getattr(settings, 'GUARDRAILS_ENABLED', False):
            # Check redaction entities
            entities = getattr(settings, 'GUARDRAILS_REDACTION_ENTITIES', [])
            if not entities:
                errors.append(
                    Warning(
                        'GUARDRAILS_REDACTION_ENTITIES is empty',
                        hint='Consider adding entities like ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS"]',
                        id='clingpt.W002',
                    )
                )

        return errors
