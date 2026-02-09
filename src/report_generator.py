import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Color
from openpyxl.formatting.rule import ColorScaleRule
from .config import OUTPUT_DIR, REPORT_FILENAME
import logging

logger = logging.getLogger(__name__)

class ReportGenerator:
    """生成 Excel 報表與熱點圖"""

    def __init__(self):
        self.output_path = OUTPUT_DIR / REPORT_FILENAME

    def generate(self, df: pd.DataFrame):
        """
        將 DataFrame 寫入 Excel 並套用格式
        """
        try:
            with pd.ExcelWriter(self.output_path, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Keyword Analysis')
                
                # 取得工作表
                workbook = writer.book
                worksheet = writer.sheets['Keyword Analysis']
                
                # 套用色階熱點 (Heatmap)
                # 假設從 B2 到最後一格是數據區
                # 這裡簡單對數值欄位套用
                max_row = worksheet.max_row
                max_col = worksheet.max_column
                
                # 建立三色色階規則 (白 -> 黃 -> 紅)
                color_scale_rule = ColorScaleRule(
                    start_type='min', start_color='FFFFFF',
                    mid_type='percentile', mid_value=50, mid_color='FFFF00',
                    end_type='max', end_color='FF0000'
                )
                
                # 找出數值欄位的範圍並套用 (略過第一欄公司名)
                from openpyxl.utils import get_column_letter
                for col_idx in range(2, max_col + 1):
                    col_letter = get_column_letter(col_idx)
                    addr = f"{col_letter}2:{col_letter}{max_row}"
                    worksheet.conditional_formatting.add(addr, color_scale_rule)
            
            logger.info(f"報表已生成: {self.output_path}")
            return self.output_path
        except Exception as e:
            logger.error(f"生成報表失敗: {e}")
            return None
