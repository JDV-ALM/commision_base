# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Commission related fields
    delivery_date = fields.Date(
        string='Delivery Date',
        tracking=True,
        help="Date when goods/services were delivered to customer. Used for commission calculations if needed."
    )
    
    commission_calculation_ids = fields.One2many(
        'commission.calculation',
        'invoice_id',
        string='Commission Calculations',
        help="Commission calculations related to this invoice"
    )
    
    commission_calculation_count = fields.Integer(
        string='Commission Count',
        compute='_compute_commission_stats'
    )
    
    total_commission_amount = fields.Monetary(
        string='Total Commission',
        compute='_compute_commission_stats',
        currency_field='company_currency_id',
        help="Total commission amount calculated from payments of this invoice"
    )
    
    avg_collection_days = fields.Float(
        string='Avg. Collection Days',
        compute='_compute_commission_stats',
        help="Average days between due date and payment for this invoice"
    )
    
    commission_override_rule_id = fields.Many2one(
        'commission.rule',
        string='Override Commission Rule',
        help="If set, this rule will be used instead of automatic rule selection"
    )
    
    skip_commission = fields.Boolean(
        string='Skip Commission',
        default=False,
        help="If checked, no commission will be calculated for payments of this invoice"
    )

    @api.depends('commission_calculation_ids', 'commission_calculation_ids.state', 
                 'commission_calculation_ids.commission_amount', 'commission_calculation_ids.days_overdue')
    def _compute_commission_stats(self):
        for move in self:
            valid_calculations = move.commission_calculation_ids.filtered(
                lambda c: c.state not in ['cancelled']
            )
            
            move.commission_calculation_count = len(valid_calculations)
            
            # Calculate total commission in company currency
            total = 0.0
            for calc in valid_calculations:
                total += calc.commission_amount_company
            move.total_commission_amount = total
            
            # Calculate average collection days
            days_list = valid_calculations.filtered('days_overdue').mapped('days_overdue')
            move.avg_collection_days = sum(days_list) / len(days_list) if days_list else 0.0

    @api.onchange('invoice_date')
    def _onchange_invoice_date_set_delivery(self):
        """Set delivery date to invoice date if not set"""
        if self.invoice_date and not self.delivery_date:
            self.delivery_date = self.invoice_date

    def action_view_commission_calculations(self):
        """Action to view commission calculations for this invoice"""
        self.ensure_one()
        return {
            'name': _('Commission Calculations'),
            'type': 'ir.actions.act_window',
            'res_model': 'commission.calculation',
            'view_mode': 'tree,form,graph,pivot',
            'domain': [('invoice_id', '=', self.id)],
            'context': {
                'default_invoice_id': self.id,
                'search_default_group_by_payment': 1,
            }
        }

    def get_commission_info(self):
        """Get commission information for this invoice
        
        Returns:
            dict: Commission information including applicable rules and calculations
        """
        self.ensure_one()
        
        info = {
            'invoice': self.name,
            'salesperson': self.invoice_user_id.name if self.invoice_user_id else _('Not assigned'),
            'skip_commission': self.skip_commission,
            'override_rule': self.commission_override_rule_id.name if self.commission_override_rule_id else _('None'),
            'calculations': [],
            'potential_rules': [],
        }
        
        # Get existing calculations
        for calc in self.commission_calculation_ids.filtered(lambda c: c.state != 'cancelled'):
            info['calculations'].append({
                'payment': calc.payment_id.name,
                'payment_date': calc.payment_date,
                'days_overdue': calc.days_overdue,
                'commission_amount': calc.commission_amount,
                'currency': calc.currency_id.name,
                'state': calc.state,
                'rule': calc.rule_id.name if calc.rule_id else _('Direct'),
            })
        
        # Get potential rules if salesperson assigned
        if self.invoice_user_id and not self.skip_commission:
            # Search for applicable rules
            rules = self.env['commission.rule'].search([
                ('active', '=', True),
                ('company_id', '=', self.company_id.id),
            ], order='priority, sequence')
            
            for rule in rules:
                # Check if rule could apply to this invoice
                if rule.customer_ids and self.partner_id not in rule.customer_ids:
                    continue
                if rule.salesperson_ids and self.invoice_user_id not in rule.salesperson_ids:
                    continue
                if rule.team_ids and self.team_id not in rule.team_ids:
                    continue
                
                info['potential_rules'].append({
                    'name': rule.name,
                    'priority': rule.priority,
                    'type': rule.commission_type,
                    'band': rule.band_id.name if rule.band_id else _('N/A'),
                })
        
        return info

    @api.model
    def _get_invoice_computed_account(self):
        """Override to ensure salesperson is set on invoice creation"""
        account = super()._get_invoice_computed_account()
        
        # Ensure salesperson is set if not already
        if not self.invoice_user_id and self.user_id:
            self.invoice_user_id = self.user_id
        elif not self.invoice_user_id and self.team_id and self.team_id.user_id:
            self.invoice_user_id = self.team_id.user_id
        
        return account

    def _post(self, soft=True):
        """Override to ensure commission fields are properly set"""
        # Set delivery date if not set
        for move in self:
            if move.is_sale_document() and not move.delivery_date:
                move.delivery_date = move.invoice_date
        
        return super()._post(soft=soft)

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        """Override to add commission information in invoice form view"""
        res = super().fields_view_get(view_id=view_id, view_type=view_type, 
                                    toolbar=toolbar, submenu=submenu)
        
        # Add commission smart button in invoice form view
        if view_type == 'form' and res.get('model') == 'account.move':
            # This would typically modify the arch to add commission smart button
            # but since we'll handle this in XML views, we just pass
            pass
        
        return res