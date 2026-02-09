import re
import pandas as pd
import numpy as np
from collections import Counter
from .config import KEYWORDS

class KeywordAnalyzer:
    """關鍵字統計與熱點分析邏輯"""

    def __init__(self):
        self.keywords = KEYWORDS

    def count_keywords(self, text: str):
        """
        在文本中統計各類別關鍵字出現次數
        """
        results = {}
        for category, kws in self.keywords.items():
            category_counts = {}
            for kw in kws:
                # 針對中英文採用不同 Regex 策略
                is_english = all(ord(c) < 128 for c in kw)
                if is_english:
                    # 英文：使用邊界匹配，忽略大小寫
                    pattern = re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE | re.ASCII)
                else:
                    # 中文：直接匹配
                    pattern = re.compile(re.escape(kw), re.IGNORECASE)
                
                matches = pattern.findall(text)
                category_counts[kw] = len(matches)
            results[category] = category_counts
        return results

    def calculate_metrics(self, df: pd.DataFrame):
        """
        計算進階指標：Ln(Freq+1), Skewness 等
        """
        # 展平字典結構以進行運算
        # 假設 df 的欄位是各個關鍵字
        
        # 1. Ln(x+1) 轉換
        kw_cols = [col for col in df.columns if col not in ['company', 'category']]
        for col in kw_cols:
            df[f'ln_{col}'] = np.log1p(df[col].astype(float))
        
        # 2. 計算偏態 (Skewness)
        df['dist_skewness'] = df[kw_cols].skew(axis=1)
        
        # 3. 總聲量
        df['total_mentions'] = df[kw_cols].sum(axis=1)
        
        return df

    def get_category_summary(self, detailed_results):
        """
        彙整各類別的總分
        """
        summary = {}
        for category, counts in detailed_results.items():
            summary[category] = sum(counts.values())
        return summary
