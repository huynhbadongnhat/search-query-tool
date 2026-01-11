#This script returns UMLS CUIs based on an input file of codes, where each line in txt file is a separate code.
#All codes must be from the same vocabulary.
#If no results are found for a specific code, this will be noted in output and output file.
#Each set of results for a code is separated in the output file with '***'.

import requests
import argparse

parser = argparse.ArgumentParser(description='process user given parameters')
parser.add_argument('-k', '--apikey', required = True, dest = 'apikey', help = 'enter api key from your UTS Profile')
parser.add_argument('-v', '--version', required =  False, dest='version', default = 'current', help = 'enter version example-2015AA')
parser.add_argument('-o', '--outputfile', required = True, dest = 'outputfile', help = 'enter a name for your output file')
parser.add_argument('-s', '--sabs', required = True, dest='sabs',help = 'enter a single vocabulary, like MSH, SNOMEDCT_US, or RXNORM')
parser.add_argument('-i', '--inputfile', required = True, dest = 'inputfile', help = 'enter a name for your input file')

args = parser.parse_args()
apikey = args.apikey
version = args.version
outputfile = args.outputfile
inputfile = args.inputfile
sabs = args.sabs

base_uri = 'https://uts-ws.nlm.nih.gov'
code_list = []

with open(inputfile, encoding='utf-8') as f:
    for line in f:
        if line.isspace() is False: 
            codes = line.strip()
            code_list.append(codes)
        else:
            continue

with open(outputfile, 'w', encoding='utf-8') as o:
    for code in code_list:
        o.write('SEARCH CODE: ' + code + '\n' + '\n')

        path = '/search/'+version
        query = {'apiKey':apikey, 'string':code, 'rootSource':sabs, 'inputType':'sourceUI', 'pageSize':200}
        output = requests.get(base_uri+path, params=query)
        output.encoding = 'utf-8'
        #print(output.url)

        outputJson = output.json()
        results = (([outputJson['result']])[0])['results']

        if len(results) == 0:
            print('No results found for ' + code +'\n')
            o.write('No results found.' + '\n' + '\n')
        else:
            for item in results:
                o.write('CUI: ' + item['ui'] + '\n' + 'Name: ' + item['name'] + '\n'  + 'URI: ' + item['uri'] + '\n' + 'Source Vocabulary: ' + item['rootSource'] + '\n' + 'Code: '+ code + '\n' + '\n')

        o.write('***' + '\n' + '\n')