# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request, content_disposition
from odoo.exceptions import AccessError
import io
import xlsxwriter
from datetime import datetime


class CommissionBandController(http.Controller):
    
    @http.route('/commission_band/payment_document/<int:document_id>/export', type='http', auth='user')
    def export_payment_document(self, document_id, **kwargs):
        """Export payment document to Excel"""
        
        # Check access rights
        try:
            document = request.env['commission.payment.document'].browse(document_id)
            document.check_access_rights('read')
            document.check_access_rule('read')
        except AccessError:
            return request.not_found()
        
        if not document.exists():
            return request.not_found()
        
        # Create Excel file in memory
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        # Define formats
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 16,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#003366',
            'font_color': 'white'
        })
        
        header_format = workbook.add_format({
            'bold': True,
            'font_size': 12,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1
        })
        
        subheader_format = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'bg_color': '#D9E2F3',
            'border': 1
        })
        
        data_format = workbook.add_format({
            'align': 'left',
            'valign': 'vcenter',
            'border': 1
        })
        
        number_format = workbook.add_format({
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '#,##0.00'
        })
        
        date_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'num_format': 'dd/mm/yyyy'
        })
        
        total_format = workbook.add_format({
            'bold': True,
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '#,##0.00',
            'bg_color': '#F2F2F2'
        })
        
        # Create main sheet
        sheet = workbook.add_worksheet('Payment Document')
        
        # Set column widths
        sheet.set_column('A:A', 5)   # #
        sheet.set_column('B:B', 40)  # Salesperson
        sheet.set_column('C:C', 15)  # Commissions
        sheet.set_column('D:E', 20)  # USD amounts
        sheet.set_column('F:G', 20)  # VES amounts
        sheet.set_column('H:H', 20)  # Total
        
        # Title
        sheet.merge_range('A1:H1', f'DOCUMENTO DE PAGO DE COMISIONES - {document.name}', title_format)
        sheet.set_row(0, 30)
        
        # Document info
        row = 2
        sheet.write(row, 1, 'Lote:', subheader_format)
        sheet.write(row, 2, document.batch_id.name, data_format)
        sheet.write(row, 4, 'Fecha de Pago:', subheader_format)
        sheet.write(row, 5, document.payment_date, date_format)
        row += 1
        
        sheet.write(row, 1, 'Período:', subheader_format)
        sheet.write(row, 2, f"{document.batch_id.date_from.strftime('%d/%m/%Y')} - {document.batch_id.date_to.strftime('%d/%m/%Y')}", data_format)
        sheet.write(row, 4, 'Tasa USD/VES:', subheader_format)
        sheet.write(row, 5, document.exchange_rate_usd_ves or 1.0, number_format)
        row += 2
        
        # Headers
        headers = [
            '#',
            'Vendedor',
            'Cant. Comisiones',
            'USD Original',
            'USD a Pagar',
            'VES Original',
            'VES a Pagar',
            'Total a Pagar'
        ]
        
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)
        row += 1
        
        # Data rows
        line_number = 1
        total_usd_original = 0
        total_usd_payment = 0
        total_ves_original = 0
        total_ves_payment = 0
        total_payment = 0
        
        for line in document.line_ids.sorted('salesperson_id'):
            sheet.write(row, 0, line_number, data_format)
            sheet.write(row, 1, line.salesperson_id.name, data_format)
            sheet.write(row, 2, line.commission_count, data_format)
            sheet.write(row, 3, line.amount_usd_original, number_format)
            sheet.write(row, 4, line.amount_usd_payment, number_format)
            sheet.write(row, 5, line.amount_ves_original, number_format)
            sheet.write(row, 6, line.amount_ves_payment, number_format)
            sheet.write(row, 7, line.total_payment, number_format)
            
            total_usd_original += line.amount_usd_original
            total_usd_payment += line.amount_usd_payment
            total_ves_original += line.amount_ves_original
            total_ves_payment += line.amount_ves_payment
            total_payment += line.total_payment
            
            line_number += 1
            row += 1
        
        # Totals
        sheet.write(row, 1, 'TOTALES:', total_format)
        sheet.write(row, 2, document.total_lines, total_format)
        sheet.write(row, 3, total_usd_original, total_format)
        sheet.write(row, 4, total_usd_payment, total_format)
        sheet.write(row, 5, total_ves_original, total_format)
        sheet.write(row, 6, total_ves_payment, total_format)
        sheet.write(row, 7, total_payment, total_format)
        
        # Create detail sheet
        detail_sheet = workbook.add_worksheet('Detalle por Vendedor')
        
        # Detail headers
        detail_headers = [
            'Vendedor',
            'Cliente',
            'Factura',
            'Fecha Factura',
            'Fecha Vencimiento',
            'Fecha Pago',
            'Días Vencidos',
            'Monto Pago',
            'Moneda',
            '% Comisión',
            'Monto Comisión'
        ]
        
        # Set column widths for detail sheet
        detail_sheet.set_column('A:A', 30)  # Salesperson
        detail_sheet.set_column('B:B', 40)  # Customer
        detail_sheet.set_column('C:C', 20)  # Invoice
        detail_sheet.set_column('D:F', 15)  # Dates
        detail_sheet.set_column('G:G', 12)  # Days
        detail_sheet.set_column('H:H', 18)  # Amount
        detail_sheet.set_column('I:I', 10)  # Currency
        detail_sheet.set_column('J:J', 12)  # Rate
        detail_sheet.set_column('K:K', 18)  # Commission
        
        # Title
        detail_sheet.merge_range('A1:K1', 'DETALLE DE COMISIONES POR VENDEDOR', title_format)
        detail_sheet.set_row(0, 30)
        
        # Headers
        row = 2
        for col, header in enumerate(detail_headers):
            detail_sheet.write(row, col, header, header_format)
        row += 1
        
        # Detail data grouped by salesperson
        for line in document.line_ids.sorted('salesperson_id'):
            # Salesperson header
            detail_sheet.merge_range(row, 0, row, 10, line.salesperson_id.name, subheader_format)
            row += 1
            
            # Commission details
            for calc in line.calculation_ids.sorted('payment_date'):
                detail_sheet.write(row, 0, line.salesperson_id.name, data_format)
                detail_sheet.write(row, 1, calc.partner_id.name, data_format)
                detail_sheet.write(row, 2, calc.invoice_id.name, data_format)
                detail_sheet.write(row, 3, calc.invoice_date, date_format)
                detail_sheet.write(row, 4, calc.due_date, date_format)
                detail_sheet.write(row, 5, calc.payment_date, date_format)
                detail_sheet.write(row, 6, calc.days_overdue, data_format)
                detail_sheet.write(row, 7, calc.payment_amount, number_format)
                detail_sheet.write(row, 8, calc.currency_id.name, data_format)
                detail_sheet.write(row, 9, f"{calc.commission_rate}%", data_format)
                detail_sheet.write(row, 10, calc.commission_amount, number_format)
                row += 1
            
            # Subtotal for salesperson
            detail_sheet.write(row, 9, f'Subtotal {line.salesperson_id.name}:', total_format)
            detail_sheet.write(row, 10, sum(line.calculation_ids.mapped('commission_amount')), total_format)
            row += 2
        
        # Close workbook
        workbook.close()
        
        # Prepare response
        output.seek(0)
        filename = f"Documento_Pago_{document.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return request.make_response(
            output.getvalue(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', content_disposition(filename))
            ]
        )