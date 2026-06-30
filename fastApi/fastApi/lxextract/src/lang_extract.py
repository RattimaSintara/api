import re

import langextract as lx
import textwrap
import os
import json
import requests
from openai import OpenAI

def get_openai_client():
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    return OpenAI(api_key=api_key, base_url=base_url)


# 1. กำหนด prompt ว่าต้องการ extract อะไร
prompt_sys = textwrap.dedent("""
    You are given an academic reference.

    Extract all bibliographic metadata that can be explicitly identified from the reference.
    If a field is not present, indicate "Not available".

    Consider (but are not limited to) the following fields and return the result in the following JSON format:

    - validRef: Check if the text is a reference, Answer "Yes" if yes, and "No" if no, and do not extract any other fields.
    - authors: Names of all authors of the publication, listed in the order they appear.
    - title: Title of the paper, article, book, thesis, or report.
    - publication_type: Type of publication, such as conference paper, journal article, book, thesis, or technical report, if available.
    - conference_journal: Name of the conference or journal where the work was published.
    - conference_number: Conference edition number or book edition (e.g., 13th, 3rd edition), if available.
    - year: Year of publication.
    - month: Month of publication, if explicitly stated, if available.
    - pages: Page range of the publication (e.g., 123–130), if available.
    - volume: Volume number of the journal or book series, if available.
    - issue: Issue or number of the journal or conference proceedings, if available.
    - publisher: Name of the publisher or publishing organization, if available.
    - location: Place of publication or conference location (city and/or country), if available.
    - doi: Digital Object Identifier of the publication, if available.
    - isbn_issn: International Standard Book Number (ISBN) or International Standard Serial Number (ISSN), if available.
    - url: URL where the publication or online resource can be accessed, if available.
    - editors: Names of editors, typically for books or edited conference proceedings, if available.
    - organization: Organization or institution responsible for publishing, sponsoring, or hosting the work, if available.
    
    Use exact text from the source. Do not paraphrase.
    Do not infer or guess missing information.
""")
def loadExample(fileName):
    with open(fileName, "r", encoding="utf-8") as f:
        data = json.load(f)

    examples = []
    for item in data:
        extractions = []
        for ext in item["extractions"]:
            extractions.append(
                lx.data.Extraction(
                    extraction_class=ext["extraction_class"],
                    extraction_text=ext["extraction_text"],
                    attributes=ext["attributes"]
                )
            )
        examples.append(
            lx.data.ExampleData(
                text=item["text"],
                extractions=extractions
            )
        )
    return examples
# examples_sys = loadExample("/opt/data/Project/TCI/RefExtraction/Evaluation/LLM/lxextract/input/examples_data_few.json")
# # 2. ให้ตัวอย่างที่ดี (few-shot example)
examples_sys = [
    lx.data.ExampleData(
        text="[1] Smith J., Brown L., and Chen Y. Advances in Large Language Models for Bibliographic Reference Extraction. In Proceedings of the 15th International Conference on Document Analysis and Recognition (ICDAR 2023), Paris, France, July 2023. Springer, Lecture Notes in Computer Science, Vol. 14123, No. 2, pp. 120–135. DOI: 10.1007/978-3-031-12345-6_9. ISBN: 978-3-031-12345-6. Available at: https://link.springer.com/chapter/10.1007/978-3-031-12345-6_9. Edited by D. Lopresti and G. Nagy. Sponsored by IAPR.",
        extractions=[
            lx.data.Extraction(
                extraction_class="reference",
                extraction_text="[1] Smith J., Brown L., and Chen Y. Advances in Large Language Models for Bibliographic Reference Extraction. In Proceedings of the 15th International Conference on Document Analysis and Recognition (ICDAR 2023), Paris, France, July 2023. Springer, Lecture Notes in Computer Science, Vol. 14123, No. 2, pp. 120–135. DOI: 10.1007/978-3-031-12345-6_9. ISBN: 978-3-031-12345-6. Available at: https://link.springer.com/chapter/10.1007/978-3-031-12345-6_9. Edited by D. Lopresti and G. Nagy. Sponsored by IAPR.",
                attributes={
                    "validRef":"Yes",
                    "authors": "Smith J., Brown L., Chen Y.",
                    "title": "Advances in Large Language Models for Bibliographic Reference Extraction",
                    "publication_type": "conference paper",
                    "conference_journal": "International Conference on Document Analysis and Recognition (ICDAR)",
                    "conference_number": "15th",
                    "year": "2023",
                    "month": "July",
                    "pages": "120–135",
                    "volume": "14123",
                    "issue": "2",
                    "publisher": "Springer",
                    "location": "Paris, France",
                    "doi": "10.1007/978-3-031-12345-6_9",
                    "isbn_issn": "ISBN 978-3-031-12345-6",
                    "url": "https://link.springer.com/chapter/10.1007/978-3-031-12345-6_9",
                    "editors": "D. Lopresti, G. Nagy",
                    "organization": "International Association for Pattern Recognition (IAPR)"
                }
            )
        ]
    )
]

examples_fewShort = [
    { 
        "text": "[1] Smith J., Brown L., and Chen Y. Advances in Large Language Models for Bibliographic Reference Extraction. In Proceedings of the 15th International Conference on Document Analysis and Recognition (ICDAR 2023), Paris, France, July 2023. Springer, Lecture Notes in Computer Science, Vol. 14123, No. 2, pp. 120–135. DOI: 10.1007/978-3-031-12345-6_9. ISBN: 978-3-031-12345-6. Available at: https://link.springer.com/chapter/10.1007/978-3-031-12345-6_9. Edited by D. Lopresti and G. Nagy. Sponsored by IAPR.",
        "extractions" : {
            "validRef": "Yes",
            "authors": "Smith J., Brown L., and Chen Y.",
            "title": "Advances in Large Language Models for Bibliographic Reference Extraction",
            "publication_type": "conference paper",
            "conference_journal": "International Conference on Document Analysis and Recognition (ICDAR)",
            "conference_number": "15th",
            "year": "2023",
            "month": "July",
            "pages": "120–135",
            "volume": "14123",
            "issue": "2",
            "publisher": "Springer",
            "location": "Paris, France",
            "doi": "10.1007/978-3-031-12345-6_9",
            "isbn_issn": "ISBN 978-3-031-12345-6",
            "url": "https://link.springer.com/chapter/10.1007/978-3-031-12345-6_9",
            "editors": "D. Lopresti, G. Nagy",
            "organization": "International Association for Pattern Recognition (IAPR)"
        }
    },
    {
        "text": "[7] Anderson P., Müller T., and Wong K. Hybrid Neural Approaches for Multilingual Reference Extraction. In Proceedings of the 12th International Conference on Language Resources and Evaluation (LREC 2024), Marseille, France, May 2024, pp. 1023–1034. Volume 2, Issue 1. European Language Resources Association (ELRA). Edited by N. Calzolari and K. Choukri. DOI: 10.5555/lrec.2024.1023. ISBN: 978-2-9517408-0-0. Available at: https://www.lrec-conf.org/proceedings/lrec2024/1023.",
        "extractions": 
        {
            "validRef": "Yes",
            "authors": "Anderson P., Müller T., Wong K.",
            "title": "Hybrid Neural Approaches for Multilingual Reference Extraction",
            "publication_type": "conference paper",
            "conference_journal": "International Conference on Language Resources and Evaluation (LREC)",
            "conference_number": "12th",
            "year": "2024",
            "month": "May",
            "pages": "1023–1034",
            "volume": "2",
            "issue": "1",
            "publisher": "European Language Resources Association (ELRA)",
            "location": "Marseille, France",
            "doi": "10.5555/lrec.2024.1023",
            "isbn_issn": "ISBN 978-2-9517408-0-0",
            "url": "https://www.lrec-conf.org/proceedings/lrec2024/1023",
            "editors": "N. Calzolari, K. Choukri",
            "organization": "European Language Resources Association (ELRA)"
            
        }
        
    },
    {
        "text": "[8] กิตติพงษ์ สุวรรณชัย และ พัชรี รัตนาภรณ์. การพัฒนาแบบจำลองภาษาขนาดใหญ่เพื่อการวิเคราะห์บรรณานุกรมภาษาไทย. วารสารวิจัยปัญญาประดิษฐ์และวิทยาการข้อมูล, ปีที่ 7, ฉบับที่ 3, หน้า 88–105, ธันวาคม 2566. มหาวิทยาลัยเทคโนโลยีพระจอมเกล้าธนบุรี, กรุงเทพฯ, ประเทศไทย. DOI: 10.14456/jaiads.2023.15. ISSN: 2985-1234. Available at: https://jaiads.kmutt.ac.th/article/2023-15.",
        "extractions": 
        {
            "validRef": "Yes",
            "authors": "กิตติพงษ์ สุวรรณชัย, พัชรี รัตนาภรณ์",
            "title": "การพัฒนาแบบจำลองภาษาขนาดใหญ่เพื่อการวิเคราะห์บรรณานุกรมภาษาไทย",
            "publication_type": "journal article",
            "conference_journal": "วารสารวิจัยปัญญาประดิษฐ์และวิทยาการข้อมูล",
            "conference_number": "Not available",
            "year": "2023",
            "month": "ธันวาคม",
            "pages": "88–105",
            "volume": "7",
            "issue": "3",
            "publisher": "มหาวิทยาลัยเทคโนโลยีพระจอมเกล้าธนบุรี",
            "location": "กรุงเทพฯ, ประเทศไทย",
            "doi": "10.14456/jaiads.2023.15",
            "isbn_issn": "ISSN 2985-1234",
            "url": "https://jaiads.kmutt.ac.th/article/2023-15",
            "editors": "Not available",
            "organization": "มหาวิทยาลัยเทคโนโลยีพระจอมเกล้าธนบุรี"
        }
    }
]

examples_prompt_oneShort = f"""
### Example ###
Input:
{examples_fewShort[0]['text']}
Output:
{json.dumps(examples_fewShort[0]['extractions'], indent=2, ensure_ascii=False)}
### End Example ###
"""

examples_prompt_fewShort = ""
for i, ex in enumerate(examples_fewShort, 1):
    examples_prompt_fewShort += f"""
### Example {i} ###
Input:
{ex['text']}
Output:
{json.dumps(ex['extractions'], ensure_ascii=False, indent=2)}
### End Example {i} ###
"""
    
def print_extraction_details(result):
    references_list = []
    for i, extraction in enumerate(result.extractions, 1):
        # เก็บเป็น dict
        references_list.append({
            "text": extraction.extraction_text,
            "validRef": extraction.attributes.get("validRef"),
            "authors": extraction.attributes.get("authors"),
            "title": extraction.attributes.get("title"),
            "publication_type": extraction.attributes.get("publication_type"),
            "conference_journal": extraction.attributes.get("conference_journal"),
            "conference_number": extraction.attributes.get("conference_number"),
            "year": extraction.attributes.get("year"),
            "month": extraction.attributes.get("month"),
            "pages": extraction.attributes.get("pages"),
            "volume": extraction.attributes.get("volume"),
            "issue": extraction.attributes.get("issue"),
            "publisher": extraction.attributes.get("publisher"),
            "location": extraction.attributes.get("location"),
            "doi": extraction.attributes.get("doi"),
            "isbn_issn": extraction.attributes.get("isbn_issn"),
            "url": extraction.attributes.get("url"),
            "editors": extraction.attributes.get("editors"),
            "organization": extraction.attributes.get("organization")
        })
    return references_list

# def lx_extract_ollama(text,model="llama3:latest"):
#     if not isinstance(text, str):
#         text = str(text)
#     try:
#         result = lx.extract(
#             text_or_documents=text,
#             prompt_description=prompt_sys,
#             examples=examples_sys,
#             model_id=model,
#             temperature=0,
#             model_url="http://localhost:11434"  # URL ของ Ollama server
#         )
#         if result != []:
#             return {"status": 1,"result":print_extraction_details(result)}
#         return({"status": 0,"result":[]})
#     except Exception as e:
#         return({"status": -1,"result":[]})
    
PROMPT_TEMPLATE_Ollama = prompt_sys + """ 

    {example_blocks} 
    
    Input:
    \"\"\"{input_text}\"\"\"
    Output:
"""

def safe_json_load(text):
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        json_str = match.group(0)
        return json.loads(json_str)
    else:
        raise ValueError("No JSON object found")
OLLAMA_URL = "http://localhost:11434/api/generate"
def lx_extract_ollama(text,model):
    prompt = PROMPT_TEMPLATE_Ollama.format(input_text=text, example_blocks=examples_prompt_fewShort)
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",  # บังคับ JSON mode
            "options": {
                "temperature": 0  # เพิ่มบรรทัดนี้เพื่อคุมความนิ่งของคำตอบ
            }
        }
    )
    try:
        response.raise_for_status() 

        result = response.json()["response"]

        res_json = safe_json_load(result)
        # res_json = json.loads(result)
        if "authors" in res_json:
            if isinstance(res_json["authors"], list):
                res_json["authors"] = ', '.join(res_json["authors"])
        return {"status": 1,"result":[res_json]} if res_json else {"status": 0,"result":[]} 
    except Exception as e:
        return({"status": -1,"result":[]})
# ===================================================================================

def lx_extract(text,model="gpt-4.1-mini"):
    try:
        resp = get_openai_client().chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": prompt_sys},
                {"role": "user", "content": examples_prompt_oneShort},
                {"role": "user", "content": text}
            ]
        )
        content = resp.choices[0].message.content
        # # แปลงเป็น dict
        extracted_data = safe_json_load(content)
        if "authors" in extracted_data:
            if isinstance(extracted_data["authors"], list):
                extracted_data["authors"] = ', '.join(extracted_data["authors"])

        # print(json.dumps(extracted_data, indent=4, ensure_ascii=False))
        return {"status": 1,"result":[extracted_data]} if extracted_data else {"status": 0,"result":[]} 
        
    except Exception as e:
        return({"status": -1,"result":[]})
