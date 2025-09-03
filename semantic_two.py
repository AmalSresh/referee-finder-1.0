import requests
from requests_ratelimiter import LimiterSession
import sys
import os
from dotenv import load_dotenv, dotenv_values

load_dotenv()

search_url = "https://api.semanticscholar.org/graph/v1/paper/search/match?query="
#snippet_url = "https://api.semanticscholar.org/graph/v1/snippet/search?query={snippet}&limit=1"
#test list of preprints
papers = ["Campus-based genomic surveillance uncovers early emergence of a future dominant A(H3N2) influenza clade", "Post-sampling degradation of viral RNA in wastewater impacts the quality of PCR-based concentration estimates", "Emetine dihydrochloride inhibits Chikungunya virus nsP2 helicase and shows antiviral activity in the cell culture and mouse model of virus infection", "Diagnostic Accuracy of Swab-Based Molecular Tests for Tuberculosis Using Novel Near-Point-Of-Care Platforms: A Multi-Country Evaluation", "Neutralisation and Antibody-Dependent Cellular Cytotoxicity Functions Map to Distinct SARS-CoV-2 Spike Subdomains and Vaccine Platforms"]

# dict structure:
# {'paper title' : {authors: [{'author name', 'author id'}]}}
reference_info = {}
header = {"x-api-key": os.getenv('SEMANTIC_SCHOLAR_API_KEY')}
session_semantic = LimiterSession(
        per_minute=30,
        burst=1
    )

def main():
    for paper in papers[0:1]:
        #get info for each paper
        response = session_semantic.get(search_url + paper, headers=header)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"An error occurred while fetching paper {paper}: {e}")
            continue
        print("successfully fetched paper: ", paper)
        # get paper ID for first paper returned from search. Then use the paperID to get references of paper
        paperid = response.json()['data'][0]['paperId']
        url = f"https://api.semanticscholar.org/graph/v1/paper/{paperid}?fields=references"
        
        response = session_semantic.get(url, headers=header)
        print(response.json()['references'])
        snippet = "Bayesian modeling, two-deme compartmental SIR, H3 epitope-based modeling"
        snippet_url = f"https://api.semanticscholar.org/graph/v1/snippet/search?query={snippet}&limit=5"

        response = session_semantic.get(snippet_url, headers=header)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"An error occurred while fetching references for {paper}: {e}")
        for result in response.json()['data']:
            print(result['paper']['title']) 
        
if __name__ == "__main__":
    main()