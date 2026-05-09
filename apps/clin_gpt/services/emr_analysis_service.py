"""
EMR Analysis Service - Specialized service for comprehensive EMR analysis
Extends OpenAI service with EMR-specific methods for differential diagnosis,
treatment planning, and risk assessment
"""
import openai
from django.conf import settings
from django.core.cache import cache
import hashlib
import json
import logging

# Import base service and dependencies
from .openai_service import OpenAIService
from .phi_guardrail import get_phi_guardrail
from .rag_service import get_rag_service

logger = logging.getLogger(__name__)


class EmrAnalysisService(OpenAIService):
    """
    Specialized service for EMR analysis
    Inherits from OpenAIService and adds EMR-specific functionality
    """

    def __init__(self):
        super().__init__()
        logger.info("EMR Analysis Service initialized")

    def analyze_emr_data(self, emr_data: dict) -> dict:
        """
        Analyze comprehensive EMR data for clinical insights

        Enhanced workflow for EMR analysis:
        1. Build clinical narrative from EMR sections (CC, HPI, ROS, etc.)
        2. Apply input guardrails (detect/redact PHI)
        3. Retrieve relevant clinical guidelines (RAG)
        4. Build specialized EMR prompt
        5. Call GPT-4
        6. Parse structured response
        7. Apply output guardrails
        8. Return comprehensive clinical insights

        Args:
            emr_data: Dictionary containing comprehensive EMR data

        Returns:
            dict: Structured clinical insights with differential diagnosis, treatment, risk
        """
        # Check cache first (1 minute cache)
        cache_key = self._generate_emr_cache_key(emr_data)
        cached_result = cache.get(cache_key)
        if cached_result:
            cached_result['cached'] = True
            logger.info("Returning cached EMR analysis")
            return cached_result

        # STEP 1: Build clinical narrative from EMR sections
        clinical_narrative = self._build_emr_narrative(emr_data)

        # STEP 2: Apply input guardrails (PHI detection/redaction)
        safe_narrative, input_phi_detections = self.guardrail.redact_phi(
            clinical_narrative
        )

        if input_phi_detections:
            logger.warning(
                f"Input Guardrails detected {len(input_phi_detections)} PHI entities in EMR"
            )
            self._log_phi_detections(input_phi_detections, 'input')

        # STEP 3: Retrieve relevant clinical guidelines (RAG)
        relevant_guidelines = []
        if self.rag.enabled:
            # Use the narrative for RAG retrieval
            try:
                # Try using text-based retrieval if available
                if hasattr(self.rag, 'retrieve_relevant_guidelines_text'):
                    relevant_guidelines = self.rag.retrieve_relevant_guidelines_text(safe_narrative)
                else:
                    # Fallback to standard retrieval with emr_data
                    relevant_guidelines = self.rag.retrieve_relevant_guidelines(emr_data)

                if relevant_guidelines:
                    logger.info(f"RAG retrieved {len(relevant_guidelines)} guidelines for EMR")
            except Exception as e:
                logger.warning(f"RAG retrieval failed: {e}, continuing without guidelines")

        # STEP 4: Build specialized EMR analysis prompt
        prompt = self._build_emr_analysis_prompt(emr_data, safe_narrative, relevant_guidelines)

        try:
            # STEP 5: Call OpenAI API with EMR-specific system prompt
            system_prompt = (
                "You are an expert medical AI assistant providing comprehensive clinical analysis. "
                "You specialize in analyzing complete EMR data including chief complaint, HPI, ROS, "
                "social history, family history, allergies, and physical exam findings. "
            )

            if relevant_guidelines:
                system_prompt += (
                    "Use the provided clinical guidelines to inform your differential diagnosis. "
                    "Reference specific guidelines when making recommendations. "
                )

            system_prompt += (
                "Provide a structured analysis with differential diagnosis, treatment plan, "
                "risk assessment, clinical concerns, and recommended tests. "
                "Be evidence-based, thorough, and precise. "
                "CRITICAL: This is decision support only. All recommendations must be reviewed "
                "by the attending physician before implementation."
            )

            response = openai.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Lower temperature for medical accuracy
                max_tokens=1500,  # More tokens for comprehensive EMR analysis
                response_format={"type": "json_object"},
                timeout=self.timeout
            )

            # STEP 6: Parse structured response
            result = self._parse_emr_analysis_response(response)

            # STEP 7: Apply output guardrails
            safe_result, output_phi_detections = self.guardrail.apply_output_guardrails(result)

            if output_phi_detections:
                logger.error(
                    f"⚠️ OUTPUT GUARDRAIL ALERT: Detected {len(output_phi_detections)} PHI leaks in EMR analysis!"
                )
                self._log_phi_detections(output_phi_detections, 'output')

            # STEP 8: Add metadata
            safe_result['model'] = self.model
            safe_result['cached'] = False
            safe_result['usage'] = {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            }

            # Add RAG metadata
            safe_result['rag_enabled'] = self.rag.enabled
            if relevant_guidelines:
                safe_result['sources'] = [
                    {
                        'title': g.get('title', 'Clinical Guideline'),
                        'source': g.get('source', 'Unknown'),
                        'relevance': round(g.get('relevance_score', 0), 2)
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

            # Cache result for 1 minute
            cache.set(cache_key, safe_result, 60)

            return safe_result

        except Exception as e:
            logger.error(f"OpenAI API Error in EMR analysis: {str(e)}")
            import traceback
            traceback.print_exc()

            return {
                'error': str(e),
                'summary': 'Unable to generate EMR analysis at this time.',
                'differential_diagnosis': [],
                'treatment_plan': {'immediate': [], 'ongoing': []},
                'risk_assessment': {'level': 'unknown', 'factors': []},
                'clinical_concerns': ['AI service error - manual physician review required'],
                'recommended_tests': [],
                'confidence': 'low',
                'guardrails': {'enabled': self.guardrail.enabled},
                'rag_enabled': False
            }

    def _build_emr_narrative(self, emr_data: dict) -> str:
        """
        Build a comprehensive clinical narrative from EMR sections

        Args:
            emr_data: Dictionary containing all EMR fields

        Returns:
            str: Formatted clinical narrative
        """
        narrative_parts = []

        # Demographics
        demo_parts = []
        if emr_data.get('age'):
            demo_parts.append(f"{emr_data['age']} year old")
        if emr_data.get('gender'):
            demo_parts.append(emr_data['gender'])
        if demo_parts:
            narrative_parts.append("Patient: " + " ".join(demo_parts))

        # Chief Complaint
        if emr_data.get('cc'):
            narrative_parts.append(f"\nCHIEF COMPLAINT: {emr_data['cc']}")
            if emr_data.get('durationcc'):
                narrative_parts.append(f"Duration: {emr_data['durationcc']}")
            if emr_data.get('severitycc'):
                narrative_parts.append(f"Severity: {emr_data['severitycc']}")
            if emr_data.get('notes'):
                narrative_parts.append(f"Notes: {emr_data['notes']}")

        # History of Present Illness (OLDCARTS)
        hpi_parts = []
        if emr_data.get('onset'):
            hpi_parts.append(f"Onset: {emr_data['onset']}")
        if emr_data.get('location'):
            hpi_parts.append(f"Location: {emr_data['location']}")
        if emr_data.get('durationhpi'):
            hpi_parts.append(f"Duration: {emr_data['durationhpi']}")
        if emr_data.get('characteristics'):
            hpi_parts.append(f"Characteristics: {emr_data['characteristics']}")
        if emr_data.get('aggravating'):
            hpi_parts.append(f"Aggravating factors: {emr_data['aggravating']}")
        if emr_data.get('relieving'):
            hpi_parts.append(f"Relieving factors: {emr_data['relieving']}")
        if emr_data.get('severityhpi'):
            hpi_parts.append(f"Severity: {emr_data['severityhpi']}")
        if emr_data.get('associated'):
            hpi_parts.append(f"Associated symptoms: {emr_data['associated']}")
        if emr_data.get('context'):
            hpi_parts.append(f"Context: {emr_data['context']}")
        if emr_data.get('prior'):
            hpi_parts.append(f"Prior episodes: {emr_data['prior']}")

        if hpi_parts:
            narrative_parts.append("\nHISTORY OF PRESENT ILLNESS:")
            narrative_parts.extend(hpi_parts)

        # Review of Systems
        ros_parts = []
        ros_fields = [
            ('general', 'General'), ('cardiovascularros', 'Cardiovascular'),
            ('respiratoryros', 'Respiratory'), ('gastrointestinalros', 'Gastrointestinal'),
            ('genitourinaryros', 'Genitourinary'), ('musculoskeletalros', 'Musculoskeletal'),
            ('neurologicalros', 'Neurological'), ('endocrine', 'Endocrine'),
            ('integumentaryros', 'Integumentary'), ('psychiatricros', 'Psychiatric'),
            ('hematologic_lymphatic', 'Hematologic/Lymphatic'), ('allergic_immunologic', 'Allergic/Immunologic')
        ]
        for field, label in ros_fields:
            if emr_data.get(field):
                ros_parts.append(f"{label}: {emr_data[field]}")

        if ros_parts:
            narrative_parts.append("\nREVIEW OF SYSTEMS:")
            narrative_parts.extend(ros_parts)

        # Social History
        social_parts = []
        if emr_data.get('tobacco_use'):
            social_parts.append(f"Tobacco: {emr_data['tobacco_use']}")
        if emr_data.get('alcohol_use'):
            social_parts.append(f"Alcohol: {emr_data['alcohol_use']}")
        if emr_data.get('drug_use'):
            social_parts.append(f"Drug use: {emr_data['drug_use']}")
        if emr_data.get('sexual_history'):
            social_parts.append(f"Sexual history: {emr_data['sexual_history']}")
        if emr_data.get('occupation'):
            social_parts.append(f"Occupation: {emr_data['occupation']}")
        if emr_data.get('living_situation'):
            social_parts.append(f"Living situation: {emr_data['living_situation']}")
        if emr_data.get('exercise'):
            social_parts.append(f"Exercise: {emr_data['exercise']}")
        if emr_data.get('diet'):
            social_parts.append(f"Diet: {emr_data['diet']}")
        if emr_data.get('sleep'):
            social_parts.append(f"Sleep: {emr_data['sleep']}")

        if social_parts:
            narrative_parts.append("\nSOCIAL HISTORY:")
            narrative_parts.extend(social_parts)

        # Family History
        if emr_data.get('family_health_conditions'):
            narrative_parts.append(f"\nFAMILY HISTORY: {emr_data['family_health_conditions']}")

        # Allergies
        allergy_parts = []
        if emr_data.get('medication_allergies'):
            allergy_parts.append(f"Medications: {emr_data['medication_allergies']}")
        if emr_data.get('environmental_allergies'):
            allergy_parts.append(f"Environmental: {emr_data['environmental_allergies']}")
        if emr_data.get('food_allergies'):
            allergy_parts.append(f"Food: {emr_data['food_allergies']}")

        if allergy_parts:
            narrative_parts.append("\nALLERGIES:")
            narrative_parts.extend(allergy_parts)

        # Physical Exam
        pe_parts = []
        pe_fields = [
            ('general_appearance', 'General Appearance'), ('heent', 'HEENT'),
            ('neck', 'Neck'), ('cardiovascular', 'Cardiovascular'),
            ('respiratory', 'Respiratory'), ('gastrointestinal', 'Gastrointestinal'),
            ('genitourinary', 'Genitourinary'), ('musculoskeletal', 'Musculoskeletal'),
            ('neurological', 'Neurological'), ('integumentary', 'Integumentary'),
            ('psychiatric', 'Psychiatric')
        ]
        for field, label in pe_fields:
            if emr_data.get(field):
                pe_parts.append(f"{label}: {emr_data[field]}")

        if pe_parts:
            narrative_parts.append("\nPHYSICAL EXAM:")
            narrative_parts.extend(pe_parts)

        # Vitals (if available)
        vitals_parts = []
        if emr_data.get('heart_rate'):
            vitals_parts.append(f"HR: {emr_data['heart_rate']} bpm")
        if emr_data.get('blood_pressure_systolic') and emr_data.get('blood_pressure_diastolic'):
            vitals_parts.append(f"BP: {emr_data['blood_pressure_systolic']}/{emr_data['blood_pressure_diastolic']} mmHg")
        if emr_data.get('spo2'):
            vitals_parts.append(f"SpO2: {emr_data['spo2']}%")
        if emr_data.get('temperature'):
            vitals_parts.append(f"Temp: {emr_data['temperature']}°F")
        if emr_data.get('glucose'):
            vitals_parts.append(f"Glucose: {emr_data['glucose']} mg/dL")
        if emr_data.get('respiration_rate'):
            vitals_parts.append(f"RR: {emr_data['respiration_rate']} breaths/min")
        if emr_data.get('weight'):
            vitals_parts.append(f"Weight: {emr_data['weight']} kg")
        if emr_data.get('height'):
            vitals_parts.append(f"Height: {emr_data['height']} cm")

        if vitals_parts:
            narrative_parts.append("\nVITAL SIGNS:")
            narrative_parts.append(", ".join(vitals_parts))

        return "\n".join(narrative_parts)

    def _build_emr_analysis_prompt(self, emr_data: dict, narrative: str, guidelines: list) -> str:
        """
        Build specialized prompt for EMR analysis

        Args:
            emr_data: Raw EMR data
            narrative: Formatted clinical narrative
            guidelines: Retrieved clinical guidelines (if RAG enabled)

        Returns:
            str: Formatted prompt for GPT-4
        """
        prompt_parts = []

        # Add guidelines if available
        if guidelines:
            prompt_parts.extend([
                "=" * 60,
                "RELEVANT CLINICAL GUIDELINES",
                "=" * 60,
                ""
            ])
            for i, guideline in enumerate(guidelines, 1):
                prompt_parts.append(f"\n[Guideline {i}]")
                prompt_parts.append(f"Source: {guideline.get('source', 'Unknown')}")
                if guideline.get('title'):
                    prompt_parts.append(f"Title: {guideline['title']}")
                prompt_parts.append(f"\n{guideline.get('content', '')}\n")

        # Add clinical narrative
        prompt_parts.extend([
            "=" * 60,
            "PATIENT EMR DATA",
            "=" * 60,
            "",
            narrative,
            "",
            "=" * 60,
            "ANALYSIS REQUEST",
            "=" * 60,
            "",
            "Based on the complete EMR data above, provide a comprehensive clinical analysis.",
            "",
            "Respond in the following JSON format:",
            "{",
            '  "summary": "Brief clinical summary (2-3 sentences)",',
            '  "differential_diagnosis": [',
            '    {"condition": "Most likely diagnosis", "probability": "high|moderate|low", "reasoning": "Why this diagnosis fits"},',
            '    {"condition": "Alternative diagnosis", "probability": "moderate|low", "reasoning": "Supporting evidence"}',
            '  ],',
            '  "treatment_plan": {',
            '    "immediate": ["Immediate interventions needed"],',
            '    "ongoing": ["Long-term management recommendations"]',
            '  },',
            '  "risk_assessment": {',
            '    "level": "low|moderate|high|critical",',
            '    "factors": ["Risk factors identified"],',
            '    "timeframe": "Urgency assessment"',
            '  },',
            '  "clinical_concerns": ["Specific concerns requiring attention"],',
            '  "recommended_tests": ["Diagnostic tests to order"],',
            '  "confidence": "low|medium|high"',
            "}"
        ])

        return "\n".join(prompt_parts)

    def _parse_emr_analysis_response(self, response) -> dict:
        """
        Parse and validate EMR analysis response from OpenAI

        Args:
            response: OpenAI API response object

        Returns:
            dict: Parsed and structured analysis
        """
        try:
            result = json.loads(response.choices[0].message.content)

            # Ensure all required fields exist with defaults
            structured_result = {
                'summary': result.get('summary', 'Analysis completed'),
                'differential_diagnosis': result.get('differential_diagnosis', []),
                'treatment_plan': result.get('treatment_plan', {'immediate': [], 'ongoing': []}),
                'risk_assessment': result.get('risk_assessment', {'level': 'unknown', 'factors': []}),
                'clinical_concerns': result.get('clinical_concerns', []),
                'recommended_tests': result.get('recommended_tests', []),
                'confidence': result.get('confidence', 'medium')
            }

            return structured_result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse EMR analysis JSON: {e}")
            return {
                'summary': 'Error parsing AI response',
                'differential_diagnosis': [],
                'treatment_plan': {'immediate': [], 'ongoing': []},
                'risk_assessment': {'level': 'unknown', 'factors': []},
                'clinical_concerns': ['AI response parsing error'],
                'recommended_tests': [],
                'confidence': 'low'
            }

    def _generate_emr_cache_key(self, data: dict) -> str:
        """
        Generate cache key for EMR analysis

        Args:
            data: EMR data dictionary

        Returns:
            str: Cache key
        """
        # Use all EMR content fields for cache key
        cache_data = {k: v for k, v in data.items() if v is not None and k not in ['patient_id', 'emr_id']}
        data_string = json.dumps(cache_data, sort_keys=True)
        hash_object = hashlib.md5(data_string.encode())
        return f"clin_gpt_emr_analysis:{hash_object.hexdigest()}"


# Module-level singleton instance and lock
_emr_analysis_service_instance = None
_emr_analysis_service_lock = __import__('threading').Lock()


def get_emr_analysis_service() -> EmrAnalysisService:
    """
    Get or create the singleton EMR Analysis service instance.
    Thread-safe singleton pattern.

    Returns:
        EmrAnalysisService: Singleton instance of the EMR Analysis service
    """
    global _emr_analysis_service_instance

    if _emr_analysis_service_instance is None:
        with _emr_analysis_service_lock:
            # Double-check locking pattern
            if _emr_analysis_service_instance is None:
                logger.info("Creating EMR Analysis service singleton instance")
                _emr_analysis_service_instance = EmrAnalysisService()

    return _emr_analysis_service_instance
