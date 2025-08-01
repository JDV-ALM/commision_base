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
    
    can_calculate_commission = fields.Boolean(
        string='Can Calculate Commission',
        compute='_compute_can_calculate_commission',
        help="Indicates if commission can be calculated for this payment"
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

    @api.depends('payment_type', 'partner_type', 'is_reconciled', 'skip_commission_calculation', 'state')
    def _compute_can_calculate_commission(self):
        """Compute if commission can be calculated for this payment"""
        for payment in self:
            can_calculate = (
                payment.payment_type == 'inbound' and
                payment.partner_type == 'customer' and
                payment.is_reconciled and
                not payment.skip_commission_calculation and
                payment.state in ['posted', 'paid']  # Aceptar posted o paid
            )
            
            # Check if there are already calculations
            if can_calculate and payment.commission_calculation_ids:
                # Only allow if all existing are cancelled
                can_calculate = all(calc.state == 'cancelled' for calc in payment.commission_calculation_ids)
            
            payment.can_calculate_commission = can_calculate

    def action_post(self):
        """Override to trigger commission calculation after payment is posted"""
        res = super().action_post()
        
        # Trigger commission calculation for each payment
        for payment in self:
            if payment.payment_type == 'inbound' and not payment.skip_commission_calculation:
                # Try to calculate immediately if already reconciled
                payment._trigger_commission_calculation()
        
        return res

    def write(self, vals):
        """Override to handle skip_commission_calculation changes"""
        res = super().write(vals)
        
        # Solo manejar el caso donde skip_commission_calculation se desactiva
        if 'skip_commission_calculation' in vals and not vals['skip_commission_calculation']:
            for payment in self.filtered(lambda p: p.is_reconciled and p.payment_type == 'inbound'):
                if not payment.commission_calculation_ids.filtered(lambda c: c.state != 'cancelled'):
                    payment._trigger_commission_calculation()
        
        return res

    def _trigger_commission_calculation(self):
        """Trigger commission calculation when payment is reconciled"""
        self.ensure_one()
        
        _logger.info("=== Starting commission calculation for payment %s ===", self.name)
        
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
            _logger.info("Commission already calculated for payment %s. Found %d existing calculations.", 
                        self.name, len(existing_calculations))
            return
        
        # Get reconciled invoices
        reconciled_invoices = self.reconciled_invoice_ids
        if not reconciled_invoices:
            _logger.warning("No reconciled invoices found for payment %s", self.name)
            return
        
        _logger.info("Found %d reconciled invoices for payment %s", len(reconciled_invoices), self.name)
        
        # Delegate to commission calculation model
        calculation_model = self.env['commission.calculation']
        calculation_model._calculate_commission_from_payment(self.id)
        
        # Check if calculations were created
        new_calculations = self.commission_calculation_ids.filtered(
            lambda c: c.state != 'cancelled'
        )
        if new_calculations:
            _logger.info("Successfully created %d commission calculations for payment %s", 
                        len(new_calculations), self.name)
        else:
            _logger.warning("No commission calculations were created for payment %s", self.name)

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

    def action_calculate_commission(self):
        """Manual action to calculate commission for this payment"""
        self.ensure_one()
        
        if not self.can_calculate_commission:
            # Provide specific error message
            if self.payment_type != 'inbound':
                raise UserError(_("Commission can only be calculated for incoming payments."))
            elif not self.is_reconciled:
                raise UserError(_("Payment must be reconciled before calculating commission."))
            elif self.skip_commission_calculation:
                raise UserError(_("Commission calculation is disabled for this payment."))
            elif self.commission_calculation_ids.filtered(lambda c: c.state != 'cancelled'):
                raise UserError(_("Commission has already been calculated for this payment."))
            else:
                raise UserError(_("Cannot calculate commission for this payment."))
        
        # Force trigger calculation
        _logger.info("Manual commission calculation triggered for payment %s", self.name)
        self._trigger_commission_calculation()
        
        # Refresh the view
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Commission Calculation'),
                'message': _('Commission calculation process has been executed for payment %s') % self.name,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_recalculate_commissions(self):
        """Action to recalculate commissions for this payment"""
        self.ensure_one()
        
        # Cancel existing calculations
        existing_calculations = self.commission_calculation_ids.filtered(
            lambda c: c.state not in ['paid', 'cancelled']
        )
        
        if not existing_calculations:
            raise UserError(_("No commissions to recalculate."))
        
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
            ('state', 'in', ['posted', 'paid']),  # Incluir tanto posted como paid
        ]
        
        payments = self.search(domain)
        
        # Filter payments without valid commission calculations
        # Usar la misma lógica que skip_commission
        pending_payments = payments.filtered(
            lambda p: not p.commission_calculation_ids.filtered(lambda c: c.state != 'cancelled')
        )
        
        _logger.info("Found %d payments pending commission calculation", len(pending_payments))
        
        for payment in pending_payments:
            try:
                payment._trigger_commission_calculation()
            except Exception as e:
                _logger.error("Error calculating commission for payment %s: %s", payment.name, str(e))
                continue
        
        return True

    # Debug method
    def action_debug_commission_info(self):
        """Debug method to check why commission is not calculated"""
        self.ensure_one()
        
        info = []
        info.append(f"Payment: {self.name}")
        info.append(f"Type: {self.payment_type}")
        info.append(f"Partner Type: {self.partner_type}")
        info.append(f"Is Reconciled: {self.is_reconciled}")
        info.append(f"Skip Commission: {self.skip_commission_calculation}")
        info.append(f"State: {self.state}")
        
        # Check invoices
        invoices = self.reconciled_invoice_ids
        info.append(f"\nReconciled Invoices: {len(invoices)}")
        
        for inv in invoices:
            info.append(f"  - {inv.name}")
            info.append(f"    Salesperson: {inv.invoice_user_id.name if inv.invoice_user_id else 'NOT SET'}")
            info.append(f"    Skip Commission: {inv.skip_commission}")
        
        # Check existing calculations
        calcs = self.commission_calculation_ids
        info.append(f"\nExisting Calculations: {len(calcs)}")
        for calc in calcs:
            info.append(f"  - State: {calc.state}")
            info.append(f"    Amount: {calc.commission_amount}")
        
        message = '\n'.join(info)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Commission Debug Info'),
                'message': message,
                'type': 'info',
                'sticky': True,
            }
        }