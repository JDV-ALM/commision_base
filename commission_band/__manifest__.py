# -*- coding: utf-8 -*-
{
    'name': 'Bandas de Comisiones - Sistema de Prelación',
    'version': '18.0.1.0.0',
    'category': 'Sales/Commission',
    'summary': 'Advanced commission calculation based on payment collection time bands',
    'description': """
Sistema de Bandas de Comisiones 
=================================

Este módulo extiende el sistema de comisiones de Odoo para implementar un sistema de "Bandas de Comisiones"
que calcula las comisiones basado en el tiempo transcurrido entre la fecha de vencimiento de la factura y la fecha de recolección de la
pago.   

Características Clave:
-------------
* Configuración de bandas de comisiones con rangos de tiempo
* Asignación de comisiones basada en reglas
* Cálculo automático al reconciliar el pago
* Soporte para múltiples monedas (comisión en la moneda del pago)
* Configuración individual para cada vendedor
* Trazabilidad completa y flujo de aprobación
* **Nuevo: Gestión de lotes de comisiones para el procesamiento mensual**
* **Nuevo: Generación de documentos de pago con conversión de moneda**

Componentes Principales:
---------------
* Bandas de Comisiones: Define porcentajes basados en los días de recolección
* Reglas de Comisiones: Aplica bandas basadas en múltiples criterios
* Cálculo Automático: Activado al reconciliar el pago
* Configuración Flexible: Configuración manual para todos los parámetros
* **Lotes de Comisiones: Agrupa comisiones mensuales para revisión y pago**
* **Documentos de Pago: Genera instrucciones de pago con manejo adecuado de monedas**
    """,
    'author': 'Almus Dev',
    'website': 'https://www.almus.dev',
    'depends': [
        'sale',
        'account',
        'sales_team',
        'sale_management',
        'web',
    ],
    'external_dependencies': {
        'python': ['xlsxwriter'],
    },
    'data': [
        # Security
        'security/commission_band_security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/commission_band_data.xml',
        
        # Views (orden importante: primero las vistas base, luego las que heredan)
        'views/commission_band_views.xml',
        'views/commission_rule_views.xml',
        'views/salesperson_config_views.xml',
        'views/commission_calculation_views.xml',
        'views/commission_batch_views.xml',
        'views/commission_payment_document_views.xml',
        'views/commission_calculation_batch_views.xml',
        'views/res_users_views.xml',
        'views/commission_band_menu.xml',
        
        # Wizards (después de las vistas que heredan)
        'wizards/commission_band_config_wizard_views.xml',
        'wizards/commission_batch_create_wizard_views.xml',
        'wizards/commission_payment_export_wizard_views.xml',
        
        # Reports
        'reports/commission_payment_report.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}