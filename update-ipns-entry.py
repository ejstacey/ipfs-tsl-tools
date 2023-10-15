#!/bin/env python3

import pprint
import json
import requests
import os
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
    prog='update-ipnfs-entry',
    description='This program looks at the current given directory and makes sure it republishes the IPNS key for it.'
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
        'arg'   : '/',
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

    print("Updating IPNS entry")
    settings['remote']['ipnsKey'] = findKey(settings, settings['remote']['ipnskeyname'])
    print("IPNS key loaded.")
    rootDir = grabCurrentIpfsRoot(settings)
    if (rootDir is None):
        raise Exception("Could not get the current ipfs root directory of " + settings['remote']['ipnskeyname'] + ".")
    
    ipns = updateIpns(settings, rootDir['Hash'])
    print("IPNS key: " + ipns)


main()

