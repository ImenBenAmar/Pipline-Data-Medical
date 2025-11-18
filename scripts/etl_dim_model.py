import pandas as pd
import os

def run_dimensional_etl():
    source_path = "/opt/airflow/processed/xml_data.csv"
    output_folder = "/opt/airflow/processed"
    os.makedirs(output_folder, exist_ok=True)

    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Fichier source introuvable : {source_path}")

    df = pd.read_csv(source_path, sep=",", encoding="utf-8")
    df = df.fillna("Non précisé")

    # -------------------------
    # FORCER TOUTES LES COLONNES CLÉS EN STRING
    # -------------------------
    key_columns = [
        "Description", "ClinicalPresentation", "Birthdate", "Age",
        "Hospital", "Department", "Diagnosis", "Chapter",
        "source_file", "Title", "Language", "Commentary", "ImageThumbnailID",
        "WEBURL", "Date", "ACR1", "ACR2", "ACR3", "ACR4"
    ]
    for col in key_columns:
        if col in df.columns:
            df[col] = df[col].astype(str).replace({"nan": "Non précisé", "None": "Non précisé"})

    # -------------------------
    # MAPPING INVERSE GLOBAL (renommé → source)
    # -------------------------
    REVERSE_MAP = {
        "description_patient": "Description",
        "clinical_presentation": "ClinicalPresentation",
        "birthdate": "Birthdate",
        "age": "Age",
        "hospital": "Hospital",
        "department": "Department",
        "diagnosis": "Diagnosis",
        "chapter": "Chapter",
        "weburl": "WEBURL",
        "date_event": "Date",
        "source_file": "source_file",
        "title": "Title",
        "language": "Language",
        "commentary": "Commentary",
        "image_thumbnail_id": "ImageThumbnailID"
    }

    # -------------------------
    # UTILS
    # -------------------------
    def build_dim(df, src_cols, dim_id_name, rename_map):
        for col in src_cols:
            if col not in df.columns:
                df[col] = "Non précisé"
        dim = df[src_cols].drop_duplicates().reset_index(drop=True)
        dim = dim.rename(columns=rename_map)
        for col in dim.columns:
            if col != dim_id_name:
                dim[col] = dim[col].astype(str)
        dim[dim_id_name] = range(1, len(dim) + 1)
        return dim

    def map_keys(df_source, dim, src_cols, dim_id_name):
        dim_temp = dim.copy()
        
        # Renommer temporairement les colonnes de dim pour matcher les colonnes source
        rename_back = {v: k for k, v in REVERSE_MAP.items() if v in dim_temp.columns}
        dim_temp = dim_temp.rename(columns=rename_back)
        
        # S'assurer que les colonnes source existent
        for col in src_cols:
            if col not in df_source.columns:
                df_source[col] = "Non précisé"
            if col not in dim_temp.columns:
                dim_temp[col] = "Non précisé"
            df_source[col] = df_source[col].astype(str)
            dim_temp[col] = dim_temp[col].astype(str)
        
        # Merge
        merged = df_source.merge(dim_temp[src_cols + [dim_id_name]], on=src_cols, how="left")
        
        # CORRECTION FINALE :
        # 1. Remplacer NaN par pd.NA → NULL en DB
        # 2. Forcer les valeurs non-nulles en INT → évite 1.0
        result = merged[dim_id_name].fillna(pd.NA)
        # Convertir en Int64 (gère NaN) puis en int pour les non-null
        result = result.astype('Int64')  # Int64 = pandas nullable int
        return result

    # -------------------------
    # DIMENSIONS
    # -------------------------

    # DIM PATIENT
    patient_src_cols = ["Description", "ClinicalPresentation", "Birthdate", "Age"]
    dim_patient = build_dim(df, patient_src_cols, "id_patient", {
        "Description": "description_patient",
        "ClinicalPresentation": "clinical_presentation",
        "Birthdate": "birthdate",
        "Age": "age"
    })

    # DIM HOSPITAL
    hospital_src_cols = ["Hospital", "Department"]
    dim_hospital = build_dim(df, hospital_src_cols, "id_hospital", {
        "Hospital": "hospital", "Department": "department"
    })

    # DIM DIAGNOSIS
    diagnosis_src_cols = ["Diagnosis"]
    dim_diagnosis = build_dim(df, diagnosis_src_cols, "id_diagnosis", {"Diagnosis": "diagnosis"})

    # DIM CHAPTER
    chapter_src_cols = ["Chapter"]
    dim_chapter = build_dim(df, chapter_src_cols, "id_chapter", {"Chapter": "chapter"})

    # DIM WEB
    web_src_cols = ["WEBURL"]
    dim_web = build_dim(df, web_src_cols, "id_web", {"WEBURL": "weburl"})

    # DIM DATE
    date_src_cols = ["Date"]
    dim_date = build_dim(df, date_src_cols, "id_date", {"Date": "date_event"})

    # DIM ACR
    acr_src_cols = ["ACR1", "ACR2", "ACR3", "ACR4"]
    dim_acr = build_dim(df, acr_src_cols, "id_acr", {})

    # DIM DOCUMENT
    doc_src_cols = ["source_file", "Title", "Language", "Commentary", "ImageThumbnailID"]
    dim_document = build_dim(df, doc_src_cols, "id_document", {
        "source_file": "source_file",
        "Title": "title",
        "Language": "language",
        "Commentary": "commentary",
        "ImageThumbnailID": "image_thumbnail_id"
    })

    # -------------------------
    # FACT TABLE
    # -------------------------
    fact = pd.DataFrame()

    fact["id_patient"]   = map_keys(df, dim_patient, patient_src_cols, "id_patient")
    fact["id_hospital"]  = map_keys(df, dim_hospital, hospital_src_cols, "id_hospital")
    fact["id_diagnosis"] = map_keys(df, dim_diagnosis, diagnosis_src_cols, "id_diagnosis")
    fact["id_chapter"]   = map_keys(df, dim_chapter, chapter_src_cols, "id_chapter")
    fact["id_document"]  = map_keys(df, dim_document, doc_src_cols, "id_document")
    fact["id_web"]       = map_keys(df, dim_web, web_src_cols, "id_web")
    fact["id_acr"]       = map_keys(df, dim_acr, acr_src_cols, "id_acr")
    fact["id_date"]      = map_keys(df, dim_date, date_src_cols, "id_date")
    # Métriques (forcer en INT pour PostgreSQL)
    metrics = ["ODislocation", "OPolytrauma", "OOpen", "OPathologic", "OGraft", "Order"]
    for col in metrics:
        target_col = col.lower() if col != "Order" else "order_num"
        if col in df.columns:
            # Convertir en numérique, remplacer NaN par 0, puis forcer en INT
            fact[target_col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        else:
            fact[target_col] = 0

    # Dates et heures
    fact["creation"] = (
        pd.to_datetime(df["Creation"], errors="coerce").dt.date 
        if "Creation" in df.columns else None
    )

    fact["date_time"] = (
        pd.to_datetime(df["DateTime"], errors="coerce").dt.time 
        if "DateTime" in df.columns else None
    )

    # ID fact (à supprimer avant export)
    fact["id_fact"] = range(1, len(fact) + 1)

    # -------------------------
    # EXPORT SANS ID
    # -------------------------
# -------------------------
# EXPORT SANS ID + CORRECTIONS
# -------------------------

    # Fonction utilitaire
    def export_dim(dim, id_col, path):
        dim.drop(columns=[id_col]).to_csv(path, index=False)

    # --- dim_document : image_thumbnail_id → INT ou NULL ---
    dim_doc_export = dim_document.drop(columns=["id_document"]).copy()
    dim_doc_export["image_thumbnail_id"] = pd.to_numeric(
        dim_doc_export["image_thumbnail_id"], errors="coerce"
    ).astype("Int64")  # Int64 gère NaN → NULL en DB
    dim_doc_export.to_csv(f"{output_folder}/dim_document.csv", index=False)

    # --- fact_consultation : supprimer id_fact ---
    fact_export = fact.drop(columns=["id_fact"])
    fact_export.to_csv(f"{output_folder}/fact_consultation.csv", index=False)

    # --- Autres dimensions ---
    export_dim(dim_acr, "id_acr", f"{output_folder}/dim_acr.csv")
    export_dim(dim_chapter, "id_chapter", f"{output_folder}/dim_chapter.csv")
    export_dim(dim_date, "id_date", f"{output_folder}/dim_date.csv")
    export_dim(dim_diagnosis, "id_diagnosis", f"{output_folder}/dim_diagnosis.csv")
    export_dim(dim_hospital, "id_hospital", f"{output_folder}/dim_hospital.csv")
    export_dim(dim_patient, "id_patient", f"{output_folder}/dim_patient.csv")
    export_dim(dim_web, "id_web", f"{output_folder}/dim_web.csv")

    print("ETL dimensionnel terminé avec succès")

        