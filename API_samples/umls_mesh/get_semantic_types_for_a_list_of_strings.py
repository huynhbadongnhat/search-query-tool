import requests
import argparse
#import json
''' The standard Python library argparse is used to incorporate the parsing of command line arguments. 
Instead of manually setting variables in the code, argparse adds flexibility and reusability by allowing user input values to be parsed and utilized.'''

#initialize parser
parser = argparse.ArgumentParser(description='process user given parameters')

#add arguments
parser.add_argument('-k', '--apikey', required = True, dest = 'apikey', help = 'enter api key from your UTS Profile')
parser.add_argument('-v', '--version', required =  False, dest='version', default = 'current', help = 'enter version example-2015AA')
parser.add_argument('-o', '--outputfile', required = True, dest = 'outputfile', help = 'enter a name for your output file')
parser.add_argument('-s', '--sabs', required = False, dest='sabs',help = 'enter a comma-separated list of vocabularies, like MSH, SNOMEDCT_US, or RXNORM')
parser.add_argument('-i', '--inputfile', required = True, dest = 'inputfile', help = 'enter a name for your input file')
parser.add_argument('-t', '--searchtype', required = False, dest = 'searchtype', help = 'enter a searchtype')

#parse the arguments
args = parser.parse_args()
apikey = args.apikey
version = args.version
outputfile = args.outputfile
inputfile = args.inputfile
sabs = args.sabs
searchtype = args.searchtype

base_uri = 'https://uts-ws.nlm.nih.gov'
string_list = []
string_cui_dict = {}

with open(inputfile) as f:
    for line in f:
        if line.isspace() is False:    
            strings = line.strip()
            string_list.append(strings)
        #print(string_list)
        else:
            continue

with open(outputfile, 'w') as o:
    for string in string_list:
        temp_list = []

        path = '/search/'+version
        query = {'string':string, 'apiKey':apikey, 'rootSource':sabs, 'searchType':searchtype, 'pageSize':200}
        r1 = requests.get(base_uri+path, params=query)
        r1.encoding = 'utf-8'

        r = r1.json()

        try:
            res1 = ([r['result']])[0]['results']
        except KeyError as e:
            print(r1.reason)
            print(r1.status_code)
            raise(e)

        if len(res1) == 0:
            print('No results found for'+ string + '\n')
        else:
            for item in res1:
                temp_list.append(item['ui'])

            string_cui_dict[string] = [temp_list]

    #print(string_cui_dict)
    
    #output = []
    
    for k,v in string_cui_dict.items():
        for alist in v:
            for acui in alist:
                path = '/content/'+version+'/CUI/'+acui
                query = {'apiKey':apikey}
                r2 = requests.get(base_uri+path, params=query)
                res2 = r2.json()
            
                results = res2['result']
                o.write('SEARCH STRING: ' + k + '\n')
                o.write('UI: ' + results['ui'] + '\n' + 'Name: ' + results['name'] + '\n' + 'Semantic Type: ' + results['semanticTypes'][0]['name'] + '\n' + 'Semantic Type URI: ' + results['semanticTypes'][0]['uri'] + '\n' + '\n')

#For JSON output, comment out the two previous lines of code, un-comment out the below and "output = []" line above, and import json package at top
    
                #ui = results['ui']
                #name = results['name']
                #stype = results['semanticTypes']
        
                #record = {
                #    "ui": ui,
                #    "name": name,
                #    "semanticTypes": stype
                #    }
                #output.append(record)   
    
    #json_output = json.dumps(output, indent=4)
    #o.write(json_output)