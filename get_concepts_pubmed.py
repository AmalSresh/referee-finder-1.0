import os
from pyairtable import Api
import requests
import time
import openai
import dspy
from dotenv import load_dotenv
import re
import xml.etree.ElementTree as ET

load_dotenv()

#global_methods = []
# Get API keys from environment variables
AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if not AIRTABLE_API_KEY:
    raise ValueError("AIRTABLE_API_KEY environment variable is not set")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set")

api = Api(AIRTABLE_API_KEY)
openai.api_key = OPENAI_API_KEY

table1 = api.table('appvtCMw78DSAMOUH', 'Team1_Preprints')

pubmed_base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
email = "your-email@example.com"

# Configure DSPy
dspy.settings.configure(api_key=OPENAI_API_KEY)
model_name = "gpt-4o"
lm = dspy.LM(f"openai/{model_name}", cache=False)
dspy.settings.configure(lm=lm)

class MethodExtractor(dspy.Signature):
    """Extract scientific concepts and methods from text."""
    text = dspy.InputField()
    global_methods = dspy.InputField()
    methods = dspy.OutputField(desc=f"Use words from this list {global_methods} to make a list of methods based on this abstract. If no methods are found, return an empty list.")

class ExtractorProgram(dspy.Module):
    def __init__(self):
        super().__init__()
        self.extractor = dspy.ChainOfThought(MethodExtractor)
    
    def forward(self, text, global_methods):
        result = self.extractor(text=text, global_methods=global_methods)
        return result.methods

# Initialize DSPy programs
#extractor_program = ExtractorProgram()

def chunk_text(text, max_tokens):
    """Split text into chunks that fit within token limits."""
    words = text.split()
    chunks = []
    current_chunk = []
    current_length = 0
    
    for word in words:
        # Rough estimate: 1 word ≈ 1.3 tokens
        word_tokens = len(word) * 1.3
        if current_length + word_tokens > max_tokens:
            chunks.append(' '.join(current_chunk))
            current_chunk = [word]
            current_length = word_tokens
        else:
            current_chunk.append(word)
            current_length += word_tokens
    
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    return chunks


def analyze_content(text, preprint_methods):
    """Analyze text content using DSPy to extract concepts and methods."""
    try:
        extractor_program = ExtractorProgram()
        # Use DSPy to extract concepts and methods
        methods_str = extractor_program(text, preprint_methods)
        # Split the comma-separated strings into lists
        methods = [m.strip() for m in methods_str.split(',') if m.strip()]
        
        return methods
    except Exception as e:
        print(f"Error in DSPy analysis: {e}")
        return []

def get_id(paper, doi):
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
            return []

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

def get_ref_info(reference_list, preprint_methods):
    paper_and_methods = {}
    fetch_url = f"{pubmed_base_url}/efetch.fcgi"
    for ref in reference_list[1:20]:
        paper_and_methods.update({ref: {"title": "", "authors": [], "abstract": "", "methods": ""}})
        params = {
            "db": "pubmed", 
            "id": ref, 
            "retmode": "xml", 
            "email": email
        }
        try:
            response = requests.get(fetch_url, params = params)
            time.sleep(2)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            article = root.find(".//PubmedArticle")
            title_elem = article.find(".//ArticleTitle")
            paper_and_methods[ref]["title"] = title_elem.text if title_elem is not None else "N/A"
            authors = []
            for author in article.findall(".//Author"):
                lastname = author.find(".//LastName")
                forename = author.find(".//ForeName")
                affiliation = author.find(".//AffiliationInfo/Affiliation")
                authors.append(f"{forename.text if forename is not None else ""} {lastname.text if lastname is not None else ""} (affiliation: {affiliation.text if affiliation is not None else 'N/A'})")
            paper_and_methods[ref]["authors"] = authors
            abstract_elem = article.find(".//Abstract/AbstractText")
            paper_and_methods[ref]["abstract"] = abstract_elem.text if abstract_elem is not None else "N/A"
            #text_chunks = chunk_text      paper_and_methods[ref]["abstract"], 1000)
            #for chunk in text_chunks:
            methods = analyze_content(paper_and_methods[ref]["abstract"], preprint_methods)
                #print(methods)
            paper_and_methods[ref]["methods"] = methods  # methods
        except requests.RequestException as e:
            print(f"Error fetching article for ID {ref}: {e}")
            continue
    return paper_and_methods

def get_preprint_methods(concepts_methods):
    if not concepts_methods:
        print("Concepts and Methods not found in the string.")
        return [], []
    else:
        pos = concepts_methods.find('Methods:')
    #    concepts = concepts_methods[:pos].split('Concepts: ')[1].lstrip().rstrip().split(';')
        methods = concepts_methods[pos:].split('Methods: ')[1].lstrip().rstrip().split(';')
        methods = [m.strip().lower() for m in methods if m.strip()]
        return methods
    
final_references = {}

def main():
    records = table1.all(view='Proposals')
    
    records_to_update = [
        record for record in records
        if (record['fields'].get('Status') == 'To Pitch(Editorial)'
            or record['fields'].get('Status') == 'Selected')
        and (record['fields'].get('Updated Concepts'))
            # or record['fields'].get('Updated Concepts').strip() == '')
    ]
    for record in records_to_update[1:2]:
        preprint_references = []
        fields = record['fields']
        title = fields['Title']
        title = fields.get('Title').replace(',', ' ')
        title = re.sub(r'\[.*?\]', '', title).strip()
        #print(title)
        doi = fields.get('Link/DOI')
        concepts_methods=fields.get('Updated Concepts')

        #print(doi)
        id = get_id(title, doi)
        refs = get_pubmed_references(id)
        preprint_methods = get_preprint_methods(concepts_methods)
        preprint_clean = [m.strip().lower() for m in preprint_methods]
        #extractor_program = ExtractorProgram()
        methods = get_ref_info(refs, preprint_clean)
        final_references.update({title: {"authors": []}})
        for method in methods:
            ref_methods = [m.strip().lower() for m in methods[method]["methods"]]
            
            #print(f"These are the methods from the reference: {methods[method]['methods']}")
            #print(f"These are the methods from the preprint: {preprint_methods}")

            common = set(ref_methods) & set(preprint_clean)

            if common:
                final_references[title]["authors"].append(methods[method]["authors"])
             #   print(f"{method} has common methods: {list(common)}")
            else:
                print(f"{method} not suitable for referee")
    print(final_references)

            
        
        
if __name__ == "__main__":
    main()
    
