"""
RAG Service - Retrieval-Augmented Generation for Clinical Guidelines
Uses pgvector for semantic similarity search in clinical guidelines database
"""

from typing import List, Dict, Optional
from sentence_transformers import SentenceTransformer
from django.conf import settings
from django.db.models import F
from django.utils import timezone
import logging
import threading

logger = logging.getLogger(__name__)

# Module-level singleton instance and lock
_rag_instance = None
_rag_lock = threading.Lock()


class ClinicalRAGService:
    """
    Retrieval-Augmented Generation service for clinical guidelines

    Uses semantic similarity search to find relevant clinical guidelines
    from the local knowledge base to augment AI prompts.

    Implemented as a singleton to avoid reloading the embedding model on each request.
    """

    def __init__(self):
        """Initialize embedding model and RAG configuration"""
        self.enabled = settings.RAG_ENABLED
        self.top_k = settings.RAG_TOP_K_RESULTS
        self.similarity_threshold = settings.RAG_SIMILARITY_THRESHOLD
        self.embedding_model = None

        if self.enabled:
            try:
                # Load sentence transformer model (local, no API calls)
                logger.info(f"Loading embedding model: {settings.RAG_EMBEDDING_MODEL}")
                self.embedding_model = SentenceTransformer(settings.RAG_EMBEDDING_MODEL)
                logger.info("RAG Service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize RAG Service: {str(e)}")
                self.enabled = False


    def retrieve_relevant_guidelines(
        self,
        patient_data: Dict,
        category_filter: Optional[str] = None,
        top_k: Optional[int] = None
    ) -> List[Dict]:
        """
        Retrieve relevant clinical guidelines based on patient presentation

        Args:
            patient_data: Dictionary containing patient symptoms, vitals, etc.
            category_filter: Optional category to filter guidelines (e.g., 'cardiology')
            top_k: Number of results to return (overrides default)

        Returns:
            List of relevant guidelines with content, source, and relevance score
        """
        if not self.enabled or self.embedding_model is None:
            logger.warning("RAG Service not enabled or model not loaded")
            return []

        try:
            # Import here to avoid circular dependency
            from apps.clin_gpt.models import ClinicalGuideline

            # Build search query from patient data
            query_text = self._build_search_query(patient_data)

            if not query_text:
                logger.warning("Empty query text, cannot retrieve guidelines")
                return []

            # Generate query embedding
            query_embedding = self.embedding_model.encode(query_text)

            # Use top_k parameter if provided, otherwise use default
            k = top_k if top_k is not None else self.top_k

            # Build query
            queryset = ClinicalGuideline.objects.all()

            # Apply category filter if specified
            if category_filter:
                queryset = queryset.filter(category=category_filter)

            # Perform vector similarity search using pgvector
            # Calculate cosine distance and order by similarity
            try:
                from pgvector.django import CosineDistance
                results = queryset.annotate(
                    distance=CosineDistance('embedding', query_embedding)
                ).order_by('distance')[:k]
            except Exception as e:
                # Fallback: pgvector not available (using SQLite or pgvector not installed)
                logger.warning(f"pgvector not available: {str(e)}. Falling back to keyword matching.")
                # Use basic keyword filtering as fallback
                query_keywords = query_text.lower().split()
                results = queryset.filter(content__icontains=query_keywords[0])[:k] if query_keywords else []

            # Convert to list of dictionaries with relevance scores
            guidelines = []
            for guideline in results:
                # Convert cosine distance to similarity score (1 - distance)
                # Use hasattr to check if pgvector distance is available
                if hasattr(guideline, 'distance'):
                    similarity_score = 1 - guideline.distance
                else:
                    # Fallback: assign default score for keyword-based results
                    similarity_score = 0.7

                # Skip if below threshold
                if similarity_score < self.similarity_threshold:
                    continue

                guidelines.append({
                    'id': guideline.id,
                    'title': guideline.title,
                    'content': guideline.content,
                    'source': guideline.source,
                    'category': guideline.category,
                    'year': guideline.year,
                    'url': guideline.url,
                    'relevance_score': float(similarity_score),
                    'keywords': guideline.keywords
                })

                # Increment usage counter asynchronously
                guideline.increment_usage()

            logger.info(
                f"RAG retrieved {len(guidelines)} guidelines "
                f"(query: '{query_text[:50]}...', category: {category_filter})"
            )

            return guidelines

        except Exception as e:
            logger.error(f"RAG retrieval error: {str(e)}")
            return []

    def _build_search_query(self, patient_data: Dict) -> str:
        """
        Build semantic search query from patient data

        Extracts relevant medical information to search for guidelines:
        - Symptoms
        - Medical conditions
        - Abnormal vital signs

        Args:
            patient_data: Dictionary containing patient information

        Returns:
            Search query string
        """
        query_parts = []

        # Add symptoms (highest priority)
        if patient_data.get('symptoms'):
            symptoms = patient_data['symptoms']
            # Already redacted by guardrails at this point
            query_parts.append(f"Symptoms: {symptoms}")

        # Add medical history
        if patient_data.get('medical_history'):
            history = patient_data['medical_history']
            query_parts.append(f"Medical history: {history}")

        # Add chief complaint if available
        if patient_data.get('chief_complaint'):
            query_parts.append(f"Chief complaint: {patient_data['chief_complaint']}")

        # Detect concerning vital signs and add to query
        vital_concerns = self._detect_vital_concerns(patient_data)
        if vital_concerns:
            query_parts.extend(vital_concerns)

        # If no query parts, create generic query from demographics
        if not query_parts:
            age = patient_data.get('age')
            gender = patient_data.get('gender')
            if age and gender:
                query_parts.append(f"General clinical assessment for {age}-year-old {gender}")

        return " ".join(query_parts)

    def _detect_vital_concerns(self, data: Dict) -> List[str]:
        """
        Detect abnormal vital signs and generate search terms

        Args:
            data: Patient data dictionary

        Returns:
            List of concern strings for search query
        """
        concerns = []

        # Blood pressure
        bp_sys = data.get('blood_pressure_systolic')
        bp_dia = data.get('blood_pressure_diastolic')
        if bp_sys and bp_dia:
            if bp_sys >= 180 or bp_dia >= 120:
                concerns.append("hypertensive crisis management")
            elif bp_sys >= 140 or bp_dia >= 90:
                concerns.append("hypertension management")
            elif bp_sys < 90:
                concerns.append("hypotension management")

        # Oxygen saturation
        spo2 = data.get('spo2')
        if spo2 is not None:
            if spo2 < 90:
                concerns.append("severe hypoxia treatment")
            elif spo2 < 95:
                concerns.append("hypoxia management")

        # Heart rate
        hr = data.get('heart_rate')
        if hr is not None:
            if hr > 120:
                concerns.append("tachycardia management")
            elif hr < 50:
                concerns.append("bradycardia management")

        # Blood glucose
        glucose = data.get('glucose')
        if glucose is not None:
            if glucose < 70:
                concerns.append("hypoglycemia treatment")
            elif glucose > 180:
                concerns.append("hyperglycemia management")

        # Temperature
        temp = data.get('temperature')
        if temp is not None:
            # Assume temperature in Fahrenheit
            if temp >= 103:
                concerns.append("high fever management")
            elif temp < 95:
                concerns.append("hypothermia treatment")

        # Respiration rate
        rr = data.get('respiration_rate')
        if rr is not None:
            if rr > 24:
                concerns.append("tachypnea assessment")
            elif rr < 12:
                concerns.append("bradypnea evaluation")

        return concerns

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text

        Args:
            text: Input text to embed

        Returns:
            List of floats representing the embedding vector
        """
        if not self.enabled or self.embedding_model is None:
            return []

        try:
            embedding = self.embedding_model.encode(text)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Failed to generate embedding: {str(e)}")
            return []

    def get_categories(self) -> List[str]:
        """
        Get list of all available guideline categories

        Returns:
            List of unique categories in the database
        """
        try:
            from apps.clin_gpt.models import ClinicalGuideline

            categories = ClinicalGuideline.objects.values_list(
                'category', flat=True
            ).distinct().order_by('category')

            return list(categories)

        except Exception as e:
            logger.error(f"Failed to get categories: {str(e)}")
            return []

    def get_stats(self) -> Dict:
        """
        Get RAG system statistics

        Returns:
            Dictionary with stats about the knowledge base
        """
        try:
            from apps.clin_gpt.models import ClinicalGuideline

            total_guidelines = ClinicalGuideline.objects.count()
            categories = ClinicalGuideline.objects.values_list(
                'category', flat=True
            ).distinct().count()
            sources = ClinicalGuideline.objects.values_list(
                'source', flat=True
            ).distinct().count()

            # Most used guidelines
            top_used = list(
                ClinicalGuideline.objects.order_by('-usage_count')[:5].values(
                    'title', 'source', 'usage_count'
                )
            )

            return {
                'total_guidelines': total_guidelines,
                'total_categories': categories,
                'total_sources': sources,
                'top_used_guidelines': top_used,
                'embedding_model': settings.RAG_EMBEDDING_MODEL,
                'embedding_dimension': settings.RAG_EMBEDDING_DIMENSION,
                'enabled': self.enabled
            }

        except Exception as e:
            logger.error(f"Failed to get RAG stats: {str(e)}")
            return {'enabled': self.enabled, 'error': str(e)}


# Module-level singleton factory function
def get_rag_service() -> ClinicalRAGService:
    """
    Get or create the singleton RAG service instance.
    Thread-safe singleton pattern to avoid reloading the embedding model.

    Returns:
        ClinicalRAGService: Singleton instance of the RAG service
    """
    global _rag_instance

    if _rag_instance is None:
        with _rag_lock:
            # Double-check locking pattern
            if _rag_instance is None:
                logger.info("Creating RAG service singleton instance")
                _rag_instance = ClinicalRAGService()

    return _rag_instance
