# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # Commission related fields
    commission_calculation_ids = fields.One2many(
        'commission.calculation',
        'payment_id',
        string='Commission Calculations',
        help="Commission calculations generated from this payment"
    )
    
    commission_calculation_count = fields.Integer(
        string='Commission Count',
        compute='_compute_commission_count'
    )
    
    has_commission_calculations = fields.Boolean(
        string='Has Commissions',
        compute='_compute_commission_count',
        store=True,
        help="Indicates if this payment has generated commission calculations"
    )
    
    total_commission_amount = fields.Monetary(
        string='Total Commission',
        compute='_compute_total_commission',
        currency_field='currency_id',
        help="Total commission amount generated from this payment"
    )
    
    skip_commission_calculation = fields.Boolean(
        string='Skip Commission',
        default=False,
        help="If checked, commission will not be calculated for this payment"
    )

    @api.depends('commission_calculation_ids')
    def _compute_commission_count(self):
        for payment in self:
            payment.commission_calculation_count = len(payment.commission_calculation_ids)
            payment.has_commission_calculations = bool(payment.commission_calculation_ids)

    @api.depends('commission_calculation_ids.commission_amount', 'commission_calculation_ids.state')
    def _compute_total_commission(self):
        for payment in self:
            valid_calculations = payment.commission_calculation_ids.filtered(
                lambda c: c.state not in ['cancelled']
            )
            # Sum commissions in payment currency
            total = sum(valid_calculations.filtered(
                lambda c: c.currency_id == payment.currency_id
            ).mapped('commission_amount'))
            
            # Convert and sum commissions in other currencies
            for calc in valid_calculations.filtered(lambda c: c.currency_id != payment.currency_id):
                amount_converted = calc.currency_id._convert(
                    calc.commission_amount,
                    payment.currency_id,
                    payment.company_id,
                    payment.date
                )
                total += amount_converted
            
            payment.total_commission_amount = total

    def action_post(self):
        """Override to trigger commission calculation after payment is posted"""
        res = super().action_post()
        
        # Trigger commission calculation for each payment
        for payment in self:
            if payment.payment_type == 'inbound' and not payment.skip_commission_calculation:
                payment._trigger_commission_calculation()
        
        return res

    def _trigger_commission_calculation(self):
        """Trigger commission calculation when payment is reconciled"""
        self.ensure_one()
        
        # Only process customer payments
        if self.payment_type != 'inbound' or self.partner_type != 'customer':
            _logger.info("Payment %s is not a customer payment. Skipping commission calculation.", self.name)
            return
        
        # Check if payment is reconciled
        if not self.is_reconciled:
            _logger.info("Payment %s is not reconciled. Commission will be calculated when reconciled.", self.name)
            return
        
        # Check if commission calculation should be skipped
        if self.skip_commission_calculation:
            _logger.info("Commission calculation skipped for payment %s as per user request.", self.name)
            return
        
        # Check if commissions already calculated
        existing_calculations = self.commission_calculation_ids.filtered(
            lambda c: c.state != 'cancelled'
        )
        if existing_calculations:
            _logger.info("Commission already calculated for payment %s.", self.name)
            return
        
        # Delegate to commission calculation model
        self.env['commission.calculation']._calculate_commission_from_payment(self.id)

    def _reconcile_create_hook(self, counterpart_aml, payment_aml):
        """Hook called when payment is reconciled"""
        res = super()._reconcile_create_hook(counterpart_aml, payment_aml)
        
        # Trigger commission calculation after reconciliation
        if not self.skip_commission_calculation:
            self._trigger_commission_calculation()
        
        return res

    def action_view_commission_calculations(self):
        """Action to view commission calculations for this payment"""
        self.ensure_one()
        return {
            'name': _('Commission Calculations'),
            'type': 'ir.actions.act_window',
            'res_model': 'commission.calculation',
            'view_mode': 'list,form',
            'domain': [('payment_id', '=', self.id)],
            'context': {
                'default_payment_id': self.id,
                'create': False,  # Prevent manual creation from this view
            }
        }

    def action_recalculate_commissions(self):
        """Action to recalculate commissions for this payment"""
        self.ensure_one()
        
        # Cancel existing calculations
        existing_calculations = self.commission_calculation_ids.filtered(
            lambda c: c.state not in ['paid', 'cancelled']
        )
        existing_calculations.action_cancel()
        
        # Trigger recalculation
        self._trigger_commission_calculation()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Commission Recalculation'),
                'message': _('Commission has been recalculated for payment %s') % self.name,
                'type': 'success',
                'sticky': False,
            }
        }

    @api.model
    def _cron_calculate_pending_commissions(self):
        """Cron job to calculate commissions for reconciled payments without calculations"""
        # Find reconciled customer payments without commission calculations
        domain = [
            ('payment_type', '=', 'inbound'),
            ('partner_type', '=', 'customer'),
            ('is_reconciled', '=', True),
            ('skip_commission_calculation', '=', False),
            ('state', '=', 'posted'),
        ]
        
        payments = self.search(domain)
        
        # Filter payments without valid commission calculations
        pending_payments = payments.filtered(
            lambda p: not p.commission_calculation_ids or 
            all(c.state == 'cancelled' for c in p.commission_calculation_ids)
        )
        
        _logger.info("Found %d payments pending commission calculation", len(pending_payments))
        
        for payment in pending_payments:
            try:
                payment._trigger_commission_calculation()
            except Exception as e:
                _logger.error("Error calculating commission for payment %s: %s", payment.name, str(e))
                continue
        
        return True

    def write(self, vals):
        """Override to handle skip_commission_calculation changes"""
        res = super().write(vals)
        
        # If skip_commission_calculation is turned off, trigger calculation
        if 'skip_commission_calculation' in vals and not vals['skip_commission_calculation']:
            for payment in self.filtered(lambda p: p.is_reconciled and p.payment_type == 'inbound'):
                if not payment.commission_calculation_ids.filtered(lambda c: c.state != 'cancelled'):
                    payment._trigger_commission_calculation()
        
        return res