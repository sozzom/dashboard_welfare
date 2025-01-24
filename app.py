from flask import Flask, render_template, request, jsonify, session, Response
import os
import pandas as pd
import io
import hashlib
import json
from datetime import timedelta


app = Flask(__name__)
UPLOAD_FOLDER = 'datasets'
app.config.update(
    UPLOAD_FOLDER=UPLOAD_FOLDER,
    SECRET_KEY='super_secret_key',  # In produzione, usa una chiave sicura
    SESSION_COOKIE_SECURE=True,      # Solo HTTPS
    SESSION_COOKIE_HTTPONLY=True,    # Previene accesso JS
    SESSION_COOKIE_SAMESITE='Lax',   # Protezione CSRF
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30)
)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def validate_csv(file):
    try:
        content = file.read()
        if len(content) > 10 * 1024 * 1024:  # 10MB limit
            return None, "File troppo grande (max 10MB)"
            
        content_str = content.decode('utf-8')
        if any(suspicious in content_str.lower() for suspicious in ['<script', 'javascript:', 'data:']):
            return None, "Contenuto non valido"

        separators = [',', ';', '\t']
        for sep in separators:
            try:
                data = pd.read_csv(io.StringIO(content_str), sep=sep)
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

@app.before_request
def before_request():
    session.permanent = True  # Abilita scadenza sessione

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
        # Verifica consenso privacy
        if not request.form.get('privacy_consent'):
            return render_template("index.html", error="È necessario accettare l'informativa privacy")
            
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
            # Salva DataFrame in sessione
            session['original_df'] = data.to_json()
            session['current_df'] = data.to_json()
            session['pseudonymized_columns'] = json.dumps([])
            session['removed_columns'] = json.dumps([])
            
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

@app.route("/download_csv", methods=["GET"])
def download_csv():
    if 'current_df' not in session:
        return jsonify({"error": "Nessun dataset disponibile"}), 400
        
    try:
        df = pd.read_json(session['current_df'])
        output = io.StringIO()
        df.to_csv(output, index=False)
        
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=dataset_modificato.csv"}
        )
    except Exception as e:
        return jsonify({"error": f"Errore durante il download: {str(e)}"}), 500


@app.route("/privacy", methods=["GET"])
def privacy():
    return render_template("privacy.html")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)