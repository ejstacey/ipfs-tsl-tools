#!/bin/env python

import psycopg2
import csv
import pprint
from configparser import ConfigParser
import urllib.parse

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
    
# cvsEntries = {}
# with open('hash-list', mode ='r', encoding="utf-8") as file:
#     csvFile = csv.reader(file, delimiter=':')

#     # use the directory + file as a key 
#     for lines in csvFile:
#         entry = {
#             'directory': lines[0],
#             'filename': lines[1],
#             'cid': lines[2]
#         }
#         cvsEntries[lines[0]+'/'+lines[1]] = entry


# pp.pprint(cvsEntries)

def recurse_path(dirs, temp, entry):
    for path in dirs:
        if path not in temp:
            temp[path] = {}
        dirs.pop(0)
        # pp.pprint(dirs)
        if len(dirs) <= 0:
            temp[path][entry['filename']] = entry
        else:
            temp[path] = recurse_path(dirs, temp[path], entry)

    return temp    

def generate_html(html, node):
    for i in node:
        entry = node[i]

        # pp.pprint(entry)
        if 'cid' in entry:
            # actual entry
            html += '<li><a href="https://ipfs.joyrex.net/ipfs/' + entry['cid'] + '?filename=' + urllib.parse.quote(entry['filename']) + '" target="_blank">' + entry['filename'] + '</a></li>'
            html += "\n"
        else:
            html += '<li><span class="rootTree">' + i + '/</span>'
            html += "\n"
            html += '<ul class="children">'
            html += "\n"
            html = generate_html(html, entry)
            html += '</ul></li>'

    return html
                        

params = config()
conn = get_connection()
cur = conn.cursor()

dbEntries = {}
sql = 'select * from ' + params['table']
cur.execute(sql)
rows=cur.fetchall()
for row in rows:
    entry = {
        'id': row[0],
        'cid': row[3],
        'directory': row[1],
        'filename': row[2]
    }

    dirs = row[1].split('/')
    dbEntries = recurse_path(dirs, dbEntries, entry)

cur.close()
conn.commit()
conn.close()

dbEntries = dict(sorted(dbEntries.items()))
# pp.pprint(dbEntries)

html = '''
<!-- stolen from https://www.tutorialspoint.com/how-to-create-a-tree-view-with-css-and-javascript -->
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link rel="stylesheet" href="treeview.css">
</head>
<body>
<h1>TSL</h1>
<ul id="treeUL">
'''

html = generate_html(html, dbEntries)

html += '''                    
</ul>
<script>
   debugger;
   console.log('wow');
   var toggler = document.querySelectorAll(".rootTree");
   Array.from(toggler).forEach(item => {
      item.addEventListener("click", () => {
         item.parentElement .querySelector(".children") .classList.toggle("active");
         item.classList.toggle("rootTree-down");
      });
   });
</script>
'''

file = open('list.html', 'w+')
file.writelines(html)