# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    # Commission band fields
    commission_band_active = fields.Boolean(
        string='Commission Band Active',
        default=True,
        help="If unchecked, the commission band system will not calculate commissions for this user"
    )
    
    commission_config_ids = fields.One2many(
        'salesperson.config',
        'user_id',
        string='Commission Configurations',
        help="Commission configuration per company"
    )
    
    # Quick access to current company config
    current_commission_config_id = fields.Many2one(
        'salesperson.config',
        string='Current Commission Config',
        compute='_compute_current_commission_config',
        help="Commission configuration for current company"
    )
    
    # Statistics
    commission_calculation_count = fields.Integer(
        string='Commission Calculations',
        compute='_compute_commission_stats'
    )
    total_commission_amount = fields.Monetary(
        string='Total Commissions',
        compute='_compute_commission_stats',
        currency_field='company_currency_id'
    )
    avg_collection_days = fields.Float(
        string='Avg. Collection Days',
        compute='_compute_commission_stats',
        help="Average days between invoice due date and payment"
    )
    company_currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        readonly=True
    )

    @api.depends('commission_config_ids', 'company_id')
    def _compute_current_commission_config(self):
        """Compute the commission configuration for the current company"""
        for user in self:
            config = user.commission_config_ids.filtered(
                lambda c: c.company_id == user.company_id
            )
            user.current_commission_config_id = config[0] if config else False

    @api.depends('commission_calculation_ids')
    def _compute_commission_stats(self):
        """Compute commission statistics for the user"""
        for user in self:
            calculations = self.env['commission.calculation'].search([
                ('salesperson_id', '=', user.id),
                ('company_id', '=', user.company_id.id),
                ('state', 'in', ['validated', 'approved', 'paid'])
            ])
            
            user.commission_calculation_count = len(calculations)
            
            # Convert all amounts to company currency for summing
            total = 0.0
            for calc in calculations:
                total += calc.commission_amount_company
            user.total_commission_amount = total
            
            # Calculate average collection days
            days_list = calculations.filtered('days_overdue').mapped('days_overdue')
            user.avg_collection_days = sum(days_list) / len(days_list) if days_list else 0.0

    def get_applicable_commission_rule(self, invoice=None, payment=None):
        """Get the applicable commission rule for this user
        
        Args:
            invoice: account.move record (optional)
            payment: account.payment record (optional)
            
        Returns:
            commission.rule record or False
        """
        self.ensure_one()
        
        # Check if commission band is active for this user
        if not self.commission_band_active:
            _logger.info("Commission band not active for user %s", self.name)
            return False
        
        # Get current company config
        config = self.commission_config_ids.filtered(
            lambda c: c.company_id == (invoice.company_id if invoice else self.company_id)
        )
        
        if config and not config.commission_active:
            _logger.info("Commission not active in configuration for user %s", self.name)
            return False
        
        # Search for applicable rules
        domain = [
            ('active', '=', True),
            ('company_id', '=', invoice.company_id.id if invoice else self.company_id.id)
        ]
        
        # Add date filter if payment exists
        if payment:
            domain.extend([
                '|', ('date_from', '=', False), ('date_from', '<=', payment.date),
                '|', ('date_to', '=', False), ('date_to', '>=', payment.date),
            ])
        
        rules = self.env['commission.rule'].search(domain, order='priority, sequence')
        
        # Find first matching rule
        for rule in rules:
            if rule.matches_criteria(invoice, payment, self):
                _logger.info("Found applicable rule %s for user %s", rule.name, self.name)
                return rule
        
        # Check for default rule in config
        if config and config.default_rule_id and config.default_rule_id.active:
            if config.default_rule_id.matches_criteria(invoice, payment, self):
                _logger.info("Using default rule %s for user %s", config.default_rule_id.name, self.name)
                return config.default_rule_id
        
        _logger.info("No applicable commission rule found for user %s", self.name)
        return False

    def action_view_commission_calculations(self):
        """Action to view commission calculations for this user"""
        self.ensure_one()
        return {
            'name': _('Commission Calculations'),
            'type': 'ir.actions.act_window',
            'res_model': 'commission.calculation',
            'view_mode': 'tree,form,graph,pivot',
            'domain': [('salesperson_id', '=', self.id)],
            'context': {
                'default_salesperson_id': self.id,
                'search_default_group_by_state': 1,
                'search_default_current_year': 1,
            }
        }

    def action_view_commission_config(self):
        """Action to view/edit commission configuration"""
        self.ensure_one()
        
        # Get or create config for current company
        config = self.env['salesperson.config'].search([
            ('user_id', '=', self.id),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not config:
            config = self.env['salesperson.config'].create({
                'user_id': self.id,
                'company_id': self.company_id.id,
            })
        
        return {
            'name': _('Commission Configuration'),
            'type': 'ir.actions.act_window',
            'res_model': 'salesperson.config',
            'view_mode': 'form',
            'res_id': config.id,
            'target': 'current',
        }

    def get_commission_dashboard_data(self):
        """Get data for commission dashboard
        
        Returns:
            dict: Dashboard data including calculations by state, monthly trends, etc.
        """
        self.ensure_one()
        
        calculations = self.env['commission.calculation'].search([
            ('salesperson_id', '=', self.id),
            ('company_id', '=', self.company_id.id)
        ])
        
        # Group by state
        states_data = {}
        for state, label in calculations._fields['state'].selection:
            state_calcs = calculations.filtered(lambda c: c.state == state)
            states_data[state] = {
                'label': label,
                'count': len(state_calcs),
                'amount': sum(state_calcs.mapped('commission_amount_company'))
            }
        
        # Monthly trend (last 12 months)
        monthly_data = []
        for i in range(11, -1, -1):
            month_start = fields.Date.today().replace(day=1) - relativedelta(months=i)
            month_end = month_start + relativedelta(months=1, days=-1)
            
            month_calcs = calculations.filtered(
                lambda c: month_start <= c.payment_date <= month_end and 
                c.state in ['validated', 'approved', 'paid']
            )
            
            monthly_data.append({
                'month': month_start.strftime('%b %Y'),
                'amount': sum(month_calcs.mapped('commission_amount_company')),
                'count': len(month_calcs)
            })
        
        # Collection efficiency by range
        range_data = []
        ranges = [
            ('early', _('Early (< 0 days)'), lambda d: d < 0),
            ('ontime', _('On Time (0-15 days)'), lambda d: 0 <= d <= 15),
            ('minor', _('Minor Delay (16-30 days)'), lambda d: 16 <= d <= 30),
            ('moderate', _('Moderate Delay (31-60 days)'), lambda d: 31 <= d <= 60),
            ('major', _('Major Delay (61-120 days)'), lambda d: 61 <= d <= 120),
            ('critical', _('Critical Delay (> 120 days)'), lambda d: d > 120),
        ]
        
        for key, label, condition in ranges:
            range_calcs = calculations.filtered(
                lambda c: c.state in ['validated', 'approved', 'paid'] and 
                condition(c.days_overdue)
            )
            range_data.append({
                'key': key,
                'label': label,
                'count': len(range_calcs),
                'amount': sum(range_calcs.mapped('commission_amount_company'))
            })
        
        return {
            'states': states_data,
            'monthly_trend': monthly_data,
            'collection_ranges': range_data,
            'total_commission': self.total_commission_amount,
            'avg_collection_days': self.avg_collection_days,
            'calculation_count': self.commission_calculation_count,
        }

    @api.model
    def create_commission_config_for_all_users(self):
        """Utility method to create commission configurations for all sales users"""
        sales_users = self.search([
            ('share', '=', False),
            ('sale_team_id', '!=', False)
        ])
        
        created_count = 0
        for user in sales_users:
            for company in user.company_ids:
                existing = self.env['salesperson.config'].search([
                    ('user_id', '=', user.id),
                    ('company_id', '=', company.id)
                ], limit=1)
                
                if not existing:
                    self.env['salesperson.config'].create({
                        'user_id': user.id,
                        'company_id': company.id,
                        'commission_active': True,
                    })
                    created_count += 1
        
        return created_count