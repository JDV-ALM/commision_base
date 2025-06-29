# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class CommissionBandConfigWizard(models.TransientModel):
    _name = 'commission.band.config.wizard'
    _description = 'Commission Band Configuration Wizard'

    name = fields.Char(
        string='Configuration Name',
        default='Initial Commission Configuration',
        required=True
    )
    
    # Step tracking
    state = fields.Selection([
        ('welcome', 'Welcome'),
        ('bands', 'Create Bands'),
        ('rules', 'Create Rules'),
        ('users', 'Assign Users'),
        ('done', 'Done')
    ], default='welcome', string='Step')
    
    # Band creation
    create_default_bands = fields.Boolean(
        string='Create Default Bands',
        default=True,
        help="Create the standard commission bands based on Excel template"
    )
    
    band_ids = fields.Many2many(
        'commission.band',
        string='Created Bands',
        readonly=True
    )
    
    # Rule creation
    create_default_rules = fields.Boolean(
        string='Create Default Rules',
        default=True,
        help="Create standard commission rules"
    )
    
    rule_ids = fields.Many2many(
        'commission.rule',
        string='Created Rules',
        readonly=True
    )
    
    # User assignment
    user_ids = fields.Many2many(
        'res.users',
        string='Sales Users',
        domain=[('share', '=', False)],
        help="Select users to configure for commission calculation"
    )
    
    activate_all_users = fields.Boolean(
        string='Activate for All Sales Users',
        default=False,
        help="Automatically activate commission for all users with sales teams"
    )
    
    # Summary
    summary = fields.Html(
        string='Configuration Summary',
        readonly=True
    )

    def action_next(self):
        """Move to next step"""
        self.ensure_one()
        
        if self.state == 'welcome':
            self.state = 'bands'
        elif self.state == 'bands':
            if self.create_default_bands:
                self._create_default_bands()
            self.state = 'rules'
        elif self.state == 'rules':
            if self.create_default_rules:
                self._create_default_rules()
            self.state = 'users'
        elif self.state == 'users':
            self._configure_users()
            self._generate_summary()
            self.state = 'done'
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_previous(self):
        """Move to previous step"""
        self.ensure_one()
        
        if self.state == 'bands':
            self.state = 'welcome'
        elif self.state == 'rules':
            self.state = 'bands'
        elif self.state == 'users':
            self.state = 'rules'
        elif self.state == 'done':
            self.state = 'users'
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _create_default_bands(self):
        """Create default commission bands based on Excel template"""
        self.ensure_one()
        
        band_obj = self.env['commission.band']
        range_obj = self.env['commission.range']
        
        bands_data = [
            {
                'name': 'Premium Sales Band (Type A)',
                'code': 'BAND_PREMIUM',
                'description': 'Commission band for premium salespersons with higher rates',
                'ranges': [
                    {'from': -999, 'to': 15, 'rate': 2.8, 'indicator': 3.5, 'name': 'Early payment'},
                    {'from': 16, 'to': 30, 'rate': 2.3, 'indicator': 3.0, 'name': 'On time'},
                    {'from': 31, 'to': 45, 'rate': 1.8, 'indicator': 2.5, 'name': 'Minor delay'},
                    {'from': 46, 'to': 60, 'rate': 1.3, 'indicator': 2.0, 'name': 'Moderate delay'},
                    {'from': 61, 'to': 120, 'rate': 1.0, 'indicator': 1.7, 'name': 'Major delay'},
                    {'from': 121, 'to': 999, 'rate': 0.5, 'indicator': 0.5, 'name': 'Critical delay'},
                ]
            },
            {
                'name': 'Supervision Band (Type B)',
                'code': 'BAND_SUPERVISION',
                'description': 'Commission band for supervisors and team leads',
                'ranges': [
                    {'from': -999, 'to': 15, 'rate': 2.0, 'indicator': 0, 'name': 'Early payment'},
                    {'from': 16, 'to': 30, 'rate': 1.5, 'indicator': 0, 'name': 'On time'},
                    {'from': 31, 'to': 45, 'rate': 1.0, 'indicator': 0, 'name': 'Minor delay'},
                    {'from': 46, 'to': 60, 'rate': 0.75, 'indicator': 0, 'name': 'Moderate delay'},
                    {'from': 61, 'to': 120, 'rate': 0.5, 'indicator': 0, 'name': 'Major delay'},
                    {'from': 121, 'to': 999, 'rate': 0.25, 'indicator': 0, 'name': 'Critical delay'},
                ]
            },
            {
                'name': 'Office Band (Type C)',
                'code': 'BAND_OFFICE',
                'description': 'Commission band for office sales staff',
                'ranges': [
                    {'from': -999, 'to': 30, 'rate': 1.5, 'indicator': 0, 'name': 'On time'},
                    {'from': 31, 'to': 60, 'rate': 1.5, 'indicator': 0, 'name': 'Acceptable delay'},
                    {'from': 61, 'to': 999, 'rate': 0.0, 'indicator': 0, 'name': 'Late payment'},
                ]
            },
        ]
        
        created_bands = band_obj
        
        for band_data in bands_data:
            # Check if band already exists
            existing = band_obj.search([('code', '=', band_data['code'])], limit=1)
            if existing:
                continue
            
            # Create band
            band = band_obj.create({
                'name': band_data['name'],
                'code': band_data['code'],
                'description': band_data['description'],
                'company_id': self.env.company.id,
            })
            
            # Create ranges
            for idx, range_data in enumerate(band_data['ranges']):
                range_obj.create({
                    'band_id': band.id,
                    'name': range_data['name'],
                    'day_from': range_data['from'],
                    'day_to': range_data['to'],
                    'commission_rate': range_data['rate'],
                    'indicator_rate': range_data['indicator'],
                    'sequence': idx * 10,
                })
            
            created_bands |= band
        
        self.band_ids = created_bands

    def _create_default_rules(self):
        """Create default commission rules"""
        self.ensure_one()
        
        rule_obj = self.env['commission.rule']
        
        # Get created bands
        band_premium = self.env['commission.band'].search([('code', '=', 'BAND_PREMIUM')], limit=1)
        band_supervision = self.env['commission.band'].search([('code', '=', 'BAND_SUPERVISION')], limit=1)
        band_office = self.env['commission.band'].search([('code', '=', 'BAND_OFFICE')], limit=1)
        
        rules_data = [
            {
                'name': 'Premium Sales Rule',
                'code': 'RULE_PREMIUM',
                'priority': 10,
                'commission_type': 'band',
                'band_id': band_premium.id if band_premium else False,
            },
            {
                'name': 'Supervision Rule',
                'code': 'RULE_SUPERVISION',
                'priority': 20,
                'commission_type': 'band',
                'band_id': band_supervision.id if band_supervision else False,
            },
            {
                'name': 'Office Sales Rule',
                'code': 'RULE_OFFICE',
                'priority': 30,
                'commission_type': 'band',
                'band_id': band_office.id if band_office else False,
            },
            {
                'name': 'No Commission Rule',
                'code': 'RULE_NO_COMMISSION',
                'priority': 100,
                'commission_type': 'none',
            },
        ]
        
        created_rules = rule_obj
        
        for rule_data in rules_data:
            # Skip if no band assigned (for band type rules)
            if rule_data['commission_type'] == 'band' and not rule_data.get('band_id'):
                continue
            
            # Check if rule already exists
            existing = rule_obj.search([('code', '=', rule_data['code'])], limit=1)
            if existing:
                continue
            
            # Create rule
            rule = rule_obj.create({
                'name': rule_data['name'],
                'code': rule_data['code'],
                'priority': rule_data['priority'],
                'commission_type': rule_data['commission_type'],
                'band_id': rule_data.get('band_id', False),
                'company_id': self.env.company.id,
            })
            
            created_rules |= rule
        
        self.rule_ids = created_rules

    def _configure_users(self):
        """Configure commission for selected users"""
        self.ensure_one()
        
        config_obj = self.env['salesperson.config']
        
        # Get users to configure
        if self.activate_all_users:
            users = self.env['res.users'].search([
                ('share', '=', False),
                ('sale_team_id', '!=', False)
            ])
        else:
            users = self.user_ids
        
        # Get default rule (lowest priority)
        default_rule = self.rule_ids.sorted('priority')[-1] if self.rule_ids else False
        
        for user in users:
            # Create or update configuration
            config_obj.create_or_update_config(
                user.id,
                self.env.company.id,
                {
                    'commission_active': True,
                    'default_rule_id': default_rule.id if default_rule else False,
                }
            )

    def _generate_summary(self):
        """Generate configuration summary"""
        self.ensure_one()
        
        summary_lines = [
            '<h3>Commission Configuration Summary</h3>',
            '<ul>'
        ]
        
        # Bands summary
        if self.band_ids:
            summary_lines.append('<li><strong>Commission Bands Created:</strong>')
            summary_lines.append('<ul>')
            for band in self.band_ids:
                summary_lines.append(f'<li>{band.name} ({len(band.range_ids)} ranges)</li>')
            summary_lines.append('</ul></li>')
        
        # Rules summary
        if self.rule_ids:
            summary_lines.append('<li><strong>Commission Rules Created:</strong>')
            summary_lines.append('<ul>')
            for rule in self.rule_ids:
                rule_type = dict(rule._fields['commission_type'].selection)[rule.commission_type]
                summary_lines.append(f'<li>{rule.name} - Type: {rule_type}</li>')
            summary_lines.append('</ul></li>')
        
        # Users summary
        if self.activate_all_users:
            user_count = self.env['res.users'].search_count([
                ('share', '=', False),
                ('sale_team_id', '!=', False)
            ])
            summary_lines.append(f'<li><strong>Users Configured:</strong> All {user_count} sales users</li>')
        elif self.user_ids:
            summary_lines.append(f'<li><strong>Users Configured:</strong> {len(self.user_ids)} selected users</li>')
        
        summary_lines.append('</ul>')
        summary_lines.append('<p><strong>Configuration completed successfully!</strong></p>')
        
        self.summary = '\n'.join(summary_lines)

    def action_close(self):
        """Close wizard and optionally open commission configuration"""
        self.ensure_one()
        
        if self.state == 'done':
            # Open commission bands list view - CORREGIDO: tree -> list
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'commission.band',
                'view_mode': 'list,form',  # CAMBIADO DE tree,form a list,form
                'target': 'current',
            }
        
        return {'type': 'ir.actions.act_window_close'}