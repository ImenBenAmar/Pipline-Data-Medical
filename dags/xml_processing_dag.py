import sys
sys.path.append('/opt/airflow/scripts')
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from datetime import datetime

from xml_to_csv import xml_to_csv
from etl_dim_model import run_dimensional_etl
from load_postgres import copy_csv_to_postgres

with DAG(
    dag_id="xml_processing_pipeline",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@once",
    catchup=False,
    tags=["etl", "xml", "dimensionnel"]
) as dag:

    convert_task = PythonOperator(task_id="convert_xml_to_csv", python_callable=xml_to_csv)
    etl_task = PythonOperator(task_id="dimensional_etl", python_callable=run_dimensional_etl)

    create_tables = PostgresOperator(
        task_id="create_tables",
        postgres_conn_id="postgres_default",
        sql="""
        DROP TABLE IF EXISTS fact_consultation CASCADE;
        DROP TABLE IF EXISTS dim_patient, dim_hospital, dim_diagnosis, dim_chapter,
               dim_web, dim_acr, dim_document, dim_date CASCADE;

        CREATE TABLE dim_patient (
            id_patient SERIAL PRIMARY KEY,
            description_patient TEXT,
            clinical_presentation TEXT,
            birthdate DATE,
            age INT
        );
        CREATE TABLE dim_hospital (
            id_hospital SERIAL PRIMARY KEY,
            hospital TEXT,
            department TEXT
        );
        CREATE TABLE dim_diagnosis (
            id_diagnosis SERIAL PRIMARY KEY,
            diagnosis TEXT
        );
        CREATE TABLE dim_chapter (
            id_chapter SERIAL PRIMARY KEY,
            chapter TEXT
        );
        CREATE TABLE dim_web (
            id_web SERIAL PRIMARY KEY,
            weburl TEXT
        );
        CREATE TABLE dim_acr (
            id_acr SERIAL PRIMARY KEY,
            acr1 NUMERIC,
            acr2 NUMERIC,
            acr3 NUMERIC,
            acr4 NUMERIC
        );
        CREATE TABLE dim_document (
            id_document SERIAL PRIMARY KEY,
            source_file TEXT,
            title TEXT,
            language TEXT,
            commentary TEXT,
            image_thumbnail_id INT
        );
        CREATE TABLE dim_date (
            id_date SERIAL PRIMARY KEY,
            date_event DATE
        );
        CREATE TABLE fact_consultation (
            id_fact SERIAL PRIMARY KEY,
            id_patient INT REFERENCES dim_patient(id_patient),
            id_hospital INT REFERENCES dim_hospital(id_hospital),
            id_diagnosis INT REFERENCES dim_diagnosis(id_diagnosis),
            id_chapter INT REFERENCES dim_chapter(id_chapter),
            id_document INT REFERENCES dim_document(id_document),
            id_web INT REFERENCES dim_web(id_web),
            id_acr INT REFERENCES dim_acr(id_acr),
            id_date INT REFERENCES dim_date(id_date),
            odislocation INT,
            opolytrauma INT,
            oopen INT,
            opathologic INT,
            ograft INT,
            order_num INT,
            creation DATE,
            date_time TIME
        );
        """
    )

    tables = [
        "dim_patient", "dim_hospital", "dim_diagnosis", "dim_chapter",
        "dim_web", "dim_acr", "dim_document", "dim_date", "fact_consultation"
    ]

    copy_tasks = [
        PythonOperator(
            task_id=f"copy_{t}_to_postgres",
            python_callable=copy_csv_to_postgres,
            op_kwargs={"table_name": t}
        ) for t in tables
    ]

    convert_task >> etl_task >> create_tables >> copy_tasks