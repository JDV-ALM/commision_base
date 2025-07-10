# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class CommissionCalculation(models.Model):
    _name = 'commission.calculation'
    _description = 'Commission Calculation Record'
    _order = 'payment_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'display_name'

    # Relational fields
    payment_id = fields.Many2one(
        'account.payment',
        string='Payment',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Invoice',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True
    )
    salesperson_id = fields.Many2one(
        'res.users',
        string='Salesperson',
        required=True,
        index=True,
        tracking=True
    )
    rule_id = fields.Many2one(
        'commission.rule',
        string='Applied Rule',
        tracking=True
    )
    band_id = fields.Many2one(
        'commission.band',
        string='Applied Band',
        tracking=True
    )
    range_id = fields.Many2one(
        'commission.range',
        string='Applied Range',
        tracking=True
    )
    batch_id = fields.Many2one(
        'commission.batch',
        string='Commission Batch',
        index=True,
        help="Batch this calculation belongs to"
    )
    
    # Date fields
    invoice_date = fields.Date(
        string='Invoice Date',
        related='invoice_id.invoice_date',
        store=True,
        readonly=True
    )
    due_date = fields.Date(
        string='Due Date',
        related='invoice_id.invoice_date_due',
        store=True,
        readonly=True
    )
    payment_date = fields.Date(
        string='Payment Date',
        related='payment_id.date',
        store=True,
        readonly=True
    )
    delivery_date = fields.Date(
        string='Delivery Date',
        help="Date when goods were delivered (if tracked)"
    )
    
    # Calculation fields
    days_overdue = fields.Integer(
        string='Days Overdue',
        compute='_compute_days_overdue',
        store=True,
        help="Days between due date and payment date (negative for early payment)"
    )
    
    # Amount fields
    payment_amount = fields.Monetary(
        string='Payment Amount',
        currency_field='currency_id',
        required=True,
        tracking=True
    )
    payment_amount_company = fields.Monetary(
        string='Payment Amount (Company Currency)',
        currency_field='company_currency_id',
        compute='_compute_amounts_company',
        store=True,
        compute_sudo=True
    )
    commission_rate = fields.Float(
        string='Commission Rate (%)',
        digits=(5, 4),
        tracking=True
    )
    commission_amount = fields.Monetary(
        string='Commission Amount',
        currency_field='currency_id',
        required=True,
        tracking=True
    )
    commission_amount_company = fields.Monetary(
        string='Commission Amount (Company Currency)',
        currency_field='company_currency_id',
        compute='_compute_amounts_company',
        store=True,
        compute_sudo=True
    )
    
    # Currency fields
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        tracking=True
    )
    company_currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True
    )
    exchange_rate = fields.Float(
        string='Exchange Rate',
        digits=(12, 6),
        compute='_compute_exchange_rate',
        store=True
    )
    
    # Control fields
    is_reconciled = fields.Boolean(
        string='Payment Reconciled',
        related='payment_id.is_reconciled',
        store=True,
        readonly=True
    )
    reconciliation_date = fields.Date(
        string='Reconciliation Date',
        compute='_compute_reconciliation_date',
        store=True
    )
    journal_id = fields.Many2one(
        'account.journal',
        related='payment_id.journal_id',
        store=True,
        readonly=True
    )
    
    # State and workflow
    state = fields.Selection([
        ('draft', 'Draft'),
        ('calculated', 'Calculated'),
        ('validated', 'Validated'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled')
    ], string='State', default='draft', required=True, tracking=True, index=True)
    
    # Additional fields
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True
    )
    notes = fields.Text(
        string='Notes',
        help="Additional notes or observations about this commission"
    )
    
    # Partner fields (for reporting)
    partner_id = fields.Many2one(
        'res.partner',
        related='invoice_id.partner_id',
        store=True,
        readonly=True,
        string='Customer'
    )
    
    # Display
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    color = fields.Integer(
        string='Color Index',
        compute='_compute_color'
    )
    in_batch = fields.Boolean(
        string='In Batch',
        compute='_compute_in_batch',
        store=True,
        help="Indicates if this calculation is included in a batch"
    )

    @api.depends('salesperson_id', 'invoice_id', 'commission_amount', 'currency_id')
    def _compute_display_name(self):
        for calc in self:
            name = _("Commission for %s on %s: %s %s") % (
                calc.salesperson_id.name or _("Unknown"),
                calc.invoice_id.name or _("Unknown"),
                calc.commission_amount,
                calc.currency_id.symbol or calc.currency_id.name
            )
            calc.display_name = name

    @api.depends('state')
    def _compute_color(self):
        color_map = {
            'draft': 0,
            'calculated': 3,
            'validated': 4,
            'approved': 10,
            'paid': 11,
            'cancelled': 1
        }
        for calc in self:
            calc.color = color_map.get(calc.state, 0)

    @api.depends('due_date', 'payment_date')
    def _compute_days_overdue(self):
        for calc in self:
            if calc.due_date and calc.payment_date:
                calc.days_overdue = (calc.payment_date - calc.due_date).days
            else:
                calc.days_overdue = 0

    @api.depends('payment_id.reconciled_invoice_ids')
    def _compute_reconciliation_date(self):
        for calc in self:
            if calc.is_reconciled and calc.payment_id.reconciled_invoice_ids:
                calc.reconciliation_date = calc.payment_id.date
            else:
                calc.reconciliation_date = False

    @api.depends('payment_date', 'currency_id', 'company_currency_id')
    def _compute_exchange_rate(self):
        for calc in self:
            if calc.currency_id and calc.company_currency_id and calc.payment_date:
                calc.exchange_rate = calc.currency_id._get_conversion_rate(
                    calc.currency_id,
                    calc.company_currency_id,
                    calc.company_id,
                    calc.payment_date
                )
            else:
                calc.exchange_rate = 1.0

    @api.depends('payment_amount', 'commission_amount', 'exchange_rate')
    def _compute_amounts_company(self):
        for calc in self:
            if calc.currency_id != calc.company_currency_id:
                calc.payment_amount_company = calc.payment_amount * calc.exchange_rate
                calc.commission_amount_company = calc.commission_amount * calc.exchange_rate
            else:
                calc.payment_amount_company = calc.payment_amount
                calc.commission_amount_company = calc.commission_amount

    @api.depends('batch_id')
    def _compute_in_batch(self):
        for calc in self:
            calc.in_batch = bool(calc.batch_id)

    @api.constrains('commission_amount')
    def _check_commission_amount(self):
        """Ensure commission amount is not negative"""
        for calc in self:
            if calc.commission_amount < 0:
                raise ValidationError(_("Commission amount cannot be negative!"))

    @api.constrains('payment_amount')
    def _check_payment_amount(self):
        """Ensure payment amount is positive"""
        for calc in self:
            if calc.payment_amount <= 0:
                raise ValidationError(_("Payment amount must be positive!"))

    # Workflow actions
    def action_calculate(self):
        """Mark as calculated"""
        self.write({'state': 'calculated'})

    def action_validate(self):
        """Validate commission calculation"""
        for calc in self:
            if calc.state != 'calculated':
                raise UserError(_("Only calculated commissions can be validated."))
            
            # If calculation is in a batch, check batch state
            if calc.batch_id and calc.batch_id.state not in ['calculated', 'reviewed']:
                raise UserError(_("Cannot validate commission in a batch that is not in 'Calculated' or 'Reviewed' state."))
            
            # Additional validation checks
            if not calc.is_reconciled:
                raise UserError(_("Cannot validate commission for unreconciled payment."))
            
            # Check if salesperson configuration allows commission
            config = self.env['salesperson.config'].search([
                ('user_id', '=', calc.salesperson_id.id),
                ('company_id', '=', calc.company_id.id)
            ], limit=1)
            
            if config and not config.commission_active:
                raise UserError(_("Commission is not active for salesperson %s") % calc.salesperson_id.name)
            
            # Apply min/max limits if configured
            if config:
                if config.min_commission_amount and calc.commission_amount < config.min_commission_amount:
                    calc.commission_amount = config.min_commission_amount
                if config.max_commission_amount and calc.commission_amount > config.max_commission_amount:
                    calc.commission_amount = config.max_commission_amount
        
        self.write({'state': 'validated'})

    def action_approve(self):
        """Approve commission for payment"""
        for calc in self:
            if calc.state != 'validated':
                raise UserError(_("Only validated commissions can be approved."))
        self.write({'state': 'approved'})

    def action_mark_paid(self):
        """Mark commission as paid"""
        for calc in self:
            if calc.state != 'approved':
                raise UserError(_("Only approved commissions can be marked as paid."))
        self.write({'state': 'paid'})

    def action_cancel(self):
        """Cancel commission calculation"""
        for calc in self:
            if calc.state == 'paid':
                raise UserError(_("Cannot cancel paid commissions."))
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        """Reset to draft state"""
        for calc in self:
            if calc.state == 'paid':
                raise UserError(_("Cannot reset paid commissions to draft."))
        self.write({'state': 'draft'})

    def action_remove_from_batch(self):
        """Remove calculation from batch"""
        for calc in self:
            if calc.batch_id and calc.batch_id.state in ['payment_generated', 'paid']:
                raise UserError(_("Cannot remove calculation from a batch that has a payment document generated or is paid."))
            calc.batch_id = False
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Removed from Batch'),
                'message': _('Commission calculation(s) removed from batch.'),
                'type': 'success',
                'sticky': False,
            }
        }

    # Calculation methods
    @api.model
    def _calculate_commission_from_payment(self, payment_id):
        """Main method to calculate commission from a payment
        
        Args:
            payment_id: ID of the account.payment record
        """
        payment = self.env['account.payment'].browse(payment_id)
        
        # Skip if payment is not reconciled
        if not payment.is_reconciled:
            _logger.info("Payment %s is not reconciled. Skipping commission calculation.", payment.name)
            return
        
        # Process each reconciled invoice
        for invoice in payment.reconciled_invoice_ids:
            # Skip if no salesperson assigned
            if not invoice.invoice_user_id:
                _logger.info("Invoice %s has no salesperson. Skipping commission calculation.", invoice.name)
                continue
            
            salesperson = invoice.invoice_user_id
            
            # Check if salesperson has commission active
            config = self.env['salesperson.config'].search([
                ('user_id', '=', salesperson.id),
                ('company_id', '=', invoice.company_id.id)
            ], limit=1)
            
            if config and not config.commission_active:
                _logger.info("Commission not active for salesperson %s. Skipping.", salesperson.name)
                continue
            
            # Check if commission already calculated for this payment-invoice combination
            existing = self.search([
                ('payment_id', '=', payment.id),
                ('invoice_id', '=', invoice.id),
                ('state', '!=', 'cancelled')
            ], limit=1)
            
            if existing:
                _logger.info("Commission already calculated for payment %s and invoice %s.", 
                           payment.name, invoice.name)
                continue
            
            # Find applicable rule
            applicable_rule = salesperson.get_applicable_commission_rule(invoice, payment)
            
            if not applicable_rule and config and config.default_rule_id:
                applicable_rule = config.default_rule_id
            
            if not applicable_rule:
                _logger.info("No applicable commission rule found for salesperson %s.", salesperson.name)
                continue
            
            # Calculate commission
            commission_data = applicable_rule.calculate_commission(payment, invoice, salesperson)
            
            if commission_data:
                # Create commission calculation record
                self.create({
                    'payment_id': payment.id,
                    'invoice_id': invoice.id,
                    'salesperson_id': salesperson.id,
                    'rule_id': applicable_rule.id,
                    'currency_id': payment.currency_id.id,
                    'state': 'calculated',
                    **commission_data
                })
                _logger.info("Commission calculated for payment %s, invoice %s, salesperson %s.", 
                           payment.name, invoice.name, salesperson.name)

    @api.model
    def cron_validate_commissions(self):
        """Cron job to automatically validate calculated commissions"""
        calculations = self.search([
            ('state', '=', 'calculated'),
            ('is_reconciled', '=', True)
        ])
        
        for calc in calculations:
            try:
                calc.action_validate()
            except UserError as e:
                _logger.warning("Could not validate commission %s: %s", calc.id, str(e))

    # Reporting methods
    def get_commission_summary(self):
        """Get commission summary data for reporting"""
        self.ensure_one()
        return {
            'salesperson': self.salesperson_id.name,
            'customer': self.partner_id.name,
            'invoice': self.invoice_id.name,
            'payment': self.payment_id.name,
            'payment_date': self.payment_date,
            'days_overdue': self.days_overdue,
            'payment_amount': self.payment_amount,
            'commission_rate': self.commission_rate,
            'commission_amount': self.commission_amount,
            'currency': self.currency_id.name,
            'state': self.state,
            'rule': self.rule_id.name if self.rule_id else _("Direct"),
            'band': self.band_id.name if self.band_id else _("N/A"),
            'range': self.range_id.display_name if self.range_id else _("N/A"),
            'batch': self.batch_id.name if self.batch_id else _("N/A"),
        }