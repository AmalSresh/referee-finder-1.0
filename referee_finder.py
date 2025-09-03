from pyairtable import Api
import requests
from requests_ratelimiter import LimiterSession
import sys
import os
import time
from dotenv import load_dotenv, dotenv_values
import xml.etree.ElementTree as ET
import re

load_dotenv()

semantic_url = "https://api.semanticscholar.org/graph/v1/paper/search/match?query="
header = {"x-api-key": os.getenv('SEMANTIC_SCHOLAR_API_KEY')}
pubmed_base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
email = "your-email@example.com"

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

COUNT = 0

def increment():
    global COUNT
    COUNT+=1


def open_alex_search(paper, concepts, methods, final_reference_list):
    search_url = "https://api.openalex.org/works?filter=title.search:"
    try:
        response = session_alex.get(search_url + paper)
        response.raise_for_status()
        print("successfully searched for paper: ", paper)
        #raw link to preprint
        preprint_link = response.json()['results'][0]['id']
        # Convert preprint link to API URL
        preprint_link = preprint_link[:8] + 'api.' + preprint_link[8:] 
        try:
            response = session_alex.get(preprint_link)
            response.raise_for_status()
            #put all the referenced works in a dict
            reference_table(paper, response)
            #print(concepts, methods)
            if not concepts or not methods:
                print(f"No concepts or methods found for paper {paper}.")
                return []
            else:
                cross_reference(concepts, methods, final_reference_list)
                update_author_list(paper, final_reference_list)
                return []
        except requests.exceptions.HTTPError as e:
            print(f"An error occurred while fetching paper {paper}: {e}")
            return []
    except requests.exceptions.HTTPError as e:
        print(f"An error occurred while fetching paper {paper}: {e}")
        return []

def search_semantic(paper):
    try:
        response = session_semantic.get(semantic_url + paper, headers=header)
        time.sleep(2)
        response.raise_for_status()
        print(f"successfully fetched paper: {paper} from semantic scholar")
        # get paper ID for first paper returned from search. Then use the paperID to get references of paper
        paperid = response.json()['data'][0]['paperId']
        url = f"https://api.semanticscholar.org/graph/v1/paper/{paperid}?fields=references"
        try:
            response = session_semantic.get(url, headers=header)
            time.sleep(2)
            response.raise_for_status()
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
            print(f"successfully fetched referenced paper for: {paper} from semantic scholar")
            return
        except requests.exceptions.HTTPError as e:
            print(f"An error occurred while fetching references for {paper}: {e}") 
            return
    except requests.exceptions.HTTPError as e:
        print(f"An error occurred while fetching paper {paper}: {e}")
        return
    
    
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
        print(f"No references found for paper: {paper}.")
        return
    #set up dict structure
    for reference in response.json()['referenced_works']:
        reference_info.update({reference: 1})


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

def preprint_id_pubmed(paper, doi):
    search_url = f"{pubmed_base_url}/esearch.fcgi"
    params = {
         "db": "pubmed",
         "term": paper,
         "retmode": "xml",
         "retmax": 10,
         "email": email
     }
    try:
        response = requests.get(search_url, params=params)
        time.sleep(2)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        pmids = []
        for pmid_elem in root.findall(".//Id"):
            pmids.append(pmid_elem.text)
        clean_doi = (
        doi.replace("https://doi.org/", "")
        .replace("http://dx.doi.org/", "")
        .replace("doi:", "")
        )
        params = {
            "db": "pubmed",
            "term": f"'{clean_doi}[AID]'",
            "retmode": "xml",
            "retmax": 10,
            "email": email
        }
        try:
            response = requests.get(search_url, params=params)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            for pmid_elem in root.findall(".//Id"):
                if pmid_elem.text in pmids:
                    return pmid_elem.text
        except requests.RequestException as e:
            print(f"Error searching PubMed for DOI: {e}")
            return None

    except requests.RequestException as e:

        print(f"Error searching PubMed: {e}")
        return []

def get_pubmed_references(id):
    fetch_url = f"{pubmed_base_url}/efetch.fcgi"
    params = {
        "db": "pubmed", 
        "id": id, 
        "retmode": "xml", 
        "email": email
        }
    references = []

    try:
        response = requests.get(fetch_url, params=params)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        article = root.find(".//PubmedArticle")
        if article is None:
            return None
        reference_list = article.find(".//ReferenceList")
        if reference_list is not None:
            for ref in reference_list.findall(".//Reference"):
                ref_info = {}
                # Article IDs in references (PMID, DOI, etc.)
                article_ids = ref.findall(".//ArticleId")
                for aid in article_ids:
                    id_type = aid.get("IdType") 
                    #print(id_type)
                    if id_type == "pubmed" and aid.text:
                        references.append(aid.text)
        return references
    except requests.RequestException as e:
        print(f"Error fetching references for ID {id}: {e}")
        return None

def update_author_pubmed(reference_codes, paper):
    fetch_url = f"{pubmed_base_url}/efetch.fcgi"
    references.update({paper: {"authors": []}})
    if not reference_codes:
        print(f"No references found for paper: {paper}.")
        return
    for ref in reference_codes:
        params = { 
            "db": "pubmed", 
            "id": ref, 
            "retmode": "xml", 
            "email": email
            }
        try:
            response = requests.get(fetch_url, params=params)
            print("fetching authors for reference: ", ref)
            time.sleep(2)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            article = root.find(".//PubmedArticle")
            if article is None:
                print(f"No article found for ID {ref}.")
                return None
            author_list = article.find(".//AuthorList")
            if author_list is not None:
                for author in author_list.findall(".//Author"):
                    first_name = author.find(".//ForeName")
                    #print(first_name.text)
                    last_name = author.find(".//LastName")
                    #print(last_name.text)
                    affiliation = author.find(".//AffiliationInfo/Affiliation")
                    #print(affiliation.text)
                    references[paper]["authors"].append({f"{first_name.text} {last_name.text}", affiliation.text if affiliation is not None else "No Affiliation"})
                    print("Successfully fetched authors for reference: ", ref)
                    
        except requests.RequestException as e:
            print(f"Error fetching references for ID {id}: {e}")
            return None
    return references

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
        #remove any bracketed text from title
        paper = re.sub(r'\[.*?\]', '', paper).strip()
        #print(record)
        doi = fields.get('Link/DOI')
        print(doi)
        concepts_methods=fields.get('Updated Concepts')
        #extract concepts and methods from string and split into two lists
        concepts,methods = split_concepts_and_methods(concepts_methods)
        open_alex_search(paper, concepts, methods, final_reference_list)
        if len(references[paper]["authors"]) == 0:
            print(f"Open Alex did not work for paper: {paper}. Trying Semantic Scholar.")
            search_semantic(paper)
        if len(references[paper]["authors"]) == 0:
            '''Get authors from PubMed, doesn't use extensive filtering. More advanced methods in pubtest.py'''
            print(f"Semantic Scholar did not work for paper: {paper}. Trying PubMed.")
            id = preprint_id_pubmed(paper, doi)
            pubmed_references = get_pubmed_references(id)
            update_author_pubmed(pubmed_references, paper)
        if len(references[paper]["authors"]) == 0:
            print(f"No authors found for paper: {paper} from any API.")
        else:
            increment()
    print(references)
    print(f"Found {COUNT} out of {len(records_to_update[0:10])} papers with references.")
    
    
if __name__ == "__main__":
    main()