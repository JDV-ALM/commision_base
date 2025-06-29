# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CommissionRule(models.Model):
    _name = 'commission.rule'
    _description = 'Commission Rule - Configurable Commission Assignment'
    _order = 'priority, sequence, name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Rule Name',
        required=True,
        tracking=True,
        help="Descriptive name for this commission rule"
    )
    code = fields.Char(
        string='Code',
        required=True,
        tracking=True,
        help="Unique code to identify this rule"
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
        help="If unchecked, this rule will not be evaluated"
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
        help="Used to order rules within the same priority"
    )
    priority = fields.Integer(
        string='Priority',
        default=10,
        required=True,
        tracking=True,
        help="Lower number means higher priority. Rules are evaluated in priority order."
    )
    
    # Application criteria
    salesperson_ids = fields.Many2many(
        'res.users',
        'commission_rule_user_rel',
        'rule_id',
        'user_id',
        string='Specific Salespersons',
        domain=[('share', '=', False)],
        help="Leave empty to apply to all salespersons"
    )
    team_ids = fields.Many2many(
        'crm.team',
        'commission_rule_team_rel',
        'rule_id',
        'team_id',
        string='Sales Teams',
        help="Leave empty to apply to all teams"
    )
    category_ids = fields.Many2many(
        'product.category',
        'commission_rule_category_rel',
        'rule_id',
        'category_id',
        string='Product Categories',
        help="Leave empty to apply to all categories"
    )
    product_ids = fields.Many2many(
        'product.product',
        'commission_rule_product_rel',
        'rule_id',
        'product_id',
        string='Specific Products',
        help="Leave empty to apply to all products"
    )
    customer_ids = fields.Many2many(
        'res.partner',
        'commission_rule_partner_rel',
        'rule_id',
        'partner_id',
        string='Specific Customers',
        domain=[('is_company', '=', True)],
        help="Leave empty to apply to all customers"
    )
    
    # Commission configuration
    commission_type = fields.Selection([
        ('percentage', 'Fixed Percentage'),
        ('fixed', 'Fixed Amount'),
        ('band', 'Prelation Band'),
        ('none', 'No Commission')
    ], string='Commission Type', required=True, default='band', tracking=True)
    
    fixed_amount = fields.Monetary(
        string='Fixed Amount',
        currency_field='currency_id',
        help="Fixed commission amount (when type is 'fixed')"
    )
    percentage_rate = fields.Float(
        string='Fixed Percentage',
        digits=(5, 4),
        help="Fixed commission percentage (when type is 'percentage')"
    )
    band_id = fields.Many2one(
        'commission.band',
        string='Prelation Band',
        help="Commission band to use (when type is 'band')"
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )
    
    # Additional conditions
    date_from = fields.Date(
        string='Valid From',
        tracking=True,
        help="Start date for this rule (inclusive)"
    )
    date_to = fields.Date(
        string='Valid Until',
        tracking=True,
        help="End date for this rule (inclusive)"
    )
    min_amount = fields.Monetary(
        string='Minimum Amount',
        currency_field='currency_id',
        help="Minimum payment amount for this rule to apply"
    )
    max_amount = fields.Monetary(
        string='Maximum Amount',
        currency_field='currency_id',
        help="Maximum payment amount for this rule to apply"
    )
    
    # Payment conditions
    payment_term_ids = fields.Many2many(
        'account.payment.term',
        'commission_rule_payment_term_rel',
        'rule_id',
        'payment_term_id',
        string='Payment Terms',
        help="Apply only to invoices with these payment terms"
    )
    journal_ids = fields.Many2many(
        'account.journal',
        'commission_rule_journal_rel',
        'rule_id',
        'journal_id',
        string='Payment Journals',
        domain=[('type', 'in', ['bank', 'cash'])],
        help="Apply only to payments from these journals"
    )
    
    # Statistics - Made searchable with store=True
    calculation_count = fields.Integer(
        string='Number of Calculations',
        compute='_compute_calculation_count',
        store=True
    )
    
    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)',
         'The code must be unique per company!'),
    ]

    @api.constrains('commission_type', 'band_id', 'fixed_amount', 'percentage_rate')
    def _check_commission_config(self):
        """Ensure commission configuration is complete"""
        for rule in self:
            if rule.commission_type == 'band' and not rule.band_id:
                raise ValidationError(_("Please select a commission band for rule '%s'") % rule.name)
            elif rule.commission_type == 'fixed' and not rule.fixed_amount:
                raise ValidationError(_("Please set a fixed amount for rule '%s'") % rule.name)
            elif rule.commission_type == 'percentage' and not rule.percentage_rate:
                raise ValidationError(_("Please set a percentage rate for rule '%s'") % rule.name)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        """Ensure date_from <= date_to"""
        for rule in self:
            if rule.date_from and rule.date_to and rule.date_from > rule.date_to:
                raise ValidationError(_("'Valid From' must be before or equal to 'Valid Until'"))

    @api.constrains('min_amount', 'max_amount')
    def _check_amounts(self):
        """Ensure min_amount <= max_amount"""
        for rule in self:
            if rule.min_amount and rule.max_amount and rule.min_amount > rule.max_amount:
                raise ValidationError(_("'Minimum Amount' must be less than or equal to 'Maximum Amount'"))

    def _compute_calculation_count(self):
        """Compute the number of calculations using this rule"""
        for rule in self:
            rule.calculation_count = self.env['commission.calculation'].search_count([
                ('rule_id', '=', rule.id)
            ])

    @api.onchange('commission_type')
    def _onchange_commission_type(self):
        """Clear irrelevant fields when commission type changes"""
        if self.commission_type != 'band':
            self.band_id = False
        if self.commission_type != 'fixed':
            self.fixed_amount = 0
        if self.commission_type != 'percentage':
            self.percentage_rate = 0

    def action_view_calculations(self):
        """Action to view all calculations using this rule"""
        self.ensure_one()
        return {
            'name': _('Commission Calculations'),
            'type': 'ir.actions.act_window',
            'res_model': 'commission.calculation',
            'view_mode': 'list,form,graph,pivot',
            'domain': [('rule_id', '=', self.id)],
        }

    def matches_criteria(self, invoice=None, payment=None, salesperson=None):
        """Check if this rule matches the given criteria
        
        Args:
            invoice: account.move record
            payment: account.payment record
            salesperson: res.users record
            
        Returns:
            bool: True if all criteria match
        """
        self.ensure_one()
        
        # Check dates
        check_date = payment.date if payment else fields.Date.today()
        if self.date_from and check_date < self.date_from:
            return False
        if self.date_to and check_date > self.date_to:
            return False
        
        # Check amount
        amount = payment.amount if payment else 0
        if self.min_amount and amount < self.min_amount:
            return False
        if self.max_amount and amount > self.max_amount:
            return False
        
        # Check salesperson
        if self.salesperson_ids and salesperson:
            if salesperson not in self.salesperson_ids:
                return False
        
        # Check team
        if self.team_ids and salesperson and salesperson.sale_team_id:
            if salesperson.sale_team_id not in self.team_ids:
                return False
        
        # Check customer
        if self.customer_ids and invoice:
            if invoice.partner_id not in self.customer_ids:
                return False
        
        # Check payment term
        if self.payment_term_ids and invoice:
            if invoice.invoice_payment_term_id not in self.payment_term_ids:
                return False
        
        # Check journal
        if self.journal_ids and payment:
            if payment.journal_id not in self.journal_ids:
                return False
        
        # Check products and categories
        if (self.product_ids or self.category_ids) and invoice:
            invoice_products = invoice.invoice_line_ids.mapped('product_id')
            invoice_categories = invoice_products.mapped('categ_id')
            
            if self.product_ids:
                if not any(p in self.product_ids for p in invoice_products):
                    return False
            
            if self.category_ids:
                if not any(c in self.category_ids for c in invoice_categories):
                    return False
        
        return True

    def calculate_commission(self, payment, invoice, salesperson):
        """Calculate commission based on rule configuration
        
        Args:
            payment: account.payment record
            invoice: account.move record
            salesperson: res.users record
            
        Returns:
            dict: Commission calculation data or None
        """
        self.ensure_one()
        
        if self.commission_type == 'none':
            return None
        
        base_data = {
            'payment_amount': payment.amount,
            'invoice_date': invoice.invoice_date,
            'due_date': invoice.invoice_date_due,
            'payment_date': payment.date,
        }
        
        if self.commission_type == 'fixed':
            return {
                **base_data,
                'commission_rate': 0,
                'commission_amount': self.fixed_amount,
            }
        
        elif self.commission_type == 'percentage':
            return {
                **base_data,
                'commission_rate': self.percentage_rate,
                'commission_amount': payment.amount * (self.percentage_rate / 100.0),
            }
        
        elif self.commission_type == 'band' and self.band_id:
            # Calculate days overdue
            days_overdue = (payment.date - invoice.invoice_date_due).days
            
            # Get commission rate from band
            rate, indicator_rate, range_id = self.band_id.get_commission_rate(
                days_overdue,
                payment.amount,
                payment.currency_id.id
            )
            
            if rate > 0:
                return {
                    **base_data,
                    'band_id': self.band_id.id,
                    'range_id': range_id,
                    'days_overdue': days_overdue,
                    'commission_rate': rate * 100,  # Convert to percentage
                    'commission_amount': payment.amount * rate,
                }
        
        return None

    def copy(self, default=None):
        default = dict(default or {})
        default['name'] = _("%s (copy)") % self.name
        default['code'] = _("%s_COPY") % self.code
        return super().copy(default)