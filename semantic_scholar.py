import requests

search_url = "https://api.semanticscholar.org/graph/v1/paper/search/match?query="
#test list of preprints
papers = ["Post-sampling degradation of viral RNA in wastewater impacts the quality of PCR-based concentration estimates", "Emetine dihydrochloride inhibits Chikungunya virus nsP2 helicase and shows antiviral activity in the cell culture and mouse model of virus infection", "Diagnostic Accuracy of Swab-Based Molecular Tests for Tuberculosis Using Novel Near-Point-Of-Care Platforms: A Multi-Country Evaluation", "Neutralisation and Antibody-Dependent Cellular Cytotoxicity Functions Map to Distinct SARS-CoV-2 Spike Subdomains and Vaccine Platforms"]

# dict structure:
# {'paper title' : {authors: [{'author name', 'author id'}]}}
reference_info = {}

def update_references(response, paper):
     print("successfully fetched references")
     references = response.json()['citingPaperInfo']['authors']
     reference_info.update({paper: {"authors": []}})
     for author in references:
         reference_info[paper]["authors"].append({author['name'], author['authorId']})

def main():  
    for paper in papers:
        #get info for each paper
        response = requests.get(search_url + paper)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"An error occurred while fetching paper {paper}: {e}")
            continue
        print("successfully fetched paper: ", paper)
        # get paper ID for first paper returned from search. Then use the paperID to get references of paper
        paperid = response.json()['data'][0]['paperId']
        url = f"https://api.semanticscholar.org/graph/v1/paper/{paperid}/references?fields=authors&offset=1500&limit=500"
        
        response = requests.get(url)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"An error occurred while fetching references for {paper}: {e}") 
        
        update_references(response, paper)
    print(reference_info)
    
if __name__ == "__main__":
    main()