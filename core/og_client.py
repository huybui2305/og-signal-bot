import os
import logging
from typing import Optional, Tuple, Dict, Any
import opengradient as og

logger = logging.getLogger(__name__)

class OGClient:
    """
    Wrapper for OpenGradient SDK to handle initialization and LLM inference.
    """
    def __init__(self, private_key: str, email: Optional[str] = None, password: Optional[str] = None):
        self.private_key = private_key
        self.email = email
        self.password = password
        self.client: Optional[og.Client] = None
        self._initialize()

    def _initialize(self):
        try:
            # Using the Client pattern as recommended in docs for better management
            self.client = og.Client(
                private_key=self.private_key,
                email=self.email,
                password=self.password
            )
            logger.info("OpenGradient Client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OpenGradient Client: {e}")
            self.client = None

    def llm_chat(self, prompt: str, mode: str = "VANILLA", model_cid: str = og.LLM.MISTRAL_7B_INSTRUCT_V3) -> Tuple[Optional[str], Optional[str], str]:
        """
        Run verifiable LLM inference.
        Returns (tx_hash, content, model_used)
        """
        if not self.client:
            raise Exception("OpenGradient Client not initialized")

        inference_mode = og.LlmInferenceMode.TEE if mode == "TEE" else og.LlmInferenceMode.VANILLA
        
        messages = [
            {
                "role": "system",
                "content": "You are an expert crypto trading analyst. Always respond with valid JSON only, no markdown formatting."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        try:
            tx_hash, finish_reason, message = self.client.llm_chat(
                model_cid=model_cid,
                messages=messages,
                inference_mode=inference_mode,
                max_tokens=800,
                temperature=0.1,
            )
            
            content = message.get("content", "") if isinstance(message, dict) else str(message)
            return tx_hash, content, str(model_cid)
        except Exception as e:
            logger.error(f"OG LLM inference failed: {e}")
            raise e
