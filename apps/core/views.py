"""
Core views - Health check and utilities
"""
from django.http import JsonResponse
from datetime import datetime


def health_check(request):
    """
    Health check endpoint
    Returns 200 if service is running
    """
    return JsonResponse({
        'status': 'healthy',
        'service': 'InTEAM AI Service',
        'version': '1.0.0',
        'timestamp': datetime.now().isoformat()
    })
