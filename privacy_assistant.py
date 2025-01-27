from typing import Dict, List, Any
import pandas as pd
import re

class PrivacyAssistant:
    def __init__(self):
        # Dizionario di pattern per identificare tipi di dati sensibili
        self.patterns = {
            'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
            'phone': r'^\+?[\d\s-]{10,}$',
            'fiscal_code': r'^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$',
            'date': r'^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$',
            'address': r'\b\d+\s+[A-Za-z\s]+(?:street|st|avenue|ave|road|rd|boulevard|blvd)\b',
            'name': r'^[A-Z][a-z]+(?:\s[A-Z][a-z]+)*$'
        }
        
        # Categorie di dati sensibili per il GDPR
        self.gdpr_categories = {
            'direct_identifiers': ['name', 'email', 'phone', 'fiscal_code', 'id', 'codice', 'identifier'],
            'quasi_identifiers': ['date_of_birth', 'birth', 'age', 'età', 'zip', 'cap', 'address', 'indirizzo', 'gender', 'sesso'],
            'sensitive_attributes': ['health', 'salute', 'religion', 'religione', 'ethnicity', 'etnia', 
                                   'political', 'politico', 'sexual', 'sessuale', 'orientation', 'orientamento',
                                   'criminal', 'penale', 'medical', 'medico', 'disability', 'disabilità']
        }

    def analyze_column_content(self, column_data: pd.Series) -> Dict[str, float]:
        """Analizza il contenuto di una colonna per identificare il tipo di dati."""
        matches = {}
        sample_size = min(100, len(column_data))
        sample = column_data.dropna().head(sample_size).astype(str)
        
        for pattern_name, pattern in self.patterns.items():
            match_count = sum(1 for value in sample if re.match(pattern, str(value)))
            match_percentage = (match_count / sample_size) * 100 if sample_size > 0 else 0
            if match_percentage > 30:  # Soglia del 30% per considerare un match significativo
                matches[pattern_name] = match_percentage
                
        return matches

    def analyze_column_name(self, column_name: str) -> List[str]:
        """Analizza il nome della colonna per identificare potenziali dati sensibili."""
        column_name = column_name.lower()
        categories = []
        
        # Cerca corrispondenze nelle categorie GDPR
        for category, fields in self.gdpr_categories.items():
            if any(field in column_name for field in fields):
                categories.append(category)
                
        return categories

    def analyze_column_uniqueness(self, df: pd.DataFrame, column: str) -> float:
        """Calcola il tasso di unicità dei valori in una colonna."""
        total_rows = len(df)
        unique_values = df[column].nunique()
        return (unique_values / total_rows) * 100 if total_rows > 0 else 0

    def generate_suggestions(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Genera suggerimenti per l'anonimizzazione del dataset."""
        suggestions = {
            'columns_to_pseudonymize': [],
            'columns_to_remove': [],
            'columns_to_aggregate': [],
            'general_recommendations': []
        }
        
        # Analizza ogni colonna
        for column in df.columns:
            content_analysis = self.analyze_column_content(df[column])
            name_analysis = self.analyze_column_name(column)
            uniqueness_rate = self.analyze_column_uniqueness(df, column)
            
            # Analisi e suggerimenti
            if content_analysis or any(cat in ['direct_identifiers', 'sensitive_attributes'] for cat in name_analysis):
                if any(cat in ['direct_identifiers'] for cat in name_analysis) or content_analysis:
                    suggestions['columns_to_pseudonymize'].append({
                        'column': column,
                        'reason': f"Identificata come dato identificativo diretto" +
                                (f" (tipo rilevato: {', '.join(content_analysis.keys())})" if content_analysis else "")
                    })
                elif any(cat in ['sensitive_attributes'] for cat in name_analysis):
                    suggestions['columns_to_remove'].append({
                        'column': column,
                        'reason': "Contiene attributi sensibili secondo GDPR"
                    })
            
            # Suggerimenti per aggregazione
            if df[column].dtype in ['int64', 'float64']:
                if 'age' in column.lower() or 'età' in column.lower():
                    suggestions['columns_to_aggregate'].append({
                        'column': column,
                        'reason': "Considerare l'aggregazione in fasce d'età per ridurre la granularità"
                    })
                elif uniqueness_rate > 50:
                    suggestions['columns_to_aggregate'].append({
                        'column': column,
                        'reason': f"Alta unicità ({uniqueness_rate:.1f}%). Considerare l'aggregazione in intervalli"
                    })

        # Raccomandazioni generali
        if len(df) > 0:
            unique_combinations = df.groupby(list(df.columns)).size()
            unique_records = len(unique_combinations[unique_combinations == 1])
            risk_percentage = (unique_records / len(df)) * 100
            
            if risk_percentage > 20:
                suggestions['general_recommendations'].append(
                    f"⚠️ ATTENZIONE: Il {risk_percentage:.1f}% dei record sono univocamente identificabili. " +
                    "Considera l'applicazione di tecniche di generalizzazione dei dati."
                )
            
            if risk_percentage > 50:
                suggestions['general_recommendations'].append(
                    "🔴 RISCHIO ELEVATO: L'alto tasso di unicità suggerisce un rischio significativo " +
                    "di re-identificazione. Considera di applicare k-anonymity con k ≥ 5."
                )

        return suggestions

def format_suggestions_html(suggestions: Dict[str, Any]) -> str:
    """Formatta i suggerimenti in HTML per la visualizzazione."""
    html = '<div class="card mb-4"><div class="card-body">'
    html += '<h4 class="card-title mb-4">🤖 Suggerimenti IA per l\'Anonimizzazione</h4>'
    
    if suggestions['columns_to_pseudonymize']:
        html += '<div class="mb-4"><h5>📝 Colonne da Pseudonimizzare:</h5><ul class="list-group list-group-flush">'
        for item in suggestions['columns_to_pseudonymize']:
            html += f'<li class="list-group-item"><strong>{item["column"]}</strong>: {item["reason"]}</li>'
        html += '</ul></div>'
    
    if suggestions['columns_to_remove']:
        html += '<div class="mb-4"><h5>🗑️ Colonne da Rimuovere:</h5><ul class="list-group list-group-flush">'
        for item in suggestions['columns_to_remove']:
            html += f'<li class="list-group-item"><strong>{item["column"]}</strong>: {item["reason"]}</li>'
        html += '</ul></div>'
    
    if suggestions['columns_to_aggregate']:
        html += '<div class="mb-4"><h5>📊 Colonne da Aggregare:</h5><ul class="list-group list-group-flush">'
        for item in suggestions['columns_to_aggregate']:
            html += f'<li class="list-group-item"><strong>{item["column"]}</strong>: {item["reason"]}</li>'
        html += '</ul></div>'
    
    if suggestions['general_recommendations']:
        html += '<div class="mb-4"><h5>💡 Raccomandazioni Generali:</h5><ul class="list-group list-group-flush">'
        for rec in suggestions['general_recommendations']:
            html += f'<li class="list-group-item">{rec}</li>'
        html += '</ul></div>'
    
    html += '</div></div>'
    return html