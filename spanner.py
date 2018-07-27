import glob
import os
import argparse
import re

from google.cloud import spanner
from subprocess import call

import pandas as pd
import numpy as np

green = 2
yellow = 1
year_month_regex = "tripdata_([0-9]{4})-([0-9]{2})"


def set_credentials(path_to_json_file):
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = path_to_json_file


def run(args):
    spanner_client = spanner.Client()
    instance = spanner_client.instance(args.instance_id)

    create_database(instance=instance, database_name=args.database_name)
    insert_cab_type(instance=instance, database_id=args.database_id)
    insert_trips(instance=instance, database_id=args.database_id, data_source=args.source)


def create_instance(args):
    create_instance_command = 'gcloud spanner instances create {0} --config={1} --description={2} --nodes={3}'.format(
        args.instance_id, args.instance_config, args.instance_description, args.number_of_nodes)
    call(create_instance_command)


def create_database(instance, database_name):
    database = instance.database(database_name, ddl_statements=[
        """CREATE TABLE cab_types (
            cab_type_id INT64 NOT NULL,
            cab_type    STRING(1024)
            ) PRIMARY KEY (cab_type_id)
        """,
        """
            CREATE TABLE trips (
              trip_id INT64 NOT NULL,
              cab_type_id INT64 NOT NULL,
              passenger_count INT64,
              pickup_datetime timestamp,
              dropoff_datetime timestamp,
              pickup_longitude FLOAT64,
              pickup_latitude FLOAT64,
              dropoff_longitude FLOAT64,
              dropoff_latitude FLOAT64,
              trip_distance FLOAT64,
              fare_amount FLOAT64,
              total_amount FLOAT64
            )PRIMARY KEY (trip_id, cab_type_id),
            INTERLEAVE IN PARENT cab_types
        """
    ])

    operation = database.create()
    print('Waiting for operation to complete...')
    operation.result()


def insert_cab_type(instance, database_id):
    database = instance.database(database_id)
    with database.batch() as batch:
        batch.insert(
            table='cab_types',
            columns=('cab_type', 'cab_type',),
            values=[
                (green, u'green'),
                (yellow, u'yellow')
            ])
    print('Inserted cab types.')


def insert_trips(instance, database_id, data_source):
    os.chdir(data_source)
    df = None
    cab_type = green
    for file in glob.glob("*.csv"):
        year, month = get_year_month(file)
        schema = None
        if "green" in file:
            if year == 2015 and month < 7:
                schema = green_schema_2015_h1
            else:
                schema = green_schema_2015_h2_2016_h1
        elif "yellow" in file:
            cab_type = yellow
            schema = yellow_schema_2015_2016_h1
        df = load_data(file, schema, cab_type)

    values = []
    for index, row in df.iterrows():
        values.append((
            index, row['cab_type_id'], row['passenger_count'], row['pickup_datetime'], row['dropoff_datetime'],
            row['pickup_longitude'], row['pickup_latitude'], row['dropoff_longitude'], row['dropoff_latitude'],
            row['trip_distance'], row['fare_amount'], row['total_amount']
        ))

    database = instance.database(database_id)
    with database.batch() as batch:
        batch.insert(
            table='trips',
            columns=(
                'trip_id', 'cab_type_id', 'passenger_count', 'pickup_datetime', 'dropoff_datetime', 'pickup_longitude',
                'pickup_latitude', 'dropoff_longitude', 'dropoff_latitude', 'trip_distance', 'fare_amount',
                'total_amount'
            ),
            values=values)


def load_data(file, schema, cab_type):
    df = pd.read_csv(file, names=schema)
    df = df.iloc[1:]
    df = rename_columns(df, cab_type=cab_type)
    df = df.fillna(0.0)
    return df


def rename_columns(df, cab_type=2):
    df['cab_type_id'] = cab_type
    df = add_non_existing_columns(df)
    df = df.rename(columns={'lpep_pickup_datetime': 'pickup_datetime', 'lpep_dropoff_datetime': 'dropoff_datetime',
                            'tpep_pickup_datetime': 'pickup_datetime', 'tpep_dropoff_datetime': 'dropoff_datetime'})
    return df[
        ['cab_type_id', 'passenger_count', 'pickup_datetime', 'dropoff_datetime', 'pickup_longitude', 'pickup_latitude',
         'dropoff_longitude', 'dropoff_latitude', 'trip_distance', 'fare_amount', 'total_amount']]


def add_non_existing_columns(df):
    if 'pickup_longitude' not in df:
        df["pickup_longitude"] = np.nan
    if 'pickup_latitude' not in df:
        df["pickup_latitude"] = np.nan
    if 'pickup_longitude' not in df:
        df["pickup_longitude"] = np.nan
    if 'dropoff_longitude' not in df:
        df["dropoff_longitude"] = np.nan
    if 'dropoff_latitude' not in df:
        df["dropoff_latitude"] = np.nan
    return df


def get_year_month(file):
    match = re.findall(year_month_regex, file)
    year = int(match[0][0])
    month = int(match[0][1])
    return year, month


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Google Cloud Spanner script for the DB Seminar HSR, Fall 2018',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-c', '--credentials', dest='credentials', help='Path to the JSON credential file')
    parser.add_argument('-i', '--instance_id', dest='instance_id', help='Instance ID')
    parser.add_argument('-r', '--region', dest='region', help='Instance deployment region')
    parser.add_argument('-n', '--nodes', dest='region', help='Number of nodes')
    parser.add_argument('-d', '--description', dest='region', help='Instance description')
    parser.add_argument('-db', '--database_name', dest='region', help='Database name')
    parser.add_argument('-s', '--source', dest='source', help='Data directory')

    current_directory = os.path.realpath(os.path.dirname(__file__))
    parser.set_defaults(credentials='credentials.json', instance_id='paris-instance', region='regional-europe-west1',
                        nodes=1, description='db_seminar', database_name='your', source=current_directory + "/data/")
    args = parser.parse_args()
    set_credentials(args.credentials)

    run(args)

yellow_schema_2015_2016_h1 = ['vendor_id', 'tpep_pickup_datetime', 'tpep_dropoff_datetime', 'passenger_count',
                              'trip_distance', 'pickup_longitude', 'pickup_latitude', 'rate_code_id',
                              'store_and_fwd_flag', 'dropoff_longitude', 'dropoff_latitude', 'payment_type',
                              'fare_amount', 'extra', 'mta_tax', 'tip_amount', 'tolls_amount', 'improvement_surcharge',
                              'total_amount']

green_schema_2015_h1 = ['vendor_id', 'lpep_pickup_datetime', 'lpep_dropoff_datetime', 'store_and_fwd_flag',
                        'rate_code_id', 'pickup_longitude', 'pickup_latitude', 'dropoff_longitude', 'dropoff_latitude',
                        'passenger_count', 'trip_distance', 'fare_amount', 'extra', 'mta_tax,tip_amount',
                        'tolls_amount,ehail_fee', 'improvement_surcharge', 'total_amount', 'payment_type', 'trip_type',
                        'junk1', 'junk2']

green_schema_2015_h2_2016_h1 = ['vendor_id', 'lpep_pickup_datetime', 'lpep_dropoff_datetime', 'store_and_fwd_flag',
                                'rate_code_id', 'pickup_longitude', 'pickup_latitude', 'dropoff_longitude',
                                'dropoff_latitude', 'passenger_count', 'trip_distance', 'fare_amount', 'extra,mta_tax',
                                'tip_amount', 'tolls_amount', 'ehail_fee', 'improvement_surcharge', 'total_amount',
                                'payment_type', 'trip_type']
