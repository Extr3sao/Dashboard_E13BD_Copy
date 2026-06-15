class ScoringEngine:
    def __init__(self, days_threshold=180):
        self.days_threshold = days_threshold

    def classify_schema(self, row):
        """
        Calcula la fase de neteja i el nivell de risc basat en les regles expertes.
        Fase 5: SEGUR (Verd) - Buit i sense vida
        Fase 4: NETEJA PRÈVIA (Verd) - Té dades però sense activitat/deps
        Fase 3: INVESTIGAR (Groc) - Té APEX
        Fase 2: ATURADA (Roig) - Activitat recent (< 30 dies)
        Fase 1: CRÍTIC (Roig) - Dependències externes
        """
        reasons = []
        
        # 🔴 FASE 1: DEPENDÈNCIES EXTERNES (CRÍTIC)
        if row.get('EXTERNAL_DEPENDENCIES', 0) > 0:
            return {
                "fase": "Fase 1: ATURAR - Dependències externes",
                "risc": "ROIG (No eliminar)",
                "motiu": f"Té {row['EXTERNAL_DEPENDENCIES']} dependències entrants d'altres esquemes."
            }

        # 🔴 FASE 2: ACTIVITAT RECENT (LOGIN/JOBS)
        if row.get('LAST_LOGIN_DAYS_AGO', 999) < 30:
            return {
                "fase": "Fase 2: ATURAR - Activitat recent",
                "risc": "ROIG (No eliminar)",
                "motiu": f"Login detectat fa {row['LAST_LOGIN_DAYS_AGO']} dies."
            }
        
        if row.get('ACTIVE_JOBS', 0) > 0:
            return {
                "fase": "Fase 2: ATURAR - Jobs actius",
                "risc": "ROIG (No eliminar)",
                "motiu": f"Té {row['ACTIVE_JOBS']} jobs programats en execució."
            }

        # 🟡 FASE 3: APLICACIONS APEX (INVESTIGAR)
        if row.get('APEX_APPLICATIONS', 0) > 0:
            return {
                "fase": "Fase 3: INVESTIGAR - APEX",
                "risc": "GROC (Revisar)",
                "motiu": f"Conté {row['APEX_APPLICATIONS']} aplicacions APEX vinculades."
            }

        # 🟢 FASE 4: NETEJA PRÈVIA (SENSE VIDA PERÒ AMB DADES)
        if row.get('SIZE_GB', 0) > 0.1:
            return {
                "fase": "Fase 4: PROCEDIR - Neteja prèvia",
                "risc": "VERD (Amb precaució)",
                "motiu": f"Esquema inactiu però amb volum ({row['SIZE_GB']:.2f} GB)."
            }

        # 🟢 FASE 5: ELIMINACIÓ SEGURA (BUIT I SENSE VIDA)
        return {
            "fase": "Fase 5: PROCEDIR - Segur per eliminar",
            "risc": "VERD (Segur)",
            "motiu": "Esquema completament buit i sense cap senyal de vida."
        }
