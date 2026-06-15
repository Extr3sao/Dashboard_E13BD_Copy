import React, { useState } from 'react';
import { 
  Network, 
  Cpu, 
  Database, 
  Zap, 
  Activity, 
  Code, 
  ArrowRight, 
  Info, 
  Layers, 
  Webhook, 
  Fingerprint,
  ArrowBigDown,
  ChevronRight
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const ARCHITECTURE_DATA = {
  layers: [
    {
      id: 'ui-layer',
      name: 'UI Layer (React Views)',
      icon: Layers,
      description: 'Capa de presentació on resideixen les vistes principals i els components de la interfície.',
      items: [
        { id: 'App', name: 'App.jsx', type: 'Controller', details: 'Orquestrador global de l\'estat de navegació i context d\'auditoria.' },
        { id: 'DatabaseAuditWorkspace', name: 'DatabaseAuditWorkspace', type: 'View', details: 'Contenidor principal per a totes les operacions d\'auditoria (Deep Scan, Post-CRQ).' },
        { id: 'DeepScanView', name: 'DeepScanView', type: 'View', details: 'Visualització detallada de l\'estat d\'un esquema Oracle i la seva obsolescència.' },
        { id: 'PostCrqAuditView', name: 'PostCrqAuditView', type: 'View', details: 'Interfície per executar i analitzar els checks pre/post canvi en BBDD.' }
      ]
    },
    {
      id: 'logic-layer',
      name: 'Logic Layer (Custom Hooks)',
      icon: Cpu,
      description: 'On resideix la lògica de negoci, la gestió de l\'estat complex i les crides asíncrones.',
      items: [
        { id: 'useDeepScan', name: 'useDeepScan', type: 'Hook', details: 'Gestiona l\'estat de l\'auditoria profunda, el càlcul de l\'score i la comunicació amb l\'API.' },
        { id: 'usePostCrqAudit', name: 'usePostCrqAudit', type: 'Hook', details: 'Encapsula la càrrega de checks, la selecció i l\'execució de l\'auditoria Post-CRQ.' },
        { id: 'useProfiles', name: 'useProfiles', type: 'Hook', details: 'Obté i gestiona els perfils de connexió Oracle disponibles al backend.' }
      ]
    },
    {
      id: 'api-layer',
      name: 'API Layer (Axios Services)',
      icon: Webhook,
      description: 'Interfície de comunicació amb el backend FastAPI.',
      items: [
        { id: 'postCrqAuditApi', name: 'postCrqAudit.js', type: 'Service', details: 'Endpoints per executar l\'audit i descarregar les queries SQL generades.' },
        { id: 'automationApi', name: 'automation.js', type: 'Service', details: 'Gestió de tasques programades i regles d\'automatització.' }
      ]
    }
  ],
  flows: [
    {
      id: 'audit-execution',
      name: 'Flow: Execució d\'Auditoria',
      steps: [
        { action: 'Click "Auditar"', actor: 'Usuari', target: 'DeepScanView' },
        { action: 'Invoke runDeepAudit()', actor: 'DeepScanView', target: 'useDeepScan' },
        { action: 'POST /audit/deep', actor: 'useDeepScan', target: 'FastAPI Backend' },
        { action: 'Update auditData', actor: 'useDeepScan', target: 'App State' },
        { action: 'Re-render Components', actor: 'App State', target: 'UI' }
      ]
    }
  ]
};

export default function SystemArchitectureView() {
  const [selectedNode, setSelectedNode] = useState(null);
  const [activeFlow, setActiveFlow] = useState(null);

  return (
    <div className="flex flex-col gap-6 p-4">
      <div className="glass-card p-6 border-l-4 border-l-primary mb-2">
        <h3 className="text-2xl font-extrabold flex items-center gap-3">
          <Network className="text-primary" /> Architecture Explorer
        </h3>
        <p className="text-muted-foreground mt-2 max-w-2xl">
          Aquesta vista interactiva explica com està construït el Dashboard E13BD, mostrant la relació entre components, hooks i el flux de dades cap al backend.
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        {/* PANEL ESQUERRA: MAPA DE COMPONENTS */}
        <div className="xl:col-span-8 flex flex-col gap-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {ARCHITECTURE_DATA.layers.map((layer) => (
              <div key={layer.id} className="flex flex-col gap-3">
                <div className="flex items-center gap-2 mb-1 px-2">
                  <layer.icon size={18} className="text-primary" />
                  <span className="text-sm font-bold uppercase tracking-wider opacity-70">{layer.name}</span>
                </div>
                <div className="space-y-3">
                  {layer.items.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => {
                        setSelectedNode(item);
                        setActiveFlow(null);
                      }}
                      className={`w-full text-left p-4 rounded-xl border transition-all hover:scale-[1.02] active:scale-[0.98] ${
                        selectedNode?.id === item.id 
                          ? 'bg-primary/20 border-primary shadow-lg shadow-primary/10' 
                          : 'bg-white/5 border-white/10 hover:bg-white/10'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-mono text-sm font-bold">{item.name}</span>
                        <span className="text-[10px] px-2 py-0.5 rounded bg-white/10 text-muted-foreground border border-white/5">
                          {item.type}
                        </span>
                      </div>
                      <p className="text-[11px] opacity-60 line-clamp-2 leading-relaxed">
                        {item.details}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* SECCIÓ FLUXES D'INTERACCIÓ */}
          <div className="glass-card p-6 bg-primary/5 border border-primary/20 relative overflow-hidden">
            <div className="absolute top-[-20px] right-[-20px] opacity-5">
              <Activity size={200} />
            </div>
            
            <h4 className="text-lg font-bold mb-4 flex items-center gap-2">
              <Zap size={20} className="text-yellow-400" /> Fluxos d'Interacció del Sistema
            </h4>
            
            <div className="flex gap-4 mb-6">
              {ARCHITECTURE_DATA.flows.map(flow => (
                <button
                  key={flow.id}
                  onClick={() => {
                    setActiveFlow(flow);
                    setSelectedNode(null);
                  }}
                  className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${
                    activeFlow?.id === flow.id 
                    ? 'bg-primary text-primary-foreground' 
                    : 'bg-white/10 hover:bg-white/20'
                  }`}
                >
                  {flow.name}
                </button>
              ))}
            </div>

            <AnimatePresence mode="wait">
              {activeFlow ? (
                <motion.div 
                  key={activeFlow.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="flex flex-col md:flex-row items-center justify-between gap-4 py-4"
                >
                  {activeFlow.steps.map((step, idx) => (
                    <React.Fragment key={idx}>
                      <div className="flex flex-col items-center gap-2 p-3 bg-background/50 border border-white/10 rounded-xl min-w-[140px] relative z-10">
                        <span className="text-[9px] font-bold uppercase opacity-50">{step.actor}</span>
                        <span className="text-xs font-bold text-center">{step.action}</span>
                        <div className="w-1 h-1 bg-primary rounded-full mt-1" />
                        <span className="text-[9px] font-mono text-primary">{step.target}</span>
                      </div>
                      {idx < activeFlow.steps.length - 1 && (
                        <div className="hidden md:block">
                          <ChevronRight className="text-primary/40 animate-pulse" />
                        </div>
                      )}
                    </React.Fragment>
                  ))}
                </motion.div>
              ) : (
                <div className="text-sm italic opacity-40 py-8 text-center border border-dashed border-white/10 rounded-xl">
                  Selecciona un flux per visualitzar l'ordre d'execució i canvis d'estat.
                </div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* PANEL DRETA: DETALLS I EXPLICACIÓ */}
        <div className="xl:col-span-4">
          <AnimatePresence mode="wait">
            {selectedNode ? (
              <motion.div
                key={selectedNode.id}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="glass-card p-6 h-full border-t-4 border-t-primary"
              >
                <div className="flex items-center justify-between mb-6">
                  <h4 className="text-xl font-black">{selectedNode.name}</h4>
                  <span className="px-3 py-1 bg-primary text-primary-foreground text-[10px] font-black rounded-full">
                    {selectedNode.type.toUpperCase()}
                  </span>
                </div>

                <div className="space-y-6">
                  <div>
                    <h5 className="text-xs font-bold uppercase opacity-50 mb-2 flex items-center gap-1">
                      <Info size={12} /> Responsabilitat
                    </h5>
                    <p className="text-sm leading-relaxed">
                      {selectedNode.details}
                    </p>
                  </div>

                  {selectedNode.type === 'Hook' && (
                    <div>
                      <h5 className="text-xs font-bold uppercase opacity-50 mb-2 flex items-center gap-1">
                        <Fingerprint size={12} /> Gestió de l'Estat
                      </h5>
                      <div className="bg-white/5 rounded-lg p-3 text-xs space-y-2 border border-white/5">
                        <p className="flex justify-between"><span>Inputs:</span> <span className="text-primary font-mono">activeTab, profile</span></p>
                        <p className="flex justify-between"><span>Outputs:</span> <span className="text-green-400 font-mono">auditData, isAuditing</span></p>
                      </div>
                    </div>
                  )}

                  <div>
                    <h5 className="text-xs font-bold uppercase opacity-50 mb-2 flex items-center gap-1">
                      <Code size={12} /> Explicació del Codi
                    </h5>
                    <div className="bg-background/80 rounded-xl p-4 font-mono text-[11px] leading-relaxed border border-white/5 whitespace-pre-wrap">
                      {selectedNode.id === 'useDeepScan' && (
                        `// El hook centralitza la consulta asíncrona\nconst runDeepAudit = async () => {\n  setIsAuditing(true);\n  const res = await api.post('/audit/deep');\n  setAuditData(res.data);\n  setIsAuditing(false);\n};`
                      )}
                      {selectedNode.id === 'App' && (
                        `// L'App és el context global\nconst { activeTab, setActiveTab } = usePersistedState();\n\nreturn (\n  <main>\n    {activeTab === 'Deep Scan' && <DeepScanView />}\n  </main>\n);`
                      )}
                      {!['useDeepScan', 'App'].includes(selectedNode.id) && (
                        `// Aquest component encapsula la lògica de ${selectedNode.name}\ni s'integra mitjançant props heretades de la vista superior.`
                      )}
                    </div>
                  </div>

                  <div className="bg-yellow-500/5 border border-yellow-500/20 p-4 rounded-xl">
                    <p className="text-[10px] uppercase font-bold text-yellow-500 mb-1">Nota Tècnica</p>
                    <p className="text-[11px] leading-tight opacity-70 italic">
                      L'acoblament es manté baix mitjançant l'ús de hooks que separen la lògica de la representació visual.
                    </p>
                  </div>
                </div>
              </motion.div>
            ) : (
              <div className="glass-card p-8 h-full flex flex-col items-center justify-center text-center gap-4 border border-dashed border-white/20 opacity-60">
                <div className="p-4 bg-white/5 rounded-full">
                  <Network size={40} className="text-primary" />
                </div>
                <div>
                  <h4 className="font-bold">Detalls del Component</h4>
                  <p className="text-sm max-w-[200px] mt-2">Selecciona un objecte del mapa per veure el seu funcionament detallat.</p>
                </div>
              </div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
