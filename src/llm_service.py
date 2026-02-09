from google import genai
from google.genai import types
from .config import GEMINI_API_KEY, GEMINI_MODEL_NAME
import logging

logger = logging.getLogger("GEMINI_API")

class LLMService:
    """Gemini API 封裝，支持 Token 使用量統計"""
    
    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("未設定 GOOGLE_API_KEY 環境變數")
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.total_prompt_tokens = 0
        self.total_candidate_tokens = 0

    def segment_chapters(self, text_preview: str):
        """
        利用 LLM 分析目錄或前幾頁，識別 E、S、G 各章節的範圍。
        """
        prompt = f"""
        以下是一份 ESG 報告的前幾頁內容，請協助我識別出：
        1. 環境 (Environmental, E) 相關章節標題
        2. 社會 (Social, S) 相關章節標題
        3. 公司治理 (Governance, G) 相關章節標題

        報告內容：
        {text_preview}
        """
        
        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {
                            "Environmental": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "Social": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "Governance": {"type": "ARRAY", "items": {"type": "STRING"}}
                        }
                    }
                )
            )
            
            # 累加 Token 使用量
            usage = response.usage_metadata
            self.total_prompt_tokens += usage.prompt_token_count
            self.total_candidate_tokens += usage.candidates_token_count
            
            return response.parsed, usage
        except Exception as e:
            logger.error(f"LLM 分段失敗: {e}")
            return None, None

    def get_usage_report(self):
        """獲取累計 Token 報告"""
        return {
            "Prompt Tokens": self.total_prompt_tokens,
            "Completion Tokens": self.total_candidate_tokens,
            "Total Tokens": self.total_prompt_tokens + self.total_candidate_tokens
        }