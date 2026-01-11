#This script displays hierarchical relationships for an identifier (code).
#Source vocabulary is required.
#Only one type of hierarchical relationship can be searched for at a time - such as children, parents, descendents, or ancestors.

import requests
import argparse

parser = argparse.ArgumentParser(description='process user given parameters')
parser.add_argument("-k", "--apikey", required = True, dest = "apikey", help = "enter api key from your UTS Profile")
parser.add_argument("-v", "--version", required =  False, dest="version", default = "current", help = "enter version example-2015AA")
parser.add_argument("-s", "--source", required =  True, dest="source", help = "enter a source vocabulary, like SNOMEDCT_US")
parser.add_argument("-i", "--identifier", required =  True, dest="identifier", help = "enter an identifier, like 9468002")
parser.add_argument("-o", "--operation", required = True, dest="operation", help = "choose an operation such as children, parents, descendants, or ancestors")

args = parser.parse_args()
apikey = args.apikey
version = args.version
source = args.source
identifier = args.identifier
operation = args.operation
uri = "https://uts-ws.nlm.nih.gov"
content_endpoint = "/rest/content/"+version+"/source/"+source+"/"+identifier+"/"+operation

pageNumber=0

try:
    while True:
        pageNumber += 1
        query = {'apiKey':apikey,'pageNumber':pageNumber,'pageSize':200}
        r = requests.get(uri+content_endpoint,params=query)
        r.encoding = 'utf-8'
        items  = r.json()
        
        if r.status_code != 200:
            if pageNumber == 1:
                print('No results found.'+'\n')
                break
            else:
                break
            
        print("Results for page " + str(pageNumber)+"\n")
        
        for result in items["result"]:
            try:
                print("ui: " + result["ui"])
            except:
                NameError
            try:
                print("uri: " + result["uri"])
            except:
                NameError
            try:
                print("name: " + result["name"])
            except:
                NameError
            try:
                print("Source Vocabulary: " + result["rootSource"])
            except:
                NameError
            print("\n")

    print("*********")
except Exception as except_error:
    print(except_error)