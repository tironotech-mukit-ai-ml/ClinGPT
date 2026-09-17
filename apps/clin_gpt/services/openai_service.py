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
from apps.clin_gpt.services.report_context_service import ReportContextService
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

    def generate_vitals_report(self, report_context: dict) -> dict:
        """
        Generate a clinical report from wearable vitals pipeline output.

        Parameters
        ----------
        report_context : dict
            Output of ReportContextService.build_context() — contains
            current_reading (raw vitals), alerts (Rule Engine), highest_severity,
            ml_prediction (risk_score/risk_label/class_probabilities), and
            similar_cases (FAISS neighbors with raw vitals + risk_label).

        Returns
        -------
        dict — same shape as generate_clinical_analysis()'s return value.
        """
        # STEP 1: Input guardrails (defensive — this pipeline's data is
        # structured vitals/demographics, not free-text PHI, but we run
        # this for HIPAA-audit consistency with the rest of the system).
        # NOTE: apply_input_guardrails was designed for the flat symptom
        # schema; if it errors on this nested structure, we log and
        # proceed with the original context rather than blocking a
        # potentially urgent clinical report.
        input_phi_detections = []
        safe_context = report_context
        try:
            safe_context, input_phi_detections = self.guardrail.apply_input_guardrails(
                report_context
            )
            if input_phi_detections:
                logger.warning(
                    f"Input Guardrails detected {len(input_phi_detections)} "
                    f"entities in vitals report context"
                )
                self._log_phi_detections(input_phi_detections, 'input')
        except Exception as e:
            logger.warning(
                f"Guardrail input scan failed on vitals context, proceeding "
                f"unredacted (structured vitals data, low PHI risk): {e}"
            )

        # STEP 2: No RAG — this schema has no symptoms/history free text.
        prompt = self._build_vitals_report_prompt(safe_context)

        try:
            # STEP 3: Call OpenAI API
            system_prompt = (
                "You are an expert medical AI assistant providing clinical decision "
                "support for continuous wearable vital-sign monitoring. "
                "You are given: the patient's current vitals, alerts already fired by "
                "a deterministic Rule Engine (fixed clinical thresholds), a probabilistic "
                "risk prediction from a machine learning model trained on historical cases, "
                "and the most similar historical cases with their outcomes. "
                "Synthesize ALL of this into a clear clinical summary. "
                "The Rule Engine and ML model may occasionally disagree — if so, note it "
                "explicitly and lean toward the more cautious interpretation. "
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
                max_completion_tokens=4000,
                reasoning_effort="low",
                response_format={"type": "json_object"},
                timeout=self.timeout
            )

            result = json.loads(response.choices[0].message.content)

            # STEP 4: Output guardrails (scan for PHI leaks in the generated text)
            safe_result, output_phi_detections = self.guardrail.apply_output_guardrails(result)

            if output_phi_detections:
                logger.error(
                    f"⚠️ OUTPUT GUARDRAIL ALERT: Detected {len(output_phi_detections)} "
                    f"PHI leaks in vitals report AI response!"
                )
                self._log_phi_detections(output_phi_detections, 'output')

            # STEP 5: Metadata (same wrapper shape as generate_clinical_analysis)
            safe_result['model'] = self.model
            safe_result['cached'] = False
            safe_result['usage'] = {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            }
            safe_result['rag_enabled'] = False
            safe_result['sources'] = []
            safe_result['guardrails'] = {
                'enabled': self.guardrail.enabled,
                'input_phi_detected': len(input_phi_detections),
                'output_phi_detected': len(output_phi_detections),
                'phi_types_detected': list(set(
                    d['type'] for d in input_phi_detections + output_phi_detections
                ))
            }

            return safe_result

        except Exception as e:
            logger.error(f"OpenAI API Error (vitals report): {str(e)}")
            import traceback
            traceback.print_exc()

            return {
                'error': str(e),
                'summary': 'Unable to generate AI analysis at this time.',
                'concerns': [],
                'recommendations': ['Please consult with a physician for manual assessment.'],
                'risk_level': 'unknown',
                'confidence': 'low',
                'guardrails': {'enabled': self.guardrail.enabled},
                'rag_enabled': False,
                'sources': [],
            }

    def _build_vitals_report_prompt(self, context: dict) -> str:
        """
        Build the LLM prompt from ReportContextService's assembled context.
        Reuses ReportContextService.to_prompt_text() as the single source
        of truth for how raw values are formatted, then wraps it with the
        JSON output instructions.
        """
        from apps.clin_gpt.services.report_context_service import ReportContextService

        base_text = ReportContextService.to_prompt_text(context)

        instructions = (
            "\n\nProvide your analysis in the following JSON format:\n"
            "{\n"
            '  "summary": "Brief overview of patient status, referencing both the '
            'Rule Engine alerts and the ML risk prediction",\n'
            '  "concerns": ["List of clinical concerns based on abnormal values and '
            'similar historical cases"],\n'
            '  "recommendations": ["Specific actionable recommendations"],\n'
            '  "risk_level": "low|moderate|high|critical",\n'
            '  "confidence": "low|medium|high"\n'
            "}"
        )

        return base_text + instructions

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
                "Always include: summary, concerns, differential diagnoses (with probability "
                "and description for each), recommendations, and risk level. "
                "Be precise, evidence-based, and cautious. "
                "IMPORTANT: This is decision support only. A physician must review all recommendations."
            )

            response = openai.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=4000,
                reasoning_effort="low",
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
                'concerns': [],
                'differential_diagnoses': [],
                'recommendations': ['Please consult with a physician for manual assessment.'],
                'risk_level': 'unknown',
                'confidence': 'low',
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
            '  "differential_diagnoses": [\n'
            '    {\n'
            '      "diagnosis": "Name of the candidate condition",\n'
            '      "probability": 0.0,\n'
            '      "description": "Brief clinical reasoning for this candidate, '
            'referencing the specific vitals/symptoms that support or argue against it"\n'
            '    }\n'
            '  ],\n'
            '  "recommendations": ["Specific actionable recommendations"],\n'
            '  "risk_level": "low|moderate|high|critical",\n'
            '  "confidence": "low|medium|high"\n'
            "}\n\n"
            "For differential_diagnoses: list 2-5 candidate conditions ordered by "
            "probability (highest first). probability values should be reasonable "
            "estimates between 0.0 and 1.0 reflecting your confidence given the "
            "presented vitals and symptoms — they do not need to sum to 1.0, since "
            "multiple conditions may coexist or be independently possible."
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
            "3. Differential diagnoses ranked by probability, referencing the guidelines",
            "4. Evidence-based recommendations referencing the guidelines",
            "5. Risk level assessment",
            "",
            "Respond in JSON format:",
            "{",
            '  "summary": "Brief overview of patient status",',
            '  "concerns": ["List of clinical concerns"],',
            '  "differential_diagnoses": [',
            '    {',
            '      "diagnosis": "Name of the candidate condition",',
            '      "probability": 0.0,',
            '      "description": "Clinical reasoning, referencing specific guidelines where relevant"',
            '    }',
            '  ],',
            '  "recommendations": ["Specific actionable recommendations with guideline references"],',
            '  "risk_level": "low|moderate|high|critical",',
            '  "confidence": "low|medium|high"',
            "}",
            "",
            "List 2-5 differential diagnoses ordered by probability (highest first). "
            "probability is a value between 0.0 and 1.0.",
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
