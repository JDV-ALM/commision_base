# -*- coding: utf-8 -*-
{
    'name': 'Commission Band - Prelation System',
    'version': '18.0.1.0.0',
    'category': 'Sales/Commission',
    'summary': 'Advanced commission calculation based on payment collection time bands',
    'description': """
Commission Band Management System
=================================

This module extends Odoo's commission system to implement a "Prelation Band" system
that calculates commissions based on the time elapsed between invoice due date and
actual payment collection.

Key Features:
-------------
* Configurable commission bands with time-based ranges
* Rule-based commission assignment with priorities
* Automatic calculation upon payment reconciliation
* Multi-currency support (commission in payment currency)
* Individual salesperson configuration
* Complete audit trail and approval workflow

Main Components:
---------------
* Commission Bands: Define percentage scales based on collection days
* Commission Rules: Apply bands based on multiple criteria
* Automatic Calculation: Triggered on payment reconciliation
* Flexible Configuration: Manual setup for all parameters
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'sale_commission',
        'account',
        'sales_team',
        'sale_management',
    ],
    'data': [
        # Security
        'security/commission_band_security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/commission_band_data.xml',
        
        # Wizards
        'wizards/commission_band_config_wizard_views.xml',
        
        # Views
        'views/commission_band_views.xml',
        'views/commission_rule_views.xml',
        'views/salesperson_config_views.xml',
        'views/commission_calculation_views.xml',
        'views/res_users_views.xml',
        'views/commission_band_menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}