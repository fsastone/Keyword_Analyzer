import pandas as pd
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule
from .config import OUTPUT_DIR
import logging

logger = logging.getLogger("REPORTER")

class ReportGenerator:
    """針對單一 PDF 生成專業報表"""

    def __init__(self):
        self.output_dir = OUTPUT_DIR

    def generate(self, company_name, summary_df, heatmap_df, evidence_df, chapter_df):
        """
        為特定的公司生成獨立報表
        """
        output_path = self.output_dir / f"{company_name}_analysis.xlsx"
        
        try:
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                # 1. Summary
                summary_df.to_excel(writer, index=False, sheet_name='Summary')
                
                # 2. Report Structure
                if not chapter_df.empty:
                    chapter_df.to_excel(writer, index=False, sheet_name='Report_Chapters')
                
                # 3. Hotspot Matrix
                if not heatmap_df.empty:
                    # 獲取摘要頁中的所有關鍵字 (排除統計指標)
                    all_keywords = [col for col in summary_df.columns if col not in ['company', 'total_pages'] and not col.startswith('ln_') and col not in ['dist_skewness', 'total_mentions']]
                    
                    matrix = heatmap_df.pivot_table(
                        index='Keyword', columns='Page', values='Count', fill_value=0
                    )
                    
                    # 強制重新索引，確保所有關鍵字都出現在矩陣中
                    matrix = matrix.reindex(all_keywords, fill_value=0)
                    
                    matrix.to_excel(writer, sheet_name='Hotspot_Matrix')
                    self._apply_heatmap(writer.sheets['Hotspot_Matrix'], matrix.shape[0]+1, matrix.shape[1]+1)
                
                # 4. Context Evidence
                if not evidence_df.empty:
                    evidence_df.to_excel(writer, index=False, sheet_name='Context_Evidence')
            
            display_path = str(output_path)
            if len(display_path) > 40:
                display_path = "..." + display_path[-37:]
            logger.info(f"報表已生成: {display_path}")
            return output_path
        except Exception as e:
            logger.error(f"報表生成失敗 ({company_name}): {e}")
            return None

    def _apply_heatmap(self, ws, max_row, max_col):
        """套用 Excel 色階格式：按列(Row)進行分析，並跳過全為 0 的列"""
        color_scale_rule = ColorScaleRule(
            start_type='num', start_value=0, start_color='FFFFFF', # 0 為白色
            mid_type='percentile', mid_value=50, mid_color='FFFF00', # 50% 為黃色
            end_type='max', end_color='FF0000' # 最大值為紅色
        )
        
        for row_idx in range(2, max_row + 1):
            # 檢查該列的值，確定最大值是否大於 0
            row_max = 0
            for col_idx in range(2, max_col + 1):
                val = ws.cell(row=row_idx, column=col_idx).value
                if val and isinstance(val, (int, float)):
                    if val > row_max:
                        row_max = val
            
            # 如果整列最大值是 0，則不需要套用色階 (保持白色)
            if row_max == 0:
                continue
                
            first_col = get_column_letter(2)
            last_col = get_column_letter(max_col)
            addr = f"{first_col}{row_idx}:{last_col}{row_idx}"
            ws.conditional_formatting.add(addr, color_scale_rule)
