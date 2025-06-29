# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SalespersonConfig(models.Model):
    _name = 'salesperson.config'
    _description = 'Salesperson Commission Configuration'
    _rec_name = 'user_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    user_id = fields.Many2one(
        'res.users',
        string='Salesperson',
        required=True,
        ondelete='cascade',
        domain=[('share', '=', False)],
        tracking=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    
    # Commission configuration
    commission_active = fields.Boolean(
        string='Commission Active',
        default=True,
        tracking=True,
        help="If unchecked, no commissions will be calculated for this salesperson"
    )
    default_rule_id = fields.Many2one(
        'commission.rule',
        string='Default Rule',
        tracking=True,
        help="Default commission rule for this salesperson when no other rule applies"
    )
    
    # Override settings
    override_commission_type = fields.Selection([
        ('none', 'Use Rule Settings'),
        ('percentage', 'Override with Fixed Percentage'),
        ('fixed', 'Override with Fixed Amount'),
        ('band', 'Override with Specific Band')
    ], string='Override Type', default='none', tracking=True)
    
    override_percentage = fields.Float(
        string='Override Percentage',
        digits=(5, 4),
        help="Custom percentage to use instead of rule settings"
    )
    override_fixed_amount = fields.Monetary(
        string='Override Fixed Amount',
        currency_field='currency_id',
        help="Custom fixed amount to use instead of rule settings"
    )
    override_band_id = fields.Many2one(
        'commission.band',
        string='Override Band',
        help="Custom band to use instead of rule settings"
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True
    )
    
    # Additional settings
    min_commission_amount = fields.Monetary(
        string='Minimum Commission',
        currency_field='currency_id',
        help="Minimum commission amount per calculation"
    )
    max_commission_amount = fields.Monetary(
        string='Maximum Commission',
        currency_field='currency_id',
        help="Maximum commission amount per calculation"
    )
    
    # Notes and tracking
    notes = fields.Text(
        string='Configuration Notes',
        help="Internal notes about this salesperson's commission configuration"
    )
    
    # Statistics
    calculation_count = fields.Integer(
        string='Number of Calculations',
        compute='_compute_calculation_count'
    )
    total_commission = fields.Monetary(
        string='Total Commission',
        compute='_compute_total_commission',
        currency_field='currency_id'
    )
    avg_collection_days = fields.Float(
        string='Avg. Collection Days',
        compute='_compute_avg_collection_days',
        help="Average days between invoice due date and payment"
    )
    
    # Display
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )

    _sql_constraints = [
        ('user_company_uniq', 'unique(user_id, company_id)',
         'Only one configuration per salesperson per company is allowed!'),
    ]

    @api.depends('user_id', 'commission_active')
    def _compute_display_name(self):
        for config in self:
            name = config.user_id.name if config.user_id else _("Unknown")
            if not config.commission_active:
                name += _(" (Inactive)")
            config.display_name = name

    def _compute_calculation_count(self):
        for config in self:
            config.calculation_count = self.env['commission.calculation'].search_count([
                ('salesperson_id', '=', config.user_id.id),
                ('company_id', '=', config.company_id.id)
            ])

    def _compute_total_commission(self):
        for config in self:
            calculations = self.env['commission.calculation'].search([
                ('salesperson_id', '=', config.user_id.id),
                ('company_id', '=', config.company_id.id),
                ('state', 'in', ['validated', 'approved', 'paid'])
            ])
            config.total_commission = sum(calculations.mapped('commission_amount'))

    def _compute_avg_collection_days(self):
        for config in self:
            calculations = self.env['commission.calculation'].search([
                ('salesperson_id', '=', config.user_id.id),
                ('company_id', '=', config.company_id.id),
                ('state', 'in', ['validated', 'approved', 'paid']),
                ('days_overdue', '!=', False)
            ])
            if calculations:
                config.avg_collection_days = sum(calculations.mapped('days_overdue')) / len(calculations)
            else:
                config.avg_collection_days = 0

    @api.constrains('override_commission_type', 'override_percentage', 'override_fixed_amount', 'override_band_id')
    def _check_override_config(self):
        """Ensure override configuration is complete"""
        for config in self:
            if config.override_commission_type == 'percentage' and not config.override_percentage:
                raise ValidationError(_("Please set an override percentage"))
            elif config.override_commission_type == 'fixed' and not config.override_fixed_amount:
                raise ValidationError(_("Please set an override fixed amount"))
            elif config.override_commission_type == 'band' and not config.override_band_id:
                raise ValidationError(_("Please select an override band"))

    @api.constrains('min_commission_amount', 'max_commission_amount')
    def _check_commission_limits(self):
        """Ensure min <= max"""
        for config in self:
            if (config.min_commission_amount and config.max_commission_amount and 
                config.min_commission_amount > config.max_commission_amount):
                raise ValidationError(_("Minimum commission must be less than or equal to maximum commission"))

    @api.onchange('override_commission_type')
    def _onchange_override_type(self):
        """Clear irrelevant fields when override type changes"""
        if self.override_commission_type != 'percentage':
            self.override_percentage = 0
        if self.override_commission_type != 'fixed':
            self.override_fixed_amount = 0
        if self.override_commission_type != 'band':
            self.override_band_id = False

    def action_view_calculations(self):
        """Action to view all calculations for this salesperson"""
        self.ensure_one()
        return {
            'name': _('Commission Calculations'),
            'type': 'ir.actions.act_window',
            'res_model': 'commission.calculation',
            'view_mode': 'list,form,graph,pivot',  # CAMBIADO DE tree,form,graph,pivot
            'domain': [
                ('salesperson_id', '=', self.user_id.id),
                ('company_id', '=', self.company_id.id)
            ],
            'context': {
                'default_salesperson_id': self.user_id.id,
                'search_default_group_by_state': 1,
            }
        }

    def action_toggle_active(self):
        """Toggle commission active status"""
        for config in self:
            config.commission_active = not config.commission_active

    def get_commission_parameters(self, rule=None):
        """Get commission calculation parameters considering overrides
        
        Args:
            rule: commission.rule record (optional)
            
        Returns:
            dict: Commission parameters to use for calculation
        """
        self.ensure_one()
        
        if not self.commission_active:
            return {'type': 'none'}
        
        # Check for overrides
        if self.override_commission_type != 'none':
            if self.override_commission_type == 'percentage':
                return {
                    'type': 'percentage',
                    'rate': self.override_percentage
                }
            elif self.override_commission_type == 'fixed':
                return {
                    'type': 'fixed',
                    'amount': self.override_fixed_amount
                }
            elif self.override_commission_type == 'band':
                return {
                    'type': 'band',
                    'band_id': self.override_band_id
                }
        
        # Use rule parameters if no override
        if rule:
            return {
                'type': rule.commission_type,
                'rate': rule.percentage_rate,
                'amount': rule.fixed_amount,
                'band_id': rule.band_id
            }
        
        # Use default rule if available
        if self.default_rule_id:
            return {
                'type': self.default_rule_id.commission_type,
                'rate': self.default_rule_id.percentage_rate,
                'amount': self.default_rule_id.fixed_amount,
                'band_id': self.default_rule_id.band_id
            }
        
        return {'type': 'none'}

    @api.model
    def create_or_update_config(self, user_id, company_id=None, vals=None):
        """Helper method to create or update salesperson configuration
        
        Args:
            user_id: ID of the user
            company_id: ID of the company (optional, defaults to current)
            vals: Dictionary of values to update
            
        Returns:
            salesperson.config record
        """
        if not company_id:
            company_id = self.env.company.id
        
        config = self.search([
            ('user_id', '=', user_id),
            ('company_id', '=', company_id)
        ], limit=1)
        
        if config:
            if vals:
                config.write(vals)
        else:
            create_vals = {
                'user_id': user_id,
                'company_id': company_id,
            }
            if vals:
                create_vals.update(vals)
            config = self.create(create_vals)
        
        return config