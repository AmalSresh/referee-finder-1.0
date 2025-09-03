import requests
import sys

search_url = "https://api.openalex.org/works?filter=title.search:"
papers = ["Integrated treatment-decision algorithms for childhood TB: modelling diagnostic performance and costs", "Post-sampling degradation of viral RNA in wastewater impacts the quality of PCR-based concentration estimates", "Emetine dihydrochloride inhibits Chikungunya virus nsP2 helicase and shows antiviral activity in the cell culture and mouse model of virus infection", "Diagnostic Accuracy of Swab-Based Molecular Tests for Tuberculosis Using Novel Near-Point-Of-Care Platforms: A Multi-Country Evaluation", "Neutralisation and Antibody-Dependent Cellular Cytotoxicity Functions Map to Distinct SARS-CoV-2 Spike Subdomains and Vaccine Platforms"]

reference_info = {}
'''
so...
request.get(url for preprint)
for each referenced paper url in preprint:
    request.get(url for referenced paper)[authorships]
    for author in authorships:
        dict[preprint tiltle][authors].append({author['display_name'], author['orcid'][18:]})
'''

def get_info(paper, reference_link, response):
    if response.json()['referenced_works_count'] == 0:
        print(f"No references found for {paper}.")
        return
    #set up dict structure
    reference_info.update({paper: {"authors": []}})
    for reference in response.json()['referenced_works']:
        # Convert reference link to API URL
        reference_link = reference[:8] + 'api.' + reference[8:]
        print(reference_link)
        response = requests.get(reference_link)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"An error occurred while fetching referenced paper {reference}: {e}")
            continue
        authors = response.json()['authorships']
        for author in authors:
            reference_info[paper]["authors"].append({author['author']['display_name'], author['author']['orcid']})

def main():
    #search for specific preprint
    for paper in papers:
        response = requests.get(search_url + paper)
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

        response = requests.get(preprint_link)

        get_info(paper, preprint_link, response)
    #print(reference_info)

if __name__ == "__main__":
    main()
