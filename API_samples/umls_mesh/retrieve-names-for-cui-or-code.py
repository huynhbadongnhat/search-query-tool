#This program returns atoms from CUI or code input.
#If using a code, the source vocabulary must be specified.

import requests
import argparse

parser = argparse.ArgumentParser(description='process user given parameters')
parser.add_argument('-k', '--apikey', required = True, dest = 'apikey', help = 'enter api key from your UTS Profile')
parser.add_argument('-v', '--version', required =  False, dest='version', default = 'current', help = 'enter version example-2015AA')
parser.add_argument('-s', '--source', required =  False, dest='source', help = 'enter source name if known')
parser.add_argument("-i", "--identifier", required =  True, dest="identifier", help = "enter identifier example-C0018787")

args = parser.parse_args()

apikey = args.apikey
version = args.version
source = args.source
identifier = args.identifier

uri = 'https://uts-ws.nlm.nih.gov'

try:
   source
except NameError:
   source = None

#If we don't specify a source vocabulary, it's assumed we're using UMLS CUIs.
if source is None:
    content_endpoint = '/rest/content/'+str(version)+'/CUI/'+str(identifier)

else:
    content_endpoint = '/rest/content/'+str(version)+'/source/'+str(source)+'/'+str(identifier)
                
query = {'apiKey':apikey}
r = requests.get(uri+content_endpoint, params=query)
r.encoding = 'utf-8'
            
if r.status_code != 200:
    if source is None:
        raise Exception('Search term ' + "'" + str(identifier) + "'" + ' not found')
    else:
        raise Exception('Search term ' + "'" + str(identifier) + "'" + 'or source ' + "'" + str(source) + "'" + ' not found')
            
items  = r.json()
jsonData = items['result']
            
Atoms = jsonData['atoms']

#The below uses the atoms' URI value from above as the starting URI.
try:
    atom_query = {'apiKey':apikey, 'pageSize':200}
    a = requests.get(Atoms, params=atom_query)
    a.encoding = 'utf-8'

    if a.status_code == 200:
        all_atoms = a.json()
        jsonAtoms = all_atoms['result']

        for atom in jsonAtoms:
            print('Name: ' + atom['name'])
            print('CUI: ' + jsonData['ui'])
            print('AUI: ' + atom['ui'])
            print('Term Type: ' + atom['termType'])
            print('Code: ' + atom['code'])
            print('Source Vocabulary: ' + atom['rootSource'])
            print('\n')
    else:
        print('No results found.')
except Exception as except_error:
    print(except_error)