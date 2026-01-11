#This script will return CUI information for a single search term.
#Optional query parameters are commented out below.

import requests
import argparse

def results_list():
    parser = argparse.ArgumentParser(description='process user given parameters')
    parser.add_argument("-k", "--apikey", required = True, dest = "apikey", help = "enter api key from your UTS Profile")
    parser.add_argument("-v", "--version", required =  False, dest="version", default = "current", help = "enter version example-2021AA")
    parser.add_argument("-s", "--string", required =  True, dest="string", help = "enter a search term, using hyphens between words, like diabetic-foot")

    args = parser.parse_args()
    apikey = args.apikey
    version = args.version
    string = args.string
    uri = "https://uts-ws.nlm.nih.gov"
    content_endpoint = "/rest/search/"+version
    full_url = uri+content_endpoint

    try:
        query = {'string':string,'apiKey':apikey, 'pageSize':200}
        #query['includeObsolete'] = 'true'
        #query['includeSuppressible'] = 'true'
        #query['returnIdType'] = "sourceConcept"
        #query['sabs'] = "SNOMEDCT_US"
        r = requests.get(full_url,params=query)
        r.raise_for_status()
        print(r.url)
        r.encoding = 'utf-8'
        outputs  = r.json()

        items = (([outputs['result']])[0])['results']

        if len(items) == 0:
            print('No results found.'+'\n')
        else:
            print("Results:\n")
            for result in items:
                print('UI: ' + result['ui'])
                print('URI: ' + result['uri'])
                print('Name: ' + result['name'])
                print('Source Vocabulary: ' + result['rootSource'])
                print('\n')

        print('*********')

    except Exception as except_error:
        print(except_error)

results_list()