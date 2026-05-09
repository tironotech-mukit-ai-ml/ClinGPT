"""
OpenAI Service - Handles all GPT-4 API calls with Guardrails and RAG
Enhanced with PHI detection/redaction and Retrieval-Augmented Generation
"""
import openai
from django.conf import settings
from django.core.cache import cache
import hashlib
import json
import logging
import threading

# Import Guardrails and RAG services
from .phi_guardrail import get_phi_guardrail
from .rag_service import get_rag_service

logger = logging.getLogger(__name__)

# Module-level singleton instance and lock
_openai_service_instance = None
_openai_service_lock = threading.Lock()


class OpenAIService:
    """
    Service to interact with OpenAI GPT-4
    Enhanced with:
    - Guardrails: PHI detection and redaction
    - RAG: Retrieval-Augmented Generation from clinical guidelines
    """

    def __init__(self):
        openai.api_key = settings.OPENAI_API_KEY
        self.model = settings.OPENAI_MODEL
        self.timeout = getattr(settings, 'OPENAI_TIMEOUT', 30)  # 30 second timeout

        # Initialize Guardrails and RAG (both use singleton pattern)
        self.guardrail = get_phi_guardrail()
        self.rag = get_rag_service()

        logger.info(
            f"OpenAI Service initialized with Guardrails={self.guardrail.enabled}, "
            f"RAG={self.rag.enabled}, Timeout={self.timeout}s"
        )

    def generate_clinical_analysis(self, patient_data: dict) -> dict:
        """
        Generate clinical analysis using GPT-4 with Guardrails and RAG

        Enhanced workflow:
        1. Apply input guardrails (detect/redact PHI)
        2. Retrieve relevant clinical guidelines (RAG)
        3. Build enhanced prompt with guidelines
        4. Call GPT-4
        5. Apply output guardrails (scan for PHI leaks)
        6. Add metadata and return

        Args:
            patient_data: Dictionary containing patient vitals and info

        Returns:
            dict: AI-generated clinical analysis with sources and PHI stats
        """
        # Check cache first (1 minute cache)
        # Cache key uses safe data so PHI in symptoms doesn't affect cache lookup
        # We generate a preliminary key from raw data for the cache check,
        # but store under the safe-data key to avoid cross-patient cache collisions.
        cache_key = self._generate_cache_key(patient_data)
        cached_result = cache.get(cache_key)
        if cached_result:
            cached_result['cached'] = True
            logger.info("Returning cached analysis")
            return cached_result

        # STEP 1: Apply input guardrails (PHI detection/redaction)
        safe_patient_data, input_phi_detections = self.guardrail.apply_input_guardrails(
            patient_data
        )

        # Use safe data for cache key so PHI variants don't share a cache entry
        safe_cache_key = self._generate_cache_key(safe_patient_data)
        cached_result = cache.get(safe_cache_key)
        if cached_result:
            cached_result['cached'] = True
            logger.info("Returning cached analysis (safe key)")
            return cached_result

        if input_phi_detections:
            logger.warning(
                f"Input Guardrails detected {len(input_phi_detections)} PHI entities"
            )
            # Log to database for audit
            self._log_phi_detections(input_phi_detections, 'input')

        # STEP 2: Retrieve relevant clinical guidelines (RAG)
        relevant_guidelines = self.rag.retrieve_relevant_guidelines(safe_patient_data)

        if relevant_guidelines:
            logger.info(f"RAG retrieved {len(relevant_guidelines)} relevant guidelines")

        # STEP 3: Build enhanced prompt with guidelines
        if relevant_guidelines and self.rag.enabled:
            prompt = self._build_rag_prompt(safe_patient_data, relevant_guidelines)
        else:
            prompt = self._build_clinical_prompt(safe_patient_data)

        try:
            # STEP 4: Call OpenAI API
            system_prompt = (
                "You are an expert medical AI assistant providing clinical decision support. "
                "Analyze patient vital signs and provide actionable insights. "
            )

            if relevant_guidelines:
                system_prompt += (
                    "Use the provided clinical guidelines to inform your analysis. "
                    "Reference specific guidelines when relevant. "
                )

            system_prompt += (
                "Always include: summary, concerns, recommendations, and risk level. "
                "Be precise, evidence-based, and cautious. "
                "IMPORTANT: This is decision support only. A physician must review all recommendations."
            )

            response = openai.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for medical accuracy
                max_tokens=1000,
                response_format={"type": "json_object"},
                timeout=self.timeout  # Add timeout to prevent hanging
            )

            # Parse response
            result = json.loads(response.choices[0].message.content)

            # STEP 5: Apply output guardrails (scan for PHI leaks)
            safe_result, output_phi_detections = self.guardrail.apply_output_guardrails(result)

            if output_phi_detections:
                logger.error(
                    f"⚠️ OUTPUT GUARDRAIL ALERT: Detected {len(output_phi_detections)} PHI leaks in AI response!"
                )
                # Log to database for audit (this is serious!)
                self._log_phi_detections(output_phi_detections, 'output')

            # STEP 6: Add metadata
            safe_result['model'] = self.model
            safe_result['cached'] = False
            safe_result['usage'] = {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            }

            # Add RAG metadata
            safe_result['rag_enabled'] = self.rag.enabled

            # Add RAG sources if retrieved
            if relevant_guidelines:
                safe_result['sources'] = [
                    {
                        'title': g['title'],
                        'source': g['source'],
                        'relevance': round(g['relevance_score'], 2)
                    }
                    for g in relevant_guidelines
                ]
            else:
                safe_result['sources'] = []

            # Add guardrails stats
            safe_result['guardrails'] = {
                'enabled': self.guardrail.enabled,
                'input_phi_detected': len(input_phi_detections),
                'output_phi_detected': len(output_phi_detections),
                'phi_types_detected': list(set(d['type'] for d in input_phi_detections + output_phi_detections))
            }

            # Cache result for 1 minute (under the safe-data key)
            cache.set(safe_cache_key, safe_result, 60)

            return safe_result

        except Exception as e:
            logger.error(f"OpenAI API Error: {str(e)}")
            import traceback
            traceback.print_exc()

            return {
                'error': str(e),
                'summary': 'Unable to generate AI analysis at this time.',
                'recommendations': ['Please consult with a physician for manual assessment.'],
                'risk_level': 'unknown',
                'guardrails': {'enabled': self.guardrail.enabled},
                'rag_enabled': False
            }

    def _build_clinical_prompt(self, data: dict) -> str:
        """
        Build detailed clinical prompt from patient data
        """
        prompt_parts = [
            "Analyze the following patient vital signs and provide clinical insights:\n"
        ]

        # Demographics
        if 'age' in data:
            prompt_parts.append(f"- Age: {data['age']} years")
        if 'gender' in data:
            prompt_parts.append(f"- Gender: {data['gender']}")
        if 'weight' in data and 'height' in data:
            bmi = data['weight'] / ((data['height']/100) ** 2)
            prompt_parts.append(f"- Weight: {data['weight']} kg, Height: {data['height']} cm (BMI: {bmi:.1f})")

        # Vital signs
        prompt_parts.append("\nVital Signs:")
        if 'heart_rate' in data:
            prompt_parts.append(f"- Heart Rate: {data['heart_rate']} bpm")
        if 'spo2' in data:
            prompt_parts.append(f"- SpO2: {data['spo2']}%")
        if 'blood_pressure_systolic' in data and 'blood_pressure_diastolic' in data:
            prompt_parts.append(
                f"- Blood Pressure: {data['blood_pressure_systolic']}/{data['blood_pressure_diastolic']} mmHg"
            )
        if 'temperature' in data:
            prompt_parts.append(f"- Temperature: {data['temperature']}°F")
        if 'glucose' in data:
            prompt_parts.append(f"- Blood Glucose: {data['glucose']} mg/dL")
        if 'cholesterol' in data:
            prompt_parts.append(f"- Cholesterol: {data['cholesterol']} mg/dL")
        if 'respiration_rate' in data:
            prompt_parts.append(f"- Respiration Rate: {data['respiration_rate']} breaths/min")

        # Symptoms
        if data.get('symptoms'):
            prompt_parts.append(f"\nReported Symptoms: {data['symptoms']}")

        # Medical history
        if data.get('medical_history'):
            prompt_parts.append(f"\nMedical History: {data['medical_history']}")

        prompt_parts.append(
            "\n\nProvide your analysis in the following JSON format:\n"
            "{\n"
            '  "summary": "Brief overview of patient status",\n'
            '  "concerns": ["List of clinical concerns based on abnormal values"],\n'
            '  "recommendations": ["Specific actionable recommendations"],\n'
            '  "risk_level": "low|moderate|high|critical",\n'
            '  "confidence": "low|medium|high"\n'
            "}"
        )

        return "\n".join(prompt_parts)

    def _build_rag_prompt(self, data: dict, guidelines: list) -> str:
        """
        Build enhanced prompt with retrieved clinical guidelines
        """
        prompt_parts = [
            "=" * 60,
            "RELEVANT CLINICAL GUIDELINES",
            "=" * 60,
            ""
        ]

        # Add retrieved guidelines
        for i, guideline in enumerate(guidelines, 1):
            prompt_parts.append(f"\n[Guideline {i}]")
            prompt_parts.append(f"Source: {guideline['source']}")
            if guideline.get('year'):
                prompt_parts.append(f"Year: {guideline['year']}")
            prompt_parts.append(f"Relevance: {guideline['relevance_score']:.0%}")
            prompt_parts.append(f"\n{guideline['content']}\n")

        prompt_parts.extend([
            "",
            "=" * 60,
            "PATIENT CASE",
            "=" * 60,
            ""
        ])

        # Add patient data (already redacted by guardrails)
        if 'age' in data:
            prompt_parts.append(f"Age: {data['age']} years")
        if 'gender' in data:
            prompt_parts.append(f"Gender: {data['gender']}")
        if 'weight' in data and 'height' in data:
            bmi = data['weight'] / ((data['height']/100) ** 2)
            prompt_parts.append(f"Weight: {data['weight']} kg, Height: {data['height']} cm (BMI: {bmi:.1f})")

        # Vital signs
        prompt_parts.append("\nVital Signs:")
        if 'heart_rate' in data:
            prompt_parts.append(f"- Heart Rate: {data['heart_rate']} bpm")
        if 'spo2' in data:
            prompt_parts.append(f"- SpO2: {data['spo2']}%")
        if 'blood_pressure_systolic' in data and 'blood_pressure_diastolic' in data:
            prompt_parts.append(
                f"- Blood Pressure: {data['blood_pressure_systolic']}/{data['blood_pressure_diastolic']} mmHg"
            )
        if 'temperature' in data:
            prompt_parts.append(f"- Temperature: {data['temperature']}°F")
        if 'glucose' in data:
            prompt_parts.append(f"- Blood Glucose: {data['glucose']} mg/dL")
        if 'cholesterol' in data:
            prompt_parts.append(f"- Cholesterol: {data['cholesterol']} mg/dL")
        if 'respiration_rate' in data:
            prompt_parts.append(f"- Respiration Rate: {data['respiration_rate']} breaths/min")

        # Symptoms (already redacted)
        if data.get('symptoms'):
            prompt_parts.append(f"\nReported Symptoms: {data['symptoms']}")

        # Medical history (already redacted)
        if data.get('medical_history'):
            prompt_parts.append(f"\nMedical History: {data['medical_history']}")

        prompt_parts.extend([
            "",
            "=" * 60,
            "INSTRUCTIONS",
            "=" * 60,
            "",
            "Based on the clinical guidelines above and the patient case, provide:",
            "1. Clinical summary",
            "2. Concerns based on abnormal values and guidelines",
            "3. Evidence-based recommendations referencing the guidelines",
            "4. Risk level assessment",
            "",
            "Respond in JSON format:",
            "{",
            '  "summary": "Brief overview of patient status",',
            '  "concerns": ["List of clinical concerns"],',
            '  "recommendations": ["Specific actionable recommendations with guideline references"],',
            '  "risk_level": "low|moderate|high|critical",',
            '  "confidence": "low|medium|high"',
            "}"
        ])

        return "\n".join(prompt_parts)

    def _log_phi_detections(self, detections: list, detection_type: str):
        """
        Log PHI detections to database for audit trail

        Args:
            detections: List of detected PHI entities
            detection_type: 'input' or 'output'
        """
        # Skip logging if database is not set up (SQLite or migrations not run)
        if not settings.GUARDRAILS_LOG_PHI_DETECTIONS:
            return

        try:
            from apps.clin_gpt.models import PHIDetectionLog
            from django.db import connection

            # Check if table exists before trying to log
            table_names = connection.introspection.table_names()
            if 'phi_detection_logs' not in table_names:
                logger.debug("PHI detection logs table not created yet. Run migrations to enable logging.")
                return

            for detection in detections:
                PHIDetectionLog.objects.create(
                    entity_type=detection['type'],
                    field_name=detection.get('field', 'unknown'),
                    is_output_leak=(detection_type == 'output'),
                    confidence_score=detection.get('confidence', 0),
                    text_length=detection.get('end', 0) - detection.get('start', 0),
                    position_start=detection.get('start', 0),
                    position_end=detection.get('end', 0)
                )

        except Exception as e:
            logger.debug(f"PHI detection logging skipped: {str(e)}")

    def _generate_cache_key(self, data: dict) -> str:
        """
        Generate cache key from essential patient data fields only.
        Optimized to only hash relevant fields for better cache performance.

        Args:
            data: Patient data dictionary

        Returns:
            str: Cache key for this request
        """
        # Extract only essential fields for caching (exclude metadata)
        essential_fields = [
            'age', 'gender', 'heart_rate', 'spo2', 'glucose',
            'blood_pressure_systolic', 'blood_pressure_diastolic',
            'temperature', 'cholesterol', 'respiration_rate',
            'symptoms', 'medical_history', 'chief_complaint'
        ]

        # Build minimal dict with only present essential fields
        cache_data = {k: v for k, v in data.items() if k in essential_fields and v is not None}

        # Create deterministic hash of essential data only
        data_string = json.dumps(cache_data, sort_keys=True)
        hash_object = hashlib.md5(data_string.encode())
        return f"clin_gpt_analysis:{hash_object.hexdigest()}"


# Module-level singleton factory function
def get_openai_service() -> OpenAIService:
    """
    Get or create the singleton OpenAI service instance.
    Thread-safe singleton pattern to avoid re-initializing services.

    Returns:
        OpenAIService: Singleton instance of the OpenAI service
    """
    global _openai_service_instance

    if _openai_service_instance is None:
        with _openai_service_lock:
            # Double-check locking pattern
            if _openai_service_instance is None:
                logger.info("Creating OpenAI service singleton instance")
                _openai_service_instance = OpenAIService()

    return _openai_service_instance