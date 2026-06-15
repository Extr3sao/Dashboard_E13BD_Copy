import os
import json
from pathlib import Path

class ReportDesignAgent:
    """
    Agent responsable de definir la 'guia d'estil' i l'estructura dels informes.
    Actua com la font de veritat per al disseny professional i institucional
    llegint la seva configuració des d'un fitxer JSON administrat (Dumb Engine pattern).
    """
    
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Load identity from config file instead of hardcoded
        config_path = Path(self.base_dir) / "config" / "report_identity.json"
        self._load_config(config_path)

        # Rutes de Recursos
        preferred_logo = Path(self.base_dir) / "logo" / "Logo-Departament-Educacio.png"
        fallback_logo = Path(self.base_dir) / "resources" / "logo_oracle_audit.png"
        self.logo_path = str(preferred_logo if preferred_logo.exists() else fallback_logo)

    def _load_config(self, filepath):
        """Carrega la configuració corporativa i estilística."""
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            # Fallback if config does not exist
            config = {
                "identity": {"institution_name": "", "department_name": "", "application_name": "Auditoria Oracle E13BD"},
                "colors": {"primary": "#0A4FB3", "secondary": "#1e3a8a", "text_light": "#6b7280"},
                "style": {"font_family": "sans-serif", "font_size_base": "9pt", "line_height": "1.5"},
                "report_structure": {"standard": []},
                "narrative_templates": {"summary": ""}
            }
            
        self.identity = config.get("identity", {})
        self.institution_name = self.identity.get("institution_name", "")
        self.department_name = self.identity.get("department_name", "")
        self.application_name = self.identity.get("application_name", "Auditoria Oracle E13BD")
        
        self.colors = config.get("colors", {})
        self.style = config.get("style", {})
        self.report_structures = config.get("report_structure", {})
        self.narrative_templates = config.get("narrative_templates", {})

    def get_style_config(self):
        """Retorna la configuració CSS basada en les regles recollides en configuració."""
        style_config = self.style.copy()
        
        # Merge dynamic color assignments
        style_config.update({
            "h1_color": self.colors.get("primary", "#000"),
            "h2_color": self.colors.get("secondary", "#000"),
            "h3_color": self.colors.get("secondary", "#000"),
            "table_header_bg": self.colors.get("secondary", "#000")
        })
        return style_config

    def get_report_structure(self, report_type="standard"):
        """Defineix l'ordre i els títols de les seccions segons el tipus d'informe."""
        return self.report_structures.get(report_type, [])

    def get_summary_narrative_template(self):
        """Retorna el format de narrativa formal per als resums."""
        return self.narrative_templates.get("summary", "")

    def get_header_html(self, profile, generation_date):
        """Genera el bloc HTML de la capçalera seguint les guies de disseny carregades."""
        logo_img = ""
        if os.path.exists(self.logo_path):
            logo_src = Path(self.logo_path).resolve().as_posix()
            logo_img = f'<img src="{logo_src}" height="36" style="vertical-align:middle;"/>'
            
        return f"""
        <table style="width:100%; border:none; border-bottom:2px solid {self.colors.get('primary', '#000')}; padding-bottom:8px; margin-bottom:8px;">
            <tr>
                <td style="border:none; vertical-align:middle;">
                    {logo_img}
                </td>
                <td style="text-align:right; color:{self.colors.get('text_light', '#333')}; font-size:8pt; line-height:1.35; vertical-align:middle; border:none;">
                    <span style="font-size:9pt; color:{self.colors.get('secondary', '#000')};"><strong>{self.application_name}</strong></span><br/>
                    {self.department_name}<br/>
                    Perfil: {profile} | {generation_date}
                </td>
            </tr>
        </table>
        """
