import os, json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
text = "Sum Insured Basis?"  # your test question
pvid = 'ACKHLIP20039V012021'

emb = client.embeddings.create(model="text-embedding-3-small", input=[text]).data[0].embedding
print(len(emb))                 # should print 1536
print("'" + json.dumps(emb) + "'")

smt = f""" SELECT
          c.id,
          c.section_id,
          c.page_from,
          c.page_to,
          c.content,
          d.source_uri AS document_pdf,
          c.embedding
        FROM policy_chunk c
        JOIN policy_document d ON d.id = c.document_id
        WHERE c.policy_version_id = {pvid}
        ORDER BY c.embedding <=> {emb}    -- cosine distance
        LIMIT 100 ; """

with open("output.txt", "w") as file:
    file.write(smt)