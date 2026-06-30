from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
import re
import unicodedata
import html
from unittest import result
import requests
import json
import time
import xml.etree.ElementTree as ET
from rapidfuzz.distance import JaroWinkler
from pythainlp.util import normalize as thai_normalize
from semanticscholar import SemanticScholar

sch = SemanticScholar()

DATACITE_API = "https://api.datacite.org/dois/"

DATACITE_HEADERS = {
    "Accept": "application/vnd.api+json",
    "User-Agent": "ReferenceVerificationBot/1.0"
}

OPENALEX_BASE_URL = "https://api.openalex.org"
OPENALEX_EMAIL = "your_email@example.com"

PUBMED_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
PUBMED_EMAIL = "your_email@example.com"   # แนะนำให้ใส่

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

SCHOLAR_BASE_URL = "https://api.semanticscholar.org/graph/v1"

SCHOLAR_API_KEY = "VAXT2HHjqC1SK0ikS7Xb7auWxqDMRbAlaSnkVZCL"

SCHOLAR_HEADERS = {
    "User-Agent": "ReferenceVerifier/1.0",
    "x-api-key": SCHOLAR_API_KEY
}

pattern_doi = r'10\.\d{4,9}/[-._;()/:A-Z0-9]+'

def getDOI(text):
    match = re.search(pattern_doi, text, re.IGNORECASE)
    if match:
        doi = match.group(0).rstrip('.,;')
        return doi
    else:
        return ''
    
def semantic_scholar_check_doi_exists(doi: str):
    try:
        paper = sch.get_paper(f"DOI:{doi}")
    except Exception:
        return False, None
    
    if paper is None:
        return False, None

    journal = paper.journal
    venue = paper.publicationVenue

    return True, {
        "source": "Semantic Scholar",
        "doi": paper.externalIds.get("DOI"),
        "title": paper.title,
        "authors": [a["name"] for a in paper.authors],
        "issue": getattr(journal, "issue", None),
        "volume": getattr(journal, "volume", None),
        "year": paper.year,
        "pages": getattr(journal, "pages", None),
        "publisher": (
            getattr(venue, "publisher", None)
            if venue
            else paper.venue
        ),
        "url": f"https://doi.org/{doi}"
    }
def semantic_scholar_search_by_title(title, limit=5, sleep=1.0):
    url = f"{SCHOLAR_BASE_URL}/paper/search"
    params = {
        "query": title,
        "limit": limit,
        "fields": "title,authors,year,venue,externalIds"
    }

    r = requests.get(url, params=params, headers=SCHOLAR_HEADERS, timeout=10)

    if r.status_code == 429:
        print("⚠️ Rate limited. Sleeping...")
        # time.sleep(sleep)
        # return semantic_scholar_search_by_title(title, limit, sleep * 2)
        return [{}]
    r.raise_for_status()

    res_json = r.json()["data"]
    for i in range(len(res_json)):
        if 'venue' in res_json[i]:
            res_json[i]["source"] = "Semantic Scholar"
            res_json[i]['conference_journal'] = res_json[i].pop('venue')
        res_json[i]['doi'] = res_json[i].get("externalIds",{}).get("DOI","")
    return res_json

def crossref_check_doi_exists(doi, mailto="sittipong.saychum@nectec.or.th"):
    url = f"https://api.crossref.org/works/{doi}"
    headers = {
        "User-Agent": f"ReferenceVerifier/1.0 (mailto:{mailto})"
    }
    r = requests.get(url, headers=headers, timeout=10)

    if r.status_code == 200:
        return True, r.json()["message"]
    elif r.status_code == 404:
        return False, None
    else:
        r.raise_for_status()

def crossref_get_metadata_from_doi(msg):
    title = msg.get("title", [""])[0]
    authors = [
        f"{a.get('family','')} {a.get('given','')}"
        for a in msg.get("author", [])
    ]
    year = msg.get("published-print", msg.get("published-online", {})) \
               .get("date-parts", [[None]])[0][0]
    url = next((item["URL"] for item in msg.get("link", []) if item.get("content-type") == "application/pdf"),None)
    return {
        "source": "Crossref",
        "doi": msg.get("DOI"),
        "title": title,
        "authors": authors,
        "issue": msg.get("issue"),
        "volume": msg.get("volume"),
        "year": year,
        "pages": msg.get("page"),
        "publisher": msg.get("publisher"),
        "url": url
    }

def crossref_search_by_title(title, rows=5, mailto="sittipong.saychum@nectec.or.th"):
    url = "https://api.crossref.org/works"
    params = {
        "query.title": title,
        "rows": rows,
        "mailto": mailto
    }

    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()

    items = r.json()["message"]["items"]

    results = []
    for item in items:
        # print(item)
        results.append({
            "source": "Crossref",
            "doi": item.get("DOI"),
            "title": item.get("title", [""])[0],
            "issue": item.get("issue", ''),
            "volume": item.get("volume", ''),
            "pages": item.get("page", ''),
            "year": item.get("published-print",
                             item.get("published-online", {}))
                             .get("date-parts", [[None]])[0][0],
            "conference_journal": item.get("publisher")
        })
    return results

def pubmed_get_metadata_by_doi(doi: str):
    doi = doi.replace("https://doi.org/", "").strip()

    # ---- Step 1: ESearch (DOI → PMID) ----
    params = {
        "db": "pubmed",
        "term": f"{doi}[AID]",
        "retmode": "json"
    }

    r = requests.get(ESEARCH_URL, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    # print(data)

    id_list = data["esearchresult"]["idlist"]
    if not id_list:
        return False, None  # DOI not indexed in PubMed

    for pmid in id_list[:1]:
        # pmid = id_list[0]

        # ---- Step 2: EFetch (PMID → Metadata) ----
        params = {
            "db": "pubmed",
            "id": pmid,
            "retmode": "xml"
        }

        r = requests.get(EFETCH_URL, params=params, timeout=10)
        r.raise_for_status()
        # print(r.text)
        root = ET.fromstring(r.text)

        doi_element = root.find(".//ArticleId[@IdType='doi']")
        if doi_element is not None:
            if getDOI(doi).lower() == getDOI(doi_element.text).lower():

                article = root.find(".//Article")
                journal = article.find("Journal") if article is not None else None

                # helper function
                def safe_text(value):
                    return value.strip() if value and value.strip() else "Not available"

                # ---- title ----
                title = safe_text(article.findtext("ArticleTitle") if article is not None else None)

                # ---- authors ----
                authors = []
                if article is not None:
                    for a in article.findall(".//Author"):
                        last = a.findtext("LastName")
                        fore = a.findtext("ForeName")
                        name = " ".join(filter(None, [fore, last])).strip()
                        if name:
                            authors.append(name)

                if not authors:
                    authors = ["Not available"]

                # ---- journal info ----
                issue = safe_text(journal.findtext("JournalIssue/Issue") if journal is not None else None)
                volume = safe_text(journal.findtext("JournalIssue/Volume") if journal is not None else None)
                pages = safe_text(article.findtext("Pagination/MedlinePgn") if article is not None else None)
                publisher = safe_text(journal.findtext("Title") if journal is not None else None)

                # ---- year ----
                year_value = (
                    journal.findtext("JournalIssue/PubDate/Year") if journal is not None else None
                ) or (
                    journal.findtext("JournalIssue/PubDate/MedlineDate") if journal is not None else None
                )

                year = safe_text(year_value)

                return True, {
                    "source": "PubMed",
                    "doi": safe_text(doi_element.text),
                    "title": title,
                    "authors": authors,
                    "issue": issue,
                    "volume": volume,
                    "year": year,
                    "pages": pages,
                    "publisher": publisher,
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                }
    return False, {}  # No matching DOI found in results

def pubmed_search_by_title(title, retmax=5):
    params = {
        "db": "pubmed",
        "term": f"{title}[Title]",
        "retmode": "json",
        "retmax": retmax,
        "email": PUBMED_EMAIL
    }
    r = requests.get(PUBMED_BASE_URL + "esearch.fcgi", params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    return data["esearchresult"]["idlist"]


def pubmed_summary(pmids):
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
        "email": PUBMED_EMAIL
    }
    r = requests.get(PUBMED_BASE_URL + "esummary.fcgi", params=params, timeout=10)
    r.raise_for_status()
    data = r.json()["result"]

    results = []
    for pmid in pmids:
        
        item = data.get(pmid, {})
        # print(item)
        results.append({
            "source": "PubMed",
            "pmid": pmid,
            "title": item.get("title"),
            "volume": item.get("volume"),
            "issue": item.get("issue"),
            "pages": item.get("pages"),
            "doi": item.get("elocationid").replace('doi: ',''),
            "conference_journal": item.get("fulljournalname"),
            "year": item.get("pubdate", "")[:4],
            "authors": [a["name"] for a in item.get("authors", [])]
        })
    return results

def parse_openalex_work(work):

    first_page = work.get("biblio", {}).get('first_page')
    last_page = work.get("biblio", {}).get('last_page')
    return {
        # "id": work.get("id"),
        "source": "Open Alex",
        "doi": work.get("doi"),
        "title": work.get("title"),
        "year": work.get("publication_year"),
        "conference_journal": work.get("publisher"),
        "issue": work.get("biblio", {})
                        .get("issue"),
        "volume": work.get("biblio", {})
                        .get("volume"),
        "pages": f"{first_page}-{last_page}" if first_page and last_page else None ,
        # "venue": work.get("primary_location", {})
        #                 .get("source", {})
        #                 .get("display_name"),
        "authors": [
            a["author"]["display_name"]
            for a in work.get("authorships", [])
        ],
        "url": work.get("primary_location", {})
                        .get("pdf_url")

    }


def openalex_search_by_title(title, per_page=5):
    url = f"{OPENALEX_BASE_URL}/works"
    params = {
        "search": title,
        "per-page": per_page,
        "mailto": OPENALEX_EMAIL
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()

    return r.json()["results"]

def openalex_get_by_doi(doi):
    doi = doi.lower().replace("https://doi.org/", "")
    url = f"{OPENALEX_BASE_URL}/works/doi:{doi}"
    params = {"mailto": OPENALEX_EMAIL}
    r = requests.get(url, params=params, timeout=10)

    if r.status_code == 404:
        return False, None
    r.raise_for_status()
    return True, r.json()

def aiforthai_search_by_title(title):
  url = "https://www.tci-thaijo.org/api/articles/search/"

  payload = json.dumps({
    "term": title,
    "page": 2,
    "size": 20,
    "strict": False,
    "title": True,
    "author": True,
    "abstract": False
  })
  headers = {
    'content-type': 'application/json'
  }

  r = requests.request("POST", url, headers=headers, data=payload)
  r.raise_for_status()
  return r.json()["result"]



def thaijo_to_reference(record: dict) -> dict:
    # ---- DOI ----
    doi = record.get("pubIdDoi") or None

    # ---- Title ----
    title = (
        record.get("title", {})
        .get("en_US")
    )

    # ---- Authors ----
    authors = []
    for a in record.get("authors", []):
        name = a.get("full_name", {}).get("en_US")
        if name:
            authors.append(name)

    # ---- Issue / Volume ----
    issue = record.get("issue_id")
    volume = None  # ThaiJO usually does not expose volume directly

    # ---- Year ----
    year = None
    date_published = record.get("datePublished")
    if date_published:
        year = date_published[:4]

    # ---- Pages ----
    pages = record.get("pages")

    # ---- Publisher (Journal name) ----
    publisher = (
        record.get("copyrightHolder", {})
        .get("en_US")
    )

    # ---- URL ----
    url = record.get("articleUrl")

    return {
        "source": "AIForThai",
        "doi": doi,
        "title": title,
        "authors": authors,
        "issue": issue,
        "volume": volume,
        "year": year,
        "pages": pages,
        "conference_journal": publisher,
        "url": url
    }


def datacite_get_metadata(doi: str):
    # normalize DOI
    doi = doi.replace("https://doi.org/", "").strip()
    url = f"{DATACITE_API}{doi}"

    r = requests.get(url, headers=DATACITE_HEADERS, timeout=10)
    if r.status_code != 200:
        return False, None

    data = r.json()["data"]
    attr = data["attributes"]

    # ---- title ----
    title = None
    titles = attr.get("titles", [])
    if titles:
        title = titles[0].get("title")

    # ---- authors ----
    authors = []
    for c in attr.get("creators", []):
        if "name" in c:
            authors.append(c["name"])
        else:
            given = c.get("givenName")
            family = c.get("familyName")
            name = " ".join(filter(None, [given, family]))
            if name:
                authors.append(name)

    # ---- year ----
    year = None
    pub_year = attr.get("publicationYear")
    if pub_year:
        year = int(pub_year)

    return True, {
        "source": "Data cite",
        "doi": attr.get("doi"),
        "title": title,
        "authors": authors,
        "issue": None,          # DataCite มักไม่มี issue
        "volume": None,         # DataCite มักไม่มี volume
        "year": year,
        "pages": None,          # DataCite มักไม่มี pages
        "publisher": attr.get("publisher"),
        "url": attr.get("url")
    }

def clean_tags_and_entities(text):
    # 1. แปลง Entity (เช่น &lt; เป็น <) ให้กลับมาเป็น Tag ปกติก่อน
    text = html.unescape(str(text))
    # 2. ใช้ Regex ลบทุกอย่างที่อยู่ในวงเล็บแหลม <...> ออก
    clean_text = re.sub(r'<[^>]+>', '', text)
    # 3. ตัดช่องว่างส่วนเกิน
    return clean_text.strip()

def clean_for_compare(text):
    if not text: return ""
    if isinstance(text, (int, float)):
        text = str(text)  # ให้แปลงเป็น text
    # 1. จัดการภาษาไทย
    text = thai_normalize(text)
    # 2. จัดการ Unicode มาตรฐาน
    text = unicodedata.normalize('NFKC', text)
    text = clean_tags_and_entities(text)
    text = "".join(char for char in text if char.isalnum())
    # 3. ทำเป็นตัวพิมพ์เล็ก (สำหรับภาษาอังกฤษ)
    return text.lower()


def meta_available(meta_object,key):
    if not key in meta_object: return False
    text = meta_object[key]
    if not text: return False
    if isinstance(text, (int, float)):
        text = str(text)  # ให้แปลงเป็น text
    if text == "Not available":
        return False
    return True

def compare_exit_match(meta_object,llm_object,key):
    if meta_available(meta_object,key):
        if not key in llm_object: llm_object[key] = ''
        resStr_meta = clean_for_compare(meta_object[key])
        resStr_llm = clean_for_compare(llm_object[key])
        if re.fullmatch(r'\d+', resStr_meta) and re.fullmatch(r'\d+', resStr_llm):
            resStr_meta = int(resStr_meta)
            resStr_llm = int(resStr_llm)
        if resStr_meta != resStr_llm:
            return 0
        else:
            return 1
    return -1
def compare_sequence_matcher(meta_object,llm_object,key):
    if meta_available(meta_object,key) and meta_available(llm_object,key):
        if not key in llm_object: llm_object[key] = ''
        return SequenceMatcher(None
            , clean_for_compare(meta_object[key]) 
            , clean_for_compare(llm_object[key])).ratio()
    return -1
def compare_jaroWinkler(meta_object,llm_object,key):
    if meta_available(meta_object,key) and meta_available(llm_object,key):
        if not key in llm_object: llm_object[key] = ''
        if isinstance(meta_object[key], list):
            meta_object[key] = ', '.join(meta_object[key])
        if isinstance(llm_object[key], list):
            llm_object[key] = ', '.join(llm_object[key])
        return JaroWinkler.similarity(
            clean_for_compare(', '.join(meta_object[key]))
            , clean_for_compare(llm_object[key]) 
                )
    return -1
def compare_subset(meta_object,llm_object,key):
    if meta_available(meta_object,key) and meta_available(llm_object,key):
        if not key in llm_object: llm_object[key] = ''
        a = clean_for_compare(meta_object[key]) 
        b = clean_for_compare(llm_object[key])
        if a in b or b in a:
            return 1
        else:
            return 0
    return -1


def _check_crossref(doi):
    exists, meta = crossref_check_doi_exists(doi)
    if exists:
        return True, crossref_get_metadata_from_doi(meta)
    return False, None

def _check_semantic_scholar(doi):
    return semantic_scholar_check_doi_exists(doi)

def _check_openalex(doi):
    exists, meta = openalex_get_by_doi(doi)
    if exists:
        return True, parse_openalex_work(meta)
    return False, None

def _check_pubmed(doi):
    return pubmed_get_metadata_by_doi(doi)

def _check_datacite(doi):
    return datacite_get_metadata(doi)


def check_doi_exists_mutithread(doi=None):
    if not doi or doi == "Not available":
        return False, {}

    doi = doi.lower().replace("https://doi.org/", "")

    checkers = [
        _check_crossref,
        _check_semantic_scholar,
        _check_openalex,
        _check_pubmed,
        _check_datacite,
    ]

    with ThreadPoolExecutor(max_workers=len(checkers)) as executor:
        futures = {
            executor.submit(checker, doi): checker
            for checker in checkers
        }

        for future in as_completed(futures):
            try:
                exists, meta = future.result()
                if exists:
                    # ยกเลิกงานที่เหลือทั้งหมด
                    for f in futures:
                        f.cancel()
                    return True, meta
            except Exception:
                pass  # กันพังจาก source ใด source หนึ่ง

    return False, {}

def compare_title(metaJson,extractJson):
    maxPoint = 0
    res_mata = {}
    for meta in metaJson:
        resPoint = 0
        count = 0
        for key in ['title','conference_journal']:
            if key in  meta:
                # print(result[key])
                res = compare_sequence_matcher(meta,extractJson,key)
                # print(res)
                if  res >=0 :
                    count += 1
                    resPoint += res
        for key in ['year','volume','issue']:
            if key in  meta:
                # print(result[key])
                res = compare_exit_match(meta,extractJson,key)
                # print(res)
                if  res >=0 :
                    count += 1
                    resPoint += res
        if count > 0 and (resPoint/count) > maxPoint:
            # print(resPoint,count,resPoint/count)
            maxPoint = (resPoint/count)
            res_mata = meta
    return maxPoint,res_mata

def _check_title_crossref(title,orgJson):
    results = crossref_search_by_title(title)
    point, mete_title = compare_title(results,orgJson)
    if 'doi' in mete_title:
        exists, meta = check_doi_exists_mutithread(mete_title['doi'])
        if exists:
            return True, point, meta
    return False, point, mete_title

def _check_title_semantic_scholar(title,orgJson):
    results = semantic_scholar_search_by_title(title)
    point, mete_title = compare_title(results,orgJson)
    if 'doi' in mete_title:
        exists, meta = check_doi_exists_mutithread(mete_title['doi'])
        if exists:
            return True, point, meta
    return False, point, mete_title

def _check_title_openalex(title,orgJson):
    meta = openalex_search_by_title(title)
    results = []
    for res in meta:
        if res:
            work = parse_openalex_work(res)
            results.append(work)
    point, mete_title = compare_title(results,orgJson)
    if 'doi' in mete_title:
        exists, meta = check_doi_exists_mutithread(mete_title['doi'])
        if exists:
            return True, point, meta
    return False, point, mete_title

def _check_title_pubmed(title,orgJson):
    pmids = pubmed_search_by_title(title)
    results = []
    if len(pmids) > 0:
        results = pubmed_summary(pmids)
    point, mete_title = compare_title(results,orgJson)
    if 'doi' in mete_title:
        exists, meta = check_doi_exists_mutithread(mete_title['doi'])
        if exists:
            return True, point, meta
    return False, point, mete_title

def _check_title_thaijo(title,orgJson):
    meta = aiforthai_search_by_title(title)
    results = []
    for res in meta:
        if res:
            work = thaijo_to_reference(res)
            results.append(work)
    point, mete_title = compare_title(results,orgJson)
    if 'doi' in mete_title:
        exists, meta = check_doi_exists_mutithread(mete_title['doi'])
        if exists:
            return True, point, meta
    return False, point, mete_title


def check_title_exists_mutithread(title, orgJson):
    if not title or title == "Not available":
        return False, None
    title = title.strip()
    checkers = [
        _check_title_crossref,
        _check_title_semantic_scholar,
        _check_title_openalex,
        _check_title_pubmed,
        _check_title_thaijo,
    ]

    with ThreadPoolExecutor(max_workers=len(checkers)) as executor:
        futures = {
            executor.submit(checker, title, orgJson): checker
            for checker in checkers
        }
        maxPoint = 0
        bestMeta = {}
        for future in as_completed(futures):
            try:
                exists ,point, meta = future.result()
                if  point > maxPoint:
                    maxPoint = point
                    bestMeta = meta
                if exists:
                    # ยกเลิกงานที่เหลือทั้งหมด
                    for f in futures:
                        f.cancel()
                    return True, point, meta
            except Exception:
                pass  # กันพังจาก source ใด source หนึ่ง
        if maxPoint > 0:
            return True, maxPoint, bestMeta
    return False, 0, {}
def verify_reference_json(extractJson):
    if extractJson['doi'] == 'Not available' or not extractJson['doi']:
        status, point, meta = check_title_exists_mutithread(extractJson['title'], extractJson)
    else:
        status, meta = check_doi_exists_mutithread(extractJson['doi'])

    result_meta = {}
    result_point = {}
    count = 0
    resPoint = 0
    if meta and meta != {}:
        for key in ['authors']:
            if key in meta:
                result_meta[key] = meta[key]
                res = compare_jaroWinkler(extractJson,meta,key)
                result_point[key] = res
                if  res >=0 :
                    count += 1
                    resPoint += res
            else:
                result_meta[key] = 'Not available'
        for key in ['title','conference_journal']:
            if key in meta:
                result_meta[key] = meta[key]
                res = compare_sequence_matcher(extractJson,meta,key)
                result_point[key] = res
                if  res >=0 :
                    count += 1
                    resPoint += res
            else:
                result_meta[key] = 'Not available'
        for key in ['year','volume','issue']:
            if key in meta:
                result_meta[key] = meta[key]
                res = compare_exit_match(extractJson,meta,key)
                result_point[key] = res
                if  res >=0 :
                    count += 1
                    resPoint += res
            else:
                result_meta[key] = 'Not available'
        for key in ['doi']:
            if key in meta:
                result_meta[key] = meta[key]
            else:
                result_meta[key] = 'Not available'
        if "source" in meta:
            result_meta["source"] = meta["source"]
        return resPoint,count,result_meta, result_point
    else:
        return 0,0,{},{}

def verify_reference(extract_list):
    results = []
    try:
        for extractJson in extract_list:
            if "validRef" in extractJson and extractJson['validRef'] == 'Yes':
                point, count,meta, point_obj = verify_reference_json(extractJson)
        
                final_score = (point/count) if count > 0 else 0
                if "source" in meta:
                    extractJson["source"] = "Extraction"
                results.append({
                    "final_score": final_score,
                    "extracted": extractJson,
                    "metadata": meta,
                    "point_details": point_obj
                })
            else:
                results.append({
                    "final_score": -1,
                    "extracted": {},
                    "metadata": {},
                    "point_details": {}
                })
        if results != []:
            return {"status": 1, "result": results}
        return({"status": 0,"result":[]})
    except Exception as e:
        return({"status": -1,"result":[]})

# orgJson = {'status': 1,
#  'result': [{'text': 'S. Lee, H. Chang and J. Lee, Construction and demolition waste management and its impacts on the environment and human health: Moving forward sustainability enhancement, Sustainable Cities and Society, 2024, 115, 105855.',
#    'authors': 'S. Lee, H. Chang, J. Lee',
#    'title': 'Construction and demolition waste management and its impacts on the environment and human health: Moving forward sustainability enhancement',
#    'publication_type': 'journal article',
#    'conference_journal': 'Sustainable Cities and Society',
#    'conference_number': 'Not available',
#    'year': '2024',
#    'month': 'Not available',
#    'pages': '105855',
#    'volume': '115',
#    'issue': 'Not available',
#    'publisher': 'Not available',
#    'location': 'Not available',
#    'doi': 'Not available',
#    'isbn_issn': 'Not available',
#    'url': 'Not available',
#    'editors': 'Not available',
#    'organization': 'Not available'}]}

# print(json.dumps(verify_reference(orgJson['result']), indent=2, ensure_ascii=False))
