from pyairtable import Api
import requests
from requests_ratelimiter import LimiterSession
import sys
import os
import time
from dotenv import load_dotenv, dotenv_values

load_dotenv()

search_url = "https://api.openalex.org/works?filter=title.search:"
semantic_url = "https://api.semanticscholar.org/graph/v1/paper/search/match?query="
header = {"x-api-key": os.getenv('SEMANTIC_SCHOLAR_API_KEY')}

api = Api(os.getenv('AIRTABLE_API_KEY'))
reference_info = {}
references = {}

table1 = api.table('appvtCMw78DSAMOUH', 'Team1_Preprints')
session_alex = LimiterSession(
        per_second=10,
        per_day=100000
    )
session_semantic = LimiterSession(
        per_second=1
    )
    
def split_concepts_and_methods(concepts_methods):
    if not concepts_methods:
        print("Concepts and Methods not found in the string.")
        return [], []
    else:
        pos = concepts_methods.find('Methods:')
        concepts = concepts_methods[:pos].split('Concepts: ')[1].lstrip().rstrip().split(';')
        methods = concepts_methods[pos:].split('Methods: ')[1].lstrip().rstrip().split(';')
        return concepts, methods

def reference_table(paper, response):
    if response.json()['referenced_works_count'] == 0:
        print(f"No references found for paper: {paper}. Now trying semantic scholar")
        search_semantic(paper)
        return
    #set up dict structure
    for reference in response.json()['referenced_works']:
        reference_info.update({reference: 1})

def search_semantic(paper):
    response = session_semantic.get(semantic_url + paper, headers=header)
    time.sleep(2)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"An error occurred while fetching paper {paper}: {e}")
        return
    print(f"successfully fetched paper: {paper} from semantic scholar")
    # get paper ID for first paper returned from search. Then use the paperID to get references of paper
    paperid = response.json()['data'][0]['paperId']
    url = f"https://api.semanticscholar.org/graph/v1/paper/{paperid}?fields=references"
    
    response = session_semantic.get(url, headers=header)
    time.sleep(2)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"An error occurred while fetching references for {paper}: {e}") 
        return
    print(f"successfully fetched referenced paper for: {paper} from semantic scholar")
    semantic_references = response.json()['references']
    if not semantic_references:
        print(f"No references found for paper: {paper} in semantic scholar")
        return
    references.update({paper: {"authors": []}})
    for reference in semantic_references:
        paperid = reference['paperId']
        url = f"https://api.semanticscholar.org/graph/v1/paper/{paperid}?fields=authors"
        response = session_semantic.get(url, headers=header)
        time.sleep(2)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"An error occurred while fetching authors for {paper}: {e}")
            continue
        new_references = response.json()['authors']
        for author in new_references:
           references[paper]["authors"].append({author['name'], author['authorId']})
    return
      
def check_reference(response, final_reference_list):
    #cross check if reference from filtered search is in the original list of references
    if response.json()['meta']['count'] == 0:
        print(f"No references found for this paper through Open Alex.")
        return
    #print(response.json()['results'][0]['id'])
    for result in response.json()['results']:
        result = result['id']
        #print(reference_info[result])
        if reference_info.get(result) != None:
            final_reference_list.append(result)
    

def cross_reference(concepts, methods, final_reference_list):
    extension = 'fulltext.search:'
    #chain together all the methods with OR operation
    for method in methods:
        extension += f"{method}|"
    extension = extension.rstrip('|')  
    #make call for each concept and use the same methods for all concepts
    for concept in concepts:
        url = f"https://api.openalex.org/works?filter=abstract.search:{concept},"
        url = url+extension 
        response = session_alex.get(url)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"An error occurred while fetching papers for concept {concept}: {e}")
            sys.exit(1)
        check_reference(response, final_reference_list)
        #print(url)

def update_author_list(paper, final_reference_list):
    #for each reference link in final_reference_list, convert each link to API URL and then get authors and orcid of each paper
    references.update({paper: {"authors": []}})

    for reference in final_reference_list:
        preprint_link = reference[:8] + 'api.' + reference[8:] 
        response = session_alex.get(preprint_link)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"An error occurred while fetching paper {paper}: {e}")
            sys.exit(1)
        authors = response.json()['authorships']
        for author in authors:
            references[paper]["authors"].append({author['author']['display_name'], author['author']['orcid']})

def main():
    records = table1.all(view='Proposals')
    records_to_update = [
        record for record in records
        if (record['fields'].get('Status') == 'To Pitch(Editorial)'
            or record['fields'].get('Status') == 'Selected')
        and (record['fields'].get('Updated Concepts'))
            # or record['fields'].get('Updated Concepts').strip() == '')
    ]
    for record in records_to_update[0:10]:
        final_reference_list = []
        fields = record['fields']
        paper = fields.get('Title').replace(',', ' ')
        response = session_alex.get(search_url + paper)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"An error occurred while fetching paper {paper}: {e}")
            sys.exit(1)

        print("successfully searched for paper: ", paper)

        #raw link to preprint
        preprint_link = response.json()['results'][0]['id']
        # Convert preprint link to API URL
        preprint_link = preprint_link[:8] + 'api.' + preprint_link[8:] 
        response = session_alex.get(preprint_link)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"An error occurred while fetching paper {paper}: {e}")
            sys.exit(1)
        #put all the referenced works in a dict
        reference_table(paper, response)
        
        if paper not in references:
            concepts_methods=fields.get('Updated Concepts')
            #extract concepts and methods from string and split into two lists
            concepts,methods = split_concepts_and_methods(concepts_methods)
            if not concepts or not methods:
                print(f"No concepts or methods found for paper {paper}.")
                continue
            else:
                cross_reference(concepts, methods, final_reference_list)
                update_author_list(paper, final_reference_list)
        else:
            continue
    
    print(references)
    
if __name__ == "__main__":
    main()