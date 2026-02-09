import re
import pandas as pd
import numpy as np
from .config import KEYWORDS

# 不需要額外匯入 logging，只需定義 logger
import logging
logger = logging.getLogger("ANALYZER")

class KeywordAnalyzer:
    """關鍵字統計與位置追蹤邏輯"""

    def __init__(self):
        self.keywords = KEYWORDS
        # 建立反向查詢字典: { '再生能源': 'Environmental', 'AI': 'Tech/Innovation' }
        self.kw_to_category = {}
        for cat, kws in self.keywords.items():
            for kw in kws:
                self.kw_to_category[kw] = cat

    def analyze_with_positions(self, pages_data: list):
        """分析關鍵字在每一頁的分布，並擷取上下文與分類"""
        page_hits = []
        evidence = []
        
        flat_keywords = [kw for sublist in self.keywords.values() for kw in sublist]
        
        for page in pages_data:
            page_num = page['page_num']
            text = page['content']
            
            for kw in flat_keywords:
                is_english = all(ord(c) < 128 for c in kw)
                pattern = re.compile(rf"\b{re.escape(kw)}\b" if is_english else re.escape(kw), re.IGNORECASE)
                
                matches = list(pattern.finditer(text))
                if matches:
                    # 1. 記錄次數
                    page_hits.append({'Keyword': kw, 'Page': page_num, 'Count': len(matches)})
                    
                    # 2. 記錄證據與分類
                    category = self.kw_to_category.get(kw, "Unknown")
                    for m in matches[:3]: # 每頁最多 3 筆證據
                        start = max(0, m.start() - 40)
                        end = min(len(text), m.end() + 40)
                        context = text[start:end].replace("\n", " ")
                        evidence.append({
                            'Keyword': kw,
                            'Category': category, # 新增分類標籤
                            'Page': page_num,
                            'Context': f"...{context}..."
                        })
        
        return pd.DataFrame(page_hits), pd.DataFrame(evidence)

    def calculate_metrics(self, df: pd.DataFrame):
        kw_cols = [col for col in df.columns if col not in ['company', 'total_pages']]
        for col in kw_cols:
            df[f'ln_{col}'] = np.log1p(df[col].astype(float))
        df['dist_skewness'] = df[kw_cols].skew(axis=1)
        df['total_mentions'] = df[kw_cols].sum(axis=1)
        return df
