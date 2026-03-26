from google import genai
from google.genai import types
from .config import GEMINI_API_KEY, GEMINI_MODEL_NAME
import logging

logger = logging.getLogger("GEMINI")

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
            p_tokens = usage.prompt_token_count or 0
            c_tokens = usage.candidates_token_count or 0
            
            self.total_prompt_tokens += p_tokens
            self.total_candidate_tokens += c_tokens
            
            return response.parsed, {
                "prompt": p_tokens,
                "completion": c_tokens,
                "total": p_tokens + c_tokens
            }
        except Exception as e:
            logger.error(f"LLM 分段失敗: {e}")
            return None, None

    def parse_esg_toc(self, toc_text: str, total_pdf_pages: int, mapping: dict = None) -> dict:
        """
        利用 LLM 分析 PDF 前面頁面文字，識別 E、S、G 章節的頁碼範圍。
        """
        # 尋找合理的最後一頁邏輯頁碼
        max_logical_page = total_pdf_pages
        if mapping:
            sorted_p = sorted(mapping.values())
            if sorted_p:
                last_physical = sorted_p[-1]
                # 如果最後一個物理點已經接近總頁數，則使用對應的邏輯頁碼
                if last_physical >= total_pdf_pages * 0.9:
                    max_logical_page = max(mapping.keys())
                else:
                    # 否則根據斜率推算
                    l_vals = sorted(mapping.keys())
                    if len(l_vals) >= 2:
                        slope = (l_vals[-1] - l_vals[0]) / (mapping[l_vals[-1]] - mapping[l_vals[0]])
                        max_logical_page = int(l_vals[-1] + (total_pdf_pages - last_physical) * slope)

        prompt = f"""
        你是一位專業的 ESG 報告分析師。請從以下目錄 (TOC) 內容中，精確識別出環境 (E)、社會 (S) 及公司治理 (G) 各類別所對應的**報告邏輯頁碼**範圍。

        【分析目標】
        1. 根據目錄標題關鍵字分配報告中所標註的頁碼（邏輯頁碼）。
        2. **盡可能識別出所有大章節與二級子章節的起始頁碼**，這有助於定位。
        3. 起始頁碼為目錄中該章節標註的數字。
        4. 結束頁碼應為「下一個同級或更高層級章節起始頁碼減 1」。報告最後一頁為第 {max_logical_page} 頁。
        5. **重要規則：互斥性**。各類別 (E/S/G) 之間的頁碼範圍**絕對不能重疊**。請根據章節順序嚴格分配。
        
        【ESG分類準則】
        環境, Environmental (E):
        - SDG 6: Clean Water and Sanitation (水資源管理、污染防治)
        - SDG 7: Affordable and Clean Energy (綠能、能源轉型)
        - SDG 12: Responsible Consumption and Production (循環經濟、廢棄物管理、綠色產品)
        - SDG 13: Climate Action (溫室氣體盤查、減碳策略、氣候變遷)
        - SDG 14: Life Below Water (海洋生態保育)
        - SDG 15: Life on Land (陸地生態與生物多樣性)
        社會, Social (S):
        - SDG 1 & 2: No Poverty & Zero Hunger (社會公益、弱勢關懷)
        - SDG 3: Good Health and Well-being (員工健康、職場安全、友善職場)
        - SDG 4: Quality Education (人才培育、產學合作、教育科技)
        - SDG 5: Gender Equality (多元包容 DEI、女性主管比例)
        - SDG 8: Decent Work and Economic Growth (勞動權益、薪資福利)
        - SDG 10: Reduced Inequalities (人權保障、無歧視)
        公司治理, Governance (G):
        - SDG 9: Industry, Innovation and Infrastructure (研發創新、資安管理、數位轉型)
        - SDG 11: Sustainable Cities and Communities (企業營運韌性、在地深耕)
        - SDG 16: Peace, Justice and Strong Institutions (公司治理、誠信經營、法規遵循、風險管理)
        - SDG 17: Partnerships for the Goals (供應鏈管理、供應商稽核、利害關係人議合)
        - Others: 報告前言、編輯摘要、公司簡介、營運狀況、組織架構、董事長的話、執行長的話接歸類為 G 類別。

        【輸出格式】
        必須輸出 JSON，包含 "analysis" 以及 E, S, G 的邏輯頁碼範圍。
        範例：
        {{
          "analysis": "CH4(94-109)屬G；CH5(102-161)屬E；CH6(162-193)屬S；CH7(194-213)屬G...",
          "E": [ {{"start": 102, "end": 161}} ], 
          "S": [ {{"start": 162, "end": 193}}, {{"start": 214, "end": 255}} ], 
          "G": [ {{"start": 14, "end": 101}}, {{"start": 194, "end": 213}} ]
        }}

        【待分析文本內容 (可能包含亂碼或換行錯誤，請根據上下文理解)】
        {toc_text}
        """
        
        try:
            range_schema = {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "start": {"type": "INTEGER"},
                        "end": {"type": "INTEGER"}
                    },
                    "required": ["start", "end"]
                }
            }
            
            response = self.client.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {
                            "analysis": {"type": "STRING"},
                            "E": range_schema,
                            "S": range_schema,
                            "G": range_schema
                        },
                        "required": ["analysis", "E", "S", "G"]
                    }
                )
            )
            
            # 累加 Token 使用量
            usage = response.usage_metadata
            self.total_prompt_tokens += usage.prompt_token_count or 0
            self.total_candidate_tokens += usage.candidates_token_count or 0
            
            # 獲取 JSON 結果
            result = response.parsed
            logger.info(f"LLM TOC 邏輯頁碼分析結果: {result.get('analysis')}")
            
            if mapping:
                logger.info(f"頁碼映射摘要: {sorted(mapping.items())[:3]} ... {sorted(mapping.items())[-2:]}")

            # 準備存儲物理範圍
            section_physical_ranges = {"E": [], "S": [], "G": []}
            
            # 1. 邏輯轉物理
            for sec_key in ["E", "S", "G"]:
                logical_ranges = result.get(sec_key, [])
                for r in logical_ranges:
                    l_start = r.get("start", 0)
                    l_end = r.get("end", 0)
                    p_start = self._map_to_physical(l_start, mapping, total_pdf_pages)
                    p_end = self._map_to_physical(l_end, mapping, total_pdf_pages)
                    if 0 < p_start <= p_end <= total_pdf_pages:
                        section_physical_ranges[sec_key].append({"start": p_start, "end": p_end})

            # 2. 合併各類別內部的範圍
            for sec_key in ["E", "S", "G"]:
                section_physical_ranges[sec_key] = self._merge_ranges(section_physical_ranges[sec_key])

            # 3. 處理跨類別衝突 (互斥性)
            all_ranges = []
            for sec_key in ["E", "S", "G"]:
                for r in section_physical_ranges[sec_key]:
                    all_ranges.append({"section": sec_key, "start": r["start"], "end": r["end"]})
            
            all_ranges.sort(key=lambda x: x["start"])
            
            for i in range(len(all_ranges) - 1):
                curr = all_ranges[i]
                nxt = all_ranges[i+1]
                if curr["end"] >= nxt["start"]:
                    logger.warning(f"檢測到類別衝突: {curr['section']} 與 {nxt['section']} 重疊於 {curr['end']} 頁。已強制切分。")
                    curr["end"] = nxt["start"] - 1

            # 4. 寫回最終結果並執行前言擴展
            final_result = {"analysis": result.get("analysis"), "E": [], "S": [], "G": []}
            for r in all_ranges:
                if r["start"] <= r["end"]:
                    final_result[r["section"]].append({"start": r["start"], "end": r["end"]})

            # 自動擴展第一個類別到第 1 頁
            all_starts = []
            for sec_key in ["E", "S", "G"]:
                for r in final_result[sec_key]:
                    all_starts.append(r["start"])
            
            if all_starts:
                min_p_start = min(all_starts)
                if min_p_start > 1:
                    for sec_key in ["E", "S", "G"]:
                        for r in final_result[sec_key]:
                            if r['start'] == min_p_start:
                                logger.info(f"自動擴展 {sec_key} 類別至第 1 頁。")
                                r['start'] = 1
                                break
            
            for sec_key in ["E", "S", "G"]:
                if final_result[sec_key]:
                    logger.info(f"{sec_key} 物理範圍: {final_result[sec_key]}")
            
            return final_result
            
        except Exception as e:
            logger.error(f"LLM 解析 TOC 失敗: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"analysis": "Error", "E": [], "S": [], "G": []}

    def _merge_ranges(self, ranges: list) -> list:
        """合併重疊或相鄰的頁碼範圍"""
        if not ranges:
            return []
        # 按起始頁碼排序
        sorted_ranges = sorted(ranges, key=lambda x: x['start'])
        merged = [dict(sorted_ranges[0])]
        for current in sorted_ranges[1:]:
            prev = merged[-1]
            if current['start'] <= prev['end'] + 1:
                prev['end'] = max(prev['end'], current['end'])
            else:
                merged.append(dict(current))
        return merged

    def _map_to_physical(self, logical_page: int, mapping: dict, total_pdf_pages: int) -> int:
        """將報告印出的頁碼轉換為 PDF 檔案的實際頁碼，採用局部插值法"""
        if logical_page is None or logical_page <= 0:
            return 0
        
        if not mapping:
            if logical_page > total_pdf_pages * 1.1:
                return max(1, min(int(logical_page / 2), total_pdf_pages))
            return max(1, min(logical_page, total_pdf_pages))

        sorted_logical = sorted(mapping.keys())
        if logical_page in mapping:
            return mapping[logical_page]
            
        lower_idx = -1
        for i, l_val in enumerate(sorted_logical):
            if l_val < logical_page:
                lower_idx = i
            else:
                break
        
        if lower_idx == -1:
            first_l = sorted_logical[0]
            first_p = mapping[first_l]
            if first_l > 1:
                if first_p <= 1: return 1
                slope = (first_p - 1) / (first_l - 1)
                est_p = 1 + (logical_page - 1) * slope
                return max(1, min(int(est_p), total_pdf_pages))
            return first_p
            
        if lower_idx == len(sorted_logical) - 1:
            last_l = sorted_logical[-1]
            last_p = mapping[last_l]
            # 嘗試使用最後一段的斜率
            if len(sorted_logical) >= 2:
                prev_l = sorted_logical[-2]
                prev_p = mapping[prev_l]
                slope = (last_p - prev_p) / (last_l - prev_l)
            else:
                is_2up = sorted_logical[-1] > total_pdf_pages * 1.1
                slope = 0.5 if is_2up else 1.0
            
            slope = max(0.3, min(2.0, slope))
            est_p = last_p + (logical_page - last_l) * slope
            return max(1, min(int(est_p), total_pdf_pages))
            
        l1, l2 = sorted_logical[lower_idx], sorted_logical[lower_idx+1]
        p1, p2 = mapping[l1], mapping[l2]
        if l2 != l1:
            slope = (p2 - p1) / (l2 - l1)
            slope = max(0.3, min(2.0, slope))
            est_p = p1 + (logical_page - l1) * slope
            return max(1, min(int(est_p), total_pdf_pages))
        return p1

    def get_usage_report(self):
        """獲取累計 Token 報告"""
        return {
            "Prompt Tokens": self.total_prompt_tokens,
            "Completion Tokens": self.total_candidate_tokens,
            "Total Tokens": self.total_prompt_tokens + self.total_candidate_tokens
        }