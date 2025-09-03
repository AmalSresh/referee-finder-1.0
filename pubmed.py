#!/usr/bin/env python3

"""

PubMed Preprint Search Tool
A simple tool to search for preprint information using PubMed's E-utilities API.
Given a title or DOI, it searches PubMed and retrieves detailed information about the preprint.
Automatically detects whether the input is a title or DOI and uses the appropriate search method.
"""
import requests
import xml.etree.ElementTree as ET
import json
import argparse

class PubMedSearcher:
    def __init__(self):
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        self.email = "your-email@example.com"  # Required by NCBI for API usage
    
    def search_by_title(self, title):
        """
        Search PubMed for articles matching the given title.
        Returns a list of PMIDs.
        """
        return self._search_pubmed(f'"{title}"[Title]')

    def search_by_doi(self, doi):
        """
        Search PubMed for articles matching the given DOI.
        Returns a list of PMIDs.
        """
        # Clean DOI - remove common prefixes if present
        clean_doi = (
            doi.replace("https://doi.org/", "")
            .replace("http://dx.doi.org/", "")
            .replace("doi:", "")
        )
        return self._search_pubmed(f'"{clean_doi}"[AID]')

    def _search_pubmed(self, query):
        """
        Internal method to search PubMed with a given query.
        Returns a list of PMIDs.
        """

        search_url = f"{self.base_url}/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "xml",
            "retmax": 10,  # Limit to top 10 results
            "email": self.email,
        }

        try:

            response = requests.get(search_url, params=params)
            response.raise_for_status()
            root = ET.fromstring(response.content)

            pmids = []
            for pmid_elem in root.findall(".//Id"):

                pmids.append(pmid_elem.text)
            return pmids

        except requests.RequestException as e:

            print(f"Error searching PubMed: {e}")

            return []

    def get_article_details(self, pmid):
        """
        Fetch detailed information for a given PMID.
        """
        fetch_url = f"{self.base_url}/efetch.fcgi"
        params = {"db": "pubmed", "id": pmid, "retmode": "xml", "email": self.email}
        try:
            response = requests.get(fetch_url, params=params)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            article = root.find(".//PubmedArticle")
            if article is None:
                return None
            # Extract article information
            info = {}
            # Title
            title_elem = article.find(".//ArticleTitle")
            info["title"] = title_elem.text if title_elem is not None else "N/A"
            # Authors
            authors = []
            for author in article.findall(".//Author"):
                lastname = author.find("LastName")
                forename = author.find("ForeName")
                if lastname is not None and forename is not None:
                    authors.append(f"{forename.text} {lastname.text}")

                elif lastname is not None:
                    authors.append(lastname.text)
            info["authors"] = authors
            # Journal
            journal_elem = article.find(".//Journal/Title")
            info["journal"] = journal_elem.text if journal_elem is not None else "N/A"
            # Publication date
            pub_date = article.find(".//PubDate")
            if pub_date is not None:
                year = pub_date.find("Year")
                month = pub_date.find("Month")
                day = pub_date.find("Day")
                date_parts = []
                if year is not None:
                    date_parts.append(year.text)
                if month is not None:
                    date_parts.append(month.text)
                if day is not None:
                    date_parts.append(day.text)
                info["publication_date"] = " ".join(date_parts) if date_parts else "N/A"
            else:
                info["publication_date"] = "N/A"

            # Abstract
            abstract_elem = article.find(".//Abstract/AbstractText")
            info["abstract"] = (
                abstract_elem.text if abstract_elem is not None else "N/A"
            )
            # DOI
            doi_elem = article.find('.//ArticleId[@IdType="doi"]')
            info["doi"] = doi_elem.text if doi_elem is not None else "N/A"
            # PMID
            info["pmid"] = pmid
            # Check if it's a preprint
            publication_types = []
            for pub_type in article.findall(".//PublicationType"):
                if pub_type.text:
                    publication_types.append(pub_type.text)
            info["publication_types"] = publication_types
            info["is_preprint"] = any(
                "preprint" in pt.lower() for pt in publication_types
            )
            # Extract references
            info["references"] = self._extract_references(article)
            return info
        except requests.RequestException as e:
            print(f"Error fetching article details: {e}")
            return None

    def _extract_references(self, article):
        """
        Extract reference list from the article XML.
        """
        references = []
        reference_list = article.find(".//ReferenceList")
        if reference_list is not None:
            for ref in reference_list.findall(".//Reference"):
                ref_info = {}
                # Reference citation text
                citation = ref.find(".//Citation")
                if citation is not None and citation.text:
                    ref_info["citation"] = citation.text.strip()
                # Article IDs in references (PMID, DOI, etc.)
                article_ids = ref.findall(".//ArticleId")
                for aid in article_ids:
                    id_type = aid.get("IdType")
                    if id_type and aid.text:
                        ref_info[f"{id_type}"] = aid.text
                if ref_info:  # Only add if we found some info
                    references.append(ref_info)
        return references

    def get_similar_papers(self, pmid, max_results=5):
        """
        Get similar papers using PubMed's ELink API.
        """
        elink_url = f"{self.base_url}/elink.fcgi"
        params = {
            "dbfrom": "pubmed",
            "db": "pubmed",
            "id": pmid,
            "cmd": "neighbor",
            "linkname": "pubmed_pubmed",
            "retmode": "xml",
            "email": self.email,
        }
        try:
            response = requests.get(elink_url, params=params)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            similar_pmids = []
            # Find linked PMIDs
            for link in root.findall(".//Link"):
                linked_pmid = link.find("Id")
                if linked_pmid is not None and linked_pmid.text != pmid:
                    similar_pmids.append(linked_pmid.text)
                    if len(similar_pmids) >= max_results:
                        break
            # Get details for similar papers
            similar_papers = []
            for similar_pmid in similar_pmids:
                paper_info = self.get_article_details(similar_pmid)
                if paper_info:
                    # Simplify info for similar papers (less detail)
                    simplified_info = {
                        "pmid": paper_info["pmid"],
                        "title": paper_info["title"],
                        "authors": (
                            paper_info["authors"][:3] if paper_info["authors"] else []
                        ),  # First 3 authors
                        "journal": paper_info["journal"],
                        "publication_date": paper_info["publication_date"],
                        "doi": paper_info["doi"],
                    }
                    similar_papers.append(simplified_info)
            return similar_papers

        except requests.RequestException as e:
            print(f"Error fetching similar papers: {e}")
            return []

    def _is_doi(self, text):
        """
        Simple heuristic to determine if text looks like a DOI.
        """
        text = text.lower().strip()
        return (
            text.startswith("10.")
            or text.startswith("doi:")
            or text.startswith("https://doi.org/")
            or text.startswith("http://dx.doi.org/")
        )

    def search_preprint(
        self, search_term, include_similar=False, include_references=True
    ):
        """
        Main method to search for preprint by title or DOI and return detailed information.
        Args:

            search_term: Title or DOI to search for

            include_similar: Whether to fetch similar papers (slower)

            include_references: Whether to include reference lists

        """
        if self._is_doi(search_term):

            print(f"Searching by DOI: '{search_term}'")

            pmids = self.search_by_doi(search_term)

        else:
            print(f"Searching by title: '{search_term}'")
            pmids = self.search_by_title(search_term)
        print("-" * 50)
        if not pmids:
            print("No articles found matching the search term.")
            return []

        results = []
        for pmid in pmids:
            article_info = self.get_article_details(pmid)
            if article_info:
                # Add similar papers if requested
                if include_similar:
                    print(f"Fetching similar papers for PMID {pmid}...")
                    article_info["similar_papers"] = self.get_similar_papers(pmid)

                else:
                    article_info["similar_papers"] = []

                # Remove references if not requested

                if not include_references:
                    article_info["references"] = []

                results.append(article_info)
        return results

    def display_results(self, results):
        """
        Display search results in a formatted way.
        """

        if not results:
            print("No results to display.")
            return
        for i, article in enumerate(results, 1):
            print(f"\n=== Result {i} ===")
            print(f"PMID: {article['pmid']}")
            print(f"Title: {article['title']}")
            print(
                f"Authors: {', '.join(article['authors']) if article['authors'] else 'N/A'}"
            )
            print(f"Journal: {article['journal']}")
            print(f"Publication Date: {article['publication_date']}")
            print(f"DOI: {article['doi']}")
            print(f"Is Preprint: {'Yes' if article['is_preprint'] else 'No'}")
            print(f"Publication Types: {', '.join(article['publication_types'])}")
            if article["abstract"] != "N/A":
                abstract = article["abstract"]
                # if len(abstract) > 300:

                #     abstract = abstract[:300] + "..."
                print(f"Abstract: {abstract}")

            # Display references if available

            if article.get("references"):
                print(f"\nReferences ({len(article['references'])} found):")
                for j, ref in enumerate(
                    article["references"][:10], 1
                ):  # Show first 10 reference
                    print(f"  {j}. {ref.get('citation', 'N/A')}")
                    if "pmid" in ref:
                        print(f"     PMID: {ref['pmid']}")
                    if "doi" in ref:
                        print(f"     DOI: {ref['doi']}")
                if len(article["references"]) > 10:
                    print(
                        f"     ... and {len(article['references']) - 10} more references"
                    )
            # Display similar papers if available
            if article.get("similar_papers"):
                print(f"\nSimilar Papers ({len(article['similar_papers'])} found):")
                for j, similar in enumerate(article["similar_papers"], 1):
                    print(f"  {j}. {similar['title']}")
                    print(
                        f"     Authors: {', '.join(similar['authors']) if similar['authors'] else 'N/A'}"
                    )
                    print(
                        f"     Journal: {similar['journal']} ({similar['publication_date']})"
                    )
                    print(f"     PMID: {similar['pmid']} | DOI: {similar['doi']}")
                    print()
            print("-" * 50)


def main():
    """
    Main function to run the PubMed preprint search tool.
    """
    parser = argparse.ArgumentParser(
        description="Search PubMed for articles by title or DOI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""

Examples:

  python pubmed_preprint_search.py "COVID-19 vaccine efficacy"

  python pubmed_preprint_search.py "10.1038/s41591-021-01230-y" --similar

  python pubmed_preprint_search.py "SARS-CoV-2" --no-references --similar

        """,
    )

    parser.add_argument("search_term", help="Article title or DOI to search for")

    parser.add_argument(
        "--similar",
        "-s",
        action="store_true",
        help="Include similar papers (slower but more comprehensive)",
    )

    parser.add_argument(
        "--no-references",
        "-nr",
        action="store_true",
        help="Exclude reference lists from results",
    )

    parser.add_argument(
        "--output", "-o", help="Output JSON file name (default: auto-generated)"
    )

    args = parser.parse_args()

    searcher = PubMedSearcher()

    results = searcher.search_preprint(
        args.search_term,
        include_similar=args.similar,
        include_references=not args.no_references,
    )

    searcher.display_results(results)

    # Save results to JSON

    if results:

        if args.output:
            output_file = args.output
        else:
            output_file = f"pubmed_results_{len(results)}_articles.json"
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {output_file}")

if __name__ == "__main__":

    main()
