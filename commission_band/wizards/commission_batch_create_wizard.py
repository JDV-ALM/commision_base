# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta


class CommissionBatchCreateWizard(models.TransientModel):
    _name = 'commission.batch.create.wizard'
    _description = 'Create Commission Batch Wizard'

    name = fields.Char(
        string='Batch Name',
        required=True,
        help="Name for the new commission batch"
    )
    
    period_type = fields.Selection([
        ('month', 'Monthly'),
        ('custom', 'Custom Period')
    ], string='Period Type', default='month', required=True)
    
    month = fields.Selection([
        ('01', 'January'), ('02', 'February'), ('03', 'March'),
        ('04', 'April'), ('05', 'May'), ('06', 'June'),
        ('07', 'July'), ('08', 'August'), ('09', 'September'),
        ('10', 'October'), ('11', 'November'), ('12', 'December')
    ], string='Month', default=lambda self: fields.Date.today().strftime('%m'))
    
    year = fields.Integer(
        string='Year',
        default=lambda self: fields.Date.today().year,
        required=True
    )
    
    date_from = fields.Date(
        string='Date From',
        required=True
    )
    date_to = fields.Date(
        string='Date To',
        required=True
    )
    payment_date = fields.Date(
        string='Payment Date',
        required=True,
        help="Date when commissions will be paid (usually 10th of next month)"
    )
    
    # Preview information
    calculation_count = fields.Integer(
        string='Calculations Found',
        compute='_compute_preview',
        help="Number of commission calculations found for the period"
    )
    salesperson_count = fields.Integer(
        string='Salespersons',
        compute='_compute_preview'
    )
    total_amount = fields.Float(
        string='Total Amount',
        compute='_compute_preview'
    )
    
    include_validated = fields.Boolean(
        string='Include Validated Calculations',
        default=True,
        help="Include calculations in 'validated' state"
    )
    include_approved = fields.Boolean(
        string='Include Approved Calculations',
        default=False,
        help="Include calculations in 'approved' state (not yet paid)"
    )

    @api.onchange('period_type', 'month', 'year')
    def _onchange_period(self):
        """Update dates based on period selection"""
        if self.period_type == 'month' and self.month and self.year:
            # Calculate first and last day of the month
            date_str = f"{self.year}-{self.month}-01"
            first_day = fields.Date.from_string(date_str)
            last_day = first_day + relativedelta(months=1, days=-1)
            
            self.date_from = first_day
            self.date_to = last_day
            
            # Set payment date to 10th of next month
            next_month = first_day + relativedelta(months=1)
            self.payment_date = next_month.replace(day=10)
            
            # Update default name
            if not self.name or 'Commissions' in self.name:
                month_name = dict(self._fields['month'].selection)[self.month]
                self.name = _("Commissions %s %s") % (month_name, self.year)

    @api.depends('date_from', 'date_to', 'include_validated', 'include_approved')
    def _compute_preview(self):
        """Compute preview information"""
        for wizard in self:
            if wizard.date_from and wizard.date_to:
                # Build domain for calculations
                domain = [
                    ('payment_date', '>=', wizard.date_from),
                    ('payment_date', '<=', wizard.date_to),
                    ('batch_id', '=', False),
                    ('company_id', '=', self.env.company.id)
                ]
                
                # Add state filter
                states = ['calculated']
                if wizard.include_validated:
                    states.append('validated')
                if wizard.include_approved:
                    states.append('approved')
                
                domain.append(('state', 'in', states))
                
                calculations = self.env['commission.calculation'].search(domain)
                
                wizard.calculation_count = len(calculations)
                wizard.salesperson_count = len(calculations.mapped('salesperson_id'))
                
                # Calculate total in company currency
                total = 0.0
                for calc in calculations:
                    total += calc.commission_amount_company
                wizard.total_amount = total
            else:
                wizard.calculation_count = 0
                wizard.salesperson_count = 0
                wizard.total_amount = 0.0

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        """Ensure date_from <= date_to"""
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_("'Date From' must be before or equal to 'Date To'"))

    def action_create_batch(self):
        """Create the commission batch"""
        self.ensure_one()
        
        # Check for existing batch in the period
        existing = self.env['commission.batch'].search([
            ('date_from', '<=', self.date_to),
            ('date_to', '>=', self.date_from),
            ('company_id', '=', self.env.company.id),
            ('state', '!=', 'cancelled')
        ], limit=1)
        
        if existing:
            raise UserError(_(
                "A batch already exists for this period: %s\n"
                "Please select a different period or modify the existing batch."
            ) % existing.name)
        
        # Check if there are calculations to include
        if self.calculation_count == 0:
            raise UserError(_("No commission calculations found for the selected period and criteria."))
        
        # Create the batch
        batch = self.env['commission.batch'].create({
            'name': self.name,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'payment_date': self.payment_date,
            'company_id': self.env.company.id,
        })
        
        # Calculate commissions for the batch
        batch.action_calculate()
        
        # Return action to open the created batch
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'commission.batch',
            'res_id': batch.id,
            'view_mode': 'form',
            'target': 'current',
        }