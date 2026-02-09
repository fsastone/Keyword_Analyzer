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
            
            # 僅顯示路徑末端以保持整潔
            display_path = str(output_path)
            if len(display_path) > 40:
                display_path = "..." + display_path[-37:]
            logger.info(f"報表已生成: {display_path}")
            return output_path
        except Exception as e:
            logger.error(f"報表生成失敗 ({company_name}): {e}")
            return None

    def _apply_heatmap(self, ws, max_row, max_col):
        color_scale_rule = ColorScaleRule(
            start_type='min', start_color='FFFFFF',
            mid_type='percentile', mid_value=50, mid_color='FFFF00',
            end_type='max', end_color='FF0000'
        )
        for row_idx in range(2, max_row + 1):
            addr = f"{get_column_letter(2)}{row_idx}:{get_column_letter(max_col)}{row_idx}"
            ws.conditional_formatting.add(addr, color_scale_rule)