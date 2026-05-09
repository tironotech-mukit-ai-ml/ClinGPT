"""
Monitoring Middleware for Clinical GPT
Tracks API performance metrics and logs key statistics
"""

import time
import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)


class PerformanceMonitoringMiddleware:
    """
    Middleware to track API request performance metrics
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip non-API paths
        if not request.path.startswith('/api/'):
            return self.get_response(request)

        # Start timing
        start_time = time.time()

        # Process request
        response = self.get_response(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Log performance metrics
        logger.info(
            "API request completed",
            extra={
                'method': request.method,
                'path': request.path,
                'status_code': response.status_code,
                'duration_ms': round(duration_ms, 2),
                'user_agent': request.META.get('HTTP_USER_AGENT', '')[:100]
            }
        )

        # Track metrics in cache for dashboard (optional)
        self._update_metrics(request.path, duration_ms, response.status_code)

        # Add performance header
        response['X-Response-Time'] = f'{duration_ms:.2f}ms'

        return response

    def _update_metrics(self, path, duration_ms, status_code):
        """
        Update rolling metrics in cache for monitoring
        """
        try:
            # Track request counts
            count_key = f'metrics:requests:{path}:count'
            cache.set(count_key, cache.get(count_key, 0) + 1, 86400)  # 24 hour window

            # Track average response time
            avg_key = f'metrics:requests:{path}:avg_duration'
            current_avg = cache.get(avg_key, duration_ms)
            new_avg = (current_avg * 0.9) + (duration_ms * 0.1)  # Exponential moving average
            cache.set(avg_key, new_avg, 86400)

            # Track errors
            if status_code >= 400:
                error_key = f'metrics:requests:{path}:errors'
                cache.set(error_key, cache.get(error_key, 0) + 1, 86400)

        except Exception as e:
            # Don't fail requests if metrics fail
            logger.debug(f"Metrics update failed: {e}")
