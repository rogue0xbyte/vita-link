from flask import Flask, flash, redirect, render_template, request, session, url_for, jsonify, send_file
from pymongo import MongoClient
from bson.objectid import ObjectId
from bson.binary import Binary
import uuid, json, io
import hashlib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import ssl, smtplib, hashlib, uuid
from werkzeug.utils import secure_filename

import os
import datetime as dt
from datetime import datetime, timedelta
app = Flask(__name__)

app.secret_key = "KrrrzPPghtfgSKbtJEQCTA"
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.permanent_session_lifetime = timedelta(minutes=15)

client = MongoClient("mongodb+srv://21z233:vitalink@db.rj56s.mongodb.net/?retryWrites=true&w=majority&appName=db")
db = client["db"]


#-----------FUNCTIONS-----------------

def addDoctor(cat, id, name, password):
    password.replace("\n", "")
    passHash = hashlib.sha512(password.encode('utf-8')).hexdigest()
    doctor = {'type': "Doctor", 'category': cat, 'ID': id, 'fullName': name, 'PassHash': passHash, "PFP":"/static/images/empty_user.jpg","patients":[]}
    db["dataset"].insert_one(doctor)
    print("addition done")
    return doctor

def addIT(id, name, password):
    password.replace("\n", "")
    passHash = hashlib.sha512(password.encode('utf-8')).hexdigest()
    doctor = {'type': "IT", "category":"IT", 'ID': id, 'fullName': name, 'PassHash': passHash, "PFP":"/static/images/empty_user.jpg"}
    db["dataset"].insert_one(doctor)
    return doctor

def removeUser(_id):
    db["dataset"].delete_one({"_id": ObjectId(str(_id))})


def addPatient(Name, History, Contact, Kin, Kin_cont, age, gener, ID, therapy, strength, bf, af, mor, after, night, days, docs=[], StartDate='', TargetINR='0 - 0'):
    # History format: [{"from":"Month YYYY", "to": "Month YYYY", "condition": "Describe"}]
    patient = {"type":"Patient", "Name": Name, "Contact": Contact,"Kin name": Kin,"Kin Contact": Kin_cont,"Age": age,"Gender": gener,"Patient ID": ID, "Drug":{"type": therapy, "strength": strength, "before_food": bf, "after_food":af, "morning":mor, "afternoon":after, "night":night, "days":days},
                "medical_history": History, "inr_levels":[], "reports": [], "misdose-alert": False,
                "dosages": [], "next_test_date": "UNSCHEDULED", "start_date": StartDate, "target_inr":TargetINR}
    db["dataset"].insert_one(patient)
    for i in docs:
        patients = db["dataset"].find_one({"ID": i}).get("patients")
        if patients==None: patients=[]
        patients.append(ID)
        db["dataset"].update_one({"ID": i}, {"$set": {"patients": patients}})
    return patient

def assignCaretaker(patientID, docID):
    patients = db["dataset"].find_one({"ID": docID}).get("patients")
    if patients==None: patients=[]

    # patient = db["dataset"].find_one({"Patient ID":patientID})
    # caretakers = db["dataset"].find({"type":"Doctor"})
    # caretaker = {"fullName":"Unassigned"}
    # for j in caretakers:
    #     if (i in list(j.get("patients"))) and j.get("ID")!=json.loads(session.get("user")).get("ID"):
    #         caretaker = j
    #         break
    # patient.update({"caretaker":caretaker})

    if patientID not in patients:
        patients.append(patientID)
        db["dataset"].update_one({"ID": docID}, {"$set": {"patients": patients}})
    return True

def addPatientReport(PID, repType, details):
    report = {"type": repType, # "side", "lifestyle" or "others"
              "details":details}
    reports = db["dataset"].find_one({"Patient ID": PID}).get("reports")
    reports.append(report)
    db["dataset"].update_one({"Patient ID": PID}, {"$set": {"reports": reports}})

def addDosage(PID, Drug, amt, Date, rmk=""): 
    dose = {"datetime": Date,
            "drug": Drug,
            "strength": amt,
            "remark": rmk}
    doses = db["dataset"].find_one({"Patient ID": PID}).get("dosages")
    doses.append(dose)
    db["dataset"].update_one({"Patient ID": PID}, {"$set": {"dosages": doses}})
    return dose  

def updateINR(PID, INR, datetimeValue=datetime.now().strftime("%Y-%m-%dT%H:%M:%SI")):
    INR.update({"datetime":datetimeValue})
    inr_levels = db["dataset"].find_one({"Patient ID": PID}).get("inr_levels")
    if inr_levels==None: inr_levels=[]
    inr_levels.append(INR)
    db["dataset"].update_one({"Patient ID": PID}, {"$set": {"inr_levels": inr_levels}})
    db["dataset"].update_one({"Patient ID": PID}, {"$set": {"next_test_date": "UNASSIGNED"}})
    return True

def listMissedDoses(PID):
    from datetime import datetime as myDT
    from datetime import timedelta as TD

    today = myDT.now().date()
    try:
        patient = db["dataset"].find_one({"_id": ObjectId(str(PID))})
    except:
        patient = db["dataset"].find_one({"Patient ID": (str(PID))})
    start_date = myDT.strptime(patient.get("start_date"), '%d %B \'%y').date()

    dayDelt = (today - start_date).days

    if (today - start_date).days >7:
        dayDelt = 8
        start_date = today - TD(days=8)

    dates = [(start_date + TD(days=i)).strftime("%d-%m-%y") for i in range(2,dayDelt+1)]
    doses = patient.get("dosages")

    for dosage in doses:
        dosedate = myDT.fromisoformat(dosage['datetime'].replace("I",""))
        dosage_date = dosedate.date()
        if dosage_date.strftime("%d-%m-%y") in dates:
            dates.remove(dosage_date.strftime("%d-%m-%y"))

    return dates


def getMyWeek():
    from datetime import datetime as myDT
    from datetime import timedelta as TD

    today = myDT.now().date()
    dayDelt = 8
    start_date = today - TD(days=8)

    dates = [(start_date + TD(days=i)).strftime("%d-%m-%y") for i in range(2,dayDelt+1)]

    return dates

def toggleMedSched(PID):
    now = datetime.now().strftime("%H:%M %d/%m/%y")
    if db["dataset"].find_one({"Patient ID": PID}).get("stopped"):
        db["dataset"].update_one({"Patient ID": PID}, {"$set": {"stopped": False}})
        drug = db["dataset"].find_one({"Patient ID": PID}).get("Drug")
        days = db["dataset"].find_one({"Patient ID": PID}).get("backup_days")
        drug["days"] = days
        db["dataset"].update_one({"Patient ID": PID}, {"$set": {"Drug": drug}})
        stopscheds = db["dataset"].find_one({"Patient ID": PID}).get("stopscheds")
        if stopscheds == None:
            stopscheds = []
        stopscheds.append({"datetime": now, "action": "Resumed Treatment"})
        db["dataset"].update_one({"Patient ID": PID}, {"$set": {"stopscheds": stopscheds}})

    else:
        drug = db["dataset"].find_one({"Patient ID": PID}).get("Drug")
        db["dataset"].update_one({"Patient ID": PID}, {"$set": {"backup_days": drug["days"]}})
        drug["days"] = []
        db["dataset"].update_one({"Patient ID": PID}, {"$set": {"Drug": drug}})
        db["dataset"].update_one({"Patient ID": PID}, {"$set": {"stopped": True}})
        stopscheds = db["dataset"].find_one({"Patient ID": PID}).get("stopscheds")
        if stopscheds == None:
            stopscheds = []
        stopscheds.append({"datetime": now, "action": "Stopped Treatment"})
        db["dataset"].update_one({"Patient ID": PID}, {"$set": {"stopscheds": stopscheds}})



#-------------------------------------

@app.route("/")
def index():
    if session.get("logged_in_as")=="doctor":
        return redirect(url_for("doctor_home"))
    if session.get("logged_in_as")=="it":
        return redirect(url_for("it_page"))
    return redirect("/login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        # Get username and password from form
        username = request.form.get("username")
        password = request.form.get("password")

        # Validate user
        doctors = db["dataset"].find({"type":"Doctor"})
        for i in doctors:
            if username==i["ID"] and str(hashlib.sha512(password.encode('utf-8')).hexdigest())==i["PassHash"]:
                session.clear()
                session["logged_in"] = True
                session["logged_in_as"] = "doctor"
                myUser = dict(i)
                myUser.pop("_id")
                session["user"] = json.dumps(myUser)
                return redirect(url_for("doctor_home"))

        it = db["dataset"].find({"type":"IT"})
        for i in it:
            if username==i["ID"] and str(hashlib.sha512(password.encode('utf-8')).hexdigest())==i["PassHash"]:
                session.clear()
                session["logged_in"] = True
                session["logged_in_as"] = "it"
                myUser = dict(i)
                myUser.pop("_id")
                session["user"] = json.dumps(myUser)
                return redirect(url_for("it_page"))

        dataset = list(db["dataset"].find())
        patients = [i for i in dataset if "Patient ID" in list(dict(i).keys())]
        for i in patients:
            mypass = str("".join(i["Contact"].split(" ")[1:])).strip()
            # print(mypass)
            mypass = str(hashlib.sha512(mypass.encode('utf-8')).hexdigest())
            if username==i["Patient ID"] and str(hashlib.sha512(password.encode('utf-8')).hexdigest())==mypass:
                session.clear()
                session["logged_in"] = True
                session["patient"] = True
                session["logged_in_as"] = "patient"
                myUser = dict(i)
                myUser.pop("_id")
                session["user"] = json.dumps(myUser)
                return redirect(url_for("patient_home"))

        else:
            return render_template("406.html",
                                    title="Invalid Login!",
                                    content="Incorrect username or password."),406

    return render_template("doctor/login.html")

@app.route("/doctor")
def doctor_home():
    if not session.get("user"): return redirect("/login")
    if json.loads(session.get("user")).get("category").lower() not in\
            ["cardiologist", "resident", "clinical pharmacist", "paramedical"]:
        return redirect("/login")
    menu = "higherMenu"
    if json.loads(session.get("user")).get("category").lower() not in ["cardiologist", "resident"]:
        menu = "lowerMenu"

    patients = db["dataset"].find_one({"ID": json.loads(session.get("user")).get("ID")}).get("patients")
    # print(patients)
    toRemovePatients = []
    myPatients = []
    for i in patients:
        patient = db["dataset"].find_one({"Patient ID":i})
        if patient == None:
            toRemovePatients.append(i)
            continue
        caretakers = db["dataset"].find({"type":"Doctor"})
        caretaker = {"fullName":"Unassigned"}
        for j in caretakers:
            if (i in list(j.get("patients"))) and j.get("ID")!=json.loads(session.get("user")).get("ID"):
                caretaker = j
                break
        patient.update({"caretaker":caretaker})
        print(patient["Patient ID"],patient["Name"])   
        myPatients.append(patient)
    rawPatients = list(db["dataset"].find_one({"ID": json.loads(session.get("user")).get("ID")}).get("patients"))
    if len(toRemovePatients)>0:
        for i in toRemovePatients:
            rawPatients.remove(i)
        rawPatients = set(list(rawPatients))
        db["dataset"].update_one({"ID": json.loads(session.get("user")).get("ID")}, {"$set": {"patients":rawPatients}})
    return render_template("doctor/view_patients.html", menu=menu, user=json.loads(session.get("user")), patients=myPatients)

@app.route("/doctor/table")
def doctor_table():
    if not session.get("user"): return redirect("/login")
    if json.loads(session.get("user")).get("category").lower() not in\
            ["cardiologist", "resident", "clinical pharmacist", "paramedical"]:
        return redirect("/login")
    menu = "higherMenu"
    if json.loads(session.get("user")).get("category").lower() not in ["cardiologist", "resident"]:
        menu = "lowerMenu"

    patients = db["dataset"].find_one({"ID": json.loads(session.get("user")).get("ID")}).get("patients")
    myPatients = []
    for i in patients:
        patient = db["dataset"].find_one({"Patient ID":i})
        patient.pop("_id")
        caretakers = db["dataset"].find({"type":"Doctor"})
        caretaker = {"fullName":"Unassigned"}
        for j in caretakers:
            if (i in list(j.get("patients"))) and j.get("ID")!=json.loads(session.get("user")).get("ID"):
                caretaker = j
                break
        patient.update({"caretaker":caretaker})
        myPatients.append(patient)
    return render_template("doctor/view_patient_table.html", menu=menu, user=json.loads(session.get("user")), patients=myPatients)

@app.route("/doctor/patient-reassign", methods=['POST'])
def patient_reassign():
    if not session.get("user"): return redirect("/login")
    if json.loads(session.get("user")).get("category").lower() not in\
            ["cardiologist", "resident", "clinical pharmacist", "paramedical"]:
        return redirect("/login")
    menu = "higherMenu"
    if json.loads(session.get("user")).get("category").lower() not in ["cardiologist", "resident"]:
        menu = "lowerMenu"

    
    if request.form.get("for"):
        session["reassign_for"] = request.form.get("for")
        doctors = db["dataset"].find({"type":"Doctor"})
        return render_template("doctor/view_avbl_doctors.html", menu=menu, doctors = doctors, user=json.loads(session.get("user")))
    if request.form.get("ID"):
        assignCaretaker(session.get("reassign_for"),request.form.get("ID"))
        return redirect(url_for('doctor_home'))

@app.route("/doctor/patient-specific-view/<id>")
def patient_specific_view(id):
    patID = id
    if not session.get("user"): return redirect("/login")
    if json.loads(session.get("user")).get("category").lower() not in\
            ["cardiologist", "resident", "clinical pharmacist", "paramedical"]:
        return redirect("/login")
    menu = "higherMenu"
    if json.loads(session.get("user")).get("category").lower() not in ["cardiologist", "resident"]:
        menu = "lowerMenu"

    patient = dict(db["dataset"].find_one({"Patient ID":id}))
    dosages = patient["inr_levels"]
    now = dt.datetime.now()
    start_date = patient["start_date"]
    three_months = False

    from datetime import datetime as myDT
    from datetime import timedelta as TD

    input_date = myDT.strptime(start_date, '%d %B \'%y')

    # Compute the current date
    current_date = myDT.now()

    # Compute the date interval between the input date and the current date
    interval = current_date - input_date

    # Check if the interval is at least 3 months
    if interval >= TD(days=90):
        three_months = True

    if patient["Drug"]["strength"]==0:
        three_months = False


    # Create an empty monthly dosage strength array
    monthly_dosage_strength = [0] * 12
    monthly_doses = [1] * 12

    # Iterate over the dosages list and add up the dosage strengths for each month
    for dosage in dosages:
        # Convert the datetime string to a datetime object
        dosedate = dt.datetime.fromisoformat(dosage['datetime'].replace("I",""))
        istchange = dt.timedelta(hours=5, minutes=30)
        dosedate = dosedate - istchange
        
        # Check if the dosage was taken within the last year
        if (now.year) == dosedate.year:
            # Calculate the month index for the dosage
            month_index = dosedate.month - 1
            
            # Add the dosage strength to the monthly total
            try:
                monthly_dosage_strength[month_index] += float(dosage["level"])
                monthly_doses[month_index] +=1
            except:
                monthly_dosage_strength[month_index] += 0
                monthly_doses[month_index] +=1
    for month_index in range(len(monthly_doses)):
        if monthly_doses[month_index]>1:
            monthly_doses[month_index] = monthly_doses[month_index]-1

    # Calculate the average monthly dosage strength
    num_months = len(monthly_dosage_strength)
    for i in range(num_months):
        monthly_dosage_strength[i] = monthly_dosage_strength[i] / monthly_doses[i]
    sides = []
    lifestyles = []
    other_meds = []
    prolonged = []
    for i in patient["reports"]:
        if i["type"] == "side":
            sides.append(i["details"])
        if i["type"] == "lifestyle":
            lifestyles.append(i.get("details"))
        if i["type"]=="others":
            other_meds.append(i.get("details"))
        if i["type"]=="prolonged":
            prolonged.append(i.get("details"))
    try:
        inr_level = patient["inr_levels"][-1]["level"]
    except:
        inr_level = 0
    stopscheds = [{"action":"None"}]
    try:
        lastStopScheds = patient["stopscheds"][-1].get("action")
    except:
        lastStopScheds = stopscheds[-1].get("action")
    myDays = [i[0] for i in patient["Drug"]["days"]]
    try:
        cum_dose = sum([float(i[-1]) for i in patient["Drug"]["days"]])
    except:
        cum_dose = "UNKNOWN"
    try:
        targ = float(patient["target_inr"])
    except:
        targ = (float(patient["target_inr"].split(" - ")[0]) + float(patient["target_inr"].split(" - ")[-1]))/2
    try:
        current_inr = float(inr_level)
    except:
        current_inr = 0
    return render_template("doctor/patient_specific_view.html", menu=menu, patient=patient,
            user=json.loads(session.get("user")),
            monthly_average_inr=monthly_dosage_strength,
            sides = ", ".join(sides),
            lifestyles = ", ".join(lifestyles),
            other_meds = ", ".join(other_meds),
            prolonged = ", ".join(prolonged),
            three_mo = three_months,
            current_inr = current_inr,
            target_inr = targ,
            lastStopScheds = lastStopScheds,
            missed = listMissedDoses(patID),
            week = getMyWeek(),
            myDays = myDays,
            cum_dose = cum_dose)


@app.route("/doctor/end-therapy/<PID>", methods=['POST', 'GET'])
def end_therapy(PID):
    if not session.get("user"): return redirect("/login")
    if json.loads(session.get("user")).get("category").lower() not in\
            ["cardiologist", "resident", "clinical pharmacist", "paramedical"]:
        return redirect("/login")
    menu = "higherMenu"
    if json.loads(session.get("user")).get("category").lower() not in ["cardiologist", "resident"]:
        menu = "lowerMenu"

    patient = dict(db["dataset"].find_one({"Patient ID":PID}))
    Drug = patient.get("Drug")
    if request.method=="GET":
        rzn = "3 Months Passed since Therapy Started"
    else:
        rzn = str(request.form.get("reason"))
    
    Drug["strength"] = 0
    db["dataset"].update_one({"Patient ID": PID}, {"$set": {"Drug": Drug, "StoppageReason": rzn}})

    return redirect(url_for('patient_specific_view', id=PID))



@app.route("/doctor/inr-level-reports/<PID>")
def inr_level_reports(PID):
    if not session.get("user"): return redirect("/login")
    if json.loads(session.get("user")).get("category").lower() not in\
            ["cardiologist", "resident", "clinical pharmacist", "paramedical"]:
        return redirect("/login")
    menu = "higherMenu"
    if json.loads(session.get("user")).get("category").lower() not in ["cardiologist", "resident"]:
        menu = "lowerMenu"

    return render_template("doctor/inr_uploads.html", menu=menu,
                    user=json.loads(session.get("user")),
                    patient = dict(db["dataset"].find_one({"Patient ID":PID})))

@app.route('/doctor/inr_report/<filename>')
def view_inr_filename(filename):
    return send_file(f'docs/inr/{filename}')

@app.route("/doctor/historic-dosage-and-mis-dosage-view/<id>")
def historic_dosage_and_mis_dosage_view(id):
    if not session.get("user"): return redirect("/login")
    if json.loads(session.get("user")).get("category").lower() not in\
            ["cardiologist", "resident", "clinical pharmacist", "paramedical"]:
        return redirect("/login")
    menu = "higherMenu"
    if json.loads(session.get("user")).get("category").lower() not in ["cardiologist", "resident"]:
        menu = "lowerMenu"

    Oid = str(dict(db["dataset"].find_one({"Patient ID":id})).get("_id"))

    return render_template("doctor/historic_dosage_and_mis_dosage_view.html", menu=menu,
                    user=json.loads(session.get("user")),
                    patient = dict(db["dataset"].find_one({"Patient ID":id})),
                    missedDoses = listMissedDoses(Oid))

@app.route("/doctor/assign-dosage/<id>", methods=["GET","POST"])
def assign_dosage(id):
    if not session.get("user"): return redirect("/login")
    if json.loads(session.get("user")).get("category").lower() not in\
            ["cardiologist", "resident", "clinical pharmacist", "paramedical"]:
        return redirect("/login")
    menu = "higherMenu"
    if json.loads(session.get("user")).get("category").lower() not in ["cardiologist", "resident"]:
        menu = "lowerMenu"

    if request.method=="GET":
        patient = dict(db["dataset"].find_one({"Patient ID":id}))
        dosages = patient["dosages"]
        now = dt.datetime.now()
        # Create an empty monthly dosage strength array
        monthly_dosage_strength = [0] * 12
        monthly_doses = [1] * 12

        # Iterate over the dosages list and add up the dosage strengths for each month
        for dosage in dosages:
            # Convert the datetime string to a datetime object
            dosedate = dt.datetime.fromisoformat(dosage['datetime'].replace("I",""))
            istchange = dt.timedelta(hours=5, minutes=30)
            dosedate = dosedate - istchange
            
            # Check if the dosage was taken within the last year
            if (now.year) == dosedate.year:
                # Calculate the month index for the dosage
                month_index = dosedate.month - 1
                
                # Add the dosage strength to the monthly total
                monthly_dosage_strength[month_index] += float(dosage["strength"])
                monthly_doses[month_index] +=1
        for month_index in range(len(monthly_doses)):
            if monthly_doses[month_index]>1:
                monthly_doses[month_index] = monthly_doses[month_index]-1

        # Calculate the average monthly dosage strength
        num_months = len(monthly_dosage_strength)
        for i in range(num_months):
            monthly_dosage_strength[i] = monthly_dosage_strength[i] / monthly_doses[i]
        sides = []
        lifestyles = []
        other_meds = []
        prolonged = []
        for i in patient["reports"]:
            if i["type"] == "side":
                sides.append(i["details"])
            if i["type"] == "lifestyle":
                lifestyles.append(i["details"])
            if i["type"]=="others":
                other_meds.append(i["details"])
            if i["type"]=="prolonged":
                prolonged.append(i["details"])
        myDays = [i[0] for i in patient["Drug"]["days"]]
        return render_template("doctor/assign_dosage.html", menu=menu, patient=patient,
                user=json.loads(session.get("user")),
                monthly_average_inr=monthly_dosage_strength,
                sides = ", ".join(sides),
                lifestyles = ", ".join(lifestyles),
                other_meds = ", ".join(other_meds),
                prolonged = ", ".join(prolonged),
                MON="MON" in myDays ,
                TUE="TUE" in myDays ,
                WED="WED" in myDays ,
                THU="THU" in myDays ,
                FRI="FRI" in myDays ,
                SAT="SAT" in myDays ,
                SUN="SUN" in myDays )
    else:
        patient = dict(db["dataset"].find_one({"Patient ID":id}))
        days = []
        def getbool(x):
            if x=="on":
                return True
            return False
        if getbool(request.form.get("MON")): days.append(["MON", request.form.get("MON-dose")])
        if getbool(request.form.get("TUE")): days.append(["TUE", request.form.get("TUE-dose")])
        if getbool(request.form.get("WED")): days.append(["WED", request.form.get("WED-dose")])
        if getbool(request.form.get("THU")): days.append(["THU", request.form.get("THU-dose")])
        if getbool(request.form.get("FRI")): days.append(["FRI", request.form.get("FRI-dose")])
        if getbool(request.form.get("SAT")): days.append(["SAT", request.form.get("SAT-dose")])
        if getbool(request.form.get("SUN")): days.append(["SUN", request.form.get("SUN-dose")])
        Drug = {"type": request.form["type"],
                "strength": '25',
                "before_food": getbool(request.form.get("before_food")),
                "after_food": getbool(request.form.get("after_food")),
                "morning": getbool(request.form.get("morning")),
                "afternoon": getbool(request.form.get("afternoon")),
                "night": getbool(request.form.get("night")),
                "days": days}
        db["dataset"].update_one({"Patient ID": id}, {"$set": {"Drug": Drug}})
        return redirect(url_for("patient_specific_view", id=id))

@app.route("/doctor/schedules", methods=['GET','POST'])
def doctor_schedules():
    if not session.get("user"): return redirect("/login")
    if json.loads(session.get("user")).get("category").lower() not in\
            ["cardiologist", "resident", "clinical pharmacist", "paramedical"]:
        return redirect("/login")
    menu = "higherMenu"
    if json.loads(session.get("user")).get("category").lower() not in ["cardiologist", "resident"]:
        menu = "lowerMenu"
    if request.method=='POST':
        date = (list(request.form.values())[0]).split("T")[0]
        time = (list(request.form.values())[0]).split("T")[-1]
        db["dataset"].update_one({"Patient ID": list(dict(request.form).keys())[0].split("-")[2]}, {"$set": {"next_test_date": f"{datetime.strptime(date , '%Y-%m-%d').strftime('%d-%b-%Y')} {time}"}})
        return redirect(url_for("doctor_schedules"))
    else:
        patients = db["dataset"].find_one({"ID": json.loads(session.get("user")).get("ID")}).get("patients")
        myPatients = []
        for i in patients:
            patient = db["dataset"].find_one({"Patient ID":i})
            patient.pop("_id")
            caretakers = db["dataset"].find({"type":"Doctor"})
            caretaker = {"fullName":"Unassigned"}
            for j in caretakers:
                if (i in list(j.get("patients"))) and j.get("ID")!=json.loads(session.get("user")).get("ID"):
                    caretaker = j
                    break
            patient.update({"caretaker":caretaker})
            myPatients.append(patient)
        return render_template("doctor/doctor_schedules.html", menu=menu, patients = myPatients, user=json.loads(session.get("user")))

@app.route("/doctor/new-patient-creation", methods=['GET', 'POST'])
def new_patient_creation():
    if not session.get("user"): return redirect("/login")
    if json.loads(session.get("user")).get("category").lower() not in\
            ["cardiologist", "resident"]:
        return redirect("/login")
    menu = "higherMenu"
    if json.loads(session.get("user")).get("category").lower() not in ["cardiologist", "resident"]:
        menu = "lowerMenu"

    if request.method=='GET':
        return render_template("doctor/new_patient_creation.html", menu=menu, user=json.loads(session.get("user")))
    else:
        dataset = db["dataset"].find()
        patients = [i for i in dataset if "Patient ID" in list(dict(i).keys())]
        counter = 0
        for i in patients:
            # print(i["Patient ID"][:9])
            if i["Patient ID"][:9]==f'{datetime.now().strftime("%y")}PAT{datetime.now().strftime("%m")}{datetime.now().strftime("%d")}':
                counter+=1
        def getbool(x):
            if x=="on":
                return True
            return False
        days = []
        if getbool(request.form.get("MON")): days.append(["MON", request.form.get("MON-dose")])
        if getbool(request.form.get("TUE")): days.append(["TUE", request.form.get("TUE-dose")])
        if getbool(request.form.get("WED")): days.append(["WED", request.form.get("WED-dose")])
        if getbool(request.form.get("THU")): days.append(["THU", request.form.get("THU-dose")])
        if getbool(request.form.get("FRI")): days.append(["FRI", request.form.get("FRI-dose")])
        if getbool(request.form.get("SAT")): days.append(["SAT", request.form.get("SAT-dose")])
        if getbool(request.form.get("SUN")): days.append(["SUN", request.form.get("SUN-dose")])
        drug = {"type": request.form["type"],
                "strength": 25,
                "before_food": getbool(request.form.get("before_food")),
                "after_food": getbool(request.form.get("after_food")),
                "morning": getbool(request.form.get("morning")),
                "evening": getbool(request.form.get("evening")),
                "night": getbool(request.form.get("night")),
                "days": days}
        user=json.loads(session.get("user"))
        history = []
        counter = 1
        for i,j in dict(request.form).items():
            if (("history" in i) and (str(counter) in i)):
                try:
                    durn = request.form.get(f"history-duration-{counter}")
                    new_object = {"duration":durn,
                                   "condition":request.form.get(f"history-text-{counter}")}
                    history.append(new_object)
                    counter+=1
                except:
                    pass
        counter = 0
        for i in patients:
            # print(i["Patient ID"], counter)
            # print(i["Patient ID"][:9], f'{datetime.now().strftime("%y")}PAT{datetime.now().strftime("%m")}{datetime.now().strftime("%d")}', i["Patient ID"][:9]==f'{datetime.now().strftime("%y")}PAT{datetime.now().strftime("%m")}{datetime.now().strftime("%d")}')
            if i["Patient ID"][:9]==f'{datetime.now().strftime("%y")}PAT{datetime.now().strftime("%m")}{datetime.now().strftime("%d")}':
                counter+=1
        date_str = request.form.get(f"start-date")
        date = datetime.strptime(date_str, "%Y-%m-%d")

        month = date.strftime("%B")
        day = date.strftime("%d")
        year = date.strftime("%y")

        start_date = f"{day} {month} '{year}"

        target_inr = f'{request.form.get("target-inr-fro")} - {request.form.get("target-inr-to")}'

        # print("\nName:",request.form.get("name"),
        #             "\nHistory:",history,
        #             "\nContact:",f'+91 {request.form.get("contact")[:5]} {request.form.get("contact")[5:]}',
        #             "\nKin:",request.form.get("kin-name"),
        #             "\nKin_cont:",request.form.get("kin-contact"),
        #             "\nage:",str(request.form.get("age")),
        #             "\ngener:",str(request.form.get("gender").upper()),
        #             "\nID:",f'{datetime.now().strftime("%y")}PAT{datetime.now().strftime("%m")}{datetime.now().strftime("%d")}{counter+1}',
        #             "\ntherapy:",drug["type"],
        #             "\nstrength:",drug["strength"],
        #             "\nbf:",drug["before_food"],
        #             "\naf:",drug["after_food"],
        #             "\nmor:",drug["morning"],
        #             "\nafter:",drug["evening"],
        #             "\nnight:",drug["night"],
        #             "\ndays:",days,
        #             "\ndocs:",[user["ID"]])
        addPatient(Name=request.form.get("name"),
                    History=history,
                    Contact=f'+91 {request.form.get("contact")[:5]} {request.form.get("contact")[5:]}',
                    Kin=request.form.get("kin-name"),
                    Kin_cont=request.form.get("kin-contact"),
                    age=str(request.form.get("age")),
                    gener=str(request.form.get("gender").upper()),
                    ID=f'{datetime.now().strftime("%y")}PAT{datetime.now().strftime("%m")}{datetime.now().strftime("%d")}{counter+1}',
                    therapy=drug["type"],
                    strength=drug["strength"],
                    bf=drug["before_food"],
                    af=drug["after_food"],
                    mor=drug["morning"],
                    after=drug["evening"],
                    night=drug["night"],
                    days=days,
                    docs=[user["ID"]],
                    StartDate = start_date,
                    TargetINR = target_inr)
        return redirect(url_for("doctor_home"))

@app.route("/doctor/update_inr", methods=['GET', 'POST'])
def doctor_update_inr():
    if not session.get("user"): return redirect("/login")
    if json.loads(session.get("user")).get("category").lower() not in\
            ["cardiologist", "resident", "clinical pharmacist", "paramedical", "lab personnel"]:
        return redirect("/login")
    menu = "higherMenu"
    if json.loads(session.get("user")).get("category").lower() not in ["cardiologist", "resident"]:
        menu = "lowerMenu"

    if request.method=='GET':
        return render_template("doctor/update_inr.html", menu=menu, user=json.loads(session.get("user")))
    else:
        PID = request.form.get("PID")
        INR = dict(request.form)
        INR.pop("PID")
        updateINR(PID, INR)
        if json.loads(session.get("user")).get("category").lower()=="lab personnel":
            return redirect(url_for("doctor_update_inr"))
        return redirect(url_for("patient_specific_view", id=PID))

@app.route("/inhouse-api/patient-details")
def patient_details():
    if not session.get("user"): return redirect("/login")
    if json.loads(session.get("user")).get("category").lower() not in\
            ["cardiologist", "resident", "clinical pharmacist", "paramedical", "lab personnel"]:
        return redirect("/login")
    return jsonify({"name": db["dataset"].find_one({"Patient ID":request.args.get("patientCode")})["Name"],
                    "age":  db["dataset"].find_one({"Patient ID":request.args.get("patientCode")})["Age"],
                    "gender":  db["dataset"].find_one({"Patient ID":request.args.get("patientCode")})["Gender"]})

@app.route("/it-personnel", methods=['POST','GET'])
def it_page():
    if not session.get("user"): return redirect("/login")
    if json.loads(session.get("user")).get("category").lower() not in\
            ["it"]:
        return redirect("/login")
    if request.method=='GET':
        users = db["dataset"].find()
        myUsers = []
        for i in users:
            if i.get("type"):
                if i.get("Patient ID"):
                    i["ID"] = i.get("Patient ID")
                i["role"] = i.get("type")
                if i.get("category"):
                    i["role"] = i.get("category")
                i["name"] = i.get("Name")
                if i.get("fullName"):
                    i["name"] = i.get("fullName")
                myUsers.append(i)
        return render_template("it/it_page.html", users=myUsers)
    else:
        if request.form.get("todo") == "addDoctor":
            patients = db["dataset"].find({"type":"Doctor"})
            counter = len(list(patients))+1
            addDoctor(request.form.get("categ"),f"DOC{counter:0>5}",request.form.get("name"),"password")
            return redirect(url_for("it_page"))
        elif request.form.get("todo") == "addIT":
            patients = db["dataset"].find({"type":"IT"})
            counter = len(list(patients))+1
            addIT(f"IT{counter:0>5}",request.form.get("name"),"password")
            return redirect(url_for("it_page"))

@app.route("/it-personnel/remove-user/<uid>", methods=['POST','GET'])
def remove_user(uid):
    if not session.get("user"): return redirect("/login")
    if json.loads(session.get("user")).get("category").lower() not in\
            ["it"]:
        return redirect("/login")
    removeUser(uid)
    return redirect(url_for("it_page"))

@app.route("/patient", methods=["GET"])
def patient_home():
    if not session.get("user"): return redirect("/login")
    # Check if the user is logged in as a patient
    if "patient" in session:

        # Render the Personal Details Page
        today = dt.date.today()
        date_range = [today - dt.timedelta(days=i) for i in range(7)]

        strengths = []
        dosages = json.loads(session.get("user"))["dosages"]
        for date in date_range:
            for dosage in dosages:
                dosedate = dt.datetime.fromisoformat(dosage['datetime'].replace("I",""))
                istchange = dt.timedelta(hours=5, minutes=30)
                dosedate = dosedate - istchange
                dosage_date = dosedate.date()
                # print(dosage_date,date)
                if dosage_date == date:
                    strengths.append(float(dosage['strength']))
                    break
            else:
                strengths.append(0)
        date_range = [str((today - dt.timedelta(days=i)).day) for i in range(7)]

        now = dt.datetime.now()

        # Create an empty monthly dosage strength array
        monthly_dosage_strength = [0] * 12
        monthly_doses = [1] * 12

        # Iterate over the dosages list and add up the dosage strengths for each month
        for dosage in dosages:
            # Convert the datetime string to a datetime object
            dosedate = dt.datetime.fromisoformat(dosage['datetime'].replace("I",""))
            istchange = dt.timedelta(hours=5, minutes=30)
            dosedate = dosedate - istchange
            
            # Check if the dosage was taken within the last year
            if (now.year) == dosedate.year:
                # Calculate the month index for the dosage
                month_index = dosedate.month - 1
                
                # Add the dosage strength to the monthly total
                monthly_dosage_strength[month_index] += float(dosage["strength"])
                monthly_doses[month_index] +=1
        for month_index in range(len(monthly_doses)):
            if monthly_doses[month_index]>1:
                monthly_doses[month_index] = monthly_doses[month_index]-1

        # Calculate the average monthly dosage strength
        num_months = len(monthly_dosage_strength)
        for i in range(num_months):
            monthly_dosage_strength[i] = monthly_dosage_strength[i] / monthly_doses[i]
        monthNames = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"
        ]
        week = f"{monthNames[now.month-1]} {date_range[-1]} - {monthNames[now.month-1]} {now.day}"
        return render_template("patient/dose_dashboard.html", user=json.loads(session.get("user")),
                                                              doses=str(strengths),
                                                              dates=str(date_range),
                                                              monthly_doses = str(monthly_dosage_strength),
                                                              week = week,
                                                              year = now.year,
                                                              missed = listMissedDoses(json.loads(session.get("user"))["Patient ID"]))
    else:
        # Redirect to the login page if the user is not logged in as a patient
        return redirect("/login")


@app.route("/patient/other-medication", methods=["GET", "POST"])
def other_medication():
    if not session.get("user"): return redirect("/login")
    # Check if the user is logged in as a patient
    if "patient" in session:
        if request.method=='POST':
            addPatientReport(json.loads(session.get("user"))["Patient ID"], "others", request.form.get("drug"))
            pat = db["dataset"].find_one({"Patient ID": json.loads(session.get("user"))["Patient ID"]})
            pat.update({"patient":True})
            session.clear()
            session["logged_in"] = True
            session["patient"] = True
            session["logged_in_as"] = "patient"
            pat.pop("_id")
            session["user"] = json.dumps(dict(pat))
        return render_template("patient/other_medication.html", user=json.loads(session.get("user")))
    else:
        # Redirect to the login page if the user is not logged in as a patient
        return redirect("/login")

@app.route("/patient/lifestyle-changes", methods=["GET", "POST"])
def lifestyle_changes():
    if not session.get("user"): return redirect("/login")
    # Check if the user is logged in as a patient
    if "patient" in session:
        if request.method=='POST':
            addPatientReport(json.loads(session.get("user"))["Patient ID"], "lifestyle", request.form.get("drug"))
            pat = db["dataset"].find_one({"Patient ID": json.loads(session.get("user"))["Patient ID"]})
            pat.update({"patient":True})
            session.clear()
            session["logged_in"] = True
            session["patient"] = True
            session["logged_in_as"] = "patient"
            pat.pop("_id")
            session["user"] = json.dumps(dict(pat))
        return render_template("patient/lifestyle_changes.html", user=json.loads(session.get("user")))
    else:
        # Redirect to the login page if the user is not logged in as a patient
        return redirect("/login")

@app.route("/patient/side-effects", methods=["GET", "POST"])
def side_effects():
    if not session.get("user"): return redirect("/login")
    # Check if the user is logged in as a patient
    if "patient" in session:
        if request.method=='POST':
            for i in list(dict(request.form).keys()):
                addPatientReport(json.loads(session.get("user"))["Patient ID"], "side", i)
            pat = db["dataset"].find_one({"Patient ID": json.loads(session.get("user"))["Patient ID"]})
            pat.update({"patient":True})
            session.clear()
            session["logged_in"] = True
            session["patient"] = True
            session["logged_in_as"] = "patient"
            pat.pop("_id")
            session["user"] = json.dumps(dict(pat))
        return render_template("patient/side_effects.html", user=json.loads(session.get("user")))
    else:
        # Redirect to the login page if the user is not logged in as a patient
        return redirect("/login")

@app.route("/patient/prolonged-illness", methods=["GET", "POST"])
def prolonged_illness():
    if not session.get("user"): return redirect("/login")
    # Check if the user is logged in as a patient
    if "patient" in session:
        if request.method=='POST':
            addPatientReport(json.loads(session.get("user"))["Patient ID"], "prolonged", request.form.get("drug"))
            pat = db["dataset"].find_one({"Patient ID": json.loads(session.get("user"))["Patient ID"]})
            pat.update({"patient":True})
            session.clear()
            session["logged_in"] = True
            session["patient"] = True
            session["logged_in_as"] = "patient"
            pat.pop("_id")
            session["user"] = json.dumps(dict(pat))
        return render_template("patient/prolonged_illness.html", user=json.loads(session.get("user")))
    else:
        # Redirect to the login page if the user is not logged in as a patient
        return redirect("/login")

@app.route("/patient/take-dose", methods=["GET", "POST"])
def take_dose():
    if not session.get("user"): return redirect("/login")
    # Check if the user is logged in as a patient
    if "patient" in session:

        if request.method=='POST':
            strength = request.form.get("strength")
            dosedate = dt.datetime.now()
            istchange = dt.timedelta(hours=5, minutes=30)
            dosedate = (dosedate - istchange).strftime("%Y-%m-%dT%H:%M:%SI")
            addDosage(json.loads(session.get("user"))["Patient ID"],json.loads(session.get("user"))["Drug"]["type"],strength,dosedate)
            pat = db["dataset"].find_one({"Patient ID": json.loads(session.get("user"))["Patient ID"]})
            pat.update({"patient":True})
            session.clear()
            session["logged_in"] = True
            session["patient"] = True
            session["logged_in_as"] = "patient"
            pat.pop("_id")
            session["user"] = json.dumps(dict(pat))
            # print(json.dumps(json.loads(session.get("user")),indent=4))

        now = dt.datetime.now().strftime('%d-%m-%y')
        md = listMissedDoses(json.loads(session.get("user"))["Patient ID"])

        # print(md)

        tdyComp = "true"

        try:
            md.remove(now)
            tdyComp = "false"
        except Exception as e:
            pass

        today = False
        tod = dt.datetime.now().strftime('%a').upper()
        myDays = [i[0] for i in json.loads(session.get("user"))["Drug"]["days"]]
        if tod in myDays:
            today = True

        return render_template("patient/take_dose.html", user=json.loads(session.get("user")),
                                                         missed_doses = md,
                                                         tdy = now,
                                                         tdyComp = tdyComp,
                                                         drug = json.loads(session.get("user"))["Drug"],
                                                         takeToday = today)
    else:
        # Redirect to the login page if the user is not logged in as a patient
        return redirect("/login")

@app.route("/patient/update_inr", methods=['GET', 'POST'])
def update_INR_pat():
    if not session.get("user"): return redirect("/login")
    

    if "patient" not in session: return redirect("/login")

    if request.method=='GET':
        return render_template("patient/update_inr.html", user=json.loads(session.get("user")))
    else:
        PID = json.loads(session.get("user")).get("Patient ID")
        INR = dict(request.form)
        files = os.listdir("docs/inr")
        filename = request.files["filename"].filename
        while filename in files:
            filename = str(uuid.uuid1()).split("-")[0] + "_" + secure_filename(request.files["filename"].filename).upper()
        INR["filename"] = filename
        request.files["filename"].save(f"docs/inr/{filename}")
        updateINR(PID, INR, datetime.now().strftime("%Y-%m-%dT%H:%M:%SI").replace(datetime.now().strftime("%Y-%m-%d"),request.form.get("datetime")))
        return redirect(url_for("patient_home", id=PID))

@app.route("/patient/stop-meds", methods=["GET", "POST"])
def stop_meds():
    if not session.get("user"): return redirect("/login")
    # Check if the user is logged in as a patient
    if "patient" in session:
        if request.method=='POST':
            toggleMedSched(json.loads(session.get("user"))["Patient ID"])
            pat = db["dataset"].find_one({"Patient ID": json.loads(session.get("user"))["Patient ID"]})
            pat.update({"patient":True})
            session.clear()
            session["logged_in"] = True
            session["patient"] = True
            session["logged_in_as"] = "patient"
            pat.pop("_id")
            session["user"] = json.dumps(dict(pat))
        return render_template("patient/stop_medic.html", user=json.loads(session.get("user")))
    else:
        # Redirect to the login page if the user is not logged in as a patient
        return redirect("/login")

@app.route("/patient/profile")
def patient_profile():
    if not session.get("user"): return redirect("/login")
    if "patient" not in session:
        return redirect("/login")

    patient = dict(db["dataset"].find_one({"Patient ID":json.loads(session.get("user"))["Patient ID"]}))
    dosages = patient["dosages"]
    now = dt.datetime.now()
    # Create an empty monthly dosage strength array
    monthly_dosage_strength = [0] * 12
    monthly_doses = [1] * 12

    # Iterate over the dosages list and add up the dosage strengths for each month
    for dosage in dosages:
        # Convert the datetime string to a datetime object
        dosedate = dt.datetime.fromisoformat(dosage['datetime'].replace("I",""))
        istchange = dt.timedelta(hours=5, minutes=30)
        dosedate = dosedate - istchange
        
        # Check if the dosage was taken within the last year
        if (now.year) == dosedate.year:
            # Calculate the month index for the dosage
            month_index = dosedate.month - 1
            
            # Add the dosage strength to the monthly total
            monthly_dosage_strength[month_index] += float(dosage["strength"])
            monthly_doses[month_index] +=1
    for month_index in range(len(monthly_doses)):
        if monthly_doses[month_index]>1:
            monthly_doses[month_index] = monthly_doses[month_index]-1

    # Calculate the average monthly dosage strength
    num_months = len(monthly_dosage_strength)
    for i in range(num_months):
        monthly_dosage_strength[i] = monthly_dosage_strength[i] / monthly_doses[i]
    sides = []
    lifestyles = []
    other_meds = []
    prolonged = []
    for i in patient["reports"]:
        if i["type"] == "side":
            sides.append(i["details"])
        if i["type"] == "lifestyle":
            lifestyles.append(i["details"])
        if i["type"]=="others":
            other_meds.append(i["details"])
        if i["type"]=="prolonged":
            prolonged.append(i["details"])
    try:
        inr_level = float(patient["inr_levels"][-1]["level"])
    except:
        inr_level = 0
    return render_template("patient/my_profile.html", patient=patient,
            user=json.loads(session.get("user")),
            monthly_average_inr=monthly_dosage_strength,
            sides = ", ".join(sides),
            lifestyles = ", ".join(lifestyles),
            other_meds = ", ".join(other_meds),
            prolonged = ", ".join(prolonged),
            current_inr = inr_level)

@app.errorhandler(404)
def page_not_found(e):
    # note that we set the 404 status explicitly
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    # note that we set the 50 status explicitly
    return render_template('500.html', error=str(e)), 500

if __name__ == "__main__":
    addDoctor("Cardiologist","DOC00001","Aaditya Rengarajan","password")
    addDoctor("Clinical Pharmacist","DOC00002","Subhasri Shreya S L","password")
    # dosages = [
    # {"datetime": "2023-01-15T08:00:00I", "drug": "Warfarin", "strength": "90", "remark": ""},
    # {"datetime": "2023-01-22T08:00:00I", "drug": "Warfarin", "strength": "92", "remark": ""},
    # {"datetime": "2023-02-05T08:00:00I", "drug": "Warfarin", "strength": "90", "remark": ""},
    # {"datetime": "2023-02-12T08:00:00I", "drug": "Warfarin", "strength": "90", "remark": ""}
    # ]

    # for i in dosages:
    #     addDosage("23PAT02052",i)
    app.run(
           host='0.0.0.0',
           port=3209
            )