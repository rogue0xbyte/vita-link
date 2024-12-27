from extensions import mongo
from bson.objectid import ObjectId
from bson.binary import Binary
import uuid, json, io

from flask import Flask, flash, redirect, render_template, request, session
from datetime import datetime, timedelta


app = Flask(__name__)

app.secret_key = "KrrrzPPghtfgSKbtJEQCTA"
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.permanent_session_lifetime = timedelta(minutes=5)

app.config['MONGO_URI'] = "mongodb+srv://flask-access:qwertyuiop@cardio.z2m3vrf.mongodb.net/app?retryWrites=true&w=majority"
mongo.init_app(app)

print("[MONGODB] CONNECTED")

dataset = mongo.db["dataset"]

a = dataset.find()

arr = []

for i in a:
    i.pop("_id")
    arr.append(i)

dumpster = (json.dumps(arr, indent=4))

with open("vita-dumpster.json","w") as dumpr:
	dumpr.write(dumpster)
'''
with open("sample_data.json") as dataset:
	for i in json.load(dataset):
		mongo.db.dataset.insert_one(i)
'''
