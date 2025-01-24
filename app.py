from flask import Flask, render_template, request, jsonify, session
import os
import pandas as pd
import io
import hashlib
import json

app = Flask(__name__)
UPLOAD_FOLDER = 'datasets'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'super_secret_key'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def validate_csv(file):
    try:
        content = file.read().decode('utf-8')
        separators = [',', ';', '\t']
        for sep in separators:
            try:
                data = pd.read_csv(io.StringIO(content), sep=sep)
                if data.empty:
                    return None, "Il file è vuoto"
                if len(data.columns) < 2:
                    return None, "Il file deve contenere almeno due colonne"
                return data, None
            except:
                continue
        return None, "Formato file non valido"
    except Exception as e:
        return None, f"Errore: {str(e)}"

def pseudonymize_column(df, column_name):
    df[column_name] = df[column_name].astype(str).apply(
        lambda x: hashlib.sha256(x.encode()).hexdigest()[:16]
    )
    return df

def analyze_risk(df):
    if df.empty or len(df.columns) == 0:
        return {
            "total_records": 0,
            "unique_records": 0,
            "risk_score": 0.00
        }
        
    total_records = len(df)
    
    # Calcola quanti record sono univocamente identificabili
    unique_combinations = df.groupby(list(df.columns)).size()
    unique_records = len(unique_combinations[unique_combinations == 1])
    
    # Calcola il rischio come percentuale di record univocamente identificabili
    risk_score = (unique_records / total_records) * 100 if total_records > 0 else 0
    
    return {
        "total_records": total_records,
        "unique_records": unique_records,
        "risk_score": round(risk_score, 2)
    }

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        if "file" not in request.files:
            return render_template("index.html", error="Nessun file selezionato")
        
        file = request.files["file"]
        if file.filename == "":
            return render_template("index.html", error="Nessun file selezionato")
        
        if not file.filename.endswith('.csv'):
            return render_template("index.html", error="Per favore carica un file CSV")
        
        data, error = validate_csv(file)
        if error:
            return render_template("index.html", error=error)
        
        try:
            # Salva sia il DataFrame originale che quello modificabile
            session['original_df'] = data.to_json()
            session['current_df'] = data.to_json()
            session['pseudonymized_columns'] = json.dumps([])  # Tiene traccia delle colonne pseudonimizzate
            session['removed_columns'] = json.dumps([])  # Tiene traccia delle colonne rimosse
            
            preview = data.head(10).to_html(classes="table table-striped table-bordered", justify="left")
            risk_analysis = analyze_risk(data)
            
            return render_template("index.html", 
                                preview=preview,
                                columns=data.columns.tolist(),
                                risk_analysis=risk_analysis,
                                success=f"File caricato: {len(data)} righe, {len(data.columns)} colonne")
        except Exception as e:
            return render_template("index.html", error=f"Errore: {str(e)}")
    
    return render_template("index.html")

@app.route("/toggle_pseudonymize", methods=["POST"])
def toggle_pseudonymize():
    if 'original_df' not in session:
        return jsonify({"error": "Nessun dataset caricato"}), 400
    
    column = request.json.get("column")
    action = request.json.get("action")  # 'add' o 'remove'
    
    if not column:
        return jsonify({"error": "Colonna non specificata"}), 400
    
    try:
        # Recupera i DataFrame e le liste dalla sessione
        df = pd.read_json(session['current_df'])
        original_df = pd.read_json(session['original_df'])
        pseudonymized_columns = json.loads(session['pseudonymized_columns'])
        removed_columns = json.loads(session['removed_columns'])
        
        if action == 'add' and column not in pseudonymized_columns:
            df[column] = pseudonymize_column(df.copy(), column)[column]
            pseudonymized_columns.append(column)
        elif action == 'remove' and column in pseudonymized_columns:
            df[column] = original_df[column]
            pseudonymized_columns.remove(column)
        
        # Aggiorna la sessione
        session['current_df'] = df.to_json()
        session['pseudonymized_columns'] = json.dumps(pseudonymized_columns)
        
        preview = df.head(10).to_html(classes="table table-striped table-bordered", justify="left")
        risk_analysis = analyze_risk(df)
        
        return jsonify({
            "preview": preview,
            "risk_analysis": risk_analysis,
            "success": "Operazione completata"
        })
    except Exception as e:
        return jsonify({"error": f"Errore durante l'operazione: {str(e)}"}), 500

@app.route("/toggle_column", methods=["POST"])
def toggle_column():
    if 'original_df' not in session:
        return jsonify({"error": "Nessun dataset caricato"}), 400
    
    column = request.json.get("column")
    action = request.json.get("action")  # 'add' o 'remove'
    
    if not column:
        return jsonify({"error": "Colonna non specificata"}), 400
    
    try:
        # Recupera i DataFrame e le liste dalla sessione
        df = pd.read_json(session['current_df'])
        original_df = pd.read_json(session['original_df'])
        removed_columns = json.loads(session['removed_columns'])
        
        if action == 'add' and column not in removed_columns:
            df = df.drop(columns=[column])
            removed_columns.append(column)
        elif action == 'remove' and column in removed_columns:
            # Ripristina la colonna mantenendo l'ordine originale
            df = pd.concat([df, original_df[column]], axis=1)
            # Riordina le colonne come nel DataFrame originale
            df = df.reindex(columns=[col for col in original_df.columns if col in df.columns])
            removed_columns.remove(column)
        
        # Aggiorna la sessione
        session['current_df'] = df.to_json()
        session['removed_columns'] = json.dumps(removed_columns)
        
        preview = df.head(10).to_html(classes="table table-striped table-bordered", justify="left")
        risk_analysis = analyze_risk(df)
        
        return jsonify({
            "preview": preview,
            "risk_analysis": risk_analysis,
            "success": "Operazione completata"
        })
    except Exception as e:
        return jsonify({"error": f"Errore durante l'operazione: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)