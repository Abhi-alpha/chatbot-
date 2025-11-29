import datetime as dt
from app.db import SessionLocal
from app.models import Insurer, Product, PolicyVersion

db = SessionLocal()
try:
    ins = Insurer(name="Acko General Insurance Limited ")
    db.add(ins); db.flush()

    prod = Product(insurer_id=ins.id, line_of_business="health", name="Acko Health Insurance Policy")
    db.add(prod); db.flush()

    ver = PolicyVersion(product_id=prod.id,uin ="ACKHLIP20039V012021", version_label="FY2021", effective_from=dt.date(2024,4,1), status="active")
    db.add(ver); db.commit()
    print("Seeded:", ins.id, prod.id, ver.id) 
    #Seeded1: 0eabeb57-1393-4145-9b1e-40b6633d6dba 82d7d45a-a300-4359-9d7a-2d83065adef8 f07d77c2-021c-4367-91ad-5d9aa5137ef8
    #seeded2: a278a4bf-d0e9-4a59-bbd1-822ba9ec9f2d 0f8916d6-c76b-4db2-8938-ed4f516ce6d9 98224b6a-5d68-4d13-8a92-6cf429c6b803
    #d2e2be4b-ce88-4b48-a82c-949047e59035 29005be8-7003-49ce-ad71-e17fd99f2e22 ac1e8b34-58d9-4157-a74d-c13f6c388d2e
finally:
    db.close()