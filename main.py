from fastapi import *
from fastapi.templating import Jinja2Templates
from fastapi.responses import *
from fastapi.staticfiles import StaticFiles
from pymongo import MongoClient
from bson import ObjectId
from pydantic import BaseModel
from typing import Callable
from uuid import UUID, uuid4
from fastapi_sessions.backends.implementations import InMemoryBackend
from fastapi_sessions.session_verifier import SessionVerifier
from fastapi_sessions.frontends.implementations import SessionCookie, CookieParameters
from typing import List, Dict
import json, os
import uvicorn
from functools import wraps
import hashlib

from datetime import datetime
import pytz

from models import *
from utils import *

cookie_params = CookieParameters()

# Uses UUID
cookie = SessionCookie(
    cookie_name="cookie",
    identifier="general_verifier",
    auto_error=True,
    secret_key="DONOTUSE",
    cookie_params=cookie_params,
)
backend = InMemoryBackend[UUID, SessionData]()


class BasicVerifier(SessionVerifier[UUID, SessionData]):
    def __init__(
        self,
        *,
        identifier: str,
        auto_error: bool,
        backend: InMemoryBackend[UUID, SessionData],
        auth_http_exception: HTTPException,
    ):
        self._identifier = identifier
        self._auto_error = auto_error
        self._backend = backend
        self._auth_http_exception = auth_http_exception

    @property
    def identifier(self):
        return self._identifier

    @property
    def backend(self):
        return self._backend

    @property
    def auto_error(self):
        return self._auto_error

    @property
    def auth_http_exception(self):
        return self._auth_http_exception

    def verify_session(self, model: SessionData) -> bool:
        """If the session exists, it is valid"""
        return True


verifier = BasicVerifier(
    identifier="general_verifier",
    auto_error=True,
    backend=backend,
    auth_http_exception=HTTPException(status_code=403, detail="invalid session"),
)

def role_verifier(role: str = "*"):
    async def check_role(session_data: SessionData = Depends(verifier)):
        if role != "*" and ("role" not in session_data.data or session_data.data["role"] != role):
            raise HTTPException(status_code=403, detail="Unauthorized access")
        return session_data
    return check_role

def is_valid_objectid(id: str) -> bool:
    try:
        ObjectId(id)
        return True
    except:
        return False

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
os.makedirs("static/patient_docs", exist_ok=True)
templates = Jinja2Templates(directory="templates")

# MongoDB connection setup
MONGO_URI = "mongodb+srv://flask-access:qwertyuiop@vitalink.ykzz1.mongodb.net/?retryWrites=true&w=majority&appName=db"
client = MongoClient(MONGO_URI)
db = client.get_database("testdb")  # replace with your database name
collection = db.get_collection("items")


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Redirect based on login status and role."""
    return RedirectResponse(url="/login", status_code=302)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Display the login page."""
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=HTMLResponse)
async def login(response: Response, request: Request, username: str = Form(...), password: str = Form(...)):
    """Handle user login and set session variables."""
    # Replace with actual user authentication
    if username == "admin" and password == "admin123":
        session = uuid4()
        data = SessionData(data={"name": username, "role": "admin"})

        await backend.create(session, data)
        cookie.attach_to_response(response, session)
    
        return '<meta http-equiv="refresh" content="0; url=/">'

    elif "DOC" in username:
        user = collection.find_one({"ID":username, "type":"Doctor"})
        if hashlib.sha512(password.encode('utf-8')).hexdigest() == user["passHash"]:
            session = uuid4()
            user2 = user.copy()
            user2.pop('passHash')
            user2.update({"role": "doctor"})
            data = SessionData(data=user2)

            await backend.create(session, data)
            cookie.attach_to_response(response, session)
        
            return '<meta http-equiv="refresh" content="0; url=/">'
        else:
            raise HTTPException(status_code=401, detail="Invalid credentials")

    elif "PAT" in username:
        patient = collection.aggregate([
            {
                "$match": {
                    "type": "Patient",
                    "ID": username
                }
            },
            {
                "$lookup": {
                    "from": "items",  # Join with the 'users' collection to get the doctor (caretaker)
                    "localField": "caretaker",  # The patient's caretaker ID
                    "foreignField": "ID",  # The doctor's ID
                    "as": "caretaker_info"  # Output will be in the 'caretaker_info' array
                }
            },
            {
                "$unwind": "$caretaker_info"  # Flatten the 'caretaker_info' array to access the fields
            },
            {
                "$addFields": {
                    "caretakerName": "$caretaker_info.fullName"  # Add the caretaker's full name to the patient document
                }
            }
        ])
        user = list(patient)[0]
        if password == user["contact"].replace(" ","").replace("+91",""):
            session = uuid4()
            user2 = user.copy()
            user2.update({"role": "patient"})
            data = SessionData(data=user2)

            await backend.create(session, data)
            cookie.attach_to_response(response, session)
        
            return '<meta http-equiv="refresh" content="0; url=/">'
        else:
            raise HTTPException(status_code=401, detail="Invalid credentials")

    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/logout")
async def logout(response: Response, request: Request, session_id: UUID = Depends(cookie)):
    await backend.delete(session_id)
    cookie.delete_from_response(response)
    return RedirectResponse(url="/login", status_code=302)

@app.get("/admin", response_class=HTMLResponse, dependencies=[Depends(cookie)])
async def read_root(request: Request, session_data: SessionData = Depends(role_verifier("admin"))):
    """Render the main page with all items."""
    items = list(collection.find())
    columns = set()

    # Collect all keys (columns) from each item
    for item in items:
        item["_id"] = str(item["_id"])  # Convert ObjectId to string
        columns.update(item.keys())  # Collect all keys from each item for the table headers
    
    # Reorder columns: first name columns, then ID, then others
    name_columns = [col for col in columns if (('name' in col.lower()) and ('kin' not in col.lower()) and ('side' not in col.lower()))]
    id_column = [col for col in columns if 'id' in col.lower()]
    type_column = [col for col in columns if 'type' in col.lower()]
    other_columns = [col for col in columns if col not in name_columns and col not in id_column and col not in type_column]

    # Create the final sorted column order
    sorted_columns = name_columns + id_column + type_column + other_columns

    return templates.TemplateResponse("admin.html", {"request": request, "items": items, "columns": sorted_columns})


@app.get("/item/update/{item_id}", dependencies=[Depends(cookie)])
async def get_item(item_id: str, session_data: SessionData = Depends(role_verifier("admin"))):
    """Fetch an item's details by its ID."""
    try:
        # Convert the item_id to ObjectId and fetch from the database
        item = collection.find_one({"_id": ObjectId(item_id)})
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        
        # Convert the ObjectId to string for JSON serialization
        item["_id"] = str(item["_id"])
        item.pop("_id")
        return item
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching item: {str(e)}")

@app.post("/item/create", dependencies=[Depends(cookie)])
async def create_item(item: Item, session_data: SessionData = Depends(role_verifier("admin"))):
    """Create a new item."""
    item = json.loads(item.item)
    collection.insert_one(item)
    return {"message": "Item created successfully"}


@app.post("/item/update/{item_id}", dependencies=[Depends(cookie)])
async def update_item(item_id: str, item: Item, session_data: SessionData = Depends(role_verifier("admin"))):
    """Update an existing item."""
    item = json.loads(item.item)
    result = collection.find_one_and_update(
        {"_id": ObjectId(item_id)}, {"$set": item}, return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Item not found")
    result["_id"] = str(result["_id"])
    return {"message": "Item updated successfully"}


@app.post("/item/delete/{item_id}", dependencies=[Depends(cookie)])
async def delete_item(item_id: str, session_data: SessionData = Depends(role_verifier("admin"))):
    """Delete an item."""
    result = collection.delete_one({"_id": ObjectId(item_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"message": "Item deleted successfully"}

@app.get("/doctor", response_class=HTMLResponse, dependencies=[Depends(cookie)])
async def doctor_root(request: Request, session_data: SessionData = Depends(role_verifier("doctor"))):
    """Render the view patients page with all patients."""
    patients = list(collection.aggregate([
        {
            "$match": {
                "type": "Patient",
                "doctor": session_data.data["ID"]
            }
        },
        {
            "$lookup": {
                "from": "items",  # Join with the 'db' collection to get the doctor (caretaker)
                "localField": "caretaker",  # The patient's caretaker ID
                "foreignField": "ID",  # The doctor's ID
                "as": "caretaker_info"  # Output will be in the 'caretaker_info' array
            }
        },
        {
            "$unwind": "$caretaker_info"  # Flatten the 'caretaker_info' array
        },
        {
            "$addFields": {
                "caretakerName": "$caretaker_info.fullName"  # Add the caretaker's full name to the patient document
            }
        },
        {
            "$project": {
                "caretakerName": 1,
                "name": 1,
                "doctor": 1,
                "ID": 1,
                "age": 1,
                "gender": 1
            }
        }
    ]))
    return templates.TemplateResponse("doctor/view_patients.html", {"request": request, "patients": patients, "user": session_data.data})

@app.get("/doctor/list-api", response_model=List[Doctor])
async def get_doctors():
    """
    Endpoint to fetch the list of doctors.
    """
    doctors = list(collection.find({"type": "Doctor"}, {"_id": 0, "fullName": 1, "ID": 1}))
    if not doctors:
        raise HTTPException(status_code=404, detail="No doctors found")
    return doctors

@app.post("/doctor/reassign/{patient_id}")
async def reassign_doctor(patient_id: str, doc: str = Query(..., description="New doctor ID"), typ: str = Query(..., description="Doctor or Caretaker?")):
    """
    Endpoint to reassign a doctor to a patient.
    """
    doctor = collection.find_one({"type": "Doctor", "ID": doc})
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    update_result = collection.update_one(
        {"type": "Patient", "ID": patient_id},
        {"$set": {typ: doc}}
    )
    if update_result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Patient not found")
    if update_result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Doctor reassignment failed")
    
    return {"message": "Doctor reassigned successfully", "patientID": patient_id, "newDoctorID": doc}

@app.get("/doctor/add-patient", response_class=HTMLResponse, dependencies=[Depends(cookie)])
async def add_patient_form(request: Request, session_data: SessionData = Depends(role_verifier("doctor"))):
    """Render the add patients page with form."""
    return templates.TemplateResponse("doctor/add_patient.html", {"request": request, "user": session_data.data})

@app.post("/doctor/add-patient", response_class=HTMLResponse, dependencies=[Depends(cookie)])
async def add_patient(patient: Patient, request: Request, session_data: SessionData = Depends(role_verifier("doctor"))):
    """Add a patient to database."""
    try:
        patient_data = patient.as_dict()
        patient_data["type"] = "Patient"
        patient_data["doctor"] = session_data.data["ID"]
        count = collection.count_documents({"type": "patient"})
        new_id = count + 1
        patient_id = f"PAT{new_id:05d}"
        result = collection.insert_one(patient_data)
        return {"message": "Success!"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/doctor/view-patient/{patient_id}", response_class=HTMLResponse, dependencies=[Depends(cookie)])
async def view_patient(patient_id: str, request: Request, session_data: SessionData = Depends(role_verifier("doctor"))):
    """Render the view patient page with the patient."""
    patient = collection.aggregate([
        {
            "$match": {
                "type": "Patient",
                "ID": patient_id  # Match the specific patient by their ID
            }
        },
        {
            "$lookup": {
                "from": "items",  # Join with the 'users' collection to get the doctor (caretaker)
                "localField": "caretaker",  # The patient's caretaker ID
                "foreignField": "ID",  # The doctor's ID
                "as": "caretaker_info"  # Output will be in the 'caretaker_info' array
            }
        },
        {
            "$unwind": "$caretaker_info"  # Flatten the 'caretaker_info' array to access the fields
        },
        {
            "$addFields": {
                "caretakerName": "$caretaker_info.fullName"  # Add the caretaker's full name to the patient document
            }
        }
    ])
    patient = list(patient)[0]
    return templates.TemplateResponse("doctor/view_patient.html", {"request": request, "patient": patient, "user": session_data.data,
                                            "chart_data":calculate_monthly_inr_average(patient.get("inr_reports")),
                                        "missed_doses": find_missed_doses(get_medication_dates(patient["therapy_start_date"], patient["dosage_schedule"])
                                                                        ,patient.get("taken_doses"))})

@app.post("/doctor/edit-dosage/{patient_id}", dependencies=[Depends(cookie)])
async def edit_dosage(patient_id: str, dosage: List[DosageSchedule], request: Request, session_data: SessionData = Depends(role_verifier("doctor"))):
    """Render the add patients page with form."""
    try:
        dosage = [i.as_dict() for i in dosage]
        result = collection.update_one({"type":"Patient", "ID":patient_id}, {"$set": {"dosage_schedule":dosage}})
        return {"message":"Success!"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/doctor/reports", response_class=HTMLResponse, dependencies=[Depends(cookie)])
async def view_reports(typ: str, request: Request, session_data: SessionData = Depends(role_verifier("doctor"))):
    """Render the add patients page with form."""
    if typ == "today":
        # Find patients with 'type' = 'Patient' and 'inr_reports' containing today's date
        query = {
            "type": "Patient"
        }
        results = collection.find(query)  # Replace 'patients' with your collection name
        
        # Prepare the response with patient name and matching INR report
        report_data = []
        for patient in results:
            # Check for reports with today's date
            for report in patient['inr_reports']:
                if report['date'].startswith(datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%Y-%m-%d")):  # Check if the date matches
                    report_data.append({
                        'patient_name': patient.get('name'),  # Assuming there's a 'name' field in patient
                        'inr_report': report
                    })
        
        return templates.TemplateResponse("doctor/view_reports.html", {"request": request, "user": session_data.data,
                                                                            "reports": report_data})

    else:
        # If type is a patient ID, find all reports for that specific patient
        query = {
            "type": "Patient",
            "ID": typ  # patient_type is treated as a patient ID
        }
        patient = collection.find_one(query)  # Fetch the specific patient

        if patient:
            reports = [{"patient_name":patient.get("name"), "inr_report":report} for report in patient["inr_reports"]]
            return templates.TemplateResponse("doctor/view_reports.html", {"request": request, "user": session_data.data,
                                                                            "reports": reports})
        else:
            return "Patient not found.."
    return templates.TemplateResponse("doctor/add_patient.html", {"request": request})

@app.get("/patient", response_class=HTMLResponse, dependencies=[Depends(cookie)])
async def patient_root(request: Request, session_data: SessionData = Depends(role_verifier("patient"))):
    """Render the view patient page to the patient."""
    return templates.TemplateResponse("patient/view_patient.html", {"request": request, "patient": session_data.data,
                                "chart_data":calculate_monthly_inr_average(session_data.data.get("inr_reports")),
                                "missed_doses": find_missed_doses(get_medication_dates(session_data.data["therapy_start_date"], session_data.data["dosage_schedule"])
                                                                ,session_data.data.get("taken_doses"))[-1:-11:-1]})

@app.get("/patient/update-inr", response_class=HTMLResponse, dependencies=[Depends(cookie)])
async def update_inr_form(request: Request, session_data: SessionData = Depends(role_verifier("patient"))):
    """Render the update my INR value page to the patient."""
    return templates.TemplateResponse("patient/update_inr.html", {"request": request, "patient": session_data.data})

@app.post("/patient/update-inr", response_class=HTMLResponse, dependencies=[Depends(cookie)])
async def update_inr_report(
            request: Request,
            inr_value: float = Form(...),
            location_of_test: str = Form(...),
            date: str = Form(...),
            file: UploadFile = File(...),
            session_data: SessionData = Depends(role_verifier("patient")),
        ):

    # Save the uploaded file
    file_path = f"static/patient_docs/{file.filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())

    # Convert INRReport to a dictionary and add file_path
    report_dict = {
        "inr_value": inr_value,
        "location_of_test": location_of_test,
        "date": date,
        "file_name": file.filename,
        "file_path": file_path,
        "type": "INR Report",
    }

    # Update the patient record in the database
    result = collection.update_one(
        {"type": "Patient", "ID": session_data.data["ID"]},
        {"$push": {"inr_reports": report_dict}}
    )

    if result.matched_count == 0:
        # Clean up the saved file if the patient is not found
        os.remove(file_path)
        raise HTTPException(status_code=404, detail="Patient not found")

    return JSONResponse(
        status_code=200,
        content={"message": "INR report added successfully", "report": report_dict}
    )

@app.get("/patient/report", response_class=HTMLResponse, dependencies=[Depends(cookie)])
async def patient_report_form(request: Request,
            session_data: SessionData = Depends(role_verifier("patient"))):
    report_type = request.query_params.get("type")
    type_to_message = {
        "lifestyleChanges": "Type your Lifestyle Changes Here",
        "otherMedication": "List the names of other medications you are taking",
        "sideEffects": "sideEffects",
        "prolongedIllness": "Provide details about your prolonged illness"
    }

    type_to_page = {
        "lifestyleChanges": "Report Lifestyle Changes",
        "otherMedication": "Report Other Medication",
        "sideEffects": "Report Side Effects",
        "prolongedIllness": "Report Prolonged Illness"
    }

    message = type_to_message.get(report_type, "Unknown report type")
    page = type_to_page.get(report_type, "Report")
    return templates.TemplateResponse("patient/report.html", {"request": request, "patient": session_data.data,
                                                            "message": message, "type":report_type, "page": page})

@app.post("/patient/report", dependencies=[Depends(cookie)])
async def submit_report(request: Request, typ: str = Form(None),
            field: str = Form(None), session_data: SessionData = Depends(role_verifier("patient"))):
    collection.update_one(
        {"type": "Patient", "ID": session_data.data["ID"]},
        {"$push": {typ: field}}
    )
    return RedirectResponse(url="/patient", status_code=302)

@app.get("/patient/take-dose", response_class=HTMLResponse, dependencies=[Depends(cookie)])
async def take_dose_form(request: Request, session_data: SessionData = Depends(role_verifier("patient"))):
    """Render the view patient page to the patient."""
    return templates.TemplateResponse("patient/take_dose.html", {"request": request, "patient": session_data.data,
                                "missed_doses": find_missed_doses(get_medication_dates(session_data.data["therapy_start_date"], session_data.data["dosage_schedule"])
                                                                ,session_data.data.get("taken_doses"))})

@app.post("/patient/take-dose", dependencies=[Depends(cookie)])
async def take_dose(date:str, request: Request, session_data: SessionData = Depends(role_verifier("patient"))):
    """Render the view patient page to the patient."""
    collection.update_one(
        {"type": "Patient", "ID": session_data.data["ID"]},
        {"$push": {"taken_doses": date}}
    )

    return {"message": "Success!"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)