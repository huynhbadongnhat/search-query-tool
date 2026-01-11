#This script returns codes based on an input file of UMLS CUIs, where each line in txt file is a separate CUI.
#If no results are found for a specific CUI, this will be noted in output and output file.
#Each set of results for a CUI is separated in the output file with '***'.

import requests
import argparse

parser = argparse.ArgumentParser(description='process user given parameters')
parser.add_argument('-k', '--apikey', required = True, dest = 'apikey', help = 'enter api key from your UTS Profile')
parser.add_argument('-v', '--version', required =  False, dest='version', default = 'current', help = 'enter version example-2015AA')
parser.add_argument('-o', '--outputfile', required = True, dest = 'outputfile', help = 'enter a name for your output file')
parser.add_argument('-s', '--sabs', required = True, dest='sabs',help = 'enter a comma-separated list of vocabularies without spaces, like MSH,SNOMEDCT_US')
parser.add_argument('-i', '--inputfile', required = True, dest = 'inputfile', help = 'enter a name for your input file')

args = parser.parse_args()
apikey = args.apikey
version = args.version
outputfile = args.outputfile
inputfile = args.inputfile
sabs = args.sabs

base_uri = 'https://uts-ws.nlm.nih.gov'
cui_list = []

with open(inputfile, encoding='utf-8') as f:
    for line in f:
        if line.isspace() is False: 
            cui1 = line.strip()
            cui_list.append(cui1)
        else:
            continue

with open(outputfile, 'w', encoding='utf-8') as o:
    for cui in cui_list:
        o.write('SEARCH CUI: ' + cui + '\n' + '\n')

        path = '/search/'+version
        query = {'apiKey':apikey, 'string':cui, 'sabs':sabs, 'returnIdType':'code', 'pageSize':200}
        output = requests.get(base_uri+path, params=query)
        output.encoding = 'utf-8'
        #print(output.url)

        outputJson = output.json()
        results = (([outputJson['result']])[0])['results']

        if len(results) == 0:
            print('No results found for ' + cui +'\n')
            o.write('No results found.' + '\n' + '\n')
        else:
            for item in results:
                o.write('Name: ' + item['name'] + '\n'  + 'UI: ' + item['ui'] + '\n' + 'Source Vocabulary: ' + item['rootSource'] + '\n' + 'URI: ' + item['uri'] + '\n' + '\n')

        o.write('***' + '\n' + '\n')