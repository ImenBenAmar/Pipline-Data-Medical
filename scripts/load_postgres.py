import os
from airflow.providers.postgres.hooks.postgres import PostgresHook

PROCESSED_FOLDER = "/opt/airflow/processed"

def copy_csv_to_postgres(table_name, csv_path=None, conn_id="postgres_default"):
    """
    Charge un CSV dans PostgreSQL via COPY avec gestion des sauts de ligne, guillemets, etc.
    Utilise cursor.copy_expert() pour éviter le bug de PostgresHook.copy_expert().
    """
    if csv_path is None:
        csv_path = os.path.join(PROCESSED_FOLDER, f"{table_name}.csv")
    
    # Vérifier que le fichier existe
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV introuvable : {csv_path}")

    # Mapping des colonnes (SANS les SERIAL id_*)
    column_mapping = {
        "dim_patient": ["description_patient", "clinical_presentation", "birthdate", "age"],
        "dim_hospital": ["hospital", "department"],
        "dim_diagnosis": ["diagnosis"],
        "dim_chapter": ["chapter"],
        "dim_web": ["weburl"],
        "dim_acr": ["acr1", "acr2", "acr3", "acr4"],
        "dim_document": ["source_file", "title", "language", "commentary", "image_thumbnail_id"],
        "dim_date": ["date_event"],
        "fact_consultation": [
            "id_patient", "id_hospital", "id_diagnosis", "id_chapter",
            "id_document", "id_web", "id_acr", "id_date",
            "odislocation", "opolytrauma", "oopen", "opathologic", "ograft",
            "order_num", "creation", "date_time"
        ]
    }

    columns = column_mapping.get(table_name)
    if not columns:
        raise ValueError(f"Table {table_name} non supportée")

    columns_str = ", ".join(columns)
    copy_sql = f"""
    COPY {table_name} ({columns_str})
    FROM STDIN WITH CSV HEADER DELIMITER ',' NULL '' QUOTE '"' ESCAPE '"' ENCODING 'UTF8'
    """

    # --- CONTOURNEMENT DU BUG : utiliser cursor.copy_expert() ---
    hook = PostgresHook(postgres_conn_id=conn_id)
    conn = hook.get_conn()
    cursor = conn.cursor()

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            cursor.copy_expert(copy_sql, f)
        conn.commit()
        print(f"Chargement réussi : {table_name} ← {csv_path}")
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Échec du COPY pour {table_name} : {e}")
    finally:
        cursor.close()
        conn.close()