# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class CommissionBatch(models.Model):
    _name = 'commission.batch'
    _description = 'Commission Batch - Monthly Commission Management'
    _order = 'date_from desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(
        string='Batch Name',
        required=True,
        tracking=True,
        help="Name defined by the client for this commission batch"
    )
    
    # Date fields
    date_from = fields.Date(
        string='Date From',
        required=True,
        tracking=True,
        help="Start date of the commission period"
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        tracking=True,
        help="End date of the commission period"
    )
    payment_date = fields.Date(
        string='Payment Date',
        tracking=True,
        help="Date when commissions will be paid (usually 10th of the month)"
    )
    
    # State
    state = fields.Selection([
        ('draft', 'Draft'),
        ('calculated', 'Calculated'),
        ('reviewed', 'Reviewed by Sales'),
        ('payment_generated', 'Payment Document Generated'),
        ('paid', 'Paid')
    ], string='State', default='draft', required=True, tracking=True, index=True)
    
    # Relations
    calculation_ids = fields.One2many(
        'commission.calculation',
        'batch_id',
        string='Commission Calculations',
        help="Commission calculations included in this batch"
    )
    payment_document_id = fields.Many2one(
        'commission.payment.document',
        string='Payment Document',
        readonly=True,
        help="Generated payment document for this batch"
    )
    
    # Statistics
    calculation_count = fields.Integer(
        string='Number of Calculations',
        compute='_compute_statistics',
        store=True
    )
    salesperson_count = fields.Integer(
        string='Number of Salespersons',
        compute='_compute_statistics',
        store=True
    )
    total_commission_usd = fields.Monetary(
        string='Total Commission (USD)',
        compute='_compute_statistics',
        store=True,
        currency_field='currency_usd_id',
        help="Total commission amount in USD"
    )
    total_commission_ves = fields.Monetary(
        string='Total Commission (VES)',
        compute='_compute_statistics',
        store=True,
        currency_field='currency_ves_id',
        help="Total commission amount in VES"
    )
    
    # Currency fields
    currency_usd_id = fields.Many2one(
        'res.currency',
        string='USD Currency',
        compute='_compute_currencies',
        store=True
    )
    currency_ves_id = fields.Many2one(
        'res.currency',
        string='VES Currency',
        compute='_compute_currencies',
        store=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True
    )
    
    # Additional fields
    notes = fields.Text(
        string='Notes',
        help="Internal notes about this batch"
    )
    reviewed_by_id = fields.Many2one(
        'res.users',
        string='Reviewed By',
        readonly=True,
        tracking=True
    )
    reviewed_date = fields.Datetime(
        string='Review Date',
        readonly=True,
        tracking=True
    )
    
    _sql_constraints = [
        ('date_check', 'CHECK (date_from <= date_to)', 
         'The start date must be before or equal to the end date!'),
    ]

    @api.depends('company_id')
    def _compute_currencies(self):
        for batch in self:
            usd = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
            ves = self.env['res.currency'].search([('name', '=', 'VES')], limit=1)
            batch.currency_usd_id = usd
            batch.currency_ves_id = ves

    @api.depends('calculation_ids', 'calculation_ids.state', 'calculation_ids.commission_amount', 
                 'calculation_ids.currency_id')
    def _compute_statistics(self):
        for batch in self:
            valid_calculations = batch.calculation_ids.filtered(
                lambda c: c.state not in ['cancelled']
            )
            
            batch.calculation_count = len(valid_calculations)
            batch.salesperson_count = len(valid_calculations.mapped('salesperson_id'))
            
            # Calculate totals by currency
            total_usd = 0.0
            total_ves = 0.0
            
            for calc in valid_calculations:
                if calc.currency_id.name == 'USD':
                    total_usd += calc.commission_amount
                elif calc.currency_id.name == 'VES':
                    total_ves += calc.commission_amount
                else:
                    # Convert to USD for other currencies
                    amount_usd = calc.currency_id._convert(
                        calc.commission_amount,
                        batch.currency_usd_id,
                        batch.company_id,
                        calc.payment_date or fields.Date.today()
                    )
                    total_usd += amount_usd
            
            batch.total_commission_usd = total_usd
            batch.total_commission_ves = total_ves

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for batch in self:
            # Check for overlapping batches
            domain = [
                ('id', '!=', batch.id),
                ('company_id', '=', batch.company_id.id),
                ('state', '!=', 'cancelled'),
                '|',
                '&', ('date_from', '<=', batch.date_from), ('date_to', '>=', batch.date_from),
                '&', ('date_from', '<=', batch.date_to), ('date_to', '>=', batch.date_to),
            ]
            if self.search(domain):
                raise ValidationError(_("There is already a batch covering this period!"))

    @api.onchange('date_from')
    def _onchange_date_from(self):
        """Set default values when date_from changes"""
        if self.date_from:
            # Set date_to to end of month
            next_month = self.date_from + relativedelta(months=1)
            self.date_to = next_month - relativedelta(days=1)
            
            # Set payment_date to 10th of next month
            self.payment_date = next_month.replace(day=10)
            
            # Set default name
            if not self.name:
                self.name = _("Commissions %s") % self.date_from.strftime('%B %Y')

    def action_calculate(self):
        """Calculate commissions for this batch"""
        self.ensure_one()
        
        if self.state != 'draft':
            raise UserError(_("Only draft batches can be calculated."))
        
        # Find commission calculations in the period without batch
        domain = [
            ('payment_date', '>=', self.date_from),
            ('payment_date', '<=', self.date_to),
            ('batch_id', '=', False),
            ('state', 'not in', ['cancelled']),
            ('company_id', '=', self.company_id.id)
        ]
        
        calculations = self.env['commission.calculation'].search(domain)
        
        if not calculations:
            raise UserError(_("No commission calculations found for the selected period."))
        
        # Assign calculations to this batch
        calculations.write({'batch_id': self.id})
        
        self.write({
            'state': 'calculated',
            'message_post': self.message_post(
                body=_("Batch calculated with %d commission calculations.") % len(calculations)
            )
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Batch Calculated'),
                'message': _('%d commission calculations have been added to this batch.') % len(calculations),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_review(self):
        """Mark batch as reviewed by sales"""
        self.ensure_one()
        
        if self.state != 'calculated':
            raise UserError(_("Only calculated batches can be reviewed."))
        
        if not self.calculation_ids:
            raise UserError(_("Cannot review a batch without calculations."))
        
        self.write({
            'state': 'reviewed',
            'reviewed_by_id': self.env.user.id,
            'reviewed_date': fields.Datetime.now()
        })
        
        self.message_post(
            body=_("Batch reviewed by %s") % self.env.user.name
        )

    def action_generate_payment_document(self):
        """Generate payment document for this batch"""
        self.ensure_one()
        
        if self.state != 'reviewed':
            raise UserError(_("Only reviewed batches can generate payment documents."))
        
        if not self.payment_date:
            raise UserError(_("Please set a payment date before generating the payment document."))
        
        # Create payment document
        payment_doc = self.env['commission.payment.document'].create({
            'batch_id': self.id,
            'payment_date': self.payment_date,
            'company_id': self.company_id.id,
        })
        
        # Generate payment lines
        payment_doc._generate_payment_lines()
        
        self.write({
            'state': 'payment_generated',
            'payment_document_id': payment_doc.id
        })
        
        # Open the payment document
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'commission.payment.document',
            'res_id': payment_doc.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_mark_paid(self):
        """Mark batch as paid"""
        self.ensure_one()
        
        if self.state != 'payment_generated':
            raise UserError(_("Only batches with payment documents can be marked as paid."))
        
        # Mark all calculations as paid
        self.calculation_ids.filtered(
            lambda c: c.state == 'approved'
        ).action_mark_paid()
        
        # Mark payment document as paid
        if self.payment_document_id:
            self.payment_document_id.state = 'paid'
        
        self.write({'state': 'paid'})
        
        self.message_post(
            body=_("Batch marked as paid")
        )

    def action_reset_draft(self):
        """Reset batch to draft state"""
        self.ensure_one()
        
        if self.state == 'paid':
            raise UserError(_("Cannot reset paid batches to draft."))
        
        # Remove calculations from batch
        self.calculation_ids.write({'batch_id': False})
        
        # Delete payment document if exists
        if self.payment_document_id:
            self.payment_document_id.unlink()
        
        self.write({
            'state': 'draft',
            'reviewed_by_id': False,
            'reviewed_date': False
        })

    def action_view_calculations(self):
        """View commission calculations in this batch"""
        self.ensure_one()
        return {
            'name': _('Commission Calculations'),
            'type': 'ir.actions.act_window',
            'res_model': 'commission.calculation',
            'view_mode': 'list,form,graph,pivot',
            'domain': [('batch_id', '=', self.id)],
            'context': {
                'default_batch_id': self.id,
                'search_default_group_by_salesperson': 1,
            }
        }

    def action_view_payment_document(self):
        """View payment document"""
        self.ensure_one()
        
        if not self.payment_document_id:
            raise UserError(_("No payment document generated for this batch."))
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'commission.payment.document',
            'res_id': self.payment_document_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def create_monthly_batch(self, date=None):
        """Helper method to create monthly batch (can be called from cron)"""
        if not date:
            date = fields.Date.today()
        
        # Get first and last day of previous month
        first_day = date.replace(day=1) - relativedelta(days=1)
        first_day = first_day.replace(day=1)
        last_day = date.replace(day=1) - relativedelta(days=1)
        
        # Check if batch already exists
        existing = self.search([
            ('date_from', '=', first_day),
            ('date_to', '=', last_day),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        
        if existing:
            return existing
        
        # Create batch
        batch = self.create({
            'name': _("Commissions %s") % first_day.strftime('%B %Y'),
            'date_from': first_day,
            'date_to': last_day,
            'payment_date': date.replace(day=10),
        })
        
        return batch

    def get_summary_by_currency(self):
        """Get commission summary grouped by currency"""
        self.ensure_one()
        
        summary = {}
        for calc in self.calculation_ids.filtered(lambda c: c.state != 'cancelled'):
            currency = calc.currency_id.name
            if currency not in summary:
                summary[currency] = {
                    'currency_id': calc.currency_id,
                    'total_amount': 0.0,
                    'calculation_count': 0,
                    'salesperson_count': set()
                }
            
            summary[currency]['total_amount'] += calc.commission_amount
            summary[currency]['calculation_count'] += 1
            summary[currency]['salesperson_count'].add(calc.salesperson_id.id)
        
        # Convert sets to counts
        for currency in summary:
            summary[currency]['salesperson_count'] = len(summary[currency]['salesperson_count'])
        
        return summary