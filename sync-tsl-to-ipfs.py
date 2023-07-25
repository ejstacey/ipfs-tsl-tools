#!/bin/env python3

import pprint
import json
import requests
import os
from requests_toolbelt.utils import dump
from requests_toolbelt.multipart.encoder import MultipartEncoder
import argparse
import configparser
from requests.exceptions import HTTPError
from pathlib import Path

pp = pprint.PrettyPrinter(indent=4)

if os.name == 'nt':
    DIRECTORY_SEPARATOR='\\'
else:
    DIRECTORY_SEPARATOR='/'

###### See if a different config file is specified
parser = argparse.ArgumentParser(
    prog='sync-tsl-to-ipfs',
    description='This program tries to make sure the local directory matches what the IPFS thinks is correct. It adds/removes files to the IPFS directory as necessary.'
)

parser.add_argument('--config', '-c',
                    action='store',
                    default='settings.cfg',
                    help='configuration filename (default: settings.cfg)'
)
args = parser.parse_args()

###### Settings load
config = configparser.RawConfigParser()
config.read(args.config)

settings = {}
settings['remote'] = dict(config.items('remote'))
settings['options'] = dict(config.items('options'))
settings['local'] = dict(config.items('local'))

def grabCurrentIpfs(settings, directory='/'):
    ipfsDb = {}

    url = "http://" + settings['remote']['ipfsserver'] + ":" + settings['remote']['ipfsport'] + "/api/v0/files/ls"
    args = {
        'arg'   : directory,
        'long'  : True
    }
    r = requests.post(url, params=args)
    result = r.json()
    # pp.pprint(result)
    if "Entries" in result:
        if result["Entries"] is not None:
            entries = result['Entries']
            for entry in entries:
                if entry['Type'] == 0:
                    # file, grab its info.. but we want it to be in the proper structure of the db
                    entry['Path'] = directory
                    ipfsDb[entry['Name']] = entry
                elif entry['Type'] == 1:
                    # directory, go deeper
                    newDirectory = directory + entry['Name'] + '/'
                    # print("going in " + newDirectory)
                    # quit()
                    tmpData = grabCurrentIpfs(settings, newDirectory)
                    ipfsDb[entry['Name'] + '/'] = tmpData
                else:
                    pp.pprint(entry)
                    raise Exception('Unknown IPFS type: ' + entry['Type'])

    return ipfsDb

def grabCurrentTsl(settings, directory):
    tslDb = {}

    dir = Path(directory)
    for path in dir.iterdir():
        # ignore anything starting with a /. in the path (file or directory starting with .)
        if DIRECTORY_SEPARATOR +  '.' in str(path):
            continue

        if (path.is_file()):
            stats = path.stat()
            mfsPath = str(path).replace(settings['local']['tsldirectory'], settings['remote']['mfsrootdirectory']).replace('\\', '/')
            fileEntry = {
                'name'          : path.name,
                'size'          : stats.st_size,
                'remotePath'    : str(path).replace(settings['local']['tsldirectory'], settings['remote']['tsldirectory']),
                'mfsPath'       : mfsPath,
                'localPath'     : str(path)
            }
            tslDb[path.name] = fileEntry
        elif (path.is_dir()):
            # directory, go deeper
            newDirectory = str(path)
            tempDir = str(path).split(DIRECTORY_SEPARATOR).pop() + '/'
            tslDb[tempDir] = grabCurrentTsl(settings, newDirectory)
        else:
            raise Exception("Not recognised as a file or a directory: " + str(path))

    # pp.pprint(tslDb)
    return tslDb

def verifyIpfsLibrary(settings):
    url = "http://" + settings['remote']['ipfsserver'] + ":" + str(settings['remote']['ipfsport']) + "/api/v0/filestore/verify"
    r = requests.post(url)
    print(r.json())    

def parsePaths(settings, path, ipfsDb, tslDb, fullPath=""):
    fullPath += path
    for path in ipfsDb:
        if path not in tslDb:
            # everything in this path needs to be removed from ipfs
            # print("remove: " + fullPath + path)
            if 'Name' not in ipfsDb[path]:
                # this is a directory, make the entry a bit different
                entry = {
                    'Path': '/' + fullPath.replace('\\', '/'),
                    'Name': path
                }
            else:
                # this is a file, we can use the entry
                entry = ipfsDb[path].replace('\\', '/')

            removeEntry(settings, entry)
        else:
            # compare the entries.
            if path.replace('\\', '/').endswith('/'):
                # we have a deeper path, check it
                parsePaths(settings, path, ipfsDb[path], tslDb[path], fullPath)
            else:
                if ipfsDb[path]['Size'] != tslDb[path]['size']:
                    removeEntry(settings, ipfsDb[path])
                    addEntry(settings, tslDb[path])

    for path in tslDb:
        if path not in ipfsDb:
            # everything in this path needs to be added to ipfs
            # print("add: " + fullPath + path)
            if path.endswith('/'):
                # we have a deeper path, first create the directory on the MFS
                # print("creating directory: " + fullPath + path)
                addDirectory(settings, ('/' + fullPath + path).replace('\\', '/'))
                # now parse that path.
                parsePaths(settings, path, {}, tslDb[path], fullPath)
            else:
                addEntry(settings, tslDb[path])

def removeEntry(settings, entry):
    url = "http://" + settings['remote']['ipfsserver'] + ":" + settings['remote']['ipfsport'] + "/api/v0/files/rm"

    args = {
        'arg'           : entry['Path'] + entry['Name'],
        'recursive'     : True
    }

    args['arg'] = args['arg'].replace('\\', '/'),

    print('Removing ' + entry['Path'] + entry['Name'])

    r = requests.post(url, params=args)
    r.raise_for_status()
    if (r.text == '' or 'file does not exist' in r.text):
        return
    else:
        raise Exception("Could not properly parse the return from a removal attempt of " + entry['Path'] + entry['Name'] + ":\n" + r.text)

def addEntry(settings, entry):
    url = "http://" + settings['remote']['ipfsserver'] + ":" + settings['remote']['ipfsport'] + "/api/v0/add"
    args = {
        'quieter'       : 'true',
        'nocopy'        : 'true',
        'to-files'      : DIRECTORY_SEPARATOR + entry['mfsPath']
    }

    args['to-files'] = args['to-files'].replace('\\', '/'),

    fileHeaders = {
        'Abspath': entry['remotePath']
    }

    data = MultipartEncoder(
        fields= {
            'part1': (entry['name'], open(entry['localPath'], 'rb'), 'application/octent-stream', fileHeaders)}
    )
    
    headers = {
        'Content-Type': data.content_type
    }

    
    print('Adding ' + entry['mfsPath'])
    try:
        r = requests.post(url, data=data, params=args, headers=headers)

        # data = dump.dump_all (r)
        # print (data.decode ('utf-8'))

        # If the response was successful, no Exception will be raised
        r.raise_for_status()
    except HTTPError as http_err:
        if (r.status_code == 500):
            err = r.json()
            http_err = err['Message']
        raise Exception(f'HTTP error occurred: {http_err}')
    except Exception as err:
        raise Exception(f'Other error occurred: {err}')
    else:
        result = r.json()
        if ('Name' in result):
            return
        else:
            raise Exception("Could not properly parse the return from an addition attempt of " + entry['mfsPath'] + ".\n" + r.content())

def addDirectory(settings, dir):
    url = "http://" + settings['remote']['ipfsserver'] + ":" + settings['remote']['ipfsport'] + "/api/v0/files/mkdir"
    args = {
        'parents'   : 'true',
        'arg'       : dir
    }

    args['arg'] = args['arg'].replace('\\', '/'),
    
    print('Creating ' + dir)
    try:
        r = requests.post(url,params=args)

        # data = dump.dump_all (r)
        # print (data.decode ('utf-8'))

        # If the response was successful, no Exception will be raised
        r.raise_for_status()
    except HTTPError as http_err:
        if (r.status_code == 500):
            err = r.json()
            http_err = err['Message']
        raise Exception(f'HTTP error occurred: {http_err}')
    except Exception as err:
        raise Exception(f'Other error occurred: {err}')

def findKey(settings, keyName):
    url = "http://" + settings['remote']['ipfsserver'] + ":" + settings['remote']['ipfsport'] + "/api/v0/key/list"
    args = {
        'l'   : 'true',
    }
    
    print('Listing current keys, looking for "' + keyName + '".')
    try:
        r = requests.post(url,params=args)

        # data = dump.dump_all (r)
        # print (data.decode ('utf-8'))

        # If the response was successful, no Exception will be raised
        r.raise_for_status()
    except HTTPError as http_err:
        if (r.status_code == 500):
            err = r.json()
            http_err = err['Message']
        raise Exception(f'HTTP error occurred: {http_err}')
    except Exception as err:
        raise Exception(f'Other error occurred: {err}')
    else:
        results = r.json()
        if 'Keys' not in results:
            pp.pprint(results)
            raise Exception(f'Could not load key list')
        
        key = None
        for keyEntry in results['Keys']:
            if keyEntry['Name'] == keyName:
                key = keyEntry['Name']
                break
        
        if key is None:
            # key doesn't exist, create it
            print("Key " + keyName + " not found.")
            key = addKey(settings, keyName)

    return key
 
def addKey(settings, keyName):
    url = "http://" + settings['remote']['ipfsserver'] + ":" + settings['remote']['ipfsport'] + "/api/v0/key/gen"
    args = {
        'arg'   : keyName,
    }
    
    print('Creating key "' + keyName + '".')
    try:
        r = requests.post(url,params=args)

        # data = dump.dump_all (r)
        # print (data.decode ('utf-8'))

        # If the response was successful, no Exception will be raised
        r.raise_for_status()
    except HTTPError as http_err:
        if (r.status_code == 500):
            err = r.json()
            http_err = err['Message']
        raise Exception(f'HTTP error occurred: {http_err}')
    except Exception as err:
        raise Exception(f'Other error occurred: {err}')
    else:
        key = r.json()

    return key

def grabCurrentIpfsRoot(settings):
    url = "http://" + settings['remote']['ipfsserver'] + ":" + settings['remote']['ipfsport'] + "/api/v0/files/ls"
    args = {
        'arg'   : DIRECTORY_SEPARATOR,
        'long'  : True
    }
    r = requests.post(url, params=args)
    result = r.json()
    # pp.pprint(result)
    if "Entries" in result:
        if result["Entries"] is not None:
            entries = result['Entries']
            for entry in entries:
                if entry['Type'] == 1:
                    # see if this is the directory we want
                    # pp.pprint(entry)
                    if entry['Name'] == settings['remote']['mfsrootdirectory']:
                        return entry     

    return None

def updateIpns(settings, hash):
    url = "http://" + settings['remote']['ipfsserver'] + ":" + settings['remote']['ipfsport'] + "/api/v0/name/publish"
    args = {
        'arg'   : '/ipfs/' + hash,
        'key'   : settings['remote']['ipnskeyname']
    }
    
    print('Publishing "' + hash + '".')
    try:
        r = requests.post(url,params=args)

        # data = dump.dump_all (r)
        # print (data.decode ('utf-8'))

        # If the response was successful, no Exception will be raised
        r.raise_for_status()
    except HTTPError as http_err:
        if (r.status_code == 500):
            err = r.json()
            http_err = err['Message']
        raise Exception(f'HTTP error occurred: {http_err}')
    except Exception as err:
        raise Exception(f'Other error occurred: {err}')
    else:
        results = r.json()
        # pp.pprint(results)
        return results['Name']
    
def main():
    settings['remote']['ipfsport'] = str(settings['remote']['ipfsport'])
    settings['remote']['maddr'] = '/ip4/' + settings['remote']['ipfsserver'] + '/tcp/' + settings['remote']['ipfsport']

    # Load/set up the existing ipfs info
    ipfsDb = {}
    dbFile = Path(settings['options']['ipfsdbfilename'])
    if settings['options']['refresh'] or not dbFile.is_file():
        print("Loading IPFS info from " + settings['remote']['ipfsserver'] + ":" + settings['remote']['ipfsport'] + ".")
        ipfsDb[settings['remote']['mfsrootdirectory'] + '/'] = grabCurrentIpfs(settings, '/' + settings['remote']['mfsrootdirectory'] + '/')
        with open(settings['options']['ipfsdbfilename'],"w") as file:
            file.write(json.dumps(ipfsDb))
    else:
        print("Loading IPFS info from existing file " + settings['options']['ipfsdbfilename'] + ".")
        with open(settings['options']['ipfsdbfilename'],"r") as file:
            ipfsDb = json.load(file)
    print("Done loading IPFS info.")

    # Load/set up the current TSL info
    tslDb = {}
    dbFile = Path(settings['options']['tsldbfilename'])
    if settings['options']['refresh'] or not dbFile.is_file():
        print("Loading TSL Library from " + settings['local']['tsldirectory'])
        tslDb[settings['remote']['mfsrootdirectory'] + '/'] = grabCurrentTsl(settings, settings['local']['tsldirectory'])
        with open(settings['options']['tsldbfilename'],"w") as file:
            file.write(json.dumps(tslDb))
    else:
        print("Loading TSL Library from existing file " + settings['options']['tsldbfilename'] + ".")
        with open(settings['options']['tsldbfilename'],"r") as file:
            tslDb = json.load(file)
    print("Done loading TSL Library.")

    print("Comparing data and making changes.")
    parsePaths(settings, '', ipfsDb, tslDb)
    print("Done comparing data and making changes.")

    print("Updating IPNS entry")
    settings['remote']['ipnsKey'] = findKey(settings, settings['remote']['ipnskeyname'])
    print("IPNS key loaded.")
    rootDir = grabCurrentIpfsRoot(settings)
    if (rootDir is None):
        raise Exception("Could not get the current ipfs root directory of " + settings['remote']['ipnskeyname'] + ".")
    
    ipns = updateIpns(settings, rootDir['Hash'])
    print("IPNS key: " + ipns)


main()

