# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CommissionRange(models.Model):
    _name = 'commission.range'
    _description = 'Commission Range - Day-based Commission Percentage'
    _order = 'band_id, sequence, day_from'
    _rec_name = 'display_name'

    band_id = fields.Many2one(
        'commission.band',
        string='Commission Band',
        required=True,
        ondelete='cascade',
        index=True
    )
    name = fields.Char(
        string='Range Description',
        help="Description of this day range (e.g., 'Early Payment', 'On Time', 'Late')"
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help="Used to order ranges within the band"
    )
    
    # Day range configuration
    day_from = fields.Integer(
        string='Days From',
        required=True,
        help="Start of day range (negative for days before due date)"
    )
    day_to = fields.Integer(
        string='Days To',
        required=True,
        help="End of day range (positive for days after due date)"
    )
    
    # Commission rates
    commission_rate = fields.Float(
        string='Commission Rate (%)',
        required=True,
        digits=(5, 4),
        help="Base commission percentage for this range"
    )
    indicator_rate = fields.Float(
        string='Indicator Rate (%)',
        digits=(5, 4),
        help="Additional rate for performance indicators"
    )
    
    # Additional conditions
    apply_only_currency_id = fields.Many2one(
        'res.currency',
        string='Apply Only to Currency',
        help="If set, this range only applies to payments in this currency"
    )
    min_payment_amount = fields.Monetary(
        string='Minimum Payment Amount',
        currency_field='currency_id',
        help="Minimum payment amount for this range to apply"
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='band_id.company_id.currency_id',
        store=True,
        readonly=True
    )
    
    # Display fields
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    color = fields.Integer(
        string='Color Index',
        compute='_compute_color'
    )

    @api.depends('day_from', 'day_to', 'name', 'commission_rate')
    def _compute_display_name(self):
        for range_rec in self:
            if range_rec.name:
                display = range_rec.name
            else:
                if range_rec.day_from <= -999:
                    display = _("Up to %s days") % range_rec.day_to
                elif range_rec.day_to >= 999:
                    display = _("From %s days onwards") % range_rec.day_from
                else:
                    display = _("%s to %s days") % (range_rec.day_from, range_rec.day_to)
            
            display += " (%.2f%%)" % range_rec.commission_rate
            range_rec.display_name = display

    @api.depends('commission_rate')
    def _compute_color(self):
        """Compute color based on commission rate for visual identification"""
        for range_rec in self:
            if range_rec.commission_rate >= 3:
                range_rec.color = 10  # Green
            elif range_rec.commission_rate >= 2:
                range_rec.color = 3   # Yellow
            elif range_rec.commission_rate >= 1:
                range_rec.color = 2   # Orange
            else:
                range_rec.color = 1   # Red

    @api.constrains('day_from', 'day_to')
    def _check_day_range(self):
        """Ensure day_from <= day_to"""
        for range_rec in self:
            if range_rec.day_from > range_rec.day_to:
                raise ValidationError(_(
                    "'Days From' (%s) must be less than or equal to 'Days To' (%s)"
                ) % (range_rec.day_from, range_rec.day_to))

    @api.constrains('commission_rate')
    def _check_commission_rate(self):
        """Ensure commission rate is not negative"""
        for range_rec in self:
            if range_rec.commission_rate < 0:
                raise ValidationError(_("Commission rate cannot be negative!"))

    @api.constrains('indicator_rate')
    def _check_indicator_rate(self):
        """Ensure indicator rate is not negative"""
        for range_rec in self:
            if range_rec.indicator_rate < 0:
                raise ValidationError(_("Indicator rate cannot be negative!"))

    @api.onchange('day_from', 'day_to')
    def _onchange_days(self):
        """Auto-generate name based on day range"""
        if self.day_from is not False and self.day_to is not False:
            if not self.name:
                if self.day_from <= -100:
                    self.name = _("Early payment")
                elif self.day_from <= 0 and self.day_to >= 0:
                    self.name = _("On time")
                elif self.day_from <= 30:
                    self.name = _("Minor delay")
                elif self.day_from <= 60:
                    self.name = _("Moderate delay")
                elif self.day_from <= 120:
                    self.name = _("Major delay")
                else:
                    self.name = _("Critical delay")

    def get_commission_info(self):
        """Get formatted commission information for this range"""
        self.ensure_one()
        info = {
            'range': self.display_name,
            'commission_rate': self.commission_rate,
            'indicator_rate': self.indicator_rate,
            'conditions': []
        }
        
        if self.apply_only_currency_id:
            info['conditions'].append(
                _("Only for %s") % self.apply_only_currency_id.name
            )
        
        if self.min_payment_amount:
            info['conditions'].append(
                _("Minimum amount: %s") % self.min_payment_amount
            )
        
        return info