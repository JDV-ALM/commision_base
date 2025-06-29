# Commission Band - Sistema de Bandas de Comisiones

[![Odoo Version](https://img.shields.io/badge/Odoo-18.0-875A7B.svg)](https://www.odoo.com)
[![License: LGPL-3](https://img.shields.io/badge/License-LGPL--3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0)
[![Developed by](https://img.shields.io/badge/Developed%20by-Almus%20Dev-brightgreen)](https://www.almusdev.com)

Sistema avanzado de cálculo automático de comisiones basado en tiempos de cobro para Odoo 18.

## 🌟 Características

- **Cálculo Automático**: Comisiones calculadas al momento del pago
- **Bandas Configurables**: Define escalas de comisión por rangos de días
- **Sistema de Reglas**: Aplica diferentes bandas según criterios múltiples
- **Multi-moneda**: Comisiones en la misma moneda del pago
- **Workflow Completo**: Desde cálculo hasta pago con trazabilidad total

## 📋 Requisitos

- Odoo 18.0 o superior
- Módulos requeridos:
  - `sale`
  - `account`
  - `sales_team`
  - `sale_management`

## 🚀 Instalación

1. Clonar el repositorio en tu directorio de addons:
```bash
git clone https://github.com/almusdev/commission_band.git /ruta/a/addons/
```

2. Actualizar la lista de aplicaciones:
```bash
./odoo-bin -u commission_band -d tu_base_de_datos
```

3. Instalar desde la interfaz:
   - Ir a Aplicaciones
   - Buscar "Commission Band"
   - Hacer clic en Instalar

## ⚙️ Configuración Inicial

### Usando el Asistente de Configuración

1. Navegar a **Ventas → Bandas de Comisiones → Configuración → Asistente de Configuración**
2. Seguir los pasos para crear:
   - Bandas predeterminadas (Premium, Supervisión, Oficina)
   - Reglas de comisión
   - Configuración de vendedores

### Configuración Manual

1. **Crear Bandas**: Define rangos de días y porcentajes
2. **Configurar Reglas**: Establece criterios de aplicación
3. **Asignar Vendedores**: Activa comisiones para usuarios

## 💼 Uso Básico

1. **Registro de Pago**: Cliente realiza pago de factura
2. **Cálculo Automático**: Sistema calcula comisión al conciliar
3. **Revisión**: Vendedor ve su comisión en "Mis Comisiones"
4. **Aprobación**: Administrador valida y aprueba
5. **Pago**: Marcar como pagada tras procesar

## 📊 Ejemplo de Banda

```
Banda Premium (BAND_PREMIUM):
├── Hasta 15 días: 2.8%
├── 16-30 días: 2.3%
├── 31-45 días: 1.8%
├── 46-60 días: 1.3%
├── 61-120 días: 1.0%
└── 121+ días: 0.5%
```

## 🌍 Idiomas

- Español (Venezuela)
- Inglés

## 🤝 Contribuir

Las contribuciones son bienvenidas. Por favor:

1. Fork el proyecto
2. Crea tu rama de características (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📝 Licencia

Este proyecto está licenciado bajo LGPL-3 - ver el archivo [LICENSE](LICENSE) para detalles.

## 👥 Autores

**Almus Dev**
- Website: [almusdev.com](https://almusdev.com)
- Email: info@almusdev.com

## 🆘 Soporte

Para reportar bugs o solicitar características:
- Abrir un [Issue](https://github.com/almusdev/commission_band/issues)
- Contactar a soporte@almusdev.com

## 📸 Screenshots

### Dashboard de Comisiones
![Dashboard](docs/images/dashboard.png)

### Configuración de Bandas
![Bandas](docs/images/bands.png)

### Cálculo de Comisiones
![Cálculo](docs/images/calculation.png)

---

Made with ❤️ by [Almus Dev](https://almusdev.com)