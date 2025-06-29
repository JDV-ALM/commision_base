# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CommissionBand(models.Model):
    _name = 'commission.band'
    _description = 'Commission Band - Prelation Configuration'
    _order = 'sequence, name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Band Name',
        required=True,
        tracking=True,
        help="Descriptive name for this commission band"
    )
    code = fields.Char(
        string='Code',
        required=True,
        tracking=True,
        help="Unique code to identify this band"
    )
    description = fields.Text(
        string='Description',
        help="Detailed description of when and how this band applies"
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
        help="If unchecked, this band will not be available for new rules"
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help="Used to order bands in lists"
    )
    
    # Currency configuration
    currency_specific = fields.Boolean(
        string='Currency Specific',
        default=False,
        tracking=True,
        help="Check if this band should only apply to a specific currency"
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Specific Currency',
        help="If set, this band will only apply to payments in this currency"
    )
    
    # Related ranges
    range_ids = fields.One2many(
        'commission.range',
        'band_id',
        string='Day Ranges',
        copy=True,
        help="Define the commission percentages for different day ranges"
    )
    
    # Statistics
    rule_count = fields.Integer(
        string='Number of Rules',
        compute='_compute_rule_count'
    )
    calculation_count = fields.Integer(
        string='Number of Calculations',
        compute='_compute_calculation_count'
    )
    
    # Display
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)',
         'The code must be unique per company!'),
        ('name_company_uniq', 'unique(name, company_id)',
         'The name must be unique per company!'),
    ]

    @api.depends('name', 'code', 'currency_specific', 'currency_id')
    def _compute_display_name(self):
        for band in self:
            name = f"[{band.code}] {band.name}"
            if band.currency_specific and band.currency_id:
                name += f" ({band.currency_id.name})"
            band.display_name = name

    def _compute_rule_count(self):
        for band in self:
            band.rule_count = self.env['commission.rule'].search_count([
                ('band_id', '=', band.id)
            ])

    def _compute_calculation_count(self):
        for band in self:
            band.calculation_count = self.env['commission.calculation'].search_count([
                ('band_id', '=', band.id)
            ])

    @api.constrains('range_ids')
    def _check_range_overlap(self):
        """Ensure day ranges don't overlap within the same band"""
        for band in self:
            ranges = band.range_ids.sorted('day_from')
            for i in range(len(ranges) - 1):
                if ranges[i].day_to >= ranges[i + 1].day_from:
                    raise ValidationError(_(
                        "Day ranges cannot overlap! Range '%s' (%s to %s days) "
                        "overlaps with range '%s' (%s to %s days)."
                    ) % (
                        ranges[i].name,
                        ranges[i].day_from,
                        ranges[i].day_to,
                        ranges[i + 1].name,
                        ranges[i + 1].day_from,
                        ranges[i + 1].day_to
                    ))

    @api.constrains('range_ids')
    def _check_range_coverage(self):
        """Ensure ranges cover all possible days"""
        for band in self:
            if not band.range_ids:
                continue
            
            ranges = band.range_ids.sorted('day_from')
            
            # Check if there's a range starting from negative (before due date)
            if ranges[0].day_from > -999:
                raise ValidationError(_(
                    "Commission band '%s' must have a range covering early payments "
                    "(starting from -999 days or earlier)."
                ) % band.name)
            
            # Check if there's a range going to positive infinity
            if ranges[-1].day_to < 999:
                raise ValidationError(_(
                    "Commission band '%s' must have a range covering late payments "
                    "(ending at 999 days or later)."
                ) % band.name)

    def action_view_rules(self):
        """Action to view all rules using this band"""
        self.ensure_one()
        return {
            'name': _('Commission Rules'),
            'type': 'ir.actions.act_window',
            'res_model': 'commission.rule',
            'view_mode': 'tree,form',
            'domain': [('band_id', '=', self.id)],
            'context': {'default_band_id': self.id},
        }

    def action_view_calculations(self):
        """Action to view all calculations using this band"""
        self.ensure_one()
        return {
            'name': _('Commission Calculations'),
            'type': 'ir.actions.act_window',
            'res_model': 'commission.calculation',
            'view_mode': 'tree,form,graph,pivot',
            'domain': [('band_id', '=', self.id)],
        }

    @api.model
    def get_commission_rate(self, days_overdue, payment_amount=0, currency_id=None):
        """Get the commission rate for a given number of days overdue
        
        Args:
            days_overdue: Number of days after due date (negative for early payment)
            payment_amount: Amount of the payment (for minimum amount validation)
            currency_id: Currency of the payment (for currency-specific bands)
        
        Returns:
            tuple: (commission_rate, indicator_rate, range_id)
        """
        self.ensure_one()
        
        # Check currency compatibility
        if self.currency_specific and self.currency_id:
            if not currency_id or currency_id != self.currency_id.id:
                return (0.0, 0.0, False)
        
        # Find applicable range
        applicable_range = self.range_ids.filtered(
            lambda r: r.day_from <= days_overdue <= r.day_to and
            (not r.min_payment_amount or payment_amount >= r.min_payment_amount) and
            (not r.apply_only_currency_id or r.apply_only_currency_id.id == currency_id)
        )
        
        if applicable_range:
            # Get the first range (should be only one due to overlap validation)
            range_rec = applicable_range[0]
            return (
                range_rec.commission_rate / 100.0,
                range_rec.indicator_rate / 100.0,
                range_rec.id
            )
        
        return (0.0, 0.0, False)

    def copy(self, default=None):
        default = dict(default or {})
        default['name'] = _("%s (copy)") % self.name
        default['code'] = _("%s_COPY") % self.code
        return super().copy(default)