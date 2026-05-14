"""Advanced Office helpers: Excel formula support and optional Excel COM automation."""
try:
    import openpyxl
except Exception:
    openpyxl = None


def create_excel_with_formulas(path: str, rows: list) -> bool:
    """Create an Excel file where cell values starting with '=' are treated as formulas.
    Returns True on success.
    """
    try:
        if openpyxl is None:
            # fallback: write CSV but formulas won't evaluate
            import csv
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(rows)
            return True
        wb = openpyxl.Workbook()
        ws = wb.active
        for r_idx, row in enumerate(rows, start=1):
            for c_idx, val in enumerate(row, start=1):
                cell = ws.cell(row=r_idx, column=c_idx)
                if isinstance(val, str) and val.startswith('='):
                    cell.value = val  # openpyxl treats strings starting with = as formulas
                else:
                    cell.value = val
        wb.save(path)
        return True
    except Exception:
        return False


def create_excel_and_open_in_excel(path: str, rows: list) -> bool:
    """Create the Excel file and, if on Windows with pywin32, open Excel, recalc and save.
    Returns True if file created (and optionally processed by Excel)."""
    ok = create_excel_with_formulas(path, rows)
    if not ok:
        return False

    # Try COM automation to let Excel evaluate formulas and save
    try:
        import platform
        if platform.system().lower() != 'windows':
            return True
        try:
            import win32com.client
        except Exception:
            return True
        xl = win32com.client.DispatchEx('Excel.Application')
        xl.Visible = False
        wb = xl.Workbooks.Open(path)
        try:
            # Recalculate and save
            xl.CalculateFull()
            wb.Save()
        finally:
            wb.Close(SaveChanges=True)
            xl.Quit()
        return True
    except Exception:
        return True
