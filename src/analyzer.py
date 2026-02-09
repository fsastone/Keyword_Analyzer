import re
import pandas as pd
import numpy as np
from .config import KEYWORDS

class KeywordAnalyzer:
    """關鍵字統計與位置追蹤邏輯"""

    def __init__(self):
        self.keywords = KEYWORDS

    def analyze_with_positions(self, pages_data: list):
        """
        分析關鍵字在每一頁的分布，並擷取上下文
        """
        page_hits = []    # 記錄 (關鍵字, 頁碼, 次數)
        evidence = []     # 記錄 (關鍵字, 頁碼, 上下文摘要)
        
        # 展平所有關鍵字清單
        flat_keywords = [kw for sublist in self.keywords.values() for kw in sublist]
        
        for page in pages_data:
            page_num = page['page_num']
            text = page['content']
            
            for kw in flat_keywords:
                # 匹配邏輯
                is_english = all(ord(c) < 128 for c in kw)
                if is_english:
                    pattern = re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE | re.ASCII)
                else:
                    pattern = re.compile(re.escape(kw), re.IGNORECASE)
                
                matches = pattern.finditer(text)
                match_count = 0
                
                for m in matches:
                    match_count += 1
                    # 擷取上下文 (前後 30 個字)
                    start = max(0, m.start() - 30)
                    end = min(len(text), m.end() + 30)
                    context = text[start:end].replace("\n", " ")
                    
                    if match_count <= 3: # 每個關鍵字每頁最多記錄 3 個證據，避免報表過大
                        evidence.append({
                            'Keyword': kw,
                            'Page': page_num,
                            'Context': f"...{context}..."
                        })
                
                if match_count > 0:
                    page_hits.append({
                        'Keyword': kw,
                        'Page': page_num,
                        'Count': match_count
                    })
        
        return pd.DataFrame(page_hits), pd.DataFrame(evidence)

    def calculate_metrics(self, df: pd.DataFrame):
        """計算原本的統計指標"""
        kw_cols = [col for col in df.columns if col not in ['company', 'total_pages']]
        for col in kw_cols:
            df[f'ln_{col}'] = np.log1p(df[col].astype(float))
        df['dist_skewness'] = df[kw_cols].skew(axis=1)
        df['total_mentions'] = df[kw_cols].sum(axis=1)
        return df