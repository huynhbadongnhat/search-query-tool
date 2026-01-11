# usage: python crosswalk.py -k YOUR_API_KEY -s HPO -t SNOMEDCT_US -i hpo-codes.txt -o output.txt
## You can specify a specific UMLS version with the -v argument, but it is not required
## This script processes a list of codes from a specific UMLS source vocabulary and crosswalks to codes from another UMLS source vocabulary if those codes share a UMLS CUI. 

import requests
import argparse

parser = argparse.ArgumentParser(description='process user given parameters')
parser.add_argument('-k', '--apikey', required = True, dest = 'apikey', help = 'enter api key from your UTS Profile')
parser.add_argument('-v', '--version', required =  False, dest='version', default = 'current', help = 'enter version example-2021AA')
parser.add_argument('-s', '--source', required =  True, dest='source', help = 'enter a source vocabulary, like SNOMEDCT_US')
parser.add_argument('-t', '--target', required =  True, dest='target', help = 'enter the desired target vocabulary, like MSH')
parser.add_argument('-i', '--inputfile', required = True, dest = 'inputfile', help = 'enter a name for your input file')
parser.add_argument('-o', '--outputfile', required = True, dest = 'outputfile', help = 'enter a name for your output file')

args = parser.parse_args()
apikey = args.apikey
version = args.version
source = args.source
target = args.target
inputfile = args.inputfile
outputfile = args.outputfile

base_uri = 'https://uts-ws.nlm.nih.gov'
crosswalk_endpoint = '/rest/crosswalk/'+version+'/source/' + source

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
        
        path =  crosswalk_endpoint + '/' + code
        query = {'targetSource': target, 'apiKey':apikey}
        output = requests.get(base_uri + path, params = query)
        output.encoding = 'utf-8'
        print(output.url)
            
        outputJson = output.json()
        
        if len(outputJson['result']) == 0:
            print('No results found for ' + code +'\n')
            o.write('No results found for ' + code + '\n' + '\n')
            continue
        
        else:  
            results = outputJson['result'][0]
        
            o.write(source + ' Code - ' + code + '\t' + target + ' Code - ' + results['ui'] + ': ' + results['name'] + '\n' + '\n')