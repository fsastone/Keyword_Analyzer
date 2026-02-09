from google import genai
from google.genai import types
from .config import GEMINI_API_KEY, GEMINI_MODEL_NAME
import logging
import json

logger = logging.getLogger(__name__)

class LLMService:
    """Gemini API 封裝，用於處理文件分段與分析"""
    
    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("未設定 GOOGLE_API_KEY 環境變數")
        self.client = genai.Client(api_key=GEMINI_API_KEY)

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
            return response.parsed
        except Exception as e:
            logger.error(f"LLM 分段失敗: {e}")
            return None
