function action(title, description, icon = 'Target') {
  return { title, description, icon };
}

function step(title, description) {
  return { title, description };
}

function datum(label, detail, kind = 'input') {
  return { label, detail, kind };
}

function branch(title, icon, description, items = [], tone = 'neutral') {
  return { title, icon, description, items, tone };
}

function guide(config) {
  return {
    highlights: [],
    actions: [],
    workflow: [],
    architecture: {
      components: [],
      dataSources: [],
      processes: [],
      integrations: [],
    },
    relatedData: [],
    relationships: {
      incoming: [],
      outgoing: [],
      dependencies: [],
    },
    tips: [],
    ...config,
  };
}

export const PAGE_HELP_CONTENT = {
  databaseAuditOverview: guide({
    title: 'Auditoria BBDD',
    summary: 'Módulo principal del portal. Agrupa análisis de obsolescencia, auditoría post-CRQ, automatizaciones, reglas, configuración de entrega y documentación operativa.',
    purpose: 'Sirve como espacio de trabajo transversal para revisar el estado de esquemas Oracle, ejecutar controles, automatizar distribuciones y mantener el catálogo funcional del sistema.',
    highlights: [
      { label: 'Cobertura', value: 'Deep Scan, repositorio, post-CRQ, automatizaciones, reglas, checks y configuración' },
      { label: 'Entrada común', value: 'Perfil Oracle activo, contexto de navegación y configuración persistida en `localStorage`' },
      { label: 'Salida típica', value: 'Resultados de auditoría, informes descargables, reglas operativas y configuración reutilizable' },
    ],
    diagram: {
      center: {
        label: 'Auditoria BBDD',
        subtitle: 'Workspace principal con subpestañas especializadas y estado compartido',
        icon: 'LayoutDashboard',
      },
      branches: [
        branch('Propósito', 'Target', 'Concentrar toda la operativa funcional del portal en un único flujo de trabajo.', [
          'Triar riesgo de esquemas',
          'Ejecutar auditorías post-CRQ',
          'Mantener automatizaciones y catálogos',
        ], 'primary'),
        branch('Pantallas disponibles', 'Layers3', 'Cada subpestaña cubre una fase distinta del circuito.', [
          'Anàlisi obsolets',
          "Repositori d'obsolets",
          'Auditoria de canvis',
          'Automatitzacions y Tasques i regles',
        ], 'data'),
        branch('Datos comunes', 'Database', 'La navegación comparte perfil, configuración e historial reciente.', [
          'Perfil Oracle',
          'Checks post-CRQ',
          'Configuración de entrega',
        ], 'process'),
        branch('Resultados', 'FileText', 'Las subpestañas generan informes, snapshots, reglas y configuración.', [
          'PDF/ZIP',
          'Query export',
          'Persistencia en backend',
        ], 'related'),
      ],
    },
    actions: [
      action('Escoger la subpantalla adecuada', 'La barra de subtabs dirige a análisis, ejecución, automatización, mantenimiento o documentación.'),
      action('Trabajar con un perfil común', 'El perfil activo se reutiliza en Deep Scan, post-CRQ y validaciones para evitar reconfigurar la conexión.'),
      action('Generar informes desde la cabecera', 'Cuando la vista lo soporta, el botón superior usa `useGlobalReport` para crear la salida global más relevante.'),
    ],
    workflow: [
      step('Selecciona el objetivo', 'Empiezas en la subpestaña que corresponda al caso: investigar, ejecutar, automatizar o documentar.'),
      step('Ajusta el contexto', 'Perfil, checks, ventanas temporales, rutas o reglas se heredan o persisten según la vista.'),
      step('Ejecuta o mantiene datos', 'La pantalla activa llama a su hook o servicio y actualiza el estado local.'),
      step('Consume la salida', 'Puedes revisar resultados, descargar artefactos o navegar a la vista relacionada que continúa el flujo.'),
    ],
    architecture: {
      components: [
        '`App.jsx` coordina pestaña principal, subtab, perfil y ayuda contextual.',
        '`DatabaseAuditWorkspace.jsx` resuelve qué subvista se monta según la subpestaña activa.',
        'Los hooks `useDeepScan`, `usePostCrqAudit` y `useGlobalReport` comparten el estado operativo principal.',
      ],
      dataSources: [
        'Perfil activo recuperado por `useProfiles` desde FastAPI.',
        'Datos Oracle, SQLite interna y configuración del backend según la subvista activa.',
        'Estado de navegación persistido por `usePersistedNavigationState` en `localStorage`.',
      ],
      processes: [
        'Resolución de subtabs mediante `databaseAuditTabs.js` y `helpKey` asociado.',
        'Carga diferida de vistas con `lazy` y `Suspense` para no inflar el arranque.',
        'Generación global de informes condicionada por la vista que está abierta.',
      ],
      integrations: [
        'FastAPI sirve datos operativos y la propia SPA.',
        'Oracle se usa en auditorías y validaciones.',
        'SQLite interna guarda metadatos, obsoletos y otros catálogos operativos.',
      ],
    },
    relatedData: [
      datum('Contexto compartido', 'Pestaña activa, subpestaña, perfil seleccionado y estados persistidos del frontend', 'input'),
      datum('Fuentes de backend', 'Endpoints `/api/*` específicos por módulo, todos orquestados desde la shell React', 'input'),
      datum('Artefactos de salida', 'Informes globales, snapshots y configuraciones mantenidas en backend', 'output'),
    ],
    relationships: {
      incoming: [
        'La navegación principal y el selector de perfil de la shell alimentan todas las subpestañas.',
        'Los jobs automáticos pueden redirigir a la auditoría post-CRQ con snapshot o reejecución en vivo.',
      ],
      outgoing: [
        'Los resultados pueden acabar en informes globales, historial de automatizaciones o documentación técnica.',
        'La configuración de checks, reglas o rutas afecta a otros módulos del portal.',
      ],
      dependencies: [
        '`config/appShellConfig.js` resuelve el `helpKey` contextual.',
        '`config/databaseAuditTabs.js` define el catálogo de subtabs visibles.',
      ],
    },
    tips: [
      'Usa esta ayuda como mapa del programa: después salta a la subpestaña concreta para entender el detalle operativo.',
      'Si una pantalla modifica catálogo o configuración, revisa también la guía de la vista relacionada antes de tocar datos productivos.',
    ],
  }),
  deepScan: guide({
    title: 'Anàlisi obsolets',
    summary: 'Auditoría 360° de uno o varios esquemas Oracle para estimar obsolescencia, dependencias, actividad y bloqueadores antes de una limpieza.',
    purpose: 'Detectar si un esquema parece candidato a retirada o si todavía tiene señales técnicas que obligan a revisión humana.',
    highlights: [
      { label: 'Entrada', value: 'Perfil Oracle activo + lista de esquemas en el campo `schemaToAudit`' },
      { label: 'Motor', value: '`useDeepScan` + utilidades de `utils/deepScan.js` para score y señales' },
      { label: 'Salida', value: 'Score configurable, dependencias, métricas de actividad y desglose técnico por esquema' },
    ],
    diagram: {
      center: {
        label: 'Anàlisi obsolets',
        subtitle: 'Vista de inspección técnica orientada a decidir si un esquema es candidato a limpieza',
        icon: 'Search',
      },
      branches: [
        branch('Propósito', 'Target', 'Convertir evidencia técnica dispersa en una valoración rápida y explicable.', [
          'Triatge inicial',
          'Soporte a decisión de limpieza',
          'Comparación masiva entre esquemas',
        ], 'primary'),
        branch('Inputs', 'Database', 'Necesita un perfil y al menos un esquema.', [
          'Perfil Oracle',
          'Schema único o lista',
          'Configuración local del score',
        ], 'data'),
        branch('Procesos', 'Cpu', 'La vista recalcula el score en cliente con baremos ajustables.', [
          'GET `/api/audit/deep-scan/:schemas`',
          'Recalculo local del porcentaje',
          'Clasificación visual por señales',
        ], 'process'),
        branch('Outputs', 'FileText', 'Devuelve evidencia operativa lista para revisar o reportar.', [
          'Tarjeta resumen',
          'Detalle por esquema',
          'Base para informe global',
        ], 'related'),
        branch('Dependencias', 'Link2', 'Está conectada con otras piezas del portal.', [
          '`useProfiles`',
          '`ScoringGuide` lazy',
          '`useGlobalReport`',
        ], 'warning'),
      ],
    },
    actions: [
      action('Probar la conexión antes de auditar', 'El botón de test llama a `/api/db/test` para validar el perfil activo sin lanzar aún el análisis.', 'Database'),
      action('Auditar uno o varios esquemas', 'Puedes introducir un esquema único o una lista; el hook limpia comillas, reinicia el estado y consulta el backend.', 'PlayCircle'),
      action('Abrir la explicación del score', 'La ayuda desplegable carga `ScoringGuide` para mostrar cómo se interpreta la puntuación.', 'BookOpen'),
      action('Ajustar el cálculo de obsolescencia', 'Los sliders modifican únicamente la vista actual, sin tocar el modelo base del backend.', 'Settings2'),
      action('Comparar múltiples resultados', 'Si la respuesta contiene varios esquemas, el selector superior permite navegar entre ellos sin repetir la auditoría.', 'ArrowRightLeft'),
    ],
    workflow: [
      step('Define el contexto', 'Seleccionas perfil y escribes el esquema o la lista a revisar.'),
      step('Lanzas la auditoría', '`runDeepAudit` hace una llamada GET al backend y limpia el estado previo para evitar mezclar resultados.'),
      step('Interpretas el score', 'La vista combina la respuesta del backend con `calculateCustomScoring` y renderiza señales, dependencias y breakdown.'),
      step('Revisas evidencia y decides', 'Usas el detalle técnico para confirmar si el esquema puede avanzar a limpieza, revisión o conservación.'),
    ],
    architecture: {
      components: [
        '`DeepScanView.jsx` renderiza hero, score, selector masivo y tarjetas de detalle.',
        '`useDeepScan.js` encapsula auditoría, estado de carga, test de conexión y configuración local.',
        '`ScoringGuide.jsx` se carga bajo demanda cuando el usuario abre la explicación del cálculo.',
      ],
      dataSources: [
        'Perfil seleccionado heredado desde la shell principal.',
        'Respuesta de `/api/audit/deep-scan/:schemas?profile=...`.',
        'Configuración base `DEFAULT_SCORING_CONFIG` definida en `appShellConfig.js`.',
      ],
      processes: [
        'Normalización del input y reseteo de resultados al lanzar una nueva auditoría.',
        'Cálculo local de score, breakdown efectivo y señales de riesgo por varios ejes.',
        'Renderizado diferenciado para modo masivo y modo esquema único.',
      ],
      integrations: [
        'FastAPI para la auditoría profunda y test de conexión.',
        '`useGlobalReport` puede reutilizar el `auditData` como base del informe global.',
      ],
    },
    relatedData: [
      datum('Input principal', '`selectedProfile` + `schemaToAudit`', 'input'),
      datum('Estado persistente', 'El perfil viene de la navegación global; la configuración del score vive solo en memoria de la vista', 'store'),
      datum('Salida funcional', '`auditData`, `selectedAuditIndex` y breakdown visual por esquema', 'output'),
    ],
    relationships: {
      incoming: [
        'Recibe el perfil activo desde la cabecera del portal.',
        'Comparte el modelo base de scoring definido en la configuración global de la shell.',
      ],
      outgoing: [
        'Sus resultados alimentan la generación del informe global.',
        'La decisión derivada puede acabar registrada en el repositorio de obsoletos o documentada en tutorial/arquitectura.',
      ],
      dependencies: [
        '`utils/deepScan.js` concentra la lógica visual y matemática del score.',
        'Necesita conectividad Oracle válida para que la evidencia sea útil.',
      ],
    },
    tips: [
      'Usa primero el test rápido cuando cambies de perfil; evita interpretar un score vacío como ausencia de riesgo.',
      'Toca los sliders para explorar escenarios, pero conserva el valor base cuando quieras comparar resultados entre ejecuciones.',
    ],
  }),
  obsoletsRepository: guide({
    title: "Repositori d'obsolets",
    summary: 'Registro persistente en SQLite para consultar y añadir candidatos obsoletos sin repetir una auditoría completa.',
    purpose: 'Mantener un inventario operativo de objetos o esquemas marcados como obsoletos, incluyendo motivo, riesgo y recomendación.',
    highlights: [
      { label: 'Fuente', value: '`meta_objects` a través de las APIs `listObsolets` y `createObsolet`' },
      { label: 'Modo de uso', value: 'Consulta rápida + alta manual desde la misma pantalla' },
      { label: 'Valor', value: 'Convierte decisiones técnicas en un registro persistente y compartible' },
    ],
    diagram: {
      center: {
        label: "Repositori d'obsolets",
        subtitle: 'Tabla operativa de candidatos persistidos en la base interna',
        icon: 'Database',
      },
      branches: [
        branch('Qué guarda', 'FileText', 'Cada fila conserva contexto suficiente para volver a entender la decisión.', [
          'Schema',
          'Objeto',
          'Tipo',
          'Riesgo y recomendación',
        ], 'primary'),
        branch('Entradas', 'Target', 'Acepta altas manuales y refresco de datos ya guardados.', [
          'Formulario de alta',
          'Filtro `only_obsolete`',
          'Límite de 200 filas',
        ], 'data'),
        branch('Proceso', 'Cpu', 'La vista carga datos al montar y vuelve a refrescar después de crear una entrada.', [
          '`useEffect` + `refresh()`',
          'Validación mínima en cliente',
          'POST de nueva entrada',
        ], 'process'),
        branch('Relaciones', 'GitBranch', 'Sirve como memoria operativa del módulo.', [
          'Cierra decisiones del Deep Scan',
          'Apoya revisión humana posterior',
          'Evita repetir análisis para consultas simples',
        ], 'related'),
      ],
    },
    actions: [
      action('Actualizar el registro', 'La vista vuelve a consultar SQLite para cargar la versión más reciente del inventario.', 'RefreshCcw'),
      action('Añadir una entrada manual', 'Puedes registrar un objeto validado aunque todavía no venga de un análisis automático.', 'CheckSquare'),
      action('Revisar riesgo y recomendación', 'La tabla prioriza los campos más operativos para valorar impacto y siguiente paso.', 'ShieldAlert'),
    ],
    workflow: [
      step('Cargas el inventario', 'Al montar la vista se llama a `listObsolets({ only_obsolete: true, limit: 200 })`.'),
      step('Revisas o completas contexto', 'La tabla muestra riesgo, origen y motivo; el formulario permite enriquecer el registro.'),
      step('Persistes la decisión', 'Si la alta pasa validación mínima, se llama a `createObsolet` y después se recarga la tabla.'),
    ],
    architecture: {
      components: [
        '`ObsoletsRegistryView.jsx` contiene cabecera, formulario de alta y tabla de resultados.',
        '`src/web-app/src/api/obsolets.js` abstrae las llamadas al backend.',
      ],
      dataSources: [
        'SQLite interna a través de la API de obsoletos.',
        'Formulario local con `schema_name`, `object_name`, `object_type`, `reason` y `risk_level`.',
      ],
      processes: [
        'Carga inicial y refresco manual controlados por `loading` y `error`.',
        'Normalización básica del formulario antes de persistir.',
      ],
      integrations: [
        'FastAPI expone el registro interno como servicio CRUD mínimo.',
      ],
    },
    relatedData: [
      datum('Entrada manual', 'Schema, objeto, tipo, motivo y riesgo', 'input'),
      datum('Persistencia', 'Registro interno `meta_objects` consultado y actualizado por API', 'store'),
      datum('Salida', 'Tabla operativa reutilizable en revisiones posteriores', 'output'),
    ],
    relationships: {
      incoming: [
        'Recibe decisiones validadas desde procesos de análisis o revisión manual.',
      ],
      outgoing: [
        'Sirve de referencia para limpiezas, seguimiento funcional o documentación posterior.',
      ],
      dependencies: [
        'Necesita la API interna de obsoletos y la base SQLite disponible.',
      ],
    },
    tips: [
      'No guardes aquí sospechas preliminares; usa el registro cuando ya exista criterio suficiente para justificar el riesgo.',
      'Incluye una recomendación concreta para que otra persona entienda el siguiente paso sin reabrir toda la investigación.',
    ],
  }),
  postCrqAudit: guide({
    title: 'Auditoria de canvis',
    summary: 'Pantalla central para ejecutar checks post-CRQ, ajustar criticidad y concurrencia, y revisar el informe funcional y técnico resultante.',
    purpose: 'Orquestar la auditoría de cambios recientes con control explícito sobre qué se ejecuta, sobre qué ventana temporal y con qué política operativa.',
    highlights: [
      { label: 'Entradas clave', value: 'Perfil, checks seleccionados, schemas, ventana temporal, overrides y scheduler' },
      { label: 'Motor', value: '`usePostCrqAudit` + `PostCrqAuditView` + endpoints de report y documentación técnica' },
      { label: 'Salida', value: 'Resumen por lots, detalle por check, export de queries y descarga de PDF/ZIP' },
    ],
    diagram: {
      center: {
        label: 'Auditoria de canvis',
        subtitle: 'Ejecutor controlado de checks post-CRQ con snapshot, reejecución en vivo y reporting',
        icon: 'CheckSquare',
      },
      branches: [
        branch('Objetivo', 'Target', 'Evaluar cambios recientes con un conjunto gobernado de checks.', [
          'Control de calidad',
          'Priorización por criticidad',
          'Preparación de entregables',
        ], 'primary'),
        branch('Inputs', 'Database', 'La ejecución se define desde la propia UI y se persiste parcialmente en navegador.', [
          'Perfil y schemas',
          'Checks activos',
          'Time filter',
          'Scheduler y overrides',
        ], 'data'),
        branch('Procesos', 'Workflow', 'La vista combina ejecución, resumen de configuración y render de resultados complejos.', [
          'Carga de catálogo de checks',
          'POST de auditoría',
          'Normalización de criticidades',
          'Descarga de reportes',
        ], 'process'),
        branch('Salidas', 'FileText', 'Expone tanto visión ejecutiva como detalle técnico accionable.', [
          'Resumen ejecutivo por lot',
          'Incidencias priorizadas',
          'Detalle técnico por check',
          'Queries exportables',
        ], 'related'),
        branch('Conexiones', 'GitBranch', 'Se relaciona con historial automático y documentación técnica del sistema.', [
          'Snapshots desde automatizaciones',
          'Informe global',
          'Documento técnico `/api/docs/technical-audit`',
        ], 'warning'),
      ],
    },
    actions: [
      action('Refrescar catálogo y seleccionar checks', 'Puedes recargar la lista, seleccionar todo o limpiar la selección antes de ejecutar.', 'RefreshCcw'),
      action('Configurar temporalidad y schemas', 'La pantalla permite presets diarios/semanales/mensuales o un rango manual, además de definir schemas concretos.', 'Clock3'),
      action('Ajustar scheduler y criticidad', 'Los subpaneles de configuración dejan visible qué overrides son de frontend y cómo afectará la concurrencia.', 'Settings2'),
      action('Lanzar auditoría o reabrir snapshot', 'La ejecución puede ser manual, venir de un snapshot automático o reejecutarse en vivo desde histórico.', 'PlayCircle'),
      action('Descargar queries y reportes', 'Puedes exportar el TXT de consultas y generar resumen general, ZIP completo o PDF por proveedor.', 'FileText'),
      action('Consultar la documentación técnica', 'La ayuda propia de la página también abre el documento técnico con diagramas Mermaid del backend.', 'BookOpen'),
    ],
    workflow: [
      step('Preparas el alcance', 'Seleccionas checks, schemas y ventana temporal, y revisas el resumen de configuración real.'),
      step('Afínas el comportamiento', 'Si hace falta, ajustas overrides de criticidad y parámetros del scheduler antes de ejecutar.'),
      step('Ejecutas o recuperas resultados', '`usePostCrqAudit` llama al backend, guarda `postCrqReportData` y marca el origen de la ejecución.'),
      step('Analizas la salida', 'La vista renderiza métricas, lots, incidencias priorizadas y detalle técnico por check.'),
      step('Exportas artefactos', 'Desde la misma pantalla puedes descargar queries o generar reportes filtrados por variante.'),
    ],
    architecture: {
      components: [
        '`PostCrqAuditView.jsx` concentra configuración, resultados, modales y descargas.',
        '`usePostCrqAudit.js` mantiene checks, selección, scheduler, overrides, snapshots y caché de descarga.',
        '`downloadPostCrqReport` y las APIs post-CRQ encapsulan los binarios de salida.',
      ],
      dataSources: [
        'Catálogo de checks obtenido con `listPostCrqChecks()`.',
        'Perfil activo heredado desde la shell y `localStorage` para scheduler y criticidad.',
        'Documento técnico cargado desde `/api/docs/technical-audit` cuando el usuario lo solicita.',
      ],
      processes: [
        'Normalización de criticidades y opciones de scheduler antes de ejecutar.',
        'Validación de inputs mínimos: perfil, checks y rango temporal cuando aplica.',
        'Clasificación y render del resultado para resumen ejecutivo y detalle técnico.',
      ],
      integrations: [
        'FastAPI para ejecución, descarga de reportes y documentación técnica.',
        'Mermaid para renderizar diagramas dentro de la documentación técnica embebida.',
        'Automatizaciones para abrir snapshots históricos o relanzar una ejecución en vivo.',
      ],
    },
    relatedData: [
      datum('Inputs de ejecución', 'Perfil, checks, schemas, ventana temporal, scheduler y criticidad', 'input'),
      datum('Persistencia local', 'Scheduler y overrides se guardan en `localStorage` para sesiones futuras', 'store'),
      datum('Resultado principal', '`postCrqReportData` con resúmenes, detalle técnico y `query_export`', 'output'),
    ],
    relationships: {
      incoming: [
        'Los checks se mantienen en Gestió de controls y se consumen aquí.',
        'Automatitzacions puede abrir un snapshot histórico o relanzar una ejecución en vivo en esta misma vista.',
      ],
      outgoing: [
        'La auditoría sirve de base para informes globales y entregas automáticas.',
        'El resultado técnico puede provocar cambios en criticidad, scheduler o definición de checks.',
      ],
      dependencies: [
        '`usePostCrqAudit` decide cuándo cargar checks y cómo reconstruir configuración desde snapshots.',
        'Necesita endpoints de ejecución, reporte y documentación técnica disponibles.',
      ],
    },
    tips: [
      'Lee siempre el bloque “configuración efectiva” antes de ejecutar; es la forma más rápida de detectar un override olvidado.',
      'Diferencia snapshot histórico de reejecución en vivo: la segunda vuelve a consultar Oracle y puede producir resultados distintos.',
    ],
  }),
  automationOverview: guide({
    title: 'Automatitzacions',
    summary: 'Centro operativo del módulo automático: jobs, analytics, lotes, rutas, plantillas, histórico y reintentos bajo una misma navegación lateral.',
    purpose: 'Gestionar el ciclo completo de ejecución y distribución automática de auditorías post-CRQ sin salir del frontend.',
    highlights: [
      { label: 'Pantallas internas', value: 'Dashboard, Jobs, Lots, Destinataris, Plantilles, Històric, Reintents y Ajuda' },
      { label: 'Motor', value: '`AutomationView` + `useAutomationViewModel` + APIs `/api/automation/*`' },
      { label: 'Salida', value: 'Configuración persistida, historial de runs, PDFs mensuales y snapshots reutilizables' },
    ],
    diagram: {
      center: {
        label: 'Automatitzacions',
        subtitle: 'Módulo compuesto con sidebar propia y ayudas contextuales por pantalla',
        icon: 'LayoutDashboard',
      },
      branches: [
        branch('Navegación', 'Layers3', 'La sidebar interna cambia de subpantalla sin salir del módulo.', [
          'Dashboard',
          'Jobs',
          'Lots',
          'Recipients',
          'History',
        ], 'primary'),
        branch('Configuración', 'Settings2', 'Desde aquí se gobierna el circuito automático completo.', [
          'Jobs programados',
          'Mapeo schema -> lot',
          'Rutas y plantillas',
        ], 'data'),
        branch('Seguimiento', 'History', 'El módulo también conserva trazabilidad y recuperación.', [
          'Runs',
          'Change events',
          'Retry queue',
        ], 'process'),
        branch('Integración', 'GitBranch', 'Se conecta directamente con la auditoría post-CRQ y la configuración de entrega.', [
          'Apertura de snapshots',
          'PDF mensual',
          'Rutas compartidas con Configuració del servidor',
        ], 'related'),
      ],
    },
    actions: [
      action('Cambiar de pantalla sin perder contexto', 'La sidebar interna mantiene el módulo cohesionado y ofrece ayuda contextual para cada subpantalla.', 'Route'),
      action('Refrescar todo el estado del módulo', 'La acción global vuelve a cargar jobs, rutas, lotes, historial, analytics y cola de reintentos.', 'RefreshCcw'),
      action('Abrir ayuda contextual por subpantalla', 'Cada `AutomationScreenHeader` tiene un `PageHelpButton` ligado al `helpKey` real de la pantalla activa.', 'BookOpen'),
    ],
    workflow: [
      step('Seleccionas una subpantalla', 'La sidebar marca `automationSection` y monta el panel correspondiente.'),
      step('Mantienes la configuración o consultas resultados', 'Cada panel usa el view model común para leer y actualizar datos del backend.'),
      step('Saltas a módulos relacionados', 'Desde histórico puedes abrir snapshots en Auditoria de canvis o generar reportes analíticos.'),
    ],
    architecture: {
      components: [
        '`AutomationView.jsx` compone sidebar, cabecera, modal de ayuda y los paneles funcionales.',
        '`AutomationScreenHeader.jsx` muestra métricas resumidas y un botón de ayuda por subpantalla.',
        '`useAutomationViewModel.js` centraliza el estado del módulo y las operaciones contra API.',
      ],
      dataSources: [
        'APIs de jobs, analytics, runs, routes, templates, retries y mantenimiento.',
        'Perfil y callbacks compartidos con la shell principal.',
      ],
      processes: [
        'Cambio interno de pantalla vía `automationSection`.',
        'Refresh global o parcial según el panel activo.',
        'Apertura de snapshots y reejecuciones de auditoría desde el histórico.',
      ],
      integrations: [
        'Backend `/api/automation/*`.',
        'Conexión con Auditoria de canvis y Configuració del servidor.',
      ],
    },
    relatedData: [
      datum('Estado compuesto', 'Jobs, rutas, lotes, templates, analytics, historial y cola de reintentos', 'store'),
      datum('Entradas principales', 'Cambios de navegación, formularios de mantenimiento y acciones operativas', 'input'),
      datum('Salidas', 'Jobs actualizados, snapshots reabiertos, PDFs mensuales y mensajes operativos', 'output'),
    ],
    relationships: {
      incoming: [
        'Recibe perfiles y callback para abrir runs post-CRQ en la vista de auditoría.',
      ],
      outgoing: [
        'Impacta en la generación automática de informes y en cómo se distribuyen los resultados.',
      ],
      dependencies: [
        '`automationViewConfig.js` define las subpantallas visibles y su `helpKey`.',
        'El view model necesita el catálogo de endpoints de `src/api/automation.js`.',
      ],
    },
    tips: [
      'Piensa el módulo como una cadena: Jobs decide cuándo, Lots agrupa, Destinataris entrega y Històric verifica.',
      'Usa la ayuda del panel concreto cuando estés haciendo una tarea específica; esta guía es la vista global del módulo.',
    ],
  }),
  automationDashboard: guide({
    title: "Dashboard d'automatitzacions",
    summary: 'Resumen analítico mensual del comportamiento del sistema automático por ejecuciones, lots, schemas y checks.',
    purpose: 'Obtener una visión ejecutiva del volumen, la calidad y la distribución de hallazgos de las automatizaciones.',
    highlights: [
      { label: 'Fuentes', value: 'Analytics overview, lots, schemas y checks del backend de automatización' },
      { label: 'Acciones', value: 'Cambiar mes, refrescar y exportar el PDF mensual analítico' },
      { label: 'Salida', value: 'KPIs y tablas comparativas para seguimiento operativo' },
    ],
    diagram: {
      center: {
        label: 'Dashboard',
        subtitle: 'Analítica agregada del comportamiento automático mes a mes',
        icon: 'LayoutDashboard',
      },
      branches: [
        branch('Inputs', 'Clock3', 'Trabaja sobre un mes y un conjunto de analytics agregados.', [
          'Mes seleccionado',
          'Overview',
          'Lots',
          'Schemas',
          'Checks',
        ], 'data'),
        branch('Procesos', 'Cpu', 'El panel refresca datasets analíticos y recalcula las tablas visibles.', [
          'Refresh por mes',
          'KPI cards',
          'Rankings y listados',
        ], 'process'),
        branch('Output', 'FileText', 'Permite tanto consumo visual como exportación documental.', [
          'KPIs',
          'Top lots',
          'PDF mensual',
        ], 'related'),
      ],
    },
    actions: [
      action('Cambiar el mes analizado', 'El panel consulta analytics del periodo seleccionado y actualiza los indicadores.'),
      action('Refrescar las métricas', 'Permite forzar recarga sin salir del dashboard cuando han entrado runs nuevos.'),
      action('Exportar el PDF mensual', 'Genera un artefacto compartible con la misma lectura agregada que muestra la UI.', 'FileText'),
    ],
    workflow: [
      step('Seleccionas un mes', 'El módulo consulta los datasets agregados del periodo.'),
      step('Lees los KPIs', 'Las tarjetas y tablas muestran runs, findings, lots afectados y checks problemáticos.'),
      step('Exportas si hace falta', 'El botón PDF usa el backend analítico para consolidar un documento mensual.'),
    ],
    architecture: {
      components: [
        '`AutomationDashboardPanel.jsx` renderiza tarjetas KPI y tablas analíticas.',
      ],
      dataSources: [
        '`getAutomationAnalyticsOverview`, `listAutomationAnalyticsLots`, `listAutomationAnalyticsSchemas` y `listAutomationAnalyticsChecks`.',
      ],
      processes: [
        'Refresco analítico parcial por mes.',
        'Render de métricas resumidas y rankings.',
      ],
      integrations: [
        '`exportAutomationAnalyticsMonthlyPdf` para el reporte mensual.',
      ],
    },
    relatedData: [
      datum('Input', 'Mes seleccionado en la cabecera del panel', 'input'),
      datum('Estado', 'Datasets analíticos cargados en el view model de automatización', 'store'),
      datum('Output', 'KPI cards, rankings y PDF mensual', 'output'),
    ],
    relationships: {
      incoming: ['Se alimenta de los runs generados por Jobs e Històric.'],
      outgoing: ['Ayuda a decidir ajustes en jobs, reglas o rutas según volumen y fallos.'],
      dependencies: ['Endpoints analíticos del backend de automatización.'],
    },
    tips: [
      'Usa esta pantalla para tendencia y priorización; para diagnóstico fino salta a Històric.',
    ],
  }),
  automationJobs: guide({
    title: "Jobs d'automatització",
    summary: 'Pantalla para crear, editar, activar, ejecutar y desactivar jobs programados de auditoría.',
    purpose: 'Definir cuándo se ejecuta una auditoría automática, con qué contexto y bajo qué política de distribución.',
    highlights: [
      { label: 'Controla', value: 'Calendario, perfil, checks, formato y activación de cada job' },
      { label: 'Depende de', value: 'Perfiles, catálogo de checks, rutas de entrega y lotes disponibles' },
      { label: 'Produce', value: 'Jobs persistidos y ejecuciones manuales bajo demanda' },
    ],
    diagram: {
      center: {
        label: 'Jobs',
        subtitle: 'Punto de entrada para programar y disparar auditorías automáticas',
        icon: 'PlayCircle',
      },
      branches: [
        branch('Inputs', 'Database', 'Los formularios recogen el contexto exacto del run.', [
          'Perfil',
          'Checks',
          'Programación',
          'Opciones de distribución',
        ], 'data'),
        branch('Procesos', 'Workflow', 'El panel valida, guarda y permite ejecución inmediata.', [
          'Crear o editar',
          'Activar o pausar',
          'Run now',
        ], 'process'),
        branch('Relaciones', 'GitBranch', 'El job usa rutas, templates y lotes mantenidos en otras pantallas.', [
          'Lots i mapatge',
          'Destinataris',
          'Plantilles',
        ], 'related'),
      ],
    },
    actions: [
      action('Crear o editar un job', 'El formulario recoge el perfil, checks, horario y opciones funcionales del proceso.'),
      action('Ejecutarlo sin esperar al calendario', 'El botón “run now” permite probar el circuito completo manualmente.', 'Zap'),
      action('Activar, desactivar o eliminar', 'Desde la lista se gobierna el parque de jobs disponibles y su ciclo de vida.', 'Settings2'),
    ],
    workflow: [
      step('Preparas el formulario', 'Seleccionas perfil, checks y contexto de ejecución.'),
      step('Persistes el job', 'La pantalla llama a create/update contra `/api/automation/jobs`.'),
      step('Supervisas el parque', 'La lista muestra qué jobs existen, cuáles están activos y desde cuál conviene lanzar pruebas.'),
    ],
    architecture: {
      components: ['`AutomationJobsPanel.jsx` agrupa formulario, contexto y listado de jobs.'],
      dataSources: ['Jobs del backend, perfiles, checks, rutas y lotes del view model.'],
      processes: ['Alta, edición, activación, ejecución manual y borrado de jobs.'],
      integrations: ['`listAutomationJobs`, `createAutomationJob`, `updateAutomationJob`, `runAutomationJobNow`, `deleteAutomationJob`.'],
    },
    relatedData: [
      datum('Input', 'Formulario de job con perfil, checks y entrega', 'input'),
      datum('Persistencia', 'Definición del job en backend de automatización', 'store'),
      datum('Output', 'Job listo para calendario o run manual inmediato', 'output'),
    ],
    relationships: {
      incoming: ['Necesita checks válidos y rutas/lotes disponibles.'],
      outgoing: ['Sus ejecuciones alimentan Històric, Dashboard y eventualmente Reintents.'],
      dependencies: ['Servicios de jobs del backend y datos auxiliares cargados por el view model.'],
    },
    tips: [
      'Si un job falla por configuración, revisa antes Lots, Destinataris y Plantilles: el problema suele venir de contexto incompleto.',
    ],
  }),
  automationLots: guide({
    title: 'Lots i mapatge',
    summary: 'Pantalla para mantener el catálogo maestro de lots, mapear schemas y ejecutar backfills asistidos.',
    purpose: 'Asegurar que cada schema se agrupa correctamente antes de distribuir resultados automáticos.',
    highlights: [
      { label: 'Datos clave', value: 'Schema lots, master lots y preview/apply de backfill' },
      { label: 'Riesgo que evita', value: 'Runs con `SIN_MAPEO` o agrupaciones incorrectas en la distribución' },
      { label: 'Salida', value: 'Mapa schema -> lot y catálogo maestro actualizado' },
    ],
    diagram: {
      center: {
        label: 'Lots i mapatge',
        subtitle: 'Capa de clasificación que da sentido funcional a los resultados por schema',
        icon: 'Boxes',
      },
      branches: [
        branch('Entradas', 'Database', 'Consume catálogos de schemas y lots.', [
          'Schema lots',
          'Master lots',
          'Filtros y selección de backfill',
        ], 'data'),
        branch('Proceso', 'Workflow', 'Permite mantener el mapeo manual o aplicar backfill guiado.', [
          'Editar mapeo',
          'Previsualizar backfill',
          'Aplicar cambios',
        ], 'process'),
        branch('Salidas', 'Route', 'El resultado se usa en toda la distribución automática.', [
          'Agrupación por lot',
          'Rutas de correo',
          'Reportes por proveedor',
        ], 'related'),
      ],
    },
    actions: [
      action('Editar el mapeo schema -> lot', 'La tabla principal mantiene la clasificación operativa usada por los runs.'),
      action('Gestionar el catálogo maestro', 'Puedes dar de alta o corregir lots maestros para mantener consistencia funcional.', 'Settings2'),
      action('Previsualizar y aplicar backfill', 'El backfill ayuda a incorporar esquemas sin lot asignado con una revisión previa.', 'Sparkles'),
    ],
    workflow: [
      step('Revisas el catálogo actual', 'Filtras y validas si hay schemas sin mapear o lots obsoletos.'),
      step('Corriges o amplías el modelo', 'Editas el mapeo manualmente o generas una propuesta de backfill.'),
      step('Guardas el estado operativo', 'Los cambios persistidos se reutilizan en jobs, histórico y distribución.'),
    ],
    architecture: {
      components: ['`AutomationLotsPanel.jsx` reúne mapeo, backfill y catálogo maestro.'],
      dataSources: ['`listSchemaLots`, `listMasterLots`, `previewMasterLotsBackfill`, `applyMasterLotsBackfill`.'],
      processes: ['Filtrado local, validación básica y persistencia en lotes.'],
      integrations: ['Backend de automatización para schema lots, master lots y backfill.'],
    },
    relatedData: [
      datum('Input', 'Schemas, lotes y selección de backfill', 'input'),
      datum('Persistencia', 'Mapeo de schema lots y master lots en backend', 'store'),
      datum('Output', 'Clasificación estable para agrupar informes y ruteo', 'output'),
    ],
    relationships: {
      incoming: ['Puede detectar huecos a partir de runs automáticos y catálogos existentes.'],
      outgoing: ['Condiciona la entrega por lot y la lectura del histórico.'],
      dependencies: ['Servicios de lots y backfill del backend de automatización.'],
    },
    tips: [
      'Si ves `SIN_MAPEO` en histórico, esta es la pantalla que debes corregir primero.',
    ],
  }),
  automationRecipients: guide({
    title: 'Destinataris',
    summary: 'Gestión de rutas de distribución para resumen TIC y correo por lot, sin entrar en la configuración SMTP.',
    purpose: 'Definir a quién llega cada resultado cuando la automatización ya sabe qué lot debe distribuir.',
    highlights: [
      { label: 'Alcance', value: 'Rutas por lot y destinatarios de resumen TIC' },
      { label: 'No cubre', value: 'Servidor SMTP, Teams o SharePoint; eso vive en Configuració del servidor' },
      { label: 'Salida', value: 'Rutas de entrega consumidas por jobs y reintentos' },
    ],
    diagram: {
      center: {
        label: 'Destinataris',
        subtitle: 'Enrutamiento funcional de la distribución automática',
        icon: 'Mail',
      },
      branches: [
        branch('Entradas', 'Boxes', 'Trabaja sobre lotes ya definidos y audiencias conocidas.', [
          'Lots',
          'Emails por ruta',
          'Resumen TIC',
        ], 'data'),
        branch('Proceso', 'Workflow', 'Editar, habilitar o retirar rutas según el caso.', [
          'Alta de ruta',
          'Edición de destinatarios',
          'Guardado de cambios',
        ], 'process'),
        branch('Relaciones', 'GitBranch', 'Las rutas se usan al ejecutar jobs, revisar histórico o reenviar.', [
          'Jobs',
          'Històric',
          'Reintents',
        ], 'related'),
      ],
    },
    actions: [
      action('Mantener rutas por lot', 'Cada lot puede tener su lista específica de correos para entregas automáticas.'),
      action('Gestionar el resumen TIC', 'La audiencia TIC se mantiene separada para consolidar la salida global.'),
      action('Habilitar o deshabilitar rutas', 'Puedes dejar preparada una ruta sin eliminarla definitivamente.', 'Settings2'),
    ],
    workflow: [
      step('Partes de lots existentes', 'La vista asume que el mapeo funcional ya está resuelto.'),
      step('Ajustas destinatarios', 'Defines o corriges emails y estado habilitado por ruta.'),
      step('Persistes las rutas', 'El backend reutiliza esta información en envíos normales y reintentos.'),
    ],
    architecture: {
      components: ['`AutomationRecipientsPanel.jsx` encapsula la edición de rutas.'],
      dataSources: ['`listLotRoutes` y `updateLotRoutes` desde el backend de automatización.'],
      processes: ['Edición de arrays de rutas y persistencia directa.'],
      integrations: ['Se apoya en el catálogo de lots y se complementa con MailConfigView.'],
    },
    relatedData: [
      datum('Input', 'Rutas por lot y audiencia TIC', 'input'),
      datum('Persistencia', 'Configuración de lot routes en backend', 'store'),
      datum('Output', 'Enrutamiento reutilizable por jobs, historial y reintentos', 'output'),
    ],
    relationships: {
      incoming: ['Necesita lots correctamente clasificados.'],
      outgoing: ['Afecta directamente a cómo se envían informes automáticos.'],
      dependencies: ['Servicios de lot routes y catálogo de lots.'],
    },
    tips: [
      'Si el problema es “a quién enviamos”, usa esta pantalla; si el problema es “cómo enviamos”, usa Configuració del servidor.',
    ],
  }),
  automationTemplates: guide({
    title: 'Plantilles',
    summary: 'Editor funcional de las plantillas de correo que usa el sistema en entregas normales, resúmenes y reenvíos.',
    purpose: 'Cambiar el contenido comunicativo sin tocar la lógica de ejecución ni el backend.',
    highlights: [
      { label: 'Tipos', value: 'Lot con hallazgos, lot sin hallazgos, resumen TIC, reenvío y error de generación' },
      { label: 'Depende de', value: 'Audiencia y resultado del run' },
      { label: 'Produce', value: 'Plantillas persistidas listas para distribución automática' },
    ],
    diagram: {
      center: {
        label: 'Plantilles',
        subtitle: 'Capa de copy y comunicación del circuito automático',
        icon: 'Wand2',
      },
      branches: [
        branch('Inputs', 'FileText', 'Trabaja con claves de plantilla y contenido editable.', [
          'Tipo de audiencia',
          'Cuerpo del mensaje',
          'Contexto del run',
        ], 'data'),
        branch('Proceso', 'Workflow', 'Permite editar y guardar sin tocar lógica de negocio.', [
          'Seleccionar plantilla',
          'Editar copy',
          'Persistir cambios',
        ], 'process'),
        branch('Output', 'Mail', 'El resultado se usa en el envío real de correos.', [
          'Mensajes coherentes',
          'Reenvíos manuales',
          'Notificaciones de error',
        ], 'related'),
      ],
    },
    actions: [
      action('Editar el copy por audiencia', 'Cada plantilla tiene una función concreta dentro del circuito automático.'),
      action('Guardar cambios sin tocar backend', 'La vista persiste el texto y el sistema lo reutiliza en el siguiente envío.', 'CheckSquare'),
      action('Mantener consistencia entre escenarios', 'La separación por clave evita mezclar mensajes de lot, TIC, errores o reenvíos.', 'GitBranch'),
    ],
    workflow: [
      step('Seleccionas la plantilla', 'Identificas si estás cambiando un correo de lot, TIC, error o reenvío.'),
      step('Ajustas el mensaje', 'Editas el contenido funcional sin alterar el flujo operativo.'),
      step('Guardas para futuras ejecuciones', 'El backend aplicará la nueva plantilla en los siguientes envíos.'),
    ],
    architecture: {
      components: ['`AutomationTemplatesPanel.jsx` encapsula la edición de plantillas.'],
      dataSources: ['`listDeliveryTemplates` y `updateDeliveryTemplates`.'],
      processes: ['Carga, edición y guardado de templates por audiencia.'],
      integrations: ['Distribución automática y reenvíos manuales.'],
    },
    relatedData: [
      datum('Input', 'Clave de plantilla y texto editable', 'input'),
      datum('Persistencia', 'Catálogo de templates en backend de automatización', 'store'),
      datum('Output', 'Mensajes reutilizados por jobs y reintentos', 'output'),
    ],
    relationships: {
      incoming: ['Depende de la tipología de audiencia y resultado del run.'],
      outgoing: ['Afecta el texto final de los correos distribuidos.'],
      dependencies: ['Servicios de templates del backend.'],
    },
    tips: [
      'Cambia aquí solo el contenido. Si la audiencia o los adjuntos son incorrectos, revisa Destinataris o Configuració del servidor.',
    ],
  }),
  automationHistory: guide({
    title: 'Històric',
    summary: 'Traza las ejecuciones automáticas, sus cambios y el detalle por lot, con capacidad para reabrir snapshots o relanzar auditorías.',
    purpose: 'Ofrecer trazabilidad real de lo que se ejecutó, qué produjo y cómo recuperar un contexto histórico exacto.',
    highlights: [
      { label: 'Consulta', value: 'Runs, events, detalle por lot, reportes y filtros de mantenimiento' },
      { label: 'Acciones clave', value: 'Abrir snapshot, reejecutar en vivo, exportar CSV y encolar reintentos' },
      { label: 'Salida', value: 'Diagnóstico operativo y puente hacia Auditoria de canvis o Reintents' },
    ],
    diagram: {
      center: {
        label: 'Històric',
        subtitle: 'Trazabilidad del sistema automático y punto de recuperación de contexto',
        icon: 'History',
      },
      branches: [
        branch('Datos', 'Database', 'Combina runs, lots, eventos y resumen de mantenimiento.', [
          'Runs',
          'Change events',
          'Lots por run',
          'Maintenance summary',
        ], 'data'),
        branch('Procesos', 'Workflow', 'La vista expande, filtra y reutiliza resultados históricos.', [
          'Expandir run',
          'Cargar lots',
          'Abrir snapshot',
          'Rerun live',
        ], 'process'),
        branch('Relaciones', 'GitBranch', 'Es la pantalla puente entre ejecución pasada y diagnóstico presente.', [
          'Auditoria de canvis',
          'Retry queue',
          'Export CSV',
        ], 'related'),
      ],
    },
    actions: [
      action('Inspeccionar runs y lots', 'Puedes expandir una ejecución para ver su resultado por lot y el estado final de cada entrega.'),
      action('Abrir un snapshot exacto', 'La vista puede reconstruir la configuración histórica en Auditoria de canvis.'),
      action('Relanzar en vivo desde el histórico', 'Si quieres repetir el contexto con datos actuales, la vista dispara una nueva ejecución real.', 'PlayCircle'),
      action('Exportar CSV o encolar reintentos', 'Desde el detalle del run puedes sacar artefactos o mandar fallos a la cola de recuperación.', 'FileText'),
    ],
    workflow: [
      step('Filtras el histórico', 'Reduces el ruido por lot o periodo y decides qué run revisar.'),
      step('Abres el detalle', 'La pantalla carga lots y estado operativo del run seleccionado.'),
      step('Recuperas o actúas', 'Puedes abrir snapshot, relanzar en vivo, exportar CSV o mandar una entrega a reintentos.'),
    ],
    architecture: {
      components: ['`AutomationHistoryPanel.jsx` gestiona histórico, detalle por lot y mantenimiento.'],
      dataSources: ['`listAutomationRuns`, `listAutomationRunLots`, `listAutomationChangeEvents`, `getAutomationMaintenanceSummary`.'],
      processes: ['Expansión de runs, carga diferida de lots, reapertura de snapshot y acciones de mantenimiento.'],
      integrations: ['Auditoria de canvis, export CSV y cola de reintentos.'],
    },
    relatedData: [
      datum('Input', 'Filtros de lot, retención, selección de run y acciones por entrega', 'input'),
      datum('Persistencia', 'Runs y eventos almacenados por el backend de automatización', 'store'),
      datum('Output', 'Diagnóstico histórico, snapshots reutilizados y artefactos exportados', 'output'),
    ],
    relationships: {
      incoming: ['Se alimenta de ejecuciones lanzadas por Jobs y de entregas reales del sistema automático.'],
      outgoing: ['Puede reabrir Auditoria de canvis o poblar la cola de Reintents.'],
      dependencies: ['Servicios de runs, report data, lotes, export y mantenimiento.'],
    },
    tips: [
      'Usa snapshot cuando quieras fidelidad histórica; usa rerun live cuando quieras confirmar si el problema sigue ocurriendo hoy.',
    ],
  }),
  automationRetries: guide({
    title: 'Reintents',
    summary: 'Cola operativa para reenviar entregas fallidas o pendientes sin repetir toda la auditoría.',
    purpose: 'Recuperar únicamente la fase de distribución cuando el run ya es válido y el problema está en la entrega.',
    highlights: [
      { label: 'Entrada', value: 'Elementos fallidos o pendientes, normalmente creados desde Històric' },
      { label: 'Acciones', value: 'Ejecutar reintento inmediato o purgar cola' },
      { label: 'Salida', value: 'Entrega recuperada o cola saneada' },
    ],
    diagram: {
      center: {
        label: 'Reintents',
        subtitle: 'Recuperación selectiva de entregas sin rehacer la auditoría',
        icon: 'RefreshCcw',
      },
      branches: [
        branch('Entradas', 'History', 'Trabaja sobre elementos previamente detectados como fallidos o pendientes.', [
          'Retry queue',
          'Contexto del run',
          'Estado de entrega',
        ], 'data'),
        branch('Proceso', 'Workflow', 'La acción principal es relanzar solo la fase de envío.', [
          'Run retry now',
          'Purge queue',
          'Revisión de estado',
        ], 'process'),
        branch('Relaciones', 'Mail', 'Depende fuertemente de rutas y configuración de entrega correctas.', [
          'Destinataris',
          'Configuració del servidor',
        ], 'related'),
      ],
    },
    actions: [
      action('Ejecutar un reintento puntual', 'La pantalla permite relanzar solo la entrega pendiente o fallida.'),
      action('Limpiar la cola', 'Si el ruido ya no es útil, puedes purgar la retry queue de forma controlada.', 'ShieldAlert'),
    ],
    workflow: [
      step('Entra una entrega en la cola', 'Suele llegar desde el histórico o desde un fallo detectado por el backend.'),
      step('Revisas si el contexto ya es correcto', 'Antes de relanzar conviene validar rutas, plantillas y SMTP.'),
      step('Lanzas el reintento', 'La vista llama a `runRetryNow` para intentar solo esa parte del circuito.'),
    ],
    architecture: {
      components: ['`AutomationRetryPanel.jsx` gestiona la cola y sus acciones.'],
      dataSources: ['`listRetryQueue`, `runRetryNow`, `purgeAutomationRetryQueue`.'],
      processes: ['Relanzado puntual y limpieza de cola.'],
      integrations: ['Rutas, SMTP y artefactos generados por runs anteriores.'],
    },
    relatedData: [
      datum('Input', 'Elementos de la retry queue y acciones del operador', 'input'),
      datum('Persistencia', 'Cola de reintentos del backend', 'store'),
      datum('Output', 'Entrega recuperada o cola depurada', 'output'),
    ],
    relationships: {
      incoming: ['Se alimenta de fallos detectados en Històric.'],
      outgoing: ['Cierra incidencias de entrega sin reejecutar la auditoría completa.'],
      dependencies: ['Servicios de retry queue y configuración correcta de entrega.'],
    },
    tips: [
      'No uses reintentos para arreglar un run mal configurado; primero corrige jobs, rutas o SMTP y luego relanza.',
    ],
  }),
  automationHelp: guide({
    title: "Ajuda d'automatitzacions",
    summary: 'Pantalla documental del módulo automático, pensada para explicar el circuito completo y la relación entre sus subpantallas.',
    purpose: 'Servir de guía operativa interna cuando necesitas entender el módulo automático antes de tocar configuración o historial.',
    highlights: [
      { label: 'Función', value: 'Documentación embebida del circuito automático completo' },
      { label: 'Complementa', value: 'Las ayudas contextuales más concretas de cada subpantalla' },
      { label: 'No sustituye', value: 'La operativa real de Jobs, Lots, Destinataris, Històric o Reintents' },
    ],
    diagram: {
      center: {
        label: 'Ajuda',
        subtitle: 'Vista de documentación operativa del módulo de automatización',
        icon: 'BookOpen',
      },
      branches: [
        branch('Qué explica', 'Layers3', 'Recorre el flujo de configuración, ejecución, entrega y recuperación.', [
          'Jobs',
          'Lots',
          'Destinataris',
          'Històric',
          'Reintents',
        ], 'primary'),
        branch('Cómo se usa', 'Target', 'Se consulta cuando necesitas contexto antes de operar.', [
          'Onboarding',
          'Aclarar relaciones',
          'Evitar tocar la pantalla incorrecta',
        ], 'related'),
      ],
    },
    actions: [
      action('Abrir la guía integrada', 'La propia pantalla muestra una explicación visual del circuito de automatizaciones.'),
      action('Usarla como navegación conceptual', 'Después de entender el circuito, lo normal es saltar a la subpantalla concreta para operar.', 'Route'),
    ],
    workflow: [
      step('Lees el recorrido global', 'La guía te sitúa dentro del módulo.'),
      step('Saltas a la pantalla adecuada', 'Una vez localizado el punto correcto, cambias a Jobs, Lots, Històric o Reintents.'),
    ],
    architecture: {
      components: ['`AutomationHelpPanel.jsx`, `AutomationHelpModal.jsx` y `AutomationGuide.jsx`.'],
      dataSources: ['Documentación estática embebida en frontend.'],
      processes: ['Carga diferida de la guía y apertura en modal o panel.'],
      integrations: ['Enlace opcional a una ventana dedicada de ayuda del módulo.'],
    },
    relatedData: [
      datum('Entrada', 'No modifica datos productivos; solo consume documentación embebida', 'input'),
      datum('Salida', 'Contexto funcional para usar el resto de pantallas correctamente', 'output'),
    ],
    relationships: {
      incoming: ['La abres desde el propio módulo automático o como pantalla interna.'],
      outgoing: ['Te orienta hacia la pantalla correcta del módulo.'],
      dependencies: ['Componentes documentales propios del frontend.'],
    },
    tips: [
      'Usa esta guía cuando dudes entre dos pantallas del módulo; para trabajo operativo diario es mejor la ayuda contextual de cada vista.',
    ],
  }),
  automationRules: guide({
    title: 'Tasques i regles',
    summary: 'Configura reglas globales de severidad y gestiona la bandeja interna de tareas derivadas de automatizaciones.',
    purpose: 'Traducir hallazgos automáticos en acciones operativas: crear tarea, enviar correo, adjuntar informe y seguir el estado de resolución.',
    highlights: [
      { label: 'Controla', value: 'Reglas globales por severidad y estado de tareas internas' },
      { label: 'Entrada', value: 'Severidad, prioridad, destinatarios, mínimo de hallazgos y estado habilitado' },
      { label: 'Salida', value: 'Reglas activas y tareas actualizadas para seguimiento operativo' },
    ],
    diagram: {
      center: {
        label: 'Tasques i regles',
        subtitle: 'Capa de gobierno operativo sobre los hallazgos automáticos',
        icon: 'ShieldAlert',
      },
      branches: [
        branch('Reglas', 'CheckSquare', 'Definen qué pasa cuando aparece una severidad concreta.', [
          'Crear tarea',
          'Enviar correo',
          'Adjuntar informe',
          'Mínimo de hallazgos',
        ], 'primary'),
        branch('Tareas', 'Workflow', 'La segunda mitad de la vista hace seguimiento del trabajo derivado.', [
          'Estado',
          'Prioridad',
          'Resolución',
        ], 'process'),
        branch('Conexiones', 'GitBranch', 'Se apoya en el resultado de las automatizaciones y condiciona la operación diaria.', [
          'Findings automáticos',
          'Seguimiento interno',
          'Comunicación por correo',
        ], 'related'),
      ],
    },
    actions: [
      action('Editar reglas globales existentes', 'Cada regla define cómo se comporta el sistema ante una severidad dada.'),
      action('Crear una regla nueva', 'Puedes añadir una combinación nueva de prioridad, envío, adjunto y umbral mínimo.', 'CheckSquare'),
      action('Actualizar tareas abiertas', 'La bandeja de tareas permite mover el trabajo entre pendiente, en curso, resuelta o descartada.', 'Workflow'),
    ],
    workflow: [
      step('Cargas reglas y tareas', 'La pantalla consulta ambas colecciones en paralelo.'),
      step('Ajustas la lógica operativa', 'Guardas cambios en reglas globales o creas una nueva.'),
      step('Gestionas la ejecución humana', 'La misma vista permite actualizar el estado de las tareas derivadas.'),
    ],
    architecture: {
      components: ['`AutomationRulesView.jsx` agrupa edición de reglas y bandeja de tareas.'],
      dataSources: ['`listSeverityRules`, `createSeverityRule`, `updateSeverityRule`, `listAutomationTasks`, `updateAutomationTask`.'],
      processes: ['Carga paralela, edición en memoria y persistencia puntual por acción.'],
      integrations: ['Backend de automatización y pipeline que genera hallazgos automáticos.'],
    },
    relatedData: [
      datum('Input', 'Severidad, prioridad, destinatarios, mínimos y estado de tarea', 'input'),
      datum('Persistencia', 'Reglas y tareas en el backend de automatización', 'store'),
      datum('Output', 'Gobierno operativo actualizado sobre hallazgos automáticos', 'output'),
    ],
    relationships: {
      incoming: ['Se alimenta de las severidades generadas por el circuito automático.'],
      outgoing: ['Condiciona qué tareas se crean y cuándo se envían correos.'],
      dependencies: ['Servicios de severity rules y automation tasks.'],
    },
    tips: [
      'Antes de endurecer una regla, revisa el volumen en Dashboard e Històric para no disparar demasiadas tareas o correos.',
    ],
  }),
  checksAdmin: guide({
    title: 'Gestió de controls',
    summary: 'Administra els checks SQL del sistema con CRUD, versionado, prevalidación, diff, regeneración IA y herramientas de transformación SQL.',
    purpose: 'Mantener el inventario de controles que luego ejecuta la auditoría post-CRQ, con garantías mínimas antes de activar cambios.',
    highlights: [
      { label: 'Entradas', value: 'Metadatos del check, SQL vigente, variables, ventana de validación y perfil Oracle' },
      { label: 'Capacidades', value: 'CRUD, diff, validación preview, historial, sync docs y regeneración IA' },
      { label: 'Impacto', value: 'Cualquier cambio aquí afecta directamente a Auditoria de canvis' },
    ],
    diagram: {
      center: {
        label: 'Gestió de controls',
        subtitle: 'Editor y gobierno del catálogo SQL que usa la auditoría post-CRQ',
        icon: 'SquareTerminal',
      },
      branches: [
        branch('Datos', 'FileText', 'La vista combina catálogo vivo y fuente documental en markdown.', [
          '`/api/checks`',
          '`/api/audit/post-crq/checks`',
          'Historial y sync status',
        ], 'data'),
        branch('Procesos', 'Workflow', 'Antes de guardar puedes validar, previsualizar y comparar versiones.', [
          'Validate preview',
          'Diff vs versión actual',
          'Regeneración IA',
          'Transform SQL',
        ], 'process'),
        branch('Salidas', 'GitBranch', 'El resultado es el catálogo que consume la auditoría post-CRQ.', [
          'Checks activos',
          'Historial versionado',
          'Explicación IA',
        ], 'related'),
      ],
    },
    actions: [
      action('Crear, editar o eliminar checks', 'La vista permite mantener el catálogo funcional sin tocar ficheros dispersos a mano.', 'CheckSquare'),
      action('Prevalidar la consulta y la preview IA', 'Antes de guardar puedes ejecutar `validate-preview` con un perfil y una ventana de datos reales.', 'Database'),
      action('Comparar versiones y revisar diff', 'Cada check guarda histórico y la UI muestra diferencias respecto a la versión actual.', 'ArrowRightLeft'),
      action('Regenerar explicación IA', 'La ficha de detalle puede relanzar la generación de explicación funcional del check.', 'Sparkles'),
      action('Usar el workbench SQL/Codex', 'El panel especializado transforma SQL y aporta trazas para trabajo técnico más fino.', 'SquareTerminal'),
    ],
    workflow: [
      step('Cargas catálogo y markdown de referencia', 'La vista consulta checks vivos y la fuente documental en paralelo.'),
      step('Editas o creas un check', 'Rellenas metadatos, SQL, variables y contexto funcional.'),
      step('Validas antes de guardar', 'La prevalidación usa un perfil y una ventana temporal real para evitar romper el catálogo.'),
      step('Persistes y revisas histórico', 'Tras guardar, puedes abrir el detalle, ver diff, sync status o regenerar IA.'),
    ],
    architecture: {
      components: [
        '`ChecksAdminView.jsx` es una vista compleja con formularios, tabla, panel de detalle y documentación operacional.',
        '`PostCrqOperationalDocsPanel.jsx` y `SQLCodexWorkbench.jsx` enriquecen la operativa documental y técnica.',
      ],
      dataSources: [
        '`/api/checks`, `/api/checks/:id/history`, `/api/checks/:id/sync-status`, `/api/checks/:id/regenerate`.',
        '`/api/audit/post-crq/checks` como fuente markdown complementaria.',
        '`/api/checks/validate-preview` y `/api/checks/transform-sql` para soporte técnico.',
      ],
      processes: [
        'Fusión entre catálogo vivo y fuente markdown para detectar diferencias.',
        'Validación previa con firma basada en formulario, perfil y ventana temporal.',
        'Soft-delete, versionado y regeneración de explicación IA.',
      ],
      integrations: [
        'Auditoria de canvis consume el catálogo mantenido aquí.',
        'Oracle se usa en la prevalidación real de consultas.',
      ],
    },
    relatedData: [
      datum('Input', 'Formulario del check, variables detectadas, perfil de validación y rango temporal', 'input'),
      datum('Persistencia', 'Catálogo versionado de checks en backend y referencia markdown', 'store'),
      datum('Output', 'Checks operativos, previews validadas, historial y explicación IA regenerada', 'output'),
    ],
    relationships: {
      incoming: [
        'Recibe el perfil activo desde la shell para validar consultas sobre Oracle.',
        'Se apoya en documentación técnica y fuente markdown para sincronización funcional.',
      ],
      outgoing: [
        'Impacta directamente en qué ejecuta Auditoria de canvis.',
        'Puede requerir ajustes posteriores en criticidad o documentación operacional.',
      ],
      dependencies: [
        'Servicios `/api/checks*` y el documento técnico `/api/docs/technical-audit`.',
        'Componentes auxiliares de workbench y docs operacionales.',
      ],
    },
    tips: [
      'No guardes un cambio sin prevalidar si el check toca ventanas temporales o variables dinámicas.',
      'Si el SQL y el markdown difieren, decide cuál es la fuente correcta antes de regenerar IA o activar la nueva versión.',
    ],
  }),
  mailConfig: guide({
    title: 'Configuració del servidor',
    summary: 'Configuración de entrega: SMTP, rutas compartidas, Teams, SharePoint y retención del histórico y de la cola de reintentos.',
    purpose: 'Controlar cómo se envían, enrutan y conservan los artefactos generados por las automatizaciones.',
    highlights: [
      { label: 'Capas', value: 'SMTP, destinatarios por defecto, rutas TIC/proveedor, Teams, SharePoint y retención' },
      { label: 'Prueba incluida', value: 'Envío de correo de test con la configuración actual' },
      { label: 'Impacto', value: 'Afecta a Jobs, Històric y Reintents aunque no lance auditorías por sí misma' },
    ],
    diagram: {
      center: {
        label: 'Configuració del servidor',
        subtitle: 'Capa de entrega y conectividad del circuito automático',
        icon: 'Settings2',
      },
      branches: [
        branch('SMTP', 'Mail', 'Define cómo sale el correo del sistema.', [
          'Host',
          'Puerto',
          'Credenciales',
          'TLS',
          'Remitente',
        ], 'primary'),
        branch('Rutas', 'Route', 'Conserva destinatarios globales, TIC y por proveedor.', [
          'Default recipients',
          'Failure notifications',
          'TIC summary',
          'Provider routes',
        ], 'data'),
        branch('Integraciones', 'Link2', 'Amplía el circuito fuera del correo puro.', [
          'Teams webhook',
          'SharePoint site/library/folder',
        ], 'process'),
        branch('Mantenimiento', 'History', 'Gobierna cuánto tiempo se conservan datos operativos.', [
          'History retention',
          'Retry retention',
          'Auto purge',
        ], 'related'),
      ],
    },
    actions: [
      action('Configurar SMTP y remitente', 'La primera mitad de la pantalla define cómo se enviarán los correos del sistema.'),
      action('Mantener rutas de entrega', 'Puedes editar destinatarios globales, resumen TIC y rutas por proveedor.', 'Route'),
      action('Probar un correo real', 'La acción de test verifica si la configuración actual es suficiente antes de usarla en producción.', 'Mail'),
      action('Configurar Teams y SharePoint', 'La vista también guarda conectores externos usados por el proceso de entrega.', 'Link2'),
      action('Ajustar retención y purga', 'Permite decidir cuántos días se conservan histórico y reintentos, y si la purga automática está activa.', 'History'),
    ],
    workflow: [
      step('Cargas configuración y rutas', 'La vista consulta en paralelo delivery config y delivery routes.'),
      step('Editas las capas necesarias', 'SMTP, audiencias, integraciones externas y retención se mantienen en el mismo formulario compuesto.'),
      step('Guardas y validas', 'La pantalla persiste configuración y rutas, y opcionalmente lanza un correo de prueba.'),
    ],
    architecture: {
      components: ['`MailConfigView.jsx` compone bloques SMTP, rutas, Teams, SharePoint y acciones finales.'],
      dataSources: ['`getDeliveryConfig`, `getDeliveryRoutes`, `updateDeliveryConfig`, `updateDeliveryRoutes`, `testDeliveryEmail`.'],
      processes: [
        'Normalización de recipients desde texto plano a arrays.',
        'Edición de audiencias TIC y rutas por proveedor con estado habilitado.',
        'Persistencia separada de configuración general y rutas de entrega.',
      ],
      integrations: [
        'SMTP para email.',
        'Teams y SharePoint como conectores complementarios de distribución.',
      ],
    },
    relatedData: [
      datum('Input', 'Config SMTP, destinatarios, webhooks, rutas y retención', 'input'),
      datum('Persistencia', 'Delivery config y delivery routes en backend de automatización', 'store'),
      datum('Output', 'Infraestructura de entrega lista para jobs, histórico y reintentos', 'output'),
    ],
    relationships: {
      incoming: [
        'Jobs, Històric y Reintents dependen de esta configuración para completar la entrega.',
      ],
      outgoing: [
        'Cambia cómo y a quién llegan los artefactos del sistema automático.',
      ],
      dependencies: [
        'Servicios de delivery config/routes del backend.',
        'Acceso real a SMTP cuando se ejecuta el test o la distribución automática.',
      ],
    },
    tips: [
      'Después de cambiar SMTP o remitente, ejecuta el test antes de volver a confiar en jobs o reintentos.',
      'Si la audiencia está mal, corrige las rutas aquí o en Destinataris antes de relanzar un run.',
    ],
  }),
  tutorial: guide({
    title: 'Guia i Ajuda',
    summary: 'Documentación embebida del producto: quick-start, arquitectura, mapa de menús, flujos y notas operativas.',
    purpose: 'Acelerar el onboarding y ofrecer contexto global sin obligar al usuario a salir de la aplicación.',
    highlights: [
      { label: 'Contenido', value: 'Quick-start, arquitectura React/FastAPI, menús, ejemplos y resolución de problemas' },
      { label: 'Naturaleza', value: 'Pantalla documental, no operativa' },
      { label: 'Valor', value: 'Reduce dependencia de conocimiento tácito del equipo' },
    ],
    diagram: {
      center: {
        label: 'Guia i Ajuda',
        subtitle: 'Punto de entrada documental para nuevos usuarios y referencia rápida',
        icon: 'BookOpen',
      },
      branches: [
        branch('Onboarding', 'Sparkles', 'Ayuda a orientarse en pocos minutos.', [
          'Prerequisitos',
          'Checklist',
          'Ejemplos',
        ], 'primary'),
        branch('Arquitectura', 'Network', 'Explica capas, endpoints y componentes principales.', [
          'React SPA',
          'FastAPI',
          'Oracle y SQLite',
        ], 'data'),
        branch('Menús', 'Layers3', 'Resume qué hace cada pantalla y cuándo usarla.', [
          'Deep Scan',
          'Post-CRQ',
          'Checks',
          'Configuración',
        ], 'related'),
      ],
    },
    actions: [
      action('Consultar el arranque rápido', 'La primera sección resume los pasos mínimos para empezar a trabajar.'),
      action('Entender la arquitectura del sistema', 'Los diagramas y callouts explican cómo fluyen datos y responsabilidades.'),
      action('Usarla como referencia de menús', 'Ayuda a decidir qué pantalla usar según el problema o la fase del proceso.', 'Layers3'),
    ],
    workflow: [
      step('Empiezas por quick-start', 'Entiendes prerequisitos y secuencia mínima de uso.'),
      step('Profundizas en arquitectura', 'La pantalla explica capas, endpoints y fuentes de datos.'),
      step('Saltas al módulo correcto', 'Con el contexto claro, vuelves a la pantalla operativa que corresponda.'),
    ],
    architecture: {
      components: ['`TutorialView.jsx` está compuesta como un documento interactivo con secciones, diagramas y ejemplos.'],
      dataSources: ['Contenido estático embebido en frontend y referencias explícitas a archivos/endpoints reales.'],
      processes: ['No muta datos; solo presenta conocimiento estructurado.'],
      integrations: ['Relaciona visualmente frontend, backend, Oracle, SQLite y sistema de archivos.'],
    },
    relatedData: [
      datum('Entrada', 'No depende de datos productivos; consume documentación embebida', 'input'),
      datum('Salida', 'Comprensión del producto y del flujo operativo', 'output'),
    ],
    relationships: {
      incoming: ['Se consulta desde navegación normal cuando el usuario necesita orientación general.'],
      outgoing: ['Redirige conceptualmente a todas las vistas operativas del programa.'],
      dependencies: ['Solo depende del frontend; no necesita conectividad Oracle para mostrarse.'],
    },
    tips: [
      'Si un usuario nuevo no sabe por dónde empezar, esta es la mejor primera pantalla para abrir.',
    ],
  }),
  architecture: guide({
    title: 'Arquitectura',
    summary: 'Explorador visual de capas, componentes, hooks y flujos de interacción del Dashboard E13BD.',
    purpose: 'Mostrar cómo está construido el frontend y cómo dialoga con el backend para que el usuario entienda la estructura funcional interna.',
    highlights: [
      { label: 'Cubre', value: 'UI layer, lógica en hooks, servicios API y flujos de interacción' },
      { label: 'Interacción', value: 'Seleccionar nodos y flujos para ver detalle contextual' },
      { label: 'Salida', value: 'Comprensión estructural de componentes, responsabilidades e inputs/outputs' },
    ],
    diagram: {
      center: {
        label: 'Arquitectura',
        subtitle: 'Vista metadocumental de la aplicación y sus relaciones internas',
        icon: 'Network',
      },
      branches: [
        branch('Capas', 'Layers3', 'Organiza la app en UI, hooks y servicios.', [
          'Views React',
          'Custom hooks',
          'Axios services',
        ], 'primary'),
        branch('Flujos', 'Workflow', 'Visualiza secuencias de interacción completas.', [
          'Click de usuario',
          'Hook',
          'Backend',
          'Re-render',
        ], 'process'),
        branch('Detalle', 'Info', 'Cada nodo explica rol, inputs y outputs.', [
          'Responsabilidad',
          'Estado',
          'Explicación de código',
        ], 'related'),
      ],
    },
    actions: [
      action('Seleccionar un componente o hook', 'El panel derecho cambia para explicar responsabilidad, inputs y outputs del nodo elegido.'),
      action('Abrir un flujo de interacción', 'Los flujos muestran el orden de ejecución entre usuario, frontend y backend.', 'Workflow'),
      action('Usarla como mapa de mantenimiento', 'Ayuda a entender dónde tocar cuando una funcionalidad vive en varias capas.', 'GitBranch'),
    ],
    workflow: [
      step('Exploras las capas', 'La columna principal agrupa nodos de UI, lógica y servicios.'),
      step('Seleccionas un nodo o flujo', 'La vista fija el detalle contextual o la secuencia correspondiente.'),
      step('Lees la explicación técnica', 'El panel lateral resume responsabilidad, estado e incluso un fragmento de pseudocódigo.'),
    ],
    architecture: {
      components: [
        '`SystemArchitectureView.jsx` contiene el dataset de capas y flujos y renderiza el explorador.',
        'Los nodos y flujos son puramente documentales, no operativos.',
      ],
      dataSources: [
        'Dataset estático `ARCHITECTURE_DATA` definido en la propia vista.',
      ],
      processes: [
        'Selección de nodo y flujo mediante estado local.',
        'Render condicional del detalle técnico del componente seleccionado.',
      ],
      integrations: [
        'Se apoya en `framer-motion` para transiciones suaves del panel y del flujo.',
      ],
    },
    relatedData: [
      datum('Input', 'Selección local de nodo o flujo', 'input'),
      datum('Persistencia', 'No escribe datos; funciona como explorador documental', 'store'),
      datum('Output', 'Entendimiento claro de arquitectura funcional e interna', 'output'),
    ],
    relationships: {
      incoming: ['Complementa Tutorial y la ayuda contextual de las demás páginas.'],
      outgoing: ['Ayuda a localizar qué vista, hook o servicio revisar cuando cambias el sistema.'],
      dependencies: ['Solo depende de la propia SPA y de `framer-motion`.'],
    },
    tips: [
      'Úsala para orientarte antes de hacer cambios grandes o para explicar el sistema a alguien nuevo del equipo.',
    ],
  }),
};

export function getPageHelp(helpKey) {
  if (!helpKey) return null;
  return PAGE_HELP_CONTENT[helpKey] || null;
}
