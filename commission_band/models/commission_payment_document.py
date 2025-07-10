# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class CommissionPaymentDocument(models.Model):
    _name = 'commission.payment.document'
    _description = 'Commission Payment Document'
    _order = 'payment_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(
        string='Document Number',
        required=True,
        readonly=True,
        default='New',
        copy=False
    )
    
    # Relations
    batch_id = fields.Many2one(
        'commission.batch',
        string='Commission Batch',
        required=True,
        ondelete='cascade',
        readonly=True
    )
    line_ids = fields.One2many(
        'commission.payment.line',
        'document_id',
        string='Payment Lines',
        readonly=True
    )
    
    # Dates
    payment_date = fields.Date(
        string='Payment Date',
        required=True,
        tracking=True,
        help="Date when commissions will be paid (used for currency conversion)"
    )
    generation_date = fields.Datetime(
        string='Generation Date',
        default=fields.Datetime.now,
        readonly=True
    )
    
    # State
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('paid', 'Paid')
    ], string='State', default='draft', required=True, tracking=True)
    
    # Company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    
    # Totals
    total_lines = fields.Integer(
        string='Total Lines',
        compute='_compute_totals',
        store=True
    )
    total_salespersons = fields.Integer(
        string='Total Salespersons',
        compute='_compute_totals',
        store=True
    )
    
    # Exchange rates used
    exchange_rate_usd_ves = fields.Float(
        string='USD to VES Rate',
        digits=(16, 6),
        readonly=True,
        help="Exchange rate used for USD to VES conversion"
    )
    
    # Total fields for summary
    total_usd_original = fields.Float(
        string='Total USD Original',
        compute='_compute_totals',
        digits=(16, 2),
        help="Total commission amount originally in USD"
    )
    total_ves_original = fields.Float(
        string='Total VES Original',
        compute='_compute_totals',
        digits=(16, 2),
        help="Total commission amount originally in VES"
    )
    total_usd_payment = fields.Float(
        string='Total USD Payment',
        compute='_compute_totals',
        digits=(16, 2),
        help="Total amount to pay in USD"
    )
    total_ves_payment = fields.Float(
        string='Total VES Payment',
        compute='_compute_totals',
        digits=(16, 2),
        help="Total amount to pay in VES"
    )
    
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            IrSequence = self.env['ir.sequence'].sudo()
            vals['name'] = IrSequence.next_by_code('commission.payment.document') or 'New'
        return super().create(vals)

    @api.depends('line_ids', 'line_ids.amount_usd_original', 'line_ids.amount_ves_original',
                 'line_ids.amount_usd_payment', 'line_ids.amount_ves_payment')
    def _compute_totals(self):
        for doc in self:
            doc.total_lines = len(doc.line_ids)
            doc.total_salespersons = len(doc.line_ids.mapped('salesperson_id'))
            
            # Calculate totals
            doc.total_usd_original = sum(doc.line_ids.mapped('amount_usd_original'))
            doc.total_ves_original = sum(doc.line_ids.mapped('amount_ves_original'))
            doc.total_usd_payment = sum(doc.line_ids.mapped('amount_usd_payment'))
            doc.total_ves_payment = sum(doc.line_ids.mapped('amount_ves_payment'))

    def _generate_payment_lines(self):
        """Generate payment lines from batch calculations"""
        self.ensure_one()
        
        if self.line_ids:
            raise UserError(_("Payment lines already generated for this document."))
        
        # Get exchange rate for payment date
        usd = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
        ves = self.env['res.currency'].search([('name', '=', 'VES')], limit=1)
        
        if usd and ves:
            self.exchange_rate_usd_ves = usd._get_conversion_rate(
                usd, ves, self.company_id, self.payment_date
            )
        
        # Group calculations by salesperson
        salesperson_data = {}
        
        for calc in self.batch_id.calculation_ids.filtered(
            lambda c: c.state in ['calculated', 'validated', 'approved']
        ):
            sp_id = calc.salesperson_id.id
            if sp_id not in salesperson_data:
                salesperson_data[sp_id] = {
                    'salesperson_id': sp_id,
                    'calculations': self.env['commission.calculation'],
                    'total_usd': 0.0,
                    'total_ves': 0.0,
                    'total_other': {}  # For other currencies
                }
            
            salesperson_data[sp_id]['calculations'] |= calc
            
            # Sum by currency
            if calc.currency_id.name == 'USD':
                salesperson_data[sp_id]['total_usd'] += calc.commission_amount
            elif calc.currency_id.name == 'VES':
                salesperson_data[sp_id]['total_ves'] += calc.commission_amount
            else:
                currency_name = calc.currency_id.name
                if currency_name not in salesperson_data[sp_id]['total_other']:
                    salesperson_data[sp_id]['total_other'][currency_name] = {
                        'currency_id': calc.currency_id,
                        'amount': 0.0
                    }
                salesperson_data[sp_id]['total_other'][currency_name]['amount'] += calc.commission_amount
        
        # Create payment lines
        PaymentLine = self.env['commission.payment.line']
        
        for sp_id, data in salesperson_data.items():
            # Create main line for salesperson
            line_vals = {
                'document_id': self.id,
                'salesperson_id': sp_id,
                'calculation_ids': [(6, 0, data['calculations'].ids)],
                'commission_count': len(data['calculations']),
            }
            
            # Calculate payment amounts
            # USD commissions stay in USD
            line_vals['amount_usd_original'] = data['total_usd']
            line_vals['amount_usd_payment'] = data['total_usd']
            
            # VES commissions stay in VES
            line_vals['amount_ves_original'] = data['total_ves']
            line_vals['amount_ves_payment'] = data['total_ves']
            
            # Convert other currencies to payment currency (usually VES)
            # This is where you'd implement the logic for other currencies
            # For now, we'll convert them to VES
            total_other_in_ves = 0.0
            for currency_data in data['total_other'].values():
                amount_ves = currency_data['currency_id']._convert(
                    currency_data['amount'],
                    ves,
                    self.company_id,
                    self.payment_date
                )
                total_other_in_ves += amount_ves
            
            line_vals['amount_ves_payment'] += total_other_in_ves
            
            PaymentLine.create(line_vals)
        
        # Update calculations state
        self.batch_id.calculation_ids.filtered(
            lambda c: c.state in ['calculated', 'validated']
        ).write({'state': 'approved'})

    def action_confirm(self):
        """Confirm payment document"""
        self.ensure_one()
        
        if self.state != 'draft':
            raise UserError(_("Only draft documents can be confirmed."))
        
        if not self.line_ids:
            raise UserError(_("Cannot confirm a document without payment lines."))
        
        self.write({'state': 'confirmed'})

    def action_mark_paid(self):
        """Mark document as paid"""
        self.ensure_one()
        
        if self.state != 'confirmed':
            raise UserError(_("Only confirmed documents can be marked as paid."))
        
        self.write({'state': 'paid'})
        
        # Update batch state
        if self.batch_id.state == 'payment_generated':
            self.batch_id.action_mark_paid()

    def action_export_excel(self):
        """Export payment document to Excel"""
        self.ensure_one()
        
        # Use wizard for export
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'commission.payment.export.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_id': self.id,
                'active_model': 'commission.payment.document',
                'active_id': self.id,
            }
        }

    def get_summary_by_currency(self):
        """Get payment summary by currency"""
        self.ensure_one()
        
        summary = {
            'USD': {
                'original': sum(self.line_ids.mapped('amount_usd_original')),
                'payment': sum(self.line_ids.mapped('amount_usd_payment')),
                'salesperson_count': len(self.line_ids.filtered(lambda l: l.amount_usd_original > 0))
            },
            'VES': {
                'original': sum(self.line_ids.mapped('amount_ves_original')),
                'payment': sum(self.line_ids.mapped('amount_ves_payment')),
                'salesperson_count': len(self.line_ids.filtered(lambda l: l.amount_ves_original > 0))
            }
        }
        
        return summary


class CommissionPaymentLine(models.Model):
    _name = 'commission.payment.line'
    _description = 'Commission Payment Line'
    _order = 'salesperson_id'
    _rec_name = 'salesperson_id'

    document_id = fields.Many2one(
        'commission.payment.document',
        string='Payment Document',
        required=True,
        ondelete='cascade'
    )
    salesperson_id = fields.Many2one(
        'res.users',
        string='Salesperson',
        required=True
    )
    calculation_ids = fields.Many2many(
        'commission.calculation',
        'commission_payment_line_calc_rel',
        'line_id',
        'calc_id',
        string='Commission Calculations'
    )
    
    # Statistics
    commission_count = fields.Integer(
        string='Number of Commissions',
        readonly=True
    )
    
    # Amounts in original currency
    amount_usd_original = fields.Float(
        string='USD Commissions',
        digits=(16, 2),
        readonly=True,
        help="Total commission amount originally in USD"
    )
    amount_ves_original = fields.Float(
        string='VES Commissions',
        digits=(16, 2),
        readonly=True,
        help="Total commission amount originally in VES"
    )
    
    # Amounts for payment (after conversion if needed)
    amount_usd_payment = fields.Float(
        string='USD to Pay',
        digits=(16, 2),
        readonly=True,
        help="Amount to pay in USD"
    )
    amount_ves_payment = fields.Float(
        string='VES to Pay',
        digits=(16, 2),
        readonly=True,
        help="Amount to pay in VES (includes conversions)"
    )
    
    # Total to pay (for reporting)
    total_payment = fields.Float(
        string='Total Payment',
        compute='_compute_total_payment',
        help="Total payment amount in company currency"
    )
    
    # Company
    company_id = fields.Many2one(
        'res.company',
        related='document_id.company_id',
        store=True
    )

    @api.depends('amount_usd_payment', 'amount_ves_payment')
    def _compute_total_payment(self):
        """Compute total payment in company currency"""
        for line in self:
            # Get company currency
            company_currency = line.company_id.currency_id
            
            total = 0.0
            
            # Convert USD to company currency
            if line.amount_usd_payment > 0:
                usd = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
                if usd and usd != company_currency:
                    total += usd._convert(
                        line.amount_usd_payment,
                        company_currency,
                        line.company_id,
                        line.document_id.payment_date
                    )
                else:
                    total += line.amount_usd_payment
            
            # Convert VES to company currency
            if line.amount_ves_payment > 0:
                ves = self.env['res.currency'].search([('name', '=', 'VES')], limit=1)
                if ves and ves != company_currency:
                    total += ves._convert(
                        line.amount_ves_payment,
                        company_currency,
                        line.company_id,
                        line.document_id.payment_date
                    )
                else:
                    total += line.amount_ves_payment
            
            line.total_payment = total

    def action_view_calculations(self):
        """View commission calculations for this line"""
        self.ensure_one()
        return {
            'name': _('Commission Calculations'),
            'type': 'ir.actions.act_window',
            'res_model': 'commission.calculation',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.calculation_ids.ids)],
            'context': {
                'create': False,
                'delete': False,
            }
        }