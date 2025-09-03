import re
from pyairtable import Api
import requests
from requests_ratelimiter import LimiterSession
import sys
import os
import time
from dotenv import load_dotenv, dotenv_values
import xml.etree.ElementTree as ET

load_dotenv()

api = Api(os.getenv('AIRTABLE_API_KEY'))
reference_info = {}
references = {}

table1 = api.table('appvtCMw78DSAMOUH', 'Team1_Preprints')

pubmed_base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
email = "your-email@example.com"

'''Get PubMed ID for a given title and cross-check if the doi matches'''
def get_id(title, doi):
    search_url = f"{pubmed_base_url}/esearch.fcgi"
    params = {
         "db": "pubmed",
         "term": title,
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

'''Get reference list for given PubMed ID'''
def get_references(id):
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


def update_author_pubmed(reference_codes, title):
    fetch_url = f"{pubmed_base_url}/efetch.fcgi"
    references.update({title: {"authors": []}})
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
                    references[title]["authors"].append({f"{first_name.text} {last_name.text}", affiliation.text if affiliation is not None else "No Affiliation"})
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
    for record in records_to_update[0:1]:
        preprint_references = []
        fields = record['fields']
        title = fields['Title']
        title = fields.get('Title').replace(',', ' ')
        title = re.sub(r'\[.*?\]', '', title).strip()
        print(title)
        doi = fields.get('Link/DOI')
        print(doi)
        id = get_id(title, doi)
        print(id)
        preprint_references = get_references(id)
        #print(preprint_references)
        update_author_pubmed(preprint_references, title)
    print(references)

            
if __name__ == "__main__":
    main()