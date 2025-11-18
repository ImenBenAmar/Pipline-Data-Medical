import os
import xml.etree.ElementTree as ET
import pandas as pd
import re

XML_FOLDER = "/opt/airflow/data/xml"
OUTPUT_CSV = "/opt/airflow/processed/xml_data.csv"

def xml_to_csv():
    data_list = []
    all_tags = set()

    if not os.path.exists(XML_FOLDER):
        print(f"Dossier XML introuvable : {XML_FOLDER}")
        return

    for filename in os.listdir(XML_FOLDER):
        if filename.endswith(".xml"):
            file_path = os.path.join(XML_FOLDER, filename)
            try:
                tree = ET.parse(file_path)
                root = tree.getroot()
                row_data = {child.tag: child.text.strip() if child.text else "" for child in root}
                row_data["source_file"] = filename
                data_list.append(row_data)
                all_tags.update(row_data.keys())
            except Exception as e:
                print(f"Erreur dans {filename} : {e}")

    df = pd.DataFrame(data_list)

    for tag in all_tags:
        if tag not in df.columns:
            df[tag] = None

    cols = ["source_file"] + [c for c in df.columns if c != "source_file"]
    df = df[cols]
    df = clean_dataframe(df)

    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    print(f"Export terminé : {OUTPUT_CSV}, {len(df)} lignes")

def clean_dataframe(df):
    threshold = 800
    cols_to_drop = df.columns[df.isna().sum() > threshold]
    df = df.drop(columns=cols_to_drop, errors="ignore")

    if "OOperation" in df.columns:
        df = df.drop("OOperation", axis=1)

    if "ACR" in df.columns:
        acr_split = df["ACR"].str.split(",", n=3, expand=True)
        acr_split.columns = [f"ACR{i+1}" for i in range(acr_split.shape[1])]
        acr_split = acr_split.apply(pd.to_numeric, errors="coerce")
        df = pd.concat([df.drop("ACR", axis=1), acr_split], axis=1)
        for i in range(1, 5):
            col = f"ACR{i}"
            if col not in df.columns:
                df[col] = 0
            else:
                df[col] = df[col].fillna(0)
    else:
        for i in range(1, 5):
            df[f"ACR{i}"] = 0

    textual_cols = ["Description","ClinicalPresentation","Commentary",
                    "Chapter","Hospital","Department","Language","Diagnosis","Title","WEBURL","ImageThumbnailID"]
    for col in textual_cols:
        if col not in df.columns:
            df[col] = "Non précisé"
        else:
            df[col] = df[col].fillna("Non précisé")

    numeric_cols = ["ODislocation","OPolytrauma","OOpen","OPathologic","OGraft","Age"]
    for col in numeric_cols:
        if col not in df.columns:
            df[col] = 0
        else:
            df[col] = df[col].fillna(0)

    for date_col in ["Date","Birthdate","Creation","DateTime","Order"]:
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce', dayfirst=True)
        else:
            df[date_col] = pd.NaT

    return df