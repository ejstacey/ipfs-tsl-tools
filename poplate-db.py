#!/bin/env python

import psycopg2
import pprint
import csv
from configparser import ConfigParser

pp = pprint.PrettyPrinter(indent=4)

def config(filename='database.ini', section='postgresql'):
    # create a parser
    parser = ConfigParser()
    # read config file
    parser.read(filename)

    # get section, default to postgresql
    db = {}
    if parser.has_section(section):
        params = parser.items(section)
        for param in params:
            db[param[0]] = param[1]
    else:
        raise Exception('Section {0} not found in the {1} file'.format(section, filename))

    return db

def get_connection():
    try:
        params = config()
        params.pop('table', None)

        # connect to the PostgreSQL server
        print('Connecting to the PostgreSQL database...')
        conn = psycopg2.connect(**params)
        # pp.pprint(params)
        return conn
    except:
        return False
    
cvsEntries = {}
with open('hash-list', mode ='r', encoding="utf-8") as file:
    csvFile = csv.reader(file, delimiter=':')

    # use the directory + file as a key 
    for lines in csvFile:
        entry = {
            'directory': lines[0],
            'filename': lines[1],
            'cid': lines[2]
        }
        cvsEntries[lines[0]+'/'+lines[1]] = entry


# pp.pprint(cvsEntries)

conn = get_connection()
cur = conn.cursor()

dbEntries = {}
sql = 'select * from "tsl-links".tsl'
cur.execute(sql)
rows=cur.fetchall()
for row in rows:
    entry = {
        'id': row[0],
        'cid': row[3],
        'directory': row[1],
        'filename': row[2]
    }

    dbEntries[row[1]+'/'+row[2]] = entry

# pp.pprint(dbEntries)
for name in cvsEntries:
    entry = cvsEntries[name]
    if entry['directory'] + '/' + entry['filename'] not in dbEntries:
        sql = 'insert into "tsl-links".tsl (directory, filename, cid) values (%s, %s, %s)'
        cur.execute(sql, (entry['directory'], entry['filename'], entry['cid']))
    else:
        if entry['cid'] != cvsEntries[entry['directory'] + '/' + entry['filename']]['cid']:
            sql = 'update "tsl-links".tsl set cid = %s where id = %s'
            cur.execute(sql, (entry['cid'], dbEntries[entry['directory'] + '/' + entry['filename']]['id']))

cur.close()
conn.commit()
conn.close()
