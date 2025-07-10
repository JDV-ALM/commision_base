# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import io
try:
    import xlsxwriter
    XLSXWRITER_AVAILABLE = True
except ImportError:
    XLSXWRITER_AVAILABLE = False
    import logging
    logging.getLogger(__name__).warning('xlsxwriter library is not available')


class CommissionPaymentExportWizard(models.TransientModel):
    _name = 'commission.payment.export.wizard'
    _description = 'Export Commission Payment Document'

    document_id = fields.Many2one(
        'commission.payment.document',
        string='Payment Document',
        required=True,
        readonly=True
    )
    
    export_format = fields.Selection([
        ('xlsx', 'Excel (XLSX)'),
        ('csv', 'CSV'),
    ], string='Export Format', default='xlsx', required=True)
    
    file_data = fields.Binary(
        string='File',
        readonly=True
    )
    file_name = fields.Char(
        string='Filename',
        readonly=True
    )

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if self.env.context.get('active_model') == 'commission.payment.document':
            res['document_id'] = self.env.context.get('active_id')
        return res

    def action_export(self):
        """Export the payment document"""
        self.ensure_one()
        
        if self.export_format == 'xlsx':
            if not XLSXWRITER_AVAILABLE:
                raise UserError(_("xlsxwriter library is not installed. Please install it or use CSV format."))
            return self._export_xlsx()
        else:
            return self._export_csv()

    def _export_xlsx(self):
        """Export to Excel format"""
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
        
        # Create sheet
        sheet = workbook.add_worksheet('Payment Document')
        
        # Headers
        headers = [
            '#',
            'Vendedor',
            'Comisiones',
            'USD Original',
            'USD a Pagar',
            'VES Original', 
            'VES a Pagar'
        ]
        
        # Write headers
        row = 0
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_format)
        
        # Write data
        row = 1
        for idx, line in enumerate(self.document_id.line_ids, 1):
            sheet.write(row, 0, idx)
            sheet.write(row, 1, line.salesperson_id.name)
            sheet.write(row, 2, line.commission_count)
            sheet.write(row, 3, line.amount_usd_original)
            sheet.write(row, 4, line.amount_usd_payment)
            sheet.write(row, 5, line.amount_ves_original)
            sheet.write(row, 6, line.amount_ves_payment)
            row += 1
        
        workbook.close()
        output.seek(0)
        
        # Save file
        self.file_data = base64.b64encode(output.getvalue())
        self.file_name = f"Documento_Pago_{self.document_id.name}.xlsx"
        
        # Return download action
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/file_data/{self.file_name}?download=true',
            'target': 'self',
        }

    def _export_csv(self):
        """Export to CSV format"""
        output = io.StringIO()
        
        # Headers
        headers = ['Vendedor', 'Comisiones', 'USD Original', 'USD a Pagar', 'VES Original', 'VES a Pagar']
        output.write(','.join(headers) + '\n')
        
        # Data
        for line in self.document_id.line_ids:
            row = [
                line.salesperson_id.name,
                str(line.commission_count),
                str(line.amount_usd_original),
                str(line.amount_usd_payment),
                str(line.amount_ves_original),
                str(line.amount_ves_payment)
            ]
            output.write(','.join(row) + '\n')
        
        # Save file
        self.file_data = base64.b64encode(output.getvalue().encode())
        self.file_name = f"Documento_Pago_{self.document_id.name}.csv"
        
        # Return download action
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/file_data/{self.file_name}?download=true',
            'target': 'self',
        }