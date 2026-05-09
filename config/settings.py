"""
Django settings for InTEAM AI Service
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Security Settings
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-this-in-production')
DEBUG = os.getenv('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party apps
    'rest_framework',
    'corsheaders',

    # Local apps
    'apps.core',
    'apps.clin_gpt',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Custom middleware
    'apps.clin_gpt.middleware.PerformanceMonitoringMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.sqlite3'),
        'NAME': os.getenv('DB_NAME', BASE_DIR / 'db.sqlite3'),
        'HOST': os.getenv('DB_HOST', ''),
        'PORT': os.getenv('DB_PORT', ''),
        'USER': os.getenv('DB_USER', ''),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '600')),  # Connection pooling (10 min)
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'DEFAULT_PERMISSION_CLASSES': [],
    'UNAUTHENTICATED_USER': None,
}

# CORS Settings (Allow Laravel to call Django)
# Base allowed origins
CORS_ALLOWED_ORIGINS = [
    "http://localhost",
    "http://localhost:80",
    "http://localhost:8000",
    "http://localhost:8001",
    "http://localhost:8005",
    "http://127.0.0.1",
    "http://127.0.0.1:80",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8001",
    "http://127.0.0.1:8005",
    # Production server IP
    "http://159.198.76.203",
    "http://159.198.76.203:8000",
    "http://159.198.76.203:8001",
    "http://159.198.76.203:8005",
    # Production domains
    "http://www.inteamhealth.com",
    "https://www.inteamhealth.com",
    "http://inteamhealth.com",
    "https://inteamhealth.com"
]

# Add custom origins from environment variable
# Format: CORS_ADDITIONAL_ORIGINS=http://example.com,https://example.com
additional_origins = os.getenv('CORS_ADDITIONAL_ORIGINS', '')
if additional_origins:
    CORS_ALLOWED_ORIGINS.extend([origin.strip() for origin in additional_origins.split(',')])

# For development/testing only: Allow all origins (SECURITY RISK in production)
if DEBUG and os.getenv('CORS_ALLOW_ALL', 'False') == 'True':
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOW_ALL_ORIGINS = False

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
OPENAI_TIMEOUT = int(os.getenv('OPENAI_TIMEOUT', '30'))  # Request timeout in seconds

# Laravel Integration
LARAVEL_API_URL = os.getenv('LARAVEL_API_URL', 'http://localhost:80')
LARAVEL_API_KEY = os.getenv('LARAVEL_API_KEY')

# Cache Configuration
CACHE_BACKEND = os.getenv('CACHE_BACKEND', 'django.core.cache.backends.locmem.LocMemCache')
CACHE_LOCATION = os.getenv('CACHE_LOCATION', 'inteam-ai-cache')

CACHES = {
    'default': {
        'BACKEND': CACHE_BACKEND,
        'LOCATION': CACHE_LOCATION,
    }
}

# Guardrails Configuration (PHI Detection)
GUARDRAILS_ENABLED = os.getenv('GUARDRAILS_ENABLED', 'True') == 'True'
GUARDRAILS_LOG_PHI_DETECTIONS = os.getenv('GUARDRAILS_LOG_PHI_DETECTIONS', 'True') == 'True'
GUARDRAILS_REDACTION_ENTITIES = [
    'PERSON', 'PHONE_NUMBER', 'EMAIL_ADDRESS', 'LOCATION',
    'DATE_TIME', 'US_SSN', 'MEDICAL_LICENSE', 'US_DRIVER_LICENSE',
    'IP_ADDRESS', 'IBAN_CODE', 'CREDIT_CARD', 'URL'
]

# RAG Configuration (Vector Database)
RAG_ENABLED = os.getenv('RAG_ENABLED', 'True') == 'True'
RAG_EMBEDDING_MODEL = os.getenv('RAG_EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')
RAG_EMBEDDING_DIMENSION = int(os.getenv('RAG_EMBEDDING_DIMENSION', '384'))
RAG_TOP_K_RESULTS = int(os.getenv('RAG_TOP_K_RESULTS', '5'))
RAG_SIMILARITY_THRESHOLD = float(os.getenv('RAG_SIMILARITY_THRESHOLD', '0.5'))

# Spacy Model for NER (used by Presidio)
SPACY_MODEL = os.getenv('SPACY_MODEL', 'en_core_web_sm')
