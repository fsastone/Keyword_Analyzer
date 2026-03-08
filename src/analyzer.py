import re
import pandas as pd
import numpy as np
from .config import KEYWORD_DICT

# 不需要額外匯入 logging，只需定義 logger
import logging
logger = logging.getLogger("ANALYZER")

class KeywordAnalyzer:
    """關鍵字統計與位置追蹤邏輯"""

    def __init__(self):
        self.keyword_dict = KEYWORD_DICT

    def analyze_document(self, pages_data: list[dict], esg_ranges: dict, keyword_dict: dict = None):
        """
        分析整份文件，統計關鍵字分佈與 ESG 分類統計。
        
        Args:
            pages_data: 包含頁碼與內容的列表 [{'page_num': 1, 'content': '...'}, ...]
            esg_ranges: LLM 識別出的 ESG 章節範圍 {'E': [{'start': 10, 'end': 20}], ...}
            keyword_dict: 概念字典 (若為 None 則使用預設值)
            
        Returns:
            summary_data: 彙總後的列表，包含百分比與 E/S/G 計數
            heatmap_data: 用於熱點矩陣的字典 {Main_Item: {Page_Num: Count}}
        """
        if keyword_dict is None:
            keyword_dict = self.keyword_dict

        # 初始化結果結構
        # results = { (Category, Main_Item): { 'total': 0, 'E': 0, 'S': 0, 'G': 0, 'heatmap': {} } }
        results = {}
        for category, items in keyword_dict.items():
            for main_item, synonyms in items.items():
                results[(category, main_item)] = {
                    'total': 0,
                    'E': 0,
                    'S': 0,
                    'G': 0,
                    'heatmap': {},
                    'variants': [main_item] + synonyms
                }

        # 遍歷每一頁進行統計
        for page in pages_data:
            page_num = page['page_num']
            text = page['content']
            
            # 判斷當前頁面屬於哪個 ESG 區塊 (互斥分配以確保百分比總和為 100%)
            # 若有重疊，優先順序為 E > S > G
            matched_section = None
            for section in ["E", "S", "G"]:
                ranges = esg_ranges.get(section, [])
                if isinstance(ranges, dict):
                    ranges = [ranges]
                
                in_range = False
                for r in ranges:
                    start = r.get('start', 0)
                    end = r.get('end', 0)
                    if start != 0 and start <= page_num <= end:
                        in_range = True
                        break
                
                if in_range:
                    matched_section = section
                    break # 找到第一個匹配即停止，確保互斥
            
            for (category, main_item), data in results.items():
                page_item_count = 0
                for variant in data['variants']:
                    is_english = all(ord(c) < 128 for c in variant)
                    if is_english:
                        pattern = re.compile(rf"\b{re.escape(variant)}\b", re.IGNORECASE | re.ASCII)
                    else:
                        pattern = re.compile(re.escape(variant), re.IGNORECASE)
                    matches = pattern.findall(text)
                    page_item_count += len(matches)
                
                if page_item_count > 0:
                    data['total'] += page_item_count
                    data['heatmap'][page_num] = data['heatmap'].get(page_num, 0) + page_item_count
                    
                    if matched_section:
                        data[matched_section] += page_item_count

        # 整理成彙總摘要與熱點數據
        summary_data = []
        heatmap_final = {}
        
        # 統計各類別的總計
        category_totals = {}

        for (category, main_item), data in results.items():
            total = data['total']
            summary_data.append({
                'Category': category,
                'Main_Keyword': main_item,
                'Total_Count': total,
                'E_Count': data['E'],
                'S_Count': data['S'],
                'G_Count': data['G'],
                'E_%': (data['E'] / total) if total > 0 else 0,
                'S_%': (data['S'] / total) if total > 0 else 0,
                'G_%': (data['G'] / total) if total > 0 else 0,
            })
            heatmap_final[main_item] = data['heatmap']
            
            # 累加到類別總計
            if category not in category_totals:
                category_totals[category] = {'total': 0, 'E': 0, 'S': 0, 'G': 0}
            category_totals[category]['total'] += total
            category_totals[category]['E'] += data['E']
            category_totals[category]['S'] += data['S']
            category_totals[category]['G'] += data['G']

        # 在 summary_data 開頭插入類別總計行
        for category, totals in category_totals.items():
            total = totals['total']
            summary_data.insert(0, {
                'Category': category,
                'Main_Keyword': f"【{category} 總計】",
                'Total_Count': total,
                'E_Count': totals['E'],
                'S_Count': totals['S'],
                'G_Count': totals['G'],
                'E_%': (totals['E'] / total) if total > 0 else 0,
                'S_%': (totals['S'] / total) if total > 0 else 0,
                'G_%': (totals['G'] / total) if total > 0 else 0,
            })

        return summary_data, heatmap_final

    def calculate_metrics(self, df: pd.DataFrame):
        """
        計算統計指標，如 Log 轉換。
        """
        numeric_cols = ['Total_Count', 'E_Count', 'S_Count', 'G_Count']
        for col in numeric_cols:
            if col in df.columns:
                df[f'ln_{col}'] = np.log1p(df[col].astype(float))
        return df
