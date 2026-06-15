# Sistema de guías visuales por página

## Qué es

El frontend usa un sistema reutilizable de ayuda contextual basado en `helpKey`.
Cada pantalla abre un panel rico con:

- resumen rápido
- acciones disponibles
- flujo de trabajo
- construcción interna
- datos relacionados
- relaciones con otros módulos
- mapa visual tipo nodo central + ramas

## Piezas principales

- `src/content/pageHelp.js`
  Catálogo declarativo de guías. Cada entrada describe una pantalla real del producto.

- `src/components/PageHelpButton.jsx`
  Botón reutilizable que resuelve la guía por `helpKey`, gestiona foco y abre/cierra el diálogo.

- `src/components/page-guide/PageGuideDialog.jsx`
  Renderer común del contenido estructurado.

- `src/components/page-guide/PageGuideMindMap.jsx`
  Renderer visual del mapa funcional responsive.

- `src/config/appShellConfig.js`
  Traduce la navegación activa al `helpKey` contextual.

## Estructura de una guía

Cada guía del catálogo sigue este esquema conceptual:

```js
{
  title: 'Nom de la pantalla',
  summary: 'Resumen corto visible en cabecera',
  purpose: 'Para qué sirve realmente',
  highlights: [
    { label: 'Entrada', value: '...' },
  ],
  diagram: {
    center: { label: 'Pantalla', subtitle: '...', icon: 'LayoutDashboard' },
    branches: [
      { title: 'Inputs', icon: 'Database', description: '...', items: ['...'], tone: 'data' },
    ],
  },
  actions: [
    { title: 'Acción', description: '...', icon: 'Target' },
  ],
  workflow: [
    { title: 'Paso 1', description: '...' },
  ],
  architecture: {
    components: ['...'],
    dataSources: ['...'],
    processes: ['...'],
    integrations: ['...'],
  },
  relatedData: [
    { label: 'Input', detail: '...', kind: 'input' },
  ],
  relationships: {
    incoming: ['...'],
    outgoing: ['...'],
    dependencies: ['...'],
  },
  tips: ['...'],
}
```

## Cómo añadir una guía nueva

1. Añade una nueva entrada en `src/content/pageHelp.js`.
2. Usa el nombre real de la pantalla y describe:
   - qué hace
   - qué inputs recibe
   - qué procesos ejecuta
   - qué outputs produce
   - con qué otras vistas se relaciona
3. Si la pantalla ya participa en la navegación principal, enlaza su `helpKey` desde:
   - `src/config/databaseAuditTabs.js`
   - `src/config/automationViewConfig.js`
   - o `src/config/appShellConfig.js` si depende de una pestaña principal
4. Si la pantalla abre ayuda desde un header propio, pasa el `helpKey` a `PageHelpButton`.
5. Ejecuta verificación frontend:
   - `npm run lint`
   - `npx vitest run --reporter=dot`

## Criterio de contenido

Las guías no deben ser genéricas.
Se redactan a partir del código real de la vista, sus hooks, endpoints y relaciones funcionales.
Si cambia la pantalla, actualiza también su guía.
