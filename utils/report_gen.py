from jinja2 import Environment, FileSystemLoader
import os
import pandas as pd
from datetime import datetime

class ReportGenerator:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        # In a real app, templates would be in a separate folder
        self.template_html = """
        <!DOCTYPE html>
        <html lang="ca">
        <head>
            <meta charset="UTF-8">
            <title>Informe de Neteja de BBDD - {{ timestamp }}</title>
            <style>
                body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; color: #333; margin: 40px; }
                h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
                .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px; }
                table { width: 100%; border-collapse: collapse; margin-top: 20px; }
                th, td { text-align: left; padding: 12px; border-bottom: 1px solid #ddd; }
                th { background-color: #3498db; color: white; }
                tr:hover { background-color: #f1f1f1; }
                .badge { padding: 4px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; }
                .DROP { background-color: #e74c3c; color: white; }
                .ARCHIVE { background-color: #f39c12; color: white; }
                .REVIEW { background-color: #3498db; color: white; }
                .KEEP { background-color: #2ecc71; color: white; }
            </style>
        </head>
        <body>
            <h1>Informe d'Auditoria i Neteja de BBDD</h1>
            <p>Generat el: {{ timestamp }}</p>
            
            <div class="card">
                <h2>Resum d'Obsolescència</h2>
                <p>Total objectes analitzats: {{ total_objects }}</p>
                <p>Candidats a DROP/ARCHIVE: {{ candidates_count }}</p>
            </div>

            <div class="card">
                <h2>Backlog de Neteja Prioritzat</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Esquema</th>
                            <th>Taula</th>
                            <th>Mida (GB)</th>
                            <th>Score</th>
                            <th>Recomanació</th>
                            <th>Evidència</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for item in backlog %}
                        <tr>
                            <td>{{ item.schema }}</td>
                            <td>{{ item.table_name }}</td>
                            <td>{{ "%.4f"|format(item.size_gb) }}</td>
                            <td>{{ item.score }}</td>
                            <td><span class="badge {{ item.recommendation }}">{{ item.recommendation }}</span></td>
                            <td>{{ item.evidence }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </body>
        </html>
        """

    def generate_html(self, df_backlog: pd.DataFrame) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        file_path = os.path.join(self.output_dir, filename)

        from jinja2 import Template
        template = Template(self.template_html)
        
        backlog_data = df_backlog.sort_values(by='score', ascending=False).to_dict(orient='records')
        
        html_out = template.render(
            timestamp=timestamp,
            total_objects=len(df_backlog),
            candidates_count=len(df_backlog[df_backlog['recommendation'].isin(['DROP', 'ARCHIVE'])]),
            backlog=backlog_data
        )

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_out)
        
        return file_path
